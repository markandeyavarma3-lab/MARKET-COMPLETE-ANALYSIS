#!/usr/bin/env python3
"""Read all pages fully for redesign"""
from pathlib import Path

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

pages = [
    "global", "macro", "alerts", "compare", "conviction",
    "portfolio", "eta", "analysis", "watchlist", "mf",
    "backtest", "settings", "patterns-v3"
]

for page in pages:
    p = SRC / page / "page.tsx"
    if p.exists():
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        print("\n\n=== " + page + "/page.tsx (" + str(len(lines)) + " lines) ===")
        print(content)
    else:
        print("\n=== " + page + "/page.tsx NOT FOUND ===")
