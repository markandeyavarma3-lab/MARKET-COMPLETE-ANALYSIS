# -*- coding: utf-8 -*-
# MICC v2 -- Agent Epsilon: Options Intelligence
# Drop this file at: D:\MICC\agent_epsilon.py
#
# Screens:
#   1. OI Spike Screen    -- fo_data: stocks with OI today vs 5-day avg (1.5x threshold)
#   2. PCR Divergence     -- stock-level PCR today vs 5-day PCR baseline
#   3. High Gamma Near Price -- option_greeks_raw: strikes within 1.5% of spot with highest gamma
#   4. Nifty Summary      -- PCR/MaxPain/GEX snapshot
#
# Outputs: agents/epsilon/last_report.json + Telegram message
#
# Run standalone: py agent_epsilon.py
# Run with send:  py agent_epsilon.py --send
# Imported by:    micc_engine.py (Phase 5 hook)
#
# Rules:
#   - Never use get_conn() (Python 3.14 finally/conn bug)
#   - Always filter fo_data by date

import json
import sqlite3
import argparse
import warnings
from pathlib import Path

from micc_data import (
    call_llm, now_ist,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("agents/epsilon")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = r"D:/marketDB/db/market.db"


def qdb(sql, params=()):
    """Direct sqlite3 query -- never uses get_conn()."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  [Epsilon] DB error: {e}")
        return []
    finally:
        conn.close()


# =============================================================================
# SCREEN 1 -- OI Spike
# Stocks with unusual OI buildup today vs 5-day average
# =============================================================================

def screen_oi_spikes(latest_date):
    OI_SPIKE_RATIO   = 1.5    # 50% above average
    MIN_OI_THRESHOLD = 50000  # ignore tiny/illiquid OI

    prev_dates = qdb(
        "SELECT DISTINCT date FROM fo_data "
        "WHERE date < ? AND instrument IN ('OPTSTK','OPTIDX') AND symbol != 'NIFTY' "
        "ORDER BY date DESC LIMIT 5",
        (latest_date,)
    )
    if len(prev_dates) < 3:
        return []

    date_list = "','".join(r["date"] for r in prev_dates)

    rows = qdb(f"""
        SELECT
          t.symbol,
          t.option_typ,
          SUM(t.open_int)   AS today_oi,
          AVG(h.hist_oi)    AS avg_oi
        FROM fo_data t
        JOIN (
          SELECT symbol, option_typ,
                 SUM(open_int) AS hist_oi
          FROM fo_data
          WHERE date IN ('{date_list}')
            AND instrument IN ('OPTSTK','OPTIDX')
            AND symbol != 'NIFTY'
          GROUP BY symbol, option_typ, date
        ) h ON t.symbol = h.symbol AND t.option_typ = h.option_typ
        WHERE t.date = '{latest_date}'
          AND t.instrument IN ('OPTSTK','OPTIDX')
          AND t.symbol != 'NIFTY'
        GROUP BY t.symbol, t.option_typ
        HAVING today_oi >= {MIN_OI_THRESHOLD}
          AND avg_oi > 0
          AND (CAST(today_oi AS REAL) / avg_oi) >= {OI_SPIKE_RATIO}
        ORDER BY (CAST(today_oi AS REAL) / avg_oi) DESC
        LIMIT 20
    """)

    result = []
    for r in rows:
        spike = round(r["today_oi"] / r["avg_oi"], 2) if r["avg_oi"] else None
        result.append({
            "symbol":     r["symbol"],
            "option_typ": r["option_typ"],
            "today_oi":   int(r["today_oi"]),
            "avg_oi":     round(float(r["avg_oi"]), 0),
            "spike_ratio":spike,
            "signal":     "CALL_BUILDUP" if r["option_typ"] == "CE" else "PUT_BUILDUP",
        })
    return result


# =============================================================================
# SCREEN 2 -- PCR Divergence
# Stock PCR today vs 5-day PCR baseline
# =============================================================================

def screen_pcr_divergence(latest_date):
    prev_dates = qdb(
        "SELECT DISTINCT date FROM fo_data "
        "WHERE date < ? AND instrument IN ('OPTSTK','OPTIDX') AND symbol != 'NIFTY' "
        "ORDER BY date DESC LIMIT 5",
        (latest_date,)
    )
    if len(prev_dates) < 3:
        return []

    date_list = "','".join(r["date"] for r in prev_dates)

    today_pcr = qdb(f"""
        SELECT symbol,
          SUM(CASE WHEN option_typ='CE' THEN open_int ELSE 0 END) AS call_oi,
          SUM(CASE WHEN option_typ='PE' THEN open_int ELSE 0 END) AS put_oi
        FROM fo_data
        WHERE date = '{latest_date}'
          AND instrument IN ('OPTSTK','OPTIDX')
          AND symbol != 'NIFTY'
        GROUP BY symbol
        HAVING call_oi > 10000
    """)

    hist_pcr = qdb(f"""
        SELECT symbol, date,
          SUM(CASE WHEN option_typ='CE' THEN open_int ELSE 0 END) AS call_oi,
          SUM(CASE WHEN option_typ='PE' THEN open_int ELSE 0 END) AS put_oi
        FROM fo_data
        WHERE date IN ('{date_list}')
          AND instrument IN ('OPTSTK','OPTIDX')
          AND symbol != 'NIFTY'
        GROUP BY symbol, date
    """)

    from collections import defaultdict
    hist_map = defaultdict(list)
    for r in hist_pcr:
        if r["call_oi"] and float(r["call_oi"]) > 0:
            hist_map[r["symbol"]].append(float(r["put_oi"] or 0) / float(r["call_oi"]))

    result = []
    for t in today_pcr:
        sym = t["symbol"]
        if not t["call_oi"] or float(t["call_oi"]) <= 0:
            continue
        today_p = float(t["put_oi"] or 0) / float(t["call_oi"])
        hist_list = hist_map.get(sym, [])
        if len(hist_list) < 3:
            continue
        avg_p = sum(hist_list) / len(hist_list)
        div   = today_p - avg_p
        if abs(div) < 0.3:
            continue
        result.append({
            "symbol":     sym,
            "today_pcr":  round(today_p, 3),
            "avg_pcr":    round(avg_p, 3),
            "divergence": round(div, 3),
            "signal":     "BULLISH_SHIFT" if div > 0.3 else "BEARISH_SHIFT",
        })

    result.sort(key=lambda x: abs(x["divergence"]), reverse=True)
    return result[:15]


# =============================================================================
# SCREEN 3 -- High Gamma Near Price
# Strikes within 1.5% of spot with highest gamma
# =============================================================================

def screen_high_gamma_near_price(latest_date):
    rows = qdb(f"""
        SELECT
          symbol, strike, option_type,
          underlying_price AS spot,
          gamma, delta, iv, theta
        FROM option_greeks_raw
        WHERE date = '{latest_date}'
          AND gamma IS NOT NULL
          AND underlying_price IS NOT NULL
          AND underlying_price > 0
          AND ABS((CAST(strike AS REAL) - underlying_price) / underlying_price) <= 0.015
        ORDER BY gamma DESC
        LIMIT 20
    """)

    result = []
    for r in rows:
        spot = float(r["spot"] or 0)
        dist_pct = round((float(r["strike"]) - spot) / spot * 100, 2) if spot > 0 else None
        result.append({
            "symbol":      r["symbol"],
            "strike":      float(r["strike"]),
            "option_type": r["option_type"],
            "spot":        spot,
            "dist_pct":    dist_pct,
            "gamma":       round(float(r["gamma"] or 0), 6),
            "delta":       round(float(r["delta"] or 0), 4) if r["delta"] else None,
            "iv":          round(float(r["iv"] or 0) * 100, 1) if r["iv"] else None,
        })
    return result


# =============================================================================
# NIFTY SUMMARY
# =============================================================================

def nifty_summary(latest_date):
    exp_row = qdb(
        "SELECT MIN(expiry) AS exp FROM fo_data "
        "WHERE date=? AND symbol='NIFTY' AND instrument IN ('OPTIDX','IDO') AND expiry>=?",
        (latest_date, latest_date)
    )
    expiry = exp_row[0]["exp"] if exp_row and exp_row[0]["exp"] else None
    if not expiry:
        return {}

    pcr_rows = qdb(
        "SELECT option_typ, SUM(open_int) AS oi FROM fo_data "
        "WHERE date=? AND symbol='NIFTY' AND instrument IN ('OPTIDX','IDO') AND expiry=? "
        "GROUP BY option_typ",
        (latest_date, expiry)
    )
    call_oi = next((float(r["oi"] or 0) for r in pcr_rows if r["option_typ"] == "CE"), 0.0)
    put_oi  = next((float(r["oi"] or 0) for r in pcr_rows if r["option_typ"] == "PE"), 0.0)
    pcr     = round(put_oi / call_oi, 3) if call_oi > 0 else None

    all_s = qdb(
        "SELECT strike, "
        "SUM(CASE WHEN option_typ='CE' THEN COALESCE(open_int,0) END) AS co, "
        "SUM(CASE WHEN option_typ='PE' THEN COALESCE(open_int,0) END) AS po "
        "FROM fo_data "
        "WHERE date=? AND symbol='NIFTY' AND instrument IN ('OPTIDX','IDO') AND expiry=? "
        "GROUP BY strike ORDER BY strike",
        (latest_date, expiry)
    )

    max_pain = None
    if all_s:
        min_loss = float("inf")
        for row in all_s:
            K    = float(row["strike"])
            loss = sum(
                (K - float(r["strike"])) * float(r["co"] or 0) if float(r["strike"]) < K else
                (float(r["strike"]) - K) * float(r["po"] or 0) if float(r["strike"]) > K else 0
                for r in all_s
            )
            if loss < min_loss:
                min_loss = loss
                max_pain = int(K)

    gex_row = qdb(
        "SELECT SUM(gamma_exposure) AS gex FROM gamma_exposure_daily "
        "WHERE date=(SELECT MAX(date) FROM gamma_exposure_daily WHERE symbol='NIFTY') "
        "AND symbol='NIFTY'"
    )
    net_gex = int(gex_row[0]["gex"] or 0) if gex_row and gex_row[0]["gex"] is not None else 0

    nifty_row = qdb(
        "SELECT closing_index_value AS close, change "
        "FROM market_snapshot "
        "WHERE index_name='Nifty 50' AND date=(SELECT MAX(date) FROM market_snapshot) "
        "LIMIT 1"
    )
    nifty_close  = round(float(nifty_row[0]["close"]), 2)  if nifty_row and nifty_row[0].get("close")  else None
    nifty_change = round(float(nifty_row[0]["change"]), 2) if nifty_row and nifty_row[0].get("change") else None

    return {
        "date":         latest_date,
        "expiry":       expiry,
        "pcr":          pcr,
        "max_pain":     max_pain,
        "net_gex":      net_gex,
        "call_oi":      int(call_oi),
        "put_oi":       int(put_oi),
        "nifty_close":  nifty_close,
        "nifty_change": nifty_change,
    }


# =============================================================================
# LLM SYNTHESIS
# =============================================================================

def build_epsilon_analysis(oi_spikes, pcr_div, gamma_near, nifty_sum):
    spike_syms = ", ".join(
        f"{r['symbol']}({r['option_typ']} x{r['spike_ratio']})"
        for r in oi_spikes[:5]
    )
    div_syms = ", ".join(
        f"{r['symbol']}(PCR {r['today_pcr']:.2f} vs avg {r['avg_pcr']:.2f})"
        for r in pcr_div[:5]
    )
    gamma_syms = ", ".join(
        f"{r['symbol']} {int(r['strike'])}{r['option_type']} g={r['gamma']:.5f}"
        for r in gamma_near[:4]
    )

    ns = nifty_sum
    nifty_str = (
        f"Nifty {ns.get('nifty_close')} "
        f"PCR={ns.get('pcr')} MaxPain={ns.get('max_pain')} "
        f"GEX={'LONG' if (ns.get('net_gex') or 0) > 0 else 'SHORT'} gamma"
    ) if ns else "Nifty: no data"

    prompt = (
        "You are an institutional options desk analyst. "
        "Summarize these NSE options signals in 5-6 lines.\n\n"
        f"NIFTY: {nifty_str}\n\n"
        f"OI SPIKES (buildup today vs 5d avg): {spike_syms or 'None'}\n\n"
        f"PCR DIVERGENCE (positioning shift): {div_syms or 'None'}\n\n"
        f"HIGH GAMMA NEAR PRICE: {gamma_syms or 'None'}\n\n"
        "Cover: what OI spikes suggest, PCR divergence signals, "
        "gamma strikes to watch as volatility catalysts, one overall observation.\n"
        "5-6 lines, no bullet points, institutional tone."
    )

    try:
        return call_llm(prompt, max_tokens=350)
    except Exception as e:
        print(f"  [Epsilon] LLM failed: {e}")
        return (
            f"OI spikes: {spike_syms or 'none'}. "
            f"PCR shifts: {div_syms or 'none'}. "
            f"Gamma zones: {gamma_syms or 'none'}."
        )


# =============================================================================
# TELEGRAM FORMATTER
# =============================================================================

def fmt_oi(v):
    if not v:
        return "--"
    n = float(v)
    if n >= 1e7: return f"{n/1e7:.1f}Cr"
    if n >= 1e5: return f"{n/1e5:.1f}L"
    return f"{n/1e3:.0f}K"


def fmt_gex(v):
    a = abs(v)
    if a >= 1e9: return f"{v/1e9:.2f}B"
    if a >= 1e6: return f"{v/1e6:.2f}M"
    return f"{int(v):,}"


def format_epsilon_telegram(report):
    import re
    ns  = report.get("nifty_summary", {})
    ois = report.get("oi_spikes", [])
    pcr = report.get("pcr_divergence", [])
    gma = report.get("gamma_near_price", [])
    ai  = report.get("analysis", "")

    nifty_close  = ns.get("nifty_close")
    nifty_change = ns.get("nifty_change", 0) or 0

    lines = [
        "*OPTIONS INTELLIGENCE -- AGENT EPSILON*",
        f"`{ns.get('date','?')}  |  Expiry: {ns.get('expiry','?')}`",
        "",
    ]

    if nifty_close:
        sign = "+" if nifty_change >= 0 else ""
        lines.append(f"*NIFTY:* `{nifty_close:,}` ({sign}{nifty_change:.2f}%)")
    lines.append(
        f"PCR: `{ns.get('pcr','--')}`  MaxPain: `{ns.get('max_pain','--')}`"
        f"  GEX: `{'LONG' if (ns.get('net_gex') or 0) > 0 else 'SHORT'}`"
    )
    lines.append("")

    if ois:
        lines.append("*OI SPIKES (unusual buildup):*")
        for r in ois[:6]:
            icon = "BEAR" if r["option_typ"] == "CE" else "BULL"
            sym  = str(r["symbol"]).replace("_", "\\_")
            lines.append(
                f"  {icon} `{sym:<12}` {r['option_typ']} x{r['spike_ratio']}"
                f"  OI:{fmt_oi(r['today_oi'])}"
            )
        lines.append("")

    if pcr:
        lines.append("*PCR DIVERGENCE:*")
        for r in pcr[:4]:
            icon = "+" if r["signal"] == "BULLISH_SHIFT" else "-"
            sym  = str(r["symbol"]).replace("_", "\\_")
            lines.append(
                f"  {icon} `{sym:<12}` PCR {r['today_pcr']:.2f}"
                f" vs avg {r['avg_pcr']:.2f} ({r['signal'].replace('_',' ')})"
            )
        lines.append("")

    if gma:
        lines.append("*HIGH GAMMA NEAR PRICE:*")
        for r in gma[:4]:
            dist = f"{r['dist_pct']:+.2f}%" if r["dist_pct"] is not None else "--"
            sym  = str(r["symbol"]).replace("_", "\\_")
            lines.append(
                f"  `{sym} {int(r['strike'])}{r['option_type']}`"
                f" spot{dist}  gamma:{r['gamma']:.5f}"
            )
        lines.append("")

    if ai:
        ai_clean = re.sub(r"\*\*(.+?)\*\*", r"\1", ai)
        if len(ai_clean) > 600:
            ai_clean = ai_clean[:600] + "...(truncated)"
        lines += ["*Analysis:*", ai_clean, ""]

    lines.append("_Agent Epsilon -- Options Intelligence_")
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def run_epsilon(send=False):
    print("=" * 55)
    print("  AGENT EPSILON -- Options Intelligence")
    print("=" * 55)

    latest_rows = qdb(
        "SELECT MAX(date) AS d FROM fo_data "
        "WHERE instrument IN ('OPTIDX','IDO','OPTSTK') AND symbol='NIFTY'"
    )
    latest_date = latest_rows[0]["d"] if latest_rows and latest_rows[0]["d"] else None
    if not latest_date:
        print("  [WARN] No options data in fo_data. Run daily_update.py first.")
        return {}

    print(f"  Latest options date: {latest_date}")

    print("  Screen 1: OI Spikes...")
    oi_spikes = screen_oi_spikes(latest_date)
    print(f"    {len(oi_spikes)} spikes found")

    print("  Screen 2: PCR Divergence...")
    pcr_div = screen_pcr_divergence(latest_date)
    print(f"    {len(pcr_div)} divergences found")

    print("  Screen 3: High Gamma Near Price...")
    gamma_near = screen_high_gamma_near_price(latest_date)
    print(f"    {len(gamma_near)} gamma zones found")

    print("  Nifty Summary...")
    nifty_sum = nifty_summary(latest_date)

    print("  LLM Analysis...")
    analysis = build_epsilon_analysis(oi_spikes, pcr_div, gamma_near, nifty_sum)

    report = {
        "timestamp":        now_ist(),
        "date":             latest_date,
        "nifty_summary":    nifty_sum,
        "oi_spikes":        oi_spikes,
        "pcr_divergence":   pcr_div,
        "gamma_near_price": gamma_near,
        "analysis":         analysis,
    }

    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {out}")

    if send:
        try:
            import requests as _req
            msg = format_epsilon_telegram(report)
            _req.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id":                  TELEGRAM_CHAT_ID,
                    "text":                     msg,
                    "parse_mode":               "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            print("  Telegram sent.")
        except Exception as e:
            print(f"  [WARN] Telegram send failed: {e}")

    print("=" * 55)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Send result to Telegram")
    args = parser.parse_args()
    run_epsilon(send=args.send)
