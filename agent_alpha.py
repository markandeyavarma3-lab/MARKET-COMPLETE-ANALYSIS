# -*- coding: utf-8 -*-
"""
MICC v2 — Agent Alpha: Macro Intelligence
==========================================
Responsibilities:
  - Nifty 50 regime classification (TRENDING_UP / DOWN / CONSOLIDATION / etc.)
  - All 146 indices performance over N-day window (ranked)
  - Cap rotation signals (large/mid/small)
  - Breadth analytics (advancing/declining ratio per day)
  - Index drill-down: for top 7 movers, fetch ALL constituent stocks + their changes
  - Global cues fetch (SGX Nifty, Dow, Nasdaq via web)
  - Per-index LLM analysis using Groq (preferred for speed)

Run standalone: py agent_alpha.py
Imported by: micc_engine.py
"""

import json
import re
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from micc_data import (
    get_conn, get_trading_dates, get_all_indices_for_dates,
    get_nifty50_history, get_index_constituents, get_index_stock_performance,
    get_fundamentals, clean_index_name,
    call_llm, fetch_sector_news,
    fmt_pct, now_ist,
    get_global_context,
)

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("agents/alpha")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# How many top/bottom indices to pick for deep drill-down reports
TOP_INDICES_FOR_DRILL = 7

# Major indices always included in drill-down regardless of rank
ALWAYS_INCLUDE_INDICES = ["Nifty 50", "Nifty Bank"]

# Indices to skip for drill-down — inverse, leverage, bond, VIX, USD
# These are not actionable for regime/sector analysis
SKIP_INDICES = {
    # VIX and currency
    "India VIX", "INDIA VIX", "Nifty50 USD",
}

# Patterns to skip (checked with str.lower() substring match)
SKIP_INDEX_PATTERNS = (
    "inverse",      # Nifty50 PR 1x Inverse, Nifty50 TR 1x Inverse
    "leverage",     # Nifty50 TR 2x Leverage, Nifty50 PR 2x Leverage
    "1x inverse",   # explicit
    "2x leverage",  # explicit
    "g-sec",        # bond indices — not equity
    "bharat bond",  # bond ETF indices
    "1d rate",      # overnight rate index
    "arbitrage",    # Nifty 50 Arbitrage — not directional
    "futures index",# Nifty 50 Futures Index
    "futures tr",   # Nifty 50 Futures TR Index
    "dividend points", # Nifty50 Dividend Points — not price
    "shariah",      # religious filter indices — not mainstream
)


