# -*- coding: utf-8 -*-
"""
patch_phase9a_pipeline.py  (v2 — robust, indent-agnostic)
==========================================================
Adds Phase 9A global indices fetch to run_pipeline.py.
Finds the health-check block by line scanning (no brittle string match),
detects indent automatically, inserts before it.

Run from D:/MICC/data_pipeline/:
  py patch_phase9a_pipeline.py
"""

import sys
from pathlib import Path
from datetime import datetime

PIPELINE_DIR = Path(r"D:\MICC\data_pipeline")
RUN_PIPELINE = PIPELINE_DIR / "run_pipeline.py"


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{tag}]  {msg}")


def main():
    print()
    print("=" * 60)
    print("  Patch v2: Add Phase 9A to run_pipeline.py")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    if not RUN_PIPELINE.exists():
        log(f"run_pipeline.py not found: {RUN_PIPELINE}", "FAIL")
        sys.exit(1)

    content = RUN_PIPELINE.read_text(encoding="utf-8")
    lines   = content.splitlines()

    # Already patched?
    if "phase9a_fetch_global_indices" in content:
        log("Already patched — phase9a already present", "WARN")
        sys.exit(0)

    # Find the line containing "check_db_health" (the health check run() call)
    # Walk back from it to find the comment line above it
    health_line_idx = None
    for i, line in enumerate(lines):
        if "check_db_health" in line:
            # Walk back to find the comment block above it (up to 4 lines)
            start = i
            for j in range(i - 1, max(i - 5, -1), -1):
                stripped = lines[j].strip()
                if stripped.startswith("#"):
                    start = j
                    break
            health_line_idx = start
            break

    if health_line_idx is None:
        log("Could not locate check_db_health in run_pipeline.py", "FAIL")
        log("Paste this block manually just before the health check line:", "WARN")
        print()
        print("    # Phase 9A — Global indices daily update (incremental)")
        print("    r[\"global_idx\"] = run(")
        print("        PIPELINE_DIR / \"phase9a_fetch_global_indices.py\",")
        print("        \"Global Indices (yfinance incremental)\",")
        print("        timeout=180, cwd=PIPELINE_DIR)")
        print()
        sys.exit(1)

    # Detect indentation from the health-check comment or run() line
    ref_line = lines[health_line_idx]
    indent   = len(ref_line) - len(ref_line.lstrip())
    pad      = " " * indent

    new_block = [
        f"{pad}# Phase 9A -- Global indices daily update (incremental)",
        f"{pad}r[\"global_idx\"] = run(",
        f"{pad}    PIPELINE_DIR / \"phase9a_fetch_global_indices.py\",",
        f"{pad}    \"Global Indices (yfinance incremental)\",",
        f"{pad}    timeout=180, cwd=PIPELINE_DIR)",
        f"",
        f"{pad}# Phase 9B -- Monthly index window-stats rebuild (indices only, ~10 min)",
        f"{pad}# Full stock rebuild is manual: py phase9b_build_window_stats.py --resume",
        f"{pad}from datetime import datetime as _dt9b",
        f"{pad}if _dt9b.today().day == 1:",
        f"{pad}    log(\"1st of month: rebuilding index window stats (Phase 9B)\")",
        f"{pad}    r[\"win_stats\"] = run(",
        f"{pad}        PIPELINE_DIR / \"phase9b_build_window_stats.py\",",
        f"{pad}        \"Window Stats rebuild (indices)\",",
        f"{pad}        args=[\"--indices-only\", \"--resume\"],",
        f"{pad}        timeout=900, cwd=PIPELINE_DIR)",
        f"",
    ]

    new_lines   = lines[:health_line_idx] + new_block + lines[health_line_idx:]
    new_content = "\n".join(new_lines) + "\n"

    # Backup
    backup = RUN_PIPELINE.with_suffix(".py.bak")
    backup.write_text(content, encoding="utf-8")
    log(f"Backup written: {backup.name}")

    RUN_PIPELINE.write_text(new_content, encoding="utf-8")
    log("run_pipeline.py patched", "OK")

    # Verify
    if "phase9a_fetch_global_indices" in RUN_PIPELINE.read_text(encoding="utf-8"):
        log("Verification passed", "OK")
    else:
        log("Verification FAILED — check the file manually", "FAIL")
        sys.exit(1)

    print()
    print("  Done. Global indices fetch now runs daily.")
    print("  Index window stats auto-rebuilt on 1st of each month.")
    print()


if __name__ == "__main__":
    main()
