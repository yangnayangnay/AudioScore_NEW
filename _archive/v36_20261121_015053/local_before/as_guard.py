# -*- coding: utf-8 -*-
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
