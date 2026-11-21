# -*- coding: utf-8 -*-
"""v11-eval: A/B test panel - upload base+ref MIDI, server derives
8 postproc variants, scores each vs ref via mir_eval, returns ranked table."""
from pathlib import Path
import re, shutil

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- 1. as_eval.py ----------
EVAL = r'''# -*- coding: utf-8 -*-
"""as_eval: A/B evaluation of postproc combos against a reference MIDI.
POST /api/eval/run (base, ref, combos?) -> starts bg job
GET  /api/eval/status  -> progress + results
POST /api/eval/score   -> score single pair (base, ref)"""
import io, json, time, copy, threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
STATE = {"running":False,"progress":0,"total":0,"current":"",
         "results":[],"done":False,"error":"","started":0,"finished":0}

def _load_pm(b):
    import pretty_midi
    return pretty_midi.PrettyMIDI(io.BytesIO(b))

def _pm_bytes(pm):
    buf=io.BytesIO(); pm.write(buf); return buf.getvalue()

def _notes(pm):
    out=[]
    for inst in pm.instruments:
        for n in inst.notes:
            out.append((n.start,n.end,n.pitch))
    out.sort(); return out

def score_pair(cand_bytes, ref_bytes, onset_tol=0.05, pitch_tol=50.0):
    try:
        import numpy as np, mir_eval
        c = _notes(_load_pm(cand_bytes))
        r = _notes(_load_pm(ref_bytes))
        if not r: return {"error":"reference MIDI has no notes"}
        if not c:
            return {"onset_f1":0.0,"note_f1":0.0,"onset_mae":0.0,
                    "score":0.0,"n_cand":0,"n_ref":len(r)}
        ref_i = np.array([[x[0],x[1]] for x in r])
        ref_p = np.array([x[2] for x in r], dtype=int)
        est_i = np.array([[x[0],x[1]] for x in c])
        est_p = np.array([x[2] for x in c], dtype=int)
        m = mir_eval.transcription.evaluate(
            ref_i, ref_p, est_i, est_p,
            onset_tolerance=onset_tol, pitch_tolerance=pitch_tol)
        onset_f1 = float(m.get("Onset_F-measure",0.0))
        note_f1  = float(m.get("Onset-Offset_F-measure",
                                m.get("F-measure",onset_f1)))
        errs=[]
        for (st,_,_) in c:
            errs.append(float(np.abs(ref_i[:,0]-st).min()))
        onset_mae = float(np.mean(errs)) if errs else 0.0
        score = 0.6*onset_f1 + 0.4*note_f1 - 0.05*min(1.0, onset_mae/0.2)
        return {"onset_f1":round(onset_f1,4),"note_f1":round(note_f1,4),
                "onset_mae":round(onset_mae,4),"score":round(score,4),
                "n_cand":len(c),"n_ref":len(r)}
    except Exception as e:
        return {"error":str(e)}

def apply_combo(pm, combo):
    pm = copy.deepcopy(pm)
    if combo.get("smartfrag",1):
        try:
            from as_postproc import pp17_cross_segment_merge, pp18_same_pitch_stitch
            pp17_cross_segment_merge(pm, overlap_s=0.02, gap_s=0.05)
            pp18_same_pitch_stitch(pm, gap_s=0.08)
        except Exception: pass
    if not combo.get("pp3",1):
        for inst in pm.instruments:
            for n in inst.notes:
                n.velocity = 80
    if combo.get("pp7",0):
        try:
            bpm = pm.estimate_tempos()[0]
        except Exception:
            bpm = 120.0
        beat = 60.0/bpm/4
        for inst in pm.instruments:
            for n in inst.notes:
                n.start = round(n.start/beat)*beat
                n.end   = max(n.start+beat, round(n.end/beat)*beat)
    return pm

def gen_combos():
    out=[]
    for sf in [0,1]:
        for v in [0,1]:
            for q in [0,1]:
                out.append({"smartfrag":sf,"pp3":v,"pp7":q})
    return out

def run_eval(base_bytes, ref_bytes, combos):
    STATE.update({"running":True,"progress":0,"total":len(combos),
                  "results":[],"done":False,"error":"",
                  "started":time.time(),"finished":0})
    try: base_pm = _load_pm(base_bytes)
    except Exception as e:
        STATE["error"]=str(e); STATE["running"]=False
        STATE["done"]=True; return
    for i,c in enumerate(combos):
        STATE["current"]=json.dumps(c,ensure_ascii=False)
        try:
            vpm = apply_combo(base_pm, c)
            s = score_pair(_pm_bytes(vpm), ref_bytes)
            s["combo"]=c
            STATE["results"].append(s)
        except Exception as e:
            STATE["results"].append({"combo":c,"error":str(e),"score":-1})
        STATE["progress"]=i+1
    STATE["results"].sort(key=lambda x: -(x.get("score") if x.get("score") is not None else -1))
    STATE["running"]=False; STATE["done"]=True
    STATE["finished"]=time.time()

def install_live(app):
    from fastapi import UploadFile, File, Form
    from fastapi.responses import JSONResponse

    @app.post("/api/eval/score")
    async def api_score(candidate: UploadFile = File(...),
                        ref: UploadFile = File(...)):
        try:
            return JSONResponse(score_pair(await candidate.read(),
                                            await ref.read()))
        except Exception as e:
            return JSONResponse({"error":str(e)})

    @app.post("/api/eval/run")
    async def api_run(base: UploadFile = File(...),
                      ref: UploadFile = File(...),
                      combos: str = Form("")):
        if STATE.get("running"):
            return JSONResponse({"error":"eval already running"})
        cb = await base.read(); rb = await ref.read()
        try:
            cl = json.loads(combos) if combos else gen_combos()
        except Exception:
            cl = gen_combos()
        if not cl: return JSONResponse({"error":"empty combos"})
        threading.Thread(target=run_eval,args=(cb,rb,cl),daemon=True).start()
        return JSONResponse({"ok":True,"total":len(cl)})

    @app.get("/api/eval/status")
    def api_status():
        return JSONResponse(STATE)
'''
(ROOT / "as_eval.py").write_text(EVAL, encoding="utf-8")
ok.append("as_eval.py created")

