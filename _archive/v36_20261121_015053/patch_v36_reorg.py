# -*- coding: utf-8 -*-
"""v36-reorg: 一键整理
[1] 抓取 GitHub 完整文件树(运行时,无截断)
[2] 逐文件同步:本地差异/缺失 -> 备份后以仓库为准覆盖/下载
[3] 本地独有散件(patch_*.py / *.bak / 旧脚本等) -> 移入 _archive/v36_*/(不删除)
[4] 打印整理后最终布局"""
import json, shutil, urllib.request, time
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
REPO, BRANCH = "yangnayangnay/AudioScore_NEW", "main"
RAW  = "https://raw.githubusercontent.com/%s/%s/" % (REPO, BRANCH)
TREE = "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (REPO, BRANCH)
KEEP = {".venv", ".git", "logs", "uploads", "output", "outputs", "cache",
        "__pycache__", "_archive", "data", "models", "temp", "node_modules"}
TS = time.strftime("v36_%Y%m%d_%H%M%S")
ARCH = ROOT / "_archive" / TS
PRES = ARCH / "local_before"
stat = {"identical": 0, "overwritten": 0, "downloaded": 0, "archived": 0, "failed": []}

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "v36-reorg"})
    return urllib.request.urlopen(req, timeout=30).read()

print("[1] fetch repo tree ...")
tree = json.loads(_get(TREE))
repo_files = sorted(e["path"] for e in tree["tree"]
                    if e["type"] == "blob" and not e["path"].startswith(".git"))
print("    repo files: %d" % len(repo_files))

print()
print("[2] sync local <- repo (diff files backed up first)")
for rel in repo_files:
    lp = ROOT / rel
    try:
        remote = _get(RAW + rel)
    except Exception as e:
        stat["failed"].append("%s (fetch %s)" % (rel, e)); continue
    if lp.exists():
        local = lp.read_bytes()
        if local == remote:
            stat["identical"] += 1; continue
        PRES.mkdir(parents=True, exist_ok=True)
        dst = PRES / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lp, dst)
        lp.write_bytes(remote)
        stat["overwritten"] += 1
        print("  UPDATE %-42s (local-> %s)" % (rel, dst.relative_to(ROOT)))
    else:
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_bytes(remote)
        stat["downloaded"] += 1
        print("  ADD    %s" % rel)

print()
print("[3] archive local-only clutter ...")
repo_set = set(repo_files)
def in_keep(p):
    return any(part in KEEP for part in p.parts)
loose = []
for p in ROOT.rglob("*"):
    if not p.is_file(): continue
    rel = p.relative_to(ROOT)
    if rel.as_posix() in repo_set: continue
    if in_keep(rel.parent): continue
    if rel.parts[0] in KEEP: continue
    loose.append(p)
if loose:
    for p in loose:
        rel = p.relative_to(ROOT)
        dst = ARCH / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dst))
        stat["archived"] += 1
        print("  ARCHIVE %s" % rel)
    for p in sorted(ROOT.rglob("*"), reverse=True):
        if p.is_dir() and not any(p.iterdir()) and p.parts[0] not in KEEP:
            try: p.rmdir()
            except Exception: pass
else:
    print("  (none — local already clean)")

print()
print("=" * 72)
print("[4] FINAL LAYOUT (mirror of github/%s@%s)" % (REPO, BRANCH))
print("=" * 72)
for rel in repo_files:
    lp = ROOT / rel
    ok = "OK " if lp.exists() else "MISS"
    print("  [%s] %-44s %7d B" % (ok, rel, lp.stat().st_size if lp.exists() else 0))
for d in sorted({p.name for p in ROOT.iterdir() if p.is_dir() and p.name in KEEP}):
    print("  [KEEP] %s/ (runtime, untouched)" % d)

print()
print("=" * 72)
print("SUMMARY: identical=%d overwritten=%d downloaded=%d archived=%d failed=%d"
      % (stat["identical"], stat["overwritten"], stat["downloaded"],
         stat["archived"], len(stat["failed"])))
for f in stat["failed"]:
    print("  FAIL:", f)
print("archive at:", ARCH)
print("==== V36-REORG DONE ====")
