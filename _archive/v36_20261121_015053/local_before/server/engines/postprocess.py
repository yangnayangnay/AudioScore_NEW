import json
import logging
from pathlib import Path

import numpy as np
import pretty_midi

log = logging.getLogger("muscriptor.post")

_RANGES = {
    "piano": (21, 108), "chromperc": (48, 96), "organ": (21, 96),
    "guitar": (40, 93), "bass": (28, 72), "strings": (36, 103),
    "brass": (46, 100), "sax": (48, 96), "pipe": (48, 100),
    "synth": (21, 108), "drums": None,
}
_PROG = {"piano": 0, "guitar": 24, "bass": 33, "strings": 48,
         "brass": 56, "sax": 65, "pipe": 73, "organ": 16}
_VALID = ("dedup", "frag", "vel", "harmonic", "quant", "split", "fit", "meter",
          "rest", "onsnap", "decay", "dyn", "dur", "dtw")


def _family(prog, is_drum):
    if is_drum:
        return "drums"
    if prog < 8:
        return "piano"
    if prog < 16:
        return "chromperc"
    if prog < 24:
        return "organ"
    if prog < 32:
        return "guitar"
    if prog < 40:
        return "bass"
    if prog < 56:
        return "strings"
    if prog < 64:
        return "brass"
    if prog < 72:
        return "sax"
    if prog < 80:
        return "pipe"
    return "synth"


def _merge_fragments(notes, merge_gap, min_len):
    notes = sorted(notes, key=lambda n: n.start)
    out = []
    for n in notes:
        if out and out[-1].pitch == n.pitch and n.start - out[-1].end <= merge_gap:
            out[-1].end = max(out[-1].end, n.end)
            continue
        out.append(n)
    return [n for n in out if (n.end - n.start) >= min_len]


def _range_report(inst):
    fam = _family(inst.program, inst.is_drum)
    rng = _RANGES.get(fam)
    if not rng:
        return fam, 0, 0
    lo, hi = rng
    total = len(inst.notes)
    bad = sum(1 for n in inst.notes if n.pitch < lo or n.pitch > hi)
    return fam, bad, total


def _flags(post, cfg):
    if post is None:
        fl = set()
        for k in _VALID:
            if cfg.get(k, False):
                fl.add(k)
        if cfg.get("dedup", True):
            fl.add("dedup")
        if cfg.get("frag", True):
            fl.add("frag")
        return fl
    s = str(post).strip().lower()
    if s in ("", "0", "off", "false", "none"):
        return set()
    return {x.strip() for x in s.split(",") if x.strip() in _VALID}


def _load_audio(audio_path, parent_log, tag):
    try:
        import librosa
    except Exception as e:
        parent_log.warning("%s: librosa unavailable (%s)", tag, e)
        return None, None
    try:
        return librosa.load(str(audio_path), mono=True, sr=22050)
    except Exception as e:
        parent_log.warning("%s: audio load failed (%s)", tag, e)
        return None, None


def _rebuild_velocity(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "velocity rebuild")
    if y is None:
        return
    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    if rms.size == 0:
        return
    lr = np.log10(rms + 1e-8)
    lo, hi = np.percentile(lr, 5), np.percentile(lr, 95)
    span = max(float(hi - lo), 1e-6)
    fps = sr / hop
    cnt = 0
    for inst in pm.instruments:
        for n in inst.notes:
            a = max(int(n.start * fps), 0)
            b = min(int(n.end * fps), rms.size - 1)
            if a >= rms.size:
                a = rms.size - 1
            if b < a:
                b = a
            v = int(20 + 107 * min(1.0, max(0.0, (float(lr[a:b + 1].mean()) - lo) / span)))
            n.velocity = max(20, min(127, v))
            cnt += 1
    parent_log.info("velocity rebuild: %d notes re-velocitied", cnt)


