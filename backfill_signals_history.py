# -*- coding: utf-8 -*-
"""
backfill_signals_history.py
============================
Seeds signals_history with the last N trading days of composite picks
so streak_N tags start appearing immediately in live runs.

Strategy:
  - For each trading date in the window, build a 5-day window ending on that date
  - Run composite scoring only (no LLM, no 52w, no sector rotation = fast)
  - Insert via log_beta_signals (UNIQUE constraint skips already-logged dates)
  - Skips dates already present in signals_history

Usage:
  py backfill_signals_history.py           → last 30 trading days
  py backfill_signals_history.py 45        → last 45 trading days
  py backfill_signals_history.py --check   → show what's already in signals_history

Estimated time: ~3-5 min for 30 days (parquet loads dominate)
"""

import sys
import sqlite3
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path("D:/MICC")))

from micc_data import (
    get_all_trading_dates_since,
    get_trading_dates,
    load_all_symbols_window,
    get_fundamentals,
    get_earnings_acceleration,
    log_beta_signals,
    get_regime_thresholds,
)
from agent_beta import (
    screen_momentum,
    screen_delivery_leaders,
    screen_volume_breakouts,
    screen_consistency,
    compute_composite,
    MIN_PRICE,
    TOP_N,
)

DB_PATH = Path("D:/marketDB/db/market.db")
WINDOW  = 5   # days per composite run


# ── helpers ──────────────────────────────────────────────────────────────────

