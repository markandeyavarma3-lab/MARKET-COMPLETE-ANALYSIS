# -*- coding: utf-8 -*-
"""
verify_migration.py
====================
Run after migrate_to_d_drive.py and fix_dashboard_bugs.py
to confirm the new D:\\MICC project is healthy.

Usage:
  cd D:\\MICC
  py verify_migration.py

Checks:
  1. D:\\MICC directory structure
  2. D:\\MICC\\data_pipeline scripts present
  3. D:\\marketDB\\db\\market.db accessible
  4. Key DB tables + row counts
  5. Parquet store accessible
  6. Dashboard route.ts files use D:/MICC path
  7. micc_data.py uses D:\\MICC path
  8. data_pipeline\\config.py has correct absolute paths
"""

import sqlite3
import sys
from pathlib import Path

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

issues = []

def check(label: str, ok: bool, detail: str = "", warn: bool = False):
    if ok:
        print(f"  {PASS}  {label}")
        if detail:
            print(f"         {detail}")
    elif warn:
        print(f"  {WARN}  {label}")
        if detail:
            print(f"         {detail}")
    else:
        print(f"  {FAIL}  {label}")
        if detail:
            print(f"         {detail}")
        issues.append(label)


# ── 1. Directory structure ─────────────────────────────────────────────────────
print()
print("=" * 65)
print("  MICC Migration Verification")
print("=" * 65)
print()
print("[1] Directory Structure")

ROOT     = Path(r"D:\MICC")
PIPELINE = ROOT / "data_pipeline"
DB       = Path(r"D:\marketDB\db\market.db")
STOCKS   = Path(r"D:\marketDB\stocks\all")

check("D:\\MICC\\ exists",            ROOT.exists())
check("D:\\MICC\\data_pipeline\\ exists", PIPELINE.exists())
check("D:\\MICC\\micc-dashboard\\ exists", (ROOT / "micc-dashboard").exists())
check("D:\\MICC\\agents\\ exists",
      (ROOT / "agents").exists(), warn=True)  # OK if not yet — created at runtime

key_files = [
    "micc_data.py", "micc_engine.py", "micc_db_bridge.py",
    "agent_alpha.py", "agent_beta.py", "agent_gamma.py", "agent_delta.py",
    "telegram_bot.py", "health_check.py",
]
for f in key_files:
    check(f"D:\\MICC\\{f}", (ROOT / f).exists())


# ── 2. Pipeline scripts ────────────────────────────────────────────────────────
print()
print("[2] Data Pipeline Scripts")

pipeline_scripts = [
    "config.py", "marketdb.py", "run_pipeline.py",
    "daily_update.py", "update_delivery.py", "update_macro_us.py",
    "update_mf_nav.py", "phase2_greeks_calculator.py",
    "check_db_health.py",
]
for f in pipeline_scripts:
    check(f"data_pipeline\\{f}", (PIPELINE / f).exists())

# Check config.py has absolute paths
config_path = PIPELINE / "config.py"
if config_path.exists():
    content = config_path.read_text(encoding="utf-8")
    has_abs = r"D:\marketDB" in content
    has_old = "OneDrive" in content
    check("config.py uses absolute paths (D:\\marketDB)", has_abs)
    check("config.py has no OneDrive references", not has_old,
          "Found OneDrive path — update config.py" if has_old else "")


# ── 3. Database accessibility ─────────────────────────────────────────────────
print()
print("[3] Database")

check("D:\\marketDB\\db\\market.db exists", DB.exists(),
      f"Size: {DB.stat().st_size / 1e9:.1f} GB" if DB.exists() else "FILE NOT FOUND")

