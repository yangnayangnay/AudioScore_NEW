import os
import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(_ROOT, "config.yaml")

with open(CFG_PATH, "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

# 运行时目录
TMP_DIR = os.path.join(_ROOT, "tmp")
OUT_DIR = os.path.join(_ROOT, "output")
CACHE_DIR = os.path.join(_ROOT, "cache")
WEB_DIR = os.path.join(_ROOT, "web")
for d in (TMP_DIR, OUT_DIR, CACHE_DIR):
    os.makedirs(d, exist_ok=True)