def _harmonic_reassign(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "harmonic reassign")
    if y is None:
        return
    mel = [i for i in pm.instruments if not i.is_drum and len(i.notes) >= 8]
    if len(mel) < 2:
        parent_log.info("harmonic reassign: <2 melodic tracks - skipped")
        return
    hop = 512
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)) + 1e-9
    fps = sr / hop

    def prof(inst):
        vecs = []
        for n in inst.notes[:80]:
            a = int(n.start * fps)
            b = max(int(n.end * fps), a + 1)
            seg = S[:, a:min(b, S.shape[1])]
            if seg.size:
                vecs.append(seg.mean(axis=1))
        if not vecs:
            return None
        v = np.mean(vecs, axis=0)
        return v / (np.linalg.norm(v) + 1e-9)

    profiles = {id(i): prof(i) for i in mel}
    moved = 0
    for inst in mel:
        if profiles[id(inst)] is None:
            continue
        for n in list(inst.notes):
            a = int(n.start * fps)
            b = max(int(n.end * fps), a + 1)
            seg = S[:, a:min(b, S.shape[1])]
            if not seg.size:
                continue
            v = seg.mean(axis=1)
            v /= (np.linalg.norm(v) + 1e-9)
            sims = {id(i): float(np.dot(v, profiles[id(i)]))
                    for i in mel if profiles[id(i)] is not None}
            best = max(sims, key=sims.get)
            if best != id(inst) and sims[best] - sims[id(inst)] > 0.15:
                bi = next(i for i in mel if id(i) == best)
                inst.notes.remove(n)
                bi.notes.append(n)
                moved += 1
    parent_log.info("harmonic reassign: %d notes moved", moved)


def _fit_score(onsets, step):
    a = np.asarray(onsets)
    k = np.round(a / step)
    tol = min(step * 0.25, 0.045)
    return float((np.abs(a - k * step) <= tol).mean())


def _fit_tempo_solve(pm, bpm, parent_log):
    """speed->fit: grid adherence for a given bpm.
    fit->speed: candidates = ui bpm +/-4 fine + octave checks + IOI histogram
    seeds; each scored on 16th and 8th grids; best wins."""
    onsets = [n.start for i in pm.instruments if not i.is_drum for n in i.notes]
    if len(onsets) < 16:
        parent_log.info("fit-tempo: <16 notes - skipped")
        return {"bpm": float(bpm or 0)}
    center = 0.0
    try:
        center = float(bpm or 0)
    except Exception:
        center = 0.0
    cands = set()
    if 30 <= center <= 240:
        cands |= {round(center + k * 0.25, 2) for k in range(-16, 17)}
        cands |= {round(center / 2, 2), round(center * 2, 2)}
    o = np.sort(np.asarray(onsets))
    ioi = np.diff(o)
    ioi = ioi[(ioi > 0.05) & (ioi < 2.0)]
    if ioi.size:
        med = float(np.median(ioi))
        for mult in (0.5, 1.0, 2.0, 4.0):
            b = round(60.0 / (med * mult), 1)
            if 30 <= b <= 240:
                cands.add(b)
    if not cands:
        cands = {round(60.0 + i * 0.5, 1) for i in range(0, 241)}
    cands = {c for c in cands if 30 <= c <= 240}
    ui_fit = _fit_score(onsets, 60.0 / center / 4.0) if center > 0 else 0.0
    best_b, best_f, best_g = center, ui_fit, "16th"
    for c in cands:
        f16 = _fit_score(onsets, 60.0 / c / 4.0)
        f8 = _fit_score(onsets, 60.0 / c / 2.0)
        f, g = f16, "16th"
        if f8 > f16 + 0.03:
            f, g = f8, "8th"
        if f > best_f:
            best_b, best_f, best_g = c, f, g
    parent_log.info("fit-tempo: speed->fit ui_bpm=%.2f fit=%.0f%% | "
                    "fit->speed solved_bpm=%.2f fit=%.0f%% grid=%s cands=%d",
                    center, ui_fit * 100, best_b, best_f * 100, best_g, len(cands))
    return {"bpm": best_b, "ui_bpm": center,
            "ui_fit": round(ui_fit * 100, 1),
            "fit": round(best_f * 100, 1), "grid": best_g}


def _grid_quantize(pm, bpm, parent_log):
    b = 0.0
    try:
        b = float(bpm or 0)
    except Exception:
        b = 0.0
    if b <= 0:
        try:
            b = float(pm.estimate_tempo())
        except Exception:
            b = 0.0
    if b <= 0:
        parent_log.info("grid quantize: no bpm - skipped")
        return
    step = 60.0 / b / 4.0
    moved = 0
    for inst in pm.instruments:
        for n in inst.notes:
            s2 = round(n.start / step) * step
            e2 = round(n.end / step) * step
            if e2 <= s2:
                e2 = s2 + step
            if abs(n.start - s2) > 1e-4 or abs(n.end - e2) > 1e-4:
                n.start = max(0.0, s2)
                n.end = e2
                moved += 1
    parent_log.info("grid quantize: bpm=%.2f step=%dms, %d notes snapped",
                    b, int(step * 1000), moved)


