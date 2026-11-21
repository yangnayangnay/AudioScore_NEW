from pathlib import Path
import re

f = Path(r"E:\Code\cs\AudioScore_new\config.yaml")
s = f.read_text(encoding="utf-8")

m = re.search(r"^engine:.*$", s, flags=re.M)
if m:
    if "muscriptor" in m.group(0):
        print("[engine] ??? muscriptor, ??")
    else:
        s = s[:m.start()] + "engine: muscriptor" + s[m.end():]
        print("[engine] ??? muscriptor (???: %s)" % m.group(0).strip())
else:
    print("[engine] ??: ??? engine ?, ?????")

if "batch_size" in s:
    print("[knobs] ?????, ??")
else:
    lines = s.splitlines()
    out, done = [], False
    for i, ln in enumerate(lines):
        out.append(ln)
        if ln.strip() == "muscriptor:" and not done:
            indent = "  "
            if i + 1 < len(lines) and lines[i + 1].startswith((" ", "\t")):
                j = 0
                while j < len(lines[i + 1]) and lines[i + 1][j] in " \t":
                    j += 1
                indent = lines[i + 1][:j]
            out.append(indent + "batch_size: 4")
            out.append(indent + "no_prelude_forcing: true")
            done = True
    if done:
        s = "\n".join(out) + "\n"
        print("[knobs] batch_size: 4 / no_prelude_forcing: true ???")
    else:
        print("[knobs] ??: ??? muscriptor: ?, ?????")

f.write_text(s, encoding="utf-8")
print("---- ?? config.yaml ----")
print(s)
