#!/usr/bin/env python3
"""Read all pages with proper encoding"""
from pathlib import Path
import sys

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

pages = [
    "global", "macro", "alerts", "compare", "conviction",
    "portfolio", "eta", "analysis", "watchlist", "mf",
    "backtest", "settings", "patterns-v3"
]

out = open(r"D:\MICC\pages_clean.txt", "w", encoding="utf-8")

for page in pages:
    p = SRC / page / "page.tsx"
    if p.exists():
        # Try utf-8 first, then utf-16
        for enc in ["utf-8", "utf-16", "utf-8-sig"]:
            try:
                content = p.read_text(encoding=enc)
                out.write("\n\n=== " + page + "/page.tsx (" + str(len(content.splitlines())) + " lines) ===\n")
                out.write(content)
                print("OK: " + page + " (" + enc + ")")
                break
            except Exception:
                continue
    else:
        print("MISSING: " + page)

out.close()
print("Written to D:/MICC/pages_clean.txt")
