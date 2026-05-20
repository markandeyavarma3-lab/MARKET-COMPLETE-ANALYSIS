# -*- coding: utf-8 -*-
"""
fetch_news_final.py  — MICC News (definitive version)
======================================================
Fixes:
  1. Schema conflict — drops and recreates news_headlines with correct schema
  2. Layer 2 NSE announcements — prints actual error, fixes insert
  3. Layer 3 per-stock news — uses yfinance .news property (free, works on Windows)
     yfinance already installed and working in your pipeline

Run:
  py D:\MICC\data_pipeline\fetch_news_final.py           # all layers
  py D:\MICC\data_pipeline\fetch_news_final.py --rss     # RSS only
  py D:\MICC\data_pipeline\fetch_news_final.py --nse     # NSE announcements
  py D:\MICC\data_pipeline\fetch_news_final.py --stocks  # per-stock via yfinance
  py D:\MICC\data_pipeline\fetch_news_final.py --stocks --top 200
"""
import os, sys, sqlite3, time, json, re, argparse
import xml.etree.ElementTree as ET
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import requests
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")
NOW     = datetime.now().isoformat()
TODAY   = datetime.now().strftime("%Y-%m-%d")

POS = ["surge","rally","gain","jump","rise","bull","profit","growth","record",
       "strong","beat","upgrade","positive","breakout","dividend","bonus",
       "robust","soar","climbs","recovers","wins","outperform"]
NEG = ["crash","fall","drop","decline","bear","loss","weak","miss","downgrade",
       "concern","warning","risk","fraud","probe","penalty","sebi","trouble",
       "selloff","plunge","slump","default","write-off","shutdown"]

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c

def sentiment(text):
    t = text.lower()
    p = sum(1 for w in POS if w in t)
    n = sum(1 for w in NEG if w in t)
    return round((p - n) / (p + n), 2) if (p + n) else 0.0

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA SETUP — fixes the schema conflict from earlier scripts
# ─────────────────────────────────────────────────────────────────────────────

