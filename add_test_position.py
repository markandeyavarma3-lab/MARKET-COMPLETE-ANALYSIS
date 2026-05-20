"""
add_test_position.py  v2
Checks actual my_portfolio schema first, then inserts correctly.
Run: py add_test_position.py
"""
import sqlite3
from datetime import datetime

DB = r"D:\marketDB\db\market.db"
conn = sqlite3.connect(DB, timeout=15)

# Show actual schema
cols_info = conn.execute("PRAGMA table_info(my_portfolio)").fetchall()
if not cols_info:
    print("Table my_portfolio does not exist. Creating...")
    conn.execute("""
    CREATE TABLE my_portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        entry_date TEXT,
        entry_price REAL,
        quantity REAL,
        atr_at_entry REAL,
        stop_loss REAL,
        target_price REAL,
        position_size_pct REAL,
        notes TEXT,
        last_updated TEXT
    )""")
    conn.commit()
    cols_info = conn.execute("PRAGMA table_info(my_portfolio)").fetchall()

col_names = [r[1] for r in cols_info]
print(f"my_portfolio columns: {col_names}")

# Build insert using only columns that exist
existing = conn.execute(
    "SELECT COUNT(*) FROM my_portfolio WHERE symbol='RELIANCE'"
).fetchone()[0]

if existing:
    print(f"\nRELIANCE already in portfolio ({existing} rows).")
else:
    # Map to actual column names
    target_col = "target_price" if "target_price" in col_names else \
                 "target"       if "target"       in col_names else None
    stop_col   = "stop_loss"    if "stop_loss"    in col_names else \
                 "stop"         if "stop"         in col_names else None
    ts_col     = "last_updated" if "last_updated" in col_names else None

    # Build dynamic insert
    base_cols = ["symbol", "entry_date", "entry_price", "quantity"]
    base_vals = ["RELIANCE", "2026-05-18", 1453.0, 10]

    if stop_col:
        base_cols.append(stop_col); base_vals.append(1385.0)
    if target_col:
        base_cols.append(target_col); base_vals.append(1600.0)
    if "notes" in col_names:
        base_cols.append("notes"); base_vals.append("Test position - ATR sized")
    if ts_col:
        base_cols.append(ts_col)
        base_vals.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    ph = ",".join("?" * len(base_cols))
    sql = f"INSERT INTO my_portfolio ({','.join(base_cols)}) VALUES ({ph})"
    print(f"\nInserting: {dict(zip(base_cols, base_vals))}")
    conn.execute(sql, base_vals)
    conn.commit()
    print("Added RELIANCE position.")

# Show all positions
rows = conn.execute("SELECT * FROM my_portfolio ORDER BY entry_date DESC").fetchall()
print(f"\nAll positions ({len(rows)}):")
print(f"  {' | '.join(col_names)}")
print(f"  {'-'*80}")
for r in rows:
    print(f"  {' | '.join(str(v) for v in r)}")

conn.close()
