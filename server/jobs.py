import asyncio
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import cache, midi_io, postprocess
from .engines import get_engine
from .config import CFG, TMP_DIR, OUT_DIR

# 单 GPU → 推理必须串行
_gpu_lock = asyncio.Lock()
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}


def create_job(audio_path: str, audio_hash: str, backend: str,
               instruments: list[str] | None, bpm: int | None) -> str:
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "id": job_id, "status": "queued", "stage": "排队中",
        "backend": backend, "created": time.time(), "elapsed": 0.0,
        "audio_path": audio_path, "audio_hash": audio_hash,
        "instruments": instruments, "bpm": bpm,
        "error": None, "stats": None, "result_file": None, "cached": False,
    }
    return job_id


def get_job(job_id: str) -> dict | None:
    j = _jobs.get(job_id)
    if not j:
        return None
    if j["status"] in ("done", "error"):
        j["elapsed"] = round(j.get("_elapsed_final", 0.0), 1)
    else:
        j["elapsed"] = round(time.time() - j["created"], 1)
    return j


def _run_sync(job: dict, post_cfg: dict):
    """在 executor 线程里跑(阻塞式推理)"""
    jid = job["id"]

    # 1. 缓存命中 → 秒回
    key = cache.make_key(job["audio_hash"], job["backend"],
                         job["instruments"], job["bpm"], post_cfg)
    hit = cache.cache_get(key)
    if hit:
        out = os.path.join(OUT_DIR, f"{jid}.mid")
        os.replace(hit, out)
        notes, dur = midi_io.midi_to_notes(out)
        job.update(status="done", stage="缓存命中", cached=True,
                   result_file=out, _elapsed_final=time.time() - job["created"],
                   stats={"notes": len(notes), "duration": round(dur, 1),
                          "tracks": len({(n.program, n.is_drum) for n in notes})})
        return

    # 2. 引擎转写 → raw MIDI
    job.update(status="running", stage="模型推理中")
    eng = get_engine(job["backend"])
    raw_mid = os.path.join(TMP_DIR, f"{jid}_raw.mid")
    eng.transcribe(job["audio_path"], raw_mid,
                   instruments=job["instruments"], bpm=job["bpm"])

    # 3. 统一 Note → 后处理 → 最终 MIDI
    job.update(stage="后处理中")
    notes, dur = midi_io.midi_to_notes(raw_mid)
    notes = postprocess.run_pipeline(notes, job["audio_path"], post_cfg)
    out = os.path.join(OUT_DIR, f"{jid}.mid")
    bpm = job["bpm"] or 120
    midi_io.notes_to_midi(notes, bpm=bpm, path=out)

    cache.cache_put(key, out)
    job.update(status="done", stage="完成",
               result_file=out, _elapsed_final=time.time() - job["created"],
               stats={"notes": len(notes), "duration": round(dur, 1),
                      "tracks": len({(n.program, n.is_drum) for n in notes})})


async def execute(job_id: str):
    job = _jobs[job_id]
    post_cfg = CFG.get("postprocess", {})
    async with _gpu_lock:  # GPU 串行
        if job["status"] not in ("queued",):  # 已被处理/取消
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(_executor, _run_sync, job, post_cfg)
        except Exception as e:
            job.update(status="error", stage="失败", error=str(e)[:1000],
                       _elapsed_final=time.time() - job["created"])
