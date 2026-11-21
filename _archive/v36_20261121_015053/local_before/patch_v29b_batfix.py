# -*- coding: utf-8 -*-
"""v29b-batfix: corrected start.bat rewrite (no curl poller).
v29 failed: a line starting with '@ terminated the PS here-string early ->
parse errors -> patch never written (nothing was modified on disk).
Fixes: @echo off line now double-quoted (no leading '@), removed bogus
unicode_escape round-trip, explicit CRLF bytes, verify after write."""
from pathlib import Path
import socket

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []

def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False
info.append("port 8000 now: " + ("RUNNING" if probe(8000) else "stopped"))

helper = ROOT / "as_autoopen.py"
if helper.exists():
    ok.append("as_autoopen.py exists (auto-open preserved)")
else:
    fail.append("as_autoopen.py MISSING")

bat = ROOT / "start.bat"
if not bat.exists():
    fail.append("start.bat missing")
else:
    bak = ROOT / "start.bat.v28bak"
    if not bak.exists():
        bak.write_bytes(bat.read_bytes())
        ok.append("backup -> start.bat.v28bak")
    else:
        info.append("backup already exists, kept original")

    L = [
        "@echo off",
        'set "HF_ENDPOINT=https://hf-mirror.com"',
        'set "HF_HUB_OFFLINE=1"',
        "chcp 65001 >nul",
        "cd /d %~dp0",
        "",
        "if not exist .venv\\Scripts\\activate.bat (",
        "    echo [\u9519\u8bef] \u8fd8\u6ca1\u6709\u73af\u5883, \u8bf7\u5148\u8fd0\u884c setup.bat",
        "    pause & exit /b 1",
        ")",
        "",
        "call .venv\\Scripts\\activate.bat",
        "",
        "echo.",
        "echo \u6b63\u5728\u83b7\u53d6\u672c\u673a\u5c40\u57df\u7f51 IP(\u624b\u673a\u8bbf\u95ee\u7528)...",
        "for /f \"tokens=2 delims=:\" %%a in ('ipconfig ^| findstr /c:\"IPv4\"') do (",
        "    for /f \"tokens=* delims= \" %%b in (\"%%a\") do set LAN_IP=%%b",
        ")",
        "",
        "echo.",
        "echo   \u7535\u8111\u8bbf\u95ee:  http://localhost:8000",
        "echo   \u624b\u673a\u8bbf\u95ee:  http://%LAN_IP%:8000",
        "echo   \u5173\u95ed\u670d\u52a1:  \u76f4\u63a5\u5173\u6389\u672c\u7a97\u53e3",
        "echo.",
        "echo ============================================",
        "echo  [!] \u5f15\u64ce\u540e\u53f0\u52a0\u8f7d, \u670d\u52a1\u901a\u5e38 3-5 \u79d2\u5373\u53ef\u8bbf\u95ee.",
        "echo  \u6d4f\u89c8\u5668\u5c06\u81ea\u52a8\u6253\u5f00; \u6ca1\u5f39\u5c31\u624b\u52a8\u8bbf\u95ee\u4e0a\u9762\u7684\u5730\u5740.",
        "echo ============================================",
        "",
        "start \"as-autoopen\" /min python \"%~dp0as_autoopen.py\" 8000",
        "python run.py",
        "pause",
    ]
    NEW_BAT = "\r\n".join(L) + "\r\n"
    bat.write_bytes(NEW_BAT.encode("utf-8"))
    ok.append("start.bat rewritten (CRLF, UTF-8 no BOM, poller removed)")

    back = bat.read_bytes().decode("utf-8", "ignore")
    if "as_wait" in back or "AS_TRIES" in back:
        fail.append("VERIFY FAIL: poller remnants still present?!")
    elif "python run.py" not in back:
        fail.append("VERIFY FAIL: run.py launch line missing")
    else:
        ok.append("VERIFY OK: no poller; helper + python run.py are the exec lines")
    print()
    print("==== new start.bat ====")
    print(back)
    print("=======================")

print()
print("==== V29B-BATFIX ====")
for l in ok:   print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("=====================")
