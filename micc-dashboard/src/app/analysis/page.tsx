"use client";
import NavBar from "@/components/NavBar";

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
  alpha:   { icon:"", name:"Alpha",   desc:"Market pulse & regime",         href:"/overview",    color:"var(--neg)" },
  beta:    { icon:"", name:"Beta",    desc:"Momentum & breakouts",           href:"/streaks",     color:"var(--accent)" },
  gamma:   { icon:"", name:"Gamma",   desc:"Options & GEX",                  href:"/options",     color:"var(--warn)" },
  delta:   { icon:"", name:"Delta",   desc:"Sector rotation",                href:"/indices",     color:"var(--pos)" },
  epsilon: { icon:"", name:"Epsilon", desc:"FII/DII & institutional",        href:"/overview",    color:"var(--purple)" },
  zeta:    { icon:"",  name:"Zeta",   desc:"Watchlist alerts",               href:"/watchlist",   color:"var(--cyan)" },
  eta:     { icon:"", name:"Eta",    desc:"Corporate events & insider",      href:"/eta",         color:"var(--cyan)" },
  iota:    { icon:"", name:"Iota",   desc:"Global intelligence",             href:"/deep",        color:"var(--pos)" },
  kappa:   { icon:"", name:"Kappa",  desc:"Deep stock profiles",             href:"/compare",     color:"var(--purple)" },
  alert:   { icon:"", name:"Alert",  desc:"Price & pattern triggers",        href:"/alerts",      color:"var(--warn)" },
};

function AgentCard({ name, report }: { name: string; report: AgentReport | undefined }) {
  const meta = AGENT_META[name] || { icon:"", name, desc:"", href:"/", color:"var(--muted)" };
  const hasData = !!report;
  const [open, setOpen] = useState(false);

  return (
    <div style={{
      background: "var(--card)",
      border: `1px solid ${hasData ? meta.color + "44" : "var(--border2)"}`,
      borderRadius: 6, overflow: "hidden",
      opacity: hasData ? 1 : 0.5,
    }}>
      <NavBar />
      {/* Header */}
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid #334155",
        display: "flex", alignItems: "center", gap: 10, cursor: hasData ? "pointer" : "default",
      }} onClick={() => hasData && setOpen(o => !o)}>
        <span style={{ fontSize: 18 }}>{meta.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: meta.color }}>{meta.name}</div>
          <div style={{ fontSize: 10, color: "var(--muted)" }}>{meta.desc}</div>
        </div>
        {hasData && (
          <div style={{ textAlign: "right" }}>
            {report?.generated_at && (
              <div style={{ fontSize: 9, color: "var(--muted)" }}>
                {report.generated_at.slice(11, 16)}
              </div>
            )}
            <div style={{ fontSize: 10, color: "var(--border2)" }}>{open ? "" : ""}</div>
          </div>
        )}
        {!hasData && (
          <span style={{ fontSize: 9, color: "var(--border2)" }}>NOT RUN</span>
        )}
        <a href={meta.href} onClick={e => e.stopPropagation()}
          style={{ fontSize: 10, color: meta.color, textDecoration: "none",
            padding: "2px 8px", border: `1px solid ${meta.color}44`, borderRadius: 4 }}>
          View 
        </a>
      </div>

      {/* Stats strip */}
      {hasData && (
        <div style={{
          display: "flex", gap: 0,
          borderBottom: "1px solid #334155",
          background: "var(--bg)",
        }}>
          {[
            report?.score        != null && { label: "Score",    v: Number(report.score).toFixed(1),    c: "var(--warn)" },
            report?.regime                && { label: "Regime",   v: String(report.regime),                     c: "var(--muted)" },
            report?.alerts_fired != null && { label: "Alerts",   v: String(report.alerts_fired),       c: "var(--neg)" },
            report?.patterns_today != null && { label: "Patterns",v: String(report.patterns_today),    c: "var(--accent)" },
            report?.insider_clusters != null && { label: "Clusters",v: String(report.insider_clusters),c: "var(--pos)" },
            report?.big_trades != null && { label: "Big Trades", v: String(report.big_trades),         c: "var(--cyan)" },
          ].filter(Boolean).map((s: any, i) => (
            <div key={i} style={{
              flex: 1, textAlign: "center", padding: "6px 4px",
              borderRight: "1px solid #1e293b",
            }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: s.c }}>{s.v}</div>
              <div style={{ fontSize: 9, color: "var(--muted)" }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Expanded analysis */}
      {open && report?.analysis && (
        <div style={{ padding: "12px 16px" }}>
          <p style={{ margin: 0, fontSize: 11, color: "var(--text)", lineHeight: 1.7 }}>
            {String(report.analysis).slice(0, 500)}
            {String(report.analysis).length > 500 ? "" : ""}
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
    <div className="page">

      {/* Header */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", flexWrap:"wrap", gap:16 }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"var(--text)" }}>
            Analysis Hub
          </h1>
          <p style={{ margin:"4px 0 0", fontSize:12, color:"var(--muted)" }}>
            All 10 MICC agents  Latest reports  Click any card to expand
          </p>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:10 }}>
          <div style={{ textAlign:"center", padding:"7px 14px",
            background:"var(--card)", borderRadius:8, border:"1px solid #22c55e33" }}>
            <div style={{ fontSize:18, fontWeight:800, color:"var(--pos)" }}>{available.length}</div>
            <div style={{ fontSize:10, color:"var(--muted)" }}>Ready</div>
          </div>
          <div style={{ textAlign:"center", padding:"7px 14px",
            background:"var(--card)", borderRadius:8, border:"1px solid #ef444433" }}>
            <div style={{ fontSize:18, fontWeight:800, color:"var(--neg)" }}>{missing.length}</div>
            <div style={{ fontSize:10, color:"var(--muted)" }}>Not run</div>
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ padding:"60px", textAlign:"center", color:"var(--muted)" }}>
          Loading agent reports
        </div>
      ) : (
        <div style={{ padding:"20px 28px" }}>

          {/* Quick run hint */}
          {missing.length > 0 && (
            <div style={{
              padding:"12px 16px", background:"var(--card)",
              borderRadius:10, marginBottom:20,
              border:"1px solid #334155",
            }}>
              <div style={{ fontSize:11, fontWeight:700, color:"var(--muted)", marginBottom:8 }}>
                Run agents to populate reports:
              </div>
              <code style={{ fontSize:11, color:"var(--accent)" }}>
                py D:\MICC\micc_engine.py 7 --send
              </code>
              <span style={{ fontSize:11, color:"var(--muted)", marginLeft:16 }}>
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
                padding:"8px 16px", background:"var(--card)",
                border:"1px solid #334155", borderRadius:8,
                color:"var(--muted)", fontSize:12, textDecoration:"none",
                transition:"color 0.15s, border-color 0.15s",
              }}>{l.label} </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
