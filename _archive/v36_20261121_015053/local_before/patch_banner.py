# -*- coding: utf-8 -*-
"""Restyle resume banner: soft pink, no warning triangle, auto-dismiss lost-task;
also re-apply pp4 zero-install label if it never landed."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
ok, fail = [], []

NEW_SCRIPT = r"""<script>
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
      b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;padding:8px 14px;font-size:14px;display:flex;gap:12px;align-items:center;'+(style||PINK);
      document.body.appendChild(b);}
    return b;
  }
  function clearAll(){try{localStorage.removeItem(KEY);}catch(e){}var b=$('as_resume_bar');if(b)b.remove();}
  function closeBtn(b){var x=document.createElement('span');x.textContent='\u5173\u95ed';
    x.style.cssText='cursor:pointer;opacity:.6;margin-left:auto';x.onclick=clearAll;b.appendChild(x);}
  function poll(id){
    var b=banner();
    b.textContent='\u68c0\u6d4b\u5230\u672a\u5b8c\u6210\u4efb\u52a1 '+id.slice(0,8)+' \uff0c\u6b63\u5728\u6062\u590d\u76d1\u63a7';
    closeBtn(b);
    var t=setInterval(function(){
      fetch('/api/jobs/'+id).then(function(r){
        if(r.status===404){clearInterval(t);clearAll();
          var bb=banner();
          bb.textContent='\u670d\u52a1\u5df2\u91cd\u542f\uff0c\u4e4b\u524d\u7684\u4efb\u52a1\u4e0d\u4fdd\u7559\uff0c\u91cd\u65b0\u63d0\u4ea4\u5373\u53ef';
          closeBtn(bb);
          setTimeout(function(){
            var x=$('as_resume_bar');
            if(x&&x.textContent.indexOf('\u4e0d\u4fdd\u7559')>=0)x.remove();
          },6000);
          return null;}
        return r.json();
      }).then(function(j){
        if(!j)return;
        if(j.status==='done'){clearInterval(t);clearAll();
          var bb=banner(GREEN);
          var lk=document.createElement('a');lk.href=j.download_url||'#';
          lk.textContent='\u4efb\u52a1\u5b8c\u6210\uff0c\u70b9\u51fb\u4e0b\u8f7d';
          lk.style.cssText='color:#2e6b3e;text-decoration:underline;font-weight:600';
          bb.appendChild(lk);closeBtn(bb);
          var pb=$('pbar');if(pb)pb.style.width='100%';return;}
        if(j.status==='error'){clearInterval(t);clearAll();
          var eb=banner();eb.textContent='\u4efb\u52a1\u5931\u8d25\uff0c\u8be6\u89c1\u670d\u52a1\u7aef\u65e5\u5fd7';closeBtn(eb);return;}
        var sm=$('smeta');
        var meta='\u5df2\u7528\u65f6 '+(j.elapsed||0)+'s';
        if(j.engine_line)meta+=' | \u5f15\u64ce: '+String(j.engine_line).slice(0,70);
        if(sm)sm.textContent=meta;
        var pb2=$('pbar');
        if(pb2){var pct=j.status==='running'?Math.min(88,5+83*Math.min(1,(j.elapsed||0)/480)):5;pb2.style.width=pct+'%';}
      }).catch(function(){});
    },2000);
  }
  function boot(){var id=null;try{id=localStorage.getItem(KEY);}catch(e){}if(id)poll(id);}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}
})();
</script>"""

blocks = re.findall(r"<script>.*?</script>", s, re.S)
tgt = [b for b in blocks if "as_last_job" in b]
if tgt:
    s = s.replace(tgt[0], NEW_SCRIPT, 1)
    ok.append("banner script restyled (pink / no triangle / auto-dismiss 6s)")
else:
    fail.append("banner script block not found")

OLD_LBL = "\u97f3\u8272\u9884\u5206\u79bb\uff08Demucs \u5206\u8f68\u8f6c\u5199 Stem split\uff09"
NEW_LBL = ("\u97f3\u8272\u9884\u5206\u79bb\u5206\u8f68\u8f6c\u5199"
           "\uff08\u6709Demucs\u7528ML\uff1b\u65e0Demucs\u81ea\u52a8DSP\uff0c\u96f6\u5b89\u88c5\uff09")
if "\u81ea\u52a8DSP" in s:
    ok.append("pp4 label [SKIP already zero-install text]")
elif OLD_LBL in s:
    s = s.replace(OLD_LBL, NEW_LBL, 1)
    ok.append("pp4 label -> zero-install text")
else:
    fail.append("pp4 label anchor not found")

HP.write_text(s, encoding="utf-8")
print("==== RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