def _detect_meter(pm, bpm, parent_log):
    """velocity-weighted onset envelope folded by 2/3/4/6 beat cycles;
    highest downbeat contrast wins; TimeSignature written into MIDI."""
    b = 0.0
    try:
        b = float(bpm or 0)
    except Exception:
        b = 0.0
    if b <= 0:
        try:
            b = float(pm.estimate_tempo())
        except Exception:
            b = 0.0
    if b <= 0:
        parent_log.info("meter: no bpm - skipped")
        return {"meter": None}
    beat = 60.0 / b
    dur = max((n.end for i in pm.instruments for n in i.notes), default=0.0)
    nb = int(dur / beat)
    if nb < 12:
        parent_log.info("meter: too short (%d beats) - skipped", nb)
        return {"meter": None}
    fps = 100
    T = int(dur * fps) + 1
    env = np.zeros(T)
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            idx = int(n.start * fps)
            if 0 <= idx < T:
                env[idx] += max(0.2, n.velocity / 127.0)
    acc = np.array([env[int(k * beat * fps):int((k + 1) * beat * fps)].sum()
                    for k in range(nb)])
    best_m, best_c = 4, -1.0
    for m in (2, 3, 4, 6):
        if len(acc) < m * 4:
            continue
        prof = np.array([acc[i::m].mean() for i in range(m)])
        rest = prof[1:].mean() if m > 1 else 0.0
        contrast = (prof[0] - rest) / (prof.mean() + 1e-9)
        parent_log.info("meter candidate bar=%d beats: contrast %.3f", m, contrast)
        if contrast > best_c:
            best_m, best_c = m, contrast
    parent_log.info("meter detect: %d/4 (contrast %.3f, bpm %.2f)", best_m, best_c, b)
    try:
        pm.time_signature_changes = [
            pretty_midi.TimeSignature(numerator=best_m, denominator=4, time=0.0)]
    except Exception as e:
        parent_log.warning("meter: write signature failed (%s)", e)
    return {"meter": "%d/4" % best_m, "meter_contrast": round(best_c, 3)}


def _voice_split(pm, parent_log):
    from statistics import median
    added = []
    for inst in list(pm.instruments):
        if inst.is_drum or len(inst.notes) < 24:
            continue
        pitches = [n.pitch for n in inst.notes]
        cut = median(pitches) - 7
        lo = [n for n in inst.notes if n.pitch < cut]
        hi = [n for n in inst.notes if n.pitch >= cut]
        if len(lo) < 8 or len(hi) < 8 or max(pitches) - min(pitches) < 24:
            continue
        inst.notes = hi
        ni = pretty_midi.Instrument(program=inst.program, is_drum=False,
                                    name=((inst.name or "track") + "-low")[:30])
        ni.notes = lo
        added.append(ni)
        parent_log.info("voice split: '%s' -> %d upper + %d lower",
                        inst.name or "track", len(hi), len(lo))
    pm.instruments.extend(added)


def _rest_preserve(pm, parent_log):
    GAP = 0.6
    evs = sorted((n.start, n.end) for i in pm.instruments for n in i.notes)
    if not evs:
        return
    gaps = []
    cur_end = evs[0][1]
    for s2, e2 in evs[1:]:
        if s2 - cur_end >= GAP:
            gaps.append((cur_end, s2))
        cur_end = max(cur_end, e2)
    trimmed = 0
    for inst in pm.instruments:
        for n in inst.notes:
            for gs, ge in gaps:
                if n.start < gs - 0.05 and n.end > gs + 0.05:
                    n.end = gs + 0.05
                    trimmed += 1
                    break
    parent_log.info("rest preserve: %d silence gaps, %d crossing notes trimmed",
                    len(gaps), trimmed)