# ---------- 2. server.py route ----------
srv = None
for c in [ROOT/"server.py", ROOT/"main.py", ROOT/"app.py"] + list(ROOT.glob("*.py")):
    if c.exists() and "uvicorn" in c.read_text(encoding="utf-8", errors="ignore"):
        srv = c; break
if not srv: raise SystemExit("FAIL: no uvicorn server file")
src = srv.read_text(encoding="utf-8", errors="ignore")
if "==AS_EVAL_ROUTE==" not in src:
    m = re.search(r"(?m)^\s*app\s*=\s*FastAPI\(", src)
    if m:
        nl = src.find("\n", m.start())
        BLOCK = ('\n# ==AS_EVAL_ROUTE v1==\ntry:\n'
                 '    from as_eval import install_live as _as_eval_i\n'
                 '    _as_eval_i(app)\n'
                 '    print("[as_eval] /api/eval/* ready")\n'
                 'except Exception as _e:\n    print("[as_eval] route failed:", _e)\n')
        src = src[:nl+1] + BLOCK + src[nl+1:]
        srv.write_text(src, encoding="utf-8")
        ok.append("server: /api/eval/* route installed")
    else: fail.append("server: app=FastAPI not found")
else: ok.append("server: eval route already present")

# ---------- 3. setup.bat mir_eval ----------
sb = ROOT / "setup.bat"
DEP = ('REM ==AS_EVAL_DEPS v1==\r\n'
       '"%~dp0.venv\\Scripts\\python.exe" -m pip install mir_eval\r\n')
