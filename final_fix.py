"""
final_fix.py
============
Fixes 2 remaining issues:

1. Pipeline scripts (daily_update.py etc) are in D:/marketDB/ not D:/MICC/
   Copies them from D:/marketDB/ into D:/MICC/data_pipeline/

2. Prints the correct npm command to run in a fresh terminal.

Run from D:/MICC/:
  py final_fix.py
"""

import shutil
import sys
from pathlib import Path

MICC     = Path(r"D:\MICC")
PIPE     = MICC / "data_pipeline"
MARKETDB = Path(r"D:\marketDB")   # original extraction project root

# Scripts that live in D:/marketDB/ (the original extraction project)
PIPELINE_SCRIPTS = [
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
    "master_update_part1.py",
    "master_update_part2.py",
    "master_update_part3.py",
]

print()
print("=" * 60)
print("  FINAL FIX — Pipeline scripts + npm guide")
print("=" * 60)
print()


# =============================================================================
# Step 1: Find where each script lives and copy it
# =============================================================================
print("[1] Copying pipeline scripts into D:/MICC/data_pipeline/")
print()

# Search locations in priority order
SEARCH_PATHS = [
    MARKETDB,                         # D:/marketDB/ (original home)
    MARKETDB / "scripts",             # D:/marketDB/scripts/ (possible subfolder)
    MICC,                             # D:/MICC/ root (already tried, but check again)
    Path(r"C:\Users\marka\OneDrive\Desktop\DATA-ANALYSIS"),  # OneDrive source
]

copied  = 0
already = 0
missing = []

for name in PIPELINE_SCRIPTS:
    dst = PIPE / name
    if dst.exists():
        print("  [SKIP]  Already exists: %s" % name)
        already += 1
        continue

    found = False
    for search_dir in SEARCH_PATHS:
        src = search_dir / name
        if src.exists():
            shutil.copy2(src, dst)
            print("  [ OK ]  Copied from %s: %s" % (search_dir.name, name))
            copied += 1
            found = True
            break

    if not found:
        print("  [MISS]  Not found anywhere: %s" % name)
        missing.append(name)

print()
print("  Copied: %d  |  Already existed: %d  |  Not found: %d" % (copied, already, len(missing)))

if missing:
    print()
    print("  Scripts not found (these live in D:/marketDB/ — check that path):")
    for m in missing:
        print("    - " + m)
    print()
    print("  If D:/marketDB/ has a different folder structure, run:")
    print("  py -c \"import os; [print(f) for f in os.listdir(r'D:/marketDB')]\"")


# =============================================================================
# Step 2: Patch relative DB paths in any copied scripts
# =============================================================================
print()
print("[2] Patching relative DB paths in pipeline scripts...")
print()

DB_FIXES = [
    ('Path("db/market.db")',  r'Path(r"D:\marketDB\db\market.db")'),
    ("Path('db/market.db')",  r'Path(r"D:\marketDB\db\market.db")'),
    ('"db/market.db"',        r'r"D:\marketDB\db\market.db"'),
    ("'db/market.db'",        r'r"D:\marketDB\db\market.db"'),
    ('Path("logs/',           r'Path(r"D:\MICC\data_pipeline\logs\\'),
    ("Path('logs/",           r'Path(r"D:\MICC\data_pipeline\logs\\'),
]

patched = 0
for script in PIPE.glob("*.py"):
    if script.name in ("config.py", "marketdb.py", "run_pipeline.py"):
        continue
    try:
        original = script.read_text(encoding="utf-8", errors="replace")
        content  = original
        for old, new in DB_FIXES:
            if old in content:
                content = content.replace(old, new)
        if content != original:
            script.write_text(content, encoding="utf-8")
            print("  [ OK ]  Patched: %s" % script.name)
            patched += 1
    except Exception as e:
        print("  [WARN]  Could not patch %s: %s" % (script.name, e))

if patched == 0:
    print("  [ OK ]  No patches needed (paths already absolute or no matches)")


# =============================================================================
# Step 3: npm install guide
# =============================================================================
print()
print("=" * 60)
print("[3] Dashboard npm install — MANUAL STEP REQUIRED")
print("=" * 60)
print()
print("  npm was not found in PATH. This happens when Node.js")
print("  was installed but the terminal doesn't see it yet.")
print()
print("  DO THIS — open a NEW PowerShell window and run:")
print()
print("    cd D:\\MICC\\micc-dashboard")
print("    npm install")
print("    npm run dev")
print()
print("  If npm still not found in a new terminal, Node.js needs")
print("  to be installed. Download from: https://nodejs.org")
print("  (LTS version, Windows installer)")
print()
print("  After npm install completes, open: http://localhost:3000")
print()


# =============================================================================
# Step 4: Quick agent test
# =============================================================================
print("=" * 60)
print("[4] Current Status Summary")
print("=" * 60)
print()

status_checks = [
    (MICC / "agent_alpha.py",     "agent_alpha.py"),
    (MICC / "agent_beta.py",      "agent_beta.py"),
    (MICC / "agent_gamma.py",     "agent_gamma.py"),
    (MICC / "agent_delta.py",     "agent_delta.py"),
    (MICC / "micc_engine.py",     "micc_engine.py"),
    (MICC / "telegram_bot.py",    "telegram_bot.py"),
    (MICC / "micc_data.py",       "micc_data.py"),
    (MICC / "micc_db_bridge.py",  "micc_db_bridge.py"),
    (PIPE / "config.py",          "data_pipeline/config.py"),
    (PIPE / "marketdb.py",        "data_pipeline/marketdb.py"),
    (PIPE / "run_pipeline.py",    "data_pipeline/run_pipeline.py"),
    (PIPE / "daily_update.py",    "data_pipeline/daily_update.py"),
    (PIPE / "check_db_health.py", "data_pipeline/check_db_health.py"),
]

all_ok = True
for path, label in status_checks:
    ok = path.exists()
    if not ok:
        all_ok = False
    print("  [%s]  %s" % ("PASS" if ok else "FAIL", label))

print()
if all_ok:
    print("  All files present. Project is fully migrated.")
else:
    print("  Some files still missing. Check D:/marketDB/ folder structure.")

print()
print("=" * 60)
print("  COMMANDS TO USE FROM NOW ON")
print("=" * 60)
print()
print("  Daily data update (after market close):")
print("    cd D:\\MICC\\data_pipeline")
print("    py run_pipeline.py")
print()
print("  Run intelligence engine:")
print("    cd D:\\MICC")
print("    py micc_engine.py 7 --send")
print()
print("  Dashboard:")
print("    cd D:\\MICC\\micc-dashboard")
print("    npm run dev")
print("    -> http://localhost:3000")
print()
print("  Telegram bot:")
print("    cd D:\\MICC")
print("    py telegram_bot.py")
print()
print("  Health check:")
print("    cd D:\\MICC\\data_pipeline")
print("    py run_pipeline.py --check")
print()
