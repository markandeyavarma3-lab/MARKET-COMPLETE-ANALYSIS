import sqlite3, time, sys, re
from datetime import datetime

DB = r"D:\marketDB\db\market.db"

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
DELAY   = 2.5
TIMEOUT = 25

conn = sqlite3.connect(DB, timeout=60)
conn.execute("PRAGMA journal_mode=WAL")

def clean(text):
    if text is None: return None
    t = re.sub(r"[,%\u20b9]", "", str(text)).replace("Cr.","").replace("Cr","").strip()
    t = t.replace("+","").replace("(","").replace(")","")
    t = t.split()[0] if t.split() else t
    try:
        v = float(t)
        return None if abs(v) > 1e8 else v
    except: return None

def get_html(url, retries=3):
    for _ in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200: return r.text
            if r.status_code in (404, 403): return None
            time.sleep(3)
        except: time.sleep(3)
    return None

def set_if_none(d, key, val):
    if val is not None and d.get(key) is None:
        d[key] = val

# ── Step 1: PEG from existing data (instant, no scraping) ─────────────────────
print("[1] Computing PEG from PE / profit_growth...")
conn.execute("""
    UPDATE screener_fundamentals_v2
    SET peg_ratio = ROUND(CAST(pe_ratio AS REAL) / CAST(profit_growth AS REAL), 2)
    WHERE peg_ratio IS NULL
      AND pe_ratio IS NOT NULL
      AND profit_growth IS NOT NULL
      AND CAST(profit_growth AS REAL) > 2
      AND CAST(pe_ratio AS REAL) > 0
""")
conn.commit()
peg = conn.execute("SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE peg_ratio IS NOT NULL").fetchone()[0]
print(f"  PEG: {peg} rows filled")

# ── Step 2: ROA from profit_cr / (market_cap_cr proxy) ────────────────────────
# Better: compute from existing fields where possible
# ROA ≈ ROE / (1 + Debt/Equity) -- Du Pont approximation
print("[2] Computing ROA from Du Pont (ROE / (1 + D/E))...")
conn.execute("""
    UPDATE screener_fundamentals_v2
    SET roa = ROUND(
        CAST(roe AS REAL) / (1.0 + CAST(debt_equity AS REAL) / 100.0), 1
    )
    WHERE roa IS NULL
      AND roe IS NOT NULL
      AND debt_equity IS NOT NULL
      AND CAST(debt_equity AS REAL) >= 0
      AND CAST(roe AS REAL) != 0
""")
conn.commit()
roa = conn.execute("SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE roa IS NOT NULL").fetchone()[0]
print(f"  ROA: {roa} rows filled")

# ── Step 3: Scrape P&L + Balance Sheet for remaining fields ───────────────────
symbols = [r[0] for r in conn.execute("""
    SELECT symbol FROM screener_fundamentals_v2
    WHERE pe_ratio IS NOT NULL
      AND (roic IS NULL OR interest_coverage IS NULL OR ebitda_growth IS NULL)
    ORDER BY CAST(market_cap_cr AS REAL) DESC NULLS LAST
    LIMIT 500
""").fetchall()]
print(f"\n[3] Scraping Screener financials for {len(symbols)} stocks...")
print("    Fields: ROIC, interest_coverage, ebitda_growth + verification of all others")

