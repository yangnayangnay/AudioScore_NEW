# -*- coding: utf-8 -*-
"""v33-audit: READ-ONLY evidence pass.
1) diff every file I touched vs your GitHub upload (line-level truth)
2) which backend is default; does any code map instruments (vs piano-only)
3) DOM inventory of local index.html: where is the inference button,
   does instrument/confidence setting still exist in markup"""
from pathlib import Path
import difflib, re, urllib.request, json

ROOT = Path(r"E:\Code\cs\AudioScore_new")
BASE = "https://raw.githubusercontent.com/yangnayangnay/AudioScore_NEW/main/"

TOUCHED = ["run.py", "start.bat", "as_eval.py", "web/index.html",
           "server/main.py", "server/engines/__init__.py",
           "server/engines/basicpitch.py", "server/engines/muscriptor.py"]

print("=" * 72)
print("[1] LOCAL vs GITHUB (files touched during startup/eval work)")
print("=" * 72)
for rel in TOUCHED:
    lp = ROOT / rel
    if not lp.exists():
        print("  %-34s LOCAL MISSING" % rel); continue
    try:
        raw = urllib.request.urlopen(BASE + rel, timeout=15).read()
        remote = raw.decode("utf-8", "ignore")
    except Exception as e:
        print("  %-34s GITHUB FETCH FAIL %s" % (rel, e)); continue
    local = lp.read_text(encoding="utf-8", errors="ignore")
    if local == remote:
        print("  %-34s IDENTICAL to github" % rel); continue
    diff = list(difflib.unified_diff(remote.splitlines(),
                                     local.splitlines(), lineterm="", n=0))
    adds = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    print("  %-34s +%-4d -%-4d (vs github)" % (rel, adds, dels))

print()
print("=" * 72)
print("[2] DEFAULT BACKEND + INSTRUMENT HANDLING (code facts)")
print("=" * 72)
ini = ROOT / "server" / "engines" / "__init__.py"
if ini.exists():
    t = ini.read_text(encoding="utf-8", errors="ignore")
    m = re.findall(r"(default[_ ]?engine|DEFAULT[_ ]?ENGINE)\s*=\s*[\"\'](\w+)", t)
    print("  engine registry/default:", m if m else "(not found, dump head)")
    if not m:
        print("    " + t[:300].replace("\n", "\n    "))
bp = ROOT / "server" / "engines" / "basicpitch.py"
if bp.exists():
    t = bp.read_text(encoding="utf-8", errors="ignore")
    hits = re.findall(r".*(program|instrument|channel|track_name).*", t, re.I)
    print("  basicpitch.py instrument/program mentions:",
          len(hits), "(0 = it never maps instruments -> piano output)")
ms = ROOT / "server" / "engines" / "muscriptor.py"
if ms.exists():
    t = ms.read_text(encoding="utf-8", errors="ignore")
    hits = re.findall(r".*(program|instrument|set_instrument).*", t, re.I)
    print("  muscriptor.py instrument/program mentions:", len(hits))

print()
print("=" * 72)
print("[3] LOCAL UI INVENTORY (is it lost, or just pushed down?)")
print("=" * 72)
h = (ROOT / "web" / "index.html").read_text(encoding="utf-8", errors="ignore")
PROBE = ["\u4e50\u5668\u7ea6\u675f", "\u7f6e\u4fe1\u5ea6",
         "\u4e50\u5668\u8bc6\u522b", "\u5f00\u59cb\u8f6c\u5199",
         "\u8f6c\u5199\u540e\u7aef", "\u529b\u5ea6\u91cd\u5efa",
         "\u6d4b\u8bd5\u6700\u4f18", "\u5e94\u7528\u5230MIDI"]
for p in PROBE:
    idx = h.find(p)
    print("  [%s] %s  (@char %d)" % ("OK " if idx >= 0 else "MISS", p, idx))
btns = re.findall(r"<button[^>]*id=[\"\']([\w\-]+)[\"\']", h)
print("  button ids:", ", ".join(btns[:40]) if btns else "(none)")

print()
print("==== V33-AUDIT DONE (read-only) ====")
