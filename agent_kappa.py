# -*- coding: utf-8 -*-
"""
MICC v2 — Agent Kappa (k): Deep Stock / Index Profile
=======================================================
On-demand deep analysis for ANY single symbol (stock, NSE index, or
global index). Reads directly from the Phase 9B warehouse.

Produces:
  1. Global series stats (CAGR, MaxDD, Sharpe, Sortino, Calmar,
     skewness, kurtosis, 52w hi/lo, annualised vol)
  2. Multi-window behavior table (all 17 windows):
       mean, std, p5/p25/p75/p95, prob+, prob>10%, prob<-10%, Sharpe
  3. Regime-sliced stats for 20d window (bull/bear/sideways/all)
  4. Top-10 best rallies + top-10 worst crashes (20d and 60d windows)
  5. Seasonality profile: best/worst months + best/worst weekdays
  6. Correlation profile: vs SPX, Gold, DXY, VIX, USD/INR, Nifty50
  7. Current technical snapshot: RSI, MACD signal, BB position, ADX
  8. LLM verdict: one-paragraph institutional assessment

Output written to: agents/kappa/<SYMBOL>_report.json
Also updated:      agents/kappa/last_report.json (latest run)

Run:
  py agent_kappa.py RELIANCE
  py agent_kappa.py NIFTY50           (NSE index — use exact index_name)
  py agent_kappa.py SPX               (global index)
  py agent_kappa.py HDFCBANK --send   (send to Telegram)
  py agent_kappa.py RELIANCE --vs HDFCBANK ICICIBANK  (compare mode)

Location: D:/MICC/agent_kappa.py
"""

import json
import sqlite3
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from micc_data import call_llm, send_telegram_chunks, now_ist

warnings.filterwarnings("ignore")

DB_PATH    = Path(r"D:\marketDB\db\market.db")
OUTPUT_DIR = Path("agents/kappa")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY_STR = datetime.today().strftime("%Y-%m-%d")

ALL_WINDOWS = [1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180, 252, 504, 756]
KEY_WINDOWS = [5, 10, 20, 30, 60, 90, 252]


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  [Kappa] {msg}", flush=True)


# =========================================================================
# DB
# =========================================================================