if DB.exists():
    try:
        conn = sqlite3.connect(str(DB), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")

        tables_needed = [
            "indices_data", "fo_data", "fii_dii_data", "stock_delivery",
            "global_data", "option_greeks_raw", "gamma_exposure_daily",
            "us_macro_data", "stock_fundamentals", "mf_nav_history",
            "tradable_eq_stocks", "market_snapshot",
        ]
        for t in tables_needed:
            r = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
            if r:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                check(f"Table: {t}", True, f"{n:,} rows")
            else:
                check(f"Table: {t}", False, "TABLE MISSING")

        # market_snapshot column names (critical for dashboard)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(market_snapshot)").fetchall()]
        has_index_name = "index_name" in cols
        has_closing    = "closing_index_value" in cols
        check("market_snapshot.index_name column exists", has_index_name)
        check("market_snapshot.closing_index_value column exists", has_closing,
              f"Columns: {cols}")

        conn.close()
    except Exception as e:
        check("DB connection", False, str(e))


# ── 4. Parquet store ─────────────────────────────────────────────────────────
print()
print("[4] Parquet Stock Store")

if STOCKS.exists():
    sym_dirs = [d for d in STOCKS.iterdir() if d.is_dir()]
    has_parquets = sum(1 for d in sym_dirs if any(d.glob("*.parquet")))
    check(f"D:\\marketDB\\stocks\\all\\ exists", True)
    check(f"Symbols with Parquet files",
          has_parquets >= 2000,
          f"{has_parquets:,} symbols found")
else:
    check("D:\\marketDB\\stocks\\all\\ exists", False)


# ── 5. Dashboard path checks ──────────────────────────────────────────────────
print()
print("[5] Dashboard Route.ts Paths")

# Try both src/ and non-src layouts
dash_src = ROOT / "micc-dashboard" / "src" / "app" / "api"
dash_plain = ROOT / "micc-dashboard" / "app" / "api"
api_dir = dash_src if dash_src.exists() else (dash_plain if dash_plain.exists() else None)

if api_dir:
    old_path_count = 0
    route_files = list(api_dir.rglob("route.ts"))
    check(f"Found {len(route_files)} route.ts files", len(route_files) > 0)
    for rf in route_files:
        content = rf.read_text(encoding="utf-8", errors="replace")
        if "OneDrive" in content or "DATA-ANALYSIS" in content:
            old_path_count += 1
    if old_path_count == 0:
        check("No route.ts files have old OneDrive path", True)
    else:
        check(f"{old_path_count} route.ts files still use old path", False,
              "Run fix_dashboard_bugs.py to update")
else:
    check("Dashboard API directory found", False, warn=True)


# ── 6. micc_data.py path ──────────────────────────────────────────────────────
print()
print("[6] micc_data.py")

micc_data = ROOT / "micc_data.py"
if micc_data.exists():
    content = micc_data.read_text(encoding="utf-8", errors="replace")
    has_old  = "OneDrive" in content
    has_abs  = r"D:\marketDB" in content or 'D:/marketDB' in content
    check("micc_data.py has absolute DB path", has_abs)
    check("micc_data.py has no OneDrive reference", not has_old,
          "Still has OneDrive path — re-run migrate_to_d_drive.py" if has_old else "")
else:
    check("micc_data.py exists in D:\\MICC\\", False)


# ── Summary ────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
if not issues:
    print("  ALL CHECKS PASSED — Migration verified successfully")
    print()
    print("  Next steps:")
    print("  1. Start dashboard:  cd D:\\MICC\\micc-dashboard && npm run dev")
    print("  2. Test agent:       cd D:\\MICC && py agent_alpha.py")
    print("  3. Test pipeline:    cd D:\\MICC\\data_pipeline && py run_pipeline.py --check")
    print("  4. Use marketdb API: cd D:\\MICC && py data_pipeline\\marketdb.py")
else:
    print(f"  {len(issues)} issue(s) found:")
    for issue in issues:
        print(f"    - {issue}")
    print()
    print("  Run fix_dashboard_bugs.py and migrate_to_d_drive.py to resolve.")
print("=" * 65)
print()
