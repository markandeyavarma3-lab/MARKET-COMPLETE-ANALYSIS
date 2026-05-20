# -*- coding: utf-8 -*-
"""
MICC v2 — Agent Delta: Risk Intelligence + Proactive Alerts
===========================================================
TWO modes of operation:

1. REPORT MODE (called by micc_engine.py):
   - Risk score /10 for the N-day window
   - PE/valuation risk flags
   - Nifty OI trend (fo_data, stale — context)
   - Corporate actions in window
   - Quality universe screen
   - Insider activity summary (Patch 2.3)
   - LLM risk synthesis

2. STANDALONE ALERT MODE (py agent_delta.py --alerts):
   - Runs scheduled checks at 9:20 AM IST daily
   - Proactive Telegram push for:
     * Volume spike > 3x for Nifty 100 stocks
     * 52-week high/low crosses
     * FII single-day selling > ₹2000 Cr
     * VIX spike > 20% single day
     * PE stretched alerts (Nifty PE > 24)
     * Dividend / split announcements today
     * Insider cluster buying / large transactions (Patch 2.3)

Run:
  py agent_delta.py           → one-off risk report (5 days)
  py agent_delta.py --alerts  → start alert scheduler (runs 9:20 AM IST daily)
  py agent_delta.py --alerts --now  → run alerts immediately + then schedule
"""

import json
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from micc_data import (
    get_conn, get_trading_dates, load_all_symbols_window,
    get_fundamentals, get_52w_extremes, get_corporate_actions,
    get_fii_dii_flow, get_nifty50_history,
    call_llm, send_telegram, send_telegram_chunks,
    fmt_cr, fmt_pct, now_ist,
)

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("agents/delta")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IST = ZoneInfo("Asia/Kolkata")

# Alert thresholds
FII_SINGLE_DAY_ALERT_CR  = 2000   # FII sells > ₹2000 Cr in one day
VOL_SPIKE_MULTIPLE       = 3.0    # volume 3x average
VIX_DAILY_SPIKE_PCT      = 20.0   # VIX up > 20% in one day
NIFTY_PE_STRETCHED       = 24.0   # Nifty PE above this → stretched valuation alert
NIFTY_PE_CHEAP           = 18.0   # Nifty PE below this → cheap valuation alert
INSIDER_NET_ALERT_LAKH   = 50.0   # Promoter net ≥ ₹50L in 7 days → alert
INSIDER_CLUSTER_COUNT    = 3      # 3+ insiders on same stock → cluster alert
INSIDER_LARGE_TX_LAKH    = 500.0  # Single transaction ≥ ₹5 Cr → alert


