import os
import shutil
import subprocess
import sys
from .base import TranscriptionEngine
from ..config import CFG

_MUSCRIPTOR_INSTRUMENTS = {
    "acoustic_piano","electric_piano","chromatic_percussion","organ",
    "acoustic_guitar","clean_electric_guitar","distorted_electric_guitar",
    "acoustic_bass","electric_bass","violin","viola","cello","contrabass",
    "orchestral_harp","timpani","string_ensemble","synth_strings","voice",
    "orchestra_hit","trumpet","trombone","tuba","french_horn","brass_section",
    "soprano_and_alto_sax","tenor_sax","baritone_sax","oboe","english_horn",
    "bassoon","clarinet","flutes","synth_lead","synth_pad","drums",
}

class MuscriptorEngine(TranscriptionEngine):
    def __init__(self):
        c = CFG.get("muscriptor", {}) or {}
        self.model = c.get("model", "medium")
        self.device = c.get("device") or "cuda"
        try:
            self.beat_scale = float(c.get("beat_scale", 1.0))
        except (TypeError, ValueError):
            self.beat_scale = 1.0
        self.dtype = c.get("dtype") or None
        try:
            self.timeout = int(c.get("timeout", 1800))
        except (TypeError, ValueError):
            self.timeout = 1800
        self._cli = None

    def _cli_prefix(self):
        if self._cli is not None: return self._cli
        if shutil.which("muscriptor"):
            self._cli = ["muscriptor"]
        else:
            try:
                import muscriptor
                self._cli = [sys.executable, "-m", "muscriptor"]
            except ImportError:
                self._cli = None
        return self._cli

    def is_available(self):
        return self._cli_prefix() is not None

    def _build_cmd(self, audio, out, instruments, bpm, force_gpu=None):
        cmd = list(self._cli_prefix())
        cmd += ["transcribe", audio, "-o", out, "--model", str(self.model),
                "--detect-tempo", "best-effort"]
        if force_gpu is True:   cmd += ["--device", "cuda"]
        elif force_gpu is False: cmd += ["--device", "cpu"]
        else:                    cmd += ["--device", str(self.device)]
        # 只透传官方名；不传 = 模型自检全部 36 类
        if instruments:
            ok = [i for i in instruments if str(i).strip().lower() in _MUSCRIPTOR_INSTRUMENTS]
            if ok:
                cmd += ["--instruments", ",".join(ok)]
        if bpm:
            cmd += ["--bpm", str(int(bpm))]
        if self.beat_scale and abs(self.beat_scale - 1.0) > 1e-6:
            cmd += ["--beat-scale", str(self.beat_scale)]
        if self.dtype:
            cmd += ["--dtype", str(self.dtype)]
        return cmd

    def transcribe(self, audio_path, out_mid_path,
                   instruments=None, bpm=None, force_gpu=None, timeout=None):
        cmd = self._build_cmd(audio_path, out_mid_path, instruments, bpm, force_gpu)
        try:
            _tv = int(timeout) if timeout is not None else None
        except (TypeError, ValueError):
            _tv = None
        if _tv is None:
            t = self.timeout
        elif _tv == 0:
            t = None
        elif _tv > 0:
            t = _tv
        else:
            t = self.timeout
        env = os.environ.copy()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=t, env=env,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise RuntimeError("转写超时（" + str(t) + " 秒）。可在 config.yaml 调大 muscriptor.timeout，或 UI 里把超时设为 0（无限制）后重试")
        if r.returncode != 0:
            raise RuntimeError("MuScriptor failed (code " + str(r.returncode) + "):\n"
                               + ((r.stderr or r.stdout) or "")[-2000:])
        if not os.path.exists(out_mid_path):
            raise RuntimeError("MuScriptor produced no MIDI file")
        return out_mid_path
