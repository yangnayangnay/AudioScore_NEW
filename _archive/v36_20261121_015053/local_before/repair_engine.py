# -*- coding: utf-8 -*-
"""REPAIR: ensure _smart_scan/_demucs_pipeline/_dsp_pipeline + dispatch + flags
end-block all exist in engine. Strong anchor: def transcribe. Fully self-reporting."""
from pathlib import Path
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ENG = ROOT / "server" / "engines" / "muscriptor.py"
s = ENG.read_text(encoding="utf-8")

print("==== STATE BEFORE ====")
for sym in ("_smart_scan", "_demucs_pipeline", "_dsp_pipeline",
            "_flags = set(", "separation mode: DSP", "flags=post)"):
    print("  %-22s : %s" % (sym, "present" if sym in s else "MISSING"))

# ---------- 1. signature: ensure post param ----------
if "post=None):" not in s:
    if "timeout=None):" in s:
        s = s.replace("timeout=None):", "timeout=None, post=None):", 1)
        print("  [FIX] transcribe signature + post")
    else:
        raise SystemExit("[ABORT] transcribe signature not found")
else:
    print("  [OK] transcribe signature has post")

# ---------- 2. methods (inserted before def transcribe) ----------
ANCH = "    def transcribe(self, audio_path"
if ANCH not in s:
    raise SystemExit("[ABORT] def transcribe anchor missing - paste engine tail")

