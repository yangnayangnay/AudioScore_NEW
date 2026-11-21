# -*- coding: utf-8 -*-
"""pp9 fit-tempo mutual solver + pp10 meter detection (time signature).
Quantize (pp7) uses solved bpm when pp9 enabled."""
from pathlib import Path
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- 1. HTML: pp9/pp10 ----------
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
PP8 = ('\u58f0\u90e8\u5206\u79bb\uff08\u5355\u8f68\u62c6\u65cb\u5f8b/\u4f34\u594f '
       'Voice split\uff09</label></div>')
PP910 = (PP8 + '\n<div class="opt"><input type="checkbox" id="pp9"><label>'
         '\u8282\u62cd\u4e92\u89e3\uff08\u5951\u5408\u5ea6\u2194\u901f\u5ea6\u4e92\u63a8 '
         'Fit\u2194Tempo\uff09</label></div>\n'
         '<div class="opt"><input type="checkbox" id="pp10"><label>'
         '\u62cd\u53f7\u8bc6\u522b\uff084/4\u00b73/4\u00b76/8 \u5f3a\u62cd\u4f4d\u5206\u6790 '
         'Meter\uff09</label></div>')
if 'id="pp9"' in s:
    ok.append("html: pp9/pp10 [SKIP present]")
elif PP8 in s:
    s = s.replace(PP8, PP910, 1); ok.append("html: pp9/pp10 added")
else:
    fail.append("html: pp8 anchor missing")

if "pp10: 'meter'}" in s:
    ok.append("html: _OF [SKIP present]")
elif "pp7: 'quant', pp8: 'split'}" in s:
    s = s.replace("pp7: 'quant', pp8: 'split'}",
                  "pp7: 'quant', pp8: 'split', pp9: 'fit', pp10: 'meter'}", 1)
    ok.append("html: _OF extended")
else:
    fail.append("html: _OF anchor missing")

if "'pp9','pp10'" in s.replace(" ", ""):
    ok.append("html: PPS persist [SKIP present]")
elif "pp7','pp8'];" in s.replace(" ", "") or "'pp8'];" in s:
    s2 = s.replace("'pp8'];", "'pp8','pp9','pp10'];", 1)
    if s2 != s:
        s = s2; ok.append("html: PPS persist extended")
    else:
        fail.append("html: PPS array pattern mismatch")
else:
    fail.append("html: PPS array anchor missing")
HP.write_text(s, encoding="utf-8")

# ---------- 2. engine: extend pipeline flag sets ----------
ENG = ROOT / "server" / "engines" / "muscriptor.py"
es = ENG.read_text(encoding="utf-8")
OLD = '{"dedup", "frag", "vel", "harmonic", "quant", "split"}'
NEW = '{"dedup", "frag", "vel", "harmonic", "quant", "split", "fit", "meter"}'
if NEW in es:
    ok.append("engine: pipeline sets [SKIP present]")
elif OLD in es:
    n = es.count(OLD); es = es.replace(OLD, NEW)
    ok.append("engine: pipeline sets x%d" % n)
else:
    fail.append("engine: pipeline set anchor missing")
ENG.write_text(es, encoding="utf-8")

