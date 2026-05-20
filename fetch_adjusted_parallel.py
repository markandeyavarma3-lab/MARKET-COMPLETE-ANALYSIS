"""
fetch_adjusted_parallel.py
===========================
Fetches split-adjusted prices for all NSE symbols using 6 parallel threads.
6x faster than single-threaded. Expected: 2188 symbols in ~30-45 min.

WHY IT WAS SLOW:
  - jugaad-data makes an HTTP request to NSE for each symbol
  - NSE responds in 0.5-3 seconds per symbol
  - Single thread = wait for each one before starting next
  - 2188 symbols × 1.5s avg = 55 min sequential
  - 6 threads = each handles ~365 symbols = ~9 min total

WHY NOT MORE THAN 6-8 THREADS:
  - NSE rate limits aggressive scrapers (you get 429/blocked)
  - 6 is the sweet spot — fast enough, won't get blocked

Run:
  py fetch_adjusted_parallel.py --workers 6          (default, recommended)
  py fetch_adjusted_parallel.py --workers 3           (conservative)
  py fetch_adjusted_parallel.py --symbol RELIANCE     (single test)
  py fetch_adjusted_parallel.py --verify              (check completion)
  py fetch_adjusted_parallel.py --resume              (skip already-done symbols)
"""
import sys, time, sqlite3, argparse, json
from datetime import datetime, date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pandas as pd

DB           = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
MICC         = Path(r"D:\MICC")
LOG_FILE     = MICC / "adjusted_prices_log.json"

print_lock = Lock()
results    = {"done": [], "failed": [], "skipped": []}
res_lock   = Lock()

def now(): return datetime.now().strftime("%H:%M:%S")

def plog(msg):
    with print_lock:
        print(msg, flush=True)

def get_symbols(top_n=None, single=None):
    conn = sqlite3.connect(str(DB), timeout=15)
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

def is_done(symbol):
    return (PARQUET_ROOT / symbol / "adjusted.json").exists()

