# -*- coding: utf-8 -*-
"""
MICC Phase 6 -- Agent Zeta: Watchlist Intelligence
===================================================
Screens:
  1. Price alerts  -- user-set levels triggered today
  2. Breakout watch -- within 3% of 52-week high (from parquet, proven pattern)
  3. Volume+delivery surge -- today vs 10-day average (from stock_data OHLCV)
  4. Stop-loss watch -- watchlist stocks > 2% below their 20-day MA
  5. Re-entry radar -- previously hot Beta stocks now pulling back 5-20%

Data sources (all proven working in existing agents):
  - stock_data: OHLCV, close IS NOT NULL  (universe queries)
  - stock_delivery: symbol, date, volume, delivery_qty, delivery_pct
  - signals_history: symbol, run_date, score, screen_tags  (Beta streaks)
  - Parquet: D:/marketDB/stocks/all/<SYM>/<SYM>_YYYY.parquet  (52w high)
  - micc_watchlist.json: { symbols: [...], alerts: [...], notes: {} }

Run:  py D:/MICC/agent_zeta.py
Send: py D:/MICC/agent_zeta.py --send
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── path setup ────────────────────────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent))
from micc_data import call_llm, fmt_pct, now_ist, send_telegram_chunks

DB          = r"D:\marketDB\db\market.db"
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
DA          = Path(r"D:\MICC")
OUTPUT_DIR  = DA / "agents" / "zeta"
WL_FILE     = DA / "micc_watchlist.json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOW      = 10    # trading days for averages
TOP_N       = 20
MIN_PRICE   = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# WATCHLIST
# ─────────────────────────────────────────────────────────────────────────────

def load_watchlist() -> dict:
    if WL_FILE.exists():
        try:
            return json.loads(WL_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"symbols": [], "alerts": [], "notes": {}}


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADERS  (all use sqlite3.connect() directly -- no get_conn())
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_date() -> str:
    conn = sqlite3.connect(DB, timeout=15)
    row = conn.execute(
        "SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL"
    ).fetchone()
    conn.close()
    return row[0] if row else ""


def load_universe(window: int = WINDOW) -> pd.DataFrame:
    """
    Load last `window` trading days of OHLCV from stock_data.
    Returns raw rows -- one row per (symbol, date).
    Columns: symbol, date, open, high, low, close, volume
    """
    conn = sqlite3.connect(DB, timeout=30)
    # get the N most recent dates
    date_rows = conn.execute(
        "SELECT DISTINCT date FROM stock_data WHERE close IS NOT NULL "
        "ORDER BY date DESC LIMIT ?", (window,)
    ).fetchall()
    conn.close()

    if not date_rows:
        return pd.DataFrame()
    cutoff = date_rows[-1][0]

    conn = sqlite3.connect(DB, timeout=60)
    df = pd.read_sql_query(
        "SELECT symbol, date, open, high, low, close, volume "
        "FROM stock_data "
        "WHERE date >= ? AND close IS NOT NULL AND close >= ? "
        "ORDER BY symbol, date",
        conn, params=(cutoff, MIN_PRICE)
    )
    conn.close()
    df["close"]  = pd.to_numeric(df["close"],  errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    return df


def load_delivery(window: int = WINDOW) -> pd.DataFrame:
    """
    Load last `window` days from stock_delivery.
    Real columns: symbol, date, volume, delivery_qty, delivery_pct
    """
    conn = sqlite3.connect(DB, timeout=30)
    date_rows = conn.execute(
        "SELECT DISTINCT date FROM stock_delivery ORDER BY date DESC LIMIT ?",
        (window,)
    ).fetchall()
    conn.close()

    if not date_rows:
        return pd.DataFrame()
    cutoff = date_rows[-1][0]

    conn = sqlite3.connect(DB, timeout=30)
    df = pd.read_sql_query(
        "SELECT symbol, date, volume, delivery_qty, delivery_pct "
        "FROM stock_delivery WHERE date >= ? ORDER BY symbol, date",
        conn, params=(cutoff,)
    )
    conn.close()
    df["delivery_pct"] = pd.to_numeric(df["delivery_pct"], errors="coerce").fillna(0)
    return df


def load_52w_from_parquet(symbols: list) -> pd.DataFrame:
    """
    Compute 52-week high/low directly from parquet files.
    Uses the exact same pattern as get_52w_extremes() in micc_data.py.
    Returns: symbol, high_52w, low_52w, current_price, pct_from_high
    """
    cutoff = datetime.now() - timedelta(days=365)
    cur_year = datetime.now().year
    years = [cur_year - 1, cur_year]
    records = []

    for sym in symbols:
        folder = PARQUET_ROOT / sym
        if not folder.exists():
            continue
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
            continue
        df = pd.concat(frames, ignore_index=True)
        if "date" not in df.columns or "close" not in df.columns:
            continue
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[df["date"] >= pd.Timestamp(cutoff)].copy()
        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
        if closes.empty:
            continue
        high = float(closes.max())
        low  = float(closes.min())
        cur  = float(closes.iloc[-1])
        records.append({
            "symbol":       sym,
            "high_52w":     round(high, 2),
            "low_52w":      round(low, 2),
            "current_price":round(cur, 2),
            "pct_from_high":round((cur / high - 1) * 100, 2),
        })
    return pd.DataFrame(records) if records else pd.DataFrame()


def load_signals_history(days: int = 10) -> pd.DataFrame:
    """Last `days` run_dates from signals_history for streak computation."""
    conn = sqlite3.connect(DB, timeout=15)
    rows = conn.execute(
        "SELECT DISTINCT run_date FROM signals_history "
        "ORDER BY run_date DESC LIMIT ?", (days,)
    ).fetchall()
    if not rows:
        conn.close()
        return pd.DataFrame()
    cutoff = rows[-1][0]
    df = pd.read_sql_query(
        "SELECT symbol, run_date, score, screen_tags FROM signals_history "
        "WHERE run_date >= ? ORDER BY symbol, run_date",
        conn, params=(cutoff,)
    )
    conn.close()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SCREENS
# ─────────────────────────────────────────────────────────────────────────────

def screen_price_alerts(universe: pd.DataFrame, alerts: list) -> list:
    if not alerts or universe.empty:
        return []
    # latest price per symbol
    latest = (universe.sort_values("date")
                      .groupby("symbol", sort=False)["close"]
                      .last()
                      .reset_index())   # columns: symbol, close
    price_map = dict(zip(latest["symbol"], latest["close"]))
    triggered = []
    for a in alerts:
        sym   = str(a.get("symbol", "")).upper()
        level = float(a.get("level", 0))
        cond  = a.get("condition", "above")
        price = price_map.get(sym)
        if price is None:
            continue
        hit = (cond == "above" and price >= level) or (cond == "below" and price <= level)
        if hit:
            triggered.append({
                "symbol":    sym,
                "condition": cond,
                "level":     level,
                "price":     round(float(price), 2),
                "pct_from":  round((float(price) - level) / level * 100, 2),
            })
    return triggered


def screen_breakout_watch(w52: pd.DataFrame, threshold_pct: float = 3.0) -> list:
    """
    Stocks within threshold_pct% of their 52-week high.
    w52 comes from load_52w_from_parquet() -- already has pct_from_high.
    """
    if w52.empty:
        return []
    near = w52[
        (w52["pct_from_high"] >= -threshold_pct) &
        (w52["pct_from_high"] <= 0) &
        (w52["current_price"] >= MIN_PRICE)
    ].copy()
    near = near.sort_values("pct_from_high", ascending=False)  # closest to high first
    results = []
    for _, r in near.head(TOP_N).iterrows():
        results.append({
            "symbol":       str(r["symbol"]),
            "close":        round(float(r["current_price"]), 2),
            "high_52w":     round(float(r["high_52w"]), 2),
            "pct_from_52h": round(abs(float(r["pct_from_high"])), 2),
        })
    return results


def screen_vol_delivery_surge(universe: pd.DataFrame,
                               delivery: pd.DataFrame) -> list:
    """
    Today's volume > 2x the window average AND delivery% > 40%.
    Uses stock_data for volume (reliable), stock_delivery for delivery_pct.
    """
    if universe.empty:
        return []

    dates = sorted(universe["date"].unique())
    if len(dates) < 2:
        return []
    today = dates[-1]

    today_df  = universe[universe["date"] == today].copy()
    hist_df   = universe[universe["date"] < today]

    # avg volume over history
    avg_vol = (hist_df.groupby("symbol")["volume"]
                      .mean()
                      .rename("avg_vol")
                      .reset_index())

    today_df = today_df.merge(avg_vol, on="symbol", how="left")
    today_df["vol_surge"] = (today_df["volume"] /
                              today_df["avg_vol"].replace(0, np.nan)).fillna(0)

    # merge delivery_pct for today
    if not delivery.empty:
        deliv_today = (delivery[delivery["date"] == today]
                       [["symbol", "delivery_pct"]]
                       .drop_duplicates("symbol"))
        today_df = today_df.merge(deliv_today, on="symbol", how="left")
        today_df["delivery_pct"] = today_df["delivery_pct"].fillna(0)
    else:
        today_df["delivery_pct"] = 0.0

    surges = today_df[today_df["vol_surge"] >= 2.0].sort_values(
        "vol_surge", ascending=False
    )
    results = []
    for _, r in surges.head(TOP_N).iterrows():
        results.append({
            "symbol":      str(r["symbol"]),
            "close":       round(float(r["close"]), 2),
            "vol_surge":   round(float(r["vol_surge"]), 2),
            "deliv_pct":   round(float(r.get("delivery_pct", 0)), 1),
            "date":        str(today),
        })
    return results


def screen_stoploss_watch(universe: pd.DataFrame, wl_syms: list) -> list:
    """Watchlist stocks more than 2% below their 20-day MA."""
    if universe.empty or not wl_syms:
        return []
    wl_upper = [s.upper() for s in wl_syms]
    sub = universe[universe["symbol"].isin(wl_upper)]
    results = []
    for sym, grp in sub.groupby("symbol"):
        grp = grp.sort_values("date")
        closes = grp["close"].values
        if len(closes) < 3:
            continue
        ma20  = float(np.mean(closes[-min(20, len(closes)):]))
        cur   = float(closes[-1])
        pct   = (cur - ma20) / ma20 * 100
        if pct < -2.0:
            results.append({
                "symbol":    str(sym),
                "close":     round(cur, 2),
                "ma20":      round(ma20, 2),
                "pct_vs_ma": round(pct, 2),
            })
    return sorted(results, key=lambda x: x["pct_vs_ma"])


def screen_reentry_radar(universe: pd.DataFrame,
                          signals_hist: pd.DataFrame) -> list:
    """
    Stocks that appeared in Beta screens recently AND have pulled back 5-20%
    from their recent peak -- potential re-entry setups.
    """
    if universe.empty or signals_hist.empty:
        return []
    hot_syms = set(signals_hist["symbol"].unique())
    dates = sorted(universe["date"].unique())
    if len(dates) < 3:
        return []
    today = dates[-1]

    results = []
    for sym in hot_syms:
        grp = universe[universe["symbol"] == sym].sort_values("date")
        if len(grp) < 3:
            continue
        closes = grp["close"].values
        peak   = float(np.max(closes[:-1]))
        cur    = float(closes[-1])
        if peak <= 0:
            continue
        pullback = (peak - cur) / peak * 100
        if not (5.0 <= pullback <= 20.0):
            continue
        ma10 = float(np.mean(closes[-min(10, len(closes)):]))
        results.append({
            "symbol":       str(sym),
            "close":        round(cur, 2),
            "recent_peak":  round(peak, 2),
            "pullback_pct": round(pullback, 2),
            "ma10":         round(ma10, 2),
            "near_ma10":    abs(cur - ma10) / ma10 * 100 < 3.0,
        })
    return sorted(results, key=lambda x: x["pullback_pct"])[:TOP_N]


def compute_streaks(wl_syms: list, signals_hist: pd.DataFrame) -> list:
    """Consecutive days each watchlist symbol appeared in Beta screens."""
    if not wl_syms or signals_hist.empty:
        return [{"symbol": s, "streak": 0, "score": 0.0, "tags": ""} for s in wl_syms]
    dates_sorted = sorted(signals_hist["run_date"].unique(), reverse=True)
    results = []
    for sym in [s.upper() for s in wl_syms]:
        sym_dates = set(signals_hist[signals_hist["symbol"] == sym]["run_date"])
        streak = 0
        for d in dates_sorted:
            if d in sym_dates:
                streak += 1
            else:
                break
        rows = signals_hist[signals_hist["symbol"] == sym]
        if not rows.empty:
            latest = rows.sort_values("run_date").iloc[-1]
            score = float(latest.get("score") or 0)
            tags  = str(latest.get("screen_tags") or "")
        else:
            score, tags = 0.0, ""
        results.append({"symbol": sym, "streak": streak,
                         "score": round(score, 1), "tags": tags})
    return sorted(results, key=lambda x: -x["streak"])


# ─────────────────────────────────────────────────────────────────────────────
# LLM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(breakouts, surges, reentries, sl_watch,
                 alerts, streaks, date) -> str:
    def fmt(items, keys, n=8):
        if not items:
            return "  None\n"
        return "\n".join(
            "  " + " | ".join(f"{k}={item.get(k,'?')}" for k in keys if k in item)
            for item in items[:n]
        ) + "\n"

    return f"""You are MICC Agent Zeta -- Watchlist Intelligence. Date: {date}

