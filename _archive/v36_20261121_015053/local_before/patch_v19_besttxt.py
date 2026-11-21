# -*- coding: utf-8 -*-
"""v19-besttxt: on eval finish -> auto-save best combo report
- best_combo.txt   (overwrite each run, utf-8-sig for notepad)
- eval_history.txt (append one line per run)
- /api/eval/best_txt endpoint + modal button to view it"""
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ================= 1. as_eval.py: report writer + endpoint + call =================
ep = ROOT / "as_eval.py"
s = ep.read_text(encoding="utf-8")

if "write_best_report" in s:
    ok.append("as_eval.py: report writer already present")
else:
    ANCHOR = "def install_live(app):"
    if ANCHOR not in s:
        fail.append("as_eval.py: install_live anchor missing")
    else:
        BLOCK = '''# ================= v19: best-combo txt report =================
from pathlib import Path as _P
ROOT_DIR = _P(__file__).resolve().parent

def combo_str(c):
    parts = []
    for k, v in (c or {}).items():
        if not v: continue
        meta = REGISTRY.get(k)
        parts.append(meta["label"] if meta else k)
    return "+".join(parts) if parts else "(\u65e0)"

def write_best_report(results, mode):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    valid = [r for r in (results or [])
             if isinstance(r, dict) and r.get("score") is not None
             and r.get("score") >= 0 and not r.get("error")]
    out = []
    out.append("=" * 46)
    out.append(" AudioScore \u6700\u4f18\u5904\u7406\u7ec4\u5408\u62a5\u544a")
    out.append(" \u65f6\u95f4: " + ts)
    out.append(" \u8bc4\u5206\u6a21\u5f0f: " + (
        "noref \u65e0\u53c2\u8003\u81ea\u8bc4 (NCT>SDR>NCS>TCS>BAS \u5b57\u5178\u5e8f)"
        if mode == "noref" else
        "ref \u6709\u53c2\u8003 (MidiComparator \u4e94\u7ef4)"))
    out.append("=" * 46)
    if not valid:
        out.append("")
        out.append(" [!] \u672c\u6b21\u8bc4\u6d4b\u6ca1\u6709\u6709\u6548\u7ed3\u679c")
        for r in (results or [])[:5]:
            if r.get("error"):
                out.append("   ERR %s : %s" % (combo_str(r.get("combo")), r["error"]))
    else:
        best = valid[0]
        c = best.get("combo", {})
        out.append("")
        out.append("[\u6700\u4f18\u7ec4\u5408\u5f97\u5206]")
        out.append("   \u7efc\u5408 = %s" % best.get("score"))
        if mode == "noref":
            out.append("   NCT \u5bc6\u5ea6\u5408\u7406   = %s" % best.get("nct"))
            out.append("   SDR \u65f6\u503c\u5408\u89c4   = %s" % best.get("sdr"))
            out.append("   NCS \u8fde\u8d2f\u5ea6     = %s" % best.get("ncs"))
            out.append("   TCS \u53d8\u901f\u5408\u7406   = %s" % best.get("tcs"))
            out.append("   BAS \u8282\u62cd\u8d34\u5408   = %s" % best.get("bas"))
            out.append("   \u97f3\u7b26\u6570       = %s" % best.get("n_notes"))
        else:
            out.append("   \u5b58\u5728\u6027 max(F1,\u91cd\u5408\u5ea6) = %s" % best.get("existence"))
            out.append("   onset \u4f4d\u7f6e          = %s" % best.get("onset_acc"))
            out.append("   IOI \u8282\u594f\u4fdd\u6301      = %s" % best.get("ioi_sim"))
            out.append("   \u65f6\u503c\u51c6\u786e          = %s" % best.get("dur_acc"))
            out.append("   \u97f3\u9ad8\u7cbe\u786e          = %s" % best.get("pitch_exact"))
            out.append("   P/R/F1 = %s / %s / %s" % (
                best.get("precision"), best.get("recall"), best.get("f1")))
            out.append("   \u5e73\u79fb\u0394t=%ss  \u79fb\u8c03=%s  DTW\u6821\u6b63=%sms  \u91cd\u590d\u97f3=%s" % (
                best.get("best_dt"), best.get("transpose"),
                best.get("dtw_ms"), best.get("dup")))
        if best.get("rolled_back"):
            out.append("   (\u6ce8: \u8be5\u7ec4\u5408\u89e6\u53d1\u4e86\u81ea\u8bc4\u56de\u6eda, \u5b9e\u9645\u4f7f\u7528\u4e86\u57fa\u7840MIDI)")
        out.append("")
        out.append("[\u9700\u52fe\u9009\u7684\u5904\u7406\u5f00\u5173]")
        for k, meta in REGISTRY.items():
            v = bool(c.get(k, meta["default"]))
            out.append("   %s %s" % ("\u2713" if v else "\u2717", meta["label"]))
        out.append("")
        out.append("[\u524d\u7aef\u6309\u94ae\u6620\u5c04]")
        for fb, keys in (
                ("\u57fa\u7840\u5904\u7406 (pp1+pp2)", ["smartfrag"]),
                ("\u529b\u5ea6\u91cd\u5efa (pp3)", ["pp3_vel"]),
                ("\u91cf\u5316/\u8282\u594f/\u53d8\u901f (pp7)",
                 ["tempo_hist", "tempo_adapt", "quant_global",
                  "quant_local", "rhythm_quant", "rhythm_ext", "tempo_write"])):
            on = any(c.get(k) for k in keys)
            out.append("   %s : %s" % (fb, "\u9700\u5f00\u542f" if on else "\u4e0d\u9700\u8981"))
        out.append("")
        out.append("[Top 5]")
        for i, r in enumerate(valid[:5]):
            tag = " [\u56de\u6eda]" if r.get("rolled_back") else ""
            out.append("   %d. \u7efc\u5408=%s | %s%s" % (
                i + 1, r.get("score"), combo_str(r.get("combo")), tag))
        out.append("")
        out.append("[\u5168\u90e8\u7ed3\u679c]")
        for i, r in enumerate(results or []):
            if r.get("error"):
                out.append("   %2d. ERR  %s : %s" % (
                    i + 1, combo_str(r.get("combo")), str(r["error"])[:100]))
            else:
                tag = " [\u56de\u6eda]" if r.get("rolled_back") else ""
                out.append("   %2d. %s | %s%s" % (
                    i + 1, r.get("score"), combo_str(r.get("combo")), tag))
    out.append("")
    out.append("(\u5386\u53f2\u5df2\u8ffd\u52a0: eval_history.txt)")
    p = ROOT_DIR / "best_combo.txt"
    p.write_text("\n".join(out) + "\n", encoding="utf-8-sig")
    try:
        with open(ROOT_DIR / "eval_history.txt", "a",
                  encoding="utf-8-sig") as f:
            if valid:
                f.write("%s | %s | best=%s | %s\n" % (
                    ts, mode, valid[0].get("score"),
                    combo_str(valid[0].get("combo"))))
            else:
                f.write("%s | %s | no valid result\n" % (ts, mode))
    except Exception:
        pass
    return str(p)

'''
        s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
        ok.append("as_eval.py: write_best_report + combo_str inserted")

    TAIL_OLD = ('    STATE["running"] = False; STATE["done"] = True\n'
                '    STATE["finished"] = time.time()')
    TAIL_NEW = ('    STATE["running"] = False; STATE["done"] = True\n'
                '    try:\n'
                '        STATE["best_txt"] = write_best_report(STATE["results"], mode)\n'
                '    except Exception as _e:\n'
                '        STATE["best_txt_error"] = str(_e)\n'
                '    STATE["finished"] = time.time()')
    if TAIL_OLD in s:
        s = s.replace(TAIL_OLD, TAIL_NEW, 1)
        ok.append("as_eval.py: run_eval tail hooks report saving")
    else:
        fail.append("as_eval.py: run_eval tail anchor NOT found (check manually)")

    ST_OLD = ('    @app.get("/api/eval/status")\n'
              '    def api_status():\n'
              '        return JSONResponse(STATE)')
    ST_NEW = ST_OLD + ('\n\n'
              '    @app.get("/api/eval/best_txt")\n'
              '    def api_best_txt():\n'
              '        from fastapi.responses import PlainTextResponse\n'
              '        p = ROOT_DIR / "best_combo.txt"\n'
              '        if not p.exists():\n'
              '            return PlainTextResponse('
              '"\\u8fd8\\u6ca1\\u6709\\u62a5\\u544a\\uff0c\\u5148\\u8dd1\\u4e00\\u6b21\\u8bc4\\u6d4b",\n'
              '                                    status_code=404)\n'
              '        return PlainTextResponse(p.read_text(encoding="utf-8-sig"))')
    if ST_OLD in s:
        s = s.replace(ST_OLD, ST_NEW, 1)
        ok.append("as_eval.py: GET /api/eval/best_txt endpoint added")
    else:
        fail.append("as_eval.py: api_status anchor NOT found (check manually)")

    ep.write_text(s, encoding="utf-8")

