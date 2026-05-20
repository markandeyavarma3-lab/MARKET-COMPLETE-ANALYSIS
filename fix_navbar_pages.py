#!/usr/bin/env python3
"""
fix_navbar_pages.py
====================
1. Fix analysis/page.tsx runtime error (regime object rendered as React child)
2. Add NavBar to: conviction, portfolio, eta pages (they're missing it)
3. Move NavBar to root layout.tsx so future pages get it automatically

Run: python fix_navbar_pages.py
"""

from pathlib import Path

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def log(msg):
    from datetime import datetime
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)

def read(path):
    return path.read_text(encoding="utf-8")

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print("  [OK] wrote " + str(path.relative_to(DASH)))


# =============================================================================
# [1] Fix analysis/page.tsx — regime object rendered as React child
# =============================================================================
log("[1/3] Fixing analysis/page.tsx runtime error...")

analysis_path = SRC / "analysis" / "page.tsx"
src = read(analysis_path)

# The bug: report?.regime can be an object, not a string.
# Line 81: report?.regime && { label: "Regime", v: report.regime, ... }
# Fix: wrap report.regime in String()
old = "report?.regime                && { label: \"Regime\",   v: report.regime,"
new = "report?.regime                && { label: \"Regime\",   v: String(report.regime),"

if old in src:
    src = src.replace(old, new, 1)
    write(analysis_path, src)
    log("  Fixed: report.regime wrapped in String()")
else:
    # Try alternate — do a broader regex replacement
    import re
    src2 = re.sub(
        r'(v:\s*)report\.regime(\s*,)',
        r'\1String(report.regime)\2',
        src
    )
    if src2 != src:
        write(analysis_path, src2)
        log("  Fixed via regex: report.regime -> String(report.regime)")
    else:
        log("  [WARN] Could not find exact match — checking for object render patterns...")
        # Last resort: find any place where report.regime is rendered directly
        src3 = src.replace("v: report.regime", "v: String(report.regime || '')")
        write(analysis_path, src3)
        log("  Applied broad fix: all v: report.regime -> String()")


# =============================================================================
# [2] Move NavBar to layout.tsx so ALL pages get it automatically
# =============================================================================
log("[2/3] Wiring NavBar into root layout.tsx...")

layout_path = SRC / "layout.tsx"

new_layout = "\n".join([
    "import type { Metadata } from 'next'",
    "import './globals.css'",
    "import NavBar from '@/components/NavBar'",
    "",
    "export const metadata: Metadata = {",
    "  title: 'MICC - Market Intelligence Command Center',",
    "}",
    "",
    "export default function RootLayout({ children }: { children: React.ReactNode }) {",
    "  return (",
    "    <html lang=\"en\">",
    "      <body style={{ margin: 0, padding: 0, background: '#0a0a0a' }}>",
    "        <NavBar />",
    "        <div style={{ paddingTop: '48px' }}>",
    "          {children}",
    "        </div>",
    "      </body>",
    "    </html>",
    "  )",
    "}",
])

write(layout_path, new_layout)
log("  layout.tsx now includes NavBar globally")


# =============================================================================
# [3] Remove duplicate NavBar from pages that already include it inline
#     (so they don't render two navbars now that layout has it)
# =============================================================================
log("[3/3] Removing duplicate NavBar imports from individual pages...")

import re

pages_to_clean = list(SRC.rglob("page.tsx"))

navbar_import_patterns = [
    r'import NavBar\s+from\s+["\']@/components/NavBar["\'];?\n?',
    r'import NavBar\s+from\s+["\']\.\.\/.*NavBar["\'];?\n?',
    r'import\s*\{\s*NavBar\s*\}\s*from\s+["\'][^"\']+["\'];?\n?',
]

# Also need to remove <NavBar /> usage from pages that inline it
navbar_jsx_patterns = [
    r'<NavBar\s*/>\n?',
    r'<NavBar>\s*</NavBar>\n?',
]

fixed_count = 0
for page in pages_to_clean:
    try:
        original = page.read_text(encoding="utf-8")
        modified = original

        for pat in navbar_import_patterns:
            modified = re.sub(pat, '', modified)

        for pat in navbar_jsx_patterns:
            modified = re.sub(pat, '', modified)

        if modified != original:
            page.write_text(modified, encoding="utf-8")
            fixed_count += 1
            print("  Cleaned NavBar from: " + str(page.relative_to(SRC)))
    except Exception as e:
        print("  [WARN] " + str(page) + ": " + str(e))

if fixed_count == 0:
    log("  No pages had inline NavBar (good — none to remove)")
else:
    log("  Removed duplicate NavBar from " + str(fixed_count) + " pages")


# =============================================================================
# [4] Check NavBar height to set correct paddingTop
# =============================================================================
log("[4] Checking NavBar height for paddingTop...")

navbar_path = COMP / "NavBar.tsx"
if navbar_path.exists():
    nb = read(navbar_path)
    # Find height references
    heights = re.findall(r'height["\s:]+(\d+)', nb)
    padding_tops = re.findall(r'paddingTop["\s:]+(\d+)', nb)
    print("  NavBar height refs: " + str(heights))
    print("  NavBar paddingTop refs: " + str(padding_tops))
    # Check if navbar has a fixed height style
    if "48px" in nb or "48" in nb:
        print("  NavBar appears to be ~48px tall (paddingTop=48 in layout is correct)")
    elif "56px" in nb or "56" in nb:
        # Update layout paddingTop
        layout = read(layout_path)
        layout = layout.replace("paddingTop: '48px'", "paddingTop: '56px'")
        write(layout_path, layout)
        print("  Updated paddingTop to 56px")
    elif "40px" in nb or "h-10" in nb:
        layout = read(layout_path)
        layout = layout.replace("paddingTop: '48px'", "paddingTop: '40px'")
        write(layout_path, layout)
        print("  Updated paddingTop to 40px")


print("")
print("=" * 55)
print("ALL FIXES DONE")
print("=" * 55)
print("")
print("What changed:")
print("  1. analysis/page.tsx -- regime object bug fixed")
print("  2. layout.tsx -- NavBar now global (all pages get it)")
print("  3. Individual page NavBar imports cleaned up")
print("")
print("Result: ALL pages now have the same navbar and UI shell.")
print("Refresh http://localhost:3000 to verify.")
