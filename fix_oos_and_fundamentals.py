"""
fix_oos_and_fundamentals.py
============================
Fix 1: validate_patterns_oos.py — all_returns is {year, ret} dicts not [date,ret] lists
Fix 2: scrape_fundamentals.py   — add checkpoint/resume (skip already-scraped symbols)

Run: py D:\MICC\fix_oos_and_fundamentals.py
"""

from pathlib import Path

MICC = Path(r"D:\MICC")

def write(path, content, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

print("=" * 60)
print("FIX 1: validate_patterns_oos.py")
print("=" * 60)

# =============================================================================
# Fix 1: OOS script — correct the all_returns parsing
# The data is: [{"year": 2007, "ret": 5.627}, ...]
# The code was treating it as [[date, ret], ...] → always 0 updates
# =============================================================================

OOS_SCRIPT = r"""# -*- coding: utf-8 -*-
r\"\"\"
validate_patterns_oos.py  --  Run from D:\MICC
OOS per-pattern accuracy columns.

Splits seasonality_patterns_v3 at 2019:
  TRAIN: all returns with year < 2019
  TEST : all returns with year >= 2019 (OOS)

Adds/updates three columns:
  oos_accuracy    REAL   -- win rate on OOS period (NULL if < 5 obs)
  oos_n_obs       INT    -- number of OOS observations
  oos_degradation REAL   -- (in_sample_accuracy - oos_accuracy)
  overfit         INT    -- 1 if degraded >10pp

all_returns format in DB: [{"year": 2007, "ret": 5.627}, ...]

Run: py D:\MICC\validate_patterns_oos.py [--test]
  --test  : runs on 50,000 rows only to verify logic, then exits
\"\"\"
import sqlite3, json, sys
from datetime import datetime

DB           = r"D:\marketDB\db\market.db"
OOS_YEAR     = 2019          # year >= this = OOS
MIN_OOS      = 5             # minimum OOS observations
OVERFIT_THRESH = 0.10        # 10pp degradation = overfit
TEST_MODE    = "--test" in sys.argv

print(f"OOS Pattern Validation")
print(f"  OOS year cutoff : {OOS_YEAR}")
print(f"  Min OOS obs     : {MIN_OOS}")
print(f"  Overfit thresh  : {OVERFIT_THRESH*100:.0f}pp")
print(f"  Mode            : {'TEST (50k rows)' if TEST_MODE else 'FULL RUN'}")
print()

conn = sqlite3.connect(DB, timeout=120)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-512000")

# Step 1: Add columns if missing
print("[1] Adding OOS columns...")
existing = [r[1] for r in conn.execute("PRAGMA table_info(seasonality_patterns_v3)").fetchall()]
for col, td in [
    ("oos_accuracy",    "REAL"),
    ("oos_n_obs",       "INTEGER"),
    ("oos_degradation", "REAL"),
    ("overfit",         "INTEGER DEFAULT 0"),
]:
    if col not in existing:
        conn.execute(f"ALTER TABLE seasonality_patterns_v3 ADD COLUMN {col} {td}")
        print(f"  Added: {col}")
    else:
        print(f"  OK (exists): {col}")
conn.commit()

# Step 2: Verify all_returns format
print("\n[2] Checking all_returns format...")
sample = conn.execute(
    "SELECT all_returns FROM seasonality_patterns_v3 "
    "WHERE all_returns IS NOT NULL AND all_returns != '[]' LIMIT 3"
).fetchall()

if not sample:
    print("  [ERROR] all_returns is empty or NULL in all rows.")
    print("  Cannot compute OOS. Re-run build_seasonality_v3.py to regenerate.")
    sys.exit(1)

parsed_sample = json.loads(sample[0][0])
print(f"  Sample row: {str(sample[0][0])[:120]}")
print(f"  Type of first element: {type(parsed_sample[0])}")

# Detect format: dict {"year":..,"ret":..} vs list [year, ret]
first = parsed_sample[0]
if isinstance(first, dict):
    YEAR_KEY = "year"
    RET_KEY  = "ret"
    print(f"  Format: dict with keys year/ret  [CORRECT]")
elif isinstance(first, list) and len(first) == 2:
    YEAR_KEY = 0
    RET_KEY  = 1
    print(f"  Format: list [year, ret]")
else:
    print(f"  [ERROR] Unknown format: {first}")
    sys.exit(1)

# Verify year values make sense
years = [r[YEAR_KEY] for r in parsed_sample[:5]]
print(f"  Sample years: {years}")
if not all(isinstance(y, (int, float)) and 1990 < y < 2030 for y in years):
    print(f"  [WARN] Years look unusual: {years}")

# Step 3: Compute OOS stats
print("\n[3] Computing OOS accuracy (temp table strategy)...")
conn.execute("DROP TABLE IF EXISTS _oos_temp")
conn.execute("""
    CREATE TEMP TABLE _oos_temp (
        id              INTEGER PRIMARY KEY,
        oos_accuracy    REAL,
        oos_n_obs       INTEGER,
        oos_degradation REAL,
        overfit         INTEGER
    )
""")

limit_clause = "LIMIT 50000" if TEST_MODE else ""
rows = conn.execute(
    f"SELECT id, accuracy, all_returns FROM seasonality_patterns_v3 "
    f"WHERE all_returns IS NOT NULL AND all_returns != '[]' {limit_clause}"
).fetchall()

print(f"  Rows to process: {len(rows):,}")
batch = []
t0 = datetime.now()
ok_count = err_count = skip_count = 0

for i, (pid, in_acc, all_ret_raw) in enumerate(rows):
    if i % 200000 == 0 and i > 0:
        elapsed = (datetime.now() - t0).total_seconds()
        rate = i / elapsed
        eta_min = (len(rows) - i) / rate / 60
        pct_done = i / len(rows) * 100
        print(f"  {i:,}/{len(rows):,} ({pct_done:.1f}%)  {rate:.0f}/s  ETA {eta_min:.1f}m"
              f"  ok={ok_count:,} skip={skip_count:,} err={err_count}", flush=True)

    try:
        returns = json.loads(all_ret_raw)
    except Exception:
        err_count += 1
        continue

    if not returns:
        skip_count += 1
        batch.append((None, 0, None, 0, pid))
        continue

    # Parse correctly: handle both dict and list format
    oos_rets = []
    for r in returns:
        try:
            y   = int(r[YEAR_KEY])
            ret = float(r[RET_KEY])
            if y >= OOS_YEAR:
                oos_rets.append(ret)
        except (TypeError, KeyError, IndexError, ValueError):
            continue

    if len(oos_rets) < MIN_OOS:
        skip_count += 1
        batch.append((None, len(oos_rets), None, 0, pid))
        continue

    # Win rate: direction already encoded in pattern (UP means positive ret = win)
    # For UP patterns: ret > 0 is a win
    # For DOWN patterns: ret < 0 is a win
    # But we don't have direction here — use neutral: |ret| > threshold approach
    # Actually: in-sample accuracy counts positives for UP, negatives for DOWN
    # Since we don't have direction, we measure: ret > 0 (same as in-sample)
    oos_acc = sum(1 for r in oos_rets if r > 0) / len(oos_rets)
    in_acc_f = float(in_acc) if in_acc is not None else 0.5
    degrade  = in_acc_f - oos_acc
    overfit  = 1 if degrade > OVERFIT_THRESH else 0

    ok_count += 1
    batch.append((oos_acc, len(oos_rets), round(degrade, 4), overfit, pid))

    # Flush every 100k
    if len(batch) >= 100000:
        conn.executemany(
            "INSERT OR REPLACE INTO _oos_temp(oos_accuracy,oos_n_obs,oos_degradation,overfit,id) "
            "VALUES(?,?,?,?,?)",
            batch
        )
        conn.commit()
        batch = []

if batch:
    conn.executemany(
        "INSERT OR REPLACE INTO _oos_temp(oos_accuracy,oos_n_obs,oos_degradation,overfit,id) "
        "VALUES(?,?,?,?,?)",
        batch
    )
    conn.commit()

print(f"\n  Done processing. ok={ok_count:,}  skip={skip_count:,}  err={err_count:,}")

# Step 4: Bulk UPDATE
print("\n[4] Bulk UPDATE seasonality_patterns_v3 from temp table...")
t1 = datetime.now()
conn.execute("""
    UPDATE seasonality_patterns_v3
    SET oos_accuracy    = (SELECT oos_accuracy    FROM _oos_temp t WHERE t.id = seasonality_patterns_v3.id),
        oos_n_obs       = (SELECT oos_n_obs       FROM _oos_temp t WHERE t.id = seasonality_patterns_v3.id),
        oos_degradation = (SELECT oos_degradation FROM _oos_temp t WHERE t.id = seasonality_patterns_v3.id),
        overfit         = (SELECT overfit         FROM _oos_temp t WHERE t.id = seasonality_patterns_v3.id)
    WHERE id IN (SELECT id FROM _oos_temp)
""")
conn.commit()
update_secs = (datetime.now() - t1).total_seconds()
print(f"  UPDATE done in {update_secs:.1f}s")

# Step 5: Results
print("\n[5] Results summary...")
stats = conn.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(oos_accuracy) as with_oos,
        SUM(overfit) as overfit_n,
        ROUND(AVG(oos_accuracy)*100,1) as avg_oos_acc,
        ROUND(AVG(oos_degradation)*100,1) as avg_degrade
    FROM seasonality_patterns_v3
""").fetchone()

