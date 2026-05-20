"""
fetch_adjusted_yf.py
=====================
Alternative to jugaad-data — uses yfinance which adds .NS suffix for NSE.
yfinance auto-adjusts for splits and dividends (adjusted close).
More reliable than jugaad-data for Indian stocks.

jugaad-data is currently failing because NSE blocked your IP after 
the 60-worker hammer. yfinance uses Yahoo Finance servers — different 
source, not blocked.

Run:
  py fetch_adjusted_yf.py --workers 8           (all 2188 symbols)
  py fetch_adjusted_yf.py --symbol RELIANCE      (single test)
  py fetch_adjusted_yf.py --verify               (check progress)
  py fetch_adjusted_yf.py --top 100              (top 100 first)
"""
import sys, time, json, sqlite3, argparse, warnings
warnings.filterwarnings("ignore")
from datetime import datetime, date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import pandas as pd
import yfinance as yf

DB           = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
MICC         = Path(r"D:\MICC")
LOG_FILE     = MICC / "adjusted_yf_log.json"

print_lock = Lock()
res_lock   = Lock()
counters   = {"done": 0, "failed": 0, "skipped": 0, "failed_syms": []}

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

def is_done(sym):
    return (PARQUET_ROOT / sym / "adjusted.json").exists()

def fetch_yf(sym: str) -> tuple[str, str]:
    """Fetch split-adjusted OHLCV from Yahoo Finance (.NS suffix for NSE)."""
    if is_done(sym):
        return sym, "SKIP"
    try:
        ticker = yf.Ticker(f"{sym}.NS")
        # auto_adjust=True gives split+dividend adjusted prices
        df = ticker.history(
            start="2000-01-01",
            end=date.today().isoformat(),
            auto_adjust=True,
            actions=False,
            timeout=15
        )
        if df is None or df.empty or len(df) < 50:
            return sym, "FAIL:empty"

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # yfinance returns: date, open, high, low, close, volume
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        for col in ["open","high","low","close","volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df[["date","open","high","low","close","volume"]].dropna(
            subset=["close"]).sort_values("date").reset_index(drop=True)

        if len(df) < 50:
            return sym, "FAIL:too_short"

        # Save yearly parquets
        folder = PARQUET_ROOT / sym
        folder.mkdir(parents=True, exist_ok=True)
        df["_yr"] = pd.to_datetime(df["date"]).dt.year
        for yr, grp in df.groupby("_yr"):
            grp.drop(columns=["_yr"]).to_parquet(
                str(folder / f"{sym}_{yr}.parquet"), index=False)

        # Marker
        (folder / "adjusted.json").write_text(json.dumps({
            "adjusted": True, "source": "yfinance",
            "rows": len(df), "date": datetime.now().isoformat()
        }), encoding="utf-8")

        return sym, f"OK:{len(df)}"

    except Exception as e:
        return sym, f"FAIL:{str(e)[:50]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--symbol",  default=None)
    ap.add_argument("--top",     type=int, default=0)
    ap.add_argument("--verify",  action="store_true")
    args = ap.parse_args()

    if args.symbol:
        s, status = fetch_yf(args.symbol)
        print(f"  {s}: {status}")
        return

    symbols = get_symbols(top_n=args.top or None, single=args.symbol)

    if args.verify:
        done = sum(1 for s in symbols if is_done(s))
        jug  = sum(1 for s in symbols
                   if (PARQUET_ROOT/s/"adjusted.json").exists()
                   and "jugaad" not in json.loads(
                       (PARQUET_ROOT/s/"adjusted.json").read_text()).get("source",""))
        print(f"  Adjusted (any source): {done}/{len(symbols)}")
        remaining = [s for s in symbols if not is_done(s)]
        print(f"  Remaining: {len(remaining)}")
        if remaining[:10]: print(f"  Next 10: {remaining[:10]}")
        return

    todo = [s for s in symbols if not is_done(s)]
    already = len(symbols) - len(todo)

    print(f"\n{'='*60}")
    print(f"  MICC Adjusted Prices — yfinance parallel fetcher")
    print(f"{'='*60}")
    print(f"  Total:       {len(symbols)}")
    print(f"  Done:        {already}")
    print(f"  To fetch:    {len(todo)}")
    print(f"  Workers:     {args.workers}")
    print(f"  Source:      Yahoo Finance (auto-adjusted for splits)")
    # yfinance is faster — no rate limit issues at 8 workers
    est = len(todo) * 0.8 / args.workers / 60
    print(f"  Est. time:   ~{est:.0f}-{est*2:.0f} min")
    print(f"{'='*60}\n")

    if not todo:
        print("  All done!"); return

    t0 = time.time()
    n  = [0]

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_yf, sym): sym for sym in todo}
        for fut in as_completed(futs):
            sym, status = fut.result()
            n[0] += 1
            ela  = time.time() - t0
            rate = n[0] / max(ela, 0.1)
            eta  = (len(todo) - n[0]) / max(rate, 0.01)

            with res_lock:
                if status.startswith("OK"):
                    counters["done"] += 1
                elif status == "SKIP":
                    counters["skipped"] += 1
                else:
                    counters["failed"] += 1
                    counters["failed_syms"].append(sym)

            icon = "✓" if status.startswith("OK") else "·" if status=="SKIP" else "✗"
            rows = status.split(":")[1] if ":" in status and status.startswith("OK") else status.split(":",1)[1][:30] if ":" in status else ""
            plog(f"  {icon} [{n[0]:>5}/{len(todo)}] {sym:<16} {rows:<12} ETA {eta/60:.0f}min [{now()}]")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  Done in {elapsed/60:.1f} min")
    print(f"  Adjusted:  {counters['done']}")
    print(f"  Failed:    {counters['failed']}")
    print(f"  Skipped:   {counters['skipped']}")
    if counters["failed_syms"][:10]:
        print(f"  Failed:    {counters['failed_syms'][:10]}")
    LOG_FILE.write_text(json.dumps({
        "run_at": datetime.now().isoformat(), "source": "yfinance",
        "workers": args.workers, "elapsed_min": round(elapsed/60,1),
        **{k:v for k,v in counters.items() if k != "failed_syms"},
        "failed_symbols": counters["failed_syms"],
    }, indent=2))
    print(f"  Log: {LOG_FILE}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
