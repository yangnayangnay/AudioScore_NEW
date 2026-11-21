from pathlib import Path
f = Path(r"E:\Code\cs\AudioScore_new\config.yaml")
s = f.read_text(encoding="utf-8")
if "timeout: 1800" in s:
    f.write_text(s.replace("timeout: 1800", "timeout: 3600"), encoding="utf-8")
    print("[OK] timeout: 1800 -> 3600")
elif "timeout: 3600" in s:
    print("[SKIP] already 3600")
else:
    print("[WARN] no 'timeout: 1800' found - paste muscriptor section of config.yaml")
import yaml
d = yaml.safe_load(f.read_text(encoding="utf-8"))
print("[check] muscriptor.timeout =", d.get("muscriptor", {}).get("timeout"))
