# -*- coding: utf-8 -*-
"""v31: (1) progress fields actually set (v28 regex miss - my fault)
(2) rollback honesty: record sim + pre_rollback_score, show in report
All edits: backup -> compile -> auto-restore."""
from pathlib import Path
import re, py_compile, socket, urllib.request

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []
ROLL = "\u56de\u6eda"
ZSD = "\u771f\u5b9e\u5206"

def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False
info.append("port 8000: " + ("RUNNING (\u6539\u52a8\u9700\u91cd\u542f\u751f\u6548)"
            if probe(8000) else "stopped"))

ep = ROOT / "as_eval.py"
src = ep.read_text(encoding="utf-8")
(ROOT / "as_eval.py.v30bak").write_text(src, encoding="utf-8")
ok.append("backup -> as_eval.py.v30bak")

# A. run_eval start: reset planned_total/current_combo
oldA = 'STATE.update({"running":True,"progress":0,"total":len(combos),'
newA = ('STATE.update({"running":True,"progress":0,"total":len(combos),'
        '"planned_total":len(combos),"current_combo":"",')
if src.count(oldA) == 1:
    src = src.replace(oldA, newA, 1)
    ok.append("A: eval start resets progress fields")
else:
    fail.append("A: anchor count=%d" % src.count(oldA))

# B. loop: per-iteration planned_total/current_combo
patB = re.compile(r'(?m)^([ ]+)(STATE\["current"\] = json\.dumps\(c, ensure_ascii=False\))(\r?\n)')
def repB(m):
    ind, e = m.group(1), m.group(3)
    return (ind + 'STATE["planned_total"] = len(combos)' + e +
            ind + 'STATE["current_combo"] = combo_str(c)' + e +
            ind + m.group(2) + e)
src, nB = patB.subn(repB, src)
(ok if nB == 1 else fail).append("B: loop instrumentation x%d" % nB)

# C. rollback: capture pre-rollback notes + init sim
patC = re.compile(
    r'(?m)^([ ]+)(rolled = False)(\r?\n)'
    r'([ ]+)(if sopts\.get\("self_eval", True\):)(\r?\n)'
    r'([ ]+)(sim = quality_sim\(_notes\(vpm\), base_notes\))(\r?\n)'
    r'([ ]+)(if sim < 0\.6:)(\r?\n)'
    r'([ ]+)(vpm = copy\.deepcopy\(base_pm\); rolled = True)(\r?\n)')
def repC(m):
    i1, i2, i3, i4 = m.group(1), m.group(4), m.group(7), m.group(10)
    e = m.group(3)
    return (i1 + "rolled = False" + e +
            i1 + "sim = None" + e +
            i1 + "pre_notes = None" + e +
            i2 + 'if sopts.get("self_eval", True):' + e +
            i3 + "sim = quality_sim(_notes(vpm), base_notes)" + e +
            i3 + "if sim < 0.6:" + e +
            i4 + "pre_notes = _notes(vpm)" + e +
            i4 + "vpm = copy.deepcopy(base_pm); rolled = True" + e)
src, nC = patC.subn(repC, src)
(ok if nC == 1 else fail).append("C: rollback block instrumented x%d" % nC)

# D. record sim + real pre-rollback score
patD = re.compile(r'(?m)^([ ]+)(r\["combo"\] = c; r\["rolled_back"\] = rolled)(\r?\n)')
def repD(m):
    ind, e = m.group(1), m.group(3)
    return (ind + 'r["combo"] = c; r["rolled_back"] = rolled' + e +
            ind + 'r["sim"] = sim' + e +
            ind + 'if rolled and pre_notes is not None:' + e +
            ind + '    try:' + e +
            ind + '        rpre = (score_ref(pre_notes, ref_notes, sopts)' + e +
            ind + '                if mode == "ref" else score_noref(pre_notes, ctx))' + e +
            ind + '        r["pre_rollback_score"] = rpre.get("score")' + e +
            ind + '    except Exception:' + e +
            ind + '        r["pre_rollback_score"] = None' + e)
src, nD = patD.subn(repD, src)
(ok if nD == 1 else fail).append("D: sim + pre_rollback_score recorded x%d" % nD)

# E. report: rolled rows show real score
TAGLINE = 'tag = " [' + ROLL + ']" if r.get("rolled_back") else ""'
patE = re.compile(r'(?m)^([ ]+)(' + re.escape(TAGLINE) + r')(\r?\n)')
def repE(m):
    ind, e = m.group(1), m.group(3)
    return (ind + TAGLINE + e +
            ind + 'if r.get("pre_rollback_score") is not None:' + e +
            ind + '    tag += " (' + ZSD + '=%s)" % r.get("pre_rollback_score")' + e)
src, nE = patE.subn(repE, src)
(ok if nE == 2 else fail).append("E: report tags patched x%d (want 2)" % nE)

# compile with auto-restore
try:
    ep.write_text(src, encoding="utf-8")
    py_compile.compile(str(ep), doraise=True)
    ok.append("as_eval.py compile OK")
except py_compile.PyCompileError as ex:
    ep.write_text((ROOT / "as_eval.py.v30bak").read_text(encoding="utf-8"),
                  encoding="utf-8")
    fail.append("compile FAILED -> restored | " + str(ex)[:250])

# evidence: patched loop region
m = re.search(r"(?ms)^    for i,c in enumerate\(combos\):.*?^    if mode == \"noref\":", src)
if m:
    print("---- patched run_eval loop ----")
    print(m.group(0)[:1600])
    print("-------------------------------")

print()
print("==== V31 ====")
for l in ok:   print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("=============")
