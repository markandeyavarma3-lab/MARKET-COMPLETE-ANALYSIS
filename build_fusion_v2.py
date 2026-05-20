# -*- coding: utf-8 -*-
r"""
build_fusion_v2.py  --  Run from D:\MICC
"""
from pathlib import Path
import subprocess, sys

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path, content, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

# =============================================================================
# [1]  agent_fusion.py  -- built as a list of lines, no triple-quote conflicts
# =============================================================================
print("\n[1/3] Writing agent_fusion.py ...")

lines = [
    "# -*- coding: utf-8 -*-",
    "import json, sys, sqlite3",
    "from pathlib import Path",
    "from datetime import datetime",
    "",
    r'DA         = Path(r"D:\MICC")',
    r'DB_PATH    = r"D:\marketDB\db\market.db"',
    'OUTPUT_DIR = DA / "agents" / "fusion"',
    "OUTPUT_DIR.mkdir(parents=True, exist_ok=True)",
    'send = "--send" in sys.argv',
    "",
    "def now_ist():",
    "    from datetime import timezone, timedelta",
    '    return datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime("%Y-%m-%d %H:%M IST")',
    "",
    "def read_report(name):",
    '    p = DA / "agents" / name / "last_report.json"',
    "    if not p.exists(): return {}",
    '    try: return json.loads(p.read_text(encoding="utf-8"))',
    "    except: return {}",
    "",
    "def qdb(sql, params=()):",
    "    try:",
    "        conn = sqlite3.connect(DB_PATH, timeout=15)",
    "        conn.row_factory = sqlite3.Row",
    "        rows = conn.execute(sql, params).fetchall()",
    "        conn.close()",
    "        return [dict(r) for r in rows]",
    "    except Exception as e:",
    '        print(f"  [DB ERR] {e}")',
    "        return []",
    "",
    "def extract_symbols(report, label):",
    "    out = []",
    "    if not report: return out",
    "    for key, val in report.items():",
    "        if isinstance(val, list):",
    "            for item in val:",
    "                if isinstance(item, dict):",
    '                    sym = item.get("symbol") or item.get("ticker") or ""',
    "                    sym = str(sym).strip().upper()",
    "                    if sym and 2 <= len(sym) <= 20 and sym.replace('-','').replace('&','').isalnum():",
    '                        reason = (item.get("reason") or item.get("signal") or',
    '                                  item.get("note") or item.get("screen") or label)',
    "                        out.append((sym, str(reason)))",
    "    return out",
    "",
    "AGENTS = [",
    '    ("alpha",   "Macro/Regime"),',
    '    ("beta",    "Momentum"),',
    '    ("gamma",   "Options/GEX"),',
    '    ("delta",   "Sectors"),',
    '    ("epsilon", "FII/DII"),',
    '    ("zeta",    "Watchlist"),',
    '    ("eta",     "Insider/Corp"),',
    '    ("iota",    "Global Intel"),',
    "]",
    "",
    "print('Fusion agent starting...')",
    "sym_layers   = {}",
    "sym_reasons  = {}",
    "agent_status = {}",
    "",
    "for agent_key, label in AGENTS:",
    "    report = read_report(agent_key)",
    "    pairs  = extract_symbols(report, label)",
    "    seen   = set()",
    "    for sym, reason in pairs:",
    "        if sym in seen: continue",
    "        seen.add(sym)",
    "        sym_layers.setdefault(sym, []).append(agent_key)",
    "        sym_reasons.setdefault(sym, []).append(f'[{agent_key}] {reason}')",
    "    agent_status[agent_key] = len(seen)",
    "    print(f'  {agent_key:10} -> {len(seen)} symbols')",
    "",
    "# signals_history",
    "sigs = qdb('SELECT symbol, screen_tags FROM signals_history '",
    "           'WHERE run_date=(SELECT MAX(run_date) FROM signals_history)')",
    "for s in sigs:",
    "    sym = (s.get('symbol') or '').strip().upper()",
    "    if sym:",
    "        sym_layers.setdefault(sym, []).append('engine')",
    "        sym_reasons.setdefault(sym, []).append(f'[engine] {s.get(\"screen_tags\",\"signal\")}')",
    "print(f'  {\"engine\":10} -> {len(sigs)} symbols')",
    "",
    "# watchlist",
    'wl_file = DA / "micc_watchlist.json"',
    "if wl_file.exists():",
    "    try:",
    '        wl = json.loads(wl_file.read_text(encoding="utf-8"))',
    '        wl_syms = wl.get("symbols", [])',
    "        for item in wl_syms:",
    '            sym = (item if isinstance(item, str) else item.get("symbol",""")).strip().upper()',
    "            if sym:",
    '                sym_layers.setdefault(sym, []).append("watchlist")',
    '                sym_reasons.setdefault(sym, []).append("[watchlist] manually tracked")',
    "        print(f'  {\"watchlist\":10} -> {len(wl_syms)} symbols')",
    "    except: pass",
    "",
    "# Build picks (2+ layers)",
    "picks = []",
    "for sym, layers in sym_layers.items():",
    "    n = len(set(layers))",
    "    if n < 2: continue",
    "    ul = list(dict.fromkeys(layers))",
    "    picks.append({",
    '        "symbol":           sym,',
    '        "total_score":      float(n),',
    '        "n_layers":         n,',
    '        "layers_fired":     ul,',
    '        "reasons":          sym_reasons.get(sym, []),',
    '        "beta_score":       1.0 if "beta"    in layers else 0.0,',
    '        "regime_score":     1.0 if "alpha"   in layers else 0.0,',
    '        "insider_score":    1.0 if "eta"     in layers else 0.0,',
    '        "watchlist_score":  1.0 if any(x in layers for x in ["zeta","watchlist"]) else 0.0,',
    '        "seasonal_score":   1.0 if "engine"  in layers else 0.0,',
    '        "conviction_score": 1.0 if "epsilon" in layers else 0.0,',
    '        "quant_score":      1.0 if any(x in layers for x in ["gamma","delta","iota"]) else 0.0,',
    "    })",
    "",
    "picks.sort(key=lambda x: -x['total_score'])",
    "print(f'\\n  Fusion picks (2+ layers): {len(picks)}')",
    "for p in picks[:10]:",
    "    print(f'    {p[\"symbol\"]:15} n={p[\"n_layers\"]}  {p[\"layers_fired\"]}')",
    "",
    "# Regime",
    "nr = qdb(\"SELECT closing_index_value AS close FROM market_snapshot \"",
    "         \"WHERE index_name='NIFTY 50' ORDER BY date DESC LIMIT 1\")",
    "nifty  = float(nr[0]['close']) if nr else 0",
    'regime = "BULLISH" if nifty>22000 else "SIDEWAYS" if nifty>18000 else "BEARISH" if nifty>0 else "UNKNOWN"',
    "",
    "report = {",
    '    "agent":        "fusion",',
    '    "date":         datetime.now().strftime("%Y-%m-%d"),',
    '    "generated_at": now_ist(),',
    '    "picks":        picks,',
    '    "meta": {',
    '        "total_picks":  len(picks),',
    '        "regime":       regime,',
    '        "nifty":        round(nifty, 2),',
    '        "agents_run":   sum(1 for v in agent_status.values() if v > 0),',
    '        "agent_status": agent_status,',
    "    },",
    "}",
    "",
    'out = OUTPUT_DIR / "last_report.json"',
    'out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")',
    'print(f"  Saved: {out}")',
    "",
    "if send:",
    "    try:",
    "        import re, urllib.request",
    "        env  = (DA / '.env').read_text()",
    "        BOT  = re.search(r'TELEGRAM_TOKEN=([^\\n]+)', env).group(1).strip()",
    "        CHAT = re.search(r'TELEGRAM_CHAT_ID=([^\\n]+)', env).group(1).strip()",
    "        lines2 = [f'FUSION PICKS - {datetime.now().strftime(\"%d %b\")}', '']",
    "        lines2 += [f'Regime: {regime}  Nifty: {nifty:,.0f}', f'Picks (2+ layers): {len(picks)}', '']",
    "        for p in picks[:15]:",
    "            tag = ' '.join(f'[{l[:3].upper()}]' for l in p['layers_fired'])",
    "            lines2.append(f'{p[\"symbol\"]:12} {p[\"n_layers\"]}L  {tag}')",
    "        msg  = '\\n'.join(lines2)",
    "        data = json.dumps({'chat_id':CHAT,'text':msg}).encode()",
    "        req  = urllib.request.Request(",
    "            f'https://api.telegram.org/bot{BOT}/sendMessage', data=data,",
    "            headers={'Content-Type':'application/json'})",
    "        urllib.request.urlopen(req, timeout=10)",
    "        print('  Telegram: OK')",
    "    except Exception as e:",
    "        print(f'  Telegram: {e}')",
    "",
    "print('Done.')",
]

