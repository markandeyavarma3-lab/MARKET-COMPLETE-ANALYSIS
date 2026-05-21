import sqlite3, time, sys, json
from pathlib import Path
from datetime import datetime, timedelta

DB = r'D:\marketDB\db\market.db'

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'requests', 'beautifulsoup4', 'lxml',
                    '--break-system-packages', '-q'])
    import requests
    from bs4 import BeautifulSoup

LIMIT      = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2000
RESUME     = '--resume' in sys.argv
FRESH      = '--fresh'  in sys.argv
DELAY      = 1.5
BATCH      = 30
STALE_DAYS = 7
CKPT       = Path(r'D:\MICC\fundamentals_checkpoint.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
    'Accept-Language': 'en-US,en;q=0.9',
}
BASE = 'https://www.screener.in/company'

print(f'Screener.in fundamentals scraper')
print(f'  Target : {LIMIT}   Resume: {RESUME}   Fresh: {FRESH}')

# ---- DB write helper with retry on locked ----
def db_write(conn, sql, params_list, retries=8, wait=3.0):
    for attempt in range(retries):
        try:
            conn.executemany(sql, params_list)
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower():
                print(f'  [DB LOCKED] attempt {attempt+1}/{retries}, waiting {wait}s...')
                time.sleep(wait)
                wait = min(wait * 1.5, 30.0)
            else:
                raise
    print('  [ERROR] DB still locked after all retries, skipping batch')
    return False

def db_single(conn, sql, params=(), retries=8, wait=3.0):
    for attempt in range(retries):
        try:
            conn.execute(sql, params)
            conn.commit()
            return True
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower():
                print(f'  [DB LOCKED] attempt {attempt+1}/{retries}, waiting {wait}s...')
                time.sleep(wait)
                wait = min(wait * 1.5, 30.0)
            else:
                raise
    return False

conn = sqlite3.connect(DB, timeout=60)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=30000')

# ---- Create / update table ----
conn.execute(
    'CREATE TABLE IF NOT EXISTS screener_fundamentals_v2 ('
    '  symbol TEXT PRIMARY KEY, pe_ratio REAL, pb_ratio REAL,'
    '  roce REAL, roe REAL, debt_equity REAL, promoter_pct REAL,'
    '  market_cap_cr REAL, sales_cr REAL, profit_cr REAL,'
    '  eps REAL, div_yield REAL, face_value REAL, book_value REAL,'
    '  current_price REAL, high_52w REAL, low_52w REAL,'
    '  current_ratio REAL, revenue_growth REAL, profit_growth REAL,'
    '  interest_coverage REAL, roic REAL, ebitda_growth REAL,'
    '  scraped_date TEXT, scrape_ok INTEGER DEFAULT 1'
    ')'
)
for col, td in [
    ('current_ratio','REAL'), ('revenue_growth','REAL'), ('profit_growth','REAL'),
    ('interest_coverage','REAL'), ('roic','REAL'), ('ebitda_growth','REAL'),
    ('scrape_ok','INTEGER DEFAULT 1'),
]:
    existing = [r[1] for r in conn.execute('PRAGMA table_info(screener_fundamentals_v2)').fetchall()]
    if col not in existing:
        conn.execute(f'ALTER TABLE screener_fundamentals_v2 ADD COLUMN {col} {td}')
conn.commit()

# ---- Build symbol list ----
all_rows = conn.execute(
    'SELECT s.symbol FROM (SELECT symbol FROM symbol_conviction'
    ' ORDER BY CAST(conviction_score AS REAL) DESC LIMIT ?) s',
    (LIMIT,)
).fetchall()
if not all_rows:
    all_rows = conn.execute('SELECT DISTINCT symbol FROM stock_data ORDER BY symbol LIMIT ?', (LIMIT,)).fetchall()
all_symbols = [r[0] for r in all_rows]

# ---- Build skip set ----
cutoff = (datetime.now() - timedelta(days=STALE_DAYS)).strftime('%Y-%m-%d')
done_set = set()
if RESUME and not FRESH:
    done_rows = conn.execute(
        'SELECT symbol FROM screener_fundamentals_v2 WHERE scraped_date >= ? AND scrape_ok = 1',
        (cutoff,)
    ).fetchall()
    done_set = {r[0] for r in done_rows}

# ---- Checkpoint skip ----
ckpt_done = set()
if CKPT.exists() and not FRESH:
    try:
        ckpt_done = set(json.loads(CKPT.read_text())['done'])
    except Exception:
        pass

symbols = [s for s in all_symbols if s not in done_set and s not in ckpt_done]
print(f'  Total: {len(all_symbols)}  Done in DB: {len(done_set)}  Ckpt done: {len(ckpt_done)}  To scrape: {len(symbols)}')
print()

if not symbols:
    print('All symbols already scraped. Use --fresh to force rescrape.')
    conn.close()
    sys.exit(0)

# ---- Helpers ----
def clean_num(text):
    if not text: return None
    t = str(text).replace(',','').replace('%','').replace('Cr.','').strip()
    t = t.split()[0] if t.split() else t
    try: return float(t)
    except: return None

