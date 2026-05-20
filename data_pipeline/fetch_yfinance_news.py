# fetch_yfinance_news.py  v2
# Place: D:\\MICC\\data_pipeline\\fetch_yfinance_news.py
# Run:   py D:\\MICC\\data_pipeline\\fetch_yfinance_news.py --top 500
import os, sys, sqlite3, time, json, argparse
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH  = Path(r"D:\marketDB\db\market.db")
NOW      = datetime.now().isoformat()
TODAY    = datetime.now().strftime("%Y-%m-%d")
WEEK_AGO = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

POS = ["surge","rally","gain","jump","rise","bull","profit","growth","record",
       "strong","beat","upgrade","positive","breakout","dividend","bonus","soar",
       "outperform","robust","climbs","recovers","expansion","wins","higher"]
NEG = ["crash","fall","drop","decline","bear","loss","weak","miss","downgrade",
       "concern","warning","risk","fraud","probe","penalty","trouble","plunge",
       "slump","default","write-off","shutdown","recall","selloff","lower"]

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c

def sentiment(text):
    t = text.lower()
    p = sum(1 for w in POS if w in t)
    n = sum(1 for w in NEG if w in t)
    return round((p-n)/(p+n), 2) if (p+n) else 0.0

def insert(c, date_str, headline, url, symbol, score):
    try:
        c.execute("""
            INSERT OR IGNORE INTO news_headlines
            (date,source,headline,url,symbols_mentioned,
             sentiment_score,category,last_updated)
            VALUES (?,?,?,?,?,?,'stock_news',?)
        """, (date_str, "YFINANCE", headline[:400], url, symbol, score, NOW))
        return c.execute("SELECT changes()").fetchone()[0]
    except Exception:
        return 0

