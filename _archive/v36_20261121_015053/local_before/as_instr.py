# -*- coding: utf-8 -*-
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
