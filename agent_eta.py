# -*- coding: utf-8 -*-
"""
MICC Phase 8 -- Agent Eta: Corporate Events Intelligence
=========================================================
Screens:
  1. Results Season Tracker  -- companies that reported earnings recently
     (detects "Financial Results" / "Quarterly Results" in subject)
  2. Dividend / Bonus / Split calendar
     (upcoming record dates from corporate_announcements)
  3. Insider Cluster Buying  -- multiple insiders buying same stock recently
     (3+ buy transactions in last 30 days = cluster signal)
  4. Big Insider Trades      -- single trades > Rs 1 Cr value
  5. Post-Results Price Reaction -- did Beta-screened stocks react to results?
     (cross-references signals_history with corporate_announcements dates)
  6. Earnings Surprise Calendar -- upcoming stocks with results due
     (based on historical pattern: same symbol had results ~90 days ago)

Output: agents/eta/last_report.json
Run:  py D:/MICC/agent_eta.py
Send: py D:/MICC/agent_eta.py --send
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from micc_data import call_llm, now_ist, send_telegram_chunks

DB         = r"D:\marketDB\db\market.db"
DA         = Path(r"D:\MICC")
OUTPUT_DIR = DA / "agents" / "eta"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK_CORP   = 30   # days to look back for corporate announcements
LOOKBACK_INSIDER = 30
CLUSTER_MIN     = 3    # min insider buys to flag as cluster
BIG_TRADE_CR    = 1.0  # Rs Cr threshold for big insider trade


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def cutoff(days: int) -> str:
    return (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

def today_str() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────────────────────────────────────

def load_announcements(days: int = LOOKBACK_CORP) -> pd.DataFrame:
    conn = sqlite3.connect(DB, timeout=15)
    df = pd.read_sql_query(
        "SELECT announcement_date, symbol, subject "
        "FROM corporate_announcements "
        "WHERE announcement_date >= ? "
        "ORDER BY announcement_date DESC",
        conn, params=(cutoff(days),)
    )
    conn.close()
    df["subject"] = df["subject"].fillna("").astype(str)
    df["symbol"]  = df["symbol"].fillna("").astype(str).str.upper().str.strip()
    return df


def load_insider(days: int = LOOKBACK_INSIDER) -> pd.DataFrame:
    conn = sqlite3.connect(DB, timeout=15)
    df = pd.read_sql_query(
        "SELECT filing_date, symbol, company, name, category, "
        "       transaction_type, quantity, price, value "
        "FROM insider_trading "
        "WHERE filing_date >= ? "
        "ORDER BY filing_date DESC",
        conn, params=(cutoff(days),)
    )
    conn.close()
    df["symbol"]           = df["symbol"].fillna("").astype(str).str.upper().str.strip()
    df["transaction_type"] = df["transaction_type"].fillna("").astype(str).str.upper()
    df["value"]            = pd.to_numeric(df["value"],    errors="coerce").fillna(0)
    df["quantity"]         = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["price"]            = pd.to_numeric(df["price"],    errors="coerce").fillna(0)
    return df


def load_signals_recent(days: int = 60) -> pd.DataFrame:
    conn = sqlite3.connect(DB, timeout=15)
    df = pd.read_sql_query(
        "SELECT symbol, run_date, score, screen_tags FROM signals_history "
        "WHERE run_date >= ? ORDER BY run_date DESC",
        conn, params=(cutoff(days),)
    )
    conn.close()
    return df


def get_price_reaction(symbol: str, event_date: str, window: int = 5) -> dict:
    """Get close price before and after event_date for a symbol."""
    conn = sqlite3.connect(DB, timeout=10)
    rows = conn.execute(
        "SELECT date, close FROM stock_data "
        "WHERE symbol = ? AND date BETWEEN ? AND ? AND close IS NOT NULL "
        "ORDER BY date",
        (symbol,
         (datetime.strptime(event_date, "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d"),
         (datetime.strptime(event_date, "%Y-%m-%d") + timedelta(days=window + 2)).strftime("%Y-%m-%d"))
    ).fetchall()
    conn.close()

    if len(rows) < 2:
        return {}

    dates  = [r[0] for r in rows]
    closes = [float(r[1]) for r in rows]

    # find index closest to event_date
    event_idx = None
    for i, d in enumerate(dates):
        if d >= event_date:
            event_idx = i
            break
    if event_idx is None or event_idx == 0:
        return {}

    pre  = closes[event_idx - 1]
    post = closes[min(event_idx + window - 1, len(closes) - 1)]
    ret  = round((post / pre - 1) * 100, 2) if pre > 0 else 0.0

    return {"pre": round(pre, 2), "post": round(post, 2), "ret_pct": ret,
            "event_date": event_date}


# ─────────────────────────────────────────────────────────────────────────────
# SCREENS
# ─────────────────────────────────────────────────────────────────────────────

RESULTS_KEYWORDS = [
    "financial result", "quarterly result", "unaudited result",
    "audited result", "annual result", "q1 result", "q2 result",
    "q3 result", "q4 result", "half year result"
]
DIVIDEND_KEYWORDS = ["dividend", "interim dividend", "final dividend"]
BONUS_KEYWORDS    = ["bonus"]
SPLIT_KEYWORDS    = ["stock split", "sub-division", "face value"]


def screen_results_season(ann: pd.DataFrame) -> list:
    """Companies that reported financial results recently."""
    mask = ann["subject"].str.lower().apply(
        lambda s: any(kw in s for kw in RESULTS_KEYWORDS)
    )
    results_df = ann[mask].copy()
    if results_df.empty:
        return []

    # deduplicate: one entry per symbol (most recent)
    results_df = (results_df.sort_values("announcement_date", ascending=False)
                             .drop_duplicates("symbol"))
    out = []
    for _, r in results_df.head(30).iterrows():
        out.append({
            "symbol":  r["symbol"],
            "date":    r["announcement_date"],
            "subject": r["subject"][:80],
        })
    return out


def screen_dividend_calendar(ann: pd.DataFrame) -> list:
    """Upcoming / recent dividend, bonus, split announcements."""
    out = []
    for _, r in ann.iterrows():
        subj_lower = r["subject"].lower()
        event_type = None
        if any(k in subj_lower for k in DIVIDEND_KEYWORDS):
            event_type = "DIVIDEND"
        elif any(k in subj_lower for k in BONUS_KEYWORDS):
            event_type = "BONUS"
        elif any(k in subj_lower for k in SPLIT_KEYWORDS):
            event_type = "SPLIT"
        if event_type:
            out.append({
                "symbol":     r["symbol"],
                "date":       r["announcement_date"],
                "event_type": event_type,
                "subject":    r["subject"][:80],
            })
    # deduplicate symbol+event_type
    seen = set()
    deduped = []
    for item in out:
        key = (item["symbol"], item["event_type"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:30]


def screen_insider_cluster(insider: pd.DataFrame) -> list:
    """Stocks with 3+ insider BUYS in the lookback window."""
    buys = insider[insider["transaction_type"].str.contains("BUY", na=False)]
    if buys.empty:
        return []
    counts = (buys.groupby("symbol")
                  .agg(buy_count=("name", "count"),
                       total_value=("value", "sum"),
                       names=("name", lambda x: " | ".join(x.unique()[:3])))
                  .reset_index())
    clusters = counts[counts["buy_count"] >= CLUSTER_MIN].sort_values(
        "total_value", ascending=False
    )
    out = []
    for _, r in clusters.head(20).iterrows():
        out.append({
            "symbol":      r["symbol"],
            "buy_count":   int(r["buy_count"]),
            "total_value_cr": round(float(r["total_value"]) / 1e7, 2),
            "insiders":    r["names"],
        })
    return out


def screen_big_insider_trades(insider: pd.DataFrame,
                               threshold_cr: float = BIG_TRADE_CR) -> list:
    """Single BUY/SELL insider trades above threshold_cr crores. Excludes pledge/revoke."""
    threshold = threshold_cr * 1e7
    # Only real buy/sell -- exclude PLEDGE, REVOKE, GIFT, TRANSMIT, INVOCATION
    real_tx = insider[insider["transaction_type"].apply(
        lambda t: any(kw in str(t).upper() for kw in ["BUY", "SELL", "PURCHASE", "SALE"])
    )].copy()
    big = real_tx[real_tx["value"] >= threshold].sort_values("value", ascending=False)
    if big.empty:
        return []
    out = []
    for _, r in big.head(20).iterrows():
        qty   = float(r["quantity"])
        val   = float(r["value"])
        price = float(r["price"])
        # recompute price if stored as 0 but qty > 0
        if price <= 0 and qty > 0:
            price = round(val / qty, 2)
        out.append({
            "symbol":      r["symbol"],
            "name":        str(r.get("name", ""))[:40],
            "category":    str(r.get("category", ""))[:30],
            "transaction": r["transaction_type"],
            "quantity":    int(qty),
            "price":       round(price, 2) if price > 0 else None,
            "value_cr":    round(val / 1e7, 2),
            "date":        r["filing_date"],
        })
    return out


def screen_post_results_reaction(results: list,
                                  signals: pd.DataFrame) -> list:
    """
    For stocks that (a) reported results AND (b) appeared in Beta screens,
    compute the 5-day price reaction after the results date.
    """
    if not results or signals.empty:
        return []

    hot_syms = set(signals["symbol"].unique())
    out = []
    for item in results:
        sym = item["symbol"]
        if sym not in hot_syms:
            continue
        reaction = get_price_reaction(sym, item["date"], window=5)
        if reaction:
            out.append({
                "symbol":   sym,
                "date":     item["date"],
                "ret_5d":   reaction["ret_pct"],
                "pre":      reaction["pre"],
                "post":     reaction["post"],
                "subject":  item["subject"][:60],
            })
    return sorted(out, key=lambda x: abs(x["ret_5d"]), reverse=True)[:15]


def screen_upcoming_results(ann: pd.DataFrame) -> list:
    """
    Estimate upcoming results by finding stocks whose last results were
    ~85-95 days ago (i.e., next quarterly result is due soon).
    """
    # get all historical results announcements (look back 120 days)
    conn = sqlite3.connect(DB, timeout=15)
    hist = pd.read_sql_query(
        "SELECT announcement_date, symbol, subject FROM corporate_announcements "
        "WHERE announcement_date >= ? ORDER BY announcement_date DESC",
        conn, params=(cutoff(120),)
    )
    conn.close()
    hist["subject"] = hist["subject"].fillna("").astype(str)

    results_mask = hist["subject"].str.lower().apply(
        lambda s: any(kw in s for kw in RESULTS_KEYWORDS)
    )
    results_hist = hist[results_mask].copy()
    if results_hist.empty:
        return []

    today = datetime.today()
    upcoming = []
    for sym, grp in results_hist.groupby("symbol"):
        latest_str = grp["announcement_date"].max()
        try:
            latest_dt = datetime.strptime(latest_str, "%Y-%m-%d")
        except Exception:
            continue
        days_since = (today - latest_dt).days
        # Due in next 0-15 days if last results were 85-100 days ago
        if 85 <= days_since <= 100:
            upcoming.append({
                "symbol":      str(sym),
                "last_results": latest_str,
                "days_since":  days_since,
                "est_due_in":  max(0, 90 - days_since),
            })
    return sorted(upcoming, key=lambda x: x["est_due_in"])[:20]


# ─────────────────────────────────────────────────────────────────────────────
# LLM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(results_season: list, dividends: list, clusters: list,
                 big_trades: list, reactions: list, upcoming: list) -> str:

    def fmt(items, keys, n=8):
        if not items:
            return "  None\n"
        return "\n".join(
            "  " + " | ".join(f"{k}={item.get(k,'?')}" for k in keys if k in item)
            for item in items[:n]
        ) + "\n"

    return f"""You are MICC Agent Eta -- Corporate Events Intelligence. Date: {today_str()}

