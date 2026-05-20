# -*- coding: utf-8 -*-
"""
diagnose_beta.py
=================
Quick diagnostic to find exactly why load_all_symbols_window returns 0
even though parquet files now have updated data.

Run from D:/MICC/:
  py diagnose_beta.py
"""

from pathlib import Path
from datetime import datetime
import pandas as pd

PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")

# Pick a reliable symbol
sym  = "RELIANCE"
year = 2026

folder = PARQUET_ROOT / sym

print()
print("=" * 60)
print("  BETA DIAGNOSTIC — post parquet update")
print("=" * 60)
print()

# Step 1: Read the parquet file
pf = folder / f"{sym}_{year}.parquet"
if not pf.exists():
    pf = folder / f"{year}.parquet"

print(f"Reading: {pf}")
df = pd.read_parquet(pf)
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Last 5 rows:\n{df.tail(5).to_string()}")
print()

# Step 2: Simulate exactly what load_parquet_symbol does
print("--- Simulating load_parquet_symbol ---")
df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
print(f"Columns after lowercase: {list(df.columns)}")

# date column check
if "date" not in df.columns:
    if "date1" in df.columns:
        df["date"] = pd.to_datetime(df["date1"], errors="coerce")
        print("Used date1 for date")
    else:
        print("ERROR: No date column found!")
else:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    print(f"Parsed 'date' column")

null_dates = df["date"].isna().sum()
print(f"Null dates: {null_dates}/{len(df)}")
print(f"Date dtype: {df['date'].dtype}")
print(f"Last 5 dates:\n{df['date'].tail(5)}")
print(f"Max date: {df['date'].max()}")
print()

# close column check
print("--- Close column check ---")
print(f"'close' in columns: {'close' in df.columns}")
if "close" not in df.columns:
    for alias in ("close_price", "last_price", "ltp"):
        if alias in df.columns:
            print(f"Renaming '{alias}' -> 'close'")
            df.rename(columns={alias: "close"}, inplace=True)
            break
print(f"Close values (last 5): {df['close'].tail(5).tolist() if 'close' in df.columns else 'MISSING'}")
print()

# Step 3: Simulate load_all_symbols_window date filter
print("--- Date window filter (May 4-12 2026) ---")
start_d = "2026-05-04"
end_d   = "2026-05-12"
sd = pd.to_datetime(start_d)
ed = pd.to_datetime(end_d)
print(f"sd type: {type(sd)}, value: {sd}")
print(f"df['date'] dtype: {df['date'].dtype}")
print(f"df['date'] last value type: {type(df['date'].iloc[-1])}")

# The actual comparison
df = df.dropna(subset=["date"]).sort_values("date")
df_win = df[(df["date"] >= sd) & (df["date"] <= ed)].copy()
print(f"Rows in window May 4-12: {len(df_win)}")
if len(df_win) > 0:
    print(f"Window rows:\n{df_win[['date','close']].to_string()}")
else:
    print("EMPTY WINDOW — showing dates near May 4:")
    near = df[df["date"] >= pd.to_datetime("2026-04-28")]
    print(near[["date","close"]].to_string())
print()

# Step 4: Check MIN_PRICE filter
print("--- MIN_PRICE filter ---")
MIN_PRICE = 5.0
if "close" in df.columns and len(df_win) > 0:
    closes = pd.to_numeric(df_win["close"], errors="coerce").dropna()
    print(f"First close: {closes.iloc[0] if len(closes) > 0 else 'N/A'}")
    print(f"Passes MIN_PRICE ({MIN_PRICE}): {closes.iloc[0] > MIN_PRICE if len(closes) > 0 else 'N/A'}")
print()

# Step 5: Quick check on a few other symbols to confirm pattern
print("--- Quick check on 5 symbols ---")
for test_sym in ["TCS", "INFY", "HDFCBANK", "WIPRO", "BAJFINANCE"]:
    test_folder = PARQUET_ROOT / test_sym
    test_pf = test_folder / f"{test_sym}_{year}.parquet"
    if not test_pf.exists():
        test_pf = test_folder / f"{year}.parquet"
    if not test_pf.exists():
        print(f"  {test_sym}: NO PARQUET FILE")
        continue
    try:
        tdf = pd.read_parquet(test_pf)
        tdf.columns = [c.lower().strip().replace(" ", "_") for c in tdf.columns]
        if "date" in tdf.columns:
            tdf["date"] = pd.to_datetime(tdf["date"], errors="coerce")
            max_d = tdf["date"].max()
            win = tdf[(tdf["date"] >= sd) & (tdf["date"] <= ed)]
            print(f"  {test_sym}: max={max_d.date() if pd.notna(max_d) else 'NaT'}  window_rows={len(win)}")
        else:
            print(f"  {test_sym}: no date column, has: {list(tdf.columns)[:5]}")
    except Exception as e:
        print(f"  {test_sym}: error: {e}")

print()
print("=" * 60)
print("  KEY FINDING:")
print("  If max date shows 2026-04-29 but we inserted May rows,")
print("  the new rows have 'date' as '12-May-2026' (string) which")
print("  pd.to_datetime() may parse as NaT or wrong date.")
print()
print("  Check 'Null dates' count — if high, that is the problem.")
print("=" * 60)
