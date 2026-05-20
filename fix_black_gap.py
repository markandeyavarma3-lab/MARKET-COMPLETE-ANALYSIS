# -*- coding: utf-8 -*-
"""
fix_black_gap.py  --  Run from D:\MICC

THE ACTUAL PROBLEM (confirmed from screenshots):
  - localhost:3000 (root overview page) has its OWN top bar 
    ("Market Intelligence Command Center -- Overview" + PAUSED/RESUME)
  - fix_conviction_v3.py may have added an empty <div> or padding to layout.tsx
  - The black gap is an empty space between that custom top bar and the content
  - The /conviction page shows the NavBar correctly now (single bar, good)

REAL ROOT CAUSE:
  The fix scripts that tried to "remove NavBar from layout.tsx" corrupted 
  the layout by leaving a stray <div> or added margin/padding to <body>.
  Also the root page.tsx has a top bar + below it some pages render NavBar
  = stacked bars.

FIX:
  1. Reset layout.tsx to clean minimal version (no stray divs/padding)
  2. Check root page.tsx for any duplicate nav elements
  3. Remove any margin-top / padding-top added to body/html in globals.css

Run: py D:\MICC\fix_black_gap.py
"""
from pathlib import Path
import re, subprocess, sys

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src"
APP  = SRC / "app"

def write(path, content, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

def read(path):
    try: return path.read_text(encoding="utf-8")
    except: return ""

# ── STEP 1: Read and print current layout.tsx ─────────────────────────────
print("\n[1] Reading current layout.tsx...")
layout_path = APP / "layout.tsx"
if layout_path.exists():
    lt = read(layout_path)
    print("  CURRENT CONTENT:")
    for i, line in enumerate(lt.splitlines(), 1):
        print(f"    {i:3}: {line}")
else:
    print("  [MISSING] layout.tsx not found!")
    lt = ""

# ── STEP 2: Reset layout.tsx to clean version ─────────────────────────────
print("\n[2] Writing clean layout.tsx (no stray divs, no body padding)...")
clean_layout = """\
import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "MICC", description: "Market Intelligence Command Center" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0 }}>
        {children}
      </body>
    </html>
  );
}
"""
write(layout_path, clean_layout, "app/layout.tsx")

# ── STEP 3: Check globals.css for body margin/padding ─────────────────────
print("\n[3] Checking globals.css for rogue body/html margin...")
css_path = APP / "globals.css"
if css_path.exists():
    css = read(css_path)
    # Print body/html rules
    for i, line in enumerate(css.splitlines(), 1):
        if any(k in line.lower() for k in ["body", "html", "margin", "padding", "top"]):
            print(f"    {i:3}: {line}")
else:
    print("  globals.css not found")

# ── STEP 4: Check root page.tsx for duplicate nav elements ────────────────
print("\n[4] Checking root app/page.tsx for duplicate navbars...")
root_page = APP / "page.tsx"
if root_page.exists():
    rp = read(root_page)
    # Count NavBar imports/usages
    nb_imports = rp.count("import NavBar")
    nb_usages  = rp.count("<NavBar")
    print(f"  NavBar imports: {nb_imports}, usages: {nb_usages}")
    # Show the first 20 lines of the component return
    in_return = False
    count = 0
    for i, line in enumerate(rp.splitlines(), 1):
        if "return (" in line or "return(" in line:
            in_return = True
        if in_return:
            print(f"    {i:3}: {line}")
            count += 1
            if count > 25:
                print("    ...")
                break
else:
    print("  app/page.tsx not found")

# ── STEP 5: Check /conviction/page.tsx for double NavBar ──────────────────
print("\n[5] Checking /conviction/page.tsx...")
conv_page = APP / "conviction" / "page.tsx"
if conv_page.exists():
    cp = read(conv_page)
    nb = cp.count("<NavBar")
    print(f"  <NavBar> count: {nb}")
    if nb > 1:
        print("  [!!] DOUBLE NAVBAR IN CONVICTION PAGE - fixing...")
        # Keep only first occurrence
        fixed = cp.replace("<NavBar />", "__NAVBARPLACEHOLDER__", 1)
        fixed = fixed.replace("<NavBar />", "")
        fixed = fixed.replace("__NAVBARPLACEHOLDER__", "<NavBar />")
        write(conv_page, fixed, "conviction/page.tsx (deduped NavBar)")
    else:
        print("  [OK] Single NavBar")
else:
    print("  conviction/page.tsx not found")

# ── STEP 6: Scan ALL pages for double NavBar ──────────────────────────────
print("\n[6] Scanning all pages for double NavBar...")
for page_file in (APP).rglob("page.tsx"):
    content = read(page_file)
    count = content.count("<NavBar")
    if count > 1:
        rel = page_file.relative_to(MICC)
        print(f"  [!!] {rel} has {count} NavBars - fixing...")
        fixed = content.replace("<NavBar />", "__NB__", 1)
        fixed = fixed.replace("<NavBar />", "")
        fixed = fixed.replace("<NavBar/>", "")
        fixed = fixed.replace("__NB__", "<NavBar />")
        write(page_file, fixed, str(rel))
    elif count == 0:
        rel = page_file.relative_to(MICC)
        # Check if it's a page that SHOULD have NavBar (not root page which has custom bar)
        has_custom_bar = any(k in content for k in ["PAUSED", "RESUME", "RefreshController"])
        if not has_custom_bar and "export default function" in content:
            print(f"  [??] {rel} has NO NavBar (may be intentional)")

print("""
======================================================================
  BLACK GAP FIX COMPLETE
======================================================================

  What was checked/fixed:
  1. layout.tsx  -- reset to clean version, no stray divs
  2. globals.css -- printed for review
  3. root page.tsx -- checked for duplicate navbars
  4. conviction page -- checked for duplicate navbars
  5. ALL pages scanned for double <NavBar />

  RESTART:
    taskkill /f /im node.exe
    cd D:\\MICC\\micc-dashboard && npm run dev

  IF BLACK GAP STILL ON ROOT PAGE (/):
    The root page has its own custom top bar (PAUSED/RESUME/REFRESH).
    The "black gap" below it is padding from the page itself.
    
    Run this to check:
      py -c "
p = open(r'D:\\MICC\\micc-dashboard\\src\\app\\page.tsx', encoding='utf-8').read()
lines = p.splitlines()
# Find return statement
for i,l in enumerate(lines):
    if 'return' in l: 
        print('\\n'.join(f'{i+j+1}: {lines[i+j]}' for j in range(min(30, len(lines)-i))))
        break
"
    And paste the output here.
""")
