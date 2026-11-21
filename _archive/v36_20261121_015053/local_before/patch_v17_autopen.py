# -*- coding: utf-8 -*-
"""v17-autopen: guaranteed browser auto-open.
- as_autoopen.py: standalone poller (stdlib only), opens browser when port up
- start.bat: strip old poller remnants, insert helper BEFORE server launch
- server.py: remove v12 ==AS_AUTOOPEN== block if present (avoid double-open)
- python exe reused from the bat's own launch line (venv-agnostic)
"""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- find the launcher bat ----------
cands = [ROOT/"start.bat", ROOT/"run.bat", ROOT/"start_server.bat"]
cands += [p for p in ROOT.glob("*.bat") if p.name.lower() not in
          ("setup.bat", "install.bat", "patch_v17_autopen.py")]
BAT = None
for c in cands:
    if c.exists():
        t = c.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"python|uvicorn", t, re.I):
            BAT = c; BATTEXT = t; break
if BAT is None:
    fail.append("no launcher bat found (start.bat/run.bat/...)")
else:
    ok.append("launcher: %s" % BAT.name)

# ---------- detect port ----------
PORT = None
if BAT is not None:
    for pat in (r"--port[= ](\d{4,5})", r"(?im)^\s*set\s+PORT\s*=\s*(\d{4,5})",
                r"localhost:(\d{4,5})", r":(\d{4,5})\s*\"?\s*$"):
        m = re.search(pat, BATTEXT, re.M)
        if m: PORT = m.group(1); break
if PORT is None:
    for name in ("server.py", "main.py", "app.py"):
        p = ROOT / name
        if p.exists():
            m = re.search(r"port\s*=\s*(\d{4,5})",
                          p.read_text(encoding="utf-8", errors="ignore"))
            if m: PORT = m.group(1); break
if PORT is None: PORT = "8000"
ok.append("detected port: %s  <-- VERIFY THIS" % PORT)

# ---------- 1. helper ----------
HELPER = '''# -*- coding: utf-8 -*-
"""as_autoopen: wait for local port, then open default browser (v17)."""
import sys, os, socket, time, subprocess, tempfile

LOG = os.path.join(tempfile.gettempdir(), "as_autoopen.log")
def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%H:%M:%S] ") + msg + "\\n")
    except Exception:
        pass

def main():
    if os.environ.get("AS_NO_OPEN") == "1":
        return
    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    except ValueError:
        port = 8000
    log("helper start, port=%d" % port)
    deadline = time.time() + 90
    up = False
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close(); up = True; break
        except OSError:
            time.sleep(0.3)
    if not up:
        log("TIMEOUT after 90s, port never came up"); return
    time.sleep(0.6)
    url = "http://127.0.0.1:%d" % port
    try:
        os.startfile(url)
        log("opened via os.startfile: %s" % url)
    except Exception as e:
        log("os.startfile failed: %r, trying cmd start" % e)
        try:
            subprocess.Popen(["cmd", "/c", "start", "", url])
            log("opened via cmd start")
        except Exception as e2:
            log("cmd start also failed: %r" % e2)

main()
'''
(ROOT / "as_autoopen.py").write_text(HELPER, encoding="utf-8")
ok.append("as_autoopen.py written (log: %TEMP%\\as_autoopen.log)")

# ---------- 2. strip v12 server.py hook (avoid double-open) ----------
for name in ("server.py", "main.py", "app.py"):
    p = ROOT / name
    if not p.exists(): continue
    t = p.read_text(encoding="utf-8", errors="ignore")
    if "==AS_AUTOOPEN==" in t:
        t2 = re.sub(r"\n# ==AS_AUTOOPEN==.*?_as_autoopen\(\)\n", "\n", t, flags=re.S)
        if t2 != t:
            p.write_text(t2, encoding="utf-8")
            ok.append("%s: old v12 autoopen block removed" % name)

# ---------- 3. patch launcher bat ----------
if BAT is not None:
    lines = BATTEXT.splitlines()
    # reuse the python exe the bat itself uses
    launch_i = None
    for i, l in enumerate(lines):
        ll = l.strip().lower()
        if not ll or ll.startswith("rem") or ll.startswith("::"): continue
        if re.search(r"python|uvicorn", ll):
            launch_i = i; break
    py = '"%~dp0.venv\\Scripts\\python.exe"'
    if launch_i is not None:
        m = re.search(r'("[^"]*pythonw?\.exe"|[^"\s]*pythonw?\.exe|python\b)',
                      lines[launch_i], re.I)
        if m: py = m.group(1)
    def is_junk(l):
        ll = l.lower()
        return ("api/health" in ll or "as_tries" in ll
                or "invoke-webrequest" in ll or "as_autoopen.py" in l
                or bool(re.match(r"\s*:as_(wait|ready)", l))
                or "goto as_" in ll)
    lines = [l for l in lines if not is_junk(l)]
    newline = ('start "as-autoopen" /min %s "%~dp0as_autoopen.py" %s'
               % (py, PORT))
    if launch_i is not None and launch_i < len(lines):
        lines.insert(launch_i, newline)
        ok.append("start line inserted BEFORE server launch (reuse py=%s)" % py)
    else:
        pos = 1 if lines and lines[0].strip().lower() == "@echo off" else 0
        lines.insert(pos, newline)
        ok.append("no explicit launch line found; helper inserted near top")
    BAT.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

print()
print("==== V17-AUTOOPEN RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
