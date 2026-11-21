# -*- coding: utf-8 -*-
"""v38b: 把 v37 覆盖前的本地版本恢复回去(仅在 v38+重启后仍有异常时用)。"""
import shutil
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ARCH_ROOT = ROOT / "_archive"
rollbacks = sorted([d for d in ARCH_ROOT.glob("rollback_*") if d.is_dir()],
                   key=lambda d: d.name)   # oldest first -> newest wins
n = 0
for arch in rollbacks:
    for p in sorted(arch.rglob("*")):
        if not p.is_file():
            continue
        ra = p.relative_to(arch)
        if ra.parts and ra.parts[0] == "loose":
            continue
        dest = ROOT / ra
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(p), str(dest))
        n += 1
        print("RESTORE-BACKUP %s" % ra.as_posix())
print("done: %d file(s) restored from pre-rollback backups" % n)
