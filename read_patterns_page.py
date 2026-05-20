"""Read full patterns page and save to a temp file for inspection"""
from pathlib import Path

p = Path(r"D:\MICC\micc-dashboard\src\app\patterns\page.tsx")
txt = p.read_text(encoding="utf-8")
print(f"Total chars: {len(txt)}")
print(f"Total lines: {txt.count(chr(10))}")

# Show last 200 lines
lines = txt.split("\n")
print(f"\n--- LAST 100 LINES ---")
for i, line in enumerate(lines[-100:], start=len(lines)-100):
    print(f"{i:4d}: {line}")

# Check what functions/components exist
print("\n--- FUNCTIONS/COMPONENTS ---")
for i, line in enumerate(lines):
    if line.strip().startswith("function ") or line.strip().startswith("export default"):
        print(f"  Line {i:4d}: {line.strip()[:80]}")
