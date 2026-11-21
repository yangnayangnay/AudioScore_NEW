import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from .base import TranscriptionEngine
from ..config import CFG

_MUSCRIPTOR_INSTRUMENTS = {
    "acoustic_piano", "electric_piano", "chromatic_percussion", "organ",
    "acoustic_guitar", "clean_electric_guitar", "distorted_electric_guitar",
    "acoustic_bass", "electric_bass", "violin", "viola", "cello", "contrabass",
    "orchestral_harp", "timpani", "string_ensemble", "synth_strings", "voice",
    "orchestra_hit", "trumpet", "trombone", "tuba", "french_horn", "brass_section",
    "soprano_and_alto_sax", "tenor_sax", "baritone_sax", "oboe", "english_horn",
    "bassoon", "clarinet", "flutes", "synth_lead", "synth_pad", "drums",
}

_INSTRUMENT_MAP = {
    "piano": ["acoustic_piano", "electric_piano"],
    "bass": ["acoustic_bass", "electric_bass"],
    "electric bass": ["electric_bass"],
    "electric_bass": ["electric_bass"],
    "e-bass": ["electric_bass"],
    "5-string bass": ["electric_bass"],
    "5-string electric bass": ["electric_bass"],
    "drums": ["drums"],
    "drum": ["drums"],
    "drum kit": ["drums"],
    "drum set": ["drums"],
    "drum score": ["drums"],
    "guitar": ["acoustic_guitar"],
    "acoustic guitar": ["acoustic_guitar"],
    "electric guitar": ["clean_electric_guitar", "distorted_electric_guitar"],
    "electric_guitar": ["clean_electric_guitar", "distorted_electric_guitar"],
    "strings": ["string_ensemble"],
    "violin": ["violin"],
    "viola": ["viola"],
    "cello": ["cello"],
    "brass": ["brass_section", "trumpet", "trombone", "tuba", "french_horn"],
    "trumpet": ["trumpet"],
    "saxophone": ["soprano_and_alto_sax", "tenor_sax", "baritone_sax"],
    "flute": ["flutes"],
    "organ": ["organ"],
    "synth_lead": ["synth_lead"],
    "synth_pad": ["synth_pad"],
    "vocals": ["voice"],
    "vocal": ["voice"],
    "voice": ["voice"],
    "soprano": ["voice"],
    "alto": ["voice"],
    # ---- Chinese ----
    "\u94a2\u7434": ["acoustic_piano", "electric_piano"],
    "\u8d1d\u65af": ["acoustic_bass", "electric_bass"],
    "\u7535\u8d1d\u65af": ["electric_bass"],
    "\u4e94\u5f26\u7535\u8d1d\u65af": ["electric_bass"],
    "\u9f13": ["drums"],
    "\u9f13\u7ec4": ["drums"],
    "\u67b6\u5b50\u9f13": ["drums"],
    "\u9f13\u8c31": ["drums"],
    "\u5409\u4ed6": ["acoustic_guitar"],
    "\u7535\u5409\u4ed6": ["clean_electric_guitar", "distorted_electric_guitar"],
    "\u6728\u5409\u4ed6": ["acoustic_guitar"],
    "\u5c0f\u63d0\u7434": ["violin"],
    "\u4e2d\u63d0\u7434": ["viola"],
    "\u5927\u63d0\u7434": ["cello"],
    "\u5f26\u4e50": ["string_ensemble"],
    "\u957f\u7b1b": ["flutes"],
    "\u7b1b\u5b50": ["flutes"],
    "\u8428\u514b\u65af": ["soprano_and_alto_sax", "tenor_sax", "baritone_sax"],
    "\u5c0f\u53f7": ["trumpet"],
    "\u94dc\u7ba1": ["brass_section", "trumpet", "trombone", "tuba", "french_horn"],
    "\u7ba1\u98ce\u7434": ["organ"],
    "\u4eba\u58f0": ["voice"],
    "\u5973\u9ad8\u97f3": ["voice"],
    "\u5973\u58f0": ["voice"],
    "\u7537\u58f0": ["voice"],
    "\u4e3b\u5531": ["voice"],
}

_JOB_LOCK = threading.Lock()
_LATEST = {"line": "", "ts": 0.0}
_LOG_READY = False


def _log():
    global _LOG_READY
    lg = logging.getLogger("muscriptor")
    if not _LOG_READY:
        log_dir = Path(__file__).resolve().parents[2] / "logs"
        log_dir.mkdir(exist_ok=True)
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
        fh = logging.FileHandler(log_dir / "muscriptor.log", encoding="utf-8")
        fh.setFormatter(fmt)
        lg.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        lg.addHandler(sh)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        _LOG_READY = True
    return lg


