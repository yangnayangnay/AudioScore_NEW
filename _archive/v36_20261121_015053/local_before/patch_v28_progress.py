# -*- coding: utf-8 -*-
"""v28-progress+fastlisten:
(1) eval progress: planned_total/current_combo in STATE + /status returns
    progress{done,total,remaining,failed,current}; frontend progress bar
    (已完成X次/剩余Y次/共Z次转换/当前组合/预计剩余时间)
(2) startup seconds: run.py rewritten - engine init in background thread,
    uvicorn listens immediately (root cause was available_backends() BEFORE run)
(3) all edits: backup -> compile -> auto-restore on failure; live probes"""
from pathlib import Path
import re, py_compile, socket, urllib.request

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []

def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False

def safe_write(path, new_text, label):
    bak = path.read_bytes()
    path.write_text(new_text, encoding="utf-8")
    try:
        py_compile.compile(str(path), doraise=True)
        ok.append(label + " compile OK")
        return True
    except py_compile.PyCompileError as e:
        path.write_bytes(bak)
        fail.append(label + " compile FAILED -> backup restored | " + str(e)[:200])
        return False

# ================= 1. as_eval.py: progress state =================
ep = ROOT / "as_eval.py"
src = ep.read_text(encoding="utf-8")

# dump run_eval body as evidence (printed at the end)
mb = re.search(r"(?ms)^def run_eval\(.*?(?=^def |\Z)", src)
if mb:
    print("==== run_eval body (evidence) ====")
    for i, l in enumerate(mb.group(0).splitlines()[:60]):
        print("  %3d| %s" % (i + 1, l))
    print("----")
else:
    fail.append("run_eval() not found in as_eval.py?!")
    mb = None

# 1a. reset progress at start (non-fatal if anchor differs)
m1 = re.search(r"(?m)^([ ]*)STATE\[\"running\"\] = True\s*$", src)
if m1:
    ind = m1.group(1)
    add = ('\n%sSTATE["planned_total"] = 0' % ind +
           '\n%sSTATE["current_combo"] = ""' % ind)
    src = src[:m1.end()] + add + src[m1.end():]
    ok.append("as_eval: progress reset at eval start")
else:
    info.append("STATE['running']=True anchor not found (skip reset; "
                "planned_total still set before loop)")

# 1b. before main combo-loop: planned_total; inside loop: current_combo
if mb:
    start, body = mb.start(), mb.group(0)
    lm = re.search(r"(?m)^    for (\w+) in ([A-Za-z_]\w*):[^\n]*\n", body)
    if lm:
        var, iterable = lm.group(1), lm.group(2)
        pre = ('    try:\n'
               '        STATE["planned_total"] = len(%s)\n'
               '        print("[EVAL] planned conversions: %d" %% len(%s))\n'
               '    except Exception:\n'
               '        pass\n' % (iterable, 0, iterable).replace("%d" % 0, "%d"))
        pre = ('    try:\n'
               '        STATE["planned_total"] = len(' + iterable + ')\n'
               '        print("[EVAL] planned conversions:", len(' + iterable + '))\n'
               '    except Exception:\n'
               '        pass\n')
        post = ('    STATE["current_combo"] = combo_str(' + var + ')\n')
        newbody = (body[:lm.start()] + pre + lm.group(0) + post +
                   body[lm.end():])
        src = src[:start] + newbody + src[start + len(body):]
        ok.append("as_eval: loop '%s in %s' instrumented "
                  "(planned_total + current_combo)" % (var, iterable))
    else:
        fail.append("as_eval: main for-loop not located - paste dump above")

# 1c. /api/eval/status -> include progress
OLD_ST = ('    @app.get("/api/eval/status")\n'
          '    def api_status():\n'
          '        return JSONResponse(STATE)')
NEW_ST = ('    @app.get("/api/eval/status")\n'
          '    def api_status():\n'
          '        st = dict(STATE)\n'
          '        try:\n'
          '            res = STATE.get("results") or []\n'
          '            done = sum(1 for r in res if isinstance(r, dict))\n'
          '            failed = sum(1 for r in res\n'
          '                        if isinstance(r, dict) and r.get("error"))\n'
          '            total = STATE.get("planned_total") or 0\n'
          '            st["progress"] = {"done": done, "total": total,\n'
          '                              "remaining": max(0, total - done),\n'
          '                              "failed": failed,\n'
          '                              "current":\n'
          '                              STATE.get("current_combo", "")}\n'
          '        except Exception:\n'
          '            pass\n'
          '        return JSONResponse(st)')
if src.count(OLD_ST) == 1:
    src = src.replace(OLD_ST, NEW_ST, 1)
    ok.append("as_eval: /api/eval/status now returns progress{}")
elif "progress" in src and "planned_total" in src:
    ok.append("as_eval: status progress already present")
else:
    fail.append("as_eval: api_status anchor count=%d" % src.count(OLD_ST))

safe_write(ep, src, "as_eval.py")