# ═══════════════════════════════════════════════════════════════════════════════
# REGIME COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_nifty_regime(nifty_hist: pd.DataFrame, window_closes: list) -> dict:
    """
    Compute Nifty 50 regime metrics from both long-term history (60d) and
    the N-day window being analysed.
    """
    if nifty_hist.empty or len(nifty_hist) < 5:
        return {}

    closes = nifty_hist["close"].astype(float)
    latest = float(closes.iloc[-1])

    # Returns
    ret_1d  = ((closes.iloc[-1] / closes.iloc[-2])  - 1) * 100 if len(closes) >= 2  else None
    ret_5d  = ((closes.iloc[-1] / closes.iloc[-6])  - 1) * 100 if len(closes) >= 6  else None
    ret_20d = ((closes.iloc[-1] / closes.iloc[-21]) - 1) * 100 if len(closes) >= 21 else None

    ma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else None
    ma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None

    # Annualised volatility (20d)
    vol_ann = None
    if len(closes) >= 20:
        daily_rets = closes.pct_change().dropna().tail(19)
        vol_ann = float(daily_rets.std() * (252 ** 0.5) * 100)

    # N-day window performance
    win_pct = None
    if len(window_closes) >= 2:
        wc = [v for v in window_closes if v]
        if wc:
            win_pct = ((wc[-1] / wc[0]) - 1) * 100

    # Window volatility
    win_vol = None
    if len(window_closes) > 1:
        wc = pd.Series([v for v in window_closes if v], dtype=float)
        if len(wc) > 1:
            win_vol = float(wc.pct_change().dropna().std() * (252 ** 0.5) * 100)

    # PE/PB
    latest_pe = float(nifty_hist["pe"].iloc[-1]) if "pe" in nifty_hist.columns and pd.notna(nifty_hist["pe"].iloc[-1]) else None
    avg_pe_20 = float(nifty_hist["pe"].tail(20).mean()) if "pe" in nifty_hist.columns else None
    latest_pb = float(nifty_hist["pb"].iloc[-1]) if "pb" in nifty_hist.columns and pd.notna(nifty_hist["pb"].iloc[-1]) else None

    # Volume ratio
    vol_ratio = None
    if "volume" in nifty_hist.columns and len(nifty_hist) >= 20:
        v5  = nifty_hist["volume"].tail(5).mean()
        v20 = nifty_hist["volume"].tail(20).mean()
        vol_ratio = round(float(v5 / v20), 3) if v20 else None

    # Regime classification
    v = vol_ann or 0
    r20 = ret_20d or 0
    abv_ma20 = bool(latest > ma20) if ma20 else None
    abv_ma50 = bool(latest > ma50) if ma50 else None

    if v > 28:
        regime = "HIGH_VOLATILITY"
    elif r20 > 3 and abv_ma20 and abv_ma50:
        regime = "TRENDING_UP"
    elif r20 < -3 and not (abv_ma20 or abv_ma50):
        regime = "TRENDING_DOWN"
    elif abs(r20) < 1.5:
        regime = "CONSOLIDATION"
    else:
        regime = "MEAN_REVERTING"

    confidence = "HIGH" if (v > 30 or abs(r20) > 5) else "MEDIUM" if abs(r20) > 2 else "LOW"

    def _f(v):
        return round(float(v), 2) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None

    return {
        "latest_close":       _f(latest),
        "return_1d_pct":      _f(ret_1d),
        "return_5d_pct":      _f(ret_5d),
        "return_20d_pct":     _f(ret_20d),
        "window_pct":         _f(win_pct),
        "window_vol_ann_pct": _f(win_vol),
        "ma20":               _f(ma20),
        "ma50":               _f(ma50),
        "above_ma20":         abv_ma20,
        "above_ma50":         abv_ma50,
        "vol_ann_pct":        _f(vol_ann),
        "pe":                 _f(latest_pe),
        "avg_pe_20d":         _f(avg_pe_20),
        "pb":                 _f(latest_pb),
        "volume_ratio":       vol_ratio,
        "regime":             regime,
        "confidence":         confidence,
    }


def compute_breadth(snap_df: pd.DataFrame, dates: list) -> dict:
    """Per-day breadth: advancing/declining/unchanged across all indices."""
    breadth_by_day = []
    for d in dates:
        day = snap_df[snap_df["date"] == d]
        if day.empty:
            continue
        adv = int((day["daily_change"] > 0).sum())
        dec = int((day["daily_change"] < 0).sum())
        unc = int((day["daily_change"] == 0).sum())
        tot = len(day)
        breadth_by_day.append({
            "date":      d,
            "advancing": adv,
            "declining": dec,
            "unchanged": unc,
            "total":     tot,
            "pct_adv":   round(adv / tot * 100, 1) if tot > 0 else 0,
            "ad_ratio":  round(adv / dec, 2) if dec > 0 else None,
        })

    avg_adv = (
        sum(b["pct_adv"] for b in breadth_by_day) / len(breadth_by_day)
        if breadth_by_day else 0
    )
    return {
        "by_day":      breadth_by_day,
        "avg_pct_adv": round(avg_adv, 1),
        "total_days":  len(breadth_by_day),
    }


def compute_cap_rotation(snap_df: pd.DataFrame, dates: list) -> dict:
    """
    Cap rotation: large vs mid vs small performance.
    Uses start-to-end % change over the full window.
    """
    idx_df = _build_index_perf(snap_df, dates)
    if idx_df.empty:
        return {}

    cap_map = {
        "largecap": ["Nifty 50", "Nifty 100", "Nifty Next 50", "Nifty Large Midcap 250"],
        "midcap":   ["Nifty Midcap 50", "Nifty Midcap 100", "Nifty Midcap 150", "Nifty Midcap Select"],
        "smallcap": ["Nifty Smallcap 50", "Nifty Smallcap 100", "Nifty Smallcap 250"],
    }

    rotation = {}
    for cap, names in cap_map.items():
        sub = idx_df[idx_df["index"].isin(names)]["pct_change"]
        if not sub.empty:
            rotation[f"{cap}_avg_pct"] = round(float(sub.mean()), 2)

    lc = rotation.get("largecap_avg_pct")
    sc = rotation.get("smallcap_avg_pct")
    if lc is not None and sc is not None:
        diff = sc - lc
        if diff > 1.5:
            signal = "RISK_ON — Smallcap outperforming Largecap"
        elif diff < -1.5:
            signal = "RISK_OFF — Largecap leading, defensive posture"
        else:
            signal = "NEUTRAL — Cap rotation balanced"
    else:
        signal = "N/A"

    rotation["signal"] = signal
    return rotation