if sb.exists():
    t = sb.read_text(encoding="utf-8", errors="ignore")
    if "==AS_EVAL_DEPS==" not in t:
        lines = t.splitlines(keepends=True)
        pos = len(lines)
        for i in range(len(lines)-1,-1,-1):
            if "pause" in lines[i].lower(): pos = i; break
        lines.insert(pos, DEP)
        sb.write_text("".join(lines), encoding="utf-8")
        ok.append("setup.bat: mir_eval dep added")
    else: ok.append("setup.bat: already patched")
else: fail.append("setup.bat not found")

# ---------- 4. index.html: eval button + modal ----------
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")

A_OLD = """'<span id="asQSet" style="cursor:pointer;font-size:12px;color:#9fb0c0">\\u2699 \\u8bbe\\u7f6e</span>'+"""
A_NEW = """'<span id="asQSet" style="cursor:pointer;font-size:12px;color:#9fb0c0">\\u2699 \\u8bbe\\u7f6e</span>'+
 '<span id="asQEval" style="cursor:pointer;font-size:12px;color:#9fb0c0">\\ud83e\\uddea \\u6d4b\\u8bd5</span>'+"""
if A_OLD in s: s = s.replace(A_OLD, A_NEW, 1); ok.append("A: eval button added")
elif A_NEW in s: ok.append("A: SKIP")
else: fail.append("A: NOT FOUND")