# ═══════════════════════════════════════════════════════════════════════════════
# RISK ENGINE (report mode)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_risk_score(dates: list, nifty_hist: pd.DataFrame) -> dict:
    """
    Compute overall risk score (1-10) with individual flags.
    1-3 = LOW, 4-6 = MEDIUM, 7-8 = HIGH, 9-10 = EXTREME
    """
    score = 5  # start neutral
    risk_flags  = []
    green_flags = []
    latest_vix  = None

    start_d, end_d = dates[0], dates[-1]

    # ── Nifty PE valuation ────────────────────────────────────────────────────
    if not nifty_hist.empty and "pe" in nifty_hist.columns:
        latest_pe = float(nifty_hist["pe"].dropna().iloc[-1]) \
            if nifty_hist["pe"].dropna().shape[0] > 0 else None
        if latest_pe:
            if latest_pe > 28:
                score += 2
                risk_flags.append(f"Nifty PE={latest_pe:.1f} — highly stretched, correction risk")
            elif latest_pe > NIFTY_PE_STRETCHED:
                score += 1
                risk_flags.append(f"Nifty PE={latest_pe:.1f} — above comfort zone")
            elif latest_pe < NIFTY_PE_CHEAP:
                score -= 1
                green_flags.append(f"Nifty PE={latest_pe:.1f} — attractive valuation")

    # ── Volatility (annualised) ───────────────────────────────────────────────
    if not nifty_hist.empty and len(nifty_hist) >= 20:
        closes = nifty_hist["close"].dropna()
        if len(closes) >= 20:
            vol = float(closes.pct_change().dropna().tail(19).std() * (252**0.5) * 100)
            if vol > 25:
                score += 2
                risk_flags.append(f"High volatility: {vol:.1f}% annualised — unstable market")
            elif vol > 18:
                score += 1
                risk_flags.append(f"Elevated volatility: {vol:.1f}% — caution warranted")
            elif vol < 12:
                score -= 1
                green_flags.append(f"Low volatility: {vol:.1f}% — calm market conditions")

    # ── India VIX trend ───────────────────────────────────────────────────────
    conn = get_conn()
    vix_df = pd.read_sql("""
        SELECT date, closing_index_value as vix
        FROM market_snapshot
        WHERE index_name = 'India VIX'
        ORDER BY date DESC LIMIT 10
    """, conn)
    conn.close()
    if not vix_df.empty:
        vix_df["vix"] = pd.to_numeric(vix_df["vix"], errors="coerce")
        latest_vix = float(vix_df["vix"].iloc[0]) if pd.notna(vix_df["vix"].iloc[0]) else None
        if latest_vix:
            if latest_vix > 20:
                score += 1
                risk_flags.append(f"VIX={latest_vix:.1f} — elevated fear index")
            elif latest_vix < 12:
                score -= 1
                green_flags.append(f"VIX={latest_vix:.1f} — complacency zone, low fear")

    # ── Nifty OI from fo_data (stale — context) ───────────────────────────────
    conn = get_conn()
    oi_df = pd.read_sql("""
        SELECT date, SUM(open_int) AS total_oi
        FROM fo_data
        WHERE symbol = 'NIFTY' AND instrument = 'FUTIDX'
        GROUP BY date ORDER BY date DESC LIMIT 20
    """, conn)
    conn.close()
    if not oi_df.empty and len(oi_df) >= 5:
        oi_df["total_oi"] = pd.to_numeric(oi_df["total_oi"], errors="coerce")
        latest_oi = float(oi_df["total_oi"].iloc[0])
        base_oi   = float(oi_df["total_oi"].iloc[4])
        if base_oi > 0:
            oi_chg = ((latest_oi / base_oi) - 1) * 100
            if oi_chg > 15:
                score += 1
                risk_flags.append(
                    f"Nifty OI rising sharply (+{oi_chg:.1f}%) — elevated positioning (stale data)"
                )
            elif oi_chg < -15:
                green_flags.append(
                    f"Nifty OI falling ({oi_chg:.1f}%) — short covering possible (stale data)"
                )

    # ── Corporate actions ─────────────────────────────────────────────────────
    corp = get_corporate_actions(start_d, end_d)
    if not corp.empty:
        splits = corp[corp["action_type"] == "SPLIT"]
        divs   = corp[corp["action_type"] == "DIVIDEND"]
        if len(splits) > 0:
            score -= 1
            green_flags.append(f"{len(splits)} stock splits in window — bullish corporate activity")
        if len(divs) > 0:
            green_flags.append(f"{len(divs)} dividend payouts in window — shareholder-friendly")

    # ── High-PE universe ──────────────────────────────────────────────────────
    conn = get_conn()
    high_pe = pd.read_sql("""
        SELECT COUNT(*) as cnt FROM stock_fundamentals WHERE trailingPE > 100
    """, conn)
    conn.close()
    cnt = int(high_pe["cnt"].iloc[0]) if not high_pe.empty else 0
    if cnt > 30:
        risk_flags.append(f"{cnt} stocks with PE > 100 — stretched valuation universe")

    # ── Quality universe availability ─────────────────────────────────────────
    conn = get_conn()
    quality = pd.read_sql("""
        SELECT COUNT(*) as cnt FROM stock_fundamentals
        WHERE trailingPE BETWEEN 5 AND 25 AND returnOnEquity > 0.15 AND debtToEquity < 50
    """, conn)
    conn.close()
    q_cnt = int(quality["cnt"].iloc[0]) if not quality.empty else 0
    if q_cnt > 30:
        green_flags.append(f"{q_cnt} quality stocks available (PE 5-25, ROE>15%) — healthy market")

    score = max(1, min(10, score))
    level = "LOW" if score <= 3 else "MEDIUM" if score <= 6 else "HIGH" if score <= 8 else "EXTREME"

    return {
        "risk_score":    score,
        "risk_level":    level,
        "risk_flags":    risk_flags,
        "green_flags":   green_flags,
        "vix":           latest_vix,
        "high_pe_count": cnt,
        "quality_count": q_cnt,
    }


