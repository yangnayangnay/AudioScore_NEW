# -*- coding: utf-8 -*-
"""v13-registry: registry-driven auto-enumeration of eval combos
+ pre-analysis (global BPM + local tempo curve from audio)
+ optimized pp3 (RMS-driven velocity) + quant_local (tempo-curve quant)."""
from pathlib import Path
import re, shutil

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- 1. as_eval.py (rewrite, registry-based) ----------
EVAL = r'''# -*- coding: utf-8 -*-
"""as_eval v2: registry-driven evaluation with auto combo enumeration.
GET  /api/eval/registry  -> list of evaluable toggles
POST /api/eval/preanalyze (audio) -> {times, tempos, global_bpm}
POST /api/eval/run (base, ref, audio?, combos?) -> start bg job
GET  /api/eval/status -> progress + results
"""
import io, json, time, copy, threading
import numpy as np
from pathlib import Path

try:
    import pretty_midi
    HAS_PM = True
except ImportError:
    HAS_PM = False

try:
    import librosa
    HAS_LR = True
except ImportError:
    HAS_LR = False

STATE = {"running":False,"progress":0,"total":0,"current":"",
         "results":[],"done":False,"error":"","started":0,"finished":0,
         "has_audio":False,"global_bpm":None}

def _load_pm(b):
    return pretty_midi.PrettyMIDI(io.BytesIO(b))

def _pm_bytes(pm):
    buf = io.BytesIO(); pm.write(buf); return buf.getvalue()

def _notes(pm):
    out = []
    for inst in pm.instruments:
        for n in inst.notes:
            out.append((n.start, n.end, n.pitch))
    out.sort()
    return out

def score_pair(cand_bytes, ref_bytes, onset_tol=0.05, pitch_tol=50.0):
    try:
        import mir_eval
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

# ================= REGISTRY =================
REGISTRY = {}
def reg(key, label, default=False, requires_audio=False):
    def deco(fn):
        REGISTRY[key] = {"key":key,"label":label,"default":default,
                         "requires_audio":requires_audio,"apply":fn}
        return fn
    return deco

@reg("smartfrag", "\u667a\u80fd\u53bb\u788e\uff08\u8de8\u7247\u5408\u5e76+\u788e\u97f3\u5408\u5e76\uff09", default=True)
def _r_smartfrag(pm, enabled, ctx):
    if not enabled: return pm
    try:
        from as_postproc import pp17_cross_segment_merge, pp18_same_pitch_stitch
        pp17_cross_segment_merge(pm, overlap_s=0.02, gap_s=0.05)
        pp18_same_pitch_stitch(pm, gap_s=0.08)
    except Exception: pass
    return pm

@reg("pp3_vel", "\u529b\u5ea6\u91cd\u5efa\uff08RMS \u5305\u7edc\uff0c\u9700\u97f3\u9891\uff09", default=True)
def _r_vel(pm, enabled, ctx):
    if not enabled: return pm
    audio = ctx.get("audio")
    if audio is not None and HAS_LR:
        try:
            y, sr = audio
            hop = 512
            rms = librosa.feature.rms(y=y, hop_length=hop)[0]
            times = librosa.times_like(rms, sr=sr, hop_length=hop)
            mx = float(np.max(rms)) + 1e-9
            for inst in pm.instruments:
                for n in inst.notes:
                    i = int(np.searchsorted(times, n.start))
                    if 0 <= i < len(rms):
                        v = float(rms[i]) / mx
                        n.velocity = int(np.clip(20 + 107*v, 1, 127))
            return pm
        except Exception: pass
    # fallback: neutral
    for inst in pm.instruments:
        for n in inst.notes:
            n.velocity = 80
    return pm

@reg("quant_global", "\u8282\u62cd\u91cf\u5316\uff08\u5168\u5c40 BPM\uff09", default=False)
def _r_quant_global(pm, enabled, ctx):
    if not enabled: return pm
    try: bpm = pm.estimate_tempos()[0]
    except Exception: bpm = 120.0
    beat = 60.0 / max(bpm, 30.0) / 4
    for inst in pm.instruments:
        for n in inst.notes:
            n.start = round(n.start/beat)*beat
            n.end   = max(n.start+beat, round(n.end/beat)*beat)
    return pm

@reg("quant_local", "\u8282\u62cd\u91cf\u5316\uff08\u5c40\u90e8\u52a8\u6001 tempo\uff0c\u9700\u97f3\u9891\uff09", default=False, requires_audio=True)
def _r_quant_local(pm, enabled, ctx):
    if not enabled: return pm
    curve = ctx.get("tempo_curve")
    if not curve: return pm
    ts, tps = curve
    ts_a = np.array(ts); tps_a = np.array(tps)
    for inst in pm.instruments:
        for n in inst.notes:
            i = int(np.searchsorted(ts_a, n.start))
            if 0 <= i < len(tps_a):
                bpm = float(tps_a[i])
                if bpm > 30:
                    b = 60.0/bpm/4
                    n.start = round(n.start/b)*b
                    n.end   = max(n.start+b, round(n.end/b)*b)
    return pm

def preanalyze_audio(audio_bytes, sr=22050):
    """Compute global tempo + local tempo curve. Returns dict."""
    if not HAS_LR: return None
    try:
        y, _ = librosa.load(io.BytesIO(audio_bytes), sr=sr, mono=True)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(np.atleast_1d(tempo)[0])
        if len(beats) > 2:
            beat_t = librosa.frames_to_time(beats, sr=sr)
            iv = np.diff(beat_t)
            tps = 60.0 / np.maximum(iv, 1e-3)
            if len(tps) > 4:
                tps = np.convolve(tps, np.ones(3)/3, mode='same')
            mid = (beat_t[:-1] + beat_t[1:]) / 2
            return {"times":mid.tolist(),"tempos":tps.tolist(),
                    "global_bpm":tempo}
        # fallback: constant curve
        dur = len(y)/sr
        ts = list(np.arange(0, dur, 0.5))
        return {"times":ts,"tempos":[tempo]*len(ts),"global_bpm":tempo}
    except Exception:
        return None

def apply_combo(pm, combo, ctx):
    pm = copy.deepcopy(pm)
    for k, meta in REGISTRY.items():
        v = bool(combo.get(k, meta["default"]))
        if meta["requires_audio"] and not ctx.get("audio"):
            continue
        try:
            pm = meta["apply"](pm, v, ctx)
        except Exception: pass
    return pm

def enumerate_combos(selected_keys, cap=32):
    """Enumerate all 2^N combos from selected registry keys; sample if > cap."""
    import itertools, random
    keys = [k for k in selected_keys if k in REGISTRY]
    if not keys: return []
    n = len(keys)
    if 2**n <= cap:
        sizes = list(itertools.product([False, True], repeat=n))
    else:
        sizes = []
        seen = set()
        rng = random.Random(42)
        while len(sizes) < cap:
            t = tuple(rng.random() < 0.5 for _ in range(n))
            if t not in seen:
                seen.add(t); sizes.append(t)
    out = []
    for t in sizes:
        c = {k: bool(t[i]) for i,k in enumerate(keys)}
        out.append(c)
    return out

def run_eval(base_bytes, ref_bytes, combos, ctx):
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
            vpm = apply_combo(base_pm, c, ctx)
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

    @app.get("/api/eval/registry")
    def api_registry():
        return JSONResponse({"registry": [
            {"key":m["key"],"label":m["label"],"default":m["default"],
             "requires_audio":m["requires_audio"]}
            for m in REGISTRY.values()]})

    @app.post("/api/eval/preanalyze")
    async def api_preanalyze(audio: UploadFile = File(...)):
        data = await audio.read()
        r = preanalyze_audio(data)
        if not r: return JSONResponse({"error":"librosa not available or failed"})
        return JSONResponse(r)

    @app.post("/api/eval/run")
    async def api_run(base: UploadFile = File(...),
                      ref: UploadFile = File(...),
                      audio: UploadFile = File(None),
                      combos: str = Form(""),
                      keys: str = Form("")):
        if STATE.get("running"):
            return JSONResponse({"error":"eval already running"})
        cb = await base.read(); rb = await ref.read()
        ab = None
        if audio is not None:
            try: ab = await audio.read()
            except Exception: ab = None
        ctx = {}
        if ab:
            r = preanalyze_audio(ab)
            if r:
                try:
                    y, sr = librosa.load(io.BytesIO(ab), sr=22050, mono=True)
                    ctx["audio"] = (y, sr)
                except Exception: pass
                ctx["tempo_curve"] = (r["times"], r["tempos"])
                STATE["has_audio"]=True; STATE["global_bpm"]=r["global_bpm"]
            else:
                STATE["has_audio"]=False
        else:
            STATE["has_audio"]=False
        try:
            cl = json.loads(combos) if combos else None
        except Exception:
            cl = None
        if not cl:
            try: ks = json.loads(keys) if keys else []
            except Exception: ks = []
            if not ks:
                ks = [m["key"] for m in REGISTRY.values() if m["default"]]
            cl = enumerate_combos(ks)
        if not cl: return JSONResponse({"error":"empty combos"})
        threading.Thread(target=run_eval,args=(cb,rb,cl,ctx),daemon=True).start()
        return JSONResponse({"ok":True,"total":len(cl),
                              "has_audio":STATE["has_audio"]})

    @app.get("/api/eval/status")
    def api_status():
        return JSONResponse(STATE)
'''
(ROOT / "as_eval.py").write_text(EVAL, encoding="utf-8")
ok.append("as_eval.py rewritten (registry + preanalysis)")

