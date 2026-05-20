#!/usr/bin/env python3
"""
master_update_part1.py – Core Daily + US Macro + MF NAVs
Simplified, robust version.
"""

import sys
import time
import sqlite3
import subprocess
import threading
from pathlib import Path
from datetime import datetime

DB_PATH = Path(r"D:\marketDB\db\market.db")

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp}  {msg}")
    sys.stdout.flush()

def run_script(script_name, description, max_wait_sec=600):
    log(f"▶ Starting: {description}")
    start = time.time()
    stop = threading.Event()
    def progress():
        while not stop.is_set():
            elapsed = time.time() - start
            pct = min(100, int(elapsed / max_wait_sec * 100))
            bar = '█' * (pct // 3) + '░' * (33 - pct // 3)
            print(f"\r   [{bar}] {pct}% ({elapsed:.0f}s)   ", end='', flush=True)
            time.sleep(2)
    t = threading.Thread(target=progress, daemon=True)
    t.start()
    try:
        proc = subprocess.run([sys.executable, script_name], capture_output=True, text=True, timeout=max_wait_sec+30)
        stop.set()
        t.join(1)
        elapsed = time.time() - start
        if proc.returncode != 0:
            # Special case: daily_update.py before market close
            if script_name == "daily_update.py" and "excluded – re-run after 3:30 PM" in proc.stderr:
                log(f"⚠ {description} finished with warning (before market close)")
                log(f"✅ Completed in {elapsed:.1f}s")
                return True
            log(f"❌ {description} failed (exit {proc.returncode})")
            if proc.stderr:
                log(f"   Error: {proc.stderr[:300]}")
            return False
        log(f"✅ Completed in {elapsed:.1f}s")
        return True
    except subprocess.TimeoutExpired:
        stop.set()
        log(f"⏰ Timeout: {description} > {max_wait_sec//60} min")
        return False
    except Exception as e:
        stop.set()
        log(f"💥 Exception: {e}")
        return False

def main():
    log("=" * 60)
    log("PART 1 – Daily Core + US Macro + MF NAVs")
    log("=" * 60)

    run_script("daily_update.py", "A) Core daily update", 600)
    time.sleep(2)
    run_script("update_macro_us.py", "B) US macro", 600)
    time.sleep(2)
    run_script("update_mf_nav.py", "C) MF NAVs", 120)

    # Verification
    log("\n" + "=" * 60)
    log("VERIFICATION")
    conn = sqlite3.connect(DB_PATH)
    tables = ["indices_data", "fii_dii_data", "global_data", "us_macro_data", "mf_nav_history", "fo_data"]
    for t in tables:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        latest = conn.execute(f"SELECT MAX(date) FROM {t}").fetchone()[0]
        log(f"{t:20} {cnt:>12,} rows   latest {latest}")
    conn.close()
    log("=" * 60)
    log("Part 1 done. Run master_update_part2.py next.")

if __name__ == "__main__":
    main()