"""
run_pipeline.py
================
MICC Data Pipeline - Daily Orchestrator
Location: D:/MICC/data_pipeline/run_pipeline.py

Fully automatic. No manual file downloads needed.
Runs all data updates, downloads NSE snapshots automatically,
and runs the intelligence engine at the end.

Usage:
  cd D:/MICC/data_pipeline
  py run_pipeline.py              -> full update + snapshot + engine + Telegram
  py run_pipeline.py --check      -> health check only
  py run_pipeline.py --weekly     -> include fundamentals + corporate actions
  py run_pipeline.py --no-engine  -> skip engine at the end (data only)
"""

import subprocess
import sys
import time
import os
from datetime import datetime
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.resolve()
MICC_DIR     = PIPELINE_DIR.parent


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def clean_env():
    env = os.environ.copy()
    try:
        import certifi
        b = certifi.where()
        env["REQUESTS_CA_BUNDLE"] = b
        env["SSL_CERT_FILE"]      = b
        env["CURL_CA_BUNDLE"]     = b
    except ImportError:
        pass
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(script_path, desc, args=None, timeout=1800, cwd=None):
    cmd = [sys.executable, str(script_path)] + (args or [])
    log(f"-> {desc}")
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout,
            cwd=str(cwd or Path(script_path).parent),
            env=clean_env(),
        )
        elapsed = time.time() - t0
        if result.returncode == 0:
            log(f"{desc} ({elapsed:.0f}s)", "OK")
            return True
        else:
            log(f"{desc}  exit {result.returncode}  ({elapsed:.0f}s)", "FAIL")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-5:]:
                    log(f"   {line}", "FAIL")
            return False
    except subprocess.TimeoutExpired:
        log(f"{desc} timed out after {timeout}s", "FAIL")
        return False
    except Exception as e:
        log(f"{desc} exception: {e}", "FAIL")
        return False


def main():
    weekly    = "--weekly"    in sys.argv
    no_engine = "--no-engine" in sys.argv

    if "--check" in sys.argv:
        run(PIPELINE_DIR / "check_db_health.py", "DB Health Check", timeout=60)
        return

    print()
    print("=" * 65)
    print("  MICC DATA PIPELINE - FULL DAILY UPDATE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    print()

    r = {}

    # Phase 1 — Core market data
    r["core"]        = run(PIPELINE_DIR / "daily_update.py",
                           "Core: Stocks + Indices + FII/DII + F&O + Global",
                           timeout=1200)
    r["delivery"]    = run(PIPELINE_DIR / "update_delivery.py",
                           "Delivery % (nselib)", timeout=300)

    # Phase 2 — Macro
    r["us_macro"]    = run(PIPELINE_DIR / "update_macro_us.py",
                           "US Macro (FRED)", args=["--daily"], timeout=600)
    r["mf_nav"]      = run(PIPELINE_DIR / "update_mf_nav.py",
                           "MF NAVs", timeout=300)

    # Phase 3 — Corporate events
    r["announce"]    = run(PIPELINE_DIR / "phase4_corporate_announcements.py",
                           "Corporate Announcements", timeout=180)
    r["insider"]     = run(PIPELINE_DIR / "insider_trading_fetch.py",
                           "Insider Trading (SEBI)", timeout=180)

    # Phase 4 — Analytics
    r["greeks"]      = run(PIPELINE_DIR / "phase2_greeks_calculator.py",
                           "Greeks + GEX (incremental)", args=["--daily"], timeout=600)

    # Phase 5 — Slow macro
    r["world_bank"]  = run(PIPELINE_DIR / "update_world_bank_india.py",
                           "World Bank India Macro", timeout=180)
    r["india_macro"] = run(PIPELINE_DIR / "update_macro_india_fred.py",
                           "FRED India Macro", args=["--daily"], timeout=300)

    # Phase 6 — NSE Snapshot auto-download (NO MANUAL FILES NEEDED)
    snap = MICC_DIR / "auto_update_snapshot.py"
    if snap.exists():
        r["snapshot"] = run(snap,
                            "NSE Snapshot auto-download -> market_snapshot",
                            timeout=600, cwd=MICC_DIR)
    else:
        log("auto_update_snapshot.py not in D:/MICC/ — copy it there", "WARN")
        r["snapshot"] = False

    # Phase 7 — Weekly (optional)
    if weekly:
        r["fundamentals"]  = run(PIPELINE_DIR / "update_fundamentals.py",
                                 "Fundamentals TTM", timeout=7200)
        r["corp_actions"]  = run(PIPELINE_DIR / "update_corporate_actions.py",
                                 "Corporate Actions", timeout=1800)

    # Phase 8 — Health check
    run(PIPELINE_DIR / "check_db_health.py", "Health Check", timeout=60)

    # Phase 9 — Intelligence engine (unless --no-engine)
    if not no_engine:
        eng = MICC_DIR / "micc_engine.py"
        if eng.exists():
            r["engine"] = run(eng, "MICC Engine (all agents + Telegram)",
                              args=["7", "--send"],
                              timeout=900, cwd=MICC_DIR)
        else:
            log("micc_engine.py not found", "WARN")
            r["engine"] = False

    # Summary
    passed = sum(1 for v in r.values() if v)
    failed = sum(1 for v in r.values() if not v)
    print()
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    for name, ok in r.items():
        print(f"  [{'OK  ' if ok else 'FAIL'}]  {name}")
    print()
    log(f"Passed: {passed}  |  Failed: {failed}")
    print("=" * 65)
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