BREAKOUT WATCH (stocks within 3% of 52-week high):
{fmt(breakouts, ['symbol','close','pct_from_52h'])}
VOL+DELIVERY SURGE (2x+ average volume today):
{fmt(surges, ['symbol','close','vol_surge','deliv_pct'])}
RE-ENTRY RADAR (previous Beta picks, 5-20% pullback):
{fmt(reentries, ['symbol','close','pullback_pct','near_ma10'])}
STOP-LOSS WATCH (watchlist stocks below 20-day MA):
{fmt(sl_watch, ['symbol','close','pct_vs_ma'])}
TRIGGERED PRICE ALERTS:
{fmt(alerts, ['symbol','condition','level','price'])}
WATCHLIST STREAKS (consecutive Beta screen days):
{fmt(streaks, ['symbol','streak','score','tags'])}

Write a concise watchlist note (max 250 words):
BREAKOUT SETUPS: which names are closest to new highs and worth watching
FRESH MOMENTUM: best vol+delivery surge names
RE-ENTRY CANDIDATES: best pullback setups near MA10 support
RISK: any stop-loss warnings
ONE TRADE IDEA: highest conviction setup with brief rationale

Plain text only. CAPS for section headers. No markdown."""


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM FORMATTER
# ─────────────────────────────────────────────────────────────────────────────

def format_telegram(report: dict) -> str:
    lines = [f"*MICC Zeta -- Watchlist {report.get('date','?')}*", ""]

    alerts = report.get("triggered_alerts", [])
    if alerts:
        lines.append("*ALERTS TRIGGERED:*")
        for a in alerts:
            lines.append(f"  `{a['symbol']}` {a['condition'].upper()} "
                         f"{a['level']} @ `{a['price']}`")
        lines.append("")

    syms = report.get("watchlist_symbols", [])
    if syms:
        lines.append("*WATCHING:* " + " | ".join(f"`{s}`" for s in syms[:12]))
        lines.append("")

    streaks = report.get("watchlist_streaks", [])
    if streaks:
        lines.append("*STREAKS:*")
        for s in streaks[:8]:
            bar = "=" * min(s["streak"], 8)
            lines.append(f"  `{s['symbol']}` [{bar}] {s['streak']}d")
        lines.append("")

    breakouts = report.get("breakout_watch", [])[:5]
    if breakouts:
        lines.append("*NEAR 52w HIGH:*")
        for b in breakouts:
            lines.append(f"  `{b['symbol']}` {b['close']} | -{b['pct_from_52h']}% from high")
        lines.append("")

    surges = report.get("vol_delivery_surge", [])[:5]
    if surges:
        lines.append("*VOL SURGE:*")
        for s in surges:
            lines.append(f"  `{s['symbol']}` {s['vol_surge']}x | deliv {s['deliv_pct']}%")
        lines.append("")

    reentries = report.get("reentry_radar", [])[:5]
    if reentries:
        lines.append("*RE-ENTRY:*")
        for r in reentries:
            near = " [MA10]" if r.get("near_ma10") else ""
            lines.append(f"  `{r['symbol']}` -{r['pullback_pct']}%{near}")
        lines.append("")

    analysis = str(report.get("analysis", ""))
    if analysis:
        lines.append("*INTEL:*")
        lines.append(analysis[:500])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run_zeta(send: bool = False) -> dict:
    print("=" * 55)
    print("  AGENT ZETA -- Watchlist Intelligence")
    print("=" * 55)

    wl       = load_watchlist()
    wl_syms  = [s.upper() for s in wl.get("symbols", [])]
    wl_alerts= wl.get("alerts", [])
    print(f"  Watchlist: {len(wl_syms)} symbols | {len(wl_alerts)} alerts")

    latest_date = get_latest_date()
    print(f"  Latest DB date: {latest_date}")

    # --- load data ---
    print("  Loading universe (stock_data)...")
    universe = load_universe(WINDOW)
    print(f"    {len(universe)} rows, {universe['symbol'].nunique() if not universe.empty else 0} symbols")

    print("  Loading delivery (stock_delivery)...")
    delivery = load_delivery(WINDOW)
    print(f"    {len(delivery)} rows")

    print("  Loading 52w data (parquet)...")
    # Use all symbols visible in universe for breakout screen
    all_syms = universe["symbol"].unique().tolist() if not universe.empty else []
    # Limit to 2500 to avoid very long run -- sample if needed
    if len(all_syms) > 2500:
        all_syms = all_syms[:2500]
    w52 = load_52w_from_parquet(all_syms)
    print(f"    {len(w52)} symbols with 52w data")

    print("  Loading signals history...")
    sig_hist = load_signals_history(10)
    print(f"    {len(sig_hist)} signal rows")

    # --- screens ---
    print("  Screen 1: Price alerts...")
    triggered = screen_price_alerts(universe, wl_alerts)
    print(f"    {len(triggered)} triggered")

    print("  Screen 2: Breakout watch...")
    breakouts = screen_breakout_watch(w52, threshold_pct=3.0)
    print(f"    {len(breakouts)} near 52w high")

    print("  Screen 3: Vol+delivery surge...")
    surges = screen_vol_delivery_surge(universe, delivery)
    print(f"    {len(surges)} surge setups")

    print("  Screen 4: Stop-loss watch...")
    sl_watch = screen_stoploss_watch(universe, wl_syms)
    print(f"    {len(sl_watch)} below MA20")

    print("  Screen 5: Re-entry radar...")
    reentries = screen_reentry_radar(universe, sig_hist)
    print(f"    {len(reentries)} re-entry setups")

    print("  Watchlist streaks...")
    streaks = compute_streaks(wl_syms, sig_hist)

    print("  LLM analysis...")
    prompt   = build_prompt(breakouts, surges, reentries, sl_watch,
                             triggered, streaks, latest_date)
    analysis, _src = call_llm(prompt, max_tokens=800, label="Zeta")
    print(f"    {len(str(analysis))} chars")

    report = {
        "agent":              "zeta",
        "date":               latest_date,
        "generated_at":       now_ist(),
        "watchlist_symbols":  wl_syms,
        "triggered_alerts":   triggered,
        "breakout_watch":     breakouts,
        "vol_delivery_surge": surges,
        "stoploss_watch":     sl_watch,
        "reentry_radar":      reentries,
        "watchlist_streaks":  streaks,
        "analysis":           analysis,
    }

    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {out}")

    if send:
        msg = format_telegram(report)
        ok  = send_telegram_chunks(msg)
        print(f"  Telegram: {'OK' if ok else 'FAILED'}")

    print("=" * 55)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()
    run_zeta(send=args.send)
