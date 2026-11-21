# -*- coding: utf-8 -*-
"""v20-dock: bottom dock bar
(1) eval entry button MOVED to bottom dock (keeps original binding)
(2) one visible chip-button per new mechanism (9 chips), persisted,
    dependency-linked (rhythm_ext needs rhythm_quant), prefills eval modal,
    written back by eval "apply"
(3) quick best-report button + apply-to-MIDI tool (file->process->download)
(4) /api/eval/adv_apply endpoint in as_eval.py"""
from pathlib import Path
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ================= 1. as_eval.py: adv_apply endpoint =================
ep = ROOT / "as_eval.py"
s = ep.read_text(encoding="utf-8")
A1 = '        return PlainTextResponse(p.read_text(encoding="utf-8-sig"))'
if s.count(A1) != 1:
    fail.append("as_eval.py: best_txt anchor count=%d (expected 1)" % s.count(A1))
elif "adv_apply" in s:
    ok.append("as_eval.py: adv_apply already present")
else:
    ENDPOINT = A1 + """

    @app.post("/api/eval/adv_apply")
    async def api_adv_apply(base: UploadFile = File(...),
                            audio: UploadFile = File(None),
                            flags: str = Form("{}")):
        from fastapi.responses import Response
        cb = await base.read()
        ab = None
        if audio is not None:
            try: ab = await audio.read()
            except Exception: ab = None
        try: fl = json.loads(flags) if flags else {}
        except Exception: fl = {}
        ctx = {}
        if ab:
            ta = tempo_from_audio(ab)
            if ta:
                ctx["bpm_audio"] = ta["bpm"]; ctx["curve_audio"] = ta["curve"]
            try:
                y, sr = librosa.load(io.BytesIO(ab), sr=22050, mono=True)
                ctx["audio"] = (y, sr)
            except Exception: pass
        combo = {k: bool(fl.get(k, m["default"])) for k, m in REGISTRY.items()}
        try:
            pm = _load_pm(cb)
            out = apply_combo(pm, combo, ctx)
            data = _pm_bytes(out)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return Response(content=data, media_type="audio/midi",
                        headers={"Content-Disposition":
                                 'attachment; filename="processed_adv.mid"'})"""
    s = s.replace(A1, ENDPOINT, 1)
    ep.write_text(s, encoding="utf-8")
    ok.append("as_eval.py: POST /api/eval/adv_apply added")
try:
    py_compile.compile(str(ep), doraise=True)
    ok.append("as_eval.py compile OK")
except py_compile.PyCompileError as e:
    fail.append("as_eval.py compile FAIL: %s" % str(e)[:300])

# ================= 2. index.html =================
HP = ROOT / "web" / "index.html"
h = HP.read_text(encoding="utf-8")

# 2a. applyCombo writes back to dock chips (full state incl. false)
A2 = "  if(typeof saveOpts==='function')saveOpts();"
if h.count(A2) != 1:
    fail.append("index.html: applyCombo anchor count=%d" % h.count(A2))
elif "as_adv_" in h:
    ok.append("index.html: applyCombo writeback already present")
else:
    N2 = ("  try{document.querySelectorAll('[data-adv]').forEach(function(ch){"
          "var k=ch.dataset.adv;ch.checked=!!c[k];"
          "try{localStorage.setItem('as_adv_'+k,ch.checked?'1':'0');}catch(e){}"
          "if(k==='smartfrag'){ls('as_g_smartfrag',ch.checked?'1':'0');}"
          "if(k==='pp3_vel'){ls('as_g_vel',ch.checked?'1':'0');}});"
          "ls('as_g_quant',(['tempo_hist','tempo_adapt','quant_global','quant_local',"
          "'rhythm_quant','rhythm_ext','tempo_write'].some(function(k){return !!c[k];}))?'1':'0');"
          "if(typeof window.__asSyncDeps==='function')window.__asSyncDeps();}catch(e){}\n"
          + A2)
    h = h.replace(A2, N2, 1)
    ok.append("index.html: applyCombo now writes back to dock chips")

