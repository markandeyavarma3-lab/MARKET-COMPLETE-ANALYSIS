#!/usr/bin/env python3
"""Read globals.css fully + first 30 lines of each mismatched page"""
from pathlib import Path

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

print("=== globals.css FULL ===")
print((DASH / "src" / "app" / "globals.css").read_text(encoding="utf-8"))

for page in ["global", "macro", "watchlist", "alerts", "compare", "conviction", "portfolio", "eta", "analysis", "patterns-v3"]:
    p = SRC / page / "page.tsx"
    if p.exists():
        lines = p.read_text(encoding="utf-8").splitlines()
        print("\n=== " + page + "/page.tsx — body wrapper style (lines with 'background' or 'fontFamily') ===")
        for i, l in enumerate(lines[:120], 1):
            if any(k in l for k in ["background:", "fontFamily", "minHeight", "return (", "font-family", "var(--"]):
                print(str(i).rjust(4) + " | " + l)
