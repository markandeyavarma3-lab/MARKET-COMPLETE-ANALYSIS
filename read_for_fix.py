#!/usr/bin/env python3
"""Read key files to understand navbar pattern"""
from pathlib import Path

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

# Read overview page first 40 lines (navbar import pattern)
print("=== overview/page.tsx first 40 lines ===")
ov = (SRC / "overview" / "page.tsx").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(ov[:40], 1):
    print(str(i).rjust(3) + " | " + l)

# Read analysis page in full
print("\n=== analysis/page.tsx FULL ===")
an = (SRC / "analysis" / "page.tsx").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(an, 1):
    print(str(i).rjust(3) + " | " + l)

# Read NavBar.tsx first 30 lines
print("\n=== NavBar.tsx first 30 lines ===")
nb = (DASH / "src" / "components" / "NavBar.tsx").read_text(encoding="utf-8").splitlines()
for i, l in enumerate(nb[:30], 1):
    print(str(i).rjust(3) + " | " + l)
