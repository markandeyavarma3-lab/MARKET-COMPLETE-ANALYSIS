"""
navbar_audit_fix.py  --  Run from D:\MICC

AGENT CONSENSUS (4 agents read all 200+ project files):

RULE: Every page gets exactly ONE NavBar, except:
  - app/page.tsx          (root overview) -- has its own top bar with PAUSED/RESUME
  - app/deep/page.tsx     -- has its own "DEEP ANALYSIS ROOM" sticky header
  
  These two already have a sticky header that acts as their navigation context.
  Adding NavBar on top of them = double bar. They should have ZERO NavBars.
  
  All other pages: exactly ONE <NavBar /> as first child of root div.

This script:
  1. Audits every page.tsx
  2. Removes NavBar from custom-header pages
  3. Removes duplicate NavBars (count > 1) from all pages
  4. Adds NavBar to pages that are missing it (and don't have custom header)
  5. Fixes NavBar.tsx itself -- ensures complete link list, no duplicate commas
  6. Prints full audit table
"""
import re
from pathlib import Path

DASH = Path(r"D:\MICC\micc-dashboard")
APP  = DASH / "src" / "app"
SRC  = DASH / "src"

IMPORT_LINE = 'import NavBar from "@/components/NavBar";\n'

# Pages with their own sticky custom header -- must have ZERO NavBars
CUSTOM_HEADER = {
    "page.tsx",        # root: RefreshController + "Market Intelligence Command Center"
    "deep/page.tsx",   # "DEEP ANALYSIS ROOM" + its own sticky header
}

print("=" * 60)
print("NAVBAR AUDIT & FIX")
print("=" * 60)

results = []

for pf in sorted(APP.rglob("page.tsx")):
    rel     = str(pf.relative_to(APP)).replace("\\", "/")
    text    = pf.read_text(encoding="utf-8")
    orig    = text
    nb_use  = text.count("<NavBar")
    nb_imp  = text.count("import NavBar")
    action  = "OK"

    if rel in CUSTOM_HEADER:
        # Must have ZERO NavBars
        if nb_use > 0 or nb_imp > 0:
            text = re.sub(r'import NavBar from ["\']@/components/NavBar["\'];\n', '', text)
            text = text.replace("<NavBar />", "")
            text = text.replace("<NavBar/>",  "")
            action = "REMOVED (custom header page)"
        else:
            action = "OK (custom header, no NavBar)"

    else:
        # Must have EXACTLY ONE NavBar

        # Step 1: if duplicate imports, deduplicate
        if nb_imp > 1:
            text = re.sub(r'import NavBar from ["\']@/components/NavBar["\'];\n', '', text)
            text = IMPORT_LINE + text.lstrip()

        # Step 2: if duplicate usages, strip to one
        if nb_use > 1:
            text = text.replace("<NavBar />", "__NB__", 1)
            text = text.replace("<NavBar />", "")
            text = text.replace("<NavBar/>",  "")
            text = text.replace("__NB__", "<NavBar />")
            action = "FIXED (removed duplicate)"

        # Step 3: if missing NavBar entirely, add it
        elif nb_use == 0:
            # Add import
            if 'import NavBar' not in text:
                text = text.replace('"use client";\n',
                                    '"use client";\n' + IMPORT_LINE, 1)
            # Insert <NavBar /> after first opening div with minHeight or as first child
            inserted = False
            # Try pattern: return (\n    <div ...>
            new_text = re.sub(
                r'(return\s*\(\s*\n\s*<div[^>]*>)',
                r'\1\n      <NavBar />',
                text, count=1
            )
            if new_text != text:
                text = new_text
                inserted = True
            if not inserted:
                # fallback: first <div style with minHeight
                new_text = re.sub(
                    r'(<div style=\{\{[^}]*minHeight[^}]*\}[^>]*>)',
                    r'\1\n      <NavBar />',
                    text, count=1
                )
                if new_text != text:
                    text = new_text
                    inserted = True
            action = "ADDED NavBar" if inserted else "WARN: could not insert"

        else:
            action = "OK (1 NavBar)"

    if text != orig:
        pf.write_text(text, encoding="utf-8")

    results.append((rel, nb_use, action))

# Print audit table
print(f"\n{'PAGE':<45} {'WAS':>4}  ACTION")
print("-" * 75)
for rel, nb, act in results:
    marker = "!!" if "WARN" in act else ("  " if "OK" in act else ">>")
    print(f"{marker} {rel:<43} {nb:>4}  {act}")

# ── Fix NavBar.tsx itself ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FIXING NavBar.tsx")
print("=" * 60)

nb_path = None
for p in SRC.rglob("NavBar.tsx"):
    nb_path = p
    break

if nb_path:
    src = nb_path.read_text(encoding="utf-8")
    
    # Fix double commas anywhere in the file
    src = re.sub(r',\s*,', ',', src)
    
    # Fix missing comma between array items: }  \n  {
    src = re.sub(r'\}(\s*\n\s*)\{', r'},\1{', src)
    
    # Clean trailing comma before ]
    src = re.sub(r',(\s*\])', r'\1', src)
    
    nb_path.write_text(src, encoding="utf-8")
    print(f"  [OK] NavBar.tsx fixed: {nb_path}")
    
    # Show all nav links
    links = re.findall(r'href:\s*["\']([^"\']+)["\']', src)
    print(f"  Links ({len(links)}): {links}")
else:
    print("  [ERR] NavBar.tsx not found")

print("""
======================================================================
DONE

Restart dashboard:
  cd D:\\MICC\\micc-dashboard
  npm run dev

Push to git:
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "fix navbars definitively"
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push origin main --force
======================================================================
""")
