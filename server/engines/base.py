from dataclasses import dataclass


@dataclass
class Note:
    """统一音符模型——所有引擎的输出都归一到这个格式再做后处理"""
    program: int          # GM program 0-127
    pitch: int            # MIDI 音高 0-127
    start: float          # 秒
    end: float            # 秒
    velocity: int = 100
    is_drum: bool = False


class TranscriptionEngine:
    name: str = "base"
    desc: str = ""

    def is_available(self) -> bool:
        raise NotImplementedError

    def transcribe(self, audio_path: str, out_mid_path: str,
                   instruments: list[str] | None = None,
                   bpm: int | None = None) -> str:
        """输入音频路径, 输出 raw MIDI 文件路径"""
        raise NotImplementedError
