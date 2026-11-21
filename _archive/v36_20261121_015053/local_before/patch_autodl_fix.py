# -*- coding: utf-8 -*-
"""Autodl fix: field-name fallback + refetch fallback + banner auto-download
+ toast feedback + dedupe + console debug log."""
from pathlib import Path
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
ok, fail = [], []

FULL_PPS = ",".join("'pp%d'" % k for k in range(1, 17))

def splice(text, marker, new_block):
    i = text.find(marker)
    if i < 0:
        return text, False
    start = text.rfind("<script>", 0, i)
    end = text.find("</script>", i)
    if start < 0 or end < 0:
        return text, False
    return text[:start] + new_block + text[end + 9:], True

# ---------- shared JS helpers ----------
HELPERS = r"""
  function DLURL(j){
    if(!j)return '';
    var cands=[j.download_url,j.download,j.file_url,j.file,j.url,
               j.midi,j.midi_url,j.result_url,j.result];
    for(var i=0;i<cands.length;i++)
      if(typeof cands[i]==='string'&&cands[i])return cands[i];
    return '';
  }
  function outName(on){
    var b=(on||'').replace(/\.[^.]+$/,'');
    if(!b)b='output';
    if(/audioscore$/i.test(b))return b+'.mid';
    return b+'AudioScore.mid';
  }
  function saveBlob(url,fname,cb){
    fetch(url).then(function(r){return r.blob();}).then(function(bl){
      var u=URL.createObjectURL(bl);
      var t=document.createElement('a');t.href=u;t.download=fname;
      document.body.appendChild(t);t.click();t.remove();
      setTimeout(function(){URL.revokeObjectURL(u);},4000);
      if(cb)cb(true);
    }).catch(function(){location.href=url;if(cb)cb(false);});
  }
"""

# ---------- banner v3: auto-download when enabled ----------
BANNER = r"""<script>
(function(){
  var KEY='as_last_job';
  var PINK='background:#ffe0e9;color:#8a3a4a;border-bottom:1px solid #f3b9cb';
  var GREEN='background:#e2f7e5;color:#2e6b3e;border-bottom:1px solid #b5e3c0';
  function enabled(){var v;try{v=localStorage.getItem('as_autodl');}catch(e){}
    return v!=='0';}
  __HELPERS__
  try{
    var _f=window.fetch;
    window.fetch=function(u,o){
      return _f(u,o).then(function(r){
        try{
          var s=(typeof u==='string')?u:(u&&u.url)||'';
          if(s.indexOf('/api/jobs')>=0&&o&&(o.method||'GET').toUpperCase()==='POST'){
            r.clone().json().then(function(j){
              var id=j&&(j.id||j.job_id);
              if(id)localStorage.setItem(KEY,id);
            }).catch(function(){});
            try{
              var fi=document.querySelector('input[type="file"]');
              if(fi&&fi.files&&fi.files[0])
                localStorage.setItem('as_last_name',fi.files[0].name);
            }catch(e){}
          }
        }catch(e){}
        return r;
      });
    };
  }catch(e){}
  function $(id){return document.getElementById(id);}
  function banner(style){
    var b=$('as_resume_bar');
    if(!b){b=document.createElement('div');b.id='as_resume_bar';
      b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;padding:8px 14px;font-size:14px;'+(style||PINK);
      document.body.appendChild(b);}
    return b;
  }
  function clearAll(){try{localStorage.removeItem(KEY);}catch(e){}var b=$('as_resume_bar');if(b)b.remove();}
  function closeBtn(b){var x=document.createElement('span');x.textContent='\u5173\u95ed';
    x.style.cssText='cursor:pointer;opacity:.6;margin-left:auto';x.onclick=clearAll;b.appendChild(x);}
  function poll(id){
    var b=banner();closeBtn(b);
    var t=setInterval(function(){
      fetch('/api/jobs/'+id).then(function(r){
        if(r.status===404){clearInterval(t);clearAll();
          var bb=banner();bb.textContent='\u670d\u52a1\u5df2\u91cd\u542f\uff0c\u4e4b\u524d\u7684\u4efb\u52a1\u4e0d\u4fdd\u7559\uff0c\u91cd\u65b0\u63d0\u4ea4\u5373\u53ef';
          closeBtn(bb);setTimeout(function(){var x=$('as_resume_bar');
            if(x&&x.textContent.indexOf('\u4e0d\u4fdd\u7559')>=0)x.remove();},6000);return null;}
        return r.json();
      }).then(function(j){
        if(!j)return;
        if(j.status==='done'){clearInterval(t);clearAll();
          var url=DLURL(j);
          console.log('AS banner job:',j);
          var nm=null;try{nm=localStorage.getItem('as_last_name');}catch(e){}
          if(enabled()&&url){
            saveBlob(url,outName(nm),function(good){
              var bb=banner(GREEN);
              bb.textContent=good?('\u5df2\u81ea\u52a8\u4e0b\u8f7d '+outName(nm)):
                '\u4e0b\u8f7d\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u70b9\u94fe\u63a5';
              closeBtn(bb);
              setTimeout(function(){var x=$('as_resume_bar');
                if(x&&x.textContent.indexOf('\u4e0b\u8f7d')>=0)x.remove();},8000);
            });
          }else{
            var bb=banner(GREEN);
            var lk=document.createElement('a');lk.href=url||'#';
            lk.textContent='\u4efb\u52a1\u5b8c\u6210\uff0c\u70b9\u51fb\u4e0b\u8f7d';
            lk.onclick=function(ev){ev.preventDefault();saveBlob(url,outName(nm));};
            bb.appendChild(lk);closeBtn(bb);
          }
          return;}
        if(j.status==='error'){clearInterval(t);clearAll();
          var eb=banner();eb.textContent='\u4efb\u52a1\u5931\u8d25\uff0c\u8be6\u89c1\u670d\u52a1\u7aef\u65e5\u5fd7';closeBtn(eb);return;}
      }).catch(function(){});
    },2000);
  }
  function boot(){var id=null;try{id=localStorage.getItem(KEY);}catch(e){}if(id)poll(id);}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}
})();
</script>"""
BANNER = BANNER.replace("__HELPERS__", HELPERS)
s2, did = splice(s, "as_resume_bar", BANNER)
if did:
    s = s2; ok.append("banner v3: auto-download + field fallback")
