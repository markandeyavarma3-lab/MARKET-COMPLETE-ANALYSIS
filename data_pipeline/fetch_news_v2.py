# -*- coding: utf-8 -*-
"""
fetch_news_v2.py  —  MICC Complete News Coverage (all 2,188 symbols)
=====================================================================
Three-layer approach to cover every stock regardless of market cap:

Layer 1: RSS feeds (large caps + macro) — runs daily, fast
Layer 2: NSE corporate announcements (ALL listed stocks) — already in DB,
          now properly linked to news_headlines for sentiment scoring
Layer 3: Google News search per symbol — covers mid/small caps
          Uses free Google News RSS (no API key, no rate limits)

Zero new dependencies — uses requests + xml.etree (already installed)

Place at: D:\MICC\data_pipeline\fetch_news_v2.py
Run:
  py D:\MICC\data_pipeline\fetch_news_v2.py           # all layers
  py D:\MICC\data_pipeline\fetch_news_v2.py --rss     # layer 1 only (fast)
  py D:\MICC\data_pipeline\fetch_news_v2.py --nse     # layer 2 only
  py D:\MICC\data_pipeline\fetch_news_v2.py --gnews   # layer 3 only
  py D:\MICC\data_pipeline\fetch_news_v2.py --gnews --top 500  # top 500 symbols
"""
import os, sys, sqlite3, time, re, argparse
import xml.etree.ElementTree as ET
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import requests
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

DB_PATH = Path(r"D:\marketDB\db\market.db")
NOW     = datetime.now().isoformat()
TODAY   = datetime.now().strftime("%Y-%m-%d")

# ─────────────────────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c

