from pathlib import Path
import re
import yaml

ROOT = Path(r"E:\Code\cs\AudioScore_new")

# ---- 1. engine version check ----
eng = (ROOT / "server" / "engines" / "muscriptor.py").read_text(encoding="utf-8")
marks = {
    "NO LIMIT (0=no limit)": "NO LIMIT" in eng,
    "guided-auto": "guided-auto" in eng,
    "job lock": "_JOB_LOCK" in eng,
    "kill_tree": "_kill_tree" in eng,
}
print("== engine check ==")
for k, v in marks.items():
    print("  %-24s %s" % (k, "OK" if v else "MISSING"))
new_engine = all(marks.values())

# ---- 2. set timeout ----
val = 0 if new_engine else 86400
cfg = ROOT / "config.yaml"
lines = cfg.read_text(encoding="utf-8").splitlines(keepends=True)
in_mus = False
changed = False
for i, l in enumerate(lines):
    if re.match(r"^muscriptor:\s*$", l):
        in_mus = True
        continue
    if in_mus and re.match(r"^\S", l):
        in_mus = False
    if in_mus and re.match(r"^\s*timeout\s*:", l):
        lines[i] = re.sub(r"timeout\s*:\s*.*",
                          "timeout: %d  # 0 = no limit" % val, l)
        changed = True
if changed:
    cfg.write_text("".join(lines), encoding="utf-8")
else:
    print("[WARN] no timeout line under muscriptor: - add 'timeout: %d' manually" % val)

d = yaml.safe_load(cfg.read_text(encoding="utf-8"))
print()
print("== config ==")
print("  timeout ->", d.get("muscriptor", {}).get("timeout"))
if new_engine:
    print("[OK] NEW engine + timeout 0 = true NO LIMIT, heartbeats keep logging")
else:
    print("[WARN] OLD engine detected -> set 86400 (24h) as safe stand-in.")
    print("       Run the engine-rewrite patch (patch 2, previous round) to get:")
    print("       true no-limit + 10s heartbeat + guided-auto + process-tree kill.")
