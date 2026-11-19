import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .config import CFG, TMP_DIR, WEB_DIR
from .engines import available_backends

app = FastAPI(title="midi-bridge")
MAX_UPLOAD = 200 * 1024 * 1024  # 200MB

INSTRUMENTS = [  # 前端展示的常用乐器组(子集), 留空=MuScriptor 自动检测全部
    "piano", "bass", "drums", "guitar", "electric_guitar",
    "strings", "violin", "cello", "brass", "trumpet", "saxophone",
    "flute", "organ", "synth_lead", "synth_pad", "vocals",
]


@app.get("/api/backends")
def api_backends():
    return {"backends": available_backends(), "instruments": INSTRUMENTS}


@app.post("/api/jobs")
async def api_submit(file: UploadFile = File(...),
                     backend: str = Form("muscriptor"),
                     instruments: str = Form(""),
                     bpm: int | None = Form(None)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "文件超过 200MB")
    if not data:
        raise HTTPException(400, "空文件")

    os.makedirs(TMP_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "a.wav")[1] or ".wav"
    audio_path = os.path.join(TMP_DIR, f"upload_{os.urandom(6).hex()}{ext}")
    with open(audio_path, "wb") as f:
        f.write(data)

    from . import cache
    job_id = jobs.create_job(
        audio_path, cache.audio_sha256(audio_path),
        backend=backend,
        instruments=[s.strip() for s in instruments.split(",") if s.strip()] or None,
        bpm=bpm)
    asyncio_task = __import__("asyncio").create_task(jobs.execute(job_id))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def api_status(job_id: str):
    j = jobs.get_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    resp = {k: v for k, v in j.items() if k != "audio_path"}
    if j["status"] == "done":
        resp["result_url"] = f"/api/result/{job_id}"
    return resp


@app.get("/api/result/{job_id}")
def api_result(job_id: str):
    j = jobs.get_job(job_id)
    if not j or j["status"] != "done":
        raise HTTPException(404, "结果未就绪")
    return FileResponse(j["result_file"], media_type="audio/midi",
                        filename=f"transcription_{job_id}.mid")


# 静态前端(挂在最后, 不挡 API 路由)
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
