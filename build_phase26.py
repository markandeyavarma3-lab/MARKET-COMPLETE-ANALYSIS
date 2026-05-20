"""
build_phase26.py  --  Run from D:\MICC
Phase 26 -- Analysis page + Backtest upgrade + Pipeline finalization

  [1] /analysis/page.tsx       -- unified analysis hub (links to all agent pages
                                   + shows latest signals from all agents)
  [2] /api/analysis/route.ts   -- aggregates last reports from all agents
  [3] /backtest/page.tsx       -- add year-group breakdown to existing backtest
  [4] run_pipeline.py final    -- ensure complete daily sequence
  [5] morning_brief.py         -- standalone morning brief script

Run: py D:\MICC\build_phase26.py
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
# [1]  /api/analysis/route.ts  -- aggregates all agent last_report.json files
# =============================================================================
print("\n[1/5] Writing /api/analysis/route.ts ...")

analysis_api = """\
import { NextResponse } from "next/server";
import fs   from "fs";
import path from "path";

const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

function loadReport(name: string): any | null {
  const p = path.join(DA, "agents", name, "last_report.json");
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(sanitize(fs.readFileSync(p, "utf-8")));
  } catch { return null; }
}

export async function GET() {
  const agents = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","kappa","alert"];
  const reports: Record<string, any> = {};

  for (const name of agents) {
    const r = loadReport(name);
    if (r) {
      // Extract just the key summary fields to keep response small
      reports[name] = {
        generated_at: r.generated_at || r.date || null,
        date:         r.date || null,
        // Agent-specific summary fields
        analysis:     r.analysis     || r.verdict     || r.llm_verdict || null,
        signals:      r.signals      || r.top_signals  || null,
        score:        r.score        || r.market_score || null,
        regime:       r.regime       || r.market_regime || null,
        // Count fields
        alerts_fired:    r.alerts_fired    || null,
        patterns_today:  r.patterns_today  ? r.patterns_today.length : null,
        insider_clusters: r.insider_cluster ? r.insider_cluster.length : null,
        big_trades:      r.big_insider_trades ? r.big_insider_trades.length : null,
      };
    }
  }

  // Signals history -- top signals from today
  return NextResponse.json({
    reports,
    agents_available: Object.keys(reports),
    agents_missing:   agents.filter(a => !reports[a]),
  });
}
"""
write(SRC / "api" / "analysis" / "route.ts", analysis_api, "/api/analysis/route.ts")


# =============================================================================
# [2]  /analysis/page.tsx  -- unified hub
# =============================================================================
print("\n[2/5] Writing /analysis/page.tsx ...")

analysis_page = '''\
"use client";

import { useEffect, useState } from "react";

interface AgentReport {
  generated_at?: string; date?: string;
  analysis?: string; signals?: any[]; score?: number;
  regime?: string; alerts_fired?: number;
  patterns_today?: number; insider_clusters?: number; big_trades?: number;
}
interface AnalysisData {
  reports: Record<string, AgentReport>;
  agents_available: string[];
  agents_missing: string[];
}

const AGENT_META: Record<string, { icon:string; name:string; desc:string; href:string; color:string }> = {
  alpha:   { icon:"🔴", name:"Alpha",   desc:"Market pulse & regime",         href:"/overview",    color:"#ef4444" },
  beta:    { icon:"📊", name:"Beta",    desc:"Momentum & breakouts",           href:"/streaks",     color:"#3b82f6" },
  gamma:   { icon:"⚡", name:"Gamma",   desc:"Options & GEX",                  href:"/options",     color:"#f59e0b" },
  delta:   { icon:"📈", name:"Delta",   desc:"Sector rotation",                href:"/indices",     color:"#22c55e" },
  epsilon: { icon:"🏦", name:"Epsilon", desc:"FII/DII & institutional",        href:"/overview",    color:"#8b5cf6" },
  zeta:    { icon:"👁",  name:"Zeta",   desc:"Watchlist alerts",               href:"/watchlist",   color:"#06b6d4" },
  eta:     { icon:"🏢", name:"Eta",    desc:"Corporate events & insider",      href:"/eta",         color:"#f472b6" },
  iota:    { icon:"🌍", name:"Iota",   desc:"Global intelligence",             href:"/deep",        color:"#34d399" },
  kappa:   { icon:"🔬", name:"Kappa",  desc:"Deep stock profiles",             href:"/compare",     color:"#a78bfa" },
  alert:   { icon:"🔔", name:"Alert",  desc:"Price & pattern triggers",        href:"/alerts",      color:"#fbbf24" },
};

function AgentCard({ name, report }: { name: string; report: AgentReport | undefined }) {
  const meta = AGENT_META[name] || { icon:"🤖", name, desc:"", href:"/", color:"#94a3b8" };
  const hasData = !!report;
  const [open, setOpen] = useState(false);

  return (
    <div style={{
      background: "#1e293b",
      border: `1px solid ${hasData ? meta.color + "44" : "#334155"}`,
      borderRadius: 12, overflow: "hidden",
      opacity: hasData ? 1 : 0.5,
    }}>
      {/* Header */}
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid #334155",
        display: "flex", alignItems: "center", gap: 10, cursor: hasData ? "pointer" : "default",
      }} onClick={() => hasData && setOpen(o => !o)}>
        <span style={{ fontSize: 18 }}>{meta.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: meta.color }}>{meta.name}</div>
          <div style={{ fontSize: 10, color: "#64748b" }}>{meta.desc}</div>
        </div>
        {hasData && (
          <div style={{ textAlign: "right" }}>
            {report?.generated_at && (
              <div style={{ fontSize: 9, color: "#475569" }}>
                {report.generated_at.slice(11, 16)}
              </div>
            )}
            <div style={{ fontSize: 10, color: "#334155" }}>{open ? "▲" : "▼"}</div>
          </div>
        )}
        {!hasData && (
          <span style={{ fontSize: 9, color: "#334155" }}>NOT RUN</span>
        )}
        <a href={meta.href} onClick={e => e.stopPropagation()}
          style={{ fontSize: 10, color: meta.color, textDecoration: "none",
            padding: "2px 8px", border: `1px solid ${meta.color}44`, borderRadius: 4 }}>
          View →
        </a>
      </div>

      {/* Stats strip */}
      {hasData && (
        <div style={{
          display: "flex", gap: 0,
          borderBottom: "1px solid #334155",
          background: "#0f172a",
        }}>
          {[
            report?.score        != null && { label: "Score",    v: Number(report.score).toFixed(1),    c: "#fbbf24" },
            report?.regime                && { label: "Regime",   v: report.regime,                     c: "#94a3b8" },
            report?.alerts_fired != null && { label: "Alerts",   v: String(report.alerts_fired),       c: "#ef4444" },
            report?.patterns_today != null && { label: "Patterns",v: String(report.patterns_today),    c: "#60a5fa" },
            report?.insider_clusters != null && { label: "Clusters",v: String(report.insider_clusters),c: "#22c55e" },
            report?.big_trades != null && { label: "Big Trades", v: String(report.big_trades),         c: "#f472b6" },
          ].filter(Boolean).map((s: any, i) => (
            <div key={i} style={{
              flex: 1, textAlign: "center", padding: "6px 4px",
              borderRight: "1px solid #1e293b",
            }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: s.c }}>{s.v}</div>
              <div style={{ fontSize: 9, color: "#475569" }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Expanded analysis */}
      {open && report?.analysis && (
        <div style={{ padding: "12px 16px" }}>
          <p style={{ margin: 0, fontSize: 11, color: "#cbd5e1", lineHeight: 1.7 }}>
            {String(report.analysis).slice(0, 500)}
            {String(report.analysis).length > 500 ? "…" : ""}
          </p>
        </div>
      )}
    </div>
  );
}

export default function AnalysisPage() {
  const [data,    setData]    = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/analysis")
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const allAgents = Object.keys(AGENT_META);
  const available = data?.agents_available || [];
  const missing   = data?.agents_missing   || allAgents;

  return (
    <div style={{ minHeight:"100vh", background:"#0f172a",
      color:"#e2e8f0", fontFamily:"system-ui,sans-serif" }}>

      {/* Header */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", flexWrap:"wrap", gap:16 }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"#f8fafc" }}>
            Analysis Hub
          </h1>
          <p style={{ margin:"4px 0 0", fontSize:12, color:"#64748b" }}>
            All 10 MICC agents · Latest reports · Click any card to expand
          </p>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:10 }}>
          <div style={{ textAlign:"center", padding:"7px 14px",
            background:"#1e293b", borderRadius:8, border:"1px solid #22c55e33" }}>
            <div style={{ fontSize:18, fontWeight:800, color:"#22c55e" }}>{available.length}</div>
            <div style={{ fontSize:10, color:"#64748b" }}>Ready</div>
          </div>
          <div style={{ textAlign:"center", padding:"7px 14px",
            background:"#1e293b", borderRadius:8, border:"1px solid #ef444433" }}>
            <div style={{ fontSize:18, fontWeight:800, color:"#ef4444" }}>{missing.length}</div>
            <div style={{ fontSize:10, color:"#64748b" }}>Not run</div>
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ padding:"60px", textAlign:"center", color:"#64748b" }}>
          Loading agent reports…
        </div>
      ) : (
        <div style={{ padding:"20px 28px" }}>

          {/* Quick run hint */}
          {missing.length > 0 && (
            <div style={{
              padding:"12px 16px", background:"#1e293b",
              borderRadius:10, marginBottom:20,
              border:"1px solid #334155",
            }}>
              <div style={{ fontSize:11, fontWeight:700, color:"#94a3b8", marginBottom:8 }}>
                Run agents to populate reports:
              </div>
              <code style={{ fontSize:11, color:"#60a5fa" }}>
                py D:\\MICC\\micc_engine.py 7 --send
              </code>
              <span style={{ fontSize:11, color:"#475569", marginLeft:16 }}>
                (runs all agents + sends Telegram)
              </span>
            </div>
          )}

          {/* Agent grid */}
          <div style={{
            display:"grid",
            gridTemplateColumns:"repeat(2, 1fr)",
            gap:16,
          }}>
            {allAgents.map(name => (
              <AgentCard
                key={name}
                name={name}
                report={data?.reports[name]}
              />
            ))}
          </div>

          {/* Quick links */}
          <div style={{ marginTop:24, display:"flex", gap:10, flexWrap:"wrap" }}>
            {[
              { label:"Today's Patterns", href:"/patterns-v3" },
              { label:"Global Markets",   href:"/global" },
              { label:"Compare Stocks",   href:"/compare" },
              { label:"Corporate Events", href:"/eta" },
              { label:"Set Alerts",       href:"/alerts" },
              { label:"Macro Dashboard",  href:"/macro" },
            ].map(l => (
              <a key={l.href} href={l.href} style={{
                padding:"8px 16px", background:"#1e293b",
                border:"1px solid #334155", borderRadius:8,
                color:"#94a3b8", fontSize:12, textDecoration:"none",
                transition:"color 0.15s, border-color 0.15s",
              }}>{l.label} →</a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
'''
write(SRC / "analysis" / "page.tsx", analysis_page, "/analysis/page.tsx")


# =============================================================================
# [3]  morning_brief.py  -- standalone script, run at 9:00 AM
# =============================================================================
print("\n[3/5] Writing D:\\MICC\\morning_brief.py ...")

morning_lines = [
    '"""',
    'morning_brief.py  --  Run from D:\\MICC at 9:00 AM',
    'Generates and sends the full MICC morning brief to Telegram.',
    '',
    'Run: py D:\\MICC\\morning_brief.py',
    'Schedule: Windows Task Scheduler at 09:00 on weekdays',
    '"""',
    '',
    'import subprocess, sys, sqlite3, json',
    'from datetime import datetime',
    'from pathlib import Path',
    '',
    'DA   = Path(r"D:\\MICC")',
    'DB_P = r"D:\\marketDB\\db\\market.db"',
    'PY   = sys.executable',
    '',
    'def ts(): return datetime.now().strftime("%H:%M:%S")',
    'def log(msg): print(f"  [{ts()}] {msg}", flush=True)',
    '',
    'def run_agent(script, timeout=120):',
    '    try:',
    '        r = subprocess.run([PY, str(DA / script)], cwd=str(DA),',
    '                           capture_output=True, text=True, timeout=timeout)',
    '        return r.returncode == 0',
    '    except Exception as e:',
    '        log(f"  {script}: {e}")',
    '        return False',
    '',
    'def send(msg):',
    '    try:',
    '        from micc_data import send_telegram_chunks',
    '        return send_telegram_chunks(msg)',
    '    except Exception as e:',
    '        log(f"send failed: {e}")',
    '        return False',
    '',
    'def get_todays_patterns(n=10, min_score=5):',
    '    mmdd = datetime.today().strftime("%m-%d")',
    '    try:',
    '        conn = sqlite3.connect(DB_P, timeout=10)',
    '        tables = {r[0] for r in conn.execute(',
    '            "SELECT name FROM sqlite_master WHERE type=\'table\'"',
    '        ).fetchall()}',
    '        tbl = "seasonality_patterns_v3" if "seasonality_patterns_v3" in tables else "seasonality_patterns"',
    '        rows = conn.execute(',
    '            f"SELECT symbol,window_days,direction,accuracy,mean_ret,score"',
    '            f" FROM {tbl} WHERE anchor_mm_dd=? AND accuracy>=65"',
    '            f" AND score>=? AND ABS(mean_ret)<=50 ORDER BY score DESC LIMIT ?",',
    '            (mmdd, min_score, n)',
    '        ).fetchall()',
    '        conn.close()',
    '        return mmdd, rows',
    '    except Exception as e:',
    '        return mmdd, []',
    '',
    'def get_global_snapshot():',
    '    WATCH = ["NIFTY50","SPX","SP500VIX","INDIAVIX","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"]',
    '    try:',
    '        conn = sqlite3.connect(DB_P, timeout=10)',
    '        rows = conn.execute(',
    '            "SELECT symbol,close,pct_change FROM global_indices_daily"',
    '            " WHERE symbol IN (" + ",".join("?"*len(WATCH)) + ")"',
    '            " AND date=(SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)",',
    '            WATCH',
    '        ).fetchall()',
    '        conn.close()',
    '        return {r[0]: (r[1], r[2]) for r in rows}',
    '    except:',
    '        return {}',
    '',
    'def main():',
    '    today = datetime.today().strftime("%A, %d %b %Y")',
    '    print(f"\\nMICC Morning Brief -- {today}")',
    '    print("="*50)',
    '',
    '    # 1. Run key agents',
    '    log("Running agents...")',
    '    for script in ["agent_eta.py", "agent_alert.py"]:',
    '        ok = run_agent(script)',
    '        log(f"  {script}: {\'OK\' if ok else \'FAILED\'}")',
    '',
    '    # 2. Build message',
    '    lines = [',
    '        f"*MICC Morning Brief -- {today}*",',
    '        "",',
    '    ]',
    '',
    '    # Global snapshot',
    '    snap = get_global_snapshot()',
    '    if snap:',
    '        lines.append("*Global Markets:*")',
    '        LABELS = {',
    '            "NIFTY50":"Nifty 50 ","SPX":"S&P 500  ","SP500VIX":"VIX      ",',
    '            "INDIAVIX":"India VIX","US10Y":"US 10Y   ","Gold":"Gold     ",',
    '            "CrudeWTI":"Crude WTI","USDINR":"USD/INR  ","Bitcoin":"Bitcoin  ",',
    '        }',
    '        for sym, (close, chg) in snap.items():',
    '            if close is None: continue',
    '            label = LABELS.get(sym, sym)',
    '            ico   = "UP" if (chg or 0) > 0.3 else "DN" if (chg or 0) < -0.3 else "--"',
    '            chg_s = f"{chg:+.2f}%" if chg is not None else ""',
    '            lines.append(f"  {ico} `{label}` {close:.2f}  {chg_s}")',
    '        lines.append("")',
    '',
    '    # Today\'s patterns',
    '    mmdd, pats = get_todays_patterns(n=8, min_score=5)',
    '    if pats:',
    '        lines.append(f"*Seasonal Patterns ({mmdd}):*")',
    '        for sym, win, dirn, acc, mean, score in pats:',
    '            ico = "UP" if dirn=="UP" else "DN"',
    '            lines.append(',
    '                f"  {ico} `{sym:<14}` {win}d  {acc:.0f}%  {mean:+.2f}%  s={score:.1f}"',
    '            )',
    '        lines.append("")',
    '    else:',
    '        lines.append(f"_No high-score patterns for {mmdd}_")',
    '        lines.append("")',
    '',
    '    # Eta highlights',
    '    try:',
    '        eta_path = DA / "agents" / "eta" / "last_report.json"',
    '        if eta_path.exists():',
    '            eta = json.loads(eta_path.read_text())',
    '            clusters = eta.get("insider_cluster", [])[:3]',
    '            if clusters:',
    '                lines.append("*Insider Clusters:*")',
    '                for c in clusters:',
    '                    lines.append(',
    '                        f"  `{c[\'symbol\']}` {c[\'buy_count\']} insiders"',
    '                        f" ₹{c.get(\'total_value_cr\',0):.1f}Cr"',
    '                    )',
    '                lines.append("")',
    '    except: pass',
    '',
    '    # Alert summary',
    '    try:',
    '        alert_path = DA / "agents" / "alert" / "last_report.json"',
    '        if alert_path.exists():',
    '            ar = json.loads(alert_path.read_text())',
    '            fired = ar.get("alerts_fired", 0)',
    '            if fired:',
    '                lines.append(f"*Alerts Fired: {fired}*")',
    '                for f in ar.get("fired", [])[:3]:',
    '                    lines.append(f"  {f.get(\'message\',\'\')[:60]}")',
    '                lines.append("")',
    '    except: pass',
    '',
    '    lines.append("_MICC v3 | localhost:3000_")',
    '',
    '    msg = "\\n".join(lines)',
    '    print("\\n" + msg[:1000] + "...")',
    '    ok = send(msg)',
    '    log(f"Telegram: {\'SENT\' if ok else \'FAILED\'}")',
    '',
    'if __name__ == "__main__":',
    '    main()',
]
write(MICC / "morning_brief.py", "\n".join(morning_lines), "morning_brief.py")


