import sqlite3, time, sys, json
from pathlib import Path
from datetime import datetime

DB = r"D:\marketDB\db\market.db"

# ── Install deps if missing ───────────────────────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "requests", "beautifulsoup4", "lxml",
                    "--break-system-packages", "-q"])
    import requests
    from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
BASE    = "https://www.screener.in/company"
DELAY   = 1.2       # seconds between requests (be polite)
BATCH   = 50        # commit every N rows
LIMIT   = int(sys.argv[1]) if len(sys.argv) > 1 else 500   # py script.py 100

print(f"Screener.in fundamentals scraper")
print(f"  Target : {LIMIT} symbols")
print(f"  Delay  : {DELAY}s between requests")

conn = sqlite3.connect(DB, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

# ── Create / update table ─────────────────────────────────────────────────────
conn.execute("""
    CREATE TABLE IF NOT EXISTS screener_fundamentals_v2 (
        symbol          TEXT PRIMARY KEY,
        pe_ratio        REAL,
        pb_ratio        REAL,
        roce            REAL,
        roe             REAL,
        debt_equity     REAL,
        promoter_pct    REAL,
        market_cap_cr   REAL,
        sales_cr        REAL,
        profit_cr       REAL,
        eps             REAL,
        div_yield       REAL,
        face_value      REAL,
        book_value      REAL,
        current_price   REAL,
        high_52w        REAL,
        low_52w         REAL,
        scraped_date    TEXT
    )
""")
conn.commit()

# ── Get symbols to scrape ─────────────────────────────────────────────────────
# Priority: conviction top stocks first, then by market cap
rows = conn.execute("""
    SELECT s.symbol FROM (
        SELECT symbol, conviction_score
        FROM symbol_conviction
        ORDER BY CAST(conviction_score AS REAL) DESC
        LIMIT ?
    ) s
""", (LIMIT,)).fetchall()

if not rows:
    # fallback: just use stock_data symbols
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM stock_data ORDER BY symbol LIMIT ?", (LIMIT,)
    ).fetchall()

symbols = [r[0] for r in rows]
print(f"  Symbols: {len(symbols)}")

# ── Helper: parse a Screener page ─────────────────────────────────────────────
def clean_num(text):
    if not text:
        return None
    t = str(text).replace(",", "").replace("%", "").replace("Cr.", "").strip()
    t = t.split()[0] if t.split() else t
    try:
        return float(t)
    except Exception:
        return None

def scrape(symbol):
    url = f"{BASE}/{symbol}/consolidated/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 404:
            # try non-consolidated
            r = requests.get(f"{BASE}/{symbol}/", headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f"    [{symbol}] request error: {e}")
        return None

    soup = BeautifulSoup(r.text, "lxml")

    def ratio_val(label):
        # Screener puts ratios in <li> tags like:
        # <li><span class="name">P/E</span><span class="number">23.5</span></li>
        for li in soup.select("ul.company-ratios li, #top-ratios li"):
            name_el = li.select_one(".name, span:first-child")
            num_el  = li.select_one(".number, .value, span:last-child")
            if name_el and num_el:
                if label.lower() in name_el.get_text(strip=True).lower():
                    return clean_num(num_el.get_text(strip=True))
        return None

    def table_val(table_id, row_label):
        tbl = soup.select_one(f"#{table_id}, .{table_id}")
        if not tbl:
            return None
        for tr in tbl.select("tr"):
            cells = tr.select("td, th")
            if cells and row_label.lower() in cells[0].get_text(strip=True).lower():
                if len(cells) > 1:
                    return clean_num(cells[-1].get_text(strip=True))
        return None

    data = {
        "symbol":        symbol,
        "pe_ratio":      ratio_val("P/E"),
        "pb_ratio":      ratio_val("P/B"),
        "roce":          ratio_val("ROCE"),
        "roe":           ratio_val("ROE"),
        "debt_equity":   ratio_val("Debt / Equity") or ratio_val("Debt/Equity"),
        "promoter_pct":  None,
        "market_cap_cr": ratio_val("Market Cap"),
        "eps":           ratio_val("EPS"),
        "div_yield":     ratio_val("Div Yield") or ratio_val("Dividend Yield"),
        "face_value":    ratio_val("Face Value"),
        "book_value":    ratio_val("Book Value"),
        "current_price": ratio_val("Current Price") or ratio_val("CMP"),
        "high_52w":      ratio_val("52 Week High") or ratio_val("High / Low"),
        "low_52w":       ratio_val("52 Week Low"),
        "sales_cr":      None,
        "profit_cr":     None,
        "scraped_date":  datetime.now().strftime("%Y-%m-%d"),
    }

    # Promoter holding from shareholding table
    for tbl in soup.select("table"):
        headers = [th.get_text(strip=True).lower() for th in tbl.select("th")]
        if any("promoter" in h for h in headers):
            rows_t = tbl.select("tr")
            for row in rows_t:
                cells = row.select("td")
                if cells and "promoter" in cells[0].get_text(strip=True).lower():
                    data["promoter_pct"] = clean_num(cells[-1].get_text(strip=True))
                    break

    # Sales and profit from P&L section
    for section in soup.select("section, div.card"):
        h2 = section.select_one("h2, h3")
        if h2 and "profit" in h2.get_text(strip=True).lower():
            for tr in section.select("tr"):
                cells = tr.select("td")
                if not cells:
                    continue
                label = cells[0].get_text(strip=True).lower()
                if "sales" in label or "revenue" in label:
                    data["sales_cr"] = clean_num(cells[-1].get_text(strip=True))
                if "net profit" in label or "profit after" in label:
                    data["profit_cr"] = clean_num(cells[-1].get_text(strip=True))

    return data