def scrape_all_financials(symbol):
    updates = {}
    html = None
    for url in [
        f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/",
    ]:
        html = get_html(url)
        if html: break
    if not html: return updates

    soup = BeautifulSoup(html, "lxml")

    # ── TOP RATIOS (re-scrape all in case earlier scrape missed some) ──────────
    for li in soup.select("#top-ratios li, ul.company-ratios li"):
        spans = li.select("span")
        if len(spans) < 2: continue
        name = spans[0].get_text(strip=True).lower()
        raw  = spans[-1].get_text(strip=True)
        val  = clean(raw)

        if "roce"              in name: set_if_none(updates, "roce",             val)
        elif name == "roe" or "return on equity" in name: set_if_none(updates, "roe", val)
        elif "current ratio"   in name: set_if_none(updates, "current_ratio",    val)
        elif "quick ratio"     in name: set_if_none(updates, "quick_ratio",      val)
        elif "interest coverage" in name: set_if_none(updates, "interest_coverage", val)
        elif "face value"      in name: set_if_none(updates, "face_value",       val)
        elif "debt to equity"  in name or "debt / equity" in name:
            set_if_none(updates, "debt_equity", val)

    # ── P&L TABLE ─────────────────────────────────────────────────────────────
    ebit_series    = []
    interest_series= []
    ebitda_series  = []
    revenue_series = []
    pat_series     = []
    depreciation   = []

    for section in soup.select("section"):
        h = section.select_one("h2, h3")
        if not h: continue
        ht = h.get_text(strip=True).lower()
        if "profit" not in ht and "loss" not in ht: continue

        for tr in section.select("tr"):
            cells = [c.get_text(strip=True) for c in tr.select("td")]
            if len(cells) < 3: continue
            label = cells[0].lower().strip()
            # All year values (skip label column)
            vals = []
            for c in cells[1:]:
                v = clean(c)
                if v is not None: vals.append(v)

            if not vals: continue

            if ("sales" in label or "revenue" in label) and "growth" not in label:
                revenue_series = vals
            elif "net profit" in label or "profit after tax" in label or "pat" == label:
                pat_series = vals
            elif label in ("ebit", "operating profit") or "operating profit" in label:
                ebit_series = vals
            elif "interest" in label and ("expense" in label or "cost" in label or "paid" in label):
                interest_series = vals
            elif "finance cost" in label or "financing cost" in label:
                interest_series = vals
            elif "ebitda" in label:
                ebitda_series = vals
            elif "depreciation" in label or "amortization" in label:
                depreciation = vals

    # Compute interest coverage = EBIT / Interest (latest year)
    if ebit_series and interest_series:
        e = ebit_series[-1]
        i = interest_series[-1]
        if e and i and i > 0:
            ic = round(e / i, 2)
            if 0 < ic < 5000:
                set_if_none(updates, "interest_coverage", ic)

    # EBITDA = EBIT + Depreciation (if EBITDA not directly available)
    if not ebitda_series and ebit_series and depreciation:
        ebitda_series = [
            (e + d) if e and d else None
            for e, d in zip(ebit_series, depreciation)
        ]
        ebitda_series = [v for v in ebitda_series if v is not None]

    # EBITDA growth (latest vs previous year)
    if len(ebitda_series) >= 2:
        curr = ebitda_series[-1]
        prev = ebitda_series[-2]
        if curr and prev and prev != 0:
            g = round((curr - prev) / abs(prev) * 100, 1)
            if -500 < g < 2000:
                set_if_none(updates, "ebitda_growth", g)

    # Revenue growth (cross-verify)
    if len(revenue_series) >= 2:
        curr = revenue_series[-1]
        prev = revenue_series[-2]
        if curr and prev and prev != 0:
            g = round((curr - prev) / abs(prev) * 100, 1)
            if -200 < g < 2000:
                set_if_none(updates, "revenue_growth", g)

    # Profit growth (cross-verify)
    if len(pat_series) >= 2:
        curr = pat_series[-1]
        prev = pat_series[-2]
        if curr and prev and prev != 0:
            g = round((curr - prev) / abs(prev) * 100, 1)
            if -500 < g < 5000:
                set_if_none(updates, "profit_growth", g)

    # ── BALANCE SHEET ─────────────────────────────────────────────────────────
    total_assets  = None
    total_equity  = None
    total_debt    = None
    current_liab  = None
    current_assets= None
    inventory     = None
    cash          = None

    for section in soup.select("section"):
        h = section.select_one("h2, h3")
        if not h or "balance" not in h.get_text(strip=True).lower(): continue

        for tr in section.select("tr"):
            cells = [c.get_text(strip=True) for c in tr.select("td")]
            if len(cells) < 2: continue
            label = cells[0].lower().strip()
            vals  = [clean(c) for c in cells[1:] if clean(c) is not None]
            if not vals: continue
            v = vals[-1]  # most recent year

            if "total asset"   in label:                 total_assets  = v
            elif "total equity" in label or "shareholders" in label: total_equity  = v
            elif "total borrowing" in label or ("total debt" in label and "equity" not in label):
                total_debt = v
            elif "current liabilit" in label:            current_liab  = v
            elif "current asset"    in label:            current_assets= v
            elif "inventor"         in label:            inventory     = v
            elif "cash" in label and "equivalent" in label: cash       = v

    # ROIC = NOPAT / Invested Capital
    # NOPAT = EBIT * (1 - 0.25)
    # Invested Capital = Total Equity + Total Debt
    if ebit_series:
        nopat = ebit_series[-1] * 0.75 if ebit_series[-1] else None
        invested = (total_equity or 0) + (total_debt or 0)
        if nopat and invested > 0:
            roic = round(nopat / invested * 100, 1)
            if 0 < roic < 500:
                set_if_none(updates, "roic", roic)

    # Current ratio from balance sheet (cross-verify)
    if current_assets and current_liab and current_liab > 0:
        cr = round(current_assets / current_liab, 2)
        if 0 < cr < 50:
            set_if_none(updates, "current_ratio", cr)

    # Quick ratio = (Current Assets - Inventory) / Current Liabilities
    if current_assets and current_liab and current_liab > 0 and inventory is not None:
        qr = round((current_assets - inventory) / current_liab, 2)
        if 0 < qr < 50:
            set_if_none(updates, "quick_ratio", qr)

    # Cash (cross-verify)
    if cash:
        set_if_none(updates, "cash_cr", cash)

    # ROA = PAT / Total Assets
    if pat_series and total_assets and total_assets > 0:
        roa = round(pat_series[-1] / total_assets * 100, 1)
        if -100 < roa < 200:
            set_if_none(updates, "roa", roa)

    return updates

