# -*- coding: utf-8 -*-
"""
fix_duplicate_vars.py  --  Run from D:\\MICC
Removes duplicate state variable declarations in patterns/page.tsx
that were caused by multiple patch scripts running on the same file.
Run: py D:\\MICC\\fix_duplicate_vars.py
"""
import re
from pathlib import Path

BASE = Path(r"D:\MICC")
PAGE = BASE / "micc-dashboard" / "src" / "app" / "patterns" / "page.tsx"

if not PAGE.exists():
    print("ERROR: patterns/page.tsx not found")
    exit(1)

txt = PAGE.read_text(encoding="utf-8")
original_len = len(txt)

# ── Fix 1: Remove duplicate hover/lockA/lockB/svgContainerRef lines ───────
# These appear inside InteractiveYearChart function body multiple times
# The pattern is exactly 4 lines repeated N times — keep only first occurrence

DUPE_BLOCK = (
    "  const [hover,setHover]=useState<{yr:number;dayIdx:number;ret:number;screenX:number;screenY:number}|null>(null);\n"
    "  const [lockA,setLockA]=useState<{yr:number;dayIdx:number;ret:number}|null>(null);\n"
    "  const [lockB,setLockB]=useState<{yr:number;dayIdx:number;ret:number}|null>(null);\n"
    "  const svgContainerRef=useRef<HTMLDivElement>(null);\n"
)

# Count occurrences
count = txt.count(DUPE_BLOCK)
print(f"Found {count} occurrences of hover/lock state block")

if count > 1:
    # Keep only the first one, remove the rest
    first_idx = txt.find(DUPE_BLOCK)
    # Replace all occurrences after the first with empty string
    after_first = txt[first_idx + len(DUPE_BLOCK):]
    after_first_cleaned = after_first.replace(DUPE_BLOCK, "")
    txt = txt[:first_idx + len(DUPE_BLOCK)] + after_first_cleaned
    print(f"  Removed {count - 1} duplicate hover/lock blocks")

# ── Fix 2: Remove duplicate openPanels/togglePanel declarations ───────────
DUPE_PANELS = (
    "  const [openPanels,setOpenPanels]=useState<Set<string>>(new Set());\n"
    "  const togglePanel=(id:string)=>setOpenPanels(prev=>{const n=new Set(prev);n.has(id)?n.delete(id):n.add(id);return n;});\n"
)

count2 = txt.count(DUPE_PANELS)
print(f"Found {count2} occurrences of openPanels/togglePanel block")

if count2 > 1:
    first_idx = txt.find(DUPE_PANELS)
    after_first = txt[first_idx + len(DUPE_PANELS):]
    after_first_cleaned = after_first.replace(DUPE_PANELS, "")
    txt = txt[:first_idx + len(DUPE_PANELS)] + after_first_cleaned
    print(f"  Removed {count2 - 1} duplicate openPanels blocks")

# ── Fix 3: Catch any other exact-duplicate consecutive lines ───────────────
# Split into lines and deduplicate consecutive identical lines
lines = txt.split("\n")
deduped = []
i = 0
removed = 0
while i < len(lines):
    deduped.append(lines[i])
    # Check for block duplication: if next N lines are identical to current N lines
    # Only do this for non-empty state declaration lines
    if (lines[i].strip().startswith("const [") or
        lines[i].strip().startswith("const svg")):
        # Check if next line is identical
        if i + 1 < len(lines) and lines[i] == lines[i + 1]:
            # Skip duplicates
            while i + 1 < len(lines) and lines[i] == lines[i + 1]:
                i += 1
                removed += 1
    i += 1

if removed > 0:
    txt = "\n".join(deduped)
    print(f"  Removed {removed} additional duplicate lines")

# ── Save ──────────────────────────────────────────────────────────────────
PAGE.write_text(txt, encoding="utf-8", newline="\n")
new_len = len(txt)
print(f"\nFile size: {original_len:,} -> {new_len:,} chars (removed {original_len-new_len:,})")
print("Saved patterns/page.tsx")
print("\nNow restart: cd D:\\MICC\\micc-dashboard && npm run dev")
