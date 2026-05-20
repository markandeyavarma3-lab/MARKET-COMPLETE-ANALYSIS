"""
oos_backtest.py
================
MICC Out-of-Sample (OOS) Backtest Validator
============================================

PROBLEM:
  agent_backtest.py uses ALL signals_history to compute metrics.
  The screens that GENERATED those signals were tuned (even if implicitly)
  on the same data — making it 100% in-sample. Hit rates are overstated.

SOLUTION: Walk-forward expanding window OOS validation.
  - Sort all signal dates ascending
  - For each month M starting from month 6:
      TRAIN = signals with run_date < M (all prior history)
      TEST  = signals with run_date in month M
      → Compute forward returns ONLY for TEST signals
      → Compute hit rates for TEST period only
  - Aggregate: OOS hit rate = average of monthly TEST hit rates

This is proper OOS — each test set was never seen during "training".

OUTPUTS:
  agents/backtest/oos_report.json     -- full walk-forward results
  agents/backtest/oos_summary.json    -- compact: oos_hit_rate per horizon+screen

COLUMN ADDED TO signals_history (if not present):
  fwd_1d, fwd_3d, fwd_5d, fwd_10d   (forward returns, filled from parquet)
  hit_1d, hit_3d, hit_5d, hit_10d   (1/0 binary)

These are the same columns agent_backtest may have written — we reuse them.

RUN:
  python oos_backtest.py              -- full OOS validation
  python oos_backtest.py --quick      -- last 90 days only (fast check)
  python oos_backtest.py --report     -- print existing oos_summary.json
"""

import sys
import json
import math
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

DB           = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
DA           = Path(r"D:\MICC")
OUTPUT_DIR   = DA / "agents" / "backtest"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = [1, 3, 5, 10]
MIN_SIGNALS_PER_MONTH = 5   # skip months with too few signals to be meaningful


