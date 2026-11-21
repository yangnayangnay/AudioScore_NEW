# -*- coding: utf-8 -*-
"""AudioScore_NEW one-click consolidator.
Ensures ALL recent features are present (idempotent: existing -> SKIP, missing -> apply):
engine(no-limit/heartbeat/gpu/kill-tree/guided-auto/lock), postprocess+UI toggle,
timeout selector, bilingual chips, live progress, job-resume, config(timeout=0)."""
from pathlib import Path
import re
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []

TEN = ("acoustic_piano, electric_piano, electric_bass, acoustic_bass, drums, "
       "voice, violin, flutes, clean_electric_guitar, distorted_electric_guitar")

# ================= FULL ENGINE SOURCE (only used if old engine detected) =================
ENGINE_SRC = r'''import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from .base import TranscriptionEngine
from ..config import CFG

_MUSCRIPTOR_INSTRUMENTS = {
    "acoustic_piano", "electric_piano", "chromatic_percussion", "organ",
    "acoustic_guitar", "clean_electric_guitar", "distorted_electric_guitar",
    "acoustic_bass", "electric_bass", "violin", "viola", "cello", "contrabass",
    "orchestral_harp", "timpani", "string_ensemble", "synth_strings", "voice",
    "orchestra_hit", "trumpet", "trombone", "tuba", "french_horn", "brass_section",
    "soprano_and_alto_sax", "tenor_sax", "baritone_sax", "oboe", "english_horn",
    "bassoon", "clarinet", "flutes", "synth_lead", "synth_pad", "drums",
}

_INSTRUMENT_MAP = {
    "piano": ["acoustic_piano", "electric_piano"],
    "bass": ["acoustic_bass", "electric_bass"],
    "electric bass": ["electric_bass"],
    "electric_bass": ["electric_bass"],
    "e-bass": ["electric_bass"],
    "5-string bass": ["electric_bass"],
    "5-string electric bass": ["electric_bass"],
    "drums": ["drums"],
    "drum": ["drums"],
    "drum kit": ["drums"],
    "drum set": ["drums"],
    "drum score": ["drums"],
    "guitar": ["acoustic_guitar"],
    "acoustic guitar": ["acoustic_guitar"],
    "electric guitar": ["clean_electric_guitar", "distorted_electric_guitar"],
    "electric_guitar": ["clean_electric_guitar", "distorted_electric_guitar"],
    "strings": ["string_ensemble"],
    "violin": ["violin"],
    "viola": ["viola"],
    "cello": ["cello"],
    "brass": ["brass_section", "trumpet", "trombone", "tuba", "french_horn"],
    "trumpet": ["trumpet"],
    "saxophone": ["soprano_and_alto_sax", "tenor_sax", "baritone_sax"],
    "flute": ["flutes"],
    "organ": ["organ"],
    "synth_lead": ["synth_lead"],
    "synth_pad": ["synth_pad"],
    "vocals": ["voice"],
    "vocal": ["voice"],
    "voice": ["voice"],
    "soprano": ["voice"],
    "alto": ["voice"],
    "\u94a2\u7434": ["acoustic_piano", "electric_piano"],
    "\u8d1d\u65af": ["acoustic_bass", "electric_bass"],
    "\u7535\u8d1d\u65af": ["electric_bass"],
    "\u4e94\u5f26\u7535\u8d1d\u65af": ["electric_bass"],
    "\u9f13": ["drums"],
    "\u9f13\u7ec4": ["drums"],
    "\u67b6\u5b50\u9f13": ["drums"],
    "\u9f13\u8c31": ["drums"],
    "\u5409\u4ed6": ["acoustic_guitar"],
    "\u7535\u5409\u4ed6": ["clean_electric_guitar", "distorted_electric_guitar"],
    "\u6728\u5409\u4ed6": ["acoustic_guitar"],
    "\u5c0f\u63d0\u7434": ["violin"],
    "\u4e2d\u63d0\u7434": ["viola"],
    "\u5927\u63d0\u7434": ["cello"],
    "\u5f26\u4e50": ["string_ensemble"],
    "\u957f\u7b1b": ["flutes"],
    "\u7b1b\u5b50": ["flutes"],
    "\u8428\u514b\u65af": ["soprano_and_alto_sax", "tenor_sax", "baritone_sax"],
    "\u5c0f\u53f7": ["trumpet"],
    "\u94dc\u7ba1": ["brass_section", "trumpet", "trombone", "tuba", "french_horn"],
    "\u7ba1\u98ce\u7434": ["organ"],
    "\u4eba\u58f0": ["voice"],
    "\u5973\u9ad8\u97f3": ["voice"],
    "\u5973\u58f0": ["voice"],
    "\u7537\u58f0": ["voice"],
    "\u4e3b\u5531": ["voice"],
}

_JOB_LOCK = threading.Lock()
_LATEST = {"line": "", "ts": 0.0}
_LOG_READY = False


def _log():
    global _LOG_READY
    lg = logging.getLogger("muscriptor")
    if not _LOG_READY:
        log_dir = Path(__file__).resolve().parents[2] / "logs"
        log_dir.mkdir(exist_ok=True)
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
        fh = logging.FileHandler(log_dir / "muscriptor.log", encoding="utf-8")
        fh.setFormatter(fmt)
        lg.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        lg.addHandler(sh)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        _LOG_READY = True
    return lg


class MuscriptorEngine(TranscriptionEngine):
    """Call MuScriptor through its official CLI (subprocess mode)."""

    def __init__(self):
        super().__init__()
        c = CFG.get("muscriptor", {})
        self.model = c.get("model", "large")
        self.device = c.get("device") or c.get("torch_backend") or ""
        self.timeout = int(c.get("timeout", 3600))
        self.batch_size = c.get("batch_size")
        self.no_prelude_forcing = bool(c.get("no_prelude_forcing", False))
        self.beam_size = c.get("beam_size")
        ai = c.get("auto_instruments") or []
        if isinstance(ai, str):
            ai = [x.strip() for x in ai.split(",") if x.strip()]
        self.auto_instruments = [str(x).strip().lower() for x in ai]
        self.pp_cfg = dict(c.get("postprocess", {}) or {})
        _log().info("engine init: model=%s device=%r batch=%r timeout=%ss (0=no limit) guided_auto=%s",
                    self.model, self.device, self.batch_size, self.timeout,
                    ",".join(self.auto_instruments) or "(off)")

    def get_status(self):
        return dict(_LATEST)

    def _cli_prefix(self):
        if shutil.which("muscriptor"):
            return ["muscriptor"]
        try:
            import muscriptor  # noqa: F401
            return [sys.executable, "-m", "muscriptor"]
        except ImportError:
            return None

    def is_available(self):
        return self._cli_prefix() is not None

    def _translate_instruments(self, instruments):
        if not instruments:
            return None
        out = []
        for name in instruments:
            key = str(name).strip().lower()
            plain = re.sub(r"[^\x20-\x7e]", "", key).strip()
            for k in (key, plain):
                if k in _INSTRUMENT_MAP:
                    out += _INSTRUMENT_MAP[k]
                    break
            else:
                if key in _MUSCRIPTOR_INSTRUMENTS:
                    out.append(key)
                elif plain in _MUSCRIPTOR_INSTRUMENTS:
                    out.append(plain)
        out = list(dict.fromkeys(out))
        return ",".join(out) if out else None

    def _resolve_instruments(self, instruments):
        inst = self._translate_instruments(instruments)
        if inst:
            return inst, "user-selected"
        if self.auto_instruments:
            return ",".join(self.auto_instruments), "guided-auto"
        return None, "raw-auto"

    def _build_cmd(self, audio, out, instruments=None, bpm=None):
        cmd = list(self._cli_prefix())
        cmd += ["transcribe", audio, "-o", out, "--model", str(self.model),
                "--detect-tempo", "false"]
        if self.device:
            cmd += ["--device", self.device]
        if self.batch_size:
            cmd += ["--batch-size", str(int(self.batch_size))]
            if self.no_prelude_forcing:
                cmd += ["--no-prelude-forcing"]
        if self.beam_size:
            cmd += ["--beam-size", str(int(self.beam_size))]
        inst, _mode = self._resolve_instruments(instruments)
        if inst:
            cmd += ["--instruments", inst]
        if bpm:
            cmd += ["--bpm", str(int(bpm))]
        return cmd

    def _log_midi_summary(self, mid_path):
        try:
            import pretty_midi
            pm = pretty_midi.PrettyMIDI(mid_path)
            lines = []
            total = 0
            for i, inst in enumerate(pm.instruments):
                nm = pretty_midi.program_to_instrument_name(inst.program)
                lines.append("track %02d | program %3d | %-28s | drums=%-5s | notes=%d"
                             % (i, inst.program, nm, inst.is_drum, len(inst.notes)))
                total += len(inst.notes)
            _log().info("midi summary: %d track(s), %d notes\n%s",
                        len(pm.instruments), total, "\n".join(lines))
        except Exception as e:
            _log().warning("midi summary failed: %s", e)

    @staticmethod
    def _kill_tree(proc):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, text=True)
            else:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def transcribe(self, audio_path, out_mid_path, instruments=None, bpm=None,
                   timeout=None, post=None):
        lg = _log()
        tmo = self.timeout if timeout is None else int(timeout)
        if tmo < 0:
            tmo = 0
        inst_cli, inst_mode = self._resolve_instruments(instruments)
        cmd = self._build_cmd(audio_path, out_mid_path, instruments, bpm)
        lg.info("---- job start ----")
        lg.info("audio      : %s", audio_path)
        lg.info("out        : %s", out_mid_path)
        lg.info("inst (web) : %r  [mode=%s]", instruments, inst_mode)
        lg.info("inst (cli) : %s", inst_cli or "(none)")
        lg.info("bpm        : %r", bpm)
        lg.info("time limit : %s", ("%ss" % tmo) if tmo > 0 else "NO LIMIT")
        lg.info("command    : %s", " ".join(cmd))
        if _JOB_LOCK.locked():
            lg.info("another job still running -> this job QUEUED")
        with _JOB_LOCK:
            lg.info("lock acquired, starting subprocess")
            return self._run(cmd, out_mid_path, lg, tmo, post)

    def _run(self, cmd, out_mid_path, lg, tmo, post):
        env = os.environ.copy()
        t0 = time.time()
        _LATEST["line"] = ""
        _LATEST["ts"] = 0.0
        tail = deque(maxlen=40)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=env)
        lg.info("process started pid=%s (cli output streams below)", proc.pid)

        def reader():
            for line in proc.stdout:
                line = (line or "").rstrip()
                if not line:
                    continue
                tail.append(line)
                _LATEST["line"] = line
                _LATEST["ts"] = time.time()
                lg.info("[cli] %s", line)

        th = threading.Thread(target=reader, daemon=True)
        th.start()
        rc = None
        try:
            while True:
                rc = proc.poll()
                if rc is not None:
                    break
                el = time.time() - t0
                if tmo and tmo > 0 and el > tmo:
                    self._kill_tree(proc)
                    lg.error("TIMEOUT after %.0fs (limit %ss) -> process tree killed",
                             el, tmo)
                    raise RuntimeError("MuScriptor timeout (%ss)" % tmo)
                time.sleep(10)
                gap = (time.time() - _LATEST["ts"]) if _LATEST["ts"] else el
                gpu = ""
                try:
                    _g = subprocess.run(
                        ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                         "--format=csv,noheader"],
                        capture_output=True, text=True, timeout=5)
                    if _g.returncode == 0 and _g.stdout.strip():
                        gpu = ", gpu " + _g.stdout.strip().splitlines()[0].strip()
                except Exception:
                    pass
                lg.info("heartbeat: alive, %.0fs elapsed%s, last cli output %.0fs ago%s",
                        el, "" if tmo > 0 else ", NO LIMIT", gap, gpu)
        finally:
            th.join(timeout=3)
        dt = time.time() - t0
        if rc != 0:
            lg.error("FAILED code=%s elapsed=%.1fs", rc, dt)
            tailtxt = "\n".join(list(tail)[-25:])
            lg.error("cli tail:\n%s", tailtxt)
            raise RuntimeError("MuScriptor failed (code %s):\n%s" % (rc, tailtxt))
        if not os.path.exists(out_mid_path):
            lg.error("FAILED: no midi produced, elapsed=%.1fs", dt)
            raise RuntimeError("MuScriptor produced no MIDI file")
        self._log_midi_summary(out_mid_path)
        _ui = self.pp_cfg.get("enabled", True) if post is None else bool(post)
        if _ui:
            try:
                from .postprocess import run_postprocess
                lg.info("postprocess: ON (ui=%s)", post)
                run_postprocess(out_mid_path, self.pp_cfg, lg)
            except Exception as _e:
                lg.warning("postprocess skipped: %s", _e)
        else:
            lg.info("postprocess: OFF (ui flag)")
        lg.info("SUCCESS in %.1fs", dt)
        return out_mid_path
'''

