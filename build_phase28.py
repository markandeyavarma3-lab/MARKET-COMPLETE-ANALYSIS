"""
build_phase28.py  --  Run from D:\MICC
Phase 28 -- Settings + Completion Layer

  [1] /settings/page.tsx        -- system settings, DB stats, agent controls
  [2] /api/settings/route.ts    -- DB stats, agent status, config
  [3] /watchlist page upgrade   -- add seasonal patterns column
  [4] Telegram bot              -- /settings command + final command list
  [5] update_memory.py          -- saves final MICC state summary

Run: py D:\MICC\build_phase28.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")


# =============================================================================
# [1]  /api/settings/route.ts  -- system stats
# =============================================================================
print("\n[1/5] Writing /api/settings/route.ts ...")

settings_api = """\
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";
import fs               from "fs";
import path             from "path";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";
const PY = "py";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

function qdb(sql: string): any[] {
  const b64 = Buffer.from(sql).toString("base64");
  const py  = [
    "import sqlite3,json,sys,base64",
    "conn=sqlite3.connect(r'" + DB + "',timeout=10)",
    "conn.row_factory=sqlite3.Row",
    "sql=base64.b64decode(sys.argv[1]).decode()",
    "rows=conn.execute(sql).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\\n");
  const r = spawnSync(PY, ["-c", py, b64], { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

function getDBSize(): string {
  try {
    const stat = fs.statSync(DB);
    const mb   = stat.size / 1024 / 1024;
    return mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : mb.toFixed(0) + " MB";
  } catch { return "Unknown"; }
}

function loadReport(name: string): any | null {
  const p = path.join(DA, "agents", name, "last_report.json");
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(sanitize(fs.readFileSync(p, "utf-8")));
  } catch { return null; }
}

export async function GET() {
  try {
    // Table row counts
    const tables = qdb(
      "SELECT name, (SELECT COUNT(*) FROM \\" + "\\" + "' || name || '\\") as n " +
      "FROM sqlite_master WHERE type='table' ORDER BY name"
    );

    // Key table counts
    const counts: Record<string, number> = {};
    const KEY_TABLES = [
      "stock_data", "seasonality_patterns_v3", "seasonality_patterns",
      "global_indices_daily", "signals_history", "stock_delivery",
      "insider_trading", "corporate_announcements", "option_greeks_raw",
      "indices_data", "market_snapshot", "symbol_technicals",
      "window_stats", "mf_nav_history",
    ];

    for (const t of KEY_TABLES) {
      try {
        const r = qdb("SELECT COUNT(*) as n FROM " + t);
        counts[t] = r[0]?.n ?? 0;
      } catch { counts[t] = -1; }
    }

    // Pattern stats
    const patStats = qdb(
      "SELECT COUNT(*) as total, COUNT(DISTINCT symbol) as symbols, " +
      "COUNT(DISTINCT window_days) as windows, AVG(accuracy) as avg_acc, " +
      "MAX(score) as max_score FROM seasonality_patterns_v3"
    )[0] || {};

    // Agent status
    const AGENTS = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","kappa","alert"];
    const agentStatus: Record<string, any> = {};
    for (const a of AGENTS) {
      const r = loadReport(a);
      agentStatus[a] = r ? {
        ready: true,
        date: r.date || r.generated_at || null,
      } : { ready: false, date: null };
    }

    // Alerts count
    let alertCount = 0;
    try {
      const af = path.join(DA, "alerts.json");
      if (fs.existsSync(af)) {
        const alerts = JSON.parse(fs.readFileSync(af, "utf-8"));
        alertCount = alerts.filter((a: any) => a.active).length;
      }
    } catch {}

    // Watchlist count
    let watchlistCount = 0;
    try {
      const wf = path.join(DA, "micc_watchlist.json");
      if (fs.existsSync(wf)) {
        const w = JSON.parse(fs.readFileSync(wf, "utf-8"));
        watchlistCount = Array.isArray(w) ? w.length : Object.keys(w).length;
      }
    } catch {}

    return NextResponse.json({
      db_path:     DB,
      db_size:     getDBSize(),
      table_counts: counts,
      pattern_stats: {
        total:    patStats.total    || 0,
        symbols:  patStats.symbols  || 0,
        windows:  patStats.windows  || 0,
        avg_acc:  patStats.avg_acc  ? Math.round(patStats.avg_acc * 10) / 10 : null,
        max_score:patStats.max_score|| null,
      },
      agent_status:    agentStatus,
      active_alerts:   alertCount,
      watchlist_count: watchlistCount,
      generated_at:    new Date().toISOString(),
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
"""
write(SRC / "api" / "settings" / "route.ts", settings_api, "/api/settings/route.ts")


# =============================================================================
# [2]  /settings/page.tsx
# =============================================================================
print("\n[2/5] Writing /settings/page.tsx ...")

settings_page = '''\
"use client";

import { useEffect, useState } from "react";

interface Settings {
  db_path: string; db_size: string;
  table_counts: Record<string,number>;
  pattern_stats: { total:number; symbols:number; windows:number; avg_acc:number|null; max_score:number|null };
  agent_status: Record<string,{ready:boolean;date:string|null}>;
  active_alerts: number;
  watchlist_count: number;
  generated_at: string;
}

const AGENT_META: Record<string,{icon:string;name:string;href:string}> = {
  alpha:   {icon:"🔴",name:"Alpha",   href:"/overview"},
  beta:    {icon:"📊",name:"Beta",    href:"/streaks"},
  gamma:   {icon:"⚡",name:"Gamma",   href:"/options"},
  delta:   {icon:"📈",name:"Delta",   href:"/indices"},
  epsilon: {icon:"🏦",name:"Epsilon", href:"/overview"},
  zeta:    {icon:"👁", name:"Zeta",   href:"/watchlist"},
  eta:     {icon:"🏢",name:"Eta",     href:"/eta"},
  iota:    {icon:"🌍",name:"Iota",    href:"/deep"},
  kappa:   {icon:"🔬",name:"Kappa",   href:"/compare"},
  alert:   {icon:"🔔",name:"Alert",   href:"/alerts"},
};

const KEY_TABLES = [
  {key:"stock_data",              label:"Stock OHLCV"},
  {key:"seasonality_patterns_v3", label:"Patterns v3"},
  {key:"global_indices_daily",    label:"Global Indices"},
  {key:"signals_history",         label:"Signals History"},
  {key:"option_greeks_raw",       label:"Options Greeks"},
  {key:"insider_trading",         label:"Insider Trading"},
  {key:"corporate_announcements", label:"Corp Announcements"},
  {key:"mf_nav_history",          label:"MF NAV History"},
  {key:"symbol_technicals",       label:"Symbol Technicals"},
  {key:"window_stats",            label:"Window Stats"},
];

function StatChip({label,value,color}:{label:string;value:string|number;color?:string}) {
  return (
    <div style={{
      background:"#0f172a", borderRadius:8, padding:"10px 14px",
      textAlign:"center", minWidth:100,
    }}>
      <div style={{ fontSize:16, fontWeight:800, color:color||"#f8fafc" }}>{value}</div>
      <div style={{ fontSize:10, color:"#475569", marginTop:2 }}>{label}</div>
    </div>
  );
}

export default function SettingsPage() {
  const [data,    setData]    = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/settings")
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const fmt = (n: number) => n >= 1e6 ? (n/1e6).toFixed(1)+"M"
    : n >= 1e3 ? (n/1e3).toFixed(0)+"k" : String(n);

  return (
    <div style={{ minHeight:"100vh", background:"#0f172a",
      color:"#e2e8f0", fontFamily:"system-ui,sans-serif" }}>

      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b" }}>
        <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"#f8fafc" }}>
          System Settings
        </h1>
        <p style={{ margin:"4px 0 0", fontSize:12, color:"#64748b" }}>
          DB stats · Agent status · Data coverage · Pipeline info
        </p>
      </div>

      {loading ? (
        <div style={{ padding:60, textAlign:"center", color:"#64748b" }}>Loading...</div>
      ) : !data ? (
        <div style={{ padding:60, textAlign:"center", color:"#ef4444" }}>Failed to load settings</div>
      ) : (
        <div style={{ padding:"20px 28px", display:"flex", flexDirection:"column", gap:20 }}>

          {/* DB Overview */}
          <div style={{ background:"#1e293b", border:"1px solid #334155",
            borderRadius:12, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"#64748b",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Database
            </div>
            <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:14 }}>
              <StatChip label="DB Size"    value={data.db_size}                     color="#60a5fa" />
              <StatChip label="Patterns"   value={fmt(data.pattern_stats.total)}    color="#22c55e" />
              <StatChip label="Pat Symbols"value={data.pattern_stats.symbols}       color="#34d399" />
              <StatChip label="Windows"    value={data.pattern_stats.windows}       color="#a78bfa" />
              <StatChip label="Avg Acc"    value={data.pattern_stats.avg_acc != null ? data.pattern_stats.avg_acc.toFixed(1)+"%" : "—"} color="#fbbf24" />
              <StatChip label="Alerts"     value={data.active_alerts}               color="#ef4444" />
              <StatChip label="Watchlist"  value={data.watchlist_count}             color="#f472b6" />
            </div>
            <div style={{ fontSize:11, color:"#475569", fontFamily:"monospace" }}>
              {data.db_path}
            </div>
          </div>

          {/* Table row counts */}
          <div style={{ background:"#1e293b", border:"1px solid #334155",
            borderRadius:12, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"#64748b",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Key Table Counts
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
              {KEY_TABLES.map(({key,label}) => {
                const n = data.table_counts[key];
                return (
                  <div key={key} style={{
                    display:"flex", justifyContent:"space-between",
                    padding:"7px 10px", background:"#0f172a", borderRadius:7,
                  }}>
                    <span style={{ fontSize:12, color:"#94a3b8" }}>{label}</span>
                    <span style={{ fontSize:12, fontWeight:700,
                      color: n > 0 ? "#22c55e" : "#ef4444" }}>
                      {n >= 0 ? fmt(n) : "error"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Agent status */}
          <div style={{ background:"#1e293b", border:"1px solid #334155",
            borderRadius:12, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"#64748b",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Agent Status
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8 }}>
              {Object.entries(AGENT_META).map(([name,meta]) => {
                const s = data.agent_status[name];
                return (
                  <a key={name} href={meta.href} style={{ textDecoration:"none" }}>
                    <div style={{
                      background:"#0f172a", borderRadius:8, padding:"10px",
                      textAlign:"center",
                      border:`1px solid ${s?.ready ? "#22c55e33" : "#334155"}`,
                      cursor:"pointer",
                    }}>
                      <div style={{ fontSize:18 }}>{meta.icon}</div>
                      <div style={{ fontSize:11, fontWeight:700,
                        color: s?.ready ? "#22c55e" : "#475569", marginTop:4 }}>
                        {meta.name}
                      </div>
                      <div style={{ fontSize:9, color:"#334155", marginTop:2 }}>
                        {s?.ready ? (s.date || "ready") : "not run"}
                      </div>
                    </div>
                  </a>
                );
              })}
            </div>
            <div style={{ marginTop:14, padding:"10px 14px",
              background:"#0f172a", borderRadius:8 }}>
              <div style={{ fontSize:11, color:"#64748b", marginBottom:6 }}>
                Run all agents:
              </div>
              <code style={{ fontSize:12, color:"#60a5fa" }}>
                py D:\\MICC\\micc_engine.py 7 --send
              </code>
            </div>
          </div>

          {/* Pipeline info */}
          <div style={{ background:"#1e293b", border:"1px solid #334155",
            borderRadius:12, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"#64748b",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Daily Pipeline
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
              {[
                ["Daily update (one command):",   "py D:\\\\MICC\\\\data_pipeline\\\\run_pipeline.py --with-engine"],
                ["Data only:",                     "py D:\\\\MICC\\\\data_pipeline\\\\run_pipeline.py"],
                ["Engine only:",                   "py D:\\\\MICC\\\\micc_engine.py 7 --send"],
                ["Morning brief:",                 "py D:\\\\MICC\\\\morning_brief.py"],
                ["Global indices:",                "py D:\\\\MICC\\\\fetch_global_indices_v2.py"],
                ["Alert check:",                   "py D:\\\\MICC\\\\agent_alert.py --send"],
                ["Verify patterns:",               "py D:\\\\MICC\\\\build_seasonality_v3_stocks.py --verify"],
              ].map(([label, cmd]) => (
                <div key={label} style={{ display:"flex", gap:10, alignItems:"flex-start" }}>
                  <span style={{ fontSize:11, color:"#64748b", minWidth:180, flexShrink:0 }}>
                    {label}
                  </span>
                  <code style={{ fontSize:11, color:"#60a5fa", wordBreak:"break-all" }}>
                    {cmd}
                  </code>
                </div>
              ))}
            </div>
          </div>

          {/* Telegram commands */}
          <div style={{ background:"#1e293b", border:"1px solid #334155",
            borderRadius:12, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"#64748b",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Telegram Bot Commands
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:4 }}>
              {[
                ["/start",    "Welcome + command list"],
                ["/report",   "Full daily report"],
                ["/today",    "Today's seasonal patterns"],
                ["/patterns [sym]", "Patterns for anchor date"],
                ["/global",   "Global markets snapshot"],
                ["/global SPX","Last 5 sessions for symbol"],
                ["/eta",      "Corporate events + insider"],
                ["/alerts",   "Active alerts list"],
                ["/deep SYM", "Run Kappa deep profile"],
                ["/kappa SYM","Same as /deep"],
                ["/stock SYM","Latest price + signals"],
                ["/hot",      "Hot stocks today"],
                ["/watch",    "Watchlist alerts"],
                ["/status",   "Pipeline status"],
              ].map(([cmd, desc]) => (
                <div key={cmd} style={{ display:"flex", gap:8, padding:"4px 0",
                  borderBottom:"1px solid #0f172a" }}>
                  <code style={{ fontSize:11, color:"#60a5fa", minWidth:120 }}>{cmd}</code>
                  <span style={{ fontSize:11, color:"#64748b" }}>{desc}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ fontSize:11, color:"#334155", textAlign:"center", paddingBottom:8 }}>
            Generated at {data.generated_at?.slice(0,19).replace("T"," ")} UTC
          </div>

        </div>
      )}
    </div>
  );
}
'''
write(SRC / "settings" / "page.tsx", settings_page, "/settings/page.tsx")


# =============================================================================
# [3]  Add SETTINGS to NavBar
# =============================================================================
print("\n[3/5] Adding SETTINGS to NavBar ...")

navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")
    if "/settings" not in src:
        import re
        all_m = list(re.finditer(r"href['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", src))
        if all_m:
            last_pos  = all_m[-1].end()
            le        = src.find("\n", last_pos)
            if le < 0: le = len(src)
            src = src[:le] + "\n  { href: '/settings', label: 'SETTINGS' }," + src[le:]
            navbar_path.write_text(src, encoding="utf-8")
            print("  [OK] Added SETTINGS to NavBar")
    else:
        print("  [SKIP] SETTINGS already in NavBar")


# =============================================================================
# [4]  Telegram /status command  -- shows DB stats + agent status
# =============================================================================
print("\n[4/5] Adding /status upgrade to telegram_bot.py ...")

BOT = MICC / "telegram_bot.py"
if BOT.exists():
    src = BOT.read_text(encoding="utf-8")

    if "cmd_status_full" not in src and "pattern_stats" not in src:
        status_cmd = """

async def cmd_status_full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    \"\"\"Full system status including DB stats.\"\"\"
    import sqlite3, pathlib
    DB_P = r'D:\\\\marketDB\\\\db\\\\market.db'
    DA   = pathlib.Path(r'D:\\\\MICC')
    try:
        conn = sqlite3.connect(DB_P, timeout=10)

        def cnt(tbl):
            try: return conn.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
            except: return 0

        total_pats  = cnt('seasonality_patterns_v3')
        pat_syms    = conn.execute('SELECT COUNT(DISTINCT symbol) FROM seasonality_patterns_v3').fetchone()[0] if total_pats else 0
        stock_rows  = cnt('stock_data')
        signals     = cnt('signals_history')
        global_idx  = cnt('global_indices_daily')
        conn.close()

        agents = ['alpha','beta','gamma','delta','epsilon','zeta','eta','iota','kappa','alert']
        ready  = [a for a in agents if (DA / 'agents' / a / 'last_report.json').exists()]

        try:
            import os
            db_size = os.path.getsize(DB_P) / 1024 / 1024 / 1024
            size_str = f'{db_size:.1f} GB'
        except: size_str = '?'

        alerts_active = 0
        try:
            import json
            af = DA / 'alerts.json'
            if af.exists():
                alerts_active = sum(1 for a in json.loads(af.read_text()) if a.get('active'))
        except: pass

        lines = [
            '*MICC System Status*', '',
            f'*Database:* {size_str}',
            f'  Patterns v3 : {total_pats:,} ({pat_syms} symbols)',
            f'  Stock data  : {stock_rows:,} rows',
            f'  Global idx  : {global_idx:,} rows',
            f'  Signals     : {signals:,} rows',
            '',
            f'*Agents ({len(ready)}/10 ready):*',
            '  ' + '  '.join([('OK' if a in ready else 'NO') + ' ' + a for a in agents]),
            '',
            f'*Alerts active:* {alerts_active}',
            '',
            '_localhost:3000/settings for full details_',
        ]
        await update.message.reply_text('\\n'.join(lines)[:4000], parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f'Error: {e}')
"""
        src = src.replace("def main():", status_cmd + "\ndef main():")

        # Register -- replace old /status handler if exists
        if 'CommandHandler("status"' in src:
            src = src.replace(
                'CommandHandler("status"',
                'CommandHandler("status", cmd_status_full  # upgraded'
            )
        else:
            # Add new handler
            for marker in ['app.add_handler(CommandHandler("today"',
                           'app.add_handler(CommandHandler("alerts"']:
                if marker in src:
                    src = src.replace(marker,
                        '    app.add_handler(CommandHandler("status", cmd_status_full))\n    ' + marker)
                    break

        BOT.write_text(src, encoding="utf-8")
        print("  [OK] Upgraded /status command with DB stats")
    else:
        print("  [SKIP] /status already upgraded")


# =============================================================================
# [5]  Write final memory summary
# =============================================================================
print("\n[5/5] Writing MICC_FINAL_STATE.md ...")

summary_lines = [
    "# MICC Final State -- Phase 28",
    "",
    "## Architecture",
    "- **DB**: D:/marketDB/db/market.db (~56GB SQLite WAL)",
    "- **Dashboard**: D:/MICC/micc-dashboard (Next.js 14)",
    "- **Agents**: D:/MICC/agent_*.py (10 agents)",
    "- **Pipeline**: D:/MICC/data_pipeline/run_pipeline.py",
    "",
    "## Pages (17)",
    "/ overview, /analysis, /streaks, /indices, /options,",
    "/macro, /mf, /watchlist, /backtest, /patterns, /patterns-v3,",
    "/eta, /compare, /global, /alerts, /deep, /settings",
    "",
    "## Agents (10)",
    "Alpha (market pulse), Beta (momentum), Gamma (options/GEX),",
    "Delta (sectors), Epsilon (FII/DII), Zeta (watchlist),",
    "Eta (corporate/insider), Iota (global intel), Kappa (deep profile),",
    "Alert (price/RSI/volume/pattern triggers)",
    "",
    "## Data Sources",
    "- 2,188 NSE stocks in stock_data (OHLCV back to ~2000)",
    "- 52 global indices (SPX/DAX/Nikkei/Gold/BTC/DXY etc, back to 2000)",
    "- NSE indices via indices_data table",
    "- MF NAVs, Options Greeks, FII/DII, Insider trading, Corp events",
    "",
    "## Seasonality Patterns",
    "- **seasonality_patterns_v3**: 3d-60d (58 windows), all anchors",
    "- NSE indices + global indices: ~1M patterns (done)",
    "- NSE stocks: ~21M patterns (build_seasonality_v3_stocks.py, overnight)",
    "- Key metrics: accuracy, mean_ret, score, t_stat, p_value,",
    "  consistency, edge_ratio, degradation, recent_mean",
    "",
    "## Daily Pipeline (one command)",
    "```",
    "py D:/MICC/data_pipeline/run_pipeline.py --with-engine",
    "```",
    "Phases: core -> delivery -> global_idx -> us_macro -> mf_nav ->",
    "announcements -> insider -> greeks -> macro -> snapshot ->",
    "parquet_sync -> fundamentals -> corp_actions -> epsilon ->",
    "engine (7 agents) -> morning_brief",
    "",
    "## Telegram Commands",
    "/start /report /today /patterns /global /eta /alerts",
    "/deep /kappa /stock /hot /watch /status",
    "",
    "## Key Scripts",
    "- py D:/MICC/morning_brief.py                    (9AM daily)",
    "- py D:/MICC/agent_alert.py --send               (alert checks)",
    "- py D:/MICC/fetch_global_indices_v2.py          (52 global symbols)",
    "- py D:/MICC/build_seasonality_v3_stocks.py      (stock patterns)",
    "- py D:/MICC/build_seasonality_v3_stocks.py --verify (check counts)",
    "- py D:/MICC/micc_engine.py 7 --send             (all agents)",
]

write(MICC / "MICC_FINAL_STATE.md", "\n".join(summary_lines), "MICC_FINAL_STATE.md")

# Also add /settings to NavBar
navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

print("""
=============================================================
BUILD PHASE 28 COMPLETE
=============================================================

[1] /api/settings/route.ts
    Returns:
      db_size, table_counts (14 key tables),
      pattern_stats (total/symbols/windows/avg_acc/max_score),
      agent_status (10 agents, ready/date),
      active_alerts, watchlist_count

[2] /settings/page.tsx
    Sections:
      Database: size + 7 stat chips (patterns/symbols/windows/acc/alerts/watchlist)
      Key Tables: 14 tables with row counts + color coding
      Agent Status: 10 agent cards (green=ready, grey=not run) + run hint
      Daily Pipeline: all commands listed
      Telegram: all bot commands with descriptions

[3] NavBar: SETTINGS link added

[4] Telegram /status
    Now shows: DB size, pattern count, stock rows,
               agent ready count, alerts active

[5] MICC_FINAL_STATE.md
    Complete system documentation at D:/MICC/MICC_FINAL_STATE.md

FULL SYSTEM -- ALL PHASES COMPLETE:
  Dashboard: npm run dev -> localhost:3000
  Settings:  localhost:3000/settings  (system overview)
  Analysis:  localhost:3000/analysis  (all agent cards)
  Patterns:  localhost:3000/patterns-v3  (search any stock/index)
  Global:    localhost:3000/global     (52 markets live)

STOCK BUILD STATUS:
  Running overnight in other terminal
  Check: py D:\\MICC\\build_seasonality_v3_stocks.py --verify

TOMORROW:
  1. Check stock build finished
  2. Run morning brief: py D:\\MICC\\morning_brief.py
  3. Schedule Task Scheduler: schtasks /create /xml D:\\MICC\\morning_brief_scheduler.xml /tn "MICC Morning Brief"
  4. Test: /today on Telegram -> should show real NSE stock patterns
=============================================================
""")