def setup_tables(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS news_headlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            source TEXT,
            headline TEXT NOT NULL,
            url TEXT UNIQUE,
            symbols_mentioned TEXT,
            sentiment_score REAL,
            category TEXT,
            last_updated TEXT
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_nh_date ON news_headlines(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_nh_sym  ON news_headlines(symbols_mentioned)")

    # Symbol news summary — one row per symbol per day, aggregated
    c.execute("""
        CREATE TABLE IF NOT EXISTS symbol_news_daily (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            mention_count INTEGER DEFAULT 0,
            sentiment_avg REAL,
            sentiment_min REAL,
            sentiment_max REAL,
            headlines_json TEXT,
            last_updated TEXT,
            PRIMARY KEY (symbol, date)
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snd_sym ON symbol_news_daily(symbol, date)")
    c.commit()

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

POS_WORDS = ["surge","rally","gain","jump","rise","bull","profit","growth",
             "record","strong","high","beat","upgrade","buy","positive",
             "breakout","outperform","dividend","bonus","expansion","wins",
             "robust","stellar","soar","climbs","recovers"]
NEG_WORDS = ["crash","fall","drop","decline","bear","loss","weak","low",
             "miss","downgrade","concern","warning","risk","fraud","scam",
             "penalty","sebi","probe","trouble","selloff","plunge","slump",
             "defaults","downfall","write-off","writeoff","recall","shutdown"]

def sentiment(text):
    t = text.lower()
    p = sum(1 for w in POS_WORDS if w in t)
    n = sum(1 for w in NEG_WORDS if w in t)
    if p + n == 0:
        return 0.0
    return round((p - n) / (p + n), 2)

def parse_rss_xml(xml_text):
    """Parse RSS/Atom XML, return list of (title, link, date_str)."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        # Standard RSS 2.0
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            try:
                from email.utils import parsedate
                t = parsedate(pub)
                date_str = f"{t[0]}-{t[1]:02d}-{t[2]:02d}" if t else TODAY
            except Exception:
                date_str = TODAY
            items.append((title, link, date_str))

        # Atom feed fallback
        if not items:
            ATOM = "http://www.w3.org/2005/Atom"
            for entry in root.iter(f"{{{ATOM}}}entry"):
                title = (entry.findtext(f"{{{ATOM}}}title") or "").strip()
                link_el = entry.find(f"{{{ATOM}}}link")
                link = link_el.get("href","") if link_el is not None else ""
                items.append((title, link, TODAY))
    except Exception:
        pass
    return items

def store_headline(c, date_str, source, title, url, symbols_str, score, category="general"):
    """Insert headline, ignore duplicates. Returns 1 if inserted."""
    try:
        c.execute("""
            INSERT OR IGNORE INTO news_headlines
            (date,source,headline,url,symbols_mentioned,sentiment_score,category,last_updated)
            VALUES (?,?,?,?,?,?,?,?)
        """, (date_str, source, title, url or None, symbols_str, score, category, NOW))
        return c.execute("SELECT changes()").fetchone()[0]
    except Exception:
        return 0

def build_symbol_lookup(c):
    """
    Build dict: company_name_lower -> symbol, and symbol -> company_name
    From stock_fundamentals + a manual map for common names.
    """
    lookup = {}  # keyword -> symbol

    # From stock_fundamentals (sector/industry names may help)
    rows = c.execute("""
        SELECT symbol, sector, industry FROM stock_fundamentals
        WHERE symbol IS NOT NULL
    """).fetchall()

    for sym, sector, industry in rows:
        sym = sym.strip().upper()
        lookup[sym.lower()] = sym

    # From corporate_announcements (company names are in there)
    rows2 = c.execute("""
        SELECT DISTINCT symbol FROM corporate_announcements
        WHERE symbol IS NOT NULL
    """).fetchall()
    for (sym,) in rows2:
        if sym:
            lookup[sym.strip().lower()] = sym.strip().upper()

    # Manual large-cap keyword map (common names in news)
    MANUAL = {
        "reliance": "RELIANCE", "ril": "RELIANCE", "mukesh ambani": "RELIANCE",
        "tcs": "TCS", "tata consultancy": "TCS",
        "hdfc bank": "HDFCBANK", "hdfcbank": "HDFCBANK",
        "infosys": "INFY", "infy": "INFY",
        "wipro": "WIPRO",
        "icici bank": "ICICIBANK", "icicibank": "ICICIBANK",
        "axis bank": "AXISBANK", "axisbank": "AXISBANK",
        "kotak": "KOTAKBANK", "kotak mahindra": "KOTAKBANK",
        "sbi": "SBIN", "state bank": "SBIN",
        "bajaj finance": "BAJFINANCE", "bajajfinance": "BAJFINANCE",
        "tata motors": "TATAMOTORS", "tatamotors": "TATAMOTORS",
        "maruti": "MARUTI", "maruti suzuki": "MARUTI",
        "asian paints": "ASIANPAINT",
        "hindustan unilever": "HINDUNILVR", "hul": "HINDUNILVR",
        "itc": "ITC",
        "larsen": "LT", "l&t": "LT",
        "sun pharma": "SUNPHARMA", "sunpharma": "SUNPHARMA",
        "dr reddy": "DRREDDY", "dr. reddy": "DRREDDY",
        "cipla": "CIPLA",
        "titan": "TITAN",
        "adani": "ADANIENT", "gautam adani": "ADANIENT",
        "adani ports": "ADANIPORTS",
        "adani green": "ADANIGREEN",
        "adani power": "ADANIPOWER",
        "zomato": "ZOMATO",
        "paytm": "PAYTM", "one 97": "PAYTM",
        "nykaa": "NYKAA",
        "ola": "OLAELEC",
        "swiggy": "SWIGGY",
        "indigo": "INDIGO", "interglobe": "INDIGO",
        "air india": "AIRINDIA",
        "ongc": "ONGC",
        "ntpc": "NTPC",
        "power grid": "POWERGRID",
        "coal india": "COALINDIA",
        "bhel": "BHEL",
        "sail": "SAIL",
        "jsw steel": "JSWSTEEL",
        "tata steel": "TATASTEEL",
        "hindalco": "HINDALCO",
        "vedanta": "VEDL",
        "ultratech": "ULTRACEMCO",
        "ambuja cement": "AMBUJACEM",
        "acc": "ACC",
        "shree cement": "SHREECEM",
        "bajaj auto": "BAJAJ-AUTO",
        "hero motocorp": "HEROMOTOCO",
        "eicher motors": "EICHERMOT",
        "tvs motor": "TVSMOTOR",
        "mahindra": "M&M",
        "nifty": "NIFTY", "sensex": "SENSEX",
        "rbi": "MACRO", "reserve bank": "MACRO",
        "sebi": "MACRO",
    }
    lookup.update(MANUAL)
    return lookup

def extract_symbols(text, lookup):
    """Find all symbols mentioned in text using lookup."""
    t = text.lower()
    found = set()
    for keyword, symbol in lookup.items():
        if len(keyword) >= 3 and keyword in t:
            found.add(symbol)
    return ",".join(sorted(found)) if found else None


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1: RSS FEEDS (large caps + macro)
# ─────────────────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("ET Markets",   "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("ET Stocks",    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("ET Results",   "https://economictimes.indiatimes.com/markets/earnings/rssfeeds/2146826.cms"),
    ("Livemint",     "https://www.livemint.com/rss/markets"),
    ("Livemint Corp","https://www.livemint.com/rss/companies"),
    ("Hindu Biz",    "https://www.thehindu.com/business/markets/?service=rss"),
    ("Hindu Corp",   "https://www.thehindu.com/business/Industry/?service=rss"),
    ("NDTV Profit",  "https://www.ndtvprofit.com/rss"),
    ("Zee Biz",      "https://www.zeebiz.com/rss"),
]

def fetch_rss_layer(lookup):
    """Layer 1: RSS feeds."""
    print("\n  [Layer 1] RSS Feeds...")
    c = get_conn()
    setup_tables(c)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (compatible)"})
    total = 0

    for source, url in RSS_FEEDS:
        try:
            resp = sess.get(url, timeout=12)
            if resp.status_code != 200:
                print(f"    ⚠️  {source}: HTTP {resp.status_code}")
                continue
            items = parse_rss_xml(resp.text)
            added = 0
            for title, link, date_str in items[:50]:
                syms  = extract_symbols(title, lookup)
                score = sentiment(title)
                added += store_headline(c, date_str, source, title, link,
                                        syms, score, "rss")
            c.commit()
            total += added
            print(f"    ✅  {source}: {added} new")
            time.sleep(0.3)
        except Exception as e:
            print(f"    ❌  {source}: {e}")

    c.close()
    print(f"  Layer 1 done: {total} headlines added")
    return total


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2: NSE CORPORATE ANNOUNCEMENTS → news_headlines
# ─────────────────────────────────────────────────────────────────────────────

def fetch_nse_announcements_layer():
    """
    Layer 2: Convert corporate_announcements to news_headlines.
    These cover ALL listed stocks — every mid/small cap with any NSE filing.
    """
    print("\n  [Layer 2] NSE Corporate Announcements → news_headlines...")
    c = get_conn()
    setup_tables(c)

    # Get recent announcements (last 7 days) not yet in news_headlines
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = c.execute("""
        SELECT ca.symbol, ca.announcement_date, ca.subject
        FROM corporate_announcements ca
        WHERE ca.announcement_date >= ?
        AND ca.subject IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM news_headlines nh
            WHERE nh.symbols_mentioned LIKE '%' || ca.symbol || '%'
            AND nh.date = ca.announcement_date
            AND nh.source = 'NSE_ANNOUNCEMENT'
            AND nh.headline = ca.subject
        )
        ORDER BY ca.announcement_date DESC
        LIMIT 2000
    """, (cutoff,)).fetchall()

    added = 0
    for symbol, ann_date, subject in rows:
        if not subject or not symbol:
            continue
        score = sentiment(subject)
        # Classify announcement type
        subj_lower = subject.lower()
        if any(w in subj_lower for w in ["results","financial","quarterly","annual"]):
            cat = "earnings"
        elif any(w in subj_lower for w in ["dividend","bonus","split","buyback"]):
            cat = "corporate_action"
        elif any(w in subj_lower for w in ["board","meeting","agm","egm"]):
            cat = "board"
        elif any(w in subj_lower for w in ["insider","trading","shareholding"]):
            cat = "insider"
        else:
            cat = "announcement"

        added += store_headline(c, ann_date, "NSE_ANNOUNCEMENT",
                                subject, None, symbol, score, cat)

    c.commit()
    c.close()
    print(f"  Layer 2 done: {added} announcement headlines linked")
    return added


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3: GOOGLE NEWS RSS PER SYMBOL (mid/small cap coverage)
# ─────────────────────────────────────────────────────────────────────────────

def google_news_rss_url(query):
    """Google News RSS — free, no API key, works for any query."""
    encoded = quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

def fetch_gnews_for_symbol(sess, symbol, company_name=None):
    """Fetch Google News RSS for one symbol. Returns list of (title, link, date_str)."""
    queries = [f"{symbol} NSE stock"]
    if company_name and company_name != symbol:
        queries.append(f"{company_name} share price")

    items = []
    for query in queries:
        try:
            url  = google_news_rss_url(query)
            resp = sess.get(url, timeout=10)
            if resp.status_code == 200:
                new_items = parse_rss_xml(resp.text)
                items.extend(new_items[:8])  # max 8 per query
            time.sleep(0.3)
        except Exception:
            pass
    return items

def get_symbols_by_priority(c, top_n):
    """
    Get symbols prioritized by:
    1. High delivery % (institutional interest)
    2. In signals_history recently (MICC is already watching them)
    3. All remaining by alphabetical
    """
    # Symbols in recent signals (MICC is watching these)
    signal_syms = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM signals_history
        WHERE run_date >= date('now', '-7 days')
        ORDER BY symbol
    """).fetchall()]

    # Symbols in watchlist
    watchlist_syms = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM stock_data
        WHERE symbol IN (
            SELECT DISTINCT symbol FROM signals_history
            WHERE run_date >= date('now', '-3 days')
        )
        ORDER BY symbol
    """).fetchall()]

    # All symbols
    all_syms = [r[0] for r in c.execute("""
        SELECT symbol FROM (
            SELECT symbol, COUNT(*) as n FROM stock_data
            GROUP BY symbol HAVING n > 250
        ) ORDER BY symbol
    """).fetchall()]

    # Deduplicate preserving priority order
    seen = set()
    ordered = []
    for sym in (signal_syms + watchlist_syms + all_syms):
        if sym not in seen:
            seen.add(sym)
            ordered.append(sym)

    return ordered[:top_n]