# 2b. prefill combo checkboxes from chips when modal opens
A3 = "if(!REG.length)fetchRegistry();};"
if h.count(A3) != 1:
    fail.append("index.html: open-modal anchor count=%d" % h.count(A3))
elif "__asPrefill" in h:
    ok.append("index.html: prefill hook already present")
else:
    N3 = ("if(!REG.length)fetchRegistry();"
          "setTimeout(function(){"
          "if(typeof window.__asPrefill==='function')window.__asPrefill();},300);};")
    h = h.replace(A3, N3, 1)
    ok.append("index.html: modal open prefills from dock chips")

# 2c. dock script
if "==AS_DOCK==" in h:
    ok.append("index.html: dock already present")
elif "</body>" not in h:
    fail.append("index.html: </body> not found")
else:
    DOCK = r"""<script>
/* ==AS_DOCK== v20 bottom dock: eval entry + 9 mechanism chips + tools */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
function ls(k,v){try{if(v===undefined)return localStorage.getItem(k);
 if(v===null){localStorage.removeItem(k);return null;}
 localStorage.setItem(k,v);}catch(e){return null;}}
if(el('asDock'))return;
var CHIPS=[["smartfrag","\u667a\u80fd\u53bb\u788e","as_g_smartfrag"],
 ["pp3_vel","\u529b\u5ea6\u91cd\u5efa","as_g_vel"],
 ["tempo_hist","\u901f\u5ea6\u00b7IOI\u76f4\u65b9\u56fe",null],
 ["tempo_adapt","\u53d8\u901f\u00b7\u81ea\u9002\u5e94\u722c\u5c71",null],
 ["quant_global","\u8282\u62cd\u91cf\u5316\u00b7\u5168\u5c40",null],
 ["quant_local","\u8282\u62cd\u91cf\u5316\u00b7\u5c40\u90e8",null],
 ["rhythm_quant","\u8282\u594f\u578b\u6a21\u5f0f\u91cf\u5316",null],
 ["rhythm_ext","\u6269\u5c55\u8282\u594f\u578b(\u9700\u8282\u594f\u91cf\u5316)",null],
 ["tempo_write","\u53d8\u901f\u5199\u56de",null]];
var NEEDS_Q=["tempo_hist","tempo_adapt","quant_global","quant_local",
 "rhythm_quant","rhythm_ext","tempo_write"];
var dock=document.createElement('div');dock.id='asDock';
dock.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:10002;'+
 'background:rgba(16,20,26,.97);border-top:1px solid #2a3140;'+
 'padding:8px 12px;display:flex;align-items:center;gap:8px;overflow-x:auto';
var lab=document.createElement('span');
lab.textContent='\u9ad8\u7ea7\u5904\u7406:';
lab.style.cssText='font-size:12px;color:#8fa0b5;white-space:nowrap';
dock.appendChild(lab);
function chipStyle(c,chip){chip.style.background=c?'#25406a':'#141820';
 chip.style.borderColor=c?'#3a6ea5':'#2a3140';
 chip.style.color=c?'#fff':'#cfd8e3';}
function syncChip(key){
 var cb=el('adv_'+key);if(!cb)return;var chip=cb.parentNode;
 chipStyle(cb.checked,chip);
 ls('as_adv_'+key,cb.checked?'1':'0');
 if(key==='smartfrag')ls('as_g_smartfrag',cb.checked?'1':'0');
 if(key==='pp3_vel')ls('as_g_vel',cb.checked?'1':'0');
 if(NEEDS_Q.indexOf(key)>=0){
   var any=NEEDS_Q.some(function(k){var c=el('adv_'+k);return c&&c.checked;});
   ls('as_g_quant',any?'1':'0');}
 if(key==='rhythm_quant'){var ex=el('adv_rhythm_ext');
   if(ex){var l2=ex.parentNode;
     if(!cb.checked){ex.checked=false;ls('as_adv_rhythm_ext','0');
       l2.style.opacity='.4';l2.style.pointerEvents='none';chipStyle(false,l2);}
     else{l2.style.opacity='1';l2.style.pointerEvents='auto';
       syncChip('rhythm_ext');}}}}
CHIPS.forEach(function(d){
 var key=d[0];
 var l=document.createElement('label');l.className='as-chip';
 l.style.cssText='display:inline-flex;align-items:center;gap:6px;'+
  'padding:4px 10px;border:1px solid #2a3140;border-radius:16px;'+
  'cursor:pointer;font-size:12px;user-select:none;white-space:nowrap';
 var cb=document.createElement('input');cb.type='checkbox';
 cb.id='adv_'+key;cb.dataset.adv=key;cb.style.display='none';
 var saved=ls('as_adv_'+key);
 cb.checked=(saved===null)?(key==='smartfrag'||key==='pp3_vel'):(saved==='1');
 var txt=document.createElement('span');txt.textContent=d[1];
 l.appendChild(cb);l.appendChild(txt);
 l.addEventListener('click',function(ev){ev.preventDefault();
   if(key==='rhythm_ext'){var rq=el('adv_rhythm_quant');
     if(!rq||!rq.checked)return;}
   cb.checked=!cb.checked;syncChip(key);});
 dock.appendChild(l);});
document.body.appendChild(dock);
try{document.body.style.paddingBottom='70px';}catch(e){}
window.__asSyncDeps=function(){CHIPS.forEach(function(d){syncChip(d[0]);});};
window.__asSyncDeps();
window.__asPrefill=function(){
 var kb=el('asEvKeys');if(!kb)return;
 kb.querySelectorAll('input[data-k]').forEach(function(cb){
   var chip=el('adv_'+cb.dataset.k);if(chip)cb.checked=chip.checked;});
 var n=kb.querySelectorAll('input:checked').length;
 var ne=el('asEvN');
 if(ne)ne.textContent='\u5f53\u524d '+n+' \u9879 \u2192 '+
  (n===0?0:Math.min(32,Math.pow(2,n)))+
  ' \u7ec4\uff08\u4f9d\u8d56\u65e0\u6548\u7ec4\u5408\u81ea\u52a8\u5254\u9664\uff09';};
window.__asEnsureRegistry=function(){
 var kb=el('asEvKeys');if(!kb||kb.children.length)return;
 fetch('/api/eval/registry',{cache:'no-store'})
 .then(function(r){return r.json();}).then(function(j){
   var ob=el('asEvOpts');
   if(ob&&!ob.children.length){
     (j.score_options||[]).forEach(function(o){
       if(o.type==='enum'){
         var w=document.createElement('label');
         w.style.cssText='display:flex;align-items:center;gap:8px';
         w.appendChild(document.createTextNode(o.label));
         var sel=document.createElement('select');sel.dataset.k=o.key;
         sel.style.cssText='margin-left:auto;background:#1a1f28;'+
          'color:#e6ecf2;border:1px solid #2a3140';
         (o.options||[]).forEach(function(v){
           var op=document.createElement('option');op.value=v;op.textContent=v;
           if(v===o.default)op.selected=true;sel.appendChild(op);});
         w.appendChild(sel);ob.appendChild(w);
       }else{
         var w2=document.createElement('label');
         w2.style.cssText='display:flex;align-items:center;gap:8px;cursor:pointer';
         var cb2=document.createElement('input');cb2.type='checkbox';
         cb2.dataset.k=o.key;cb2.checked=!!o.default;
         w2.appendChild(cb2);w2.appendChild(document.createTextNode(o.label));
         ob.appendChild(w2);}});}
   (j.combo_items||[]).forEach(function(it){
     var l3=document.createElement('label');
     l3.style.cssText='display:flex;align-items:center;gap:8px;cursor:pointer';
     var cb3=document.createElement('input');cb3.type='checkbox';
     cb3.dataset.k=it.key;cb3.checked=!!it.default;
     l3.appendChild(cb3);l3.appendChild(document.createTextNode(it.label));
     kb.appendChild(l3);});
   if(typeof window.__asPrefill==='function')window.__asPrefill();})
 .catch(function(){});};
var q=el('asQEval');
if(q){q.style.whiteSpace='nowrap';dock.insertBefore(q,dock.children[1]);}
else{var b=document.createElement('button');b.id='asQEval';
 b.textContent='\ud83e\uddea \u6d4b\u8bd5\u6700\u4f18\u7ec4\u5408';
 b.style.cssText='cursor:pointer;padding:5px 12px;white-space:nowrap';
 b.onclick=function(){var m=el('asEvalModal');if(!m)return;
   m.style.display='flex';window.__asEnsureRegistry();
   setTimeout(function(){if(typeof window.__asPrefill==='function')
     window.__asPrefill();},300);};
 dock.insertBefore(b,dock.children[1]);}
var rb=document.createElement('button');
rb.textContent='\ud83d\udcc4 \u6700\u4f18\u62a5\u544a';
rb.title='\u6253\u5f00 best_combo.txt';
rb.style.cssText='cursor:pointer;padding:5px 10px;font-size:12px;white-space:nowrap';
rb.onclick=function(){window.open('/api/eval/best_txt','_blank');};
dock.appendChild(rb);
var ab=document.createElement('button');
ab.textContent='\ud83d\udee0 \u5e94\u7528\u5230MIDI';
ab.title='\u9009\u62e9MIDI\u2192\u6309\u5f53\u524d\u5f00\u5173\u5904\u7406\u2192\u4e0b\u8f7d';
ab.style.cssText='cursor:pointer;padding:5px 10px;font-size:12px;white-space:nowrap';
var fi=document.createElement('input');fi.type='file';
fi.accept='.mid,.midi';fi.style.display='none';document.body.appendChild(fi);
var ai=document.createElement('input');ai.type='file';
ai.accept='audio/*';ai.style.display='none';document.body.appendChild(ai);
function flagsJson(){var o={};
 dock.querySelectorAll('input[data-adv]').forEach(function(cb){
   o[cb.dataset.adv]=cb.checked;});return JSON.stringify(o);}
function doApply(){
 var f=fi.files[0];if(!f)return;
 var fd=new FormData();fd.append('base',f,f.name);
 if(ai.files[0])fd.append('audio',ai.files[0],ai.files[0].name);
 fd.append('flags',flagsJson());
 ab.textContent='\u5904\u7406\u4e2d\u2026';
 fetch('/api/eval/adv_apply',{method:'POST',body:fd})
 .then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.blob();})
 .then(function(bl){var u=URL.createObjectURL(bl);
   var a=document.createElement('a');a.href=u;a.download='processed_adv.mid';
   document.body.appendChild(a);a.click();a.remove();
   setTimeout(function(){URL.revokeObjectURL(u);},3000);})
 .catch(function(e){alert('\u5e94\u7528\u5931\u8d25: '+e);})
 .then(function(){ab.textContent='\ud83d\udee0 \u5e94\u7528\u5230MIDI';});}
ab.onclick=function(){fi.value='';ai.value='';fi.click();};
fi.onchange=function(){if(!fi.files[0])return;
 if(confirm('\u9644\u5e26\u97f3\u9891\uff1f\uff08\u7528\u4e8e\u529b\u5ea6\u91cd\u5efa/\u97f3\u9891tempo\uff0c\u53d6\u6d88=\u4e0d\u9644\u5e26\uff09'))ai.click();
 else doApply();};
ai.onchange=function(){doApply();};
dock.appendChild(ab);
})();
</script>"""
    h = h.replace("</body>", DOCK + "\n</body>", 1)
    ok.append("index.html: bottom dock injected (chips + moved eval entry + 2 tools)")
HP.write_text(h, encoding="utf-8")

print()
print("==== V20-DOCK RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