# ── Scrape loop ───────────────────────────────────────────────────────────────
ok = 0
err = 0
batch_data = []
t0 = datetime.now()

SQL_UPSERT = (
    "INSERT OR REPLACE INTO screener_fundamentals_v2 "
    "(symbol, pe_ratio, pb_ratio, roce, roe, debt_equity, promoter_pct, "
    "market_cap_cr, sales_cr, profit_cr, eps, div_yield, face_value, "
    "book_value, current_price, high_52w, low_52w, scraped_date) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

for i, sym in enumerate(symbols):
    data = scrape(sym)
    elapsed = (datetime.now() - t0).total_seconds()
    eta = ((len(symbols) - i) / max(i, 1)) * elapsed / 60 if i > 0 else 0

    if data:
        batch_data.append((
            data["symbol"],    data["pe_ratio"],    data["pb_ratio"],
            data["roce"],      data["roe"],          data["debt_equity"],
            data["promoter_pct"], data["market_cap_cr"], data["sales_cr"],
            data["profit_cr"], data["eps"],          data["div_yield"],
            data["face_value"],data["book_value"],   data["current_price"],
            data["high_52w"],  data["low_52w"],      data["scraped_date"],
        ))
        ok += 1
        pe  = f"PE={data['pe_ratio']}" if data["pe_ratio"] else "PE=--"
        roe = f"ROE={data['roe']}"     if data["roe"]      else "ROE=--"
        print(f"  [{i+1:4}/{len(symbols)}] {sym:15} {pe}  {roe}  ETA {eta:.1f}m")
    else:
        err += 1
        print(f"  [{i+1:4}/{len(symbols)}] {sym:15} FAILED  ETA {eta:.1f}m")

    if len(batch_data) >= BATCH:
        conn.executemany(SQL_UPSERT, batch_data)
        conn.commit()
        batch_data = []

    time.sleep(DELAY)

if batch_data:
    conn.executemany(SQL_UPSERT, batch_data)
    conn.commit()

# ── Report ────────────────────────────────────────────────────────────────────
total_in_db = conn.execute("SELECT COUNT(*) FROM screener_fundamentals_v2").fetchone()[0]
sample = conn.execute(
    "SELECT symbol, pe_ratio, roe, roce, promoter_pct, debt_equity "
    "FROM screener_fundamentals_v2 "
    "WHERE pe_ratio IS NOT NULL ORDER BY ROWID DESC LIMIT 5"
).fetchall()

print(f"\nDone.  OK={ok}  Failed={err}  Total in DB={total_in_db}")
print("\nSample (latest 5 with P/E):")
print(f"  {'SYMBOL':15} {'P/E':>8} {'ROE':>8} {'ROCE':>8} {'PROMO%':>8} {'D/E':>8}")
for r in sample:
    def f(v): return f"{v:8.1f}" if v is not None else "      --"
    print(f"  {r[0]:15} {f(r[1])} {f(r[2])} {f(r[3])} {f(r[4])} {f(r[5])}")

conn.close()
print(f"\nRun time: {(datetime.now()-t0).total_seconds()/60:.1f} min")
print("Add to daily pipeline: py D:\\MICC\\data_pipeline\\scrape_fundamentals.py 500")
