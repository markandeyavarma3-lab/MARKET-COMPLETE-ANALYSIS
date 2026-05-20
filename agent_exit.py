#!/usr/bin/env python3
# agent_exit.py - MICC Exit Signal Engine
# Checks open portfolio positions for stop hits, target hits, trail updates
# Run: python agent_exit.py [--send]

import sqlite3, json, sys
from datetime import datetime, timedelta
from pathlib import Path

DA    = Path('D:/MICC')
DB    = 'D:/marketDB/db/market.db'
TODAY = datetime.today().strftime('%Y-%m-%d')
SEND  = '--send' in sys.argv

def log(msg):
    print('[' + datetime.now().strftime('%H:%M:%S') + '] ' + msg, flush=True)

def send_tg(msg):
    try:
        from micc_data import send_telegram_chunks
        send_telegram_chunks(msg)
    except Exception as e:
        log('Telegram failed: ' + str(e))

def main():
    log('Exit Signal Engine starting...')
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row

    sql_positions = (
        'SELECT p.*, st.close as current_price '
        'FROM my_portfolio p '
        'LEFT JOIN ('
        '    SELECT symbol, close FROM stock_data '
        '    WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL) '
        '    AND close IS NOT NULL'
        ') st ON st.symbol=p.symbol '
        'WHERE p.status=\'OPEN\' ORDER BY p.symbol'
    )
    positions = conn.execute(sql_positions).fetchall()
    log('Open positions: ' + str(len(positions)))

    alerts = []
    stop_hits = []
    target_hits = []
    trail_updates = []

    for pos in positions:
        sym         = pos['symbol']
        entry_price = pos['entry_price'] or 0
        qty         = pos['quantity'] or 0
        atr         = pos['atr_at_entry'] or 0
        stop_loss   = pos['stop_loss'] or 0
        target_1    = pos['target_1'] or 0
        target_2    = pos['target_2'] or 0
        risk_pt     = entry_price - stop_loss
        cur         = pos['current_price']

        if not cur or cur <= 0:
            continue

        unrealized_r = (cur - entry_price) / risk_pt if risk_pt > 0 else 0
        pnl_pct      = (cur - entry_price) / entry_price * 100 if entry_price else 0

        if cur <= stop_loss:
            a = {'symbol':sym,'signal':'STOP_HIT','urgency':'HIGH',
                 'current':cur,'stop_loss':stop_loss,'entry':entry_price,
                 'pnl_pct':round(pnl_pct,2),
                 'message':sym+' STOP HIT -- price '+str(round(cur,1))+' <= stop '+str(round(stop_loss,1))}
            stop_hits.append(a); alerts.append(a)

        elif target_2 > 0 and cur >= target_2:
            a = {'symbol':sym,'signal':'TARGET2_HIT','urgency':'HIGH',
                 'current':cur,'target':target_2,'pnl_pct':round(pnl_pct,2),
                 'message':sym+' TARGET 2 HIT -- +'+str(round(pnl_pct,1))+'% Consider full exit'}
            target_hits.append(a); alerts.append(a)

        elif target_1 > 0 and cur >= target_1:
            a = {'symbol':sym,'signal':'TARGET1_HIT','urgency':'MED',
                 'current':cur,'target':target_1,'pnl_pct':round(pnl_pct,2),
                 'message':sym+' TARGET 1 HIT -- +'+str(round(pnl_pct,1))+'% Consider partial exit'}
            target_hits.append(a); alerts.append(a)

        elif unrealized_r >= 2.0 and risk_pt > 0:
            new_stop = round(entry_price + 0.5 * atr, 2) if atr > 0 else entry_price
            if new_stop > stop_loss:
                a = {'symbol':sym,'signal':'TRAIL_STOP','urgency':'LOW',
                     'current':cur,'old_stop':stop_loss,'new_stop':new_stop,
                     'unreal_r':round(unrealized_r,1),'pnl_pct':round(pnl_pct,2),
                     'message':sym+' +'+str(round(unrealized_r,1))+'R trail stop to '+str(new_stop)}
                trail_updates.append(a); alerts.append(a)

        # Seasonal window closing check
        try:
            pats = conn.execute(
                'SELECT anchor_month, window_days, direction, accuracy '
                'FROM seasonality_patterns WHERE symbol=? AND accuracy>=0.65 '
                'AND n_years>=8 ORDER BY score DESC LIMIT 3',
                (sym,)
            ).fetchall()
            for pat in pats:
                if pat['anchor_month'] == datetime.today().month:
                    alerts.append({
                        'symbol':sym,'signal':'SEASONAL_WINDOW_CLOSING',
                        'urgency':'LOW','current':cur,'pnl_pct':round(pnl_pct,2),
                        'message':sym+' seasonal '+str(pat['direction'])+' window closing this month',
                    })
                    break
        except Exception:
            pass

    conn.close()

    report = {
        'generated_at': datetime.now().isoformat(),
        'date': TODAY,
        'positions_checked': len(positions),
        'total_alerts': len(alerts),
        'stop_hits': stop_hits,
        'target_hits': target_hits,
        'trail_updates': trail_updates,
        'alerts': alerts,
    }

    out_dir = DA / 'agents' / 'exit'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'last_report.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8'
    )

    log('Exit signals: ' + str(len(alerts)) + ' total')
    for a in alerts:
        log('  [' + a['urgency'] + '] ' + a['message'])

    if SEND and alerts:
        lines = ['*MICC Exit Signals -- ' + TODAY + '*', '']
        for a in [x for x in alerts if x['urgency']=='HIGH']:
            lines.append('STOP/TARGET `' + a['symbol'] + '` ' + str(round(a['pnl_pct'],1)) + '% -- ' + a['signal'])
        for a in [x for x in alerts if x['urgency']=='LOW']:
            lines.append('TRAIL `' + a['symbol'] + '` ' + a['message'][:60])
        send_tg('\n'.join(lines))

    if not alerts:
        log('No exit signals -- all positions within range')

if __name__ == '__main__':
    main()