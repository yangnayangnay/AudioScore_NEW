import inspect

from .base import TranscriptionEngine
from ..config import CFG


class BasicPitchEngine(TranscriptionEngine):
    """Spotify Basic Pitch: 轻量单轨转写(不区分乐器), 用于链路验证与单乐器素材。"""

    def __init__(self):
        c = CFG.get("basic_pitch", {})
        self.onset_threshold = c.get("onset_threshold", 0.5)
        self.frame_threshold = c.get("frame_threshold", 0.3)

    def is_available(self) -> bool:
        try:
            import basic_pitch  # noqa: F401
            return True
        except ImportError:
            return False

    def transcribe(self, audio_path, out_mid_path, instruments=None, bpm=None):
        # instruments / bpm 由上层统一传入; Basic Pitch 不支持乐器约束, 静默忽略
        from basic_pitch.inference import predict

        # 只传当前安装版本确实支持的参数: 可选参数(如 midi_tempo)在旧版本
        # 不存在时按签名过滤掉, 自动回退默认值, 而不是 TypeError 崩掉
        supported = inspect.signature(predict).parameters
        kwargs = {
            "onset_threshold": self.onset_threshold,
            "frame_threshold": self.frame_threshold,
            "midi_tempo": bpm or 120,
        }
        kwargs = {k: v for k, v in kwargs.items() if k in supported}

        # predict 返回 NamedTuple(model_output, midi_data, note_events);
        # 按属性名取 midi_data(PrettyMIDI 对象)比按位置解包更抗版本变化
        result = predict(audio_path, **kwargs)
        result.midi_data.write(out_mid_path)
        return out_mid_path
