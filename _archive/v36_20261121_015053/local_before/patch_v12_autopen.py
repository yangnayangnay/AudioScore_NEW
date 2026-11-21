# -*- coding: utf-8 -*-
"""v12-autopen: auto-open browser from server.py after TCP port ready.
Removes fragile PowerShell poller from start.bat. AS_NO_OPEN=1 opt-out."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- locate server file ----------
srv = None
for c in [ROOT/"server.py", ROOT/"main.py", ROOT/"app.py"] + list(ROOT.glob("*.py")):
    if c.exists() and "uvicorn" in c.read_text(encoding="utf-8", errors="ignore"):
        srv = c; break
if not srv: raise SystemExit("FAIL: no uvicorn server file")
src = srv.read_text(encoding="utf-8", errors="ignore")

# ---------- locate start.bat (for port hint) ----------
sb = ROOT / "start.bat"
battext = sb.read_text(encoding="utf-8", errors="ignore") if sb.exists() else ""

def detect_port():
    m = re.search(r"uvicorn\.run[\s\S]{0,500}?port\s*=\s*(\d{4,5})", src)
    if m: return m.group(1)
    m = re.search(r"(?m)^\s*.*?\bport\s*=\s*(\d{4,5})", src)
    if m: return m.group(1)
    m = re.search(r"--port[= ](\d{4,5})", battext)
    if m: return m.group(1)
    m = re.search(r":(\d{4,5})", battext)
    if m: return m.group(1)
    return "8000"

PORT = detect_port()
ok.append("detected port: %s (server=%s)" % (PORT, srv.name))

# ---------- 1. server.py: autoopen hook ----------
if "==AS_AUTOOPEN==" not in src:
    m = re.search(r"(?m)^\s*app\s*=\s*FastAPI\(", src)
    if m:
        nl = src.find("\n", m.start())
        BLOCK = (
"\n# ==AS_AUTOOPEN v1== open browser when port is ready\n"
"def _as_autoopen():\n"
"    try:\n"
"        import os, time, socket, threading, subprocess\n"
"        if os.environ.get('AS_NO_OPEN') == '1':\n"
"            return\n"
"        _P = " + PORT + "\n"
"        def _go():\n"
"            try:\n"
"                t0 = time.time()\n"
"                while time.time() - t0 < 30:\n"
"                    try:\n"
"                        s = socket.create_connection(('127.0.0.1', _P), 0.5)\n"
"                        s.close(); break\n"
"                    except Exception:\n"
"                        time.sleep(0.2)\n"
"                time.sleep(0.3)\n"
"                try:\n"
"                    os.startfile('http://localhost:%d' % _P)\n"
"                except Exception:\n"
"                    subprocess.Popen(['cmd', '/c', 'start', '',\n"
"                                      'http://localhost:%d' % _P])\n"
"            except Exception:\n"
"                pass\n"
"        threading.Thread(target=_go, daemon=True).start()\n"
"    except Exception:\n"
"        pass\n"
"_as_autoopen()\n")
        src2 = src[:nl+1] + BLOCK + src[nl+1:]
        srv.write_text(src2, encoding="utf-8")
        ok.append("server.py: autoopen hook injected (port %s)" % PORT)
    else:
        fail.append("server.py: app=FastAPI not found -> autoopen NOT injected")
else:
    ok.append("server.py: autoopen already present")

# ---------- 2. start.bat: strip pollers / old open lines ----------
if sb.exists():
    bak = ROOT / "start.bat.bak"
    base = bak.read_text(encoding="utf-8", errors="ignore") if bak.exists() else battext
    lines = base.splitlines()
    drop = lambda l: (
        "api/health" in l
        or re.search(r'start\s+(""\s+)?["\']?https?://', l, re.I)
        or re.match(r'\s*:as_(wait|ready)', l)
        or re.search(r'goto as_(wait|ready)', l)
        or "AS_TRIES" in l)
    lines = [l for l in lines if not drop(l)]
    sb.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    ok.append("start.bat: poller/open lines stripped (%d lines kept)" % len(lines))
else:
    fail.append("start.bat not found (server-side open still works if you run server directly)")

# ---------- 3. fallback: if server hook failed, add curl wait loop to bat ----------
if any("autoopen NOT injected" in f for f in fail) and sb.exists():
    t = sb.read_text(encoding="utf-8", errors="ignore")
    if ":as_wait" not in t:
        run_i = -1
        for i, l in enumerate(t.splitlines()):
            if re.search(r'python|uvicorn|server\.py|main\.py|app\.py', l, re.I) \
               and not re.match(r'\s*rem\b', l, re.I):
                run_i = i; break
        if run_i < 0: run_i = len(t.splitlines())
        FB = ("set /a AS_TRIES=0\r\n"
              ":as_wait\r\n"
              "curl -s -o NUL -m 2 http://localhost:" + PORT + "/api/health\r\n"
              "if not errorlevel 1 goto as_ready\r\n"
              "set /a AS_TRIES+=1\r\n"
              "if %AS_TRIES% geq 240 goto as_ready\r\n"
              "timeout /t 1 /nobreak >nul\r\n"
              "goto as_wait\r\n"
              ":as_ready\r\n"
              "start \"\" http://localhost:" + PORT + "\r\n")
        ls2 = t.splitlines()
        out = ls2[:run_i] + FB.splitlines() + ls2[run_i:]
        sb.write_text("\r\n".join(out) + "\r\n", encoding="utf-8")
        ok.append("start.bat: curl-wait fallback added (port %s)" % PORT)

print()
print("==== V12-AUTOOPEN RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