SMART_SRC = '''    def _smart_scan(self, audio_path, lg):
        """transformerOfMusic entry 16-24: listen first, then constrain.
        YAMNet when TF present; spectral heuristic fallback otherwise."""
        try:
            import tensorflow_hub as hub
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
                    [(n, round(float(v), 2)) for n, v in pairs])
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

'''
DEMUCS_SRC = '''    def _demucs_pipeline(self, audio_path, out_mid_path, instruments, bpm,
                         tmo, flags, lg):
        """transformerOfMusic timbre_split orchestrator: separate -> per-stem
        transcribe -> merge -> postprocess. Requires: pip install demucs."""
        import copy as _copy
        import pretty_midi
        import demucs  # noqa: F401
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
DSP_SRC = '''    def _dsp_pipeline(self, audio_path, out_mid_path, instruments, bpm,
                      tmo, flags, lg):
        """Zero-install separation: librosa HPSS + low-band split.
        transformerOfMusic timbre_split idea, classical DSP edition."""
        import copy as _copy
        import numpy as np
        import librosa
        import soundfile as sf
        import pretty_midi
        lg.info("---- DSP pipeline start (hpss + band split, no ML) ----")
        tmp = Path(out_mid_path).parent / ("_dsp_" + Path(out_mid_path).stem)
        tmp.mkdir(parents=True, exist_ok=True)
        y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
        harm, perc = librosa.effects.hpss(y)
        D = librosa.stft(harm, n_fft=2048)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        mask = (freqs <= 180).astype(float)
        bass = librosa.istft(D * mask[:, None])
        melo = librosa.istft(D * (1.0 - mask[:, None]))
        sf.write(str(tmp / "perc.wav"), perc, sr)
        sf.write(str(tmp / "bass.wav"), bass, sr)
        sf.write(str(tmp / "melo.wav"), melo, sr)
        stems = {"perc.wav": "drums",
                 "bass.wav": "electric_bass,acoustic_bass",
                 "melo.wav": None}
        collected = []
        per = (tmo // max(1, len(stems))) if tmo and tmo > 0 else 0
        t0 = time.time()
        for fname, hint in stems.items():
            f = tmp / fname
            out_m = tmp / (fname[:-4] + ".mid")
            eff = hint if hint else instruments
            cmd = self._build_cmd(str(f), str(out_m), eff, bpm)
            lg.info("[dsp] stem %s -> transcribe (%s)",
                    fname, "fixed hint" if hint else "user/auto")
            with _JOB_LOCK:
                self._run(cmd, str(out_m), lg, per, None)
            if out_m.exists():
                collected.append((fname[:-4], str(out_m)))
        if not collected:
            raise RuntimeError("DSP pipeline produced no stems")
        merged = pretty_midi.PrettyMIDI(resolution=480)
        PROG = {"perc": 0, "bass": 33, "melo": 0}
        for name, mp in collected:
            pm_s = pretty_midi.PrettyMIDI(mp)
            for inst in pm_s.instruments:
                ni = pretty_midi.Instrument(program=PROG[name],
                                            is_drum=(name == "perc"),
                                            name=name)
                for n in inst.notes:
                    ni.notes.append(_copy.deepcopy(n))
                merged.instruments.append(ni)
        merged.write(str(out_mid_path))
        lg.info("[dsp] merged %d stems -> %s (%.1fs total)",
                len(collected), out_mid_path, time.time() - t0)
        try:
            from .postprocess import run_postprocess
            sub = flags & {"dedup", "frag", "vel", "harmonic"}
            run_postprocess(out_mid_path, self.pp_cfg, lg,
                            audio_path=str(audio_path),
                            flags=",".join(sorted(sub)))
        except Exception as _e:
            lg.warning("postprocess skipped: %s", _e)
        lg.info("SUCCESS (dsp pipeline)")
        return out_mid_path

'''
idx = s.index(ANCH)
for label, code in (("_smart_scan", SMART_SRC),
                    ("_demucs_pipeline", DEMUCS_SRC),
                    ("_dsp_pipeline", DSP_SRC)):
    if "def " + label + "(" in s:
        print("  [SKIP] %s present" % label)
    else:
        s = s[:idx] + code + s[idx:]
        idx += len(code)
        print("  [FIX] %s inserted" % label)

# ---------- 3. dispatch: insert or upgrade ----------
FALLBACK_DISP = ('        if "demucs" in _flags:\n'
                 '            try:\n'
                 '                import demucs  # noqa: F401\n'
                 '                _ml = True\n'
                 '            except ImportError:\n'
                 '                _ml = False\n'
                 '            if _ml:\n'
                 '                lg.info("separation mode: demucs (ML)")\n'
                 '                return self._demucs_pipeline(audio_path, out_mid_path, instruments,\n'
                 '                                             bpm, tmo, _flags, lg)\n'
                 '            lg.info("demucs not installed -> separation mode: DSP (zero install)")\n'
                 '            return self._dsp_pipeline(audio_path, out_mid_path, instruments,\n'
                 '                                      bpm, tmo, _flags, lg)\n')
if "_flags = set(" not in s:
    anc = "        inst_cli, inst_mode = self._resolve_instruments(instruments)\n"
    if anc not in s:
        raise SystemExit("[ABORT] dispatch anchor missing")
    SMART_DISP = ('        _flags = set(x.strip() for x in str(post or "").split(",") if x.strip())\n'
                  '        if "smart" in _flags and not instruments:\n'
                  '            try:\n'
                  '                _si = self._smart_scan(audio_path, lg)\n'
                  '            except Exception as _e:\n'
                  '                lg.warning("smart scan failed: %s", _e)\n'
                  '                _si = None\n'
                  '            if _si:\n'
                  '                instruments = _si\n'
                  '                lg.info("smart scan -> instruments: %s", _si)\n')
    s = s.replace(anc, SMART_DISP + FALLBACK_DISP + anc, 1)
    print("  [FIX] dispatch inserted (smart + demucs/DSP fallback)")
elif "separation mode: DSP" not in s:
    OLD_DISP = ('        if "demucs" in _flags:\n'
                '            return self._demucs_pipeline(audio_path, out_mid_path, instruments,\n'
                '                                         bpm, tmo, _flags, lg)\n')
    if OLD_DISP in s:
        s = s.replace(OLD_DISP, FALLBACK_DISP, 1)
        print("  [FIX] dispatch upgraded with DSP fallback")
    else:
        print("  [WARN] dispatch in unknown form - paste transcribe head")
else:
    print("  [SKIP] dispatch already has DSP fallback")

# ---------- 4. end-block: ensure flags reach postprocess ----------
if "flags=post)" not in s:
    OLD_END_A = ('        try:\n'
                 '            from .postprocess import run_postprocess\n'
                 '            run_postprocess(out_mid_path, self.pp_cfg, lg)\n'
                 '        except Exception as _e:\n'
                 '            lg.warning("postprocess skipped: %s", _e)\n'
                 '        else:\n'
                 '            lg.info("postprocess: OFF (ui flag)")')
    OLD_END_B = ('        try:\n'
                 '            from .postprocess import run_postprocess\n'
                 '            run_postprocess(out_mid_path, self.pp_cfg, lg)\n'
                 '        except Exception as _e:\n'
                 '            lg.warning("postprocess skipped: %s", _e)')
    NEW_END = ('        try:\n'
               '            from .postprocess import run_postprocess\n'
               '            run_postprocess(out_mid_path, self.pp_cfg, lg,\n'
               '                            audio_path=str(audio_path), flags=post)\n'
               '        except Exception as _e:\n'
               '            lg.warning("postprocess skipped: %s", _e)')
    if OLD_END_A in s:
        s = s.replace(OLD_END_A, NEW_END, 1)
    elif OLD_END_B in s:
        s = s.replace(OLD_END_B, NEW_END, 1)
    else:
        print("  [WARN] end-block not matched - paste transcribe tail")
    print("  [FIX] end-block now forwards flags")
else:
    print("  [SKIP] end-block already forwards flags")

ENG.write_text(s, encoding="utf-8")

# ---------- 5. postprocess: ensure harmonic stage ----------
PP = ROOT / "server" / "engines" / "postprocess.py"
ps = PP.read_text(encoding="utf-8")
if "_harmonic_reassign" not in ps:
    print("  [WARN] postprocess lacks harmonic stage - rerun patch_tom_buttons step or say so")
else:
    print("  [SKIP] postprocess has harmonic stage")

py_compile.compile(str(ENG), doraise=True)
py_compile.compile(str(PP), doraise=True)
print("==== syntax OK: engine + postprocess ====")
print("NEXT: restart start.bat -> staged validation (see answer)")
