# -*- coding: utf-8 -*-
"""
fetch_news.py  —  MICC News Headlines (zero new dependencies)
=============================================================
Uses only: requests, sqlite3 — both already installed and working.
No feedparser needed. Parses RSS XML directly.

Place at: D:\MICC\data_pipeline\fetch_news.py
Run:      py D:\MICC\data_pipeline\fetch_news.py
"""
import os, sqlite3, time, re, sys
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")
NOW     = datetime.now().isoformat()
TODAY   = datetime.now().strftime("%Y-%m-%d")

# ── RSS feeds — no library needed, pure XML ──────────────────────────────────
FEEDS = [
    ("ET Markets",    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("ET Stocks",     "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Business Std",  "https://www.business-standard.com/rss/markets-106.rss"),
    ("Livemint",      "https://www.livemint.com/rss/markets"),
    ("Hindu Biz",     "https://www.thehindu.com/business/markets/?service=rss"),
]

# ── Symbols to watch for in headlines ────────────────────────────────────────
WATCH = {
    "RELIANCE":  ["reliance","ril"],
    "TCS":       ["tcs","tata consultancy"],
    "HDFCBANK":  ["hdfc bank"],
    "INFY":      ["infosys"],
    "ICICIBANK": ["icici bank"],
    "SBIN":      ["sbi","state bank"],
    "WIPRO":     ["wipro"],
    "AXISBANK":  ["axis bank"],
    "ADANIENT":  ["adani"],
    "TATAMOTORS":["tata motors"],
    "ZOMATO":    ["zomato"],
    "LT":        ["larsen","l&t"],
    "BAJFINANCE":["bajaj finance"],
    "NIFTY":     ["nifty","nse index"],
    "SENSEX":    ["sensex","bse"],
}

POS = ["surge","rally","gain","jump","rise","bull","profit","growth","record","strong","high","beat","upgrade"]
NEG = ["crash","fall","drop","decline","bear","loss","weak","low","miss","downgrade","concern","warning"]

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def setup(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS news_headlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            source TEXT,
            headline TEXT NOT NULL,
            url TEXT UNIQUE,
            symbols_mentioned TEXT,
            sentiment_score REAL,
            last_updated TEXT
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_news_date ON news_headlines(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_news_sym  ON news_headlines(symbols_mentioned)")
    c.commit()

def sentiment(text):
    t = text.lower()
    p = sum(1 for w in POS if w in t)
    n = sum(1 for w in NEG if w in t)
    return round((p - n) / (p + n), 2) if (p + n) else 0.0

def symbols(text):
    t = text.lower()
    found = [sym for sym, kws in WATCH.items() if any(k in t for k in kws)]
    return ",".join(found) or None

def parse_rss(xml_text):
    """Parse RSS XML without feedparser."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # Standard RSS
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link  = item.findtext("link",  "").strip()
            pub   = item.findtext("pubDate", "").strip()
            if title:
                try:
                    from email.utils import parsedate
                    import calendar
                    t = parsedate(pub)
                    date_str = f"{t[0]}-{t[1]:02d}-{t[2]:02d}" if t else TODAY
                except Exception:
                    date_str = TODAY
                items.append((title, link, date_str))
        # Atom feeds
        if not items:
            for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                title = entry.findtext("{http://www.w3.org/2005/Atom}title", "").strip()
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                link = link_el.get("href","") if link_el is not None else ""
                items.append((title, link, TODAY))
    except Exception as e:
        print(f"    XML parse error: {e}")
    return items

def main():
    print(f"\n{'='*55}")
    print("  MICC News Headlines")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    c = get_conn()
    setup(c)
    total = 0

    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0"})

    for source, url in FEEDS:
        try:
            resp = sess.get(url, timeout=12)
            if resp.status_code != 200:
                print(f"  ⚠️  {source}: HTTP {resp.status_code}")
                continue
            items = parse_rss(resp.text)
            inserted = 0
            for title, link, date_str in items[:40]:
                try:
                    c.execute("""
                        INSERT OR IGNORE INTO news_headlines
                        (date,source,headline,url,symbols_mentioned,sentiment_score,last_updated)
                        VALUES (?,?,?,?,?,?,?)
                    """, (date_str, source, title, link or None,
                          symbols(title), sentiment(title), NOW))
                    if c.execute("SELECT changes()").fetchone()[0]:
                        inserted += 1
                except Exception:
                    pass
            c.commit()
            total += inserted
            print(f"  ✅  {source}: {inserted} new headlines")
            time.sleep(0.5)
        except Exception as e:
            print(f"  ❌  {source}: {e}")

    # Summary
    row = c.execute("SELECT COUNT(*) FROM news_headlines").fetchone()
    print(f"\n  Total in DB: {row[0]} headlines | Added today: {total}")

    # Top symbols today
    rows = c.execute("""
        SELECT symbols_mentioned, COUNT(*) as n
        FROM news_headlines
        WHERE date=? AND symbols_mentioned IS NOT NULL
        GROUP BY symbols_mentioned ORDER BY n DESC LIMIT 8
    """, (TODAY,)).fetchall()
    if rows:
        print("\n  Most mentioned today:")
        for sym, n in rows:
            print(f"    {sym:<15} {n} articles")

    c.close()
    print(f"\n{'='*55}\n")

if __name__ == "__main__":
    main()
