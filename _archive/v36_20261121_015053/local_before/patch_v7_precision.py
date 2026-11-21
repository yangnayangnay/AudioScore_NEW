# -*- coding: utf-8 -*-
"""v7-precision: (1) pp17/18 server-side postproc via pretty_midi
(2) precision preset dropdown (standard/accuracy/expression)
(3) client downloads routed through /api/postproc when enabled."""
from pathlib import Path
import re, shutil

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- 1. as_postproc.py ----------
AS_PP = r'''# -*- coding: utf-8 -*-
"""as_postproc: pretty_midi based postproc on uploaded MIDI files.
POST /api/postproc?pp17=1&pp18=1 (multipart, file=<midi>)
returns postproc-ed midi as bytes."""
import io, math
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

def _load(midi_bytes):
    import pretty_midi
    return pretty_midi.PrettyMIDI(io.BytesIO(midi_bytes))

def _save(pm):
    buf = io.BytesIO()
    pm.write(buf)
    return buf.getvalue()

def _collect_notes(pm):
    """flatten notes from all instruments (preserving channel/ref)"""
    out = []
    for ci, inst in enumerate(pm.instruments):
        for ni, n in enumerate(inst.notes):
            out.append({"ci": ci, "ni": ni, "note": n,
                        "start": n.start, "end": n.end,
                        "pitch": n.pitch, "vel": n.velocity})
    return out

def pp17_cross_segment_merge(pm, overlap_s=0.02, gap_s=0.05):
    """merge notes of same pitch if: time-overlap OR gap<=50ms
    usually split-by-window artifacts from sliding-inference."""
    n = 0
    for inst in pm.instruments:
        notes = sorted(inst.notes, key=lambda x: (x.pitch, x.start))
        merged = []
        for x in notes:
            if merged:
                p = merged[-1]
                if p.pitch == x.pitch:
                    # overlap OR small gap
                    if x.start <= p.end + gap_s:
                        p.end = max(p.end, x.end)
                        p.velocity = int(max(p.velocity, x.velocity))
                        n += 1; continue
            merged.append(x)
        inst.notes = merged
    return n

def pp18_same_pitch_stitch(pm, gap_s=0.08):
    """stitch same-pitch notes separated by <80ms (model confidence flicker)"""
    n = 0
    for inst in pm.instruments:
        notes = sorted(inst.notes, key=lambda x: (x.pitch, x.start))
        merged = []
        for x in notes:
            if merged:
                p = merged[-1]
                if p.pitch == x.pitch and x.start - p.end <= gap_s \
                   and x.start - p.end > 0:
                    p.end = x.end
                    p.velocity = int((p.velocity + x.velocity)/2)
                    n += 1; continue
            merged.append(x)
        inst.notes = merged
    return n

def postproc_bytes(midi_bytes, pp17=True, pp18=True):
    pm = _load(midi_bytes)
    n17 = n18 = 0
    if pp17: n17 = pp17_cross_segment_merge(pm)
    if pp18: n18 = pp18_same_pitch_stitch(pm)
    return _save(pm), {"pp17": n17, "pp18": n18}

def install_live(app):
    from fastapi import UploadFile, File, Form
    from fastapi.responses import Response
    @app.post("/api/postproc")
    async def api_postproc(file: UploadFile = File(...),
                            pp17: int = Form(1), pp18: int = Form(1)):
        data = await file.read()
        try:
            out, stats = postproc_bytes(data, bool(pp17), bool(pp18))
            return Response(content=out, media_type="audio/midi",
                headers={"X-AS-PP17": str(stats["pp17"]),
                         "X-AS-PP18": str(stats["pp18"])})
        except Exception as e:
            return Response(content=data, media_type="audio/midi",
                headers={"X-AS-PPERR": str(e)[:80]})
'''
(ROOT / "as_postproc.py").write_text(AS_PP, encoding="utf-8")
ok.append("as_postproc.py created")

# ---------- 2. server.py route ----------
srv = None
for c in [ROOT/"server.py", ROOT/"main.py", ROOT/"app.py"] + list(ROOT.glob("*.py")):
    if c.exists() and "uvicorn" in c.read_text(encoding="utf-8", errors="ignore"):
        srv = c; break