# ================= 2. run.py: listen first, engines in background =================
rp = ROOT / "run.py"
NEW_RUN = '''import threading

import uvicorn

from server.config import CFG


def _warm_and_list():
    # v28: heavy engine init moved OFF the critical path.
    # Engines are constructed here in background; first transcription
    # job reuses the cached engine, or constructs on demand if user is faster.
    try:
        from server.engines import available_backends
        print("=" * 50)
        print("[后台] 正在初始化转写引擎 (首次 10-90 秒, 不影响服务使用)...")
        for b in available_backends():
            print("  %s %-22s %s" % (
                "[OK] " if b["available"] else "[缺失]", b["name"], b["desc"]))
        print("[后台] 引擎就绪")
        print("=" * 50)
    except Exception as e:
        print("[后台] engine warmup error:", e)


if __name__ == "__main__":
    print("=" * 50)
    print("服务启动中 (引擎后台加载, 通常 3-5 秒即可访问):")
    print("    http://localhost:%s" % CFG["server"]["port"])
    print("=" * 50)
    threading.Thread(target=_warm_and_list, daemon=True).start()
    uvicorn.run("server.main:app",
                host=CFG["server"]["host"],
                port=CFG["server"]["port"],
                reload=False)
'''
if rp.exists():
    old = rp.read_text(encoding="utf-8", errors="ignore")
    (ROOT / "run.py.v27bak").write_text(old, encoding="utf-8")
    safe_write(rp, NEW_RUN, "run.py (backup: run.py.v27bak)")
else:
    fail.append("run.py missing?!")

# ================= 3. index.html: progress bar =================
HP = ROOT / "web" / "index.html"
h = HP.read_text(encoding="utf-8")
if "==AS_PROG==" in h:
    ok.append("index.html: progress bar already present")
elif "</body>" not in h:
    fail.append("index.html: </body> not found")
else:
    PROG = r"""<script>
/* ==AS_PROG== v28 eval progress bar (self-contained poller) */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
if(el('asEvProg'))return;
var wrap=document.createElement('div');wrap.id='asEvProg';
wrap.style.cssText='display:none;margin-top:8px';
wrap.innerHTML='<div style="height:8px;background:#141820;border:1px solid #2a3140;border-radius:4px;overflow:hidden">'
 +'<div id="asEvProgFill" style="height:100%;width:0%;background:#3a6ea5;transition:width .3s"></div></div>'
 +'<div id="asEvProgTxt" style="font-size:12px;color:#8fa0b5;margin-top:4px"></div>';
var tbl=el('asEvTable');
if(tbl&&tbl.parentNode)tbl.parentNode.insertBefore(wrap,tbl);
else{var m=el('asEvalModal');if(m)m.appendChild(wrap);else document.body.appendChild(wrap);}
var fill=el('asEvProgFill'),txt=el('asEvProgTxt');
var lastRunning=false;
setInterval(function(){
 var m=el('asEvalModal');
 var open=m&&m.style.display!=='none';
 if(!open&&!lastRunning)return;
 fetch('/api/eval/status',{cache:'no-store'}).then(function(r){return r.json();})
 .then(function(j){
  lastRunning=!!j.running;
  var p=j.progress||{};
  var d=p.done||0,t=p.total||0,rem=Math.max(0,t-d),f=p.failed||0;
  if(!j.running&&!j.done&&t===0){wrap.style.display='none';return;}
  wrap.style.display='block';
  var pct=t>0?Math.min(100,Math.round(d*100/t)):(j.done?100:0);
  fill.style.width=pct+'%';
  fill.style.background=j.done?'#3f8a4f':'#3a6ea5';
  var cur=p.current?(' | \u5f53\u524d: '+p.current):'';
  var eta='';
  if(j.started&&d>0&&j.running){
    var el2=Math.max(0,Date.now()/1000-j.started);
    eta=' | \u5df2\u7528 '+Math.round(el2)+'s | \u9884\u8ba1\u8fd8\u9700 '+Math.round(el2/d*rem)+'s';}
  txt.textContent='\u8f6c\u6362\u8fdb\u5ea6: '+d+' / '+t+
   ' (\u5df2\u5b8c\u6210 '+d+' \u6b21, \u5269\u4f59 '+rem+' \u6b21, \u5171 '+t+' \u6b21\u8f6c\u6362'+
   (f?'; \u5931\u8d25 '+f:'')+')'+cur+eta;
  if(j.done)txt.textContent+=' | \u2714 \u5b8c\u6210';
 }).catch(function(){});
},700);
})();
</script>"""
    h = h.replace("</body>", PROG + "\n</body>", 1)
    ok.append("index.html: progress bar injected")
HP.write_text(h, encoding="utf-8")

# ================= 4. live probes =================
info.append("port 8000: " + ("RUNNING" if probe(8000) else "stopped"))
for pth in ("/api/health", "/api/eval/registry"):
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8000" + pth, timeout=4)
        info.append("PROBE %s -> %s OK" % (pth, r.status))
    except Exception as e:
        code = getattr(e, "code", None)
        if code:
            fail.append("PROBE %s -> HTTP %s (旧进程? 重启服务后消失)" % (pth, code))
        else:
            info.append("PROBE %s -> 连接失败 (服务未运行)" % pth)

print()
print("==== V28-PROGRESS+FASTLISTEN ====")
for l in ok:   print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("=================================")
