# -*- coding: utf-8 -*-
"""One-shot: pp7 quantize + pp8 voice-split (transformerOfMusic notes),
switch state persistence, conversion queue (add/delete/drag-sort/gated start)."""
from pathlib import Path
import re
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []
HP = ROOT / "web" / "index.html"
s = HP.read_text(encoding="utf-8")

# ---------- 1. pp7/pp8 checkboxes ----------
PP6 = ('<div class="opt"><input type="checkbox" id="pp6"><label>'
       '\u8c10\u6ce2\u91cd\u5206\u914d\uff08\u6309\u9891\u8c31\u6307\u7eb9\u7ea0\u6b63\u8f68\u9053 '
       'Harmonic fix\uff09</label></div>')
PP78 = (PP6 + '\n<div class="opt"><input type="checkbox" id="pp7"><label>'
        '\u8282\u62cd\u7f51\u683c\u91cf\u5316\uff08\u5341\u516d\u5206\u97f3\u7b26\u5bf9\u9f50 '
        'Quantize\uff09</label></div>\n'
        '<div class="opt"><input type="checkbox" id="pp8"><label>'
        '\u58f0\u90e8\u5206\u79bb\uff08\u5355\u8f68\u62c6\u65cb\u5f8b/\u4f34\u594f '
        'Voice split\uff09</label></div>')
if 'id="pp7"' in s:
    ok.append("html: pp7/pp8 [SKIP present]")
elif PP6 in s:
    s = s.replace(PP6, PP78, 1); ok.append("html: pp7/pp8 added")
else:
    fail.append("html: pp6 anchor missing")

# ---------- 2. flags map ----------
if "pp8: 'split'" in s:
    ok.append("html: _OF [SKIP present]")
elif "pp6: 'harmonic'}" in s:
    s = s.replace("pp6: 'harmonic'}",
                  "pp6: 'harmonic', pp7: 'quant', pp8: 'split'}", 1)
    ok.append("html: _OF extended")
else:
    fail.append("html: _OF anchor missing")

