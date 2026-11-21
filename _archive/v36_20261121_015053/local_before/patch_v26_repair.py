# -*- coding: utf-8 -*-
"""v26-repair:
(1) repair as_eval.py syntax corruption (v19 bug: \\n became real newlines)
(2) find the REAL FastAPI app (run.py + server/ package; server.py never existed)
    -> install as_eval hook + /api/health there (evidence-driven)
(3) dump run.py full + server package engine-init lines -> map for v27 fix"""
from pathlib import Path
import re, py_compile, subprocess, sys, socket

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []

def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False
info.append("port 8000: " + ("RUNNING" if probe(8000) else "stopped"))

# ---------- 1. repair as_eval.py ----------
ep = ROOT / "as_eval.py"
s = ep.read_text(encoding="utf-8")
FIXES = [
    (r'p\.write_text\("\n"\.join\(out\) \+ "\n", encoding="utf-8-sig"\)',
     'p.write_text("\\n".join(out) + "\\n", encoding="utf-8-sig")'),
    (r'f\.write\("%s \| %s \| best=%s \| %s\n" % \(',
     'f.write("%s | %s | best=%s | %s\\n" % ('),
    (r'f\.write\("%s \| %s \| no valid result\n" % \(ts, mode\)\)',
     'f.write("%s | %s | no valid result\\n" % (ts, mode))'),
]
for pat, rep in FIXES:
    n = len(re.findall(pat, s))
    if n == 0:
        info.append("repair: pattern not found (maybe fixed): " + pat[:50])
        continue
    s = re.sub(pat, lambda m, r=rep: r, s)
    ok.append("as_eval repair: fixed %d spot(s)" % n)
ep.write_text(s, encoding="utf-8")
try:
    py_compile.compile(str(ep), doraise=True)
    ok.append("as_eval.py compile OK  <-- syntax repaired")
except py_compile.PyCompileError as e:
    fail.append("as_eval STILL broken: " + str(e)[:300])
    m = re.search(r'line (\d+)', str(e))
    if m:
        ln = int(m.group(1))
        lines = s.splitlines()
        for k in range(max(0, ln-4), min(len(lines), ln+3)):
            print("  %s%d: %s" % (">>" if k+1 == ln else "  ", k+1, lines[k]))

# ---------- re-time as_eval import ----------
try:
    r = subprocess.run(
        [sys.executable, "-c",
         "import time,sys;sys.path.insert(0,r'" + str(ROOT) +
         "');t0=time.time();import as_eval;"
         "print('AS_EVAL_IMPORT_SEC=%.2f'%(time.time()-t0))"],
        capture_output=True, text=True, timeout=120)
    tail = (r.stdout.strip() or r.stderr.strip()[-150:])
    print("as_eval import ->", tail)
except Exception as e:
    fail.append("import test failed: %s" % str(e)[:120])

# ---------- 2. find the REAL app ----------
files = [p for p in ROOT.glob("*.py")] + \
        ([p for p in (ROOT / "server").glob("*.py")]
         if (ROOT / "server").exists() else [])
cands = []
for p in files:
    t = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"FastAPI\s*\(", t):
        routes = len(re.findall(r"@app\.(get|post|websocket)", t))
        cands.append((p, routes, t))
print()
print("==== FastAPI app candidates ====")
for p, routes, _ in cands:
    print("  %s  (@app routes: %d)" % (p, routes))
target = None
if len(cands) == 1:
    target = cands[0]
else:
    scored = sorted(cands, key=lambda x: -x[1])
    if scored and scored[0][1] > 0 and \
       (len(scored) == 1 or scored[0][1] > scored[1][1]):
        target = scored[0]
        info.append("picked by route count: %s" % target[0].name)
if target is None:
    fail.append("cannot decide app file - paste the candidate list above")
else:
    ap, _, at = target
    if "==AS_EVAL_HOOK==" in at:
        ok.append("%s: hook already present" % ap.name)
    else:
        lines = at.splitlines(keepends=True)
        idx = None
        for i, l in enumerate(lines):
            if re.search(r"app\s*=\s*FastAPI\(", l):
                idx = i; break
        if idx is None:
            fail.append("%s: FastAPI( line not located" % ap.name)
        else:
            bal, end = 0, idx
            for j in range(idx, len(lines)):
                bal += lines[j].count("(") - lines[j].count(")")
                if bal <= 0: end = j; break
            HOOK = ('# ==AS_EVAL_HOOK v26==\n'
                    'import sys as _as_sys\n'
                    '_as_sys.path.insert(0, r"' + str(ROOT) + '")\n'
                    'try:\n'
                    '    import as_eval as _as_eval\n'
                    '    _as_eval.install_live(app)\n'
                    '    print("[OK] as_eval endpoints installed")\n'
                    'except Exception:\n'
                    '    import traceback as _as_tb\n'
                    '    print("[FAIL] as_eval hook:")\n'
                    '    _as_tb.print_exc()\n'
                    '\n'
                    '@app.get("/api/health")\n'
                    'def _as_health():\n'
                    '    return {"ok": True}\n'
                    '# ==/AS_EVAL_HOOK==\n')
            lines.insert(end + 1, HOOK)
            ap.write_text("".join(lines), encoding="utf-8")
            ok.append("%s: as_eval hook + /api/health inserted "
                      "(after FastAPI(...) line %d)" % (ap.name, end + 1))
    try:
        py_compile.compile(str(ap), doraise=True)
        ok.append("%s compile OK" % ap.name)
    except py_compile.PyCompileError as e:
        fail.append("%s compile FAIL: %s" % (ap.name, str(e)[:250]))

# ---------- 3. evidence dumps for v27 ----------
rp = ROOT / "run.py"
if rp.exists():
    print()
    print("==== run.py FULL ====")
    print(rp.read_text(encoding="utf-8", errors="ignore"))
spkg = ROOT / "server"
if spkg.exists():
    print("==== server/ package ====")
    pat = re.compile(r"engine|basic_pitch|tensorflow|load|model|Model|init"
                     r"|startup|on_event|asyncio|thread", re.I)
    for p in sorted(spkg.glob("*.py")):
        t = p.read_text(encoding="utf-8", errors="ignore")
        ls_ = t.splitlines()
        hits = [(i + 1, l) for i, l in enumerate(ls_) if pat.search(l)]
        print("-- %s (%d lines, %d engine-ish) --" % (p.name, len(ls_), len(hits)))
        for ln, l in hits[:25]:
            print("  L%d: %s" % (ln, l.strip()[:110]))
else:
    fail.append("server/ package not found either - paste dir listing")

print()
print("==== V26-REPAIR ====")
for l in ok:   print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("=====================")
