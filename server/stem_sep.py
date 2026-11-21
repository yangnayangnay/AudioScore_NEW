import glob
import os
import shutil
import subprocess
import sys

from .config import CFG, TMP_DIR

STEMS = ("drums", "bass", "other", "vocals")

# tier -> {逻辑音轨: 参与混音的源 stem}
TIER_STEMS = {
    1: {"drums": ["drums"], "rest": ["bass", "other", "vocals"]},
    2: {"drums": ["drums"], "bass": ["bass"], "rest": ["other", "vocals"]},
    3: {"drums": ["drums"], "bass": ["bass"], "vocals": ["vocals"], "other": ["other"]},
}

def _dir(audio_hash):
    return os.path.join(TMP_DIR, "stems_" + audio_hash[:16])

def _raw_ok(d):
    return all(os.path.exists(os.path.join(d, s + ".wav")) for s in STEMS)

def _cli_cmd():
    exe = shutil.which("demucs")
    if exe:
        return [exe]
    return [sys.executable, "-m", "demucs.separate"]

def separate(audio_path, audio_hash, timeout=None):
    """跑一次 htdemucs 四轨分离，按 audio_hash 缓存。返回 stems 目录。"""
    d = _dir(audio_hash)
    if _raw_ok(d):
        return d
    cfg = CFG.get("separation", {}) or {}
    model = str(cfg.get("model", "htdemucs"))
    dev = str(cfg.get("device") or "auto")
    os.makedirs(d, exist_ok=True)
    cmd = _cli_cmd() + ["-n", model, "--out", d]
    if dev and dev.lower() != "auto":
        cmd += ["-d", dev]
    cmd += [audio_path]
    try:
        _tv = int(timeout) if timeout is not None else None
    except (TypeError, ValueError):
        _tv = None
    t = _tv if (_tv is not None and _tv > 0) else None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise RuntimeError("音轨分离超时。可在 config.yaml 设 separation.device: cpu（CPU 慢但稳）或把超时设为 0")
    if r.returncode != 0:
        raise RuntimeError("Demucs 分离失败 (code " + str(r.returncode) + "):\n"
                           + ((r.stderr or r.stdout) or "")[-1500:])
    for s in STEMS:
        hits = glob.glob(os.path.join(d, "**", s + ".wav"), recursive=True)
        if not hits:
            raise RuntimeError("Demucs 输出缺少 " + s + ".wav")
        shutil.copyfile(hits[0], os.path.join(d, s + ".wav"))
    if _raw_ok(d):
        return d
    raise RuntimeError("Demucs 未产出预期 stem 文件")

def mix_stems(audio_hash, tier, stem_name):
    """返回某档位某逻辑音轨的 wav 路径（多源 stem 时现场混音并缓存）。"""
    import numpy as np
    import librosa
    import soundfile as sf
    spec = TIER_STEMS.get(int(tier))
    if not spec or stem_name not in spec:
        raise RuntimeError("未知分轨规格: tier=" + str(tier) + " stem=" + str(stem_name))
    parts = spec[stem_name]
    d = _dir(audio_hash)
    if len(parts) == 1:
        return os.path.join(d, parts[0] + ".wav")
    out_path = os.path.join(d, "mix_" + stem_name + ".wav")
    if os.path.exists(out_path):
        return out_path
    mix = None
    sr = 44100
    for p in parts:
        y, sr = librosa.load(os.path.join(d, p + ".wav"), sr=44100, mono=False)
        if y.ndim == 1:
            y = np.stack([y, y])
        mix = y if mix is None else mix + y
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 1.0:
        mix = mix / peak * 0.99
    sf.write(out_path, mix.T, sr)
    return out_path