if not srv: raise SystemExit("FAIL: no uvicorn server file")
src = srv.read_text(encoding="utf-8", errors="ignore")
if "==AS_PP_ROUTE==" not in src:
    m = re.search(r"(?m)^\s*app\s*=\s*FastAPI\(", src)
    if m:
        nl = src.find("\n", m.start())
        BLOCK = ('\n# ==AS_PP_ROUTE v1==\ntry:\n'
                 '    from as_postproc import install_live as _as_ppl\n'
                 '    _as_ppl(app)\n    print("[as_postproc] /api/postproc ready")\n'
                 'except Exception as _e:\n    print("[as_postproc] route failed:", _e)\n')
        src = src[:nl+1] + BLOCK + src[nl+1:]
        srv.write_text(src, encoding="utf-8")
        ok.append("server: /api/postproc route installed")
    else:
        fail.append("server: app=FastAPI not found; route NOT added")
else:
    ok.append("server: route already present")

# ---------- 3. setup.bat add pretty_midi ----------
sb = ROOT / "setup.bat"
BLOCK = ('REM ==AS_PP_DEPS v1==\r\n'
         '"%~dp0.venv\\Scripts\\python.exe" -m pip install pretty_midi\r\n')
if sb.exists():
    t = sb.read_text(encoding="utf-8", errors="ignore")
    if "==AS_PP_DEPS==" not in t:
        lines = t.splitlines(keepends=True)
        pos = len(lines)
        for i in range(len(lines)-1, -1, -1):
            if "pause" in lines[i].lower(): pos = i; break
        lines.insert(pos, BLOCK)
        sb.write_text("".join(lines), encoding="utf-8")
        ok.append("setup.bat: pretty_midi dep added")
    else:
        ok.append("setup.bat: already patched")
else:
    sb.write_text(BLOCK, encoding="utf-8")
    ok.append("setup.bat: created")

# ---------- 4. index.html: preset dropdown + client-side postproc ----------
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")

A_OLD = r"""'<span id="asQSet" style="cursor:pointer;font-size:12px;color:#9fb0c0">\u2699 \u8bbe\u7f6e</span>'+"""
A_NEW = r"""'<span id="asQSet" style="cursor:pointer;font-size:12px;color:#9fb0c0">\u2699 \u8bbe\u7f6e</span>'+
 '<select id="asPrec" style="background:#1a1f28;color:#e6ecf2;border:1px solid #3a3f4a;'+
 'border-radius:4px;font-size:12px;padding:2px 6px;cursor:pointer">'+
 '<option value="std">\u6807\u51c6</option>'+
 '<option value="acc">\u7cbe\u5ea6\u4f18\u5148</option>'+
 '<option value="expr">\u8868\u73b0\u4f18\u5148</option></select>'+"""
if A_OLD in s: s = s.replace(A_OLD, A_NEW, 1); ok.append("A: preset dropdown in header")
elif A_NEW in s: ok.append("A: SKIP")
else: fail.append("A: NOT FOUND")

B_OLD = r"""var thrIn=el('asThresh');"""
B_NEW = r"""var precSel=el('asPrec');
if(precSel){precSel.value=ls('as_prec')||'std';
  precSel.onchange=function(){ls('as_prec',precSel.value);applyPrec(precSel.value);};}
function applyPrec(mode){
  function setP(id,v){var e=el(id);if(e){e.checked=v;}}
  if(mode==='acc'){
    ['pp9','pp14','pp15','pp16'].forEach(function(k){setP(k,false);});
    toast('\u7cbe\u5ea6\u4f18\u5148\uff1a\u5df2\u5173 pp9/14/15/16\uff0c\u4fdd\u6301 pp17/18');}
  else if(mode==='expr'){
    ['pp9','pp11','pp16'].forEach(function(k){setP(k,true);});
    toast('\u8868\u73b0\u4f18\u5148\uff1a\u5df2\u5f00 pp9/11/16\uff0c\u9002\u5408\u89c4\u6574\u66f2\u98ce');}
  else{toast('\u6807\u51c6\u6a21\u5f0f\uff1a\u4fdd\u6301\u5f53\u524d\u624b\u52a8\u8bbe\u7f6e');}
  saveOpts();}
var thrIn=el('asThresh');"""
if B_OLD in s: s = s.replace(B_OLD, B_NEW, 1); ok.append("B: applyPrec() logic")
elif "function applyPrec" in s: ok.append("B: SKIP")
else: fail.append("B: NOT FOUND")

