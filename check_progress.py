"""
check_progress.py
Run in a NEW terminal to check status of all running jobs.
py check_progress.py
"""
import sqlite3, json, os
from pathlib import Path
from datetime import datetime

DB   = Path(r"D:\marketDB\db\market.db")
MICC = Path(r"D:\MICC")
PARK = Path(r"D:\marketDB\stocks\all")

print(f"\n=== MICC Status Check  {datetime.now().strftime('%H:%M:%S')} ===\n")

# 1. Consistency metric progress
try:
    conn = sqlite3.connect(str(DB), timeout=10)
    total = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]
    done  = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE consistency_v2 IS NOT NULL").fetchone()[0]
    avg   = conn.execute("SELECT AVG(consistency_v2) FROM seasonality_patterns_v3 WHERE consistency_v2 IS NOT NULL").fetchone()[0]
    conn.close()
    pct = 100*done/max(total,1)
    print(f"[1] Consistency metric fix:")
    print(f"    {done:>12,} / {total:,} rows done ({pct:.1f}%)")
    if avg: print(f"    avg consistency_v2 = {avg:.1f}%")
    if done == total: print("    STATUS: COMPLETE")
    elif done == 0:   print("    STATUS: Running (UPDATE not yet committed, normal for SQLite)")
    else:             print("    STATUS: In progress...")
except Exception as e:
    print(f"[1] Consistency check error: {e}")

print()

# 2. Adjusted prices progress
try:
    log = MICC / "adjusted_prices_log.json"
    adj_done = sum(1 for p in PARK.glob("*/adjusted.json")) if PARK.exists() else 0
    total_syms = len(list(PARK.iterdir())) if PARK.exists() else 0
    print(f"[2] Adjusted prices:")
    print(f"    {adj_done} / {total_syms} symbols adjusted")
    if log.exists():
        data = json.loads(log.read_text())
        print(f"    Last run: done={data.get('done',0)}  failed={data.get('failed',0)}")
        failed = data.get('failed_symbols', [])[:5]
        if failed: print(f"    Failed examples: {failed}")
    else:
        print("    Still running (no log file yet = in progress)")
except Exception as e:
    print(f"[2] Adjusted prices check error: {e}")

print()

# 3. FDR status
try:
    conn = sqlite3.connect(str(DB), timeout=10)
    kept = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE fdr_reject=1").fetchone()[0]
    conn.close()
    print(f"[3] FDR correction: {kept:,} real signals (should be 557,104) {'OK' if kept>500000 else 'CHECK'}")
except Exception as e:
    print(f"[3] FDR check error: {e}")

print()

# 4. Alert dedup
try:
    alerts_file = MICC / "alerts.json"
    if alerts_file.exists():
        data = json.loads(alerts_file.read_text())
        items = data if isinstance(data, list) else data.get("alerts", [])
        has_dedup = all("last_fired" in a for a in items) if items else False
        print(f"[4] Alert dedup: {'OK — last_fired in all alerts' if has_dedup else 'MISSING last_fired field'}")
        print(f"    {len(items)} alerts configured")
    else:
        print("[4] alerts.json not found")
except Exception as e:
    print(f"[4] Alert check error: {e}")

print()

# 5. .env security
try:
    env = MICC / ".env"
    if env.exists():
        content = env.read_text()
        has_groq = "GROQ_API_KEY" in content
        has_tele = "TELEGRAM_BOT_TOKEN" in content
        print(f"[5] .env file: {'OK' if has_groq and has_tele else 'INCOMPLETE'}")
        # Check if tokens are still the old ones
        if "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" in content:
            print("    WARNING: Groq key NOT rotated yet (still old key)")
        else:
            print("    Groq key: ROTATED OK")
        if "8420620581:AAGz9ztaCkj8KUJ5etBOaB0vmH69vHpeMRI" in content:
            print("    WARNING: Telegram token NOT rotated yet (still old token)")
        else:
            print("    Telegram token: ROTATED OK")
    else:
        print("[5] .env not found!")
except Exception as e:
    print(f"[5] .env check error: {e}")

print("\n" + "="*40)
