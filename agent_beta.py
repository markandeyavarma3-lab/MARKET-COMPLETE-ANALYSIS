import sqlite3
# -*- coding: utf-8 -*-
"""
MICC v2 — Agent Beta: Stock Universe Screener
==============================================
Responsibilities:
  - Screen 2500+ stocks over N-day window from parquet files
  - Screen 1: Momentum (top N-day return with minimum liquidity)
  - Screen 2: Delivery leaders (institutional accumulation signal)
  - Screen 3: Volume breakouts (unusual surge vs historical avg)
  - Screen 4: Consistency score (advancing most days)
  - Screen 5: 52-week high/low proximity (breakout / capitulation)
  - Composite conviction score (appears in multiple screens = higher confidence)
  - Sector rotation summary (which sectors winning/losing)
  - Top losers (momentum fade / short setups)
  - LLM synthesis of all screens → actionable watchlist

Run standalone: py agent_beta.py
Imported by: micc_engine.py
"""

import json
import warnings
from datetime import datetime, date as _date
from pathlib import Path

import numpy as np
import pandas as pd

from micc_data import (
    get_conn, get_trading_dates, load_all_symbols_window,
    get_fundamentals, get_52w_extremes,
    call_llm, fmt_pct, now_ist,
    get_eps_level,
    log_beta_signals, get_signal_streak,
    get_regime_thresholds,
)

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("agents/beta")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Screening thresholds
TOP_N          = 20    # stocks per screen
MIN_DELIV_PCT  = 55.0  # delivery % threshold for accumulation signal
MIN_VOL_SURGE  = 2.0   # vol surge multiple for breakout screen
MIN_PRICE      = 10.0  # filter sub-penny garbage


# ═══════════════════════════════════════════════════════════════════════════════
# SCREENS
# ═══════════════════════════════════════════════════════════════════════════════

def screen_momentum(df: pd.DataFrame, min_pct_chg: float = 0.0) -> pd.DataFrame:
    """Top N stocks by N-day % return. Filter: positive return + min price."""
    sub = df[
        (df["pct_chg"] > min_pct_chg) &
        (df["end_close"] >= MIN_PRICE)
    ].copy()
    return sub.nlargest(TOP_N, "pct_chg").reset_index(drop=True)


def screen_delivery_leaders(df: pd.DataFrame, min_deliv_pct: float = MIN_DELIV_PCT) -> pd.DataFrame:
    """
    Stocks with high delivery % + positive return.
    High delivery = institutional/genuine buying (not speculative).
    """
    if "avg_deliv_pct" not in df.columns or df["avg_deliv_pct"].isna().all():
        return pd.DataFrame()
    sub = df[
        (df["avg_deliv_pct"] >= min_deliv_pct) &
        (df["pct_chg"] > 0) &
        (df["end_close"] >= MIN_PRICE)
    ].copy()
    return sub.nlargest(TOP_N, "avg_deliv_pct").reset_index(drop=True)


def screen_volume_breakouts(df: pd.DataFrame, min_vol_surge: float = MIN_VOL_SURGE) -> pd.DataFrame:
    """
    Volume surge on last day vs average.
    Surge >= 2x + positive price = breakout signal.
    """
    sub = df[
        (df["vol_surge_lastday"] >= min_vol_surge) &
        (df["pct_chg"] > 0) &
        (df["end_close"] >= MIN_PRICE)
    ].copy()
    return sub.nlargest(TOP_N, "vol_surge_lastday").reset_index(drop=True)


def screen_consistency(df: pd.DataFrame, n_days: int, min_adv_offset: int = 0) -> pd.DataFrame:
    """
    Stocks advancing on most days in the window.
    Consistent upward movement = trend strength.
    """
    min_adv = max(2, n_days - 1 + min_adv_offset)  # offset shifts bar up/down per regime
    sub = df[
        (df["adv_days"] >= min_adv) &
        (df["pct_chg"] > 0) &
        (df["end_close"] >= MIN_PRICE)
    ].copy()
    return sub.nlargest(TOP_N, "adv_days").reset_index(drop=True)


