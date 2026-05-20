# -*- coding: utf-8 -*-
"""
fetch_yfinance_news.py  —  Per-stock news via yfinance 1.2.2
============================================================
yfinance 1.2.2 changed the news dict structure to:
  item["content"]["title"]
  item["content"]["pubDate"]
  item["content"]["canonicalUrl"]["url"]
  item["content"]["summary"]

Run:
  py D:\MICC\data_pipeline\fetch_yfinance_news.py           # top 200
  py D:\MICC\data_pipeline\fetch_yfinance_news.py --top 500 # top 500
  py D:\MICC\data_pipeline\fetch_yfinance_news.py --top 500 --all  # all signals+watchlist+500
"""
import os, sys, sqlite3, time, json, argparse
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")
NOW     = datetime.now().isoformat()
TODAY   = datetime.now().strftime("%Y-%m-%d")

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

def insert(c, date_str, source, headline, url, symbol, score):
    try:
        c.execute("""
            INSERT OR IGNORE INTO news_headlines
            (date,source,headline,url,symbols_mentioned,sentiment_score,category,last_updated)
            VALUES (?,?,?,?,?,?,'stock_news',?)
        """, (date_str, source, headline[:400], url, symbol, score, NOW))
        return c.execute("SELECT changes()").fetchone()[0]
    except Exception:
        return 0

# ── Parse yfinance 1.2.2 news structure ──────────────────────────────────────