# ---------- 2. setup.bat librosa ----------
sb = ROOT / "setup.bat"
DEP = ('REM ==AS_LR_DEPS v1==\r\n'
       '"%~dp0.venv\\Scripts\\python.exe" -m pip install librosa\r\n')
if sb.exists():
    t = sb.read_text(encoding="utf-8", errors="ignore")
    if "==AS_LR_DEPS==" not in t:
        lines = t.splitlines(keepends=True)
        pos = len(lines)
        for i in range(len(lines)-1,-1,-1):
            if "pause" in lines[i].lower(): pos = i; break
        lines.insert(pos, DEP)
        sb.write_text("".join(lines), encoding="utf-8")
        ok.append("setup.bat: librosa dep added")
    else: ok.append("setup.bat: already patched")
else: fail.append("setup.bat not found")

# ---------- 3. index.html: rewrite eval modal (registry-driven) ----------
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")

# remove old eval modal script
blocks = re.findall(r"<script\b[^>]*>[\s\S]*?</script>", s)
for b in blocks:
    if "==AS_EVAL_MODAL==" in b:
        s = s.replace(b, "", 1); ok.append("index.html: old eval modal removed")

MARK = "/* ==AS_EVAL_MODAL== */"
if MARK not in s:
    MODAL = r"""<script>
/* ==AS_EVAL_MODAL== v2 registry-driven */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
function ls(k,v){try{
  if(v===undefined)return localStorage.getItem(k);
  if(v===null){localStorage.removeItem(k);return null;}
  localStorage.setItem(k,v);}catch(e){return null;}}

var REG=[]; // fetched from server
var m=document.createElement('div');m.id='asEvalModal';
m.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);'+
 'z-index:10003;align-items:center;justify-content:center';
m.innerHTML='<div style="background:#1a1f28;color:#e6ecf2;border-radius:10px;'+
 'padding:16px 20px;width:600px;max-width:94vw;max-height:90vh;'+
 'overflow:auto;box-shadow:0 8px 24px rgba(0,0,0,.5)">'+
 '<div style="font-weight:600;margin-bottom:4px">\ud83e\uddea \u6d4b\u8bd5\u6700\u4f18\u5904\u7406\u7ec4\u5408</div>'+
 '<div style="font-size:11px;opacity:.55;margin-bottom:12px">'+
 '\u57fa\u7840 MIDI = \u5f53\u524d\u8bbe\u7f6e\u8f6c\u51fa\u7684\u7ed3\u679c\uff0c\u53c2\u8003 MIDI = \u6743\u5a01\u7248\u3002'+
 '\u97f3\u9891\u53ef\u9009\uff0c\u4f20\u4e86\u624d\u80fd\u8bc4\u6d4b\u529b\u5ea6\u91cd\u5efa\u548c\u52a8\u6001 tempo \u91cf\u5316</div>'+
 '<div style="display:flex;flex-direction:column;gap:10px">'+
 '<label style="font-size:12px">\u57fa\u7840 MIDI'+
 '<input type="file" id="asEvBase" accept=".mid,.midi" style="margin-top:4px;display:block"></label>'+
 '<label style="font-size:12px">\u53c2\u8003 MIDI'+
 '<input type="file" id="asEvRef" accept=".mid,.midi" style="margin-top:4px;display:block"></label>'+
 '<label style="font-size:12px">\u97f3\u9891\uff08\u53ef\u9009\uff0c\u542f\u7528 RMS \u529b\u5ea6\u548c\u52a8\u6001 tempo\uff09'+
 '<input type="file" id="asEvAudio" accept="audio/*" style="margin-top:4px;display:block"></label>'+
 '<div style="font-size:12px">\u8bc4\u6d4b\u9879\uff08\u4ece\u670d\u52a1\u7aef\u6ce8\u518c\u8868\u52a8\u6001\u52a0\u8f7d\uff09'+
 '<div id="asEvKeys" style="display:flex;flex-direction:column;gap:6px;'+
 'margin-top:6px;padding:8px;background:#141820;border:1px solid #2a3140;'+
 'border-radius:6px;font-size:12px"></div>'+
 '<div style="font-size:11px;opacity:.6;margin-top:6px">'+
 '\u9009\u62e9 N \u9879 \u2192 \u81ea\u52a8\u679a\u4e3e 2^N \u7ec4\u5408\uff0c\u8d85\u8fc7 32 \u7ec4\u81ea\u52a8\u91c7\u6837'+
 ' <span id="asEvN"></span></div></div>'+
 '<div><button id="asEvStart" style="cursor:pointer;padding:5px 14px">\u5f00\u59cb\u8bc4\u6d4b</button>'+
 '<button id="asEvAll" style="cursor:pointer;padding:5px 10px;margin-left:8px;font-size:12px">\u5168\u9009</button>'+
 '<button id="asEvNone" style="cursor:pointer;padding:5px 10px;margin-left:8px;font-size:12px">\u5168\u4e0d\u9009</button>'+
 '<span id="asEvProg" style="margin-left:10px;font-size:12px;opacity:.7"></span>'+
 '<span id="asEvErr" style="margin-left:10px;font-size:12px;color:#e08a8a"></span></div>'+
 '<div id="asEvTable" style="margin-top:8px"></div>'+
 '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">'+
 '<button id="asEvClose" style="cursor:pointer;padding:4px 14px">\u5173\u95ed</button></div>'+
 '</div></div>';
document.body.appendChild(m);
m.addEventListener('click',function(e){if(e.target===m)m.style.display='none';});
el('asEvClose').onclick=function(){m.style.display='none';};

function fetchRegistry(){
  fetch('/api/eval/registry',{cache:'no-store'}).then(function(r){return r.json();})
  .then(function(j){
    REG=(j.registry||[]);
    renderKeys();})
  .catch(function(){el('asEvErr').textContent='\u6ce8\u518c\u8868\u52a0\u8f7d\u5931\u8d25';});}
function renderKeys(){
  var box=el('asEvKeys');box.innerHTML='';
  REG.forEach(function(it,i){
    var lab=document.createElement('label');
    lab.style.cssText='display:flex;align-items:center;gap:8px;cursor:pointer';
    var cb=document.createElement('input');cb.type='checkbox';
    cb.dataset.k=it.key;cb.checked=!!it.default;
    if(it.requires_audio){
      var sp=document.createElement('span');
      sp.style.cssText='font-size:10px;color:#e0b060;margin-left:4px';
      sp.textContent='[\u9700\u97f3\u9891]';
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(it.label));
      lab.appendChild(sp);
    } else {
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(it.label));
    }
    cb.onchange=updN;
    box.appendChild(lab);});
  updN();}
function updN(){
  var n=el('asEvKeys').querySelectorAll('input:checked').length;
  el('asEvN').textContent='\uff08\u5f53\u524d '+n+' \u9879 \u2192 '+
    (n===0?0:Math.min(32,Math.pow(2,n)))+' \u7ec4\uff09';}
function comboLabel(c){
  var parts=[];
  Object.keys(c).forEach(function(k){
    var it=REG.filter(function(x){return x.key===k;})[0];
    if(!it)return;
    parts.push((c[k]?'\u2713':'\u2717')+' '+it.label);});
  return parts.join(' | ')||'(none)';}
function applyCombo(c){
  Object.keys(c).forEach(function(k){
    var it=REG.filter(function(x){return x.key===k;})[0];
    if(!it)return;
    // map registry key back to pp toggles (best effort)
    if(k==='smartfrag'){
      ['pp1','pp2'].forEach(function(id){var e=el(id);if(e)e.checked=!!c[k];});
      ls('as_g_smartfrag',c[k]?'1':'0');}
    else if(k==='pp3_vel'){
      var e=el('pp3');if(e)e.checked=!!c[k];
      ls('as_g_vel',c[k]?'1':'0');}
    else if(k==='quant_global'||k==='quant_local'){
      var e2=el('pp7');if(e2)e2.checked=!!c[k];
      ls('as_g_quant',c[k]?'1':'0');}});
  if(typeof saveOpts==='function')saveOpts();
  if(typeof toast==='function')toast('\u5df2\u5e94\u7528\u7ec4\u5408');
  m.style.display='none';}
function renderResults(results){
  var tb=el('asEvTable');
  if(!results||!results.length){tb.innerHTML='<div style="font-size:12px;opacity:.5">\u6682\u65e0\u7ed3\u679c</div>';return;}
  var h='<table style="width:100%;border-collapse:collapse;font-size:11px">'+
   '<tr style="background:#141820"><th style="text-align:left;padding:6px">#</th>'+
   '<th style="text-align:left;padding:6px">\u7ec4\u5408</th>'+
   '<th style="text-align:right;padding:6px">Onset F1</th>'+
   '<th style="text-align:right;padding:6px">Note F1</th>'+
   '<th style="text-align:right;padding:6px">MAE</th>'+
   '<th style="text-align:right;padding:6px">\u7efc\u5408</th>'+
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
     '<td style="padding:6px;font-size:10px">'+comboLabel(c)+(err?' '+err:'')+'</td>'+
     '<td style="text-align:right;padding:6px">'+of+'</td>'+
     '<td style="text-align:right;padding:6px">'+nf+'</td>'+
     '<td style="text-align:right;padding:6px">'+ma+'</td>'+
     '<td style="text-align:right;padding:6px;color:'+
     (i===0?'#8ad0a0':'#dfe6ee')+'">'+sc+'</td>'+
     '<td style="padding:6px"><button data-i="'+i+'" '+
     'style="cursor:pointer;padding:2px 8px;font-size:11px">\u5e94\u7528</button></td></tr>';});
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
      el('asEvProg').textContent='\u8fdb\u5ea6 '+j.progress+'/'+j.total;
      setTimeout(poll,600);return;}
    if(polling){clearInterval(polling);polling=null;}
    el('asEvProg').textContent='\u5b8c\u6210\uff08'+(j.results||[]).length+' \u7ec4\uff09'+
      (j.global_bpm?'\uff0c\u5168\u5c40 BPM='+j.global_bpm.toFixed(1):'');
    if(j.error)el('asEvErr').textContent=j.error;
    renderResults(j.results||[]);
    if(j.results&&j.results.length)
      ls('as_eval_last',JSON.stringify(j.results));})
  .catch(function(){el('asEvErr').textContent='\u8f6e\u8be2\u5931\u8d25';
    if(polling){clearInterval(polling);polling=null;}});}

el('asEvStart').onclick=function(){
  var bf=el('asEvBase').files[0], rf=el('asEvRef').files[0];
  var af=el('asEvAudio').files[0];
  el('asEvErr').textContent='';
  if(!bf||!rf){el('asEvErr').textContent='\u8bf7\u5148\u9009\u62e9\u57fa\u7840\u548c\u53c2\u8003 MIDI';return;}
  var ks=[];
  el('asEvKeys').querySelectorAll('input:checked').forEach(function(cb){
    ks.push(cb.dataset.k);});
  if(!ks.length){el('asEvErr').textContent='\u81f3\u5c11\u9009\u4e00\u9879\u8bc4\u6d4b';return;}
  var fd=new FormData();
  fd.append('base',bf,bf.name);fd.append('ref',rf,rf.name);
  if(af)fd.append('audio',af,af.name);
  fd.append('keys',JSON.stringify(ks));
  el('asEvProg').textContent='\u542f\u52a8\u4e2d\u2026';
  fetch('/api/eval/run',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(j){
    if(j.error){el('asEvErr').textContent=j.error;return;}
    if(polling)clearInterval(polling);
    polling=setInterval(poll,600);poll();})
  .catch(function(e){el('asEvErr').textContent='\u542f\u52a8\u5931\u8d25\uff1a'+e;});};

el('asEvAll').onclick=function(){
  el('asEvKeys').querySelectorAll('input[type=checkbox]').forEach(function(cb){cb.checked=true;});
  updN();};
el('asEvNone').onclick=function(){
  el('asEvKeys').querySelectorAll('input[type=checkbox]').forEach(function(cb){cb.checked=false;});
  updN();};

el('asQEval').onclick=function(){
  m.style.display='flex';
  if(!REG.length)fetchRegistry();};

try{var lr=JSON.parse(ls('as_eval_last')||'null');
  if(lr&&lr.length)renderResults(lr);}catch(e){}
})();
</script>"""
    if "</body>" in s:
        s = s.replace("</body>", MODAL + "\n</body>", 1)
        ok.append("index.html: eval modal v2 injected")
    else: fail.append("index.html: </body> not found")
else: ok.append("index.html: eval modal already present")
HP.write_text(s, encoding="utf-8")

print()
print("==== V13-REGISTRY RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
