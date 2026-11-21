# -*- coding: utf-8 -*-
"""v23-fastboot: restore original startup speed
- ROOT CAUSE of slowdown: v16 put librosa/scipy/pretty_midi at as_eval top-level,
  server.py imports as_eval at boot -> paid 10-30s every start. Now LAZY.
- also fixes v22 crash (%~dp0 vs %-format) and re-applies bat banner (ASCII, no
  encoding risk) + auto-open helper, using the bat's own interpreter token.
- every step prints evidence; nothing silent."""
from pathlib import Path
import re, py_compile, socket, subprocess, sys

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []

# ---------- 0. live probe ----------
def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False
info.append("PROBE port 8000: " + ("RESPONDING (service is up right now)"
            if probe(8000) else "no response (service not running now)"))

# ---------- 1. as_eval.py: lazy heavy imports ----------
ep = ROOT / "as_eval.py"
s = ep.read_text(encoding="utf-8")
OLD_IMP = (
"try:\n"
"    import pretty_midi; HAS_PM = True\n"
"except Exception: HAS_PM = False\n"
"try:\n"
"    import librosa; HAS_LR = True\n"
"except Exception: HAS_LR = False\n"
"try:\n"
"    from scipy.optimize import linear_sum_assignment; HAS_SCIPY = True\n"
"except Exception: HAS_SCIPY = False")
NEW_IMP = (
"# v23: heavy libs are LAZY (startup speed) - loaded on first use\n"
"_PM = None\n"
"def _pm():\n"
"    global _PM\n"
"    if _PM is None:\n"
"        import pretty_midi as _m\n"
"        _PM = _m\n"
"    return _PM\n"
"_LR = None\n"
"def _lr():\n"
"    global _LR\n"
"    if _LR is None:\n"
"        try:\n"
"            import librosa as _m\n"
"            _LR = _m\n"
"        except Exception:\n"
"            _LR = False\n"
"    return _LR or None\n"
"_LSA = None\n"
"def _lsa():\n"
"    global _LSA\n"
"    if _LSA is None:\n"
"        try:\n"
"            from scipy.optimize import linear_sum_assignment as _f\n"
"            _LSA = _f\n"
"        except Exception:\n"
"            _LSA = False\n"
"    return _LSA or None")
if OLD_IMP in s:
    s = s.replace(OLD_IMP, NEW_IMP, 1)
    ok.append("as_eval: top-level heavy imports -> lazy getters")
elif "_lsa" in s and "_lr" in s:
    ok.append("as_eval: lazy getters already present")
else:
    fail.append("as_eval: import block anchor NOT found - paste its first 20 lines")

REPS = [
 ("pretty_midi.PrettyMIDI(io.BytesIO(b))", "_pm().PrettyMIDI(io.BytesIO(b))"),
 ("if not HAS_LR: return None", "if _lr() is None: return None"),
 ("librosa.load(", "_lr().load("),
 ("librosa.beat.beat_track(", "_lr().beat.beat_track("),
 ("librosa.frames_to_time(", "_lr().frames_to_time("),
 ("librosa.feature.rms(", "_lr().feature.rms("),
 ("librosa.times_like(", "_lr().times_like("),
 ("if HAS_SCIPY and n <= MAX_HUNG and m <= MAX_HUNG:",
  "if n <= MAX_HUNG and m <= MAX_HUNG and _lsa() is not None:"),
 ("linear_sum_assignment(Cm)", "_lsa()(Cm)"),
]
for old, new in REPS:
    n = s.count(old)
    if n:
        s = s.replace(old, new)
        ok.append("as_eval: replaced %dx  %s" % (n, old[:40]))
left = [(i+1, l.strip()[:70]) for i, l in enumerate(s.splitlines())
        if re.search(r"\b(HAS_PM|HAS_LR|HAS_SCIPY)\b", l)
        or re.search(r"librosa\.|pretty_midi\.", l)]
if left:
    fail.append("as_eval: leftover direct refs: " + str(left[:4]))
else:
    ok.append("as_eval: no leftover direct heavy-lib refs")
ep.write_text(s, encoding="utf-8")

# ---------- 2. compile everything ----------
for name in ("as_eval.py", "server.py", "run.py", "as_autoopen.py"):
    p = ROOT / name
    if not p.exists():
        fail.append("%s MISSING" % name); continue
    try:
        py_compile.compile(str(p), doraise=True)
        ok.append("compile OK: %s" % name)
    except py_compile.PyCompileError as e:
        fail.append("compile FAIL: %s | %s" % (name, str(e)[:200]))

# ---------- 3. bat: helper + ASCII banner (concatenation, no %-format) ----------
cands = [ROOT / n for n in ("start.bat", "run.bat", "start_server.bat")]
BAT = next((c for c in cands if c.exists()), None)
if BAT is None:
    fail.append("no launcher bat found")
else:
    raw = BAT.read_bytes()
    enc = None
    for e in ("utf-8", "gbk"):
        try:
            text = raw.decode(e); enc = e; break
        except UnicodeDecodeError:
            continue
    if enc is None:
        text = raw.decode("latin-1"); enc = "latin-1"
    ok.append("bat=%s encoding=%s (preserved)" % (BAT.name, enc))
    lines = [l for l in text.splitlines()
             if ("as_autoopen" not in l and "[BOOT" not in l
                 and "Model loading takes" not in l)]
    li = None
    for i, l in enumerate(lines):
        ll = l.strip().lower()
        if (not ll or ll.startswith(("rem", "::", "echo", "set", "@echo"))):
            continue
        if re.search(r"python|uvicorn", ll):
            li = i; break
    if li is None:
        fail.append("bat: launch line not found")
    else:
        toks = lines[li].strip().split()
        py = toks[0] if toks else "python"
        ok.append("bat launch line: " + lines[li].strip() + "  (py token=" + py + ")")
        ins = ['start "as-autoopen" /min ' + py + ' "%~dp0as_autoopen.py" 8000',
               "echo ============================================",
               "echo  [!] Model loading takes 30-90 seconds.",
               "echo  NO new output during load is NORMAL - do not close.",
               "echo  Browser opens automatically when server is ready.",
               "echo  Manual URL: http://localhost:8000",
               "echo ============================================"]
        lines[li:li] = ins
        BAT.write_text("\r\n".join(lines) + "\r\n", encoding=enc)
        ok.append("bat: helper + banner inserted BEFORE launch")
        print()
        print("---- " + BAT.name + " final ----")
        print("\n".join(lines))
        print("-----------------------------")

# ---------- 4. measure as_eval import cost (the proof) ----------
try:
    r = subprocess.run(
        [sys.executable, "-c",
         "import time,sys; sys.path.insert(0, r'" + str(ROOT) + "');"
         "t0=time.time(); import as_eval;"
         "print('AS_EVAL_IMPORT_SEC=%.2f' % (time.time()-t0))"],
        capture_output=True, text=True, timeout=120)
    for ln in r.stdout.splitlines():
        if "AS_EVAL_IMPORT_SEC" in ln:
            info.append("as_eval boot cost now = " + ln.split("=")[1] +
                        "s  (was 10-30s with librosa/scipy at top level)")
except Exception as e:
    fail.append("import timing failed: %s" % str(e)[:120])

print()
print("==== V23-FASTBOOT ====")
for l in ok:   print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("======================")
