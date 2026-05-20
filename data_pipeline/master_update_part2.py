#!/usr/bin/env python3
"""
master_update_part2.py – Fundamentals, Corporate Actions, Registry, Announcements, Insider Trading
Shows animated progress bars for each task.
"""

import sys
import time
import sqlite3
import subprocess
import threading
from pathlib import Path
from datetime import datetime

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp}  {level:<8}  {msg}")
    sys.stdout.flush()

def run_with_progress(script_name, description, max_expected_seconds=600):
    log(f"▶ Starting: {description}")
    start = time.time()
    stop_event = threading.Event()
    progress_event = threading.Event()

    def progress_updater():
        while not stop_event.is_set():
            elapsed = time.time() - start
            percent = min(100, int((elapsed / max_expected_seconds) * 100))
            bar_length = 30
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"\r   Progress: [{bar}] {percent}% ({elapsed:.1f}s elapsed)   ", end='', flush=True)
            progress_event.set()
            time.sleep(2)
        elapsed = time.time() - start
        bar = '█' * 30
        print(f"\r   Progress: [{bar}] 100% ({elapsed:.1f}s elapsed)   ", flush=True)

    t = threading.Thread(target=progress_updater, daemon=True)
    t.start()

    try:
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=max_expected_seconds + 60
        )
        stop_event.set()
        t.join(timeout=1)
        elapsed = time.time() - start
        if result.returncode != 0:
            print()
            log(f"❌ Failed: {description} (exit {result.returncode})", "ERROR")
            if result.stderr:
                log(f"   Stderr: {result.stderr[:800]}", "ERROR")
            return False
        print()
        log(f"✅ Completed: {description} in {elapsed:.1f}s")
        return True
    except subprocess.TimeoutExpired:
        stop_event.set()
        print()
        log(f"⏰ Timeout: {description} (> {max_expected_seconds//60} min)", "ERROR")
        return False
    except Exception as e:
        stop_event.set()
        print()
        log(f"💥 Exception: {description}: {e}", "ERROR")
        return False

def get_row_count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except:
        return 0

def main():
    log("=" * 70)
    log("MASTER UPDATE – PART 2 (Fundamentals, Corporate Actions, Registry, Announcements, Insider Trading)")
    log("=" * 70)

    # Task D: Stock fundamentals (longest)
    run_with_progress("update_fundamentals.py", "D) Stock fundamentals (TTM)", max_expected_seconds=7200)  # 1 hour
    time.sleep(5)

    # Task E: Corporate actions
    run_with_progress("update_corporate_actions.py", "E) Corporate actions (splits/dividends)", max_expected_seconds=1800)  # 15 min
    time.sleep(3)

    # Task F: Stock registry
    run_with_progress("refresh_stock_registry.py", "F) Stock registry (active symbols)", max_expected_seconds=120)
    time.sleep(2)

    # Task G: Corporate announcements
    run_with_progress("phase4_corporate_announcements.py", "G) Corporate announcements", max_expected_seconds=120)
    time.sleep(2)

    # Task H: Insider trading
    run_with_progress("insider_trading_fetch.py", "H) Insider trading", max_expected_seconds=120)
    time.sleep(2)

    # Verification
    log("\n" + "=" * 70)
    log("VERIFICATION AFTER PART 2")
    log("=" * 70)

    conn = sqlite3.connect(DB_PATH)

    cnt = get_row_count(conn, "stock_fundamentals")
    log(f"Stock fundamentals: {cnt} rows (one per active symbol)")
    if cnt >= 2000:
        log("✓ Stock fundamentals OK")
    else:
        log(f"⚠ Stock fundamentals low: {cnt} (expected ≥2000)", "WARNING")

    cnt = get_row_count(conn, "corporate_actions")
    log(f"Corporate actions: {cnt} rows")
    if cnt > 20000:
        log("✓ Corporate actions OK")
    else:
        log(f"⚠ Corporate actions low: {cnt}", "WARNING")

    cnt = get_row_count(conn, "stock_registry")
    active = conn.execute("SELECT COUNT(*) FROM stock_registry WHERE is_active=1").fetchone()[0]
    log(f"Stock registry: {cnt} total rows, {active} active symbols")
    if active >= 2000:
        log("✓ Stock registry OK")
    else:
        log(f"⚠ Stock registry low active symbols: {active}", "WARNING")

    cnt = get_row_count(conn, "corporate_announcements")
    latest = conn.execute("SELECT MAX(announcement_date) FROM corporate_announcements").fetchone()[0]
    log(f"Corporate announcements: {cnt} rows, latest {latest}")

    cnt = get_row_count(conn, "insider_trading")
    latest = conn.execute("SELECT MAX(filing_date) FROM insider_trading").fetchone()[0]
    log(f"Insider trading: {cnt} rows, latest filing {latest}")

    conn.close()

    log("\n" + "=" * 70)
    log("PART 2 COMPLETED")
    log("Run master_update_part3.py for optional backfills (Greeks, Bulk/Block, Delivery historical)")
    log("=" * 70)

if __name__ == "__main__":
    main()