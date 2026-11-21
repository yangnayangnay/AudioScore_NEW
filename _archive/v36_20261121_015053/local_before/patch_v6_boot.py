# -*- coding: utf-8 -*-
"""v6-boot: start.bat polls port then opens browser; page shows loading
overlay until /api/health ready; auto-recover overlay if server dies."""
from pathlib import Path
import re, shutil

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- 1. server.py: /api/health ----------
srv = None
for c in [ROOT/"server.py", ROOT/"main.py", ROOT/"app.py"] + list(ROOT.glob("*.py")):
    if c.exists() and "uvicorn" in c.read_text(encoding="utf-8", errors="ignore"):
        srv = c; break
if not srv: raise SystemExit("FAIL: no uvicorn server file")
src = srv.read_text(encoding="utf-8", errors="ignore")
if "==AS_BOOT_HEALTH==" not in src:
    m = re.search(r"(?m)^\s*app\s*=\s*FastAPI\(", src)
    if m:
        nl = src.find("\n", m.start())
        BLOCK = ('\n# ==AS_BOOT_HEALTH v1==\n'
                 '@app.get("/api/health")\n'
                 'def _as_boot_health():\n    return {"ok": True, "ready": True}\n')
        src = src[:nl+1] + BLOCK + src[nl+1:]
        srv.write_text(src, encoding="utf-8")
        ok.append("server: GET /api/health added")
    else:
        fail.append("server: app=FastAPI not found; health route NOT added")
else:
    ok.append("server: health route already present")

# ---------- 2. index.html: boot overlay ----------
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
MARK = "/* ==AS_BOOT_OVERLAY== */"
if MARK not in s:
    OVJS = r"""<script>
/* ==AS_BOOT_OVERLAY== v1 */
(function(){
'use strict';
var ov=document.createElement('div');ov.id='asBoot';
ov.style.cssText='position:fixed;inset:0;z-index:20000;background:#0f1216;'+
 'display:flex;flex-direction:column;align-items:center;justify-content:center;'+
 'color:#dfe6ee;font:14px/1.6 system-ui,sans-serif;gap:14px;transition:opacity .4s';
ov.innerHTML='<div style="width:34px;height:34px;border:3px solid #2a3140;'+
 'border-top-color:#5b8dd6;border-radius:50%;animation:asSpin 1s linear infinite"></div>'+
 '<div id="asBootTxt">\u6b63\u5728\u8fde\u63a5\u670d\u52a1\u2026</div>'+
 '<div id="asBootSub" style="font-size:11px;opacity:.5">AudioScore backend</div>';
var st=document.createElement('style');
st.textContent='@keyframes asSpin{to{transform:rotate(360deg)}}';
document.head.appendChild(st);document.body.appendChild(ov);
function txt(m){var t=document.getElementById('asBootTxt');if(t)t.textContent=m;}
function show(m){ov.style.display='flex';ov.style.opacity='1';txt(m||'\u6b63\u5728\u8fde\u63a5\u670d\u52a1\u2026');}
function hide(){ov.style.opacity='0';
  setTimeout(function(){ov.style.display='none';},420);}
var tries=0,down=false;
function ping(){
  fetch('/api/health',{cache:'no-store'}).then(function(r){
    if(r.ok||r.status===404){tries=0;down=false;hide();}
    else throw 0;})
  .catch(function(){tries++;down=true;
    if(tries>45){txt('\u670d\u52a1\u672a\u54cd\u5e94\uff1a\u8bf7\u56de\u5230\u7ec8\u7aef\u770b\u62a5\u9519\uff0c\u6216\u91cd\u65b0\u8fd0\u884c start.bat');}
    else{txt(tries>6?('\u670d\u52a1\u542f\u52a8\u4e2d\uff08'+tries+'s\uff09\u2026'):'\u6b63\u5728\u8fde\u63a5\u670d\u52a1\u2026');
      setTimeout(ping,800);}});}
setInterval(function(){
  if(ov.style.display==='none'){
    fetch('/api/health',{cache:'no-store'}).then(function(r){
      if(!(r.ok||r.status===404))throw 0;})
    .catch(function(){tries=0;show('\u4e0e\u670d\u52a1\u7684\u8fde\u63a5\u4e2d\u65ad\uff0c\u7b49\u5f85\u6062\u590d\u2026');ping();});}
},5000);
ping();
})();
</script>"""
    if "</body>" in s:
        s = s.replace("</body>", OVJS + "\n</body>", 1)
        ok.append("index.html: boot overlay injected")
    else:
        fail.append("index.html: </body> not found")
else:
    ok.append("index.html: overlay already present")
HP.write_text(s, encoding="utf-8")

# ---------- 3. start.bat: poll-then-open ----------
sb = ROOT / "start.bat"
if not sb.exists():
    fail.append("start.bat not found -> 请把你的启动命令发我,我按它改")
else:
    bak = ROOT / "start.bat.bak"
    if not bak.exists(): shutil.copy2(sb, bak); ok.append("start.bat backup -> start.bat.bak")
    t = bak.read_text(encoding="utf-8", errors="ignore")
    lines = [l for l in t.splitlines()
             if not re.search(r'start\s+(""\s+)?["\']?https?://', l, re.I)]
    run_i = -1; port = "8000"
    for i,l in enumerate(lines):
        if re.search(r'python|uvicorn|server\.py|main\.py|app\.py', l, re.I) \
           and not re.match(r'\s*rem\b', l, re.I):
            run_i = i
            mp = re.search(r':(\d{4,5})', l)
            if mp: port = mp.group(1)
            break
    if run_i < 0:
        fail.append("start.bat: 没识别到启动命令行;原文如下,发我后手工适配")
        print("\n".join(lines))
    else:
        poller = ('start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command '
                  '"$u=\'http://localhost:' + port + '/api/health\';'
                  'for($i=0;$i -lt 600;$i++){try{'
                  '$r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop;'
                  'if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){break}}catch{};'
                  'Start-Sleep -Milliseconds 500};'
                  'Start-Process \'http://localhost:' + port + '\'"\r\n')
        out = lines[:run_i] + [poller.rstrip('\r\n')] + lines[run_i:]
        sb.write_text("\r\n".join(out) + "\r\n", encoding="utf-8")
        ok.append("start.bat: poller inserted before run line (port %s)" % port)

print()
print("==== V6 RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
