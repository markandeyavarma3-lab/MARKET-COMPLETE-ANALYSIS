#!/usr/bin/env python3
"""Read the 4 liked pages fully"""
from pathlib import Path

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

out = open(r"D:\MICC\liked_pages.txt", "w", encoding="utf-8")

for page in ["", "streaks", "indices", "mf"]:
    p = SRC / (page or "page") / ("page.tsx" if page else "page.tsx")
    if not page:
        p = SRC / "page.tsx"
    else:
        p = SRC / page / "page.tsx"
    if p.exists():
        content = p.read_text(encoding="utf-8")
        out.write("\n\n=== " + (page or "root/overview") + " ===\n")
        out.write(content)
        print("READ: " + (page or "overview") + " (" + str(len(content.splitlines())) + " lines)")
    else:
        print("MISSING: " + page)

# Also read overview page (the actual overview not root)
for page in ["overview", "macro", "patterns", "global", "watchlist", "alerts", "compare", "settings"]:
    p = SRC / page / "page.tsx"
    if p.exists():
        content = p.read_text(encoding="utf-8")
        out.write("\n\n=== " + page + " ===\n")
        out.write(content)
        print("READ: " + page + " (" + str(len(content.splitlines())) + " lines)")

out.close()
print("\nDone -> D:/MICC/liked_pages.txt")
