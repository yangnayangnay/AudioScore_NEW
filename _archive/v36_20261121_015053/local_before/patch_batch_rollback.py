# -*- coding: utf-8 -*-
"""Rollback batch_size to 1 (keep fp16), then show full traceback from log."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")

# ---- 1. config: batch_size 4 -> 1 ----
f = ROOT / "config.yaml"
s = f.read_text(encoding="utf-8")
s2, n = re.subn(r"^(\s*)batch_size:\s*4\s*$", r"\1batch_size: 1", s, flags=re.M)
if n:
    f.write_text(s2, encoding="utf-8")
    print("[FIX] config: batch_size 4 -> 1 (KV cache back to 1x size)")
elif re.search(r"^\s*batch_size:\s*1\s*$", s, flags=re.M):
    print("[SKIP] batch_size already 1")
else:
    print("[WARN] batch_size line not found - check config manually")

# ---- 2. show the REAL error from log ----
log = ROOT / "logs" / "muscriptor.log"
if log.exists():
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    print()
    print("==== last 80 lines of muscriptor.log ====")
    for l in lines[-80:]:
        print(" ", l)
else:
    print("[WARN] no logs/muscriptor.log found")
