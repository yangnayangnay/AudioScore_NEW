import re
from pathlib import Path

ROOT = Path(r"E:\Code\cs\AudioScore_new")
SKIP = {".venv", "models", "logs", "uploads", ".git", "__pycache__", "node_modules"}
WEB_EXT = {".html", ".js", ".vue", ".jsx", ".ts"}

ZH = {
    "Piano": "\u94a2\u7434",
    "Acoustic Piano": "\u94a2\u7434",
    "Electric Piano": "\u7535\u94a2\u7434",
    "Electric Guitar": "\u7535\u5409\u4ed6",
    "Acoustic Guitar": "\u6728\u5409\u4ed6",
    "Guitar": "\u5409\u4ed6",
    "Electric Bass": "\u7535\u8d1d\u65af",
    "Acoustic Bass": "\u4f4e\u97f3\u63d0\u7434",
    "Bass": "\u8d1d\u65af",
    "Drums": "\u67b6\u5b50\u9f13",
    "Drum Kit": "\u67b6\u5b50\u9f13",
    "Drum Set": "\u67b6\u5b50\u9f13",
    "Drum Score": "\u9f13\u8c31",
    "Violin": "\u5c0f\u63d0\u7434",
    "Viola": "\u4e2d\u63d0\u7434",
    "Cello": "\u5927\u63d0\u7434",
    "Double Bass": "\u4f4e\u97f3\u63d0\u7434",
    "Contrabass": "\u4f4e\u97f3\u63d0\u7434",
    "Flute": "\u957f\u7b1b",
    "Clarinet": "\u5355\u7c27\u7ba1",
    "Oboe": "\u53cc\u7c27\u7ba1",
    "Bassoon": "\u5df4\u677e",
    "Trumpet": "\u5c0f\u53f7",
    "Trombone": "\u957f\u53f7",
    "French Horn": "\u5706\u53f7",
    "Tuba": "\u5927\u53f7",
    "Saxophone": "\u8428\u514b\u65af",
    "Voice": "\u4eba\u58f0",
    "Vocals": "\u4eba\u58f0",
    "Soprano": "\u5973\u9ad8\u97f3",
    "Alto": "\u5973\u4f4e\u97f3",
    "Organ": "\u7ba1\u98ce\u7434",
    "Strings": "\u5f26\u4e50",
    "String Ensemble": "\u5f26\u4e50\u5408\u594f",
    "Brass": "\u94dc\u7ba1",
    "Harp": "\u7ad6\u7434",
    "Synth": "\u5408\u6210\u5668",
    "Synth Lead": "\u5408\u6210\u4e3b\u97f3",
    "Synth Pad": "\u5408\u6210\u94fa\u5e95",
    "Timpani": "\u5b9a\u97f3\u9f13",
    "Chromatic Percussion": "\u8272\u5f69\u6253\u51fb\u4e50",
    "Percussion": "\u6253\u51fb\u4e50",
}
LABELS = sorted(ZH.keys(), key=len, reverse=True)


def rx(lb):
    return re.compile(r"(['\"])" + re.escape(lb) + r"\1|(>)" + re.escape(lb) + r"(<)")


hits = []
for p in ROOT.rglob("*"):
    if not p.is_file() or (set(p.parts) & SKIP):
        continue
    if p.suffix.lower() not in WEB_EXT and p.suffix.lower() != ".py":
        continue
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception:
        continue
    found = [lb for lb in LABELS if rx(lb).search(txt)]
    if found:
        hits.append((p, found))

patched = 0
for p, found in hits:
    if p.suffix.lower() == ".py":
        print("[REPORT ONLY]", p)
        lines = p.read_text(encoding="utf-8").splitlines()
        for lb in found[:6]:
            for i, l in enumerate(lines):
                if rx(lb).search(l):
                    print("   line %d: %s" % (i + 1, l.rstrip()[:110]))
                    break
        continue
    txt = p.read_text(encoding="utf-8")
    orig = txt
    for lb in found:
        zh = ZH[lb]
        txt = txt.replace("'" + lb + "'", "'" + zh + " " + lb + "'")
        txt = txt.replace('"' + lb + '"', '"' + zh + " " + lb + '"')
        txt = txt.replace(">" + lb + "<", ">" + zh + " " + lb + "<")
    if txt != orig:
        p.write_text(txt, encoding="utf-8")
        patched += 1
        print("[PATCHED]", p, "labels:", ",".join(found[:8]))
print("done: %d web file(s) patched" % patched)
if not hits:
    print("no label hits at all - paste this message to the assistant")