def get_quality_universe() -> pd.DataFrame:
    """Quality stocks: PE 5-30, ROE > 15%, low debt."""
    conn = get_conn()
    df = pd.read_sql("""
        SELECT symbol, sector, trailingPE as pe, returnOnEquity as roe,
               debtToEquity as de, priceToBook as pb, currentRatio, beta
        FROM stock_fundamentals
        WHERE trailingPE BETWEEN 5 AND 30
          AND returnOnEquity > 0.15
          AND debtToEquity < 60
        ORDER BY returnOnEquity DESC LIMIT 20
    """, conn)
    conn.close()
    for col in ["pe", "roe", "de", "pb", "beta"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def analyse_risk_llm(risk: dict, corp: pd.DataFrame, n_days: int,
                      quality: pd.DataFrame, regime: str = "") -> str:
    """LLM risk synthesis — comprehensive risk-adjusted outlook."""
    risk_str  = " | ".join(risk.get("risk_flags", [])[:4])
    green_str = " | ".join(risk.get("green_flags", [])[:3])
    corp_str  = " | ".join(
        f"{r['symbol']}({r['action_type']}={r.get('amount', r.get('ratio','?'))})"
        for _, r in corp.head(8).iterrows()
    ) if not corp.empty else "None"

    def _fmt_quality_row(r) -> str:
        pe_val  = r.get("pe")
        roe_val = r.get("roe")
        pe_str  = f"{float(pe_val):.0f}"       if pe_val  is not None and str(pe_val)  != "nan" else "?"
        roe_str = f"{float(roe_val)*100:.0f}%"  if roe_val is not None and str(roe_val) != "nan" else "?"
        return f"{r['symbol']}(PE={pe_str},ROE={roe_str})"

    top_quality = " | ".join(
        _fmt_quality_row(r) for _, r in quality.head(5).iterrows()
    ) if not quality.empty else "None"

    prompt = (
        f"You are a senior NSE risk analyst. Write a comprehensive {n_days}-day risk intelligence report.\n\n"
        f"Structure EXACTLY as:\n\n"
        f"## Risk Intelligence Report — {n_days} Days\n\n"
        f"**1. Overall Risk Assessment**\n"
        f"[2-3 sentences: risk level interpretation. What does {risk['risk_score']}/10 mean "
        f"for a trader vs a long-term investor?]\n\n"
        f"**2. Key Risk Factors**\n"
        f"[2-3 sentences: analyse the specific risk flags. Which is most systemic? "
        f"Which can be ignored vs which demands immediate attention?]\n\n"
        f"**3. Positive Risk Offsets**\n"
        f"[2-3 sentences: analyse the green flags. Are these structural or temporary?]\n\n"
        f"**4. Corporate Action Intelligence**\n"
        f"[2-3 sentences: what do the corporate actions signal? "
        f"Dividend-paying stocks in a volatile market can be defensive anchors.]\n\n"
        f"**5. Quality Universe — Defensive Positions**\n"
        f"[2-3 sentences: in the current risk environment, which quality stocks offer "
        f"the best risk-adjusted positioning? Why?]\n\n"
        f"**6. Risk-Adjusted Strategy for Next 5-7 Days**\n"
        f"[3-4 sentences: concrete positioning advice based on current risk level. "
        f"What % cash/exposure is appropriate? Any specific hedges to consider?]\n\n"
        f"RISK DATA:\n"
        f"Risk score: {risk['risk_score']}/10 — {risk['risk_level']}\n"
        f"VIX: {risk.get('vix', 'N/A')}\n"
        f"Risk flags: {risk_str or 'None'}\n"
        f"Positive signals: {green_str or 'None'}\n"
        f"Corporate actions in window: {corp_str}\n"
        f"Top quality picks: {top_quality}"
    )

    _rctx = (
        "BEAR REGIME: elevate downside scenarios, flag cascading FII outflow risk."
        if "DOWN" in (regime or "").upper() else
        "HIGH VOLATILITY: focus on VIX trajectory, hedge recommendations, position sizing."
        if "VOLAT" in (regime or "").upper() else
        "BULL REGIME: flag valuation stretch and crowding risks despite positive momentum."
        if "UP" in (regime or "").upper() else
        "Neutral regime — balanced risk assessment."
    )
    prompt += f"\n\nRegime context: {_rctx}"

    text, source = call_llm(prompt, max_tokens=1000, label="Delta-Risk", prefer_groq=True)
    print(f"[Delta] Risk analysis done via {source}")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# PROACTIVE ALERT ENGINE (standalone mode)
# ═══════════════════════════════════════════════════════════════════════════════

def check_fii_alerts() -> list:
    """Alert if FII single-day sell > ₹2000 Cr."""
    alerts = []
    today  = get_trading_dates(1)
    if not today:
        return alerts

    conn = get_conn()
    df = pd.read_sql("""
        SELECT date, participant,
               MAX(buy_value) as buy, MAX(sell_value) as sell, MAX(net_value) as net
        FROM fii_dii_data
        WHERE segment = 'EQ' AND participant = 'FII'
          AND date = (SELECT MAX(date) FROM fii_dii_data WHERE segment='EQ' AND participant='FII')
        GROUP BY date, participant
    """, conn)
    conn.close()

    if df.empty:
        return alerts

    net = float(df["net"].iloc[0]) if pd.notna(df["net"].iloc[0]) else None
    if net and net < -FII_SINGLE_DAY_ALERT_CR:
        msg = (
            "\U0001f534 *FII ALERT* \u2014 Heavy selling detected!\n"
            f"FII net: `{fmt_cr(net)}` today\n"
            f"Date: {df['date'].iloc[0]}\n"
            f"\u26a0\ufe0f FII single-day selling exceeded \u20b9{FII_SINGLE_DAY_ALERT_CR:,}Cr threshold"
        )
        alerts.append({"type": "FII_HEAVY_SELL", "message": msg, "severity": "HIGH"})
    return alerts


def check_vix_alerts() -> list:
    """Alert if VIX spikes > 20% in one day."""
    alerts = []
    conn = get_conn()
    df = pd.read_sql("""
        SELECT date, closing_index_value as vix, change
        FROM market_snapshot
        WHERE index_name = 'India VIX'
        ORDER BY date DESC LIMIT 5
    """, conn)
    conn.close()

    if df.empty:
        return alerts

    df["vix"]    = pd.to_numeric(df["vix"],    errors="coerce")
    df["change"] = pd.to_numeric(df["change"], errors="coerce")

    latest_vix    = float(df["vix"].iloc[0])    if pd.notna(df["vix"].iloc[0])    else None
    latest_change = float(df["change"].iloc[0]) if pd.notna(df["change"].iloc[0]) else 0

    if latest_vix is None:
        return alerts

    prev_vix = latest_vix - latest_change
    if prev_vix and prev_vix != 0:
        latest_pct = (latest_change / prev_vix) * 100
    else:
        latest_pct = 0

    print(f"[Delta] VIX: {latest_vix:.2f} | change: {latest_change:+.2f} pts | {latest_pct:+.1f}%")

    if abs(latest_pct) > VIX_DAILY_SPIKE_PCT:
        direction = "SPIKE" if latest_pct > 0 else "DROP"
        emoji = "\U0001f534" if latest_pct > 0 else "\U0001f7e2"
        tail  = "\u26a0\ufe0f Fear spike \u2014 consider reducing exposure" if direction == "SPIKE" \
                else "\u2705 Fear easing \u2014 opportunity window"
        msg = (
            f"{emoji} *VIX {direction} ALERT*\n"
            f"India VIX: `{latest_vix:.2f}` ({latest_pct:+.1f}% today)\n"
            f"Date: {df['date'].iloc[0]}\n"
            f"{tail}"
        )
        alerts.append({
            "type":     f"VIX_{direction}",
            "message":  msg,
            "severity": "HIGH" if direction == "SPIKE" else "INFO",
        })
    return alerts


def check_pe_alerts() -> list:
    """Alert if Nifty PE crosses stretched or cheap thresholds."""
    alerts = []
    conn = get_conn()
    df = pd.read_sql("""
        SELECT date, pe FROM market_snapshot
        WHERE index_name = 'Nifty 50'
        ORDER BY date DESC LIMIT 5
    """, conn)
    conn.close()

    if df.empty:
        return alerts

    df["pe"] = pd.to_numeric(df["pe"], errors="coerce")
    latest_pe = float(df["pe"].dropna().iloc[0]) if df["pe"].dropna().shape[0] > 0 else None

    if latest_pe:
        if latest_pe > NIFTY_PE_STRETCHED:
            msg = (
                f"\u26a0\ufe0f *NIFTY VALUATION ALERT*\n"
                f"Nifty 50 PE: `{latest_pe:.1f}` \u2014 above {NIFTY_PE_STRETCHED:.0f}x\n"
                f"Market is in stretched valuation zone.\n"
                f"Historically, returns are muted above 24x PE."
            )
            alerts.append({"type": "PE_STRETCHED", "message": msg, "severity": "MEDIUM"})
        elif latest_pe < NIFTY_PE_CHEAP:
            msg = (
                f"\U0001f48e *NIFTY CHEAP ZONE ALERT*\n"
                f"Nifty 50 PE: `{latest_pe:.1f}` \u2014 below {NIFTY_PE_CHEAP:.0f}x\n"
                f"Market entering attractive valuation zone.\n"
                f"Historically good long-term entry point."
            )
            alerts.append({"type": "PE_CHEAP", "message": msg, "severity": "INFO"})
    return alerts


def check_volume_spikes() -> list:
    """Alert on stocks with vol > 3x average (Nifty 100 universe only for speed)."""
    alerts = []
    try:
        dates_3d = get_trading_dates(3)
        if len(dates_3d) < 2:
            return alerts

        conn = get_conn()
        rows = conn.execute("""
            SELECT DISTINCT symbol FROM indices_data
            WHERE (index_name LIKE 'Nifty 100%' OR index_name = 'Nifty 100')
              AND symbol IS NOT NULL
              AND date = (SELECT MAX(date) FROM indices_data WHERE index_name LIKE 'Nifty 100%')
        """).fetchall()
        conn.close()
        symbols = [r[0] for r in rows][:100]

        if not symbols:
            return alerts

        from micc_data import load_parquet_symbol
        cur_year = datetime.now().year
        spikes = []

        for sym in symbols:
            df = load_parquet_symbol(sym, [cur_year - 1, cur_year])
            if df.empty or "volume" not in df.columns:
                continue
            df_20 = df.tail(22)
            if len(df_20) < 15:
                continue
            vols = pd.to_numeric(df_20["volume"], errors="coerce").dropna()
            avg_vol  = float(vols.iloc[:-1].mean()) if len(vols) > 1 else 0
            last_vol = float(vols.iloc[-1])
            if avg_vol > 0 and last_vol / avg_vol >= VOL_SPIKE_MULTIPLE:
                closes    = pd.to_numeric(df_20["close"], errors="coerce").dropna()
                price_chg = ((float(closes.iloc[-1]) / float(closes.iloc[-2])) - 1) * 100 \
                    if len(closes) >= 2 else 0
                spikes.append({
                    "symbol":    sym,
                    "vol_spike": round(last_vol / avg_vol, 1),
                    "price_chg": round(price_chg, 2),
                    "last_vol":  int(last_vol),
                })

        if spikes:
            spikes.sort(key=lambda x: x["vol_spike"], reverse=True)
            lines = "\n".join(
                f"  `{s['symbol']}` {s['vol_spike']:.1f}x vol | {s['price_chg']:+.2f}%"
                for s in spikes[:8]
            )
            msg = (
                f"\U0001f4a5 *VOLUME SPIKE ALERT \u2014 {len(spikes)} stocks*\n"
                f"Stocks with 3x+ volume in Nifty 100:\n{lines}\n"
                f"_Check for news/results before acting_"
            )
            alerts.append({"type": "VOL_SPIKES", "message": msg, "severity": "INFO"})

    except Exception as e:
        print(f"[Delta] Vol spike check failed: {e}")

    return alerts


def check_52w_crossings() -> list:
    """Alert on Nifty 50 stocks crossing 52-week highs."""
    alerts = []
    try:
        from micc_data import get_52w_extremes

        conn = get_conn()
        rows = conn.execute("""
            SELECT DISTINCT symbol FROM indices_data
            WHERE (index_name = 'Nifty 50' OR index_name LIKE 'Nifty 50 %')
              AND symbol IS NOT NULL
              AND date = (SELECT MAX(date) FROM indices_data WHERE index_name LIKE 'Nifty 50%')
        """).fetchall()
        conn.close()
        symbols = [r[0] for r in rows][:55]

        if not symbols:
            return alerts

        extremes = get_52w_extremes(symbols)
        if extremes.empty:
            return alerts

        at_high = extremes[extremes["pct_from_high"] >= -0.5]
        at_low  = extremes[extremes["pct_from_low"]  <= 0.5]

        if not at_high.empty:
            high_str = " | ".join(
                f"`{r['symbol']}`({r['current_price']:.0f})"
                for _, r in at_high.iterrows()
            )
            msg = (
                f"\U0001f680 *52-WEEK HIGH ALERT \u2014 Nifty 50 stocks*\n"
                f"At/near 52w high: {high_str}\n"
                f"_Breakout candidates \u2014 watch for volume confirmation_"
            )
            alerts.append({"type": "52W_HIGH", "message": msg, "severity": "INFO"})

        if not at_low.empty:
            low_str = " | ".join(
                f"`{r['symbol']}`({r['current_price']:.0f})"
                for _, r in at_low.iterrows()
            )
            msg = (
                f"\U0001f534 *52-WEEK LOW ALERT \u2014 Nifty 50 stocks*\n"
                f"At/near 52w low: {low_str}\n"
                f"_Could be value or value trap \u2014 check fundamentals_"
            )
            alerts.append({"type": "52W_LOW", "message": msg, "severity": "MEDIUM"})

    except Exception as e:
        print(f"[Delta] 52w crossing check failed: {e}")

    return alerts


def check_corporate_actions_today() -> list:
    """Alert on corporate actions today (dividends, splits)."""
    alerts = []
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        corp = get_corporate_actions(today_str, today_str)
        if corp.empty:
            return alerts

        splits = corp[corp["action_type"] == "SPLIT"]
        divs   = corp[corp["action_type"] == "DIVIDEND"]

        if not splits.empty:
            split_str = " | ".join(
                f"`{r['symbol']}`(1:{r.get('ratio','?')})"
                for _, r in splits.iterrows()
            )
            alerts.append({
                "type":     "SPLIT_TODAY",
                "message":  f"\u2702\ufe0f *STOCK SPLITS TODAY*\n{split_str}",
                "severity": "INFO",
            })

        if not divs.empty:
            div_str = " | ".join(
                f"`{r['symbol']}`(\u20b9{r.get('amount','?')})"
                for _, r in divs.head(8).iterrows()
            )
            alerts.append({
                "type":     "DIVIDENDS_TODAY",
                "message":  f"\U0001f4b0 *DIVIDENDS TODAY*\n{div_str}",
                "severity": "INFO",
            })

    except Exception as e:
        print(f"[Delta] Corp actions check failed: {e}")

    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# INSIDER TRADING ALERTS (Patch 2.3)
# ─────────────────────────────────────────────────────────────────────────────

def check_insider_alerts() -> list:
    """
    Alert on significant insider activity in the last 7 days.

    Triggers:
      - Cluster buying: 3+ insiders buying same stock
      - Promoter/director net buy or sell >= INSIDER_NET_ALERT_LAKH (₹50L)
      - Any single transaction >= INSIDER_LARGE_TX_LAKH (₹5 Cr)

    insider_trading schema:
      filing_date, symbol, company, name, category,
      transaction_type, quantity, price, value, post_holding
    """
    alerts = []
    try:
        conn = get_conn()
        df = pd.read_sql(
            """
            SELECT filing_date, symbol, company, name, category,
                   transaction_type, quantity, price, value, post_holding
            FROM insider_trading
            WHERE filing_date >= date('now', '-7 days')
            ORDER BY filing_date DESC
            """,
            conn,
        )
        conn.close()

        if df.empty:
            return alerts

        df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)

        # Classify buy / sell
        tx_upper = df["transaction_type"].str.upper().fillna("")
        df["is_buy"]  = tx_upper.str.contains("BUY|ACQUISITION|ACQUIRE|PURCHASE", regex=True)
        df["is_sell"] = tx_upper.str.contains("SELL|DISPOSAL|DISPOSE", regex=True)
        df["signed_value"] = df.apply(
            lambda r: r["value"] if r["is_buy"] else (-r["value"] if r["is_sell"] else 0),
            axis=1,
        )

        # ── 1. Promoter / director analysis ──────────────────────────────────
        cat_upper  = df["category"].str.upper().fillna("")
        promoter_mask = cat_upper.str.contains(
            "PROMOTER|DIRECTOR|OFFICER|MANAGEMENT", regex=True
        )
        promoter_df = df[promoter_mask]

        if not promoter_df.empty:
            stock_nets = (
                promoter_df.groupby("symbol")
                .agg(
                    net_value=("signed_value", "sum"),
                    tx_count=("name", "count"),
                    unique_insiders=("name", "nunique"),
                )
                .reset_index()
            )

            # Cluster buying
            clusters = stock_nets[
                (stock_nets["unique_insiders"] >= INSIDER_CLUSTER_COUNT)
                & (stock_nets["net_value"] > 0)
            ].head(5)
            if not clusters.empty:
                lines = "\n".join(
                    "  `{sym}` \u2014 {n} insiders, net \u20b9{val:.1f}L".format(
                        sym=r["symbol"],
                        n=r["unique_insiders"],
                        val=r["net_value"] / 1e5,
                    )
                    for _, r in clusters.iterrows()
                )
                msg = (
                    "\U0001f7e2 *INSIDER CLUSTER BUYING*\n"
                    "3+ insiders buying same stock (last 7 days):\n"
                    + lines
                    + "\n_Cluster buying is a strong conviction signal_"
                )
                alerts.append({
                    "type":     "INSIDER_CLUSTER_BUY",
                    "message":  msg,
                    "severity": "HIGH",
                })

            # Net threshold alert
            big_nets = stock_nets[
                stock_nets["net_value"].abs() / 1e5 >= INSIDER_NET_ALERT_LAKH
            ].sort_values("net_value", ascending=False)

            if not big_nets.empty:
                buy_rows  = big_nets[big_nets["net_value"] > 0].head(5)
                sell_rows = big_nets[big_nets["net_value"] < 0].head(5)

                buy_str  = " | ".join(
                    "`{s}`(+\u20b9{v:.0f}L)".format(s=r["symbol"], v=r["net_value"] / 1e5)
                    for _, r in buy_rows.iterrows()
                )
                sell_str = " | ".join(
                    "`{s}`(-\u20b9{v:.0f}L)".format(s=r["symbol"], v=abs(r["net_value"]) / 1e5)
                    for _, r in sell_rows.iterrows()
                )

                body_lines = []
                if buy_str:
                    body_lines.append("  \U0001f7e2 Buying: " + buy_str)
                if sell_str:
                    body_lines.append("  \U0001f534 Selling: " + sell_str)

                if body_lines:
                    msg = (
                        "\U0001f464 *SIGNIFICANT INSIDER ACTIVITY (last 7 days)*\n"
                        "Promoter/director net trades \u2265\u20b9{th:.0f}L:\n".format(
                            th=INSIDER_NET_ALERT_LAKH
                        )
                        + "\n".join(body_lines)
                    )
                    alerts.append({
                        "type":     "INSIDER_NET_ACTIVITY",
                        "message":  msg,
                        "severity": "INFO",
                    })

        # ── 2. Large single transaction ───────────────────────────────────────
        large_tx = df[
            df["value"] / 1e5 >= INSIDER_LARGE_TX_LAKH
        ].sort_values("value", ascending=False).head(5)

        if not large_tx.empty:
            lines = "\n".join(
                "  `{sym}` \u2014 {cat} {tx} \u20b9{val:.1f}Cr ({dt})".format(
                    sym=r["symbol"],
                    cat=r["category"],
                    tx=r["transaction_type"],
                    val=r["value"] / 1e7,
                    dt=r["filing_date"],
                )
                for _, r in large_tx.iterrows()
            )
            msg = "\U0001f4b0 *LARGE INSIDER TRANSACTIONS (\u2265\u20b95Cr)*\n" + lines
            alerts.append({
                "type":     "INSIDER_LARGE_TX",
                "message":  msg,
                "severity": "MEDIUM",
            })

    except Exception as e:
        print(f"[Delta] Insider alert check failed: {e}")

    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_all_alerts(send: bool = True) -> list:
    """
    Run all alert checks and optionally send to Telegram.
    Returns list of triggered alerts.
    """
    print(f"[Delta] Running proactive alert checks at {now_ist()}...")
    all_alerts = []

    print("[Delta] Checking FII heavy selling...")
    all_alerts.extend(check_fii_alerts())

    print("[Delta] Checking VIX spikes...")
    all_alerts.extend(check_vix_alerts())

    print("[Delta] Checking PE alerts...")
    all_alerts.extend(check_pe_alerts())

    print("[Delta] Checking volume spikes (Nifty 100)...")
    all_alerts.extend(check_volume_spikes())

    print("[Delta] Checking 52-week crossings (Nifty 50)...")
    all_alerts.extend(check_52w_crossings())

    print("[Delta] Checking corporate actions today...")
    all_alerts.extend(check_corporate_actions_today())

    print("[Delta] Checking insider trading activity...")
    all_alerts.extend(check_insider_alerts())

    print(f"[Delta] {len(all_alerts)} alert(s) triggered")

    if all_alerts and send:
        header = f"*\u26a1 MICC DELTA ALERTS \u2014 {now_ist()}*\n{'\u2500'*35}\n\n"
        body   = "\n\n".join(a["message"] for a in all_alerts)
        full   = header + body
        print(f"[Delta] Sending {len(all_alerts)} alerts to Telegram...")
        send_telegram_chunks(full)
    elif not all_alerts and send:
        send_telegram(f"\u2705 *MICC Delta* \u2014 No alerts triggered at {now_ist()}")

    out = OUTPUT_DIR / "last_alerts.json"
    with open(out, "w") as f:
        json.dump(
            {"timestamp": datetime.now().isoformat(), "alerts": all_alerts},
            f, indent=2, default=str,
        )

    return all_alerts


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT MODE (called by micc_engine.py)
# ═══════════════════════════════════════════════════════════════════════════════

