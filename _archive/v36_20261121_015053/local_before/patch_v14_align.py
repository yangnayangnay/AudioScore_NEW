# -*- coding: utf-8 -*-
"""v14: as_eval rewritten per transformerOfMusic design:
shift-alignment + Hungarian matching (MidiComparator), pre-tempo
(audio) + dynamic tempo (notes IOI) interleaved into quant variants."""
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
(ROOT / "as_eval.py").write_text(r'''# -*- coding: utf-8 -*-
"""as_eval v3: aligned with transformerOfMusic MidiComparator design.
- Shift alignment: discrete candidates, 20ms grid dedup, coarse+fine scan
- Hungarian matching: cost=0.5*onsetN+0.3*pitchN+0.2*durN, |dp|<=2,|dt|<=0.5s
- Pre-tempo from audio (librosa), dynamic tempo from notes (IOI, sliding)
- Registry-driven combos, cap 32 with sampling.
"""
import io, json, time, copy, threading, bisect
import numpy as np
from pathlib import Path

try:
    import pretty_midi
    HAS_PM = True
except ImportError:
    HAS_PM = False
try:
    import librosa
    HAS_LR = True
except ImportError:
    HAS_LR = False
try:
    from scipy.optimize import linear_sum_assignment
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

STATE = {"running":False,"progress":0,"total":0,"current":"",
         "results":[],"done":False,"error":"","started":0,"finished":0,
         "has_audio":False,"global_bpm":None}

# ---------- MIDI io ----------
def _load_pm(b): return pretty_midi.PrettyMIDI(io.BytesIO(b))
def _pm_bytes(pm):
    buf=io.BytesIO(); pm.write(buf); return buf.getvalue()
def _notes(pm):
    out=[]
    for inst in pm.instruments:
        for n in inst.notes: out.append((n.start,n.end,int(n.pitch)))
    out.sort(); return out

# ---------- tempo (pre-analysis + dynamic from notes) ----------
def tempo_from_audio(audio_bytes, sr=22050):
    if not HAS_LR: return None
    try:
        y,_=librosa.load(io.BytesIO(audio_bytes),sr=sr,mono=True)
        tempo,beats=librosa.beat.beat_track(y=y,sr=sr)
        tempo=float(np.atleast_1d(tempo)[0])
        curve=None
        if len(beats)>2:
            bt=librosa.frames_to_time(beats,sr=sr)
            iv=np.diff(bt); tps=60.0/np.maximum(iv,1e-3)
            if len(tps)>4: tps=np.convolve(tps,np.ones(3)/3,mode="same")
            mid=(bt[:-1]+bt[1:])/2
            curve=(mid.tolist(),tps.tolist())
        return {"bpm":tempo,"curve":curve}
    except Exception: return None

def tempo_from_notes(notes):
    onsets=sorted(set(s for s,e,p in notes))
    if len(onsets)<4: return None
    iv=np.diff(onsets); iv=iv[(iv>0.15)&(iv<2.5)]
    if len(iv)==0: return None
    def fold(b):
        while b<60: b*=2
        while b>180: b/=2
        return float(b)
    bpm=fold(60.0/np.median(iv))
    curve=None
    W=8.0; pos=onsets[0]; tend=onsets[-1]
    ts,tps=[],[]
    oa=np.array(onsets)
    while pos<tend:
        sel=oa[(oa>=pos)&(oa<pos+W)]
        if len(sel)>=4:
            iv2=np.diff(sel); iv2=iv2[(iv2>0.15)&(iv2<2.5)]
            if len(iv2): ts.append(pos+W/2); tps.append(fold(60.0/np.median(iv2)))
        pos+=W/2
    if len(ts)>=3: curve=(ts,tps)
    return {"bpm":bpm,"curve":curve}

# ---------- scoring: shift align + Hungarian (per MidiComparator) ----------
def _shift_align(gen,ref):
    refb={}
    for s,e,p in ref: refb.setdefault(p,[]).append(s)
    for k in refb: refb[k].sort()
    cand=[]
    for s,e,p in gen:
        arr=refb.get(p)
        if not arr: continue
        i=bisect.bisect_left(arr,s)
        for j in (i-1,i,i+1):
            if 0<=j<len(arr):
                d=arr[j]-s
                if abs(d)<2.0: cand.append(d)
    if not cand: return 0.0,0.0
    grid={}
    for d in cand:
        k=round(d/0.02)
        if k not in grid or abs(d)<abs(grid[k]): grid[k]=d
    cands=sorted(grid.values(),key=abs)[:200]
    def overlap(dt):
        m=0
        for s,e,p in gen:
            t=s+dt; arr=refb.get(p)
            if not arr: continue
            i=bisect.bisect_left(arr,t)
            hit=False
            for j in (i-1,i):
                if 0<=j<len(arr) and abs(arr[j]-t)<=0.05: hit=True; break
            if hit: m+=1
        return m/max(len(ref),len(gen))
    best=max(cands,key=overlap)
    fines=[best+k*0.005 for k in range(-4,5)]
    best=max(fines,key=overlap)
    return best,overlap(best)

def score_pair(cand_bytes,ref_bytes):
    try:
        gen=_notes(_load_pm(cand_bytes)); ref=_notes(_load_pm(ref_bytes))
        if not ref: return {"error":"reference has no notes"}
        if not gen: return {"best_dt":0.0,"overlap":0.0,"precision":0.0,
                            "recall":0.0,"f1":0.0,"score":0.0,
                            "n_cand":0,"n_ref":len(ref)}
        dt,ov=_shift_align(gen,ref)
        G=[(s+dt,e,p) for (s,e,p) in gen]
        n,m=len(ref),len(G)
        dmax=max(max(e-s for s,e,p in ref),max(e-s for s,e,p in G),1e-3)
        C=np.full((n,m),1e9)
        if HAS_SCIPY:
            for i,(rs,re,rp) in enumerate(ref):
                for j,(gs,ge,gp) in enumerate(G):
                    if abs(rp-gp)<=2 and abs(gs-rs)<=0.5:
                        C[i,j]=0.5*abs(gs-rs)/0.5+0.3*abs(rp-gp)/2.0 \
                              +0.2*abs((ge-gs)-(re-rs))/dmax
            Cm=np.where(C<1e9,C,1e6)
            ri,cj=linear_sum_assignment(Cm)
            match=[(i,j) for i,j in zip(ri,cj) if C[i,j]<1e9]
        else:
            match=[]
            used=set()
            for i,(rs,re,rp) in enumerate(ref):
                best=None
                for j,(gs,ge,gp) in enumerate(G):
                    if j in used: continue
                    if abs(rp-gp)<=2 and abs(gs-rs)<=0.5:
                        c=0.5*abs(gs-rs)/0.5+0.3*abs(rp-gp)/2.0 \
                          +0.2*abs((ge-gs)-(re-rs))/dmax
                        if best is None or c<best[0]: best=(c,j)
                if best: used.add(best[1]); match.append((i,best[1]))
        P=len(match)/m if m else 0.0
        R=len(match)/n if n else 0.0
        F1=2*P*R/(P+R) if P+R>0 else 0.0
        avg=np.mean([C[i,j] for i,j in match]) if match else 1.0
        score=0.7*F1+0.3*ov
        return {"best_dt":round(dt,3),"overlap":round(ov,4),
                "precision":round(P,4),"recall":round(R,4),
                "f1":round(F1,4),"avg_cost":round(float(avg),4),
                "score":round(score,4),"n_cand":m,"n_ref":n}
    except Exception as e:
        return {"error":str(e)}

# ---------- registry ----------
REGISTRY={}
def reg(key,label,default=False,requires_audio=False):
    def deco(fn):
        REGISTRY[key]={"key":key,"label":label,"default":default,
                       "requires_audio":requires_audio,"apply":fn}
        return fn
    return deco

@reg("smartfrag","\u667a\u80fd\u53bb\u788e\uff08\u8de8\u7247\u5408\u5e76+\u788e\u97f3\u5408\u5e76\uff09",default=True)
def _r_smartfrag(pm,on,ctx):
    if not on: return pm
    try:
        from as_postproc import pp17_cross_segment_merge,pp18_same_pitch_stitch
        pp17_cross_segment_merge(pm,gap_s=0.05)
        pp18_same_pitch_stitch(pm,gap_s=0.08)
    except Exception: pass
    return pm

@reg("pp3_vel","\u529b\u5ea6\u91cd\u5efa\uff08RMS\uff0c\u9700\u97f3\u9891\uff09",default=True,requires_audio=True)
def _r_vel(pm,on,ctx):
    if not on: return pm
    a=ctx.get("audio")
    if a is None: return pm
    y,sr=a
    try:
        rms=librosa.feature.rms(y=y,hop_length=512)[0]
        times=librosa.times_like(rms,sr=sr,hop_length=512)
        mx=float(np.max(rms))+1e-9
        for inst in pm.instruments:
            for nn in inst.notes:
                i=int(np.searchsorted(times,nn.start))
                if 0<=i<len(rms):
                    nn.velocity=int(np.clip(20+107*rms[i]/mx,1,127))
    except Exception: pass
    return pm

@reg("quant_global","\u8282\u62cd\u91cf\u5316\uff08\u9884\u4f30 BPM\uff1a\u97f3\u9891\u2192\u97f3\u7b26IOI\uff09",default=False)
def _r_qg(pm,on,ctx):
    if not on: return pm
    bpm=ctx.get("bpm_audio") or (ctx.get("bpm_notes") or 120.0)
    b=60.0/max(bpm,30.0)/4
    for inst in pm.instruments:
        for nn in inst.notes:
            nn.start=round(nn.start/b)*b
            nn.end=max(nn.start+b,round(nn.end/b)*b)
    return pm

@reg("quant_local","\u52a8\u6001tempo\u91cf\u5316\uff08\u5c40\u90e8\u66f2\u7ebf\uff1a\u97f3\u9891\u2192\u97f3\u7b26IOI\uff09",default=False)
def _r_ql(pm,on,ctx):
    if not on: return pm
    curve=ctx.get("curve_audio") or ctx.get("curve_notes")
    if not curve: return pm
    ts,tps=curve
    ts_a=np.array(ts); tps_a=np.array(tps)
    for inst in pm.instruments:
        for nn in inst.notes:
            i=int(np.searchsorted(ts_a,nn.start))
            if 0<=i<len(tps_a):
                bpm=float(tps_a[i])
                if bpm>30:
                    b=60.0/bpm/4
                    nn.start=round(nn.start/b)*b
                    nn.end=max(nn.start+b,round(nn.end/b)*b)
    return pm

# ---------- combos ----------
def enumerate_combos(keys,cap=32):
    import itertools,random
    keys=[k for k in keys if k in REGISTRY]
    if not keys: return []
    n=len(keys)
    if 2**n<=cap:
        tuples=list(itertools.product([False,True],repeat=n))
    else:
        rng=random.Random(42); tuples=[]
        seen=set()
        while len(tuples)<cap:
            t=tuple(rng.random()<0.5 for _ in range(n))
            if t not in seen: seen.add(t); tuples.append(t)
    return [{k:bool(t[i]) for i,k in enumerate(keys)} for t in tuples]

def apply_combo(pm,combo,ctx):
    pm=copy.deepcopy(pm)
    for k,meta in REGISTRY.items():
        v=bool(combo.get(k,meta["default"]))
        if meta["requires_audio"] and not ctx.get("audio"): continue
        try: pm=meta["apply"](pm,v,ctx)
        except Exception: pass
    return pm

def run_eval(base_bytes,ref_bytes,combos,ctx):
    STATE.update({"running":True,"progress":0,"total":len(combos),
                  "results":[],"done":False,"error":"",
                  "started":time.time(),"finished":0})
    try: base_pm=_load_pm(base_bytes)
    except Exception as e:
        STATE["error"]=str(e); STATE["running"]=False
        STATE["done"]=True; return
    for i,c in enumerate(combos):
        STATE["current"]=json.dumps(c,ensure_ascii=False)
        try:
            vpm=apply_combo(base_pm,c,ctx)
            s=score_pair(_pm_bytes(vpm),ref_bytes)
            s["combo"]=c
            STATE["results"].append(s)
        except Exception as e:
            STATE["results"].append({"combo":c,"error":str(e),"score":-1})
        STATE["progress"]=i+1
    STATE["results"].sort(key=lambda x:-(x.get("score") if x.get("score") is not None else -1))
    STATE["running"]=False; STATE["done"]=True
    STATE["finished"]=time.time()

def install_live(app):
    from fastapi import UploadFile,File,Form
    from fastapi.responses import JSONResponse

    @app.get("/api/eval/registry")
    def api_registry():
        return JSONResponse({"registry":[
            {"key":m["key"],"label":m["label"],"default":m["default"],
             "requires_audio":m["requires_audio"]}
            for m in REGISTRY.values()]})

    @app.post("/api/eval/run")
    async def api_run(base:UploadFile=File(...),ref:UploadFile=File(...),
                      audio:UploadFile=File(None),
                      keys:str=Form("")):
        if STATE.get("running"):
            return JSONResponse({"error":"eval already running"})
        cb=await base.read(); rb=await ref.read()
        ctx={}
        ab=None
        if audio is not None:
            try: ab=await audio.read()
            except Exception: ab=None
        if ab:
            ta=tempo_from_audio(ab)
            if ta:
                ctx["bpm_audio"]=ta["bpm"]; ctx["curve_audio"]=ta["curve"]
                STATE["global_bpm"]=ta["bpm"]
            try:
                y,sr=librosa.load(io.BytesIO(ab),sr=22050,mono=True)
                ctx["audio"]=(y,sr)
            except Exception: pass
            STATE["has_audio"]=bool(ctx.get("audio"))
        else:
            STATE["has_audio"]=False
        try:
            tn=tempo_from_notes(_notes(_load_pm(cb)))
            if tn: ctx["bpm_notes"]=tn["bpm"]; ctx["curve_notes"]=tn["curve"]
        except Exception: pass
        if not ctx.get("bpm_audio") and ctx.get("bpm_notes"):
            STATE["global_bpm"]=ctx["bpm_notes"]
        try: ks=json.loads(keys) if keys else []
        except Exception: ks=[]
        if not ks: ks=[m["key"] for m in REGISTRY.values() if m["default"]]
        cl=enumerate_combos(ks)
        if not cl: return JSONResponse({"error":"empty combos"})
        threading.Thread(target=run_eval,args=(cb,rb,cl,ctx),daemon=True).start()
        return JSONResponse({"ok":True,"total":len(cl),
                             "has_audio":STATE["has_audio"]})

    @app.get("/api/eval/status")
    def api_status():
        return JSONResponse(STATE)
''', encoding="utf-8")
print("as_eval.py v3 written (shift-align + hungarian + pre/dynamic tempo)")
print("restart server.py to load (route already installed)")
