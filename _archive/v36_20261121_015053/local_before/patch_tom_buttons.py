# -*- coding: utf-8 -*-
"""Add transformerOfMusic-derived feature buttons: demucs pipeline, smart scan,
harmonic reassignment. UI -> post flags -> engine."""
from pathlib import Path
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []


def rep(fname, alts, label, skip=None):
    p = ROOT / fname
    s = p.read_text(encoding="utf-8")
    if skip and skip in s:
        ok.append(label + " [SKIP]")
        return
    for old, new in alts:
        if old in s:
            p.write_text(s.replace(old, new, 1), encoding="utf-8")
            ok.append(label)
            return
    fail.append(label + " : anchor missing in " + fname)


# ---- 1. UI: three new checkboxes after pp3 ----
PP3 = ('<div class="opt"><input type="checkbox" id="pp3"><label>'
       '\u529b\u5ea6\u91cd\u5efa\uff08\u57fa\u4e8e\u539f\u59cb\u97f3\u9891\u80fd\u91cf\uff09</label></div>')
NEW3 = (PP3 + '\n'
        '<div class="opt"><input type="checkbox" id="pp4"><label>'
        '\u97f3\u8272\u9884\u5206\u79bb\uff08Demucs \u5206\u8f68\u8f6c\u5199 Stem split\uff09</label></div>\n'
        '<div class="opt"><input type="checkbox" id="pp5"><label>'
        '\u667a\u80fd\u4e50\u5668\u8bc6\u522b\uff08\u81ea\u52a8\u542c\u97f3\u9009\u4e50\u5668 Smart auto\uff09</label></div>\n'
        '<div class="opt"><input type="checkbox" id="pp6"><label>'
        '\u8c10\u6ce2\u91cd\u5206\u914d\uff08\u6309\u9891\u8c31\u6307\u7eb9\u7ea0\u6b63\u8f68\u9053 Harmonic fix\uff09</label></div>')
rep("web/index.html", [(PP3, NEW3)], "html: pp4/5/6 buttons", skip='id="pp4"')

rep("web/index.html", [
    ("_OF = {pp1: 'dedup', pp2: 'frag', pp3: 'vel'}",
     "_OF = {pp1: 'dedup', pp2: 'frag', pp3: 'vel', pp4: 'demucs', pp5: 'smart', pp6: 'harmonic'}"),
], "html: flags map extended", skip="pp6: 'harmonic'")

# ---- 2. engine: flag dispatch at transcribe start ----
rep("server/engines/muscriptor.py", [
    ('        inst_cli, inst_mode = self._resolve_instruments(instruments)\n',
     '        _flags = set(x.strip() for x in str(post or "").split(",") if x.strip())\n'
     '        if "smart" in _flags and not instruments:\n'
     '            try:\n'
     '                _si = self._smart_scan(audio_path, lg)\n'
     '            except Exception as _e:\n'
     '                lg.warning("smart scan failed: %s", _e)\n'
     '                _si = None\n'
     '            if _si:\n'
     '                instruments = _si\n'
     '                lg.info("smart scan -> instruments: %s", _si)\n'
     '        if "demucs" in _flags:\n'
     '            return self._demucs_pipeline(audio_path, out_mid_path, instruments,\n'
     '                                         bpm, tmo, _flags, lg)\n'
     '        inst_cli, inst_mode = self._resolve_instruments(instruments)\n'),
], "engine: smart scan + demucs dispatch", skip="_flags = set(")

