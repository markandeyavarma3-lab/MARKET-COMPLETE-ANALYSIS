# -*- coding: utf-8 -*-
"""
MICC Phase 7 -- Signal Backtester
==================================
Takes every entry in signals_history, looks up actual forward returns
from parquet files, and measures how well Beta screens performed.

Metrics computed per signal entry:
  fwd_1d, fwd_3d, fwd_5d, fwd_10d  -- forward % returns after signal date
  hit_1d, hit_3d, hit_5d, hit_10d  -- 1 = positive return (hit), 0 = miss

Aggregated stats (overall + per screen_tag + per regime):
  hit_rate_%     -- % of signals that were positive at N days
  avg_return_%   -- mean forward return
  median_return_%
  best / worst
  avg_score_of_hits vs misses
  streak_edge    -- do higher streaks lead to better returns?

Output:
  agents/backtest/last_report.json  -- full results
  agents/backtest/summary.json      -- compact summary for dashboard

Dashboard: /backtest page
Telegram:  /backtest command

Run:  py D:/MICC/agent_backtest.py
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from micc_data import call_llm, now_ist, send_telegram_chunks

DB           = r"D:\marketDB\db\market.db"
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
DA           = Path(r"D:\MICC")
OUTPUT_DIR   = DA / "agents" / "backtest"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS     = [1, 3, 5, 10]   # forward-return windows in trading days
MIN_PRICE    = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────────────────────────────────────

def load_signals() -> pd.DataFrame:
    """Load all rows from signals_history."""
    conn = sqlite3.connect(DB, timeout=15)
    df = pd.read_sql_query(
        "SELECT symbol, run_date, score, screen_tags, pct_chg, "
        "       avg_deliv_pct, regime "
        "FROM signals_history "
        "ORDER BY run_date, symbol",
        conn
    )
    conn.close()
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    df["run_date"] = df["run_date"].astype(str)
    return df


def load_parquet_for_symbol(sym: str) -> pd.DataFrame:
    """
    Load all available parquet data for a symbol.
    Returns DataFrame with columns: date (datetime), close
    Sorted ascending by date.
    """
    folder = PARQUET_ROOT / sym
    if not folder.exists():
        return pd.DataFrame()

    cur_year = datetime.now().year
    years = list(range(cur_year - 2, cur_year + 1))
    frames = []
    for yr in years:
        for fname in [f"{sym}_{yr}.parquet", f"{yr}.parquet"]:
            pf = folder / fname
            if pf.exists():
                try:
                    frames.append(pd.read_parquet(pf))
                except Exception:
                    pass
                break

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    if "date" not in df.columns or "close" not in df.columns:
        return pd.DataFrame()

    df["date"]  = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    df = df[df["close"] >= MIN_PRICE]
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return df[["date", "close"]]


# ─────────────────────────────────────────────────────────────────────────────
# FORWARD RETURN COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_forward_returns(signals: pd.DataFrame) -> pd.DataFrame:
    """
    For every signal row, look up the close on run_date and the close
    N trading days later in the parquet data.

    Adds columns: fwd_1d, fwd_3d, fwd_5d, fwd_10d (% returns)
                  hit_1d, hit_3d, hit_5d, hit_10d  (1/0)
    """
    # cache parquet per symbol to avoid re-loading
    cache: dict[str, pd.DataFrame] = {}

    fwd_cols = {h: [] for h in HORIZONS}
    hit_cols = {h: [] for h in HORIZONS}

    total   = len(signals)
    matched = 0

    for idx, row in signals.iterrows():
        sym      = row["symbol"]
        sig_date = pd.Timestamp(row["run_date"])

        if sym not in cache:
            cache[sym] = load_parquet_for_symbol(sym)

        df = cache[sym]
        if df.empty:
            for h in HORIZONS:
                fwd_cols[h].append(np.nan)
                hit_cols[h].append(np.nan)
            continue

        # find the signal date index (or next available date)
        future_mask = df["date"] >= sig_date
        if not future_mask.any():
            for h in HORIZONS:
                fwd_cols[h].append(np.nan)
                hit_cols[h].append(np.nan)
            continue

        entry_idx = df[future_mask].index[0]
        entry_close = float(df.loc[entry_idx, "close"])
        matched += 1

        for h in HORIZONS:
            exit_idx = entry_idx + h
            if exit_idx < len(df):
                exit_close = float(df.loc[exit_idx, "close"])
                ret = (exit_close / entry_close - 1) * 100
                fwd_cols[h].append(round(ret, 3))
                hit_cols[h].append(1 if ret > 0 else 0)
            else:
                fwd_cols[h].append(np.nan)
                hit_cols[h].append(np.nan)

    for h in HORIZONS:
        signals[f"fwd_{h}d"]  = fwd_cols[h]
        signals[f"hit_{h}d"]  = hit_cols[h]

    print(f"  Forward returns: matched {matched}/{total} signals to parquet")
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# STATS COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def stats_block(df: pd.DataFrame, label: str) -> dict:
    """Compute summary stats for a subset of signals."""
    n = len(df)
    if n == 0:
        return {"label": label, "n": 0}

    block = {"label": label, "n": n}
    for h in HORIZONS:
        col_ret = f"fwd_{h}d"
        col_hit = f"hit_{h}d"
        valid   = df[col_ret].dropna()
        hits    = df[col_hit].dropna()
        if len(valid) == 0:
            continue
        block[f"h{h}_hit_rate"]   = round(float(hits.mean() * 100), 1)
        block[f"h{h}_avg_ret"]    = round(float(valid.mean()), 2)
        block[f"h{h}_median_ret"] = round(float(valid.median()), 2)
        block[f"h{h}_best"]       = round(float(valid.max()), 2)
        block[f"h{h}_worst"]      = round(float(valid.min()), 2)
        block[f"h{h}_n_valid"]    = len(valid)
    return block


def compute_all_stats(df: pd.DataFrame) -> dict:
    """Compute overall + per-screen + per-regime stats."""

    # ── overall ───────────────────────────────────────────────────────────────
    overall = stats_block(df, "OVERALL")

    # ── per screen_tag ────────────────────────────────────────────────────────
    # screen_tags can be comma-separated like "Momentum,Delivery,Breakout"
    # split and count per individual screen
    screen_stats = []
    for screen in ["Momentum", "Delivery", "Breakout", "Consistency", "52W"]:
        sub = df[df["screen_tags"].str.contains(screen, na=False, case=False)]
        if len(sub) > 5:
            screen_stats.append(stats_block(sub, screen))

    # ── per regime ────────────────────────────────────────────────────────────
    regime_stats = []
    for reg in df["regime"].dropna().unique():
        sub = df[df["regime"] == reg]
        if len(sub) > 5:
            regime_stats.append(stats_block(sub, str(reg)))

    # ── score buckets ─────────────────────────────────────────────────────────
    score_stats = []
    for lo, hi, label in [(0, 2, "score_1-2"), (2, 4, "score_3-4"), (4, 99, "score_5+")]:
        sub = df[(df["score"] > lo) & (df["score"] <= hi)]
        if len(sub) > 5:
            score_stats.append(stats_block(sub, label))

    # ── streak edge ───────────────────────────────────────────────────────────
    # compute streak per symbol (days appearing in signals_history consecutively)
    # use a simple approximation: how many times does the symbol appear in df
    freq = df.groupby("symbol").size().rename("freq")
    df2  = df.merge(freq.reset_index(), on="symbol", how="left")
    streak_stats = []
    for lo, hi, label in [(1, 2, "appeared_1-2x"), (2, 5, "appeared_3-5x"), (5, 999, "appeared_6x+")]:
        sub = df2[(df2["freq"] > lo) & (df2["freq"] <= hi)]
        if len(sub) > 5:
            streak_stats.append(stats_block(sub, label))

    # ── top performers ────────────────────────────────────────────────────────
    df_valid = df.dropna(subset=["fwd_5d"])
    top10 = (df_valid.groupby("symbol")["fwd_5d"]
                     .mean()
                     .sort_values(ascending=False)
                     .head(10)
                     .reset_index()
                     .rename(columns={"fwd_5d": "avg_fwd_5d"}))
    top10["avg_fwd_5d"] = top10["avg_fwd_5d"].round(2)

    bot10 = (df_valid.groupby("symbol")["fwd_5d"]
                     .mean()
                     .sort_values(ascending=True)
                     .head(10)
                     .reset_index()
                     .rename(columns={"fwd_5d": "avg_fwd_5d"}))
    bot10["avg_fwd_5d"] = bot10["avg_fwd_5d"].round(2)

    # ── monthly hit rate trend ────────────────────────────────────────────────
    df["month"] = df["run_date"].str[:7]   # YYYY-MM
    monthly = []
    for mo in sorted(df["month"].unique()):
        sub = df[df["month"] == mo]
        valid = sub["hit_5d"].dropna()
        if len(valid) >= 3:
            monthly.append({
                "month":    mo,
                "hit_rate": round(float(valid.mean() * 100), 1),
                "n":        len(valid),
                "avg_ret":  round(float(sub["fwd_5d"].dropna().mean()), 2),
            })

    return {
        "overall":       overall,
        "by_screen":     screen_stats,
        "by_regime":     regime_stats,
        "by_score":      score_stats,
        "by_frequency":  streak_stats,
        "top_performers":top10.to_dict("records"),
        "worst_performers": bot10.to_dict("records"),
        "monthly_trend": monthly,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM SYNTHESIS
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(stats: dict, n_signals: int, date_range: str) -> str:
    ov = stats["overall"]
    lines = [
        f"MICC Beta Screener Backtest -- {n_signals} signals, {date_range}",
        "",
        "OVERALL PERFORMANCE:",
    ]
    for h in HORIZONS:
        hr  = ov.get(f"h{h}_hit_rate", "N/A")
        avg = ov.get(f"h{h}_avg_ret",  "N/A")
        lines.append(f"  {h}d: hit_rate={hr}% | avg_return={avg}%")

    lines.append("\nBY SCREEN:")
    for s in stats["by_screen"]:
        hr5  = s.get("h5_hit_rate", "N/A")
        avg5 = s.get("h5_avg_ret",  "N/A")
        lines.append(f"  {s['label']}: hit_rate_5d={hr5}% | avg_5d={avg5}% (n={s['n']})")

    lines.append("\nBY REGIME:")
    for s in stats["by_regime"]:
        hr5  = s.get("h5_hit_rate", "N/A")
        avg5 = s.get("h5_avg_ret",  "N/A")
        lines.append(f"  {s['label']}: hit_rate_5d={hr5}% | avg_5d={avg5}% (n={s['n']})")

    lines.append("\nBY SCORE BUCKET:")
    for s in stats["by_score"]:
        hr5  = s.get("h5_hit_rate", "N/A")
        avg5 = s.get("h5_avg_ret",  "N/A")
        lines.append(f"  {s['label']}: hit_rate_5d={hr5}% | avg_5d={avg5}% (n={s['n']})")

    top = stats["top_performers"][:5]
    lines.append(f"\nTOP 5 BY AVG 5D RETURN: " +
                 ", ".join(f"{r['symbol']}({r['avg_fwd_5d']}%)" for r in top))

    lines.append("""