def parse_article(article, sym):
    """yfinance 1.2.2: title is inside article['content']['title']"""
    ct = article.get("content", {})
    if not ct:
        return None
    title = ct.get("title","").strip()
    if not title:
        return None
    url = ""
    for k in ["canonicalUrl","clickThroughUrl"]:
        obj = ct.get(k, {})
        if isinstance(obj, dict) and obj.get("url"):
            url = obj["url"]; break
    pub = ct.get("pubDate","")
    try:
        ds = datetime.strptime(pub[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        ds = TODAY
    summary = ct.get("summary","")
    return {"title":title, "url":url, "date":ds,
            "score":sentiment(f"{title} {summary}"), "sym":sym}

def get_symbols(c, top_n):
    sig = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM signals_history
        WHERE run_date >= date('now','-7 days') ORDER BY symbol
    """).fetchall()]
    watch = []
    for wf in [Path(r"D:\MICC\micc_watchlist.json"),
               Path(r"D:\MICC\micc_watchlists.json")]:
        if wf.exists():
            try:
                d = json.loads(wf.read_text())
                watch = list(d.keys()) if isinstance(d, dict) else []
                break
            except Exception:
                pass
    all_s = [r[0] for r in c.execute("""
        SELECT symbol FROM (
            SELECT symbol, COUNT(*) n FROM stock_data
            WHERE close IS NOT NULL GROUP BY symbol HAVING n > 500
        ) ORDER BY symbol LIMIT 3000
    """).fetchall()]
    seen = set(); out = []
    for s in sig + watch + all_s:
        if s and s not in seen:
            seen.add(s); out.append(s)
    return out[:top_n], len(sig), len(watch)

def aggregate(c):
    rows = c.execute("""
        SELECT date, symbols_mentioned, headline, sentiment_score
        FROM news_headlines
        WHERE date >= ? AND symbols_mentioned IS NOT NULL
    """, (WEEK_AGO,)).fetchall()
    from collections import defaultdict
    g = defaultdict(list)
    for ds, syms, hl, sc in rows:
        if not syms: continue
        for sym in syms.split(","):
            sym = sym.strip().upper()
            if sym: g[(sym, ds)].append((hl, sc or 0.0))
    for (sym, ds), items in g.items():
        sc = [s for _, s in items]
        c.execute("""
            INSERT OR REPLACE INTO symbol_news_daily
            (symbol,date,mention_count,sentiment_avg,headlines_json,last_updated)
            VALUES (?,?,?,?,?,?)
        """, (sym, ds, len(items),
              round(sum(sc)/len(sc), 3) if sc else 0.0,
              json.dumps([h for h, _ in items][:8]), NOW))
    c.commit()

def show(c):
    total = c.execute(
        "SELECT COUNT(*) FROM news_headlines WHERE date>=?", (WEEK_AGO,)
    ).fetchone()[0]
    syms = c.execute(
        "SELECT COUNT(DISTINCT symbol) FROM symbol_news_daily WHERE date>=?", (WEEK_AGO,)
    ).fetchone()[0]
    today_n = c.execute(
        "SELECT COUNT(*) FROM news_headlines WHERE date=?", (TODAY,)
    ).fetchone()[0]

    print(f"\n  {'='*55}")
    print(f"  Last 7 days : {total} headlines | {syms} symbols")
    print(f"  Today only  : {today_n} headlines")

    srcs = c.execute("""
        SELECT source, COUNT(*) n FROM news_headlines
        WHERE date>=? GROUP BY source ORDER BY n DESC
    """, (WEEK_AGO,)).fetchall()
    print(f"\n  Sources (7 days):")
    for s, n in srcs:
        bar = "█" * min(n//5, 30)
        print(f"    {s:<25} {n:>5}  {bar}")

    rows = c.execute("""
        SELECT symbol, SUM(mention_count) total, AVG(sentiment_avg) avg_s
        FROM symbol_news_daily WHERE date>=?
        GROUP BY symbol ORDER BY total DESC LIMIT 30
    """, (WEEK_AGO,)).fetchall()
    if rows:
        print(f"\n  Top 30 symbols (7 days):")
        print(f"  {'Symbol':<15} {'Articles':>8}  Sentiment")
        print(f"  {'-'*45}")
        for sym, cnt, sent in rows:
            ico = "🟢" if (sent or 0)>0.1 else ("🔴" if (sent or 0)<-0.1 else "⚪")
            bar = "█" * min(int(cnt), 20)
            print(f"  {sym:<15} {int(cnt):>8}  {ico} {(sent or 0):>+5.2f}  {bar}")

    neg = c.execute("""
        SELECT symbol, AVG(sentiment_avg) s, SUM(mention_count) n
        FROM symbol_news_daily WHERE date>=?
        GROUP BY symbol HAVING s < -0.2 AND n >= 3
        ORDER BY s ASC LIMIT 8
    """, (WEEK_AGO,)).fetchall()
    if neg:
        print(f"\n  Negative alerts (7 days):")
        for sym, s, n in neg:
            print(f"    {sym:<15} {s:+.2f}  ({int(n)} articles)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top",  type=int, default=200)
    ap.add_argument("--show", action="store_true", help="Stats only, no fetch")
    args = ap.parse_args()

    print(f"\n{'='*60}")
    print(f"  MICC yfinance News  |  yfinance {yf.__version__}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    c = get_conn()

    if args.show:
        aggregate(c); show(c); c.close(); return

    symbols, n_sig, n_watch = get_symbols(c, args.top)
    print(f"  {len(symbols)} symbols  ({n_sig} signals, {n_watch} watchlist)\n")

    total = 0; with_news = 0; no_news = 0

    for i, sym in enumerate(symbols):
        try:
            raw = yf.Ticker(f"{sym}.NS").news or []
            added = 0
            for art in raw[:8]:
                p = parse_article(art, sym)
                if p:
                    added += insert(c, p["date"], p["title"],
                                    p["url"] or None, sym, p["score"])
            if added > 0:
                total += added; with_news += 1
            else:
                no_news += 1
        except Exception:
            no_news += 1

        if (i+1) % 50 == 0:
            c.commit()
            pct = (i+1)/len(symbols)*100
            print(f"  {i+1:>4}/{len(symbols)} ({pct:.0f}%)"
                  f"  ✅ {with_news} stocks"
                  f"  📰 {total} articles"
                  f"  ⚪ {no_news} no news")
        time.sleep(0.2)

    c.commit()
    print(f"\n  Done: {total} articles for {with_news} stocks")
    aggregate(c)
    show(c)
    c.close()
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