POSTPROCESS_SRC = '''import logging
import pretty_midi

log = logging.getLogger("muscriptor.post")

_RANGES = {
    "piano": (21, 108), "chromperc": (48, 96), "organ": (21, 96),
    "guitar": (40, 93), "bass": (28, 72), "strings": (36, 103),
    "brass": (46, 100), "sax": (48, 96), "pipe": (48, 100),
    "synth": (21, 108), "drums": None,
}
_PROG = {"piano": 0, "guitar": 24, "bass": 33, "strings": 48,
         "brass": 56, "sax": 65, "pipe": 73, "organ": 16}


def _family(prog, is_drum):
    if is_drum:
        return "drums"
    if prog < 8:
        return "piano"
    if prog < 16:
        return "chromperc"
    if prog < 24:
        return "organ"
    if prog < 32:
        return "guitar"
    if prog < 40:
        return "bass"
    if prog < 56:
        return "strings"
    if prog < 64:
        return "brass"
    if prog < 72:
        return "sax"
    if prog < 80:
        return "pipe"
    return "synth"


def _merge_fragments(notes, merge_gap, min_len):
    notes = sorted(notes, key=lambda n: n.start)
    out = []
    for n in notes:
        if out and out[-1].pitch == n.pitch and n.start - out[-1].end <= merge_gap:
            out[-1].end = max(out[-1].end, n.end)
            continue
        out.append(n)
    return [n for n in out if (n.end - n.start) >= min_len]


def _range_report(inst):
    fam = _family(inst.program, inst.is_drum)
    rng = _RANGES.get(fam)
    if not rng:
        return fam, 0, 0
    lo, hi = rng
    total = len(inst.notes)
    bad = sum(1 for n in inst.notes if n.pitch < lo or n.pitch > hi)
    return fam, bad, total


def run_postprocess(mid_path, cfg, parent_log):
    if not cfg.get("enabled", True):
        parent_log.info("postprocess disabled")
        return
    merge_gap = float(cfg.get("merge_gap", 0.08))
    min_note = float(cfg.get("min_note", 0.05))
    range_fix = bool(cfg.get("range_fix", False))
    iso_merge = bool(cfg.get("isolated_merge", True))
    iso_min = int(cfg.get("isolated_min_notes", 3))

    pm = pretty_midi.PrettyMIDI(str(mid_path))
    log.info("---- postprocess start: %s", mid_path)

    for i, inst in enumerate(pm.instruments):
        before = len(inst.notes)
        inst.notes = _merge_fragments(inst.notes, merge_gap, min_note)
        if before != len(inst.notes):
            log.info("track %02d hygiene: %d -> %d notes (merge/stub-drop)",
                     i, before, len(inst.notes))

    for i, inst in enumerate(pm.instruments):
        fam, bad, total = _range_report(inst)
        if total and bad / total > 0.3:
            log.info("track %02d range WARN: family=%s %d/%d notes out of range",
                     i, fam, bad, total)
            if range_fix and fam not in ("piano", "synth", "drums"):
                cands = []
                for f, rng in _RANGES.items():
                    if f == "drums":
                        continue
                    lo, hi = rng
                    cov = sum(1 for n in inst.notes if lo <= n.pitch <= hi)
                    cands.append((cov / total, f))
                cands.sort(reverse=True)
                best_cov, best_fam = cands[0]
                cur_cov = 1 - bad / total
                if best_cov > cur_cov + 0.3 and best_fam in _PROG:
                    log.info("track %02d range FIX: %s -> %s (coverage %.0f%%)",
                             i, fam, best_fam, best_cov * 100)
                    inst.program = _PROG[best_fam]

    if iso_merge and len(pm.instruments) > 1:
        dom = max(pm.instruments, key=lambda x: len(x.notes))
        for inst in pm.instruments:
            if inst is dom or inst.is_drum:
                continue
            if 0 < len(inst.notes) < iso_min:
                log.info("isolated track FIX: %s (%d notes) -> %s",
                         pretty_midi.program_to_instrument_name(inst.program),
                         len(inst.notes),
                         pretty_midi.program_to_instrument_name(dom.program))
                dom.notes.extend(inst.notes)
                inst.notes = []

    pm.instruments = [x for x in pm.instruments if x.notes]

    fams = {_family(x.program, x.is_drum) for x in pm.instruments}
    fams.discard("drums")
    if len(fams) >= 6:
        log.info("coexistence WARN: %d distinct families -> %s",
                 len(fams), sorted(fams))

    pm.write(str(mid_path))
    log.info("---- postprocess done: %d tracks remain", len(pm.instruments))
'''