def setup_schema(c):
    """
    Recreate tables with correct schema.
    Migrates existing data from old news_headlines if it exists.
    """
    # Check current schema
    cols = [row[1] for row in c.execute("PRAGMA table_info(news_headlines)").fetchall()]

    if cols and "category" not in cols:
        # Old schema from fetch_news.py — migrate
        print("  Migrating news_headlines to new schema...")
        c.execute("ALTER TABLE news_headlines RENAME TO news_headlines_old")
        c.execute("""
            CREATE TABLE news_headlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                source TEXT NOT NULL,
                headline TEXT NOT NULL,
                url TEXT,
                symbols_mentioned TEXT,
                sentiment_score REAL,
                category TEXT DEFAULT 'general',
                last_updated TEXT,
                UNIQUE(date, source, headline)
            )""")
        # Copy old data
        c.execute("""
            INSERT OR IGNORE INTO news_headlines
            (date, source, headline, url, symbols_mentioned, sentiment_score, last_updated)
            SELECT date, source, headline, url, symbols_mentioned, sentiment_score, last_updated
            FROM news_headlines_old
        """)
        c.execute("DROP TABLE news_headlines_old")
        print("  Migration done.")

    elif not cols:
        # Fresh create
        c.execute("""
            CREATE TABLE IF NOT EXISTS news_headlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                source TEXT NOT NULL,
                headline TEXT NOT NULL,
                url TEXT,
                symbols_mentioned TEXT,
                sentiment_score REAL,
                category TEXT DEFAULT 'general',
                last_updated TEXT,
                UNIQUE(date, source, headline)
            )""")

    c.execute("CREATE INDEX IF NOT EXISTS idx_nh_date ON news_headlines(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_nh_sym  ON news_headlines(symbols_mentioned)")

    # symbol_news_daily — aggregated per symbol per day
    c.execute("""
        CREATE TABLE IF NOT EXISTS symbol_news_daily (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            mention_count INTEGER DEFAULT 0,
            sentiment_avg REAL,
            headlines_json TEXT,
            last_updated TEXT,
            PRIMARY KEY (symbol, date)
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snd ON symbol_news_daily(symbol, date)")
    c.commit()

def insert(c, date_str, source, headline, url, symbols, score, category="general"):
    """Insert headline. Returns 1 if inserted, 0 if duplicate."""
    try:
        c.execute("""
            INSERT OR IGNORE INTO news_headlines
            (date,source,headline,url,symbols_mentioned,sentiment_score,category,last_updated)
            VALUES (?,?,?,?,?,?,?,?)
        """, (date_str, source, headline[:400], url, symbols, score, category, NOW))
        return c.execute("SELECT changes()").fetchone()[0]
    except Exception as e:
        print(f"    INSERT ERROR: {e} | headline={headline[:50]}")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# SYMBOL LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

HARDCODED = {
    "reliance": "RELIANCE", "ril": "RELIANCE", "mukesh ambani": "RELIANCE",
    "tcs": "TCS", "tata consultancy": "TCS",
    "hdfc bank": "HDFCBANK",
    "infosys": "INFY", "wipro": "WIPRO",
    "icici bank": "ICICIBANK", "axis bank": "AXISBANK",
    "kotak bank": "KOTAKBANK", "kotak mahindra": "KOTAKBANK",
    "state bank": "SBIN", "sbi ": "SBIN",
    "bajaj finance": "BAJFINANCE", "tata motors": "TATAMOTORS",
    "maruti suzuki": "MARUTI", "maruti ": "MARUTI",
    "asian paints": "ASIANPAINT",
    "hindustan unilever": "HINDUNILVR", " hul ": "HINDUNILVR",
    "larsen": "LT", "l&t ": "LT",
    "sun pharma": "SUNPHARMA", "dr reddy": "DRREDDY",
    "cipla": "CIPLA", "titan ": "TITAN",
    "adani enterprises": "ADANIENT", "adani ports": "ADANIPORTS",
    "adani green": "ADANIGREEN", "adani power": "ADANIPOWER",
    "zomato": "ZOMATO", "paytm": "PAYTM",
    "indigo airlines": "INDIGO", "interglobe": "INDIGO",
    "ongc": "ONGC", "ntpc": "NTPC", "bhel": "BHEL", "sail ": "SAIL",
    "jsw steel": "JSWSTEEL", "tata steel": "TATASTEEL",
    "hindalco": "HINDALCO", "vedanta": "VEDL",
    "ultratech": "ULTRACEMCO", "ambuja cement": "AMBUJACEM",
    "bajaj auto": "BAJAJ-AUTO", "hero motocorp": "HEROMOTOCO",
    "mahindra": "M&M", "dmart": "DMART", "avenue supermarts": "DMART",
    "polycab": "POLYCAB", "havells": "HAVELLS",
    "irctc": "IRCTC", "dixon": "DIXON",
    "nifty": "NIFTY", "sensex": "SENSEX",
    "rbi ": "MACRO", "reserve bank": "MACRO", "sebi ": "MACRO",
}

def build_lookup(c):
    lk = dict(HARDCODED)
    rows = c.execute("SELECT DISTINCT symbol FROM stock_data WHERE symbol IS NOT NULL").fetchall()
    for (s,) in rows:
        if s and len(s) >= 2:
            lk[s.lower()] = s.upper()
    return lk

def find_symbols(text, lookup):
    t = " " + text.lower() + " "
    found = set()
    for kw, sym in lookup.items():
        if len(kw) >= 3 and kw in t:
            found.add(sym)
    return ",".join(sorted(found)) if found else None


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1: RSS FEEDS
# ─────────────────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("ET Markets",    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("ET Stocks",     "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("ET Earnings",   "https://economictimes.indiatimes.com/markets/earnings/rssfeeds/2146826.cms"),
    ("ET Companies",  "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms"),
    ("Livemint Mkt",  "https://www.livemint.com/rss/markets"),
    ("Livemint Corp", "https://www.livemint.com/rss/companies"),
    ("Hindu Biz",     "https://www.thehindu.com/business/markets/?service=rss"),
    ("Hindu Corp",    "https://www.thehindu.com/business/Industry/?service=rss"),
]

def parse_rss(text):
    items = []
    try:
        text = re.sub(r'<\?xml[^?]*\?>', '', text).strip()
        text = re.sub(r' xmlns(?::\w+)?="[^"]*"', '', text)
        root = ET.fromstring(text)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or item.findtext("guid") or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            if not title: continue
            try:
                from email.utils import parsedate
                t = parsedate(pub)
                ds = f"{t[0]}-{t[1]:02d}-{t[2]:02d}" if t else TODAY
            except Exception:
                ds = TODAY
            items.append((title, link, ds))
        if not items:
            for entry in root.iter("entry"):
                title = (entry.findtext("title") or "").strip()
                link_el = entry.find("link")
                link = link_el.get("href","") if link_el is not None else ""
                if title: items.append((title, link, TODAY))
    except Exception as e:
        pass
    return items

def run_rss(lookup):
    print("\n  [Layer 1] RSS Feeds...")
    c = get_conn(); setup_schema(c)
    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    total = 0
    for source, url in RSS_FEEDS:
        try:
            r = sess.get(url, timeout=12)
            if r.status_code != 200:
                print(f"    ⚠️  {source}: HTTP {r.status_code}")
                continue
            items = parse_rss(r.text)
            added = 0
            for title, link, ds in items[:50]:
                added += insert(c, ds, source, title, link or None,
                                find_symbols(title, lookup), sentiment(title), "rss")
            c.commit()
            total += added
            print(f"    ✅  {source}: {added} new ({len(items)} fetched)")
            time.sleep(0.3)
        except Exception as e:
            print(f"    ❌  {source}: {e}")
    c.close()
    print(f"  Layer 1: {total} new")
    return total


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2: NSE CORPORATE ANNOUNCEMENTS
# ─────────────────────────────────────────────────────────────────────────────

def run_nse_announcements():
    print("\n  [Layer 2] NSE Corporate Announcements...")
    c = get_conn(); setup_schema(c)

    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    rows = c.execute("""
        SELECT symbol, announcement_date, subject
        FROM corporate_announcements
        WHERE announcement_date >= ?
          AND subject IS NOT NULL
          AND symbol IS NOT NULL
        ORDER BY announcement_date DESC
        LIMIT 5000
    """, (cutoff,)).fetchall()

    print(f"    {len(rows)} announcements since {cutoff}")

    added = 0; errors = 0
    for symbol, ann_date, subject in rows:
        s  = subject.strip()
        sl = s.lower()
        if any(w in sl for w in ["results","financial","quarterly","annual","profit","revenue"]):
            cat = "earnings"
        elif any(w in sl for w in ["dividend","bonus","split","buyback","rights"]):
            cat = "corporate_action"
        elif any(w in sl for w in ["board","meeting","agm","egm","director"]):
            cat = "board"
        elif any(w in sl for w in ["insider","trading","shareholding","pledge"]):
            cat = "insider"
        elif any(w in sl for w in ["acquisition","merger","demerger","subsidiary"]):
            cat = "corporate_event"
        else:
            cat = "announcement"

        n = insert(c, ann_date, "NSE_ANNOUNCEMENT", s, None,
                   symbol.upper(), sentiment(s), cat)
        added += n
        if n == 0: errors += 1

    c.commit()
    c.close()
    print(f"  Layer 2: {added} added, {errors} duplicates skipped")
    return added


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3: PER-STOCK NEWS VIA YFINANCE (already installed, works on Windows)
# ─────────────────────────────────────────────────────────────────────────────

def run_stock_news(top_n=200):
    """
    yfinance Ticker.news gives recent news articles per stock.
    Already installed, uses Yahoo Finance internally, works on Windows.
    Covers mid/small caps that RSS feeds never mention.
    """
    print(f"\n  [Layer 3] Per-stock news via yfinance (top {top_n})...")

    try:
        import yfinance as yf
    except ImportError:
        print("    ❌ yfinance not installed")
        return 0

    c = get_conn(); setup_schema(c)

    # Priority: signals_history first (stocks MICC is watching)
    sig_syms = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM signals_history
        WHERE run_date >= date('now', '-7 days')
        ORDER BY symbol
    """).fetchall()]

    # Then watchlist
    watch_syms = []
    try:
        import json as _json
        wf = Path(r"D:\MICC\micc_watchlist.json")
        if wf.exists():
            watch_syms = list(_json.loads(wf.read_text()).keys())
    except Exception:
        pass

    # Then all symbols by activity
    all_syms = [r[0] for r in c.execute("""
        SELECT symbol FROM (
            SELECT symbol, COUNT(*) n FROM stock_data
            WHERE close IS NOT NULL
            GROUP BY symbol HAVING n > 500
        ) ORDER BY symbol
    """).fetchall()]

    # Deduplicate preserving priority
    seen = set(); ordered = []
    for s in sig_syms + watch_syms + all_syms:
        if s and s not in seen:
            seen.add(s); ordered.append(s)
    symbols = ordered[:top_n]
    print(f"    {len(symbols)} symbols ({len(sig_syms)} from signals, {len(watch_syms)} from watchlist)")

    total_added = 0; syms_with_news = 0
    batch = 50

    for i, sym in enumerate(symbols):
        try:
            # yfinance uses NSE suffix for Indian stocks
            ticker = yf.Ticker(f"{sym}.NS")
            news   = ticker.news  # list of dicts

            if not news:
                time.sleep(0.1)
                continue

            added = 0
            for article in news[:8]:  # max 8 per stock
                title = article.get("title", "").strip()
                if not title: continue

                # yfinance news has providerPublishTime (unix timestamp)
                ts    = article.get("providerPublishTime", 0)
                try:
                    ds = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                except Exception:
                    ds = TODAY

                url   = article.get("link", "")
                score = sentiment(title)

                # Also check if other symbols mentioned in headline
                all_syms_in_title = find_symbols(title, {})
                syms_str = sym  # at minimum this stock

                added += insert(c, ds, "YFINANCE_NEWS", title, url or None,
                                syms_str, score, "stock_news")

            if added > 0:
                total_added += added
                syms_with_news += 1

        except Exception:
            pass  # silent — don't spam for 200 symbols

        # Commit + progress every batch
        if (i + 1) % batch == 0:
            c.commit()
            pct = (i + 1) / len(symbols) * 100
            print(f"    {i+1}/{len(symbols)} ({pct:.0f}%) "
                  f"— {total_added} headlines, {syms_with_news} stocks with news")

        time.sleep(0.15)  # yfinance is generous with rate limits

    c.commit()
    c.close()
    print(f"  Layer 3: {total_added} headlines for {syms_with_news} stocks")
    return total_added


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE
# ─────────────────────────────────────────────────────────────────────────────