def qdb(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:
        log(f"DB: {e}", "WARN"); return []
    finally:
        conn.close()


def qdf(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql(sql, conn, params=list(params))
    except Exception as e:
        log(f"DB: {e}", "WARN"); return pd.DataFrame()
    finally:
        conn.close()


def r2(x):
    try:
        v = float(x); return round(v, 2) if v == v else None
    except Exception:
        return None

def r4(x):
    try:
        v = float(x); return round(v, 4) if v == v else None
    except Exception:
        return None


# =========================================================================
# RESOLVE SYMBOL — detect asset_type automatically
# =========================================================================

def resolve_symbol(symbol: str) -> tuple[str, str]:
    """
    Returns (canonical_symbol, asset_type) or raises ValueError.
    asset_type: 'stock' | 'index' | 'global'
    """
    sym = symbol.strip().upper()

    # Check global_indices_daily first (exact match)
    row = qdb("SELECT symbol FROM global_indices_daily WHERE symbol=? LIMIT 1", (sym,))
    if row:
        return sym, "global"

    # Check symbol_series_stats (stocks)
    row = qdb("SELECT symbol FROM symbol_series_stats WHERE symbol=? AND asset_type='stock' LIMIT 1", (sym,))
    if row:
        return sym, "stock"

    # Check window_stats for index — exact match
    row = qdb("SELECT symbol FROM window_stats WHERE symbol=? AND asset_type='index' LIMIT 1", (sym,))
    if row:
        return sym, "index"

    # Check window_stats for index — case-insensitive LIKE
    row = qdb(
        "SELECT symbol FROM window_stats "
        "WHERE asset_type='index' AND UPPER(symbol) LIKE ? LIMIT 1",
        (f"%{sym}%",)
    )
    if row:
        return row[0][0], "index"

    raise ValueError(
        f"Symbol '{symbol}' not found in window_stats, symbol_series_stats, "
        f"or global_indices_daily. "
        f"Run: py agent_kappa.py --list  to see available symbols."
    )


def list_available(limit=50):
    stocks  = qdb("SELECT symbol FROM symbol_series_stats WHERE asset_type='stock' ORDER BY symbol LIMIT ?", (limit,))
    indices = qdb("SELECT DISTINCT symbol FROM window_stats WHERE asset_type='index' ORDER BY symbol LIMIT 30")
    global_ = qdb("SELECT DISTINCT symbol FROM global_indices_daily ORDER BY symbol")
    print(f"\nStocks  ({len(stocks)} shown): {[r[0] for r in stocks]}")
    print(f"Indices ({len(indices)} shown): {[r[0] for r in indices]}")
    print(f"Global  ({len(global_)} total): {[r[0] for r in global_]}")


# =========================================================================
# SECTION 1 — SERIES STATS
# =========================================================================

def get_series_stats(symbol: str, asset_type: str) -> dict:
    row = qdb(
        "SELECT first_date, last_date, n_trading_days, "
        "       cagr_pct, ann_volatility_pct, max_drawdown_pct, "
        "       mdd_start_date, mdd_trough_date, mdd_recovery_days, "
        "       sharpe_ratio, sortino_ratio, calmar_ratio, "
        "       skewness, kurtosis, "
        "       high_52w, low_52w, last_close "
        "FROM symbol_series_stats "
        "WHERE symbol=? AND asset_type=?",
        (symbol, asset_type)
    )
    if not row:
        return {}
    r = row[0]
    keys = ["first_date","last_date","total_trading_days",
            "cagr_pct","ann_volatility_pct","max_drawdown_pct",
            "max_drawdown_start","max_drawdown_end","drawdown_recovery_days",
            "sharpe_ratio","sortino_ratio","calmar_ratio",
            "skewness","kurtosis","high_52w","low_52w","last_close"]
    d = dict(zip(keys, r))
    for k in ("cagr_pct","ann_volatility_pct","max_drawdown_pct",
              "skewness","kurtosis","high_52w","low_52w","last_close"):
        d[k] = r2(d[k])
    d["sharpe_ratio"]  = r4(d["sharpe_ratio"])
    d["sortino_ratio"] = r4(d["sortino_ratio"])
    d["calmar_ratio"]  = r4(d["calmar_ratio"])
    return d


# =========================================================================
# SECTION 2 — WINDOW STATS TABLE
# =========================================================================

def get_window_table(symbol: str, asset_type: str) -> list:
    rows = qdb("""
        SELECT window_days, n_windows, mean_return, median_return, std_return,
               p1, p5, p10, p25, p75, p90, p95, p99,
               prob_positive, prob_gt5, prob_gt10, prob_gt20,
               prob_lt_neg5, prob_lt_neg10, prob_lt_neg20,
               sharpe_ratio, calmar_ratio, ann_return_equiv,
               min_return, max_return
        FROM window_stats
        WHERE symbol=? AND asset_type=?
        ORDER BY window_days
    """, (symbol, asset_type))

    result = []
    for r in rows:
        if r[0] not in KEY_WINDOWS:
            continue
        result.append({
            "window_days":    int(r[0]),
            "n_windows":      int(r[1]),
            "mean":           r2(r[2]),
            "median":         r2(r[3]),
            "std":            r2(r[4]),
            "p1":             r2(r[5]),
            "p5":             r2(r[6]),
            "p10":            r2(r[7]),
            "p25":            r2(r[8]),
            "p75":            r2(r[9]),
            "p90":            r2(r[10]),
            "p95":            r2(r[11]),
            "p99":            r2(r[12]),
            "prob_positive":  r2(r[13] * 100) if r[13] else None,
            "prob_gt5":       r2(r[14] * 100) if r[14] else None,
            "prob_gt10":      r2(r[15] * 100) if r[15] else None,
            "prob_gt20":      r2(r[16] * 100) if r[16] else None,
            "prob_lt_neg5":   r2(r[17] * 100) if r[17] else None,
            "prob_lt_neg10":  r2(r[18] * 100) if r[18] else None,
            "prob_lt_neg20":  r2(r[19] * 100) if r[19] else None,
            "sharpe":         r4(r[20]),
            "calmar":         r4(r[21]),
            "ann_equiv":      r2(r[22]),
            "worst_ever":     r2(r[23]),
            "best_ever":      r2(r[24]),
        })
    return result


# =========================================================================
# SECTION 3 — REGIME STATS
# =========================================================================

def get_regime_stats(symbol: str, asset_type: str, window: int = 20) -> list:
    rows = qdb("""
        SELECT regime, n_windows, mean_return, median_return, std_return,
               p5, p25, p75, p95, prob_positive, prob_gt10, prob_lt_neg10,
               min_return, max_return
        FROM window_regime_stats
        WHERE symbol=? AND asset_type=? AND window_days=?
        ORDER BY CASE regime
            WHEN 'bull'     THEN 1
            WHEN 'sideways' THEN 2
            WHEN 'bear'     THEN 3
            ELSE 4 END
    """, (symbol, asset_type, window))

    result = []
    for r in rows:
        result.append({
            "regime":        r[0],
            "n_windows":     int(r[1]),
            "mean":          r2(r[2]),
            "median":        r2(r[3]),
            "std":           r2(r[4]),
            "p5":            r2(r[5]),
            "p25":           r2(r[6]),
            "p75":           r2(r[7]),
            "p95":           r2(r[8]),
            "prob_positive": r2(r[9] * 100) if r[9] else None,
            "prob_gt10":     r2(r[10] * 100) if r[10] else None,
            "prob_lt_neg10": r2(r[11] * 100) if r[11] else None,
            "worst_ever":    r2(r[12]),
            "best_ever":     r2(r[13]),
        })
    return result


# =========================================================================
# SECTION 4 — HISTORICAL EPISODES
# =========================================================================

def get_episodes(symbol: str, asset_type: str) -> dict:
    episodes = {}
    for w in (20, 60):
        best = qdb("""
            SELECT rank_n, start_date, end_date, return_pct
            FROM window_extremes
            WHERE symbol=? AND asset_type=? AND window_days=? AND direction='up'
            ORDER BY rank_n LIMIT 10
        """, (symbol, asset_type, w))

        worst = qdb("""
            SELECT rank_n, start_date, end_date, return_pct
            FROM window_extremes
            WHERE symbol=? AND asset_type=? AND window_days=? AND direction='down'
            ORDER BY rank_n LIMIT 10
        """, (symbol, asset_type, w))

        episodes[f"{w}d_best"] = [
            {"rank": r[0], "start": r[1], "end": r[2], "return_pct": r2(r[3])}
            for r in best
        ]
        episodes[f"{w}d_worst"] = [
            {"rank": r[0], "start": r[1], "end": r[2], "return_pct": r2(r[3])}
            for r in worst
        ]
    return episodes


# =========================================================================
# SECTION 5 — SEASONALITY
# =========================================================================

# Month number -> name mapping
MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
DAY_NAMES   = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri"}

def get_seasonality(symbol: str, asset_type: str) -> dict:
    # Actual columns: period_type, period_value, n_obs, mean_return_pct,
    #                 median_return_pct, std_return_pct, p25, p75, prob_positive
    monthly = qdb("""
        SELECT period_value, n_obs, mean_return_pct, median_return_pct,
               prob_positive
        FROM symbol_seasonality
        WHERE symbol=? AND asset_type=? AND period_type='month'
        ORDER BY period_value
    """, (symbol, asset_type))

    weekday = qdb("""
        SELECT period_value, n_obs, mean_return_pct, prob_positive
        FROM symbol_seasonality
        WHERE symbol=? AND asset_type=? AND period_type='weekday'
        ORDER BY period_value
    """, (symbol, asset_type))

    month_data = [
        {
            "month":         MONTH_NAMES.get(int(r[0]), str(r[0])),
            "avg_return":    r2(r[2]),
            "median_return": r2(r[3]),
            "prob_positive": r2(r[4] * 100) if r[4] else None,
            "n_obs":         int(r[1]) if r[1] else 0,
        }
        for r in monthly
    ]

    valid_months = [m for m in month_data if m["avg_return"] is not None]
    best_m  = max(valid_months, key=lambda x: x["avg_return"]) if valid_months else {}
    worst_m = min(valid_months, key=lambda x: x["avg_return"]) if valid_months else {}

    return {
        "monthly":    month_data,
        "weekday":    [
            {"day": DAY_NAMES.get(int(r[0]), str(r[0])),
             "avg_return": r2(r[2]),
             "prob_positive": r2(r[3] * 100) if r[3] else None,
             "n_obs": int(r[1]) if r[1] else 0}
            for r in weekday
        ],
        "best_month":  best_m,
        "worst_month": worst_m,
    }


# =========================================================================
# SECTION 6 — CORRELATIONS
# =========================================================================

def get_correlations(symbol: str, asset_type: str) -> list:
    rows = qdb("""
        SELECT benchmark, corr_1y, corr_3y, corr_alltime, beta_1y
        FROM symbol_correlations
        WHERE symbol=? AND asset_type=?
        ORDER BY ABS(COALESCE(corr_alltime, 0)) DESC
    """, (symbol, asset_type))

    return [
        {
            "benchmark":   r[0],
            "corr_1y":     r4(r[1]),
            "corr_3y":     r4(r[2]),
            "corr_5y":     None,
            "corr_all":    r4(r[3]),
            "beta_1y":     r4(r[4]),
            "beta_all":    None,
        }
        for r in rows
    ]


# =========================================================================
# SECTION 7 — TECHNICALS
# =========================================================================

def get_technicals(symbol: str, asset_type: str) -> dict:
    row = qdb("""
        SELECT as_of_date, rsi_14, rsi_21,
               macd_line, macd_signal, macd_histogram,
               bb_position, bb_width_pct,
               atr_14_pct, adx_14,
               pct_above_sma20, pct_above_sma50, pct_above_sma200,
               sma20_above_sma50, sma50_above_sma200, vol_surge_20d
        FROM symbol_technicals
        WHERE symbol=? AND asset_type=?
        ORDER BY as_of_date DESC LIMIT 1
    """, (symbol, asset_type))

    if not row:
        return {}
    r = row[0]
    # Derive MACD signal text from line vs signal
    macd_line = r[3]; macd_sig = r[4]; macd_hist = r[5]
    if macd_line is not None and macd_sig is not None:
        macd_signal_text = "bullish" if macd_line > macd_sig else "bearish"
    else:
        macd_signal_text = "neutral"

    golden = bool(r[13]) if r[13] is not None else None
    death  = (not golden) if golden is not None else None

    return {
        "as_of":           r[0],
        "rsi_14":          r2(r[1]),
        "rsi_21":          r2(r[2]),
        "macd_line":       r2(macd_line),
        "macd_signal":     macd_signal_text,
        "macd_histogram":  r2(macd_hist),
        "bb_position":     r2(r[6]),
        "bb_width_pct":    r2(r[7]),
        "atr_pct":         r2(r[8]),
        "adx":             r2(r[9]),
        "dist_sma20":      r2(r[10]),
        "dist_sma50":      r2(r[11]),
        "dist_sma200":     r2(r[12]),
        "golden_cross":    golden,
        "death_cross":     death,
        "volume_surge":    r2(r[15]),
    }


# =========================================================================
# LLM VERDICT
# =========================================================================

def llm_verdict(symbol, asset_type, series, window_table, regime_stats,
                episodes, seasonality, correlations, technicals) -> tuple[str, str]:

    # Summarise 20d window
    w20 = next((w for w in window_table if w["window_days"] == 20), None)
    w60 = next((w for w in window_table if w["window_days"] == 60), None)

    # Regime summary
    bull_r = next((r for r in regime_stats if r["regime"] == "bull"), None)
    bear_r = next((r for r in regime_stats if r["regime"] == "bear"), None)

    # Best/worst episodes
    best3  = episodes.get("20d_best", [])[:3]
    worst3 = episodes.get("20d_worst", [])[:3]

    # Correlations top 3
    top_corr = correlations[:3]

    # Seasonality
    best_m  = seasonality.get("best_month", {}) or {}
    worst_m = seasonality.get("worst_month", {}) or {}

    tech = technicals

    series_str = (
        f"CAGR={series.get('cagr_pct')}%  Vol={series.get('ann_volatility_pct')}%  "
        f"MaxDD={series.get('max_drawdown_pct')}% ({series.get('max_drawdown_start')} to {series.get('max_drawdown_end')})  "
        f"Sharpe={series.get('sharpe_ratio')}  Sortino={series.get('sortino_ratio')}"
    ) if series else "No series stats"

    w20_str = (
        f"20d window: mean={w20['mean']}% std={w20['std']}% "
        f"p5={w20['p5']}% p95={w20['p95']}% prob+={w20['prob_positive']}% "
        f"Sharpe={w20['sharpe']}"
    ) if w20 else "20d: no data"

    w60_str = (
        f"60d window: mean={w60['mean']}% std={w60['std']}% "
        f"p5={w60['p5']}% prob+={w60['prob_positive']}%"
    ) if w60 else "60d: no data"

    regime_str = (
        f"Bull: mean={bull_r['mean'] if bull_r else 'N/A'}% prob+={bull_r['prob_positive'] if bull_r else 'N/A'}%  |  "
        f"Bear: mean={bear_r['mean'] if bear_r else 'N/A'}% prob+={bear_r['prob_positive'] if bear_r else 'N/A'}%"
    )

    best_ep = " | ".join(
        f"{e['start']}→{e['end']}:{e['return_pct']:+.1f}%"
        for e in best3 if e.get("return_pct")
    )
    worst_ep = " | ".join(
        f"{e['start']}→{e['end']}:{e['return_pct']:+.1f}%"
        for e in worst3 if e.get("return_pct")
    )

    corr_str = " | ".join(
        f"{c['benchmark']}:corr1y={c['corr_1y']} beta={c['beta_1y']}"
        for c in top_corr
    )

    tech_str = (
        f"RSI14={tech.get('rsi_14')}  MACD={tech.get('macd_signal')}  "
        f"BB_pos={tech.get('bb_position')}  ADX={tech.get('adx')}  "
        f"dist_SMA200={tech.get('dist_sma200')}%  "
        f"Golden_cross={tech.get('golden_cross')}  Vol_surge={tech.get('volume_surge')}"
    ) if tech else "No technicals"

    prompt = f"""You are MICC Deep Stock Analyst (Kappa). Date: {TODAY_STR}
Analysing: {symbol}  (type: {asset_type})

FULL HISTORY STATS:
{series_str}

WINDOW BEHAVIOR:
{w20_str}
{w60_str}

REGIME BEHAVIOR (20d):
{regime_str}

TOP-3 BEST 20d RALLIES: {best_ep or 'N/A'}
TOP-3 WORST 20d CRASHES: {worst_ep or 'N/A'}

SEASONALITY: Best month={best_m.get('month')} ({best_m.get('avg_return')}%)  |  Worst month={worst_m.get('month')} ({worst_m.get('avg_return')}%)

CORRELATIONS: {corr_str or 'N/A'}

CURRENT TECHNICALS: {tech_str}

Write a concise institutional assessment covering:
1. HISTORICAL CHARACTER — what kind of stock/asset is this historically?
2. WINDOW EDGE — what holding period works best and why?
3. REGIME SENSITIVITY — how does it behave in bull vs bear markets?
4. TECHNICAL SETUP NOW — is the current technical picture constructive or not?
5. CONCLUSION — one clear sentence: is this a high-quality asset to own?

Max 5 sections, 2-3 lines each. Institutional tone. No bullet lists."""

    return call_llm(prompt, max_tokens=800, label=f"Kappa-{symbol}", prefer_groq=True)


# =========================================================================
# TELEGRAM FORMAT
# =========================================================================

def format_telegram(symbol, report):
    s  = report.get("series_stats", {})
    w  = report.get("window_table", [])
    w20 = next((x for x in w if x["window_days"] == 20), {})
    t  = report.get("technicals", {})
    best_m  = report.get("seasonality", {}).get("best_month", {}) or {}
    worst_m = report.get("seasonality", {}).get("worst_month", {}) or {}

    lines = [
        f"*MICC Deep Stock Profile — {symbol}* | {TODAY_STR}",
        "",
        "*Full History:*",
        f"  CAGR={s.get('cagr_pct')}%  Vol={s.get('ann_volatility_pct')}%  "
        f"MaxDD={s.get('max_drawdown_pct')}%",
        f"  Sharpe={s.get('sharpe_ratio')}  Sortino={s.get('sortino_ratio')}  "
        f"Calmar={s.get('calmar_ratio')}",
        f"  Since: {s.get('first_date')} → {s.get('last_date')} "
        f"({s.get('total_trading_days')} days)",
        "",
        "*20d Window Stats:*",
        f"  mean={w20.get('mean')}%  std={w20.get('std')}%  "
        f"Sharpe={w20.get('sharpe')}",
        f"  p5={w20.get('p5')}%  p25={w20.get('p25')}%  "
        f"p75={w20.get('p75')}%  p95={w20.get('p95')}%",
        f"  prob+={w20.get('prob_positive')}%  "
        f"prob>10%={w20.get('prob_gt10')}%  "
        f"prob<-10%={w20.get('prob_lt_neg10')}%",
        "",
        "*Technicals:*",
        f"  RSI14={t.get('rsi_14')}  MACD={t.get('macd_signal')}  "
        f"ADX={t.get('adx')}",
        f"  vs SMA200: {t.get('dist_sma200')}%  "
        f"Golden={t.get('golden_cross')}",
        "",
        f"*Seasonality:* Best={best_m.get('month')} ({best_m.get('avg_return')}%)  "
        f"Worst={worst_m.get('month')} ({worst_m.get('avg_return')}%)",
        "",
        "*LLM Verdict:*",
        report.get("llm_verdict", "")[:1000],
        f"\n_{now_ist()}_",
    ]
    return "\n".join(lines)


# =========================================================================
# COMPARE MODE — quick side-by-side of 2-5 symbols
# =========================================================================

def compare_symbols(symbols: list, window: int = 20):
    print(f"\n{'='*70}")
    print(f"  COMPARISON: {' vs '.join(symbols)} | {window}d window | {TODAY_STR}")
    print(f"{'='*70}")
    header = f"{'Symbol':<15} {'mean':>7} {'std':>7} {'p5':>7} {'p95':>7} "
    header += f"{'prob+':>7} {'>10%':>6} {'Sharpe':>8} {'CAGR':>7} {'MaxDD':>8}"
    print(header)
    print("-" * 70)

    for sym in symbols:
        try:
            canonical, atype = resolve_symbol(sym)
        except ValueError as e:
            print(f"  {sym}: NOT FOUND"); continue

        w_row = qdb("""
            SELECT mean_return, std_return, p5, p95, prob_positive,
                   prob_gt10, sharpe_ratio
            FROM window_stats
            WHERE symbol=? AND asset_type=? AND window_days=?
        """, (canonical, atype, window))

        s_row = qdb("""
            SELECT cagr_pct, max_drawdown_pct, sharpe_ratio
            FROM symbol_series_stats WHERE symbol=? AND asset_type=?
        """, (canonical, atype))

        if not w_row:
            print(f"  {canonical:<15} no window data for {window}d"); continue

        w = w_row[0]
        s = s_row[0] if s_row else (None, None, None)

        prob_pos = r2(w[4] * 100) if w[4] else None
        prob_gt10 = r2(w[5] * 100) if w[5] else None

        print(
            f"  {canonical:<15}"
            f" {r2(w[0]):>+7.2f}"
            f" {r2(w[1]):>7.2f}"
            f" {r2(w[2]):>+7.2f}"
            f" {r2(w[3]):>+7.2f}"
            f" {str(prob_pos):>7}"
            f" {str(prob_gt10):>6}"
            f" {str(r4(w[6])):>8}"
            f" {str(r2(s[0])):>7}"
            f" {str(r2(s[1])):>8}"
        )
    print()


# =========================================================================
# MAIN — run full deep profile
# =========================================================================

def run_kappa(symbol: str, send: bool = False) -> dict:
    try:
        canonical, asset_type = resolve_symbol(symbol)
    except ValueError as e:
        print(f"[Kappa] ERROR: {e}"); return {}

    print(f"\n{'='*60}")
    print(f"  MICC Agent Kappa — Deep Profile: {canonical} ({asset_type})")
    print(f"  {TODAY_STR}")
    print(f"{'='*60}\n")

    log(f"Loading series stats...")
    series = get_series_stats(canonical, asset_type)
    if series:
        log(f"  CAGR={series.get('cagr_pct')}%  MaxDD={series.get('max_drawdown_pct')}%  "
            f"Sharpe={series.get('sharpe_ratio')}  "
            f"Period: {series.get('first_date')} → {series.get('last_date')}", "OK")

    log("Loading window stats table...")
    window_table = get_window_table(canonical, asset_type)
    log(f"  {len(window_table)} windows loaded", "OK" if window_table else "WARN")

    log("Loading regime stats (20d)...")
    regime_stats = get_regime_stats(canonical, asset_type, window=20)
    log(f"  {len(regime_stats)} regimes", "OK" if regime_stats else "WARN")

    log("Loading historical episodes (top-10 best/worst, 20d+60d)...")
    episodes = get_episodes(canonical, asset_type)
    log(f"  20d best: {len(episodes.get('20d_best',[]))}  "
        f"20d worst: {len(episodes.get('20d_worst',[]))}  "
        f"60d best: {len(episodes.get('60d_best',[]))}  "
        f"60d worst: {len(episodes.get('60d_worst',[]))}", "OK")

    log("Loading seasonality...")
    seasonality = get_seasonality(canonical, asset_type)
    bm_log = (seasonality.get("best_month") or {}).get("month", "N/A")
    wm_log = (seasonality.get("worst_month") or {}).get("month", "N/A")
    log(f"  Monthly: {len(seasonality.get('monthly',[]))} months  "
        f"Best: {bm_log}  Worst: {wm_log}", "OK")

    log("Loading correlations...")
    correlations = get_correlations(canonical, asset_type)
    log(f"  {len(correlations)} benchmarks", "OK" if correlations else "WARN")

    log("Loading technicals...")
    technicals = get_technicals(canonical, asset_type)
    log(f"  RSI14={technicals.get('rsi_14')}  MACD={technicals.get('macd_signal')}  "
        f"ADX={technicals.get('adx')}", "OK" if technicals else "WARN")

    log("LLM verdict (Groq)...")
    verdict, llm_src = llm_verdict(
        canonical, asset_type, series, window_table,
        regime_stats, episodes, seasonality, correlations, technicals
    )
    log(f"LLM done via {llm_src}", "OK")

    report = {
        "agent":       "Kappa",
        "symbol":      canonical,
        "asset_type":  asset_type,
        "timestamp":   datetime.now().isoformat(),
        "date":        TODAY_STR,
        "series_stats":     series,
        "window_table":     window_table,
        "regime_stats_20d": regime_stats,
        "episodes":         episodes,
        "seasonality":      seasonality,
        "correlations":     correlations,
        "technicals":       technicals,
        "llm_verdict":      verdict,
        "llm_source":       llm_src,
    }

    # Save per-symbol report
    sym_out = OUTPUT_DIR / f"{canonical}_report.json"
    with open(sym_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # Also update last_report
    last_out = OUTPUT_DIR / "last_report.json"
    with open(last_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    log(f"Reports saved -> {sym_out}", "OK")

    # Terminal summary
    print(f"\n{'='*60}")
    print(f"  {canonical} ({asset_type})")
    if series:
        print(f"  CAGR={series.get('cagr_pct')}%  Vol={series.get('ann_volatility_pct')}%  "
              f"MaxDD={series.get('max_drawdown_pct')}%")
        print(f"  Sharpe={series.get('sharpe_ratio')}  Sortino={series.get('sortino_ratio')}  "
              f"Calmar={series.get('calmar_ratio')}")
    if window_table:
        print(f"\n  Window behavior:")
        print(f"  {'Win':>4} {'mean%':>7} {'std%':>6} {'p5%':>7} {'p95%':>7} "
              f"{'prob+':>6} {'>10%':>6} {'Sharpe':>8}")
        print("  " + "-" * 55)
        for w in window_table:
            print(
                f"  {w['window_days']:>4}d"
                f" {str(w['mean'] or '?'):>7}"
                f" {str(w['std']  or '?'):>6}"
                f" {str(w['p5']   or '?'):>7}"
                f" {str(w['p95']  or '?'):>7}"
                f" {str(w['prob_positive'] or '?'):>6}%"
                f" {str(w['prob_gt10'] or '?'):>6}%"
                f" {str(w['sharpe'] or '?'):>8}"
            )
    if regime_stats:
        print(f"\n  Regime stats (20d window):")
        for r in regime_stats:
            print(f"  {r['regime']:>10}: mean={r['mean']:>+6.1f}%  "
                  f"p5={r['p5']:>+6.1f}%  prob+={r['prob_positive']:>5}%  "
                  f"n={r['n_windows']}")
    if episodes.get("20d_best"):
        print(f"\n  Top-3 best 20d rallies:")
        for e in episodes["20d_best"][:3]:
            print(f"    {e['start']} → {e['end']}: {e['return_pct']:>+7.2f}%")
        print(f"  Top-3 worst 20d crashes:")
        for e in episodes["20d_worst"][:3]:
            print(f"    {e['start']} → {e['end']}: {e['return_pct']:>+7.2f}%")
    bm = seasonality.get("best_month") or {}
    wm = seasonality.get("worst_month") or {}
    if bm.get("month"):
        print(f"\n  Seasonality: Best={bm.get('month')} ({bm.get('avg_return')}%)  "
              f"Worst={wm.get('month')} ({wm.get('avg_return')}%)")
    if technicals:
        print(f"\n  Technicals: RSI14={technicals.get('rsi_14')}  "
              f"MACD={technicals.get('macd_signal')}  "
              f"ADX={technicals.get('adx')}  "
              f"SMA200_dist={technicals.get('dist_sma200')}%")
    print(f"\n  LLM Verdict ({llm_src}):")
    print(f"  {verdict[:600]}")
    print(f"{'='*60}\n")

    if send:
        log("Sending to Telegram...")
        send_telegram_chunks(format_telegram(canonical, report))
        log("Sent", "OK")

    return report


# =========================================================================
# ENTRY POINT
# =========================================================================

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--list" in args:
        list_available(limit=50)
        sys.exit(0)

    # Compare mode: --vs symbol1 symbol2 symbol3...
    if "--vs" in args:
        idx   = args.index("--vs")
        base  = args[0]
        vs    = args[idx+1:]
        symbols = [base] + [s for s in vs if not s.startswith("--")]
        window  = 20
        for a in args:
            if a.startswith("--w="):
                try: window = int(a.split("=")[1])
                except Exception: pass
        compare_symbols(symbols, window=window)
        sys.exit(0)

    # Normal mode: deep profile for one symbol
    symbol = args[0]
    send   = "--send" in args
    run_kappa(symbol, send=send)