RESUME_JS = """
<script>
(function(){
  var KEY='as_last_job';
  try{
    var _f=window.fetch;
    window.fetch=function(u,o){
      return _f(u,o).then(function(r){
        try{
          var s=(typeof u==='string')?u:(u&&u.url)||'';
          if(s.indexOf('/api/jobs')>=0&&o&&(o.method||'GET').toUpperCase()==='POST'){
            r.clone().json().then(function(j){
              var id=j&&(j.id||j.job_id); if(id) localStorage.setItem(KEY,id);
            }).catch(function(){});
          }
        }catch(e){}
        return r;
      });
    };
  }catch(e){}
  function $(id){return document.getElementById(id);}
  function banner(){
    var b=$('as_resume_bar');
    if(!b){b=document.createElement('div');b.id='as_resume_bar';
      b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;background:#1f6feb;color:#fff;padding:8px 14px;font-size:14px;display:flex;gap:12px;align-items:center';
      document.body.appendChild(b);}
    return b;
  }
  function clearAll(){try{localStorage.removeItem(KEY);}catch(e){}var b=$('as_resume_bar');if(b)b.remove();}
  function poll(id){
    var b=banner();
    b.innerHTML='<span>\\u21bb \\u68c0\\u6d4b\\u5230\\u672a\\u5b8c\\u6210\\u4efb\\u52a1 '+id.slice(0,8)+' \\u2014 \\u6b63\\u5728\\u6062\\u590d\\u76d1\\u63a7</span>';
    var x=document.createElement('span');x.textContent='\\u2716 \\u4e0d\\u518d\\u76d1\\u63a7';
    x.style.cssText='cursor:pointer;opacity:.85';x.onclick=clearAll;b.appendChild(x);
    var t=setInterval(function(){
      fetch('/api/jobs/'+id).then(function(r){
        if(r.status===404){clearInterval(t);clearAll();
          banner().innerHTML='\\u26a0 \\u670d\\u52a1\\u5df2\\u91cd\\u542f\\uff0c\\u539f\\u4efb\\u52a1\\u5df2\\u4e22\\u5931';
          return null;}
        return r.json();
      }).then(function(j){
        if(!j)return;
        if(j.status==='done'){clearInterval(t);clearAll();
          var bb=banner();bb.innerHTML='';
          var lk=document.createElement('a');lk.href=j.download_url||'#';
          lk.textContent='\\u2714 \\u4efb\\u52a1\\u5b8c\\u6210\\uff0c\\u70b9\\u51fb\\u4e0b\\u8f7d';
          lk.style.cssText='color:#fff;text-decoration:underline;font-weight:600';
          bb.appendChild(lk);
          var xx=document.createElement('span');xx.textContent='\\u2716 \\u5173\\u95ed';
          xx.style.cssText='cursor:pointer;opacity:.85';xx.onclick=clearAll;bb.appendChild(xx);
          var pb=$('pbar');if(pb)pb.style.width='100%';return;}
        if(j.status==='error'){clearInterval(t);clearAll();
          banner().innerHTML='\\u2716 \\u4efb\\u52a1\\u5931\\u8d25';return;}
        var sm=$('smeta');
        var meta='\\u5df2\\u7528\\u65f6 '+(j.elapsed||0)+'s';
        if(j.engine_line)meta+=' | \\u5f15\\u64ce: '+String(j.engine_line).slice(0,70);
        if(sm)sm.textContent=meta;
        var pb2=$('pbar');
        if(pb2){var pct=j.status==='running'?Math.min(88,5+83*Math.min(1,(j.elapsed||0)/480)):5;pb2.style.width=pct+'%';}
      }).catch(function(){});
    },2000);
  }
  function boot(){var id=null;try{id=localStorage.getItem(KEY);}catch(e){}if(id)poll(id);}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}
})();
</script>
"""


