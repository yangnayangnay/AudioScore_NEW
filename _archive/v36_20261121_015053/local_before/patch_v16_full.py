# -*- coding: utf-8 -*-
"""v16: full port of transformerOfMusic mechanisms into as_eval
(1) ref scoring: 4-level alignment chain (transpose->DTW->shift->hungarian)
    + duplicate 0.3 penalty + 5-dim weighted overall
(2) noref scoring: FeedbackScorer SDR/NCS/TCS/BAS/NCT + lexicographic
(3) tempo: IOI histogram 200 bins (replaces sliding median)
(4) adaptive sensitivity hill-climb for tempo curve
(5) rhythm pattern category filter (6 default-on vs extended)
(6) registry deps (requires_key) + combo filter
(7) TCS penalty (noref) / ioi dim (ref) catches tempo_write over-segmentation
(8) stage self-eval: similarityTo rollback per variant
All switches exposed: global score options + registry combo items."""
from pathlib import Path
import re

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

# ================= as_eval.py v4 (full rewrite) =================
EVAL = r'''# -*- coding: utf-8 -*-
"""as_eval v4 - ported from transformerOfMusic (yangnayangnay):
ref-score: detectBestTranspose -> DTW refine -> findBestShift -> hungarian
           (pitch+-2/onset0.15/dur0.1/win0.5, dup weight 0.3)
           overall = .35*max(F1,overlap)+.25*onset+.15*ioi+.10*dur+.15*pitch
noref-score: SDR(15 std durs, dur-weighted) NCS(gaps) TCS(tempo-change count)
             BAS(beat grid) NCT(density range); lexicographic NCT>SDR>NCS>TCS>BAS
tempo: IOI histogram 200 bins (0.1-2.0s) argmax clamp[30,300]
       + adaptive sensitivity hill-climb (score=1-.15*freq-3.0*durErr, sens[2,20])
self-eval: MidiQualityEvaluator.similarityTo (count.4+pitch.3+dur.3) rollback<0.6
"""
import io, json, time, copy, threading, bisect
import numpy as np

try:
    import pretty_midi; HAS_PM = True
except Exception: HAS_PM = False
try:
    import librosa; HAS_LR = True
except Exception: HAS_LR = False
try:
    from scipy.optimize import linear_sum_assignment; HAS_SCIPY = True
except Exception: HAS_SCIPY = False

STATE = {"running":False,"progress":0,"total":0,"current":"",
         "results":[],"done":False,"error":"","started":0,"finished":0,
         "has_audio":False,"global_bpm":None,"mode":""}

MAX_HUNG = 1500  # above this -> greedy fallback

def _load_pm(b): return pretty_midi.PrettyMIDI(io.BytesIO(b))
def _pm_bytes(pm):
    buf = io.BytesIO(); pm.write(buf); return buf.getvalue()
def _notes(pm):
    out = []
    for inst in pm.instruments:
        for n in inst.notes: out.append((n.start, n.end, int(n.pitch)))
    out.sort(); return out

# ================= tempo =================
def _fold_bpm(b):
    while b < 60: b *= 2
    while b > 180: b /= 2
    return float(b)

def tempo_ioi_hist(notes):
    """IOI histogram 200 bins (0.1-2.0s) argmax -> bpm clamp[30,300]"""
    on = sorted(set(s for s,e,p in notes))
    if len(on) < 4: return None
    iv = np.diff(np.array(on)); iv = iv[(iv>0.1)&(iv<2.0)]
    if len(iv) < 3: return None
    hist, edges = np.histogram(iv, bins=200, range=(0.1, 2.0))
    k = int(np.argmax(hist))
    ioi = (edges[k] + edges[k+1]) / 2
    bpm = 60.0 / max(ioi, 1e-3)
    return float(min(300.0, max(30.0, bpm)))

def tempo_notes_median(notes):
    on = sorted(set(s for s,e,p in notes))
    if len(on) < 4: return None
    iv = np.diff(np.array(on)); iv = iv[(iv>0.15)&(iv<2.5)]
    if len(iv) == 0: return None
    return _fold_bpm(60.0/float(np.median(iv)))

def tempo_from_audio(audio_bytes, sr=22050):
    if not HAS_LR: return None
    try:
        y,_ = librosa.load(io.BytesIO(audio_bytes), sr=sr, mono=True)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(np.atleast_1d(tempo)[0])
        curve = None
        if len(beats) > 2:
            bt = librosa.frames_to_time(beats, sr=sr)
            tps = 60.0/np.maximum(np.diff(bt), 1e-3)
            if len(tps) > 4: tps = np.convolve(tps, np.ones(3)/3, mode="same")
            curve = (((bt[:-1]+bt[1:])/2).tolist(), tps.tolist())
        return {"bpm": tempo, "curve": curve}
    except Exception: return None

def detect_tempo_changes(notes, sensitivity=10):
    """sliding segments -> weighted smooth -> merge -> multiple-collapse
    -> stability filter (>=5s). min_change_bpm grows with sensitivity."""
    on = sorted(set(s for s,e,p in notes))
    n = len(on)
    if n < 6: return []
    seg = max(6, min(20, n//6)); step = max(1, seg//2)
    g = tempo_ioi_hist(notes) or tempo_notes_median(notes) or 120.0
    min_chg = 3.0 + 0.5*sensitivity
    segs = []
    oa = np.array(on)
    for i in range(0, n-seg, step):
        w = on[i:i+seg]
        iv = np.diff(np.array(w)); iv = iv[(iv>0.12)&(iv<2.5)]
        if len(iv) >= 3:
            segs.append((float((w[0]+w[-1])/2), _fold_bpm(60.0/float(np.median(iv)))))
    if len(segs) < 2: return []
    ts = np.array([s[0] for s in segs]); bs = np.array([s[1] for s in segs])
    sm = []
    for i in range(len(segs)):
        wgt = 1.0/(1.0 + np.abs(ts-ts[i])*2.0)
        sm.append(float((bs*wgt).sum()/wgt.sum()))
    merged = []
    for t,b in zip(ts.tolist(), sm):
        b = round(b, 1)
        if merged and abs(merged[-1][1]-b) < min_chg:
            merged[-1] = ((merged[-1][0]+t)/2, (merged[-1][1]+b)/2)
        else:
            merged.append((t, b))
    if len(merged) > 1:
        try:
            if all(abs(b/g - round(b/g)) < 0.08 for t,b in merged): merged = []
        except Exception: pass
    stable = []
    for i,(t,b) in enumerate(merged):
        nxt = merged[i+1][0] if i+1 < len(merged) else on[-1]
        if nxt - t >= 5.0: stable.append((t, b))
    return stable

def _curve_from_changes(changes, notes):
    if not changes: return None
    ts = [c[0] for c in changes]; tps = [c[1] for c in changes]
    t0 = min(s for s,e,p in notes); t1 = max(e for s,e,p in notes)
    ts = [t0] + ts + [t1]; tps = [tps[0]] + tps + [tps[-1]]
    return (ts, tps)

_STD_D = [0.25, 1/3, 0.5, 2/3, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]
def _dur_err_vs_curve(notes, curve):
    if not curve: return 1.0
    ts, tps = curve
    ta = np.array(ts)
    errs = []
    for s,e,p in notes:
        i = min(int(np.searchsorted(ta, s)), len(tps)-1)
        bpm = max(float(tps[i]), 30.0)
        d = (e-s) * bpm / 60.0
        if d <= 0: continue
        nearest = min(_STD_D, key=lambda v: abs(d-v))
        errs.append(abs(d-nearest)/nearest)
    return float(np.mean(errs)) if errs else 1.0

def evaluate_tempo(notes, changes):
    if not notes: return 3.0, 1.0, "BAD"
    dur = max(1.0, max(e for s,e,p in notes) - min(s for s,e,p in notes))
    cf = len(changes)/(dur/60.0)
    de = _dur_err_vs_curve(notes, _curve_from_changes(changes, notes))
    v = "GOOD" if (cf < 1.0 and de < 0.10) else ("OK" if (cf < 2.5 and de < 0.15) else "BAD")
    return cf, de, v

def adaptive_tempo(notes):
    """sensitivity hill-climb [2,20]: +2 if too many changes, -2 if dur err big;
    score = max(0, 1 - freq*.15 - err*3.0); 5 rounds; GOOD&>.8 early exit"""
    sens = 10; best = None
    for _ in range(5):
        ch = detect_tempo_changes(notes, sens)
        cf, de, v = evaluate_tempo(notes, ch)
        sc = max(0.0, 1.0 - cf*0.15 - de*3.0)
        if best is None or sc > best[0]: best = (sc, ch)
        if v == "GOOD" and sc > 0.8: break
        if cf > 3.0: sens = min(20, sens+2)
        elif de > 0.15: sens = max(2, sens-2)
        else: break
    return best[1] if best else []

def tempo_from_notes_fallback(notes):
    on = sorted(set(s for s,e,p in notes))
    if len(on) < 8: return None
    W = 8.0; oa = np.array(on); ts, tps = [], []
    pos = on[0]
    while pos < on[-1]:
        sel = oa[(oa>=pos)&(oa<pos+W)]
        if len(sel) >= 4:
            iv = np.diff(sel); iv = iv[(iv>0.15)&(iv<2.5)]
            if len(iv): ts.append(pos+W/2); tps.append(_fold_bpm(60.0/np.median(iv)))
        pos += W/2
    return (ts, tps) if len(ts) >= 3 else None

# ================= ref scoring: 4-level chain =================
def _pclass_hist(notes):
    h = np.zeros(12)
    for s,e,p in notes: h[p % 12] += 1.0
    return h

def detect_best_transpose(gen, ref):
    hg, hr = _pclass_hist(gen), _pclass_hist(ref)
    best_s, best_v = 0, -1.0
    for s in range(12):
        v = float(sum(hg[k]*hr[(k+s) % 12] for k in range(12)))
        if v > best_v: best_v, best_s = v, s
    s0 = float(sum(hg[k]*hr[k] for k in range(12)))
    if s0 >= best_v: return 0
    return best_s - 12 if best_s > 6 else best_s

def _pitch_profile(notes, nseg=20):
    if not notes: return None
    t0 = min(s for s,e,p in notes); t1 = max(e for s,e,p in notes)
    if t1 - t0 < 1e-3: return None
    seglen = (t1-t0)/nseg
    prof = np.zeros((nseg, 12))
    for s,e,p in notes:
        i = min(nseg-1, max(0, int((s-t0)/seglen)))
        prof[i, p % 12] += 1.0
    rn = prof.sum(axis=1, keepdims=True); rn[rn == 0] = 1.0
    return (t0, t1, prof/rn)

def dtw_refine(gen, ref):
    """DTW over 20-segment pitch profiles; returns (a,b,avg_ms) for t'=a*t+b
    via least squares on path; None if avg correction <=5ms or <10 notes."""
    gp, rp = _pitch_profile(gen), _pitch_profile(ref)
    if gp is None or rp is None: return None
    if len(gen) < 10 or len(ref) < 10: return None
    G, R = gp[2], rp[2]; n = G.shape[0]
    C = np.abs(G[:,None,:] - R[None,:,:]).sum(axis=2)
    D = np.full((n+1, n+1), np.inf); D[0,0] = 0.0
    for i in range(1, n+1):
        for j in range(1, n+1):
            D[i,j] = C[i-1,j-1] + min(D[i-1,j], D[i,j-1], D[i-1,j-1])
    pts = []
    i, j = n, n
    while i > 0 and j > 0:
        gt = gp[0] + (i-0.5)*(gp[1]-gp[0])/n
        rt = rp[0] + (j-0.5)*(rp[1]-rp[0])/n
        pts.append((gt, rt))
        cands = [(D[i-1,j],(i-1,j)),(D[i,j-1],(i,j-1)),(D[i-1,j-1],(i-1,j-1))]
        _, (i,j) = min(cands, key=lambda x: x[0])
    if len(pts) < 5: return None
    ga = np.array([p[0] for p in pts]); ra = np.array([p[1] for p in pts])
    a = float((ga*ra).sum()/max((ga*ga).sum(), 1e-9))
    corr = float(np.mean(np.abs(ga*a - ra))) * 1000.0
    if corr <= 5.0: return None
    return a, corr

def find_best_shift(gen, ref):
    refb = {}
    for s,e,p in ref: refb.setdefault(p, []).append(s)
    for k in refb: refb[k].sort()
    cand = []
    for s,e,p in gen:
        arr = refb.get(p)
        if not arr: continue
        i = bisect.bisect_left(arr, s)
        for j in (i-1, i, i+1):
            if 0 <= j < len(arr):
                d = arr[j] - s
                if abs(d) < 2.0: cand.append(d)
    if not cand: return 0.0, 0.0, 0.0
    grid = {}
    for d in cand:
        k = round(d/0.02)
        if k not in grid or abs(d) < abs(grid[k]): grid[k] = d
    cands = sorted(grid.values(), key=abs)[:200]
    def cnt(dt):
        m = 0
        for s,e,p in gen:
            t = s + dt; arr = refb.get(p)
            if not arr: continue
            i = bisect.bisect_left(arr, t)
            for j in (i-1, i):
                if 0 <= j < len(arr) and abs(arr[j]-t) <= 0.05: m += 1; break
        return m
    before = cnt(0.0)
    best = max(cands, key=cnt)
    fines = [best + k*0.005 for k in range(-4, 5)]
    best = max(fines, key=cnt)
    ov = cnt(best)/max(len(ref), len(gen))
    return best, ov, before/max(len(ref), len(gen))

def _match(gen, ref):
    """hungarian (cost=.5*onN+.3*pN+.2*dN; pitch+-2/onset.15/dur.1/win.5)
    + duplicate detection (weight .3)"""
    n, m = len(ref), len(gen)
    dmax = 0.1
    C = np.full((n, m), 1e9)
    for i,(rs,re,rp) in enumerate(ref):
        for j,(gs,ge,gp) in enumerate(gen):
            if abs(gs-rs) > 0.5: continue
            if abs(rp-gp) > 2: continue
            if abs((ge-gs)-(re-rs)) > 0.1: continue
            C[i,j] = 0.5*min(1.0, abs(gs-rs)/0.15) + 0.3*min(1.0, abs(rp-gp)/2.0) \
                   + 0.2*min(1.0, abs((ge-gs)-(re-rs))/dmax)
    match = []
    if HAS_SCIPY and n <= MAX_HUNG and m <= MAX_HUNG:
        Cm = np.where(C < 1e9, C, 1e6)
        ri, cj = linear_sum_assignment(Cm)
        match = [(i,j) for i,j in zip(ri,cj) if C[i,j] < 1e9]
    else:
        used = set()
        order = sorted(((C[i,j], i, j) for i in range(n) for j in range(m)
                        if C[i,j] < 1e9), key=lambda x: x[0])
        for c,i,j in order:
            if i in used or j in used: continue
            used.add(i); used.add(j); match.append((i,j))
    matched_g = set(j for _,j in match); matched_r = set(i for i,_ in match)
    dup = 0
    for j,(gs,ge,gp) in enumerate(gen):
        if j in matched_g: continue
        for i,(rs,re,rp) in enumerate(ref):
            if i in matched_r and rp == gp and abs(gs-rs) < 0.1: dup += 1; break
    extra = (m - len(match)) - dup
    return match, extra, dup

def _seg_ioi_sim(ref, gen):
    if len(ref) < 3 or len(gen) < 3: return 0.0
    r0 = min(s for s,e,p in ref); r1 = max(e for s,e,p in ref)
    nseg = int(max(1, min(8, (r1-r0)//5)))
    def dists(notes):
        d = np.zeros(nseg)
        t0 = min(s for s,e,p in notes); t1 = max(e for s,e,p in notes)
        sl = max((t1-t0)/nseg, 1e-3)
        on = sorted(s for s,e,p in notes)
        for a,b in zip(on[:-1], on[1:]):
            i = min(nseg-1, max(0, int(((a+b)/2 - t0)/sl)))
            d[i] += (b-a)
        tot = d.sum()
        return d/tot if tot > 0 else d
    dr, dg = dists(ref), dists(gen)
    sim = 1.0 - float(np.abs(dr-dg).sum())/2.0
    if nseg < 8: sim -= 0.1*(8-nseg)/8.0
    return max(0.0, sim)

def score_ref(gen, ref, opts):
    """4-level chain + 5-dim overall [0,1]"""
    if not ref: return {"error":"reference has no notes"}
    if not gen:
        return {"best_dt":0.0,"overlap":0.0,"transpose":0,"dtw_ms":0.0,
                "precision":0.0,"recall":0.0,"f1":0.0,"existence":0.0,
                "onset_acc":0.0,"ioi_sim":0.0,"dur_acc":0.0,"pitch_exact":0.0,
                "score":0.0,"n_cand":0,"n_ref":len(ref)}
    g = list(gen)
    tr = detect_best_transpose(g, ref) if opts.get("use_transpose", True) else 0
    if tr: g = [(s,e,p+tr) for (s,e,p) in g]
    g0 = min(s for s,e,p in g); r0 = min(s for s,e,p in ref)
    gd = max(e for s,e,p in g) - g0; rd = max(e for s,e,p in ref) - r0
    scale = rd/gd if gd > 1e-3 else 1.0
    dtw_ms = 0.0
    if opts.get("use_dtw", True):
        r2 = dtw_refine([(s,e,p) for (s,e,p) in g], ref)
        if r2:
            a, dtw_ms = r2
            scale = a
    gw = [((s-g0)*scale + r0, (e-g0)*scale + r0, p) for (s,e,p) in g]
    dt, ov, ovb = find_best_shift(gw, ref)
    if dt: gw = [(s+dt, e+dt, p) for (s,e,p) in gw]
    match, extra, dup = _match(gw, ref)
    nm = len(match)
    dupw = 0.3 if opts.get("use_dup_penalty", True) else 1.0
    P = nm/max(nm + extra + dup*dupw, 1) if m else 0.0
    R = nm/len(ref) if ref else 0.0
    F1 = 2*P*R/(P+R) if P+R > 0 else 0.0
    odev = [abs(gw[j][0]-ref[i][0]) for i,j in match]
    onset_acc = max(0.0, 1.0 - float(np.mean(odev))*20.0) if odev else 0.0
    ddev = [abs((gw[j][1]-gw[j][0])-(ref[i][1]-ref[i][0])) for i,j in match]
    dur_acc = max(0.0, 1.0 - float(np.mean(ddev))*10.0) if ddev else 0.0
    pex = (sum(1 for i,j in match if gw[j][2] == ref[i][2])/nm) if nm else 0.0
    ioi = _seg_ioi_sim(ref, gw)
    existence = max(F1, ov)
    overall = (0.35*existence + 0.25*onset_acc + 0.15*ioi
               + 0.10*dur_acc + 0.15*pex)
    return {"best_dt":round(dt,3),"overlap":round(ov,4),"transpose":int(tr),
            "dtw_ms":round(dtw_ms,1),
            "precision":round(P,4),"recall":round(R,4),"f1":round(F1,4),
            "existence":round(existence,4),"onset_acc":round(onset_acc,4),
            "ioi_sim":round(ioi,4),"dur_acc":round(dur_acc,4),
            "pitch_exact":round(pex,4),"score":round(overall,4),
            "n_cand":m,"n_ref":len(ref),"dup":dup}

# ================= noref scoring (FeedbackScorer) =================
_STD15 = [0.125,0.16667,0.1875,0.25,0.33333,0.375,0.5,0.66667,0.75,
          1.0,1.5,2.0,3.0,4.0,6.0]

def _sdr(notes, beat):
    if not notes: return 0.0
    num = den = 0.0
    for s,e,p in notes:
        d = (e-s)/beat
        if d <= 0: continue
        nearest = min(_STD15, key=lambda v: abs(d-v))
        sc = max(0.0, 1.0 - 2.0*abs(d-nearest)/nearest)
        num += d*sc; den += d
    return num/den if den > 0 else 0.0

def _ncs(notes):
    if len(notes) < 2: return 1.0
    tot = 0.0
    for a,b in zip(notes[:-1], notes[1:]):
        gap = b[0] - a[1]; pd = a[1] - a[0]
        if gap < 0 or gap <= pd*0.5: tot += 1.0
        elif gap <= pd: tot += 0.5
    return tot/(len(notes)-1)

def _tcs(notes):
    ch = detect_tempo_changes(notes, 10)
    n = len(ch)
    if n <= 2: return 1.0
    if n <= 5: return 0.8
    if n <= 10: return 0.5
    return max(0.05, 0.5 - (n-10)*0.03)

def _bas(notes, beat):
    if not notes: return 0.0
    tol = beat*0.25
    tot = 0.0
    for s,e,p in notes:
        frac = abs(s/beat - round(s/beat))*beat
        tot += max(0.0, 1.0 - frac/tol)
    return tot/len(notes)

def _nct(notes, dur):
    low = max(30.0, dur*5.0); high = max(100.0, dur*20.0)
    n = len(notes)
    if low <= n <= high: return 1.0
    if n > high: return max(0.05, 1.0 - (n-high)/high*0.5)
    return max(0.3, 1.0 - (low-n)/low*0.7)

def score_noref(notes, ctx):
    dur = max(1.0, max(e for s,e,p in notes) - min(s for s,e,p in notes)) if notes else 1.0
    bpm = ctx.get("bpm_final") or ctx.get("bpm_audio") or 120.0
    beat = 60.0/max(bpm, 30.0)
    nct = _nct(notes, dur); sdr = _sdr(notes, beat); ncs = _ncs(notes)
    tcs = _tcs(notes); bas = _bas(notes, beat)
    lex = [round(nct,6), round(sdr,6), round(ncs,6), round(tcs,6), round(bas,6)]
    avg = 0.25*nct + 0.25*sdr + 0.20*ncs + 0.15*tcs + 0.15*bas
    return {"nct":round(nct,4),"sdr":round(sdr,4),"ncs":round(ncs,4),
            "tcs":round(tcs,4),"bas":round(bas,4),"lex":lex,
            "score":round(avg,4),"n_notes":len(notes)}

# ================= quality similarity (self-eval rollback) =================
_DUR_EDGES = [0.05,0.1,0.25,0.5,1.0,1.5,2.0,3.0]
def quality_sim(a, b):
    na, nb = len(a), len(b)
    cs = 1.0 - abs(na-nb)/max(na, nb, 1)
    def pdist(notes):
        h = np.zeros(12)
        for s,e,p in notes: h[p % 12] += 1.0
        t = h.sum()
        return h/t if t > 0 else h
    def ddist(notes):
        d = np.zeros(len(_DUR_EDGES)+1)
        for s,e,p in notes:
            i = sum(1 for x in _DUR_EDGES if (e-s) >= x)
            d[i] += 1.0
        t = d.sum()
        return d/t if t > 0 else d
    def dsim(x, y):
        den = float(np.maximum(x, y).sum())
        return 1.0 - float(np.abs(x-y).sum())/den if den > 0 else 0.0
    return 0.4*cs + 0.3*dsim(pdist(a), pdist(b)) + 0.3*dsim(ddist(a), ddist(b))

# ================= registry =================
REGISTRY = {}
def reg(key, label, default=False, requires_audio=False, requires_key=None):
    REGISTRY[key] = {"key":key,"label":label,"default":default,
                     "requires_audio":requires_audio,"requires_key":requires_key}

def _ctx_bpm(ctx):
    return (ctx.get("bpm_audio") or ctx.get("bpm_notes") or 120.0)

def _ctx_curve(ctx, pm):
    c = ctx.get("curve_audio") or ctx.get("curve_notes")
    if c: return c
    return tempo_from_notes_fallback(_notes(pm))

reg("smartfrag", "\u667a\u80fd\u53bb\u788e\uff08\u8de8\u7247\u5408\u5e76+\u788e\u97f3\u5408\u5e76\uff09", default=True)
reg("pp3_vel", "\u529b\u5ea6\u91cd\u5efa\uff08RMS\uff0c\u9700\u97f3\u9891\uff09", default=True, requires_audio=True)
reg("tempo_hist", "\u901f\u5ea6\u68c0\u6d4b\uff1aIOI\u76f4\u65b9\u56fe200bins", default=False)
reg("tempo_adapt", "\u53d8\u901f\u81ea\u9002\u5e94\u7075\u654f\u5ea6\u722c\u5c71", default=False)
reg("quant_global", "\u8282\u62cd\u91cf\u5316\uff08\u5168\u5c40BPM\uff09", default=False)
reg("quant_local", "\u8282\u62cd\u91cf\u5316\uff08\u5c40\u90e8\u66f2\u7ebf\uff09", default=False)
reg("rhythm_ext", "\u6269\u5c55\u8282\u594f\u578b\uff08\u8fde\u97f3/\u6447\u6446/\u8d6b\u7c73\u5965\u62c9\uff09", default=False, requires_key="rhythm_quant")
reg("rhythm_quant", "\u8282\u594f\u578b\u6a21\u5f0f\u91cf\u5316\uff08\u591a\u7f51\u683c+\u6a21\u5f0f\u5e93\uff09", default=False)
reg("tempo_write", "\u53d8\u901f\u5199\u56de\uff08set_tempo\u4e8b\u4ef6\uff09", default=False)

# v15 rhythm core (kept, now category-filtered)
RHYTHM_BASE = [
    ("\u56db\u5206",(1.0,),10.0,1), ("\u4e8c\u516b",(0.5,0.5),9.5,1),
    ("\u56db\u5341\u516d",(0.25,)*4,7.0,1), ("\u4e8c\u5206",(2.0,),8.0,2),
    ("\u5168\u97f3\u7b26",(4.0,),5.0,4),
    ("\u524d\u516b\u540e\u5341\u516d",(0.5,0.25,0.25),9.0,1),
    ("\u524d\u5341\u516d\u540e\u516b",(0.25,0.25,0.5),9.0,1),
    ("\u77ed\u957f\u77ed",(0.25,0.5,0.25),7.0,1),
    ("\u5c0f\u9644\u70b9",(0.75,0.25),8.5,1),
    ("\u5c0f\u9644\u70b9\u9006",(0.25,0.75),6.0,1),
    ("\u5927\u9644\u70b9",(1.5,0.5),8.5,2),
    ("\u5927\u9644\u70b9\u9006",(0.5,1.5),5.5,2),
    ("\u5c0f\u5207\u5206",(0.25,0.5,0.25),8.0,1),
    ("\u5927\u5207\u5206",(0.5,1.0,0.5),8.5,2),
    ("\u4e09\u8fde\u97f3",(1/3,)*3,7.5,1),
    ("\u4e8c\u5206\u4f11\u6b62\u524d",(0.25,0.75),4.5,1),
]
RHYTHM_EXT = [
    ("\u4e09\u8fde\u97f32\u62cd",(1/3,)*6,5.5,2),
    ("\u4e8c\u5206\u4e09\u8fde\u97f3",(2/3,)*3,4.0,2),
    ("\u4e94\u8fde\u97f3",(0.2,)*5,4.5,1),
    ("\u516d\u8fde\u97f3",(1/6,)*6,4.0,1),
    ("Swing\u516b\u5206",(2/3,1/3),6.0,1),
    ("Swing\u4e24\u62cd",(2/3,1/3)*2,4.5,2),
    ("\u8d6b\u7c73\u5965\u62c9",(2/3,)*3,3.5,2),
    ("\u5f31\u8d77\u516b\u5206",(0.5,1.0,0.5,0.5,0.5),3.5,3),
]

def _snap(t, beat):
    best_d, best_t = 1e9, t
    for g in (beat/4.0, beat/3.0, beat/2.0, beat, beat*2.0):
        gs = round(t/g)*g; d = abs(gs-t)
        if d < best_d and d < beat*0.2: best_d, best_t = d, gs
    return best_t

def rhythm_quantize(pm, beat, extended=False):
    if beat <= 0: return
    notes = []
    for inst in pm.instruments: notes.extend(inst.notes)
    notes.sort(key=lambda n: n.start)
    n_orig = len(notes)
    if n_orig < 2: return
    pats = list(RHYTHM_BASE) + (RHYTHM_EXT if extended else [])
    done = [None]*n_orig
    start = 0
    while start < n_orig:
        bs, bp, bl = -1e9, None, 0
        for (name, ratios, weight, span) in pats:
            L = len(ratios)
            if L > 8 or start+L > n_orig: continue
            if any(done[start+k] is not None for k in range(L)): continue
            ok2 = True
            for k in range(L-1):
                if notes[start+k+1].start - notes[start+k].end > beat*0.3: ok2 = False; break
            if not ok2: continue
            durs = [notes[start+k].end-notes[start+k].start for k in range(L)]
            if any(d <= 0 for d in durs): continue
            dsum = sum(durs)
            te = abs(dsum/(span*beat) - 1.0)
            if te > 0.20: continue
            scaled = [d/dsum for d in durs]
            re_ = sum(abs(scaled[k]-ratios[k]) for k in range(L))/L
            sc = weight*(1-re_*3.0)*(1-te*2.0)
            if sc > bs: bs, bp, bl = sc, (ratios, span), L
        if bp is not None and bs > 4.0:
            ratios, span = bp
            cur = _snap(notes[start].start, beat)
            for k in range(bl):
                d = notes[start+k].end-notes[start+k].start
                done[start+k] = (cur, cur+d)
                cur += d
            start += bl
        else:
            st = _snap(notes[start].start, beat)
            done[start] = (st, st+(notes[start].end-notes[start].start))
            start += 1
    for i in range(n_orig):
        if done[i] is not None:
            notes[i].start, notes[i].end = done[i]
    notes.sort(key=lambda n: n.start)
    for i in range(1, len(notes)):
        if notes[i].start < notes[i-1].end:
            sh = notes[i-1].end + 0.005 - notes[i].start
            if 0 <= sh < beat*0.15:
                notes[i].start = notes[i-1].end + 0.005
                notes[i].end += sh

def write_tempo_events(pm, changes):
    import mido
    from mido import MetaMessage
    buf = io.BytesIO(); pm.write(buf); buf.seek(0)
    mid = mido.MidiFile(file=buf)
    tpb = mid.ticks_per_beat
    tr = mid.tracks[0]
    kept = [m for m in tr if m.type != "set_tempo"]
    new_tr = mido.MidiTrack()
    for m in kept: new_tr.append(m)
    last = 0
    for (t, b) in changes:
        tick = int(round(t * tpb * 2.0))
        msg = MetaMessage("set_tempo", tempo=int(round(60000000/b)), time=max(0, tick-last))
        last = tick
        new_tr.append(msg)
    mid.tracks[0] = new_tr
    out = io.BytesIO(); mid.save(file=out); out.seek(0)
    return out.getvalue()

def apply_combo(pm, combo, ctx):
    pm = copy.deepcopy(pm)
    # --- tempo source stage (before consumers) ---
    notes0 = _notes(pm)
    if combo.get("tempo_hist"):
        g = tempo_ioi_hist(notes0)
        if g: ctx["bpm_notes"] = g
        ch = detect_tempo_changes(notes0, 10)
        if ch: ctx["curve_notes"] = _curve_from_changes(ch, notes0)
    if combo.get("tempo_adapt"):
        ch = adaptive_tempo(notes0)
        if ch:
            ctx["curve_notes"] = _curve_from_changes(ch, notes0)
            if ch: ctx["bpm_notes"] = ch[0][1]
    ctx["bpm_final"] = ctx.get("bpm_audio") or ctx.get("bpm_notes")
    # --- processing items ---
    if combo.get("smartfrag"):
        try:
            from as_postproc import pp17_cross_segment_merge, pp18_same_pitch_stitch
            pp17_cross_segment_merge(pm, gap_s=0.05)
            pp18_same_pitch_stitch(pm, gap_s=0.08)
        except Exception: pass
    if combo.get("pp3_vel") and ctx.get("audio"):
        try:
            y, sr = ctx["audio"]
            rms = librosa.feature.rms(y=y, hop_length=512)[0]
            times = librosa.times_like(rms, sr=sr, hop_length=512)
            mx = float(np.max(rms)) + 1e-9
            for inst in pm.instruments:
                for nn in inst.notes:
                    i = int(np.searchsorted(times, nn.start))
                    if 0 <= i < len(rms):
                        nn.velocity = int(np.clip(20+107*rms[i]/mx, 1, 127))
        except Exception: pass
    if combo.get("quant_global"):
        bpm = ctx.get("bpm_final") or 120.0
        b = 60.0/max(bpm, 30.0)/4
        for inst in pm.instruments:
            for nn in inst.notes:
                nn.start = round(nn.start/b)*b
                nn.end = max(nn.start+b, round(nn.end/b)*b)
    if combo.get("quant_local"):
        c = _ctx_curve(ctx, pm)
        if c:
            ta = np.array(c[0]); tpa = np.array(c[1])
            for inst in pm.instruments:
                for nn in inst.notes:
                    i = min(int(np.searchsorted(ta, nn.start)), len(tpa)-1)
                    bpm = float(tpa[i])
                    if bpm > 30:
                        b = 60.0/bpm/4
                        nn.start = round(nn.start/b)*b
                        nn.end = max(nn.start+b, round(nn.end/b)*b)
    if combo.get("rhythm_quant"):
        extended = bool(combo.get("rhythm_ext"))
        try: rhythm_quantize(pm, 60.0/max(_ctx_bpm(ctx), 30.0), extended=extended)
        except Exception: pass
    if combo.get("tempo_write"):
        c = _ctx_curve(ctx, pm)
        if c:
            try:
                ts, tps = c
                chg = list(zip(ts, [round(float(x),1) for x in tps]))
                merged = []
                for t,b in chg:
                    if merged and merged[-1][1] == b: continue
                    merged.append((t,b))
                if merged:
                    data = write_tempo_events(pm, merged)
                    npm = _load_pm(data)
                    pm.instruments = npm.instruments
            except Exception: pass
    return pm

def enumerate_combos(keys, cap=32):
    import itertools, random
    keys = [k for k in keys if k in REGISTRY]
    if not keys: return []
    n = len(keys)
    if 2**n <= cap:
        tuples = list(itertools.product([False, True], repeat=n))
    else:
        rng = random.Random(42); tuples = []
        seen = set()
        while len(tuples) < cap*3 and len(seen) < cap*3:
            t = tuple(rng.random() < 0.5 for _ in range(n))
            if t not in seen: seen.add(t); tuples.append(t)
    valid = []
    for t in tuples:
        c = {k: bool(t[i]) for i,k in enumerate(keys)}
        bad = False
        for k in keys:
            meta = REGISTRY[k]
            if meta.get("requires_key") and c.get(k) and not c.get(meta["requires_key"]):
                bad = True; break
        if not bad: valid.append(c)
        if len(valid) >= cap: break
    return valid

def run_eval(base_bytes, ref_bytes, combos, ctx, sopts):
    mode = sopts.get("score_mode", "auto")
    if ref_bytes is None: mode = "noref"
    elif mode == "auto": mode = "ref"
    STATE["mode"] = mode
    STATE.update({"running":True,"progress":0,"total":len(combos),
                  "results":[],"done":False,"error":"",
                  "started":time.time(),"finished":0})
    try: base_pm = _load_pm(base_bytes)
    except Exception as e:
        STATE["error"] = str(e); STATE["running"] = False
        STATE["done"] = True; return
    base_notes = _notes(base_pm)
    ref_notes = _load_and_notes(ref_bytes) if ref_bytes else None
    if mode == "ref" and not ref_notes:
        STATE["error"] = "reference MIDI invalid"; STATE["running"] = False
        STATE["done"] = True; return
    for i,c in enumerate(combos):
        STATE["current"] = json.dumps(c, ensure_ascii=False)
        rec = {"combo": c}
        try:
            vpm = apply_combo(base_pm, c, ctx)
            rolled = False
            if sopts.get("self_eval", True):
                sim = quality_sim(_notes(vpm), base_notes)
                if sim < 0.6:
                    vpm = copy.deepcopy(base_pm); rolled = True
            vn = _notes(vpm)
            if mode == "ref":
                r = score_ref(vn, ref_notes, sopts)
            else:
                r = score_noref(vn, ctx)
            r["combo"] = c; r["rolled_back"] = rolled
            rec = r
        except Exception as e:
            rec = {"combo": c, "error": str(e), "score": -1}
        STATE["results"].append(rec)
        STATE["progress"] = i+1
    if mode == "noref":
        STATE["results"].sort(key=lambda x: tuple(x.get("lex", [0]*5)), reverse=True)
    else:
        STATE["results"].sort(key=lambda x: -(x.get("score") if x.get("score") is not None else -1))
    STATE["running"] = False; STATE["done"] = True
    STATE["finished"] = time.time()

def _load_and_notes(b):
    try: return _notes(_load_pm(b))
    except Exception: return None

def install_live(app):
    from fastapi import UploadFile, File, Form
    from fastapi.responses import JSONResponse

    @app.get("/api/eval/registry")
    def api_registry():
        return JSONResponse({
            "combo_items": [
                {"key":m["key"],"label":m["label"],"default":m["default"],
                 "requires_audio":m["requires_audio"],
                 "requires_key":m["requires_key"]}
                for m in REGISTRY.values()],
            "score_options": [
                {"key":"score_mode","label":"\u8bc4\u5206\u6a21\u5f0f","type":"enum",
                 "default":"auto","options":["auto","ref","noref"]},
                {"key":"use_transpose","label":"\u79fb\u8c03\u5bf9\u9f50","type":"bool","default":True},
                {"key":"use_dtw","label":"DTW\u901f\u5ea6\u7cbe\u5316","type":"bool","default":True},
                {"key":"use_dup_penalty","label":"\u91cd\u590d\u97f3\u7b26\u60e9\u7f590.3","type":"bool","default":True},
                {"key":"self_eval","label":"\u9636\u6bb5\u81ea\u8bc4\u56de\u6eda(sim<0.6)","type":"bool","default":True}]})

    @app.post("/api/eval/run")
    async def api_run(base: UploadFile = File(...),
                      ref: UploadFile = File(None),
                      audio: UploadFile = File(None),
                      keys: str = Form(""),
                      score_opts: str = Form("")):
        if STATE.get("running"):
            return JSONResponse({"error":"eval already running"})
        cb = await base.read()
        rb = await ref.read() if ref is not None else None
        ab = None
        if audio is not None:
            try: ab = await audio.read()
            except Exception: ab = None
        ctx = {}
        if ab:
            ta = tempo_from_audio(ab)
            if ta:
                ctx["bpm_audio"] = ta["bpm"]; ctx["curve_audio"] = ta["curve"]
                STATE["global_bpm"] = ta["bpm"]
            try:
                y, sr = librosa.load(io.BytesIO(ab), sr=22050, mono=True)
                ctx["audio"] = (y, sr)
            except Exception: pass
        STATE["has_audio"] = bool(ctx.get("audio"))
        try: so = json.loads(score_opts) if score_opts else {}
        except Exception: so = {}
        try: ks = json.loads(keys) if keys else []
        except Exception: ks = []
        if not ks: ks = [m["key"] for m in REGISTRY.values() if m["default"]]
        cl = enumerate_combos(ks)
        if not cl: return JSONResponse({"error":"empty combos"})
        threading.Thread(target=run_eval,
                         args=(cb, rb, cl, ctx, so), daemon=True).start()
        return JSONResponse({"ok":True,"total":len(cl),
                             "has_audio":STATE["has_audio"]})

    @app.get("/api/eval/status")
    def api_status():
        return JSONResponse(STATE)
'''
(ROOT / "as_eval.py").write_text(EVAL, encoding="utf-8")
ok.append("as_eval.py v4 written (4-level chain + noref lexicographic + adaptive tempo + rollback)")

