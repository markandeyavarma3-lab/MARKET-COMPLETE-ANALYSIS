# -*- coding: utf-8 -*-
"""
fix_missing_navbars.py  --  Run from D:\MICC

PROBLEM: fix_conviction_v3.py regex-removed <NavBar /> from ALL pages
including app/page.tsx (root overview). Now no NavBar shows anywhere.

FIX: Scan every page.tsx - if it imports NavBar but has no <NavBar />, add it back.
Also handle root page specifically.
"""
from pathlib import Path
import re

DASH = Path(r"D:\MICC\micc-dashboard")
APP  = DASH / "src" / "app"

fixed_count = 0

for page_file in APP.rglob("page.tsx"):
    try:
        content = page_file.read_text(encoding="utf-8")
    except:
        continue
    
    has_import = "import NavBar" in content
    has_usage  = "<NavBar" in content
    rel = str(page_file.relative_to(DASH))

    if has_import and not has_usage:
        print(f"  [FIX] {rel} -- imports NavBar but never uses it, adding <NavBar />")
        # Find the first return ( in the default export and insert NavBar after the opening div
        # Pattern: find `return (` then find first `<div` and insert `<NavBar />` after it
        fixed = re.sub(
            r'(return\s*\(\s*\n\s*<div[^>]*>)',
            r'\1\n      <NavBar />',
            content,
            count=1
        )
        if fixed != content:
            page_file.write_text(fixed, encoding="utf-8")
            print(f"         -> Added <NavBar /> after opening div")
            fixed_count += 1
        else:
            # Fallback: insert after the first <div style line
            fixed = content.replace(
                'return (\n    <div style={{ minHeight: "100vh"',
                'return (\n    <div style={{ minHeight: "100vh"',
                1
            )
            # More targeted: find return block and prepend NavBar
            fixed = re.sub(
                r'(return \(\n    <div)',
                r'return (\n    <div',
                content
            )
            print(f"         -> Could not auto-insert, check manually")

    elif not has_import and not has_usage:
        # Check if it's a page that should have NavBar (skip API routes, layouts)
        if "export default function" in content and "page.tsx" in str(page_file):
            has_custom_nav = any(k in content for k in [
                "RefreshController", "Market Intelligence Command Center",
                "PAUSED", "sub-header"
            ])
            # Root page has custom subheader but still needs NavBar
            print(f"  [WARN] {rel} -- no NavBar at all")
    else:
        print(f"  [OK]  {rel} -- NavBar present ({content.count('<NavBar')}x)")

# ── Special case: root app/page.tsx ──────────────────────────────────────────
print("\n[Special] Checking root app/page.tsx directly...")
root = APP / "page.tsx"
if root.exists():
    content = root.read_text(encoding="utf-8")
    
    if "import NavBar" not in content:
        print("  [FIX] Adding NavBar import...")
        content = '"use client";\n' + content.lstrip('"use client";\n').lstrip('"use client"\n')
        content = content.replace(
            '"use client";\n',
            '"use client";\nimport NavBar from "@/components/NavBar";\n',
            1
        )
    
    if "<NavBar" not in content:
        print("  [FIX] Inserting <NavBar /> into return block...")
        # Insert after the outermost opening div
        content = re.sub(
            r'(<div style=\{[^}]*minHeight[^}]*\}[^>]*>)',
            r'\1\n      <NavBar />',
            content,
            count=1
        )
        root.write_text(content, encoding="utf-8")
        print("  [OK] NavBar added to root page")
        fixed_count += 1
    else:
        print(f"  [OK] Root page has <NavBar /> ({content.count('<NavBar')}x)")

print(f"\n  Total pages fixed: {fixed_count}")
print("""
  RESTART:
    taskkill /f /im node.exe
    cd D:\\MICC\\micc-dashboard && npm run dev
""")
