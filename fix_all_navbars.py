# -*- coding: utf-8 -*-
"""
fix_all_navbars.py  --  Run from D:\MICC

1. Fixes the syntax error in app/page.tsx (mport -> import)
2. Adds NavBar to ALL pages that are missing it
"""
from pathlib import Path
import re

DASH = Path(r"D:\MICC\micc-dashboard")
APP  = DASH / "src" / "app"

def read(p): return p.read_text(encoding="utf-8")
def write(p, c): p.write_text(c, encoding="utf-8")

# ── Fix root page.tsx syntax error first ─────────────────────────────────────
print("[1] Fixing root app/page.tsx syntax error...")
root = APP / "page.tsx"
c = read(root)
# The bug: "use client";\nimport NavBar...\nmport { ...  <- missing 'i'
c = re.sub(r'\nmport\s+\{', '\nimport {', c)
# Also ensure no duplicate "use client"
lines = c.splitlines()
new_lines = []
seen_use_client = False
for line in lines:
    if line.strip() == '"use client";':
        if seen_use_client:
            continue  # skip duplicate
        seen_use_client = True
    new_lines.append(line)
c = "\n".join(new_lines)
write(root, c)
print("  [OK] Syntax error fixed")

# ── Add NavBar to every page that's missing it ────────────────────────────────
print("\n[2] Adding NavBar to all pages...")

SKIP_PAGES = set()  # root page has custom sub-header but still needs NavBar

for page_file in sorted(APP.rglob("page.tsx")):
    c = read(page_file)
    rel = str(page_file.relative_to(DASH))
    
    # Skip if already has NavBar usage
    if "<NavBar" in c:
        print(f"  [OK]  {rel}")
        continue
    
    # Skip non-component files (shouldn't happen but safety)
    if "export default function" not in c:
        print(f"  [SKIP] {rel} (no default export)")
        continue

    # Add import if missing
    if 'import NavBar' not in c:
        c = c.replace(
            '"use client";\n',
            '"use client";\nimport NavBar from "@/components/NavBar";\n',
            1
        )

    # Insert <NavBar /> as first child of the outermost div in return
    # Pattern: the return block starts with <div style={{...minHeight...}}> or similar
    # Strategy: find `return (` then insert after the first `>` of the first tag
    
    # Try pattern 1: <div style={{ minHeight
    if re.search(r'<div style=\{\{[^}]*minHeight', c):
        c = re.sub(
            r'(<div style=\{\{[^}]*minHeight[^}]*\}[^>]*>)',
            r'\1\n      <NavBar />',
            c, count=1
        )
    # Try pattern 2: return (\n    <div  (generic)
    elif re.search(r'return \(\s*\n\s*<div', c):
        c = re.sub(
            r'(return \(\s*\n\s*<div[^>]*>)',
            r'\1\n      <NavBar />',
            c, count=1
        )
    else:
        print(f"  [WARN] {rel} -- could not find insert point, skipping")
        continue

    write(page_file, c)
    print(f"  [FIX] {rel} -- NavBar added")

print("""
Done!
  cd D:\\MICC\\micc-dashboard && npm run dev
""")
