# -*- coding: utf-8 -*-
"""v9: /api/instruments (PANNs-CNN14 onnx, DSP fallback) + client threshold
auto-accept + auto pp4/pp5 toggle + setup.bat update."""
from pathlib import Path
import re, shutil

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- 1. as_instr.py ----------
AS_INSTR = r'''# -*- coding: utf-8 -*-
"""as_instr: instrument recognition. ML=PANNs CNN14(onnx) if model present,
else DSP rough estimate. POST /api/instruments."""
import io, os, csv, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_MDIR = _ROOT / "models" / "instr"
_ONNX = _MDIR / "Cnn14.onnx"
_CSV  = _MDIR / "class_labels_indices.csv"
_SESS = [None]
_TOKENS = [
 ("electric_piano", ["electric piano"], []),
 ("acoustic_piano", ["piano"], ["electric piano"]),
 ("electric_bass", ["bass guitar"], []),
 ("acoustic_bass", ["double bass", "contrabass", "upright bass"], []),
 ("drums", ["drum kit", "drum", "percussion"], []),
 ("voice", ["singing", "choir", "vocal"], []),
 ("violin", ["violin", "fiddle"], []),
 ("flutes", ["flute"], []),
 ("clean_electric_guitar", ["electric guitar"], []),
 ("acoustic_guitar", ["acoustic guitar", "guitar"], ["electric guitar", "bass guitar"]),
 ("harp", ["harp"], []), ("organ", ["organ"], []),
 ("saxophone", ["saxophone"], []), ("trumpet", ["trumpet"], []),
 ("clarinet", ["clarinet"], []), ("cello", ["cello"], []),
 ("accordion", ["accordion"], []), ("synthesizer", ["synthesizer"], []),
]
def _load_sess():
    if _SESS[0] is None:
        import onnxruntime as ort
        _SESS[0] = ort.InferenceSession(str(_ONNX), providers=["CPUExecutionProvider"])
    return _SESS[0]
def _load_labels():
    with open(_CSV, encoding="utf-8") as f:
        return [r["display_name"] for r in csv.DictReader(f)]
def _ml(y, sr):
    import numpy as np, librosa
    mel = librosa.feature.melspectrogram(y=y, sr=32000, n_fft=1024,
        hop=320, n_mels=64).T
    F = 1000
    if mel.shape[0] >= F:
        s0 = (mel.shape[0] - F) // 2; mel = mel[s0:s0+F]
    else:
        mel = np.pad(mel, ((0, F - mel.shape[0]), (0, 0)))
    x = np.log1p(mel)[None].astype(np.float32)
    sess = _load_sess()
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
    if float(out.max()) > 1.0: out = 1.0 / (1.0 + np.exp(-out))
    labels = _load_labels()
    rows = [(labels[i], float(out[i])) for i in range(min(len(labels), out.shape[0]))]
    res, used = [], set()
    for k, toks, excl in _TOKENS:
        best = None
        for i, (nm, cf) in enumerate(rows):
            if i in used: continue
            ln = nm.lower()
            if any(e in ln for e in excl): continue
            if any(t in ln for t in toks):
                if best is None or cf > best[1]: best = (i, nm, cf)
        if best and best[2] >= 0.05:
            used.add(best[0]); res.append({"n": best[1], "k": k,
                "c": round(best[2], 3)})
    res.sort(key=lambda d: -d["c"]); return res
def _dsp(y, sr):
    import numpy as np, librosa
    D = librosa.stft(y); H, P = librosa.decompose.hpss(D)
    pe = float(np.sum(np.abs(P))); te = pe + float(np.sum(np.abs(H))) or 1.0
    perc = pe / te
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    fr = librosa.fft_frequencies(sr=sr, n_fft=2048)
    e = S ** 2; tot = e.sum() or 1.0
    low = e[fr < 120].sum() / tot
    mid = e[(fr >= 120) & (fr < 2000)].sum() / tot
    hi = e[fr >= 2000].sum() / tot
    oe = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    rate = float(librosa.onset.onset_detect(onset_envelope=oe, sr=sr,
        units="time").size) / max(1.0, y.size / sr)
    return [
     {"n": "drums", "k": "drums", "c": round(min(1.0, .5*perc + .5*min(1, rate/8)), 3)},
     {"n": "bass", "k": "electric_bass", "c": round(min(1.0, low*2.2), 3)},
     {"n": "piano/guitar", "k": "acoustic_piano",
      "c": round(min(1.0, mid*1.6*(1-perc)), 3)},
     {"n": "voice/high", "k": "voice", "c": round(min(1.0, hi*1.8*(1-perc)), 3)}]
def detect_bytes(data):
    import librosa
    y = None
    try: y, sr = librosa.load(io.BytesIO(data), sr=32000, mono=True)
    except Exception:
        import tempfile
        fd, p = tempfile.mkstemp(suffix=".audio")
        with os.fdopen(fd, "wb") as f: f.write(data)
        try: y, sr = librosa.load(p, sr=32000, mono=True)
        finally:
            try: os.remove(p)
            except Exception: pass
    if y is None: raise RuntimeError("decode failed")
    try:
        if _ONNX.exists() and _CSV.exists():
            return {"instruments": _ml(y, sr), "model": "panns-cnn14"}
        raise RuntimeError("model missing")
    except Exception:
        return {"instruments": _dsp(y, sr), "model": "dsp-rough"}
def install_live(app):
    from fastapi import UploadFile, File
    @app.post("/api/instruments")
    def api_instruments(file: UploadFile = File(...)):
        t = time.time()
        try:
            r = detect_bytes(file.file.read())
        except Exception as e:
            return {"instruments": [], "model": "error", "detail": str(e)}
        r["elapsed"] = round(time.time() - t, 2); return r
'''
(ROOT / "as_instr.py").write_text(AS_INSTR, encoding="utf-8")
ok.append("as_instr.py created")

