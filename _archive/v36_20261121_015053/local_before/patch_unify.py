# -*- coding: utf-8 -*-
"""Unify checkboxes: retire my ppc, wire ORIGINAL pp1/pp2/pp3 into MuScriptor.
pp1=dedup(same-pitch merge+iso-track) pp2=frag(<60ms filter) pp3=vel(energy rebuild)."""
from pathlib import Path
import py_compile

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ok, fail = [], []


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


# ---- 1. remove my ppc checkbox ----
PPC = ('<div class="opt"><input type="checkbox" id="ppc" checked>'
       '<label>\u97f3\u7b26\u6e05\u7406\uff08\u5408\u5e76\u788e\u97f3/\u97f3\u57df\u68c0\u67e5/'
       '\u5b64\u7acb\u8f68\u56de\u6536\uff09 Note cleanup</label></div>\n')
hp = ROOT / "web" / "index.html"
hs = hp.read_text(encoding="utf-8")
if 'id="ppc"' not in hs:
    ok.append("html: remove ppc [SKIP]")
elif PPC in hs:
    hp.write_text(hs.replace(PPC, "", 1), encoding="utf-8")
    ok.append("html: remove ppc")
else:
    fail.append("html: ppc line text mismatch")

# ---- 2. wrap original checkboxes in <label> (click-text toggles) ----
rep("web/index.html", [
    ('<div class="opt"><input type="checkbox" id="pp1" checked>'
     '\u91cd\u53e0\u5206\u7247\u53bb\u91cd\uff08\u8de8 5s \u5206\u7247\u91cd\u590d\u97f3\u7b26\u5408\u5e76\uff09</div>',
     '<div class="opt"><input type="checkbox" id="pp1" checked><label>'
     '\u91cd\u53e0\u5206\u7247\u53bb\u91cd\uff08\u8de8 5s \u5206\u7247\u91cd\u590d\u97f3\u7b26\u5408\u5e76\uff09</label></div>'),
], "html: pp1 label wrap", skip='pp1" checked><label>')

rep("web/index.html", [
    ('<div class="opt"><input type="checkbox" id="pp2" checked>'
     '\u788e\u97f3\u7b26\u8fc7\u6ee4\uff08&lt;60ms\uff09</div>',
     '<div class="opt"><input type="checkbox" id="pp2" checked><label>'
     '\u788e\u97f3\u7b26\u8fc7\u6ee4\uff08&lt;60ms\uff09</label></div>'),
], "html: pp2 label wrap", skip='pp2" checked><label>')

rep("web/index.html", [
    ('<div class="opt"><input type="checkbox" id="pp3">'
     '\u529b\u5ea6\u91cd\u5efa\uff08\u57fa\u4e8e\u539f\u59cb\u97f3\u9891\u80fd\u91cf\uff09</div>',
     '<div class="opt"><input type="checkbox" id="pp3"><label>'
     '\u529b\u5ea6\u91cd\u5efa\uff08\u57fa\u4e8e\u539f\u59cb\u97f3\u9891\u80fd\u91cf\uff09</label></div>'),
], "html: pp3 label wrap", skip='pp3"><label>')

# ---- 3. send pp1/2/3 as flags in 'post' ----
rep("web/index.html", [
    ("fd.append('post', $('ppc') && $('ppc').checked ? '1' : '0');",
     "var _OF = {pp1: 'dedup', pp2: 'frag', pp3: 'vel'}, _on = [];\n"
     "for (var k in _OF) { var e = document.getElementById(k);"
     " if (e && e.checked) _on.push(_OF[k]); }\n"
     "fd.append('post', _on.join(','));"),
], "html: send dedup/frag/vel flags", skip="_OF = {pp1")

# ---- 4. main.py: stop squashing post to bool ----
rep("server/main.py", [
    ("post=(None if post is None else post in ('1', 'true', 'on'))", "post=post"),
    ("bpm=bpm, timeout=timeout)",
     "bpm=bpm, timeout=timeout,\n                   post=post)"),
], "main.py: pass post string verbatim", skip="post=post)")

# ---- 5. engine: hand flags+audio to postprocess ----
OLDBLOCK = (
    '        _ui = self.pp_cfg.get("enabled", True) if post is None else bool(post)\n'
    '        if _ui:\n'
    '            try:\n'
    '                from .postprocess import run_postprocess\n'
    '                lg.info("postprocess: ON (ui=%s)", post)\n'
    '                run_postprocess(out_mid_path, self.pp_cfg, lg)\n'
    '            except Exception as _e:\n'
    '                lg.warning("postprocess skipped: %s", _e)\n'
    '        else:\n'
    '            lg.info("postprocess: OFF (ui flag)")')
NEWBLOCK = (
    '        try:\n'
    '            from .postprocess import run_postprocess\n'
    '            run_postprocess(out_mid_path, self.pp_cfg, lg,\n'
    '                            audio_path=str(audio_path), flags=post)\n'
    '        except Exception as _e:\n'
    '            lg.warning("postprocess skipped: %s", _e)')
rep("server/engines/muscriptor.py", [(OLDBLOCK, NEWBLOCK)],
    "engine: pass flags+audio_path", skip="flags=post)")

# ---- 6. postprocess.py: flag-driven rewrite + velocity rebuild ----
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
_VALID = ("dedup", "frag", "vel")


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


def run_postprocess(mid_path, cfg, parent_log, audio_path=None, flags=None):
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

    if "vel" in fl and audio_path:
        _rebuild_velocity(pm, audio_path, parent_log)

    pm.write(str(mid_path))
    log.info("---- postprocess done: %d tracks remain", len(pm.instruments))
''', encoding="utf-8")
ok.append("postprocess.py rewritten (flag-driven + velocity rebuild)")

print()
print("==== PATCH RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
print("=======================")

for fn in ("server/main.py", "server/engines/muscriptor.py",
           "server/engines/postprocess.py"):
    try:
        py_compile.compile(str(ROOT / fn), doraise=True)
        print("  syntax OK :", fn)
    except Exception as e:
        print("  syntax FAIL:", fn, e)