def screen_52w_proximity(df: pd.DataFrame) -> dict:
    """
    52-week high/low proximity screener.
    Near-high = momentum continuation candidates.
    Near-low = possible capitulation / value candidates.
    Uses only top symbols (by turnover) to keep it fast.
    """
    # Take top 200 symbols by turnover to avoid 2500-symbol 52w calc
    if "avg_turnover_lacs" in df.columns:
        top_syms = df.nlargest(200, "avg_turnover_lacs")["symbol"].tolist()
    else:
        top_syms = df["symbol"].tolist()[:200]

    extremes = get_52w_extremes(top_syms)
    if extremes.empty:
        return {"near_high": [], "near_low": []}

    # Near 52w high: within 3% of high → breakout potential
    near_high = extremes[extremes["pct_from_high"] >= -3.0].nlargest(10, "pct_from_high")
    # Near 52w low: within 5% of low → potential bounce / avoid
    near_low  = extremes[extremes["pct_from_low"] <= 5.0].nsmallest(10, "pct_from_low")

    return {
        "near_high": near_high.to_dict("records"),
        "near_low":  near_low.to_dict("records"),
    }


def compute_composite(momentum: pd.DataFrame, delivery: pd.DataFrame,
                       breakouts: pd.DataFrame, consistency: pd.DataFrame,
                       weights: dict = None) -> pd.DataFrame:
    """
    Multi-screen conviction score.
    Stock appearing in more screens = higher conviction.
    Weights: Momentum=3, Delivery=3, Breakout=2, Consistency=2 (default)
    Pass weights dict to override per regime.
    """
    score_map = {}

    _w = weights or {"Momentum": 3, "Delivery": 3, "Breakout": 2, "Consistency": 2}

    def _add(syms, key, weight):
        for s in syms:
            if s not in score_map:
                score_map[s] = {"symbol": s, "score": 0, "screens": []}
            score_map[s]["score"]   += weight
            score_map[s]["screens"].append(key)

    _add(momentum["symbol"].tolist()    if not momentum.empty    else [], "Momentum",    _w.get("Momentum",    3))
    _add(delivery["symbol"].tolist()    if not delivery.empty    else [], "Delivery",    _w.get("Delivery",    3))
    _add(breakouts["symbol"].tolist()   if not breakouts.empty   else [], "Breakout",    _w.get("Breakout",    2))
    _add(consistency["symbol"].tolist() if not consistency.empty else [], "Consistency", _w.get("Consistency", 2))

    if not score_map:
        return pd.DataFrame()

    comp = pd.DataFrame(score_map.values()).sort_values("score", ascending=False)
    comp["screens"] = comp["screens"].apply(lambda x: "+".join(sorted(set(x))))
    return comp.head(TOP_N).reset_index(drop=True)