Analyse this backtest data and write a concise evaluation (max 300 words):
SCREEN QUALITY: which screens have the best hit rates and returns
REGIME IMPACT: does market regime affect screen performance significantly
SCORE EDGE: do higher composite scores actually lead to better outcomes
DECAY: how quickly do returns decay (1d vs 3d vs 5d vs 10d)
RECOMMENDATION: which screens/conditions to trust most, which to ignore
KEY FINDING: one sentence summary

Plain text. CAPS for section headers.""")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM FORMATTER
# ─────────────────────────────────────────────────────────────────────────────

def format_telegram(report: dict) -> str:
    ov   = report["stats"]["overall"]
    date = report.get("date_range", "?")
    n    = report.get("n_signals", 0)
    lines = [
        f"*MICC Backtest -- {n} signals*",
        f"_{date}_",
        "",
        "*OVERALL HIT RATES:*",
    ]
    for h in HORIZONS:
        hr  = ov.get(f"h{h}_hit_rate", "N/A")
        avg = ov.get(f"h{h}_avg_ret",  "N/A")
        lines.append(f"  `{h}d` hit={hr}% | avg={avg}%")

    lines.append("")
    lines.append("*BY SCREEN (5d hit rate):*")
    for s in report["stats"]["by_screen"]:
        lines.append(f"  `{s['label'][:12]}` {s.get('h5_hit_rate','?')}% "
                     f"(avg {s.get('h5_avg_ret','?')}%)")

    analysis = str(report.get("analysis", ""))
    if analysis:
        lines.append("")
        lines.append("*ANALYSIS:*")
        lines.append(analysis[:500])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(send: bool = False) -> dict:
    print("=" * 55)
    print("  AGENT BACKTEST -- Signal Performance Analysis")
    print("=" * 55)

    print("  Loading signals_history...")
    signals = load_signals()
    print(f"  {len(signals)} signal rows across "
          f"{signals['symbol'].nunique()} symbols, "
          f"{signals['run_date'].nunique()} dates")

    if signals.empty:
        print("  No signals found. Run the pipeline first.")
        return {}

    date_range = f"{signals['run_date'].min()} to {signals['run_date'].max()}"
    print(f"  Date range: {date_range}")

    print("  Computing forward returns from parquet...")
    signals = compute_forward_returns(signals)

    # how many have at least 1d forward data
    have_fwd = signals["fwd_1d"].notna().sum()
    print(f"  Signals with forward data: {have_fwd}/{len(signals)}")

    print("  Computing statistics...")
    stats = compute_all_stats(signals)

    print("  LLM analysis...")
    prompt   = build_prompt(stats, len(signals), date_range)
    analysis, _src = call_llm(prompt, max_tokens=600, label="Backtest")
    print(f"  Analysis: {len(str(analysis))} chars")

    # compact summary for dashboard
    ov = stats["overall"]
    summary = {
        "n_signals":    len(signals),
        "n_symbols":    int(signals["symbol"].nunique()),
        "date_range":   date_range,
        "hit_rate_1d":  ov.get("h1_hit_rate"),
        "hit_rate_3d":  ov.get("h3_hit_rate"),
        "hit_rate_5d":  ov.get("h5_hit_rate"),
        "hit_rate_10d": ov.get("h10_hit_rate"),
        "avg_ret_5d":   ov.get("h5_avg_ret"),
        "best_screen":  max(stats["by_screen"],
                            key=lambda x: x.get("h5_hit_rate", 0),
                            default={}).get("label", "N/A"),
    }

    report = {
        "generated_at": now_ist(),
        "date_range":   date_range,
        "n_signals":    len(signals),
        "stats":        stats,
        "summary":      summary,
        "analysis":     analysis,
    }

    # save full report
    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {out}")

    # save compact summary
    summ_out = OUTPUT_DIR / "summary.json"
    summ_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if send:
        msg = format_telegram(report)
        ok  = send_telegram_chunks(msg)
        print(f"  Telegram: {'OK' if ok else 'FAILED'}")

    # print quick summary to console
    print("\n  QUICK RESULTS:")
    for h in HORIZONS:
        hr  = ov.get(f"h{h}_hit_rate", "?")
        avg = ov.get(f"h{h}_avg_ret",  "?")
        print(f"    {h:2d}d  hit={hr}%  avg_ret={avg}%")
    print(f"  Best screen: {summary['best_screen']}")

    print("=" * 55)
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Send to Telegram")
    args = ap.parse_args()
    run_backtest(send=args.send)
