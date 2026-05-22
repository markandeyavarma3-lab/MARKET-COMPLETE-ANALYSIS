import subprocess, sys, sqlite3, json
from datetime import datetime
from pathlib import Path

DA   = Path(r'D:\MICC')
DB_P = r'D:\marketDB\db\market.db'
PY   = sys.executable

def ts(): return datetime.now().strftime('%H:%M:%S')
def log(msg): print(f'  [{ts()}] {msg}', flush=True)

def run_agent(script, timeout=120, extra_args=None):
    try:
        cmd = [PY, str(DA / script)] + (extra_args or [])
        r = subprocess.run(cmd, cwd=str(DA),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception as e:
        log(f'{script}: {e}')
        return False

def send(msg):
    try:
        from micc_data import send_telegram_chunks
        return send_telegram_chunks(msg)
    except Exception as e:
        log(f'send failed: {e}')
        return False

# ---- Data getters -------------------------------------------------------

def get_global_snapshot():
    # Flexible alias map: display_label -> list of possible DB names
    WANT = {
        'Nifty 50 ':  ['NIFTY50','NIFTY 50','^NSEI','Nifty 50','NIFTY'],
        'S&P 500  ':  ['SPX','S&P 500','^GSPC','SP500','S&P500'],
        'Dow Jones':  ['DJI','Dow Jones','^DJI','DJIA'],
        'Nasdaq   ':  ['NDX','Nasdaq','^NDX','^IXIC','NASDAQ'],
        'VIX      ':  ['VIX','^VIX','CBOE VIX','CBOE Volatility Index'],
        'IndiaVIX ':  ['IndiaVIX','INDIA VIX','India VIX','^INDIAVIX','INDIAVIX'],
        'US 10Y   ':  ['US10Y','US 10Y','TNX','^TNX','US 10-Yr'],
        'Gold     ':  ['Gold','GOLD','GC=F','XAU','Gold Futures'],
        'Crude WTI':  ['CrudeWTI','Crude WTI','WTI','CL=F','Crude Oil WTI'],
        'USD/INR  ':  ['USDINR','USD/INR','USDINR=X','USD-INR'],
        'Bitcoin  ':  ['Bitcoin','BITCOIN','BTC-USD','BTC','BTC/USD'],
        'Nikkei   ':  ['Nikkei','NIKKEI','^N225','Nikkei 225'],
        'DAX      ':  ['DAX','^GDAXI','DAX Index'],
        'SGX Nifty':  ['SGXNifty','SGX Nifty','SGXNIFTY'],
    }
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        avail = {r[0] for r in conn.execute(
            'SELECT DISTINCT symbol FROM global_indices_daily'
        ).fetchall()}
        to_query = {}  # label -> db_symbol
        for label, candidates in WANT.items():
            for c in candidates:
                if c in avail:
                    to_query[label] = c
                    break
        if not to_query:
            log(f'global_snapshot: 0 matches. DB has: {sorted(avail)[:15]}')
            conn.close(); return []
        syms = list(to_query.values())
        ph   = ','.join('?'*len(syms))
        rows = conn.execute(
            f'SELECT symbol,close,pct_change FROM global_indices_daily'
            f' WHERE symbol IN ({ph})'
            f' AND date=(SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)',
            syms
        ).fetchall()
        conn.close()
        data = {r[0]:(r[1],r[2]) for r in rows}
        result = []
        for label, db_sym in to_query.items():
            if db_sym not in data: continue
            close, chg = data[db_sym]
            if close is None: continue
            ico   = 'UP' if (chg or 0) > 0.3 else 'DN' if (chg or 0) < -0.3 else '--'
            chg_s = f'{chg:+.2f}%' if chg is not None else ''
            result.append(f'  {ico} `{label}` {close:,.2f}  {chg_s}')
        log(f'global_snapshot: {len(result)}/{len(to_query)} symbols found')
        return result
    except Exception as e:
        log(f'global_snapshot error: {e}')
        return []


def get_fusion_picks(n=8):
    # agent_fusion saves to agents/fusion/last_report.json with key 'picks'
    # picks schema: {symbol, n_layers, fusion_score, layers_fired:[...]}
    try:
        p = DA / 'agents' / 'fusion' / 'last_report.json'
        if not p.exists(): return []
        rpt   = json.loads(p.read_text(encoding='utf-8'))
        picks = rpt.get('picks', [])
        return picks[:n]
    except Exception as e:
        log(f'fusion picks error: {e}')
        return []

def get_todays_patterns(n=6):
    mmdd = datetime.today().strftime('%m-%d')
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        cols = {r[1] for r in conn.execute('PRAGMA table_info(seasonality_patterns_v3)').fetchall()}
        # prefer OOS-validated non-overfit patterns
        if 'overfit' in cols and 'fdr_reject' in cols:
            rows = conn.execute(
                'SELECT symbol,window_days,direction,accuracy,mean_ret,score_v2'
                ' FROM seasonality_patterns_v3'
                ' WHERE anchor_mm_dd=? AND fdr_reject=1 AND (overfit=0 OR overfit IS NULL)'
                ' AND score_v2>1.0 AND ABS(mean_ret)<=50'
                ' ORDER BY score_v2 DESC LIMIT ?',
                (mmdd, n)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT symbol,window_days,direction,accuracy,mean_ret,score_v2'
                ' FROM seasonality_patterns_v3'
                ' WHERE anchor_mm_dd=? AND fdr_reject=1 AND score_v2>1.0'
                ' ORDER BY score_v2 DESC LIMIT ?',
                (mmdd, n)
            ).fetchall()
        conn.close()
        return mmdd, rows
    except Exception as e:
        log(f'patterns error: {e}')
        return mmdd, []

def get_quality_picks(n=5):
    # Top quality stocks: ROCE>=15, ROE>=15, D/E<=1, sorted by conviction
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        tables = {r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()}
        if 'screener_fundamentals_v2' not in tables:
            conn.close(); return []
        rows = conn.execute(
            'SELECT f.symbol, f.roce, f.roe, f.debt_equity, f.pe_ratio,'
            ' COALESCE(c.conviction_score,0) AS conviction'
            ' FROM screener_fundamentals_v2 f'
            ' LEFT JOIN symbol_conviction c ON c.symbol=f.symbol'
            ' WHERE f.roce>=15 AND f.roe>=12 AND (f.debt_equity IS NULL OR f.debt_equity<=1.5)'
            ' AND f.scrape_ok=1'
            ' ORDER BY CAST(c.conviction_score AS REAL) DESC, f.roce DESC'
            ' LIMIT ?',
            (n,)
        ).fetchall()
        conn.close()
        return rows
    except Exception as e:
        log(f'quality picks error: {e}')
        return []

def get_eta_highlights():
    try:
        eta_path = DA / 'agents' / 'eta' / 'last_report.json'
        if not eta_path.exists(): return []
        eta = json.loads(eta_path.read_text(encoding='utf-8'))
        # new schema: screen3_insider_clusters
        clusters = (eta.get('screen3_insider_clusters') or
                    eta.get('insider_cluster') or [])[:3]
        return clusters
    except Exception:
        return []

def get_conviction_top(n=4):
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        rows = conn.execute(
            'SELECT symbol, ROUND(CAST(conviction_score AS REAL),1)'
            ' FROM symbol_conviction ORDER BY CAST(conviction_score AS REAL) DESC LIMIT ?',
            (n,)
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []

def get_alerts():
    try:
        p = DA / 'agents' / 'alert' / 'last_report.json'
        if not p.exists(): return 0, []
        ar    = json.loads(p.read_text(encoding='utf-8'))
        fired = ar.get('alerts_fired', 0)
        msgs  = [f.get('message','')[:60] for f in ar.get('fired',[])[:3]]
        return fired, msgs
    except Exception:
        return 0, []

# ---- Main ---------------------------------------------------------------

def main():
    today = datetime.today().strftime('%A, %d %b %Y')
    print(f'MICC Morning Brief -- {today}')
    print('='*50)

    log('Running agents...')
    for script, tout, extra_args in [('agent_fusion.py',120,[]),("agent_eta.py",300,["--no-llm"]),("agent_alert.py",60,[])]:
        ok = run_agent(script, timeout=tout, extra_args=extra_args)
        log(f'  {script}: {"OK" if ok else "FAILED"}')

    lines = [f'*MICC Morning Brief -- {today}*', '']

    # 1. Global markets
    snap = get_global_snapshot()
    if snap:
        lines.append('*Global Markets:*')
        lines.extend(snap)
        lines.append('')
    else:
        lines += ['_Global markets: no data_', '']

    # 2. Fusion picks
    fusion = get_fusion_picks(n=8)
    if fusion:
        lines.append('*Fusion Signals (multi-layer):*')
        for p in fusion:
            sym    = p.get('symbol', '?')
            nl     = p.get('n_layers', 0)
            fs     = p.get('fusion_score', 0)
            layers = p.get('layers_fired', [])
            tag    = '+'.join(str(l)[:3].upper() for l in layers[:5])
            lines.append(f'  `{sym:<12}` {nl}L  [{tag}]')
        lines += ['_Layers: Beta/Insider/Watch/Season/Conviction/Quant_', '']
    else:
        lines += ['_Fusion: no data -- run agent_fusion.py_', '']

    # 3. Quality picks (ROCE+ROE fundamentals)
    quality = get_quality_picks(n=5)
    if quality:
        lines.append('*Quality Picks (ROCE>=15, ROE>=12, D/E<=1.5):*')
        for sym, roce, roe, de, pe, conv in quality:
            roce_s = f'{roce:.1f}' if roce else '--'
            roe_s  = f'{roe:.1f}'  if roe  else '--'
            de_s   = f'{de:.2f}'   if de   else '--'
            pe_s   = f'{pe:.1f}'   if pe   else '--'
            lines.append(f'  `{sym:<12}` ROCE={roce_s}% ROE={roe_s}% D/E={de_s} PE={pe_s} Conv={conv:.0f}')
        lines.append('')

    # 4. Today's patterns (OOS-clean)
    mmdd, pats = get_todays_patterns(n=6)
    if pats:
        # Dedup: one row per symbol, keep best score
        seen = {}  
        for row in pats:
            s = row[0]
            if s not in seen or float(row[5] or 0) > float(seen[s][5] or 0):
                seen[s] = row
        pats = list(seen.values())[:6]
        lines.append(f'*Seasonal Patterns ({mmdd}) [OOS-validated]:*')
        for sym, win, dirn, acc, mean, score in pats:
            ico  = 'UP' if str(dirn).upper() == 'UP' else 'DN'
            accf = float(acc) if acc else 0
            accf = accf if accf <= 1 else accf / 100
            lines.append(f'  {ico} `{sym:<12}` {win}d  {accf*100:.0f}%  {mean:+.2f}%  s={score:.2f}')
        lines.append('')
    else:
        lines += [f'_No OOS-clean patterns for {mmdd}_', '']

    # 5. Insider clusters
    clusters = get_eta_highlights()
    if clusters:
        lines.append('*Insider Clusters:*')
        for c in clusters:
            sym   = c.get('symbol','?')
            buys  = c.get('n_buys') or c.get('buy_count',0)
            val   = c.get('total_value_cr',0) or 0
            lines.append(f'  `{sym}` {buys}x BUY  Rs.{val:.1f}Cr')
        lines.append('')

    # 6. Conviction top
    conv = get_conviction_top(n=4)
    if conv:
        lines.append('*High Conviction:*')
        for sym, score in conv:
            lines.append(f'  `{sym:<12}` {score}/100')
        lines.append('')

    # 7. Alerts
    fired, alert_msgs = get_alerts()
    if fired:
        lines.append(f'*Alerts Fired: {fired}*')
        lines.extend(f'  {m}' for m in alert_msgs)
        lines.append('')

    lines.append('_MICC v3 | localhost:3000_')

    msg = '\n'.join(lines)
    print('\n' + msg[:1500] + ('...' if len(msg) > 1500 else ''))
    ok = send(msg)
    log(f'Telegram: {"SENT" if ok else "FAILED"}')

if __name__ == '__main__':
    main()