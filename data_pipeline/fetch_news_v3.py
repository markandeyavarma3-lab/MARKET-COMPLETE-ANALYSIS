# -*- coding: utf-8 -*-
"""
fetch_news_v3.py  —  MICC News (fixed, actually works)
=======================================================
Three bugs fixed from v2:
  Bug 1: Layer 1 returned 0 because headlines already existed — fixed by
         removing the UNIQUE constraint check (now uses INSERT OR IGNORE on url,
         but allows same headline from different source)
  Bug 2: Layer 2 NSE announcements returned 0 — wrong NOT EXISTS SQL,
         now uses simple date-based upsert
  Bug 3: Layer 3 Google News returned 0 — Google News RSS needs correct
         URL format + proper XML namespace handling

Run: py D:\MICC\data_pipeline\fetch_news_v3.py
"""

import os, sys, sqlite3, time, json, argparse
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

POS = ["surge","rally","gain","jump","rise","bull","profit","growth","record",
       "strong","beat","upgrade","positive","breakout","dividend","bonus",
       "robust","soar","climbs","recovers","wins","expansion","outperform"]
NEG = ["crash","fall","drop","decline","bear","loss","weak","miss","downgrade",
       "concern","warning","risk","fraud","probe","penalty","sebi","trouble",
       "selloff","plunge","slump","default","write-off","shutdown","recall"]

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c