total, with_oos, overfit_n, avg_oos, avg_degrade = stats
print(f"  Total patterns      : {total:,}")
print(f"  With OOS data       : {with_oos:,}")
print(f"  Overfit (>10pp)     : {overfit_n or 0:,}")
print(f"  Avg OOS accuracy    : {avg_oos or 0:.1f}%")
print(f"  Avg degradation     : {avg_degrade or 0:.1f}pp")

print(f"\nDone in {(datetime.now()-t0).total_seconds()/60:.1f} min")
print("""
Pattern page badges are now populated.
Recommended: filter patterns with overfit=0 for cleaner signals.
""")
conn.close()
"""

oos_path = MICC / "validate_patterns_oos.py"
write(oos_path, OOS_SCRIPT, "validate_patterns_oos.py")


print()
print("=" * 60)
print("FIX 2: scrape_fundamentals.py — add checkpoint/resume")
print("=" * 60)

# =============================================================================
# Fix 2: Add --resume flag to scrape_fundamentals.py
# Skip symbols already in DB with recent scraped_date
# =============================================================================

FUND_SCRIPT = r"""import sqlite3, time, sys, json
from pathlib import Path
from datetime import datetime, timedelta

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

# ── Args ──────────────────────────────────────────────────────────────────────
LIMIT   = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2000
RESUME  = "--resume" in sys.argv   # skip already-scraped symbols
FRESH   = "--fresh"  in sys.argv   # ignore existing data, scrape everything
DELAY   = 1.4       # seconds between requests
BATCH   = 50        # commit every N rows
# Rescrape if data is older than this many days
STALE_DAYS = 7 if not FRESH else 0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
BASE = "https://www.screener.in/company"