# ── Main loop ─────────────────────────────────────────────────────────────────
patched = 0
t0 = datetime.now()

for i, sym in enumerate(symbols):
    elapsed = (datetime.now()-t0).total_seconds()
    eta = ((len(symbols)-i)/max(i,1))*elapsed/60 if i > 0 else 0

    updates = scrape_all_financials(sym)

    if updates:
        set_parts = ", ".join(f"{k}=?" for k in updates)
        conn.execute(
            f"UPDATE screener_fundamentals_v2 SET {set_parts} WHERE symbol=?",
            list(updates.values()) + [sym]
        )
        conn.commit()
        patched += 1
        # Show all filled fields
        filled = [f"{k}={v}" for k,v in updates.items()]
        fields_str = "  ".join(filled[:6])  # show first 6
        extra = f"  +{len(filled)-6} more" if len(filled) > 6 else ""
        print(f"  [{i+1:4}/{len(symbols)}] {sym:15} {len(updates):2} fields: {fields_str}{extra}  ETA {eta:.1f}m")
    else:
        print(f"  [{i+1:4}/{len(symbols)}] {sym:15} --  ETA {eta:.1f}m")

    time.sleep(DELAY)

# ── Final coverage ─────────────────────────────────────────────────────────────
print(f"\n[4] Final coverage ({patched}/{len(symbols)} stocks updated):")
total = conn.execute("SELECT COUNT(*) FROM screener_fundamentals_v2").fetchone()[0]
fields = [
    "pe_ratio","pb_ratio","roce","roe","roa","roic",
    "debt_equity","current_ratio","quick_ratio","interest_coverage",
    "promoter_pct","fii_pct","market_cap_cr","revenue_growth",
    "profit_growth","ebitda_growth","peg_ratio","beta",
    "div_yield","cash_cr","ebitda_cr","enterprise_value_cr",
]
for col in fields:
    c = conn.execute(
        f"SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE {col} IS NOT NULL"
    ).fetchone()[0]
    pct = int(c/max(total,1)*100)
    bar = "#"*(pct//5) + "-"*(20-pct//5)
    print(f"  {col:25} [{bar}] {pct:3}%  ({c}/{total})")

conn.close()
print(f"\nTotal time: {(datetime.now()-t0).total_seconds()/60:.1f} min")
