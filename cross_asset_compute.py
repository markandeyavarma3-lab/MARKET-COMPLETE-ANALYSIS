import sqlite3, math
from datetime import datetime
import numpy as np

DB = 'D:/marketDB/db/market.db'
conn = sqlite3.connect(DB, timeout=30)
conn.execute('PRAGMA journal_mode=WAL')
TODAY = datetime.today().strftime('%Y-%m-%d')

def load_series(symbol, days=504):
    rows = conn.execute(
        'SELECT date, close FROM global_indices_daily WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT ?',
        (symbol, days)
    ).fetchall()
    return list(reversed(rows)) if rows else []

nifty_rows = load_series('NIFTY50', 504)
nifty_dates = [r[0] for r in nifty_rows]
nifty_closes = [r[1] for r in nifty_rows]

def nifty_fwd(date_str, days):
    try:
        idx = nifty_dates.index(date_str)
        fi = idx + days
        if fi < len(nifty_rows):
            p0 = nifty_closes[idx]
            p1 = nifty_closes[fi]
            return round((p1 - p0) / p0 * 100, 3)
    except Exception:
        pass
    return None

def compute_signal(name, asset, values, condition_fn, fwd_days=10):
    if len(values) < 20: return None
    closes = [v[1] for v in values]
    dates  = [v[0] for v in values]
    signal_type, condition_desc = condition_fn(closes)
    if not signal_type: return None
    hits = total = 0
    for i in range(20, len(closes) - fwd_days):
        stype, _ = condition_fn(closes[max(0, i-20):i+1])
        if stype == signal_type:
            fwd = nifty_fwd(dates[i], fwd_days)
            if fwd is not None:
                total += 1
                if fwd > 0: hits += 1
    hit_rate = round(hits / total, 3) if total >= 5 else None
    return {
        'date': dates[-1], 'signal_name': name, 'asset': asset,
        'value': round(closes[-1], 2), 'signal_type': signal_type,
        'condition_desc': condition_desc,
        'nifty_fwd_5d': nifty_fwd(dates[-1], 5),
        'nifty_fwd_10d': nifty_fwd(dates[-1], 10),
        'hit_rate_hist': hit_rate, 'n_historical': total,
        'computed_date': TODAY,
    }

signals = []

vix = load_series('VIX')
if vix:
    def vix_cond(closes):
        if len(closes) < 5: return None, None
        cur = closes[-1]
        avg = np.mean(closes[-min(20,len(closes)):])
        if cur > 25: return 'FEAR', 'VIX > 25 (high fear = contrarian buy)'
        if cur > avg * 1.2: return 'SPIKE', 'VIX spike >20pct above 20d avg'
        if cur < 15: return 'CALM', 'VIX < 15 (complacency)'
        return None, None
    s = compute_signal('VIX_REGIME', 'VIX', vix, vix_cond)
    if s: signals.append(s)

dxy = load_series('DXY')
if dxy:
    def dxy_cond(closes):
        if len(closes) < 20: return None, None
        cur = closes[-1]
        sma20 = np.mean(closes[-20:])
        sma50 = np.mean(closes[-min(50,len(closes)):])
        if cur > sma20 and sma20 > sma50: return 'STRONG', 'DXY above SMA20 and SMA50'
        if cur < sma20 and sma20 < sma50: return 'WEAK', 'DXY below SMA20 and SMA50'
        return None, None
    s = compute_signal('DXY_TREND', 'DXY', dxy, dxy_cond)
    if s: signals.append(s)

gold = load_series('Gold')
if gold:
    def gold_cond(closes):
        if len(closes) < 20: return None, None
        ret20 = (closes[-1] - closes[-20]) / closes[-20] * 100
        if ret20 > 3: return 'BULLISH', 'Gold up >3pct in 20d (risk-off)'
        if ret20 < -3: return 'BEARISH', 'Gold down >3pct in 20d (risk-on)'
        return None, None
    s = compute_signal('GOLD_TREND', 'Gold', gold, gold_cond)
    if s: signals.append(s)

usdinr = load_series('USDINR')
if usdinr:
    def usdinr_cond(closes):
        if len(closes) < 20: return None, None
        cur = closes[-1]
        sma20 = np.mean(closes[-20:])
        if cur > sma20 * 1.01: return 'WEAK_INR', 'USDINR above SMA20 (rupee weak)'
        if cur < sma20 * 0.99: return 'STRONG_INR', 'USDINR below SMA20 (rupee strong)'
        return None, None
    s = compute_signal('USDINR_TREND', 'USDINR', usdinr, usdinr_cond)
    if s: signals.append(s)

spx = load_series('SPX')
if spx:
    def spx_cond(closes):
        if len(closes) < 50: return None, None
        cur = closes[-1]
        sma50 = np.mean(closes[-50:])
        ret5 = (closes[-1] - closes[-5]) / closes[-5] * 100
        if cur > sma50 and ret5 > 1: return 'RISK_ON', 'SPX above SMA50 up >1pct in 5d'
        if cur < sma50 and ret5 < -1: return 'RISK_OFF', 'SPX below SMA50 down >1pct in 5d'
        return None, None
    s = compute_signal('SPX_REGIME', 'SPX', spx, spx_cond)
    if s: signals.append(s)

us10y = load_series('US10Y')
if us10y:
    def us10y_cond(closes):
        if len(closes) < 20: return None, None
        delta = closes[-1] - closes[-20]
        if delta > 0.2: return 'RISING', 'US10Y up >20bp in 20d (tightening)'
        if delta < -0.2: return 'FALLING', 'US10Y down >20bp in 20d (easing)'
        return None, None
    s = compute_signal('US10Y_TREND', 'US10Y', us10y, us10y_cond)
    if s: signals.append(s)

conn.execute('DELETE FROM cross_asset_signals WHERE date = ?', (TODAY,))
for s in signals:
    conn.execute(
        'INSERT OR REPLACE INTO cross_asset_signals'
        ' (date, signal_name, asset, value, signal_type, condition_desc,'
        ' nifty_fwd_5d, nifty_fwd_10d, hit_rate_hist, n_historical, computed_date)'
        ' VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (s['date'], s['signal_name'], s['asset'], s['value'],
         s['signal_type'], s['condition_desc'],
         s['nifty_fwd_5d'], s['nifty_fwd_10d'],
         s['hit_rate_hist'], s['n_historical'], s['computed_date'])
    )
conn.commit()
conn.close()
print('Cross-asset signals: ' + str(len(signals)))
for s in signals:
    hr = str(round(s['hit_rate_hist']*100)) + '%' if s['hit_rate_hist'] else '?'
    print('  ' + s['signal_name'].ljust(16) + ' | ' + str(s['signal_type']).ljust(12) + ' | hit=' + hr + ' n=' + str(s['n_historical']))