def _onset_snap(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "onset snap")
    if y is None:
        return
    ons = librosa.onset.onset_detect(y=y, sr=sr, hop_length=512,
                                     units="time", backtrack=False)
    if ons.size == 0:
        return
    ons = np.sort(ons)
    TOL = 0.05
    moved = 0
    for inst in pm.instruments:
        for n in inst.notes:
            j = int(np.searchsorted(ons, n.start))
            cands = []
            if j > 0:
                cands.append(ons[j - 1])
            if j < len(ons):
                cands.append(ons[j])
            if not cands:
                continue
            best = min(cands, key=lambda t: abs(float(t) - n.start))
            if abs(float(best) - n.start) <= TOL:
                dur = n.end - n.start
                n.start = float(best)
                n.end = n.start + dur
                moved += 1
    parent_log.info("onset snap: %d notes aligned (tol %dms)", moved, int(TOL * 1000))


def _decay_aware(pm, parent_log):
    FAST = {"piano", "guitar", "bass", "chromperc"}
    SUST = {"strings", "brass", "sax", "pipe", "organ"}
    capped = merged = 0
    for inst in pm.instruments:
        fam = _family(inst.program, inst.is_drum)
        if fam in FAST:
            durs = sorted((n.end - n.start) for n in inst.notes)
            if len(durs) < 8:
                continue
            med = durs[len(durs) // 2]
            cap = max(med * 2.0, 0.5)
            for n in inst.notes:
                if n.end - n.start > cap:
                    n.end = n.start + cap
                    capped += 1
        elif fam in SUST:
            ns = sorted(inst.notes, key=lambda n: n.start)
            out = []
            for n in ns:
                if out and out[-1].pitch == n.pitch and \
                        0 <= n.start - out[-1].end <= 0.15:
                    out[-1].end = n.end
                    merged += 1
                    continue
                out.append(n)
            inst.notes = out
    parent_log.info("decay aware: %d capped, %d merged", capped, merged)


def _dyn_threshold(pm, parent_log):
    vels = [n.velocity for i in pm.instruments for n in i.notes]
    if len(vels) < 20:
        return
    lo = float(np.percentile(vels, 10))
    hi = float(np.percentile(vels, 90))
    if hi - lo < 20:
        parent_log.info("dyn thresh: no dynamic layering")
        return
    floor = lo + 0.15 * (hi - lo)
    removed = 0
    for inst in pm.instruments:
        keep = [n for n in inst.notes if n.velocity >= floor]
        removed += len(inst.notes) - len(keep)
        inst.notes = keep
    parent_log.info("dyn thresh: floor=%.0f, %d dropped", floor, removed)


def _duration_normalize(pm, bpm, parent_log):
    b = 0.0
    try:
        b = float(bpm or 0)
    except Exception:
        b = 0.0
    if b <= 0:
        try:
            b = float(pm.estimate_tempo())
        except Exception:
            b = 0.0
    if b <= 0:
        return
    beat = 60.0 / b
    DURS = [beat / 4, beat / 3, beat / 2, beat * 2 / 3, beat,
            beat * 1.5, beat * 2, beat * 3, beat * 4]
    snapped = 0
    for inst in pm.instruments:
        for n in inst.notes:
            d = n.end - n.start
            best = min(DURS, key=lambda x: abs(x - d))
            if d > 0 and abs(best - d) / d < 0.18:
                n.end = n.start + best
                snapped += 1
    parent_log.info("duration norm: %d durations snapped (bpm %.1f)", snapped, b)


def _dtw_diag(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "dtw diag")
    if y is None:
        return
    ons = librosa.onset.onset_detect(y=y, sr=sr, hop_length=512,
                                     units="time", backtrack=False)
    starts = sorted(n.start for i in pm.instruments
                    if not i.is_drum for n in i.notes)
    if ons.size < 5 or len(starts) < 5:
        return
    A = np.asarray(ons[:400])
    B = np.asarray(starts[:400])
    n, m = len(A), len(B)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = abs(float(A[i - 1]) - float(B[j - 1]))
            D[i, j] = c + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    devs = []
    i, j = n, m
    while i > 0 and j > 0:
        devs.append(abs(float(A[i - 1]) - float(B[j - 1])))
        step = int(np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]]))
        if step == 0:
            i -= 1; j -= 1
        elif step == 1:
            i -= 1
        else:
            j -= 1
    mean_dev = float(np.mean(devs)) if devs else 0.0
    med_dev = float(np.median(devs)) if devs else 0.0
    parent_log.info("dtw diag: mean=%.0fms median=%.0fms %s",
                    mean_dev * 1000, med_dev * 1000,
                    "(good sync)" if mean_dev < 0.08 else "(sync drift)")


