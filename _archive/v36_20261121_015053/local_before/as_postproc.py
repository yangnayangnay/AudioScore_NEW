# -*- coding: utf-8 -*-
"""as_postproc: pretty_midi based postproc on uploaded MIDI files.
POST /api/postproc?pp17=1&pp18=1 (multipart, file=<midi>)
returns postproc-ed midi as bytes."""
import io, math
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

def _load(midi_bytes):
    import pretty_midi
    return pretty_midi.PrettyMIDI(io.BytesIO(midi_bytes))

def _save(pm):
    buf = io.BytesIO()
    pm.write(buf)
    return buf.getvalue()

def _collect_notes(pm):
    """flatten notes from all instruments (preserving channel/ref)"""
    out = []
    for ci, inst in enumerate(pm.instruments):
        for ni, n in enumerate(inst.notes):
            out.append({"ci": ci, "ni": ni, "note": n,
                        "start": n.start, "end": n.end,
                        "pitch": n.pitch, "vel": n.velocity})
    return out

def pp17_cross_segment_merge(pm, overlap_s=0.02, gap_s=0.05):
    """merge notes of same pitch if: time-overlap OR gap<=50ms
    usually split-by-window artifacts from sliding-inference."""
    n = 0
    for inst in pm.instruments:
        notes = sorted(inst.notes, key=lambda x: (x.pitch, x.start))
        merged = []
        for x in notes:
            if merged:
                p = merged[-1]
                if p.pitch == x.pitch:
                    # overlap OR small gap
                    if x.start <= p.end + gap_s:
                        p.end = max(p.end, x.end)
                        p.velocity = int(max(p.velocity, x.velocity))
                        n += 1; continue
            merged.append(x)
        inst.notes = merged
    return n

def pp18_same_pitch_stitch(pm, gap_s=0.08):
    """stitch same-pitch notes separated by <80ms (model confidence flicker)"""
    n = 0
    for inst in pm.instruments:
        notes = sorted(inst.notes, key=lambda x: (x.pitch, x.start))
        merged = []
        for x in notes:
            if merged:
                p = merged[-1]
                if p.pitch == x.pitch and x.start - p.end <= gap_s \
                   and x.start - p.end > 0:
                    p.end = x.end
                    p.velocity = int((p.velocity + x.velocity)/2)
                    n += 1; continue
            merged.append(x)
        inst.notes = merged
    return n

def postproc_bytes(midi_bytes, pp17=True, pp18=True):
    pm = _load(midi_bytes)
    n17 = n18 = 0
    if pp17: n17 = pp17_cross_segment_merge(pm)
    if pp18: n18 = pp18_same_pitch_stitch(pm)
    return _save(pm), {"pp17": n17, "pp18": n18}

def install_live(app):
    from fastapi import UploadFile, File, Form
    from fastapi.responses import Response
    @app.post("/api/postproc")
    async def api_postproc(file: UploadFile = File(...),
                            pp17: int = Form(1), pp18: int = Form(1)):
        data = await file.read()
        try:
            out, stats = postproc_bytes(data, bool(pp17), bool(pp18))
            return Response(content=out, media_type="audio/midi",
                headers={"X-AS-PP17": str(stats["pp17"]),
                         "X-AS-PP18": str(stats["pp18"])})
        except Exception as e:
            return Response(content=data, media_type="audio/midi",
                headers={"X-AS-PPERR": str(e)[:80]})
