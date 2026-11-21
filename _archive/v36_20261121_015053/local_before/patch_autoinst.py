from pathlib import Path
import yaml
f = Path(r"E:\Code\cs\AudioScore_new\config.yaml")
s = f.read_text(encoding="utf-8")
if "auto_instruments" in s:
    print("[SKIP] auto_instruments already present")
else:
    lines = s.splitlines()
    idx = next(i for i, l in enumerate(lines) if l.strip() == "muscriptor:")
    ins = len(lines)
    for j in range(idx + 1, len(lines)):
        l = lines[j]
        if l.strip() and not l.startswith((" ", "\t", "#")):
            ins = j
            break
    lines[ins:ins] = ["  auto_instruments: [acoustic_piano, electric_piano, electric_bass, acoustic_bass, drums, voice, violin, flutes, clean_electric_guitar, distorted_electric_guitar]"]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
d = yaml.safe_load(f.read_text(encoding="utf-8"))
print("[OK] auto_instruments =", d["muscriptor"].get("auto_instruments"))