def get_company_names(c):
    """Get symbol -> company name from stock_fundamentals."""
    rows = c.execute("""
        SELECT symbol, sector FROM stock_fundamentals
        WHERE symbol IS NOT NULL
    """).fetchall()
    # Fallback: just use symbol as name
    names = {r[0]: r[0] for r in rows}
    # Try to get actual company name from screener_fundamentals if exists
    try:
        rows2 = c.execute("""
            SELECT symbol, company_name FROM screener_fundamentals
            WHERE company_name IS NOT NULL
        """).fetchall()
        for sym, name in rows2:
            if name:
                names[sym] = name
    except Exception:
        pass
    return names

def fetch_gnews_layer(top_n=300):
    """
    Layer 3: Google News RSS per symbol.
    Covers mid/small caps that RSS feeds never mention.
    """
    print(f"\n  [Layer 3] Google News per symbol (top {top_n} symbols)...")
    c = get_conn()
    setup_tables(c)

    symbols   = get_symbols_by_priority(c, top_n)
    names     = get_company_names(c)
    total_added = 0
    total_syms  = 0

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    })

    print(f"    Processing {len(symbols)} symbols...")

    for i, symbol in enumerate(symbols):
        company = names.get(symbol, symbol)
        items   = fetch_gnews_for_symbol(sess, symbol, company)

        added = 0
        for title, link, date_str in items:
            score = sentiment(title)
            added += store_headline(c, date_str, "GOOGLE_NEWS",
                                    title, link, symbol, score, "gnews")

        if added > 0:
            total_added += added
            total_syms  += 1

        # Commit every 50 symbols
        if (i + 1) % 50 == 0:
            c.commit()
            pct = (i + 1) / len(symbols) * 100
            print(f"    {i+1}/{len(symbols)} ({pct:.0f}%) — {total_added} headlines, "
                  f"{total_syms} symbols with news")

        # Polite delay — Google News allows ~2 req/sec
        time.sleep(0.5)

    c.commit()
    c.close()
    print(f"  Layer 3 done: {total_added} headlines for {total_syms} symbols")
    return total_added


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE: symbol_news_daily summary
# ─────────────────────────────────────────────────────────────────────────────