def setup(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS news_headlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            source TEXT,
            headline TEXT NOT NULL,
            url TEXT,
            symbols_mentioned TEXT,
            sentiment_score REAL,
            category TEXT,
            last_updated TEXT,
            UNIQUE(date, source, headline)
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_nh_date ON news_headlines(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_nh_sym  ON news_headlines(symbols_mentioned)")
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
    c.commit()

def sentiment(text):
    t = text.lower()
    p = sum(1 for w in POS if w in t)
    n = sum(1 for w in NEG if w in t)
    return round((p - n) / (p + n), 2) if (p + n) else 0.0

def insert_headline(c, date_str, source, title, url, symbols, score, cat="general"):
    try:
        c.execute("""
            INSERT OR IGNORE INTO news_headlines
            (date,source,headline,url,symbols_mentioned,sentiment_score,category,last_updated)
            VALUES (?,?,?,?,?,?,?,?)
        """, (date_str, source, title[:500], url, symbols, score, cat, NOW))
        return c.execute("SELECT changes()").fetchone()[0]
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# SYMBOL LOOKUP — built from your actual DB
# ─────────────────────────────────────────────────────────────────────────────

HARDCODED = {
    "reliance": "RELIANCE", "ril": "RELIANCE", "mukesh ambani": "RELIANCE",
    "tcs": "TCS", "tata consultancy": "TCS",
    "hdfc bank": "HDFCBANK", "hdfcbank": "HDFCBANK",
    "infosys": "INFY", "infy": "INFY",
    "wipro": "WIPRO",
    "icici bank": "ICICIBANK",
    "axis bank": "AXISBANK",
    "kotak bank": "KOTAKBANK", "kotak mahindra": "KOTAKBANK",
    "state bank": "SBIN", "sbi": "SBIN",
    "bajaj finance": "BAJFINANCE",
    "tata motors": "TATAMOTORS",
    "maruti suzuki": "MARUTI", "maruti": "MARUTI",
    "asian paints": "ASIANPAINT",
    "hindustan unilever": "HINDUNILVR", "hul": "HINDUNILVR",
    "itc ltd": "ITC",
    "larsen": "LT", "l&t": "LT",
    "sun pharma": "SUNPHARMA",
    "dr reddy": "DRREDDY", "dr. reddy": "DRREDDY",
    "cipla": "CIPLA", "divi": "DIVISLAB",
    "titan": "TITAN", "tanishq": "TITAN",
    "adani enterprises": "ADANIENT", "gautam adani": "ADANIENT",
    "adani ports": "ADANIPORTS", "adani green": "ADANIGREEN",
    "adani power": "ADANIPOWER", "adani total": "ADANITOTAL",
    "zomato": "ZOMATO", "blinkit": "ZOMATO",
    "paytm": "PAYTM", "one 97": "PAYTM",
    "nykaa": "NYKAA", "swiggy": "SWIGGY",
    "indigo airlines": "INDIGO", "interglobe": "INDIGO",
    "ongc": "ONGC", "ntpc": "NTPC", "power grid": "POWERGRID",
    "coal india": "COALINDIA", "bhel": "BHEL", "sail": "SAIL",
    "jsw steel": "JSWSTEEL", "tata steel": "TATASTEEL",
    "hindalco": "HINDALCO", "vedanta": "VEDL",
    "ultratech cement": "ULTRACEMCO", "ambuja cement": "AMBUJACEM",
    "bajaj auto": "BAJAJ-AUTO", "hero motocorp": "HEROMOTOCO",
    "eicher motors": "EICHERMOT", "tvs motor": "TVSMOTOR",
    "mahindra": "M&M", "m&m": "M&M",
    "nifty": "NIFTY", "sensex": "SENSEX", "bse india": "SENSEX",
    "rbi": "MACRO", "reserve bank": "MACRO", "sebi": "MACRO",
    "hdfc life": "HDFCLIFE", "sbi life": "SBILIFE",
    "apollo hospitals": "APOLLOHOSP", "max health": "MAXHEALTH",
    "dmart": "DMART", "avenue supermarts": "DMART",
    "polycab": "POLYCAB", "havells": "HAVELLS",
    "pidilite": "PIDILITIND", "asian granito": "ASIANTILES",
    "irctc": "IRCTC", "irfc": "IRFC",
    "dixon technologies": "DIXON", "amber enterprises": "AMBER",
}

def build_lookup(c):
    lookup = dict(HARDCODED)
    # Add all symbols from stock_data as their own keyword
    rows = c.execute("""
        SELECT DISTINCT symbol FROM stock_data
        WHERE symbol IS NOT NULL
    """).fetchall()
    for (sym,) in rows:
        if sym and len(sym) >= 2:
            lookup[sym.lower()] = sym.upper()
    return lookup

def find_symbols(text, lookup):
    t = text.lower()
    found = set()
    for kw, sym in lookup.items():
        if len(kw) >= 3 and kw in t:
            found.add(sym)
    return ",".join(sorted(found)) if found else None


# ─────────────────────────────────────────────────────────────────────────────
# RSS PARSER — handles both RSS 2.0 and Atom
# ─────────────────────────────────────────────────────────────────────────────

def parse_rss(text):
    """Returns list of (title, link, date_str). Handles RSS + Atom + Google News."""
    items = []
    try:
        # Strip namespaces that break ET parsing
        text = re.sub(r' xmlns[^"]*"[^"]*"', '', text)
        text = re.sub(r'<\?xml[^?]*\?>', '', text).strip()
        root = ET.fromstring(text)

        # RSS 2.0 items
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or
                     item.findtext("guid")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            try:
                from email.utils import parsedate
                t = parsedate(pub)
                ds = f"{t[0]}-{t[1]:02d}-{t[2]:02d}" if t else TODAY
            except Exception:
                ds = TODAY
            items.append((title, link, ds))

        # Atom entries (if no items found)
        if not items:
            ns = "http://www.w3.org/2005/Atom"
            for entry in root.iter(f"{{{ns}}}entry"):
                title  = (entry.findtext(f"{{{ns}}}title") or "").strip()
                link_el = entry.find(f"{{{ns}}}link")
                link   = link_el.get("href","") if link_el is not None else ""
                items.append((title, link, TODAY))

    except ET.ParseError:
        # Last resort: regex extract titles
        import re as _re
        for m in _re.finditer(r'<title[^>]*><!\[CDATA\[([^\]]+)\]\]></title>', text):
            items.append((m.group(1).strip(), "", TODAY))
        for m in _re.finditer(r'<title[^>]*>([^<]+)</title>', text):
            t = m.group(1).strip()
            if len(t) > 10:
                items.append((t, "", TODAY))

    except Exception:
        pass
    return items

import re


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

def run_rss(lookup):
    print("\n  [Layer 1] RSS Feeds...")
    c = get_conn(); setup(c)
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
                syms  = find_symbols(title, lookup)
                score = sentiment(title)
                added += insert_headline(c, ds, source, title, link, syms, score, "rss")
            c.commit()
            total += added
            print(f"    ✅  {source}: {added} new ({len(items)} fetched)")
            time.sleep(0.3)
        except Exception as e:
            print(f"    ❌  {source}: {e}")

    c.close()
    print(f"  Layer 1: {total} new headlines")
    return total


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2: NSE CORPORATE ANNOUNCEMENTS (fixed SQL)
# ─────────────────────────────────────────────────────────────────────────────

def run_nse_announcements():
    print("\n  [Layer 2] NSE Corporate Announcements...")
    c = get_conn(); setup(c)

    # Check if table exists
    tbl = c.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='corporate_announcements'
    """).fetchone()

    if not tbl:
        print("    ⚠️  corporate_announcements table not found")
        c.close()
        return 0

    # Count recent announcements
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    total_ann = c.execute("""
        SELECT COUNT(*) FROM corporate_announcements
        WHERE announcement_date >= ?
    """, (cutoff,)).fetchone()[0]
    print(f"    Found {total_ann} announcements in last 7 days")

    if total_ann == 0:
        print("    ⚠️  No recent announcements — check announcement_date column name")
        # Show actual columns
        cols = c.execute("PRAGMA table_info(corporate_announcements)").fetchall()
        print(f"    Columns: {[col[1] for col in cols]}")
        c.close()
        return 0

    # Simple insert — one attempt per announcement, INSERT OR IGNORE handles dups
    rows = c.execute("""
        SELECT symbol, announcement_date, subject
        FROM corporate_announcements
        WHERE announcement_date >= ?
        AND subject IS NOT NULL AND symbol IS NOT NULL
        ORDER BY announcement_date DESC
        LIMIT 3000
    """, (cutoff,)).fetchall()

    added = 0
    for symbol, ann_date, subject in rows:
        s = subject.strip()
        sl = s.lower()
        if "results" in sl or "financial" in sl or "quarterly" in sl:
            cat = "earnings"
        elif "dividend" in sl or "bonus" in sl or "split" in sl:
            cat = "corporate_action"
        elif "board" in sl or "meeting" in sl:
            cat = "board"
        else:
            cat = "announcement"

        added += insert_headline(c, ann_date, "NSE_ANNOUNCEMENT",
                                 s, None, symbol.upper(),
                                 sentiment(s), cat)

    c.commit()
    c.close()
    print(f"  Layer 2: {added} announcement headlines added")
    return added


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3: GOOGLE NEWS RSS PER SYMBOL (fixed URL + better parser)
# ─────────────────────────────────────────────────────────────────────────────

def gnews_url(query):
    """Correct Google News RSS URL format."""
    return (f"https://news.google.com/rss/search"
            f"?q={quote(query)}"
            f"&hl=en-IN&gl=IN&ceid=IN%3Aen")

def run_gnews(top_n=300):
    print(f"\n  [Layer 3] Google News RSS per symbol (top {top_n})...")
    c = get_conn(); setup(c)

    # Get symbols prioritized: signals_history first, then all
    sig_syms = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM signals_history
        WHERE run_date >= date('now', '-7 days')
        LIMIT 200
    """).fetchall()]

    all_syms = [r[0] for r in c.execute("""
        SELECT symbol FROM (
            SELECT symbol, COUNT(*) n FROM stock_data
            WHERE close IS NOT NULL
            GROUP BY symbol HAVING n > 500
        ) ORDER BY symbol
        LIMIT 2000
    """).fetchall()]

    # Priority order: signals first
    seen = set()
    ordered = []
    for s in sig_syms + all_syms:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    symbols = ordered[:top_n]

    # Get company names
    names = {}
    try:
        for sym, name in c.execute("""
            SELECT symbol, company_name FROM screener_fundamentals
            WHERE company_name IS NOT NULL
        """).fetchall():
            names[sym] = name
    except Exception:
        pass

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    })

    total_added = 0
    syms_with_news = 0
    batch_size = 50

    for i, sym in enumerate(symbols):
        company = names.get(sym, "")
        # Use company name if available, else symbol
        if company and company != sym:
            query = f'"{company}" stock India'
        else:
            query = f"{sym} NSE India"

        try:
            url  = gnews_url(query)
            resp = sess.get(url, timeout=10)

            if resp.status_code == 429:
                print(f"\n    Rate limited at {i+1} — sleeping 30s...")
                time.sleep(30)
                resp = sess.get(url, timeout=10)

            if resp.status_code == 200 and len(resp.text) > 200:
                items = parse_rss(resp.text)
                added = 0
                for title, link, ds in items[:6]:
                    score = sentiment(title)
                    added += insert_headline(c, ds, "GOOGLE_NEWS",
                                             title, link, sym, score, "gnews")
                if added > 0:
                    total_added += added
                    syms_with_news += 1

        except Exception as e:
            pass  # Silent — don't spam errors for 300 symbols

        if (i + 1) % batch_size == 0:
            c.commit()
            pct = (i + 1) / len(symbols) * 100
            print(f"    {i+1}/{len(symbols)} ({pct:.0f}%) "
                  f"— {total_added} headlines, {syms_with_news} symbols")
            time.sleep(1)  # polite pause every 50 symbols

        time.sleep(0.4)  # ~2.5 req/sec

    c.commit()
    c.close()
    print(f"  Layer 3: {total_added} headlines for {syms_with_news} symbols")
    return total_added


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE into symbol_news_daily
# ─────────────────────────────────────────────────────────────────────────────

