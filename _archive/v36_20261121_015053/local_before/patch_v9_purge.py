# -*- coding: utf-8 -*-
"""v9-purge: physically remove pp6/8/9/12/14/15/16 from execution path.
Server middleware strips them from any incoming job; client DOM deletes
the checkboxes; v8 simplify script removed (no longer needed)."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

HARMFUL = {"pp6","pp8","pp9","pp12","pp14","pp15","pp16",
           "harmonic_fix","voice_split","fit_tempo","onset_snap",
           "dyn_thresh","dur_norm","dtw_diag","dtw","onset_refine",
           "harmonic","duration_norm","dynamic_threshold"}

# ---------- 1. as_guard.py: server middleware ----------
GUARD = r'''# -*- coding: utf-8 -*-
"""as_guard: strip accuracy-harming pp options from any incoming request.
Physical removal from execution path - regardless of what client sends,
these params are forced off before reaching muscriptor."""
from pathlib import Path
import json

_HARMFUL = {"pp6","pp8","pp9","pp12","pp14","pp15","pp16",
            "harmonic_fix","voice_split","fit_tempo","onset_snap",
            "dyn_thresh","dur_norm","dtw_diag","dtw","onset_refine",
            "harmonic","duration_norm","dynamic_threshold"}

def _scrub_dict(d):
    if not isinstance(d, dict): return d, 0
    n = 0
    for k in list(d.keys()):
        if str(k).lower() in _HARMFUL:
            d[k] = False if isinstance(d[k], bool) else 0
            n += 1
    return d, n

def install_live(app):
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class AsGuardMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.method in ("POST","PUT","PATCH"):
                ctype = (request.headers.get("content-type") or "").lower()
                if "application/json" in ctype:
                    try:
                        body = await request.body()
                        data = json.loads(body or b"{}")
                        data, n = _scrub_dict(data)
                        if n:
                            new_body = json.dumps(data).encode()
                            request = Request(request.scope, receive=lambda: None)
                            request._body = new_body
                            # rebuild receive
                            async def rx():
                                return {"type":"http.request","body":new_body,"more_body":False}
                            request = Request(request.scope, receive=rx)
                    except Exception:
                        pass
                elif "form" in ctype or "multipart" in ctype:
                    # for multipart, we can't easily rewrite; rely on client
                    # not sending harmful keys. As defense-in-depth, we also
                    # patch muscriptor postproc at the source below.
                    pass
            return await call_next(request)

    app.add_middleware(AsGuardMiddleware)

    # defense-in-depth: monkey-patch any function in muscriptor namespace
    # that might consume these flags (best-effort, won't crash if absent)
    try:
        import muscriptor  # noqa
        for attr in dir(muscriptor):
            fn = getattr(muscriptor, attr)
            if callable(fn) and not attr.startswith("_"):
                # check if function has keyword args matching harmful names
                import inspect
                try:
                    sig = inspect.signature(fn)
                    bad = [p for p in sig.parameters if p.lower() in _HARMFUL]
                    if bad:
                        orig = fn
                        def wrapped(*a, __orig=orig, __bad=bad, **kw):
                            for b in __bad:
                                kw.pop(b, None)
                                kw.pop(b.upper(), None)
                            return __orig(*a, **kw)
                        wrapped.__name__ = attr
                        setattr(muscriptor, attr, wrapped)
                except (ValueError, TypeError):
                    pass
    except ImportError:
        pass  # muscriptor not importable from server context - fine
'''
(ROOT / "as_guard.py").write_text(GUARD, encoding="utf-8")
ok.append("as_guard.py created")

# ---------- 2. server.py: install guard ----------
srv = None
for c in [ROOT/"server.py", ROOT/"main.py", ROOT/"app.py"] + list(ROOT.glob("*.py")):
    if c.exists() and "uvicorn" in c.read_text(encoding="utf-8", errors="ignore"):
        srv = c; break
if not srv: raise SystemExit("FAIL: no uvicorn server file")
src = srv.read_text(encoding="utf-8", errors="ignore")
if "==AS_GUARD==" not in src:
    m = re.search(r"(?m)^\s*app\s*=\s*FastAPI\(", src)
    if m:
        nl = src.find("\n", m.start())
        BLOCK = ('\n# ==AS_GUARD v1== strip harmful pp options\n'
                 'try:\n'
                 '    from as_guard import install_live as _as_guard\n'
                 '    _as_guard(app)\n'
                 '    print("[as_guard] harmful pp options neutralized")\n'
                 'except Exception as _e:\n'
                 '    print("[as_guard] failed:", _e)\n')
        src = src[:nl+1] + BLOCK + src[nl+1:]
        srv.write_text(src, encoding="utf-8")
        ok.append("server: guard middleware installed")
    else:
        fail.append("server: app=FastAPI not found")
else:
    ok.append("server: guard already installed")

# ---------- 3. index.html: physically delete harmful checkboxes + simplify script ----------
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")

# 3a. remove v8 simplify script
blocks = re.findall(r"<script\b[^>]*>[\s\S]*?</script>", s)
for b in blocks:
    if "==AS_SIMPLIFY==" in b:
        s = s.replace(b, "", 1); ok.append("index.html: v8 simplify script removed")

# 3b. remove harmful checkbox labels (find wrapping <label> containing pp6/8/9/12/14/15/16)
removed = 0
for pid in ["pp6","pp8","pp9","pp12","pp14","pp15","pp16"]:
    # find <label ...>...id="ppX"...</label>
    pat = re.compile(
        r"<label\b[^>]*>(?:(?!</label>).)*?id=[\"\\']" + re.escape(pid) + r"[\"\\'](?:(?!</label>).)*?</label>",
        re.S | re.I)
    s2 = pat.sub("", s)
    if s2 != s: removed += 1; s = s2
    else:
        # try <div>/<span> wrappers
        pat2 = re.compile(
            r"<(?:div|span|p|li)\b[^>]*>(?:(?!</(?:div|span|p|li)>).)*?id=[\"\\']" + re.escape(pid) + r"[\"\\'](?:(?!</(?:div|span|p|li)>).)*?</(?:div|span|p|li)>",
            re.S | re.I)
        s3 = pat2.sub("", s)
        if s3 != s: removed += 1; s = s3
if removed:
    ok.append("index.html: removed %d harmful checkbox wrappers" % removed)
else:
    fail.append("index.html: no harmful checkboxes found (already clean?)")

HP.write_text(s, encoding="utf-8")

print()
print("==== V9-PURGE RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