MARK = "/* ==AS_EVAL_MODAL== */"
if MARK not in s:
    MODAL = r"""<script>
/* ==AS_EVAL_MODAL== v1 */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
function ls(k,v){try{
  if(v===undefined)return localStorage.getItem(k);
  if(v===null){localStorage.removeItem(k);return null;}
  localStorage.setItem(k,v);}catch(e){return null;}}

var m=document.createElement('div');m.id='asEvalModal';
m.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);'+
 'z-index:10003;align-items:center;justify-content:center';
m.innerHTML='<div style="background:#1a1f28;color:#e6ecf2;border-radius:10px;'+
 'padding:16px 20px;width:560px;max-width:92vw;max-height:88vh;'+
 'overflow:auto;box-shadow:0 8px 24px rgba(0,0,0,.5)">'+
 '<div style="font-weight:600;margin-bottom:4px">\\ud83e\\uddea \\u6d4b\\u8bd5\\u6700\\u4f18\\u5904\\u7406\\u7ec4\\u5408</div>'+
 '<div style="font-size:11px;opacity:.55;margin-bottom:12px">'+
 '\\u4e0a\\u4f20\\u540c\\u4e00\\u9996\\u66f2\\u76ee\\u7684\\u57fa\\u7840 MIDI\\uff08\\u5148\\u6b63\\u5e38\\u8f6c\\u4e00\\u6b21\\u5f97\\u5230\\uff09'+
 '\\u548c\\u53c2\\u8003 MIDI\\uff08\\u6743\\u5a01\\u7248\\uff09\\uff0c\\u670d\\u52a1\\u7aef\\u6d3e\\u751f 8 \\u4e2a\\u540e\\u5904\\u7406\\u53d8\\u4f53\\u5e76\\u8bc4\\u5206'+
 '\\uff08onset F1 + note F1 + onset MAE\\uff09\\uff0c\\u9009\\u4f18\\u540e\\u4e00\\u952e\\u5e94\\u7528\\u5230\\u5f53\\u524d\\u8bbe\\u7f6e</div>'+
 '<div style="display:flex;flex-direction:column;gap:10px">'+
 '<label style="font-size:12px">\\u57fa\\u7840 MIDI\\uff08\\u5f53\\u524d\\u8bbe\\u7f6e\\u8f6c\\u51fa\\u7684\\u7ed3\\u679c\\uff09'+
 '<input type="file" id="asEvBase" accept=".mid,.midi" style="margin-top:4px;display:block">'+
 '</label>'+
 '<label style="font-size:12px">\\u53c2\\u8003 MIDI\\uff08\\u6743\\u5a01\\u7248\\u672c\\uff09'+
 '<input type="file" id="asEvRef" accept=".mid,.midi" style="margin-top:4px;display:block">'+
 '</label>'+
 '<div style="font-size:11px;opacity:.6">\\u8bc4\\u6d4b\\u8303\\u56f4\\uff1a\\u667a\\u80fd\\u53bb\\u788e \\u00d7 \\u529b\\u5ea6\\u91cd\\u5efa \\u00d7 \\u8282\\u62cd\\u91cf\\u5316 = 8 \\u7ec4\\u5408'+
 '\\uff08pp4/5/7 \\u5b8c\\u6574\\u91cd\\u8f6c\\u9700\\u8981\\u53e6\\u5916\\u8dd1\\u961f\\u5217\\uff0c\\u4e0d\\u5728\\u672c\\u5730\\u8bc4\\u6d4b\\u8303\\u56f4\\uff09</div>'+
 '<div><button id="asEvStart" style="cursor:pointer;padding:5px 14px">\\u5f00\\u59cb\\u8bc4\\u6d4b</button>'+
 '<span id="asEvProg" style="margin-left:10px;font-size:12px;opacity:.7"></span>'+
 '<span id="asEvErr" style="margin-left:10px;font-size:12px;color:#e08a8a"></span></div>'+
 '<div id="asEvTable" style="margin-top:8px"></div>'+
 '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">'+
 '<button id="asEvClose" style="cursor:pointer;padding:4px 14px">\\u5173\\u95ed</button></div>'+
 '</div></div>';
document.body.appendChild(m);
m.addEventListener('click',function(e){if(e.target===m)m.style.display='none';});
el('asEvClose').onclick=function(){m.style.display='none';};

function comboLabel(c){
  var parts=[];
  parts.push(c.smartfrag?'\\u53bb\\u788e\\u5f00':'\\u53bb\\u788e\\u5173');
  parts.push(c.pp3?'\\u529b\\u5ea6\\u5f00':'\\u529b\\u5ea6\\u5173');
  parts.push(c.pp7?'\\u91cf\\u5316\\u5f00':'\\u91cf\\u5316\\u5173');
  return parts.join(' / ');}
function applyCombo(c){
  var m1=el('pp1'),m2=el('pp2'),p3=el('pp3'),p7=el('pp7');
  if(m1)m1.checked=!!c.smartfrag;
  if(m2)m2.checked=!!c.smartfrag;
  if(p3)p3.checked=!!c.pp3;
  if(p7)p7.checked=!!c.pp7;
  ls('as_g_smartfrag',c.smartfrag?'1':'0');
  ls('as_g_vel',c.pp3?'1':'0');
  ls('as_g_quant',c.pp7?'1':'0');
  if(typeof saveOpts==='function')saveOpts();
  if(typeof toast==='function')toast('\\u5df2\\u5e94\\u7528\\u7ec4\\u5408\\uff1a'+comboLabel(c));
  m.style.display='none';}
function renderResults(results){
  var tb=el('asEvTable');
  if(!results||!results.length){tb.innerHTML='<div style="font-size:12px;opacity:.5">\\u6682\\u65e0\\u7ed3\\u679c</div>';return;}
  var h='<table style="width:100%;border-collapse:collapse;font-size:12px">'+
   '<tr style="background:#141820"><th style="text-align:left;padding:6px">#</th>'+
   '<th style="text-align:left;padding:6px">\\u7ec4\\u5408</th>'+
   '<th style="text-align:right;padding:6px">Onset F1</th>'+
   '<th style="text-align:right;padding:6px">Note F1</th>'+
   '<th style="text-align:right;padding:6px">MAE</th>'+
   '<th style="text-align:right;padding:6px">\\u7efc\\u5408</th>'+
   '<th style="padding:6px"></th></tr>';
  results.forEach(function(r,i){
    var c=r.combo||{};
    var sc=(r.score!=null)?r.score.toFixed(4):'-';
    var of=(r.onset_f1!=null)?r.onset_f1.toFixed(4):'-';
    var nf=(r.note_f1!=null)?r.note_f1.toFixed(4):'-';
    var ma=(r.onset_mae!=null)?r.onset_mae.toFixed(3):'-';
    var err=r.error?'<span style="color:#e08a8a">ERR</span>':'';
    h+='<tr style="border-top:1px solid #2a3140">'+
     '<td style="padding:6px">'+(i+1)+'</td>'+
     '<td style="padding:6px">'+comboLabel(c)+(err?' '+err:'')+'</td>'+
     '<td style="text-align:right;padding:6px">'+of+'</td>'+
     '<td style="text-align:right;padding:6px">'+nf+'</td>'+
     '<td style="text-align:right;padding:6px">'+ma+'</td>'+
     '<td style="text-align:right;padding:6px;color:'+
     (i===0?'#8ad0a0':'#dfe6ee')+'">'+sc+'</td>'+
     '<td style="padding:6px"><button data-i="'+i+'" '+
     'style="cursor:pointer;padding:2px 8px;font-size:11px">\\u5e94\\u7528</button></td></tr>';});
  h+='</table>';
  tb.innerHTML=h;
  tb.querySelectorAll('button[data-i]').forEach(function(btn){
    btn.onclick=function(){
      var r=results[+btn.dataset.i];
      if(r&&r.combo)applyCombo(r.combo);};});}

var polling=null;
function poll(){
  fetch('/api/eval/status',{cache:'no-store'}).then(function(r){return r.json();})
  .then(function(j){
    if(j.running){
      el('asEvProg').textContent='\\u8fdb\\u5ea6 '+j.progress+'/'+j.total+
        (j.current?'\\uff08'+comboLabel(JSON.parse(j.current||'{}'))+'\\uff09':'');
      setTimeout(poll,600);return;}
    if(polling){clearInterval(polling);polling=null;}
    el('asEvProg').textContent='\\u5b8c\\u6210\\uff08'+(j.results||[]).length+' \\u7ec4\\uff09';
    if(j.error)el('asEvErr').textContent=j.error;
    renderResults(j.results||[]);})
  .catch(function(){el('asEvErr').textContent='\\u8f6e\\u8be2\\u5931\\u8d25';
    if(polling){clearInterval(polling);polling=null;}});}

el('asEvStart').onclick=function(){
  var bf=el('asEvBase').files[0], rf=el('asEvRef').files[0];
  el('asEvErr').textContent='';
  if(!bf||!rf){el('asEvErr').textContent='\\u8bf7\\u5148\\u9009\\u62e9\\u4e24\\u4e2a MIDI \\u6587\\u4ef6';return;}
  var fd=new FormData();
  fd.append('base',bf,bf.name);fd.append('ref',rf,rf.name);
  el('asEvProg').textContent='\\u542f\\u52a8\\u4e2d\\u2026';
  fetch('/api/eval/run',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(j){
    if(j.error){el('asEvErr').textContent=j.error;return;}
    if(polling)clearInterval(polling);
    polling=setInterval(poll,600);poll();})
  .catch(function(e){el('asEvErr').textContent='\\u542f\\u52a8\\u5931\\u8d25\\uff1a'+e;});};

el('asQEval').onclick=function(){
  m.style.display='flex';
  if(!polling)poll();};

// restore last results if any
try{var lr=JSON.parse(ls('as_eval_last')||'null');
  if(lr&&lr.length)renderResults(lr);}catch(e){}
// auto-save results after each poll completes
var _origPoll=poll;
poll=function(){
  fetch('/api/eval/status',{cache:'no-store'}).then(function(r){return r.json();})
  .then(function(j){
    if(j.done&&j.results&&j.results.length)
      ls('as_eval_last',JSON.stringify(j.results));
    _origPoll();}).catch(function(){});};
})();
</script>"""
    if "</body>" in s:
        s = s.replace("</body>", MODAL + "\n</body>", 1)
        ok.append("index.html: eval modal injected")
    else: fail.append("index.html: </body> not found")
else: ok.append("index.html: eval modal already present")
HP.write_text(s, encoding="utf-8")

print()
print("==== V11-EVAL RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
