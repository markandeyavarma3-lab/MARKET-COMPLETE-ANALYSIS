"use client";
import NavBar from "@/components/NavBar";

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
  alpha:   {icon:"",name:"Alpha",   href:"/overview"},
  beta:    {icon:"",name:"Beta",    href:"/streaks"},
  gamma:   {icon:"",name:"Gamma",   href:"/options"},
  delta:   {icon:"",name:"Delta",   href:"/indices"},
  epsilon: {icon:"",name:"Epsilon", href:"/overview"},
  zeta:    {icon:"", name:"Zeta",   href:"/watchlist"},
  eta:     {icon:"",name:"Eta",     href:"/eta"},
  iota:    {icon:"",name:"Iota",    href:"/deep"},
  kappa:   {icon:"",name:"Kappa",   href:"/compare"},
  alert:   {icon:"",name:"Alert",   href:"/alerts"},
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
      background:"var(--bg)", borderRadius:8, padding:"10px 14px",
      textAlign:"center", minWidth:100,
    }}>
      <div style={{ fontSize:16, fontWeight:800, color:color||"var(--text)" }}>{value}</div>
      <div style={{ fontSize:10, color:"var(--muted)", marginTop:2 }}>{label}</div>
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
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />

      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b" }}>
        <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"var(--text)" }}>
          System Settings
        </h1>
        <p style={{ margin:"4px 0 0", fontSize:12, color:"var(--muted)" }}>
          DB stats  Agent status  Data coverage  Pipeline info
        </p>
      </div>

      {loading ? (
        <div style={{ padding:60, textAlign:"center", color:"var(--muted)" }}>Loading...</div>
      ) : !data ? (
        <div style={{ padding:60, textAlign:"center", color:"var(--neg)" }}>Failed to load settings</div>
      ) : (
        <div style={{ padding:"20px 28px", display:"flex", flexDirection:"column", gap:20 }}>

          {/* DB Overview */}
          <div style={{ background:"var(--card)", border:"1px solid #334155",
            borderRadius:6, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"var(--muted)",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Database
            </div>
            <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:14 }}>
              <StatChip label="DB Size"    value={data.db_size}                     color="var(--accent)" />
              <StatChip label="Patterns"   value={fmt(data.pattern_stats.total)}    color="var(--pos)" />
              <StatChip label="Pat Symbols"value={data.pattern_stats.symbols}       color="var(--pos)" />
              <StatChip label="Windows"    value={data.pattern_stats.windows}       color="var(--purple)" />
              <StatChip label="Avg Acc"    value={data.pattern_stats.avg_acc != null ? data.pattern_stats.avg_acc.toFixed(1)+"%" : ""} color="var(--warn)" />
              <StatChip label="Alerts"     value={data.active_alerts}               color="var(--neg)" />
              <StatChip label="Watchlist"  value={data.watchlist_count}             color="#f472b6" />
            </div>
            <div style={{ fontSize:11, color:"var(--muted)", fontFamily:"monospace" }}>
              {data.db_path}
            </div>
          </div>

          {/* Table row counts */}
          <div style={{ background:"var(--card)", border:"1px solid #334155",
            borderRadius:6, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"var(--muted)",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Key Table Counts
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
              {KEY_TABLES.map(({key,label}) => {
                const n = data.table_counts[key];
                return (
                  <div key={key} style={{
                    display:"flex", justifyContent:"space-between",
                    padding:"7px 10px", background:"var(--bg)", borderRadius:7,
                  }}>
                    <span style={{ fontSize:12, color:"var(--muted)" }}>{label}</span>
                    <span style={{ fontSize:12, fontWeight:700,
                      color: n > 0 ? "var(--pos)" : "var(--neg)" }}>
                      {n >= 0 ? fmt(n) : "error"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Agent status */}
          <div style={{ background:"var(--card)", border:"1px solid #334155",
            borderRadius:6, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"var(--muted)",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Agent Status
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8 }}>
              {Object.entries(AGENT_META).map(([name,meta]) => {
                const s = data.agent_status[name];
                return (
                  <a key={name} href={meta.href} style={{ textDecoration:"none" }}>
                    <div style={{
                      background:"var(--bg)", borderRadius:8, padding:"10px",
                      textAlign:"center",
                      border:`1px solid ${s?.ready ? "#22c55e33" : "var(--border2)"}`,
                      cursor:"pointer",
                    }}>
                      <div style={{ fontSize:18 }}>{meta.icon}</div>
                      <div style={{ fontSize:11, fontWeight:700,
                        color: s?.ready ? "var(--pos)" : "var(--muted)", marginTop:4 }}>
                        {meta.name}
                      </div>
                      <div style={{ fontSize:9, color:"var(--border2)", marginTop:2 }}>
                        {s?.ready ? (s.date || "ready") : "not run"}
                      </div>
                    </div>
                  </a>
                );
              })}
            </div>
            <div style={{ marginTop:14, padding:"10px 14px",
              background:"var(--bg)", borderRadius:8 }}>
              <div style={{ fontSize:11, color:"var(--muted)", marginBottom:6 }}>
                Run all agents:
              </div>
              <code style={{ fontSize:12, color:"var(--accent)" }}>
                py D:\MICC\micc_engine.py 7 --send
              </code>
            </div>
          </div>

          {/* Pipeline info */}
          <div style={{ background:"var(--card)", border:"1px solid #334155",
            borderRadius:6, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"var(--muted)",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Daily Pipeline
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
              {[
                ["Daily update (one command):",   "py D:\\MICC\\data_pipeline\\run_pipeline.py --with-engine"],
                ["Data only:",                     "py D:\\MICC\\data_pipeline\\run_pipeline.py"],
                ["Engine only:",                   "py D:\\MICC\\micc_engine.py 7 --send"],
                ["Morning brief:",                 "py D:\\MICC\\morning_brief.py"],
                ["Global indices:",                "py D:\\MICC\\fetch_global_indices_v2.py"],
                ["Alert check:",                   "py D:\\MICC\\agent_alert.py --send"],
                ["Verify patterns:",               "py D:\\MICC\\build_seasonality_v3_stocks.py --verify"],
              ].map(([label, cmd]) => (
                <div key={label} style={{ display:"flex", gap:10, alignItems:"flex-start" }}>
                  <span style={{ fontSize:11, color:"var(--muted)", minWidth:180, flexShrink:0 }}>
                    {label}
                  </span>
                  <code style={{ fontSize:11, color:"var(--accent)", wordBreak:"break-all" }}>
                    {cmd}
                  </code>
                </div>
              ))}
            </div>
          </div>

          {/* Telegram commands */}
          <div style={{ background:"var(--card)", border:"1px solid #334155",
            borderRadius:6, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"var(--muted)",
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
                  <code style={{ fontSize:11, color:"var(--accent)", minWidth:120 }}>{cmd}</code>
                  <span style={{ fontSize:11, color:"var(--muted)" }}>{desc}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ fontSize:11, color:"var(--border2)", textAlign:"center", paddingBottom:8 }}>
            Generated at {data.generated_at?.slice(0,19).replace("T"," ")} UTC
          </div>

        </div>
      )}
    </div>
  );
}