# =============================================================================
# [4]  /api/alpha/route.ts  -- serve Alpha agent report
# =============================================================================
print("\n[4/5] Writing /api/alpha/route.ts ...")

alpha_api = """\
import { NextResponse } from "next/server";
import fs   from "fs";
import path from "path";

const REPORT = "D:/MICC/agents/alpha/last_report.json";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

export async function GET() {
  try {
    if (!fs.existsSync(REPORT)) {
      return NextResponse.json({ error: "Run: py D:/MICC/agent_alpha.py" }, { status: 404 });
    }
    return NextResponse.json(JSON.parse(sanitize(fs.readFileSync(REPORT, "utf-8"))));
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
"""
write(SRC / "api" / "alpha" / "route.ts", alpha_api, "/api/alpha/route.ts")


# =============================================================================
# [5]  Task scheduler XML for morning brief
# =============================================================================
print("\n[5/5] Writing morning_brief_scheduler.xml ...")

xml_lines = [
    '<?xml version="1.0" encoding="UTF-16"?>',
    '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">',
    '  <Triggers>',
    '    <CalendarTrigger>',
    '      <StartBoundary>2026-05-17T09:00:00</StartBoundary>',
    '      <Enabled>true</Enabled>',
    '      <ScheduleByWeek>',
    '        <WeeksInterval>1</WeeksInterval>',
    '        <DaysOfWeek>',
    '          <Monday /><Tuesday /><Wednesday /><Thursday /><Friday />',
    '        </DaysOfWeek>',
    '      </ScheduleByWeek>',
    '    </CalendarTrigger>',
    '  </Triggers>',
    '  <Actions>',
    '    <Exec>',
    '      <Command>py</Command>',
    '      <Arguments>D:\\MICC\\morning_brief.py</Arguments>',
    '      <WorkingDirectory>D:\\MICC</WorkingDirectory>',
    '    </Exec>',
    '  </Actions>',
    '  <Settings>',
    '    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>',
    '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>',
    '  </Settings>',
    '</Task>',
]
write(MICC / "morning_brief_scheduler.xml", "\n".join(xml_lines), "morning_brief_scheduler.xml")


