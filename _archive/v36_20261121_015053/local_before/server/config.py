# -*- coding: utf-8 -*-
"""
server/config.py —— 全局配置 + 路径常量
1) CFG    : 从根目录 config.yaml 加载，缺键用内置默认值兜底
2) 路径常量: main.py 要 WEB_DIR，cache/jobs/midi_io 等要各自目录
"""

import os
import copy

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DEFAULTS = {
    "server": {"host": "0.0.0.0", "port": 8000},
    "engine": "muscriptor",
    "muscriptor": {
        "model": os.path.join(ROOT, "models", "muscriptor-large", "model.safetensors"),
    },
}


def _deep_merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def _load() -> dict:
    cfg = copy.deepcopy(_DEFAULTS)
    path = os.path.join(ROOT, "config.yaml")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if isinstance(loaded, dict):
            _deep_merge(cfg, loaded)
    return cfg


CFG = _load()

# ---------- 路径常量 ----------
DATA_DIR   = os.path.join(ROOT, "data")
CACHE_DIR  = os.path.join(DATA_DIR, "cache")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
JOBS_DIR   = os.path.join(DATA_DIR, "jobs")
MIDI_DIR   = os.path.join(DATA_DIR, "midi")
TMP_DIR    = os.path.join(DATA_DIR, "tmp")
MODEL_DIR  = os.path.join(ROOT, "models")
WEB_DIR    = os.path.join(ROOT, "web")          # ★ 网页界面目录（含 index.html）

for _d in (DATA_DIR, CACHE_DIR, UPLOAD_DIR, OUTPUT_DIR, JOBS_DIR, MIDI_DIR, TMP_DIR):
    os.makedirs(_d, exist_ok=True)

# 已知名字 -> 目录 的映射，供兜底用
_KNOWN_DIRS = {
    "CACHE": CACHE_DIR,   "UPLOAD": UPLOAD_DIR,  "UPLOADS": UPLOAD_DIR,
    "OUTPUT": OUTPUT_DIR, "OUT": OUTPUT_DIR,     "RESULT": OUTPUT_DIR,
    "RESULTS": OUTPUT_DIR, "JOB": JOBS_DIR,      "JOBS": JOBS_DIR,
    "MIDI": MIDI_DIR,     "TMP": TMP_DIR,        "TEMP": TMP_DIR,
    "MODEL": MODEL_DIR,   "MODELS": MODEL_DIR,
    "WEB": WEB_DIR,       "WEBROOT": WEB_DIR,    "STATIC": WEB_DIR,
    "FRONTEND": WEB_DIR,  "HTML": WEB_DIR,
}


def __getattr__(name: str):
    """模块级属性兜底。

    规矩：
      1) 双下划线内部属性（__path__/__all__ 等）-> 只抛 AttributeError；
      2) 未知 XXX_DIR -> 先看项目根目录有没有同名文件夹（如 web\），
         有就用它，没有才落到 data\ 下自动新建；
      3) 其它未知名字 -> AttributeError，并提示把报错发给助手。
    """
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(name)

    if name.endswith(("_DIR", "_PATH", "_DIRS", "_PATHS")):
        stem = name.rsplit("_", 1)[0].upper()
        if stem in _KNOWN_DIRS:
            d = _KNOWN_DIRS[stem]
        else:
            guess_root = os.path.join(ROOT, stem.lower())
            d = guess_root if os.path.isdir(guess_root) else os.path.join(DATA_DIR, stem.lower())
        os.makedirs(d, exist_ok=True)
        globals()[name] = d
        return d

    raise AttributeError(
        "server.config 里没有 '" + name + "' —— 把这行报错原样发给助手即可修复"
    )


# 启动自检
_m = CFG.get("muscriptor", {}).get("model", "")
if isinstance(_m, str) and _m and not os.path.exists(_m):
    print("[config] 提示: muscriptor 模型文件不存在: " + str(_m))