def _build_index_perf(snap_df: pd.DataFrame, dates: list) -> pd.DataFrame:
    """Compute start-to-end % change for each index over window."""
    rows = []
    for idx_name, grp in snap_df.groupby("index_name"):
        if not idx_name or idx_name in SKIP_INDICES:
            continue
        if any(pat in idx_name.lower() for pat in SKIP_INDEX_PATTERNS):
            continue
        grp = grp.sort_values("date")
        if len(grp) < 2:
            continue
        start_close = float(grp.iloc[0]["close"]) if pd.notna(grp.iloc[0]["close"]) else None
        end_close   = float(grp.iloc[-1]["close"]) if pd.notna(grp.iloc[-1]["close"]) else None
        if not start_close or not end_close or start_close <= 0:
            continue
        pct_chg  = ((end_close / start_close) - 1) * 100
        adv_days = int((grp["daily_change"] > 0).sum())
        avg_pe   = float(grp["pe"].mean()) if grp["pe"].notna().any() else None
        rows.append({
            "index":       idx_name,
            "start_close": round(start_close, 2),
            "end_close":   round(end_close, 2),
            "pct_change":  round(pct_chg, 2),
            "adv_days":    adv_days,
            "total_days":  len(grp),
            "avg_pe":      round(avg_pe, 2) if avg_pe else None,
        })

    return pd.DataFrame(rows).sort_values("pct_change", ascending=False).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX DRILL-DOWN — top 7 indices with full stock breakdown
# ═══════════════════════════════════════════════════════════════════════════════

def build_index_drilldown(idx_df: pd.DataFrame, dates: list) -> list:
    """
    Pick top 7 indices by absolute % change (gainers and losers both matter).
    For each, fetch ALL constituent stocks and their N-day performance.
    Returns list of index report dicts.
    """
    if idx_df.empty:
        return []

    # Exclude unwanted
    def _should_skip(name: str) -> bool:
        if name in SKIP_INDICES:
            return True
        nl = name.lower()
        return any(pat in nl for pat in SKIP_INDEX_PATTERNS)

    filtered = idx_df[~idx_df["index"].apply(_should_skip)].copy()

    # Always include key indices
    always = filtered[filtered["index"].isin(ALWAYS_INCLUDE_INDICES)]
    rest   = filtered[~filtered["index"].isin(ALWAYS_INCLUDE_INDICES)]

    # Top movers by absolute change (mix of top gainers + top losers)
    top_gainers = rest.nlargest(4, "pct_change")
    top_losers  = rest.nsmallest(2, "pct_change")

    selected = pd.concat([always, top_gainers, top_losers]).drop_duplicates(subset=["index"])
    selected = selected.head(TOP_INDICES_FOR_DRILL)

    drill_reports = []
    for _, row in selected.iterrows():
        idx_name = row["index"]
        print(f"[Alpha] Drilling into {idx_name}...")

        stock_df = get_index_stock_performance(idx_name, dates)
        constituents_count = len(stock_df)

        # Enrich with fundamentals
        if not stock_df.empty:
            fund_df = get_fundamentals(stock_df["symbol"].tolist())
            if not fund_df.empty:
                stock_df = stock_df.merge(fund_df, on="symbol", how="left")

        # Top gainers / losers within this index
        top_stocks   = stock_df.nlargest(10, "pct_chg").to_dict("records") if not stock_df.empty else []
        worst_stocks = stock_df.nsmallest(5, "pct_chg").to_dict("records") if not stock_df.empty else []

        # High delivery conviction stocks in this index
        if not stock_df.empty and "avg_deliv_pct" in stock_df.columns:
            conviction = stock_df[
                (stock_df["avg_deliv_pct"] >= 60) & (stock_df["pct_chg"] > 0)
            ].nlargest(5, "avg_deliv_pct").to_dict("records")
        else:
            conviction = []

        drill_reports.append({
            "index_name":          idx_name,
            "index_pct_change":    row["pct_change"],
            "index_start":         row["start_close"],
            "index_end":           row["end_close"],
            "adv_days":            row["adv_days"],
            "total_days":          row["total_days"],
            "avg_pe":              row["avg_pe"],
            "constituents_count":  constituents_count,
            "all_stocks":          stock_df.to_dict("records") if not stock_df.empty else [],
            "top_gainers":         top_stocks,
            "worst_performers":    worst_stocks,
            "conviction_buys":     conviction,
        })

    return drill_reports


