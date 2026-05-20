#!/usr/bin/env python3
"""Read working pages to extract exact design tokens"""
from pathlib import Path

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

# Read streaks page (image 3 - perfect example)
print("=== streaks/page.tsx first 80 lines ===")
lines = (SRC / "streaks" / "page.tsx").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(lines[:80], 1):
    print(str(i).rjust(3) + " | " + l)

print("\n=== globals.css ===")
css = (DASH / "src" / "app" / "globals.css").read_text(encoding="utf-8")
print(css[:300])

print("\n=== overview page first 60 lines (body style) ===")
ov = (SRC / "overview" / "page.tsx").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(ov[:60], 1):
    if any(k in l for k in ["background", "fontFamily", "color", "font", "body", "style"]):
        print(str(i).rjust(3) + " | " + l)

print("\n=== NavBar.tsx FULL ===")
nb = (DASH / "src" / "components" / "NavBar.tsx").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(nb, 1):
    print(str(i).rjust(3) + " | " + l)