def already_logged_dates() -> set:
    """Dates already in signals_history."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT DISTINCT run_date FROM signals_history"
        ).fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception as e:
        print(f"[Backfill] Could not read signals_history: {e}")
        return set()


def composite_for_window(dates: list) -> pd.DataFrame:
    """
    Fast composite — no LLM, no 52w, no sector rotation.
    Returns enriched composite DataFrame or empty DataFrame on failure.
    """
    df = load_all_symbols_window(dates)
    if df.empty:
        return pd.DataFrame()

    n_days = len(dates)

    # Use DEFAULT thresholds for backfill (regime unknown for historical dates)
    thresh = get_regime_thresholds("")

    momentum    = screen_momentum(df,    min_pct_chg=thresh["min_pct_chg"])
    delivery    = screen_delivery_leaders(df, min_deliv_pct=thresh["min_deliv_pct"])
    breakouts   = screen_volume_breakouts(df, min_vol_surge=thresh["min_vol_surge"])
    consistency = screen_consistency(df, n_days, min_adv_offset=thresh["min_adv_offset"])

    composite = compute_composite(
        momentum, delivery, breakouts, consistency,
        weights=thresh["composite_weights"]
    )
    if composite.empty:
        return pd.DataFrame()

    # Enrich with price data
    composite = composite.merge(
        df[["symbol", "pct_chg", "end_close", "avg_deliv_pct",
            "avg_turnover_lacs", "vol_surge_lastday"]],
        on="symbol", how="left"
    )

    # EPS boost (inlined sqlite3 — Python 3.14 safe)
    top_syms = composite["symbol"].tolist()
    try:
        conn = sqlite3.connect(str(DB_PATH))
        placeholders = ",".join("?" * len(top_syms))
        rows = conn.execute(
            f"SELECT symbol, data_json FROM quarterly_income WHERE symbol IN ({placeholders})",
            top_syms
        ).fetchall()
        conn.close()

        import json, math

        eps_map = {}
        for sym, djson in rows:
            if not djson:
                continue
            try:
                clean = djson.replace(": NaN", ": null").replace(":NaN", ":null")
                d = json.loads(clean)
                eps_val = d.get("eps") or d.get("EPS") or d.get("basic_eps")
                if eps_val is None:
                    for k, v in d.items():
                        if "eps" in k.lower() and v is not None:
                            try:
                                eps_val = float(v)
                            except Exception:
                                pass
                            break
                if eps_val is not None:
                    try:
                        eps_float = float(eps_val)
                        eps_map[sym] = {
                            "eps": eps_float,
                            "profitable": eps_float > 0,
                        }
                    except Exception:
                        pass
            except Exception:
                pass

        profitable   = [s for s in top_syms if eps_map.get(s, {}).get("profitable")]
        loss_making  = [s for s in top_syms if s in eps_map and not eps_map[s].get("profitable")]

        if profitable:
            composite.loc[composite["symbol"].isin(profitable),  "score"] += 2
        if loss_making:
            composite.loc[composite["symbol"].isin(loss_making), "score"] -= 1

        def _eps_flag(sym):
            d = eps_map.get(sym)
            if d is None:
                return ""
            if d.get("profitable"):
                return "PROFITABLE"
            if d.get("eps") is not None and not d.get("profitable"):
                return "LOSS_MAKING"
            return ""

        composite["earnings_flag"] = composite["symbol"].map(_eps_flag)
        composite = composite.sort_values("score", ascending=False).reset_index(drop=True)

    except Exception as e:
        print(f"[Backfill] EPS boost skipped: {e}")
        composite["earnings_flag"] = ""

    return composite


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    # --check mode
    if "--check" in sys.argv:
        logged = already_logged_dates()
        if logged:
            print(f"signals_history has {len(logged)} dates:")
            for d in sorted(logged):
                print(f"  {d}")
        else:
            print("signals_history is empty")
        return

    # How many days to backfill
    n_days = 30
    for arg in sys.argv[1:]:
        if arg.isdigit():
            n_days = int(arg)
            break

    print(f"\n{'='*55}")
    print(f"  MICC signals_history backfill — last {n_days} trading days")
    print(f"{'='*55}\n")

    # All trading dates available
    all_dates = get_trading_dates(n_days + WINDOW + 5)  # extra buffer for window
    if len(all_dates) < WINDOW + 1:
        print(f"[Backfill] Not enough dates in DB ({len(all_dates)}). Aborting.")
        return

    # Dates to backfill = last n_days only (need WINDOW preceding days for context)
    target_dates = all_dates[-(n_days):]   # end-dates we want to log
    already      = already_logged_dates()

    to_run = [d for d in target_dates if d not in already]
    skip   = [d for d in target_dates if d in already]

    print(f"Target dates  : {len(target_dates)}")
    print(f"Already logged: {len(skip)}")
    print(f"To backfill   : {len(to_run)}")

    if not to_run:
        print("\nAll dates already logged. Nothing to do.")
        print("Run with a larger N if you want more history:")
        print("  py backfill_signals_history.py 45")
        return

    print(f"\nStarting backfill...\n")

    total_inserted = 0
    errors = 0

    for i, end_date in enumerate(to_run, 1):
        # Build 5-day window ending on end_date
        end_idx = all_dates.index(end_date)
        if end_idx < WINDOW - 1:
            print(f"  [{i:02d}/{len(to_run)}] {end_date} — not enough history, skip")
            continue

        window = all_dates[end_idx - WINDOW + 1 : end_idx + 1]
        assert window[-1] == end_date

        print(f"  [{i:02d}/{len(to_run)}] {end_date}  window: {window[0]}→{window[-1]}", end="  ")

        try:
            composite = composite_for_window(window)
            if composite.empty:
                print("EMPTY")
                continue

            n = log_beta_signals(composite, end_date, regime="BACKFILL")
            total_inserted += n
            print(f"→ {len(composite)} picks, {n} new rows")

        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1
            continue

    print(f"\n{'='*55}")
    print(f"  Backfill complete.")
    print(f"  Total new rows inserted : {total_inserted}")
    print(f"  Errors                  : {errors}")
    print(f"{'='*55}")

    if total_inserted > 0:
        # Quick streak preview
        print("\nTop streak stocks (appeared most days):")
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute("""
                SELECT symbol, COUNT(DISTINCT run_date) as days
                FROM signals_history
                GROUP BY symbol
                ORDER BY days DESC
                LIMIT 15
            """).fetchall()
            conn.close()
            for sym, days in rows:
                bar = "█" * days
                print(f"  {sym:<14} {days:>2}d  {bar}")
        except Exception as e:
            print(f"  (streak preview failed: {e})")

        print(f"\nNext live run will show streak_N tags for stocks appearing ≥3 days.")
        print("Run: py agent_beta.py 5")


if __name__ == "__main__":
    main()