def build_symbol_news_summary(days_back=1):
    """
    Aggregate news_headlines into symbol_news_daily.
    One row per symbol per day with: count, avg sentiment, headline list.
    """
    print("\n  [Aggregating] Building symbol_news_daily...")
    c = get_conn()

    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Get all headlines since cutoff
    rows = c.execute("""
        SELECT date, symbols_mentioned, headline, sentiment_score
        FROM news_headlines
        WHERE date >= ? AND symbols_mentioned IS NOT NULL
        ORDER BY date DESC
    """, (cutoff,)).fetchall()

    # Group by symbol+date
    from collections import defaultdict
    import json as _json
    groups = defaultdict(list)

    for date_str, syms_str, headline, score in rows:
        if not syms_str:
            continue
        for sym in syms_str.split(","):
            sym = sym.strip().upper()
            if sym and sym not in ("MACRO",):
                groups[(sym, date_str)].append((headline, score or 0.0))

    inserted = 0
    for (sym, date_str), items in groups.items():
        scores    = [s for _, s in items]
        headlines = [h for h, _ in items]
        avg_s = round(sum(scores) / len(scores), 3) if scores else 0.0
        min_s = round(min(scores), 3) if scores else 0.0
        max_s = round(max(scores), 3) if scores else 0.0

        c.execute("""
            INSERT OR REPLACE INTO symbol_news_daily
            (symbol, date, mention_count, sentiment_avg, sentiment_min,
             sentiment_max, headlines_json, last_updated)
            VALUES (?,?,?,?,?,?,?,?)
        """, (sym, date_str, len(items), avg_s, min_s, max_s,
              _json.dumps(headlines[:10]), NOW))
        inserted += 1

    c.commit()
    c.close()
    print(f"  Done: {inserted} symbol-day summaries built")
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# SHOW TODAY'S COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