def rep(fname, alts, label, skip=None):
    p = ROOT / fname
    s = p.read_text(encoding="utf-8")
    if skip and skip in s:
        ok.append(label + " [SKIP]")
        return
    for old, new in alts:
        if old in s:
            p.write_text(s.replace(old, new, 1), encoding="utf-8")
            ok.append(label)
            return
    fail.append(label + " : anchor missing in " + fname)


# ================= 1. ENGINE =================
ENG = ROOT / "server" / "engines" / "muscriptor.py"
es = ENG.read_text(encoding="utf-8")
if "guided-auto" not in es:
    ENG.write_text(ENGINE_SRC, encoding="utf-8")
    ok.append("engine: FULL REWRITE (old engine detected -> all features baked in)")
else:
    ok.append("engine: new version present")

rep("server/engines/muscriptor.py", [
    ("self.auto_instruments = [str(x).strip().lower() for x in ai]\n",
     "self.auto_instruments = [str(x).strip().lower() for x in ai]\n"
     "        self.pp_cfg = dict(CFG.get(\"muscriptor\", {}).get(\"postprocess\", {}) or {})\n"),
], "engine: pp_cfg init", skip="pp_cfg")

rep("server/engines/muscriptor.py", [
    ("timeout=None):", "timeout=None, post=None):"),
], "engine: transcribe post param", skip="post=None")

