# -*- coding: utf-8 -*-
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
