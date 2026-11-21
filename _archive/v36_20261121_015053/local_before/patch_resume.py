# -*- coding: utf-8 -*-
"""Inject job-resume script into web/index.html (localStorage based)."""
from pathlib import Path

p = Path(r"E:\Code\cs\AudioScore_new\web\index.html")
s = p.read_text(encoding="utf-8")

if "as_last_job" in s:
    print("[SKIP] resume script already present")
    raise SystemExit

JS = """
<script>
(function(){
  var KEY='as_last_job';
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
  function banner(){
    var b=$('as_resume_bar');
    if(!b){b=document.createElement('div');b.id='as_resume_bar';
      b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;background:#1f6feb;color:#fff;padding:8px 14px;font-size:14px;display:flex;gap:12px;align-items:center';
      document.body.appendChild(b);}
    return b;
  }
  function clearAll(){try{localStorage.removeItem(KEY);}catch(e){}var b=$('as_resume_bar');if(b)b.remove();}
  function poll(id){
    var b=banner();
    b.innerHTML='<span>\\u21bb \\u68c0\\u6d4b\\u5230\\u672a\\u5b8c\\u6210\\u4efb\\u52a1 '+id.slice(0,8)+' \\u2014 \\u6b63\\u5728\\u6062\\u590d\\u76d1\\u63a7</span>';
    var x=document.createElement('span');x.textContent='\\u2716 \\u4e0d\\u518d\\u76d1\\u63a7';
    x.style.cssText='cursor:pointer;opacity:.85';x.onclick=clearAll;b.appendChild(x);
    var t=setInterval(function(){
      fetch('/api/jobs/'+id).then(function(r){
        if(r.status===404){clearInterval(t);clearAll();
          banner().innerHTML='\\u26a0 \\u670d\\u52a1\\u5df2\\u91cd\\u542f\\uff0c\\u539f\\u4efb\\u52a1\\u5df2\\u4e22\\u5931\\uff08\\u4efb\\u52a1\\u5728\\u670d\\u52a1\\u5668\\u5185\\u5b58\\uff0c\\u91cd\\u542f\\u4e0d\\u4fdd\\u7559\\uff09';
          return null;}
        return r.json();
      }).then(function(j){
        if(!j)return;
        if(j.status==='done'){clearInterval(t);clearAll();
          var bb=banner();bb.innerHTML='';
          var lk=document.createElement('a');lk.href=j.download_url||'#';
          lk.textContent='\\u2714 \\u4efb\\u52a1\\u5b8c\\u6210\\uff0c\\u70b9\\u51fb\\u4e0b\\u8f7d';
          lk.style.cssText='color:#fff;text-decoration:underline;font-weight:600';
          bb.appendChild(lk);
          var xx=document.createElement('span');xx.textContent='\\u2716 \\u5173\\u95ed';
          xx.style.cssText='cursor:pointer;opacity:.85';xx.onclick=clearAll;bb.appendChild(xx);
          var pb=$('pbar');if(pb)pb.style.width='100%';return;}
        if(j.status==='error'){clearInterval(t);clearAll();
          banner().innerHTML='\\u2716 \\u4efb\\u52a1\\u5931\\u8d25\\uff08\\u8be6\\u89c1\\u65e5\\u5fd7\\uff09';return;}
        var sm=$('smeta');
        var meta='\\u5df2\\u7528\\u65f6 '+(j.elapsed||0)+'s';
        if(j.engine_line)meta+=' | \\u5f15\\u64ce: '+String(j.engine_line).slice(0,70);
        if(sm)sm.textContent=meta;
        var pb2=$('pbar');
        if(pb2){var pct=j.status==='running'?Math.min(88,5+83*Math.min(1,(j.elapsed||0)/480)):5;pb2.style.width=pct+'%';}
      }).catch(function(){});
    },2000);
  }
  function boot(){var id=null;try{id=localStorage.getItem(KEY);}catch(e){}if(id)poll(id);}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}
})();
</script>
"""

if "</body>" not in s:
    print("[FAIL] no </body> anchor found - paste index.html tail to assistant")
    raise SystemExit
s = s.replace("</body>", JS + "\n</body>", 1)
p.write_text(s, encoding="utf-8")
print("[OK] resume script injected before </body>")
print("     refresh page (Ctrl+F5) to activate; existing in-flight job id")
print("     will be picked up on next submit.")
