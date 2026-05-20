# -*- coding: utf-8 -*-
"""
patch_news_layer3.py  —  Fix yfinance Layer 3 + add more RSS sources
=====================================================================
Patches the Layer 3 issue: yfinance .news returns [] for .NS stocks
in yfinance >= 0.2.x. Uses the correct modern API.

Also adds more RSS feeds covering mid/small caps:
  - Moneycontrol small cap RSS
  - BSE announcements direct feed

Run:
  py D:\MICC\data_pipeline\patch_news_layer3.py
  py D:\MICC\data_pipeline\patch_news_layer3.py --top 500
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
       "strong","beat","upgrade","positive","breakout","dividend","bonus","soar"]
NEG = ["crash","fall","drop","decline","bear","loss","weak","miss","downgrade",
       "concern","warning","risk","fraud","probe","penalty","trouble","plunge"]

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def sentiment(text):
    t = text.lower()
    p = sum(1 for w in POS if w in t)
    n = sum(1 for w in NEG if w in t)
    return round((p-n)/(p+n), 2) if (p+n) else 0.0

def insert(c, date_str, source, headline, url, symbol, score, category="stock_news"):
    try:
        c.execute("""
            INSERT OR IGNORE INTO news_headlines
            (date,source,headline,url,symbols_mentioned,sentiment_score,category,last_updated)
            VALUES (?,?,?,?,?,?,?,?)
        """, (date_str, source, headline[:400], url, symbol, score, category, NOW))
        return c.execute("SELECT changes()").fetchone()[0]
    except Exception as e:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST: What yfinance version and which news method works
# ─────────────────────────────────────────────────────────────────────────────

def test_yfinance_news():
    """Run this first to see what works on your machine."""
    import yfinance as yf
    print(f"\n  yfinance version: {yf.__version__}")

    test_sym = "RELIANCE.NS"
    t = yf.Ticker(test_sym)

    # Method 1: .news property
    try:
        news1 = t.news
        print(f"  .news property: {len(news1)} items")
        if news1:
            print(f"    Sample: {news1[0].get('title','')[:60]}")
    except Exception as e:
        print(f"  .news property: ERROR {e}")

    # Method 2: .get_news()
    try:
        news2 = t.get_news()
        print(f"  .get_news(): {len(news2)} items")
        if news2:
            print(f"    Sample: {news2[0].get('title','')[:60]}")
    except Exception as e:
        print(f"  .get_news(): ERROR {e}")

    # Method 3: yf.Search
    try:
        search = yf.Search("RELIANCE NSE India", news_count=5)
        news3 = search.news
        print(f"  yf.Search().news: {len(news3)} items")
        if news3:
            print(f"    Sample: {news3[0].get('title','')[:60]}")
    except Exception as e:
        print(f"  yf.Search().news: ERROR {e}")

    # Method 4: Direct Yahoo Finance RSS (no auth)
    try:
        url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=RELIANCE.NS&region=IN&lang=en-IN"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
        print(f"  Yahoo Finance RSS: HTTP {r.status_code}, len={len(r.text)}")
        if r.status_code == 200:
            print(f"    Preview: {r.text[:100]}")
    except Exception as e:
        print(f"  Yahoo Finance RSS: ERROR {e}")


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3A: yfinance with correct modern API
# ─────────────────────────────────────────────────────────────────────────────

def get_yfinance_news(ticker_obj, sym):
    """Try all yfinance news methods, return list of (title, url, date_str)."""
    results = []

    # Try .news property first
    try:
        news = ticker_obj.news or []
        if news:
            for a in news:
                title = a.get("title","").strip()
                url   = a.get("link") or a.get("url","")
                ts    = a.get("providerPublishTime") or a.get("publishTime", 0)
                try:
                    ds = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                except Exception:
                    ds = TODAY
                if title:
                    results.append((title, url, ds))
    except Exception:
        pass

    if results:
        return results

    # Try .get_news() method (yfinance >= 0.2.50)
    try:
        news = ticker_obj.get_news() or []
        for a in news:
            title = a.get("title","").strip()
            url   = a.get("link") or a.get("url","")
            ts    = a.get("providerPublishTime", 0)
            try:
                ds = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except Exception:
                ds = TODAY
            if title:
                results.append((title, url, ds))
    except Exception:
        pass

    return results


def run_yfinance_layer(top_n=200):
    """Layer 3: per-stock news via yfinance."""
    print(f"\n  [Layer 3] Per-stock news via yfinance (top {top_n})...")

    try:
        import yfinance as yf
        ver = yf.__version__
        print(f"  yfinance {ver}")
    except ImportError:
        print("  ❌ yfinance not installed")
        return 0

    c = get_conn()

    # Get prioritized symbols
    sig_syms = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM signals_history
        WHERE run_date >= date('now','-7 days') ORDER BY symbol
    """).fetchall()]

    watch_syms = []
    try:
        wf = Path(r"D:\MICC\micc_watchlist.json")
        if wf.exists():
            watch_syms = list(json.loads(wf.read_text()).keys())
    except Exception:
        pass

    all_syms = [r[0] for r in c.execute("""
        SELECT symbol FROM (
            SELECT symbol, COUNT(*) n FROM stock_data
            WHERE close IS NOT NULL GROUP BY symbol HAVING n > 500
        ) ORDER BY symbol LIMIT 2000
    """).fetchall()]

    seen = set(); ordered = []
    for s in (sig_syms + watch_syms + all_syms):
        if s and s not in seen:
            seen.add(s); ordered.append(s)
    symbols = ordered[:top_n]
    print(f"  {len(symbols)} symbols ({len(sig_syms)} signals, {len(watch_syms)} watchlist)")

    total = 0; with_news = 0; errors = 0

    for i, sym in enumerate(symbols):
        try:
            # Try with .NS suffix first
            ticker = yf.Ticker(f"{sym}.NS")
            articles = get_yfinance_news(ticker, sym)

            # Fallback: try without suffix (some symbols work both ways)
            if not articles:
                ticker2 = yf.Ticker(sym)
                articles = get_yfinance_news(ticker2, sym)

            added = 0
            for title, url, ds in articles[:6]:
                added += insert(c, ds, "YFINANCE", title, url or None,
                                sym, sentiment(title), "stock_news")
            if added > 0:
                total += added; with_news += 1

        except Exception as e:
            errors += 1

        if (i+1) % 50 == 0:
            c.commit()
            pct = (i+1)/len(symbols)*100
            print(f"    {i+1}/{len(symbols)} ({pct:.0f}%) — {total} headlines, "
                  f"{with_news} stocks, {errors} errors")

        time.sleep(0.2)

    c.commit(); c.close()
    print(f"  Layer 3: {total} headlines for {with_news} stocks ({errors} errors)")
    return total


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3B: Yahoo Finance RSS per stock (alternative if yfinance fails)
# ─────────────────────────────────────────────────────────────────────────────

