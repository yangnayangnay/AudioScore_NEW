# -*- coding: utf-8 -*-
"""as_live: stdout/stderr tee -> ring buffer + GET /api/as/logs"""
import sys, time, re, threading
from collections import deque
_RING = deque(maxlen=400)
_BUF = {"out": "", "err": ""}
_LOCK = threading.Lock()
_PCT = [None, 0.0]
_PCT_RE = re.compile(r"(\d{1,3})\s*%")
def _push(tag, ln):
    ln = ln.strip()
    if not ln: return
    m = _PCT_RE.search(ln)
    if m:
        v = int(m.group(1))
        if 0 <= v <= 100: _PCT[0], _PCT[1] = v, time.time()
    _RING.append({"t": time.strftime("%H:%M:%S"), "s": tag, "l": ln[:500]})
def _feed(tag, s):
    with _LOCK:
        _BUF[tag] += s
        segs = re.split(r"[\r\n]+", _BUF[tag])
        _BUF[tag] = segs.pop()
        for ln in segs: _push(tag, ln)
def _drain(tag):
    with _LOCK:
        if _BUF[tag].strip():
            _push(tag, _BUF[tag]); _BUF[tag] = ""
class _Tee(object):
    def __init__(self, orig, tag):
        self.orig = orig; self.tag = tag; self._as_tee = True
    def write(self, s):
        try: _feed(self.tag, s)
        except Exception: pass
        return self.orig.write(s)
    def flush(self):
        try: _drain(self.tag)
        except Exception: pass
        return self.orig.flush()
    def __getattr__(self, name): return getattr(self.orig, name)
def install_tee():
    if isinstance(sys.stdout, _Tee): return
    sys.stdout = _Tee(sys.stdout, "out")
    sys.stderr = _Tee(sys.stderr, "err")
    _push("out", "[as_live] tee installed")
def install_live(app):
    @app.get("/api/as/logs")
    def as_logs(n: int = 30):
        k = max(1, min(int(n), 400))
        with _LOCK: lines = list(_RING)[-k:]
        return {"lines": lines, "progress": _PCT[0],
                "progress_at": _PCT[1], "now": time.time()}
