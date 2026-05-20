"""
fix_pattern_scores.py  --  Run ONCE from D:\MICC
Removes patterns where |mean_ret| > 50% (price-level artifacts).
Run: py D:\MICC\fix_pattern_scores.py
"""
import sqlite3
from pathlib import Path

DB = Path(r"D:\marketDB\db\market.db")
conn = sqlite3.connect(DB, timeout=30)

print("Checking seasonality_patterns_v3 for outlier mean_ret...")

bad = conn.execute(
    "SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE ABS(mean_ret) > 50"
).fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]
print(f"  Total rows:   {total:,}")
print(f"  Outlier rows: {bad:,}  (|mean_ret| > 50%)")

if bad == 0:
    print("  No outliers -- nothing to do.")
    conn.close()
    raise SystemExit(0)

rows = conn.execute(
    "SELECT symbol, COUNT(*), AVG(ABS(mean_ret)), MAX(ABS(mean_ret)) "
    "FROM seasonality_patterns_v3 WHERE ABS(mean_ret) > 50 "
    "GROUP BY symbol ORDER BY AVG(ABS(mean_ret)) DESC LIMIT 20"
).fetchall()
print("\nTop symbols with outlier returns:")
for sym, cnt, avg_ret, max_ret in rows:
    print(f"  {sym:<35} {cnt:>6,} rows  avg={avg_ret:.1f}%  max={max_ret:.1f}%")

ans = input(f"\nDelete {bad:,} outlier rows? [y/n]: ").strip().lower()
if ans != "y":
    print("  Aborted.")
    conn.close()
    raise SystemExit(0)

conn.execute("DELETE FROM seasonality_patterns_v3 WHERE ABS(mean_ret) > 50")
conn.commit()
remaining = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]
conn.close()

print(f"\nDeleted {bad:,} outlier rows")
print(f"Remaining: {remaining:,} valid patterns")
print("Done. Restart dashboard -- /patterns-v3 will show clean data.")