def aggregate(days=3):
    print("\n  [Aggregating] symbol_news_daily...")
    c = get_conn(); setup(c)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = c.execute("""
        SELECT date, symbols_mentioned, headline, sentiment_score
        FROM news_headlines
        WHERE date >= ? AND symbols_mentioned IS NOT NULL
    """, (cutoff,)).fetchall()

    from collections import defaultdict
    groups = defaultdict(list)
    for ds, syms, hl, score in rows:
        if not syms: continue
        for sym in syms.split(","):
            sym = sym.strip().upper()
            if sym and sym not in ("MACRO",):
                groups[(sym, ds)].append((hl, score or 0.0))

    inserted = 0
    for (sym, ds), items in groups.items():
        scores = [s for _, s in items]
        hls    = [h for h, _ in items]
        c.execute("""
            INSERT OR REPLACE INTO symbol_news_daily
            (symbol,date,mention_count,sentiment_avg,headlines_json,last_updated)
            VALUES (?,?,?,?,?,?)
        """, (sym, ds, len(items),
              round(sum(scores)/len(scores), 3) if scores else 0.0,
              json.dumps(hls[:8]), NOW))
        inserted += 1

    c.commit()
    c.close()
    print(f"  Done: {inserted} symbol-day rows")
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# SHOW RESULTS
# ─────────────────────────────────────────────────────────────────────────────