# ---------- 3. postprocess.py full rewrite ----------
PP = ROOT / "server" / "engines" / "postprocess.py"
PP.write_text('''import logging
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
_VALID = ("dedup", "frag", "vel", "harmonic", "quant", "split", "fit", "meter")


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


def _rebuild_velocity(pm, audio_path, parent_log):
    try:
        import librosa
    except Exception as e:
        parent_log.warning("velocity rebuild: librosa unavailable (%s)", e)
        return
    try:
        y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
    except Exception as e:
        parent_log.warning("velocity rebuild: audio load failed (%s)", e)
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
    try:
        import librosa
    except Exception as e:
        parent_log.warning("harmonic reassign: librosa unavailable (%s)", e)
        return
    mel = [i for i in pm.instruments if not i.is_drum and len(i.notes) >= 8]
    if len(mel) < 2:
        parent_log.info("harmonic reassign: <2 melodic tracks - skipped")
        return
    try:
        y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
    except Exception as e:
        parent_log.warning("harmonic reassign: audio load failed (%s)", e)
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
    """Speed->fit direction: fraction of onsets near 16th-grid lines."""
    a = np.asarray(onsets)
    k = np.round(a / step)
    tol = min(step * 0.25, 0.045)
    return float((np.abs(a - k * step) <= tol).mean())


def _fit_tempo_solve(pm, bpm, parent_log):
    """Fit->speed direction: scan candidates, return bpm with best fit."""
    onsets = [n.start for i in pm.instruments if not i.is_drum for n in i.notes]
    if len(onsets) < 16:
        parent_log.info("fit-tempo: <16 notes - skipped")
        return float(bpm or 0)
    center = 0.0
    try:
        center = float(bpm or 0)
    except Exception:
        center = 0.0
    if 30 <= center <= 240:
        cands = [center + k * 0.25 for k in range(-16, 17)]
    else:
        cands = [60.0 + i * 0.5 for i in range(0, 241)]
    ui_fit = _fit_score(onsets, 60.0 / center / 4.0) if center > 0 else 0.0
    best_b, best_f = center, ui_fit
    for c in cands:
        if c < 30 or c > 240:
            continue
        f = _fit_score(onsets, 60.0 / c / 4.0)
        if f > best_f:
            best_b, best_f = c, f
    delta = (best_f - ui_fit) * 100
    parent_log.info(
        "fit-tempo: speed->fit ui_bpm=%.2f fit=%.0f%% | fit->speed solved_bpm=%.2f fit=%.0f%% (%+.0fpt)",
        center, ui_fit * 100, best_b, best_f * 100, delta)
    if abs(best_b - center) > 0.5 and delta > 5:
        parent_log.info("fit-tempo: recommend solved bpm %.2f for quantize", best_b)
    return best_b


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
    """transformerOfMusic meter idea: fold beat accents by 2/3/4/6,
    highest downbeat-contrast wins; write TimeSignature into MIDI."""
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
        return
    beat = 60.0 / b
    dur = max((n.end for i in pm.instruments for n in i.notes), default=0.0)
    nb = int(dur / beat)
    if nb < 12:
        parent_log.info("meter: too short (%d beats) - skipped", nb)
        return
    fps = 100
    T = int(dur * fps) + 1
    env = np.zeros(T)
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            idx = int(n.start * fps)
            if 0 <= idx < T:
                env[idx] += 1
    acc = np.array([env[int(k * beat * fps):int((k + 1) * beat * fps)].sum()
                    for k in range(nb)])
    best_m, best_c = 4, -1.0
    for m in (2, 3, 4, 6):
        if len(acc) < m * 4:
            continue
        prof = np.array([acc[i::m].mean() for i in range(m)])
        rest = prof[1:].mean() if m > 1 else 0.0
        contrast = (prof[0] - rest) / (prof.mean() + 1e-9)
        parent_log.info("meter candidate bar=%d beats: downbeat contrast %.3f", m, contrast)
        if contrast > best_c:
            best_m, best_c = m, contrast
    parent_log.info("meter detect: %d/4 (contrast %.3f, bpm %.2f)", best_m, best_c, b)
    try:
        pm.time_signature_changes = [
            pretty_midi.TimeSignature(numerator=best_m, denominator=4, time=0.0)]
        parent_log.info("meter: TimeSignature %d/4 written into MIDI", best_m)
    except Exception as e:
        parent_log.warning("meter: write signature failed (%s)", e)


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

    eff_bpm = bpm
    if "fit" in fl:
        eff_bpm = _fit_tempo_solve(pm, bpm, log)
    if "quant" in fl:
        _grid_quantize(pm, eff_bpm, log)
    if "split" in fl:
        _voice_split(pm, log)
    if "meter" in fl:
        _detect_meter(pm, eff_bpm, log)

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
        log.info("coexistence WARN: %d families -> %s", len(fams), sorted(fams))

    if "harmonic" in fl and audio_path:
        _harmonic_reassign(pm, audio_path, log)
    if "vel" in fl and audio_path:
        _rebuild_velocity(pm, audio_path, log)

    pm.write(str(mid_path))
    log.info("---- postprocess done: %d tracks remain", len(pm.instruments))
''', encoding="utf-8")
ok.append("postprocess.py rewritten (+fit-tempo / meter)")

print()
print("==== PATCH RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("=======================")
py_compile.compile(str(ENG), doraise=True)
py_compile.compile(str(PP), doraise=True)
print("  syntax OK : engine + postprocess")
