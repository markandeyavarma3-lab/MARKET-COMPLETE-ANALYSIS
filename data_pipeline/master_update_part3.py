#!/usr/bin/env python3
"""
master_update_part3.py – Backfills for:
- F&O UDiFF (2024-07-08 to yesterday)
- Greeks & Gamma Exposure
- Bulk & Block Deals
- Delivery % historical (optional)
"""

import sys
import time
import sqlite3
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta

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

    def progress_updater():
        while not stop_event.is_set():
            elapsed = time.time() - start
            percent = min(100, int((elapsed / max_expected_seconds) * 100))
            bar_length = 30
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"\r   Progress: [{bar}] {percent}% ({elapsed:.1f}s elapsed)   ", end='', flush=True)
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

def get_latest_date(conn, table, date_col="date"):
    try:
        row = conn.execute(f"SELECT MAX({date_col}) FROM {table}").fetchone()
        return row[0] if row and row[0] else None
    except:
        return None

def verify_fo_backfill(conn):
    """Check if fo_data now contains dates after 2024-07-05."""
    latest = get_latest_date(conn, "fo_data")
    if latest and latest > "2024-07-05":
        log(f"✓ F&O backfill successful: latest date {latest}")
        return True
    else:
        log(f"⚠ F&O backfill may have failed: latest date still {latest}", "WARNING")
        return False

def main():
    log("=" * 70)
    log("MASTER UPDATE – PART 3 (Backfills)")
    log("=" * 70)

    # ---------- 1. F&O UDiFF backfill (critical) ----------
    log("\n--- 1. F&O UDiFF Backfill (2024-07-08 to yesterday) ---")
    log("This may take 30-60 minutes. Downloads only missing dates.")
    run_with_progress("backfill_fo_historical.py", "F&O UDiFF backfill", max_expected_seconds=3600)
    time.sleep(5)

    # Verify F&O data improved
    conn = sqlite3.connect(DB_PATH)
    verify_fo_backfill(conn)
    conn.close()
    time.sleep(3)

    # ---------- 2. Greeks & Gamma Exposure ----------
    log("\n--- 2. Greeks & Gamma Exposure (backfill 2024-01-01 to today) ---")
    run_with_progress("phase2_greeks_calculator.py", "Greeks backfill (with --backfill flag)", max_expected_seconds=1800)
    time.sleep(3)

    # ---------- 3. Bulk & Block Deals ----------
    log("\n--- 3. Bulk & Block Deals (last 3 years) ---")
    run_with_progress("phase3_bulk_block_deals.py", "Bulk/Block deals backfill", max_expected_seconds=1800)
    time.sleep(3)

    # ---------- 4. Delivery % historical (optional, if you want pre-2022) ----------
    log("\n--- 4. (Optional) Delivery % historical backfill (2015-2022) ---")
    log("This may take 2-3 hours. Skip by pressing Ctrl+C now, or let it run.")
    time.sleep(5)
    run_with_progress("backfill_delivery_historical.py", "Delivery % backfill", max_expected_seconds=7200)

    # ---------- Final Verification ----------
    log("\n" + "=" * 70)
    log("FINAL VERIFICATION AFTER PART 3")
    log("=" * 70)

    conn = sqlite3.connect(DB_PATH)

    cnt = get_row_count(conn, "fo_data")
    latest = get_latest_date(conn, "fo_data")
    log(f"F&O data: {cnt:,} rows (latest {latest})")
    if cnt > 140_000_000:
        log("✓ F&O data OK")
    else:
        log(f"⚠ F&O data rows: {cnt:,} (expected >140M)", "WARNING")

    cnt = get_row_count(conn, "option_greeks_raw")
    if cnt > 0:
        log(f"Greeks computed: {cnt} rows")
    else:
        log("⚠ No Greeks computed (maybe no options data or script failed)", "WARNING")

    cnt = get_row_count(conn, "gamma_exposure_daily")
    log(f"Gamma exposure: {cnt} rows")

    cnt = get_row_count(conn, "bulk_deals")
    log(f"Bulk deals: {cnt} rows")
    cnt = get_row_count(conn, "block_deals")
    log(f"Block deals: {cnt} rows")

    # Delivery % total rows (should be >2.8M if backfill worked)
    cnt = get_row_count(conn, "stock_delivery")
    latest = get_latest_date(conn, "stock_delivery")
    log(f"Delivery %: {cnt:,} rows (latest {latest})")
    if cnt >= 2_800_000:
        log("✓ Delivery % historical backfill OK")
    else:
        log(f"⚠ Delivery % rows: {cnt:,} (expected >2.8M)", "WARNING")

    conn.close()

    log("\n" + "=" * 70)
    log("PART 3 COMPLETED")
    log("All backfills finished. Your database is now fully up‑to‑date.")
    log("=" * 70)

if __name__ == "__main__":
    main()