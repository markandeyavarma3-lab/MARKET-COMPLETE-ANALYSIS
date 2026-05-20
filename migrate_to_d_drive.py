"""
migrate_to_d_drive.py
=====================
Moves DATA-ANALYSIS from OneDrive to D:/MICC
and sets up D:/MICC/data_pipeline/ for the extraction pipeline.

Run from DATA-ANALYSIS folder:
  py migrate_to_d_drive.py
"""

import shutil
import sys
from pathlib import Path
from datetime import datetime

# -- Paths (raw strings to avoid escape issues) --------------------------------
SRC  = Path(r"D:\MICC")
DST  = Path(r"D:\MICC")
PIPE = DST / "data_pipeline"

IGNORE_DIRS = {"node_modules", ".next", "__pycache__", ".git"}
IGNORE_EXTS = {".pyc", ".pyo"}

PIPELINE_SCRIPTS = [
    "config.py", "marketdb.py", "daily_update.py", "run_all.py",
    "update_delivery.py", "update_macro_us.py", "update_macro_india_fred.py",
    "update_world_bank_india.py", "update_mf_nav.py", "update_fundamentals.py",
    "update_corporate_actions.py", "phase2_greeks_calculator.py",
    "phase4_corporate_announcements.py", "insider_trading_fetch.py",
    "refresh_stock_registry.py", "refresh_bse_registry.py",
    "build_tradable_universe.py", "extract_bhavcopy_universe.py",
    "fill_parquet_from_delivery.py", "check_db_health.py", "optimize_db.py",
    "backfill_fo_data.py", "backfill_indices.py",
    "master_update_part1.py", "master_update_part2.py", "master_update_part3.py",
]


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print("[%s] %-4s  %s" % (ts, level, msg))
    sys.stdout.flush()


def confirm(prompt):
    try:
        ans = input("\n%s [y/N]: " % prompt).strip().lower()
        return ans == "y"
    except KeyboardInterrupt:
        return False


def copy_tree(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    for item in src.rglob("*"):
        rel   = item.relative_to(src)
        parts = rel.parts
        if any(p in IGNORE_DIRS for p in parts):
            skipped += 1
            continue
        if item.is_file():
            if item.suffix in IGNORE_EXTS:
                skipped += 1
                continue
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, out)
            copied += 1
        elif item.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
    return copied, skipped


def main():
    print()
    print("=" * 60)
    print("  MICC PROJECT MIGRATION")
    print("  OneDrive/DATA-ANALYSIS  ->  D:/MICC/")
    print("=" * 60)
    print()

    if not SRC.exists():
        log("Source not found: %s" % SRC, "ERR")
        sys.exit(1)

    if DST.exists():
        log("D:/MICC already exists", "WARN")
        if not confirm("Merge/overwrite D:/MICC?"):
            log("Aborted.", "WARN")
            sys.exit(0)

    log("Source : %s" % SRC)
    log("Dest   : %s" % DST)
    log("DB     : D:/marketDB/db/market.db  (stays, not moved)")
    print()

    if not confirm("Proceed with migration?"):
        log("Aborted.", "WARN")
        sys.exit(0)

    print()

    # -- Step 1: Copy DATA-ANALYSIS -> D:/MICC --------------------------------
    log("STEP 1/5  Copying MICC project (skipping node_modules)...")
    copied, skipped = copy_tree(SRC, DST)
    log("  Copied %d files, skipped %d" % (copied, skipped), "OK")

    # -- Step 2: Create data_pipeline directory --------------------------------
    log("STEP 2/5  Creating data_pipeline/ directory...")
    PIPE.mkdir(parents=True, exist_ok=True)
    (PIPE / "logs").mkdir(exist_ok=True)
    log("  Created D:/MICC/data_pipeline/", "OK")

    # -- Step 3: Copy extraction scripts into data_pipeline --------------------
    log("STEP 3/5  Copying extraction scripts into data_pipeline/...")
    found = 0
    for name in PIPELINE_SCRIPTS:
        src_f = SRC / name
        if src_f.exists():
            shutil.copy2(src_f, PIPE / name)
            found += 1
    log("  Copied %d scripts" % found, "OK")

    # -- Step 4: Update hardcoded paths in Python + TS files -------------------
    log("STEP 4/5  Updating hardcoded OneDrive paths...")
    old_fwd  = "D:/MICC"
    old_back = "C:\\Users\\marka\\OneDrive\\Desktop\\DATA-ANALYSIS"
    new_fwd  = "D:/MICC"
    new_back = "D:\\MICC"

    updated_py = 0
    for py_file in DST.rglob("*.py"):
        if any(p in py_file.parts for p in IGNORE_DIRS):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            original = content
            content = content.replace(old_fwd, new_fwd)
            content = content.replace(old_back, new_back)
            if content != original:
                py_file.write_text(content, encoding="utf-8")
                updated_py += 1
        except Exception:
            pass

    updated_ts = 0
    for api_dir in [
        DST / "micc-dashboard" / "src" / "app" / "api",
        DST / "micc-dashboard" / "app" / "api",
    ]:
        if api_dir.exists():
            for ts_file in api_dir.rglob("route.ts"):
                try:
                    content = ts_file.read_text(encoding="utf-8")
                    original = content
                    content = content.replace(old_fwd, new_fwd)
                    content = content.replace(old_back, new_back)
                    if content != original:
                        ts_file.write_text(content, encoding="utf-8")
                        updated_ts += 1
                except Exception:
                    pass

    log("  Updated %d Python files, %d route.ts files" % (updated_py, updated_ts), "OK")

    # -- Step 5: Write README --------------------------------------------------
    log("STEP 5/5  Writing README.md...")
    readme_lines = [
        "# MICC - Market Intelligence Command Center",
        "",
        "## Layout",
        "",
        "  D:\\MICC\\                    <- Intelligence layer",
        "  D:\\MICC\\data_pipeline\\     <- Data extraction pipeline",
        "  D:\\marketDB\\                <- 53GB database (not moved)",
        "",
        "## Daily Commands",
        "",
        "  # Update data (after 3:30 PM IST)",
        "  cd D:\\MICC\\data_pipeline",
        "  py run_pipeline.py",
        "",
        "  # Run engine",
        "  cd D:\\MICC",
        "  py micc_engine.py 7 --send",
        "",
        "  # Dashboard",
        "  cd D:\\MICC\\micc-dashboard",
        "  npm run dev",
        "",
        "  # Health check",
        "  cd D:\\MICC\\data_pipeline",
        "  py run_pipeline.py --check",
    ]
    (DST / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
    log("  Written D:/MICC/README.md", "OK")

    print()
    print("=" * 60)
    print("  MIGRATION COMPLETE")
    print("=" * 60)
    print()
    print("  D:/MICC/                    <- new project root")
    print("  D:/MICC/data_pipeline/      <- extraction pipeline")
    print("  D:/marketDB/db/market.db    <- database (unchanged)")
    print()
    print("  NOW DO THIS:")
    print()
    print("  1. Copy these 4 files into D:/MICC/data_pipeline/")
    print("       marketdb.py")
    print("       config.py")
    print("       run_pipeline.py")
    print("       requirements_pipeline.txt")
    print()
    print("  2. cd D:/MICC")
    print("     py verify_migration.py")
    print()
    print("  3. cd D:/MICC/micc-dashboard")
    print("     npm run dev")
    print()
    print("  4. After verifying, delete the OneDrive copy:")
    print("     D:/MICC/")
    print()


if __name__ == "__main__":
    main()