# fix the stray smart-quote that crept in
agent_src = "\n".join(lines)
agent_src = agent_src.replace('\u201c', '"').replace('\u201d', '"')
write(MICC / "agent_fusion.py", agent_src, "agent_fusion.py")


# =============================================================================
# [2]  /api/fusion/route.ts
# =============================================================================
print("\n[2/3] Writing /api/fusion/route.ts ...")

api = (
    'import { NextResponse } from "next/server";\n'
    'import { spawnSync }    from "child_process";\n'
    'import { readFileSync } from "fs";\n'
    'import { Buffer }       from "buffer";\n'
    '\n'
    'const DA = "D:/MICC";\n'
    'const PY = "py";\n'
    '\n'
    'function san(s: string) {\n'
    '  return s.replace(/:[ \\t]*NaN\\b/g,": null").replace(/:[ \\t]*-?Infinity\\b/g,": null");\n'
    '}\n'
    'function qdb(sql: string, params: (string|number)[] = []): any[] {\n'
    '  const payload = Buffer.from(JSON.stringify({ sql, params })).toString("base64");\n'
    "  const script = [\n"
    "    \"import sqlite3,json,base64,sys\",\n"
    "    \"d=json.loads(base64.b64decode(sys.argv[1]))\",\n"
    "    \"conn=sqlite3.connect(r'D:/marketDB/db/market.db',timeout=15)\",\n"
    "    \"conn.row_factory=sqlite3.Row\",\n"
    "    \"rows=conn.execute(d['sql'],d['params']).fetchall()\",\n"
    "    \"print(json.dumps([dict(r) for r in rows],default=str))\",\n"
    "    \"conn.close()\",\n"
    "  ].join(\"\\n\");\n"
    '  const r = spawnSync(PY,["-c",script,payload],{cwd:DA,encoding:"utf-8",timeout:20000});\n'
    '  if(r.status!==0){console.error("[fusion]",r.stderr?.slice(0,200));return[];}\n'
    '  try{return JSON.parse(san(r.stdout.trim()||"[]"));}catch{return[];}\n'
    '}\n'
    '\n'
    'export const dynamic = "force-dynamic";\n'
    '\n'
    'export async function GET() {\n'
    '  let report: any = null;\n'
    '  try {\n'
    '    report = JSON.parse(san(readFileSync(`${DA}/agents/fusion/last_report.json`,"utf-8")));\n'
    '  } catch {\n'
    '    return NextResponse.json({\n'
    '      picks:[],meta:null,regime:"UNKNOWN",nifty:0,n_total:0,\n'
    '      error:"Run: py D:/MICC/agent_fusion.py",\n'
    '      generated_at:new Date().toISOString(),\n'
    '    });\n'
    '  }\n'
    '\n'
    '  const picks: any[] = report.picks ?? [];\n'
    '  const meta          = report.meta  ?? {};\n'
    '\n'
    '  if (picks.length === 0) {\n'
    '    return NextResponse.json({\n'
    '      picks:[],meta,regime:meta.regime??"UNKNOWN",nifty:meta.nifty??0,n_total:0,\n'
    '      error:"No picks with 2+ layers. Run all agents then agent_fusion.py.",\n'
    '      generated_at:new Date().toISOString(),\n'
    '    });\n'
    '  }\n'
    '\n'
    '  const syms = picks.map((p:any)=>p.symbol);\n'
    '  const ph   = syms.map(()=>"?").join(",");\n'
    '\n'
    '  const techs = qdb(\n'
    '    `SELECT symbol,rsi_14,adx_14,macd_line,macd_signal,\n'
    '            ROUND(CAST(atr_14_pct AS REAL),2) AS atr_14_pct,\n'
    '            ROUND(CAST(pct_from_52w_high AS REAL),1) AS pct_52h\n'
    '     FROM symbol_technicals WHERE symbol IN (${ph})`,syms);\n'
    '  const tMap:Record<string,any>={};\n'
    '  for(const t of techs) tMap[t.symbol]=t;\n'
    '\n'
    '  const prices = qdb(\n'
    '    `SELECT symbol,close FROM stock_data\n'
    '     WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)\n'
    '       AND symbol IN (${ph}) AND close IS NOT NULL`,syms);\n'
    '  const pMap:Record<string,number>={};\n'
    '  for(const p of prices) pMap[p.symbol]=parseFloat(p.close);\n'
    '\n'
    '  const pats = qdb(\n'
    "    `SELECT symbol,direction,\n"
    "            ROUND(CAST(mean_ret AS REAL),2) AS mean_ret,\n"
    "            ROUND(CAST(accuracy AS REAL)*100,1) AS win_pct,window_days\n"
    "     FROM seasonality_patterns_v3\n"
    "     WHERE anchor_mm_dd=strftime('%m-%d','now','localtime')\n"
    "       AND fdr_reject=1 AND n_obs>=10 AND symbol IN (${ph})\n"
    '     ORDER BY CAST(score_v2 AS REAL) DESC`,syms);\n'
    '  const patMap:Record<string,any>={};\n'
    '  for(const p of pats){if(!patMap[p.symbol])patMap[p.symbol]=p;}\n'
    '\n'
    "  const nr=qdb(\"SELECT closing_index_value AS close FROM market_snapshot WHERE index_name='NIFTY 50' ORDER BY date DESC LIMIT 1\");\n"
    '  const nifty=parseFloat(nr[0]?.close??meta.nifty??"0");\n'
    '  const regime=nifty>22000?"BULLISH":nifty>18000?"SIDEWAYS":nifty>0?"BEARISH":(meta.regime??"UNKNOWN");\n'
    '\n'
    '  const enriched=picks.map((p:any)=>{\n'
    '    const t=tMap[p.symbol]??{};\n'
    '    return{\n'
    '      ...p,\n'
    '      rsi_14:   t.rsi_14??null,\n'
    '      adx_14:   t.adx_14??null,\n'
    '      atr_pct:  t.atr_14_pct??null,\n'
    '      pct_52h:  t.pct_52h??null,\n'
    '      macd_bull:(t.macd_line??0)>(t.macd_signal??0),\n'
    '      price:    pMap[p.symbol]??null,\n'
    '      today_pat:patMap[p.symbol]??null,\n'
    '    };\n'
    '  });\n'
    '\n'
    '  return NextResponse.json({\n'
    '    picks:enriched,meta,\n'
    '    report_date:report.date??report.generated_at??null,\n'
    '    regime,nifty,n_total:enriched.length,\n'
    '    generated_at:new Date().toISOString(),\n'
    '  });\n'
    '}\n'
)

write(SRC / "api" / "fusion" / "route.ts", api, "/api/fusion/route.ts")


# =============================================================================
# [3]  Run agent_fusion.py now
# =============================================================================
print("\n[3/3] Running agent_fusion.py ...")
r = subprocess.run(
    [sys.executable, str(MICC / "agent_fusion.py")],
    capture_output=True, text=True, timeout=60, cwd=str(MICC)
)
if r.stdout: print(r.stdout[-2000:])
if r.returncode != 0: print(f"  [ERR] {r.stderr[:400]}")

print("""
======================================================================
  DONE  -- fusion v2
======================================================================
  RESTART:
    cd D:\\MICC\\micc-dashboard && npm run dev
  OPEN:
    http://localhost:3000/fusion
""")