RECENT RESULTS ({len(results_season)} companies reported last 30 days):
{fmt(results_season, ['symbol','date','subject'], 8)}

DIVIDEND / BONUS / SPLIT CALENDAR:
{fmt(dividends, ['symbol','event_type','date','subject'], 8)}

INSIDER CLUSTER BUYING (3+ insiders buying same stock):
{fmt(clusters, ['symbol','buy_count','total_value_cr','insiders'], 8)}

BIG INSIDER TRADES (>1 Cr):
{fmt(big_trades, ['symbol','transaction','value_cr','name','date'], 8)}

POST-RESULTS PRICE REACTION (Beta-screened stocks after results):
{fmt(reactions, ['symbol','date','ret_5d'], 10)}

UPCOMING RESULTS (estimated due in next 15 days):
{fmt(upcoming, ['symbol','last_results','est_due_in'], 10)}

Write a concise corporate events note (max 250 words):
EARNINGS SEASON: quality of results -- are reactions positive or negative overall
INSIDER SIGNALS: which cluster buys or big trades look most significant
UPCOMING CATALYSTS: which stocks have results due and are worth watching
CORPORATE ACTIONS: any dividends/bonus/splits worth noting
KEY ALERT: one highest-priority corporate event to act on

Plain text. CAPS for section headers. No markdown."""


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────────────────────

def format_telegram(report: dict) -> str:
    d = report.get("date", today_str())
    out_lines = [f"*MICC Eta -- Corporate Events {d}*", ""]

    clusters = report.get("insider_cluster", [])[:4]
    if clusters:
        out_lines.append("*INSIDER CLUSTER BUYING:*")
        for c in clusters:
            out_lines.append(f"  `{c['symbol']}` {c['buy_count']} insiders | Rs {c['total_value_cr']}Cr")
        out_lines.append("")

    big = report.get("big_insider_trades", [])[:5]
    if big:
        out_lines.append("*BIG INSIDER TRADES:*")
        for b in big:
            price_str = f"@ {b['price']}" if b.get("price") else ""
            out_lines.append(f"  `{b['symbol']}` {b['transaction']} Rs {b['value_cr']}Cr {price_str}")
        out_lines.append("")

    results = report.get("results_season", [])[:6]
    if results:
        total = len(report.get("results_season", []))
        out_lines.append(f"*RESULTS REPORTED ({total} total):*")
        for r in results:
            out_lines.append(f"  `{r['symbol']}` {r['date']}")
        out_lines.append("")

    upcoming = report.get("upcoming_results", [])[:6]
    if upcoming:
        out_lines.append("*RESULTS DUE SOON:*")
        for u in upcoming:
            out_lines.append(f"  `{u['symbol']}` ~{u['est_due_in']}d away")
        out_lines.append("")

    divs = [x for x in report.get("dividend_calendar", []) if x["event_type"] == "DIVIDEND"][:4]
    if divs:
        out_lines.append("*DIVIDENDS:*")
        for dv in divs:
            out_lines.append(f"  `{dv['symbol']}` {dv['date']}")
        out_lines.append("")

    analysis = str(report.get("analysis", "")).strip()
    if analysis:
        out_lines.append("*INTEL:*")
        trimmed = analysis[:400]
        last_dot = trimmed.rfind(".")
        if last_dot > 100:
            trimmed = trimmed[:last_dot + 1]
        out_lines.append(trimmed)

    return "\n".join(out_lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run_eta(send: bool = False) -> dict:
    print("=" * 55)
    print("  AGENT ETA -- Corporate Events Intelligence")
    print("=" * 55)

    print("  Loading corporate_announcements...")
    ann = load_announcements(LOOKBACK_CORP)
    print(f"    {len(ann)} announcements ({LOOKBACK_CORP}d)")

    print("  Loading insider_trading...")
    insider = load_insider(LOOKBACK_INSIDER)
    print(f"    {len(insider)} insider trades ({LOOKBACK_INSIDER}d)")

    print("  Loading signals history...")
    signals = load_signals_recent(60)
    print(f"    {len(signals)} recent signal rows")

    print("  Screen 1: Results season...")
    results_season = screen_results_season(ann)
    print(f"    {len(results_season)} results reported")

    print("  Screen 2: Dividend / bonus / split calendar...")
    dividends = screen_dividend_calendar(ann)
    print(f"    {len(dividends)} corporate action events")

    print("  Screen 3: Insider cluster buying...")
    clusters = screen_insider_cluster(insider)
    print(f"    {len(clusters)} cluster signals")

    print("  Screen 4: Big insider trades...")
    big_trades = screen_big_insider_trades(insider)
    print(f"    {len(big_trades)} big trades")

    print("  Screen 5: Post-results price reaction...")
    reactions = screen_post_results_reaction(results_season, signals)
    print(f"    {len(reactions)} reaction data points")

    print("  Screen 6: Upcoming results calendar...")
    upcoming = screen_upcoming_results(ann)
    print(f"    {len(upcoming)} stocks with results due soon")

    print("  LLM analysis...")
    prompt   = build_prompt(results_season, dividends, clusters,
                             big_trades, reactions, upcoming)
    analysis, _src = call_llm(prompt, max_tokens=600, label="Eta")
    print(f"    {len(str(analysis))} chars")

    report = {
        "agent":              "eta",
        "date":               today_str(),
        "generated_at":       now_ist(),
        "results_season":     results_season,
        "dividend_calendar":  dividends,
        "insider_cluster":    clusters,
        "big_insider_trades": big_trades,
        "post_results_reaction": reactions,
        "upcoming_results":   upcoming,
        "analysis":           analysis,
    }

    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {out}")

    if send:
        msg = format_telegram(report)
        ok  = send_telegram_chunks(msg)
        print(f"  Telegram: {'OK' if ok else 'FAILED'}")

    # console summary
    print(f"\n  Results reported:      {len(results_season)}")
    print(f"  Corporate actions:     {len(dividends)}")
    print(f"  Insider clusters:      {len(clusters)}")
    print(f"  Big insider trades:    {len(big_trades)}")
    print(f"  Upcoming results:      {len(upcoming)}")
    print("=" * 55)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()
    run_eta(send=args.send)
