# -*- coding: utf-8 -*-
"""
MICC v2 — Main Engine (Orchestrator + HTML Report Generator)
=============================================================
Runs all 4 agents in sequence, synthesises everything via LLM,
generates a comprehensive HTML report, and sends to Telegram.

Report structure:
  PART 1 — MACRO INTELLIGENCE
    1.1 Market Regime (Alpha: Nifty 50, regime, breadth, cap rotation)
    1.2 All Indices Performance (ranked table)
    1.3 Institutional Flow Intelligence (Gamma: FII/DII analysis)
    1.4 Risk & Corporate Intelligence (Delta: risk score, flags, quality universe)
    1.5 Overall LLM Synthesis (all 4 agents → final verdict)

  PART 2 — STOCK UNIVERSE INTELLIGENCE
    2.1 Composite Watchlist (multi-screen conviction)
    2.2 Momentum Screen
    2.3 Delivery Leaders
    2.4 Volume Breakouts
    2.5 Sector Rotation

  PART 3 — INDEX DEEP DIVES (top 7 indices)
    [For each index]:
      - Index performance + PE
      - All constituent stocks table (sortable)
      - High-conviction delivery picks
      - LLM in-depth analysis (Groq Llama 70B)
      - Recent sector news

Usage:
  py micc_engine.py            → interactive (prompts for N days)
  py micc_engine.py 10         → 10-day analysis
  py micc_engine.py 5 --send   → 5-day analysis + send to Telegram
"""

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

from micc_data import (
    get_trading_dates, call_llm,
    send_telegram_chunks, now_ist, fmt_pct, fmt_cr,
)
from agent_alpha import run_alpha
from agent_beta  import run_beta
from agent_gamma import run_gamma
from agent_delta   import run_delta
from agent_eta     import run_eta
from agent_iota    import run_iota

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("agents/custom")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_DAYS = 60


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL LLM SYNTHESIS (Part 1.5) — all 4 agents → one verdict
# ═══════════════════════════════════════════════════════════════════════════════

def synthesise_all(alpha: dict, beta: dict, gamma: dict, delta: dict,
                    n_days: int) -> str:
    """
    Master synthesis: fuse all 4 agents into one comprehensive verdict.
    Uses Groq (free, fast, high quality).
    """
    regime   = alpha.get("regime", {})
    rotation = alpha.get("cap_rotation", {})

    top3_idx = " | ".join(
        f"{r['index']}({r['pct_change']:+.1f}%)"
        for r in alpha.get("top10_gainers", [])[:3]
    )
    bot3_idx = " | ".join(
        f"{r['index']}({r['pct_change']:+.1f}%)"
        for r in alpha.get("top10_losers", [])[:3]
    )

    comp_stocks = beta.get("screens", {}).get("composite", [])[:8]
    comp_str = " | ".join(
        f"{r.get('symbol','?')}({r.get('pct_chg',0):+.1f}%,sc:{r.get('score',0)})"
        for r in comp_stocks
    )

    sector_top = " | ".join(
        f"{s['sector']}({s['avg_pct']:+.1f}%)"
        for s in beta.get("sector_rotation", {}).get("top_sectors", [])[:4]
    )

    gm = gamma.get("eq_flow", {}).get("metrics", {})
    fs = gamma.get("flow_score", {})
    fii_cum   = gm.get("fii_cumulative_cr", 0)
    dii_cum   = gm.get("dii_cumulative_cr", 0)
    fii_trend = gm.get("fii_trend", "?")

    risk_score = delta.get("risk_score", 5)
    risk_level = delta.get("risk_level", "MEDIUM")
    risk_str   = " | ".join(delta.get("risk_flags", [])[:3])
    green_str  = " | ".join(delta.get("green_flags", [])[:2])

    prompt = (
        f"You are the head of NSE market intelligence. Write the MASTER SYNTHESIS for "
        f"a {n_days}-day comprehensive market report. This is the most important section — "
        f"it must be actionable, specific, and insightful.\n\n"
        f"Structure EXACTLY as:\n\n"
        f"# MICC Master Intelligence Report — {n_days} Days\n\n"
        f"## Executive Summary (3-4 sentences)\n"
        f"[The most important things that happened. What does a fund manager need to know immediately?]\n\n"
        f"## Market Verdict: {regime.get('regime','?')}\n"
        f"[3-4 sentences: why this regime? What are the key evidence points? "
        f"Is this regime sustainable or about to change?]\n\n"
        f"## Institutional Intelligence\n"
        f"[3-4 sentences: FII selling/buying + DII counter. "
        f"What does the institutional posture tell us about near-term direction? "
        f"Is smart money accumulating or distributing?]\n\n"
        f"## Sector Rotation & Key Themes\n"
        f"[3-4 sentences: which sectors are seeing capital inflows? "
        f"What macro themes are driving sector performance? "
        f"Where is the next opportunity likely to emerge?]\n\n"
        f"## Top 5 Conviction Picks (from composite screener)\n"
        f"[For each of top 5: one sentence with symbol, why it appeared in multiple screens, "
        f"and the key risk to the thesis.]\n\n"
        f"## Risk-Adjusted Outlook (5-10 days)\n"
        f"[4-5 sentences: overall market direction, key levels to watch, "
        f"biggest risks that could derail the thesis, and a clear BULLISH/BEARISH/NEUTRAL "
        f"stance with exact reasoning.]\n\n"
        f"ALL AGENT DATA:\n"
        f"ALPHA — Regime: {regime.get('regime','?')} | Nifty window: {regime.get('window_pct',0):+.2f}% | "
        f"PE: {regime.get('pe','N/A')} | Vol: {regime.get('vol_ann_pct','N/A')}% | "
        f"MA20: {'above' if regime.get('above_ma20') else 'below'} | "
        f"MA50: {'above' if regime.get('above_ma50') else 'below'}\n"
        f"Rotation: {rotation.get('signal','N/A')} | "
        f"LC: {rotation.get('largecap_avg_pct',0):+.1f}% MC: {rotation.get('midcap_avg_pct',0):+.1f}% "
        f"SC: {rotation.get('smallcap_avg_pct',0):+.1f}%\n"
        f"Top: {top3_idx} | Worst: {bot3_idx}\n\n"
        f"BETA — Composite picks: {comp_str[:300] or 'None'}\n"
        f"Top sectors: {sector_top or 'N/A'}\n\n"
        f"GAMMA — FII {n_days}d: {fmt_cr(fii_cum)} ({fii_trend}) | DII: {fmt_cr(dii_cum)} | "
        f"Flow score: {fs.get('flow_score',0)}/10 → {fs.get('flow_sentiment','?')}\n\n"
        f"DELTA — Risk: {risk_score}/10 {risk_level} | "
        f"Flags: {risk_str or 'None'} | Positives: {green_str or 'None'}"
    )

    text, source = call_llm(prompt, max_tokens=1800, label="MasterSynthesis", prefer_groq=True)
    print(f"[Engine] Master synthesis done via {source} ({len(text)} chars)")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# HTML REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def _pct_color(val) -> str:
    """Return CSS class based on % change."""
    try:
        v = float(val)
        if v > 2:  return "pos-strong"
        if v > 0:  return "pos"
        if v < -2: return "neg-strong"
        if v < 0:  return "neg"
        return "neutral"
    except Exception:
        return "neutral"


