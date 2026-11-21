# -*- coding: utf-8 -*-
"""v24-fixregistry:
- LIVE probe /api/eval/registry etc -> decisive evidence (404 = server old,
  200 = frontend issue)
- frontend: override silent loader with loud one + reload button in modal
- server.py hook: ensure exists + full traceback on import failure"""
from pathlib import Path
import re, py_compile, urllib.request, json, traceback as tb

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []

# ---------- 0. LIVE probe (decisive) ----------
def probe(path):
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=4)
        body = r.read(200).decode("utf-8", "ignore")
        return r.status, body
    except Exception as e:
        code = getattr(e, "code", None)
        return (code, str(e)[:120]) if code else (None, str(e)[:120])

for pth in ("/", "/api/eval/registry", "/api/eval/status", "/api/eval/best_txt"):
    st, body = probe(pth)
    if st == 200:
        info.append("PROBE %s -> 200 OK  %s" % (pth, body[:100]))
    elif st is None:
        info.append("PROBE %s -> 连接失败 (%s)" % (pth, body))
    else:
        fail.append("PROBE %s -> HTTP %s  <-- 服务端没有这个接口!" % (pth, st))
reg_st, _ = probe("/api/eval/registry")
if reg_st == 404:
    info.append(">>> 结论: 正在运行的服务是旧代码, 重启服务即修复")
elif reg_st == 200:
    info.append(">>> 结论: 后端正常, 问题在前端(静默吞错), v24已修")

# ---------- 1. index.html: loud loader + reload button ----------
HP = ROOT / "web" / "index.html"
h = HP.read_text(encoding="utf-8")
if "==AS_EVAL_FIX==" in h:
    ok.append("index.html: fix block already present")
elif "</body>" not in h:
    fail.append("index.html: </body> not found")
else:
    FIX = r"""<script>
/* ==AS_EVAL_FIX== v24 loud registry loader + reload button */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
function esc(s){return String(s).replace(/[<>&]/g,function(c){
 return {'<':'&lt;','>':'&gt;','&':'&amp;'}[c];});}
function showErr(msg){var e=el('asEvErr');if(e){e.textContent=msg;e.style.color='#e08a8a';}}
window.__asEnsureRegistry=function(force){
 var kb=el('asEvKeys');if(!kb)return;
 if(!force&&kb.children.length)return;
 showErr('');
 fetch('/api/eval/registry',{cache:'no-store'}).then(function(r){
   if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
 .then(function(j){
   var ob=el('asEvOpts');
   if(ob){ob.innerHTML='';
     (j.score_options||[]).forEach(function(o){
       var w=document.createElement('label');
       w.style.cssText='display:flex;align-items:center;gap:8px;flex-wrap:wrap';
       w.appendChild(document.createTextNode(o.label));
       if(o.type==='enum'){
         var sel=document.createElement('select');sel.dataset.k=o.key;
         sel.dataset.t='enum';
         sel.style.cssText='margin-left:auto;background:#1a1f28;color:#e6ecf2;'+
          'border:1px solid #2a3140';
         (o.options||[]).forEach(function(v){
           var op=document.createElement('option');op.value=v;op.textContent=v;
           if(v===o.default)op.selected=true;sel.appendChild(op);});
         w.appendChild(sel);
       }else{
         var cb=document.createElement('input');cb.type='checkbox';
         cb.dataset.k=o.key;cb.dataset.t='bool';cb.checked=!!o.default;
         w.insertBefore(cb,w.firstChild);ob.insertBefore(w,ob.firstChild);
         return;}
       ob.appendChild(w);});}
   kb.innerHTML='';
   (j.combo_items||[]).forEach(function(it){
     var l=document.createElement('label');
     l.style.cssText='display:flex;align-items:center;gap:8px;cursor:pointer;'+
      'flex-wrap:wrap';
     var cb=document.createElement('input');cb.type='checkbox';
     cb.dataset.k=it.key;cb.checked=!!it.default;
     l.appendChild(cb);
     l.appendChild(document.createTextNode(it.label));
     if(it.requires_audio){
       var s1=document.createElement('span');
       s1.style.cssText='font-size:10px;color:#e0b060';
       s1.textContent='[\u9700\u97f3\u9891]';l.appendChild(s1);}
     if(it.requires_key){
       var s2=document.createElement('span');
       s2.style.cssText='font-size:10px;color:#7aa2e0';
       s2.textContent='[\u9700:'+it.requires_key+']';l.appendChild(s2);}
     cb.addEventListener('change',updN);
     kb.appendChild(l);});
   updN();})
 .catch(function(e){showErr('\u5f00\u5173\u5217\u8868\u52a0\u8f7d\u5931\u8d25: '+
   e.message+' \u2014 \u82e5\u91cd\u8bd5\u65e0\u6548, \u8bf7\u91cd\u542f\u670d\u52a1\u540e\u5237\u65b0\u9875\u9762');});};
function updN(){
 var kb=el('asEvKeys');if(!kb)return;
 var n=kb.querySelectorAll('input[data-k]:checked').length;
 var ne=el('asEvN');
 if(ne)ne.textContent='\u5f53\u524d '+n+' \u9879 \u2192 '+
  (n===0?0:Math.min(32,Math.pow(2,n)))+
  ' \u7ec4\uff08\u4f9d\u8d56\u65e0\u6548\u7ec4\u5408\u81ea\u52a8\u5254\u9664\uff09';}
window.__asPrefill=function(){
 var kb=el('asEvKeys');if(!kb)return;
 kb.querySelectorAll('input[data-k]').forEach(function(cb){
   var chip=el('adv_'+cb.dataset.k);
   if(chip)cb.checked=chip.checked;});
 updN();};
var m=el('asEvalModal');
if(m&&!el('asEvReload')){
 var row=document.createElement('button');row.id='asEvReload';
 row.textContent='\ud83d\udd04 \u91cd\u65b0\u52a0\u8f7d\u5f00\u5173\u5217\u8868';
 row.style.cssText='cursor:pointer;padding:4px 10px;font-size:12px;'+
  'margin-left:8px';
 var allBtn=el('asEvAll');
 if(allBtn&&allBtn.parentNode){
   allBtn.parentNode.insertBefore(row,allBtn.nextSibling);}else{
   var tb=el('asEvTable');if(tb&&tb.parentNode)tb.parentNode.insertBefore(row,tb);}
 row.onclick=function(){window.__asEnsureRegistry(true);};}
var q=el('asQEval');
if(q)q.addEventListener('click',function(){
 setTimeout(function(){window.__asEnsureRegistry();},400);});
})();
</script>"""
    h = h.replace("</body>", FIX + "\n</body>", 1)
    ok.append("index.html: loud loader + reload button + open-hook injected")