# ═══════════════════════════════════════════════════════════════════════════════
# LLM ANALYSIS — regime + per-index
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_regime_llm(regime: dict, breadth: dict, rotation: dict,
                        top3: list, bot3: list, n_days: int,
                        global_ctx: dict = None) -> str:
    """Overall market regime analysis — uses Ollama (local, fast enough)."""
    global_ctx = global_ctx or {}
    top_str = " | ".join(f"{r['index']}({r['pct_change']:+.1f}%)" for r in top3[:3])
    bot_str = " | ".join(f"{r['index']}({r['pct_change']:+.1f}%)" for r in bot3[:3])

    prompt = (
        f"You are a senior NSE market analyst. Write a comprehensive {n_days}-day market regime report.\n"
        f"Structure your response as:\n"
        f"REGIME: <label> | CONFIDENCE: <H/M/L>\n\n"
        f"## Global Context\n"
        f"[1-2 sentences: how are global cues (DXY, crude, gold, US markets) impacting India? "
        f"Is the global environment a headwind or tailwind for FII flows?]\n\n"
        f"## Market Regime Analysis\n"
        f"[2-3 sentences on overall market direction and key drivers]\n\n"
        f"## Breadth & Participation\n"
        f"[1-2 sentences on market breadth quality]\n\n"
        f"## Valuation Assessment\n"
        f"[1-2 sentences: CHEAP/FAIR/EXPENSIVE/STRETCHED with reasoning]\n\n"
        f"## Capital Rotation\n"
        f"[1-2 sentences on large/mid/small cap dynamics]\n\n"
        f"## Outlook & Risk\n"
        f"[2-3 sentences: key opportunities and risks for next 5-10 days]\n\n"
        f"DATA:\n"
        f"Nifty 50: close={regime.get('latest_close')} window_return={regime.get('window_pct',0):+.2f}% "
        f"vol={regime.get('vol_ann_pct')}% MA20={'above' if regime.get('above_ma20') else 'below'} "
        f"MA50={'above' if regime.get('above_ma50') else 'below'} PE={regime.get('pe')} PB={regime.get('pb')} "
        f"vol_ratio={regime.get('volume_ratio')}\n"
        f"Breadth: avg {breadth.get('avg_pct_adv')}% advancing over {n_days} days\n"
        f"Rotation: {rotation.get('signal')} | LC={rotation.get('largecap_avg_pct',0):+.1f}% "
        f"MC={rotation.get('midcap_avg_pct',0):+.1f}% SC={rotation.get('smallcap_avg_pct',0):+.1f}%\n"
        f"Top indices: {top_str}\n"
        f"Worst: {bot_str}\n"
        f"GLOBAL MACRO ({n_days}d): {global_ctx.get('summary', 'N/A')}\n"
        f"DXY: {global_ctx.get('tickers', {}).get('DXY', {}).get('pct_chg', 'N/A')}% | "
        f"Crude: {global_ctx.get('tickers', {}).get('Crude Oil', {}).get('pct_chg', 'N/A')}% | "
        f"Gold: {global_ctx.get('tickers', {}).get('Gold', {}).get('pct_chg', 'N/A')}% | "
        f"S&P500: {global_ctx.get('tickers', {}).get('S&P 500', {}).get('pct_chg', 'N/A')}% | "
        f"USD/INR: {global_ctx.get('tickers', {}).get('USD/INR', {}).get('pct_chg', 'N/A')}%"
    )

    text, source = call_llm(prompt, max_tokens=900, label="Regime", prefer_groq=False)
    return text