def fetch_and_save(symbol: str) -> tuple[str, str]:
    """Fetch adjusted OHLCV from jugaad-data, save parquet. Returns (symbol, status)."""
    if is_done(symbol):
        return symbol, "SKIP"
    try:
        from jugaad_data.nse import stock_df
        import warnings
        warnings.filterwarnings("ignore")  # suppress timezone warning

        df = stock_df(
            symbol=symbol,
            from_date=date(2000, 1, 1),
            to_date=date.today(),
            series="EQ"
        )
        if df is None or df.empty or len(df) < 50:
            return symbol, "FAIL:empty"

        # Normalize columns
        df.columns = [c.upper() for c in df.columns]
        col_map = {}
        for want, alts in [
            ("DATE",   ["DATE","DT","TIMESTAMP"]),
            ("OPEN",   ["OPEN","OPEN PRICE"]),
            ("HIGH",   ["HIGH","HIGH PRICE"]),
            ("LOW",    ["LOW","LOW PRICE"]),
            ("CLOSE",  ["CLOSE","CLOSE PRICE","LTP","LAST"]),
            ("VOLUME", ["VOLUME","TOTAL TRADED QUANTITY","TTQ","NO OF TRADES"]),
        ]:
            for alt in alts:
                if alt in df.columns:
                    col_map[alt] = want
                    break
        df = df.rename(columns=col_map)

        needed = [c for c in ["DATE","OPEN","HIGH","LOW","CLOSE","VOLUME"] if c in df.columns]
        df = df[needed].copy()
        df.columns = [c.lower() for c in df.columns]

        if "date" not in df.columns or "close" not in df.columns:
            return symbol, "FAIL:missing_cols"

        df["date"]  = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)

        if len(df) < 50:
            return symbol, "FAIL:too_short"

        # Save as yearly parquets
        folder = PARQUET_ROOT / symbol
        folder.mkdir(parents=True, exist_ok=True)
        df["_year"] = pd.to_datetime(df["date"]).dt.year
        for year, grp in df.groupby("_year"):
            grp.drop(columns=["_year"]).to_parquet(
                str(folder / f"{symbol}_{year}.parquet"), index=False)

        # Marker file
        (folder / "adjusted.json").write_text(
            json.dumps({"adjusted": True, "rows": len(df),
                        "date": datetime.now().isoformat()}),
            encoding="utf-8"
        )
        return symbol, f"OK:{len(df)}"

    except Exception as e:
        err = str(e)[:60].replace("\n"," ")
        return symbol, f"FAIL:{err}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--symbol",  default=None)
    ap.add_argument("--top",     type=int, default=0)
    ap.add_argument("--verify",  action="store_true")
    ap.add_argument("--resume",  action="store_true",
                    help="Skip already-done symbols (default behavior)")
    args = ap.parse_args()

    if args.symbol:
        sym, status = fetch_and_save(args.symbol)
        print(f"  {sym}: {status}")
        return

    symbols = get_symbols(top_n=args.top or None)

    if args.verify:
        done = sum(1 for s in symbols if is_done(s))
        not_done = [s for s in symbols if not is_done(s)]
        print(f"  Adjusted: {done}/{len(symbols)} ({100*done/max(len(symbols),1):.1f}%)")
        print(f"  Remaining: {len(not_done)}")
        if not_done[:20]:
            print(f"  Next 20: {not_done[:20]}")
        return

    # Filter out already done
    todo = [s for s in symbols if not is_done(s)]
    already = len(symbols) - len(todo)
    total = len(symbols)

    print(f"\n{'='*60}")
    print(f"  MICC Adjusted Prices — Parallel Fetcher")
    print(f"{'='*60}")
    print(f"  Total symbols:   {total}")
    print(f"  Already done:    {already}")
    print(f"  To fetch:        {len(todo)}")
    print(f"  Workers:         {args.workers}")
    print(f"  Est. time:       ~{len(todo)*1.5/args.workers/60:.0f}-{len(todo)*3/args.workers/60:.0f} min")
    print(f"{'='*60}\n")

    if not todo:
        print("  All symbols already adjusted!")
        return

    t0     = time.time()
    done_n = [0]  # mutable counter for closure

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_and_save, sym): sym for sym in todo}
        for fut in as_completed(futures):
            sym, status = fut.result()
            done_n[0] += 1
            n    = done_n[0]
            ela  = time.time() - t0
            rate = n / max(ela, 1)
            eta  = (len(todo) - n) / max(rate, 0.01)

            with res_lock:
                if status.startswith("OK"):
                    results["done"].append(sym)
                elif status == "SKIP":
                    results["skipped"].append(sym)
                else:
                    results["failed"].append(sym)

            icon = "✓" if status.startswith("OK") else "·" if status=="SKIP" else "✗"
            rows = status.split(":")[1] if ":" in status and status.startswith("OK") else ""
            plog(f"  {icon} [{n:>5}/{len(todo)}] {sym:<16} {rows:<8} "
                 f"ETA {eta/60:.0f}min  [{now()}]")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  DONE in {elapsed/60:.1f} min")
    print(f"  Adjusted:  {len(results['done'])}")
    print(f"  Failed:    {len(results['failed'])}")
    print(f"  Skipped:   {len(results['skipped'])}")
    if results["failed"]:
        print(f"  Failed symbols: {results['failed'][:20]}")

    # Save log
    LOG_FILE.write_text(json.dumps({
        "run_at":          datetime.now().isoformat(),
        "workers":         args.workers,
        "elapsed_min":     round(elapsed/60, 1),
        "done":            len(results["done"]),
        "failed":          len(results["failed"]),
        "skipped":         len(results["skipped"]),
        "failed_symbols":  results["failed"],
    }, indent=2), encoding="utf-8")
    print(f"  Log: {LOG_FILE}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