class MuscriptorEngine(TranscriptionEngine):
    """Call MuScriptor through its official CLI (subprocess mode)."""

    def __init__(self):
        super().__init__()
        c = CFG.get("muscriptor", {})
        self.model = c.get("model", "large")
        self.device = c.get("device") or c.get("torch_backend") or ""
        self.dtype = c.get("dtype") or ""
        self.timeout = int(c.get("timeout", 3600))
        self.batch_size = c.get("batch_size")
        self.no_prelude_forcing = bool(c.get("no_prelude_forcing", False))
        self.beam_size = c.get("beam_size")
        ai = c.get("auto_instruments") or []
        if isinstance(ai, str):
            ai = [x.strip() for x in ai.split(",") if x.strip()]
        self.auto_instruments = [str(x).strip().lower() for x in ai]
        self.pp_cfg = dict(CFG.get("muscriptor", {}).get("postprocess", {}) or {})
        _log().info("engine init: model=%s device=%r batch=%r timeout=%ss (0=no limit) guided_auto=%s",
                    self.model, self.device, self.batch_size, self.timeout,
                    ",".join(self.auto_instruments) or "(off)")

    def get_status(self):
        return dict(_LATEST)

    def _cli_prefix(self):
        if shutil.which("muscriptor"):
            return ["muscriptor"]
        try:
            import muscriptor  # noqa: F401
            return [sys.executable, "-m", "muscriptor"]
        except ImportError:
            return None

    def is_available(self):
        return self._cli_prefix() is not None

    def _translate_instruments(self, instruments):
        if not instruments:
            return None
        out = []
        for name in instruments:
            key = str(name).strip().lower()
            plain = re.sub(r"[^\x20-\x7e]", "", key).strip()
            for k in (key, plain):
                if k in _INSTRUMENT_MAP:
                    out += _INSTRUMENT_MAP[k]
                    break
            else:
                if key in _MUSCRIPTOR_INSTRUMENTS:
                    out.append(key)
                elif plain in _MUSCRIPTOR_INSTRUMENTS:
                    out.append(plain)
        out = list(dict.fromkeys(out))
        return ",".join(out) if out else None

    def _resolve_instruments(self, instruments):
        inst = self._translate_instruments(instruments)
        if inst:
            return inst, "user-selected"
        if self.auto_instruments:
            return ",".join(self.auto_instruments), "guided-auto"
        return None, "raw-auto"

    def _build_cmd(self, audio, out, instruments=None, bpm=None):
        cmd = list(self._cli_prefix())
        cmd += ["transcribe", audio, "-o", out, "--model", str(self.model),
                "--detect-tempo", "false"]
        if self.device:
            cmd += ["--device", self.device]
        if self.dtype:
            cmd += ["--dtype", self.dtype]
        if self.batch_size:
            cmd += ["--batch-size", str(int(self.batch_size))]
            if self.no_prelude_forcing:
                cmd += ["--no-prelude-forcing"]
        if self.beam_size:
            cmd += ["--beam-size", str(int(self.beam_size))]
        inst, _mode = self._resolve_instruments(instruments)
        if inst:
            cmd += ["--instruments", inst]
        if bpm:
            cmd += ["--bpm", str(int(bpm))]
        return cmd

    def _log_midi_summary(self, mid_path):
        try:
            import pretty_midi
            pm = pretty_midi.PrettyMIDI(mid_path)
            lines = []
            total = 0
            for i, inst in enumerate(pm.instruments):
                nm = pretty_midi.program_to_instrument_name(inst.program)
                lines.append("track %02d | program %3d | %-28s | drums=%-5s | notes=%d"
                             % (i, inst.program, nm, inst.is_drum, len(inst.notes)))
                total += len(inst.notes)
            _log().info("midi summary: %d track(s), %d notes\n%s",
                        len(pm.instruments), total, "\n".join(lines))
        except Exception as e:
            _log().warning("midi summary failed: %s", e)

    @staticmethod
    def _kill_tree(proc):
        """Kill the whole process tree (torch spawns children; plain kill leaks them)."""
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, text=True)
            else:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _smart_scan(self, audio_path, lg):
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

    def _demucs_pipeline(self, audio_path, out_mid_path, instruments, bpm,
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
            lg.error("demucs separation failed:\n%s", (sep.stderr or "")[-800:])
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
            sub = flags & {"dedup", "frag", "vel", "harmonic", "quant", "split", "fit", "meter"}
            run_postprocess(out_mid_path, self.pp_cfg, lg,
                            audio_path=str(audio_path),
                            flags=",".join(sorted(sub)), bpm=bpm)
        except Exception as _e:
            lg.warning("postprocess skipped: %s", _e)
        lg.info("SUCCESS (demucs pipeline)")
        return out_mid_path

    def _dsp_pipeline(self, audio_path, out_mid_path, instruments, bpm,
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
            sub = flags & {"dedup", "frag", "vel", "harmonic", "quant", "split", "fit", "meter"}
            run_postprocess(out_mid_path, self.pp_cfg, lg,
                            audio_path=str(audio_path),
                            flags=",".join(sorted(sub)), bpm=bpm)
        except Exception as _e:
            lg.warning("postprocess skipped: %s", _e)
        lg.info("SUCCESS (dsp pipeline)")
        return out_mid_path

    def transcribe(self, audio_path, out_mid_path, instruments=None, bpm=None,
                   timeout=None, post=None):
        lg = _log()
        tmo = self.timeout if timeout is None else int(timeout)
        if tmo < 0:
            tmo = 0
        _flags = set(x.strip() for x in str(post or "").split(",") if x.strip())
        if "smart" in _flags and not instruments:
            try:
                _si = self._smart_scan(audio_path, lg)
            except Exception as _e:
                lg.warning("smart scan failed: %s", _e)
                _si = None
            if _si:
                instruments = _si
                lg.info("smart scan -> instruments: %s", _si)
        if "demucs" in _flags:
            try:
                import demucs  # noqa: F401
                _ml = True
            except ImportError:
                _ml = False
            if _ml:
                lg.info("separation mode: demucs (ML)")
                return self._demucs_pipeline(audio_path, out_mid_path, instruments,
                                             bpm, tmo, _flags, lg)
            lg.info("demucs not installed -> separation mode: DSP (zero install)")
            return self._dsp_pipeline(audio_path, out_mid_path, instruments,
                                      bpm, tmo, _flags, lg)
        inst_cli, inst_mode = self._resolve_instruments(instruments)
        cmd = self._build_cmd(audio_path, out_mid_path, instruments, bpm)
        lg.info("---- job start ----")
        lg.info("audio      : %s", audio_path)
        lg.info("out        : %s", out_mid_path)
        lg.info("inst (web) : %r  [mode=%s]", instruments, inst_mode)
        lg.info("inst (cli) : %s", inst_cli or "(none)")
        lg.info("bpm        : %r", bpm)
        lg.info("time limit : %s", ("%ss" % tmo) if tmo > 0 else "NO LIMIT")
        lg.info("command    : %s", " ".join(cmd))
        if _JOB_LOCK.locked():
            lg.info("another job still running -> this job QUEUED")
        with _JOB_LOCK:
            lg.info("lock acquired, starting subprocess")
            return self._run(cmd, out_mid_path, lg, tmo, post)

    def _run(self, cmd, out_mid_path, lg, tmo, post):
        env = os.environ.copy()
        t0 = time.time()
        _LATEST["line"] = ""
        _LATEST["ts"] = 0.0
        tail = deque(maxlen=40)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=env)
        lg.info("process started pid=%s (cli output streams below)", proc.pid)

        def reader():
            for line in proc.stdout:
                line = (line or "").rstrip()
                if not line:
                    continue
                tail.append(line)
                _LATEST["line"] = line
                _LATEST["ts"] = time.time()
                lg.info("[cli] %s", line)

        th = threading.Thread(target=reader, daemon=True)
        th.start()
        rc = None
        try:
            while True:
                rc = proc.poll()
                if rc is not None:
                    break
                el = time.time() - t0
                if tmo and tmo > 0 and el > tmo:
                    self._kill_tree(proc)
                    lg.error("TIMEOUT after %.0fs (limit %ss) -> process tree killed",
                             el, tmo)
                    raise RuntimeError("MuScriptor timeout (%ss)" % tmo)
                time.sleep(10)
                gap = (time.time() - _LATEST["ts"]) if _LATEST["ts"] else el
                lg.info("heartbeat: alive, %.0fs elapsed%s, last cli output %.0fs ago",
                        el, "" if tmo > 0 else ", NO LIMIT", gap)
        finally:
            th.join(timeout=3)
        dt = time.time() - t0
        if rc != 0:
            lg.error("FAILED code=%s elapsed=%.1fs", rc, dt)
            tailtxt = "\n".join(list(tail)[-25:])
            lg.error("cli tail:\n%s", tailtxt)
            raise RuntimeError("MuScriptor failed (code %s):\n%s" % (rc, tailtxt))
        if not os.path.exists(out_mid_path):
            lg.error("FAILED: no midi produced, elapsed=%.1fs", dt)
            raise RuntimeError("MuScriptor produced no MIDI file")
        self._log_midi_summary(out_mid_path)
        lg.info("SUCCESS in %.1fs", dt)
        return out_mid_path
