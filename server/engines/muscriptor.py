import os
import shutil
import subprocess
import sys
from .base import TranscriptionEngine
from ..config import CFG

# muscriptor CLI 璁よ瘑鐨勫叏閮ㄤ箰鍣ㄧ粍鍚嶏紙鏉ヨ嚜 muscriptor list-instruments 瀹炴祴杈撳嚭锛?
_MUSCRIPTOR_INSTRUMENTS = {
    "acoustic_piano", "electric_piano", "chromatic_percussion", "organ",
    "acoustic_guitar", "clean_electric_guitar", "distorted_electric_guitar",
    "acoustic_bass", "electric_bass", "violin", "viola", "cello", "contrabass",
    "orchestral_harp", "timpani", "string_ensemble", "synth_strings", "voice",
    "orchestra_hit", "trumpet", "trombone", "tuba", "french_horn", "brass_section",
    "soprano_and_alto_sax", "tenor_sax", "baritone_sax", "oboe", "english_horn",
    "bassoon", "clarinet", "flutes", "synth_lead", "synth_pad", "drums",
}

# 缃戦〉鐣岄潰鐨勪箰鍣ㄥ悕 -> CLI 涔愬櫒缁勫悕锛堜竴涓晫闈㈤€夐」鍙睍寮€涓哄涓?CLI 缁勶級
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
    """閫氳繃瀹樻柟 CLI 璋冪敤 MuScriptor(subprocess 妯″紡)銆?
    浼樼偣: 涓嶄緷璧栧唴閮?Python API, 杩涚▼骞插噣閫€鍑烘棤鏄惧瓨娉勬紡;
    浠ｄ环: 姣忔鍐峰姞杞芥ā鍨?~10-20s)銆傚悗缁彲鏀?inproc 甯搁┗銆?""

    def __init__(self):
        c = CFG.get("muscriptor", {})
        self.model = c.get("model", "large")
        # 鍏煎鏃ч厤缃敭 torch_backend(閭ｆ槸 uv 鐨勫畨瑁呭弬鏁? 涓嶆槸 muscriptor 鐨?:
        # 缁熶竴鏄犲皠鍒?CLI 鐪熷疄瀛樺湪鐨?--device(auto/cpu/cuda/cuda:0/mps)
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
        """鐣岄潰涔愬櫒鍚?-> CLI 缁勫悕銆傝璇嗙殑缈昏瘧, 鏈潵灏辨槸 CLI 鍘熺敓鍚嶇殑鐩存帴鐢?
        璋侀兘涓嶈璇嗙殑涓㈠純(鍚﹀垯鏁翠釜 --instruments 鍙傛暟浼氳 CLI 鎷掓敹)銆?""
        if not instruments:
            return None
        out: list[str] = []
        for name in instruments:
            key = str(name).strip().lower()
            if key in _INSTRUMENT_MAP:
                out += _INSTRUMENT_MAP[key]
            elif key in _MUSCRIPTOR_INSTRUMENTS:
                out.append(key)
        out = list(dict.fromkeys(out))  # 鍘婚噸涓斾繚鎸侀『搴?
        return ",".join(out) if out else None

    def _build_cmd(self, audio: str, out: str,
                   instruments: list[str] | None, bpm: int | None) -> list[str]:
        cmd = list(self._cli_prefix())
        # 鈽?淇1: 琛ヤ笂瀹樻柟瑕佹眰鐨?transcribe 瀛愬懡浠?涔嬪墠闊抽璺緞琚綋鎴愪簡瀛愬懡浠?
        cmd += ["transcribe", audio, "-o", out, "--model", str(self.model), "--detect-tempo", "false"]
        # 鈽?淇2: --torch-backend 鍦?CLI 閲屼笉瀛樺湪, 鏀圭敤鐪熷疄閫夐」 --device
        if self.device:
            cmd += ["--device", self.device]
        # 鈽?淇3: 涔愬櫒鍚嶅厛缈昏瘧鎴?CLI 璁よ瘑鐨勭粍鍚嶅啀浼?
        inst = self._translate_instruments(instruments)
        if inst:
            cmd += ["--instruments", inst]
        if bpm:
            cmd += ["--bpm", str(int(bpm))]  # CLI 闄愬畾 20-400
        # 鍙傛暟鍚嶅凡閫愪竴瀵圭収 `muscriptor transcribe --help` 鏍稿
        return cmd

    def transcribe(self, audio_path, out_mid_path, instruments=None, bpm=None):
        cmd = self._build_cmd(audio_path, out_mid_path, instruments, bpm)
        env = os.environ.copy()  # 缁ф壙 HF_TOKEN 绛?
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=self.timeout, env=env,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"MuScriptor 瓒呮椂({self.timeout}s)")
        if r.returncode != 0:
            raise RuntimeError(
                f"MuScriptor 澶辫触(鐮?{r.returncode}):\n"
                f"{(r.stderr or r.stdout)[-2000:]}")
        if not os.path.exists(out_mid_path):
            raise RuntimeError("MuScriptor 鏈骇鍑?MIDI 鏂囦欢")
        return out_mid_path

