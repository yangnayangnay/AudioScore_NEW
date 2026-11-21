import os
import time
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import cache, jobs
from .config import CFG, TMP_DIR, WEB_DIR
from .engines import available_backends

app = FastAPI(title="AudioScore")
MAX_UPLOAD = 200 * 1024 * 1024
SUFFIX = "AudioScore.mid"

INSTRUMENTS = ["acoustic_piano","electric_piano","chromatic_percussion","organ",
               "acoustic_guitar","clean_electric_guitar","distorted_electric_guitar",
               "acoustic_bass","electric_bass","violin","viola","cello","contrabass",
               "orchestral_harp","timpani","string_ensemble","synth_strings","voice",
               "orchestra_hit","trumpet","trombone","tuba","french_horn","brass_section",
               "soprano_and_alto_sax","tenor_sax","baritone_sax","oboe","english_horn",
               "bassoon","clarinet","flutes","synth_lead","synth_pad","drums"]

def _result_name(orig_name, job_id):
    stem = os.path.splitext(orig_name or "")[0] if orig_name else ""
    return (stem + SUFFIX) if stem else (job_id + SUFFIX)

@app.get("/api/backends")
def api_backends():
    err = None
    try:
        bl = available_backends()
    except Exception as e:
        bl = []
        err = str(e)[:300]
    return {"backends": bl, "instruments": INSTRUMENTS, "backend_error": err}

@app.post("/api/batch")
async def api_batch(files: list[UploadFile] = File(...),
                    backend: str = Form("muscriptor"),
                    instruments: str = Form(""),
                    bpm: int = Form(None),
                    force_gpu: str = Form("1"),
                    skip_post: str = Form("0"),
                    auto_inst: str = Form("0"),
                    timeout_min: int = Form(30),
                    no_size_limit: str = Form("0"),
                    separate: str = Form("0"),
                    opt_dedup: str = Form("1"),
                    opt_short: str = Form("1"),
                    opt_vel: str = Form("1")):
    if not files:
        raise HTTPException(400, "no files")
    os.makedirs(TMP_DIR, exist_ok=True)
    inst_list = [s.strip() for s in instruments.split(",") if s.strip()] or None
    post_cfg = {"enabled": skip_post != "1", "dedup": opt_dedup == "1",
                "filter_short": opt_short == "1", "rebuild_velocity": opt_vel == "1"}
    fg = force_gpu == "1"
    ai = (auto_inst == "1") and inst_list is None
    try:
        tier = int(separate)
    except (TypeError, ValueError):
        tier = 0
    if tier not in (0, 1, 2, 3):
        tier = 0
    if tier > 0:
        inst_list = None
        ai = False
    try:
        _tm = int(timeout_min)
        engine_timeout = 0 if _tm == 0 else (_tm * 60 if _tm > 0 else None)
    except (TypeError, ValueError):
        engine_timeout = None
    out = []
    for f in files:
        try:
            ext = os.path.splitext(f.filename or "a.wav")[1] or ".wav"
            audio_path = os.path.join(TMP_DIR, "upload_" + os.urandom(6).hex() + ext)
            cap = None if no_size_limit == "1" else MAX_UPLOAD
            total = 0
            too_big = False
            with open(audio_path, "wb") as fp:
                while True:
                    chunk = await f.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if cap is not None and total > cap:
                        too_big = True
                        break
                    fp.write(chunk)
            if total == 0:
                try: os.remove(audio_path)
                except OSError: pass
                out.append({"file": f.filename, "error": "empty file"})
                continue
            if too_big:
                try: os.remove(audio_path)
                except OSError: pass
                out.append({"file": f.filename, "error": "file exceeds 200MB limit"})
                continue
            jid = jobs.create_job(audio_path, cache.audio_sha256(audio_path),
                                  backend=backend, instruments=inst_list,
                                  bpm=bpm, post_cfg=post_cfg, force_gpu=fg,
                                  orig_name=f.filename, auto_inst=ai,
                                  separate=tier,
                                  engine_timeout=engine_timeout)
            jobs.enqueue(jid)
            out.append({"file": f.filename, "job_id": jid})
        except Exception as e:
            out.append({"file": f.filename, "error": str(e)[:300]})
    return {"submitted": out}

@app.get("/api/queue")
def api_queue():
    return {"queue": jobs.list_jobs()}

@app.get("/api/jobs/{job_id}")
def api_status(job_id: str):
    j = jobs.get_job(job_id)
    if not j: raise HTTPException(404, "job not found")
    resp = {k: v for k, v in j.items() if k != "audio_path"}
    if j["status"] == "done":
        resp["result_url"] = "/api/result/" + job_id
        resp["result_name"] = _result_name(j.get("orig_name"), job_id)
    return resp

@app.get("/api/result/{job_id}")
def api_result(job_id: str):
    j = jobs.get_job(job_id)
    if not j or j["status"] != "done":
        raise HTTPException(404, "result not ready")
    return FileResponse(j["result_file"], media_type="audio/midi",
                        filename=_result_name(j.get("orig_name"), job_id))

@app.get("/api/zip")
def api_zip(ids: str):
    id_list = [s.strip() for s in ids.split(",") if s.strip()]
    pairs = []
    used = set()
    for jid in id_list:
        j = jobs.get_job(jid)
        if j and j["status"] == "done":
            name = _result_name(j.get("orig_name"), jid)
            stem = name[:-len(SUFFIX)]
            n, i = name, 2
            while n in used:
                n = stem + "(" + str(i) + ")" + SUFFIX
                i += 1
            used.add(n)
            pairs.append((j["result_file"], n))
    if not pairs:
        raise HTTPException(404, "no completed results to zip")
    zip_path = os.path.join(TMP_DIR, "batch_" + os.urandom(4).hex() + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, name in pairs:
            z.write(src, name)
    fname = "AudioScore_" + time.strftime("%Y%m%d_%H%M%S") + ".zip"
    return FileResponse(zip_path, media_type="application/zip", filename=fname)

app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