def run_postprocess(mid_path, cfg, parent_log, audio_path=None, flags=None, bpm=None):
    fl = _flags(flags, cfg)
    if not fl:
        parent_log.info("postprocess: OFF (no flags)")
        return
    merge_gap = float(cfg.get("merge_gap", 0.08))
    min_note = float(cfg.get("min_note", 0.06)) if "frag" in fl else 0.0
    iso_min = int(cfg.get("isolated_min_notes", 3))
    range_fix = bool(cfg.get("range_fix", False))

    pm = pretty_midi.PrettyMIDI(str(mid_path))
    log.info("---- postprocess start: flags=%s", ",".join(sorted(fl)))

    for i, inst in enumerate(pm.instruments):
        before = len(inst.notes)
        if "dedup" in fl:
            inst.notes = _merge_fragments(inst.notes, merge_gap, 0.0)
        if min_note > 0:
            inst.notes = [n for n in inst.notes if (n.end - n.start) >= min_note]
        if before != len(inst.notes):
            log.info("track %02d hygiene: %d -> %d notes", i, before, len(inst.notes))

    if "dyn" in fl:
        _dyn_threshold(pm, log)

    res = {}
    eff_bpm = bpm
    if "fit" in fl:
        fit = _fit_tempo_solve(pm, bpm, log)
        eff_bpm = fit.get("bpm", eff_bpm)
        res.update(fit)
    if "onsnap" in fl and audio_path:
        _onset_snap(pm, audio_path, log)
    if "quant" in fl:
        _grid_quantize(pm, eff_bpm, log)
    if "dur" in fl:
        _duration_normalize(pm, eff_bpm, log)
    if "decay" in fl:
        _decay_aware(pm, log)
    if "rest" in fl:
        _rest_preserve(pm, log)
    if "split" in fl:
        _voice_split(pm, log)
    if "meter" in fl:
        res.update(_detect_meter(pm, eff_bpm, log))

    for i, inst in enumerate(pm.instruments):
        fam, bad, total = _range_report(inst)
        if total and bad / total > 0.3:
            log.info("track %02d range WARN: %s %d/%d out of range", i, fam, bad, total)
            if range_fix and fam not in ("piano", "synth", "drums"):
                cands = []
                for f, rng in _RANGES.items():
                    if f == "drums":
                        continue
                    lo, hi = rng
                    cov = sum(1 for n in inst.notes if lo <= n.pitch <= hi)
                    cands.append((cov / total, f))
                cands.sort(reverse=True)
                bc, bf = cands[0]
                if bc > (1 - bad / total) + 0.3 and bf in _PROG:
                    log.info("track %02d range FIX: %s -> %s", i, fam, bf)
                    inst.program = _PROG[bf]

    if "dedup" in fl and len(pm.instruments) > 1:
        dom = max(pm.instruments, key=lambda x: len(x.notes))
        for inst in pm.instruments:
            if inst is dom or inst.is_drum:
                continue
            if 0 < len(inst.notes) < iso_min:
                log.info("isolated track FIX -> dominant track")
                dom.notes.extend(inst.notes)
                inst.notes = []

    pm.instruments = [x for x in pm.instruments if x.notes]

    fams = {_family(x.program, x.is_drum) for x in pm.instruments}
    fams.discard("drums")
    if len(fams) >= 6:
        log.info("coexistence WARN: %d families", len(fams))

    if "harmonic" in fl and audio_path:
        _harmonic_reassign(pm, audio_path, log)
    if "vel" in fl and audio_path:
        _rebuild_velocity(pm, audio_path, log)
    if "dtw" in fl and audio_path:
        _dtw_diag(pm, audio_path, log)

    pm.write(str(mid_path))
    if res:
        try:
            side = Path(str(mid_path)).with_suffix(".post.json")
            side.write_text(json.dumps(res, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            log.info("analysis sidecar -> %s (%s)", side.name, res)
        except Exception as e:
            log.warning("sidecar write failed (%s)", e)
    log.info("---- postprocess done: %d tracks remain", len(pm.instruments))
