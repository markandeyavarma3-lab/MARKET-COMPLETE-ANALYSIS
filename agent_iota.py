# -*- coding: utf-8 -*-
"""
MICC v2 — Agent Iota (i): Deep Analysis Room
==============================================
Reads the Phase 9B statistical warehouse and generates 6 screens
of deep probabilistic intelligence.

SCREEN 1 — Best probability stocks (regime-aware, 20d window)
SCREEN 2 — Risk-adjusted gems (high Sharpe ratio windows)
SCREEN 3 — Worst-case protected (p5 floor > -5%)
SCREEN 4 — Regime movers vs defensives
SCREEN 5 — Global macro pulse (29 symbols + NSE correlations)
SCREEN 6 — Index deep stats (Nifty50, Bank, IT, Metal, Pharma, etc.)

LLM synthesis via Groq llama-3.3-70b.

Run:  py agent_iota.py [--send]
      py agent_iota.py --send   -> also posts to Telegram

Location: D:/MICC/agent_iota.py
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
OUTPUT_DIR = Path("agents/iota")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY_STR = datetime.today().strftime("%Y-%m-%d")

DISPLAY_WINDOWS = [5, 10, 20, 30, 60, 90, 252]

KEY_INDICES = [
    "Nifty 50", "Nifty Bank", "Nifty IT", "Nifty Metal",
    "Nifty Pharma", "Nifty FMCG", "Nifty Auto", "Nifty Realty",
]

GLOBAL_EQUITY = ["SPX", "NDX", "Nikkei225", "DAX", "HangSeng", "FTSE100"]
GLOBAL_MACRO  = ["VIX", "DXY", "Gold", "CrudeWTI", "US10Y", "USDINR"]
GLOBAL_CRYPTO = ["Bitcoin"]


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  [Iota] {msg}", flush=True)


# =========================================================================
# DB HELPERS (never use get_conn in agents)
# =========================================================================

def qdb(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:
        log(f"DB error: {e}", "WARN"); return []
    finally:
        conn.close()


def qdf(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql(sql, conn, params=list(params))
    except Exception as e:
        log(f"DB error: {e}", "WARN"); return pd.DataFrame()
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
# DETECT CURRENT REGIME
# =========================================================================

def get_current_regime():
    try:
        # indices_data has Nifty 50 history (4573 rows, 2007-2026).
        # The fix_regime script confirmed: index_name='NIFTY 50', col=close, 4573 rows.
        # Nifty 50 is always > 5000, so filter close>5000 to exclude any stock rows.
        rows = qdb(
            "SELECT date, close FROM indices_data "
            "WHERE index_name='NIFTY 50' AND close > 5000 "
            "ORDER BY date DESC LIMIT 60"
        )
        # Fallback: try exact 'Nifty 50' (mixed case)
        if len(rows) < 10:
            rows = qdb(
                "SELECT date, close FROM indices_data "
                "WHERE index_name='Nifty 50' AND close > 5000 "
                "ORDER BY date DESC LIMIT 60"
            )
        # Final fallback: market_snapshot
        if len(rows) < 10:
            rows = qdb(
                "SELECT date, closing_index_value FROM market_snapshot "
                "WHERE index_name='Nifty 50' AND closing_index_value > 5000 "
                "ORDER BY date DESC LIMIT 60"
            )
        if len(rows) >= 50:
            closes = [float(r[1]) for r in reversed(rows)]
            sma20  = float(np.mean(closes[-20:]))
            sma50  = float(np.mean(closes[-50:]))
            last   = closes[-1]
            ret20  = (last / closes[-21] - 1) * 100 if len(closes) >= 21 else 0

            if last > sma20 > sma50 and ret20 > 0:
                regime = "bull"
            elif last < sma20 < sma50 and ret20 < 0:
                regime = "bear"
            else:
                regime = "sideways"

            # VIX override — if VIX > 25, treat as bear regardless
            vix_rows = qdb(
                "SELECT close FROM global_indices_daily "
                "WHERE symbol='IndiaVIX' ORDER BY date DESC LIMIT 1"
            )
            vix = float(vix_rows[0][0]) if vix_rows else None
            if vix and vix > 28 and regime == "bull":
                regime = "sideways"

            log(f"Regime: {regime.upper()}  Nifty={last:.0f}  "
                f"SMA20={sma20:.0f}  SMA50={sma50:.0f}  "
                f"20d={ret20:+.1f}%  VIX={vix}")
            return regime, vix, ret20

    except Exception as e:
        log(f"Regime detection: {e}", "WARN")

    return "sideways", None, None


# =========================================================================
# SCREEN 1 — BEST PROBABILITY STOCKS (regime-aware)
# =========================================================================

def screen_best_probability(regime, window=20, top_n=25):
    log(f"Screen 1: Best probability (w={window}d, regime={regime})")

    # Try regime-specific first
    df = qdf("""
        SELECT r.symbol,
               r.n_windows, r.mean_return, r.std_return,
               r.prob_positive, r.prob_gt10,
               r.p5, r.p25, r.p75, r.p95,
               r.min_return, r.max_return,
               s.last_close, s.cagr_pct, s.sharpe_ratio, s.ann_volatility_pct
        FROM window_regime_stats r
        JOIN symbol_series_stats s
          ON r.symbol = s.symbol AND s.asset_type = 'stock'
        WHERE r.asset_type = 'stock'
          AND r.window_days = ?
          AND r.regime      = ?
          AND r.n_windows  >= 20
          AND r.mean_return > 0
          AND r.prob_positive > 0.5
    """, (window, regime))

    # Fallback to 'all' regime
    if len(df) < 50:
        log(f"  Only {len(df)} in '{regime}' — using 'all' regime")
        df = qdf("""
            SELECT r.symbol,
                   r.n_windows, r.mean_return, r.std_return,
                   r.prob_positive, r.prob_gt10,
                   r.p5, r.p25, r.p75, r.p95,
                   r.min_return, r.max_return,
                   s.last_close, s.cagr_pct, s.sharpe_ratio, s.ann_volatility_pct
            FROM window_regime_stats r
            JOIN symbol_series_stats s
              ON r.symbol = s.symbol AND s.asset_type = 'stock'
            WHERE r.asset_type = 'stock'
              AND r.window_days = ?
              AND r.regime      = 'all'
              AND r.n_windows  >= 30
              AND r.mean_return > 0
              AND r.prob_positive > 0.5
        """, (window,))

    if df.empty:
        return []

    df["std_safe"] = df["std_return"].clip(lower=0.1)
    df["score"] = (df["prob_positive"] * (df["mean_return"] / df["std_safe"])).round(4)
    df = df.sort_values("score", ascending=False).head(top_n)

    result = []
    for _, r in df.iterrows():
        result.append({
            "symbol":        str(r["symbol"]),
            "score":         r4(r["score"]),
            "prob_positive": r2(r["prob_positive"] * 100),
            "prob_gt10pct":  r2(r.get("prob_gt10", 0) * 100),
            "mean_return":   r2(r["mean_return"]),
            "std_return":    r2(r["std_return"]),
            "p5_worst":      r2(r["p5"]),
            "p25":           r2(r["p25"]),
            "p75":           r2(r["p75"]),
            "p95_best":      r2(r["p95"]),
            "n_samples":     int(r["n_windows"]),
            "last_close":    r2(r.get("last_close")),
            "cagr_pct":      r2(r.get("cagr_pct")),
        })

    log(f"  {len(result)} stocks | top: {result[0]['symbol']} "
        f"score={result[0]['score']} prob={result[0]['prob_positive']}%")
    return result


# =========================================================================
# SCREEN 2 — RISK-ADJUSTED GEMS
# =========================================================================

def screen_risk_adjusted_gems(top_n=20):
    log("Screen 2: Risk-adjusted gems (Sharpe > 1.2)")

    df = qdf("""
        SELECT ws.symbol, ws.window_days, ws.sharpe_ratio, ws.calmar_ratio,
               ws.mean_return, ws.std_return, ws.prob_positive,
               ws.p5, ws.p25, ws.p75, ws.p95,
               ss.cagr_pct, ss.max_drawdown_pct, ss.sortino_ratio,
               ss.last_close, ss.ann_volatility_pct
        FROM window_stats ws
        JOIN symbol_series_stats ss
          ON ws.symbol = ss.symbol AND ss.asset_type = 'stock'
        WHERE ws.asset_type    = 'stock'
          AND ws.window_days  IN (20, 30)
          AND ws.sharpe_ratio  > 0.8
          AND ws.prob_positive > 0.50
          AND ws.n_windows    >= 30
          AND ss.max_drawdown_pct > -90
        ORDER BY ws.sharpe_ratio DESC
        LIMIT 100
    """)

    if df.empty:
        return []

    df = df.sort_values("sharpe_ratio", ascending=False).drop_duplicates("symbol").head(top_n)

    result = []
    for _, r in df.iterrows():
        result.append({
            "symbol":        str(r["symbol"]),
            "window_days":   int(r["window_days"]),
            "sharpe_ratio":  r4(r["sharpe_ratio"]),
            "calmar_ratio":  r4(r.get("calmar_ratio")),
            "sortino_ratio": r4(r.get("sortino_ratio")),
            "mean_return":   r2(r["mean_return"]),
            "std_return":    r2(r["std_return"]),
            "prob_positive": r2(r["prob_positive"] * 100),
            "p5_worst":      r2(r["p5"]),
            "p95_best":      r2(r["p95"]),
            "cagr_pct":      r2(r.get("cagr_pct")),
            "max_drawdown":  r2(r.get("max_drawdown_pct")),
            "ann_vol":       r2(r.get("ann_volatility_pct")),
            "last_close":    r2(r.get("last_close")),
        })

    log(f"  {len(result)} gems | top: {result[0]['symbol']} Sharpe={result[0]['sharpe_ratio']}")
    return result


# =========================================================================
# SCREEN 3 — WORST-CASE PROTECTED
# =========================================================================

def screen_worst_case_protected(window=20, top_n=20):
    log(f"Screen 3: Worst-case protected (p5 > -5%, w={window}d)")

    df = qdf("""
        SELECT ws.symbol, ws.p5, ws.p25, ws.p75, ws.p95,
               ws.mean_return, ws.prob_positive,
               ws.min_return, ws.max_return, ws.n_windows,
               ss.last_close, ss.max_drawdown_pct, ss.cagr_pct,
               ss.ann_volatility_pct, ss.sharpe_ratio
        FROM window_stats ws
        JOIN symbol_series_stats ss
          ON ws.symbol = ss.symbol AND ss.asset_type = 'stock'
        WHERE ws.asset_type    = 'stock'
          AND ws.window_days   = ?
          AND ws.p5            > -8.0
          AND ws.mean_return   > 0
          AND ws.prob_positive > 0.5
          AND ws.n_windows    >= 20
        ORDER BY ws.p5 DESC, ws.mean_return DESC
        LIMIT ?
    """, (window, top_n))

    if df.empty:
        return []

    result = []
    for _, r in df.iterrows():
        result.append({
            "symbol":        str(r["symbol"]),
            "p5_floor":      r2(r["p5"]),
            "p25":           r2(r["p25"]),
            "mean_return":   r2(r["mean_return"]),
            "p75":           r2(r["p75"]),
            "p95_ceiling":   r2(r["p95"]),
            "prob_positive": r2(r["prob_positive"] * 100),
            "worst_ever":    r2(r["min_return"]),
            "best_ever":     r2(r["max_return"]),
            "n_samples":     int(r["n_windows"]),
            "cagr_pct":      r2(r.get("cagr_pct")),
            "max_drawdown":  r2(r.get("max_drawdown_pct")),
            "last_close":    r2(r.get("last_close")),
            "sharpe":        r4(r.get("sharpe_ratio")),
        })

    log(f"  {len(result)} protected | best floor: {result[0]['symbol']} p5={result[0]['p5_floor']}%")
    return result


# =========================================================================
# SCREEN 4 — REGIME MOVERS & DEFENSIVES
# =========================================================================

def screen_regime_sensitivity(window=20, top_n=15):
    log(f"Screen 4: Regime sensitivity (w={window}d)")

    df = qdf("""
        SELECT symbol,
               MAX(CASE WHEN regime='bull'     THEN mean_return  END) AS bull_mean,
               MAX(CASE WHEN regime='bear'     THEN mean_return  END) AS bear_mean,
               MAX(CASE WHEN regime='sideways' THEN mean_return  END) AS sw_mean,
               MAX(CASE WHEN regime='all'      THEN mean_return  END) AS all_mean,
               MAX(CASE WHEN regime='bull'     THEN prob_positive END) AS bull_prob,
               MAX(CASE WHEN regime='bear'     THEN prob_positive END) AS bear_prob,
               MAX(CASE WHEN regime='all'      THEN n_windows    END) AS n_all
        FROM window_regime_stats
        WHERE asset_type = 'stock' AND window_days = ?
        GROUP BY symbol
        HAVING bull_mean IS NOT NULL AND bear_mean IS NOT NULL AND n_all >= 20
    """, (window,))

    if df.empty:
        return {"amplifiers": [], "defensives": []}

    df["spread"]      = df["bull_mean"] - df["bear_mean"]
    df["consistency"] = df[["bull_mean", "bear_mean", "sw_mean"]].std(axis=1)

    amps = df[(df["bull_mean"] > 5) & (df["spread"] > 10)]\
             .sort_values("spread", ascending=False).head(top_n)

    defs = df[(df["bull_mean"] > 0) & (df["bear_mean"] > 0) &
              (df["sw_mean"].notna()) & (df["sw_mean"] > 0) &
              (df["consistency"] < 8)]\
             .sort_values("bear_mean", ascending=False).head(top_n)

    def fmt(sub):
        out = []
        for _, r in sub.iterrows():
            out.append({
                "symbol":      str(r["symbol"]),
                "bull_mean":   r2(r["bull_mean"]),
                "bear_mean":   r2(r["bear_mean"]),
                "sw_mean":     r2(r.get("sw_mean")),
                "all_mean":    r2(r.get("all_mean")),
                "bull_prob":   r2(r.get("bull_prob", 0) * 100),
                "bear_prob":   r2(r.get("bear_prob", 0) * 100),
                "spread":      r2(r["spread"]),
                "consistency": r2(r.get("consistency")),
            })
        return out

    result = {"amplifiers": fmt(amps), "defensives": fmt(defs)}
    log(f"  Amplifiers: {len(result['amplifiers'])}  Defensives: {len(result['defensives'])}")
    return result


# =========================================================================
# SCREEN 5 — GLOBAL MACRO PULSE
# =========================================================================

def screen_global_macro_pulse():
    log("Screen 5: Global macro pulse")

    pulse = []
    for sym in GLOBAL_EQUITY + GLOBAL_MACRO + GLOBAL_CRYPTO:
        rows = qdb(
            "SELECT date, close FROM global_indices_daily "
            "WHERE symbol=? AND close IS NOT NULL "
            "ORDER BY date DESC LIMIT 25",
            (sym,)
        )
        if not rows:
            continue
        closes = [float(r[1]) for r in rows]
        last   = closes[0]
        ret1d  = (last / closes[1]  - 1) * 100 if len(closes) >= 2  else None
        ret5d  = (last / closes[5]  - 1) * 100 if len(closes) >= 6  else None
        ret20d = (last / closes[20] - 1) * 100 if len(closes) >= 21 else None
        pulse.append({
            "symbol":  sym,
            "date":    rows[0][0],
            "close":   r2(last),
            "ret_1d":  r2(ret1d),
            "ret_5d":  r2(ret5d),
            "ret_20d": r2(ret20d),
        })

    vix_r  = next((p for p in pulse if p["symbol"] == "VIX"), None)
    spx_r  = next((p for p in pulse if p["symbol"] == "SPX"), None)
    dxy_r  = next((p for p in pulse if p["symbol"] == "DXY"), None)
    gold_r = next((p for p in pulse if p["symbol"] == "Gold"), None)

    vix   = vix_r["close"]  if vix_r  else None
    spx5d = spx_r["ret_5d"] if spx_r  else None
    dxy5d = dxy_r["ret_5d"] if dxy_r  else None
    gold5d = gold_r["ret_5d"] if gold_r else None

    if vix and spx5d is not None:
        if vix > 25 or spx5d < -3:
            global_risk = "RISK-OFF"
        elif vix < 16 and spx5d > 1:
            global_risk = "RISK-ON"
        else:
            global_risk = "NEUTRAL"
    else:
        global_risk = "UNKNOWN"

    log(f"  {global_risk}  VIX={vix}  SPX5d={spx5d}%  DXY5d={dxy5d}%")

    spx_corr = qdf("""
        SELECT symbol, corr_1y, corr_3y, corr_alltime, beta_1y
        FROM symbol_correlations
        WHERE asset_type='stock' AND benchmark='S&P 500'
          AND corr_1y IS NOT NULL
        ORDER BY ABS(corr_1y) DESC LIMIT 15
    """)

    gold_corr = qdf("""
        SELECT symbol, corr_1y, corr_alltime
        FROM symbol_correlations
        WHERE asset_type='stock' AND benchmark='Gold'
          AND corr_1y > 0.4
        ORDER BY corr_1y DESC LIMIT 10
    """)

    dxy_corr = qdf("""
        SELECT symbol, corr_1y, corr_alltime
        FROM symbol_correlations
        WHERE asset_type='stock' AND benchmark='USD Index'
          AND corr_1y IS NOT NULL
        ORDER BY corr_1y ASC LIMIT 10
    """)

    return {
        "pulse":                    pulse,
        "global_risk":              global_risk,
        "vix":                      r2(vix),
        "spx_5d":                   r2(spx5d),
        "dxy_5d":                   r2(dxy5d),
        "gold_5d":                  r2(gold5d),
        "spx_correlated_stocks":    spx_corr.to_dict("records") if not spx_corr.empty else [],
        "gold_correlated_stocks":   gold_corr.to_dict("records") if not gold_corr.empty else [],
        "dxy_sensitive_stocks":     dxy_corr.to_dict("records") if not dxy_corr.empty else [],
    }


# =========================================================================
# SCREEN 6 — INDEX DEEP STATS
# =========================================================================

def screen_index_deep_stats():
    log(f"Screen 6: Index deep stats ({len(KEY_INDICES)} indices)")
    results = []

    for idx_name in KEY_INDICES:
        ws = qdf("""
            SELECT window_days, n_windows, mean_return, std_return,
                   p5, p25, p75, p95, prob_positive, prob_gt10,
                   prob_lt_neg10, sharpe_ratio, ann_return_equiv
            FROM window_stats
            WHERE symbol=? AND asset_type='index'
            ORDER BY window_days
        """, (idx_name,))

        best = qdb("""
            SELECT start_date, end_date, return_pct FROM window_extremes
            WHERE symbol=? AND asset_type='index'
              AND window_days=20 AND direction='up'
            ORDER BY rank_n LIMIT 3
        """, (idx_name,))

        worst = qdb("""
            SELECT start_date, end_date, return_pct FROM window_extremes
            WHERE symbol=? AND asset_type='index'
              AND window_days=20 AND direction='down'
            ORDER BY rank_n LIMIT 3
        """, (idx_name,))

        regime_rows = qdb("""
            SELECT regime, n_windows, mean_return, std_return,
                   prob_positive, p5, p95
            FROM window_regime_stats
            WHERE symbol=? AND asset_type='index' AND window_days=20
            ORDER BY regime
        """, (idx_name,))

        if ws.empty:
            log(f"  {idx_name}: no window stats — market_snapshot may be short", "WARN")
            continue

        results.append({
            "index_name": idx_name,
            "window_stats": [
                {
                    "window_days":   int(r["window_days"]),
                    "n_windows":     int(r["n_windows"]),
                    "mean_return":   r2(r["mean_return"]),
                    "std_return":    r2(r["std_return"]),
                    "p5":            r2(r["p5"]),
                    "p25":           r2(r["p25"]),
                    "p75":           r2(r["p75"]),
                    "p95":           r2(r["p95"]),
                    "prob_positive": r2(r["prob_positive"] * 100),
                    "prob_gt10":     r2(r.get("prob_gt10", 0) * 100),
                    "prob_lt_neg10": r2(r.get("prob_lt_neg10", 0) * 100),
                    "sharpe":        r4(r.get("sharpe_ratio")),
                    "ann_equiv":     r2(r.get("ann_return_equiv")),
                }
                for _, r in ws.iterrows()
                if r["window_days"] in DISPLAY_WINDOWS
            ],
            "best_20d_rallies": [
                {"start": r[0], "end": r[1], "return_pct": r2(r[2])}
                for r in best
            ],
            "worst_20d_crashes": [
                {"start": r[0], "end": r[1], "return_pct": r2(r[2])}
                for r in worst
            ],
            "regime_breakdown_20d": [
                {
                    "regime":        r[0],
                    "n_windows":     r[1],
                    "mean_return":   r2(r[2]),
                    "std_return":    r2(r[3]),
                    "prob_positive": r2(r[4] * 100) if r[4] else None,
                    "p5":            r2(r[5]),
                    "p95":           r2(r[6]),
                }
                for r in regime_rows
            ],
        })

    log(f"  Built stats for {len(results)} indices")
    return results


# =========================================================================
# LLM SYNTHESIS
# =========================================================================

def synthesise_iota(regime, vix, ret20, s1, s2, s3, s4, s5, s6):
    top5_prob = " | ".join(
        f"{s['symbol']}(prob={s['prob_positive']}%,mean={s['mean_return']}%,p5={s['p5_worst']}%)"
        for s in s1[:5]
    ) if s1 else "N/A"

    top5_gems = " | ".join(
        f"{s['symbol']}(Sharpe={s['sharpe_ratio']},mean={s['mean_return']}%)"
        for s in s2[:5]
    ) if s2 else "N/A"

    top5_prot = " | ".join(
        f"{s['symbol']}(floor={s['p5_floor']}%,mean={s['mean_return']}%)"
        for s in s3[:5]
    ) if s3 else "N/A"

    top5_amp = " | ".join(
        f"{s['symbol']}(bull={s['bull_mean']}%,bear={s['bear_mean']}%)"
        for s in s4.get("amplifiers", [])[:5]
    ) or "N/A"

    top5_def = " | ".join(
        f"{s['symbol']}(bear={s['bear_mean']}%)"
        for s in s4.get("defensives", [])[:5]
    ) or "N/A"

    g = s5
    pulse_str = " | ".join(
        f"{p['symbol']}:{p['ret_5d']:+.1f}%"
        for p in g.get("pulse", []) if p.get("ret_5d") is not None
    )[:300]

    n50 = next((x for x in s6 if x["index_name"] == "Nifty 50"), None)
    n50_20 = next(
        (w for w in (n50 or {}).get("window_stats", []) if w["window_days"] == 20),
        None
    )
    n50_str = (
        f"Nifty50 20d: mean={n50_20['mean_return']}% "
        f"prob+={n50_20['prob_positive']}% "
        f"p5={n50_20['p5']}% Sharpe={n50_20['sharpe']}"
    ) if n50_20 else "Nifty50 index data limited"

    prompt = f"""You are MICC Deep Analysis Agent (Iota). Date: {TODAY_STR}
