# -*- coding: utf-8 -*-
"""v22-once: startup UX fix with live evidence
- live probe: is server up RIGHT NOW (proof: stuck vs running)
- bat: loud banner BEFORE launch explaining 30-90s silent loading
- verify helper/server compile + dump helper log + print final bat"""
from pathlib import Path
import socket, py_compile, re, tempfile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []

# ---------- 0. LIVE PROBE ----------
def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False
up = probe(8000)
if up:
    info.append("PROBE: port 8000 RESPONDING -> 服务此刻正在运行, "
                "'卡在横线'=加载完成的正常等待态, 现在就能开 http://localhost:8000")
else:
    info.append("PROBE: port 8000 无响应 -> 服务当前没在跑(正常, 你关过窗口)")

# ---------- 1. bat: banner before launch ----------
cands = [ROOT / n for n in ("start.bat", "run.bat", "start_server.bat")]
BAT = next((c for c in cands if c.exists()), None)
if BAT is None:
    fail.append("no launcher bat found")
else:
    t = BAT.read_text(encoding="utf-8", errors="ignore")
    lines = [l for l in t.splitlines() if "[BOOT" not in l]
    m = re.search(r'("[^"]*pythonw?\.exe"|[^"\s]*pythonw?\.exe)', t, re.I)
    PY = m.group(1) if m else '"%~dp0.venv\\Scripts\\python.exe"'
    print("PY =", PY)
    launch_idx = None
    for i, l in enumerate(lines):
        ll = l.strip().lower()
        if (not ll or ll.startswith(("rem", "::", "echo", "set", "@echo"))
                or "as_autoopen" in ll):
            continue
        if re.search(r"python|uvicorn", ll):
            launch_idx = i; break
    if launch_idx is None:
        fail.append("cannot locate server launch line in %s" % BAT.name)
    else:
        print("launch line =", lines[launch_idx])
        ins = []
        if not any("as_autoopen.py" in l for l in lines):
            ins.append('start "as-autoopen" /min %s "%~dp0as_autoopen.py" 8000'
                       % PY)
        ins += [
            "echo ============================================",
            "echo  [!] \u6b63\u5728\u52a0\u8f7d\u6a21\u578b, \u9700\u8981 30-90 \u79d2,",
            "echo  \u671f\u95f4\u7a97\u53e3\u6ca1\u6709\u65b0\u8f93\u51fa\u662f\u6b63\u5e38\u7684, \u4e0d\u662f\u5361\u6b7b!",
            "echo  \u4e0d\u8981\u5173\u7a97\u53e3, \u4e0d\u8981\u5728\u7a97\u53e3\u91cc\u70b9\u9f20\u6807.",
            "echo  \u5c31\u7eea\u540e\u6d4f\u89c8\u5668\u81ea\u52a8\u6253\u5f00, \u6216\u624b\u52a8\u8bbf\u95ee:",
            "echo      http://localhost:8000",
            "echo ============================================",
        ]
        lines[launch_idx:launch_idx] = ins
        BAT.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        ok.append("%s: banner + helper placed before launch" % BAT.name)
    print()
    print("---- %s final content ----" % BAT.name)
    print("\n".join(lines))
    print("----------------------------")

# ---------- 2. helper + server verify ----------
hp = ROOT / "as_autoopen.py"
if hp.exists():
    try:
        py_compile.compile(str(hp), doraise=True)
        ok.append("as_autoopen.py compile OK")
    except py_compile.PyCompileError as e:
        fail.append("as_autoopen.py compile FAIL: %s" % str(e)[:200])
else:
    fail.append("as_autoopen.py MISSING")
logf = Path(tempfile.gettempdir()) / "as_autoopen.log"
if logf.exists():
    print()
    print("---- as_autoopen.log (tail) ----")
    print("\n".join(logf.read_text(encoding="utf-8",
                                   errors="ignore").splitlines()[-15:]))
else:
    info.append("as_autoopen.log \u4e0d\u5b58\u5728 (helper \u8fd8\u6ca1\u8dd1\u8fc7)")
sp = ROOT / "server.py"
try:
    py_compile.compile(str(sp), doraise=True)
    ok.append("server.py compile OK")
except py_compile.PyCompileError as e:
    fail.append("server.py compile FAIL: %s" % str(e)[:300])

print()
print("==== V22-ONCE ====")
for l in ok: print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("=================")
