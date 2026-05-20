"""
debug_stocks_patterns.py  --  Run from D:\MICC
Diagnoses why AXISBANK / RELIANCE return 0 patterns.
Checks: parquet loading, date format, return values, filter thresholds.

Run: py D:\MICC\debug_stocks_patterns.py
"""
import sqlite3, math, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
from datetime import datetime, date

import numpy as np
import pandas as pd

PARQUET = Path(r"D:\marketDB\stocks\all")
DB      = Path(r"D:\marketDB\db\market.db")

TEST_SYMS = ["AXISBANK", "RELIANCE", "HDFCBANK", "INFY"]

print("=" * 60)
print("  STOCKS PATTERN DEBUGGER")
print("=" * 60)

for SYM in TEST_SYMS:
    print(f"\n--- {SYM} ---")

    # 1. Check parquet files exist
    sym_dir = PARQUET / SYM
    if not sym_dir.exists():
        print(f"  [FAIL] Directory not found: {sym_dir}")
        continue

    files = sorted(sym_dir.glob(f"{SYM}_*.parquet"))
    print(f"  Parquet files: {len(files)}")
    if not files:
        print(f"  [FAIL] No parquet files found")
        continue

    for f in files[:3]:
        print(f"    {f.name}")

    # 2. Load parquet
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f, columns=["date", "close"])
            dfs.append(df)
        except Exception as e:
            print(f"  [WARN] Failed to read {f.name}: {e}")

    if not dfs:
        print(f"  [FAIL] Could not read any parquet files")
        continue

    df = pd.concat(dfs, ignore_index=True)
    print(f"  Total rows before cleanup: {len(df):,}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Date dtype: {df['date'].dtype}")
    print(f"  Sample dates (raw): {df['date'].head(3).tolist()}")

    # 3. Parse dates
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["close"]).sort_values("date")
    df = df.drop_duplicates("date").set_index("date")
    prices = df["close"].astype(float)

    print(f"  Rows after cleanup: {len(prices):,}")
    print(f"  Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"  Price range: {prices.min():.2f} to {prices.max():.2f}")
    print(f"  Sample prices:")
    for d, v in prices.tail(5).items():
        print(f"    {d.date()} = {v:.2f}")

    # 4. Test forward return calculation for one anchor
    import bisect
    dates_arr  = sorted(prices.index)
    price_map  = prices.to_dict()

    anchor_mm_dd = "01-15"
    window       = 20
    mm, dd       = int(anchor_mm_dd[:2]), int(anchor_mm_dd[3:])

    year_returns = {}
    years        = sorted(set(d.year for d in dates_arr))

    for yr in years:
        try: target = date(yr, mm, dd)
        except ValueError: continue

        target_ts = pd.Timestamp(target)
        bi = bisect.bisect_left(dates_arr, target_ts)
        entry_date = None
        for k in range(bi, min(bi + 5, len(dates_arr))):
            if dates_arr[k].year == yr:
                entry_date = dates_arr[k]; break

        if entry_date is None: continue

        ep = price_map.get(entry_date)
        if not ep or ep <= 0: continue

        exit_bi = bisect.bisect_left(dates_arr, entry_date) + window
        if exit_bi >= len(dates_arr): continue

        xp = price_map.get(dates_arr[exit_bi])
        if not xp or xp <= 0: continue

        ret = (xp / ep - 1) * 100
        year_returns[yr] = round(ret, 4)

    print(f"\n  Test anchor={anchor_mm_dd} window={window}d:")
    print(f"  Occurrences found: {len(year_returns)}")
    if year_returns:
        rets = list(year_returns.values())
        print(f"  Returns: {rets[:10]}")
        print(f"  Mean: {np.mean(rets):.2f}%  Max: {max(rets):.2f}%  Min: {min(rets):.2f}%")
        print(f"  |mean_ret| > 50 filter would BLOCK: {abs(np.mean(rets)) > 50}")
        accuracy = np.mean([r > 0 for r in rets]) * 100
        print(f"  Accuracy (% UP): {accuracy:.1f}%")
        score = accuracy * abs(np.mean(rets)) * math.log(max(len(rets), 2)) / 100
        print(f"  Score: {score:.4f}")
        print(f"  MIN_SCORE filter (0.3) would BLOCK: {score < 0.3}")
        print(f"  MIN_ACCURACY filter (55%) would BLOCK: {accuracy < 55}")
    else:
        print(f"  [FAIL] No occurrences found for this anchor!")
        print(f"         This means date lookup is failing.")
        print(f"         Sample dates_arr[0]: {dates_arr[0]}")
        print(f"         Target was: {date(2020, mm, dd)}")
        # Try manual lookup
        print(f"  Manual check: dates in Jan 2020:")
        jan_2020 = [d for d in dates_arr if d.year == 2020 and d.month == 1]
        for d in jan_2020[:5]:
            print(f"    {d}  type={type(d)}")

    break  # Only debug first working symbol in detail

print("\n" + "=" * 60)
print("  DIAGNOSIS SUMMARY")
print("=" * 60)

# Check if the 50% cap is the issue
print("\nChecking if |mean_ret| > 50 filter is too aggressive for stocks...")
conn = sqlite3.connect(DB, timeout=10)

# Check stock_data for AXISBANK returns
rows = conn.execute(
    "SELECT date, close FROM stock_data WHERE symbol='AXISBANK' "
    "AND close IS NOT NULL ORDER BY date DESC LIMIT 10"
).fetchall()
print(f"\nstock_data AXISBANK (latest 10 rows):")
for r in rows:
    print(f"  {r[0]}  {r[1]:.2f}")

conn.close()

print("""
=== WHAT TO CHECK ===
1. If 'Occurrences found: 0' -> date lookup broken (bisect issue)
2. If returns show large values (>50%) -> 50% cap is blocking valid stock data
3. If accuracy < 55% -> lower MIN_ACCURACY to 52%
4. If score < 0.3 -> lower MIN_SCORE to 0.1 for first pass

Run this script and share output to determine the exact fix needed.
""")
