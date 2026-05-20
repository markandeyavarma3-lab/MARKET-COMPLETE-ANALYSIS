"""
fetch_adjusted_prices.py
=========================
Downloads split/bonus-adjusted OHLCV for all NSE symbols via jugaad-data.
Replaces parquet files with adjusted close prices.
Adds is_adjusted=True marker file per symbol folder.

WHY: Pre-split prices in parquet are inflated (RELIANCE 1:1 bonus 2017 = 2x prices).
     All seasonality patterns on those stocks are wrong without adjustment.

INSTALL FIRST:
  py -m pip install jugaad-data --break-system-packages

Run: py fetch_adjusted_prices.py
     py fetch_adjusted_prices.py --symbol RELIANCE  (single symbol test)
     py fetch_adjusted_prices.py --top 100          (top 100 by volume first)
     py fetch_adjusted_prices.py --verify           (check adjustment status)
"""
import sys, time, sqlite3, argparse, json
from datetime import datetime, date
from pathlib import Path
import pandas as pd
import numpy as np

DB           = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
MICC         = Path(r"D:\MICC")
LOG_FILE     = MICC / "adjusted_prices_log.json"

def now(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"  [{now()}] {msg}", flush=True)

def get_symbols(db, top_n=None, single=None):
    conn = sqlite3.connect(str(db), timeout=15)
    if single:
        rows = [(single,)]
    elif top_n:
        rows = conn.execute(
            "SELECT symbol FROM stock_data GROUP BY symbol "
            "ORDER BY SUM(volume) DESC LIMIT ?", (top_n,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM stock_data ORDER BY symbol"
        ).fetchall()
    conn.close()
    return [r[0] for r in rows]

def fetch_adjusted(symbol: str) -> pd.DataFrame | None:
    """Fetch adjusted OHLCV from jugaad-data."""
    try:
        from jugaad_data.nse import stock_df
        from datetime import date as dt
        df = stock_df(symbol=symbol,
                      from_date=dt(2000, 1, 1),
                      to_date=dt.today(),
                      series="EQ")
        if df is None or df.empty:
            return None
        # jugaad_data columns: DATE, OPEN, HIGH, LOW, CLOSE, VOLUME, etc.
        df = df.rename(columns=str.upper)
        needed = ["DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]
        for col in needed:
            if col not in df.columns:
                # try lowercase
                lc = {c.upper(): c for c in df.columns}
                if col in lc:
                    df.rename(columns={lc[col]: col}, inplace=True)
        df = df[["DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]].copy()
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["close"]).sort_values("date")
        df["is_adjusted"] = True
        return df
    except Exception as e:
        return None

def save_parquet(symbol: str, df: pd.DataFrame):
    """Save adjusted data as yearly parquet files."""
    folder = PARQUET_ROOT / symbol
    folder.mkdir(parents=True, exist_ok=True)
    df["year"] = pd.to_datetime(df["date"]).dt.year
    for year, grp in df.groupby("year"):
        path = folder / f"{symbol}_{year}.parquet"
        grp.drop(columns=["year"]).to_parquet(str(path), index=False)
    # marker file
    (folder / "adjusted.json").write_text(
        json.dumps({"adjusted": True, "date": datetime.now().isoformat()}))

def verify(symbols):
    adj = sum(1 for s in symbols if (PARQUET_ROOT/s/"adjusted.json").exists())
    log(f"Adjusted: {adj}/{len(symbols)} symbols ({100*adj/max(len(symbols),1):.1f}%)")
    not_adj = [s for s in symbols[:20] if not (PARQUET_ROOT/s/"adjusted.json").exists()]
    if not_adj:
        log(f"First 20 not adjusted: {not_adj}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    # Check jugaad-data installed
    try:
        import jugaad_data
    except ImportError:
        print("  jugaad-data not installed!")
        print("  Run: py -m pip install jugaad-data --break-system-packages")
        sys.exit(1)

    symbols = get_symbols(DB, top_n=args.top or None, single=args.symbol)
    log(f"Symbols to process: {len(symbols)}")

    if args.verify:
        verify(symbols); return

    results = {"done": [], "failed": [], "skipped": []}
    t0 = time.time()

    for i, sym in enumerate(symbols):
        # Skip if already adjusted
        if (PARQUET_ROOT / sym / "adjusted.json").exists():
            results["skipped"].append(sym)
            continue

        df = fetch_adjusted(sym)
        if df is not None and len(df) > 100:
            save_parquet(sym, df)
            results["done"].append(sym)
            status = f"OK ({len(df)} rows)"
        else:
            results["failed"].append(sym)
            status = "FAILED"

        elapsed = time.time() - t0
        rate = (i+1) / max(elapsed, 1)
        eta = (len(symbols)-i-1) / max(rate, 0.01)
        print(f"  [{i+1:>5}/{len(symbols)}] {sym:<16} {status:<20} "
              f"ETA {eta/60:.0f}min", flush=True)
        time.sleep(0.5)  # polite rate limit

    LOG_FILE.write_text(json.dumps({
        "run_at": datetime.now().isoformat(),
        "done": len(results["done"]),
        "failed": len(results["failed"]),
        "skipped": len(results["skipped"]),
        "failed_symbols": results["failed"][:50],
    }, indent=2))

    log(f"Done: {len(results['done'])}  Failed: {len(results['failed'])}  "
        f"Skipped (already adj): {len(results['skipped'])}")
    log(f"Log: {LOG_FILE}")

if __name__ == "__main__":
    main()