def parse_yf_article(article, sym):
    """
    yfinance 1.2.2 structure:
      article = { "id": "...", "content": { "title": "...", "pubDate": "...", ... } }
    """
    content = article.get("content", {})
    if not content:
        return None

    title = content.get("title", "").strip()
    if not title:
        return None

    # URL: prefer canonicalUrl, fallback clickThroughUrl
    url = ""
    for url_key in ["canonicalUrl", "clickThroughUrl"]:
        url_obj = content.get(url_key, {})
        if isinstance(url_obj, dict) and url_obj.get("url"):
            url = url_obj["url"]
            break

    # Date
    pub = content.get("pubDate") or content.get("displayTime") or ""
    try:
        ds = datetime.strptime(pub[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        ds = TODAY

    # Summary for richer sentiment
    summary = content.get("summary", "")
    sentiment_text = f"{title} {summary}"

    return {
        "title":    title,
        "url":      url,
        "date":     ds,
        "summary":  summary[:300],
        "provider": content.get("provider", {}).get("displayName", ""),
        "symbol":   sym,
        "score":    sentiment(sentiment_text),
    }

# ── Get symbol list ───────────────────────────────────────────────────────────

def get_symbols(c, top_n):
    # Priority 1: signals_history (MICC is watching these)
    sig = [r[0] for r in c.execute("""
        SELECT DISTINCT symbol FROM signals_history
        WHERE run_date >= date('now','-7 days') ORDER BY symbol
    """).fetchall()]

    # Priority 2: watchlist
    watch = []
    for wf in [Path(r"D:\MICC\micc_watchlist.json"),
                Path(r"D:\MICC\micc_watchlists.json")]:
        if wf.exists():
            try:
                data = json.loads(wf.read_text())
                watch = list(data.keys()) if isinstance(data, dict) else []
                break
            except Exception:
                pass

    # Priority 3: all symbols with enough history
    all_syms = [r[0] for r in c.execute("""
        SELECT symbol FROM (
            SELECT symbol, COUNT(*) n FROM stock_data
            WHERE close IS NOT NULL GROUP BY symbol HAVING n > 500
        ) ORDER BY symbol LIMIT 3000
    """).fetchall()]

    seen = set(); ordered = []
    for s in (sig + watch + all_syms):
        if s and s not in seen:
            seen.add(s); ordered.append(s)

    return ordered[:top_n], len(sig), len(watch)

# ── Aggregate into symbol_news_daily ─────────────────────────────────────────

def aggregate(c):
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
            if sym:
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
    c.commit()

# ── Main fetch ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=200, help="Max symbols (default 200)")
    args = ap.parse_args()

    print(f"\n{'='*60}")
    print(f"  MICC yfinance News (v1.2.2 fixed)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    c = get_conn()
    symbols, n_sig, n_watch = get_symbols(c, args.top)
    print(f"  Symbols: {len(symbols)} total ({n_sig} from signals, {n_watch} from watchlist)")
    print(f"  yfinance: {yf.__version__}\n")

    total_added = 0
    syms_with_news = 0
    syms_no_news   = 0
    BATCH = 50

    for i, sym in enumerate(symbols):
        try:
            ticker = yf.Ticker(f"{sym}.NS")
            raw_news = ticker.news or []

            added = 0
            for article in raw_news[:8]:
                parsed = parse_yf_article(article, sym)
                if not parsed:
                    continue
                n = insert(c, parsed["date"], "YFINANCE",
                           parsed["title"], parsed["url"] or None,
                           sym, parsed["score"])
                added += n

            if added > 0:
                total_added  += added
                syms_with_news += 1
            else:
                syms_no_news += 1

        except Exception as e:
            syms_no_news += 1

        # Progress + commit every batch
        if (i + 1) % BATCH == 0:
            c.commit()
            pct = (i+1) / len(symbols) * 100
            print(f"  {i+1:>4}/{len(symbols)} ({pct:.0f}%) "
                  f"— ✅ {syms_with_news} stocks  "
                  f"📰 {total_added} headlines  "
                  f"⚪ {syms_no_news} no news")

        time.sleep(0.2)  # ~5 req/sec — yfinance is fine with this

    c.commit()

    # Final aggregate
    aggregate(c)

    # Show results
    print(f"\n{'─'*60}")
    print(f"  Done: {total_added} headlines for {syms_with_news} stocks")

    total_today = c.execute(
        "SELECT COUNT(*) FROM news_headlines WHERE date=?", (TODAY,)
    ).fetchone()[0]
    syms_today = c.execute(
        "SELECT COUNT(DISTINCT symbol) FROM symbol_news_daily WHERE date=?", (TODAY,)
    ).fetchone()[0]

    print(f"  DB today: {total_today} headlines | {syms_today} symbols covered")
    print()

    # Top 30 by mention count
    rows = c.execute("""
        SELECT symbol, mention_count, sentiment_avg
        FROM symbol_news_daily WHERE date=?
        ORDER BY mention_count DESC LIMIT 30
    """, (TODAY,)).fetchall()

    if rows:
        print(f"  {'Symbol':<15} {'Count':>5}  Sentiment")
        print(f"  {'-'*45}")
        for sym, cnt, sent in rows:
            ico = "🟢" if (sent or 0)>0.1 else ("🔴" if (sent or 0)<-0.1 else "⚪")
            bar = "█" * min(cnt, 20)
            print(f"  {sym:<15} {cnt:>5}  {ico} {(sent or 0):>+5.2f}  {bar}")

    # Source breakdown
    srcs = c.execute("""
        SELECT source, COUNT(*) FROM news_headlines
        WHERE date=? GROUP BY source ORDER BY 2 DESC
    """, (TODAY,)).fetchall()
    print(f"\n  Sources today:")
    for s, n in srcs:
        print(f"    {s:<25} {n}")

    # Negative alerts
    neg = c.execute("""
        SELECT symbol, sentiment_avg, headlines_json
        FROM symbol_news_daily
        WHERE date=? AND sentiment_avg < -0.2 AND mention_count >= 2
        ORDER BY sentiment_avg ASC LIMIT 8
    """, (TODAY,)).fetchall()
    if neg:
        print(f"\n  🚨 Negative alerts today:")
        for sym, sent, hlj in neg:
            print(f"    {sym}: {sent:+.2f}")
            try:
                h = json.loads(hlj or "[]")
                if h: print(f"      → {h[0][:70]}")
            except Exception:
                pass

    c.close()
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
