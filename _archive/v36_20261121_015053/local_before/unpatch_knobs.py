from pathlib import Path

f = Path(r"E:\Code\cs\AudioScore_new\config.yaml")
lines = f.read_text(encoding="utf-8").splitlines()
out = [ln for ln in lines
       if ln.strip() not in ("batch_size: 4", "no_prelude_forcing: true")]
f.write_text("\n".join(out) + "\n", encoding="utf-8")
print("[OK] knobs removed. current muscriptor section:")
for ln in out:
    if ln.strip() and not ln.startswith("engine"):
        print("   " + ln)