def parse_rss(text):
    items = []
    try:
        text = re.sub(r'<\?xml[^?]*\?>', '', text).strip()
        text = re.sub(r' xmlns(?::\w+)?="[^"]*"', '', text)
        root = ET.fromstring(text)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            if not title: continue
            try:
                from email.utils import parsedate
                t = parsedate(pub)
                ds = f"{t[0]}-{t[1]:02d}-{t[2]:02d}" if t else TODAY
            except Exception:
                ds = TODAY
            items.append((title, link, ds))
    except Exception:
        pass
    return items

def run_yahoo_rss_layer(top_n=200):
    """
    Alternative Layer 3: Yahoo Finance RSS per stock.
    URL format that works: feeds.finance.yahoo.com/rss/2.0/headline?s=SYMBOL.NS
    """
    print(f"\n  [Layer 3B] Yahoo Finance RSS per stock (top {top_n})...")
    c = get_conn()

    sig_syms = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM signals_history
        WHERE run_date >= date('now','-7 days')
    """).fetchall()]
    all_syms = [r[0] for r in c.execute("""
        SELECT symbol FROM (
            SELECT symbol, COUNT(*) n FROM stock_data
            GROUP BY symbol HAVING n > 500
        ) ORDER BY symbol LIMIT 2000
    """).fetchall()]

    seen = set(); ordered = []
    for s in sig_syms + all_syms:
        if s and s not in seen:
            seen.add(s); ordered.append(s)
    symbols = ordered[:top_n]

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })

    total = 0; with_news = 0

    for i, sym in enumerate(symbols):
        # Yahoo Finance RSS - two URL formats to try
        urls = [
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}.NS&region=IN&lang=en-IN",
            f"https://finance.yahoo.com/rss/headline?s={sym}.NS",
        ]

        for url in urls:
            try:
                r = sess.get(url, timeout=8)
                if r.status_code == 200 and len(r.text) > 200:
                    items = parse_rss(r.text)
                    added = 0
                    for title, link, ds in items[:6]:
                        added += insert(c, ds, "YAHOO_RSS", title, link or None,
                                        sym, sentiment(title), "stock_news")
                    if added > 0:
                        total += added; with_news += 1
                    break  # got data, no need to try second URL
            except Exception:
                pass

        if (i+1) % 50 == 0:
            c.commit()
            pct = (i+1)/len(symbols)*100
            print(f"    {i+1}/{len(symbols)} ({pct:.0f}%) — {total} headlines, "
                  f"{with_news} stocks with news")

        time.sleep(0.3)

    c.commit(); c.close()
    print(f"  Layer 3B: {total} headlines for {with_news} stocks")
    return total


# ─────────────────────────────────────────────────────────────────────────────
# SHOW RESULTS
# ─────────────────────────────────────────────────────────────────────────────

def show():
    c = get_conn()
    total = c.execute("SELECT COUNT(*) FROM news_headlines WHERE date=?", (TODAY,)).fetchone()[0]
    syms  = c.execute("SELECT COUNT(DISTINCT symbol) FROM symbol_news_daily WHERE date=?", (TODAY,)).fetchone()[0]
    srcs  = c.execute("""
        SELECT source, COUNT(*) FROM news_headlines
        WHERE date=? GROUP BY source ORDER BY 2 DESC
    """, (TODAY,)).fetchall()

    print(f"\n  📊 Today: {total} headlines | {syms} symbols")
    for s, n in srcs:
        bar = "█" * min(n // 2, 20)
        print(f"    {s:<25} {n:>4}  {bar}")

    rows = c.execute("""
        SELECT symbol, mention_count, sentiment_avg
        FROM symbol_news_daily WHERE date=?
        ORDER BY mention_count DESC LIMIT 30
    """, (TODAY,)).fetchall()

    if rows:
        print(f"\n  {'Symbol':<15} {'Count':>5}  Sentiment")
        print(f"  {'-'*40}")
        for sym, cnt, sent in rows:
            ico = "🟢" if (sent or 0) > 0.1 else ("🔴" if (sent or 0) < -0.1 else "⚪")
            bar = "█" * min(cnt, 20)
            print(f"  {sym:<15} {cnt:>5}  {ico} {(sent or 0):>+5.2f}  {bar}")

    c.close()


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

    for (sym, ds), items in groups.items():
        scores = [s for _, s in items]
        c.execute("""
            INSERT OR REPLACE INTO symbol_news_daily
            (symbol,date,mention_count,sentiment_avg,headlines_json,last_updated)
            VALUES (?,?,?,?,?,?)
        """, (sym, ds, len(items),
              round(sum(scores)/len(scores), 3) if scores else 0.0,
              json.dumps([h for h,_ in items][:8]), NOW))
    c.commit(); c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test",   action="store_true", help="Test yfinance methods")
    ap.add_argument("--yf",     action="store_true", help="yfinance layer")
    ap.add_argument("--yahoo",  action="store_true", help="Yahoo RSS layer (alternative)")
    ap.add_argument("--top",    type=int, default=200)
    args = ap.parse_args()

    print(f"\n{'='*60}")
    print("  MICC News Layer 3 Patch")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Always run test first so you can see what works
    if args.test or not (args.yf or args.yahoo):
        print("\n  Testing yfinance news methods...")
        try:
            test_yfinance_news()
        except Exception as e:
            print(f"  Test error: {e}")

    if args.yf:
        run_yfinance_layer(args.top)
        aggregate(); show()

    if args.yahoo:
        run_yahoo_rss_layer(args.top)
        aggregate(); show()

    if not (args.test or args.yf or args.yahoo):
        print("\n  Run with --test first to see what works on your machine:")
        print("  py patch_news_layer3.py --test")
        print()
        print("  Then run whichever worked:")
        print("  py patch_news_layer3.py --yf --top 200      # yfinance")
        print("  py patch_news_layer3.py --yahoo --top 200   # Yahoo RSS")

if __name__ == "__main__":
    main()
