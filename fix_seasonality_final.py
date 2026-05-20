"""
fix_seasonality_final.py  --  Run from D:\MICC
Direct fix: replaces lines 626-632 (the entire print block) cleanly.

Run: py D:\MICC\fix_seasonality_final.py
Then: py D:\MICC\build_seasonality_v3.py --resume
"""
import subprocess, sys
from pathlib import Path

V3 = Path(r"D:\MICC\build_seasonality_v3.py")
lines = V3.read_text(encoding="utf-8").splitlines()
print(f"Read {len(lines)} lines")

# Show current state of the broken area
print("\nCurrent lines 624-640:")
for i, l in enumerate(lines[623:640], start=624):
    print(f"  {i:3d}: {l}")

# Find the line with `print(` that starts the broken block
# We look for the print( that is immediately followed by the f-string with sym_label or str(symbol
start_idx = None
for i, line in enumerate(lines):
    if line.strip() == "print(" and i + 1 < len(lines):
        next_line = lines[i + 1]
        if "sym_label" in next_line or 'str(symbol' in next_line or 'symbol or' in next_line:
            start_idx = i
            break

if start_idx is None:
    # Try: find print( near the prog/pbar lines
    for i, line in enumerate(lines):
        if "prog = pbar" in line:
            # Look forward for a print( within 5 lines
            for j in range(i, min(i + 8, len(lines))):
                if lines[j].strip() == "print(":
                    start_idx = j
                    break
            if start_idx is not None:
                break

if start_idx is None:
    print("[ERROR] Could not find the broken print block")
    raise SystemExit(1)

print(f"\nFound broken print( block starting at line {start_idx + 1}")

# Find the end of the block (the closing paren at same indent level)
indent_level = len(lines[start_idx]) - len(lines[start_idx].lstrip())
end_idx = start_idx
for i in range(start_idx + 1, min(start_idx + 15, len(lines))):
    end_idx = i
    stripped = lines[i].strip()
    # The block ends at the ) that closes the print(
    if stripped == ")" and (len(lines[i]) - len(lines[i].lstrip())) == indent_level:
        break

print(f"Block spans lines {start_idx + 1} to {end_idx + 1}:")
for i in range(start_idx, end_idx + 1):
    print(f"  {i+1:3d}: {lines[i]}")

# Build the clean replacement (7 lines, same indentation)
ind = " " * indent_level
replacement = [
    ind + "sym_label  = str(symbol  or '?')[:20]",
    ind + "type_label = str(sym_type or '')[:14]",
    ind + "print(",
    ind + "    f\"\\r  {prog}  {type_clr}{sym_label:<20}{R}{D}{type_label:<14}{R}\"",
    ind + "    f\"  ETA {hms(eta_s)}  pats={total_pats:,}  \",",
    ind + "    end=\"\", flush=True",
    ind + ")",
]

print(f"\nReplacement ({len(replacement)} lines):")
for l in replacement:
    print(f"    {l}")

# Splice: keep everything before start_idx, insert replacement, keep everything after end_idx
new_lines = lines[:start_idx] + replacement + lines[end_idx + 1:]
new_src = "\n".join(new_lines)
V3.write_text(new_src, encoding="utf-8")
print(f"\n[SAVED] {len(new_lines)} lines")

# Show new state
all_lines = new_src.splitlines()
print(f"\nNew lines {start_idx - 1} to {start_idx + 10}:")
for i, l in enumerate(all_lines[start_idx - 2: start_idx + 10], start=start_idx - 1):
    print(f"  {i+1:3d}: {l}")

# Syntax check
result = subprocess.run(
    [sys.executable, "-m", "py_compile", str(V3)],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("\n  [OK] Syntax check PASSED")
else:
    print(f"\n  [FAIL] {result.stderr}")
    import re
    m = re.search(r"line (\d+)", result.stderr)
    if m:
        ln = int(m.group(1))
        context = new_src.splitlines()
        print(f"\n  Context around line {ln}:")
        for i, l in enumerate(context[max(0, ln-4):ln+5], start=max(1, ln-3)):
            marker = " >>>" if i == ln else "    "
            print(f"  {marker} {i:3d}: {l}")

print("""
=============================================================
Now run:
  py D:\\MICC\\build_seasonality_v3.py --resume
=============================================================
""")
