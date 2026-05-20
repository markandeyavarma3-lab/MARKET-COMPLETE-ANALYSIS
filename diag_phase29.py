#!/usr/bin/env python3
"""Diagnose actual schemas and data for Phase 29 fixes"""
import sqlite3, json

DB = r"D:\marketDB\db\market.db"
conn = sqlite3.connect(DB, timeout=15)

# 1. seasonality_patterns columns
print("=== seasonality_patterns columns ===")
cols = conn.execute("PRAGMA table_info(seasonality_patterns)").fetchall()
for c in cols:
    print(f"  {c[1]} ({c[2]})")

# 2. screener_fundamentals columns
print("\n=== screener_fundamentals columns ===")
cols = conn.execute("PRAGMA table_info(screener_fundamentals)").fetchall()
for c in cols:
    print(f"  {c[1]} ({c[2]})")

# 3. quarterly_balance sample — what does a row look like?
print("\n=== quarterly_balance sample (1 symbol) ===")
rows = conn.execute(
    "SELECT symbol, report_date, data_json FROM quarterly_balance ORDER BY symbol LIMIT 1"
).fetchall()
for r in rows:
    print(f"  symbol={r[0]}, date={r[1]}")
    d = json.loads(r[2])
    print(f"  keys ({len(d)}): {list(d.keys())[:20]}")

# 4. How many symbols have >= 2 balance rows?
count = conn.execute("""
    SELECT COUNT(*) FROM (
        SELECT symbol FROM quarterly_balance
        GROUP BY symbol HAVING COUNT(*) >= 2
    )
""").fetchone()[0]
print(f"\n=== Symbols with >= 2 quarterly_balance rows: {count} ===")

# 5. quarterly_income sample
print("\n=== quarterly_income sample keys ===")
rows = conn.execute(
    "SELECT data_json FROM quarterly_income ORDER BY symbol LIMIT 1"
).fetchall()
if rows:
    d = json.loads(rows[0][0])
    print(f"  keys: {list(d.keys())[:30]}")

# 6. quarterly_cashflow sample
print("\n=== quarterly_cashflow sample keys ===")
rows = conn.execute(
    "SELECT data_json FROM quarterly_cashflow ORDER BY symbol LIMIT 1"
).fetchall()
if rows:
    d = json.loads(rows[0][0])
    print(f"  keys: {list(d.keys())[:20]}")

# 7. seasonality_patterns sample
print("\n=== seasonality_patterns sample row ===")
row = conn.execute("SELECT * FROM seasonality_patterns LIMIT 1").fetchone()
if row:
    desc = conn.execute("PRAGMA table_info(seasonality_patterns)").fetchall()
    for col, val in zip(desc, row):
        print(f"  {col[1]}: {val}")

conn.close()
print("\nDone.")