C_OLD = r"""function saveBlob(url,fn,cb){fetch(url).then(function(r){return r.blob();})
  .then(function(bl){var u=URL.createObjectURL(bl);var t=document.createElement('a');
  t.href=u;t.download=fn;document.body.appendChild(t);t.click();t.remove();
  setTimeout(function(){URL.revokeObjectURL(u);},4000);if(cb)cb(true);})
  .catch(function(){if(cb)cb(false);});}"""
C_NEW = r"""function precMode(){return ls('as_prec')||'std';}
function postprocBlob(blob,cb){
  if(precMode()!=='acc'){cb(blob);return;}
  var fd=new FormData();fd.append('file',blob,'m.mid');
  fd.append('pp17','1');fd.append('pp18','1');
  fetch('/api/postproc',{method:'POST',body:fd})
  .then(function(r){return r.blob();}).then(cb)
  .catch(function(){cb(blob);});}
function saveBlob(url,fn,cb){fetch(url).then(function(r){return r.blob();})
  .then(function(bl){return new Promise(function(res){
    if(precMode()==='acc'){postprocBlob(bl,function(p){res(p);});}
    else res(bl);});})
  .then(function(bl){var u=URL.createObjectURL(bl);var t=document.createElement('a');
  t.href=u;t.download=fn;document.body.appendChild(t);t.click();t.remove();
  setTimeout(function(){URL.revokeObjectURL(u);},4000);if(cb)cb(true);})
  .catch(function(){if(cb)cb(false);});}"""
if C_OLD in s: s = s.replace(C_OLD, C_NEW, 1); ok.append("C: saveBlob postproc hook")
elif "function postprocBlob" in s: ok.append("C: SKIP")
else: fail.append("C: NOT FOUND")

D_OLD = r"""      return fetch(u).then(function(r){return r.blob();})
        .then(function(bl){return {name:e.name,blob:bl};})
        .catch(function(){return null;});});}"""
D_NEW = r"""      return fetch(u).then(function(r){return r.blob();})
        .then(function(bl){return new Promise(function(res){
          if(precMode()==='acc'){postprocBlob(bl,function(p){res({name:e.name,blob:p});});}
          else res({name:e.name,blob:bl});});})
        .catch(function(){return null;});});}"""
if D_OLD in s: s = s.replace(D_OLD, D_NEW, 1); ok.append("D: ZIP postproc hook")
elif "postprocBlob(bl,function(p){res({name:e.name" in s: ok.append("D: SKIP")
else: fail.append("D: NOT FOUND")

E_OLD = r"""'<option value="std">\u6807\u51c6</option>'+
 '<option value="acc">\u7cbe\u5ea6\u4f18\u5148</option>'+
 '<option value="expr">\u8868\u73b0\u4f18\u5148</option></select>'+"""
E_NEW = r"""'<option value="std">\u6807\u51c6</option>'+
 '<option value="acc">\u7cbe\u5ea6\u4f18\u5148</option>'+
 '<option value="expr">\u8868\u73b0\u4f18\u5148</option></select>'+
 '<span style="font-size:10px;opacity:.5" title="\u7cbe\u5ea6\u4f18\u5148\u5173\u95ed\u4f24\u7cbe\u5ea6\u7684\u89c4\u5219\u6539\u5199\uff0c\u8868\u73b0\u4f18\u5148\u5f00\u542f\u91cf\u5316">\u63d0\u793a</span>'+"""
if E_OLD in s and E_NEW not in s: s = s.replace(E_OLD, E_NEW, 1); ok.append("E: hint")
elif E_NEW in s: ok.append("E: SKIP")
else: pass

HP.write_text(s, encoding="utf-8")

print()
print("==== V7 RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