rep("server/engines/muscriptor.py", [
    ("def _run(self, cmd, out_mid_path, lg, tmo):",
     "def _run(self, cmd, out_mid_path, lg, tmo, post):"),
], "engine: _run post param", skip="lg, tmo, post")

rep("server/engines/muscriptor.py", [
    ("return self._run(cmd, out_mid_path, lg, tmo)",
     "return self._run(cmd, out_mid_path, lg, tmo, post)"),
], "engine: pass post to _run", skip="_run(cmd, out_mid_path, lg, tmo, post)")

rep("server/engines/muscriptor.py", [
    ('            from .postprocess import run_postprocess\n'
     '            run_postprocess(out_mid_path, self.pp_cfg, lg)\n'
     '        except Exception as _e:\n'
     '            lg.warning("postprocess skipped: %s", _e)',
     '            from .postprocess import run_postprocess\n'
     '            lg.info("postprocess: ON (ui=%s)", post)\n'
     '            run_postprocess(out_mid_path, self.pp_cfg, lg)\n'
     '        except Exception as _e:\n'
     '            lg.warning("postprocess skipped: %s", _e)\n'
     '        else:\n'
     '            lg.info("postprocess: OFF (ui flag)")'),
], "engine: conditional postprocess (ui toggle)", skip="postprocess: ON")