def run_delta(dates: list, regime: str = "") -> dict:
    """Full Delta risk report for N-day window."""
    print(f"[Delta] Analysing risk signals for {len(dates)}-day window...")
    n_days = len(dates)
    start_d, end_d = dates[0], dates[-1]

    # ── Nifty 50 history for regime ───────────────────────────────────────────
    nifty_hist = get_nifty50_history(n_days=30)

    # ── Risk score ────────────────────────────────────────────────────────────
    risk = compute_risk_score(dates, nifty_hist)

    # ── Corporate actions ─────────────────────────────────────────────────────
    corp = get_corporate_actions(start_d, end_d)

    # ── Quality universe ──────────────────────────────────────────────────────
    quality = get_quality_universe()

    # ── Insider activity summary ──────────────────────────────────────────────
    insider_summary = []
    try:
        conn = get_conn()
        ins_df = pd.read_sql(
            """
            SELECT filing_date, symbol, category, transaction_type, value
            FROM insider_trading
            WHERE filing_date >= date('now', '-14 days')
            ORDER BY ABS(CAST(value AS REAL)) DESC
            LIMIT 10
            """,
            conn,
        )
        conn.close()
        if not ins_df.empty:
            ins_df["value"] = pd.to_numeric(ins_df["value"], errors="coerce")
            insider_summary = ins_df.to_dict("records")
    except Exception as e:
        print(f"[Delta] Insider summary failed: {e}")

    # ── LLM risk synthesis ────────────────────────────────────────────────────
    print("[Delta] Running LLM risk analysis...")
    analysis = analyse_risk_llm(risk, corp, n_days, quality, regime=regime)

    return {
        "agent":             "Delta",
        "timestamp":         datetime.now().isoformat(),
        "regime":            regime or "DEFAULT",
        "start_date":        start_d,
        "end_date":          end_d,
        "n_days":            n_days,
        "risk_score":        risk["risk_score"],
        "risk_level":        risk["risk_level"],
        "risk_flags":        risk["risk_flags"],
        "green_flags":       risk["green_flags"],
        "vix":               risk.get("vix"),
        "high_pe_count":     risk.get("high_pe_count"),
        "quality_count":     risk.get("quality_count"),
        "corporate_actions": corp.to_dict("records") if not corp.empty else [],
        "quality_universe":  quality.head(10).to_dict("records") if not quality.empty else [],
        "insider_activity":  insider_summary,
        "analysis":          analysis,
        "data_note":         "fo_data OI is stale (max Jul 2024) — used for directional context only",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--alerts" in sys.argv:
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            HAS_SCHEDULER = True
        except ImportError:
            HAS_SCHEDULER = False
            print("[Delta] apscheduler not installed — running alerts once only")

        if "--now" in sys.argv or not HAS_SCHEDULER:
            print("[Delta] Running alert checks now...")
            alerts = run_all_alerts(send=True)
            for a in alerts:
                print(f"  [{a['severity']}] {a['type']}: {a['message'][:80]}...")

        if HAS_SCHEDULER:
            print("[Delta] Starting alert scheduler — daily at 9:20 AM IST")
            print("[Delta] Press Ctrl+C to stop\n")
            scheduler = BlockingScheduler(timezone=IST)
            scheduler.add_job(
                run_all_alerts,
                trigger="cron",
                hour=9,
                minute=20,
                kwargs={"send": True},
                name="delta_alerts",
            )
            try:
                scheduler.start()
            except KeyboardInterrupt:
                print("\n[Delta] Alert scheduler stopped.")

    else:
        n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
        dates = get_trading_dates(n)
        print(f"[Delta] Window: {dates[0]} → {dates[-1]} ({len(dates)} days)")

        result = run_delta(dates)

        out = OUTPUT_DIR / "last_report.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n[Delta] Report saved → {out}")

        print(f"\n{'='*60}")
        print(f"  Risk Score: {result['risk_score']}/10 — {result['risk_level']}")
        print(f"  VIX: {result.get('vix', 'N/A')}")
        print(f"\n  Risk Flags:")
        for f in result.get("risk_flags", []):
            print(f"    \U0001f534 {f}")
        print(f"\n  Green Flags:")
        for f in result.get("green_flags", []):
            print(f"    \U0001f7e2 {f}")
        print(f"\n  Quality stocks: {result.get('quality_count')}")
        print(f"  Corp actions in window: {len(result.get('corporate_actions', []))}")
        print(f"  Insider activity (14d): {len(result.get('insider_activity', []))} records")
        print(f"{'='*60}")
        print(f"\n[Delta] ANALYSIS:\n{result.get('analysis', 'N/A')[:600]}...")