# ================= index.html: modal v3 =================
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")
blocks = re.findall(r"<script\b[^>]*>[\s\S]*?</script>", s)
removed = False
for b in blocks:
    if "==AS_EVAL_MODAL==" in b:
        s = s.replace(b, "", 1); removed = True
if removed: ok.append("index.html: old eval modal removed")

MARK = "/* ==AS_EVAL_MODAL== */"
if MARK not in s:
    MODAL = r"""<script>
/* ==AS_EVAL_MODAL== v3 registry + score options + dynamic table */
(function(){
'use strict';
function el(id){return document.getElementById(id);}
function ls(k,v){try{
  if(v===undefined)return localStorage.getItem(k);
  if(v===null){localStorage.removeItem(k);return null;}
  localStorage.setItem(k,v);}catch(e){return null;}}

var REG=[],OPTS=[];
var m=document.createElement('div');m.id='asEvalModal';
m.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);'+
 'z-index:10003;align-items:center;justify-content:center';
m.innerHTML='<div style="background:#1a1f28;color:#e6ecf2;border-radius:10px;'+
 'padding:16px 20px;width:640px;max-width:94vw;max-height:90vh;'+
 'overflow:auto;box-shadow:0 8px 24px rgba(0,0,0,.5)">'+
 '<div style="font-weight:600;margin-bottom:4px">\ud83e\uddea \u6d4b\u8bd5\u6700\u4f18\u5904\u7406\u7ec4\u5408</div>'+
 '<div style="font-size:11px;opacity:.55;margin-bottom:12px">'+
 '\u57fa\u7840 MIDI = \u5f53\u524d\u8bbe\u7f6e\u8f6c\u51fa\u7684\u7ed3\u679c\u3002'+
 '\u53c2\u8003 MIDI \u53ef\u7559\u7a7a = \u65e0\u53c2\u8003\u81ea\u8bc4\u6a21\u5f0f'+
 '\uff08SDR/NCS/TCS/BAS/NCT \u5b57\u5178\u5e8f\uff09</div>'+
 '<div style="display:flex;flex-direction:column;gap:10px">'+
 '<label style="font-size:12px">\u57fa\u7840 MIDI'+
 '<input type="file" id="asEvBase" accept=".mid,.midi" style="margin-top:4px;display:block"></label>'+
 '<label style="font-size:12px">\u53c2\u8003 MIDI\uff08\u53ef\u7559\u7a7a\uff09'+
 '<input type="file" id="asEvRef" accept=".mid,.midi" style="margin-top:4px;display:block"></label>'+
 '<label style="font-size:12px">\u97f3\u9891\uff08\u53ef\u9009\uff1a\u542f\u7528RMS\u529b\u5ea6/\u97f3\u9891tempo\uff09'+
 '<input type="file" id="asEvAudio" accept="audio/*" style="margin-top:4px;display:block"></label>'+
 '<div style="font-size:12px">\u8bc4\u5206\u9009\u9879\uff08\u5168\u5c40\uff0c\u9002\u7528\u4e8e\u6240\u6709\u7ec4\u5408\uff09'+
 '<div id="asEvOpts" style="display:flex;flex-direction:column;gap:5px;margin-top:6px;'+
 'padding:8px;background:#141820;border:1px solid #2a3140;border-radius:6px;font-size:12px"></div></div>'+
 '<div style="font-size:12px">\u5904\u7406\u5f00\u5173\uff08\u81ea\u52a8\u679a\u4e3e 2^N \u7ec4\u5408\uff0c\u4e0a\u965032\uff09'+
 '<div id="asEvKeys" style="display:flex;flex-direction:column;gap:6px;'+
 'margin-top:6px;padding:8px;background:#141820;border:1px solid #2a3140;'+
 'border-radius:6px;font-size:12px"></div>'+
 '<div style="font-size:11px;opacity:.6;margin-top:6px">'+
 '<span id="asEvN"></span></div></div>'+
 '<div><button id="asEvStart" style="cursor:pointer;padding:5px 14px">\u5f00\u59cb\u8bc4\u6d4b</button>'+
 '<button id="asEvAll" style="cursor:pointer;padding:5px 10px;margin-left:8px;font-size:12px">\u5168\u9009</button>'+
 '<button id="asEvNone" style="cursor:pointer;padding:5px 10px;margin-left:8px;font-size:12px">\u5168\u4e0d\u9009</button>'+
 '<span id="asEvProg" style="margin-left:10px;font-size:12px;opacity:.7"></span>'+
 '<span id="asEvErr" style="margin-left:10px;font-size:12px;color:#e08a8a"></span></div>'+
 '<div id="asEvTable" style="margin-top:8px"></div>'+
 '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">'+
 '<button id="asEvClose" style="cursor:pointer;padding:4px 14px">\u5173\u95ed</button></div>'+
 '</div></div>';
document.body.appendChild(m);
m.addEventListener('click',function(e){if(e.target===m)m.style.display='none';});
el('asEvClose').onclick=function(){m.style.display='none';};

function fetchRegistry(){
  fetch('/api/eval/registry',{cache:'no-store'}).then(function(r){return r.json();})
  .then(function(j){
    REG=j.combo_items||[];OPTS=j.score_options||[];
    renderOpts();renderKeys();})
  .catch(function(){el('asEvErr').textContent='\u6ce8\u518c\u8868\u52a0\u8f7d\u5931\u8d25';});}
function renderOpts(){
  var box=el('asEvOpts');box.innerHTML='';
  OPTS.forEach(function(o){
    if(o.type==='enum'){
      var lab=document.createElement('label');
      lab.style.cssText='display:flex;align-items:center;gap:8px';
      lab.appendChild(document.createTextNode(o.label));
      var sel=document.createElement('select');
      sel.dataset.k=o.key;sel.dataset.t='enum';
      (o.options||[]).forEach(function(v){
        var op=document.createElement('option');op.value=v;op.textContent=v;
        if(v===o.default)op.selected=true;sel.appendChild(op);});
      sel.style.cssText='margin-left:auto;background:#1a1f28;color:#e6ecf2;border:1px solid #2a3140';
      lab.appendChild(sel);box.appendChild(lab);
    } else {
      var lab2=document.createElement('label');
      lab2.style.cssText='display:flex;align-items:center;gap:8px;cursor:pointer';
      var cb=document.createElement('input');cb.type='checkbox';
      cb.dataset.k=o.key;cb.dataset.t='bool';cb.checked=!!o.default;
      lab2.appendChild(cb);lab2.appendChild(document.createTextNode(o.label));
      box.appendChild(lab2);
    }});}
function renderKeys(){
  var box=el('asEvKeys');box.innerHTML='';
  REG.forEach(function(it){
    var lab=document.createElement('label');
    lab.style.cssText='display:flex;align-items:center;gap:8px;cursor:pointer;flex-wrap:wrap';
    var cb=document.createElement('input');cb.type='checkbox';
    cb.dataset.k=it.key;cb.checked=!!it.default;
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(it.label));
    if(it.requires_audio){
      var sp=document.createElement('span');
      sp.style.cssText='font-size:10px;color:#e0b060';
      sp.textContent='[\u9700\u97f3\u9891]';lab.appendChild(sp);}
    if(it.requires_key){
      var sp2=document.createElement('span');
      sp2.style.cssText='font-size:10px;color:#7aa2e0';
      sp2.textContent='[\u9700:'+it.requires_key+']';lab.appendChild(sp2);}
    cb.onchange=updN;
    box.appendChild(lab);});
  updN();}
function updN(){
  var n=el('asEvKeys').querySelectorAll('input:checked').length;
  el('asEvN').textContent='\u5f53\u524d '+n+' \u9879 \u2192 '+
    (n===0?0:Math.min(32,Math.pow(2,n)))+' \u7ec4\uff08\u4f9d\u8d56\u65e0\u6548\u7ec4\u5408\u81ea\u52a8\u5254\u9664\uff09';}
function comboLabel(c){
  var parts=[];
  Object.keys(c).forEach(function(k){
    var it=REG.filter(function(x){return x.key===k;})[0];
    if(!it)return;
    parts.push((c[k]?'\u2713':'\u2717')+it.label);});
  return parts.join(' | ')||'(none)';}
function applyCombo(c){
  Object.keys(c).forEach(function(k){
    if(!c[k])return;
    if(k==='smartfrag'){
      ['pp1','pp2'].forEach(function(id){var e=el(id);if(e)e.checked=true;});
      ls('as_g_smartfrag','1');}
    else if(k==='pp3_vel'){
      var e=el('pp3');if(e)e.checked=true;ls('as_g_vel','1');}
    else if(k==='quant_global'||k==='quant_local'||k==='rhythm_quant'||k==='tempo_write'||k==='tempo_hist'||k==='tempo_adapt'||k==='rhythm_ext'){
      var e2=el('pp7');if(e2)e2.checked=true;ls('as_g_quant','1');}});
  if(typeof saveOpts==='function')saveOpts();
  if(typeof toast==='function')toast('\u5df2\u5e94\u7528\u6700\u4f18\u7ec4\u5408');
  m.style.display='none';}
function fmt(x){return (x!=null&&x!==''&&!isNaN(x))?Number(x).toFixed(4):'-';}
function renderResults(results){
  var tb=el('asEvTable');
  if(!results||!results.length){
    tb.innerHTML='<div style="font-size:12px;opacity:.5">\u6682\u65e0\u7ed3\u679c</div>';return;}
  var noref=results[0]&&results[0].sdr!=null;
  var h='<table style="width:100%;border-collapse:collapse;font-size:11px">';
  if(noref){
    h+='<tr style="background:#141820"><th style="text-align:left;padding:6px">#</th>'+
     '<th style="text-align:left;padding:6px">\u7ec4\u5408</th>'+
     '<th>NCT</th><th>SDR</th><th>NCS</th><th>TCS</th><th>BAS</th>'+
     '<th>\u7efc\u5408</th><th>\u72b6\u6001</th><th></th></tr>';
  } else {
    h+='<tr style="background:#141820"><th style="text-align:left;padding:6px">#</th>'+
     '<th style="text-align:left;padding:6px">\u7ec4\u5408</th>'+
     '<th>\u5b58\u5728</th><th>onset</th><th>IOI</th><th>\u65f6\u503c</th><th>\u97f3\u9ad8</th>'+
     '<th>\u7efc\u5408</th><th>\u0394t</th><th>\u72b6\u6001</th><th></th></tr>';
  }
  results.forEach(function(r,i){
    var c=r.combo||{};
    var st='';
    if(r.error)st='<span style="color:#e08a8a">ERR</span>';
    else if(r.rolled_back)st='<span style="color:#e0b060">\u56de\u6eda</span>';
    h+='<tr style="border-top:1px solid #2a3140">'+
     '<td style="padding:6px">'+(i+1)+'</td>'+
     '<td style="padding:6px;font-size:10px">'+comboLabel(c)+'</td>';
    if(noref){
      h+='<td style="text-align:right;padding:6px">'+fmt(r.nct)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.sdr)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.ncs)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.tcs)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.bas)+'</td>';
    } else {
      h+='<td style="text-align:right;padding:6px">'+fmt(r.existence)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.onset_acc)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.ioi_sim)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.dur_acc)+'</td>'+
       '<td style="text-align:right;padding:6px">'+fmt(r.pitch_exact)+'</td>';
    }
    h+='<td style="text-align:right;padding:6px;color:'+
     (i===0?'#8ad0a0':'#dfe6ee')+'">'+fmt(r.score)+'</td>';
    if(!noref)h+='<td style="text-align:right;padding:6px">'+
     (r.best_dt!=null?Number(r.best_dt).toFixed(2):'-')+'</td>';
    h+='<td style="text-align:center;padding:6px">'+st+'</td>'+
     '<td style="padding:6px"><button data-i="'+i+'" '+
     'style="cursor:pointer;padding:2px 8px;font-size:11px">\u5e94\u7528</button></td></tr>';});
  h+='</table>';
  tb.innerHTML=h;
  tb.querySelectorAll('button[data-i]').forEach(function(btn){
    btn.onclick=function(){
      var r=results[+btn.dataset.i];
      if(r&&r.combo)applyCombo(r.combo);};});}

var polling=null;
function poll(){
  fetch('/api/eval/status',{cache:'no-store'}).then(function(r){return r.json();})
  .then(function(j){
    if(j.running){
      el('asEvProg').textContent='\u8fdb\u5ea6 '+j.progress+'/'+j.total+
        (j.mode?'\uff08'+j.mode+'\uff09':'');
      setTimeout(poll,600);return;}
    if(polling){clearInterval(polling);polling=null;}
    el('asEvProg').textContent='\u5b8c\u6210\uff08'+(j.results||[]).length+' \u7ec4'+
      (j.mode?'\uff0c'+j.mode+'\u6a21\u5f0f':'')+')';
    if(j.error)el('asEvErr').textContent=j.error;
    renderResults(j.results||[]);
    if(j.results&&j.results.length)
      ls('as_eval_last',JSON.stringify(j.results));})
  .catch(function(){el('asEvErr').textContent='\u8f6e\u8be2\u5931\u8d25';
    if(polling){clearInterval(polling);polling=null;}});}

function collectOpts(){
  var o={};
  el('asEvOpts').querySelectorAll('select[data-t=enum]').forEach(function(s){o[s.dataset.k]=s.value;});
  el('asEvOpts').querySelectorAll('input[data-t=bool]').forEach(function(cb){o[cb.dataset.k]=cb.checked;});
  return o;}

el('asEvStart').onclick=function(){
  var bf=el('asEvBase').files[0], rf=el('asEvRef').files[0];
  var af=el('asEvAudio').files[0];
  el('asEvErr').textContent='';
  if(!bf){el('asEvErr').textContent='\u8bf7\u9009\u62e9\u57fa\u7840 MIDI';return;}
  var so=collectOpts();
  if(so.score_mode==='ref'&&!rf){el('asEvErr').textContent='ref\u6a21\u5f0f\u9700\u8981\u53c2\u8003 MIDI';return;}
  var ks=[];
  el('asEvKeys').querySelectorAll('input:checked').forEach(function(cb){
    ks.push(cb.dataset.k);});
  if(!ks.length){el('asEvErr').textContent='\u81f3\u5c11\u9009\u4e00\u9879\u5904\u7406\u5f00\u5173';return;}
  var fd=new FormData();
  fd.append('base',bf,bf.name);
  if(rf)fd.append('ref',rf,rf.name);
  if(af)fd.append('audio',af,af.name);
  fd.append('keys',JSON.stringify(ks));
  fd.append('score_opts',JSON.stringify(so));
  el('asEvProg').textContent='\u542f\u52a8\u4e2d\u2026';
  fetch('/api/eval/run',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(j){
    if(j.error){el('asEvErr').textContent=j.error;return;}
    if(polling)clearInterval(polling);
    polling=setInterval(poll,600);poll();})
  .catch(function(e){el('asEvErr').textContent='\u542f\u52a8\u5931\u8d25\uff1a'+e;});};

el('asEvAll').onclick=function(){
  el('asEvKeys').querySelectorAll('input[type=checkbox]').forEach(function(cb){cb.checked=true;});
  updN();};
el('asEvNone').onclick=function(){
  el('asEvKeys').querySelectorAll('input[type=checkbox]').forEach(function(cb){cb.checked=false;});
  updN();};

el('asQEval').onclick=function(){
  m.style.display='flex';
  if(!REG.length)fetchRegistry();};

try{var lr=JSON.parse(ls('as_eval_last')||'null');
  if(lr&&lr.length)renderResults(lr);}catch(e){}
})();
</script>"""
    if "</body>" in s:
        s = s.replace("</body>", MODAL + "\n</body>", 1)
        ok.append("index.html: eval modal v3 injected")
    else: fail.append("index.html: </body> not found")
else:
    ok.append("index.html: marker present (check manually)")
HP.write_text(s, encoding="utf-8")

print()
print("==== V16-FULL RESULTS ====")
for l in ok: print("  PASS :", l)
for l in fail: print("  FAIL :", l)
print("===================")
