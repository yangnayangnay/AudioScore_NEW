# -*- coding: utf-8 -*-
"""v32: "apply best combo" button
- backend: GET /api/eval/best -> best combo (same rule as report: valid[0],
  noref lexicographic) + labels/defaults from REGISTRY
- frontend: button in eval modal button-row; applies combo to bottom-bar
  chips (#adv_<key>) AND modal switches (#asEvKeys input[data-k]),
  dispatching change events so existing listeners/persistence fire.
Scope: 9 fine chips + modal switches only; old pp-buttons untouched."""
from pathlib import Path
import py_compile, socket, urllib.request

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail, info = [], [], []

def probe(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        s.close(); return True
    except OSError:
        return False
info.append("port 8000: " + ("RUNNING (\u9700\u91cd\u542f\u624d\u6709\u65b0\u63a5\u53e3)"
            if probe(8000) else "stopped"))

# ---------- 1. backend endpoint ----------
ep = ROOT / "as_eval.py"
src = ep.read_text(encoding="utf-8")
(ROOT / "as_eval.py.v32bak").write_text(src, encoding="utf-8")
ok.append("backup -> as_eval.py.v32bak")

if "/api/eval/best" in src:
    ok.append("backend: /api/eval/best already present")
else:
    ANCHOR = "    @app.get(\"/api/eval/status\")"
    n = src.count(ANCHOR)
    if n != 1:
        fail.append("backend: api_status anchor count=%d" % n)
    else:
        NEW_EP = (
            "    @app.get(\"/api/eval/best\")\n"
            "    def api_best():\n"
            "        res = [r for r in (STATE.get(\"results\") or [])\n"
            "               if isinstance(r, dict) and r.get(\"score\") is not None\n"
            "               and r.get(\"score\") >= 0 and not r.get(\"error\")]\n"
            "        if not res:\n"
            "            return JSONResponse({\"ok\": False,\n"
            "                                 \"reason\": \"no valid eval results yet\"})\n"
            "        best = res[0]\n"
            "        c = best.get(\"combo\") or {}\n"
            "        combo, labels = {}, {}\n"
            "        for k, m in REGISTRY.items():\n"
            "            combo[k] = bool(c.get(k, m.get(\"default\", False)))\n"
            "            labels[k] = m.get(\"label\", k)\n"
            "        return JSONResponse({\"ok\": True,\n"
            "                             \"score\": best.get(\"score\"),\n"
            "                             \"combo\": combo, \"labels\": labels,\n"
            "                             \"rolled_back\": bool(best.get(\"rolled_back\"))})\n"
            "\n")
        src = src.replace(ANCHOR, NEW_EP + ANCHOR, 1)
        ok.append("backend: /api/eval/best endpoint inserted")

try:
    ep.write_text(src, encoding="utf-8")
    py_compile.compile(str(ep), doraise=True)
    ok.append("as_eval.py compile OK")
except py_compile.PyCompileError as ex:
    ep.write_text((ROOT / "as_eval.py.v32bak").read_text(encoding="utf-8"),
                  encoding="utf-8")
    fail.append("compile FAILED -> restored | " + str(ex)[:250])

# ---------- 2. frontend button ----------
HP = ROOT / "web" / "index.html"
h = HP.read_text(encoding="utf-8")
if "==AS_APPLY==" in h:
    ok.append("frontend: apply button already present")
elif "</body>" not in h:
    fail.append("index.html: </body> not found")
else:
    APPLY = r"""<script>
/* ==AS_APPLY== v32 apply-best-combo button */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
function msg(t,good){
 var e=el('asEvMsg');
 if(!e){var m=el('asEvalModal');if(!m)return;
  e=document.createElement('div');e.id='asEvMsg';
  e.style.cssText='font-size:12px;margin-top:6px;min-height:16px';
  m.appendChild(e);}
 e.textContent=t;e.style.color=good?'#7fc97f':'#e08a8a';}
var btn=el('asEvApply');
if(!btn){
 btn=document.createElement('button');btn.id='asEvApply';btn.type='button';
 btn.textContent='\u2705 \u5e94\u7528\u6700\u4f18\u5f00\u5173';
 btn.style.cssText='cursor:pointer;padding:4px 10px;font-size:12px;margin-left:8px';
 var anchor=el('asEvReload')||el('asEvAll')||el('asEvTable');
 var done=false;
 if(anchor&&anchor.parentNode){
  if(anchor.nextSibling)anchor.parentNode.insertBefore(btn,anchor.nextSibling);
  else anchor.parentNode.appendChild(btn);
  done=true;}
 if(!done){var tb=el('asEvTable');
  if(tb&&tb.parentNode)tb.parentNode.insertBefore(btn,tb);
  else{var m=el('asEvalModal');if(m)m.appendChild(btn);}}}
btn.onclick=function(){
 msg('\u83b7\u53d6\u4e2d...',true);
 fetch('/api/eval/best',{cache:'no-store'}).then(function(r){return r.json();})
 .then(function(j){
  if(!j||!j.ok){msg('\u6682\u65e0\u53ef\u7528\u7684\u8bc4\u6d4b\u7ed3\u679c: '+
   ((j&&j.reason)||'\u8bf7\u5148\u8fd0\u884c\u4e00\u6b21\u8bc4\u6d4b'),false);return;}
  var combo=j.combo||{};var onN=0,offN=0,missing=[];
  Object.keys(combo).forEach(function(k){
   var chip=el('adv_'+k);
   if(chip){
    if(chip.checked!==!!combo[k]){chip.checked=!!combo[k];
     chip.dispatchEvent(new Event('change',{bubbles:true}));}
    if(combo[k])onN++;else offN++;}
   else missing.push(k);
   var sw=document.querySelector('#asEvKeys input[data-k="'+k+'"]');
   if(sw&&sw.checked!==!!combo[k]){sw.checked=!!combo[k];
    sw.dispatchEvent(new Event('change',{bubbles:true}));}});
  var t='\u5df2\u5e94\u7528\u6700\u4f18\u7ec4\u5408 (\u7efc\u5408='+j.score+
   '): \u5f00 '+onN+' \u9879 / \u5173 '+offN+' \u9879';
  if(j.rolled_back)t+=' [\u6ce8: \u8be5\u7ec4\u5408\u542b\u56de\u6eda\u673a\u5236]';
  if(missing.length)t+='; \u672a\u627e\u5230\u82af\u7247: '+missing.join(',');
  msg(t,true);})
 .catch(function(e){msg('\u83b7\u53d6\u5931\u8d25: '+e.message,false);});};
})();
</script>"""
    h = h.replace("</body>", APPLY + "\n</body>", 1)
    ok.append("frontend: apply button + status line injected")
HP.write_text(h, encoding="utf-8")

# ---------- 3. live probe ----------
try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/api/eval/best", timeout=4)
    info.append("PROBE /api/eval/best -> 200 (server already restarted)")
except Exception as e:
    code = getattr(e, "code", None)
    if code == 404:
        info.append("PROBE /api/eval/best -> 404 (\u9884\u671f\u5185: \u91cd\u542f\u670d\u52a1\u540e\u6d88\u5931)")
    else:
        info.append("PROBE /api/eval/best -> \u8fde\u63a5\u5931\u8d25 (\u670d\u52a1\u672a\u8fd0\u884c)")

print()
print("==== V32-APPLYBEST ====")
for l in ok:   print("  PASS:", l)
for l in info: print("  >>>", l)
for l in fail: print("  FAIL:", l)
print("=======================")
