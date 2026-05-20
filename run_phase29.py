#!/usr/bin/env python3
"""
run_phase29.py — Run all Phase 29 steps in order
=================================================
Run from D:\MICC\:
  py run_phase29.py

Steps:
  1. build_piotroski.py   — compute F-Score → symbol_quality_scores
  2. build_conviction.py  — fuse all layers → symbol_conviction
  3. build_phase29.py     — write dashboard files

Also patches run_pipeline.py to add phase 12 = conviction rebuild.
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

DA = Path(r"D:\MICC")

def run(script: str, label: str):
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {label}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(DA / script)],
        cwd=DA,
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"❌ {label} FAILED (exit code {result.returncode})")
        return False
    print(f"✅ {label} complete")
    return True


def patch_pipeline():
    """Add conviction rebuild as phase 12 in run_pipeline.py"""
    pipeline = DA / "data_pipeline" / "run_pipeline.py"
    if not pipeline.exists():
        print("⚠️  run_pipeline.py not found, skipping patch")
        return

    text = pipeline.read_text(encoding="utf-8")
    if "build_piotroski" in text:
        print("✅ Pipeline already has conviction phases")
        return

    # Find the phases list and add two new ones
    # Look for the pattern of PHASES list or phases dict
    old_marker = '"check_db_health"'
    if old_marker not in text:
        # Try alternate patterns
        old_marker = "phase11"
        if old_marker not in text:
            print("⚠️  Could not find pipeline phase insertion point")
            return

    new_phases = '''
    # Phase 12: Piotroski F-Score quality scoring
    {
        "name": "piotroski_fscore",
        "script": str(DA / "build_piotroski.py"),
        "label": "Piotroski F-Score → symbol_quality_scores",
    },
    # Phase 13: Conviction score fusion
    {
        "name": "conviction_build",
        "script": str(DA / "build_conviction.py"),
        "label": "Conviction fusion → symbol_conviction",
    },
'''
    print("⚠️  Pipeline patch skipped — add conviction phases manually after verifying pipeline structure")


def main():
    print(f"\n⚡ MICC Phase 29 — Conviction Score System")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    steps = [
        ("build_piotroski.py",  "Step 1: Piotroski F-Score (symbol_quality_scores)"),
        ("build_conviction.py", "Step 2: Conviction Fusion (symbol_conviction)"),
        ("build_phase29.py",    "Step 3: Dashboard files"),
    ]

    for script, label in steps:
        ok = run(script, label)
        if not ok:
            print(f"\n❌ Aborting at: {label}")
            sys.exit(1)

    patch_pipeline()

    print(f"\n{'='*60}")
    print("⚡ PHASE 29 COMPLETE")
    print(f"{'='*60}")
    print("\nNext steps:")
    print("  → Visit http://localhost:3000/conviction")
    print("  → Check symbol_conviction table in DB")
    print("  → Add to run_pipeline.py phases list")
    print("\nNext build (Phase 30):")
    print("  → Cross-asset signals (DXY/VIX/Gold → NIFTY conditionals)")
    print("  → my_portfolio table + ATR position sizing")
    print("  → Exit signals (seasonal window close + ATR trailing stop)")


if __name__ == "__main__":
    main()