def analyse_index_llm(index_report: dict, news: list, n_days: int) -> str:
    """
    Deep per-index analysis — uses Groq (free, fast, high quality Llama 70B).
    This is the most detailed LLM call — covers stocks, flow, news, outlook.
    """
    idx  = index_report["index_name"]
    pct  = index_report["index_pct_change"]
    pe   = index_report.get("avg_pe", "N/A")
    adv  = index_report["adv_days"]
    tot  = index_report["total_days"]

    top_stocks = index_report.get("top_gainers", [])[:8]
    worst      = index_report.get("worst_performers", [])[:5]
    conviction = index_report.get("conviction_buys", [])[:5]

    top_str = " | ".join(
        f"{s['symbol']}({s.get('pct_chg', 0):+.1f}%,deliv={s.get('avg_deliv_pct','?')}%)"
        for s in top_stocks
    )
    worst_str = " | ".join(
        f"{s['symbol']}({s.get('pct_chg', 0):+.1f}%)"
        for s in worst
    )
    conv_str = " | ".join(
        f"{s['symbol']}(deliv={s.get('avg_deliv_pct','?')}%,{s.get('pct_chg',0):+.1f}%)"
        for s in conviction
    )

    news_str = "\n".join(f"  • {n['title'][:100]}" for n in news[:6]) if news else "  No recent news fetched."

    prompt = (
        f"You are an elite NSE sector analyst. Write a detailed {n_days}-day in-depth report on the {idx} index.\n\n"
        f"Structure your response EXACTLY as follows:\n\n"
        f"### {idx} — {n_days}-Day Deep Dive\n\n"
        f"**1. Performance Summary**\n"
        f"[3-4 sentences: how the index moved, key inflection points, was movement broad or narrow?]\n\n"
        f"**2. Stock-Level Analysis**\n"
        f"[4-5 sentences: analyse the top gainers and laggards. What drove the outperformers? "
        f"Are the high-delivery stocks showing genuine accumulation? Identify any divergences.]\n\n"
        f"**3. Sector Themes & Catalysts**\n"
        f"[3-4 sentences: what macro/policy/earnings themes are driving this sector? "
        f"Reference the news headlines if relevant.]\n\n"
        f"**4. Institutional Positioning Signal**\n"
        f"[2-3 sentences: based on delivery %, vol patterns — are institutions buying or distributing?]\n\n"
        f"**5. Outlook & Actionable Intelligence**\n"
        f"[3-4 sentences: support/resistance levels, key stocks to watch, risk factors specific to this sector, "
        f"and a clear BULLISH/BEARISH/NEUTRAL verdict with reasoning.]\n\n"
        f"INDEX DATA:\n"
        f"Index: {idx} | {n_days}d change: {pct:+.2f}% | Avg PE: {pe} | "
        f"Advancing: {adv}/{tot} days\n"
        f"Top gainers: {top_str or 'N/A'}\n"
        f"Worst performers: {worst_str or 'N/A'}\n"
        f"High-conviction delivery buys: {conv_str or 'None identified'}\n\n"
        f"RECENT NEWS:\n{news_str}"
    )

    # Use Groq for index reports (faster, better quality for long-form)
    text, source = call_llm(prompt, max_tokens=1200, label=idx, prefer_groq=True)
    print(f"[Alpha] {idx} analysis done via {source}")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AGENT
# ═══════════════════════════════════════════════════════════════════════════════