def _fmt_val(val, digits=2, suffix="", sign=False) -> str:
    if val is None:
        return "—"
    try:
        v = float(val)
        s = "+" if (sign and v > 0) else ""
        return f"{s}{v:.{digits}f}{suffix}"
    except Exception:
        return str(val)

def _fmt_pct(val, digits=2) -> str:
    """Always show sign for % values."""
    if val is None:
        return "—"
    try:
        v = float(val)
        return f"{v:+.{digits}f}%"
    except Exception:
        return "—"


def generate_html(alpha: dict, beta: dict, gamma: dict, delta: dict,
                   synthesis: str, n_days: int, out_path: Path):
    """Generate comprehensive HTML report."""

    start_d = alpha.get("start_date", "?")
    end_d   = alpha.get("end_date", "?")
    regime  = alpha.get("regime", {})
    now     = now_ist()

    # ── CSS ───────────────────────────────────────────────────────────────────
    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0d1117; color: #c9d1d9; font-size: 14px; line-height: 1.6; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
h1 { font-size: 22px; color: #58a6ff; margin-bottom: 4px; }
h2 { font-size: 17px; color: #79c0ff; margin: 24px 0 10px;
     border-bottom: 1px solid #21262d; padding-bottom: 6px; }
h3 { font-size: 15px; color: #8b949e; margin: 16px 0 8px; }
h4 { font-size: 13px; color: #8b949e; margin: 10px 0 6px; }
.meta { color: #8b949e; font-size: 12px; margin-bottom: 20px; }
.section { background: #161b22; border: 1px solid #21262d; border-radius: 8px;
           padding: 18px; margin-bottom: 18px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.card { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 14px; }
.kpi-label { font-size: 11px; color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.kpi-value { font-size: 20px; font-weight: 600; color: #c9d1d9; }
.kpi-sub { font-size: 12px; color: #8b949e; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 8px 10px; background: #21262d;
     color: #8b949e; font-weight: 500; white-space: nowrap; }
td { padding: 6px 10px; border-bottom: 1px solid #161b22; }
tr:hover td { background: #1c2129; }
.pos-strong { color: #3fb950; font-weight: 600; }
.pos        { color: #56d364; }
.neg-strong { color: #f85149; font-weight: 600; }
.neg        { color: #da3633; }
.neutral    { color: #8b949e; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
         font-size: 11px; font-weight: 500; }
.badge-green  { background: #1a3327; color: #3fb950; }
.badge-red    { background: #3b1a1a; color: #f85149; }
.badge-amber  { background: #2b2000; color: #e3b341; }
.badge-blue   { background: #1a2744; color: #79c0ff; }
.badge-purple { background: #2a1a44; color: #bc8cff; }
.regime-box { padding: 12px 16px; border-radius: 6px; margin-bottom: 12px;
              border-left: 4px solid; }
.regime-up   { border-color: #3fb950; background: #0d2016; }
.regime-down { border-color: #f85149; background: #200d0d; }
.regime-vol  { border-color: #e3b341; background: #1a1500; }
.regime-cons { border-color: #79c0ff; background: #0d1d2e; }
.regime-mean { border-color: #bc8cff; background: #1a0d2e; }
.llm-box { background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
           padding: 14px; margin-top: 12px; font-size: 13px; line-height: 1.7; white-space: pre-wrap; }
.news-item { padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 12px; }
.news-item:last-child { border-bottom: none; }
.news-source { color: #58a6ff; font-size: 11px; margin-right: 6px; }
.flow-bar { height: 8px; border-radius: 4px; margin: 4px 0; }
.flow-pos { background: #3fb950; }
.flow-neg { background: #f85149; }
.score-pill { display: inline-block; padding: 3px 12px; border-radius: 20px; font-weight: 600; }
.part-header { font-size: 18px; color: #f0f6fc; padding: 12px 0 8px;
               border-top: 2px solid #21262d; margin-top: 28px; }
.index-section { margin-bottom: 28px; }
.sticky-header th { position: sticky; top: 0; z-index: 1; }
@media (max-width: 768px) { .grid-2,.grid-3,.grid-4 { grid-template-columns: 1fr; } }
.navbar { position: sticky; top: 0; z-index: 100; background: #0d1117cc;
          backdrop-filter: blur(8px); border-bottom: 1px solid #21262d;
          padding: 8px 20px; display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.navbar a { color: #58a6ff; font-size: 12px; text-decoration: none; white-space: nowrap; }
.navbar a:hover { color: #79c0ff; text-decoration: underline; }
.risk-bar { height: 10px; border-radius: 5px; background: #21262d; margin-top: 6px; overflow:hidden; }
.risk-fill { height: 100%; border-radius: 5px; }
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { background: #30363d; }
th.sort-asc::after  { content: " ▲"; font-size: 10px; }
th.sort-desc::after { content: " ▼"; font-size: 10px; }
.llm-rendered h3 { font-size:14px; color:#79c0ff; margin:12px 0 6px; }
.llm-rendered h4 { font-size:13px; color:#8b949e; margin:10px 0 4px; }
.llm-rendered strong { color:#e6edf3; }
.llm-rendered p { margin-bottom:8px; }
.llm-rendered ul { margin:4px 0 8px 16px; }
.llm-rendered li { margin-bottom:3px; }
.trend-up   { color:#3fb950; }
.trend-down { color:#f85149; }
"""

    # ── Helper builders ───────────────────────────────────────────────────────
    def regime_class(r: str) -> str:
        return {"TRENDING_UP": "regime-up", "TRENDING_DOWN": "regime-down",
                "HIGH_VOLATILITY": "regime-vol", "CONSOLIDATION": "regime-cons"}.get(r, "regime-mean")

    def badge(text, color="blue") -> str:
        return f'<span class="badge badge-{color}">{text}</span>'

    def pct_cell(val) -> str:
        cls = _pct_color(val)
        return f'<td class="{cls}">{_fmt_pct(val)}</td>'

    def build_index_table(rows: list) -> str:
        if not rows:
            return "<p>No data</p>"
        html = ('<table class="sticky-header"><thead><tr>'
                '<th>#</th><th>Index</th><th>Start</th><th>End</th>'
                '<th>Change %</th><th>Adv Days</th><th>Avg PE</th>'
                '</tr></thead><tbody>')
        for i, r in enumerate(rows, 1):
            pct = r.get("pct_change", 0)
            cls = _pct_color(pct)
            adv = f"{r.get('adv_days',0)}/{r.get('total_days',0)}"
            pe  = _fmt_val(r.get("avg_pe"), 1) if r.get("avg_pe") else "—"
            html += (f'<tr><td>{i}</td><td>{r.get("index","?")}</td>'
                     f'<td>{abs(float(r["start_close"])):.2f}</td>'
                     f'<td>{abs(float(r["end_close"])):.2f}</td>'
                     f'<td class="{cls}">{_fmt_pct(pct)}</td>'
                     f'<td>{adv}</td><td>{pe}</td></tr>')
        html += "</tbody></table>"
        return html

    def build_stock_table(rows: list, title: str = "", max_rows: int = 50) -> str:
        if not rows:
            return "<p style='color:#6e7681'>No data</p>"
        has_deliv   = any(r.get("avg_deliv_pct") is not None for r in rows[:5])
        has_score   = any("score" in r for r in rows[:3])
        has_sector  = any(r.get("sector") for r in rows[:5])
        has_screens = any(r.get("screens") for r in rows[:3])
        html = f'<table><thead><tr><th>#</th><th>Symbol</th><th>Change %</th>'
        if has_deliv:   html += '<th>Avg Delivery%</th>'
        if has_score:   html += '<th>Score</th>'
        if has_screens: html += '<th>Screens</th>'
        if has_sector:  html += '<th>Sector</th>'
        html += '<th>Start</th><th>End</th></tr></thead><tbody>'
        for i, r in enumerate(rows[:max_rows], 1):
            sym   = r.get("symbol", r.get("SYMBOL", "?"))
            pct   = r.get("pct_chg", r.get("pct_change", 0))
            cls   = _pct_color(pct)
            raw_s = r.get("start_close")
            raw_e = r.get("end_close")
            start = f"{abs(float(raw_s)):.2f}" if raw_s is not None else "—"
            end   = f"{abs(float(raw_e)):.2f}" if raw_e is not None else "—"
            html += f'<tr><td>{i}</td><td><strong>{sym}</strong></td>'
            html += f'<td class="{cls}">{_fmt_pct(pct)}</td>'
            if has_deliv:
                d = r.get("avg_deliv_pct")
                try:
                    d = abs(float(d)) if d is not None else None
                except Exception:
                    d = None
                dcls = "pos-strong" if d and d >= 70 else "pos" if d and d >= 50 else "neutral"
                html += f'<td class="{dcls}">{f"{d:.1f}%" if d is not None else "—"}</td>'
            if has_score:   html += f'<td>{r.get("score","—")}</td>'
            if has_screens: html += f'<td><small>{r.get("screens","—")}</small></td>'
            if has_sector:  html += f'<td><small>{r.get("sector","—")}</small></td>'
            html += f'<td>{start}</td><td>{end}</td></tr>'
        html += "</tbody></table>"
        return html

    def build_flow_table(flow_table: list) -> str:
        if not flow_table:
            return "<p style='color:#6e7681'>No EQ flow data in this window</p>"
        html = ('<table><thead><tr><th>Date</th><th>FII Net (₹Cr)</th>'
                '<th>DII Net (₹Cr)</th><th>Combined (₹Cr)</th></tr></thead><tbody>')
        for r in flow_table:
            fii = r.get("fii_net")
            dii = r.get("dii_net")
            ins = r.get("inst_net", 0)
            fcls = _pct_color(fii) if fii else "neutral"
            dcls = _pct_color(dii) if dii else "neutral"
            icls = _pct_color(ins)
            html += (f'<tr><td>{r.get("date","?")}</td>'
                     f'<td class="{fcls}">{_fmt_val(fii, 2, " Cr") if fii else "—"}</td>'
                     f'<td class="{dcls}">{_fmt_val(dii, 2, " Cr") if dii else "—"}</td>'
                     f'<td class="{icls}">{_fmt_val(ins, 2, " Cr")}</td></tr>')
        html += "</tbody></table>"
        return html

    def news_block(news: list) -> str:
        if not news:
            return '<p style="color:#6e7681;font-size:12px">No news fetched for this sector</p>'
        html = ""
        for n in news[:8]:
            src   = n.get("source", "")
            title = n.get("title", "")[:120]
            link  = n.get("link", "")
            pub   = n.get("published", "")[:20]
            href  = f'<a href="{link}" target="_blank" style="color:#58a6ff;text-decoration:none">{title}</a>' \
                    if link else title
            html += (f'<div class="news-item">'
                     f'<span class="news-source">[{src}]</span>{href}'
                     f'<span style="color:#6e7681;font-size:11px;margin-left:8px">{pub}</span>'
                     f'</div>')
        return html

    # ── PART 1: Macro Intelligence ────────────────────────────────────────────

    # Regime
    rm = regime
    regime_label = rm.get("regime", "UNKNOWN")
    regime_emoji = {"TRENDING_UP": "🟢", "TRENDING_DOWN": "🔴",
                    "HIGH_VOLATILITY": "⚡", "CONSOLIDATION": "🟡",
                    "MEAN_REVERTING": "🔄"}.get(regime_label, "⚪")

    # Flow
    gm      = gamma.get("eq_flow", {}).get("metrics", {})
    fs      = gamma.get("flow_score", {})
    flow_t  = gamma.get("eq_flow", {}).get("flow_table", [])
    fii_cum = gm.get("fii_cumulative_cr", 0) or 0
    dii_cum = gm.get("dii_cumulative_cr", 0) or 0

    # Risk
    risk_score = delta.get("risk_score", 5)
    risk_level = delta.get("risk_level", "MEDIUM")
    risk_clr   = "green" if risk_score <= 3 else "amber" if risk_score <= 6 else "red"

    # Breadth
    breadth = alpha.get("breadth", {})
    avg_adv = breadth.get("avg_pct_adv", 0)

    # KPI cards row
    nifty_close = rm.get("latest_close", "N/A")
    nifty_pct   = rm.get("window_pct", 0)
    nifty_pe    = rm.get("pe", "N/A")
    nifty_vol   = rm.get("vol_ann_pct", "N/A")

    kpi_cards = f"""
<div class="grid-4">
  <div class="card">
    <div class="kpi-label">Nifty 50</div>
    <div class="kpi-value">{nifty_close}</div>
    <div class="kpi-sub {_pct_color(nifty_pct)}">{_fmt_val(nifty_pct, suffix='%')} ({n_days}d)</div>
  </div>
  <div class="card">
    <div class="kpi-label">Regime</div>
    <div class="kpi-value" style="font-size:15px">{regime_emoji} {regime_label}</div>
    <div class="kpi-sub">PE: {nifty_pe} | Vol: {nifty_vol}%</div>
  </div>
  <div class="card">
    <div class="kpi-label">FII/DII Flow ({n_days}d)</div>
    <div class="kpi-value {_pct_color(fii_cum)}" style="font-size:16px">
      FII {_fmt_val(fii_cum, 0, 'Cr')}
    </div>
    <div class="kpi-sub {_pct_color(dii_cum)}">DII {_fmt_val(dii_cum, 0, 'Cr')}</div>
  </div>
  <div class="card">
    <div class="kpi-label">Risk Level</div>
    <div class="kpi-value">{badge(risk_level, risk_clr)}</div>
    <div class="risk-bar"><div class="risk-fill" style="width:{risk_score*10}%;background:{'#3fb950' if risk_score<=3 else '#e3b341' if risk_score<=6 else '#f85149'}"></div></div>
    <div class="kpi-sub">{risk_score}/10 | Breadth: {avg_adv:.1f}% adv.</div>
  </div>
</div>"""

    # All indices tables
    top10 = build_index_table(alpha.get("top10_gainers", []))
    bot10 = build_index_table(list(reversed(alpha.get("top10_losers", []))))

    # Breadth by day table
    breadth_rows = ""
    for b in breadth.get("by_day", []):
        cls = "pos" if b["pct_adv"] >= 60 else "neg" if b["pct_adv"] <= 40 else "neutral"
        breadth_rows += (f'<tr><td>{b["date"]}</td><td>{b["advancing"]}</td>'
                         f'<td>{b["declining"]}</td><td class="{cls}">{b["pct_adv"]:.1f}%</td></tr>')

    # Cap rotation
    rot = alpha.get("cap_rotation", {})
    rot_html = f"""
<div class="grid-3">
  <div class="card"><div class="kpi-label">Large Cap</div>
    <div class="kpi-value {_pct_color(rot.get('largecap_avg_pct',0))}">{_fmt_val(rot.get('largecap_avg_pct',0),2,'%')}</div></div>
  <div class="card"><div class="kpi-label">Mid Cap</div>
    <div class="kpi-value {_pct_color(rot.get('midcap_avg_pct',0))}">{_fmt_val(rot.get('midcap_avg_pct',0),2,'%')}</div></div>
  <div class="card"><div class="kpi-label">Small Cap</div>
    <div class="kpi-value {_pct_color(rot.get('smallcap_avg_pct',0))}">{_fmt_val(rot.get('smallcap_avg_pct',0),2,'%')}</div></div>
</div>
<p style="margin-top:8px;color:#79c0ff">{rot.get('signal','N/A')}</p>"""

    # Risk flags
    risk_flags_html = "".join(
        f'<div style="padding:6px 0;border-bottom:1px solid #21262d">'
        f'<span style="color:#f85149">🔴</span> {f}</div>'
        for f in delta.get("risk_flags", [])
    )
    green_flags_html = "".join(
        f'<div style="padding:6px 0;border-bottom:1px solid #21262d">'
        f'<span style="color:#3fb950">🟢</span> {f}</div>'
        for f in delta.get("green_flags", [])
    )

    # Quality universe
    quality_rows = ""
    for r in delta.get("quality_universe", [])[:10]:
        roe_pct = f"{float(r.get('roe',0))*100:.0f}%" if r.get("roe") else "—"
        quality_rows += (
            f'<tr><td><strong>{r.get("symbol","?")}</strong></td>'
            f'<td><small>{r.get("sector","?")}</small></td>'
            f'<td>{_fmt_val(r.get("pe"),1)}</td>'
            f'<td class="pos">{roe_pct}</td>'
            f'<td>{_fmt_val(r.get("de"),1)}</td></tr>'
        )

    # Corp actions
    corp_rows = ""
    for r in delta.get("corporate_actions", [])[:12]:
        val = r.get("amount") or r.get("ratio") or "—"
        corp_rows += (f'<tr><td><strong>{r.get("symbol","?")}</strong></td>'
                      f'<td>{r.get("date","?")}</td>'
                      f'<td>{badge(r.get("action_type","?"), "blue")}</td>'
                      f'<td>{val}</td></tr>')

    # ── PART 2: Stock Universe ────────────────────────────────────────────────
    sc = beta.get("screens", {})

    composite_table  = build_stock_table(sc.get("composite", []))
    momentum_table   = build_stock_table(sc.get("momentum", [])[:15])
    delivery_table   = build_stock_table(sc.get("delivery", [])[:15])
    breakout_table   = build_stock_table(sc.get("breakouts", [])[:15])
    losers_table     = build_stock_table(sc.get("top_losers", [])[:10])

    # Sector rotation table
    sector_rows = ""
    for s in beta.get("sector_rotation", {}).get("all_sectors", [])[:15]:
        cls = _pct_color(s.get("avg_pct", 0))
        sector_rows += (f'<tr><td>{s.get("sector","?")}</td>'
                        f'<td class="{cls}">{_fmt_val(s.get("avg_pct",0),2,"%")}</td>'
                        f'<td>{s.get("stock_count",0)} stocks</td></tr>')

    # 52-week signals
    w52 = beta.get("w52", {})
    w52_high_table = build_stock_table(
        [{**r, "pct_chg": r.get("pct_from_high", 0)} for r in w52.get("near_high", [])]
    )
    w52_low_table = build_stock_table(
        [{**r, "pct_chg": r.get("pct_from_low", 0)} for r in w52.get("near_low", [])]
    )

    # ── PART 3: Index Deep Dives ──────────────────────────────────────────────
    drill_sections = ""
    for idx_report in alpha.get("index_drilldowns", []):
        idx_name   = idx_report.get("index_name", "?")
        idx_pct    = idx_report.get("index_pct_change", 0)
        idx_pe     = idx_report.get("avg_pe")
        idx_start  = idx_report.get("index_start")
        idx_end    = idx_report.get("index_end")
        adv_d      = idx_report.get("adv_days", 0)
        tot_d      = idx_report.get("total_days", 0)
        n_stocks   = idx_report.get("constituents_count", 0)
        llm_text   = idx_report.get("llm_analysis", "Analysis not available")
        news       = idx_report.get("news", [])
        all_stocks = idx_report.get("all_stocks", [])

        pct_cls    = _pct_color(idx_pct)
        idx_badge  = badge(f"{_fmt_val(idx_pct, 2, '%')}", "green" if idx_pct > 0 else "red")

        top_stocks   = build_stock_table(idx_report.get("top_gainers", [])[:10], max_rows=10)
        worst_stocks = build_stock_table(idx_report.get("worst_performers", [])[:5], max_rows=5)
        conv_stocks  = build_stock_table(idx_report.get("conviction_buys", [])[:5], max_rows=5)
        all_stk_tbl  = build_stock_table(all_stocks, max_rows=100)

        drill_sections += f"""
<div class="index-section section">
  <h2>{idx_name} {idx_badge}
    <span style="font-size:13px;color:#8b949e;font-weight:normal;margin-left:12px">
      {_fmt_val(idx_start,2)} → {_fmt_val(idx_end,2)} &nbsp;|&nbsp;
      Adv: {adv_d}/{tot_d} days &nbsp;|&nbsp;
      Avg PE: {_fmt_val(idx_pe,1) if idx_pe else '—'} &nbsp;|&nbsp;
      {n_stocks} stocks
    </span>
  </h2>

  <div class="llm-box">{llm_text}</div>

  <div class="grid-2" style="margin-top:16px">
    <div>
      <h4>🏆 Top Gainers</h4>
      {top_stocks}
    </div>
    <div>
      <h4>📉 Worst Performers</h4>
      {worst_stocks}
    </div>
  </div>

  {"<div><h4>💎 High Conviction (Delivery ≥60%)</h4>" + conv_stocks + "</div>" if idx_report.get("conviction_buys") else ""}

  <details style="margin-top:16px">
    <summary style="cursor:pointer;color:#58a6ff;font-size:13px">
      📊 All {n_stocks} Constituent Stocks — Click to Expand
    </summary>
    <div style="margin-top:8px;overflow-x:auto">{all_stk_tbl}</div>
  </details>

  <div style="margin-top:16px">
    <h4>📰 Recent Sector News</h4>
    {news_block(news)}
  </div>
</div>"""

    # ── Assemble full HTML ────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MICC v2 — {n_days}-Day Report | {start_d} → {end_d}</title>
<style>{css}</style>
MICC_HEAD_JS
</head>
<body>
<div class="container">

<!-- HEADER -->
<h1>🏛️ MICC v2 — Market Intelligence Command Center</h1>
<div class="meta">
  {n_days}-Day Analysis &nbsp;|&nbsp; {start_d} → {end_d} &nbsp;|&nbsp;
  Generated: {now} &nbsp;|&nbsp;
  {alpha.get("total_indices",0)} indices tracked &nbsp;|&nbsp;
  {beta.get("total_symbols",0)} stocks screened
</div>

{kpi_cards}

<!-- NAVBAR -->
<nav class="navbar">
  <a href="#part1">📊 Part 1: Macro</a>
  <a href="#regime">1.1 Regime</a>
  <a href="#indices">1.2 Indices</a>
  <a href="#flow">1.3 FII/DII Flow</a>
  <a href="#risk">1.4 Risk</a>
  <a href="#synthesis">1.5 Synthesis</a>
  <a href="#part2">🔍 Part 2: Stocks</a>
  <a href="#composite">2.1 Composite</a>
  <a href="#momentum">2.2 Momentum</a>
  <a href="#delivery">2.3 Delivery</a>
  <a href="#breakouts">2.4 Breakouts</a>
  <a href="#sectors">2.6 Sectors</a>
  <a href="#w52">2.7 52W</a>
  <a href="#part3">📈 Part 3: Index Deep Dives</a>
</nav>

<!-- ═════════════════ PART 1 ═════════════════ -->
<div class="part-header" id="part1">📊 PART 1 — MACRO INTELLIGENCE</div>

<!-- 1.1 Regime -->
<div class="section" id="regime">
  <h2>1.1 Market Regime — Nifty 50</h2>
  <div class="regime-box {regime_class(regime_label)}">
    <strong>{regime_emoji} {regime_label}</strong> &nbsp;
    {badge(rm.get('confidence','?'), 'blue')} &nbsp;
    Nifty: <strong>{nifty_close}</strong> &nbsp;
    {n_days}d return: <span class="{_pct_color(nifty_pct)}">{_fmt_val(nifty_pct, suffix='%')}</span>
  </div>
  <div class="grid-4">
    <div class="card"><div class="kpi-label">PE</div><div class="kpi-value">{nifty_pe}</div></div>
    <div class="card"><div class="kpi-label">PB</div><div class="kpi-value">{rm.get('pb','N/A')}</div></div>
    <div class="card"><div class="kpi-label">Vol (Ann.)</div><div class="kpi-value">{nifty_vol}%</div></div>
    <div class="card"><div class="kpi-label">Vol Ratio 5d/20d</div><div class="kpi-value">{rm.get('volume_ratio','N/A')}</div></div>
  </div>
  <div class="grid-2" style="margin-top:14px">
    <div>
      <h4>MA Levels</h4>
      <div class="card" style="font-size:13px">
        MA20: {_fmt_val(rm.get('ma20'),2)} — {badge('ABOVE','green') if rm.get('above_ma20') else badge('BELOW','red')}<br>
        MA50: {_fmt_val(rm.get('ma50'),2)} — {badge('ABOVE','green') if rm.get('above_ma50') else badge('BELOW','red')}
      </div>
    </div>
    <div>
      <h4>Cap Rotation</h4>
      {rot_html}
    </div>
  </div>
  <div class="llm-box" style="margin-top:14px">{alpha.get("regime_analysis","N/A")}</div>
</div>

<!-- 1.2 All Indices -->
<div class="section" id="indices">
  <h2>1.2 All {alpha.get("total_indices",0)} Indices Performance ({n_days} Days)</h2>
  <div class="grid-2">
    <div>
      <h4>🏆 Top 10 Gainers</h4>
      {top10}
    </div>
    <div>
      <h4>📉 Top 10 Losers</h4>
      {bot10}
    </div>
  </div>
  <details style="margin-top:12px">
    <summary style="cursor:pointer;color:#58a6ff;font-size:13px">
      📅 Daily Breadth — Click to Expand
    </summary>
    <table style="margin-top:8px;max-width:400px">
      <tr><th>Date</th><th>Adv</th><th>Dec</th><th>% Adv</th></tr>
      {breadth_rows}
    </table>
  </details>
</div>

<!-- 1.3 FII/DII Flow -->
<div class="section" id="flow">
  <h2>1.3 Institutional Flow Intelligence (FII/DII)</h2>
  <div class="grid-4">
    <div class="card">
      <div class="kpi-label">FII Cumulative</div>
      <div class="kpi-value {_pct_color(fii_cum)}" style="font-size:16px">{fmt_cr(fii_cum,0)}</div>
      <div class="kpi-sub">{gm.get("fii_buy_days",0)} buy / {gm.get("fii_sell_days",0)} sell days</div>
    </div>
    <div class="card">
      <div class="kpi-label">DII Cumulative</div>
      <div class="kpi-value {_pct_color(dii_cum)}" style="font-size:16px">{fmt_cr(dii_cum,0)}</div>
      <div class="kpi-sub">{gm.get("dii_buy_days",0)} buy days</div>
    </div>
    <div class="card">
      <div class="kpi-label">Flow Score</div>
      <div class="kpi-value">{fs.get("flow_score",0)}/10</div>
      <div class="kpi-sub">{badge(fs.get("flow_sentiment","?"), "green" if (fs.get("flow_score",0) or 0)>0 else "red")}</div>
    </div>
    <div class="card">
      <div class="kpi-label">FII Trend</div>
      <div class="kpi-value" style="font-size:15px">{gm.get("fii_trend","?")}</div>
      <div class="kpi-sub">Divergence: {'YES ⚠️' if gm.get('fii_dii_divergence') else 'No'}</div>
    </div>
  </div>
  <div style="margin-top:14px">{build_flow_table(flow_t)}</div>
  <h4 style="margin-top:12px">Flow Score Components</h4>
  {"".join(f'<div style="font-size:12px;padding:3px 0;color:#8b949e">• {c}</div>' for c in fs.get("components",[]))}
  <div class="llm-box" style="margin-top:12px">{gamma.get("analysis","N/A")}</div>
</div>

<!-- 1.4 Risk -->
<div class="section" id="risk">
  <h2>1.4 Risk & Corporate Intelligence</h2>
  <div class="grid-2">
    <div>
      <h4>Risk Flags</h4>
      {risk_flags_html or '<p style="color:#3fb950">No significant risk flags</p>'}
      <h4 style="margin-top:12px">Positive Signals</h4>
      {green_flags_html or '<p style="color:#6e7681">No green flags</p>'}
    </div>
    <div>
      <h4>Quality Universe (PE 5-30, ROE>15%)</h4>
      <table>
        <tr><th>Symbol</th><th>Sector</th><th>PE</th><th>ROE</th><th>D/E</th></tr>
        {quality_rows or "<tr><td colspan='5'>No data</td></tr>"}
      </table>
    </div>
  </div>
  {f'<div style="margin-top:14px"><h4>Corporate Actions in Window</h4><table><tr><th>Symbol</th><th>Date</th><th>Action</th><th>Value</th></tr>{corp_rows}</table></div>' if corp_rows else ""}
  <div class="llm-box" style="margin-top:12px">{delta.get("analysis","N/A")}</div>
</div>

<!-- 1.5 Master Synthesis -->
<div class="section" id="synthesis" style="border-color:#30363d">
  <h2>1.5 🤖 MICC Master Synthesis (All 4 Agents)</h2>
  <div class="llm-box" style="font-size:14px;line-height:1.8">{synthesis}</div>
</div>

<!-- ═════════════════ PART 2 ═════════════════ -->
<div class="part-header" id="part2">🔍 PART 2 — STOCK UNIVERSE INTELLIGENCE</div>

<!-- 2.1 Composite -->
<div class="section" id="composite">
  <h2>2.1 ⭐ Composite Conviction Watchlist (Multi-Screen)</h2>
  {composite_table}
  <div class="llm-box" style="margin-top:14px">{beta.get("synthesis","N/A")}</div>
</div>

<!-- 2.2-2.5 Individual screens -->
<div class="grid-2">
  <div class="section" id="momentum">
    <h2>2.2 🚀 Momentum Screen</h2>
    {momentum_table}
  </div>
  <div class="section" id="delivery">
    <h2>2.3 📦 Delivery Leaders</h2>
    {delivery_table}
  </div>
</div>

<div class="grid-2">
  <div class="section" id="breakouts">
    <h2>2.4 💥 Volume Breakouts</h2>
    {breakout_table}
  </div>
  <div class="section">
    <h2>2.5 📉 Top Losers</h2>
    {losers_table}
  </div>
</div>

<!-- Sector rotation -->
<div class="section" id="sectors">
  <h2>2.6 🏭 Sector Rotation</h2>
  <table style="max-width:500px">
    <tr><th>Sector</th><th>Avg Return ({n_days}d)</th><th>Stocks</th></tr>
    {sector_rows or "<tr><td colspan='3'>No sector data</td></tr>"}
  </table>
</div>

<!-- 52-week signals -->
<div class="grid-2">
  <div class="section" id="w52">
    <h2>2.7 🚀 Near 52-Week Highs</h2>
    {w52_high_table}
  </div>
  <div class="section">
    <h2>2.8 🔴 Near 52-Week Lows</h2>
    {w52_low_table}
  </div>
</div>

<!-- ═════════════════ PART 3 ═════════════════ -->
<div class="part-header" id="part3">📈 PART 3 — INDEX DEEP DIVES (Top {len(alpha.get("index_drilldowns",[]))} Indices)</div>

{drill_sections or '<div class="section"><p>No index drill-down data available</p></div>'}

<!-- FOOTER -->
<div style="text-align:center;padding:30px 0 10px;color:#6e7681;font-size:12px">
  MICC v2 — Market Intelligence Command Center &nbsp;|&nbsp; Generated: {now}<br>
  LLM: Groq (llama-3.3-70b) + Ollama (gemma3:4b) &nbsp;|&nbsp;
  Data: NSE India &nbsp;|&nbsp; For research purposes only. Not financial advice.
</div>

</div>

</div>
</body>
</html>"""

    # Inject JS block separately (never embed JS regex/arrow-funcs inside f-strings)
    _head_js = """<script>
function makeTableSortable(table) {
  var headers = table.querySelectorAll("th");
  headers.forEach(function(th, col) {
    th.classList.add("sortable");
    th.dataset.dir = "none";
    th.addEventListener("click", function() {
      var dir = th.dataset.dir === "asc" ? "desc" : "asc";
      headers.forEach(function(h) { h.dataset.dir = "none"; h.classList.remove("sort-asc","sort-desc"); });
      th.dataset.dir = dir;
      th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
      var tbody = table.querySelector("tbody");
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll("tr"));
      rows.sort(function(a, b) {
        var av = a.cells[col] ? a.cells[col].textContent.replace(/[+%\u20b9,]/g,"").trim() : "";
        var bv = b.cells[col] ? b.cells[col].textContent.replace(/[+%\u20b9,]/g,"").trim() : "";
        var an = parseFloat(av), bn = parseFloat(bv);
        var cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
        return dir === "asc" ? cmp : -cmp;
      });
      rows.forEach(function(r) { tbody.appendChild(r); });
    });
  });
}
function renderMarkdown() {
  document.querySelectorAll(".llm-box").forEach(function(el) {
    var h = el.textContent;
    h = h.replace(/^### (.+)$/gm, '<h3 style="color:#79c0ff;font-size:14px;margin:12px 0 5px">$1</h3>');
    h = h.replace(/^## (.+)$/gm, '<h3 style="color:#58a6ff;font-size:15px;margin:14px 0 6px;border-bottom:1px solid #21262d;padding-bottom:4px">$1</h3>');
    h = h.replace(/^# (.+)$/gm, '<h3 style="color:#e6edf3;font-size:16px;margin:14px 0 6px">$1</h3>');
    h = h.replace(/[*][*](.+?)[*][*]/g, '<strong style="color:#e6edf3">$1</strong>');
    h = h.replace(/[*]([^\n*]+?)[*]/g, '<em>$1</em>');
    h = h.replace(/`([^`]+)`/g, '<code style="background:#21262d;padding:1px 5px;border-radius:3px;font-size:12px">$1</code>');
    h = h.replace(/^[-] (.+)$/gm, '<li style="margin-bottom:3px">$1</li>');
    h = h.replace(/^[0-9]+[.] (.+)$/gm, '<li style="margin-bottom:3px">$1</li>');
    h = h.replace(/\n\n/g, '</p><p style="margin-bottom:8px">');
    h = "<p style='margin-bottom:8px'>" + h + "</p>";
    h = h.replace(/<p[^>]*><[/]p>/g, "");
    el.innerHTML = '<div class="llm-rendered">' + h + '</div>';
    el.style.whiteSpace = "normal";
  });
}
document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll("table").forEach(makeTableSortable);
  renderMarkdown();
});
</script>"""
    html = html.replace("MICC_HEAD_JS", _head_js)

    out_path.write_text(html, encoding="utf-8")
    print(f"[Engine] HTML saved → {out_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM SUMMARY BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_telegram_message(alpha: dict, beta: dict, gamma: dict, delta: dict,
                             synthesis: str, n_days: int) -> str:
    """Build a comprehensive Telegram message with all key data."""
    start_d = alpha.get("start_date", "?")
    end_d   = alpha.get("end_date", "?")
    rm      = alpha.get("regime", {})
    gm      = gamma.get("eq_flow", {}).get("metrics", {})
    fs      = gamma.get("flow_score", {})
    sc      = beta.get("screens", {})

    regime_icons = {"TRENDING_UP": "🟢", "TRENDING_DOWN": "🔴",
                    "HIGH_VOLATILITY": "⚡", "CONSOLIDATION": "🟡",
                    "MEAN_REVERTING": "🔄"}
    re_icon = regime_icons.get(rm.get("regime", ""), "⚪")

    top5_idx = "\n".join(
        f"  {'🟢' if r['pct_change']>0 else '🔴'} `{r['index'][:28]}` `{r['pct_change']:+.2f}%`"
        for r in alpha.get("top10_gainers", [])[:5]
    )
    bot3_idx = "\n".join(
        f"  🔴 `{r['index'][:28]}` `{r['pct_change']:+.2f}%`"
        for r in alpha.get("top10_losers", [])[:3]
    )

    comp_stocks = "\n".join(
        f"  ⭐ `{r.get('symbol','?')}` `{r.get('pct_chg',0):+.2f}%` [{r.get('screens','?')}]"
        for r in sc.get("composite", [])[:6]
    )

    drill_names = " | ".join(
        r.get("index_name", "?") for r in alpha.get("index_drilldowns", [])
    )

    risk_flags_str = "\n".join(
        f"  🔴 {f[:70]}"
        for f in delta.get("risk_flags", [])[:3]
    )
    green_flags_str = "\n".join(
        f"  🟢 {f[:70]}"
        for f in delta.get("green_flags", [])[:2]
    )

    synthesis_short = synthesis[:800] + ("..." if len(synthesis) > 800 else "")

    msg = f"""*🏛️ MICC v2 — {n_days}-DAY INTELLIGENCE REPORT*
📅 {start_d} → {end_d}
{'─'*38}

*{re_icon} NIFTY 50:* `{rm.get('latest_close','N/A')}` `{rm.get('window_pct',0):+.2f}%`
  Regime: `{rm.get('regime','?')}` | PE: `{rm.get('pe','N/A')}` | Vol: `{rm.get('vol_ann_pct','N/A')}%`
  MA20: {'✅' if rm.get('above_ma20') else '❌'} | MA50: {'✅' if rm.get('above_ma50') else '❌'}

*📊 TOP INDICES:*
{top5_idx}
*Worst:*
{bot3_idx}

*💰 INSTITUTIONAL FLOW:*
  FII: `{fmt_cr(gm.get('fii_cumulative_cr',0),0)}` ({gm.get('fii_trend','?')})
  DII: `{fmt_cr(gm.get('dii_cumulative_cr',0),0)}` | Combined: `{fmt_cr(gm.get('inst_cumulative_cr',0),0)}`
  Flow Score: `{fs.get('flow_score',0)}/10` → {fs.get('flow_sentiment','?')}

*⭐ COMPOSITE WATCHLIST:*
{comp_stocks or '  No composite picks'}

*⚡ RISK:* `{delta.get('risk_level','?')}` ({delta.get('risk_score','?')}/10)
{risk_flags_str}
{green_flags_str}

*🔬 INDEX DEEP DIVES:*
  {drill_names}

{'─'*38}
*🤖 MASTER SYNTHESIS:*
{synthesis_short}

_Generated: {now_ist()} | MICC v2_"""

    return msg


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

def run_engine(n_days: int, send_telegram: bool = False) -> dict:
    """Run all 4 agents, synthesise, generate HTML, optionally send Telegram."""
    from datetime import datetime as dt
    t0 = dt.now()

    print(f"\n{'='*65}")
    print(f"  MICC v2 ENGINE — {n_days} TRADING DAYS")
    print(f"{'='*65}\n")

    # ── Resolve dates ─────────────────────────────────────────────────────────
    dates = get_trading_dates(n_days)
    if not dates:
        print("[Engine] No dates found in DB. Check market_snapshot.")
        return {}

    print(f"[Engine] Window: {dates[0]} → {dates[-1]} ({len(dates)} dates)\n")

    # ── Logging setup ────────────────────────────────────────────────────────
    from datetime import datetime as _dt2
    import traceback as _tb
    _log_dir  = Path("agents/logs")
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = _log_dir / f"{_dt2.now().strftime('%Y%m%d_%H%M')}_engine.log"

    def _log(msg: str):
        """Write timestamped line to log file and print it."""
        line = f"[{_dt2.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(line + "\n")

    def _run_agent(name: str, fn, args):
        """
        Run one agent function safely.
        Returns (result_dict, elapsed_seconds, error_string_or_None).
        On failure returns a safe fallback dict so the engine keeps running.
        """
        _t = _dt2.now()
        try:
            result = fn(*args)
            elapsed = (_dt2.now() - _t).total_seconds()
            _log(f"[{name}] OK in {elapsed:.1f}s")
            return result, elapsed, None
        except Exception as _e:
            elapsed = (_dt2.now() - _t).total_seconds()
            tb = _tb.format_exc()
            _log(f"[{name}] FAILED after {elapsed:.1f}s: {_e}")
            _log(f"[{name}] Traceback:\n{tb}")
            # Send Telegram alert for agent failure
            try:
                import requests as _req, os as _os
                import certifi as _certifi
                _os.environ["REQUESTS_CA_BUNDLE"] = _certifi.where()
                _req.post(
                    "https://api.telegram.org/bot8420620581:AAGz9ztaCkj8KUJ5etBOaB0vmH69vHpeMRI/sendMessage",
                    json={
                        "chat_id": "6505636241",
                        "text": f"MICC {name} FAILED\n{str(_e)[:200]}\nSee: {_log_path.name}",
                    },
                    timeout=10,
                )
            except Exception:
                pass
            return {"agent": name, "error": str(_e), "traceback": tb[:500]}, elapsed, str(_e)

    # ── Run all 4 agents — each isolated ─────────────────────────────────────
    _log("=== ENGINE RUN START ===")
    _log(f"Window: {dates[0]} to {dates[-1]} ({len(dates)} days)")

    alpha, _t_alpha, _e_alpha = _run_agent("Alpha", run_alpha, [dates])
    _alpha_regime = alpha.get("regime", {}).get("regime", "") if isinstance(alpha.get("regime"), dict) else ""
    beta,  _t_beta,  _e_beta  = _run_agent("Beta",  run_beta,  [dates, _alpha_regime])
    gamma, _t_gamma, _e_gamma = _run_agent("Gamma", run_gamma, [dates, _alpha_regime])
    delta, _t_delta, _e_delta = _run_agent("Delta", run_delta, [dates, _alpha_regime])

    _agent_errors = [n for n, e in [
        ("Alpha", _e_alpha), ("Beta", _e_beta),
        ("Gamma", _e_gamma), ("Delta", _e_delta)
    ] if e is not None]

    if _agent_errors:
        _log(f"WARNING: {len(_agent_errors)} agent(s) failed: {', '.join(_agent_errors)}")
        _log("Engine will continue — HTML report will show partial data.")
    else:
        _log("All 4 agents completed successfully.")

    # ── Master synthesis ──────────────────────────────────────────────────────
    print("\n[Engine] Running master synthesis (all 4 agents)...")
    try:
        synthesis = synthesise_all(alpha, beta, gamma, delta, n_days)
        _log("Synthesis OK")
    except Exception as _e:
        _log(f"Synthesis FAILED: {_e}")
        synthesis = f"Synthesis unavailable: {_e}"

    # ── Save HTML ─────────────────────────────────────────────────────────────
    ts        = dt.now().strftime("%Y%m%d_%H%M")
    html_path = OUTPUT_DIR / f"{ts}_{n_days}d_report.html"
    generate_html(alpha, beta, gamma, delta, synthesis, n_days, html_path)

    output = {
        "n_days":    n_days,
        "generated": dt.now().isoformat(),
        "dates":     dates,
        "alpha":     alpha,
        "beta":      beta,
        "gamma":     gamma,
        "delta":     delta,
        "synthesis": synthesis,
    }

    # ── Send Telegram ─────────────────────────────────────────────────────────
    if send_telegram:
        print("[Engine] Sending Telegram report...")
        msg = build_telegram_message(alpha, beta, gamma, delta, synthesis, n_days)
        send_telegram_chunks(msg)
        print("[Engine] Telegram sent.")

    elapsed = (dt.now() - t0).total_seconds()

    # ── Final run summary in log ──────────────────────────────────────────────
    _log(f"=== ENGINE RUN COMPLETE ===")
    _log(f"Total: {elapsed:.1f}s | Alpha:{_t_alpha:.0f}s Beta:{_t_beta:.0f}s Gamma:{_t_gamma:.0f}s Delta:{_t_delta:.0f}s")
    if _agent_errors:
        _log(f"Failed agents: {', '.join(_agent_errors)}")
    else:
        _log("All agents OK")
    _log(f"Log: {_log_path}")

    print(f"\n[Engine] Done in {elapsed:.1f}s")
    print(f"[Engine] HTML → {html_path}")
    print(f"[Engine] Log  → {_log_path}")

    return output


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    import argparse

    DEFAULT_DAYS = 7

    parser = argparse.ArgumentParser(
        prog="micc_engine",
        description="MICC v2 - Market Intelligence Command Center",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  py micc_engine.py                  -- 7-day report (default)\n"
            "  py micc_engine.py 10               -- 10-day report\n"
            "  py micc_engine.py --days 10        -- 10-day report (explicit)\n"
            "  py micc_engine.py 7 --send         -- 7-day report + Telegram\n"
            "  py micc_engine.py --days 7 --send  -- 7-day report + Telegram\n"
        ),
    )
    parser.add_argument(
        "days_pos",
        nargs="?",
        type=int,
        default=None,
        metavar="DAYS",
        help=f"Trading days to analyse (1-{MAX_DAYS}). Backward-compat positional.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help=f"Trading days to analyse (1-{MAX_DAYS}). Overrides positional if given.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send report to Telegram after generation.",
    )
    args = parser.parse_args()

    # --days wins over positional; fallback to DEFAULT_DAYS
    n = (
        args.days
        if args.days is not None
        else (args.days_pos if args.days_pos is not None else DEFAULT_DAYS)
    )

    if not (1 <= n <= MAX_DAYS):
        parser.error(f"DAYS must be between 1 and {MAX_DAYS}. Got: {n}")

    tg = args.send

    print("\n" + "=" * 65)
    print("  MICC v2 - Market Intelligence Command Center")
    print("=" * 65)
    print(f"  Trading days  : {n}")
    print(f"  Telegram push : {'YES' if tg else 'NO  (add --send to enable)'}")
    print("-" * 65 + "\n")

    run_engine(n_days=n, send_telegram=tg)

