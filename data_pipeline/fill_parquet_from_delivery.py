#!/usr/bin/env python3
"""Create Parquet OHLCV files from stock_delivery for missing symbols."""
import sqlite3, pandas as pd
from pathlib import Path

DB = r"D:\marketDB\db\market.db"
STOCKS_DIR = Path("stocks/all")
STOCKS_DIR.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB)
missing = conn.execute("""
    SELECT symbol FROM tradable_eq_stocks
    WHERE symbol NOT IN (
        SELECT DISTINCT symbol FROM stock_delivery
    )
""").fetchall()

if not missing:
    print("No missing symbols in delivery – all 2388 are covered.")
else:
    print(f"Found {len(missing)} symbols without Parquet data. Building from delivery…")

for (sym,) in missing:
    df = pd.read_sql(f"SELECT date, open, high, low, close, volume FROM stock_delivery WHERE symbol=? ORDER BY date", conn, params=(sym,))
    if df.empty:
        continue
    # Ensure numeric columns
    for col in ['open','high','low','close','volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close'])
    if df.empty:
        continue
    sym_dir = STOCKS_DIR / sym
    sym_dir.mkdir(exist_ok=True)
    df.to_parquet(sym_dir / "from_delivery.parquet", index=False)
    print(f"Created {sym} with {len(df)} rows")
conn.close()
print("Done.")