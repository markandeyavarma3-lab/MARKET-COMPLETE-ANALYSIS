"""
build_calendar_patterns.py
==========================
Pre-computes recurring calendar patterns for every stock and index.

ALGORITHM:
  For each symbol with >= 3 years of data:
    1. Load full price history, sorted by date
    2. For each year, label every trading day with its "day-of-year index" (1..N)
    3. For every (start_slot, window_len) combination:
         - Collect the return for that slot across all available years
         - Count how many years went UP vs DOWN
         - If accuracy >= MIN_ACCURACY and n_years >= MIN_YEARS: store the pattern
    4. Deduplicate overlapping patterns (keep highest accuracy per calendar region)
    5. Store in calendar_patterns table

WINDOWS tested: 5,7,10,12,15,18,20,25,30,35,40,45,50,60,75,90 trading days
START SLOTS:    every 3rd trading day from slot 1 to slot 220
                (step=3 reduces combinations without missing real patterns)

For 2675 symbols this takes ~3-5 hours. Progress is saved incrementally
so you can Ctrl+C and resume — already-processed symbols are skipped.

Run: py D:\\MICC\\build_calendar_patterns.py
"""

import sqlite3
import numpy as np
import json
import time
import sys
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────────
DB_PATH       = r"D:\marketDB\db\market.db"
MIN_ACCURACY  = 0.70    # 70% threshold
MIN_YEARS     = 3       # minimum years to form a pattern
MAX_OVERLAP   = 0.6     # suppress patterns that overlap >60% with a better one
START_STEP    = 3       # check every 3rd start slot (speed vs precision)
WINDOWS       = [5,7,10,12,15,18,20,25,30,35,40,45,50,60,75,90]
MAX_START     = 220     # don't start a window after slot 220 (leaves room for window)
BATCH_COMMIT  = 50      # commit every N symbols

