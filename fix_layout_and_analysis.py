#!/usr/bin/env python3
"""
fix_layout_and_analysis.py
===========================
1. Shows what's in root layout.tsx (so we understand navbar inclusion)
2. Fixes the analysis page runtime error (object rendered as React child)
3. Fixes conviction/portfolio pages to NOT include their own full-page wrapper
   (since layout.tsx already provides navbar + wrapper)

Run: python fix_layout_and_analysis.py
"""

from pathlib import Path

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def log(msg):
    from datetime import datetime
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)

# =============================================================================
# [1] Read and print layout.tsx so we know the structure
# =============================================================================
log("[1] Reading root layout.tsx...")

layout_path = SRC / "layout.tsx"
if layout_path.exists():
    content = layout_path.read_text(encoding="utf-8")
    print("  layout.tsx found (" + str(len(content.splitlines())) + " lines)")
    print("  First 60 lines:")
    for i, line in enumerate(content.splitlines()[:60], 1):
        print("    " + str(i).rjust(3) + " | " + line)
else:
    print("  layout.tsx NOT found at " + str(layout_path))
    # Check alternate locations
    for f in DASH.rglob("layout.tsx"):
        print("  Found layout at: " + str(f))

# =============================================================================
# [2] Read analysis page to find the runtime error
# =============================================================================
log("[2] Reading analysis/page.tsx for runtime error...")

analysis_path = SRC / "analysis" / "page.tsx"
if analysis_path.exists():
    content = analysis_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    print("  analysis/page.tsx: " + str(len(lines)) + " lines")
    # Find where market_snapshot object is rendered
    for i, line in enumerate(lines, 1):
        if any(k in line for k in ["market_snapshot", "latest_close", "return_1d", "regime", "confidence", "snapshot"]):
            print("    " + str(i).rjust(4) + " | " + line)
else:
    print("  analysis/page.tsx NOT found")
    for f in DASH.rglob("analysis"):
        print("  Found: " + str(f))

# =============================================================================
# [3] List all page.tsx files to see what we're dealing with
# =============================================================================
log("[3] All page.tsx files in src/app:")
for f in sorted(SRC.rglob("page.tsx")):
    rel = str(f.relative_to(SRC))
    size = f.stat().st_size
    print("  " + rel.ljust(40) + str(size) + " bytes")

log("Done. Review output above, then run fix step 2.")