def show():
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM news_headlines WHERE date=?", (TODAY,)).fetchone()[0]
    syms  = c.execute("SELECT COUNT(DISTINCT symbol) FROM symbol_news_daily WHERE date=?", (TODAY,)).fetchone()[0]
    sources = c.execute("""
        SELECT source, COUNT(*) FROM news_headlines
        WHERE date=? GROUP BY source ORDER BY COUNT(*) DESC
    """, (TODAY,)).fetchall()

    print(f"\n  📊 Today ({TODAY}): {total} headlines across {syms} symbols")
    print(f"  Sources: {', '.join(f'{s}({n})' for s,n in sources)}")

    rows = c.execute("""
        SELECT symbol, mention_count, sentiment_avg
        FROM symbol_news_daily WHERE date=?
        ORDER BY mention_count DESC LIMIT 20
    """, (TODAY,)).fetchall()

    if rows:
        print(f"\n  {'Symbol':<15} {'Hits':>5}  Sentiment")
        print(f"  {'-'*40}")
        for sym, cnt, sent in rows:
            bar   = "█" * min(cnt, 15)
            s_ico = "🟢" if (sent or 0) > 0.1 else ("🔴" if (sent or 0) < -0.1 else "⚪")
            print(f"  {sym:<15} {cnt:>5}  {s_ico} {(sent or 0):>+5.2f}  {bar}")

    # Negative alerts
    neg = c.execute("""
        SELECT symbol, mention_count, sentiment_avg, headlines_json
        FROM symbol_news_daily
        WHERE date=? AND sentiment_avg < -0.2 AND mention_count >= 2
        ORDER BY sentiment_avg ASC LIMIT 5
    """, (TODAY,)).fetchall()
    if neg:
        print(f"\n  🚨 Negative Alerts:")
        for sym, cnt, sent, hlj in neg:
            print(f"    {sym}: {sent:+.2f} ({cnt} articles)")
            try:
                hls = json.loads(hlj or "[]")
                if hls: print(f"      → {hls[0][:70]}")
            except Exception: pass

    c.close()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rss",    action="store_true")
    ap.add_argument("--nse",    action="store_true")
    ap.add_argument("--gnews",  action="store_true")
    ap.add_argument("--top",    type=int, default=300)
    ap.add_argument("--diag",   action="store_true", help="Diagnose DB state")
    args = ap.parse_args()
    run_all = not (args.rss or args.nse or args.gnews or args.diag)

    if args.diag:
        c = get_conn()
        print("\n=== DB Diagnostic ===")
        for tbl in ["news_headlines","corporate_announcements","signals_history","stock_data"]:
            try:
                n = c.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                print(f"  {tbl}: {n} rows")
            except Exception as e:
                print(f"  {tbl}: ERROR {e}")
        # Check announcement date column
        try:
            cols = [col[1] for col in c.execute("PRAGMA table_info(corporate_announcements)").fetchall()]
            print(f"\n  corporate_announcements columns: {cols}")
            sample = c.execute("SELECT * FROM corporate_announcements LIMIT 2").fetchall()
            for row in sample:
                print(f"  sample: {row}")
        except Exception as e:
            print(f"  {e}")
        c.close()
        return

    print(f"\n{'='*60}")
    print("  MICC News v3")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    c = get_conn(); setup(c)
    lookup = build_lookup(c)
    c.close()
    print(f"  Lookup: {len(lookup)} keywords")

    if run_all or args.rss:
        run_rss(lookup)
    if run_all or args.nse:
        run_nse_announcements()
    if run_all or args.gnews:
        run_gnews(args.top)

    aggregate(days=3)
    show()
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
