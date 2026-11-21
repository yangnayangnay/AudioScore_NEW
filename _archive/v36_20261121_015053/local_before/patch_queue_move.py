# -*- coding: utf-8 -*-
"""Queue panel v3: place right under file input + sticky pin + collapsible."""
from pathlib import Path
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
ok, fail = [], []

FULL_PPS = ",".join("'pp%d'" % k for k in range(1, 17))
QUEUE = r"""<script>
(function(){
  var OPTKEY='as_opts';
  var PPS=[__PPS__];
  function el(id){return document.getElementById(id);}
  function toast(msg){
    var t=el('asToast');
    if(!t){t=document.createElement('div');t.id='asToast';
      t.style.cssText='position:fixed;bottom:18px;left:50%;transform:translateX(-50%);'+
        'background:#333;color:#fff;padding:8px 16px;border-radius:6px;font-size:13px;z-index:10000';
      document.body.appendChild(t);}
    t.textContent=msg;t.style.opacity='1';
    clearTimeout(t.__h);t.__h=setTimeout(function(){t.style.opacity='0';},2400);
  }
  function saveOpts(){
    var o={};PPS.forEach(function(id){var e=el(id);if(e)o[id]=!!e.checked;});
    var be=el('backend');if(be)o.backend=be.value;
    try{localStorage.setItem(OPTKEY,JSON.stringify(o));}catch(e){}
  }
  function loadOpts(){
    var o;try{o=JSON.parse(localStorage.getItem(OPTKEY)||'{}');}catch(e){o={};}
    PPS.forEach(function(id){var e=el(id);if(e&&(id in o))e.checked=!!o[id];});
    var be=el('backend');if(be&&o.backend)be.value=o.backend;
  }
  loadOpts();
  PPS.forEach(function(id){var e=el(id);if(e)e.addEventListener('change',saveOpts);});
  var be=el('backend');if(be)be.addEventListener('change',saveOpts);
  var input=document.querySelector('input[type="file"]');
  if(input)try{input.multiple=true;}catch(e){}
  var btn=null,autoPass=false;
  var cands=document.querySelectorAll('button, input[type="button"], input[type="submit"]');
  for(var i=0;i<cands.length;i++){
    var t=((cands[i].textContent||'')+(cands[i].value||'')).trim();
    if(/\u5f00\u59cb|\u8f6c\u6362|\u8f6c\u5199/.test(t)){btn=cands[i];break;}
  }
  var Q=[],busy=false,dragIdx=-1;
  var panel=document.createElement('div');panel.id='asQueue';
  panel.style.cssText='border:1px solid #3a3f4a;border-radius:8px;padding:8px 12px;'+
    'margin:10px 0;position:sticky;top:0;z-index:500;'+
    'background:rgba(16,18,24,.97);box-shadow:0 2px 10px rgba(0,0,0,.35)';
  panel.innerHTML='<div style="display:flex;align-items:center;gap:8px">'+
    '<span style="font-weight:600">\u8f6c\u6362\u961f\u5217</span>'+
    '<span id="asQCount" style="opacity:.6;font-size:12px"></span>'+
    '<span id="asQFold" style="cursor:pointer;opacity:.7;padding:0 4px" title="\u6298\u53e0/\u5c55\u5f00">\u25be</span>'+
    '<span id="asQClear" style="cursor:pointer;font-size:12px;color:#e08a8a;margin-left:auto">\u6e05\u7a7a</span></div>'+
    '<div id="asQBody">'+
    '<div id="asQList" style="display:flex;flex-direction:column;gap:6px;min-height:28px;margin-top:8px"></div>'+
    '<div style="display:flex;align-items:center;gap:10px;margin-top:8px">'+
    '<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
    '<span style="font-size:12px;opacity:.6">\u62d6\u52a8\u6392\u5e8f\uff0c\u00d7 \u5220\u9664\uff1b'+
    '\u5b8c\u6210\u81ea\u52a8\u4e0b\u8f7d \u539f\u540d+AudioScore.mid</span></div></div>';
  if(input&&input.parentNode&&input.nextSibling)
    input.parentNode.insertBefore(panel,input.nextSibling);
  else if(btn&&btn.parentNode)btn.parentNode.insertBefore(panel,btn);
  else document.body.appendChild(panel);
  var list=el('asQList'),body=el('asQBody'),fold=el('asQFold');
  try{
    if(localStorage.getItem('as_qfold')==='1'){
      body.style.display='none';fold.textContent='\u25b8';
    }
  }catch(e){}
  fold.onclick=function(){
    var open=body.style.display!=='none';
    body.style.display=open?'none':'';
    fold.textContent=open?'\u25b8':'\u25be';
    try{localStorage.setItem('as_qfold',open?'1':'0');}catch(e){}
  };
  function esc(x){return String(x).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function syncStart(){if(!btn)return;btn.disabled=(Q.length===0);}
  function renderQ(){
    list.innerHTML='';
    Q.forEach(function(it,ix){
      var row=document.createElement('div');
      row.className='asQItem';row.draggable=true;row.dataset.i=ix;
      row.dataset.oname=it.oname||it.name||'';
      row.style.cssText='display:flex;align-items:center;gap:8px;padding:6px 8px;'+
        'border:1px solid #3a3f4a;border-radius:6px;cursor:grab';
      var stt={queued:'\u5f85\u8f6c\u6362',run:'\u8f6c\u6362\u4e2d\u2026',done:'\u5b8c\u6210',err:'\u5931\u8d25'}[it.st]||'';
      row.innerHTML='<span style="opacity:.5">\u2195</span>'+
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+
        esc(it.oname||it.name||'')+'</span>'+
        (it.dl?'<a href="'+it.dl+'" class="asQDl" style="font-size:12px;color:#8ad0a0">\u4e0b\u8f7d</a>':'')+
        '<span style="font-size:12px">'+stt+'</span>'+
        '<span class="asQX" data-x="'+ix+'" style="cursor:pointer;color:#e08a8a;font-weight:700">\u00d7</span>';
      list.appendChild(row);
    });
    el('asQCount').textContent=Q.length?('('+Q.length+')'):'';syncStart();
  }
  el('asQAdd').onclick=function(){
    if(!input||!input.files||!input.files.length){toast('\u8bf7\u5148\u9009\u62e9\u6587\u4ef6');return;}
    for(var k=0;k<input.files.length;k++)
      Q.push({file:input.files[k],name:input.files[k].name,
              oname:input.files[k].name,size:input.files[k].size,st:'queued',dl:''});
    try{input.value='';}catch(e){}
    renderQ();
  };
  list.addEventListener('click',function(e){
    var x=e.target.closest&&e.target.closest('.asQX');if(!x)return;
    Q.splice(+x.dataset.x,1);renderQ();});
  el('asQClear').onclick=function(){if(!busy)Q=[];renderQ();};
  list.addEventListener('dragstart',function(e){
    var it=e.target.closest&&e.target.closest('.asQItem');if(!it)return;
    dragIdx=+it.dataset.i;});
  list.addEventListener('dragover',function(e){e.preventDefault();});
  list.addEventListener('drop',function(e){
    e.preventDefault();
    var it=e.target.closest&&e.target.closest('.asQItem');if(!it||dragIdx<0)return;
    var to=+it.dataset.i;if(to===dragIdx)return;
    var m=Q.splice(dragIdx,1)[0];Q.splice(to,0,m);dragIdx=-1;renderQ();});
  function setFiles(f){
    try{var dt=new DataTransfer();dt.items.add(f);input.files=dt.files;return true;}
    catch(e){return false;}
  }
  function waitNewId(prev,cb){
    var t0=Date.now();
    var iv=setInterval(function(){
      var cur=null;try{cur=localStorage.getItem('as_last_job');}catch(e){}
      if(cur&&cur!==prev){clearInterval(iv);cb(cur);return;}
      if(Date.now()-t0>15000){clearInterval(iv);cb(null);}},300);}
  function pollJob(id,cb){
    var iv=setInterval(function(){
      fetch('/api/jobs/'+id).then(function(r){return r.ok?r.json():null;})
      .then(function(j){
        if(!j)return;
        if(j.status==='done'||j.status==='error'){clearInterval(iv);cb(j);}}).catch(function(){});
    },2000);}
  function runQueue(){
    if(busy)return;busy=true;renderQ();var ix=0;
    function next(){
      if(ix>=Q.length){busy=false;renderQ();toast('\u961f\u5217\u5168\u90e8\u5b8c\u6210');return;}
      var it=Q[ix];it.st='run';it.dl='';renderQ();
      var prev=null;try{prev=localStorage.getItem('as_last_job');}catch(e){}
      if(!input||!setFiles(it.file)){it.st='err';renderQ();ix++;setTimeout(next,300);return;}
      try{localStorage.setItem('as_last_name',it.oname||it.name||'');}catch(e){}
      autoPass=true;btn.click();setTimeout(function(){autoPass=false;},0);
      waitNewId(prev,function(id){
        if(!id){it.st='err';renderQ();ix++;setTimeout(next,500);return;}
        pollJob(id,function(j){
          if(j.status==='done'){it.st='done';it.dl=j.download_url||'';}else{it.st='err';}
          renderQ();ix++;setTimeout(next,600);});});}
    next();}
  document.addEventListener('click',function(e){
    if(!btn)return;
    var t=e.target;
    if(!(t===btn||(btn.contains&&btn.contains(t))))return;
    if(autoPass){autoPass=false;return;}
    e.preventDefault();e.stopPropagation();
    if(busy){toast('\u961f\u5217\u8f6c\u6362\u4e2d');return;}
    if(Q.length===0){toast('\u8bf7\u5148\u52a0\u5165\u961f\u5217');return;}
    runQueue();},true);
})();
</script>"""
QUEUE = QUEUE.replace("__PPS__", FULL_PPS)

def splice(text, marker, new_block):
    i = text.find(marker)
    if i < 0:
        return text, False
    start = text.rfind("<script>", 0, i)
    end = text.find("</script>", i)
    if start < 0 or end < 0:
        return text, False
    return text[:start] + new_block + text[end + 9:], True

s2, did = splice(s, "asQAdd", QUEUE)
if did:
    s = s2; ok.append("queue v3: sticky + top placement + fold")
elif "asQAdd" not in s and "</body>" in s:
    s = s.replace("</body>", QUEUE + "\n</body>", 1)
    ok.append("queue v3 injected fresh")
else:
    fail.append("queue v3 splice failed")

HP.write_text(s, encoding="utf-8")

print()
print("==== QUEUE MOVE RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("===========================")
print("  markers: asQAdd=%s fold=%s sticky=%s" % (
    "asQAdd" in s, "asQFold" in s, "position:sticky" in s))
