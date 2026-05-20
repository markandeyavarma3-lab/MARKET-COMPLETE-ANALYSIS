# -*- coding: utf-8 -*-
"""
MICC — Telegram Bot
Sends Alpha (regime) + Beta (screener) + Gamma (FII/DII flow) morning report at 9:15 AM IST.
Also listens for /report, /alpha, /beta, /gamma, /status commands anytime.

Usage (PowerShell):
    $env:TELEGRAM_BOT_TOKEN="your_token"
    $env:TELEGRAM_CHAT_ID="your_chat_id"
    py telegram_bot.py
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")
IST          = ZoneInfo("Asia/Kolkata")

ALPHA_REPORT = Path("agents/alpha/last_report.json")
BETA_REPORT  = Path("agents/beta/last_report.json")
GAMMA_REPORT = Path("agents/gamma/last_report.json")
MAX_MSG_LEN  = 4000

# ── Create required dirs ───────────────────────────────────────────────────────
Path("agents/bot").mkdir(parents=True, exist_ok=True)
Path("agents/eta").mkdir(parents=True, exist_ok=True)
Path("agents/iota").mkdir(parents=True, exist_ok=True)
Path("agents/kappa").mkdir(parents=True, exist_ok=True)
Path("agents/alpha").mkdir(parents=True, exist_ok=True)
Path("agents/beta").mkdir(parents=True, exist_ok=True)
Path("agents/gamma").mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agents/bot/bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("MICC-Bot")


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path):
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not load {path}: {e}")
        return None


def _pct(val, decimals=2) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.{decimals}f}%"
    except Exception:
        return str(val)


def _cr(val, decimals=0) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:,.{decimals}f}Cr"
    except Exception:
        return str(val)


def _esc(text: str) -> str:
    """
    Escape for Telegram Markdown v1.
    ONLY escape: _ * ` [
    Do NOT escape ( ) - . ! # — those are Markdown v2 syntax only.
    """
    if not text:
        return ""
    for ch in ["_", "*", "`", "["]:
        text = text.replace(ch, "\\" + ch)
    return text


def _clean_ai(text: str, max_len: int = 650) -> str:
    """
    Prepare AI text for safe Markdown v1 rendering:
    1. Strip **bold** markers (gemma/qwen emit these, break Telegram Markdown)
    2. Escape v1 special chars
    3. Truncate at newline boundary
    """
    if not text:
        return "N/A"
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    if len(text) > max_len:
        cut = text[:max_len]
        nl  = cut.rfind("\n")
        if nl > max_len // 2:
            cut = cut[:nl]
        text = cut + "\n(truncated)"
    return _esc(text)


def _to_list(data) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "stocks", "results", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        vals = list(data.values())
        if vals and isinstance(vals[0], dict):
            return vals
        return []
    return []


def _regime_emoji(regime: str) -> str:
    return {
        "TRENDING_UP":     "🟢",
        "TRENDING_DOWN":   "🔴",
        "HIGH_VOLATILITY": "⚡",
        "CONSOLIDATION":   "🟡",
        "MEAN_REVERTING":  "🔄",
    }.get((regime or "").upper(), "⚪")


def _flow_emoji(sentiment: str) -> str:
    return {
        "STRONG_BULL": "🟢🟢",
        "BULL":        "🟢",
        "NEUTRAL":     "⚪",
        "BEAR":        "🔴",
        "STRONG_BEAR": "🔴🔴",
    }.get((sentiment or "").upper(), "⚪")


# ── Formatters ────────────────────────────────────────────────────────────────

def format_alpha_section(alpha: dict) -> str:
    if not alpha:
        return "⚠️ *Agent Alpha* - No report found. Run `py agent_alpha.py` first.\n"

    m     = alpha.get("regime_metrics", {}) or {}
    b     = alpha.get("breadth_analytics", {}) or {}
    r     = alpha.get("cap_rotation", {}) or {}
    ai    = alpha.get("regime_analysis", "") or ""
    mdate = alpha.get("latest_market_date", "?")

    regime     = "UNKNOWN"
    confidence = ""
    for line in ai.splitlines():
        u = line.upper()
        for reg in ["TRENDING_UP", "TRENDING_DOWN", "HIGH_VOLATILITY", "CONSOLIDATION", "MEAN_REVERTING"]:
            if reg in u:
                regime = reg
                break
        if "CONFIDENCE" in u:
            for conf in ["HIGH", "MEDIUM", "LOW"]:
                if conf in u:
                    confidence = conf
                    break

    re_emoji = _regime_emoji(regime)
    adv      = b.get("advancing", 0) or 0
    dec      = b.get("declining", 0) or 0
    adv_pct  = b.get("breadth_pct_advancing", 0) or 0
    conf_str = f" [{confidence}]" if confidence else ""

    lines = [
        f"*{re_emoji} AGENT ALPHA - MACRO/REGIME*",
        f"📅 Market Date: `{mdate}`",
        "",
        f"*NIFTY 50:* `{m.get('nifty50_close', 'N/A')}`",
        f"  1d: `{_pct(m.get('return_1d_pct'))}` | 5d: `{_pct(m.get('return_5d_pct'))}` | 20d: `{_pct(m.get('return_20d_pct'))}`",
        f"  MA20: `{m.get('ma20','N/A')}` {'✅' if m.get('above_ma20') else '❌'}  MA50: `{m.get('ma50','N/A')}` {'✅' if m.get('above_ma50') else '❌'}",
        f"  Vol: `{m.get('volatility_20d_annualized_pct','N/A')}%`  PE: `{m.get('pe','N/A')}` PB: `{m.get('pb','N/A')}`",
        "",
        f"*BREADTH:* {adv}up {dec}dn ({adv_pct:.1f}% advancing)",
        f"  A/D: `{b.get('advance_decline_ratio','N/A')}` | Indices: `{b.get('total_indices','N/A')}`",
    ]

    top3 = b.get("top3_performers") or []
    bot3 = b.get("bottom3_performers") or []
    if top3:
        top_str = "  ".join(
            f"`{_esc(str(x.get('index_name','?')).split(' ')[-1])}` {_pct(x.get('change'),1)}"
            for x in top3
        )
        lines.append(f"  🏆 Top: {top_str}")
    if bot3:
        bot_str = "  ".join(
            f"`{_esc(str(x.get('index_name','?')).split(' ')[-1])}` {_pct(x.get('change'),1)}"
            for x in bot3
        )
        lines.append(f"  📉 Bot: {bot_str}")

    lc      = r.get("largecap_avg_change")
    mc      = r.get("midcap_avg_change")
    sc      = r.get("smallcap_avg_change")
    rot_sig = _esc(str(r.get("rotation_signal", "N/A")))

    lines += [
        "",
        f"*ROTATION:* {rot_sig}",
        f"  L: `{_pct(lc,1)}` | M: `{_pct(mc,1)}` | S: `{_pct(sc,1)}`",
        "",
        f"*REGIME:* `{regime}`{conf_str}",
        "",
        "--- AI Analysis ---",
        _clean_ai(ai, 650),
        "-------------------",
    ]
    return "\n".join(lines)


def format_beta_section(beta: dict) -> str:
    if not beta:
        return "⚠️ *Agent Beta* - No report found. Run `py agent_beta.py` first.\n"

    screens = beta.get("screens", {}) or {}
    ai      = beta.get("analysis", "") or beta.get("screener_analysis", "") or ""
    mdate   = (beta.get("end_date") or beta.get("latest_market_date") or "?")
    regime_used = beta.get("regime_used", "DEFAULT")
    run_regime  = beta.get("regime", "") or "DEFAULT"

    def fmt_screen(name: str, emoji: str, key: str, max_show: int = 5) -> list:
        raw  = screens.get(key)
        data = _to_list(raw)
        if not data:
            return [f"{emoji} *{name}:* no picks today"]

        out = [f"{emoji} *{name}* ({len(data)} picks):"]
        for row in data[:max_show]:
            if not isinstance(row, dict):
                continue
            sym      = row.get("SYMBOL") or row.get("symbol") or "?"
            close    = row.get("CLOSE_PRICE") or row.get("CLOSE") or row.get("close")
            score    = row.get("composite_score") or row.get("score")
            ret5     = row.get("RETURN_5D_PCT") or row.get("return_5d_pct") or row.get("pct_chg")
            screens_ = row.get("screens", "")
            streak   = row.get("streak", 0)
            eps_flag = row.get("earnings_flag", "")

            parts = [f"`{_esc(str(sym))}`"]
            if ret5:
                try:
                    parts.append(f"{float(ret5):+.1f}%")
                except Exception:
                    pass
            if score:
                try:
                    parts.append(f"sc:{int(float(score))}")
                except Exception:
                    pass
            if streak and int(streak) >= 3:
                parts.append(f"🔥{int(streak)}d")
            if eps_flag == "PROFITABLE":
                parts.append("✅EPS")
            elif eps_flag == "LOSS_MAKING":
                parts.append("🔴EPS")
            if screens_:
                # wrap in backticks so _ chars don't break Markdown italic parsing
                tag = str(screens_)[:28].replace("`", "")
                parts.append(f"`{tag}`")
            out.append("  " + "  ".join(parts))

        if len(data) > max_show:
            out.append(f"  (+{len(data) - max_show} more)")
        return out

    # Regime pill
    re_emoji = _regime_emoji(run_regime)
    regime_line = f"*Regime:* {re_emoji} `{run_regime}` → thresholds: `{regime_used}`"

    # EPS summary
    composite_data = _to_list(screens.get("composite"))
    profitable_ct  = sum(1 for r in composite_data if isinstance(r, dict) and r.get("earnings_flag") == "PROFITABLE")
    loss_ct        = sum(1 for r in composite_data if isinstance(r, dict) and r.get("earnings_flag") == "LOSS_MAKING")
    streak_ct      = sum(1 for r in composite_data if isinstance(r, dict) and int(r.get("streak", 0) or 0) >= 3)

    lines = [
        "*🔍 AGENT BETA - STOCK SCREENER*",
        f"📅 Market Date: `{mdate}`",
        regime_line,
        f"*Summary:* ✅ {profitable_ct} profitable | 🔴 {loss_ct} loss | 🔥 {streak_ct} streak≥3",
        "",
    ]
    lines += fmt_screen("MOMENTUM", "🚀", "momentum")
    lines.append("")
    lines += fmt_screen("DELIVERY", "📦", "delivery")
    lines.append("")
    lines += fmt_screen("BREAKOUT", "💥", "breakouts")
    lines.append("")

    sector = screens.get("sector") or {}
    if isinstance(sector, dict) and sector.get("top_sectors"):
        top_s = sector["top_sectors"][:3]
        lines.append("🏭 *SECTORS:*")
        lines.append("  TOP: " + " | ".join(
            f"`{_esc(str(s.get('INDEX_NAME', s.get('index_name','?')))[:15])}` {_pct(s.get('AVG_CHANGE', s.get('avg_change')),1)}"
            for s in top_s
        ))
        lines.append("")

    lines += fmt_screen("COMPOSITE", "⭐", "composite", max_show=8)
    lines += [
        "",
        "--- AI Synthesis ---",
        _clean_ai(ai, 600),
        "--------------------",
    ]
    return "\n".join(lines)


def format_gamma_section(gamma: dict) -> str:
    if not gamma:
        return "⚠️ *Agent Gamma* - No report found. Run `py agent_gamma.py` first.\n"

    eq    = gamma.get("eq_flow", {}) or {}
    fno   = gamma.get("fno_positioning", {}) or {}
    fs    = gamma.get("flow_score", {}) or {}
    ai    = gamma.get("flow_analysis", "") or ""
    mdate = gamma.get("latest_market_date", "?")

    sentiment = fs.get("flow_sentiment", "NEUTRAL")
    score_val = fs.get("flow_score", 0)
    fe        = _flow_emoji(sentiment)
    score_bar = "█" * abs(score_val) + "░" * (10 - abs(score_val))
    score_dir = "+" if score_val >= 0 else "-"

    lines = [
        f"*{fe} AGENT GAMMA - FII/DII FLOW*",
        f"📅 Market Date: `{mdate}`",
        "",
        f"*FLOW SCORE:* `{score_val:+}/10` -> `{sentiment}`",
        f"  `{score_dir}{score_bar}`",
        "",
    ]

    if not eq.get("error"):
        fii_net  = eq.get("fii_net_today_cr")
        dii_net  = eq.get("dii_net_today_cr")
        inst_net = eq.get("inst_net_today_cr")
        fii_dir  = eq.get("fii_direction", "?")
        dii_dir  = eq.get("dii_direction", "?")
        fii_icon = "🟢" if fii_dir == "BUY" else "🔴" if fii_dir == "SELL" else "⚪"
        dii_icon = "🟢" if dii_dir == "BUY" else "🔴" if dii_dir == "SELL" else "⚪"
        n_days   = eq.get("days_available", 0)

        lines += [
            "*CASH MARKET (Rs Cr):*",
            f"  {fii_icon} FII: `{_cr(fii_net)}` [{fii_dir}]",
            f"  {dii_icon} DII: `{_cr(dii_net)}` [{dii_dir}]",
            f"  Combined: `{_cr(inst_net)}`",
            "",
            f"*{n_days}-Day Cumulative:*",
            f"  FII: `{_cr(eq.get('fii_cumulative_net_cr'))}`  DII: `{_cr(eq.get('dii_cumulative_net_cr'))}`",
            f"  FII streak: `{eq.get('fii_consecutive_buy_days',0)}` buy / `{eq.get('fii_consecutive_sell_days',0)}` sell days",
            "",
        ]

        if eq.get("fii_dii_divergence"):
            lines.append(f"⚠️ *FII/DII DIVERGENCE:* FII={fii_dir} vs DII={dii_dir}")
            lines.append("")

        hist = eq.get("flow_history", [])
        if hist:
            lines.append("*Recent Flow (Rs Cr):*")
            for row in hist[-5:]:
                fn   = _cr(row.get("fii_net"))
                dn   = _cr(row.get("dii_net"))
                icon = "🟢" if (row.get("fii_net") or 0) > 0 else "🔴"
                lines.append(f"  {icon} `{row['date']}` FII:{fn} DII:{dn}")
            lines.append("")
    else:
        lines.append(f"⚠️ {_esc(eq.get('error', 'No EQ data'))}")
        lines.append("")

    if fno and fno.get("positions"):
        lines.append("*F&O POSITIONING:*")
        for participant, pos in fno["positions"].items():
            b_icon = "🟢" if pos["bias"] == "LONG" else "🔴" if pos["bias"] == "SHORT" else "⚪"
            lines.append(
                f"  {b_icon} `{participant}` {pos['bias']}  net: `{pos['total_net_contracts']:+,}` contracts"
            )
        if fno.get("fii_pro_divergence"):
            lines.append(f"  ⚡ FII={fno.get('fii_fno_bias')} vs Pro={fno.get('pro_fno_bias')} (contra signal)")
        lines.append("")

    signals = fs.get("score_components", [])
    if signals:
        lines.append("*Signals:*")
        for sig in signals[:5]:
            lines.append(f"  - {_esc(sig)}")
        lines.append("")

    lines += [
        "--- AI Analysis ---",
        _clean_ai(ai, 600),
        "-------------------",
    ]
    return "\n".join(lines)




def format_delta_section(delta: dict) -> str:
    if not delta:
        return "⚠️ *Agent Delta* - No report found. Run `py agent_delta.py` first.\n"

    alerts    = delta.get("alerts", []) or []
    insider   = delta.get("insider_activity", []) or []
    risk      = delta.get("risk_metrics", {}) or {}
    ai        = delta.get("risk_analysis", "") or delta.get("analysis", "") or ""
    mdate     = (delta.get("end_date") or delta.get("latest_market_date") or "?")

    lines = [
        "*🛡️ AGENT DELTA - RISK & ALERTS*",
        f"📅 Market Date: `{mdate}`",
        "",
    ]

    # Risk metrics
    vix = risk.get("india_vix") or risk.get("vix")
    if vix:
        vix_emoji = "🔴" if float(vix) > 20 else "🟡" if float(vix) > 15 else "🟢"
        lines.append(f"*India VIX:* {vix_emoji} `{vix}`")

    pcr = risk.get("pcr") or risk.get("put_call_ratio")
    if pcr:
        pcr_emoji = "🔴" if float(pcr) > 1.2 else "🟡" if float(pcr) > 0.8 else "🟢"
        lines.append(f"*PCR:* {pcr_emoji} `{pcr}`")

    if vix or pcr:
        lines.append("")

    # Price alerts
    if alerts:
        lines.append(f"*🚨 ALERTS ({len(alerts)}):*")
        for a in alerts[:6]:
            if not isinstance(a, dict):
                lines.append(f"  • {_esc(str(a)[:60])}")
                continue
            sym   = a.get("symbol", "?")
            atype = a.get("alert_type") or a.get("type", "?")
            msg   = a.get("message") or a.get("msg", "")
            icon  = "🚨" if "breakdown" in str(atype).lower() else "⚡" if "breakout" in str(atype).lower() else "⚠️"
            lines.append(f"  {icon} `{_esc(str(sym))}` {_esc(str(atype)[:20])}")
            if msg:
                lines.append(f"     {_esc(str(msg)[:50])}")
        if len(alerts) > 6:
            lines.append(f"  (+{len(alerts)-6} more alerts)")
        lines.append("")
    else:
        lines.append("*🚨 ALERTS:* none today")
        lines.append("")

    # Insider trading
    if insider:
        lines.append(f"*👤 INSIDER ACTIVITY ({len(insider)}):*")
        for row in insider[:5]:
            if not isinstance(row, dict):
                continue
            sym  = row.get("symbol", "?")
            name = str(row.get("name", "?"))[:18]
            txn  = row.get("transaction_type", "?")
            qty  = row.get("quantity")
            val  = row.get("value")
            icon = "🟢" if "buy" in str(txn).lower() or "acqui" in str(txn).lower() else "🔴"
            qty_str = f"{int(float(qty)):,}" if qty else "?"
            val_str = f"Rs{float(val)/1e5:.1f}L" if val else ""
            lines.append(f"  {icon} `{_esc(str(sym))}` {_esc(name)} {_esc(str(txn)[:10])} {qty_str}sh {val_str}")
        if len(insider) > 5:
            lines.append(f"  (+{len(insider)-5} more)")
        lines.append("")
    else:
        lines.append("*👤 INSIDER:* no recent activity")
        lines.append("")

    lines += [
        "--- AI Analysis ---",
        _clean_ai(ai, 500),
        "-------------------",
    ]
    return "\n".join(lines)

def format_footer(alpha, beta, gamma=None, delta=None) -> str:
    now  = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    a_ts = ((alpha or {}).get("timestamp") or "-")[:19]
    b_ts = ((beta  or {}).get("timestamp") or "-")[:19]
    g_ts = ((gamma or {}).get("timestamp") or "-")[:19]
    d_ts = ((delta or {}).get("timestamp") or "-")[:19]

    # Regime from alpha
    regime = ""
    ai_txt = (alpha or {}).get("regime_analysis", "") or ""
    for reg in ["TRENDING_UP","TRENDING_DOWN","HIGH_VOLATILITY","CONSOLIDATION","MEAN_REVERTING"]:
        if reg in ai_txt.upper():
            regime = reg
            break
    regime_str = f" | {_regime_emoji(regime)}{regime}" if regime else ""

    return (
        f"\n_Report: {now}{regime_str}_\n"
        f"_A:{a_ts}_\n"
        f"_B:{b_ts}_\n"
        f"_G:{g_ts}  D:{d_ts}_\n"
        f"_MICC v2.0_"
    )


DELTA_REPORT = Path("agents/delta/last_report.json")
Path("agents/delta").mkdir(parents=True, exist_ok=True)


def build_full_report() -> list:
    alpha = load_json(ALPHA_REPORT)
    beta  = load_json(BETA_REPORT)
    gamma = load_json(GAMMA_REPORT)
    delta = load_json(DELTA_REPORT)

    full = (
        "*🏛️ MICC MORNING INTELLIGENCE REPORT*\n"
        + "=" * 35 + "\n\n"
        + format_alpha_section(alpha)
        + "\n\n"
        + format_beta_section(beta)
        + "\n\n"
        + format_gamma_section(gamma)
        + "\n\n"
        + format_delta_section(delta)
        + "\n"
        + format_footer(alpha, beta, gamma, delta)
    )

    chunks = []
    while len(full) > MAX_MSG_LEN:
        split_at = full.rfind("\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        chunks.append(full[:split_at])
        full = full[split_at:].lstrip()
    chunks.append(full)
    return chunks


# ── Telegram handlers ─────────────────────────────────────────────────────────

async def send_chunks(bot: Bot, chat_id: str, chunks: list):
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.3)
        except Exception as e:
            log.error(f"Markdown send failed: {e} — retrying as plain text")
            try:
                plain = chunk.replace("*", "").replace("_", "").replace("`", "").replace("\\", "")
                await bot.send_message(chat_id=chat_id, text=plain)
            except Exception as e2:
                log.error(f"Plain text fallback also failed: {e2}")


# ── /conviction ──────────────────────────────────────────────────────────────
async def cmd_conviction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import sqlite3
    try:
        conn = sqlite3.connect('D:/marketDB/db/market.db', timeout=10)
        sql = (
            'SELECT c.symbol, c.conviction_score, c.top_reason, c.signal_count, st.close'
            ' FROM symbol_conviction c'
            ' LEFT JOIN ('
            '   SELECT symbol, close FROM stock_data'
            '   WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)'
            '   AND close IS NOT NULL'
            ' ) st ON st.symbol=c.symbol'
            ' WHERE c.conviction_score>=55'
            ' ORDER BY c.conviction_score DESC LIMIT 15'
        )
        rows = conn.execute(sql).fetchall()
        conn.close()
        lines = ['*MICC Conviction Top Picks*', '']
        for sym, score, reason, signals, close in rows:
            close_str = ' INR' + str(round(close,1)) if close else ''
            lines.append('`' + str(sym).ljust(12) + '` ' + str(round(score,1)).ljust(6) + '[' + str(reason) + '] ' + str(signals) + '/7' + close_str)
        msg = '\n'.join(lines)
    except Exception as e:
        msg = 'Error: ' + str(e)
    await update.message.reply_text(msg, parse_mode='Markdown')

# ── /portfolio ────────────────────────────────────────────────────────────────
async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import sqlite3
    try:
        conn = sqlite3.connect('D:/marketDB/db/market.db', timeout=10)
        sql = (
            'SELECT p.symbol, p.entry_price, p.quantity, p.stop_loss, p.target_1, st.close'
            ' FROM my_portfolio p'
            ' LEFT JOIN ('
            '   SELECT symbol, close FROM stock_data'
            '   WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)'
            '   AND close IS NOT NULL'
            ' ) st ON st.symbol=p.symbol'
            ' WHERE p.status=\'OPEN\' ORDER BY p.added_at DESC'
        )
        rows = conn.execute(sql).fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text('No open positions.')
            return
        total_unr = sum(((r[5] or r[1] or 0)-(r[1] or 0))*(r[2] or 0) for r in rows)
        lines = ['*MICC Portfolio -- ' + datetime.now().strftime('%Y-%m-%d') + '*',
                 str(len(rows)) + ' open | Unrealized: ' + '{:+.0f}'.format(total_unr), '']
        for sym, entry, qty, stop, t1, cur in rows:
            cur = cur or entry or 0
            pnl_pct = (cur-(entry or 0))/(entry or 1)*100
            ico = '+' if pnl_pct>0 else '-'
            lines.append(ico+' `'+str(sym).ljust(12)+'` '+'{:+.1f}%'.format(pnl_pct)+' stop='+str(round(stop or 0,1))+' T1='+str(round(t1 or 0,1)))
        msg = '\n'.join(lines)
    except Exception as e:
        msg = 'Error: ' + str(e)
    await update.message.reply_text(msg, parse_mode='Markdown')

# ── /exit ────────────────────────────────────────────────────────────────────
async def cmd_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import json
    from pathlib import Path
    try:
        p = Path('D:/MICC/agents/exit/last_report.json')
        if not p.exists():
            await update.message.reply_text('No exit report. Run agent_exit.py first.')
            return
        d = json.loads(p.read_text(encoding='utf-8'))
        alerts = d.get('alerts', [])
        if not alerts:
            await update.message.reply_text('No exit signals -- all positions within range.')
            return
        lines = ['*MICC Exit Signals -- ' + d.get('date','?') + '*', '']
        for a in alerts:
            lines.append('['+str(a.get('urgency','?'))+'] `'+str(a.get('symbol','?'))+'` '+str(a.get('signal',''))+' '+str(round(a.get('pnl_pct',0),1))+'%')
            lines.append('  '+str(a.get('message',''))[:60])
        msg = '\n'.join(lines)
    except Exception as e:
        msg = 'Error: ' + str(e)
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🏛️ *MICC - Market Intelligence Command Center*\n\n"
        "Daily NSE intelligence report at *9:15 AM IST*\n\n"
        "*Commands:*\n"
        "  /report - Full report (Alpha+Beta+Gamma+Delta)\n"
        "  /alpha  - Regime and macro only\n"
        "  /beta   - Stock screener + streak tags\n"
        "  /gamma  - FII/DII flow intelligence\n"
        "  /delta  - Risk alerts + insider activity\n"
        "  /streak - Top streak stocks leaderboard\n"
        "  /status - Data freshness + signals DB stats\n\n"
        "_Built for institutional-grade NSE analysis._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Generating report...")
    try:
        chunks = build_full_report()
        await send_chunks(ctx.bot, str(update.effective_chat.id), chunks)
    except Exception as e:
        log.error(f"cmd_report error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_alpha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        alpha = load_json(ALPHA_REPORT)
        text  = format_alpha_section(alpha)
        await send_chunks(ctx.bot, str(update.effective_chat.id), [text])
    except Exception as e:
        log.error(f"cmd_alpha error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_beta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        beta = load_json(BETA_REPORT)
        text = format_beta_section(beta)
        await send_chunks(ctx.bot, str(update.effective_chat.id), [text])
    except Exception as e:
        log.error(f"cmd_beta error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_gamma(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gamma = load_json(GAMMA_REPORT)
        text  = format_gamma_section(gamma)
        await send_chunks(ctx.bot, str(update.effective_chat.id), [text])
    except Exception as e:
        log.error(f"cmd_gamma error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_delta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        delta = load_json(DELTA_REPORT)
        text  = format_delta_section(delta)
        await send_chunks(ctx.bot, str(update.effective_chat.id), [text])
    except Exception as e:
        log.error(f"cmd_delta error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_streak(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Live streak leaderboard from signals_history DB."""
    import sqlite3 as _sl
    try:
        conn = _sl.connect(r"D:/marketDB/db/market.db")
        rows = conn.execute("""
            SELECT symbol, COUNT(DISTINCT run_date) as days,
                   MAX(run_date) as last_seen,
                   ROUND(AVG(score),1) as avg_score
            FROM signals_history
            GROUP BY symbol
            ORDER BY days DESC, avg_score DESC
            LIMIT 15
        """).fetchall()
        total_rows = conn.execute("SELECT COUNT(*) FROM signals_history").fetchone()[0]
        n_dates    = conn.execute("SELECT COUNT(DISTINCT run_date) FROM signals_history").fetchone()[0]
        last_date  = conn.execute("SELECT MAX(run_date) FROM signals_history").fetchone()[0]
        conn.close()

        if not rows:
            await update.message.reply_text("signals_history is empty — run agent_beta.py first.")
            return

        lines = [
            "*🔥 STREAK LEADERBOARD*",
            f"`{total_rows} rows | {n_dates} dates | last: {last_date}`",
            "",
        ]
        for sym, days, last_seen, avg_sc in rows:
            bar   = "█" * min(days, 15)
            flame = "🔥" if days >= 5 else "📈" if days >= 3 else "·"
            lines.append(f"{flame} `{_esc(str(sym)):<12}` {days:>2}d  sc~{avg_sc}  `{bar}`")

        lines += ["", "_Use /beta for full composite with streak tags_"]
        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_streak error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Plain text only - zero markdown - zero parse errors."""
    import sqlite3 as _sl
    now = datetime.now(IST).strftime("%d %b %Y %H:%M IST")

    def file_status(path: Path) -> str:
        if not path.exists():
            return "❌ Missing"
        data = load_json(path)
        if not data:
            return "⚠️ Corrupt"
        ts    = (data.get("timestamp") or "")[:16]
        mdate = (data.get("latest_market_date") or data.get("end_date") or "?")
        return f"✅ {ts} (market: {mdate})"

    gamma_data  = load_json(GAMMA_REPORT)
    gamma_extra = ""
    if gamma_data:
        fs        = gamma_data.get("flow_score", {}) or {}
        score     = fs.get("flow_score", "?")
        sentiment = fs.get("flow_sentiment", "?")
        gamma_extra = f" | {score}/10 {sentiment}"

    # signals_history stats
    sig_stats = "unavailable"
    try:
        conn = _sl.connect(r"D:/marketDB/db/market.db")
        total   = conn.execute("SELECT COUNT(*) FROM signals_history").fetchone()[0]
        n_dates = conn.execute("SELECT COUNT(DISTINCT run_date) FROM signals_history").fetchone()[0]
        last_dt = conn.execute("SELECT MAX(run_date) FROM signals_history").fetchone()[0]
        conn.close()
        sig_stats = f"{total} rows | {n_dates} dates | last: {last_dt}"
    except Exception:
        pass

    # Beta regime
    beta_data = load_json(BETA_REPORT)
    regime_str = ""
    if beta_data:
        r = beta_data.get("regime", "") or beta_data.get("regime_used", "")
        if r:
            regime_str = f" | regime: {r}"

    msg = (
        f"🔧 MICC BOT STATUS\n"
        f"Time: {now}\n\n"
        f"Alpha: {file_status(ALPHA_REPORT)}\n"
        f"Beta:  {file_status(BETA_REPORT)}{regime_str}\n"
        f"Gamma: {file_status(GAMMA_REPORT)}{gamma_extra}\n"
        f"Delta: {file_status(DELTA_REPORT)}\n\n"
        f"Signals DB: {sig_stats}\n\n"
        f"Commands: /report /alpha /beta /gamma /delta /streak /status"
    )
    await update.message.reply_text(msg)




# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 COMMANDS  (added by phase5_build.py)
# All query DB live -- never depend on cached agent JSON files
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_options(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Live /options -- PCR, Max Pain, GEX from fo_data."""
    import sqlite3 as _sl
    try:
        conn = _sl.connect(r"D:/marketDB/db/market.db")

        latest_row = conn.execute(
            "SELECT MAX(date) FROM fo_data "
            "WHERE instrument IN ('OPTIDX','IDO') AND symbol='NIFTY'"
        ).fetchone()
        latest_date = latest_row[0] if latest_row and latest_row[0] else None

        if not latest_date:
            await update.message.reply_text(
                "No NIFTY options data. Run: py phase2_greeks_calculator.py --daily"
            )
            conn.close()
            return

        exp_row = conn.execute(
            "SELECT MIN(expiry) FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry>=?",
            (latest_date, latest_date)
        ).fetchone()
        expiry = exp_row[0] if exp_row and exp_row[0] else "?"

        pcr_rows = conn.execute(
            "SELECT option_typ, SUM(open_int) AS oi FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry=? "
            "GROUP BY option_typ",
            (latest_date, expiry)
        ).fetchall()
        pcr_map = {r[0]: r[1] for r in pcr_rows}
        call_oi = float(pcr_map.get("CE") or 0)
        put_oi  = float(pcr_map.get("PE") or 0)
        pcr     = round(put_oi / call_oi, 3) if call_oi > 0 else None

        # Max Pain
        all_strikes = conn.execute(
            "SELECT strike, "
            "SUM(CASE WHEN option_typ='CE' THEN COALESCE(open_int,0) END) AS co, "
            "SUM(CASE WHEN option_typ='PE' THEN COALESCE(open_int,0) END) AS po "
            "FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry=? "
            "GROUP BY strike ORDER BY strike",
            (latest_date, expiry)
        ).fetchall()

        max_pain = None
        if all_strikes:
            min_loss = float("inf")
            for K, co, po in all_strikes:
                K = float(K)
                loss = sum(
                    (K - float(s)) * float(c or 0) if float(s) < K else
                    (float(s) - K) * float(p or 0) if float(s) > K else 0
                    for s, c, p in all_strikes
                )
                if loss < min_loss:
                    min_loss = loss
                    max_pain = int(K)

        # Net GEX
        gex_row = conn.execute(
            "SELECT SUM(gamma_exposure) FROM gamma_exposure_daily "
            "WHERE date=(SELECT MAX(date) FROM gamma_exposure_daily WHERE symbol='NIFTY') "
            "AND symbol='NIFTY'"
        ).fetchone()
        net_gex = int(gex_row[0] or 0) if gex_row and gex_row[0] is not None else 0

        # Top 5 OI strikes
        top_oi = conn.execute(
            "SELECT strike, "
            "SUM(CASE WHEN option_typ='CE' THEN open_int END) AS co, "
            "SUM(CASE WHEN option_typ='PE' THEN open_int END) AS po "
            "FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry=? "
            "GROUP BY strike "
            "ORDER BY (COALESCE(co,0)+COALESCE(po,0)) DESC LIMIT 5",
            (latest_date, expiry)
        ).fetchall()

        nifty_row = conn.execute(
            "SELECT closing_index_value, change FROM market_snapshot "
            "WHERE index_name='Nifty 50' "
            "AND date=(SELECT MAX(date) FROM market_snapshot)"
        ).fetchone()
        conn.close()

        def _fmt_oi(v):
            if not v: return "--"
            n = float(v)
            if n >= 1e7: return f"{n/1e7:.1f}Cr"
            if n >= 1e5: return f"{n/1e5:.1f}L"
            if n >= 1e3: return f"{n/1e3:.0f}K"
            return str(int(n))

        def _fmt_gex(v):
            a = abs(v)
            if a >= 1e9: return f"{v/1e9:.2f}B"
            if a >= 1e6: return f"{v/1e6:.2f}M"
            return f"{int(v):,}"

        nifty_close  = round(float(nifty_row[0]), 2) if nifty_row and nifty_row[0] else None
        nifty_change = round(float(nifty_row[1]), 2) if nifty_row and nifty_row[1] else None

        pcr_label = (
            "BULLISH (put-heavy)" if pcr and pcr > 1.3 else
            "BEARISH (call-heavy)" if pcr and pcr < 0.7 else
            "NEUTRAL"
        )
        gex_label = "LONG GAMMA (dampens)" if net_gex > 0 else "SHORT GAMMA (amplifies)"

        if nifty_close and nifty_change is not None:
            nifty_str = f"{nifty_close:,} ({'+' if nifty_change >= 0 else ''}{nifty_change:.2f}%)"
        else:
            nifty_str = str(nifty_close or "--")

        lines = [
            "*OPTIONS SNAPSHOT*",
            f"`Date: {latest_date}  |  Expiry: {expiry}`",
            f"Nifty 50: `{nifty_str}`",
            "",
        ]
        if pcr:
            lines.append(f"*PCR:* `{pcr:.3f}` -- {pcr_label}")
        if max_pain:
            lines.append(f"*Max Pain:* `{max_pain:,}`")
        lines.append(f"*Net GEX:* `{_fmt_gex(net_gex)}` -- {gex_label}")
        lines.append(f"Call OI: `{_fmt_oi(call_oi)}`  |  Put OI: `{_fmt_oi(put_oi)}`")
        lines += ["", "*Top OI Strikes:*"]
        for row in top_oi:
            s, co, po = row
            lines.append(f"  `{int(float(s)):,}` CE:{_fmt_oi(co)}  PE:{_fmt_oi(po)}")
        lines.append("")
        lines.append("_Use /stock SYMBOL for stock-level options_")

        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_options error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


async def cmd_index(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /index [ND] -- top 5 gainers + decliners.
    e.g. /index 7D  /index 3D  /index 1M
    """
    import sqlite3 as _sl
    try:
        args_text = " ".join(ctx.args or []).strip().upper()
        day_map = {
            "1D": 1, "3D": 3, "5D": 5, "7D": 7,
            "10D": 10, "14D": 14, "20D": 20,
            "1M": 22, "2M": 44, "3M": 66,
        }
        n_days = day_map.get(args_text, 7)
        label  = args_text or "7D"

        conn = _sl.connect(r"D:/marketDB/db/market.db")
        rows = conn.execute(f"""
            WITH ld AS (SELECT MAX(date) AS md FROM market_snapshot),
            sd AS (
              SELECT date FROM (
                SELECT DISTINCT date FROM market_snapshot
                WHERE date <= (SELECT md FROM ld)
                ORDER BY date DESC LIMIT {n_days + 1}
              ) ORDER BY date ASC LIMIT 1
            ),
            s AS (
              SELECT index_name, closing_index_value AS sc
              FROM market_snapshot WHERE date=(SELECT date FROM sd)
            ),
            e AS (
              SELECT index_name, closing_index_value AS ec
              FROM market_snapshot WHERE date=(SELECT md FROM ld)
            )
            SELECT e.index_name,
                   ROUND((e.ec - s.sc) / s.sc * 100, 2) AS pct
            FROM e JOIN s ON e.index_name = s.index_name
            WHERE s.sc > 0 AND e.ec > 0
              AND e.index_name NOT LIKE '%Inverse%'
              AND e.index_name NOT LIKE '%VIX%'
              AND e.index_name NOT LIKE '%1x%'
              AND e.index_name NOT LIKE '%Dividend Points%'
            ORDER BY pct DESC
        """).fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text("No index data available.")
            return

        gainers   = rows[:5]
        decliners = list(reversed(rows))[:5]

        lines = [f"*INDEX PERFORMANCE -- {label}*", ""]
        lines.append("*Top 5 Gainers:*")
        for name, pct in gainers:
            bar = "+" * min(int(abs(float(pct or 0))), 10)
            lines.append(f"  `{_esc(str(name)[:28]):<28}` `{float(pct):+.2f}%` {bar}")
        lines += ["", "*Bottom 5 Decliners:*"]
        for name, pct in decliners:
            bar = "-" * min(int(abs(float(pct or 0))), 10)
            lines.append(f"  `{_esc(str(name)[:28]):<28}` `{float(pct):+.2f}%` {bar}")
        lines += ["", f"_Total: {len(rows)} indices | /index 1D /index 1M_"]

        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_index error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


async def cmd_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /stock OMAXAUTO -- quick stats: close, 7d return, delivery, streak, insider
    """
    import sqlite3 as _sl
    try:
        if not ctx.args:
            await update.message.reply_text("Usage: /stock SYMBOL\nExample: /stock OMAXAUTO")
            return

        symbol = ctx.args[0].strip().upper()
        conn   = _sl.connect(r"D:/marketDB/db/market.db")

        price_rows = conn.execute(
            "SELECT date, close, volume FROM stock_data "
            "WHERE symbol=? AND close IS NOT NULL "
            "ORDER BY date DESC LIMIT 10",
            (symbol,)
        ).fetchall()

        deliv_rows = conn.execute(
            "SELECT date, deliv_qty, traded_qty FROM stock_delivery "
            "WHERE symbol=? ORDER BY date DESC LIMIT 7",
            (symbol,)
        ).fetchall()

        streak_row = conn.execute(
            """
            WITH md AS (SELECT MAX(run_date) AS md FROM signals_history)
            SELECT COUNT(DISTINCT run_date) AS days,
                   ROUND(AVG(CAST(score AS REAL)), 1) AS avg_sc,
                   MAX(run_date) AS last_seen,
                   GROUP_CONCAT(DISTINCT screen_tags) AS tags
            FROM signals_history
            WHERE symbol=?
              AND run_date >= date((SELECT md FROM md), '-30 days')
            """,
            (symbol,)
        ).fetchone()

        insider_rows = conn.execute(
            "SELECT filing_date, name, transaction_type, value "
            "FROM insider_trading "
            "WHERE symbol=? ORDER BY filing_date DESC LIMIT 3",
            (symbol,)
        ).fetchall()
        conn.close()

        if not price_rows:
            await update.message.reply_text(
                f"No data for {symbol}. Check symbol spelling."
            )
            return

        close  = float(price_rows[0][1])
        older  = float(price_rows[-1][1]) if price_rows else close
        pct_7d = round((close / older - 1) * 100, 2) if older > 0 else None
        vol    = int(price_rows[0][2] or 0)

        avg_deliv = None
        valid = [
            float(r[1]) / float(r[2]) * 100
            for r in deliv_rows
            if r[1] and r[2] and float(r[2]) > 0
        ]
        if valid:
            avg_deliv = round(sum(valid) / len(valid), 1)

        streak_days = int(streak_row[0] or 0) if streak_row else 0
        streak_sc   = float(streak_row[1] or 0) if streak_row else 0
        streak_last = streak_row[2] if streak_row and streak_row[2] else "--"
        streak_tags = streak_row[3] if streak_row and streak_row[3] else "--"

        conviction = streak_days * streak_sc + (avg_deliv or 0) * 0.1
        grade = "A+" if conviction >= 20 else "A" if conviction >= 12 else "B" if conviction >= 7 else "C" if conviction >= 3 else "--"

        pct_str = (f"{'+' if pct_7d and pct_7d >= 0 else ''}{pct_7d:.2f}%") if pct_7d is not None else "--"
        vol_str = f"{vol/1e5:.1f}L" if vol >= 1e5 else f"{vol/1e3:.0f}K" if vol >= 1e3 else str(vol)

        lines = [
            f"*{_esc(symbol)}*",
            f"Close: `{close:,.2f}`  7d: `{pct_str}`  Vol: `{vol_str}`",
        ]
        if avg_deliv is not None:
            lines.append(f"Avg Delivery: `{avg_deliv:.1f}%`")

        if streak_days > 0:
            flame = "FIRE" if streak_days >= 5 else "HOT" if streak_days >= 3 else ""
            lines += [
                "",
                f"*Streak (30d):* `{streak_days}d` {flame}",
                f"  Score: `{streak_sc:.1f}`  Grade: `{grade}`  Last: `{streak_last}`",
                f"  Screens: `{_esc(str(streak_tags)[:60])}`",
            ]
        else:
            lines.append("\nNo recent streak signals.")

        if insider_rows:
            lines += ["", "*Insider (last 30d):*"]
            for fdate, name, ttype, val in insider_rows:
                val_str = f"Rs{float(val)/1e5:.1f}L" if val and float(val) > 0 else "--"
                ttype_e = _esc(str(ttype or "")[:15])
                name_e  = _esc(str(name  or "")[:20])
                lines.append(f"  `{fdate}` {name_e} [{ttype_e}] {val_str}")

        lines.append(f"\n_Dashboard: localhost:3000/stocks/{symbol}_")
        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_stock error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


async def cmd_hot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /hot -- symbols appearing 3+ days in last 7
    """
    import sqlite3 as _sl
    try:
        conn = _sl.connect(r"D:/marketDB/db/market.db")
        rows = conn.execute("""
            WITH md AS (SELECT MAX(run_date) AS md FROM signals_history)
            SELECT symbol,
                   COUNT(DISTINCT run_date) AS days,
                   ROUND(AVG(CAST(score AS REAL)), 1) AS avg_sc,
                   ROUND(AVG(CAST(pct_chg AS REAL)), 2) AS avg_ret,
                   ROUND(AVG(CAST(avg_deliv_pct AS REAL)), 1) AS avg_deliv,
                   GROUP_CONCAT(DISTINCT screen_tags) AS tags
            FROM signals_history
            WHERE run_date >= date((SELECT md FROM md), '-7 days')
            GROUP BY symbol
            HAVING days >= 3
            ORDER BY days DESC, avg_sc DESC
            LIMIT 20
        """).fetchall()
        latest = conn.execute(
            "SELECT MAX(run_date) FROM signals_history"
        ).fetchone()[0]
        conn.close()

        if not rows:
            await update.message.reply_text(
                "No hot picks in last 7 days. Run: py micc_engine.py 7 --send"
            )
            return

        lines = [
            "*HOT PICKS -- Last 7 Days*",
            f"`Symbols 3+ days | as of {latest}`",
            "",
        ]
        for sym, days, avg_sc, avg_ret, avg_deliv, tags in rows:
            ret_s   = f"{'+' if float(avg_ret or 0) >= 0 else ''}{float(avg_ret or 0):.1f}%" if avg_ret else "--"
            del_s   = f"d{float(avg_deliv or 0):.0f}%" if avg_deliv else ""
            tag_s   = ",".join(t[:4] for t in str(tags or "").split(",") if t)[:18]
            flame   = "FIRE" if days >= 5 else "HOT"
            lines.append(
                f"{flame} `{_esc(str(sym)):<12}` {days}d "
                f"ret:{ret_s}  sc:{avg_sc}  {del_s}  `{_esc(tag_s)}`"
            )

        lines += [
            "",
            "_/stock SYMBOL for full stats on any pick_",
        ]
        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_hot error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


# ── Scheduled job ─────────────────────────────────────────────────────────────

async def morning_report_job(bot: Bot):
    log.info("Sending scheduled morning report...")
    try:
        chunks = build_full_report()
        await send_chunks(bot, CHAT_ID, chunks)
        log.info("Morning report sent.")
    except Exception as e:
        log.error(f"morning_report_job error: {e}", exc_info=True)


# ── Main ──────────────────────────────────────────────────────────────────────



async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show watchlist status from last Zeta report."""
    zeta_path = Path("agents/zeta/last_report.json")
    if not zeta_path.exists():
        await update.message.reply_text(
            "No Zeta report found. Run: py agent_zeta.py --send"
        )
        return
    try:
        report = json.loads(zeta_path.read_text(encoding="utf-8"))
    except Exception as e:
        await update.message.reply_text(f"Error loading Zeta: {e}")
        return

    d        = report.get("date", "?")
    syms     = report.get("watchlist_symbols", [])
    breakouts= report.get("breakout_watch", [])[:5]
    surges   = report.get("vol_delivery_surge", [])[:5]
    alerts   = report.get("triggered_alerts", [])
    reentries= report.get("reentry_radar", [])[:4]
    streaks  = report.get("watchlist_streaks", [])[:8]

    lines = [f"*WATCHLIST INTEL -- {d}*", ""]

    if alerts:
        lines.append("*ALERTS TRIGGERED:*")
        for a in alerts:
            lines.append(f"  `{a['symbol']}` {a['condition'].upper()} {a['level']} @ `{a['price']}`")
        lines.append("")

    if syms:
        lines.append("*WATCHING:* " + " | ".join(f"`{s}`" for s in syms[:12]))
        lines.append("")

    if streaks:
        lines.append("*STREAKS:*")
        for s in streaks:
            bar = "=" * min(s["streak"], 8)
            lines.append(f"  `{s['symbol']}` [{bar}] {s['streak']}d")
        lines.append("")

    if breakouts:
        lines.append("*NEAR 52w HIGH:*")
        for b in breakouts:
            lines.append(f"  `{b['symbol']}` @ {b['close']} (-{b['pct_from_52h']}% from high)")
        lines.append("")

    if surges:
        lines.append("*VOL SURGES:*")
        for s in surges:
            lines.append(f"  `{s['symbol']}` {s['vol_surge']}x vol | {s['deliv_pct']}% deliv")
        lines.append("")

    if reentries:
        lines.append("*RE-ENTRY:*")
        for r in reentries:
            near = " [near MA10]" if r.get("near_ma10") else ""
            lines.append(f"  `{r['symbol']}` -{r['pullback_pct']}%{near}")

    msg = "\n".join(lines)
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")


async def cmd_eta(update, context):
    """Send latest Eta (corporate events) report summary."""
    report_path = Path(r"D:\MICC\agents\eta\last_report.json")
    if not report_path.exists():
        await update.message.reply_text("No Eta report. Run: py agent_eta.py")
        return
    import json
    rpt = json.loads(report_path.read_text(encoding="utf-8"))
    lines = [
        f"*MICC Eta - Corporate Events*",
        f"Date: {rpt.get('date', '?')}",
        "",
        f"*Results Season:* {len(rpt.get('screen1_results_season', []))} companies",
        f"*Dividends/Bonus:* {len(rpt.get('screen2_dividends', []))} events",
        f"*Insider Clusters:* {len(rpt.get('screen3_insider_clusters', []))} stocks",
        f"*Big Trades (>1Cr):* {len(rpt.get('screen4_big_trades', []))} trades",
        f"*Post-Results:* {len(rpt.get('screen5_post_results_reaction', []))} reactions",
        f"*Upcoming Results:* {len(rpt.get('screen6_upcoming_results', []))} predicted",
    ]
    clusters = rpt.get("screen3_insider_clusters", [])[:3]
    if clusters:
        lines.append("")
        lines.append("*Top Insider Clusters:*")
        for c in clusters:
            lines.append(f"  {c.get('symbol')} - {c.get('n_buys')} insiders, Rs {c.get('total_value_cr', 0):.1f} Cr")
    analysis = rpt.get("llm_analysis", "")
    if analysis:
        lines.append("")
        lines.append("*Analysis:*")
        lines.append(analysis[:600])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")




async def cmd_deep(update, context):
    """Send Iota deep analysis summary."""
    report_path = Path(r"D:\MICC\agents\iota\last_report.json")
    if not report_path.exists():
        await update.message.reply_text("No Iota report. Run: py agent_iota.py")
        return
    import json
    rpt = json.loads(report_path.read_text(encoding="utf-8"))
    regime = rpt.get("current_regime", "?")
    vix    = rpt.get("vix", "?")
    ret20  = rpt.get("nifty_20d_return", "?")
    s1 = rpt.get("screen1_best_probability", [])[:5]
    s2 = rpt.get("screen2_risk_adjusted", [])[:3]
    s5 = rpt.get("screen5_global", {})
    lines = [
        f"*MICC Deep Analysis Room*",
        f"Date: {rpt.get('date', '?')}",
        f"Regime: {regime} | VIX: {vix} | Nifty20d: {ret20}%",
        "",
        f"*Global:* {s5.get('global_risk', '?')} | SPX5d: {s5.get('spx_5d', '?')}%",
        "",
        "*Top Probability Stocks (20d):*",
    ]
    for s in s1:
        lines.append(f"  {s.get('symbol')} prob={s.get('prob_positive')}% mean={s.get('mean_return')}%")
    lines.append("")
    lines.append("*Top Sharpe Gems:*")
    for s in s2:
        lines.append(f"  {s.get('symbol')} Sharpe={s.get('sharpe_ratio')} mean={s.get('mean_return')}%")
    analysis = rpt.get("llm_analysis", "")
    if analysis:
        lines.append("")
        lines.append(analysis[:500])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")




async def cmd_kappa(update, context):
    """Send Kappa deep profile for a symbol. Usage: /kappa RELIANCE"""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /kappa SYMBOL\nExample: /kappa RELIANCE")
        return
    sym = args[0].upper()
    report_path = Path(rf"D:\MICC\agents\kappa\{sym}_report.json")
    if not report_path.exists():
        await update.message.reply_text(
            f"No Kappa report for {sym}.\nRun: py D:\\MICC\\agent_kappa.py {sym}"
        )
        return
    import json
    rpt = json.loads(report_path.read_text(encoding="utf-8"))
    ss = rpt.get("series_stats", {}) or {}
    tech = rpt.get("technicals", {}) or {}
    lines = [
        f"*Kappa: {sym}*",
        f"Type: {rpt.get('asset_type', '?')} | Date: {rpt.get('date', '?')}",
        "",
        f"CAGR: {ss.get('cagr_pct', '?')}% | Vol: {ss.get('ann_volatility_pct', '?')}%",
        f"MaxDD: {ss.get('max_drawdown_pct', '?')}% | Sharpe: {ss.get('sharpe_ratio', '?')}",
    ]
    verdict = rpt.get("llm_verdict", "")
    if verdict:
        lines.append("")
        lines.append(verdict[:600])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")





async def cmd_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send global markets snapshot. Usage: /global  or  /global SPX"""
    import sqlite3
    args  = context.args
    sym   = args[0].upper() if args else None
    DB_P  = r"D:\marketDB\db\market.db"

    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        if sym:
            # Single symbol last 5 days
            rows = conn.execute(
                "SELECT date, close, pct_change FROM global_indices_daily "
                "WHERE symbol=? ORDER BY date DESC LIMIT 5", (sym,)
            ).fetchall()
            conn.close()
            if not rows:
                await update.message.reply_text(f"No data for `{sym}`", parse_mode="Markdown")
                return
            lines = [f"*{sym} — Last 5 sessions*", ""]
            for date_, close, chg in rows:
                chg_str = f"{chg:+.2f}%" if chg is not None else "—"
                clr_ico = "🟢" if (chg or 0) > 0 else "🔴" if (chg or 0) < 0 else "⚪"
                lines.append(f"  {clr_ico} `{date_}` {close:.2f}  {chg_str}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        else:
            # Summary: latest for all, grouped by category
            CATS_ORDER = ["US","India","Europe","Asia","Commodity","FX","Rates","Crypto"]
            CAT_MAP = {
                "SPX":"US","NDX":"US","DJIA":"US","RUT":"US","SP500VIX":"Volatility",
                "NIFTY50":"India","NIFTYBANK":"India","SENSEX":"India","NIFTYIT":"India",
                "INDIAVIX":"Volatility","DAX":"Europe","FTSE100":"Europe","CAC40":"Europe",
                "Nikkei225":"Asia","HangSeng":"Asia","Shanghai":"Asia","Kospi":"Asia","ASX200":"Asia",
                "Gold":"Commodity","Silver":"Commodity","CrudeWTI":"Commodity","BrentCrude":"Commodity",
                "DXY":"FX","USDINR":"FX","EURUSD":"FX","USDJPY":"FX",
                "US10Y":"Rates","US2Y":"Rates","Bitcoin":"Crypto","Ethereum":"Crypto",
            }
            rows = conn.execute(
                "SELECT symbol, close, pct_change FROM global_indices_daily "
                "WHERE date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol) "
                "ORDER BY symbol"
            ).fetchall()
            conn.close()

            by_cat: dict = {}
            for sym_, close, chg in rows:
                cat = CAT_MAP.get(sym_, "Other")
                by_cat.setdefault(cat, []).append((sym_, close, chg))

            lines = [f"*🌍 Global Markets Snapshot*", ""]
            for cat in CATS_ORDER:
                items = by_cat.get(cat, [])
                if not items: continue
                lines.append(f"*{cat}:*")
                for sym_, close, chg in sorted(items, key=lambda x: -(x[2] or 0)):
                    chg_str = f"{chg:+.2f}%" if chg is not None else "—"
                    ico = "🟢" if (chg or 0) > 0.3 else "🔴" if (chg or 0) < -0.3 else "⚪"
                    lines.append(f"  {ico} `{sym_:<12}` {chg_str}")
                lines.append("")

            await update.message.reply_text("\n".join(lines)[:4000], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top patterns active today. Usage: /patterns  or  /patterns RELIANCE"""
    import sqlite3
    from datetime import datetime
    args  = context.args
    sym   = args[0].upper() if args else None
    DB_P  = r"D:\marketDB\db\market.db"
    today_mmdd = datetime.today().strftime("%m-%d")

    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        # Try v3 first, fall back to v2
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        tbl = "seasonality_patterns_v3" if "seasonality_patterns_v3" in tables else "seasonality_patterns"

        where = f"anchor_mm_dd = '{today_mmdd}'"
        if sym: where += f" AND symbol = '{sym}'"
        else:   where += " AND accuracy >= 68 AND score >= 2"

        rows = conn.execute(
            f"SELECT symbol, anchor_mm_dd, window_days, direction, accuracy, mean_ret, score "
            f"FROM {tbl} WHERE {where} ORDER BY score DESC LIMIT 15"
        ).fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text(
                f"No patterns for {today_mmdd}" + (f" / {sym}" if sym else ""),
                parse_mode="Markdown"
            )
            return

        lines = [f"*🔬 Seasonal Patterns — {today_mmdd}*", f"_{tbl}_", ""]
        for sym_, anc, win, dirn, acc, mean, score in rows:
            ico = "🟢" if dirn == "UP" else "🔴"
            mean_str = f"{mean:+.2f}%"
            lines.append(
                f"  {ico} `{sym_:<14}` {win}d {dirn:<5} {acc:.0f}% {mean_str}  ★{score:.2f}"
            )
        await update.message.reply_text("\n".join(lines)[:4000], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")



async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active alerts. Usage: /alerts"""
    import json, pathlib
    try:
        p = pathlib.Path(r"D:\MICC\alerts.json")
        alerts = json.loads(p.read_text()) if p.exists() else []
        active = [a for a in alerts if a.get("active")]
        fired  = [a for a in alerts if not a.get("active") and a.get("triggered_at")]
        lines  = ["*MICC Alerts*", ""]
        if active:
            lines.append(f"*Active ({len(active)}):*")
            for a in active[:10]:
                lines.append(
                    f"  `{a.get('type','')[:12]:<12}` `{a.get('symbol',''):<12}` "
                    f"target={a.get('target','')}  {a.get('note','')}"
                )
            lines.append("")
        if fired:
            lines.append(f"*Fired ({len(fired)}):*")
            for a in fired[-5:]:
                lines.append(f"  `{a.get('symbol','')}` {(a.get('last_message') or '')[:60]}")
        if not active and not fired:
            lines.append("No alerts. Add via /api/alerts or dashboard.")
        await update.message.reply_text("\n".join(lines)[:4000], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")



def get_todays_patterns_msg() -> str:
    """Get today's top seasonal patterns for morning brief."""
    import sqlite3
    from datetime import datetime
    today_mmdd = datetime.today().strftime('%m-%d')
    DB_P = r'D:\marketDB\db\market.db'
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        tbl = 'seasonality_patterns_v3' if 'seasonality_patterns_v3' in tables else 'seasonality_patterns'
        rows = conn.execute(
            'SELECT symbol, window_days, direction, accuracy, mean_ret, score '
            'FROM ' + tbl + ' WHERE anchor_mm_dd=? AND accuracy>=68 AND score>=3 '
            'AND ABS(mean_ret) <= 50 ORDER BY score DESC LIMIT 10',
            (today_mmdd,)
        ).fetchall()
        conn.close()
        if not rows:
            return '_No high-accuracy patterns for ' + today_mmdd + '_'
        lines = ['*Seasonal Patterns (' + today_mmdd + '):*']
        for sym, win, dirn, acc, mean, score in rows:
            ico = 'UP' if dirn == 'UP' else 'DN'
            lines.append(
                f'  {ico} `{sym:<14}` {win}d  {acc:.0f}%  {mean:+.2f}%  s={score:.1f}'
            )
        return '\n'.join(lines)
    except Exception as e:
        return '_Patterns error: ' + str(e) + '_'



async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send today's top seasonal patterns."""
    import sqlite3
    from datetime import datetime
    mmdd = datetime.today().strftime('%m-%d')
    DB_P = r'D:\marketDB\db\market.db'
    args = context.args
    min_score = float(args[0]) if args else 5.0
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        tbl = 'seasonality_patterns_v3' if 'seasonality_patterns_v3' in tables else 'seasonality_patterns'
        rows = conn.execute(
            f'SELECT symbol, window_days, direction, accuracy, mean_ret, score, n_obs '
            f'FROM {tbl} WHERE anchor_mm_dd=? AND accuracy>=65 '
            f'AND score>=? AND ABS(mean_ret)<=50 '
            f'ORDER BY score DESC LIMIT 15',
            (mmdd, min_score)
        ).fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text(
                f'No patterns found for {mmdd} with score>={min_score}\n'
                f'Try: /today 2  (lower threshold)',
                parse_mode='Markdown'
            )
            return
        up   = sum(1 for r in rows if r[2]=='UP')
        down = sum(1 for r in rows if r[2]=='DOWN')
        lines = [
            f'*Seasonal Patterns -- {mmdd}*',
            f'_{len(rows)} patterns | {up} bullish | {down} bearish_',
            '',
        ]
        for sym, win, dirn, acc, mean, score, n in rows:
            ico = 'UP' if dirn=='UP' else 'DN'
            lines.append(
                f'  {ico} `{sym:<14}` {win}d  {acc:.0f}%  {mean:+.2f}%  s={score:.1f}  n={n}'
            )
        await update.message.reply_text('\n'.join(lines)[:4000], parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f'Error: {e}')



async def cmd_status_full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full system status including DB stats."""
    import sqlite3, pathlib
    DB_P = r'D:\\marketDB\\db\\market.db'
    DA   = pathlib.Path(r'D:\\MICC')
    try:
        conn = sqlite3.connect(DB_P, timeout=10)

        def cnt(tbl):
            try: return conn.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
            except: return 0

        total_pats  = cnt('seasonality_patterns_v3')
        pat_syms    = conn.execute('SELECT COUNT(DISTINCT symbol) FROM seasonality_patterns_v3').fetchone()[0] if total_pats else 0
        stock_rows  = cnt('stock_data')
        signals     = cnt('signals_history')
        global_idx  = cnt('global_indices_daily')
        conn.close()

        agents = ['alpha','beta','gamma','delta','epsilon','zeta','eta','iota','kappa','alert']
        ready  = [a for a in agents if (DA / 'agents' / a / 'last_report.json').exists()]

        try:
            import os
            db_size = os.path.getsize(DB_P) / 1024 / 1024 / 1024
            size_str = f'{db_size:.1f} GB'
        except: size_str = '?'

        alerts_active = 0
        try:
            import json
            af = DA / 'alerts.json'
            if af.exists():
                alerts_active = sum(1 for a in json.loads(af.read_text()) if a.get('active'))
        except: pass

        lines = [
            '*MICC System Status*', '',
            f'*Database:* {size_str}',
            f'  Patterns v3 : {total_pats:,} ({pat_syms} symbols)',
            f'  Stock data  : {stock_rows:,} rows',
            f'  Global idx  : {global_idx:,} rows',
            f'  Signals     : {signals:,} rows',
            '',
            f'*Agents ({len(ready)}/10 ready):*',
            '  ' + '  '.join([('OK' if a in ready else 'NO') + ' ' + a for a in agents]),
            '',
            f'*Alerts active:* {alerts_active}',
            '',
            '_localhost:3000/settings for full details_',
        ]
        await update.message.reply_text('\n'.join(lines)[:4000], parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f'Error: {e}')

def main():
    if not BOT_TOKEN:
        print("\n[ERROR] TELEGRAM_BOT_TOKEN not set.")
        print("  PowerShell: $env:TELEGRAM_BOT_TOKEN='your_token'\n")
        sys.exit(1)

    if not CHAT_ID:
        print("\n[WARNING] TELEGRAM_CHAT_ID not set - scheduled 9:15 AM report disabled.")

    print("=" * 60)
    print("  MICC TELEGRAM BOT")
    print("=" * 60)
    print(f"  Token    : {BOT_TOKEN[:8]}...(hidden)")
    print(f"  Chat ID  : {CHAT_ID if CHAT_ID else 'NOT SET'}")
    print(f"  Schedule : 9:15 AM IST daily")
    print("=" * 60)
    print("  Commands: /start /report /alpha /beta /gamma /delta /eta /streak /options /index /stock /hot /deep /kappa /global /patterns /watch /status")
    print("  Press Ctrl+C to stop\n")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("alpha",  cmd_alpha))
    app.add_handler(CommandHandler("beta",   cmd_beta))
    app.add_handler(CommandHandler("gamma",  cmd_gamma))
    app.add_handler(CommandHandler("delta",  cmd_delta))
    app.add_handler(CommandHandler("streak",  cmd_streak))
    app.add_handler(CommandHandler("options", cmd_options))
    app.add_handler(CommandHandler("index",   cmd_index))
    app.add_handler(CommandHandler("stock",   cmd_stock))
    app.add_handler(CommandHandler("hot",     cmd_hot))
            app.add_handler(CommandHandler("global",   cmd_global))
    app.add_handler(CommandHandler("patterns", cmd_patterns))
            app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("eta",   cmd_eta))
    app.add_handler(CommandHandler("deep",  cmd_deep))
    app.add_handler(CommandHandler("kappa", cmd_kappa))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("conviction", cmd_conviction))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("exit", cmd_exit))
    app.add_handler(CommandHandler("status", cmd_status_full  # upgraded,  cmd_status))

    if CHAT_ID:
        scheduler = AsyncIOScheduler(timezone=IST)
        scheduler.add_job(
            morning_report_job,
            trigger="cron",
            hour=9,
            minute=15,
            kwargs={"bot": app.bot},
            name="morning_report",
        )

        async def post_init(application: Application) -> None:
            scheduler.start()
            log.info("APScheduler started - daily report at 09:15 IST")

        app.post_init = post_init

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
