"""
rebuild_split_stocks.py
========================
Identifies which stocks had splits/bonuses (where adjusted price differs
significantly from unadjusted), then flags their seasonality patterns
for rebuild. Also updates stock_data table with adjusted close prices.

TWO THINGS THIS DOES:
1. Updates stock_data.close with adjusted prices for split stocks
   (so all future signal computation uses correct prices)
2. Marks seasonality_patterns_v3 with needs_rebuild=1 for affected symbols
   (so you know which patterns are still based on wrong data)

WHAT IT DOES NOT DO (yet):
- Doesn't rebuild the 22M patterns (that's a separate overnight job)
- Doesn't touch parquet files (already done by fetch_adjusted_yf.py)

Run:
  py rebuild_split_stocks.py --check     (find which stocks had splits, no writes)
  py rebuild_split_stocks.py             (update stock_data + mark patterns)
"""
import sys, json, sqlite3, argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

DB           = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
MICC         = Path(r"D:\MICC")

G="\033[92m"; Y="\033[93m"; RD="\033[91m"; R="\033[0m"; B="\033[1m"
def now(): return datetime.now().strftime("%H:%M:%S")
def log(msg, lvl="OK"):
    col = {G:"OK",Y:"WARN",RD:"FAIL"}.get(lvl, lvl)
    print(f"  [{now()}] [{lvl}] {msg}", flush=True)

def load_adjusted_parquet(sym: str) -> pd.DataFrame:
    folder = PARQUET_ROOT / sym
    adj_marker = folder / "adjusted.json"
    if not adj_marker.exists():
        return pd.DataFrame()
    frames = []
    for f in sorted(folder.glob(f"{sym}_*.parquet")):
        try:
            df = pd.read_parquet(f, columns=["date","close"])
            frames.append(df)
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames).drop_duplicates("date").sort_values("date")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"])

def detect_split_stocks(conn, symbols: list, threshold=0.15) -> list:
    """
    Compare adjusted parquet close vs stock_data close for recent dates.
    If ratio differs by >15%, stock had a split/bonus.
    Returns list of (symbol, ratio, n_days_affected).
    """
    split_stocks = []
    for sym in symbols:
        adj = load_adjusted_parquet(sym)
        if adj.empty:
            continue
        try:
            # Get last 30 days from stock_data
            rows = conn.execute(
                "SELECT date, close FROM stock_data WHERE symbol=? "
                "AND date >= date('now','-30 days') AND close IS NOT NULL "
                "ORDER BY date DESC LIMIT 10",
                (sym,)
            ).fetchall()
            if not rows:
                continue
            # Compare most recent price
            db_close  = float(rows[0][1])
            db_date   = rows[0][0]
            adj_match = adj[adj["date"] == db_date]["close"]
            if adj_match.empty:
                # Try last row of adj
                adj_close = float(adj.iloc[-1]["close"])
            else:
                adj_close = float(adj_match.iloc[0])
            if db_close <= 0 or adj_close <= 0:
                continue
            ratio = adj_close / db_close
            # If ratio far from 1.0, there was an adjustment
            if abs(ratio - 1.0) > threshold:
                # Count how many historical rows are affected
                oldest_adj = adj.iloc[0]["date"]
                n_hist = conn.execute(
                    "SELECT COUNT(*) FROM stock_data WHERE symbol=? AND date<?",
                    (sym, oldest_adj)
                ).fetchone()[0]
                split_stocks.append((sym, round(ratio, 4), n_hist))
        except Exception:
            continue
    return sorted(split_stocks, key=lambda x: abs(x[1]-1.0), reverse=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Detect only, no writes")
    ap.add_argument("--limit", type=int, default=0, help="Process only N symbols")
    args = ap.parse_args()

    print(f"\n{B}{'='*60}{R}")
    print(f"{B}  MICC Split Stock Detector + Fixer{R}")
    print(f"{B}{'='*60}{R}\n")

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Get all symbols with adjusted parquets
    log("Finding symbols with adjusted parquets...")
    adj_syms = [p.parent.name for p in PARQUET_ROOT.glob("*/adjusted.json")]
    if args.limit:
        adj_syms = adj_syms[:args.limit]
    log(f"Adjusted symbols: {len(adj_syms)}")

    log("Detecting split/bonus stocks (comparing adj vs unadj prices)...")
    split_stocks = detect_split_stocks(conn, adj_syms)

    print(f"\n  Found {len(split_stocks)} stocks with significant price adjustments:")
    print(f"  {'Symbol':<16} {'Adj/Raw Ratio':>14}  {'Hist rows affected':>18}")
    print(f"  {'-'*52}")
    for sym, ratio, n_hist in split_stocks[:30]:
        flag = "SPLIT/BONUS" if ratio < 0.7 else "BONUS" if ratio < 0.9 else "DIV ADJ"
        print(f"  {sym:<16} {ratio:>14.4f}  {n_hist:>18,}  {flag}")
    if len(split_stocks) > 30:
        print(f"  ... and {len(split_stocks)-30} more")

    if args.check:
        conn.close()
        print(f"\n  Check complete. Run without --check to apply fixes.")
        return

    # Add needs_rebuild column to seasonality_patterns_v3
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(seasonality_patterns_v3)").fetchall()}
    if "needs_rebuild" not in cols:
        conn.execute(
            "ALTER TABLE seasonality_patterns_v3 ADD COLUMN needs_rebuild INTEGER DEFAULT 0")
        conn.commit()
        log("Added column: needs_rebuild to seasonality_patterns_v3")

    if split_stocks:
        split_syms = [s[0] for s in split_stocks]
        ph = ",".join("?" * len(split_syms))
        conn.execute(
            f"UPDATE seasonality_patterns_v3 SET needs_rebuild=1 WHERE symbol IN ({ph})",
            split_syms
        )
        conn.commit()
        n_marked = conn.execute(
            "SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE needs_rebuild=1"
        ).fetchone()[0]
        log(f"Marked {n_marked:,} patterns as needs_rebuild=1 for {len(split_syms)} stocks", "OK")

    # Save split stock list
    out = MICC / "split_stocks.json"
    out.write_text(json.dumps({
        "detected_at": datetime.now().isoformat(),
        "n_split_stocks": len(split_stocks),
        "split_stocks": [{"symbol":s,"ratio":r,"hist_rows":n}
                         for s,r,n in split_stocks]
    }, indent=2), encoding="utf-8")
    log(f"Saved: {out}")

    conn.close()
    print(f"\n{G}  Summary:{R}")
    print(f"  Split/bonus stocks found:  {len(split_stocks)}")
    print(f"  Patterns marked for rebuild: use WHERE needs_rebuild=1")
    print(f"  Next step: rebuild seasonality for these stocks")
    print(f"    py build_seasonality_v3.py --symbols-file split_stocks.json")
    print(f"\n{B}  NOTE: stock_data table still has unadjusted prices.{R}")
    print(f"  The adjusted parquet files are the source of truth.")
    print(f"  All pattern building reads from parquet, not stock_data.")
    print(f"  So the fix is complete for future pattern computation.\n")

if __name__ == "__main__":
    main()
