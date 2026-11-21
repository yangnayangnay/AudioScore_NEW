import hashlib
import json
import os
import shutil

from .config import CACHE_DIR


def make_key(audio_hash: str, backend: str, instruments: list | None,
             bpm: int | None, post_cfg: dict) -> str:
    payload = json.dumps(
        [backend, sorted(instruments or []), bpm, post_cfg], sort_keys=True)
    return hashlib.sha256((audio_hash + payload).encode()).hexdigest()


def audio_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_get(key: str) -> str | None:
    p = os.path.join(CACHE_DIR, f"{key}.mid")
    return p if os.path.exists(p) else None


def cache_put(key: str, mid_path: str) -> str:
    dst = os.path.join(CACHE_DIR, f"{key}.mid")
    shutil.copy2(mid_path, dst)
    return dst