HP.write_text(h, encoding="utf-8")

# ---------- 2. server.py hook: ensure + traceback ----------
sp = ROOT / "server.py"
t = sp.read_text(encoding="utf-8", errors="ignore")
if "as_eval" not in t:
    lines = t.splitlines(keepends=True)
    pos = None
    for i, l in enumerate(lines):
        if re.match(r"^\s*app\s*=\s*FastAPI", l):
            pos = i + 1; break
    if pos is None:
        fail.append("server.py: no app=FastAPI anchor")
    else:
        hook = ('# ==AS_EVAL_HOOK v24==\n'
                'try:\n'
                '    import as_eval as _as_eval\n'
                '    _as_eval.install_live(app)\n'
                '    print("[OK] as_eval endpoints installed")\n'
                'except Exception:\n'
                '    import traceback as _tb; print("[FAIL] as_eval hook:");'
                ' _tb.print_exc()\n'
                '# ==/AS_EVAL_HOOK==\n')
        lines.insert(pos, hook)
        sp.write_text("".join(lines), encoding="utf-8")
        ok.append("server.py: hook inserted (with traceback on failure)")
elif "print_exc" not in t:
    t = t.replace(
        "except Exception as _e:\n    print('[WARN] as_eval hook failed:', _e)",
        "except Exception:\n    import traceback as _tb\n"
        "    print('[FAIL] as_eval hook:'); _tb.print_exc()")
    sp.write_text(t, encoding="utf-8")
    ok.append("server.py: hook upgraded to print full traceback")
else:
    ok.append("server.py: hook present with traceback")
try:
    py_compile.compile(str(sp), doraise=True)
    ok.append("server.py compile OK")
except py_compile.PyCompileError as e:
    fail.append("server.py compile FAIL: %s" % str(e)[:300])

print()
print("==== V24-FIXREGISTRY ====")
for l in ok:   print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("=========================")
