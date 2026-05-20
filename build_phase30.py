#!/usr/bin/env python3
"""
build_phase30.py - Phase 30 orchestrator
Writes cross_asset_compute.py, then writes dashboard files, then patches navbar.
Run: python build_phase30.py
Location: D:/MICC/build_phase30.py
"""

from pathlib import Path
import sqlite3, subprocess, sys, re
from datetime import datetime

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"
DB   = Path("D:/marketDB/db/market.db")

def write(path, content, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print("  [OK] " + label + "  (" + str(len(content.splitlines())) + " lines)")

def log(msg):
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)


# =============================================================================
# [1] CREATE DB TABLES
# =============================================================================
log("[1/5] Creating DB tables...")
conn = sqlite3.connect(DB, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

conn.execute(
    "CREATE TABLE IF NOT EXISTS cross_asset_signals ("
    "date TEXT, signal_name TEXT, asset TEXT, value REAL, signal_type TEXT,"
    "condition_desc TEXT, nifty_fwd_5d REAL, nifty_fwd_10d REAL,"
    "hit_rate_hist REAL, n_historical INTEGER, computed_date TEXT,"
    "PRIMARY KEY (date, signal_name))"
)

conn.execute(
    "CREATE TABLE IF NOT EXISTS my_portfolio ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "symbol TEXT NOT NULL, entry_date TEXT, entry_price REAL,"
    "quantity INTEGER, position_size REAL, atr_at_entry REAL,"
    "stop_loss REAL, target_1 REAL, target_2 REAL, risk_per_trade REAL,"
    "status TEXT DEFAULT 'OPEN', exit_date TEXT, exit_price REAL,"
    "pnl REAL, pnl_pct REAL, notes TEXT,"
    "added_at TEXT DEFAULT (datetime('now')))"
)
conn.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_symbol ON my_portfolio(symbol)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_status ON my_portfolio(status)")
conn.commit()
conn.close()
log("  Tables created: cross_asset_signals, my_portfolio")


# =============================================================================
# [2] WRITE cross_asset_compute.py then run it
# =============================================================================
log("[2/5] Writing and running cross_asset_compute.py...")

cross_script = [
    "import sqlite3, math",
    "from datetime import datetime",
    "import numpy as np",
    "",
    "DB = 'D:/marketDB/db/market.db'",
    "conn = sqlite3.connect(DB, timeout=30)",
    "conn.execute('PRAGMA journal_mode=WAL')",
    "TODAY = datetime.today().strftime('%Y-%m-%d')",
    "",
    "def load_series(symbol, days=504):",
    "    rows = conn.execute(",
    "        'SELECT date, close FROM global_indices_daily WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT ?',",
    "        (symbol, days)",
    "    ).fetchall()",
    "    return list(reversed(rows)) if rows else []",
    "",
    "nifty_rows = load_series('NIFTY50', 504)",
    "nifty_dates = [r[0] for r in nifty_rows]",
    "nifty_closes = [r[1] for r in nifty_rows]",
    "",
    "def nifty_fwd(date_str, days):",
    "    try:",
    "        idx = nifty_dates.index(date_str)",
    "        fi = idx + days",
    "        if fi < len(nifty_rows):",
    "            p0 = nifty_closes[idx]",
    "            p1 = nifty_closes[fi]",
    "            return round((p1 - p0) / p0 * 100, 3)",
    "    except Exception:",
    "        pass",
    "    return None",
    "",
    "def compute_signal(name, asset, values, condition_fn, fwd_days=10):",
    "    if len(values) < 20: return None",
    "    closes = [v[1] for v in values]",
    "    dates  = [v[0] for v in values]",
    "    signal_type, condition_desc = condition_fn(closes)",
    "    if not signal_type: return None",
    "    hits = total = 0",
    "    for i in range(20, len(closes) - fwd_days):",
    "        stype, _ = condition_fn(closes[max(0, i-20):i+1])",
    "        if stype == signal_type:",
    "            fwd = nifty_fwd(dates[i], fwd_days)",
    "            if fwd is not None:",
    "                total += 1",
    "                if fwd > 0: hits += 1",
    "    hit_rate = round(hits / total, 3) if total >= 5 else None",
    "    return {",
    "        'date': dates[-1], 'signal_name': name, 'asset': asset,",
    "        'value': round(closes[-1], 2), 'signal_type': signal_type,",
    "        'condition_desc': condition_desc,",
    "        'nifty_fwd_5d': nifty_fwd(dates[-1], 5),",
    "        'nifty_fwd_10d': nifty_fwd(dates[-1], 10),",
    "        'hit_rate_hist': hit_rate, 'n_historical': total,",
    "        'computed_date': TODAY,",
    "    }",
    "",
    "signals = []",
    "",
    "vix = load_series('VIX')",
    "if vix:",
    "    def vix_cond(closes):",
    "        if len(closes) < 5: return None, None",
    "        cur = closes[-1]",
    "        avg = np.mean(closes[-min(20,len(closes)):])",
    "        if cur > 25: return 'FEAR', 'VIX > 25 (high fear = contrarian buy)'",
    "        if cur > avg * 1.2: return 'SPIKE', 'VIX spike >20pct above 20d avg'",
    "        if cur < 15: return 'CALM', 'VIX < 15 (complacency)'",
    "        return None, None",
    "    s = compute_signal('VIX_REGIME', 'VIX', vix, vix_cond)",
    "    if s: signals.append(s)",
    "",
    "dxy = load_series('DXY')",
    "if dxy:",
    "    def dxy_cond(closes):",
    "        if len(closes) < 20: return None, None",
    "        cur = closes[-1]",
    "        sma20 = np.mean(closes[-20:])",
    "        sma50 = np.mean(closes[-min(50,len(closes)):])",
    "        if cur > sma20 and sma20 > sma50: return 'STRONG', 'DXY above SMA20 and SMA50'",
    "        if cur < sma20 and sma20 < sma50: return 'WEAK', 'DXY below SMA20 and SMA50'",
    "        return None, None",
    "    s = compute_signal('DXY_TREND', 'DXY', dxy, dxy_cond)",
    "    if s: signals.append(s)",
    "",
    "gold = load_series('Gold')",
    "if gold:",
    "    def gold_cond(closes):",
    "        if len(closes) < 20: return None, None",
    "        ret20 = (closes[-1] - closes[-20]) / closes[-20] * 100",
    "        if ret20 > 3: return 'BULLISH', 'Gold up >3pct in 20d (risk-off)'",
    "        if ret20 < -3: return 'BEARISH', 'Gold down >3pct in 20d (risk-on)'",
    "        return None, None",
    "    s = compute_signal('GOLD_TREND', 'Gold', gold, gold_cond)",
    "    if s: signals.append(s)",
    "",
    "usdinr = load_series('USDINR')",
    "if usdinr:",
    "    def usdinr_cond(closes):",
    "        if len(closes) < 20: return None, None",
    "        cur = closes[-1]",
    "        sma20 = np.mean(closes[-20:])",
    "        if cur > sma20 * 1.01: return 'WEAK_INR', 'USDINR above SMA20 (rupee weak)'",
    "        if cur < sma20 * 0.99: return 'STRONG_INR', 'USDINR below SMA20 (rupee strong)'",
    "        return None, None",
    "    s = compute_signal('USDINR_TREND', 'USDINR', usdinr, usdinr_cond)",
    "    if s: signals.append(s)",
    "",
    "spx = load_series('SPX')",
    "if spx:",
    "    def spx_cond(closes):",
    "        if len(closes) < 50: return None, None",
    "        cur = closes[-1]",
    "        sma50 = np.mean(closes[-50:])",
    "        ret5 = (closes[-1] - closes[-5]) / closes[-5] * 100",
    "        if cur > sma50 and ret5 > 1: return 'RISK_ON', 'SPX above SMA50 up >1pct in 5d'",
    "        if cur < sma50 and ret5 < -1: return 'RISK_OFF', 'SPX below SMA50 down >1pct in 5d'",
    "        return None, None",
    "    s = compute_signal('SPX_REGIME', 'SPX', spx, spx_cond)",
    "    if s: signals.append(s)",
    "",
    "us10y = load_series('US10Y')",
    "if us10y:",
    "    def us10y_cond(closes):",
    "        if len(closes) < 20: return None, None",
    "        delta = closes[-1] - closes[-20]",
    "        if delta > 0.2: return 'RISING', 'US10Y up >20bp in 20d (tightening)'",
    "        if delta < -0.2: return 'FALLING', 'US10Y down >20bp in 20d (easing)'",
    "        return None, None",
    "    s = compute_signal('US10Y_TREND', 'US10Y', us10y, us10y_cond)",
    "    if s: signals.append(s)",
    "",
    "conn.execute('DELETE FROM cross_asset_signals WHERE date = ?', (TODAY,))",
    "for s in signals:",
    "    conn.execute(",
    "        'INSERT OR REPLACE INTO cross_asset_signals'",
    "        ' (date, signal_name, asset, value, signal_type, condition_desc,'",
    "        ' nifty_fwd_5d, nifty_fwd_10d, hit_rate_hist, n_historical, computed_date)'",
    "        ' VALUES (?,?,?,?,?,?,?,?,?,?,?)',",
    "        (s['date'], s['signal_name'], s['asset'], s['value'],",
    "         s['signal_type'], s['condition_desc'],",
    "         s['nifty_fwd_5d'], s['nifty_fwd_10d'],",
    "         s['hit_rate_hist'], s['n_historical'], s['computed_date'])",
    "    )",
    "conn.commit()",
    "conn.close()",
    "print('Cross-asset signals: ' + str(len(signals)))",
    "for s in signals:",
    "    hr = str(round(s['hit_rate_hist']*100)) + '%' if s['hit_rate_hist'] else '?'",
    "    print('  ' + s['signal_name'].ljust(16) + ' | ' + str(s['signal_type']).ljust(12) + ' | hit=' + hr + ' n=' + str(s['n_historical']))",
]

compute_path = MICC / "cross_asset_compute.py"
compute_path.write_text("\n".join(cross_script), encoding="utf-8")
log("  Written: cross_asset_compute.py")

result = subprocess.run([sys.executable, str(compute_path)], cwd=str(MICC), capture_output=False)
if result.returncode != 0:
    log("  [WARN] cross_asset_compute.py had errors")


# =============================================================================
# [3] API ROUTES
# =============================================================================
log("[3/5] Writing API routes...")

# -- /api/portfolio/route.ts --
portfolio_api_lines = [
    'import { NextRequest, NextResponse } from "next/server";',
    'import { spawnSync } from "child_process";',
    '',
    'const DB = "D:/marketDB/db/market.db";',
    'const DA = "D:/MICC";',
    'const PY = "C:/Users/marka/AppData/Local/Programs/Python/Python314/python.exe";',
    '',
    'function runPy(script: string): string {',
    '  const r = spawnSync(PY, ["-c", script], { encoding: "utf8", timeout: 20000, cwd: DA });',
    '  if (r.error) throw r.error;',
    '  if (r.stderr) console.error(r.stderr);',
    '  return r.stdout.trim();',
    '}',
    '',
    'export async function GET() {',
    '  const script = [',
    '    "import sqlite3, json, math",',
    '    "def s(v):",',
    '    "    if v is None: return None",',
    '    "    try:",',
    '    "        f = float(v)",',
    '    "        return None if (math.isnan(f) or math.isinf(f)) else round(f,2)",',
    '    "    except: return None",',
    '    "conn = sqlite3.connect(r\\"' + str(DB).replace(chr(92), '/') + '\\", timeout=15)",',
    '    "conn.row_factory = sqlite3.Row",',
    '    "rows = conn.execute(",',
    '    "    \'SELECT p.*, st.close as current_price, sc.conviction_score, sq.f_score\'",',
    '    "    \' FROM my_portfolio p\'",',
    '    "    \' LEFT JOIN (SELECT symbol,close FROM stock_data WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL) AND close IS NOT NULL) st ON st.symbol=p.symbol\'",',
    '    "    \' LEFT JOIN symbol_conviction sc ON sc.symbol=p.symbol\'",',
    '    "    \' LEFT JOIN symbol_quality_scores sq ON sq.symbol=p.symbol\'",',
    '    "    \' ORDER BY p.status, p.added_at DESC\'",',
    '    ").fetchall()",',
    '    "positions = []",',
    '    "for r in rows:",',
    '    "    cur = s(r[\'current_price\']) or s(r[\'entry_price\']) or 0",',
    '    "    ep  = s(r[\'entry_price\']) or 0",',
    '    "    qty = r[\'quantity\'] or 0",',
    '    "    unr = round((cur-ep)*qty,2) if ep and cur else None",',
    '    "    unrp = round((cur-ep)/ep*100,2) if ep and cur else None",',
    '    "    positions.append({\'id\':r[\'id\'],\'symbol\':r[\'symbol\'],\'entry_date\':r[\'entry_date\'],",',
    '    "        \'entry_price\':s(r[\'entry_price\']),\'quantity\':qty,\'position_size\':s(r[\'position_size\']),",',
    '    "        \'atr_at_entry\':s(r[\'atr_at_entry\']),\'stop_loss\':s(r[\'stop_loss\']),",',
    '    "        \'target_1\':s(r[\'target_1\']),\'target_2\':s(r[\'target_2\']),",',
    '    "        \'risk_per_trade\':s(r[\'risk_per_trade\']),\'status\':r[\'status\'],",',
    '    "        \'exit_price\':s(r[\'exit_price\']),\'pnl\':s(r[\'pnl\']),\'pnl_pct\':s(r[\'pnl_pct\']),",',
    '    "        \'current_price\':s(r[\'current_price\']),\'unrealized\':unr,\'unrealized_pct\':unrp,",',
    '    "        \'f_score\':r[\'f_score\'],\'conviction\':s(r[\'conviction_score\'])})",',
    '    "open_pos = [p for p in positions if p[\'status\']==\'OPEN\']",',
    '    "closed_pos = [p for p in positions if p[\'status\']==\'CLOSED\']",',
    '    "sigs = conn.execute(\'SELECT * FROM cross_asset_signals WHERE date=(SELECT MAX(date) FROM cross_asset_signals) ORDER BY signal_name\').fetchall()",',
    '    "conn.close()",',
    '    "ti = sum((p[\'position_size\'] or 0) for p in open_pos)",',
    '    "tu = sum((p[\'unrealized\'] or 0) for p in open_pos)",',
    '    "tr = sum((p[\'pnl\'] or 0) for p in closed_pos)",',
    '    "wins = [p for p in closed_pos if (p[\'pnl\'] or 0)>0]",',
    '    "wr = round(len(wins)/len(closed_pos)*100,1) if closed_pos else None",',
    '    "print(json.dumps({\'positions\':positions,\'cross_asset\':[dict(r) for r in sigs],",',
    '    "    \'summary\':{\'open_count\':len(open_pos),\'closed_count\':len(closed_pos),",',
    '    "    \'total_invested\':round(ti,2),\'total_unrealized\':round(tu,2),",',
    '    "    \'total_realized\':round(tr,2),\'win_rate\':wr}},default=str))",',
    '  ].join("\\n");',
    '  try {',
    '    return NextResponse.json(JSON.parse(runPy(script)));',
    '  } catch (e: any) {',
    '    return NextResponse.json({ error: e.message, positions: [], cross_asset: [], summary: {} }, { status: 500 });',
    '  }',
    '}',
    '',
    'export async function POST(req: NextRequest) {',
    '  const body = await req.json();',
    '  if (body.action === "add") {',
    '    const { symbol, entry_date, entry_price, quantity, atr_at_entry, account_size, risk_pct } = body;',
    '    const ep = parseFloat(entry_price) || 0;',
    '    const atr = parseFloat(atr_at_entry) || 0;',
    '    const acc = parseFloat(account_size) || 500000;',
    '    const rp  = parseFloat(risk_pct) || 1.0;',
    '    const qty = parseInt(quantity) || 0;',
    '    const script = [',
    '      "import sqlite3, json",',
    '      "ep=" + ep + "; atr=" + atr + "; acc=" + acc + "; rp=" + rp + "; qty_in=" + qty,',
    '      "sl = round(ep - 2*atr, 2) if atr > 0 else round(ep*0.95, 2)",',
    '      "rps = ep - sl",',
    '      "ra = acc * rp / 100",',
    '      "qty = qty_in if qty_in > 0 else (int(ra/rps) if rps > 0 else 0)",',
    '      "ps = round(ep*qty, 2)",',
    '      "rpt = round(rps*qty, 2)",',
    '      "t1 = round(ep + 2*atr, 2) if atr > 0 else round(ep*1.06, 2)",',
    '      "t2 = round(ep + 4*atr, 2) if atr > 0 else round(ep*1.12, 2)",',
    '      "conn = sqlite3.connect(r\\"' + str(DB).replace(chr(92), '/') + '\\", timeout=15)",',
    '      "conn.execute(",',
    '      "    \'INSERT INTO my_portfolio (symbol,entry_date,entry_price,quantity,position_size,atr_at_entry,stop_loss,target_1,target_2,risk_per_trade,status) VALUES (?,?,?,?,?,?,?,?,?,?,\\\'OPEN\\\')\',",',
    '      "    (" + JSON.stringify(symbol) + ", " + JSON.stringify(entry_date) + ", ep, qty, ps, atr, sl, t1, t2, rpt))",',
    '      "conn.commit(); conn.close()",',
    '      "print(json.dumps({\'ok\':True,\'qty\':qty,\'stop_loss\':sl,\'target_1\':t1,\'target_2\':t2,\'position_size\':ps,\'risk_per_trade\':rpt}))",',
    '    ].join("\\n");',
    '    try { return NextResponse.json(JSON.parse(runPy(script))); }',
    '    catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }',
    '  }',
    '  if (body.action === "close") {',
    '    const { id, exit_price, exit_date } = body;',
    '    const xp = parseFloat(exit_price) || 0;',
    '    const script = [',
    '      "import sqlite3, json",',
    '      "conn = sqlite3.connect(r\\"' + str(DB).replace(chr(92), '/') + '\\", timeout=15)",',
    '      "conn.row_factory = sqlite3.Row",',
    '      "pos = conn.execute(\'SELECT * FROM my_portfolio WHERE id=?\', (" + id + ",)).fetchone()",',
    '      "ep = pos[\'entry_price\'] or 0; qty = pos[\'quantity\'] or 0",',
    '      "xp = " + xp,',
    '      "pnl = round((xp-ep)*qty, 2)",',
    '      "pnl_pct = round((xp-ep)/ep*100, 2) if ep else 0",',
    '      "conn.execute(\'UPDATE my_portfolio SET status=\\\'CLOSED\\\',exit_date=?,exit_price=?,pnl=?,pnl_pct=? WHERE id=?\', (" + JSON.stringify(exit_date) + ", xp, pnl, pnl_pct, " + id + "))",',
    '      "conn.commit(); conn.close()",',
    '      "print(json.dumps({\'ok\':True,\'pnl\':pnl,\'pnl_pct\':pnl_pct}))",',
    '    ].join("\\n");',
    '    try { return NextResponse.json(JSON.parse(runPy(script))); }',
    '    catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }',
    '  }',
    '  return NextResponse.json({ error: "unknown action" }, { status: 400 });',
    '}',
]

write(SRC / "api" / "portfolio" / "route.ts", "\n".join(portfolio_api_lines), "/api/portfolio/route.ts")

# -- /api/cross-asset/route.ts --
cross_api_lines = [
    'import { NextResponse } from "next/server";',
    'import { spawnSync } from "child_process";',
    '',
    'const DB = "D:/marketDB/db/market.db";',
    'const DA = "D:/MICC";',
    'const PY = "C:/Users/marka/AppData/Local/Programs/Python/Python314/python.exe";',
    '',
    'export async function GET() {',
    '  const script = [',
    '    "import sqlite3, json",',
    '    "conn = sqlite3.connect(r\\"' + str(DB).replace(chr(92), '/') + '\\", timeout=15)",',
    '    "conn.row_factory = sqlite3.Row",',
    '    "rows = conn.execute(\'SELECT * FROM cross_asset_signals WHERE date=(SELECT MAX(date) FROM cross_asset_signals) ORDER BY signal_name\').fetchall()",',
    '    "hist = conn.execute(\'SELECT signal_name, signal_type, COUNT(*) as n, AVG(nifty_fwd_10d) as avg10, AVG(CASE WHEN nifty_fwd_10d>0 THEN 1.0 ELSE 0.0 END) as hr FROM cross_asset_signals WHERE nifty_fwd_10d IS NOT NULL GROUP BY signal_name, signal_type\').fetchall()",',
    '    "conn.close()",',
    '    "print(json.dumps({\'signals\':[dict(r) for r in rows],\'history\':[dict(r) for r in hist]},default=str))",',
    '  ].join("\\n");',
    '  const r = spawnSync(PY, ["-c", script], { encoding: "utf8", timeout: 15000, cwd: DA });',
    '  try { return NextResponse.json(JSON.parse(r.stdout.trim())); }',
    '  catch (e: any) { return NextResponse.json({ error: e.message, signals: [], history: [] }, { status: 500 }); }',
    '}',
]

write(SRC / "api" / "cross-asset" / "route.ts", "\n".join(cross_api_lines), "/api/cross-asset/route.ts")


# =============================================================================
# [4] /portfolio/page.tsx  — written as list of lines to avoid escape issues
# =============================================================================
log("[4/5] Writing /portfolio/page.tsx...")

page_lines = [
    '"use client";',
    'import { useEffect, useState } from "react";',
    '',
    'interface Position {',
    '  id: number; symbol: string; entry_date: string; entry_price: number;',
    '  quantity: number; position_size: number; atr_at_entry: number;',
    '  stop_loss: number; target_1: number; target_2: number;',
    '  risk_per_trade: number; status: string; exit_date?: string;',
    '  exit_price?: number; pnl?: number; pnl_pct?: number;',
    '  current_price?: number; unrealized?: number; unrealized_pct?: number;',
    '  f_score?: number; conviction?: number;',
    '}',
    'interface Signal {',
    '  signal_name: string; asset: string; value: number;',
    '  signal_type: string; condition_desc: string;',
    '  nifty_fwd_5d?: number; nifty_fwd_10d?: number;',
    '  hit_rate_hist?: number; n_historical: number; date: string;',
    '}',
    'interface Summary {',
    '  open_count: number; closed_count: number; total_invested: number;',
    '  total_unrealized: number; total_realized: number; win_rate?: number;',
    '}',
    '',
    'const SIG_COLOR: Record<string,string> = {',
    '  FEAR:"#ef4444",SPIKE:"#f97316",CALM:"#10b981",',
    '  STRONG:"#ef4444",WEAK:"#10b981",',
    '  BULLISH:"#f59e0b",BEARISH:"#3b82f6",',
    '  WEAK_INR:"#ef4444",STRONG_INR:"#10b981",',
    '  RISK_ON:"#10b981",RISK_OFF:"#ef4444",',
    '  RISING:"#ef4444",FALLING:"#10b981",',
    '};',
    'const SIG_IMPACT: Record<string,string> = {',
    '  FEAR:"Contrarian BUY signal for India",',
    '  SPIKE:"Short-term caution, watch for reversal",',
    '  CALM:"Complacency — watch for VIX spike",',
    '  STRONG:"DXY strength = FII headwind for India",',
    '  WEAK:"DXY weak = FII tailwind for India",',
    '  BULLISH:"Risk-off — gold rising, bonds may rally",',
    '  BEARISH:"Risk-on — gold falling, equities bid",',
    '  WEAK_INR:"Rupee weak — FII outflow pressure",',
    '  STRONG_INR:"Rupee strong — FII inflow environment",',
    '  RISK_ON:"Global risk appetite positive for EMs",',
    '  RISK_OFF:"Global risk appetite negative — be cautious",',
    '  RISING:"Rate tightening — valuation headwind",',
    '  FALLING:"Rate easing — valuation tailwind",',
    '};',
    '',
    'function fmt(v?: number|null, d=1) { return v==null?"–":v.toFixed(d); }',
    'function pc(v?: number|null) { return v==null?"#9ca3af":v>=0?"#10b981":"#ef4444"; }',
    'function pstr(v?: number|null) { return v==null?"–":(v>=0?"+":"")+v!.toFixed(1)+"%"; }',
    '',
    'function StatBox({label,value,color}:{label:string;value:string|number;color:string}) {',
    '  return <div style={{background:"#161b22",border:"1px solid #30363d",borderRadius:8,padding:"10px 16px",flex:1,minWidth:100}}>',
    '    <div style={{color:"#6b7280",fontSize:10,textTransform:"uppercase",letterSpacing:1}}>{label}</div>',
    '    <div style={{color,fontSize:18,fontWeight:700}}>{value}</div>',
    '  </div>;',
    '}',
    '',
    'function AddForm({onAdd}:{onAdd:()=>void}) {',
    '  const [f,setF] = useState({symbol:"",entry_date:new Date().toISOString().slice(0,10),entry_price:"",quantity:"",atr_at_entry:"",account_size:"500000",risk_pct:"1.0"});',
    '  const [res,setRes] = useState<any>(null);',
    '  const [loading,setLoading] = useState(false);',
    '  const set=(k:string,v:string)=>setF(p=>({...p,[k]:v}));',
    '  const inp=(ph:string,k:string,t="text")=>(',
    '    <input placeholder={ph} type={t} value={(f as any)[k]} onChange={e=>set(k,e.target.value)}',
    '      style={{background:"#1f2937",border:"1px solid #374151",borderRadius:6,color:"#f9fafb",padding:"7px 12px",fontSize:13,width:"100%",outline:"none"}}/>',
    '  );',
    '  const submit=async()=>{',
    '    setLoading(true);',
    '    const r=await fetch("/api/portfolio",{method:"POST",headers:{"Content-Type":"application/json"},',
    '      body:JSON.stringify({action:"add",...f,entry_price:parseFloat(f.entry_price),quantity:parseInt(f.quantity)||0,atr_at_entry:parseFloat(f.atr_at_entry)||0,account_size:parseFloat(f.account_size),risk_pct:parseFloat(f.risk_pct)})});',
    '    const d=await r.json(); setRes(d); setLoading(false); if(d.ok) onAdd();',
    '  };',
    '  return <div style={{background:"#161b22",border:"1px solid #30363d",borderRadius:10,padding:16,marginBottom:20}}>',
    '    <div style={{color:"#9ca3af",fontSize:11,marginBottom:12,textTransform:"uppercase",letterSpacing:1}}>Add Position (ATR Position Sizing)</div>',
    '    <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:10}}>',
    '      {inp("Symbol","symbol")}{inp("Entry Date","entry_date","date")}',
    '      {inp("Entry Price","entry_price","number")}{inp("ATR 14d (0=skip)","atr_at_entry","number")}',
    '    </div>',
    '    <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:12}}>',
    '      {inp("Qty (0=auto)","quantity","number")}{inp("Account Size INR","account_size","number")}',
    '      {inp("Risk % per trade","risk_pct","number")}',
    '      <button onClick={submit} disabled={loading} style={{background:"#6366f1",color:"#fff",border:"none",borderRadius:6,padding:"7px 16px",fontSize:13,cursor:"pointer",fontWeight:700}}>',
    '        {loading?"Adding...":"Add Position"}',
    '      </button>',
    '    </div>',
    '    {res&&<div style={{background:res.ok?"#0f2a1a":"#2d1b1b",border:"1px solid "+(res.ok?"#10b981":"#ef4444"),borderRadius:6,padding:"10px 14px",fontSize:12}}>',
    '      {res.ok?<span style={{color:"#10b981"}}>Added! Qty={res.qty} | Stop=INR{res.stop_loss} | T1=INR{res.target_1} | T2=INR{res.target_2} | Risk=INR{res.risk_per_trade}</span>',
    '             :<span style={{color:"#ef4444"}}>Error: {res.error}</span>}',
    '    </div>}',
    '  </div>;',
    '}',
    '',
    'export default function PortfolioPage() {',
    '  const [data,setData]=useState<{positions:Position[];cross_asset:Signal[];summary:Summary}|null>(null);',
    '  const [loading,setLoading]=useState(true);',
    '  const [tab,setTab]=useState<"open"|"closed"|"signals">("open");',
    '  const [closing,setClosing]=useState<number|null>(null);',
    '  const [exitPrice,setExitPrice]=useState("");',
    '',
    '  const load=()=>{setLoading(true);fetch("/api/portfolio").then(r=>r.json()).then(d=>{setData(d);setLoading(false);});};',
    '  useEffect(()=>{load();},[]);',
    '',
    '  const closePos=async(id:number)=>{',
    '    const r=await fetch("/api/portfolio",{method:"POST",headers:{"Content-Type":"application/json"},',
    '      body:JSON.stringify({action:"close",id,exit_price:parseFloat(exitPrice),exit_date:new Date().toISOString().slice(0,10)})});',
    '    const d=await r.json(); if(d.ok){setClosing(null);setExitPrice("");load();}',
    '  };',
    '',
    '  const open=data?.positions.filter(p=>p.status==="OPEN")||[];',
    '  const closed=data?.positions.filter(p=>p.status==="CLOSED")||[];',
    '  const s=data?.summary;',
    '',
    '  return <div style={{minHeight:"100vh",background:"#0d1117",color:"#f9fafb",fontFamily:"Inter,sans-serif",padding:"24px 20px"}}>',
    '    <div style={{marginBottom:20}}>',
    '      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:4}}>',
    '        <span style={{fontSize:24}}>{"\\u{1F4BC}"}</span>',
    '        <h1 style={{margin:0,fontSize:22,fontWeight:700}}>Portfolio Tracker</h1>',
    '        <span style={{background:"#1e3a5f",color:"#60a5fa",fontSize:11,padding:"2px 10px",borderRadius:20,fontWeight:600}}>PHASE 30</span>',
    '      </div>',
    '      <p style={{margin:0,color:"#9ca3af",fontSize:13}}>ATR position sizing · Cross-asset regime signals · Conviction overlay</p>',
    '    </div>',
    '',
    '    {s&&<div style={{display:"flex",gap:12,marginBottom:20,flexWrap:"wrap"}}>',
    '      <StatBox label="Open" value={s.open_count} color="#f9fafb"/>',
    '      <StatBox label="Invested" value={"INR"+(s.total_invested/1000).toFixed(0)+"K"} color="#6366f1"/>',
    '      <StatBox label="Unrealized" value={(s.total_unrealized>=0?"+":"")+s.total_unrealized.toFixed(0)} color={pc(s.total_unrealized)}/>',
    '      <StatBox label="Realized" value={(s.total_realized>=0?"+":"")+s.total_realized.toFixed(0)} color={pc(s.total_realized)}/>',
    '      <StatBox label="Win Rate" value={s.win_rate!=null?s.win_rate+"%":"–"} color="#f59e0b"/>',
    '      <StatBox label="Closed" value={s.closed_count} color="#9ca3af"/>',
    '    </div>}',
    '',
    '    <AddForm onAdd={load}/>',
    '',
    '    <div style={{display:"flex",gap:4,marginBottom:16}}>',
    '      {(["open","closed","signals"] as const).map(t=>(',
    '        <button key={t} onClick={()=>setTab(t)} style={{background:tab===t?"#6366f1":"#1f2937",color:tab===t?"#fff":"#9ca3af",border:"1px solid "+(tab===t?"#6366f1":"#374151"),borderRadius:8,padding:"7px 20px",fontSize:13,cursor:"pointer",fontWeight:tab===t?700:400}}>',
    '          {t==="open"?"Open ("+open.length+")":t==="closed"?"Closed ("+closed.length+")":"Cross-Asset Signals"}',
    '        </button>',
    '      ))}',
    '    </div>',
    '',
    '    {loading&&<div style={{textAlign:"center",padding:40,color:"#6b7280"}}>Loading...</div>}',
    '',
    '    {!loading&&tab==="open"&&<div style={{overflowX:"auto",borderRadius:10,border:"1px solid #30363d"}}>',
    '      <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>',
    '        <thead><tr style={{background:"#161b22",borderBottom:"1px solid #30363d"}}>',
    '          {["Symbol","Entry","Qty","Entry","CMP","Unreal","Unreal%","Stop","T1","T2","Risk","Conv","F","Action"].map(h=>',
    '            <th key={h} style={{padding:"8px 10px",color:"#6b7280",fontSize:11,fontWeight:400,textAlign:"right",whiteSpace:"nowrap"}}>{h}</th>',
    '          )}',
    '        </tr></thead>',
    '        <tbody>',
    '          {open.map(p=>(',
    '            <tr key={p.id} style={{borderBottom:"1px solid #1f2937"}}>',
    '              <td style={{padding:"8px 10px",color:"#e2e8f0",fontWeight:700}}>{p.symbol}</td>',
    '              <td style={{padding:"8px 10px",color:"#9ca3af",fontSize:11,textAlign:"right"}}>{p.entry_date?.slice(5)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right"}}>{p.quantity}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right"}}>{"INR"+fmt(p.entry_price)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:"#60a5fa"}}>{"INR"+fmt(p.current_price)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:pc(p.unrealized)}}>{p.unrealized!=null?(p.unrealized>=0?"+":"")+fmt(p.unrealized,0):"–"}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:pc(p.unrealized_pct)}}>{pstr(p.unrealized_pct)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:"#ef4444"}}>{"INR"+fmt(p.stop_loss)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:"#10b981"}}>{"INR"+fmt(p.target_1)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:"#34d399"}}>{"INR"+fmt(p.target_2)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:"#f59e0b"}}>{"INR"+fmt(p.risk_per_trade,0)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:"#6366f1"}}>{fmt(p.conviction,0)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right"}}>{p.f_score!=null?p.f_score+"/9":"–"}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right"}}>',
    '                {closing===p.id?<span style={{display:"flex",gap:4}}>',
    '                  <input value={exitPrice} onChange={e=>setExitPrice(e.target.value)} placeholder="Exit" type="number"',
    '                    style={{width:70,background:"#1f2937",border:"1px solid #374151",borderRadius:4,color:"#f9fafb",padding:"3px 6px",fontSize:12}}/>',
    '                  <button onClick={()=>closePos(p.id)} style={{background:"#10b981",color:"#fff",border:"none",borderRadius:4,padding:"3px 8px",fontSize:11,cursor:"pointer"}}>OK</button>',
    '                  <button onClick={()=>setClosing(null)} style={{background:"#374151",color:"#fff",border:"none",borderRadius:4,padding:"3px 8px",fontSize:11,cursor:"pointer"}}>X</button>',
    '                </span>:<button onClick={()=>setClosing(p.id)} style={{background:"#1f2937",color:"#9ca3af",border:"1px solid #374151",borderRadius:4,padding:"3px 10px",fontSize:11,cursor:"pointer"}}>Close</button>}',
    '              </td>',
    '            </tr>',
    '          ))}',
    '          {open.length===0&&<tr><td colSpan={14} style={{textAlign:"center",padding:30,color:"#6b7280"}}>No open positions. Add one above.</td></tr>}',
    '        </tbody>',
    '      </table>',
    '    </div>}',
    '',
    '    {!loading&&tab==="closed"&&<div style={{overflowX:"auto",borderRadius:10,border:"1px solid #30363d"}}>',
    '      <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>',
    '        <thead><tr style={{background:"#161b22",borderBottom:"1px solid #30363d"}}>',
    '          {["Symbol","Entry","Exit","Qty","Entry","Exit","P&L","P&L%"].map(h=><th key={h} style={{padding:"8px 10px",color:"#6b7280",fontSize:11,fontWeight:400,textAlign:"right"}}>{h}</th>)}',
    '        </tr></thead>',
    '        <tbody>',
    '          {closed.map(p=>(',
    '            <tr key={p.id} style={{borderBottom:"1px solid #1f2937"}}>',
    '              <td style={{padding:"8px 10px",color:"#e2e8f0",fontWeight:700}}>{p.symbol}</td>',
    '              <td style={{padding:"8px 10px",color:"#9ca3af",fontSize:11,textAlign:"right"}}>{p.entry_date?.slice(5)}</td>',
    '              <td style={{padding:"8px 10px",color:"#9ca3af",fontSize:11,textAlign:"right"}}>{p.exit_date?.slice(5)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right"}}>{p.quantity}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right"}}>{"INR"+fmt(p.entry_price)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right"}}>{"INR"+fmt(p.exit_price)}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:pc(p.pnl)}}>{p.pnl!=null?(p.pnl>=0?"+":"")+fmt(p.pnl,0):"–"}</td>',
    '              <td style={{padding:"8px 10px",textAlign:"right",color:pc(p.pnl_pct)}}>{pstr(p.pnl_pct)}</td>',
    '            </tr>',
    '          ))}',
    '          {closed.length===0&&<tr><td colSpan={8} style={{textAlign:"center",padding:30,color:"#6b7280"}}>No closed trades yet.</td></tr>}',
    '        </tbody>',
    '      </table>',
    '    </div>}',
    '',
    '    {!loading&&tab==="signals"&&<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))",gap:12}}>',
    '      {(data?.cross_asset||[]).map(sig=>{',
    '        const color=SIG_COLOR[sig.signal_type]||"#9ca3af";',
    '        const impact=SIG_IMPACT[sig.signal_type]||"";',
    '        const hr=sig.hit_rate_hist;',
    '        return <div key={sig.signal_name} style={{background:"#161b22",border:"1px solid #30363d",borderLeft:"3px solid "+color,borderRadius:10,padding:16}}>',
    '          <div style={{display:"flex",justifyContent:"space-between",marginBottom:8}}>',
    '            <div style={{color:"#9ca3af",fontSize:11,fontWeight:700}}>{sig.asset}</div>',
    '            <div style={{background:color+"22",color,fontSize:10,padding:"2px 8px",borderRadius:10,fontWeight:700}}>{sig.signal_type}</div>',
    '          </div>',
    '          <div style={{color:"#f9fafb",fontSize:14,fontWeight:700,marginBottom:4}}>{sig.signal_name.replace(/_/g," ")}</div>',
    '          <div style={{color:"#9ca3af",fontSize:12,marginBottom:6}}>{sig.condition_desc}</div>',
    '          <div style={{color,fontSize:11,fontStyle:"italic",marginBottom:10}}>{impact}</div>',
    '          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:6}}>',
    '            {[["VALUE",fmt(sig.value,2),"#f9fafb"],["HIT RATE",hr!=null?(hr*100).toFixed(0)+"%":"–",hr!=null?(hr>0.6?"#10b981":hr>0.4?"#f59e0b":"#ef4444"):"#6b7280"],["NIFTY FWD10",sig.nifty_fwd_10d!=null?(sig.nifty_fwd_10d>0?"+":"")+fmt(sig.nifty_fwd_10d)+"%":"–",pc(sig.nifty_fwd_10d)]].map(([lbl,val,col])=>(',
    '              <div key={lbl as string} style={{background:"#1f2937",borderRadius:6,padding:"6px 8px"}}>',
    '                <div style={{color:"#6b7280",fontSize:9}}>{lbl}</div>',
    '                <div style={{color:col as string,fontSize:13,fontWeight:700}}>{val}</div>',
    '              </div>',
    '            ))}',
    '          </div>',
    '          <div style={{marginTop:8,color:"#4b5563",fontSize:10}}>n={sig.n_historical} | as of {sig.date}</div>',
    '        </div>;',
    '      })}',
    '      {(data?.cross_asset||[]).length===0&&<div style={{color:"#6b7280",padding:40,gridColumn:"1/-1",textAlign:"center"}}>No signals yet. Run build_phase30.py first.</div>}',
    '    </div>}',
    '  </div>;',
    '}',
]

write(SRC / "portfolio" / "page.tsx", "\n".join(page_lines), "/portfolio/page.tsx")


# =============================================================================
# [5] NAVBAR PATCH
# =============================================================================
log("[5/5] Patching NavBar...")

navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p
    break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")
    changed = False
    if "/conviction" not in src:
        matches = list(re.finditer(r"href['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", src))
        if matches:
            last_pos = matches[-1].end()
            le = src.find("\n", last_pos)
            if le < 0: le = len(src)
            src = src[:le] + "\n  { href: '/conviction', label: 'CONVICTION' }," + src[le:]
            changed = True
            log("  Added /conviction")
    if "/portfolio" not in src:
        matches = list(re.finditer(r"href['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", src))
        if matches:
            last_pos = matches[-1].end()
            le = src.find("\n", last_pos)
            if le < 0: le = len(src)
            src = src[:le] + "\n  { href: '/portfolio', label: 'PORTFOLIO' }," + src[le:]
            changed = True
            log("  Added /portfolio")
    if changed:
        navbar_path.write_text(src, encoding="utf-8")
        log("  NavBar saved: " + str(navbar_path))
    else:
        log("  NavBar already up to date")
else:
    log("  [WARN] NavBar.tsx not found under " + str(DASH))

print("")
print("=" * 55)
print("PHASE 30 COMPLETE")
print("=" * 55)
print("  cross_asset_signals  - 6 macro signals computed")
print("  my_portfolio         - table created")
print("  /api/portfolio       - GET + POST (add/close)")
print("  /api/cross-asset     - GET signals")
print("  /portfolio/page.tsx  - 3 tabs: open/closed/signals")
print("  NavBar               - /conviction + /portfolio added")
print("")
print("Visit:")
print("  http://localhost:3000/conviction")
print("  http://localhost:3000/portfolio")