# ---------- 3. queue + persistence script ----------
JS = r"""
(function(){
  var OPTKEY='as_opts';
  var PPS=['pp1','pp2','pp3','pp4','pp5','pp6','pp7','pp8'];
  function el(id){return document.getElementById(id);}
  function toast(msg){
    var t=el('asToast');
    if(!t){t=document.createElement('div');t.id='asToast';
      t.style.cssText='position:fixed;bottom:18px;left:50%;transform:translateX(-50%);'+
        'background:#333;color:#fff;padding:8px 16px;border-radius:6px;font-size:13px;'+
        'z-index:10000;box-shadow:0 2px 8px rgba(0,0,0,.3);transition:opacity .4s;opacity:0';
      document.body.appendChild(t);}
    t.textContent=msg;t.style.opacity='1';
    clearTimeout(t.__h);t.__h=setTimeout(function(){t.style.opacity='0';},2400);
  }
  /* ---- persist switch states ---- */
  function saveOpts(){
    var o={};PPS.forEach(function(id){var e=el(id);if(e)o[id]=!!e.checked;});
    var be=el('backend');if(be)o.backend=be.value;
    try{localStorage.setItem(OPTKEY,JSON.stringify(o));}catch(e){}
  }
  function loadOpts(){
    var o;try{o=JSON.parse(localStorage.getItem(OPTKEY)||'{}');}catch(e){o={};}
    PPS.forEach(function(id){var e=el(id);if(e&&(id in o))e.checked=!!o[id];});
    var be=el('backend');if(be&&o.backend)be.value=o.backend;
  }
  loadOpts();
  PPS.forEach(function(id){var e=el(id);if(e)e.addEventListener('change',saveOpts);});
  var be=el('backend');if(be)be.addEventListener('change',saveOpts);
  /* ---- XHR hook: capture job id (covers engines using XHR) ---- */
  try{
    var OS=XMLHttpRequest.prototype.send,OO=XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open=function(m,u){this.__asM=m;this.__asU=u;
      return OO.apply(this,arguments);};
    XMLHttpRequest.prototype.send=function(){
      var x=this;
      if(x.__asM&&String(x.__asM).toUpperCase()==='POST'&&
         String(x.__asU).indexOf('/api/jobs')>=0){
        x.addEventListener('load',function(){
          try{var j=JSON.parse(x.responseText);var id=j&&(j.id||j.job_id);
            if(id)localStorage.setItem('as_last_job',id);}catch(e){}
        });
      }
      return OS.apply(this,arguments);
    };
  }catch(e){}
  /* ---- queue UI ---- */
  var input=document.querySelector('input[type="file"]');
  if(input)try{input.multiple=true;}catch(e){}
  var btn=null,autoPass=false;
  var cands=document.querySelectorAll('button, input[type="button"], input[type="submit"]');
  for(var i=0;i<cands.length;i++){
    var t=((cands[i].textContent||'')+(cands[i].value||'')).trim();
    if(/\u5f00\u59cb|\u8f6c\u6362|\u8f6c\u5199/.test(t)){btn=cands[i];break;}
  }
  var Q=[],busy=false,dragIdx=-1;
  var panel=document.createElement('div');
  panel.id='asQueue';
  panel.style.cssText='border:1px solid #3a3f4a;border-radius:8px;padding:10px 12px;'+
    'margin:12px 0;background:rgba(255,255,255,.03)';
  panel.innerHTML=
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'+
      '<span style="font-weight:600">\u8f6c\u6362\u961f\u5217</span>'+
      '<span id="asQCount" style="opacity:.6;font-size:12px"></span>'+
      '<span id="asQClear" style="margin-left:auto;cursor:pointer;font-size:12px;'+
      'color:#e08a8a">\u6e05\u7a7a</span>'+
    '</div>'+
    '<div id="asQList" style="display:flex;flex-direction:column;gap:6px;min-height:34px"></div>'+
    '<div style="display:flex;align-items:center;gap:10px;margin-top:8px">'+
      '<button id="asQAdd" style="cursor:pointer">\uff0b \u52a0\u5165\u961f\u5217</button>'+
      '<span style="font-size:12px;opacity:.6">'+
      '\u52a0\u5165\u961f\u5217\u540e\u624d\u80fd\u5f00\u59cb\uff1b\u53ef\u62d6\u52a8\u6392\u5e8f\u3001\u00d7 \u5220\u9664</span>'+
    '</div>';
  if(btn&&btn.parentNode)btn.parentNode.insertBefore(panel,btn);
  else if(input&&input.parentNode)input.parentNode.insertBefore(panel,input.nextSibling);
  else document.body.appendChild(panel);
  var list=el('asQList');
  function esc(x){return String(x).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function fmtSize(n){return n>1048576?(n/1048576).toFixed(1)+'MB':
    Math.max(1,Math.round(n/1024))+'KB';}
  function syncStart(){
    if(!btn)return;
    btn.disabled=(Q.length===0);
    btn.title=Q.length?'':'\u8bf7\u5148\u628a\u4e50\u66f2\u52a0\u5165\u961f\u5217';
  }
  function renderQ(){
    list.innerHTML='';
    Q.forEach(function(it,ix){
      var row=document.createElement('div');
      row.className='asQItem';row.draggable=true;row.dataset.i=ix;
      row.style.cssText='display:flex;align-items:center;gap:8px;padding:6px 8px;'+
        'border:1px solid #3a3f4a;border-radius:6px;background:rgba(255,255,255,.05);cursor:grab';
      var stc={queued:'#8ab4e0',run:'#e0c98a',done:'#8ad0a0',err:'#e08a8a'}[it.st]||'#999';
      var stt={queued:'\u5f85\u8f6c\u6362',run:'\u8f6c\u6362\u4e2d\u2026',
               done:'\u5b8c\u6210',err:'\u5931\u8d25'}[it.st]||'';
      row.innerHTML='<span style="opacity:.5">\u2195</span>'+
        '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '+
        'title="'+esc(it.name)+'">'+esc(it.name)+
        ' <span style="opacity:.55;font-size:11px">'+fmtSize(it.size)+'</span></span>'+
        (it.dl?'<a href="'+it.dl+'" style="font-size:12px;color:#8ad0a0" '+
         'onclick="event.stopPropagation()">\u4e0b\u8f7d</a>':'')+
        '<span style="font-size:12px;color:'+stc+'">'+stt+'</span>'+
        '<span class="asQX" data-x="'+ix+'" style="cursor:pointer;color:#e08a8a;'+
        'padding:0 4px;font-weight:700">\u00d7</span>';
      list.appendChild(row);
    });
    el('asQCount').textContent=Q.length?('('+Q.length+' \u4e2a)'):'';
    syncStart();
  }
  el('asQAdd').onclick=function(){
    if(!input||!input.files||!input.files.length){
      toast('\u8bf7\u5148\u5728\u4e0a\u65b9\u9009\u62e9\u97f3\u9891\u6587\u4ef6');return;}
    for(var k=0;k<input.files.length;k++)
      Q.push({file:input.files[k],name:input.files[k].name,
              size:input.files[k].size,st:'queued',dl:''});
    try{input.value='';}catch(e){}
    renderQ();toast('\u5df2\u52a0\u5165\u961f\u5217\uff0c\u5171 '+Q.length+' \u4e2a\u4efb\u52a1');
  };
  list.addEventListener('click',function(e){
    var x=e.target.closest&&e.target.closest('.asQX');if(!x)return;
    Q.splice(+x.dataset.x,1);renderQ();
  });
  el('asQClear').onclick=function(){
    if(busy){toast('\u8f6c\u6362\u4e2d\u4e0d\u53ef\u6e05\u7a7a');return;}
    Q=[];renderQ();
  };
  list.addEventListener('dragstart',function(e){
    var it=e.target.closest&&e.target.closest('.asQItem');if(!it)return;
    dragIdx=+it.dataset.i;it.style.opacity='.4';
    try{e.dataTransfer.setData('text/plain','x');}catch(err){}
  });
  list.addEventListener('dragover',function(e){e.preventDefault();});
  list.addEventListener('drop',function(e){
    e.preventDefault();
    var it=e.target.closest&&e.target.closest('.asQItem');
    if(!it||dragIdx<0)return;
    var to=+it.dataset.i;
    if(to===dragIdx)return;
    var m=Q.splice(dragIdx,1)[0];Q.splice(to,0,m);dragIdx=-1;renderQ();
  });
  list.addEventListener('dragend',function(){dragIdx=-1;renderQ();});
  /* ---- sequential runner reusing original submit path ---- */
  function setFiles(f){
    try{var dt=new DataTransfer();dt.items.add(f);input.files=dt.files;return true;}
    catch(e){return false;}
  }
  function waitNewId(prev,cb){
    var t0=Date.now();
    var iv=setInterval(function(){
      var cur=null;try{cur=localStorage.getItem('as_last_job');}catch(e){}
      if(cur&&cur!==prev){clearInterval(iv);cb(cur);return;}
      if(Date.now()-t0>15000){clearInterval(iv);cb(null);}
    },300);
  }
  function pollJob(id,cb){
    var iv=setInterval(function(){
      fetch('/api/jobs/'+id).then(function(r){return r.ok?r.json():null;})
      .then(function(j){
        if(!j)return;
        if(j.status==='done'||j.status==='error'){clearInterval(iv);cb(j);return;}
        var sm=el('smeta');
        if(sm)sm.textContent='\u961f\u5217 '+String(id).slice(0,8)+
          ' \u5df2\u7528\u65f6 '+(j.elapsed||0)+'s';
      }).catch(function(){});
    },2000);
  }
  function runQueue(){
    if(busy)return;
    busy=true;renderQ();
    var ix=0;
    function next(){
      if(ix>=Q.length){busy=false;renderQ();
        toast('\u961f\u5217\u5168\u90e8\u5b8c\u6210');return;}
      var it=Q[ix];it.st='run';it.dl='';renderQ();
      var prev=null;try{prev=localStorage.getItem('as_last_job');}catch(e){}
      if(!input||!setFiles(it.file)){
        it.st='err';renderQ();ix++;setTimeout(next,300);return;}
      autoPass=true;
      btn.click();
      setTimeout(function(){autoPass=false;},0);
      waitNewId(prev,function(id){
        if(!id){it.st='err';renderQ();ix++;setTimeout(next,500);return;}
        pollJob(id,function(j){
          if(j.status==='done'){it.st='done';it.dl=j.download_url||'';}
          else{it.st='err';}
          renderQ();ix++;setTimeout(next,600);
        });
      });
    }
    next();
  }
  /* ---- start gating: document-level capture, beats any old handler ---- */
  document.addEventListener('click',function(e){
    if(!btn)return;
    var t=e.target;
    if(!(t===btn||(btn.contains&&btn.contains(t))))return;
    if(autoPass){autoPass=false;return;}
    e.preventDefault();e.stopPropagation();
    if(busy){toast('\u961f\u5217\u8f6c\u6362\u4e2d\uff0c\u8bf7\u7a0d\u5019');return;}
    if(Q.length===0){toast('\u8bf7\u5148\u9009\u62e9\u6587\u4ef6\u5e76\u70b9\u201c\uff0b\u52a0\u5165\u961f\u5217\u201d');return;}
    runQueue();
  },true);
  if(!btn)toast('\u672a\u627e\u5230\u5f00\u59cb\u6309\u94ae\uff0c\u961f\u5217\u4ec5\u6536\u7eb3\u4e0d\u89e6\u53d1');
})();
"""
QSCRIPT = "<script>" + JS + "</script>"
if "asQAdd" in s:
    ok.append("html: queue script [SKIP present]")