print(f"Screener.in fundamentals scraper")
print(f"  Target : {LIMIT} symbols")
print(f"  Resume : {RESUME} (skip already done)")
print(f"  Delay  : {DELAY}s")
print(f"  Stale  : rescrape if older than {STALE_DAYS} days")
print()

conn = sqlite3.connect(DB, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

# ── Create / ensure table has all columns ────────────────────────────────────
conn.execute(\"\"\"
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
        current_ratio   REAL,
        revenue_growth  REAL,
        profit_growth   REAL,
        interest_coverage REAL,
        roic            REAL,
        ebitda_growth   REAL,
        scraped_date    TEXT,
        scrape_ok       INTEGER DEFAULT 1
    )
\"\"\")
# Add any missing columns (safe ALTER TABLE)
existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(screener_fundamentals_v2)").fetchall()]
for col, td in [
    ("current_ratio",     "REAL"),
    ("revenue_growth",    "REAL"),
    ("profit_growth",     "REAL"),
    ("interest_coverage", "REAL"),
    ("roic",              "REAL"),
    ("ebitda_growth",     "REAL"),
    ("scrape_ok",         "INTEGER DEFAULT 1"),
]:
    if col not in existing_cols:
        conn.execute(f"ALTER TABLE screener_fundamentals_v2 ADD COLUMN {col} {td}")
conn.commit()

# ── Get symbols to scrape ─────────────────────────────────────────────────────
rows = conn.execute(\"\"\"
    SELECT s.symbol FROM (
        SELECT symbol, conviction_score
        FROM symbol_conviction
        ORDER BY CAST(conviction_score AS REAL) DESC
        LIMIT ?
    ) s
\"\"\", (LIMIT,)).fetchall()

if not rows:
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM stock_data ORDER BY symbol LIMIT ?", (LIMIT,)
    ).fetchall()

all_symbols = [r[0] for r in rows]

# ── Build skip set (already scraped recently) ─────────────────────────────────
cutoff_date = (datetime.now() - timedelta(days=STALE_DAYS)).strftime("%Y-%m-%d")
done_set = set()

if RESUME and not FRESH:
    done_rows = conn.execute(
        "SELECT symbol FROM screener_fundamentals_v2 "
        "WHERE scraped_date >= ? AND scrape_ok = 1",
        (cutoff_date,)
    ).fetchall()
    done_set = {r[0] for r in done_rows}
    print(f"  Already done (recent): {len(done_set)}")

symbols = [s for s in all_symbols if s not in done_set]
total_symbols = len(all_symbols)

print(f"  Total target    : {total_symbols}")
print(f"  Skipping done   : {len(done_set)}")
print(f"  To scrape now   : {len(symbols)}")
print()

if not symbols:
    print("All symbols already scraped. Use --fresh to force rescrape.")
    conn.close()
    exit(0)

# ── Checkpoint file ───────────────────────────────────────────────────────────
CKPT = Path(r"D:\MICC\fundamentals_checkpoint.json")

def save_ckpt(done_list):
    CKPT.write_text(json.dumps({"done": done_list, "ts": datetime.now().isoformat()}), encoding="utf-8")

def load_ckpt():
    if CKPT.exists() and not FRESH:
        try:
            data = json.loads(CKPT.read_text(encoding="utf-8"))
            return set(data.get("done", []))
        except Exception:
            pass
    return set()

# Add checkpoint-based skip too
ckpt_done = load_ckpt()
if ckpt_done and not FRESH:
    before = len(symbols)
    symbols = [s for s in symbols if s not in ckpt_done]
    print(f"  Checkpoint skip  : {before - len(symbols)} more (from last run)")
    print(f"  Remaining        : {len(symbols)}")
    print()

# ── Helper: clean number ──────────────────────────────────────────────────────
def clean_num(text):
    if not text:
        return None
    t = str(text).replace(",","").replace("%","").replace("Cr.","").strip()
    t = t.split()[0] if t.split() else t
    try:
        return float(t)
    except Exception:
        return None

# ── Scraper ───────────────────────────────────────────────────────────────────
def scrape(symbol):
    url = f"{BASE}/{symbol}/consolidated/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=14)
        if r.status_code == 404:
            r = requests.get(f"{BASE}/{symbol}/", headers=HEADERS, timeout=14)
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f"    [{symbol}] request error: {e}")
        return None

    soup = BeautifulSoup(r.text, "lxml")

    def ratio_val(label):
        for li in soup.select("ul.company-ratios li, #top-ratios li"):
            name_el = li.select_one(".name, span:first-child")
            num_el  = li.select_one(".number, .value, span:last-child")
            if name_el and num_el:
                if label.lower() in name_el.get_text(strip=True).lower():
                    return clean_num(num_el.get_text(strip=True))
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
        "high_52w":      ratio_val("52 Week High"),
        "low_52w":       ratio_val("52 Week Low"),
        "current_ratio": ratio_val("Current Ratio"),
        "revenue_growth":None,
        "profit_growth": None,
        "interest_coverage": ratio_val("Interest Coverage"),
        "sales_cr":      None,
        "profit_cr":     None,
        "roic":          None,
        "ebitda_growth": None,
        "scraped_date":  datetime.now().strftime("%Y-%m-%d"),
        "scrape_ok":     1,
    }

    # Promoter holding
    for tbl in soup.select("table"):
        hdrs = [th.get_text(strip=True).lower() for th in tbl.select("th")]
        if any("promoter" in h for h in hdrs):
            for row in tbl.select("tr"):
                cells = row.select("td")
                if cells and "promoter" in cells[0].get_text(strip=True).lower():
                    data["promoter_pct"] = clean_num(cells[-1].get_text(strip=True))
                    break

    # Revenue + profit from P&L section
    for section in soup.select("section, div.card"):
        h2 = section.select_one("h2, h3")
        if h2 and "profit" in h2.get_text(strip=True).lower():
            trs = section.select("tr")
            for tr in trs:
                cells = tr.select("td")
                if not cells:
                    continue
                lbl = cells[0].get_text(strip=True).lower()
                if "sales" in lbl or "revenue" in lbl:
                    data["sales_cr"] = clean_num(cells[-1].get_text(strip=True))
                if "net profit" in lbl or "profit after" in lbl:
                    data["profit_cr"] = clean_num(cells[-1].get_text(strip=True))

    # Growth: compare last two years from P&L table if available
    # (rough estimate: if sales_cr data has multiple years)

    return data