def run_alpha(dates: list) -> dict:
    """
    Full Alpha agent run for N-day window.
    Returns comprehensive dict with regime, all indices, and 7 deep index reports.
    """
    print(f"[Alpha] Analysing {len(dates)} trading days across all indices...")
    n_days = len(dates)
    start_d, end_d = dates[0], dates[-1]

    # ── 0. Global macro context ───────────────────────────────────────────────
    print("[Alpha] Fetching global macro context (DXY/Crude/Gold/S&P)...")
    global_ctx = get_global_context(n_days=n_days)
    if global_ctx.get("available"):
        print(f"[Alpha] Global: {global_ctx['summary']}")
    else:
        print("[Alpha] Global data unavailable — continuing without it")

    # ── 1. Load market snapshot for all dates ─────────────────────────────────
    snap = get_all_indices_for_dates(dates)
    if snap.empty:
        return {"error": "No market_snapshot data for this window"}

    # ── 2. Nifty 50 regime ────────────────────────────────────────────────────
    nifty_hist = get_nifty50_history(n_days=65)
    nifty_snap = snap[snap["index_name"] == "Nifty 50"].sort_values("date")
    window_closes = nifty_snap["close"].tolist()
    regime = compute_nifty_regime(nifty_hist, window_closes)

    # ── 3. All indices performance ────────────────────────────────────────────
    idx_df = _build_index_perf(snap, dates)

    # ── 4. Breadth ────────────────────────────────────────────────────────────
    breadth = compute_breadth(snap, dates)

    # ── 5. Cap rotation ───────────────────────────────────────────────────────
    rotation = compute_cap_rotation(snap, dates)

    # ── 6. Index drill-downs (top 7) ─────────────────────────────────────────
    print("[Alpha] Building index drill-downs (this takes 1-2 min)...")
    drill_reports = build_index_drilldown(idx_df, dates)

    # ── 7. LLM — regime analysis ──────────────────────────────────────────────
    top3 = idx_df.head(3).to_dict("records") if not idx_df.empty else []
    bot3 = idx_df.tail(3).to_dict("records") if not idx_df.empty else []
    print("[Alpha] Running regime LLM analysis...")
    regime_analysis = analyse_regime_llm(regime, breadth, rotation, top3, bot3, n_days, global_ctx)

    # ── 8. LLM — per-index deep reports ──────────────────────────────────────
    print(f"[Alpha] Running per-index LLM analysis for {len(drill_reports)} indices...")
    for i, report in enumerate(drill_reports):
        idx_name = report["index_name"]
        print(f"[Alpha] Index {i+1}/{len(drill_reports)}: {idx_name}")
        news = fetch_sector_news(idx_name, max_items=8)
        report["news"] = news
        report["llm_analysis"] = analyse_index_llm(report, news, n_days)

    return {
        "agent":          "Alpha",
        "timestamp":      datetime.now().isoformat(),
        "start_date":     start_d,
        "end_date":       end_d,
        "n_days":         n_days,
        "regime":         regime,
        "regime_analysis": regime_analysis,
        "breadth":        breadth,
        "cap_rotation":   rotation,
        "global_context": global_ctx,
        "all_indices":    idx_df.to_dict("records"),
        "top10_gainers":  idx_df.head(10).to_dict("records"),
        "top10_losers":   idx_df.tail(10).to_dict("records"),
        "index_drilldowns": drill_reports,
        "total_indices":  len(idx_df),
    }


# ── Standalone run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    dates = get_trading_dates(n)
    print(f"[Alpha] Window: {dates[0]} → {dates[-1]} ({len(dates)} days)")

    result = run_alpha(dates)

    out = OUTPUT_DIR / "last_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[Alpha] Report saved → {out}")

    # Quick terminal summary
    regime = result.get("regime", {})
    print(f"\n{'='*60}")
    print(f"  Nifty 50: {regime.get('latest_close')} | {regime.get('window_pct',0):+.2f}%")
    print(f"  Regime: {regime.get('regime')} ({regime.get('confidence')})")
    print(f"  PE: {regime.get('pe')} | Vol: {regime.get('vol_ann_pct')}%")
    print(f"\n  Top 5 indices:")
    for r in result.get("top10_gainers", [])[:5]:
        print(f"    {r['index']:<35} {r['pct_change']:>+7.2f}%")
    print(f"\n  Bottom 3 indices:")
    for r in result.get("top10_losers", [])[:3]:
        print(f"    {r['index']:<35} {r['pct_change']:>+7.2f}%")
    print(f"\n  Drill-downs built for {len(result.get('index_drilldowns', []))} indices")
    print(f"  Total indices tracked: {result.get('total_indices')}")
    print(f"{'='*60}")
    print(f"\n[Alpha] REGIME ANALYSIS:\n{result.get('regime_analysis', 'N/A')}")