# ================= 2. POSTPROCESS MODULE =================
PP = ROOT / "server" / "engines" / "postprocess.py"
if PP.exists():
    ok.append("postprocess.py [SKIP exists]")
else:
    PP.write_text(POSTPROCESS_SRC, encoding="utf-8")
    ok.append("postprocess.py created")

# ================= 3. MAIN.PY =================
rep("server/main.py", [
    ("bpm: int | None = Form(None)):",
     "bpm: int | None = Form(None),\n"
     "                     timeout: int | None = Form(None)):"),
], "main.py: timeout Form param", skip="timeout: int | None = Form(None)")

rep("server/main.py", [
    ("timeout: int | None = Form(None)):",
     "timeout: int | None = Form(None),\n"
     "                     post: str | None = Form(None)):"),
], "main.py: post Form param", skip="post: str | None = Form(None)")

rep("server/main.py", [
    ("bpm=bpm)",
     "bpm=bpm, timeout=timeout)"),
], "main.py: pass timeout", skip="timeout=timeout")

rep("server/main.py", [
    ("bpm=bpm, timeout=timeout)",
     "bpm=bpm, timeout=timeout,\n"
     "                   post=(None if post is None else post in ('1', 'true', 'on')))"),
], "main.py: pass post", skip="post=(None if post")

rep("server/main.py", [
    ('    resp = {k: v for k, v in j.items() if k != "audio_path"}',
     '    resp = {k: v for k, v in j.items() if k != "audio_path"}\n'
     '    if j.get("status") == "running" and j.get("backend") == "muscriptor":\n'
     '        try:\n'
     '            from .engines import get_engine\n'
     '            _st = getattr(get_engine("muscriptor"), "get_status", None)\n'
     '            if callable(_st):\n'
     '                resp["engine_line"] = (_st() or {}).get("line", "")\n'
     '        except Exception:\n'
     '            pass'),
], "main.py: expose engine live line", skip="engine_line")

# ================= 4. JOBS.PY =================
rep("server/jobs.py", [
    ("instruments: list[str] | None, bpm: int | None) -> str:",
     "instruments: list[str] | None, bpm: int | None,\n"
     "               timeout: int | None = None) -> str:"),
], "jobs.py: create_job timeout param", skip="timeout: int | None = None")

rep("server/jobs.py", [
    ("timeout: int | None = None) -> str:",
     "timeout: int | None = None,\n               post: bool | None = None) -> str:"),
], "jobs.py: create_job post param", skip="post: bool | None = None")

rep("server/jobs.py", [
    ('"instruments": instruments, "bpm": bpm,',
     '"instruments": instruments, "bpm": bpm, "timeout": timeout,'),
], "jobs.py: store timeout", skip='"timeout": timeout')