# ---- 3. engine: two new methods ----
METHODS = '''    def _smart_scan(self, audio_path, lg):
        """transformerOfMusic entry 16-24: listen first, then constrain.
        YAMNet when TF present; spectral heuristic fallback otherwise."""
        try:
            import tensorflow_hub as hub
            import numpy as np
            model = hub.load("https://tfhub.dev/google/yamnet/1")
            import librosa
            wav, _sr = librosa.load(str(audio_path), mono=True, sr=16000)
            scores, _, _ = model(wav)
            scores = scores.numpy().mean(axis=0)
            import csv, io, urllib.request
            url = ("https://raw.githubusercontent.com/tensorflow/models/"
                   "master/research/audioset/yamnet/yamnet_class_map.csv")
            names = [r["display_name"] for r in csv.DictReader(
                io.StringIO(urllib.request.urlopen(url).read().decode()))]
            pairs = sorted(zip(names, scores), key=lambda x: -x[1])[:12]
            lg.info("smart scan (yamnet) top: %s",
                    [(n, round(float(s), 2)) for n, s in pairs])
            LBL = {"piano": "piano", "guitar": "acoustic_guitar",
                   "bass guitar": "electric_bass", "drum": "drums",
                   "violin": "violin", "cello": "cello", "flute": "flutes",
                   "trumpet": "trumpet", "saxophone": "soprano_and_alto_sax",
                   "brass": "brass_section", "organ": "organ",
                   "singing": "voice"}
            out = []
            for nm, sc in pairs:
                if sc < 0.05:
                    continue
                low = nm.lower()
                for k, v in LBL.items():
                    if k in low and v not in out:
                        out.append(v)
            if out:
                return ",".join(out[:4])
            lg.warning("yamnet: no instrument label passed threshold")
        except Exception as e:
            lg.warning("yamnet unavailable (%s) -> heuristic scan", e)
        import librosa
        import numpy as np
        y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
        hop = 512
        onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
        dens = float((onset > np.percentile(onset, 75)).mean()) if onset.size else 0.0
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)) + 1e-9
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        low = float(S[(freqs >= 30) & (freqs <= 140)].mean())
        tot = float(S.mean()) + 1e-9
        out = []
        if dens > 0.18:
            out.append("drums")
        if low / tot > 1.15:
            out.append("electric_bass")
        if not out:
            out = ["piano"]
        lg.info("smart scan (heuristic): %s (onset_dens=%.2f low_ratio=%.2f)",
                ",".join(out), dens, low / tot)
        return ",".join(out)

    def _demucs_pipeline(self, audio_path, out_mid_path, instruments, bpm,
                         tmo, flags, lg):
        """transformerOfMusic timbre_split orchestrator: separate -> per-stem
        transcribe -> merge -> postprocess."""
        import copy as _copy
        import pretty_midi
        try:
            import demucs  # noqa: F401
        except ImportError:
            raise RuntimeError("demucs not installed -> run: pip install demucs")
        stems = {"vocals": "voice", "drums": "drums",
                 "bass": "electric_bass,acoustic_bass", "other": None}
        lg.info("---- demucs pipeline start (4 stems) ----")
        tmp = Path(out_mid_path).parent / ("_demucs_" + Path(out_mid_path).stem)
        tmp.mkdir(parents=True, exist_ok=True)
        sep = subprocess.run(
            [sys.executable, "-m", "demucs", "-n", "htdemucs",
             "-o", str(tmp), str(audio_path)],
            capture_output=True, text=True)
        if sep.returncode != 0:
            lg.error("demucs separation failed:\\n%s", (sep.stderr or "")[-800:])
            raise RuntimeError("demucs separation failed")
        base = tmp / "htdemucs" / Path(audio_path).stem
        files = {k: base / (k + ".wav") for k in stems}
        missing = [k for k, f in files.items() if not f.exists()]
        if missing:
            lg.warning("stems missing: %s", missing)
        collected = []
        per = (tmo // max(1, len(stems))) if tmo and tmo > 0 else 0
        t0 = time.time()
        for name, hint in stems.items():
            f = files[name]
            if not f.exists():
                continue
            out_m = tmp / (name + ".mid")
            cmd = self._build_cmd(str(f), str(out_m), None, bpm)
            if hint:
                cmd += ["--instruments", hint]
            lg.info("[demucs] stem %s -> %s", name, " ".join(cmd))
            with _JOB_LOCK:
                self._run(cmd, str(out_m), lg, per, None)
            if out_m.exists():
                collected.append((name, str(out_m)))
        if not collected:
            raise RuntimeError("demucs pipeline produced no stems")
        merged = pretty_midi.PrettyMIDI(resolution=480)
        PROG = {"vocals": 53, "drums": 0, "bass": 33, "other": 0}
        for name, mp in collected:
            pm_s = pretty_midi.PrettyMIDI(mp)
            for inst in pm_s.instruments:
                ni = pretty_midi.Instrument(program=PROG[name],
                                            is_drum=(name == "drums"),
                                            name=name)
                for n in inst.notes:
                    ni.notes.append(_copy.deepcopy(n))
                merged.instruments.append(ni)
        merged.write(str(out_mid_path))
        lg.info("[demucs] merged %d stems -> %s (%.1fs total)",
                len(collected), out_mid_path, time.time() - t0)
        try:
            from .postprocess import run_postprocess
            sub = flags & {"dedup", "frag", "vel", "harmonic"}
            run_postprocess(out_mid_path, self.pp_cfg, lg,
                            audio_path=str(audio_path),
                            flags=",".join(sorted(sub)))
        except Exception as _e:
            lg.warning("postprocess skipped: %s", _e)
        lg.info("SUCCESS (demucs pipeline)")
        return out_mid_path

'''
rep("server/engines/muscriptor.py", [
    ("    @staticmethod\n    def _kill_tree(proc):", METHODS + "    @staticmethod\n    def _kill_tree(proc):"),
], "engine: _smart_scan + _demucs_pipeline methods", skip="_demucs_pipeline")