def show_coverage():
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM news_headlines WHERE date=?", (TODAY,)).fetchone()[0]
    symbols_covered = c.execute("""
        SELECT COUNT(DISTINCT symbol) FROM symbol_news_daily WHERE date=?
    """, (TODAY,)).fetchone()[0]

    print(f"\n  📊 Today's Coverage ({TODAY}):")
    print(f"    Headlines: {total}")
    print(f"    Symbols with news: {symbols_covered}")

    # Top mentioned
    rows = c.execute("""
        SELECT symbol, mention_count, sentiment_avg
        FROM symbol_news_daily
        WHERE date=?
        ORDER BY mention_count DESC
        LIMIT 15
    """, (TODAY,)).fetchall()

    if rows:
        print(f"\n  {'Symbol':<15} {'Mentions':>8}  {'Sentiment':>10}  Bar")
        print(f"  {'-'*50}")
        for sym, cnt, sent in rows:
            bar   = "▓" * min(cnt, 20)
            s_icon = "🟢" if (sent or 0) > 0.1 else ("🔴" if (sent or 0) < -0.1 else "⚪")
            print(f"  {sym:<15} {cnt:>8}  {s_icon} {(sent or 0):>+6.2f}   {bar}")

    # Most negative (risk alerts)
    neg_rows = c.execute("""
        SELECT symbol, mention_count, sentiment_avg, headlines_json
        FROM symbol_news_daily
        WHERE date=? AND sentiment_avg < -0.2 AND mention_count >= 2
        ORDER BY sentiment_avg ASC
        LIMIT 5
    """, (TODAY,)).fetchall()

    if neg_rows:
        import json as _json
        print(f"\n  🚨 Most Negative Sentiment Today:")
        for sym, cnt, sent, hl_json in neg_rows:
            print(f"    {sym}: sentiment={sent:+.2f}, mentions={cnt}")
            try:
                hls = _json.loads(hl_json or "[]")
                if hls:
                    print(f"      → {hls[0][:80]}")
            except Exception:
                pass

    c.close()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MICC News v2 — Full Coverage")
    parser.add_argument("--rss",    action="store_true", help="Layer 1: RSS feeds")
    parser.add_argument("--nse",    action="store_true", help="Layer 2: NSE announcements")
    parser.add_argument("--gnews",  action="store_true", help="Layer 3: Google News per symbol")
    parser.add_argument("--top",    type=int, default=300,
                        help="Number of symbols for gnews layer (default 300)")
    parser.add_argument("--all500", action="store_true",
                        help="Run gnews for top 500 symbols (slower, ~45 min)")
    args = parser.parse_args()
    run_all = not (args.rss or args.nse or args.gnews)

    print(f"\n{'='*60}")
    print("  MICC News v2 — Complete Coverage")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    c = get_conn()
    setup_tables(c)
    lookup = build_symbol_lookup(c)
    c.close()
    print(f"  Symbol lookup: {len(lookup)} keywords loaded")

    top_n = 500 if args.all500 else args.top

    if run_all or args.rss:
        fetch_rss_layer(lookup)

    if run_all or args.nse:
        fetch_nse_announcements_layer()

    if run_all or args.gnews:
        fetch_gnews_layer(top_n)

    # Always aggregate at end
    build_symbol_news_summary(days_back=3)
    show_coverage()

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
