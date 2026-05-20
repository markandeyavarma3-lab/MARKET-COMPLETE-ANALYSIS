import sqlite3
c = sqlite3.connect(r"D:\marketDB\db\market.db", timeout=30)
total  = c.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]
done   = c.execute("SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE score_v2 IS NOT NULL").fetchone()[0]
kept   = c.execute("SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE fdr_reject=1").fetchone()[0]
undone = c.execute("SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE score_v2 IS NULL").fetchone()[0]
print(f"Total:      {total:>12,}")
print(f"Processed:  {done:>12,}  ({100*done/max(total,1):.1f}%)")
print(f"Remaining:  {undone:>12,}")
print(f"FDR kept:   {kept:>12,}  ({100*kept/max(done,1):.1f}% of processed)")
c.close()