rep("server/jobs.py", [
    ('"bpm": bpm, "timeout": timeout,',
     '"bpm": bpm, "timeout": timeout, "post": post,'),
], "jobs.py: store post", skip='"post": post')

rep("server/jobs.py", [
    ('    eng.transcribe(job["audio_path"], raw_mid,\n'
     '                   instruments=job["instruments"], bpm=job["bpm"])',
     '    import inspect as _insp\n'
     '    _kw = dict(instruments=job["instruments"], bpm=job["bpm"])\n'
     '    _sig = _insp.signature(eng.transcribe).parameters\n'
     '    if "timeout" in _sig:\n'
     '        _kw["timeout"] = job.get("timeout")\n'
     '    if "post" in _sig:\n'
     '        _kw["post"] = job.get("post")\n'
     '    eng.transcribe(job["audio_path"], raw_mid, **_kw)'),
], "jobs.py: forward timeout+post (signature-probed)", skip='_kw["timeout"]')

rep("server/jobs.py", [
    ('    if "timeout" in _insp.signature(eng.transcribe).parameters:\n'
     '        _kw["timeout"] = job.get("timeout")',
     '    if "timeout" in _insp.signature(eng.transcribe).parameters:\n'
     '        _kw["timeout"] = job.get("timeout")\n'
     '    if "post" in _insp.signature(eng.transcribe).parameters:\n'
     '        _kw["post"] = job.get("post")'),
], "jobs.py: forward post (existing probe)", skip='_kw["post"]')

# ================= 5. INDEX.HTML =================
ZH_MAP = (
    "const ZH = {piano:'\u94a2\u7434', bass:'\u8d1d\u65af', drums:'\u67b6\u5b50\u9f13', "
    "guitar:'\u5409\u4ed6', electric_guitar:'\u7535\u5409\u4ed6', strings:'\u5f26\u4e50', "
    "violin:'\u5c0f\u63d0\u7434', cello:'\u5927\u63d0\u7434', brass:'\u94dc\u7ba1', "
    "trumpet:'\u5c0f\u53f7', saxophone:'\u8428\u514b\u65af', flute:'\u957f\u7b1b', "
    "organ:'\u7ba1\u98ce\u7434', synth_lead:'\u5408\u6210\u4e3b\u97f3', "
    "synth_pad:'\u5408\u6210\u94fa\u5e95', vocals:'\u4eba\u58f0'};\n"
)
PP1 = '<div class="opt"><input type="checkbox" id="pp1" checked>'

rep("web/index.html", [
    ("const $ = id => document.getElementById(id);",
     "const $ = id => document.getElementById(id);\n" + ZH_MAP),
], "html: ZH instrument label map", skip="const ZH =")

rep("web/index.html", [
    ("c.className = 'chip'; c.textContent = name;",
     "c.className = 'chip'; c.dataset.value = name;\n"
     "c.textContent = (ZH[name] ? ZH[name] + ' ' : '') + name;"),
], "html: bilingual chips (value kept clean)", skip="dataset.value")

rep("web/index.html", [
    (".map(c => c.textContent).join(','));",
     ".map(c => c.dataset.value || c.textContent).join(','));"),
], "html: submit value from dataset", skip="dataset.value || c.textContent")

rep("web/index.html", [
    (PP1,
     '<label>\u65f6\u95f4\u4e0a\u9650\uff08\u8d85\u65f6\u81ea\u52a8\u7ec8\u6b62\u8be5\u4efb\u52a1\uff09</label>\n'
     '<select id="tmo">\n'
     '  <option value="">\u9ed8\u8ba4\uff08config.yaml\uff09</option>\n'
     '  <option value="600">10 \u5206\u949f</option>\n'
     '  <option value="1800">30 \u5206\u949f</option>\n'
     '  <option value="3600">1 \u5c0f\u65f6</option>\n'
     '  <option value="7200">2 \u5c0f\u65f6</option>\n'
     '  <option value="0">\u65e0\u9650\u5236</option>\n'
     '</select>\n' + PP1),
], "html: timeout selector UI", skip='id="tmo"')

rep("web/index.html", [
    ("if (bpm) fd.append('bpm', bpm);",
     "if (bpm) fd.append('bpm', bpm);\n"
     "const tmo = $('tmo').value;\n"
     "if (tmo !== '') fd.append('timeout', tmo);"),
], "html: send timeout with form", skip="fd.append('timeout'")