def aggregate():
    c = get_conn()
    cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    rows = c.execute("""
        SELECT date, symbols_mentioned, headline, sentiment_score
        FROM news_headlines WHERE date >= ? AND symbols_mentioned IS NOT NULL
    """, (cutoff,)).fetchall()

    from collections import defaultdict
    groups = defaultdict(list)
    for ds, syms, hl, sc in rows:
        if not syms: continue
        for sym in syms.split(","):
            sym = sym.strip().upper()
            if sym and sym not in ("MACRO",):
                groups[(sym, ds)].append((hl, sc or 0.0))

    ins = 0
    for (sym, ds), items in groups.items():
        scores = [s for _, s in items]
        c.execute("""
            INSERT OR REPLACE INTO symbol_news_daily
            (symbol,date,mention_count,sentiment_avg,headlines_json,last_updated)
            VALUES (?,?,?,?,?,?)
        """, (sym, ds, len(items),
              round(sum(scores)/len(scores), 3) if scores else 0.0,
              json.dumps([h for h,_ in items][:8]), NOW))
        ins += 1
    c.commit(); c.close()
    return ins


def show():
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM news_headlines WHERE date=?", (TODAY,)).fetchone()[0]
    syms  = c.execute("SELECT COUNT(DISTINCT symbol) FROM symbol_news_daily WHERE date=?", (TODAY,)).fetchone()[0]
    srcs  = c.execute("""
        SELECT source, COUNT(*) FROM news_headlines WHERE date=? GROUP BY source ORDER BY 2 DESC
    """, (TODAY,)).fetchall()

    print(f"\n  📊 Today ({TODAY}): {total} headlines | {syms} symbols covered")
    for s, n in srcs:
        print(f"    {s:<25} {n} articles")

    rows = c.execute("""
        SELECT symbol, mention_count, sentiment_avg FROM symbol_news_daily
        WHERE date=? ORDER BY mention_count DESC LIMIT 25
    """, (TODAY,)).fetchall()

    if rows:
        print(f"\n  {'Symbol':<15} {'Count':>5}  Sentiment")
        print(f"  {'-'*42}")
        for sym, cnt, sent in rows:
            bar  = "█" * min(cnt, 20)
            ico  = "🟢" if (sent or 0) > 0.1 else ("🔴" if (sent or 0) < -0.1 else "⚪")
            print(f"  {sym:<15} {cnt:>5}  {ico} {(sent or 0):>+5.2f}  {bar}")

    neg = c.execute("""
        SELECT symbol, sentiment_avg, headlines_json FROM symbol_news_daily
        WHERE date=? AND sentiment_avg < -0.2 AND mention_count >= 2
        ORDER BY sentiment_avg ASC LIMIT 5
    """, (TODAY,)).fetchall()
    if neg:
        print(f"\n  🚨 Negative alerts:")
        for sym, sent, hlj in neg:
            print(f"    {sym}: {sent:+.2f}")
            try:
                h = json.loads(hlj or "[]")
                if h: print(f"      → {h[0][:70]}")
            except Exception: pass
    c.close()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rss",    action="store_true")
    ap.add_argument("--nse",    action="store_true")
    ap.add_argument("--stocks", action="store_true", help="Per-stock via yfinance")
    ap.add_argument("--top",    type=int, default=200)
    args = ap.parse_args()
    run_all = not (args.rss or args.nse or args.stocks)

    print(f"\n{'='*60}")
    print("  MICC News Final")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    c = get_conn(); setup_schema(c)
    lookup = build_lookup(c); c.close()
    print(f"  Lookup: {len(lookup)} keywords")

    if run_all or args.rss:    run_rss(lookup)
    if run_all or args.nse:    run_nse_announcements()
    if run_all or args.stocks: run_stock_news(args.top)

    agg = aggregate()
    print(f"\n  Aggregated: {agg} symbol-day rows")
    show()
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