elif "</body>" in s:
    s = s.replace("</body>", QSCRIPT + "\n</body>", 1)
    ok.append("html: queue script injected")
else:
    s = s + "\n" + QSCRIPT
    ok.append("html: queue script appended")

# ---------- 4. engine: pass bpm into postprocess (quantize needs it) ----------
ENG = ROOT / "server" / "engines" / "muscriptor.py"
es = ENG.read_text(encoding="utf-8")
if "flags=post, bpm=bpm)" in es:
    ok.append("engine: main bpm pass [SKIP]")
elif "audio_path=str(audio_path), flags=post)" in es:
    es = es.replace("audio_path=str(audio_path), flags=post)",
                    "audio_path=str(audio_path), flags=post, bpm=bpm)", 1)
    ok.append("engine: main bpm pass")
else:
    fail.append("engine: main call anchor missing")

if "sorted(sub)), bpm=bpm)" in es:
    ok.append("engine: pipeline bpm pass [SKIP]")
elif 'flags=",".join(sorted(sub)))' in es:
    n = es.count('flags=",".join(sorted(sub)))')
    es = es.replace('flags=",".join(sorted(sub)))',
                    'flags=",".join(sorted(sub)), bpm=bpm)')
    ok.append("engine: pipeline bpm pass x%d" % n)
