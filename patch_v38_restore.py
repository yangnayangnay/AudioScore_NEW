# -*- coding: utf-8 -*-
"""v38-restore: 撤销 v37 的错误归档 —— 被移走的本地文件全部移回原位。
只恢复, 不删除, 不联网, 不改任何仓库内容。"""
import shutil
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
ARCH_ROOT = ROOT / "_archive"

if not ROOT.exists():
    raise SystemExit("ERROR: root not found: %s" % ROOT)
if not ARCH_ROOT.exists():
    raise SystemExit("ERROR: no _archive dir found — nothing to restore")

rollbacks = sorted([d for d in ARCH_ROOT.glob("rollback_*") if d.is_dir()],
                   key=lambda d: d.name, reverse=True)
v36s = sorted([d for d in ARCH_ROOT.glob("v36_*") if d.is_dir()],
              key=lambda d: d.name, reverse=True)

restored, dropped, conflicts, failed, backups = [], [], [], [], []

for arch in rollbacks:
    loose = arch / "loose"
    if not loose.exists():
        continue
    for p in sorted(loose.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(loose)
        dest = ROOT / rel
        try:
            if dest.exists():
                if dest.read_bytes() == p.read_bytes():
                    p.unlink()
                    dropped.append(rel.as_posix())
                else:
                    conflicts.append("%s :: %s" % (arch.name, rel.as_posix()))
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(dest))
                restored.append(rel.as_posix())
        except Exception as e:
            failed.append("%s (%s)" % (rel.as_posix(), e))
    for d in sorted(loose.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except Exception:
                pass

for arch in rollbacks:
    for p in arch.rglob("*"):
        if not p.is_file():
            continue
        ra = p.relative_to(arch)
        if ra.parts and ra.parts[0] == "loose":
            continue
        backups.append("%s :: %s" % (arch.name, ra.as_posix()))

print("=" * 72)
print("RESTORED back to original location : %d" % len(restored))
for r in restored:
    print("    %s" % r)
print("IDENTICAL (archive copy discarded) : %d" % len(dropped))
print("CONFLICTS (both exist, NOT touched): %d" % len(conflicts))
for c in conflicts:
    print("    %s" % c)
print("FAILED                             : %d" % len(failed))
for f in failed:
    print("    %s" % f)
print()
print("Still in archive (local versions that existed BEFORE repo overwrite): %d" % len(backups))
for b in backups:
    print("    %s" % b)
if v36s:
    print()
    print("v36 archives found (junk patterns, NOT auto-restored):")
    for a in v36s:
        for p in a.rglob("*"):
            if p.is_file():
                print("    %s :: %s" % (a.name, p.relative_to(a).as_posix()))
print()
print("==== V38-RESTORE DONE — restart the server, then test download ====")
