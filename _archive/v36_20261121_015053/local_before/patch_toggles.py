# -*- coding: utf-8 -*-
"""Toggles + upgraded fit-tempo/meter + auto-download. Self-healing, idempotent."""
from pathlib import Path
import re
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")

# ---------- 1. ensure checkboxes pp7-pp16 ----------
LBL = {
 7:  "\u8282\u62cd\u7f51\u683c\u91cf\u5316\uff08Quantize\uff09",
 8:  "\u58f0\u90e8\u5206\u79bb\uff08Voice split\uff09",
 9:  "\u8282\u62cd\u4e92\u89e3\uff08Fit\u2194Tempo\uff09",
 10: "\u62cd\u53f7\u8bc6\u522b\uff08Meter\uff09",
 11: "\u9759\u97f3\u7559\u767d\uff08Silence rest\uff09",
 12: "\u8d77\u97f3\u7cbe\u5316\uff08Onset snap\uff09",
 13: "\u8870\u51cf\u65f6\u503c\uff08Decay aware\uff09",
 14: "\u52a8\u6001\u9608\u503c\uff08Dyn thresh\uff09",
 15: "\u65f6\u503c\u89c4\u6574\uff08Dur norm\uff09",
 16: "DTW \u5bf9\u9f50\u8bca\u65ad\uff08DTW diag\uff09",
}
missing = [k for k in range(7, 17) if 'id="pp%d"' % k not in s]
if not missing:
    ok.append("html: pp7-16 [SKIP all present]")
else:
    last = None
    for m in re.finditer(r'<input type="checkbox" id="pp\d+">.*?</div>', s, re.S):
        last = m
    if last:
        block = "".join('\n<div class="opt"><input type="checkbox" id="pp%d">'
                        '<label>%s</label></div>' % (k, LBL[k]) for k in missing)
        s = s[:last.end()] + block + s[last.end():]
        ok.append("html: added pp%s" % ",".join(str(k) for k in missing))
    else:
        fail.append("html: no pp checkbox anchor found")

# ---------- 2. _OF flags map ----------
FLAGS = {7: "quant", 8: "split", 9: "fit", 10: "meter", 11: "rest",
         12: "onsnap", 13: "decay", 14: "dyn", 15: "dur", 16: "dtw"}
m = re.search(r"_OF\s*=\s*\{", s)
if not m:
    fail.append("html: _OF map not found")
else:
    end = s.index("}", m.end())
    inner = s[m.end():end]
    add = ["pp%d: '%s'" % (k, v) for k, v in FLAGS.items()
           if not re.search(r"pp%d\s*:" % k, inner)]
    if add:
        s = s[:end] + ("," if inner.strip() else "") + ", ".join(add) + s[end:]
        ok.append("html: _OF + %d flags" % len(add))
    else:
        ok.append("html: _OF [SKIP all present]")

# ---------- 3. PPS persistence ----------
FULL_PPS = ",".join("'pp%d'" % k for k in range(1, 17))
s2, n = re.subn(r"(var\s+PPS\s*=\s*)\[[^\]]*\]",
                lambda mm: mm.group(1) + "[" + FULL_PPS + "]", s)
if n:
    s = s2; ok.append("html: PPS persistence -> pp1-16")
else:
    fail.append("html: PPS array not found (injected with queue below)")

# ---------- 4. banner (if missing) ----------
BANNER = r"""<script>
(function(){
  var KEY='as_last_job';
  var PINK='background:#ffe0e9;color:#8a3a4a;border-bottom:1px solid #f3b9cb';
  var GREEN='background:#e2f7e5;color:#2e6b3e;border-bottom:1px solid #b5e3c0';
  try{
    var _f=window.fetch;
    window.fetch=function(u,o){
      return _f(u,o).then(function(r){
        try{
          var s=(typeof u==='string')?u:(u&&u.url)||'';
          if(s.indexOf('/api/jobs')>=0&&o&&(o.method||'GET').toUpperCase()==='POST'){
            r.clone().json().then(function(j){
              var id=j&&(j.id||j.job_id); if(id) localStorage.setItem(KEY,id);
            }).catch(function(){});
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
          var bb=banner(GREEN);
          var lk=document.createElement('a');lk.href=j.download_url||'#';
          lk.textContent='\u4efb\u52a1\u5b8c\u6210\uff0c\u70b9\u51fb\u4e0b\u8f7d';
          bb.appendChild(lk);closeBtn(bb);return;}
        if(j.status==='error'){clearInterval(t);clearAll();
          var eb=banner();eb.textContent='\u4efb\u52a1\u5931\u8d25\uff0c\u8be6\u89c1\u670d\u52a1\u7aef\u65e5\u5fd7';closeBtn(eb);return;}
      }).catch(function(){});
    },2000);
  }
  function boot(){var id=null;try{id=localStorage.getItem(KEY);}catch(e){}if(id)poll(id);}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}
})();
</script>"""
if "as_resume_bar" in s:
    ok.append("html: banner [SKIP present]")