# ---------- 2. model downloader ----------
TOOLS = ROOT / "tools"; TOOLS.mkdir(exist_ok=True)
DL = r'''# -*- coding: utf-8 -*-
"""download PANNs labels csv. ONNX weights: no stable public URL -> manual.
Manual upgrade: search HuggingFace for 'Cnn14 onnx audioset', put file at
models/instr/Cnn14.onnx  (labels csv auto-fetched here)."""
from pathlib import Path
import urllib.request
M = Path(__file__).resolve().parent.parent / "models" / "instr"
M.mkdir(parents=True, exist_ok=True)
CSV = M / "class_labels_indices.csv"
if not CSV.exists():
    for u in ["https://raw.githubusercontent.com/qiuqiangkong/audioset_tagging_cnn/master/metadata/class_labels_indices.csv"]:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            CSV.write_bytes(urllib.request.urlopen(req, timeout=60).read())
            print("[instr] labels csv OK"); break
        except Exception as e:
            print("[instr] csv url failed:", e)
else:
    print("[instr] labels csv present")
if not (M / "Cnn14.onnx").exists():
    print("[instr] Cnn14.onnx not found -> DSP fallback mode.")
    print("        manual: download 'Cnn14' ONNX from HuggingFace,")
    print("        save as", M / "Cnn14.onnx")
else:
    print("[instr] Cnn14.onnx present -> ML mode")
'''
(TOOLS / "download_instr_model.py").write_text(DL, encoding="utf-8")
ok.append("tools/download_instr_model.py created")

# ---------- 3. server.py: route ----------
srv = None
for c in [ROOT/"server.py", ROOT/"main.py", ROOT/"app.py"] + list(ROOT.glob("*.py")):
    if c.exists() and "uvicorn" in c.read_text(encoding="utf-8", errors="ignore"):
        srv = c; break
if not srv: raise SystemExit("FAIL: no uvicorn server file")
src = srv.read_text(encoding="utf-8", errors="ignore")
if "==AS_INSTR_ROUTE==" not in src:
    m = re.search(r"(?m)^\s*app\s*=\s*FastAPI\(", src)
    if m:
        nl = src.find("\n", m.start())
        ROUTE = ('\n# ==AS_INSTR_ROUTE v1==\ntry:\n'
                 '    from as_instr import install_live as _as_inst\n'
                 '    _as_inst(app)\n    print("[as_instr] /api/instruments ready")\n'
                 'except Exception as _e:\n    print("[as_instr] route failed:", _e)\n')
        src = src[:nl+1] + ROUTE + src[nl+1:]
        ok.append("server: /api/instruments route installed")
    else:
        fail.append("server: app=FastAPI not found; paste head 40 lines to me")
        print("\n".join(src.splitlines()[:40]))
    srv.write_text(src, encoding="utf-8")
else:
    ok.append("server: route already present")

# ---------- 4. setup.bat ----------
sb = ROOT / "setup.bat"
BLOCK = ('REM ==AS_INSTR_DEPS v1==\r\n'
         '"%~dp0.venv\\Scripts\\python.exe" -m pip install onnxruntime librosa soundfile\r\n'
         '"%~dp0.venv\\Scripts\\python.exe" "%~dp0tools\\download_instr_model.py"\r\n')
if sb.exists():
    t = sb.read_text(encoding="utf-8", errors="ignore")
    if "==AS_INSTR_DEPS==" not in t:
        lines = t.splitlines(keepends=True)
        pos = len(lines)
        for i in range(len(lines)-1, -1, -1):
            if "pause" in lines[i].lower(): pos = i; break
        lines.insert(pos, BLOCK)
        sb.write_text("".join(lines), encoding="utf-8")
        ok.append("setup.bat: deps+model block inserted (before pause)")
    else:
        ok.append("setup.bat: already patched")
else:
    sb.write_text(BLOCK, encoding="utf-8")
    ok.append("setup.bat: created")

