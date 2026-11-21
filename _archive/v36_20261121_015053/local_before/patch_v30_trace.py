# -*- coding: utf-8 -*-
"""v30-trace: READ-ONLY. UTF-8-aware search for the rollback marker.
findstr gave a false negative (UTF-8 file vs GBK console pattern).
Prints every hit + the full enclosing function so the rollback logic
(exception->baseline vs score-comparison) can be fixed precisely."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ROLL = "\u56de\u6eda"                 # rollback
BACK = "\u56de\u9000"                 # fallback
SMART = "\u667a\u80fd\u53bb\u788e"    # smart de-fragment
REPORT = "\u6700\u4f18\u5904\u7406\u7ec4\u5408\u62a5\u544a"  # report header
TERMS = [ROLL, "rollback", BACK, "\u57fa\u7ebf", REPORT, SMART]

files = [ROOT / n for n in ("as_eval.py", "run.py", "web/index.html")
         if (ROOT / n).exists()]
sv = ROOT / "server"
if sv.exists():
    files += sorted(sv.rglob("*.py"))

def enclosing(lines, i):
    for j in range(i, -1, -1):
        if re.match(r"^\s*def\s+", lines[j]):
            return j
    return None

def dump_func(lines, start, cap=130):
    end = min(len(lines), start + cap)
    for j in range(start + 1, len(lines)):
        if re.match(r"^(def|class)\s", lines[j]):
            end = j
            break
    for k in range(start, end):
        print("  %4d| %s" % (k + 1, lines[k][:150]))

total_hits = 0
for f in files:
    try:
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as e:
        print("!! cannot read", f, e)
        continue
    hits = [i for i, l in enumerate(lines)
            if any(t.lower() in l.lower() for t in TERMS)]
    if not hits:
        continue
    total_hits += len(hits)
    print("=" * 70)
    print(f, "->", len(hits), "hit(s) at lines:",
          ", ".join(str(i + 1) for i in hits))
    done = set()
    for i in hits:
        d = enclosing(lines, i)
        key = d if d is not None else ("mod", i)
        if key in done:
            continue
        done.add(key)
        if d is not None:
            print("-- enclosing function (starts line %d) --" % (d + 1))
            dump_func(lines, d)
        else:
            print("-- module-level context around line %d --" % (i + 1))
            for k in range(max(0, i - 6), min(len(lines), i + 7)):
                print("  %4d| %s" % (k + 1, lines[k][:150]))
print()
print("==== V30-TRACE: %d hit(s) across %d file(s) ===="
      % (total_hits, len(files)))
print("Paste the printed function(s) back - I will fix the rollback")
print("branch (smart de-fragment) against the real source, no guessing.")
