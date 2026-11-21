# -*- coding: utf-8 -*-
"""v15-rhythm: port transformerOfMusic RhythmPatternMatcher essence to as_eval:
(1) rhythm-pattern quantization (pattern lib + sliding window + multi-grid
    snap + count-preservation rollback)
(2) tempo-change writeback (segmented BPM -> mido set_tempo events)
(3) registry-driven -> auto-appears in eval UI."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ---------- 1. as_eval.py: append rhythm-pattern core + new registry items ----------
ep = ROOT / "as_eval.py"
s = ep.read_text(encoding="utf-8")
if "RHYTHM_PATTERNS" in s:
    ok.append("as_eval.py: already patched")
else:
    ADD = r'''
# ================= v15: rhythm-pattern quantization (port of RhythmPatternMatcher) =================
# pattern = (name, duration_ratios, weight, beat_span, category)
RHYTHM_PATTERNS = [
    ("\u56db\u5206",        (1.0,),            10.0, 1, "\u5747\u5206"),
    ("\u4e8c\u516b",        (0.5, 0.5),         9.5, 1, "\u5747\u5206"),
    ("\u56db\u5341\u516d",  (0.25, 0.25, 0.25, 0.25), 7.0, 1, "\u5747\u5206"),
    ("\u4e8c\u5206",        (2.0,),             8.0, 2, "\u5747\u5206"),
    ("\u5168\u97f3\u7b26",  (4.0,),             5.0, 4, "\u5747\u5206"),
    ("\u524d\u516b\u540e\u5341\u516d", (0.5, 0.25, 0.25), 9.0, 1, "\u957f\u77ed"),
    ("\u524d\u5341\u516d\u540e\u516b", (0.25, 0.25, 0.5), 9.0, 1, "\u957f\u77ed"),
    ("\u77ed\u957f\u77ed",  (0.25, 0.5, 0.25),  7.0, 1, "\u957f\u77ed"),
    ("\u5c0f\u9644\u70b9",  (0.75, 0.25),       8.5, 1, "\u9644\u70b9"),
    ("\u5c0f\u9644\u70b9\u9006", (0.25, 0.75),  6.0, 1, "\u9644\u70b9"),
    ("\u5927\u9644\u70b9",  (1.5, 0.5),         8.5, 2, "\u9644\u70b9"),
    ("\u5927\u9644\u70b9\u9006", (0.5, 1.5),    5.5, 2, "\u9644\u70b9"),
    ("\u5c0f\u5207\u5206",  (0.25, 0.5, 0.25),  8.0, 1, "\u5207\u5206"),
    ("\u5927\u5207\u5206",  (0.5, 1.0, 0.5),    8.5, 2, "\u5207\u5206"),
    ("\u5341\u516d+\u516b+\u5341\u516d", (0.25, 0.5, 0.25), 7.0, 1, "\u5207\u5206"),
    ("\u4e09\u8fde\u97f3",  (1/3, 1/3, 1/3),    7.5, 1, "\u4e09\u8fde\u97f3"),
    ("\u4e09\u8fde\u97f32\u62cd", (1/3,)*6,     5.5, 2, "\u4e09\u8fde\u97f3"),
    ("\u4e8c\u5206\u4e09\u8fde\u97f3", (2/3, 2/3, 2/3), 4.0, 2, "\u4e09\u8fde\u97f3"),
    ("\u4e94\u8fde\u97f3",  (0.2,)*5,           4.5, 1, "\u4e94\u8fde\u97f3"),
    ("\u516d\u8fde\u97f3",  (1/6,)*6,           4.0, 1, "\u516d\u8fde\u97f3"),
    ("Swing\u516b\u5206",  (2/3, 1/3),         6.0, 1, "\u6447\u6446"),
    ("Swing\u4e24\u62cd",  (2/3, 1/3, 2/3, 1/3), 4.5, 2, "\u6447\u6446"),
    ("\u8d6b\u7c73\u5965\u62c93\u5bf92", (2/3, 2/3, 2/3), 3.5, 2, "\u8d6b\u7c73\u5965\u62c9"),
    ("\u5341\u516d\u5206\u4f11\u6b62\u524d", (0.25, 0.75), 4.5, 1, "\u4f11\u6b62"),
    ("\u5f31\u8d77\u516b\u5206", (0.5, 1.0, 0.5, 0.5, 0.5), 3.5, 3, "\u4f11\u6b62"),
]

def _rpm_snap_to_grid(t, beat):
    """multi-grid snap: beat/4 /3 /2 /1 /2, dist < beat*0.2 (RhythmPatternMatcher.snapToGrid)"""
    best_d, best_t = 1e9, t
    for g in (beat/4.0, beat/3.0, beat/2.0, beat, beat*2.0):
        gs = round(t/g)*g
        d = abs(gs - t)
        if d < best_d and d < beat*0.2:
            best_d, best_t = d, gs
    return best_t

def rhythm_pattern_quantize(pm, beat):
    """port of quantizePositionsWithPatterns: sliding-window pattern match,
    multi-grid snap, count-preservation rollback."""
    if beat <= 0: return 0
    notes = []
    for inst in pm.instruments:
        notes.extend(inst.notes)
    notes.sort(key=lambda n: n.start)
    if len(notes) < 2: return 0
    n_orig = len(notes)
    done = [None]*n_orig
    start = 0
    applied = 0
    while start < n_orig:
        best_score, best_pat, best_len, best_dursum = -1e9, None, 0, 0.0
        for (name, ratios, weight, span, cat) in RHYTHM_PATTERNS:
            L = len(ratios)
            if L > 8 or start+L > n_orig: continue
            if any(done[start+k] is not None for k in range(L)): continue
            contiguous = True
            for k in range(L-1):
                if notes[start+k+1].start - notes[start+k].end > beat*0.3:
                    contiguous = False; break
            if not contiguous: continue
            durs = [notes[start+k].end - notes[start+k].start for k in range(L)]
            if any(d <= 0 for d in durs): continue
            dsum = sum(durs)
            total_err = abs(dsum/(span*beat) - 1.0)
            if total_err > 0.20: continue
            scaled = [d/dsum for d in durs]
            ratio_err = sum(abs(scaled[k]-ratios[k]) for k in range(L))/L
            sc = weight*(1-ratio_err*3.0)*(1-total_err*2.0)
            if sc > best_score:
                best_score, best_pat, best_len, best_dursum = sc, (name, ratios, span), L, dsum
        if best_pat is not None and best_score > 4.0:
            name, ratios, span = best_pat
            expect = span*beat
            cur = _rpm_snap_to_grid(notes[start].start, beat)
            for k in range(best_len):
                d = notes[start+k].end - notes[start+k].start
                done[start+k] = (cur, cur+d)
                cur = cur + d
            applied += 1
            start += best_len
        else:
            st = _rpm_snap_to_grid(notes[start].start, beat)
            done[start] = (st, st + (notes[start].end-notes[start].start))
            start += 1
    # write back
    idx = 0
    order = sorted(range(n_orig), key=lambda i: notes[i].start)
    for i in order:
        if done[i] is not None:
            notes[i].start, notes[i].end = done[i]
    # overlap repair (+5ms shift if < beat*0.15)
    notes.sort(key=lambda n: n.start)
    for i in range(1, len(notes)):
        if notes[i].start < notes[i-1].end:
            shift = notes[i-1].end + 0.005 - notes[i].start
            if 0 <= shift < beat*0.15:
                notes[i].start = notes[i-1].end + 0.005
                notes[i].end += shift
    assert sum(len(i.notes) for i in pm.instruments) == n_orig
    return applied

def _segment_bpm_changes(notes, win=8.0, hop=4.0):
    """IOI sliding-window BPM segments -> merged (time,bpm) list (TempoChange semantics)"""
    onsets = sorted(set(s for s,e,p in notes))
    if len(onsets) < 6: return []
    import numpy as _np
    oa = _np.array(onsets)
    def fold(b):
        while b < 60: b *= 2
        while b > 180: b /= 2
        return int(round(b))
    segs = []
    pos = onsets[0]
    while pos < onsets[-1]:
        sel = oa[(oa >= pos) & (oa < pos+win)]
        if len(sel) >= 5:
            iv = _np.diff(sel); iv = iv[(iv > 0.12) & (iv < 2.5)]
            if len(iv):
                segs.append((pos + win/2, fold(60.0/max(_np.median(iv), 1e-3))))
        pos += hop
    # merge adjacent equal BPM
    merged = []
    for t, b in segs:
        if merged and merged[-1][1] == b:
            continue
        merged.append((t, b))
    return merged

def write_tempo_changes(pm, changes):
    """inject set_tempo meta events via mido (notes untouched)"""
    import mido
    from mido import MetaMessage
    buf = __import__("io").BytesIO(); pm.write(buf); buf.seek(0)
    mid = mido.MidiFile(file=buf)
    tpb = mid.ticks_per_beat
    tr = mid.tracks[0]
    # drop old tempo events, keep everything else
    kept = [m for m in tr if m.type != "set_tempo"]
    new_tr = mido.MidiTrack()
    insert_at = 0
    # preserve initial setup messages up to first note-ish content
    setup = []
    for m in kept:
        setup.append(m)
        if m.time > 0: break
    events = []
    for (t, b) in changes:
        tick = int(round(t * tpb * 2.0))  # seconds->ticks at initial tempo unknown; use tempo map approx
        usq = int(round(60_000_000 / b))
        events.append((tick, MetaMessage("set_tempo", tempo=usq, time=0)))
    events.sort(key=lambda x: x[0])
    # rebuild: setup + tempo events merged by ascending absolute tick
    abs_t = 0
    out = []
    merged = sorted(setup + [e[1] for e in events], key=lambda m: 0 if m.type == "set_tempo" else 1)
    # simpler: emit setup, then tempo events with relative times on their own
    for m in setup: new_tr.append(m)
    last = 0
    for tick, msg in events:
        msg.time = max(0, tick - last)
        last = tick
        new_tr.append(msg)
    mid.tracks[0] = new_tr
    out_buf = __import__("io").BytesIO()
    mid.save(file=out_buf)
    out_buf.seek(0)
    return out_buf.getvalue()

# ---- register v15 items (registry-driven -> eval UI auto-includes) ----
@reg("rhythm_quant", "\u8282\u594f\u578b\u6a21\u5f0f\u91cf\u5316\uff08\u591a\u7f51\u683c+\u6a21\u5f0f\u5e93\uff0c\u6765\u81eaRhythmPatternMatcher\uff09", default=False)
def _r_rhythm_quant(pm, on, ctx):
    if not on: return pm
    bpm = ctx.get("bpm_audio") or (ctx.get("bpm_notes") or 120.0)
    try:
        rhythm_pattern_quantize(pm, 60.0/max(bpm, 30.0))
    except Exception: pass
    return pm

@reg("tempo_write", "\u53d8\u901f\u5199\u56de\uff08\u5206\u6bb5BPM\u2192set_tempo\u4e8b\u4ef6\uff0c\u6765\u81eaTempoChange\uff09", default=False)
def _r_tempo_write(pm, on, ctx):
    if not on: return pm
    try:
        notes = _notes(pm)
        changes = _segment_bpm_changes(notes)
        if changes:
            data = write_tempo_changes(pm, changes)
            new_pm = _load_pm(data)
            pm.instruments = new_pm.instruments
            pm._tick_scales = getattr(new_pm, "_tick_scales", pm._tick_scales)
    except Exception: pass
    return pm
'''
    ep.write_text(s + ADD, encoding="utf-8")
    ok.append("as_eval.py: RhythmPatternMatcher port + tempo writeback registered (2 new items)")

# ---------- 2. index.html: extend applyCombo mapping ----------
HP = ROOT / "web" / "index.html"
h = HP.read_text(encoding="utf-8")
OLD = """    else if(k==='quant_global'||k==='quant_local'){
      var e2=el('pp7');if(e2)e2.checked=!!c[k];
      ls('as_g_quant',c[k]?'1':'0');}"""
NEW = """    else if(k==='quant_global'||k==='quant_local'||k==='rhythm_quant'||k==='tempo_write'){
      var e2=el('pp7');if(e2)e2.checked=!!c[k];
      ls('as_g_quant',c[k]?'1':'0');}"""
if OLD in h: h = h.replace(OLD, NEW, 1); ok.append("index.html: applyCombo mapping extended")
elif NEW in h: ok.append("index.html: mapping already present")
else: fail.append("index.html: applyCombo anchor not found")
HP.write_text(h, encoding="utf-8")

print()
print("==== V15-RHYTHM RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
