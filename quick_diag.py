"""
quick_diag.py  --  Run from D:\MICC
Quick check: what's actually in stock_data for AXISBANK
"""
import sqlite3
from pathlib import Path

DB = Path(r"D:\marketDB\db\market.db")
conn = sqlite3.connect(DB, timeout=15)

print("=== TABLES IN DB ===")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
for t in tables:
    print(f"  {t[0]}")

print("\n=== stock_data: column names ===")
try:
    cols = conn.execute("PRAGMA table_info(stock_data)").fetchall()
    for c in cols:
        print(f"  {c[1]:20s}  {c[2]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== stock_data: AXISBANK rows ===")
try:
    rows = conn.execute(
        "SELECT * FROM stock_data WHERE symbol='AXISBANK' ORDER BY date DESC LIMIT 5"
    ).fetchall()
    print(f"  Count: {len(rows)}")
    for r in rows:
        print(f"  {r}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== stock_data: total AXISBANK rows ===")
try:
    n = conn.execute("SELECT COUNT(*) FROM stock_data WHERE symbol='AXISBANK'").fetchone()[0]
    print(f"  {n:,} rows")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== stock_data: close values for AXISBANK ===")
try:
    rows = conn.execute(
        "SELECT date, close FROM stock_data WHERE symbol='AXISBANK' AND close IS NOT NULL ORDER BY date DESC LIMIT 10"
    ).fetchall()
    print(f"  Rows with close != NULL: {len(rows)}")
    for r in rows:
        print(f"  {r[0]}  close={r[1]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== stock_data: distinct symbols count ===")
try:
    n = conn.execute("SELECT COUNT(DISTINCT symbol) FROM stock_data").fetchone()[0]
    print(f"  {n:,} symbols")
    # Sample some
    syms = conn.execute("SELECT symbol, COUNT(*) as n FROM stock_data GROUP BY symbol ORDER BY n DESC LIMIT 10").fetchall()
    print("  Top 10 by row count:")
    for s, c in syms:
        print(f"    {s:<20} {c:>6,}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Check if AXISBANK is in stock_delivery instead ===")
try:
    n = conn.execute("SELECT COUNT(*) FROM stock_delivery WHERE symbol='AXISBANK'").fetchone()[0]
    print(f"  stock_delivery AXISBANK rows: {n:,}")
    if n > 0:
        rows = conn.execute(
            "SELECT * FROM stock_delivery WHERE symbol='AXISBANK' ORDER BY date DESC LIMIT 3"
        ).fetchall()
        cols2 = conn.execute("PRAGMA table_info(stock_delivery)").fetchall()
        print(f"  stock_delivery columns: {[c[1] for c in cols2]}")
        for r in rows:
            print(f"  {r}")
except Exception as e:
    print(f"  stock_delivery check: {e}")

print("\n=== Check bhavcopy / market_snapshot for AXISBANK ===")
for tbl in ["bhavcopy", "market_snapshot", "stock_registry"]:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE symbol='AXISBANK'").fetchone()[0]
        print(f"  {tbl}: {n:,} rows")
        if n > 0 and tbl != "stock_registry":
            r = conn.execute(f"SELECT * FROM {tbl} WHERE symbol='AXISBANK' ORDER BY date DESC LIMIT 2").fetchall()
            print(f"    Sample: {r[0] if r else 'none'}")
    except Exception as e:
        print(f"  {tbl}: {e}")

conn.close()
print("\nDone.")