def compute_sector_rotation(df: pd.DataFrame, fund_df: pd.DataFrame) -> dict:
    """
    Sector rotation from fundamentals data.
    Shows which sectors are outperforming/underperforming in this window.
    """
    if fund_df.empty or "sector" not in fund_df.columns:
        return {}

    merged = df.merge(fund_df[["symbol", "sector"]], on="symbol", how="left")
    merged = merged.dropna(subset=["sector"])

    if merged.empty:
        return {}

    sector_grp = merged.groupby("sector")["pct_chg"].agg(["mean", "count"]).reset_index()
    sector_grp.columns = ["sector", "avg_pct", "stock_count"]
    sector_grp = sector_grp[sector_grp["stock_count"] >= 3]  # need at least 3 stocks
    sector_grp = sector_grp.sort_values("avg_pct", ascending=False)

    top_sectors  = sector_grp.head(5).to_dict("records")
    bot_sectors  = sector_grp.tail(3).to_dict("records")

    return {
        "top_sectors":    top_sectors,
        "bottom_sectors": bot_sectors,
        "all_sectors":    sector_grp.to_dict("records"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LLM SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════════

def synthesise_beta_llm(momentum: pd.DataFrame, delivery: pd.DataFrame,
                         breakouts: pd.DataFrame, composite: pd.DataFrame,
                         sector_data: dict, w52: dict, n_days: int,
                         earnings_data: dict = None) -> str:
    """
    Comprehensive stock screener synthesis via LLM.
    Groq preferred (Llama 70B gives better stock analysis than gemma3:4b).
    """
    earnings_data = earnings_data or {}
    def _fmt_stocks(df, cols=("symbol", "pct_chg", "avg_deliv_pct"), n=8) -> str:
        if df.empty:
            return "None"
        rows = []
        for _, r in df.head(n).iterrows():
            parts = [str(r.get("symbol", "?"))]
            if "pct_chg" in r:
                parts.append(f"{float(r['pct_chg'] or 0):+.1f}%")
            if "avg_deliv_pct" in r and pd.notna(r.get("avg_deliv_pct")):
                parts.append(f"D:{r['avg_deliv_pct']:.0f}%")
            if "score" in r:
                parts.append(f"sc:{r['score']}")
            rows.append(" ".join(parts))
        return " | ".join(rows)

    sector_top = " | ".join(
        f"{s['sector']}({s['avg_pct']:+.1f}%)"
        for s in sector_data.get("top_sectors", [])[:5]
    )
    sector_bot = " | ".join(
        f"{s['sector']}({s['avg_pct']:+.1f}%)"
        for s in sector_data.get("bottom_sectors", [])[:3]
    )

    near_high_str = " | ".join(
        f"{s['symbol']}({s['pct_from_high']:+.1f}% from 52w high)"
        for s in w52.get("near_high", [])[:5]
    )
    near_low_str = " | ".join(
        f"{s['symbol']}({s['pct_from_low']:+.1f}% from 52w low)"
        for s in w52.get("near_low", [])[:5]
    )

    comp_str = _fmt_stocks(composite, n=10) if not composite.empty else "None"

    prompt = (
        f"You are an elite NSE quantitative analyst. Write a detailed {n_days}-day stock screener synthesis report.\n\n"
        f"Structure EXACTLY as:\n\n"
        f"## Stock Universe Intelligence — {n_days} Days\n\n"
        f"**Part A: Momentum Leaders**\n"
        f"[3-4 sentences: analyse the top momentum stocks. Are gains sustainable? "
        f"Which have strong delivery backing? Flag any that look speculative vs genuine.]\n\n"
        f"**Part B: Institutional Accumulation Signals**\n"
        f"[3-4 sentences: focus on high-delivery stocks. These have genuine buying. "
        f"Which are worth adding to watchlist? Any sector clustering?]\n\n"
        f"**Part C: Volume Breakouts**\n"
        f"[2-3 sentences: assess breakout quality. Are volume surges confirmed by price action? "
        f"Any false breakouts to watch out for?]\n\n"
        f"**Part D: Sector Rotation Intelligence**\n"
        f"[3-4 sentences: which sectors are leading? Which are losing? "
        f"Is the rotation risk-on or risk-off? Where is smart money moving?]\n\n"
        f"**Part E: 52-Week Signals**\n"
        f"[2-3 sentences: near-high stocks as breakout candidates, near-low stocks as either "
        f"value traps or bounce candidates.]\n\n"
        f"**Part F: Composite Conviction Watchlist**\n"
        f"[Top 5 picks with one sentence rationale each. These appeared in multiple screens — "
        f"highest conviction. Include entry thesis and key risk.]\n\n"
        f"SCREENER DATA:\n"
        f"Momentum: {_fmt_stocks(momentum)}\n"
        f"Delivery leaders: {_fmt_stocks(delivery)}\n"
        f"Vol breakouts: {_fmt_stocks(breakouts)}\n"
        f"Composite (multi-screen): {comp_str}\n"
        f"Earnings acceleration (stocks with accelerating Q-o-Q revenue growth): "
        f"{', '.join([s for s, d in earnings_data.items() if d.get('accel')][:8]) or 'None identified'}\n"
        f"Top sectors: {sector_top or 'N/A'}\n"
        f"Weak sectors: {sector_bot or 'N/A'}\n"
        f"Near 52w highs: {near_high_str or 'None'}\n"
        f"Near 52w lows: {near_low_str or 'None'}"
    )

    text, source = call_llm(prompt, max_tokens=1400, label="Beta-Synthesis", prefer_groq=True)
    print(f"[Beta] Synthesis done via {source}")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AGENT
# ═══════════════════════════════════════════════════════════════════════════════

def run_beta(dates: list, regime: str = "") -> dict:
    """
    Full Beta agent run for N-day window.
    Returns all 5 screens + composite + sector rotation + LLM synthesis.
    """
    print(f"[Beta] Screening stocks over {len(dates)} days...")
    n_days = len(dates)
    start_d, end_d = dates[0], dates[-1]

    # ── 0. Load regime-conditioned thresholds ──────────────────────────────
    _thresh = get_regime_thresholds(regime)
    print(f"[Beta] Regime: {regime or 'DEFAULT'} → thresholds: "
          f"deliv>={_thresh['min_deliv_pct']}% | "
          f"vol_surge>={_thresh['min_vol_surge']}x | "
          f"pct_chg>={_thresh['min_pct_chg']}% | "
          f"tag={_thresh['regime_tag']}")

    # ── 1. Load all symbols ───────────────────────────────────────────────────
    print("[Beta] Loading parquet files (30-60s)...")
    df = load_all_symbols_window(dates)

    if df.empty:
        return {"agent": "Beta", "error": "No stock data found for window"}

    total_symbols = len(df)
    print(f"[Beta] {total_symbols} symbols loaded")

    # ── 2. Run all 5 screens ──────────────────────────────────────────────────
    print("[Beta] Running momentum screen...")
    momentum = screen_momentum(df, min_pct_chg=_thresh["min_pct_chg"])

    print("[Beta] Running delivery leaders screen...")
    delivery = screen_delivery_leaders(df, min_deliv_pct=_thresh["min_deliv_pct"])

    print("[Beta] Running volume breakouts screen...")
    breakouts = screen_volume_breakouts(df, min_vol_surge=_thresh["min_vol_surge"])

    print("[Beta] Running consistency screen...")
    consistency = screen_consistency(df, n_days, min_adv_offset=_thresh["min_adv_offset"])

    print("[Beta] Running 52-week proximity screen...")
    w52 = screen_52w_proximity(df)

    # ── 3. Composite score ────────────────────────────────────────────────────
    print("[Beta] Computing composite conviction scores...")
    composite = compute_composite(momentum, delivery, breakouts, consistency, weights=_thresh["composite_weights"])

    # ── 4. Enrich composite with price data + fundamentals ────────────────────
    if not composite.empty:
        composite = composite.merge(
            df[["symbol", "pct_chg", "end_close", "avg_deliv_pct",
                "avg_turnover_lacs", "vol_surge_lastday"]],
            on="symbol", how="left"
        )
        top_syms = composite["symbol"].tolist()
        fund_df  = get_fundamentals(top_syms)
        if not fund_df.empty:
            composite = composite.merge(fund_df, on="symbol", how="left")
    else:
        fund_df = pd.DataFrame()

    # ── 4b. EPS level boost (Patch 2.2b) ────────────────────────────────────
    # Inlined directly — get_eps_level() has a Python 3.14 finally/conn issue.
    # Logic proven working in debug_eps_level.py.
    earnings_data = {}
    if not composite.empty:
        top_syms_ea = composite["symbol"].tolist()
        print(f"[Beta] Fetching EPS level for {len(top_syms_ea)} composite stocks...")
        try:
            _db_path = "D:/marketDB/db/market.db"
            _conn = sqlite3.connect(_db_path)
            _placeholders = ",".join("?" * len(top_syms_ea))
            _rows = _conn.execute(
                "SELECT symbol, report_date, data_json "
                "FROM quarterly_income "
                "WHERE symbol IN ({}) "
                "ORDER BY symbol, report_date DESC".format(_placeholders),
                [s.upper() for s in top_syms_ea],
            ).fetchall()
            _conn.close()

            _seen = set()
            eps_data = {}
            for _sym, _rdate, _djson in _rows:
                _sym = str(_sym).upper()
                if _sym in _seen:
                    continue
                _seen.add(_sym)
                _data = {}
                if isinstance(_djson, str):
                    try:
                        _data = json.loads(_djson)
                    except Exception:
                        _safe = (_djson
                                 .replace(": NaN", ": null")
                                 .replace(":NaN", ":null")
                                 .replace(": Infinity", ": null")
                                 .replace(":-Infinity", ":null")
                                 .replace(": -Infinity", ":null"))
                        try:
                            _data = json.loads(_safe)
                        except Exception:
                            _data = {}
                elif isinstance(_djson, dict):
                    _data = _djson

                _eps = None
                for _key in ("Diluted EPS", "Basic EPS"):
                    _val = _data.get(_key)
                    if _val is not None:
                        try:
                            _f = float(_val)
                            if _f == _f:
                                _eps = _f
                                break
                        except (ValueError, TypeError):
                            pass
                if _eps is None:
                    for _key in (
                        "Net Income From Continuing Operation Net Minority Interest",
                        "Normalized Income",
                        "Net Income From Continuing And Discontinued Operation",
                    ):
                        _val = _data.get(_key)
                        if _val is not None:
                            try:
                                _f = float(_val)
                                if _f == _f:
                                    _eps = _f
                                    break
                            except (ValueError, TypeError):
                                pass
                eps_data[_sym] = {
                    "eps": round(_eps, 2) if _eps is not None else None,
                    "profitable": bool(_eps is not None and _eps > 0),
                }

            earnings_data = eps_data
            profitable = [s for s, d in eps_data.items() if d.get("profitable")]
            loss_making = [s for s, d in eps_data.items()
                           if d.get("eps") is not None and not d.get("profitable")]

            if profitable:
                composite.loc[composite["symbol"].isin(profitable), "score"] += 1
            if loss_making:
                composite.loc[composite["symbol"].isin(loss_making), "score"] -= 1

            def _eps_flag(s):
                d = eps_data.get(s, {})
                if d.get("profitable"):
                    return "PROFITABLE"
                if d.get("eps") is not None and not d.get("profitable"):
                    return "LOSS_MAKING"
                return ""

            composite["earnings_flag"] = composite["symbol"].map(_eps_flag)
            composite = composite.sort_values("score", ascending=False).reset_index(drop=True)
            print(f"[Beta] EPS boost: {len(profitable)} profitable, {len(loss_making)} loss-making")
        except Exception as _e:
            print(f"[Beta] EPS level fetch failed: {_e} — continuing")
            earnings_data = {}

    # ── 4c. Streak boost + logging (Phase 2.5) ───────────────────────────────
    if not composite.empty:
        _run_date = _date.today().isoformat()

        # Get regime from micc_engine context (passed in) or default empty
        _regime = regime  # passed from engine via run_beta(dates, regime=...)

        # --- Streak calculation (raw sqlite3, Python 3.14 safe) ---
        _streak_map = {}
        try:
            _streak_map = get_signal_streak(composite["symbol"].tolist())
        except Exception as _se:
            print(f"[Beta] Streak fetch failed: {_se} — skipping")

        if _streak_map:
            # Apply +1 score boost for streak >= 3
            def _streak_boost(sym):
                return 1 if _streak_map.get(sym, 0) >= 3 else 0

            composite["streak"] = composite["symbol"].map(
                lambda s: _streak_map.get(s, 0)
            )
            boost_syms = composite[composite["streak"] >= 3]["symbol"].tolist()
            if boost_syms:
                composite.loc[composite["symbol"].isin(boost_syms), "score"] += 1
                # Add streak_N tag to screens column
                def _tag_streak(row):
                    base = row["screens"] if row["screens"] else ""
                    if row.get("streak", 0) >= 3:
                        tag = f"streak_{int(row['streak'])}"
                        return f"{base}+{tag}" if base else tag
                    return base
                composite["screens"] = composite.apply(_tag_streak, axis=1)
                composite = composite.sort_values("score", ascending=False).reset_index(drop=True)
                print(f"[Beta] Streak boost applied to: {boost_syms[:5]}")
            else:
                composite["streak"] = composite["symbol"].map(
                    lambda s: _streak_map.get(s, 0)
                )
        else:
            composite["streak"] = 0

        # --- Log to signals_history ---
        try:
            log_beta_signals(composite, _run_date, _regime)
        except Exception as _le:
            print(f"[Beta] log_beta_signals failed: {_le} — continuing")

    # ── 5. Sector rotation ────────────────────────────────────────────────────
    print("[Beta] Computing sector rotation...")
    if fund_df.empty:
        fund_df = get_fundamentals(df.nlargest(500, "avg_turnover_lacs")["symbol"].tolist()
                                   if "avg_turnover_lacs" in df.columns else df["symbol"].tolist()[:500])
    sector_data = compute_sector_rotation(df, fund_df)

    # ── 6. Top losers ─────────────────────────────────────────────────────────
    top_losers = df[df["end_close"] >= MIN_PRICE].nsmallest(15, "pct_chg")

    # ── 7. LLM synthesis ──────────────────────────────────────────────────────
    print("[Beta] Running LLM synthesis...")
    synthesis = synthesise_beta_llm(
        momentum, delivery, breakouts, composite, sector_data, w52, n_days,
        earnings_data
    )

    return {
        "agent":           "Beta",
        "timestamp":       datetime.now().isoformat(),
        "start_date":      start_d,
        "end_date":        end_d,
        "n_days":          n_days,
        "total_symbols":   total_symbols,
        "screens": {
            "momentum":    momentum.to_dict("records"),
            "delivery":    delivery.to_dict("records") if not delivery.empty else [],
            "breakouts":   breakouts.to_dict("records"),
            "consistency": consistency.to_dict("records"),
            "composite":   composite.to_dict("records") if not composite.empty else [],
            "top_losers":  top_losers.to_dict("records"),
        },
        "w52":               w52,
        "sector_rotation":   sector_data,
        "earnings_accel":    {s: d for s, d in earnings_data.items() if d.get("profitable")},
        "synthesis":         synthesis,
    }


# ── Standalone run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    dates = get_trading_dates(n)
    print(f"[Beta] Window: {dates[0]} → {dates[-1]} ({len(dates)} days)")

    result = run_beta(dates)

    out = OUTPUT_DIR / "last_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[Beta] Report saved → {out}")

    sc = result.get("screens", {})
    print(f"\n{'='*60}")
    print(f"  Symbols screened: {result.get('total_symbols')}")
    print(f"\n  TOP MOMENTUM:")
    for r in sc.get("momentum", [])[:5]:
        print(f"    {r['symbol']:<14} {r['pct_chg']:>+7.2f}%  deliv:{r.get('avg_deliv_pct','N/A')}%")
    print(f"\n  COMPOSITE (multi-screen):")
    for r in sc.get("composite", [])[:5]:
        print(f"    {r['symbol']:<14} score:{r['score']}  [{r['screens']}]  {r.get('pct_chg',0):>+7.2f}%")
    sec = result.get("sector_rotation", {})
    if sec.get("top_sectors"):
        print(f"\n  TOP SECTORS:")
        for s in sec["top_sectors"][:5]:
            print(f"    {s['sector']:<30} {s['avg_pct']:>+7.2f}%")
    print(f"{'='*60}")
    print(f"\n[Beta] SYNTHESIS:\n{result.get('synthesis', 'N/A')[:500]}...")