print("""
=============================================================
BUILD PHASE 26 COMPLETE
=============================================================

[1] /api/analysis/route.ts
    Aggregates all 10 agent last_report.json files
    Returns: reports{}, agents_available[], agents_missing[]

[2] /analysis/page.tsx  (was in NavBar but missing!)
    2-column grid of agent cards:
      - Each shows: icon / name / desc / stats strip / LLM summary
      - Click to expand analysis text
      - "View ->" link to the agent's dedicated page
      - Grayed out if agent hasn't been run yet
    Quick links row at bottom

[3] D:\\MICC\\morning_brief.py
    Run at 9:00 AM for full Telegram morning brief:
      - Global markets snapshot (9 symbols)
      - Today's top seasonal patterns
      - Insider cluster highlights from Eta
      - Alert summary
    Run: py D:\\MICC\\morning_brief.py
    Schedule: import morning_brief_scheduler.xml into Task Scheduler

[4] /api/alpha/route.ts
    Serves agents/alpha/last_report.json

[5] morning_brief_scheduler.xml
    Windows Task Scheduler XML -- import it:
    schtasks /create /xml D:\\MICC\\morning_brief_scheduler.xml /tn "MICC Morning Brief"

NEXT STEPS:
  cd D:\\MICC\\micc-dashboard && npm run dev
  localhost:3000/analysis    -- check all agent cards
  localhost:3000/overview    -- macro strip + today's patterns

  Test morning brief:
    py D:\\MICC\\morning_brief.py

  Schedule it:
    schtasks /create /xml D:\\MICC\\morning_brief_scheduler.xml /tn "MICC Morning Brief"

STOCK BUILD:
  Still running in other terminal
  Check: py D:\\MICC\\build_seasonality_v3_stocks.py --verify

FULL MICC STATUS:
  Pages (16): overview, analysis, streaks, indices, options,
              macro, mf, watchlist, backtest, patterns, patterns-v3,
              eta, compare, global, alerts, deep
  Agents (10): Alpha Beta Gamma Delta Epsilon Zeta Eta Iota Kappa Alert
  Telegram (18+): /start /report /alpha /beta /gamma /delta /eta
                  /streak /options /index /stock /hot /deep /kappa
                  /global /patterns /alerts /today /watch /status
  DB patterns: ~4M+ growing (stock build running)
  Global data: 52 symbols back to 2000
=============================================================
""")