elif "</body>" in s:
    s = s.replace("</body>", BANNER + "\n</body>", 1)
    ok.append("html: banner injected")

# ---------- 5. queue script (if missing) ----------
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
  panel.style.cssText='border:1px solid #3a3f4a;border-radius:8px;padding:10px 12px;margin:12px 0';
  panel.innerHTML='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'+
    '<span style="font-weight:600">\u8f6c\u6362\u961f\u5217</span>'+
    '<span id="asQCount" style="opacity:.6;font-size:12px"></span>'+
    '<span id="asQClear" style="margin-left:auto;cursor:pointer;font-size:12px;color:#e08a8a">\u6e05\u7a7a</span></div>'+
    '<div id="asQList" style="display:flex;flex-direction:column;gap:6px;min-height:34px"></div>'+
    '<div style="display:flex;align-items:center;gap:10px;margin-top:8px">'+
    '<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
    '<span style="font-size:12px;opacity:.6">\u62d6\u52a8\u6392\u5e8f\uff0c\u00d7 \u5220\u9664</span></div>';
  if(btn&&btn.parentNode)btn.parentNode.insertBefore(panel,btn);
  else if(input&&input.parentNode)input.parentNode.insertBefore(panel,input.nextSibling);
  else document.body.appendChild(panel);
  var list=el('asQList');
  function esc(x){return String(x).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function syncStart(){if(!btn)return;btn.disabled=(Q.length===0);}
  function renderQ(){
    list.innerHTML='';
    Q.forEach(function(it,ix){
      var row=document.createElement('div');
      row.className='asQItem';row.draggable=true;row.dataset.i=ix;
      row.style.cssText='display:flex;align-items:center;gap:8px;padding:6px 8px;'+
        'border:1px solid #3a3f4a;border-radius:6px;cursor:grab';
      var stt={queued:'\u5f85\u8f6c\u6362',run:'\u8f6c\u6362\u4e2d\u2026',done:'\u5b8c\u6210',err:'\u5931\u8d25'}[it.st]||'';
      row.innerHTML='<span style="opacity:.5">\u2195</span>'+
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(it.name)+'</span>'+
        (it.dl?'<a href="'+it.dl+'" style="font-size:12px;color:#8ad0a0">\u4e0b\u8f7d</a>':'')+
        '<span style="font-size:12px">'+stt+'</span>'+
        '<span class="asQX" data-x="'+ix+'" style="cursor:pointer;color:#e08a8a;font-weight:700">\u00d7</span>';
      list.appendChild(row);
    });
    el('asQCount').textContent=Q.length?('('+Q.length+')'):'';syncStart();
  }
  el('asQAdd').onclick=function(){
    if(!input||!input.files||!input.files.length){toast('\u8bf7\u5148\u9009\u62e9\u6587\u4ef6');return;}
    for(var k=0;k<input.files.length;k++)
      Q.push({file:input.files[k],name:input.files[k].name,size:input.files[k].size,st:'queued',dl:''});
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
if "asQAdd" in s:
    ok.append("html: queue [SKIP present]")
elif "</body>" in s:
    s = s.replace("</body>", QUEUE + "\n</body>", 1)
    ok.append("html: queue injected")

# ---------- 6. auto-download supplement ----------
AUTO = r"""<script>
(function(){
  var KEY='as_autodl';
  function enabled(){var v;try{v=localStorage.getItem(KEY);}catch(e){}return v!=='0';}
  var lab=document.createElement('label');
  lab.style.cssText='display:inline-flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;margin-top:8px';
  var cb=document.createElement('input');cb.type='checkbox';cb.checked=enabled();
  cb.onchange=function(){try{localStorage.setItem(KEY,cb.checked?'1':'0');}catch(e){}};
  lab.appendChild(cb);
  lab.appendChild(document.createTextNode('\u5b8c\u6210\u540e\u81ea\u52a8\u4e0b\u8f7d'));
  var panel=document.getElementById('asQueue');
  if(panel)panel.appendChild(lab);else document.body.appendChild(lab);
  var list=document.getElementById('asQList');
  if(!list)return;
  var mo=new MutationObserver(function(){
    if(!enabled())return;
    list.querySelectorAll('.asQItem').forEach(function(r){
      if(r.dataset.adl)return;
      var a=r.querySelector('a[href]');
      if(a&&r.textContent.indexOf('\u5b8c\u6210')>=0){
        r.dataset.adl='1';
        fetch(a.getAttribute('href')).then(function(x){return x.blob();})
        .then(function(bl){
          var u=URL.createObjectURL(bl);
          var t=document.createElement('a');
          t.href=u;t.download=(a.href.split('/').pop()||'output.mid').split('?')[0];
          document.body.appendChild(t);t.click();t.remove();
          setTimeout(function(){URL.revokeObjectURL(u);},4000);
        }).catch(function(){});
      }
    });
  });
  mo.observe(list,{childList:true,subtree:true,characterData:true});
})();
</script>"""
if "as_autodl" in s:
    ok.append("html: auto-download [SKIP present]")
elif "</body>" in s:
    s = s.replace("</body>", AUTO + "\n</body>", 1)
    ok.append("html: auto-download injected")

# ---------- 7. toggle buttons ----------
TOG = r"""<script>
(function(){
  function el(id){return document.getElementById(id);}
  function toast(msg){
    var t=el('asToast');
    if(!t){t=document.createElement('div');t.id='asToast';
      t.style.cssText='position:fixed;bottom:18px;left:50%;transform:translateX(-50%);'+
        'background:#333;color:#fff;padding:8px 16px;border-radius:6px;font-size:13px;z-index:10000';
      document.body.appendChild(t);}
    t.textContent=msg;t.style.opacity='1';
    clearTimeout(t.__h);t.__h=setTimeout(function(){t.style.opacity='0';},3200);
  }
  var defs=[
    {pp:'pp9',label:'\u6d4b\u901f\u6c42\u89e3\uff08\u5951\u5408\u5ea6\u2194\u901f\u5ea6\uff09',
     desc:'\u8f6c\u6362\u65f6\u626b\u63cf\u5019\u9009 BPM\uff08\u542b\u500d\u9891\u6821\u9a8c\u4e0e IOI \u64ad\u79cd\uff09\uff0c\u53d6\u8d34\u5408\u7f51\u683c\u5ea6\u6700\u9ad8\u7684\u901f\u5ea6\uff1b\u7ed3\u679c\u89c1\u65e5\u5fd7 fit-tempo \u884c'},
    {pp:'pp10',label:'\u62cd\u53f7\u8bc6\u522b\uff08\u5f3a\u62cd\u4f4d\u5206\u6790\uff09',
     desc:'\u6309\u5f3a\u5ea6\u52a0\u6743\u6298\u53e0 2/3/4/6 \u62cd\uff0c\u5f3a\u62cd\u5bf9\u6bd4\u5ea6\u6700\u9ad8\u8005\u5199\u5165 MIDI \u62cd\u53f7\uff1b\u7ed3\u679c\u89c1\u65e5\u5fd7 meter \u884c'}
  ];
  var box=document.createElement('div');box.id='asToggles';
  box.style.cssText='display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0';
  function paint(b,d){
    var cb=el(d.pp),on=cb&&cb.checked;
    b.style.background=on?'rgba(138,180,224,.25)':'rgba(255,255,255,.06)';
    b.style.borderColor=on?'#8ab4e0':'#3a3f4a';
    b.style.fontWeight=on?'700':'400';
    b.textContent=(on?'\u2713 ':'')+d.label;
  }
  defs.forEach(function(d){
    var b=document.createElement('button');
    b.style.cssText='cursor:pointer;padding:6px 12px;border-radius:6px;'+
      'border:1px solid #3a3f4a;color:inherit;font-size:13px';
    b.onclick=function(){
      var cb=el(d.pp);
      if(!cb){toast('\u5f00\u5173 '+d.pp+' \u4e0d\u5b58\u5728\uff0c\u5148\u8dd1\u57fa\u7840\u8865\u4e01');return;}
      cb.checked=!cb.checked;
      cb.dispatchEvent(new Event('change'));
      paint(b,d);
      toast(cb.checked?('\u5df2\u5f00\u542f\uff1a'+d.desc):('\u5df2\u5173\u95ed\uff1a'+d.label));
    };
    b.__paint=function(){paint(b,d);};
    box.appendChild(b);d.btn=b;
  });
  var hint=document.createElement('span');
  hint.style.cssText='font-size:12px;opacity:.55';
  hint.textContent='\u7ed3\u679c\u5728\u670d\u52a1\u5668\u65e5\u5fd7\uff1afit-tempo / meter \u884c\uff0c\u5e76\u5199\u5165 .post.json';
  box.appendChild(hint);
  var anchor=el('asQueue');
  if(anchor){anchor.parentNode.insertBefore(box,anchor);}
  else{
    var input=document.querySelector('input[type="file"]');
    if(input&&input.parentNode&&input.nextSibling)input.parentNode.insertBefore(box,input.nextSibling);
    else document.body.appendChild(box);
  }
  defs.forEach(function(d){d.btn.__paint();});
  setInterval(function(){defs.forEach(function(d){d.btn.__paint();});},1500);
})();
</script>"""
if "asToggles" in s:
    ok.append("html: toggles [SKIP present]")
elif "</body>" in s:
    s = s.replace("</body>", TOG + "\n</body>", 1)
    ok.append("html: toggles injected")
HP.write_text(s, encoding="utf-8")

# ---------- 8. engine flag sets + bpm ----------
ENG = ROOT / "server" / "engines" / "muscriptor.py"
es = ENG.read_text(encoding="utf-8")
NEW_SET = ("{'dedup', 'frag', 'vel', 'harmonic', 'quant', 'split', 'fit', 'meter', "
           "'rest', 'onsnap', 'decay', 'dyn', 'dur', 'dtw'}")
pat = re.compile(r"\{'dedup'(?:\s*,\s*'[a-z]+')*\s*\}")
changed = [0]
def _sub(mm):
    if "dtw" in mm.group(0):
        return mm.group(0)
    changed[0] += 1
    return NEW_SET
es = pat.sub(_sub, es)
if changed[0]:
    ok.append("engine: pipeline sets updated x%d" % changed[0])
else:
    ok.append("engine: pipeline sets [SKIP present]")
if "bpm=bpm)" in es:
    ok.append("engine: bpm passing [SKIP present]")
elif "flags=post)" in es:
    es = es.replace("flags=post)", "flags=post, bpm=bpm)", 1)
    ok.append("engine: main bpm pass added")
ENG.write_text(es, encoding="utf-8")

# ---------- 9. postprocess.py rewrite (upgraded fit/meter + sidecar) ----------
PP = ROOT / "server" / "engines" / "postprocess.py"
PP.write_text('''import json
import logging
from pathlib import Path

import numpy as np
import pretty_midi

log = logging.getLogger("muscriptor.post")

_RANGES = {
    "piano": (21, 108), "chromperc": (48, 96), "organ": (21, 96),
    "guitar": (40, 93), "bass": (28, 72), "strings": (36, 103),
    "brass": (46, 100), "sax": (48, 96), "pipe": (48, 100),
    "synth": (21, 108), "drums": None,
}
_PROG = {"piano": 0, "guitar": 24, "bass": 33, "strings": 48,
         "brass": 56, "sax": 65, "pipe": 73, "organ": 16}
_VALID = ("dedup", "frag", "vel", "harmonic", "quant", "split", "fit", "meter",
          "rest", "onsnap", "decay", "dyn", "dur", "dtw")


def _family(prog, is_drum):
    if is_drum:
        return "drums"
    if prog < 8:
        return "piano"
    if prog < 16:
        return "chromperc"
    if prog < 24:
        return "organ"
    if prog < 32:
        return "guitar"
    if prog < 40:
        return "bass"
    if prog < 56:
        return "strings"
    if prog < 64:
        return "brass"
    if prog < 72:
        return "sax"
    if prog < 80:
        return "pipe"
    return "synth"


def _merge_fragments(notes, merge_gap, min_len):
    notes = sorted(notes, key=lambda n: n.start)
    out = []
    for n in notes:
        if out and out[-1].pitch == n.pitch and n.start - out[-1].end <= merge_gap:
            out[-1].end = max(out[-1].end, n.end)
            continue
        out.append(n)
    return [n for n in out if (n.end - n.start) >= min_len]


def _range_report(inst):
    fam = _family(inst.program, inst.is_drum)
    rng = _RANGES.get(fam)
    if not rng:
        return fam, 0, 0
    lo, hi = rng
    total = len(inst.notes)
    bad = sum(1 for n in inst.notes if n.pitch < lo or n.pitch > hi)
    return fam, bad, total


def _flags(post, cfg):
    if post is None:
        fl = set()
        for k in _VALID:
            if cfg.get(k, False):
                fl.add(k)
        if cfg.get("dedup", True):
            fl.add("dedup")
        if cfg.get("frag", True):
            fl.add("frag")
        return fl
    s = str(post).strip().lower()
    if s in ("", "0", "off", "false", "none"):
        return set()
    return {x.strip() for x in s.split(",") if x.strip() in _VALID}


def _load_audio(audio_path, parent_log, tag):
    try:
        import librosa
    except Exception as e:
        parent_log.warning("%s: librosa unavailable (%s)", tag, e)
        return None, None
    try:
        return librosa.load(str(audio_path), mono=True, sr=22050)
    except Exception as e:
        parent_log.warning("%s: audio load failed (%s)", tag, e)
        return None, None


def _rebuild_velocity(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "velocity rebuild")
    if y is None:
        return
    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    if rms.size == 0:
        return
    lr = np.log10(rms + 1e-8)
    lo, hi = np.percentile(lr, 5), np.percentile(lr, 95)
    span = max(float(hi - lo), 1e-6)
    fps = sr / hop
    cnt = 0
    for inst in pm.instruments:
        for n in inst.notes:
            a = max(int(n.start * fps), 0)
            b = min(int(n.end * fps), rms.size - 1)
            if a >= rms.size:
                a = rms.size - 1
            if b < a:
                b = a
            v = int(20 + 107 * min(1.0, max(0.0, (float(lr[a:b + 1].mean()) - lo) / span)))
            n.velocity = max(20, min(127, v))
            cnt += 1
    parent_log.info("velocity rebuild: %d notes re-velocitied", cnt)


def _harmonic_reassign(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "harmonic reassign")
    if y is None:
        return
    mel = [i for i in pm.instruments if not i.is_drum and len(i.notes) >= 8]
    if len(mel) < 2:
        parent_log.info("harmonic reassign: <2 melodic tracks - skipped")
        return
    hop = 512
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)) + 1e-9
    fps = sr / hop

    def prof(inst):
        vecs = []
        for n in inst.notes[:80]:
            a = int(n.start * fps)
            b = max(int(n.end * fps), a + 1)
            seg = S[:, a:min(b, S.shape[1])]
            if seg.size:
                vecs.append(seg.mean(axis=1))
        if not vecs:
            return None
        v = np.mean(vecs, axis=0)
        return v / (np.linalg.norm(v) + 1e-9)

    profiles = {id(i): prof(i) for i in mel}
    moved = 0
    for inst in mel:
        if profiles[id(inst)] is None:
            continue
        for n in list(inst.notes):
            a = int(n.start * fps)
            b = max(int(n.end * fps), a + 1)
            seg = S[:, a:min(b, S.shape[1])]
            if not seg.size:
                continue
            v = seg.mean(axis=1)
            v /= (np.linalg.norm(v) + 1e-9)
            sims = {id(i): float(np.dot(v, profiles[id(i)]))
                    for i in mel if profiles[id(i)] is not None}
            best = max(sims, key=sims.get)
            if best != id(inst) and sims[best] - sims[id(inst)] > 0.15:
                bi = next(i for i in mel if id(i) == best)
                inst.notes.remove(n)
                bi.notes.append(n)
                moved += 1
    parent_log.info("harmonic reassign: %d notes moved", moved)


def _fit_score(onsets, step):
    a = np.asarray(onsets)
    k = np.round(a / step)
    tol = min(step * 0.25, 0.045)
    return float((np.abs(a - k * step) <= tol).mean())


def _fit_tempo_solve(pm, bpm, parent_log):
    """speed->fit: grid adherence for a given bpm.
    fit->speed: candidates = ui bpm +/-4 fine + octave checks + IOI histogram
    seeds; each scored on 16th and 8th grids; best wins."""
    onsets = [n.start for i in pm.instruments if not i.is_drum for n in i.notes]
    if len(onsets) < 16:
        parent_log.info("fit-tempo: <16 notes - skipped")
        return {"bpm": float(bpm or 0)}
    center = 0.0
    try:
        center = float(bpm or 0)
    except Exception:
        center = 0.0
    cands = set()
    if 30 <= center <= 240:
        cands |= {round(center + k * 0.25, 2) for k in range(-16, 17)}
        cands |= {round(center / 2, 2), round(center * 2, 2)}
    o = np.sort(np.asarray(onsets))
    ioi = np.diff(o)
    ioi = ioi[(ioi > 0.05) & (ioi < 2.0)]
    if ioi.size:
        med = float(np.median(ioi))
        for mult in (0.5, 1.0, 2.0, 4.0):
            b = round(60.0 / (med * mult), 1)
            if 30 <= b <= 240:
                cands.add(b)
    if not cands:
        cands = {round(60.0 + i * 0.5, 1) for i in range(0, 241)}
    cands = {c for c in cands if 30 <= c <= 240}
    ui_fit = _fit_score(onsets, 60.0 / center / 4.0) if center > 0 else 0.0
    best_b, best_f, best_g = center, ui_fit, "16th"
    for c in cands:
        f16 = _fit_score(onsets, 60.0 / c / 4.0)
        f8 = _fit_score(onsets, 60.0 / c / 2.0)
        f, g = f16, "16th"
        if f8 > f16 + 0.03:
            f, g = f8, "8th"
        if f > best_f:
            best_b, best_f, best_g = c, f, g
    parent_log.info("fit-tempo: speed->fit ui_bpm=%.2f fit=%.0f%% | "
                    "fit->speed solved_bpm=%.2f fit=%.0f%% grid=%s cands=%d",
                    center, ui_fit * 100, best_b, best_f * 100, best_g, len(cands))
    return {"bpm": best_b, "ui_bpm": center,
            "ui_fit": round(ui_fit * 100, 1),
            "fit": round(best_f * 100, 1), "grid": best_g}


def _grid_quantize(pm, bpm, parent_log):
    b = 0.0
    try:
        b = float(bpm or 0)
    except Exception:
        b = 0.0
    if b <= 0:
        try:
            b = float(pm.estimate_tempo())
        except Exception:
            b = 0.0
    if b <= 0:
        parent_log.info("grid quantize: no bpm - skipped")
        return
    step = 60.0 / b / 4.0
    moved = 0
    for inst in pm.instruments:
        for n in inst.notes:
            s2 = round(n.start / step) * step
            e2 = round(n.end / step) * step
            if e2 <= s2:
                e2 = s2 + step
            if abs(n.start - s2) > 1e-4 or abs(n.end - e2) > 1e-4:
                n.start = max(0.0, s2)
                n.end = e2
                moved += 1
    parent_log.info("grid quantize: bpm=%.2f step=%dms, %d notes snapped",
                    b, int(step * 1000), moved)


def _detect_meter(pm, bpm, parent_log):
    """velocity-weighted onset envelope folded by 2/3/4/6 beat cycles;
    highest downbeat contrast wins; TimeSignature written into MIDI."""
    b = 0.0
    try:
        b = float(bpm or 0)
    except Exception:
        b = 0.0
    if b <= 0:
        try:
            b = float(pm.estimate_tempo())
        except Exception:
            b = 0.0
    if b <= 0:
        parent_log.info("meter: no bpm - skipped")
        return {"meter": None}
    beat = 60.0 / b
    dur = max((n.end for i in pm.instruments for n in i.notes), default=0.0)
    nb = int(dur / beat)
    if nb < 12:
        parent_log.info("meter: too short (%d beats) - skipped", nb)
        return {"meter": None}
    fps = 100
    T = int(dur * fps) + 1
    env = np.zeros(T)
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            idx = int(n.start * fps)
            if 0 <= idx < T:
                env[idx] += max(0.2, n.velocity / 127.0)
    acc = np.array([env[int(k * beat * fps):int((k + 1) * beat * fps)].sum()
                    for k in range(nb)])
    best_m, best_c = 4, -1.0
    for m in (2, 3, 4, 6):
        if len(acc) < m * 4:
            continue
        prof = np.array([acc[i::m].mean() for i in range(m)])
        rest = prof[1:].mean() if m > 1 else 0.0
        contrast = (prof[0] - rest) / (prof.mean() + 1e-9)
        parent_log.info("meter candidate bar=%d beats: contrast %.3f", m, contrast)
        if contrast > best_c:
            best_m, best_c = m, contrast
    parent_log.info("meter detect: %d/4 (contrast %.3f, bpm %.2f)", best_m, best_c, b)
    try:
        pm.time_signature_changes = [
            pretty_midi.TimeSignature(numerator=best_m, denominator=4, time=0.0)]
    except Exception as e:
        parent_log.warning("meter: write signature failed (%s)", e)
    return {"meter": "%d/4" % best_m, "meter_contrast": round(best_c, 3)}


def _voice_split(pm, parent_log):
    from statistics import median
    added = []
    for inst in list(pm.instruments):
        if inst.is_drum or len(inst.notes) < 24:
            continue
        pitches = [n.pitch for n in inst.notes]
        cut = median(pitches) - 7
        lo = [n for n in inst.notes if n.pitch < cut]
        hi = [n for n in inst.notes if n.pitch >= cut]
        if len(lo) < 8 or len(hi) < 8 or max(pitches) - min(pitches) < 24:
            continue
        inst.notes = hi
        ni = pretty_midi.Instrument(program=inst.program, is_drum=False,
                                    name=((inst.name or "track") + "-low")[:30])
        ni.notes = lo
        added.append(ni)
        parent_log.info("voice split: '%s' -> %d upper + %d lower",
                        inst.name or "track", len(hi), len(lo))
    pm.instruments.extend(added)


def _rest_preserve(pm, parent_log):
    GAP = 0.6
    evs = sorted((n.start, n.end) for i in pm.instruments for n in i.notes)
    if not evs:
        return
    gaps = []
    cur_end = evs[0][1]
    for s2, e2 in evs[1:]:
        if s2 - cur_end >= GAP:
            gaps.append((cur_end, s2))
        cur_end = max(cur_end, e2)
    trimmed = 0
    for inst in pm.instruments:
        for n in inst.notes:
            for gs, ge in gaps:
                if n.start < gs - 0.05 and n.end > gs + 0.05:
                    n.end = gs + 0.05
                    trimmed += 1
                    break
    parent_log.info("rest preserve: %d silence gaps, %d crossing notes trimmed",
                    len(gaps), trimmed)


def _onset_snap(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "onset snap")
    if y is None:
        return
    ons = librosa.onset.onset_detect(y=y, sr=sr, hop_length=512,
                                     units="time", backtrack=False)
    if ons.size == 0:
        return
    ons = np.sort(ons)
    TOL = 0.05
    moved = 0
    for inst in pm.instruments:
        for n in inst.notes:
            j = int(np.searchsorted(ons, n.start))
            cands = []
            if j > 0:
                cands.append(ons[j - 1])
            if j < len(ons):
                cands.append(ons[j])
            if not cands:
                continue
            best = min(cands, key=lambda t: abs(float(t) - n.start))
            if abs(float(best) - n.start) <= TOL:
                dur = n.end - n.start
                n.start = float(best)
                n.end = n.start + dur
                moved += 1
    parent_log.info("onset snap: %d notes aligned (tol %dms)", moved, int(TOL * 1000))


def _decay_aware(pm, parent_log):
    FAST = {"piano", "guitar", "bass", "chromperc"}
    SUST = {"strings", "brass", "sax", "pipe", "organ"}
    capped = merged = 0
    for inst in pm.instruments:
        fam = _family(inst.program, inst.is_drum)
        if fam in FAST:
            durs = sorted((n.end - n.start) for n in inst.notes)
            if len(durs) < 8:
                continue
            med = durs[len(durs) // 2]
            cap = max(med * 2.0, 0.5)
            for n in inst.notes:
                if n.end - n.start > cap:
                    n.end = n.start + cap
                    capped += 1
        elif fam in SUST:
            ns = sorted(inst.notes, key=lambda n: n.start)
            out = []
            for n in ns:
                if out and out[-1].pitch == n.pitch and \\
                        0 <= n.start - out[-1].end <= 0.15:
                    out[-1].end = n.end
                    merged += 1
                    continue
                out.append(n)
            inst.notes = out
    parent_log.info("decay aware: %d capped, %d merged", capped, merged)


def _dyn_threshold(pm, parent_log):
    vels = [n.velocity for i in pm.instruments for n in i.notes]
    if len(vels) < 20:
        return
    lo = float(np.percentile(vels, 10))
    hi = float(np.percentile(vels, 90))
    if hi - lo < 20:
        parent_log.info("dyn thresh: no dynamic layering")
        return
    floor = lo + 0.15 * (hi - lo)
    removed = 0
    for inst in pm.instruments:
        keep = [n for n in inst.notes if n.velocity >= floor]
        removed += len(inst.notes) - len(keep)
        inst.notes = keep
    parent_log.info("dyn thresh: floor=%.0f, %d dropped", floor, removed)


def _duration_normalize(pm, bpm, parent_log):
    b = 0.0
    try:
        b = float(bpm or 0)
    except Exception:
        b = 0.0
    if b <= 0:
        try:
            b = float(pm.estimate_tempo())
        except Exception:
            b = 0.0
    if b <= 0:
        return
    beat = 60.0 / b
    DURS = [beat / 4, beat / 3, beat / 2, beat * 2 / 3, beat,
            beat * 1.5, beat * 2, beat * 3, beat * 4]
    snapped = 0
    for inst in pm.instruments:
        for n in inst.notes:
            d = n.end - n.start
            best = min(DURS, key=lambda x: abs(x - d))
            if d > 0 and abs(best - d) / d < 0.18:
                n.end = n.start + best
                snapped += 1
    parent_log.info("duration norm: %d durations snapped (bpm %.1f)", snapped, b)


def _dtw_diag(pm, audio_path, parent_log):
    y, sr = _load_audio(audio_path, parent_log, "dtw diag")
    if y is None:
        return
    ons = librosa.onset.onset_detect(y=y, sr=sr, hop_length=512,
                                     units="time", backtrack=False)
    starts = sorted(n.start for i in pm.instruments
                    if not i.is_drum for n in i.notes)
    if ons.size < 5 or len(starts) < 5:
        return
    A = np.asarray(ons[:400])
    B = np.asarray(starts[:400])
    n, m = len(A), len(B)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = abs(float(A[i - 1]) - float(B[j - 1]))
            D[i, j] = c + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    devs = []
    i, j = n, m
    while i > 0 and j > 0:
        devs.append(abs(float(A[i - 1]) - float(B[j - 1])))
        step = int(np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]]))
        if step == 0:
            i -= 1; j -= 1
        elif step == 1:
            i -= 1
        else:
            j -= 1
    mean_dev = float(np.mean(devs)) if devs else 0.0
    med_dev = float(np.median(devs)) if devs else 0.0
    parent_log.info("dtw diag: mean=%.0fms median=%.0fms %s",
                    mean_dev * 1000, med_dev * 1000,
                    "(good sync)" if mean_dev < 0.08 else "(sync drift)")


def run_postprocess(mid_path, cfg, parent_log, audio_path=None, flags=None, bpm=None):
    fl = _flags(flags, cfg)
    if not fl:
        parent_log.info("postprocess: OFF (no flags)")
        return
    merge_gap = float(cfg.get("merge_gap", 0.08))
    min_note = float(cfg.get("min_note", 0.06)) if "frag" in fl else 0.0
    iso_min = int(cfg.get("isolated_min_notes", 3))
    range_fix = bool(cfg.get("range_fix", False))

    pm = pretty_midi.PrettyMIDI(str(mid_path))
    log.info("---- postprocess start: flags=%s", ",".join(sorted(fl)))

    for i, inst in enumerate(pm.instruments):
        before = len(inst.notes)
        if "dedup" in fl:
            inst.notes = _merge_fragments(inst.notes, merge_gap, 0.0)
        if min_note > 0:
            inst.notes = [n for n in inst.notes if (n.end - n.start) >= min_note]
        if before != len(inst.notes):
            log.info("track %02d hygiene: %d -> %d notes", i, before, len(inst.notes))

    if "dyn" in fl:
        _dyn_threshold(pm, log)

    res = {}
    eff_bpm = bpm
    if "fit" in fl:
        fit = _fit_tempo_solve(pm, bpm, log)
        eff_bpm = fit.get("bpm", eff_bpm)
        res.update(fit)
    if "onsnap" in fl and audio_path:
        _onset_snap(pm, audio_path, log)
    if "quant" in fl:
        _grid_quantize(pm, eff_bpm, log)
    if "dur" in fl:
        _duration_normalize(pm, eff_bpm, log)
    if "decay" in fl:
        _decay_aware(pm, log)
    if "rest" in fl:
        _rest_preserve(pm, log)
    if "split" in fl:
        _voice_split(pm, log)
    if "meter" in fl:
        res.update(_detect_meter(pm, eff_bpm, log))

    for i, inst in enumerate(pm.instruments):
        fam, bad, total = _range_report(inst)
        if total and bad / total > 0.3:
            log.info("track %02d range WARN: %s %d/%d out of range", i, fam, bad, total)
            if range_fix and fam not in ("piano", "synth", "drums"):
                cands = []
                for f, rng in _RANGES.items():
                    if f == "drums":
                        continue
                    lo, hi = rng
                    cov = sum(1 for n in inst.notes if lo <= n.pitch <= hi)
                    cands.append((cov / total, f))
                cands.sort(reverse=True)
                bc, bf = cands[0]
                if bc > (1 - bad / total) + 0.3 and bf in _PROG:
                    log.info("track %02d range FIX: %s -> %s", i, fam, bf)
                    inst.program = _PROG[bf]

    if "dedup" in fl and len(pm.instruments) > 1:
        dom = max(pm.instruments, key=lambda x: len(x.notes))
        for inst in pm.instruments:
            if inst is dom or inst.is_drum:
                continue
            if 0 < len(inst.notes) < iso_min:
                log.info("isolated track FIX -> dominant track")
                dom.notes.extend(inst.notes)
                inst.notes = []

    pm.instruments = [x for x in pm.instruments if x.notes]

    fams = {_family(x.program, x.is_drum) for x in pm.instruments}
    fams.discard("drums")
    if len(fams) >= 6:
        log.info("coexistence WARN: %d families", len(fams))

    if "harmonic" in fl and audio_path:
        _harmonic_reassign(pm, audio_path, log)
    if "vel" in fl and audio_path:
        _rebuild_velocity(pm, audio_path, log)
    if "dtw" in fl and audio_path:
        _dtw_diag(pm, audio_path, log)

    pm.write(str(mid_path))
    if res:
        try:
            side = Path(str(mid_path)).with_suffix(".post.json")
            side.write_text(json.dumps(res, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            log.info("analysis sidecar -> %s (%s)", side.name, res)
        except Exception as e:
            log.warning("sidecar write failed (%s)", e)
    log.info("---- postprocess done: %d tracks remain", len(pm.instruments))
''', encoding="utf-8")
ok.append("postprocess.py rewritten (upgraded fit/meter + sidecar)")

print()
print("==== TOGGLE PATCH RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("=============================")
py_compile.compile(str(ENG), doraise=True)
py_compile.compile(str(PP), doraise=True)
print("  syntax OK : engine + postprocess")
