# -*- coding: utf-8 -*-
"""v25-measure: numbers first, no more guessing
(1) time EVERY heavy module import in fresh python -> where the seconds go
(2) check as_eval is truly lazy; self-heal if v23 never applied
(3) dump engine-init code from run.py/server.py -> map for the real fix"""
from pathlib import Path
import re, py_compile, subprocess, sys, socket

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, rows = [], [], []

def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False

rows.append(("port 8000 now", "RUNNING" if probe(8000) else "stopped"))

# ---------- 1. as_eval laziness (self-heal if v23 missing) ----------
ep = ROOT / "as_eval.py"
s = ep.read_text(encoding="utf-8")
if "_lr()" in s:
    ok.append("as_eval: lazy imports confirmed (v23 applied)")
else:
    OLD_IMP = ("try:\n    import pretty_midi; HAS_PM = True\n"
               "except Exception: HAS_PM = False\n"
               "try:\n    import librosa; HAS_LR = True\n"
               "except Exception: HAS_LR = False\n"
               "try:\n"
               "    from scipy.optimize import linear_sum_assignment; HAS_SCIPY = True\n"
               "except Exception: HAS_SCIPY = False")
    NEW_IMP = ("# lazy heavy imports (startup speed)\n"
               "_PM = None\n"
               "def _pm():\n    global _PM\n"
               "    if _PM is None:\n        import pretty_midi as _m\n        _PM = _m\n"
               "    return _PM\n"
               "_LR = None\n"
               "def _lr():\n    global _LR\n"
               "    if _LR is None:\n"
               "        try:\n            import librosa as _m\n            _LR = _m\n"
               "        except Exception:\n            _LR = False\n"
               "    return _LR or None\n"
               "_LSA = None\n"
               "def _lsa():\n    global _LSA\n"
               "    if _LSA is None:\n"
               "        try:\n"
               "            from scipy.optimize import linear_sum_assignment as _f\n"
               "            _LSA = _f\n"
               "        except Exception:\n            _LSA = False\n"
               "    return _LSA or None")
    if OLD_IMP in s:
        s = s.replace(OLD_IMP, NEW_IMP, 1)
        REPS = [("pretty_midi.PrettyMIDI(io.BytesIO(b))",
                 "_pm().PrettyMIDI(io.BytesIO(b))"),
                ("if not HAS_LR: return None", "if _lr() is None: return None"),
                ("librosa.load(", "_lr().load("),
                ("librosa.beat.beat_track(", "_lr().beat.beat_track("),
                ("librosa.frames_to_time(", "_lr().frames_to_time("),
                ("librosa.feature.rms(", "_lr().feature.rms("),
                ("librosa.times_like(", "_lr().times_like("),
                ("if HAS_SCIPY and n <= MAX_HUNG",
                 "if n <= MAX_HUNG and _lsa() is not None"),
                ("linear_sum_assignment(Cm)", "_lsa()(Cm)")]
        for old, new in REPS:
            if old in s: s = s.replace(old, new)
        ep.write_text(s, encoding="utf-8")
        ok.append("as_eval: WAS STILL EAGER (v23 never applied) -> lazy now")
    else:
        fail.append("as_eval: unexpected import block, paste first 15 lines")
try:
    py_compile.compile(str(ep), doraise=True)
    ok.append("as_eval compile OK")
except py_compile.PyCompileError as e:
    fail.append("as_eval compile FAIL: " + str(e)[:200])

# ---------- 2. dump entry files: imports + engine init ----------
for name in ("run.py", "server.py"):
    p = ROOT / name
    if not p.exists():
        fail.append(name + " missing"); continue
    t = p.read_text(encoding="utf-8", errors="ignore")
    lines = t.splitlines()
    print()
    print("==== " + name + " : top-level imports ====")
    for i, l in enumerate(lines):
        if re.match(r"^\s*(import|from)\s+\w", l) and not l.startswith(" " * 8):
            print("  L" + str(i + 1) + ": " + l.strip())
    print("==== " + name + " : engine/model/init lines ====")
    pat = re.compile(r"engine|Engine|basic_pitch|BasicPitch|mt3|MT3|crepe|spice"
                     r"|tensorflow|load_model|init|Model|on_event|startup",
                     re.I)
    shown = set()
    for i, l in enumerate(lines):
        if pat.search(l):
            for k in range(max(0, i - 1), min(len(lines), i + 2)):
                if k not in shown:
                    shown.add(k)
                    print("  L" + str(k + 1) + ": " + lines[k])
    ok.append(name + ": dumped (see above)")

# ---------- 3. per-module import timing ----------
MODS = ["numpy", "scipy", "mido", "pretty_midi", "librosa", "numba",
        "tensorflow", "basic_pitch", "jax"]
print()
print("==== import timing (fresh python each) ====")
timed = []
for m in MODS:
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             "import time;t0=time.time();import " + m +
             ";print('%.2f'%(time.time()-t0))"],
            capture_output=True, text=True, timeout=300)
        sec = r.stdout.strip()
        if not sec:
            sec = "N/A(not installed)"
        else:
            try: timed.append((float(sec), m))
            except ValueError: pass
    except subprocess.TimeoutExpired:
        sec = ">300s !!!"
    print("  " + m.ljust(14) + str(sec))
try:
    r = subprocess.run(
        [sys.executable, "-c",
         "import time,sys;sys.path.insert(0,r'" + str(ROOT) +
         "');t0=time.time();import as_eval;print('%.2f'%(time.time()-t0))"],
        capture_output=True, text=True, timeout=120)
    sec = r.stdout.strip() or r.stderr.strip()[-120:]
    print("  " + "as_eval".ljust(14) + str(sec))
    try: timed.append((float(sec), "as_eval"))
    except ValueError: pass
except subprocess.TimeoutExpired:
    print("  as_eval        >120s !!!")
timed.sort(reverse=True)
print()
print("VERDICT (biggest first): " +
      ", ".join(m + "=" + str(v) + "s" for v, m in timed[:4]))
rows.append(("verdict", "biggest=" +
             (timed[0][1] if timed else "?")))

print()
print("==== V25-MEASURE ====")
for k, v in rows: print("  >>>", k, ":", v)
for l in ok:   print("  PASS:", l)
for l in fail: print("  FAIL:", l)
print("=====================")
