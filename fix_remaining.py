"""
fix_remaining.py
================
Fixes 2 remaining issues after migration:

Issue 1: 6 pipeline scripts missing from D:/MICC/data_pipeline/
  - daily_update.py, update_delivery.py, update_macro_us.py,
    update_mf_nav.py, phase2_greeks_calculator.py, check_db_health.py
  These exist in D:/MICC/ root (copied from DATA-ANALYSIS).
  Just copy them into data_pipeline/ as well.

Issue 2: npm run dev fails - node_modules not copied (intentional,
  node_modules is excluded from copy). Need to run npm install first.

Run from D:/MICC/:
  py fix_remaining.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

MICC = Path(r"D:\MICC")
PIPE = MICC / "data_pipeline"
DASH = MICC / "micc-dashboard"


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "ERR": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print("[%s]  %s" % (tag, msg))


# =============================================================================
# FIX 1: Copy missing pipeline scripts from D:/MICC/ root -> data_pipeline/
# =============================================================================
print()
print("=" * 55)
print("  FIX 1: Copying missing pipeline scripts")
print("=" * 55)

SCRIPTS_TO_COPY = [
    "daily_update.py",
    "update_delivery.py",
    "update_macro_us.py",
    "update_macro_india_fred.py",
    "update_world_bank_india.py",
    "update_mf_nav.py",
    "update_fundamentals.py",
    "update_corporate_actions.py",
    "phase2_greeks_calculator.py",
    "phase4_corporate_announcements.py",
    "insider_trading_fetch.py",
    "refresh_stock_registry.py",
    "refresh_bse_registry.py",
    "build_tradable_universe.py",
    "extract_bhavcopy_universe.py",
    "fill_parquet_from_delivery.py",
    "check_db_health.py",
    "optimize_db.py",
    "backfill_fo_data.py",
    "backfill_indices.py",
    "master_update_part1.py",
    "master_update_part2.py",
    "master_update_part3.py",
]

copied  = 0
missing = 0
for name in SCRIPTS_TO_COPY:
    src = MICC / name          # already in D:/MICC/ root
    dst = PIPE / name          # needs to be in data_pipeline/
    if dst.exists():
        log("Already exists: data_pipeline/%s" % name)
        copied += 1
        continue
    if src.exists():
        shutil.copy2(src, dst)
        log("Copied: %s" % name, "OK")
        copied += 1
    else:
        log("NOT FOUND in D:/MICC/: %s" % name, "WARN")
        missing += 1

print()
log("Copied %d scripts into data_pipeline/" % copied, "OK")
if missing > 0:
    log("%d scripts not found (optional/not critical)" % missing, "WARN")


# =============================================================================
# FIX 2: Update paths in copied scripts
# =============================================================================
print()
print("=" * 55)
print("  FIX 2: Checking paths in data_pipeline scripts")
print("=" * 55)

# These scripts use relative paths like Path("db/market.db")
# When run from D:/MICC/data_pipeline/ they need absolute paths.
# The ones that matter most: daily_update, phase2_greeks, check_db_health.
# We patch any relative DB path to absolute.

RELATIVE_PATHS_TO_FIX = {
    'Path("db/market.db")'           : r'Path(r"D:\marketDB\db\market.db")',
    "Path('db/market.db')"           : r'Path(r"D:\marketDB\db\market.db")',
    'Path("db/market.db")'           : r'Path(r"D:\marketDB\db\market.db")',
    'Path("logs/'                    : r'Path(r"D:\MICC\data_pipeline\logs/',
    "Path('logs/"                    : r'Path(r"D:\MICC\data_pipeline\logs/',
    '"db/market.db"'                 : r'r"D:\marketDB\db\market.db"',
}

patched = 0
for script in PIPE.glob("*.py"):
    if script.name in ("config.py", "marketdb.py", "run_pipeline.py"):
        continue  # already have absolute paths
    try:
        content = script.read_text(encoding="utf-8", errors="replace")
        original = content

        # Fix relative DB path
        if 'Path("db/market.db")' in content:
            content = content.replace(
                'Path("db/market.db")',
                r'Path(r"D:\marketDB\db\market.db")'
            )
        if "Path('db/market.db')" in content:
            content = content.replace(
                "Path('db/market.db')",
                r'Path(r"D:\marketDB\db\market.db")'
            )
        # Fix log path
        if 'Path("logs/' in content:
            content = content.replace(
                'Path("logs/',
                r'Path(r"D:\MICC\data_pipeline\logs'
            )

        if content != original:
            script.write_text(content, encoding="utf-8")
            log("Patched paths in: %s" % script.name, "OK")
            patched += 1

    except Exception as e:
        log("Could not patch %s: %s" % (script.name, e), "WARN")

log("Patched %d scripts" % patched, "OK")


# =============================================================================
# FIX 3: npm install in micc-dashboard
# =============================================================================
print()
print("=" * 55)
print("  FIX 3: Installing dashboard dependencies (npm install)")
print("  This may take 1-2 minutes...")
print("=" * 55)
print()

if not DASH.exists():
    log("micc-dashboard folder not found at: %s" % DASH, "ERR")
    sys.exit(1)

package_json = DASH / "package.json"
if not package_json.exists():
    log("package.json not found in micc-dashboard/", "ERR")
    sys.exit(1)

log("Running npm install in %s..." % DASH)
try:
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(DASH),
        text=True,
        capture_output=False,  # show output live
        timeout=300
    )
    if result.returncode == 0:
        print()
        log("npm install completed", "OK")
    else:
        print()
        log("npm install failed (exit %d)" % result.returncode, "ERR")
        log("Try manually: cd D:/MICC/micc-dashboard && npm install", "WARN")
except FileNotFoundError:
    log("npm not found — make sure Node.js is installed and in PATH", "ERR")
    log("Download: https://nodejs.org/en/download", "WARN")
except subprocess.TimeoutExpired:
    log("npm install timed out (300s)", "ERR")
except Exception as e:
    log("npm install exception: %s" % e, "ERR")


# =============================================================================
print()
print("=" * 55)
print("  DONE")
print("=" * 55)
print()
print("  Now run:")
print()
print("  1. Verify everything is correct:")
print("     cd D:/MICC")
print("     py verify_migration.py")
print()
print("  2. Start dashboard:")
print("     cd D:/MICC/micc-dashboard")
print("     npm run dev")
print()
print("  3. Test agents:")
print("     cd D:/MICC")
print("     py agent_alpha.py")
print()
print("  4. Test pipeline:")
print("     cd D:/MICC/data_pipeline")
print("     py run_pipeline.py --check")
print()