# Approximate calendar label from trading day slot (1-based, within year)
# Trading year ~252 days; map slot to month
def slot_to_cal(slot: int, window: int) -> tuple[str, str]:
    """Convert 1-based trading day slot to approximate calendar label."""
    # Each month ~ 21 trading days
    months = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]
    def day_to_label(s: int) -> str:
        if s <= 0: s = 1
        month_idx = min(11, (s - 1) // 21)
        day_in_month = ((s - 1) % 21) + 1
        # Map day_in_month to approximate calendar day
        approx_day = int(day_in_month * (30 / 21))
        approx_day = max(1, min(30, approx_day))
        return f"{months[month_idx]} {approx_day:02d}"
    start_label = day_to_label(slot)
    end_label   = day_to_label(slot + window - 1)
    return start_label, end_label

def confidence_label(n_years: int, accuracy: float) -> str:
    if n_years >= 15 and accuracy >= 0.85: return "VERY HIGH"
    if n_years >= 10 and accuracy >= 0.80: return "HIGH"
    if n_years >= 7  and accuracy >= 0.75: return "GOOD"
    if n_years >= 5  and accuracy >= 0.70: return "MODERATE"
    return "LOW"

# ── DB setup ────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")   # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn

def create_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_patterns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL,
            asset_type      TEXT    NOT NULL DEFAULT 'stock',
            direction       TEXT    NOT NULL,  -- 'up' or 'down'
            window_days     INTEGER NOT NULL,
            start_slot      INTEGER NOT NULL,  -- 1-based trading day of year
            end_slot        INTEGER NOT NULL,
            start_label     TEXT    NOT NULL,  -- e.g. "Jan 15"
            end_label       TEXT    NOT NULL,  -- e.g. "Feb 07"
            n_years         INTEGER NOT NULL,  -- total years with data for this slot
            n_hit           INTEGER NOT NULL,  -- years that went in direction
            accuracy        REAL    NOT NULL,  -- n_hit / n_years
            avg_return      REAL    NOT NULL,  -- avg return when it goes in direction
            avg_return_all  REAL    NOT NULL,  -- avg return across all years
            min_return      REAL    NOT NULL,
            max_return      REAL    NOT NULL,
            std_return      REAL    NOT NULL,
            median_return   REAL    NOT NULL,
            best_year       INTEGER,           -- year of best return
            worst_year      INTEGER,           -- year of worst return
            confidence      TEXT    NOT NULL,
            computed_date   TEXT    NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_symbol ON calendar_patterns(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_dir    ON calendar_patterns(symbol, direction)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_acc    ON calendar_patterns(symbol, accuracy DESC)")

    # Progress tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_patterns_progress (
            symbol      TEXT PRIMARY KEY,
            status      TEXT NOT NULL,  -- 'done' or 'skipped'
            n_patterns  INTEGER,
            ts          TEXT
        )
    """)
    conn.commit()

def get_done_symbols(conn: sqlite3.Connection) -> set:
    rows = conn.execute(
        "SELECT symbol FROM calendar_patterns_progress WHERE status IN ('done','skipped')"
    ).fetchall()
    return {r[0] for r in rows}

def get_all_symbols(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Return (symbol, asset_type) for all symbols that have stock_data."""
    rows = conn.execute("""
        SELECT sd.symbol,
               COALESCE(ws.asset_type, 'stock') as asset_type
        FROM (SELECT DISTINCT symbol FROM stock_data) sd
        LEFT JOIN (
            SELECT symbol, asset_type FROM window_stats GROUP BY symbol
        ) ws ON sd.symbol = ws.symbol
        ORDER BY sd.symbol
    """).fetchall()
    return [(r[0], r[1] or 'stock') for r in rows]

def load_price_series(conn: sqlite3.Connection, symbol: str) -> list[tuple[str, float]]:
    """Load (date, close) sorted ascending. Returns empty list if no data."""
    rows = conn.execute(
        "SELECT date, close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date ASC",
        (symbol,)
    ).fetchall()
    return [(r[0], float(r[1])) for r in rows if r[1] is not None and float(r[1]) > 0]

# ── Core computation ─────────────────────────────────────────────────────────

def compute_patterns(symbol: str, asset_type: str,
                     price_series: list[tuple[str, float]]) -> list[dict]:
    """
    Core pattern finder. Returns list of pattern dicts ready for DB insert.
    Vectorized using numpy for speed.
    """
    if len(price_series) < 60:   # need at least ~3 months
        return []

    # ── Group prices by year ─────────────────────────────────────────────
    # year_data[year] = list of (date_str, close) in that year, sorted
    year_data: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for d, p in price_series:
        try:
            yr = int(d[:4])
            year_data[yr].append((d, p))
        except Exception:
            continue

    years = sorted(year_data.keys())
    if len(years) < MIN_YEARS:
        return []

    # ── Build return matrix ───────────────────────────────────────────────
    # For each year, compute returns for every (start_slot, window) pair
    # return_matrix[year_idx, start_slot] = return from start_slot to start_slot+window
    # We use a dict: slot_year_returns[start_slot][window] = list of (year, return)

    # First, build per-year sorted price arrays as numpy arrays
    # year_prices[year] = np.array of closes, length = n_trading_days in that year
    year_prices: dict[int, np.ndarray] = {}
    year_dates:  dict[int, list[str]]  = {}
    for yr in years:
        prices_yr = [p for _, p in year_data[yr]]
        if len(prices_yr) < 10:
            continue
        year_prices[yr] = np.array(prices_yr, dtype=np.float64)
        year_dates[yr]  = [d for d, _ in year_data[yr]]

    valid_years = sorted(year_prices.keys())
    if len(valid_years) < MIN_YEARS:
        return []

    # ── Compute returns for all (slot, window) combinations ──────────────
    # slot_returns: dict[(start_slot, window)] -> list of (year, ret_pct)
    slot_returns: dict[tuple[int,int], list[tuple[int,float]]] = defaultdict(list)

    for yr in valid_years:
        prices = year_prices[yr]
        n      = len(prices)

        for start_slot in range(0, min(MAX_START, n - min(WINDOWS)), START_STEP):
            for window in WINDOWS:
                end_slot = start_slot + window
                if end_slot >= n:
                    continue
                p_start = prices[start_slot]
                p_end   = prices[end_slot]
                if p_start <= 0:
                    continue
                ret = (p_end - p_start) / p_start * 100.0
                slot_returns[(start_slot, window)].append((yr, ret))

    # ── Find significant patterns ─────────────────────────────────────────
    patterns: list[dict] = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for (start_slot, window), year_rets in slot_returns.items():
        if len(year_rets) < MIN_YEARS:
            continue

        yrs_  = [y for y, _ in year_rets]
        rets  = np.array([r for _, r in year_rets], dtype=np.float64)
        n_yr  = len(rets)

        # UP pattern
        n_up  = int(np.sum(rets > 0))
        acc_up = n_up / n_yr
        if acc_up >= MIN_ACCURACY:
            up_rets = rets[rets > 0]
            start_label, end_label = slot_to_cal(start_slot + 1, window)
            # Find best/worst year
            best_yr  = yrs_[int(np.argmax(rets))]
            worst_yr = yrs_[int(np.argmin(rets))]
            patterns.append({
                "symbol":        symbol,
                "asset_type":    asset_type,
                "direction":     "up",
                "window_days":   window,
                "start_slot":    start_slot + 1,   # 1-based
                "end_slot":      start_slot + window + 1,
                "start_label":   start_label,
                "end_label":     end_label,
                "n_years":       n_yr,
                "n_hit":         n_up,
                "accuracy":      round(acc_up, 4),
                "avg_return":    round(float(up_rets.mean()) if len(up_rets) else 0.0, 4),
                "avg_return_all":round(float(rets.mean()), 4),
                "min_return":    round(float(rets.min()), 4),
                "max_return":    round(float(rets.max()), 4),
                "std_return":    round(float(rets.std()), 4),
                "median_return": round(float(np.median(rets)), 4),
                "best_year":     best_yr,
                "worst_year":    worst_yr,
                "confidence":    confidence_label(n_yr, acc_up),
                "computed_date": today_str,
            })

        # DOWN pattern
        n_dn  = int(np.sum(rets < 0))
        acc_dn = n_dn / n_yr
        if acc_dn >= MIN_ACCURACY:
            dn_rets = rets[rets < 0]
            start_label, end_label = slot_to_cal(start_slot + 1, window)
            best_yr  = yrs_[int(np.argmax(rets))]
            worst_yr = yrs_[int(np.argmin(rets))]
            patterns.append({
                "symbol":        symbol,
                "asset_type":    asset_type,
                "direction":     "down",
                "window_days":   window,
                "start_slot":    start_slot + 1,
                "end_slot":      start_slot + window + 1,
                "start_label":   start_label,
                "end_label":     end_label,
                "n_years":       n_yr,
                "n_hit":         n_dn,
                "accuracy":      round(acc_dn, 4),
                "avg_return":    round(float(dn_rets.mean()) if len(dn_rets) else 0.0, 4),
                "avg_return_all":round(float(rets.mean()), 4),
                "min_return":    round(float(rets.min()), 4),
                "max_return":    round(float(rets.max()), 4),
                "std_return":    round(float(rets.std()), 4),
                "median_return": round(float(np.median(rets)), 4),
                "best_year":     best_yr,
                "worst_year":    worst_yr,
                "confidence":    confidence_label(n_yr, acc_dn),
                "computed_date": today_str,
            })

    if not patterns:
        return []

    # ── Deduplicate overlapping patterns ──────────────────────────────────
    # For each direction separately, suppress patterns whose slot range
    # overlaps >60% with a higher-accuracy pattern of the same window length
    deduped = deduplicate_patterns(patterns)
    return deduped


def deduplicate_patterns(patterns: list[dict]) -> list[dict]:
    """
    Remove overlapping patterns. Strategy:
    1. Sort by accuracy DESC (ties broken by n_years DESC)
    2. For each pattern, check if it overlaps >MAX_OVERLAP with any
       already-kept pattern of same direction and similar window
    3. If overlap too high, discard the lower-accuracy one
    """
    if not patterns:
        return []

    # Sort: highest accuracy first, then most years
    patterns.sort(key=lambda p: (-p["accuracy"], -p["n_years"], -p["window_days"]))

    kept: list[dict] = []

    for p in patterns:
        p_start = p["start_slot"]
        p_end   = p["end_slot"]
        p_dir   = p["direction"]
        p_range = set(range(p_start, p_end))
        p_len   = len(p_range)

        overlaps = False
        for k in kept:
            if k["direction"] != p_dir:
                continue
            k_range = set(range(k["start_slot"], k["end_slot"]))
            if not p_range or not k_range:
                continue
            intersection = len(p_range & k_range)
            # Overlap fraction relative to the SMALLER window
            overlap_frac = intersection / min(p_len, len(k_range))
            if overlap_frac > MAX_OVERLAP:
                overlaps = True
                break

        if not overlaps:
            kept.append(p)

    # Cap at 200 patterns per symbol (50 up + 50 down most meaningful)
    # Sort final output by direction then accuracy
    kept.sort(key=lambda p: (p["direction"], -p["accuracy"], -p["n_years"]))
    return kept[:200]


# ── Insert into DB ────────────────────────────────────────────────────────────

INSERT_SQL = """
    INSERT INTO calendar_patterns (
        symbol, asset_type, direction, window_days,
        start_slot, end_slot, start_label, end_label,
        n_years, n_hit, accuracy, avg_return, avg_return_all,
        min_return, max_return, std_return, median_return,
        best_year, worst_year, confidence, computed_date
    ) VALUES (
        :symbol, :asset_type, :direction, :window_days,
        :start_slot, :end_slot, :start_label, :end_label,
        :n_years, :n_hit, :accuracy, :avg_return, :avg_return_all,
        :min_return, :max_return, :std_return, :median_return,
        :best_year, :worst_year, :confidence, :computed_date
    )
"""

def save_patterns(conn: sqlite3.Connection, patterns: list[dict]):
    if patterns:
        conn.executemany(INSERT_SQL, patterns)

def mark_done(conn: sqlite3.Connection, symbol: str, n_patterns: int, status: str = "done"):
    conn.execute(
        "INSERT OR REPLACE INTO calendar_patterns_progress (symbol, status, n_patterns, ts) VALUES (?,?,?,?)",
        (symbol, status, n_patterns, datetime.now().isoformat())
    )

# ── Progress display ──────────────────────────────────────────────────────────

def fmt_time(seconds: float) -> str:
    if seconds < 60:   return f"{int(seconds)}s"
    if seconds < 3600: return f"{int(seconds//60)}m {int(seconds%60)}s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"

def print_progress(done: int, total: int, start_time: float,
                   symbol: str, n_pats: int, total_patterns: int):
    elapsed  = time.time() - start_time
    rate     = done / elapsed if elapsed > 0 else 0
    remaining= (total - done) / rate if rate > 0 else 0
    pct      = done / total * 100
    bar_len  = 30
    filled   = int(bar_len * done / total)
    bar      = "█" * filled + "░" * (bar_len - filled)
    sys.stdout.write(
        f"\r[{bar}] {pct:5.1f}%  {done}/{total}  "
        f"ETA: {fmt_time(remaining)}  "
        f"Last: {symbol[:12]:<12} +{n_pats:3d} pats  "
        f"Total: {total_patterns:,}"
    )
    sys.stdout.flush()

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("CALENDAR PATTERNS BUILDER")
    print("=" * 70)
    print(f"DB:            {DB_PATH}")
    print(f"Min accuracy:  {MIN_ACCURACY*100:.0f}%")
    print(f"Min years:     {MIN_YEARS}")
    print(f"Windows:       {WINDOWS}")
    print(f"Start step:    every {START_STEP} slots")
    print(f"Max overlap:   {MAX_OVERLAP*100:.0f}%")
    print()

    conn = get_conn()
    create_table(conn)

    # Load all symbols
    all_symbols = get_all_symbols(conn)
    done_set    = get_done_symbols(conn)

    todo = [(s, t) for s, t in all_symbols if s not in done_set]
    print(f"Total symbols:  {len(all_symbols)}")
    print(f"Already done:   {len(done_set)}")
    print(f"To process:     {len(todo)}")
    print()

    if not todo:
        print("All symbols already processed. Run with --reset to recompute.")
        # Show summary
        row = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol) FROM calendar_patterns"
        ).fetchone()
        print(f"DB has {row[0]:,} patterns across {row[1]:,} symbols")
        conn.close()
        return

    # Ask for confirmation (skip if --yes flag passed)
    print(f"This will process {len(todo)} symbols.")
    print("Estimated time: depends on your CPU, typically 1-4 hours for all stocks.")
    print("Progress is saved — you can Ctrl+C and resume anytime.")
    print()
    if "--yes" in sys.argv or "-y" in sys.argv:
        print("Auto-confirmed (--yes flag).")
        ans = 'y'
    else:
        try:
            ans = input("Start? [y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            conn.close()
            return
    if ans != 'y':
        print("Aborted. Run with --yes to skip this prompt.")
        conn.close()
        return

    print()
    start_time    = time.time()
    total_patterns= 0
    processed     = 0
    batch_buf: list[dict] = []
    batch_prog: list[tuple] = []

    for idx, (symbol, asset_type) in enumerate(todo):
        try:
            price_series = load_price_series(conn, symbol)

            if len(price_series) < 60:
                batch_prog.append((symbol, 0, "skipped"))
                processed += 1
                continue

            patterns = compute_patterns(symbol, asset_type, price_series)

            batch_buf.extend(patterns)
            batch_prog.append((symbol, len(patterns), "done"))
            total_patterns += len(patterns)
            processed      += 1

            print_progress(processed, len(todo), start_time,
                           symbol, len(patterns), total_patterns)

            # Commit every BATCH_COMMIT symbols
            if len(batch_prog) >= BATCH_COMMIT:
                save_patterns(conn, batch_buf)
                for sym_, npat_, status_ in batch_prog:
                    mark_done(conn, sym_, npat_, status_)
                conn.commit()
                batch_buf  = []
                batch_prog = []

        except KeyboardInterrupt:
            print("\n\nInterrupted! Saving progress...")
            save_patterns(conn, batch_buf)
            for sym_, npat_, status_ in batch_prog:
                mark_done(conn, sym_, npat_, status_)
            conn.commit()
            print(f"Saved. {processed}/{len(todo)} symbols done. Resume by running again.")
            conn.close()
            return

        except Exception as e:
            # Log error but continue with next symbol
            batch_prog.append((symbol, 0, "skipped"))
            processed += 1
            # Don't print error mid-progress bar, just continue
            continue

    # Final commit
    if batch_buf or batch_prog:
        save_patterns(conn, batch_buf)
        for sym_, npat_, status_ in batch_prog:
            mark_done(conn, sym_, npat_, status_)
        conn.commit()

    elapsed = time.time() - start_time
    print(f"\n\nDONE in {fmt_time(elapsed)}")
    print(f"Total patterns stored: {total_patterns:,}")

    # Final summary
    row = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT symbol) FROM calendar_patterns"
    ).fetchone()
    print(f"DB total: {row[0]:,} patterns across {row[1]:,} symbols")

    # Top 10 most-patterned symbols
    top = conn.execute("""
        SELECT symbol, COUNT(*) as n,
               SUM(CASE WHEN direction='up' THEN 1 ELSE 0 END) as up_n,
               SUM(CASE WHEN direction='down' THEN 1 ELSE 0 END) as dn_n,
               MAX(accuracy) as best_acc
        FROM calendar_patterns
        GROUP BY symbol ORDER BY n DESC LIMIT 10
    """).fetchall()
    print("\nTop 10 symbols by pattern count:")
    print(f"  {'Symbol':<15} {'Total':>6} {'UP':>5} {'DOWN':>5} {'Best Acc':>9}")
    print("  " + "-"*45)
    for r in top:
        print(f"  {r[0]:<15} {r[1]:>6} {r[2]:>5} {r[3]:>5} {r[4]*100:>8.1f}%")

    conn.close()
    print("\nRun setup_phase11.py to build the dashboard for this data.")


