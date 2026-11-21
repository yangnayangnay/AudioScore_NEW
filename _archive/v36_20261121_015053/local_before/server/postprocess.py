import numpy as np

from .engines.base import Note


def dedup_overlap(notes: list[Note], window_s: float = 0.2) -> list[Note]:
    """优化四: 重叠分片去重。
    MuScriptor 按 5 秒分片自回归解码, 跨分片边界的音符可能重复。
    规则: 同 (program, pitch) 且 onset 间隔 < window 的两个音符合并,
    保留更长时值。"""
    notes = sorted(notes, key=lambda n: (n.program, n.is_drum, n.pitch, n.start))
    out: list[Note] = []
    for n in notes:
        prev = out[-1] if out else None
        if (prev is not None
                and prev.program == n.program and prev.is_drum == n.is_drum
                and prev.pitch == n.pitch
                and abs(n.start - prev.start) < window_s):
            prev.end = max(prev.end, n.end)
        else:
            out.append(n)
    return out


def filter_short_notes(notes: list[Note], min_dur_s: float = 0.06) -> list[Note]:
    """碎音符过滤: < 60ms 的音符在 DAW 里很吵。鼓(仅 onset)豁免。"""
    return [n for n in notes if n.is_drum or (n.end - n.start) >= min_dur_s]


def rebuild_velocity(notes: list[Note], audio_path: str,
                     vmin: int = 30, vmax: int = 110) -> list[Note]:
    """力度重建: MuScriptor 不输出 velocity。
    用原始音频的 RMS 包络在音符 onset 处采样, 归一化映射到 [vmin, vmax]。
    局限: 对多乐器混音这是全局能量而非分轨能量, 只能提供大致动态。"""
    if not notes:
        return notes
    import librosa
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    if y.size == 0:
        return notes
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    if rms.max() <= 0:
        return notes
    times = librosa.times_like(rms, sr=sr, hop_length=512)
    for n in notes:
        idx = int(np.searchsorted(times, n.start))
        idx = min(idx, len(rms) - 1)
        # onset 处取前后 3 帧的最大值, 对齐更稳
        seg = rms[max(0, idx - 1): idx + 3]
        amp = float(seg.max()) / float(rms.max())
        n.velocity = int(vmin + (vmax - vmin) * (amp ** 0.6))
    return notes


def run_pipeline(notes: list[Note], audio_path: str, cfg: dict) -> list[Note]:
    if cfg.get("dedup", True):
        notes = dedup_overlap(notes, cfg.get("dedup_window_ms", 200) / 1000)
    if cfg.get("filter_short", True):
        notes = filter_short_notes(notes, cfg.get("min_note_ms", 60) / 1000)
    if cfg.get("rebuild_velocity", False):
        notes = rebuild_velocity(
            notes, audio_path,
            cfg.get("velocity_min", 30), cfg.get("velocity_max", 110))
    return sorted(notes, key=lambda n: (n.start, n.pitch))
