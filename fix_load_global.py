"""
fix_load_global.py  --  Run from D:\MICC
Fixes the IndentationError in load_global_index by finding
lines 243-260 and rewriting the function completely.

Run: py D:\MICC\fix_load_global.py
Then: py D:\MICC\build_seasonality_v3.py --resume
"""
import subprocess, sys
from pathlib import Path

V3 = Path(r"D:\MICC\build_seasonality_v3.py")
lines = V3.read_text(encoding="utf-8").splitlines()
print(f"Read {len(lines)} lines")

# Show lines 240-265
print("\nLines 238-268:")
for i, l in enumerate(lines[237:268], start=238):
    print(f"  {i:3d}: {l}")

# Find the start of load_global_index
start = None
for i, l in enumerate(lines):
    if "def load_global_index(" in l:
        start = i
        break

if start is None:
    print("[ERROR] Cannot find load_global_index")
    raise SystemExit(1)

print(f"\nFound load_global_index at line {start+1}")

# Find the end: next def at same indent level
end = None
for i in range(start + 1, len(lines)):
    if lines[i].startswith("def ") or (lines[i].startswith("    def ") and start == 0):
        end = i
        break
    # Also stop at next top-level def
    stripped = lines[i]
    if stripped.startswith("def ") and i > start:
        end = i
        break

if end is None:
    end = start + 30  # fallback

print(f"Function spans lines {start+1} to {end}")
print("Current function:")
for i in range(start, min(end, start+25)):
    print(f"  {i+1:3d}: {lines[i]}")

# Write the clean replacement
REPLACEMENT = """\
def load_global_index(conn, symbol: str) -> "Optional[pd.Series]":
    \"\"\"Load global index close from global_indices_daily with retry on lock.\"\"\"
    import time as _time
    for attempt in range(5):
        try:
            _c = sqlite3.connect(DB_PATH, timeout=60)
            _c.execute("PRAGMA read_uncommitted=1")
            _c.execute("PRAGMA busy_timeout=20000")
            rows = _c.execute(
                "SELECT date, close FROM global_indices_daily "
                "WHERE symbol=? AND close IS NOT NULL ORDER BY date",
                (symbol,)
            ).fetchall()
            _c.close()
            if not rows:
                return None
            idx  = pd.to_datetime([r[0] for r in rows])
            vals = [float(r[1]) for r in rows]
            return pd.Series(vals, index=idx).sort_index()
        except sqlite3.OperationalError as _e:
            if "locked" in str(_e).lower() and attempt < 4:
                _time.sleep(3 + attempt * 2)
                continue
            return None
        except Exception:
            return None
    return None
""".splitlines()

# Rebuild file
new_lines = lines[:start] + REPLACEMENT + lines[end:]
new_src = "\n".join(new_lines)
V3.write_text(new_src, encoding="utf-8")
print(f"\n[SAVED] {len(new_lines)} lines")

# Show result
final = V3.read_text(encoding="utf-8").splitlines()
print(f"\nNew function (lines {start+1} to {start+len(REPLACEMENT)+1}):")
for i, l in enumerate(final[start:start+len(REPLACEMENT)+2], start=start+1):
    print(f"  {i:3d}: {l}")

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
        ctx = V3.read_text(encoding="utf-8").splitlines()
        print(f"\n  Context around line {ln}:")
        for i, l in enumerate(ctx[max(0,ln-4):ln+5], start=max(1,ln-3)):
            print(f"  {'>>>' if i==ln else '   '} {i:3d}: {l}")

print("""
=============================================================
Now run:
  py D:\\MICC\\build_seasonality_v3.py --resume
=============================================================
""")
