# -*- coding: utf-8 -*-
"""
MICC v2 — Agent Gamma: Institutional Flow Intelligence
=======================================================
Responsibilities:
  - FII/DII EQ cash market flow (₹ crores) for N-day window
  - Cumulative flow, trend direction, buy/sell streaks
  - FII vs DII divergence detection
  - F&O positioning (stale after Jul 2024 — used as directional context)
  - Flow score /10 (composite institutional sentiment)
  - Deep LLM analysis: is smart money accumulating or distributing?

Run standalone: py agent_gamma.py
Imported by: micc_engine.py
"""

import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from micc_data import (
    get_conn, get_trading_dates, get_fii_dii_flow, get_fno_positioning,
    call_llm, fmt_cr, fmt_pct,
)

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("agents/gamma")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# FLOW ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

def build_flow_table(fii_dii_df: pd.DataFrame) -> list:
    """
    Pivot raw FII/DII data into per-day rows.
    Returns list of {date, fii_net, dii_net, inst_net} dicts.
    """
    if fii_dii_df.empty:
        return []

    table = []
    for d in sorted(fii_dii_df["date"].unique()):
        day = fii_dii_df[fii_dii_df["date"] == d]
        fii_row = day[day["participant"] == "FII"]
        dii_row = day[day["participant"] == "DII"]

        fii_net = float(fii_row["net_value"].values[0]) \
            if not fii_row.empty and pd.notna(fii_row["net_value"].values[0]) else None
        dii_net = float(dii_row["net_value"].values[0]) \
            if not dii_row.empty and pd.notna(dii_row["net_value"].values[0]) else None
        inst_net = (fii_net or 0) + (dii_net or 0)

        table.append({
            "date":     d,
            "fii_net":  round(fii_net, 2)  if fii_net  is not None else None,
            "dii_net":  round(dii_net, 2)  if dii_net  is not None else None,
            "inst_net": round(inst_net, 2),
        })

    return table