# ---- 4. postprocess.py: full rewrite with harmonic stage ----
PP = ROOT / "server" / "engines" / "postprocess.py"
PP.write_text('''import logging
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
_VALID = ("dedup", "frag", "vel", "harmonic")


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
        if cfg.get("dedup", True):
            fl.add("dedup")
        if cfg.get("frag", True):
            fl.add("frag")
        if cfg.get("vel", False):
            fl.add("vel")
        if cfg.get("harmonic", False):
            fl.add("harmonic")
        return fl
    s = str(post).strip().lower()
    if s in ("", "0", "off", "false", "none"):
        return set()
    return {x.strip() for x in s.split(",") if x.strip() in _VALID}


def _rebuild_velocity(pm, audio_path, parent_log):
    try:
        import numpy as np
        import librosa
    except Exception as e:
        parent_log.warning("velocity rebuild: librosa/numpy unavailable (%s) - skipped", e)
        return
    try:
        y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
    except Exception as e:
        parent_log.warning("velocity rebuild: audio load failed (%s) - skipped", e)
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
            seg = lr[a:b + 1]
            v = int(20 + 107 * min(1.0, max(0.0, (float(seg.mean()) - lo) / span)))
            n.velocity = max(20, min(127, v))
            cnt += 1
    parent_log.info("velocity rebuild: %d notes re-velocitied from audio RMS", cnt)


def _harmonic_reassign(pm, audio_path, parent_log):
    """transformerOfMusic entry 10 (harmonic fingerprint) + entry 1-2
    (assignment continuity): move notes whose spectrum strongly disagrees
    with their track profile to the best-matching melodic track."""
    try:
        import numpy as np
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
        p0 = profiles[id(inst)]
        if p0 is None:
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
                best_inst = next(i for i in mel if id(i) == best)
                inst.notes.remove(n)
                best_inst.notes.append(n)
                moved += 1
    parent_log.info("harmonic reassign: %d notes moved between tracks", moved)


def run_postprocess(mid_path, cfg, parent_log, audio_path=None, flags=None):
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
            log.info("track %02d hygiene: %d -> %d notes (dedup=%s frag=%s)",
                     i, before, len(inst.notes), "dedup" in fl, min_note > 0)

    for i, inst in enumerate(pm.instruments):
        fam, bad, total = _range_report(inst)
        if total and bad / total > 0.3:
            log.info("track %02d range WARN: family=%s %d/%d notes out of range",
                     i, fam, bad, total)
            if range_fix and fam not in ("piano", "synth", "drums"):
                cands = []
                for f, rng in _RANGES.items():
                    if f == "drums":
                        continue
                    lo, hi = rng
                    cov = sum(1 for n in inst.notes if lo <= n.pitch <= hi)
                    cands.append((cov / total, f))
                cands.sort(reverse=True)
                best_cov, best_fam = cands[0]
                cur_cov = 1 - bad / total
                if best_cov > cur_cov + 0.3 and best_fam in _PROG:
                    log.info("track %02d range FIX: %s -> %s (coverage %.0f%%)",
                             i, fam, best_fam, best_cov * 100)
                    inst.program = _PROG[best_fam]

    if "dedup" in fl and len(pm.instruments) > 1:
        dom = max(pm.instruments, key=lambda x: len(x.notes))
        for inst in pm.instruments:
            if inst is dom or inst.is_drum:
                continue
            if 0 < len(inst.notes) < iso_min:
                log.info("isolated track FIX: %s (%d notes) -> %s",
                         pretty_midi.program_to_instrument_name(inst.program),
                         len(inst.notes),
                         pretty_midi.program_to_instrument_name(dom.program))
                dom.notes.extend(inst.notes)
                inst.notes = []

    pm.instruments = [x for x in pm.instruments if x.notes]

    fams = {_family(x.program, x.is_drum) for x in pm.instruments}
    fams.discard("drums")
    if len(fams) >= 6:
        log.info("coexistence WARN: %d distinct families -> %s",
                 len(fams), sorted(fams))

    if "harmonic" in fl and audio_path:
        _harmonic_reassign(pm, audio_path, parent_log)
    if "vel" in fl and audio_path:
        _rebuild_velocity(pm, audio_path, parent_log)

    pm.write(str(mid_path))
    log.info("---- postprocess done: %d tracks remain", len(pm.instruments))
''', encoding="utf-8")
ok.append("postprocess.py rewritten (harmonic stage added)")

print()
print("==== PATCH RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("=======================")

for fn in ("server/engines/muscriptor.py", "server/engines/postprocess.py"):
    try:
        py_compile.compile(str(ROOT / fn), doraise=True)
        print("  syntax OK :", fn)
    except Exception as e:
        print("  syntax FAIL:", fn, e)
