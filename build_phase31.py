#!/usr/bin/env python3
"""
build_phase31.py - Phase 31 orchestrator
Writes agent_exit.py, updates morning_brief.py, patches telegram_bot.py
Run: python build_phase31.py
"""
from pathlib import Path
import re, sys

MICC = Path("D:/MICC")

def log(msg):
    from datetime import datetime
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)

def write(path, lines, label=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    lbl = label or str(path.name)
    print("  [OK] " + lbl + " (" + str(len(lines)) + " lines)")


# =============================================================================
# [1] agent_exit.py
# =============================================================================
log("[1/4] Writing agent_exit.py...")

exit_lines = [
    "#!/usr/bin/env python3",
    "# agent_exit.py - MICC Exit Signal Engine",
    "# Checks open portfolio positions for stop hits, target hits, trail updates",
    "# Run: python agent_exit.py [--send]",
    "",
    "import sqlite3, json, sys",
    "from datetime import datetime, timedelta",
    "from pathlib import Path",
    "",
    "DA    = Path('D:/MICC')",
    "DB    = 'D:/marketDB/db/market.db'",
    "TODAY = datetime.today().strftime('%Y-%m-%d')",
    "SEND  = '--send' in sys.argv",
    "",
    "def log(msg):",
    "    print('[' + datetime.now().strftime('%H:%M:%S') + '] ' + msg, flush=True)",
    "",
    "def send_tg(msg):",
    "    try:",
    "        from micc_data import send_telegram_chunks",
    "        send_telegram_chunks(msg)",
    "    except Exception as e:",
    "        log('Telegram failed: ' + str(e))",
    "",
    "def main():",
    "    log('Exit Signal Engine starting...')",
    "    conn = sqlite3.connect(DB, timeout=15)",
    "    conn.row_factory = sqlite3.Row",
    "",
    "    sql_positions = (",
    "        'SELECT p.*, st.close as current_price '",
    "        'FROM my_portfolio p '",
    "        'LEFT JOIN ('",
    "        '    SELECT symbol, close FROM stock_data '",
    "        '    WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL) '",
    "        '    AND close IS NOT NULL'",
    "        ') st ON st.symbol=p.symbol '",
    "        'WHERE p.status=\\'OPEN\\' ORDER BY p.symbol'",
    "    )",
    "    positions = conn.execute(sql_positions).fetchall()",
    "    log('Open positions: ' + str(len(positions)))",
    "",
    "    alerts = []",
    "    stop_hits = []",
    "    target_hits = []",
    "    trail_updates = []",
    "",
    "    for pos in positions:",
    "        sym         = pos['symbol']",
    "        entry_price = pos['entry_price'] or 0",
    "        qty         = pos['quantity'] or 0",
    "        atr         = pos['atr_at_entry'] or 0",
    "        stop_loss   = pos['stop_loss'] or 0",
    "        target_1    = pos['target_1'] or 0",
    "        target_2    = pos['target_2'] or 0",
    "        risk_pt     = entry_price - stop_loss",
    "        cur         = pos['current_price']",
    "",
    "        if not cur or cur <= 0:",
    "            continue",
    "",
    "        unrealized_r = (cur - entry_price) / risk_pt if risk_pt > 0 else 0",
    "        pnl_pct      = (cur - entry_price) / entry_price * 100 if entry_price else 0",
    "",
    "        if cur <= stop_loss:",
    "            a = {'symbol':sym,'signal':'STOP_HIT','urgency':'HIGH',",
    "                 'current':cur,'stop_loss':stop_loss,'entry':entry_price,",
    "                 'pnl_pct':round(pnl_pct,2),",
    "                 'message':sym+' STOP HIT -- price '+str(round(cur,1))+' <= stop '+str(round(stop_loss,1))}",
    "            stop_hits.append(a); alerts.append(a)",
    "",
    "        elif target_2 > 0 and cur >= target_2:",
    "            a = {'symbol':sym,'signal':'TARGET2_HIT','urgency':'HIGH',",
    "                 'current':cur,'target':target_2,'pnl_pct':round(pnl_pct,2),",
    "                 'message':sym+' TARGET 2 HIT -- +'+str(round(pnl_pct,1))+'% Consider full exit'}",
    "            target_hits.append(a); alerts.append(a)",
    "",
    "        elif target_1 > 0 and cur >= target_1:",
    "            a = {'symbol':sym,'signal':'TARGET1_HIT','urgency':'MED',",
    "                 'current':cur,'target':target_1,'pnl_pct':round(pnl_pct,2),",
    "                 'message':sym+' TARGET 1 HIT -- +'+str(round(pnl_pct,1))+'% Consider partial exit'}",
    "            target_hits.append(a); alerts.append(a)",
    "",
    "        elif unrealized_r >= 2.0 and risk_pt > 0:",
    "            new_stop = round(entry_price + 0.5 * atr, 2) if atr > 0 else entry_price",
    "            if new_stop > stop_loss:",
    "                a = {'symbol':sym,'signal':'TRAIL_STOP','urgency':'LOW',",
    "                     'current':cur,'old_stop':stop_loss,'new_stop':new_stop,",
    "                     'unreal_r':round(unrealized_r,1),'pnl_pct':round(pnl_pct,2),",
    "                     'message':sym+' +'+str(round(unrealized_r,1))+'R trail stop to '+str(new_stop)}",
    "                trail_updates.append(a); alerts.append(a)",
    "",
    "        # Seasonal window closing check",
    "        try:",
    "            pats = conn.execute(",
    "                'SELECT anchor_month, window_days, direction, accuracy '",
    "                'FROM seasonality_patterns WHERE symbol=? AND accuracy>=0.65 '",
    "                'AND n_years>=8 ORDER BY score DESC LIMIT 3',",
    "                (sym,)",
    "            ).fetchall()",
    "            for pat in pats:",
    "                if pat['anchor_month'] == datetime.today().month:",
    "                    alerts.append({",
    "                        'symbol':sym,'signal':'SEASONAL_WINDOW_CLOSING',",
    "                        'urgency':'LOW','current':cur,'pnl_pct':round(pnl_pct,2),",
    "                        'message':sym+' seasonal '+str(pat['direction'])+' window closing this month',",
    "                    })",
    "                    break",
    "        except Exception:",
    "            pass",
    "",
    "    conn.close()",
    "",
    "    report = {",
    "        'generated_at': datetime.now().isoformat(),",
    "        'date': TODAY,",
    "        'positions_checked': len(positions),",
    "        'total_alerts': len(alerts),",
    "        'stop_hits': stop_hits,",
    "        'target_hits': target_hits,",
    "        'trail_updates': trail_updates,",
    "        'alerts': alerts,",
    "    }",
    "",
    "    out_dir = DA / 'agents' / 'exit'",
    "    out_dir.mkdir(parents=True, exist_ok=True)",
    "    (out_dir / 'last_report.json').write_text(",
    "        json.dumps(report, indent=2), encoding='utf-8'",
    "    )",
    "",
    "    log('Exit signals: ' + str(len(alerts)) + ' total')",
    "    for a in alerts:",
    "        log('  [' + a['urgency'] + '] ' + a['message'])",
    "",
    "    if SEND and alerts:",
    "        lines = ['*MICC Exit Signals -- ' + TODAY + '*', '']",
    "        for a in [x for x in alerts if x['urgency']=='HIGH']:",
    "            lines.append('STOP/TARGET `' + a['symbol'] + '` ' + str(round(a['pnl_pct'],1)) + '% -- ' + a['signal'])",
    "        for a in [x for x in alerts if x['urgency']=='LOW']:",
    "            lines.append('TRAIL `' + a['symbol'] + '` ' + a['message'][:60])",
    "        send_tg('\\n'.join(lines))",
    "",
    "    if not alerts:",
    "        log('No exit signals -- all positions within range')",
    "",
    "if __name__ == '__main__':",
    "    main()",
]

write(MICC / "agent_exit.py", exit_lines)


# =============================================================================
# [2] morning_brief.py
# =============================================================================
log("[2/4] Writing morning_brief.py...")

mb_lines = [
    "# morning_brief.py -- MICC Morning Brief",
    "# Run: python D:/MICC/morning_brief.py",
    "# Schedule: Windows Task Scheduler 09:00 weekdays",
    "",
    "import subprocess, sys, sqlite3, json",
    "from datetime import datetime",
    "from pathlib import Path",
    "",
    "DA   = Path('D:/MICC')",
    "DB_P = 'D:/marketDB/db/market.db'",
    "PY   = sys.executable",
    "",
    "def ts(): return datetime.now().strftime('%H:%M:%S')",
    "def log(msg): print('  [' + ts() + '] ' + msg, flush=True)",
    "",
    "def run_agent(script, timeout=180):",
    "    try:",
    "        r = subprocess.run([PY, str(DA / script)], cwd=str(DA),",
    "                           capture_output=True, text=True, timeout=timeout)",
    "        return r.returncode == 0",
    "    except Exception as e:",
    "        log(script + ': ' + str(e))",
    "        return False",
    "",
    "def send(msg):",
    "    try:",
    "        from micc_data import send_telegram_chunks",
    "        return send_telegram_chunks(msg)",
    "    except Exception as e:",
    "        log('send failed: ' + str(e))",
    "        return False",
    "",
    "def get_global_snapshot():",
    "    WATCH = ['NIFTY50','SPX','SP500VIX','INDIAVIX','US10Y','Gold','CrudeWTI','USDINR']",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        ph = ','.join('?'*len(WATCH))",
    "        sql = ('SELECT symbol,close,pct_change FROM global_indices_daily'",
    "               ' WHERE symbol IN (' + ph + ')'",
    "               ' AND date=(SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)')",
    "        rows = conn.execute(sql, WATCH).fetchall()",
    "        conn.close()",
    "        return {r[0]:(r[1],r[2]) for r in rows}",
    "    except Exception:",
    "        return {}",
    "",
    "def get_top_conviction(n=5):",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        sql = ('SELECT c.symbol, c.conviction_score, c.top_reason, c.signal_count, st.close'",
    "               ' FROM symbol_conviction c'",
    "               ' LEFT JOIN ('",
    "               '   SELECT symbol, close FROM stock_data'",
    "               '   WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)'",
    "               '   AND close IS NOT NULL'",
    "               ' ) st ON st.symbol=c.symbol'",
    "               ' WHERE c.conviction_score>=60'",
    "               ' ORDER BY c.conviction_score DESC LIMIT ?')",
    "        rows = conn.execute(sql, (n,)).fetchall()",
    "        conn.close()",
    "        return rows",
    "    except Exception:",
    "        return []",
    "",
    "def get_cross_asset_signals():",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        sql = ('SELECT asset, signal_type, hit_rate_hist, condition_desc'",
    "               ' FROM cross_asset_signals'",
    "               ' WHERE date=(SELECT MAX(date) FROM cross_asset_signals)'",
    "               ' ORDER BY CASE WHEN hit_rate_hist IS NULL THEN 1 ELSE 0 END, hit_rate_hist DESC')",
    "        rows = conn.execute(sql).fetchall()",
    "        conn.close()",
    "        return rows",
    "    except Exception:",
    "        return []",
    "",
    "def get_todays_patterns(n=6):",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        tables = {r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type=\\'table\\'').fetchall()}",
    "        tbl = 'seasonality_patterns_v3' if 'seasonality_patterns_v3' in tables else 'seasonality_patterns'",
    "        sql = ('SELECT symbol,window_days,direction,accuracy,avg_return_all,score'",
    "               ' FROM ' + tbl + ' WHERE anchor_month=? AND accuracy>=0.65'",
    "               ' AND score>=5 ORDER BY score DESC LIMIT ?')",
    "        rows = conn.execute(sql, (datetime.today().month, n)).fetchall()",
    "        conn.close()",
    "        mmdd = datetime.today().strftime('%m-%d')",
    "        return mmdd, rows",
    "    except Exception:",
    "        return datetime.today().strftime('%m-%d'), []",
    "",
    "def get_exit_signals():",
    "    try:",
    "        p = DA / 'agents' / 'exit' / 'last_report.json'",
    "        if not p.exists(): return []",
    "        return json.loads(p.read_text(encoding='utf-8')).get('alerts', [])",
    "    except Exception:",
    "        return []",
    "",
    "def get_portfolio_summary():",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        sql = ('SELECT p.symbol, p.entry_price, p.quantity, st.close'",
    "               ' FROM my_portfolio p'",
    "               ' LEFT JOIN ('",
    "               '   SELECT symbol, close FROM stock_data'",
    "               '   WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)'",
    "               '   AND close IS NOT NULL'",
    "               ' ) st ON st.symbol=p.symbol'",
    "               ' WHERE p.status=\\'OPEN\\'')",
    "        rows = conn.execute(sql).fetchall()",
    "        conn.close()",
    "        return rows",
    "    except Exception:",
    "        return []",
    "",
    "def main():",
    "    today = datetime.today().strftime('%A, %d %b %Y')",
    "    print('')",
    "    print('MICC Morning Brief -- ' + today)",
    "    print('='*50)",
    "",
    "    log('Running agents...')",
    "    for script in ['agent_eta.py','agent_alert.py','agent_exit.py','build_conviction.py']:",
    "        ok = run_agent(script, timeout=180)",
    "        log(script + ': ' + ('OK' if ok else 'FAILED'))",
    "",
    "    lines = ['*MICC Morning Brief -- ' + today + '*', '']",
    "",
    "    # Global snapshot",
    "    snap = get_global_snapshot()",
    "    LABELS = {'NIFTY50':'Nifty   ','SPX':'S&P 500 ','SP500VIX':'VIX     ',",
    "              'INDIAVIX':'IndVIX  ','US10Y':'US 10Y  ','Gold':'Gold    ',",
    "              'CrudeWTI':'Crude   ','USDINR':'USD/INR '}",
    "    if snap:",
    "        lines.append('*Global Markets:*')",
    "        for sym in ['NIFTY50','SPX','SP500VIX','Gold','CrudeWTI','USDINR','US10Y','INDIAVIX']:",
    "            if sym not in snap: continue",
    "            close, chg = snap[sym]",
    "            if close is None: continue",
    "            ico = '+' if (chg or 0) > 0.3 else '-' if (chg or 0) < -0.3 else ' '",
    "            chg_s = ('{:+.2f}%'.format(chg)) if chg is not None else ''",
    "            lines.append('  ' + ico + ' `' + LABELS.get(sym,sym) + '` ' + str(round(close,2)) + '  ' + chg_s)",
    "        lines.append('')",
    "",
    "    # Cross-asset signals",
    "    sigs = get_cross_asset_signals()",
    "    if sigs:",
    "        lines.append('*Macro Regime Signals:*')",
    "        for asset, sig_type, hr, desc in sigs[:4]:",
    "            hr_str = ' hit=' + str(round(hr*100)) + '%' if hr else ''",
    "            lines.append('  `' + str(asset).ljust(8) + '` ' + str(sig_type).ljust(14) + hr_str)",
    "        lines.append('')",
    "",
    "    # Exit alerts (urgent)",
    "    exits = get_exit_signals()",
    "    urgent = [e for e in exits if e.get('urgency')=='HIGH']",
    "    if urgent:",
    "        lines.append('*EXIT ALERTS (Action Required):*')",
    "        for e in urgent:",
    "            lines.append('  ' + e.get('signal','') + ' `' + e.get('symbol','') + '` ' + str(round(e.get('pnl_pct',0),1)) + '%')",
    "        lines.append('')",
    "",
    "    # Portfolio summary",
    "    port = get_portfolio_summary()",
    "    if port:",
    "        total_pnl = sum(((r[3] or r[1] or 0)-(r[1] or 0))*(r[2] or 0) for r in port)",
    "        lines.append('*Portfolio (' + str(len(port)) + ' open | P&L ' + '{:+.0f}'.format(total_pnl) + '):*')",
    "        for sym, entry, qty, cur in port:",
    "            if not cur or not entry: continue",
    "            pnl_pct = (cur-entry)/entry*100",
    "            ico = '+' if pnl_pct > 0 else '-'",
    "            lines.append('  ' + ico + ' `' + str(sym).ljust(12) + '` ' + '{:+.1f}%'.format(pnl_pct))",
    "        lines.append('')",
    "",
    "    # Top conviction picks",
    "    conviction = get_top_conviction(5)",
    "    if conviction:",
    "        lines.append('*Top Conviction Picks:*')",
    "        for sym, score, reason, signals, close in conviction:",
    "            close_str = ' INR' + str(round(close,1)) if close else ''",
    "            lines.append('  `' + str(sym).ljust(12) + '` ' + str(round(score,1)) + ' [' + str(reason) + ']' + close_str)",
    "        lines.append('')",
    "",
    "    # Seasonal patterns",
    "    mmdd, pats = get_todays_patterns(6)",
    "    if pats:",
    "        lines.append('*Seasonal Patterns (' + mmdd + '):*')",
    "        for sym, win, dirn, acc, mean, score in pats:",
    "            ico = '+' if dirn=='UP' else '-'",
    "            acc_pct = acc*100 if acc<=1 else acc",
    "            mean_v = mean if mean else 0",
    "            lines.append('  ' + ico + ' `' + str(sym).ljust(14) + '` ' + str(win) + 'd  ' + str(round(acc_pct)) + '%  ' + '{:+.2f}%'.format(mean_v))",
    "        lines.append('')",
    "",
    "    # Insider clusters",
    "    try:",
    "        eta_path = DA / 'agents' / 'eta' / 'last_report.json'",
    "        if eta_path.exists():",
    "            eta = json.loads(eta_path.read_text(encoding='utf-8'))",
    "            clusters = eta.get('insider_cluster', [])[:3]",
    "            if clusters:",
    "                lines.append('*Insider Clusters:*')",
    "                for c in clusters:",
    "                    val = c.get('total_value_cr', c.get('total_value', 0))",
    "                    try: val = float(val)/1e7 if float(val)>1e5 else float(val)",
    "                    except: val = 0",
    "                    lines.append('  `' + str(c['symbol']) + '` ' + str(c.get('buy_count','?')) + ' buys INR' + str(round(val,1)) + 'Cr')",
    "                lines.append('')",
    "    except Exception:",
    "        pass",
    "",
    "    # Price alerts",
    "    try:",
    "        alert_path = DA / 'agents' / 'alert' / 'last_report.json'",
    "        if alert_path.exists():",
    "            ar = json.loads(alert_path.read_text(encoding='utf-8'))",
    "            fired = ar.get('alerts_fired', 0)",
    "            if fired:",
    "                lines.append('*Price Alerts Fired: ' + str(fired) + '*')",
    "                for f in ar.get('fired', [])[:3]:",
    "                    lines.append('  ' + str(f.get('message',''))[:60])",
    "                lines.append('')",
    "    except Exception:",
    "        pass",
    "",
    "    lines.append('_MICC v3 | localhost:3000_')",
    "    msg = '\\n'.join(lines)",
    "    print('')",
    "    print(msg[:800] + '...')",
    "    ok = send(msg)",
    "    log('Telegram: ' + ('SENT' if ok else 'FAILED'))",
    "",
    "if __name__ == '__main__':",
    "    main()",
]

write(MICC / "morning_brief.py", mb_lines)


# =============================================================================
# [3] Patch telegram_bot.py
# =============================================================================
log("[3/4] Patching telegram_bot.py...")

tb_path = MICC / "telegram_bot.py"
tb = tb_path.read_text(encoding="utf-8")

if "cmd_conviction" not in tb:
    new_cmds = [
        "",
        "# ── /conviction ──────────────────────────────────────────────────────────────",
        "async def cmd_conviction(update: Update, context: ContextTypes.DEFAULT_TYPE):",
        "    import sqlite3",
        "    try:",
        "        conn = sqlite3.connect('D:/marketDB/db/market.db', timeout=10)",
        "        sql = (",
        "            'SELECT c.symbol, c.conviction_score, c.top_reason, c.signal_count, st.close'",
        "            ' FROM symbol_conviction c'",
        "            ' LEFT JOIN ('",
        "            '   SELECT symbol, close FROM stock_data'",
        "            '   WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)'",
        "            '   AND close IS NOT NULL'",
        "            ' ) st ON st.symbol=c.symbol'",
        "            ' WHERE c.conviction_score>=55'",
        "            ' ORDER BY c.conviction_score DESC LIMIT 15'",
        "        )",
        "        rows = conn.execute(sql).fetchall()",
        "        conn.close()",
        "        lines = ['*MICC Conviction Top Picks*', '']",
        "        for sym, score, reason, signals, close in rows:",
        "            close_str = ' INR' + str(round(close,1)) if close else ''",
        "            lines.append('`' + str(sym).ljust(12) + '` ' + str(round(score,1)).ljust(6) + '[' + str(reason) + '] ' + str(signals) + '/7' + close_str)",
        "        msg = '\\n'.join(lines)",
        "    except Exception as e:",
        "        msg = 'Error: ' + str(e)",
        "    await update.message.reply_text(msg, parse_mode='Markdown')",
        "",
        "# ── /portfolio ────────────────────────────────────────────────────────────────",
        "async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):",
        "    import sqlite3",
        "    try:",
        "        conn = sqlite3.connect('D:/marketDB/db/market.db', timeout=10)",
        "        sql = (",
        "            'SELECT p.symbol, p.entry_price, p.quantity, p.stop_loss, p.target_1, st.close'",
        "            ' FROM my_portfolio p'",
        "            ' LEFT JOIN ('",
        "            '   SELECT symbol, close FROM stock_data'",
        "            '   WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)'",
        "            '   AND close IS NOT NULL'",
        "            ' ) st ON st.symbol=p.symbol'",
        "            ' WHERE p.status=\\'OPEN\\' ORDER BY p.added_at DESC'",
        "        )",
        "        rows = conn.execute(sql).fetchall()",
        "        conn.close()",
        "        if not rows:",
        "            await update.message.reply_text('No open positions.')",
        "            return",
        "        total_unr = sum(((r[5] or r[1] or 0)-(r[1] or 0))*(r[2] or 0) for r in rows)",
        "        lines = ['*MICC Portfolio -- ' + datetime.now().strftime('%Y-%m-%d') + '*',",
        "                 str(len(rows)) + ' open | Unrealized: ' + '{:+.0f}'.format(total_unr), '']",
        "        for sym, entry, qty, stop, t1, cur in rows:",
        "            cur = cur or entry or 0",
        "            pnl_pct = (cur-(entry or 0))/(entry or 1)*100",
        "            ico = '+' if pnl_pct>0 else '-'",
        "            lines.append(ico+' `'+str(sym).ljust(12)+'` '+'{:+.1f}%'.format(pnl_pct)+' stop='+str(round(stop or 0,1))+' T1='+str(round(t1 or 0,1)))",
        "        msg = '\\n'.join(lines)",
        "    except Exception as e:",
        "        msg = 'Error: ' + str(e)",
        "    await update.message.reply_text(msg, parse_mode='Markdown')",
        "",
        "# ── /exit ────────────────────────────────────────────────────────────────────",
        "async def cmd_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):",
        "    import json",
        "    from pathlib import Path",
        "    try:",
        "        p = Path('D:/MICC/agents/exit/last_report.json')",
        "        if not p.exists():",
        "            await update.message.reply_text('No exit report. Run agent_exit.py first.')",
        "            return",
        "        d = json.loads(p.read_text(encoding='utf-8'))",
        "        alerts = d.get('alerts', [])",
        "        if not alerts:",
        "            await update.message.reply_text('No exit signals -- all positions within range.')",
        "            return",
        "        lines = ['*MICC Exit Signals -- ' + d.get('date','?') + '*', '']",
        "        for a in alerts:",
        "            lines.append('['+str(a.get('urgency','?'))+'] `'+str(a.get('symbol','?'))+'` '+str(a.get('signal',''))+' '+str(round(a.get('pnl_pct',0),1))+'%')",
        "            lines.append('  '+str(a.get('message',''))[:60])",
        "        msg = '\\n'.join(lines)",
        "    except Exception as e:",
        "        msg = 'Error: ' + str(e)",
        "    await update.message.reply_text(msg, parse_mode='Markdown')",
        "",
    ]

    # Find injection point: right before first "async def cmd_" or before "def main("
    match = re.search(r'\nasync def cmd_', tb)
    if match:
        inject = match.start()
    else:
        match = re.search(r'\ndef main\(', tb)
        inject = match.start() if match else len(tb)

    tb = tb[:inject] + "\n".join(new_cmds) + tb[inject:]

    # Register handlers - find existing handler registration
    for anchor in [
        'CommandHandler("status"',
        'CommandHandler("report"',
        'CommandHandler("alpha"',
    ]:
        if anchor in tb:
            tb = tb.replace(
                anchor,
                'CommandHandler("conviction", cmd_conviction))\n'
                '    app.add_handler(CommandHandler("portfolio", cmd_portfolio))\n'
                '    app.add_handler(CommandHandler("exit", cmd_exit))\n'
                '    app.add_handler(' + anchor,
                1
            )
            break

    tb_path.write_text(tb, encoding="utf-8")
    log("  Patched: /conviction /portfolio /exit added")
else:
    log("  telegram_bot.py already has new commands")


# =============================================================================
# [4] Patch run_pipeline.py
# =============================================================================
log("[4/4] Patching run_pipeline.py...")

pipeline_path = MICC / "data_pipeline" / "run_pipeline.py"
if pipeline_path.exists():
    pipeline = pipeline_path.read_text(encoding="utf-8")
    if "build_conviction" not in pipeline:
        # Find last }, in PHASES list and insert after it
        last = pipeline.rfind("},\n")
        if last > 0:
            insert = last + 3
            new_phases = (
                "    {\n"
                "        'name': 'piotroski_fscore',\n"
                "        'script': 'D:/MICC/build_piotroski.py',\n"
                "        'label': 'Piotroski F-Score',\n"
                "    },\n"
                "    {\n"
                "        'name': 'conviction_build',\n"
                "        'script': 'D:/MICC/build_conviction.py',\n"
                "        'label': 'Conviction Score Fusion',\n"
                "    },\n"
                "    {\n"
                "        'name': 'exit_signals',\n"
                "        'script': 'D:/MICC/agent_exit.py',\n"
                "        'label': 'Exit Signal Engine',\n"
                "    },\n"
            )
            pipeline = pipeline[:insert] + new_phases + pipeline[insert:]
            pipeline_path.write_text(pipeline, encoding="utf-8")
            log("  run_pipeline.py patched")
        else:
            log("  [WARN] Could not find insertion point in run_pipeline.py")
    else:
        log("  run_pipeline.py already has conviction phases")
else:
    log("  run_pipeline.py not found")


print("")
print("=" * 55)
print("PHASE 31 COMPLETE")
print("=" * 55)
print("")
print("Files written:")
print("  D:/MICC/agent_exit.py")
print("  D:/MICC/morning_brief.py")
print("  D:/MICC/telegram_bot.py (patched)")
print("  D:/MICC/data_pipeline/run_pipeline.py (patched)")
print("")
print("Test now:")
print("  python D:/MICC/agent_exit.py --send")
print("  python D:/MICC/morning_brief.py")
print("")
print("New Telegram commands:")
print("  /conviction  /portfolio  /exit")