rep("web/index.html", [
    ("if (bpm) fd.append('bpm', bpm);",
     "if (bpm) fd.append('bpm', bpm);\n"
     "fd.append('post', $('ppc') && $('ppc').checked ? '1' : '0');"),
], "html: send post flag with form", skip="fd.append('post'")

rep("web/index.html", [
    ("$('pbar').style.width =\n"
     "({ queued: 5, running: 40, done: 100, error: 100 })[j.status] + '%';\n"
     "$('smeta').textContent = '\u5df2\u7528\u65f6 ' + j.elapsed + 's';",
     "let pct = ({ queued: 5, done: 100, error: 100 })[j.status];\n"
     "if (j.status === 'running') {\n"
     "  const exp = j.backend === 'muscriptor' ? 480 : 30;\n"
     "  pct = Math.min(88, 5 + 83 * Math.min(1, j.elapsed / exp));\n"
     "}\n"
     "$('pbar').style.width = pct + '%';\n"
     "let meta = '\u5df2\u7528\u65f6 ' + j.elapsed + 's';\n"
     "if (j.engine_line !== undefined) {\n"
     "  meta += ' \uff5c \u5f15\u64ce: ' + (j.engine_line || '\u2026').slice(0, 80);\n"
     "}\n"
     "$('smeta').textContent = meta;"),
], "html: progress creep + live engine line", skip="engine_line")

rep("web/index.html", [
    (PP1,
     '<div class="opt"><input type="checkbox" id="ppc" checked>'
     '<label>\u97f3\u7b26\u6e05\u7406\uff08\u5408\u5e76\u788e\u97f3/\u97f3\u57df\u68c0\u67e5/\u5b64\u7acb\u8f68\u56de\u6536\uff09 Note cleanup</label></div>\n'
     + PP1),
], "html: note-cleanup toggle checkbox", skip='id="ppc"')

rep("web/index.html", [
    ("</body>", RESUME_JS + "\n</body>"),
], "html: job-resume banner script", skip="as_last_job")

# ================= 6. CONFIG =================
f = ROOT / "config.yaml"
lines = f.read_text(encoding="utf-8").splitlines()
mi = next((i for i, l in enumerate(lines) if re.match(r"^muscriptor:\s*$", l)), None)
if mi is None:
    fail.append("config: no muscriptor: section found")
else:
    j = mi + 1
    while j < len(lines) and (lines[j].startswith((" ", "\t")) or lines[j].strip() == ""):
        j += 1
    sec = lines[mi + 1:j]

    def has(key):
        return any(re.match(r"^\s*%s\s*:" % re.escape(key), l) for l in sec)

    inserts = []
    if not has("model"):
        inserts.append("  model: large")
    if not has("device"):
        inserts.append("  device: cuda")
    if not has("auto_instruments"):
        inserts.append("  auto_instruments: [%s]" % TEN)
    if not has("postprocess"):
        inserts += ["  postprocess:", "    enabled: true", "    merge_gap: 0.08",
                    "    min_note: 0.05", "    range_warn: true",
                    "    range_fix: false", "    isolated_merge: true",
                    "    isolated_min_notes: 3"]
    tset = False
    for k in range(mi + 1, j):
        if re.match(r"^\s*timeout\s*:", lines[k]):
            lines[k] = "  timeout: 0  # 0 = no limit (UI selector can override per job)"
            tset = True
    if not tset:
        inserts.append("  timeout: 0  # 0 = no limit (UI selector can override per job)")
    lines[j:j] = inserts
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok.append("config: timeout=0(no-limit) + guided-auto + postprocess block ensured")

import yaml  # noqa: E402
d = yaml.safe_load(f.read_text(encoding="utf-8"))
m = d.get("muscriptor", {})
print()
print("== config check ==")
print("  timeout          :", m.get("timeout"), "(0 = no limit)")
print("  auto_instruments :", len(m.get("auto_instruments") or []), "instruments")
print("  postprocess      :", m.get("postprocess"))

# ================= 7. COMPILE + SUMMARY =================
print()
print("==== PATCH RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("=======================")

for fn in ("server/main.py", "server/jobs.py",
           "server/engines/muscriptor.py", "server/engines/postprocess.py"):
    try:
        py_compile.compile(str(ROOT / fn), doraise=True)
        print("  syntax OK :", fn)
    except Exception as e:
        print("  syntax FAIL:", fn, e)

print()
print("NEXT: restart start.bat  ->  browser Ctrl+F5  ->  submit a test job")