# ---------- 5. index.html: v2 -> v3 ----------
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
blocks = re.findall(r"<script\b[^>]*>[\s\S]*?</script>", s)
tgt = [b for b in blocks if "asQueuePanel" in b]
if len(tgt) == 0:
    fail.append("index.html: queue script not found (先跑 patch_clean_rebuild / v8)")
else:
    OLD = tgt[0]
    NEW = OLD
    # 5a. threshold control in options row
    NEW = NEW.replace(
        "'</div></div>'+",
        "'<label style=\"display:inline-flex;align-items:center;gap:4px;"+ 
        "font-size:12px\">\\u7f6e\\u4fe1\\u5ea6\\u2265 "+ 
        "<input type=\"number\" id=\"asThresh\" min=\"0.05\" max=\"0.9\" "+ 
        "step=\"0.05\" value=\"0.3\" style=\"width:56px\"></label>'"+ 
        "'</div></div>'+", 1)
    # 5b. threshold state init (after chkZip.onchange line)
    NEW = NEW.replace(
        "chkZip.onchange=function(){ls('as_zipmode',chkZip.checked?'1':'0');};",
        "chkZip.onchange=function(){ls('as_zipmode',chkZip.checked?'1':'0');};\n"
        "var thrIn=el('asThresh');thrIn.value=ls('as_thresh')||'0.3';\n"
        "thrIn.onchange=function(){var v=parseFloat(thrIn.value);\n"
        "  if(!(v>0))v=0.3;thrIn.value=v;ls('as_thresh',String(v));};\n"
        "function getThr(){var v=parseFloat(ls('as_thresh')||'0.3');\n"
        "  return v>0?v:0.3;}", 1)
    # 5c. instrument badge in row (before dl link in l1)
    NEW = NEW.replace(
        "'</span>'+\n      (it.dl?",
        "'</span>'+\n      (it.instr===null?'\n"
        "<span style=\"font-size:11px;color:#7fa6d9\">\\u8bc6\\u522b\\u4e2d\\u2026</span>':\n"
        "      (it.instr&&it.instr.length?'\n"
        "<span style=\"font-size:11px;color:#7fa6d9\">'+\n"
        "       esc(it.instr.map(function(x){return x.n+' '+x.c.toFixed(2);})\n"
        "         .join(' \\u00b7 '))+'</span>':\n"
        "      (it.instr&&it.instrSrc===\'fail\'?'\n"
        "<span style=\"font-size:11px;opacity:.5\">\\u8bc6\\u522b\\u5931\\u8d25</span>':'')))+\n"
        "      (it.dl?", 1)
    # 5d. detect on add
    NEW = NEW.replace(
        "el('asQAdd').onclick=function(){\n  if(!input||!input.files||!input.files.length){toast('\\u8bf7\\u5148\\u9009\\u62e9\\u6587\\u4ef6');return;}\n  for(var k=0;k<input.files.length;k++)",
        "function detectItems(from){\n  for(var k=from;k<Q.length;k++)(function(it){\n"
        "    if(!it.file)return;it.instr=null;renderQ();\n"
        "    var fd=new FormData();fd.append('file',it.file,it.name);\n"
        "    fetch('/api/instruments',{method:'POST',body:fd})\n"
        "      .then(function(r){return r.json();})\n"
        "      .then(function(j){it.instr=(j&&j.instruments)||[];\n"
        "        it.instrSrc=(j&&j.model)||'';renderQ();})\n"
        "      .catch(function(){it.instr=[];it.instrSrc='fail';renderQ();});})(Q[k]);}\n"
        "el('asQAdd').onclick=function(){\n"
        "  if(!input||!input.files||!input.files.length){toast('\\u8bf7\\u5148\\u9009\\u62e9\\u6587\\u4ef6');return;}\n"
        "  var from=Q.length;\n  for(var k=0;k<input.files.length;k++)", 1)
    NEW = NEW.replace(
        "  try{input.value='';}catch(e){}\n  renderQ();};",
        "  try{input.value='';}catch(e){}\n  renderQ();detectItems(from);};", 1)
    # 5e. auto pp4/pp5 at submit (one-shot, threshold rule)
    NEW = NEW.replace(
        "  cur.realPct=null;renderQ();\n  prevId=ls('as_last_job')||'';",
        "  cur.realPct=null;\n"
        "  (function(it){var c=it.instr||[];if(!c.length)return;\n"
        "    var thr=getThr(),above=c.filter(function(x){return x.c>=thr;});\n"
        "    var pp4=el('pp4'),pp5=el('pp5');\n"
        "    if(pp4)pp4.checked=above.length>=2;\n"
        "    if(pp5&&above.length)pp5.checked=true;})(cur);\n"
        "  renderQ();\n  prevId=ls('as_last_job')||'';", 1)
    if NEW != OLD:
        s = s.replace(OLD, NEW, 1)
        ok.append("index.html: v2 -> v3 (threshold+badge+auto pp)")
        HP.write_text(s, encoding="utf-8")
    else:
        fail.append("index.html: replacements did not match - paste F12/first lines")

print()
print("==== V9 RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