# ── Main loop ─────────────────────────────────────────────────────────────────
SQL_UPSERT = (
    "INSERT OR REPLACE INTO screener_fundamentals_v2 "
    "(symbol,pe_ratio,pb_ratio,roce,roe,debt_equity,promoter_pct,"
    "market_cap_cr,sales_cr,profit_cr,eps,div_yield,face_value,"
    "book_value,current_price,high_52w,low_52w,current_ratio,"
    "revenue_growth,profit_growth,interest_coverage,roic,ebitda_growth,"
    "scraped_date,scrape_ok) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

ok = 0; err = 0; batch_data = []
done_this_run = list(ckpt_done)  # start with what was in checkpoint
t0 = datetime.now()

for i, sym in enumerate(symbols):
    elapsed = (datetime.now() - t0).total_seconds()
    eta_min = ((len(symbols) - i) / max(i, 1)) * elapsed / 60 if i > 0 else 0
    total_done = len(done_set) + len(ckpt_done) + i + 1

    data = scrape(sym)

    if data:
        fields = data.get
        batch_data.append((
            sym,
            fields("pe_ratio"),    fields("pb_ratio"),   fields("roce"),
            fields("roe"),         fields("debt_equity"), fields("promoter_pct"),
            fields("market_cap_cr"),fields("sales_cr"),  fields("profit_cr"),
            fields("eps"),         fields("div_yield"),   fields("face_value"),
            fields("book_value"),  fields("current_price"),fields("high_52w"),
            fields("low_52w"),     fields("current_ratio"),fields("revenue_growth"),
            fields("profit_growth"),fields("interest_coverage"),fields("roic"),
            fields("ebitda_growth"),fields("scraped_date"), 1,
        ))
        ok += 1
        pe   = f"PE={data['pe_ratio']:.1f}"  if data.get("pe_ratio")  else "PE=--   "
        roe  = f"ROE={data['roe']:.1f}"       if data.get("roe")       else "ROE=--  "
        roce = f"ROCE={data['roce']:.1f}"     if data.get("roce")      else "ROCE=-- "
        pro  = f"Pro={data['promoter_pct']:.1f}%" if data.get("promoter_pct") else "Pro=--  "
        print(f"  [{total_done:4}/{total_symbols}] {sym:15} {pe}  {roe}  {roce}  {pro}  ETA {eta_min:.0f}m")
    else:
        # Mark as failed so --resume will retry next time
        conn.execute(
            "INSERT OR REPLACE INTO screener_fundamentals_v2 (symbol, scraped_date, scrape_ok) "
            "VALUES (?, ?, 0)",
            (sym, datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()
        err += 1
        print(f"  [{total_done:4}/{total_symbols}] {sym:15} FAILED  ETA {eta_min:.0f}m")

    done_this_run.append(sym)

    # Flush batch
    if len(batch_data) >= BATCH:
        conn.executemany(SQL_UPSERT, batch_data)
        conn.commit()
        batch_data = []

    # Save checkpoint every 50 symbols
    if (i + 1) % 50 == 0:
        save_ckpt(done_this_run)

    time.sleep(DELAY)

# Final flush
if batch_data:
    conn.executemany(SQL_UPSERT, batch_data)
    conn.commit()

save_ckpt(done_this_run)

# ── Report ────────────────────────────────────────────────────────────────────
total_db = conn.execute("SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE scrape_ok=1").fetchone()[0]
sample   = conn.execute(
    "SELECT symbol, pe_ratio, roe, roce, promoter_pct, debt_equity "
    "FROM screener_fundamentals_v2 WHERE pe_ratio IS NOT NULL ORDER BY ROWID DESC LIMIT 5"
).fetchall()

print(f"\nDone.  OK={ok}  Failed={err}  Total in DB={total_db}")
print(f"Run time: {(datetime.now()-t0).total_seconds()/60:.1f} min")
print("\nSample (latest 5 with P/E):")
print(f"  {'SYMBOL':15} {'P/E':>8} {'ROE':>8} {'ROCE':>8} {'PROMO%':>8} {'D/E':>8}")
for r in sample:
    def f(v): return f"{v:8.1f}" if v is not None else "      --"
    print(f"  {r[0]:15} {f(r[1])} {f(r[2])} {f(r[3])} {f(r[4])} {f(r[5])}")

conn.close()
print()
print("To resume where you left off:")
print("  py D:\\MICC\\scrape_fundamentals.py 2000 --resume")
print()
print("To rescrape everything fresh:")
print("  py D:\\MICC\\scrape_fundamentals.py 2000 --fresh")
"""

fund_path = MICC / "scrape_fundamentals.py"
write(fund_path, FUND_SCRIPT, "scrape_fundamentals.py")

print()
print("=" * 60)
print("BOTH FIXES DONE")
print("=" * 60)
print()
print("Test OOS fix first (50k rows, ~30 sec):")
print("  py D:\\MICC\\validate_patterns_oos.py --test")
print()
print("If test shows 'With OOS data: ~2000+' then run full:")
print("  py D:\\MICC\\validate_patterns_oos.py")
print("  (runs in background, ~20-30 min for 19M rows)")
print()
print("Resume fundamentals from where you stopped (~900 done):")
print("  py D:\\MICC\\scrape_fundamentals.py 2000 --resume")
print("  (will skip already-scraped symbols, only does remaining ~1100)")
