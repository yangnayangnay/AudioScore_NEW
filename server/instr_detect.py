from .config import CFG

_MUSICNN_TAG_MAP = {
    "guitar": "acoustic_guitar", "piano": "acoustic_piano",
    "drums": "drums", "violin": "violin", "cello": "cello",
    "flute": "flutes", "harp": "orchestral_harp",
    "strings": "string_ensemble", "synth": "synth_lead",
    "voice": "voice", "vocals": "voice", "vocal": "voice", "choir": "voice",
}
_MAX_INSTRUMENTS = 4
_results = {}

def detect_instruments(audio_path, audio_hash=None, window_seconds=60):
    key = audio_hash or audio_path
    if key in _results:
        return _results[key]
    result = {"instruments": None, "method": "none"}
    try:
        from musicnn.tagger import top_tags
        tags = top_tags(audio_path, model="MTT_musicnn", topN=20)
        inst = []
        for t in tags:
            m = _MUSICNN_TAG_MAP.get(t)
            if m and m not in inst:
                inst.append(m)
            if len(inst) >= _MAX_INSTRUMENTS:
                break
        if inst:
            result = {"instruments": inst, "method": "musicnn"}
    except Exception:
        pass
    if result["instruments"] is None:
        try:
            result = _heuristic(audio_path, window_seconds)
        except Exception:
            pass
    _results[key] = result
    return result

def _heuristic(audio_path, window_seconds=60):
    import librosa
    import numpy as np
    y, sr = librosa.load(audio_path, sr=22050, mono=True,
                         duration=window_seconds if window_seconds and window_seconds > 0 else None)
    if y.size == 0:
        return {"instruments": None, "method": "heuristic"}
    H, P = librosa.effects.hpss(y)
    total = float(np.sqrt(np.mean(y ** 2))) + 1e-9
    perc_ratio = float(np.sqrt(np.mean(P ** 2))) / total
    inst = []
    if perc_ratio > 0.18:
        inst.append("drums")
    S = np.abs(librosa.stft(H, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    energy = S.mean(axis=1)
    def band(lo, hi):
        m = (freqs >= lo) & (freqs < hi)
        return float(energy[m].sum())
    e_total = float(energy.sum()) + 1e-9
    bass_ratio = band(40, 180) / e_total
    mid_ratio = band(180, 2000) / e_total
    high_ratio = band(2000, 8000) / e_total
    if bass_ratio > 0.20:
        inst.append("electric_bass")
    if mid_ratio > 0.35 and high_ratio > 0.10:
        inst.append("acoustic_piano")
    out = []
    for pref in ("drums", "electric_bass", "acoustic_piano"):
        if pref in inst and len(out) < _MAX_INSTRUMENTS:
            out.append(pref)
    return {"instruments": out or None, "method": "heuristic"}