def compute_flow_metrics(flow_table: list) -> dict:
    """
    Derive actionable metrics from flow table.
    """
    if not flow_table:
        return {"error": "No EQ flow data available", "days_available": 0}

    fii_nets = [r["fii_net"] for r in flow_table if r["fii_net"] is not None]
    dii_nets = [r["dii_net"] for r in flow_table if r["dii_net"] is not None]

    # Cumulatives
    fii_cum  = sum(fii_nets)
    dii_cum  = sum(dii_nets)
    inst_cum = fii_cum + dii_cum

    # Buy/sell days
    fii_buy_days  = sum(1 for v in fii_nets if v > 0)
    fii_sell_days = sum(1 for v in fii_nets if v < 0)
    dii_buy_days  = sum(1 for v in dii_nets if v > 0)
    dii_sell_days = sum(1 for v in dii_nets if v < 0)

    # Trend
    if fii_buy_days > fii_sell_days:
        fii_trend = "NET_BUYER"
    elif fii_sell_days > fii_buy_days:
        fii_trend = "NET_SELLER"
    else:
        fii_trend = "MIXED"

    # Current streak
    fii_consec_buy = fii_consec_sell = 0
    if fii_nets:
        cur_dir = "buy" if fii_nets[-1] > 0 else "sell" if fii_nets[-1] < 0 else None
        if cur_dir == "buy":
            for v in reversed(fii_nets):
                if v > 0:
                    fii_consec_buy += 1
                else:
                    break
        elif cur_dir == "sell":
            for v in reversed(fii_nets):
                if v < 0:
                    fii_consec_sell += 1
                else:
                    break

    # Latest day
    latest = flow_table[-1]
    fii_today = latest.get("fii_net")
    dii_today = latest.get("dii_net")

    # Divergence
    fii_dir = "BUY" if fii_today and fii_today > 0 else "SELL" if fii_today and fii_today < 0 else "NEUTRAL"
    dii_dir = "BUY" if dii_today and dii_today > 0 else "SELL" if dii_today and dii_today < 0 else "NEUTRAL"
    divergence = fii_dir != dii_dir and fii_dir != "NEUTRAL" and dii_dir != "NEUTRAL"

    # Avg daily flow
    avg_fii = fii_cum / len(fii_nets) if fii_nets else 0
    avg_dii = dii_cum / len(dii_nets) if dii_nets else 0

    # Acceleration: is latest week FII flow getting stronger or weaker?
    accel = None
    if len(fii_nets) >= 4:
        first_half = sum(fii_nets[:len(fii_nets)//2])
        second_half = sum(fii_nets[len(fii_nets)//2:])
        if first_half != 0:
            accel = ((second_half / abs(first_half)) - 1) * 100

    return {
        "days_available":      len(flow_table),
        "latest_date":         latest["date"],
        "fii_net_today_cr":    round(fii_today, 2)  if fii_today  else None,
        "dii_net_today_cr":    round(dii_today, 2)  if dii_today  else None,
        "inst_net_today_cr":   round(latest["inst_net"], 2),
        "fii_cumulative_cr":   round(fii_cum, 2),
        "dii_cumulative_cr":   round(dii_cum, 2),
        "inst_cumulative_cr":  round(inst_cum, 2),
        "fii_buy_days":        fii_buy_days,
        "fii_sell_days":       fii_sell_days,
        "dii_buy_days":        dii_buy_days,
        "dii_sell_days":       dii_sell_days,
        "fii_trend":           fii_trend,
        "fii_direction":       fii_dir,
        "dii_direction":       dii_dir,
        "fii_dii_divergence":  divergence,
        "fii_consec_buy_days":  fii_consec_buy,
        "fii_consec_sell_days": fii_consec_sell,
        "avg_daily_fii_cr":    round(avg_fii, 2),
        "avg_daily_dii_cr":    round(avg_dii, 2),
        "fii_flow_accel_pct":  round(accel, 1) if accel is not None else None,
    }


def compute_flow_score(metrics: dict, fno: dict) -> dict:
    """
    Composite institutional flow score: -10 (extreme bear) to +10 (extreme bull).
    Each signal adds or removes points with reasoning.
    """
    if metrics.get("error"):
        return {"flow_score": 0, "flow_sentiment": "NO_DATA", "components": []}

    score = 0
    components = []

    # FII cumulative flow
    fii_cum = metrics.get("fii_cumulative_cr", 0) or 0
    if fii_cum > 5000:
        score += 3; components.append(f"FII strong buyer (+₹{fii_cum:,.0f}Cr) ↑↑↑")
    elif fii_cum > 1000:
        score += 2; components.append(f"FII net buyer (+₹{fii_cum:,.0f}Cr) ↑↑")
    elif fii_cum > 0:
        score += 1; components.append(f"FII marginal buyer (+₹{fii_cum:,.0f}Cr) ↑")
    elif fii_cum < -5000:
        score -= 3; components.append(f"FII heavy seller (₹{fii_cum:,.0f}Cr) ↓↓↓")
    elif fii_cum < -1000:
        score -= 2; components.append(f"FII net seller (₹{fii_cum:,.0f}Cr) ↓↓")
    elif fii_cum < 0:
        score -= 1; components.append(f"FII marginal seller (₹{fii_cum:,.0f}Cr) ↓")

    # DII flow
    dii_cum = metrics.get("dii_cumulative_cr", 0) or 0
    if dii_cum > 3000:
        score += 2; components.append(f"DII strong domestic buying (+₹{dii_cum:,.0f}Cr) ↑↑")
    elif dii_cum > 500:
        score += 1; components.append(f"DII net buyer (+₹{dii_cum:,.0f}Cr) ↑")
    elif dii_cum < 0:
        score -= 1; components.append(f"DII selling (₹{dii_cum:,.0f}Cr) ↓")

    # FII/DII divergence
    if metrics.get("fii_dii_divergence"):
        components.append(f"⚠️ FII/DII DIVERGENCE: FII={metrics['fii_direction']} vs DII={metrics['dii_direction']}")

    # Sell streak
    sell_streak = metrics.get("fii_consec_sell_days", 0)
    buy_streak  = metrics.get("fii_consec_buy_days", 0)
    if sell_streak >= 3:
        score -= 1; components.append(f"FII selling for {sell_streak} consecutive days ↓")
    if buy_streak >= 3:
        score += 1; components.append(f"FII buying for {buy_streak} consecutive days ↑")

    # F&O positioning (context only — stale data)
    fno_positions = fno.get("positions", {}) if fno else {}
    fii_fno = fno_positions.get("FII", {})
    if fii_fno.get("bias") == "LONG":
        score += 1; components.append("FII F&O: LONG bias (historical context)")
    elif fii_fno.get("bias") == "SHORT":
        score -= 1; components.append("FII F&O: SHORT bias (historical context)")

    score = max(-10, min(10, score))
    if score >= 4:
        sentiment = "STRONG_BULL"
    elif score >= 1:
        sentiment = "BULL"
    elif score <= -4:
        sentiment = "STRONG_BEAR"
    elif score <= -1:
        sentiment = "BEAR"
    else:
        sentiment = "NEUTRAL"

    return {
        "flow_score":     score,
        "flow_sentiment": sentiment,
        "components":     components,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LLM ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def analyse_gamma_llm(metrics: dict, fno: dict, flow_score: dict,
                       flow_table: list, n_days: int, regime: str = "") -> str:
    """
    Deep institutional flow analysis via LLM.
    """
    # Build flow history string
    hist_str = " | ".join(
        f"{r['date']}: FII={fmt_cr(r['fii_net'],0)} DII={fmt_cr(r['dii_net'],0)}"
        for r in flow_table[-7:]
    ) if flow_table else "No data"

    fno_str = "No F&O data"
    if fno and fno.get("positions"):
        fno_str = " | ".join(
            f"{p}:{d['bias']}(net={d['net_contracts']:+,})"
            for p, d in fno["positions"].items()
        )

    prompt = (
        f"You are a senior FII/DII flow analyst covering NSE India. "
        f"Write a comprehensive {n_days}-day institutional flow report.\n\n"
        f"Structure EXACTLY as:\n\n"
        f"## Institutional Flow Intelligence — {n_days} Days\n\n"
        f"**1. Cash Market Flow Summary**\n"
        f"[3-4 sentences: quantify FII vs DII flows, trend direction, "
        f"cumulative impact on market liquidity]\n\n"
        f"**2. Smart Money Signal**\n"
        f"[2-3 sentences: is the dominant institutional player accumulating or distributing? "
        f"Is this trend accelerating or decelerating?]\n\n"
        f"**3. FII vs DII Divergence Analysis**\n"
        f"[2-3 sentences: are FII and DII moving in the same direction? "
        f"If diverging, what does historical pattern suggest?]\n\n"
        f"**4. F&O Positioning Context**\n"
        f"[2 sentences: what does the F&O positioning suggest about institutional hedging? "
        f"Note data is historical — treat as directional context only.]\n\n"
        f"**5. Flow Score Interpretation & Market Implication**\n"
        f"[3-4 sentences: translate the flow score into market implications. "
        f"What should a trader/investor do given this institutional posture? "
        f"Key risk: if FII selling continues at this pace, when does it become systemic?]\n\n"
        f"FLOW DATA:\n"
        f"FII cumulative: {fmt_cr(metrics.get('fii_cumulative_cr',0))} over {n_days} days | "
        f"Trend: {metrics.get('fii_trend','?')}\n"
        f"DII cumulative: {fmt_cr(metrics.get('dii_cumulative_cr',0))}\n"
        f"Combined institutional: {fmt_cr(metrics.get('inst_cumulative_cr',0))}\n"
        f"FII buy days: {metrics.get('fii_buy_days',0)} | sell days: {metrics.get('fii_sell_days',0)}\n"
        f"Consecutive streak: {metrics.get('fii_consec_buy_days',0)} buy / "
        f"{metrics.get('fii_consec_sell_days',0)} sell days\n"
        f"Flow score: {flow_score.get('flow_score',0)}/10 → {flow_score.get('flow_sentiment','?')}\n"
        f"Daily flow history: {hist_str}\n"
        f"F&O positioning: {fno_str}\n"
        f"Regime context: {regime or 'DEFAULT'} — "
        f"{'Emphasise smart money accumulation and upside momentum.' if 'UP' in (regime or '').upper() else 'Emphasise FII outflow risk, capital preservation, downside scenarios.' if any(x in (regime or '').upper() for x in ['DOWN','VOLAT']) else 'Balanced view — no strong regime bias.'}"
    )

    text, source = call_llm(prompt, max_tokens=1000, label="Gamma", prefer_groq=True)
    print(f"[Gamma] Analysis done via {source}")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AGENT
# ═══════════════════════════════════════════════════════════════════════════════

def run_gamma(dates: list, regime: str = "") -> dict:
    """Full Gamma agent run for N-day window."""
    print(f"[Gamma] Analysing institutional flow over {len(dates)} days...")
    n_days = len(dates)
    start_d, end_d = dates[0], dates[-1]

    # ── 1. Load EQ flow ───────────────────────────────────────────────────────
    fii_dii_raw = get_fii_dii_flow(dates)
    flow_table  = build_flow_table(fii_dii_raw)
    metrics     = compute_flow_metrics(flow_table)

    # ── 2. F&O positioning ────────────────────────────────────────────────────
    fno = get_fno_positioning()

    # ── 3. Flow score ─────────────────────────────────────────────────────────
    flow_score = compute_flow_score(metrics, fno)

    # ── 4. LLM analysis ───────────────────────────────────────────────────────
    print("[Gamma] Running LLM flow analysis...")
    analysis = analyse_gamma_llm(metrics, fno, flow_score, flow_table, n_days, regime=regime)

    return {
        "agent":          "Gamma",
        "timestamp":      datetime.now().isoformat(),
        "start_date":     start_d,
        "end_date":       end_d,
        "regime":         regime or "DEFAULT",
        "n_days":         n_days,
        "eq_flow": {
            "flow_table":  flow_table,
            "metrics":     metrics,
        },
        "fno_positioning": fno,
        "flow_score":      flow_score,
        "analysis":        analysis,
        "data_quality": {
            "eq_days_available": len(flow_table),
            "note": "FII/DII EQ data available from Apr 2026 onward. F&O stale post Jul 2024.",
        },
    }


# ── Standalone run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    dates = get_trading_dates(n)
    print(f"[Gamma] Window: {dates[0]} → {dates[-1]} ({len(dates)} days)")

    result = run_gamma(dates)

    out = OUTPUT_DIR / "last_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[Gamma] Report saved → {out}")

    eq = result.get("eq_flow", {})
    metrics = eq.get("metrics", {})
    fs = result.get("flow_score", {})
    print(f"\n{'='*60}")
    print(f"  FII {n}-day cumulative: {fmt_cr(metrics.get('fii_cumulative_cr',0))}")
    print(f"  DII {n}-day cumulative: {fmt_cr(metrics.get('dii_cumulative_cr',0))}")
    print(f"  Combined:              {fmt_cr(metrics.get('inst_cumulative_cr',0))}")
    print(f"  FII trend: {metrics.get('fii_trend','?')} | "
          f"buy days: {metrics.get('fii_buy_days',0)} / sell: {metrics.get('fii_sell_days',0)}")
    print(f"  Flow score: {fs.get('flow_score',0)}/10 → {fs.get('flow_sentiment','?')}")
    print(f"\n  Daily flow table:")
    for row in eq.get("flow_table", []):
        print(f"    {row['date']}  FII: {fmt_cr(row['fii_net'],0):>14}  "
              f"DII: {fmt_cr(row['dii_net'],0):>14}  Combined: {fmt_cr(row['inst_net'],0):>14}")
    print(f"{'='*60}")
    print(f"\n[Gamma] ANALYSIS:\n{result.get('analysis','N/A')[:600]}...")
