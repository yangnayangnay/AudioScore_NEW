# -*- coding: utf-8 -*-
"""Wire --dtype into engine; inject dtype/batch_size/no_prelude_forcing into config."""
from pathlib import Path
import re
import py_compile
import yaml

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


# ---- engine: dtype attr ----
rep("server/engines/muscriptor.py", [
    ('        self.device = c.get("device") or c.get("torch_backend") or ""\n',
     '        self.device = c.get("device") or c.get("torch_backend") or ""\n'
     '        self.dtype = c.get("dtype") or ""\n'),
], "engine: dtype attr", skip="self.dtype = c.get")

# ---- engine: dtype in cmd ----
rep("server/engines/muscriptor.py", [
    ('        if self.device:\n            cmd += ["--device", self.device]\n',
     '        if self.device:\n            cmd += ["--device", self.device]\n'
     '        if self.dtype:\n            cmd += ["--dtype", self.dtype]\n'),
], "engine: --dtype in cmd", skip='"--dtype"')

# ---- engine: batch wiring (in case local engine predates it) ----
rep("server/engines/muscriptor.py", [
    ('        if self.beam_size:\n',
     '        if self.batch_size:\n'
     '            cmd += ["--batch-size", str(int(self.batch_size))]\n'
     '            if self.no_prelude_forcing:\n'
     '                cmd += ["--no-prelude-forcing"]\n'
     '        if self.beam_size:\n'),
], "engine: batch-size wiring", skip='"--batch-size"')

# ---- config: inject speed keys ----
f = ROOT / "config.yaml"
lines = f.read_text(encoding="utf-8").splitlines()
mi = next((i for i, l in enumerate(lines) if re.match(r"^muscriptor:\s*$", l)), None)
if mi is None:
    fail.append("config: muscriptor section not found")
else:
    j = mi + 1
    while j < len(lines) and (lines[j].startswith((" ", "\t")) or lines[j].strip() == ""):
        j += 1
    sec = lines[mi + 1:j]

    def has(key):
        return any(re.match(r"^\s*%s\s*:" % re.escape(key), l) for l in sec)

    ins = []
    if not has("dtype"):
        ins.append("  dtype: float16")
    if not has("batch_size"):
        ins.append("  batch_size: 4")
    if not has("no_prelude_forcing"):
        ins.append("  no_prelude_forcing: true")
    lines[j:j] = ins
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok.append("config: dtype/batch_size/no_prelude_forcing ensured" if ins
              else "config: speed keys [SKIP present]")

d = yaml.safe_load(f.read_text(encoding="utf-8"))
m = d.get("muscriptor", {})
print()
print("== speed config now ==")
print("  model              :", m.get("model"), " (medium = faster, A/B if quality allows)")
print("  dtype              :", m.get("dtype"), " (float16 ~1.5-2.5x on GPU)")
print("  batch_size         :", m.get("batch_size"), " (needs no_prelude_forcing)")
print("  no_prelude_forcing :", m.get("no_prelude_forcing"))
print("  beam_size          : (unset = CLI default 1 greedy, already fastest)")
print("  detect-tempo       : engine passes false (skipped, good)")

print()
print("==== RESULTS ====")
for l in ok:
    print("  PASS :", l)
for l in fail:
    print("  FAIL :", l)
py_compile.compile(str(ROOT / "server" / "engines" / "muscriptor.py"), doraise=True)
print("  syntax OK : engine")
