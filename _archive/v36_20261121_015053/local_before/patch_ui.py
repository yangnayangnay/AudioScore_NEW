# -*- coding: utf-8 -*-
"""UI upgrade: timeout selector + bilingual chips + live progress.
Edits web/index.html, server/main.py, server/jobs.py with anchor checks."""
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []


def rep(fname, old, new, label, must=True):
    p = ROOT / fname
    s = p.read_text(encoding="utf-8")
    if new.strip() and new in s:
        ok.append("%s [SKIP already]" % label)
        return
    n = s.count(old)
    if n == 0:
        fail.append("%s : anchor not found in %s" % (label, fname))
        return
    p.write_text(s.replace(old, new, 1), encoding="utf-8")
    ok.append("%s" % label)


# ============ 1. server/main.py ============
rep("server/main.py",
    "                     bpm: int | None = Form(None)):",
    "                     bpm: int | None = Form(None),\n"
    "                     timeout: int | None = Form(None)):",
    "main.py: add timeout Form param")

rep("server/main.py",
    "        bpm=bpm)",
    "        bpm=bpm, timeout=timeout)",
    "main.py: pass timeout to create_job")

rep("server/main.py",
    '    resp = {k: v for k, v in j.items() if k != "audio_path"}',
    '    resp = {k: v for k, v in j.items() if k != "audio_path"}\n'
    '    if j.get("status") == "running" and j.get("backend") == "muscriptor":\n'
    '        try:\n'
    '            from .engines import get_engine\n'
    '            _st = getattr(get_engine("muscriptor"), "get_status", None)\n'
    '            if callable(_st):\n'
    '                resp["engine_line"] = (_st() or {}).get("line", "")\n'
    '        except Exception:\n'
    '            pass',
    "main.py: expose engine live line in /api/jobs/{id}")

# ============ 2. server/jobs.py ============
rep("server/jobs.py",
    "               instruments: list[str] | None, bpm: int | None) -> str:",
    "               instruments: list[str] | None, bpm: int | None,\n"
    "               timeout: int | None = None) -> str:",
    "jobs.py: create_job accepts timeout")

rep("server/jobs.py",
    '        "instruments": instruments, "bpm": bpm,',
    '        "instruments": instruments, "bpm": bpm, "timeout": timeout,',
    "jobs.py: store timeout in job dict")

rep("server/jobs.py",
    '    eng.transcribe(job["audio_path"], raw_mid,\n'
    '                   instruments=job["instruments"], bpm=job["bpm"])',
    '    import inspect as _insp\n'
    '    _kw = dict(instruments=job["instruments"], bpm=job["bpm"])\n'
    '    if "timeout" in _insp.signature(eng.transcribe).parameters:\n'
    '        _kw["timeout"] = job.get("timeout")\n'
    '    eng.transcribe(job["audio_path"], raw_mid, **_kw)',
    "jobs.py: forward timeout to engine (old-engine safe)")

# ============ 3. web/index.html ============
ZH_MAP = (
    "const ZH = {piano:'\u94a2\u7434', bass:'\u8d1d\u65af', drums:'\u67b6\u5b50\u9f13', "
    "guitar:'\u5409\u4ed6', electric_guitar:'\u7535\u5409\u4ed6', strings:'\u5f26\u4e50', "
    "violin:'\u5c0f\u63d0\u7434', cello:'\u5927\u63d0\u7434', brass:'\u94dc\u7ba1', "
    "trumpet:'\u5c0f\u53f7', saxophone:'\u8428\u514b\u65af', flute:'\u957f\u7b1b', "
    "organ:'\u7ba1\u98ce\u7434', synth_lead:'\u5408\u6210\u4e3b\u97f3', "
    "synth_pad:'\u5408\u6210\u94fa\u5e95', vocals:'\u4eba\u58f0'};\n"
)

rep("web/index.html",
    "const $ = id => document.getElementById(id);",
    "const $ = id => document.getElementById(id);\n" + ZH_MAP,
    "html: instrument label map ZH")

rep("web/index.html",
    "c.className = 'chip'; c.textContent = name;",
    "c.className = 'chip'; c.dataset.value = name;\n"
    "c.textContent = (ZH[name] ? ZH[name] + ' ' : '') + name;",
    "html: chips show Chinese(English), value kept clean")

rep("web/index.html",
    ".map(c => c.textContent).join(','));",
    ".map(c => c.dataset.value || c.textContent).join(','));",
    "html: submit value from dataset (bilingual-proof)")

rep("web/index.html",
    "const bpm = $('bpm').value.trim();\nif (bpm) fd.append('bpm', bpm);",
    "const bpm = $('bpm').value.trim();\nif (bpm) fd.append('bpm', bpm);\n"
    "const tmo = $('tmo').value;\n"
    "if (tmo !== '') fd.append('timeout', tmo);",
    "html: send timeout with form")

rep("web/index.html",
    '<div class="opt"><input type="checkbox" id="pp1" checked>',
    '<label>\u65f6\u95f4\u4e0a\u9650\uff08\u8d85\u65f6\u81ea\u52a8\u7ec8\u6b62\u8be5\u4efb\u52a1\uff09</label>\n'
    '<select id="tmo">\n'
    '  <option value="">\u9ed8\u8ba4\uff08config.yaml\uff09</option>\n'
    '  <option value="600">10 \u5206\u949f</option>\n'
    '  <option value="1800">30 \u5206\u949f</option>\n'
    '  <option value="3600">1 \u5c0f\u65f6</option>\n'
    '  <option value="7200">2 \u5c0f\u65f6</option>\n'
    '  <option value="0">\u65e0\u9650\u5236</option>\n'
    '</select>\n'
    '<div class="opt"><input type="checkbox" id="pp1" checked>',
    "html: timeout selector UI")

rep("web/index.html",
    "$('pbar').style.width =\n"
    "({ queued: 5, running: 40, done: 100, error: 100 })[j.status] + '%';\n"
    "$('smeta').textContent = '\u5df2\u7528\u65f6 ' + j.elapsed + 's';",
    "let pct = ({ queued: 5, done: 100, error: 100 })[j.status];\n"
    "if (j.status === 'running') {\n"
    "  const exp = j.backend === 'muscriptor' ? 480 : 30;\n"
    "  pct = Math.min(88, 5 + 83 * Math.min(1, j.elapsed / exp));\n"
    "}\n"
    "$('pbar').style.width = pct + '%';\n"
    "let meta = '\u5df2\u7528\u65f6 ' + j.elapsed + 's';\n"
    "if (j.engine_line !== undefined) {\n"
    "  meta += ' \uff5c \u5f15\u64ce: ' + (j.engine_line || '\u2026').slice(0, 80);\n"
    "}\n"
    "$('smeta').textContent = meta;",
    "html: progress bar creeps with time + live engine line")

print("==== PATCH RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("=======================")

import py_compile
for f in ("server/main.py", "server/jobs.py"):
    try:
        py_compile.compile(str(ROOT / f), doraise=True)
        print("  syntax OK :", f)
    except Exception as e:
        print("  syntax FAIL:", f, e)
