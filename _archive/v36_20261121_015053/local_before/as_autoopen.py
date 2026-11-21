# -*- coding: utf-8 -*-
"""as_autoopen: wait for local port, then open default browser (v17)."""
import sys, os, socket, time, subprocess, tempfile

LOG = os.path.join(tempfile.gettempdir(), "as_autoopen.log")
def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%H:%M:%S] ") + msg + "\n")
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