else:
    fail.append("engine: pipeline call anchor missing")

OLD_SUB = '{"dedup", "frag", "vel", "harmonic"}'
if '{"dedup", "frag", "vel", "harmonic", "quant", "split"}' in es:
    ok.append("engine: pipeline flag sets [SKIP]")
elif OLD_SUB in es:
    n = es.count(OLD_SUB)
    es = es.replace(OLD_SUB, '{"dedup", "frag", "vel", "harmonic", "quant", "split"}')
    ok.append("engine: pipeline flag sets x%d" % n)
else:
    fail.append("engine: pipeline flag-set anchor missing")
ENG.write_text(es, encoding="utf-8")

# ---------- 5. postprocess.py full rewrite (+quant/split stages) ----------
PP = ROOT / "server" / "engines" / "postprocess.py"
PP.write_text('''import logging
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
_VALID = ("dedup", "frag", "vel", "harmonic", "quant", "split")


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


def _flags(post, cfg):
    if post is None:
        fl = set()
        if cfg.get("dedup", True):
            fl.add("dedup")
        if cfg.get("frag", True):
            fl.add("frag")
        if cfg.get("vel", False):
            fl.add("vel")
        if cfg.get("harmonic", False):
            fl.add("harmonic")
        if cfg.get("quant", False):
            fl.add("quant")
        if cfg.get("split", False):
            fl.add("split")
        return fl
    s = str(post).strip().lower()
    if s in ("", "0", "off", "false", "none"):
        return set()
    return {x.strip() for x in s.split(",") if x.strip() in _VALID}


def _rebuild_velocity(pm, audio_path, parent_log):
    try:
        import numpy as np
        import librosa
    except Exception as e:
        parent_log.warning("velocity rebuild: librosa/numpy unavailable (%s) - skipped", e)
        return
    try:
        y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
    except Exception as e:
        parent_log.warning("velocity rebuild: audio load failed (%s) - skipped", e)
        return
    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    if rms.size == 0:
        return
    lr = np.log10(rms + 1e-8)
    lo, hi = np.percentile(lr, 5), np.percentile(lr, 95)
    span = max(float(hi - lo), 1e-6)
    fps = sr / hop
    cnt = 0
    for inst in pm.instruments:
        for n in inst.notes:
            a = max(int(n.start * fps), 0)
            b = min(int(n.end * fps), rms.size - 1)
            if a >= rms.size:
                a = rms.size - 1
            if b < a:
                b = a
            seg = lr[a:b + 1]
            v = int(20 + 107 * min(1.0, max(0.0, (float(seg.mean()) - lo) / span)))
            n.velocity = max(20, min(127, v))
            cnt += 1
    parent_log.info("velocity rebuild: %d notes re-velocitied from audio RMS", cnt)


def _harmonic_reassign(pm, audio_path, parent_log):
    try:
        import numpy as np
        import librosa
    except Exception as e:
        parent_log.warning("harmonic reassign: librosa unavailable (%s)", e)
        return
    mel = [i for i in pm.instruments if not i.is_drum and len(i.notes) >= 8]
    if len(mel) < 2:
        parent_log.info("harmonic reassign: <2 melodic tracks - skipped")
        return
    try:
        y, sr = librosa.load(str(audio_path), mono=True, sr=22050)
    except Exception as e:
        parent_log.warning("harmonic reassign: audio load failed (%s)", e)
        return
    hop = 512
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)) + 1e-9
    fps = sr / hop

    def prof(inst):
        vecs = []
        for n in inst.notes[:80]:
            a = int(n.start * fps)
            b = max(int(n.end * fps), a + 1)
            seg = S[:, a:min(b, S.shape[1])]
            if seg.size:
                vecs.append(seg.mean(axis=1))
        if not vecs:
            return None
        v = np.mean(vecs, axis=0)
        return v / (np.linalg.norm(v) + 1e-9)

    profiles = {id(i): prof(i) for i in mel}
    moved = 0
    for inst in mel:
        p0 = profiles[id(inst)]
        if p0 is None:
            continue
        for n in list(inst.notes):
            a = int(n.start * fps)
            b = max(int(n.end * fps), a + 1)
            seg = S[:, a:min(b, S.shape[1])]
            if not seg.size:
                continue
            v = seg.mean(axis=1)
            v /= (np.linalg.norm(v) + 1e-9)
            sims = {id(i): float(np.dot(v, profiles[id(i)]))
                    for i in mel if profiles[id(i)] is not None}
            best = max(sims, key=sims.get)
            if best != id(inst) and sims[best] - sims[id(inst)] > 0.15:
                best_inst = next(i for i in mel if id(i) == best)
                inst.notes.remove(n)
                best_inst.notes.append(n)
                moved += 1
    parent_log.info("harmonic reassign: %d notes moved between tracks", moved)


def _grid_quantize(pm, bpm, parent_log):
    """transformerOfMusic quantize/grid: snap notes to 16th-note grid."""
    b = 0.0
    try:
        b = float(bpm or 0)
    except Exception:
        b = 0.0
    if b <= 0:
        try:
            b = float(pm.estimate_tempo())
        except Exception:
            b = 0.0
    if b <= 0:
        parent_log.info("grid quantize: no bpm (ui/estimate) - skipped")
        return
    step = 60.0 / b / 4.0
    moved = 0
    for inst in pm.instruments:
        for n in inst.notes:
            s2 = round(n.start / step) * step
            e2 = round(n.end / step) * step
            if e2 <= s2:
                e2 = s2 + step
            if abs(n.start - s2) > 1e-4 or abs(n.end - e2) > 1e-4:
                n.start = max(0.0, s2)
                n.end = e2
                moved += 1
    parent_log.info("grid quantize: bpm=%.1f step=%dms, %d notes snapped",
                    b, int(step * 1000), moved)


def _voice_split(pm, parent_log):
    """transformerOfMusic voice/layer idea: split dense wide-range track
    into upper (melody) and lower (accompaniment) by pitch median."""
    from statistics import median
    added = []
    for inst in list(pm.instruments):
        if inst.is_drum or len(inst.notes) < 24:
            continue
        pitches = [n.pitch for n in inst.notes]
        med = median(pitches)
        cut = med - 7
        lo = [n for n in inst.notes if n.pitch < cut]
        hi = [n for n in inst.notes if n.pitch >= cut]
        if len(lo) < 8 or len(hi) < 8:
            continue
        if max(pitches) - min(pitches) < 24:
            continue
        inst.notes = hi
        ni = pretty_midi.Instrument(program=inst.program, is_drum=False,
                                    name=((inst.name or "track") + "-low")[:30])
        ni.notes = lo
        added.append(ni)
        parent_log.info("voice split: '%s' -> %d upper + %d lower",
                        inst.name or "track", len(hi), len(lo))
    pm.instruments.extend(added)


def run_postprocess(mid_path, cfg, parent_log, audio_path=None, flags=None, bpm=None):
    fl = _flags(flags, cfg)
    if not fl:
        parent_log.info("postprocess: OFF (no flags)")
        return
    merge_gap = float(cfg.get("merge_gap", 0.08))
    min_note = float(cfg.get("min_note", 0.06)) if "frag" in fl else 0.0
    iso_min = int(cfg.get("isolated_min_notes", 3))
    range_fix = bool(cfg.get("range_fix", False))

    pm = pretty_midi.PrettyMIDI(str(mid_path))
    log.info("---- postprocess start: flags=%s", ",".join(sorted(fl)))

    for i, inst in enumerate(pm.instruments):
        before = len(inst.notes)
        if "dedup" in fl:
            inst.notes = _merge_fragments(inst.notes, merge_gap, 0.0)
        if min_note > 0:
            inst.notes = [n for n in inst.notes if (n.end - n.start) >= min_note]
        if before != len(inst.notes):
            log.info("track %02d hygiene: %d -> %d notes (dedup=%s frag=%s)",
                     i, before, len(inst.notes), "dedup" in fl, min_note > 0)

    if "quant" in fl:
        _grid_quantize(pm, bpm, log)
    if "split" in fl:
        _voice_split(pm, log)

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

    if "dedup" in fl and len(pm.instruments) > 1:
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

    if "harmonic" in fl and audio_path:
        _harmonic_reassign(pm, audio_path, log)
    if "vel" in fl and audio_path:
        _rebuild_velocity(pm, audio_path, log)

    pm.write(str(mid_path))
    log.info("---- postprocess done: %d tracks remain", len(pm.instruments))
''', encoding="utf-8")
ok.append("postprocess.py rewritten (+quant/split)")

print()
print("==== PATCH RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("=======================")
btns = re.findall(r"<button[^>]*>\s*([^<]{0,30})", s)
print("  start-button candidates seen in html:", [b.strip() for b in btns][:8])
for fn in ("web/index.html", "server/engines/muscriptor.py",
           "server/engines/postprocess.py"):
    print("  written:", fn)
py_compile.compile(str(ENG), doraise=True)
py_compile.compile(str(PP), doraise=True)
print("  syntax OK : engine + postprocess")