# ================= 2. index.html: report button =================
HP = ROOT / "web" / "index.html"
h = HP.read_text(encoding="utf-8")
if "asEvReport" in h:
    ok.append("index.html: report button already present")
else:
    A1 = "'<div id=\"asEvTable\" style=\"margin-top:8px\"></div>'+"
    N1 = (A1 + "\n"
          " '<div style=\"margin-top:6px\"><button id=\"asEvReport\" "
          "style=\"display:none;cursor:pointer;padding:4px 10px;font-size:12px\">"
          "\\ud83d\\udcc4 \\u6253\\u5f00\\u6700\\u4f18\\u914d\\u7f6e\\u62a5\\u544a "
          "best_combo.txt</button></div>'+")
    if A1 in h:
        h = h.replace(A1, N1, 1)
        ok.append("index.html: report button element added")
    else:
        fail.append("index.html: asEvTable anchor NOT found")

    A2 = "    renderResults(j.results||[]);"
    N2 = A2 + "\n    el('asEvReport').style.display='inline-block';"
    if A2 in h:
        h = h.replace(A2, N2, 1)
        ok.append("index.html: button shown after eval completes")
    else:
        fail.append("index.html: renderResults anchor NOT found")

    A3 = "el('asEvClose').onclick=function(){m.style.display='none';};"
    N3 = A3 + ("\nel('asEvReport').onclick=function(){"
               "window.open('/api/eval/best_txt','_blank');};")
    if A3 in h:
        h = h.replace(A3, N3, 1)
        ok.append("index.html: button wired to /api/eval/best_txt")
    else:
        fail.append("index.html: asEvClose anchor NOT found")
    HP.write_text(h, encoding="utf-8")

print()
print("==== V19-BESTTXT RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