else:
    fail.append("banner splice failed")

# ---------- queue v4: store jid + field fallback ----------
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
  __HELPERS__
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
    '<span id="asQFold" style="cursor:pointer;opacity:.7;padding:0 4px">\u25be</span>'+
    '<span id="asQClear" style="cursor:pointer;font-size:12px;color:#e08a8a;margin-left:auto">\u6e05\u7a7a</span></div>'+
    '<div id="asQBody">'+
    '<div id="asQList" style="display:flex;flex-direction:column;gap:6px;min-height:28px;margin-top:8px"></div>'+
    '<div style="display:flex;align-items:center;gap:10px;margin-top:8px">'+
    '<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
    '<span style="font-size:12px;opacity:.6">\u5b8c\u6210\u81ea\u52a8\u4e0b\u8f7d \u539f\u540d+AudioScore.mid</span></div></div>';
  if(input&&input.parentNode&&input.nextSibling)
    input.parentNode.insertBefore(panel,input.nextSibling);
  else if(btn&&btn.parentNode)btn.parentNode.insertBefore(panel,btn);
  else document.body.appendChild(panel);
  var list=el('asQList'),body=el('asQBody'),fold=el('asQFold');
  try{
    if(localStorage.getItem('as_qfold')==='1'){
      body.style.display='none';fold.textContent='\u25b8';}
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
      row.dataset.jid=it.jid||'';
      row.style.cssText='display:flex;align-items:center;gap:8px;padding:6px 8px;'+
        'border:1px solid #3a3f4a;border-radius:6px;cursor:grab';
      var stt={queued:'\u5f85\u8f6c\u6362',run:'\u8f6c\u6362\u4e2d\u2026',done:'\u5b8c\u6210',err:'\u5931\u8d25'}[it.st]||'';
      var nm=esc(outName(it.oname||it.name||''));
      row.innerHTML='<span style="opacity:.5">\u2195</span>'+
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+
        esc(it.oname||it.name||'')+'</span>'+
        (it.dl?'<a href="'+it.dl+'" class="asQDl" style="font-size:12px;color:#8ad0a0">'+
         nm+'</a>':'')+
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
              oname:input.files[k].name,size:input.files[k].size,st:'queued',dl:'',jid:''});
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
      var it=Q[ix];it.st='run';it.dl='';it.jid='';renderQ();
      var prev=null;try{prev=localStorage.getItem('as_last_job');}catch(e){}
      if(!input||!setFiles(it.file)){it.st='err';renderQ();ix++;setTimeout(next,300);return;}
      try{localStorage.setItem('as_last_name',it.oname||it.name||'');}catch(e){}
      autoPass=true;btn.click();setTimeout(function(){autoPass=false;},0);
      waitNewId(prev,function(id){
        if(!id){it.st='err';renderQ();ix++;setTimeout(next,500);return;}
        it.jid=id;
        pollJob(id,function(j){
          console.log('AS queue job:',id,j);
          if(j.status==='done'){
            it.st='done';it.dl=DLURL(j);
            if(!it.dl)toast('\u5b8c\u6210\u4f46\u672a\u8bc6\u522b\u4e0b\u8f7d\u5730\u5740\uff0c\u8bf7\u628aF12\u63a7\u5236\u53f0\u91cc AS queue job \u4e00\u884c\u53d1\u7ed9\u52a9\u624b');
          }else{it.st='err';}
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
QUEUE = QUEUE.replace("__PPS__", FULL_PPS).replace("__HELPERS__", HELPERS)
s2, did = splice(s, "asQAdd", QUEUE)
if did:
    s = s2; ok.append("queue v4: jid + field fallback + link shows target filename")
else:
    fail.append("queue splice failed")

# ---------- autodl v3: dedupe by jid + refetch fallback + toast ----------
AUTO = r"""<script>
(function(){
  var KEY='as_autodl';
  function enabled(){var v;try{v=localStorage.getItem(KEY);}catch(e){}return v!=='0';}
  __HELPERS__
  function toast(msg){
    var t=document.getElementById('asToast');
    if(t){t.textContent=msg;t.style.opacity='1';
      clearTimeout(t.__h);t.__h=setTimeout(function(){t.style.opacity='0';},3200);}
  }
  var done=new Set();
  function rowName(r){
    if(r&&r.dataset&&r.dataset.oname)return r.dataset.oname;
    var n=null;try{n=localStorage.getItem('as_last_name');}catch(e){}
    return n||'';
  }
  var lab=document.createElement('label');
  lab.style.cssText='display:inline-flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;margin-top:8px';
  var cb=document.createElement('input');cb.type='checkbox';cb.checked=enabled();
  cb.onchange=function(){try{localStorage.setItem(KEY,cb.checked?'1':'0');}catch(e){}};
  lab.appendChild(cb);
  lab.appendChild(document.createTextNode('\u5b8c\u6210\u540e\u81ea\u52a8\u4e0b\u8f7d\uff08\u539f\u540d+AudioScore.mid\uff09'));
  var panel=document.getElementById('asQueue');
  if(panel)panel.appendChild(lab);else document.body.appendChild(lab);
  document.addEventListener('click',function(e){
    var a=e.target.closest&&e.target.closest('.asQDl');
    if(!a)return;
    e.preventDefault();
    saveBlob(a.getAttribute('href'),outName(rowName(a.closest('.asQItem'))));
  });
  var list=document.getElementById('asQList');
  if(!list)return;
  function tryDl(r,jid,url,oname){
    var key=jid||oname;
    if(done.has(key))return;
    if(url){
      done.add(key);
      saveBlob(url,outName(oname),function(good){
        toast(good?('\u5df2\u81ea\u52a8\u4e0b\u8f7d '+outName(oname)):
          '\u81ea\u52a8\u4e0b\u8f7d\u5931\u8d25\uff0c\u8bf7\u70b9\u6761\u76ee\u91cc\u7684\u4e0b\u8f7d\u94fe\u63a5');
      });
    }else if(jid){
      fetch('/api/jobs/'+jid).then(function(x){return x.json();}).then(function(j){
        var u=DLURL(j);
        if(u){tryDl(r,jid,u,oname);}
        else{toast('\u672a\u627e\u5230\u4e0b\u8f7d\u5730\u5740\uff0c\u628aF12\u63a7\u5236\u53f0 AS queue job \u53d1\u7ed9\u52a9\u624b');}
      }).catch(function(){});
    }
  }
  var mo=new MutationObserver(function(){
    if(!enabled())return;
    list.querySelectorAll('.asQItem').forEach(function(r){
      var a=r.querySelector('a.asQDl');
      if(a&&r.textContent.indexOf('\u5b8c\u6210')>=0)
        tryDl(r,r.dataset.jid||'',a.getAttribute('href'),rowName(r));
    });
  });
  mo.observe(list,{childList:true,subtree:true,characterData:true});
})();
</script>"""
AUTO = AUTO.replace("__HELPERS__", HELPERS)
s2, did = splice(s, "as_autodl", AUTO)
if did:
    s = s2; ok.append("autodl v3: dedupe + refetch fallback + toast")
else:
    fail.append("autodl splice failed")

HP.write_text(s, encoding="utf-8")

print()
print("==== AUTODL FIX RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("============================")
print("  markers: jid=%s DLURL=%s banner-dl=%s" % (
    "dataset.jid" in s, "function DLURL" in s,
    s.count("saveBlob")))
py_compile
