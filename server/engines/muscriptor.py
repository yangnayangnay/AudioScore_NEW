import os
import shutil
import subprocess
import sys
from .base import TranscriptionEngine
from ..config import CFG

# All instrument group names recognized by the muscriptor CLI
# (from `muscriptor list-instruments` output)
_MUSCRIPTOR_INSTRUMENTS = {
    "acoustic_piano", "electric_piano", "chromatic_percussion", "organ",
    "acoustic_guitar", "clean_electric_guitar", "distorted_electric_guitar",
    "acoustic_bass", "electric_bass", "violin", "viola", "cello", "contrabass",
    "orchestral_harp", "timpani", "string_ensemble", "synth_strings", "voice",
    "orchestra_hit", "trumpet", "trombone", "tuba", "french_horn", "brass_section",
    "soprano_and_alto_sax", "tenor_sax", "baritone_sax", "oboe", "english_horn",
    "bassoon", "clarinet", "flutes", "synth_lead", "synth_pad", "drums",
}

# Web UI instrument names -> CLI group names (one UI option may expand
# to several CLI groups)
_INSTRUMENT_MAP = {
    "piano": ["acoustic_piano", "electric_piano"],
    "bass": ["acoustic_bass", "electric_bass"],
    "drums": ["drums"],
    "guitar": ["acoustic_guitar"],
    "electric guitar": ["clean_electric_guitar", "distorted_electric_guitar"],
    "electric_guitar": ["clean_electric_guitar", "distorted_electric_guitar"],
    "strings": ["string_ensemble"],
    "violin": ["violin"],
    "cello": ["cello"],
    "brass": ["brass_section", "trumpet", "trombone", "tuba", "french_horn"],
    "trumpet": ["trumpet"],
    "saxophone": ["soprano_and_alto_sax", "tenor_sax", "baritone_sax"],
    "flute": ["flutes"],
    "organ": ["organ"],
    "synth_lead": ["synth_lead"],
    "synth_pad": ["synth_pad"],
    "vocals": ["voice"],
}

class MuscriptorEngine(TranscriptionEngine):
    """Call MuScriptor through its official CLI (subprocess mode).

    Pros: no dependency on the internal Python API; the process exits
    cleanly with no lingering memory leaks.
    Cost: a cold model load on every run (~10-20s). Could later be
    switched to an in-process resident engine.
    """

    def __init__(self):
        c = CFG.get("muscriptor", {})
        self.model = c.get("model", "large")
        # Compat with the old config key torch_backend (that was a uv
        # install parameter, not a muscriptor option): map it to the
        # CLI's real --device option (auto/cpu/cuda/cuda:0/mps).
        self.device = c.get("device") or c.get("torch_backend") or ""
        self.timeout = c.get("timeout", 1800)

    def _cli_prefix(self) -> list[str] | None:
        if shutil.which("muscriptor"):
            return ["muscriptor"]
        try:
            import muscriptor  # noqa: F401
            return [sys.executable, "-m", "muscriptor"]
        except ImportError:
            return None

    def is_available(self) -> bool:
        return self._cli_prefix() is not None

    def _translate_instruments(self, instruments: list[str] | None) -> str | None:
        """Translate UI instrument names to CLI group names.

        Unknown names are dropped, otherwise the whole --instruments
        argument would be rejected by the CLI.
        """
        if not instruments:
            return None
        out: list[str] = []
        for name in instruments:
            key = str(name).strip().lower()
            if key in _INSTRUMENT_MAP:
                out += _INSTRUMENT_MAP[key]
            elif key in _MUSCRIPTOR_INSTRUMENTS:
                out.append(key)
        out = list(dict.fromkeys(out))  # dedupe, keep order
        return ",".join(out) if out else None

    def _build_cmd(self, audio: str, out: str,
                   instruments: list[str] | None, bpm: int | None) -> list[str]:
        cmd = list(self._cli_prefix())
        # Fix 1: add the required `transcribe` subcommand (previously the
        # audio path was treated as the subcommand) + skip beat detection
        # (--detect-tempo false; parameter verified against --help).
        cmd += ["transcribe", audio, "-o", out, "--model", str(self.model), "--detect-tempo", "false"]
        # Fix 2: --torch-backend does not exist in the CLI; use the real
        # option --device instead.
        if self.device:
            cmd += ["--device", self.device]
        # Fix 3: translate instrument names to CLI-recognized groups first.
        inst = self._translate_instruments(instruments)
        if inst:
            cmd += ["--instruments", inst]
        if bpm:
            cmd += ["--bpm", str(int(bpm))]  # CLI limits 20-400
        # Parameter names cross-checked against `muscriptor transcribe --help`
        return cmd

    def transcribe(self, audio_path, out_mid_path, instruments=None, bpm=None):
        cmd = self._build_cmd(audio_path, out_mid_path, instruments, bpm)
        env = os.environ.copy()  # inherit HF_TOKEN etc.
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=self.timeout, env=env,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"MuScriptor timeout ({self.timeout}s)")
        if r.returncode != 0:
            raise RuntimeError(
                f"MuScriptor failed (code {r.returncode}):\n"
                f"{(r.stderr or r.stdout)[-2000:]}")
        if not os.path.exists(out_mid_path):
            raise RuntimeError("MuScriptor produced no MIDI file")
        return out_mid_path