if __name__ == "__main__":
    # Handle --reset flag
    if "--reset" in sys.argv:
        print("Resetting all progress...")
        conn = get_conn()
        conn.execute("DROP TABLE IF EXISTS calendar_patterns")
        conn.execute("DROP TABLE IF EXISTS calendar_patterns_progress")
        conn.commit()
        conn.close()
        print("Reset done. Run again without --reset to recompute.")
        sys.exit(0)

    # Handle --test flag — process just 5 symbols to verify
    if "--test" in sys.argv:
        print("TEST MODE: processing HDFCBANK, RELIANCE, TCS, INFY, NIFTY 50")
        conn = get_conn()
        create_table(conn)

        test_syms = [
            ("HDFCBANK", "stock"), ("RELIANCE", "stock"),
            ("TCS", "stock"), ("INFY", "stock"),
        ]
        # Try to find an index (market_snapshot uses index_name not symbol)
        idx_row = conn.execute(
            "SELECT DISTINCT index_name FROM market_snapshot LIMIT 1"
        ).fetchone()
        if idx_row:
            test_syms.append((idx_row[0], "index"))

        for sym, atype in test_syms:
            print(f"\nProcessing {sym}...")
            t0 = time.time()
            if atype == "stock":
                ps = conn.execute(
                    "SELECT date, close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date",
                    (sym,)
                ).fetchall()
                ps = [(r[0], float(r[1])) for r in ps if r[1] and float(r[1]) > 0]
            else:
                # market_snapshot column might be close or Close — check first
                try:
                    ps = conn.execute(
                        "SELECT date, close FROM market_snapshot WHERE index_name=? AND close IS NOT NULL ORDER BY date",
                        (sym,)
                    ).fetchall()
                    ps = [(r[0], float(r[1])) for r in ps if r[1] and float(r[1]) > 0]
                except Exception as ex:
                    print(f"  [WARN] Could not load index {sym}: {ex}")
                    ps = []

            patterns = compute_patterns(sym, atype, ps)
            elapsed_ = time.time() - t0
            print(f"  {len(ps)} price points | {len(patterns)} patterns | {elapsed_:.1f}s")

            if patterns:
                print(f"  Sample UP patterns (top 5):")
                up_ = [p for p in patterns if p["direction"]=="up"][:5]
                for p_ in up_:
                    print(f"    {p_['window_days']:3d}d  {p_['start_label']}-{p_['end_label']}  "
                          f"{p_['n_hit']}/{p_['n_years']}={p_['accuracy']*100:.0f}%  "
                          f"avgRet={p_['avg_return_all']:+.1f}%  conf={p_['confidence']}")
                print(f"  Sample DOWN patterns (top 5):")
                dn_ = [p for p in patterns if p["direction"]=="down"][:5]
                for p_ in dn_:
                    print(f"    {p_['window_days']:3d}d  {p_['start_label']}-{p_['end_label']}  "
                          f"{p_['n_hit']}/{p_['n_years']}={p_['accuracy']*100:.0f}%  "
                          f"avgRet={p_['avg_return_all']:+.1f}%  conf={p_['confidence']}")

            save_patterns(conn, patterns)
            mark_done(conn, sym, len(patterns), "done")
            conn.commit()

        conn.close()
        print("\nTest done. Check results above.")
        sys.exit(0)

    main()
