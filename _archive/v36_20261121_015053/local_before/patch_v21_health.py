# -*- coding: utf-8 -*-
"""v21-health: add GET /api/health -> stop 404 spam (any poller source)
+ re-clean bat poller remnants + compile check."""
from pathlib import Path
import re, py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- server.py: add health route before first @app route ----------
sp = ROOT / "server.py"
t = sp.read_text(encoding="utf-8", errors="ignore")
if re.search(r"['\"](/api/health|/health)['\"]", t):
    ok.append("server.py: health route already exists, skip")
else:
    lines = t.splitlines(keepends=True)
    pos = None
    for i, l in enumerate(lines):
        if re.match(r"^\s*@app\.(get|post|put|websocket)\(", l):
            pos = i; break
    if pos is None:
        for i, l in enumerate(lines):
            if re.match(r"^\s*if\s+__name__\s*==", l):
                pos = i; break
    if pos is None:
        fail.append("server.py: no safe insertion point found")
    else:
        route = ('@app.get("/api/health")\n'
                 'def _as_health():\n'
                 '    return {"ok": True}\n\n')
        lines.insert(pos, route)
        sp.write_text("".join(lines), encoding="utf-8")
        ok.append("server.py: GET /api/health added (line %d)" % (pos + 1))

try:
    py_compile.compile(str(sp), doraise=True)
    ok.append("server.py compile OK")
except py_compile.PyCompileError as e:
    fail.append("server.py compile FAIL: %s" % str(e)[:300])

# ---------- bat: report/remove any remaining poller lines ----------
for name in ("start.bat", "run.bat", "start_server.bat"):
    p = ROOT / name
    if not p.exists(): continue
    t = p.read_text(encoding="utf-8", errors="ignore")
    hits = [l for l in t.splitlines()
            if "api/health" in l.lower() or "as_tries" in l.lower()]
    if not hits:
        ok.append("%s: no poller remnants" % name); continue
    lines = [l for l in t.splitlines()
             if "api/health" not in l.lower() and "as_tries" not in l.lower()]
    p.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    ok.append("%s: removed %d poller remnant line(s)" % (name, len(hits)))

print()
print("==== V21-HEALTH ====")
for l in ok:   print("  PASS:", l)
for l in fail: print("  FAIL:", l)
print("====================")
