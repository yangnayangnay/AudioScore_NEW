# -*- coding: utf-8 -*-
"""v34-mini: get_engine fallback truth + is_available + confidence search"""
from pathlib import Path
import re
ROOT = Path(r"E:\Code\cs\AudioScore_new")
print("---- get_engine FULL ----")
print((ROOT/"server"/"engines"/"__init__.py").read_text(encoding="utf-8"))
for n in ("muscriptor.py", "basicpitch.py"):
    t = (ROOT/"server"/"engines"/n).read_text(encoding="utf-8")
    m = re.search(r"(?ms)def is_available.*?(?=\n    def |\nclass |\Z)", t)
    print("---- %s.is_available ----" % n)
    print(m.group(0) if m else "(not found)")
    for i, l in enumerate(t.splitlines(), 1):
        if re.search(r"Path|exists|checkpoint|assets|\.pt|\.onnx|\.bin", l):
            print("   L%d| %s" % (i, l.strip()[:110]))
print("---- confidence in UI? ----")
h = (ROOT/"web"/"index.html").read_text(encoding="utf-8")
print("literal:", h.count("\u7f6e\u4fe1\u5ea6"),
      "| escaped:", h.count("\\u7f6e\\u4fe1"),
      "| 'confidence':", h.lower().count("confidence"))