Nifty 50 regime: {regime.upper()} | VIX={vix} | 20d return={ret20}%

GLOBAL MACRO:
Risk environment: {g.get('global_risk')}
VIX={g.get('vix')} | SPX_5d={g.get('spx_5d')}% | DXY_5d={g.get('dxy_5d')}% | Gold_5d={g.get('gold_5d')}%
5d global pulse: {pulse_str}

INDEX STATS:
{n50_str}

SCREEN 1 — Best probability stocks (20d hold, regime={regime}):
{top5_prob}

SCREEN 2 — High Sharpe gems:
{top5_gems}

SCREEN 3 — Worst-case protected (p5 floor):
{top5_prot}

SCREEN 4 — Regime amplifiers (benefit most from bull market):
{top5_amp}

SCREEN 4 — Regime defensives (hold value in all regimes):
{top5_def}

Write a concise institutional deep analysis brief with these 5 sections:
1. GLOBAL MACRO — what do the global signals mean for Indian equities today?
2. REGIME READ — is this a time to be aggressive, defensive, or selective?
3. HIGH-CONVICTION IDEAS — top 3-5 specific stocks with clear probabilistic rationale
4. PORTFOLIO STRATEGY — given regime + global context, how to position?
5. KEY RISKS — what could invalidate this thesis?
Each section: 3-4 lines max. Institutional tone. No bullet lists."""

    return call_llm(prompt, max_tokens=900, label="Iota", prefer_groq=True)


# =========================================================================
# TELEGRAM FORMAT
# =========================================================================

def format_telegram(report):
    regime      = report.get("current_regime", "?").upper()
    s5          = report.get("screen5_global", {})
    global_risk = s5.get("global_risk", "N/A")
    vix         = s5.get("vix", "N/A")
    spx5d       = s5.get("spx_5d", "N/A")

    s1 = report.get("screen1_best_probability", [])
    s2 = report.get("screen2_risk_adjusted", [])
    s3 = report.get("screen3_worst_case", [])
    s4 = report.get("screen4_regime_movers", {})

    lines = [
        f"*MICC Deep Analysis (Iota)* | {TODAY_STR}",
        f"Regime: *{regime}*  Global: *{global_risk}*  VIX={vix}  SPX5d={spx5d}%",
        "",
        "*Best Probability Stocks (20d):*",
    ]
    for s in s1[:8]:
        lines.append(
            f"  `{s['symbol']:<12}` prob={s['prob_positive']:>5}%  "
            f"mean={s['mean_return']:>+5.1f}%  p5={s['p5_worst']:>+5.1f}%"
        )
    lines += ["", "*High Sharpe Gems:*"]
    for s in s2[:5]:
        lines.append(
            f"  `{s['symbol']:<12}` Sharpe={s['sharpe_ratio']:<5}  "
            f"mean={s['mean_return']:>+5.1f}%"
        )
    lines += ["", "*Worst-Case Protected (floor > -5%):*"]
    for s in s3[:5]:
        lines.append(
            f"  `{s['symbol']:<12}` floor={s['p5_floor']:>+5.1f}%  "
            f"mean={s['mean_return']:>+5.1f}%"
        )

    amps = s4.get("amplifiers", [])
    if amps:
        lines += ["", "*Regime Amplifiers (bull plays):*"]
        for s in amps[:4]:
            lines.append(
                f"  `{s['symbol']:<12}` bull={s['bull_mean']:>+5.1f}%  "
                f"bear={s['bear_mean']:>+5.1f}%"
            )

    analysis = report.get("llm_analysis", "")
    if analysis:
        lines += ["", "*Deep Analysis:*", analysis[:1200]]

    lines.append(f"\n_{now_ist()}_")
    return "\n".join(lines)


# =========================================================================
# MAIN
# =========================================================================

def run_iota(send=False):
    print(f"\n{'='*60}")
    print(f"  MICC Agent Iota — Deep Analysis Room")
    print(f"  {TODAY_STR}")
    print(f"{'='*60}\n")

    regime, vix, ret20 = get_current_regime()

    log("Screen 1: Best probability stocks...")
    s1 = screen_best_probability(regime=regime, window=20, top_n=25)

    log("Screen 2: Risk-adjusted gems...")
    s2 = screen_risk_adjusted_gems(top_n=20)

    log("Screen 3: Worst-case protected...")
    s3 = screen_worst_case_protected(window=20, top_n=20)

    log("Screen 4: Regime sensitivity...")
    s4 = screen_regime_sensitivity(window=20, top_n=15)

    log("Screen 5: Global macro pulse...")
    s5 = screen_global_macro_pulse()

    log("Screen 6: Index deep stats...")
    s6 = screen_index_deep_stats()

    log("LLM synthesis (Groq)...")
    analysis, llm_src = synthesise_iota(regime, vix, ret20, s1, s2, s3, s4, s5, s6)
    log(f"LLM done via {llm_src}", "OK")

    report = {
        "agent":                    "Iota",
        "timestamp":                datetime.now().isoformat(),
        "date":                     TODAY_STR,
        "current_regime":           regime,
        "vix":                      vix,
        "nifty_20d_return":         ret20,
        "screen1_best_probability": s1,
        "screen2_risk_adjusted":    s2,
        "screen3_worst_case":       s3,
        "screen4_regime_movers":    s4,
        "screen5_global":           s5,
        "screen6_index_stats":      s6,
        "llm_analysis":             analysis,
        "llm_source":               llm_src,
    }

    out = OUTPUT_DIR / "last_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    log(f"Report saved -> {out}", "OK")

    # Terminal summary
    print(f"\n{'='*60}")
    print(f"  Regime: {regime.upper()}  VIX={vix}  Nifty20d={ret20}%")
    print(f"  Global: {s5.get('global_risk')}  SPX5d={s5.get('spx_5d')}%")
    print(f"\n  Screen 1 top-5 (probability stocks):")
    for s in s1[:5]:
        print(f"    {s['symbol']:<15} prob={s['prob_positive']:>5}%  "
              f"mean={s['mean_return']:>+6.1f}%  p5={s['p5_worst']:>+6.1f}%")
    print(f"\n  Screen 2 top-5 (Sharpe gems):")
    for s in s2[:5]:
        print(f"    {s['symbol']:<15} Sharpe={s['sharpe_ratio']}  "
              f"mean={s['mean_return']:>+6.1f}%")
    print(f"\n  Screen 3 top-5 (worst-case protected):")
    for s in s3[:5]:
        print(f"    {s['symbol']:<15} floor={s['p5_floor']:>+6.1f}%  "
              f"mean={s['mean_return']:>+6.1f}%")
    print(f"\n  Index stats for: {[x['index_name'] for x in s6]}")
    print(f"\n  LLM ({llm_src}):")
    print(f"  {analysis[:500]}")
    print(f"{'='*60}\n")

    if send:
        log("Sending to Telegram...")
        send_telegram_chunks(format_telegram(report))
        log("Sent", "OK")

    return report


if __name__ == "__main__":
    send = "--send" in sys.argv
    run_iota(send=send)
