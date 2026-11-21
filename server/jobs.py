import asyncio
import inspect
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import cache, midi_io, postprocess
from .config import CFG, TMP_DIR, OUTPUT_DIR
from .engines import get_engine

_gpu_lock = asyncio.Lock()
_executor = ThreadPoolExecutor(max_workers=1)
_jobs = {}
_queue = []
_worker_task = None

def create_job(audio_path, audio_hash, backend, instruments, bpm,
               post_cfg=None, force_gpu=None, orig_name=None,
               auto_inst=False, engine_timeout=None, separate=0):
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "id": job_id, "status": "queued", "stage": "queued",
        "backend": backend, "created": time.time(), "elapsed": 0.0,
        "audio_path": audio_path, "audio_hash": audio_hash,
        "instruments": instruments, "bpm": bpm,
        "post_cfg": post_cfg, "force_gpu": force_gpu,
        "orig_name": orig_name, "auto_inst": auto_inst,
        "engine_timeout": engine_timeout, "separate": separate,
        "detected": None, "detected_by": None,
        "error": None, "stats": None, "result_file": None, "cached": False,
    }
    return job_id

def get_job(job_id):
    j = _jobs.get(job_id)
    if not j: return None
    if j["status"] in ("done","error"):
        j["elapsed"] = round(j.get("_elapsed_final",0.0),1)
    else:
        j["elapsed"] = round(time.time()-j["created"],1)
    return j

def list_jobs():
    out=[]
    for jid in list(_jobs.keys()):
        j=_jobs.get(jid)
        if j: out.append({"id":jid,"status":j["status"],"stage":j["stage"],
                          "elapsed":j["elapsed"],"cached":j["cached"]})
    return out

def enqueue(job_id):
    global _worker_task
    _queue.append(job_id)
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker())

async def _worker():
    while _queue:
        jid = _queue.pop(0)
        try:
            await execute(jid)
        except Exception as e:
            j=_jobs.get(jid)
            if j: j.update(status="error",stage="failed",error=str(e)[:1000])

def _cache_key(job, tier):
    backend_key = job["backend"] + (("@sep%d" % tier) if tier > 0 else "")
    return cache.make_key(job["audio_hash"], backend_key,
                          job["instruments"], job["bpm"],
                          job.get("post_cfg") or {})

def _finish(job, notes, dur, key, extra=None):
    jid = job["id"]
    out = os.path.join(OUTPUT_DIR, jid + ".mid")
    midi_io.notes_to_midi(notes, bpm=job["bpm"] or 120, path=out)
    cache.cache_put(key, out)
    stats = {"notes":len(notes),"duration":round(dur,1),
             "tracks":len({(n.program,n.is_drum) for n in notes})}
    if extra: stats.update(extra)
    job.update(status="done", stage="done", result_file=out,
               _elapsed_final=time.time()-job["created"], stats=stats)

def _engine_kwargs(job, eng):
    kwargs = {}
    try:
        sig = inspect.signature(eng.transcribe).parameters
        if "force_gpu" in sig: kwargs["force_gpu"] = job.get("force_gpu")
        if "timeout"   in sig: kwargs["timeout"]   = job.get("engine_timeout")
    except (TypeError, ValueError):
        pass
    return kwargs

def _run_stems(job, eng, kwargs, tier, post_cfg):
    from . import stem_sep
    jid = job["id"]
    job.update(stage="separating")
    stem_sep.separate(job["audio_path"], job["audio_hash"],
                      timeout=job.get("engine_timeout"))
    spec = stem_sep.TIER_STEMS[tier]
    names = list(spec.keys())
    total = len(names)
    all_notes = []
    dur = 0.0
    for i, sname in enumerate(names, 1):
        job.update(stage="stem %d/%d (%s)" % (i, total, sname))
        stem_wav = stem_sep.mix_stems(job["audio_hash"], tier, sname)
        raw_mid = os.path.join(TMP_DIR, "%s_%s_raw.mid" % (jid, sname))
        try:
            eng.transcribe(stem_wav, raw_mid, instruments=None,
                           bpm=job["bpm"], **kwargs)
            notes, d = midi_io.midi_to_notes(raw_mid)
            dur = max(dur, d)
        finally:
            if os.path.exists(raw_mid):
                try: os.remove(raw_mid)
                except OSError: pass
        if sname == "drums":
            for n in notes: n.is_drum = True
        elif sname == "bass":
            for n in notes: n.is_drum = False; n.program = 33
        elif sname == "vocals":
            for n in notes: n.is_drum = False; n.program = 52
        all_notes.extend(notes)
    job.update(stage="postprocess")
    if post_cfg.get("enabled", True):
        all_notes = postprocess.run_pipeline(all_notes, job["audio_path"], post_cfg)
    _finish(job, all_notes, dur, _cache_key(job, tier),
            extra={"stems": total})

def _run_sync(job):
    jid = job["id"]
    post_cfg = job.get("post_cfg") or CFG.get("postprocess",{}) or {}
    force_gpu = job.get("force_gpu")
    try:
        tier = int(job.get("separate") or 0)
    except (TypeError, ValueError):
        tier = 0
    if tier not in (0,1,2,3): tier = 0

    if job.get("auto_inst") and not job["instruments"]:
        job.update(stage="instrument detect")
        try:
            from . import instr_detect
            _w = (CFG.get("instrument_detect", {}) or {}).get("window_seconds", 60)
            d = instr_detect.detect_instruments(job["audio_path"], job["audio_hash"],
                                                window_seconds=_w)
            job["instruments"] = d["instruments"]
            job["detected"] = d["instruments"] or []
            job["detected_by"] = d["method"]
        except Exception:
            pass

    key = _cache_key(job, tier)
    hit = cache.cache_get(key)
    if hit:
        out = os.path.join(OUTPUT_DIR, jid + ".mid")
        os.replace(hit, out)
        notes, dur = midi_io.midi_to_notes(out)
        job.update(status="done", stage="done", cached=True,
                   result_file=out,
                   _elapsed_final=time.time()-job["created"],
                   stats={"notes":len(notes),"duration":round(dur,1),
                          "tracks":len({(n.program,n.is_drum) for n in notes})})
        return

    job.update(status="running", stage="model running")
    eng = get_engine(job["backend"])
    kwargs = _engine_kwargs(job, eng)

    if tier > 0:
        _run_stems(job, eng, kwargs, tier, post_cfg)
        return

    raw_mid = os.path.join(TMP_DIR, jid + "_raw.mid")
    try:
        eng.transcribe(job["audio_path"], raw_mid,
                       instruments=job["instruments"], bpm=job["bpm"], **kwargs)
    except Exception as e:
        if os.path.exists(raw_mid):
            try: os.remove(raw_mid)
            except OSError: pass
        raise
    job.update(stage="postprocess")
    notes, dur = midi_io.midi_to_notes(raw_mid)
    if post_cfg.get("enabled", True):
        notes = postprocess.run_pipeline(notes, job["audio_path"], post_cfg)
    _finish(job, notes, dur, key)

async def execute(job_id):
    job = _jobs.get(job_id)
    if not job: return
    async with _gpu_lock:
        if job["status"] != "queued": return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(_executor, _run_sync, job)
        except Exception as e:
            job.update(status="error", stage="failed", error=str(e)[:1000],
                       _elapsed_final=time.time()-job["created"])