R="\033[0m"; B="\033[1m"; G="\033[92m"; Y="\033[93m"; RD="\033[91m"; C="\033[96m"
def now(): return datetime.now().strftime("%H:%M:%S")
def log(msg, lvl="INFO"):
    tag = {"OK":f"{G}OK {R}","FAIL":f"{RD}FAIL{R}","WARN":f"{Y}WARN{R}","INFO":f"{C}INFO{R}"}.get(lvl,"INFO")
    print(f"  [{now()}] [{tag}]  {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# PARQUET LOADER (same as agent_backtest)
# ─────────────────────────────────────────────────────────────────────────────

_parquet_cache: dict[str, pd.DataFrame] = {}

def load_parquet(sym: str) -> pd.DataFrame:
    if sym in _parquet_cache:
        return _parquet_cache[sym]
    folder = PARQUET_ROOT / sym
    if not folder.exists():
        _parquet_cache[sym] = pd.DataFrame()
        return _parquet_cache[sym]
    frames = []
    for f in sorted(folder.glob(f"{sym}_*.parquet")):
        try:
            df = pd.read_parquet(f, columns=["date", "close"])
            frames.append(df)
        except Exception:
            pass
    if not frames:
        _parquet_cache[sym] = pd.DataFrame()
        return _parquet_cache[sym]
    df = pd.concat(frames).drop_duplicates("date").sort_values("date")
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    _parquet_cache[sym] = df
    return df


def get_fwd_returns(sym: str, signal_date: str) -> dict:
    """Get forward returns at 1/3/5/10d after signal_date."""
    df = load_parquet(sym)
    if df.empty:
        return {}
    sig_dt = pd.Timestamp(signal_date)
    future = df[df["date"] > sig_dt].reset_index(drop=True)
    if future.empty:
        return {}
    base = df[df["date"] <= sig_dt]["close"]
    if base.empty:
        return {}
    base_close = base.iloc[-1]
    if base_close <= 0:
        return {}
    result = {}
    for h in HORIZONS:
        if len(future) >= h:
            fwd = (future.iloc[h - 1]["close"] / base_close - 1) * 100
            result[f"fwd_{h}d"] = round(fwd, 4)
            result[f"hit_{h}d"] = 1 if fwd > 0 else 0
    return result


# ─────────────────────────────────────────────────────────────────────────────
# LOAD SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

def load_signals() -> pd.DataFrame:
    conn = sqlite3.connect(str(DB), timeout=15)
    df = pd.read_sql_query(
        "SELECT symbol, run_date, score, screen_tags, regime "
        "FROM signals_history ORDER BY run_date, symbol",
        conn
    )
    conn.close()
    df["run_date"] = df["run_date"].astype(str)
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# FILL FORWARD RETURNS (batch)
# ─────────────────────────────────────────────────────────────────────────────

def fill_forward_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Add fwd_Nd and hit_Nd columns to df."""
    log(f"Computing forward returns for {len(df):,} signals...")
    fwd_cols = {f"fwd_{h}d": [] for h in HORIZONS}
    fwd_cols.update({f"hit_{h}d": [] for h in HORIZONS})

    for i, row in enumerate(df.itertuples()):
        fwd = get_fwd_returns(row.symbol, row.run_date)
        for h in HORIZONS:
            fwd_cols[f"fwd_{h}d"].append(fwd.get(f"fwd_{h}d", np.nan))
            fwd_cols[f"hit_{h}d"].append(fwd.get(f"hit_{h}d", np.nan))
        if i % 500 == 0:
            print(f"  [{now()}]  {i:,}/{len(df):,}  ({100*i/max(len(df),1):.1f}%)", flush=True)

    for col, vals in fwd_cols.items():
        df[col] = vals
    return df


# ─────────────────────────────────────────────────────────────────────────────
# WALK-FORWARD OOS VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def walk_forward_oos(df: pd.DataFrame, quick: bool = False) -> dict:
    """
    Walk-forward expanding window.
    For each calendar month (starting from month 6):
      TRAIN = all prior months
      TEST  = current month
      Report: hit rates computed ONLY on TEST rows.

    Returns dict with:
      monthly_results: list of {month, n_signals, hit_Nd: ...} per TEST month
      summary: overall OOS hit rates (mean of monthly hit rates)
      by_screen: OOS hit rates per screen_tag
    """
    df["month"] = df["run_date"].str[:7]  # YYYY-MM
    months = sorted(df["month"].unique())

    if quick:
        months = months[-3:]  # last 3 months for quick mode
        log(f"QUICK mode: testing {len(months)} months", "WARN")

    log(f"Walk-forward: {len(months)} test months")

    monthly = []
    screen_hits: dict[str, dict] = defaultdict(lambda: defaultdict(list))

    start_idx = 0 if quick else max(0, len(months) - len(months))
    # Minimum: need at least 1 month of training before testing
    for test_idx, test_month in enumerate(months):
        if test_idx == 0 and not quick:
            continue  # Need prior history for train

        test_df = df[df["month"] == test_month].copy()
        test_df = test_df.dropna(subset=[f"hit_{HORIZONS[0]}d"])

        if len(test_df) < MIN_SIGNALS_PER_MONTH:
            continue

        month_result = {
            "month": test_month,
            "n_signals": len(test_df),
        }

        for h in HORIZONS:
            hits = test_df[f"hit_{h}d"].dropna()
            if len(hits) > 0:
                hr = hits.mean() * 100
                avg_ret = test_df[f"fwd_{h}d"].dropna().mean()
                month_result[f"hit_{h}d_pct"] = round(hr, 2)
                month_result[f"avg_ret_{h}d"] = round(avg_ret, 3) if not np.isnan(avg_ret) else None

        monthly.append(month_result)

        # Per-screen breakdown
        if "screen_tags" in test_df.columns:
            for _, row in test_df.iterrows():
                tags = str(row.get("screen_tags", "")).split(",")
                for tag in tags:
                    tag = tag.strip()
                    if not tag:
                        continue
                    for h in HORIZONS:
                        v = row.get(f"hit_{h}d")
                        if not np.isnan(v if v == v else float("nan")):
                            screen_hits[tag][f"hit_{h}d"].append(float(v))

    # Aggregate: mean of monthly OOS hit rates (proper OOS estimate)
    summary: dict = {}
    for h in HORIZONS:
        monthly_hrs = [m[f"hit_{h}d_pct"] for m in monthly if f"hit_{h}d_pct" in m]
        if monthly_hrs:
            summary[f"oos_hit_{h}d_pct"] = round(np.mean(monthly_hrs), 2)
            summary[f"oos_hit_{h}d_std"] = round(np.std(monthly_hrs), 2)
            summary[f"oos_hit_{h}d_min"] = round(min(monthly_hrs), 2)
            summary[f"oos_hit_{h}d_max"] = round(max(monthly_hrs), 2)
            summary[f"oos_n_months_{h}d"] = len(monthly_hrs)

    # In-sample reference (for comparison — shows overfitting gap)
    insample: dict = {}
    all_valid = df.dropna(subset=[f"hit_{HORIZONS[0]}d"])
    for h in HORIZONS:
        hits = all_valid[f"hit_{h}d"].dropna()
        if len(hits) > 0:
            insample[f"insample_hit_{h}d_pct"] = round(hits.mean() * 100, 2)

    # Per-screen OOS
    by_screen: dict = {}
    for screen, horizons in screen_hits.items():
        by_screen[screen] = {}
        for h in HORIZONS:
            hits = horizons.get(f"hit_{h}d", [])
            if hits:
                by_screen[screen][f"oos_hit_{h}d_pct"] = round(np.mean(hits) * 100, 2)
                by_screen[screen]["n_signals"] = len(hits)

    # Overfitting gap
    overfitting: dict = {}
    for h in HORIZONS:
        ins = insample.get(f"insample_hit_{h}d_pct")
        oos = summary.get(f"oos_hit_{h}d_pct")
        if ins is not None and oos is not None:
            overfitting[f"gap_{h}d"] = round(ins - oos, 2)

    return {
        "monthly_results": monthly,
        "summary": summary,
        "insample_reference": insample,
        "overfitting_gap": overfitting,
        "by_screen": by_screen,
        "n_test_months": len(monthly),
        "generated_at": datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# REPORT PRINTER
# ─────────────────────────────────────────────────────────────────────────────

def print_report(report: dict):
    print(f"\n{B}{'='*64}{R}")
    print(f"{B}  MICC OOS Backtest Results{R}")
    print(f"{B}{'='*64}{R}\n")

    summary = report.get("summary", {})
    insample = report.get("insample_reference", {})
    gap = report.get("overfitting_gap", {})

    print(f"  {'Horizon':>8}  {'OOS Hit%':>10}  {'±Std':>6}  {'InSample%':>10}  {'Gap':>6}")
    print(f"  {'-'*50}")
    for h in HORIZONS:
        oos = summary.get(f"oos_hit_{h}d_pct", "N/A")
        std = summary.get(f"oos_hit_{h}d_std", "")
        ins = insample.get(f"insample_hit_{h}d_pct", "N/A")
        g   = gap.get(f"gap_{h}d", "")
        oos_s = f"{oos:.1f}%" if isinstance(oos, float) else str(oos)
        std_s = f"±{std:.1f}" if isinstance(std, float) else ""
        ins_s = f"{ins:.1f}%" if isinstance(ins, float) else str(ins)
        gap_s = f"{g:+.1f}pp" if isinstance(g, float) else ""
        # Color: red gap means overfitting
        col = RD if isinstance(g, float) and g > 3 else G if isinstance(g, float) and g < 1 else Y
        print(f"  {h:>5}d fwd  {oos_s:>10}  {std_s:>6}  {ins_s:>10}  {col}{gap_s}{R}")

    print(f"\n  Test months: {report.get('n_test_months', 0)}")

    by_screen = report.get("by_screen", {})
    if by_screen:
        print(f"\n  OOS by screen (10d hit rate):")
        for screen, stats in sorted(by_screen.items()):
            hr = stats.get("oos_hit_10d_pct", "N/A")
            n  = stats.get("n_signals", 0)
            hr_s = f"{hr:.1f}%" if isinstance(hr, float) else str(hr)
            print(f"    {screen:<20} {hr_s:>8}  (n={n})")

    monthly = report.get("monthly_results", [])
    if monthly:
        print(f"\n  Monthly OOS 10d hit rates (last 12 months):")
        for m in monthly[-12:]:
            hr = m.get("hit_10d_pct", "N/A")
            hr_s = f"{hr:.1f}%" if isinstance(hr, float) else str(hr)
            print(f"    {m['month']}  n={m['n_signals']:>4}  hit_10d={hr_s}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Test last 3 months only")
    ap.add_argument("--report", action="store_true", help="Print existing report, no recompute")
    args = ap.parse_args()

    oos_path = OUTPUT_DIR / "oos_report.json"

    if args.report:
        if oos_path.exists():
            report = json.loads(oos_path.read_text())
            print_report(report)
        else:
            log("No oos_report.json found. Run without --report first.", "WARN")
        return

    log("Loading signals...")
    df = load_signals()
    log(f"Signals loaded: {len(df):,}")

    if df.empty:
        log("No signals in signals_history!", "FAIL")
        sys.exit(1)

    # Fill forward returns
    df = fill_forward_returns(df)
    valid = df.dropna(subset=[f"hit_{HORIZONS[0]}d"])
    log(f"Signals with forward returns: {len(valid):,} / {len(df):,}")

    if len(valid) < 10:
        log("Too few signals with forward returns — need more history.", "WARN")
        sys.exit(1)

    # Walk-forward OOS
    log("Running walk-forward OOS validation...")
    report = walk_forward_oos(valid, quick=args.quick)

    # Save
    oos_path.write_text(json.dumps(report, indent=2))
    summary_path = OUTPUT_DIR / "oos_summary.json"
    summary_path.write_text(json.dumps({
        "summary": report["summary"],
        "overfitting_gap": report["overfitting_gap"],
        "by_screen": report["by_screen"],
        "generated_at": report["generated_at"],
    }, indent=2))

    log(f"Saved: {oos_path}", "OK")
    log(f"Saved: {summary_path}", "OK")

    print_report(report)

    # Interpretation
    print(f"\n{B}  Interpretation:{R}")
    gaps = report.get("overfitting_gap", {})
    for h in HORIZONS:
        g = gaps.get(f"gap_{h}d")
        if g is None:
            continue
        if g < 1:
            print(f"  {G}[{h}d]{R} Gap={g:+.1f}pp — minimal overfitting, good generalization")
        elif g < 5:
            print(f"  {Y}[{h}d]{R} Gap={g:+.1f}pp — moderate overfitting, caution on live use")
        else:
            print(f"  {RD}[{h}d]{R} Gap={g:+.1f}pp — SIGNIFICANT overfitting! Review screen logic")


if __name__ == "__main__":
    main()
