"""
fix_stocks_builder.py  --  Run from D:\MICC
Finds and fixes the silent failure in build_seasonality_v3_stocks.py
Then patches the builder to work correctly.

DIAGNOSIS: stock_data has 5273 rows for AXISBANK but builder returns 0 patterns.
The load_stock_prices function has a silent try/except hiding the real error.
"""
import sqlite3, math, bisect, json, time
from pathlib import Path
from datetime import datetime, date

DB = Path(r"D:\marketDB\db\market.db")

print("=== STEP 1: Test load directly ===")
conn = sqlite3.connect(DB, timeout=15)

# Exactly what the builder does
try:
    rows = conn.execute(
        "SELECT date, close FROM stock_data "
        "WHERE symbol=? AND close IS NOT NULL AND close > 0 "
        "ORDER BY date",
        ("AXISBANK",)
    ).fetchall()
    print(f"Rows fetched: {len(rows)}")
    print(f"First 3: {rows[:3]}")
    print(f"Last 3:  {rows[-3:]}")
except Exception as e:
    print(f"QUERY ERROR: {e}")

conn.close()

print("\n=== STEP 2: Test pandas conversion ===")
try:
    import pandas as pd
    conn = sqlite3.connect(DB, timeout=15)
    rows = conn.execute(
        "SELECT date, close FROM stock_data "
        "WHERE symbol=? AND close IS NOT NULL AND close > 0 "
        "ORDER BY date",
        ("AXISBANK",)
    ).fetchall()
    conn.close()

    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [float(r[1]) for r in rows]
    series = pd.Series(vals, index=idx).sort_index()
    series = series[series > 0]
    print(f"Series length: {len(series)}")
    print(f"Date range: {series.index[0].date()} to {series.index[-1].date()}")
    print(f"Price range: {series.min():.2f} to {series.max():.2f}")
    print(f"Passes 300-row check: {len(series) >= 300}")
except Exception as e:
    print(f"PANDAS ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n=== STEP 3: Test mine_anchor_window ===")
try:
    import pandas as pd
    import numpy as np
    conn = sqlite3.connect(DB, timeout=15)
    rows = conn.execute(
        "SELECT date, close FROM stock_data "
        "WHERE symbol=? AND close IS NOT NULL AND close > 0 ORDER BY date",
        ("AXISBANK",)
    ).fetchall()
    conn.close()

    idx    = pd.to_datetime([r[0] for r in rows])
    vals   = [float(r[1]) for r in rows]
    prices = pd.Series(vals, index=idx).sort_index()
    prices = prices[prices > 0]

    price_map = prices.to_dict()
    dates_arr = sorted(prices.index)

    # Test one anchor
    anchor_mm_dd = "01-15"
    window = 20
    mm = int(anchor_mm_dd[:2])
    dd = int(anchor_mm_dd[3:])

    year_returns = {}
    years = sorted(set(d.year for d in dates_arr))
    print(f"Years available: {years[:5]}...{years[-5:]}")

    for yr in years[:5]:  # test first 5 years
        try:
            target = date(yr, mm, dd)
        except ValueError:
            continue

        target_ts = pd.Timestamp(target)
        bi = bisect.bisect_left(dates_arr, target_ts)
        print(f"  Year {yr}: target={target}, bisect={bi}, len(dates)={len(dates_arr)}")

        entry_date = None
        for k in range(bi, min(bi + 5, len(dates_arr))):
            if dates_arr[k].year == yr:
                entry_date = dates_arr[k]
                break

        if entry_date is None:
            print(f"    No entry date found! bi={bi}")
            # Show what's around bi
            for k in range(max(0,bi-2), min(bi+5, len(dates_arr))):
                print(f"    dates_arr[{k}] = {dates_arr[k]}  year={dates_arr[k].year}")
            continue

        ep = price_map.get(entry_date)
        if not ep:
            print(f"    entry_date={entry_date} not in price_map!")
            continue

        entry_bi = bisect.bisect_left(dates_arr, entry_date)
        exit_bi  = entry_bi + window
        if exit_bi >= len(dates_arr):
            print(f"    exit_bi={exit_bi} >= len={len(dates_arr)}, skip")
            continue

        exit_date = dates_arr[exit_bi]
        xp = price_map.get(exit_date)
        if not xp:
            print(f"    exit_date={exit_date} not in price_map!")
            continue

        ret = (xp / ep - 1) * 100
        year_returns[yr] = round(ret, 4)
        print(f"    entry={entry_date.date()} @{ep:.2f}  exit={exit_date.date()} @{xp:.2f}  ret={ret:.2f}%")

    print(f"\n  year_returns found: {len(year_returns)}")
    if year_returns:
        rets = list(year_returns.values())
        mean_ret = np.mean(rets)
        accuracy = np.mean([r > 0 for r in rets]) * 100
        score    = accuracy * abs(mean_ret) * math.log(max(len(rets), 2)) / 100
        print(f"  mean={mean_ret:.2f}%  accuracy={accuracy:.1f}%  score={score:.4f}")
        print(f"  MIN_OBS check (need 5): {len(year_returns) >= 5}")

except Exception as e:
    print(f"MINE ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n=== STEP 4: Check get_all_symbols threshold ===")
try:
    conn = sqlite3.connect(DB, timeout=15)
    n_axisbank = conn.execute(
        "SELECT COUNT(*) FROM stock_data WHERE symbol='AXISBANK' AND close IS NOT NULL AND close > 0"
    ).fetchone()[0]
    print(f"AXISBANK rows passing filter: {n_axisbank}")
    print(f"MIN threshold (1250): {'PASSES' if n_axisbank >= 1250 else 'FAILS -- THIS IS THE BUG'}")

    # Check how many symbols have >=1250 rows
    n_syms = conn.execute(
        "SELECT COUNT(*) FROM (SELECT symbol, COUNT(*) as n FROM stock_data "
        "WHERE close IS NOT NULL AND close > 0 GROUP BY symbol HAVING n >= 1250)"
    ).fetchone()[0]
    print(f"Symbols with >=1250 rows: {n_syms}")

    # Check AXISBANK specifically
    row = conn.execute(
        "SELECT symbol, COUNT(*) as n FROM stock_data "
        "WHERE symbol='AXISBANK' AND close IS NOT NULL AND close > 0 GROUP BY symbol"
    ).fetchone()
    print(f"AXISBANK: {row}")
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
