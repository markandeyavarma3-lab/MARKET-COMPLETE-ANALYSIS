"""
fix_navbar_and_wire.py  --  Run from D:\MICC
Reads NavBar.tsx from disk, finds the real nav items structure,
adds WATCHLIST + BACKTEST links correctly.
"""
import re
from pathlib import Path

DASH = Path(r"D:\MICC\micc-dashboard")

navbar = None
for p in DASH.rglob("NavBar.tsx"):
    navbar = p; break

if not navbar:
    print("[ERROR] NavBar.tsx not found"); raise SystemExit(1)

src = navbar.read_text(encoding="utf-8")
print("=== Current NavBar.tsx (first 60 lines) ===")
for i, l in enumerate(src.splitlines()[:60], 1):
    print(f"  {i:3d}: {l}")

print("\n=== Lines containing href or label ===")
for i, l in enumerate(src.splitlines(), 1):
    if "href" in l or "'/" in l or '\"/' in l:
        print(f"  {i:3d}: {l}")

# ── patch: find last nav item and append after it ──────────────────────────
orig = src

# Strategy: find all existing href entries, insert after the last one
# Pattern matches both object-style { href: '/x', label: 'Y' }
# and JSX-style <Link href="/x">
hrefs = list(re.finditer(r"(href\s*[:=]\s*['\"]\/[^'\"]+['\"])", src))
if hrefs:
    last = hrefs[-1]
    # Find the end of this line
    line_end = src.find("\n", last.end())
    if line_end == -1: line_end = len(src)

    to_add = ""
    if "watchlist" not in src.lower():
        to_add += "\n  { href: '/watchlist', label: 'WATCHLIST' },"
    if "backtest" not in src.lower():
        to_add += "\n  { href: '/backtest', label: 'BACKTEST' },"

    if to_add:
        # Find the full line containing the last href
        line_start = src.rfind("\n", 0, last.start()) + 1
        full_line  = src[line_start:line_end]
        print(f"\n=== Inserting after: {full_line.strip()} ===")
        src = src[:line_end] + to_add + src[line_end:]
        navbar.write_text(src, encoding="utf-8")
        print(f"  [OK] Wrote {navbar}")
    else:
        print("  WATCHLIST and BACKTEST already present")
else:
    print("\n[WARN] No href patterns found. Printing full file for manual fix:")
    print(src)