def scrape(symbol):
    url = f'{BASE}/{symbol}/consolidated/'
    try:
        r = requests.get(url, headers=HEADERS, timeout=14)
        if r.status_code == 404:
            r = requests.get(f'{BASE}/{symbol}/', headers=HEADERS, timeout=14)
        if r.status_code != 200:
            return None
    except Exception as e:
        print(f'    [{symbol}] err: {e}')
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    def rv(label):
        for li in soup.select('ul.company-ratios li, #top-ratios li'):
            n = li.select_one('.name, span:first-child')
            v = li.select_one('.number, .value, span:last-child')
            if n and v and label.lower() in n.get_text(strip=True).lower():
                return clean_num(v.get_text(strip=True))
        return None
    d = {
        'symbol': symbol,
        'pe_ratio':      rv('P/E'),
        'pb_ratio':      rv('P/B'),
        'roce':          rv('ROCE'),
        'roe':           rv('ROE'),
        'debt_equity':   rv('Debt / Equity') or rv('Debt/Equity'),
        'promoter_pct':  None,
        'market_cap_cr': rv('Market Cap'),
        'eps':           rv('EPS'),
        'div_yield':     rv('Div Yield') or rv('Dividend Yield'),
        'face_value':    rv('Face Value'),
        'book_value':    rv('Book Value'),
        'current_price': rv('Current Price') or rv('CMP'),
        'high_52w':      rv('52 Week High'),
        'low_52w':       rv('52 Week Low'),
        'current_ratio': rv('Current Ratio'),
        'interest_coverage': rv('Interest Coverage'),
        'sales_cr':      None, 'profit_cr': None,
        'revenue_growth': None, 'profit_growth': None,
        'roic': None, 'ebitda_growth': None,
        'scraped_date':  datetime.now().strftime('%Y-%m-%d'),
    }
    for tbl in soup.select('table'):
        hdrs = [th.get_text(strip=True).lower() for th in tbl.select('th')]
        if any('promoter' in h for h in hdrs):
            for row in tbl.select('tr'):
                cells = row.select('td')
                if cells and 'promoter' in cells[0].get_text(strip=True).lower():
                    d['promoter_pct'] = clean_num(cells[-1].get_text(strip=True))
                    break
    for section in soup.select('section, div.card'):
        h2 = section.select_one('h2, h3')
        if h2 and 'profit' in h2.get_text(strip=True).lower():
            for tr in section.select('tr'):
                cells = tr.select('td')
                if not cells: continue
                lbl = cells[0].get_text(strip=True).lower()
                if 'sales' in lbl or 'revenue' in lbl:
                    d['sales_cr'] = clean_num(cells[-1].get_text(strip=True))
                if 'net profit' in lbl or 'profit after' in lbl:
                    d['profit_cr'] = clean_num(cells[-1].get_text(strip=True))
    return d

SQL = (
    'INSERT OR REPLACE INTO screener_fundamentals_v2'
    ' (symbol,pe_ratio,pb_ratio,roce,roe,debt_equity,promoter_pct,'
    '  market_cap_cr,sales_cr,profit_cr,eps,div_yield,face_value,'
    '  book_value,current_price,high_52w,low_52w,current_ratio,'
    '  revenue_growth,profit_growth,interest_coverage,roic,ebitda_growth,'
    '  scraped_date,scrape_ok)'
    ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
)

ok = 0; err = 0; batch_data = []
done_this_run = []
t0 = datetime.now()
total = len(all_symbols)

for i, sym in enumerate(symbols):
    elapsed = (datetime.now() - t0).total_seconds()
    eta = ((len(symbols) - i) / max(i, 1)) * elapsed / 60 if i > 0 else 0
    done_total = len(done_set) + len(ckpt_done) + i + 1

    data = scrape(sym)
    if data:
        g = data.get
        batch_data.append((
            sym, g('pe_ratio'), g('pb_ratio'), g('roce'), g('roe'),
            g('debt_equity'), g('promoter_pct'), g('market_cap_cr'),
            g('sales_cr'), g('profit_cr'), g('eps'), g('div_yield'),
            g('face_value'), g('book_value'), g('current_price'),
            g('high_52w'), g('low_52w'), g('current_ratio'),
            g('revenue_growth'), g('profit_growth'), g('interest_coverage'),
            g('roic'), g('ebitda_growth'), g('scraped_date'), 1,
        ))
        ok += 1
        pe   = f"PE={data['pe_ratio']:.1f}"     if data.get('pe_ratio')   else 'PE=--   '
        roe  = f"ROE={data['roe']:.1f}"         if data.get('roe')        else 'ROE=--  '
        roce = f"ROCE={data['roce']:.1f}"       if data.get('roce')       else 'ROCE=-- '
        pro  = f"Pro={data['promoter_pct']:.1f}" if data.get('promoter_pct') else 'Pro=--  '
        print(f'  [{done_total:4}/{total}] {sym:15} {pe}  {roe}  {roce}  {pro}  ETA {eta:.0f}m')
    else:
        db_single(conn, 'INSERT OR REPLACE INTO screener_fundamentals_v2 (symbol,scraped_date,scrape_ok) VALUES(?,?,0)', (sym, datetime.now().strftime('%Y-%m-%d')))
        err += 1
        print(f'  [{done_total:4}/{total}] {sym:15} FAILED  ETA {eta:.0f}m')

    done_this_run.append(sym)

    if len(batch_data) >= BATCH:
        db_write(conn, SQL, batch_data)
        batch_data = []

    if (i + 1) % 50 == 0:
        # Save checkpoint
        all_done = list(ckpt_done) + done_this_run
        CKPT.write_text(json.dumps({'done': all_done, 'ts': datetime.now().isoformat()}))

    time.sleep(DELAY)

if batch_data:
    db_write(conn, SQL, batch_data)

# Final checkpoint save
all_done = list(ckpt_done) + done_this_run
CKPT.write_text(json.dumps({'done': all_done, 'ts': datetime.now().isoformat()}))

total_db = conn.execute('SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE scrape_ok=1').fetchone()[0]
print(f'Done. OK={ok} Failed={err} Total in DB={total_db}')
print(f'Run time: {(datetime.now()-t0).total_seconds()/60:.1f} min')
print()
print('To resume: py D:\\MICC\\scrape_fundamentals.py 2000 --resume')
conn.close()