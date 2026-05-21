"use client";
import { useEffect, useState } from "react";
import NavBar from "@/components/NavBar";

interface AgentCard {
  agent: string;
  timestamp: string;
  regime?: string | Record<string, string>;
  confidence?: string;
  summary?: string;
  llm_analysis?: string;
  screens?: Record<string, unknown[]>;
  picks?: unknown[];
  signals?: unknown[];
  [key: string]: unknown;
}

function safeStr(v: unknown): string {
  if (v === null || v === undefined) return "--";
  if (typeof v === "string") return v;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function regimeStr(r: unknown): string {
  if (!r) return "--";
  if (typeof r === "string") return r;
  if (typeof r === "object" && r !== null) {
    const obj = r as Record<string, string>;
    if (obj.regime) return obj.regime + (obj.confidence ? " (" + obj.confidence + ")" : "");
    return JSON.stringify(r);
  }
  return String(r);
}

const AGENT_LABELS: Record<string, string> = {
  alpha: "ALPHA  |  MACRO INTELLIGENCE",
  beta:  "BETA   |  MOMENTUM SCREENER",
  gamma: "GAMMA  |  OPTIONS / GEX",
  delta: "DELTA  |  SECTOR ROTATION",
  epsilon: "EPSILON  |  FII / DII FLOW",
  zeta:  "ZETA   |  WATCHLIST SIGNALS",
  eta:   "ETA    |  CORPORATE EVENTS",
  iota:  "IOTA   |  GLOBAL INTEL",
  fusion: "FUSION  |  COMPOSITE PICKS",
};

const AGENTS = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","fusion"];

export default function AnalysisPage() {
  const [reports, setReports] = useState<Record<string, AgentCard>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState("");
  const [open, setOpen]     = useState<string>("alpha");

  useEffect(() => {
    fetch("/api/analysis")
      .then(r => r.json())
      .then(d => { setReports(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:   { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:    { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
              borderBottom: "1px solid var(--border)", padding: "6px 20px",
              fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:   { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    tabs:   { display: "flex", gap: 6, flexWrap: "wrap" as const, marginBottom: 20 },
    tab:    (active: boolean) => ({
      padding: "5px 14px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (active ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: active ? "var(--accent)" + "22" : "transparent",
      color: active ? "var(--accent)" : "var(--dim)",
    }),
    card:   { background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "16px 20px", marginBottom: 16 },
    label:  { fontSize: 10, color: "var(--dim)", letterSpacing: 2, marginBottom: 8 },
    val:    { fontSize: 13, color: "var(--text)" },
    grid:   { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12, marginBottom: 16 },
    kv:     { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "10px 14px" },
    kvk:    { fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 4 },
    kvv:    { fontSize: 13, color: "var(--text)", fontWeight: 600 },
    pre:    { fontSize: 12, color: "var(--text)", lineHeight: 1.7, whiteSpace: "pre-wrap" as const,
              background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6,
              padding: "12px 16px", marginTop: 8 },
    tbl:    { width: "100%", borderCollapse: "collapse" as const, fontSize: 12, marginTop: 8 },
    th:     { padding: "6px 10px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
              color: "var(--dim)", borderBottom: "1px solid var(--border)" },
    td:     { padding: "7px 10px", borderBottom: "1px solid var(--border) + 44", color: "var(--text)" },
  };

  function renderReport(name: string, rpt: AgentCard) {
    if (!rpt) return <div style={S.card}><div style={S.label}>{AGENT_LABELS[name] || name.toUpperCase()}</div><div style={{color:"var(--dim)",fontSize:12}}>No data -- run py agent_{name}.py</div></div>;
    const ts = rpt.timestamp || rpt.date || "";
    const kvs: [string, string][] = [];
    if (rpt.regime !== undefined) kvs.push(["REGIME", regimeStr(rpt.regime)]);
    if (rpt.confidence !== undefined) kvs.push(["CONFIDENCE", safeStr(rpt.confidence)]);
    if (rpt.summary !== undefined) kvs.push(["SUMMARY", safeStr(rpt.summary)]);

    const lists: [string, unknown[]][] = [];
    for (const [k, v] of Object.entries(rpt)) {
      if (["agent","timestamp","date","llm_analysis","regime","confidence","summary"].includes(k)) continue;
      if (Array.isArray(v) && v.length > 0) lists.push([k, v]);
    }

    return (
      <div style={S.card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ fontSize: 11, color: "var(--accent)", letterSpacing: 2, fontWeight: 700 }}>
            {AGENT_LABELS[name] || name.toUpperCase()}
          </span>
          <span style={{ fontSize: 10, color: "var(--dim)" }}>{ts}</span>
        </div>

        {kvs.length > 0 && (
          <div style={S.grid}>
            {kvs.map(([k, v]) => (
              <div key={k} style={S.kv}>
                <div style={S.kvk}>{k}</div>
                <div style={S.kvv}>{v}</div>
              </div>
            ))}
          </div>
        )}

        {rpt.llm_analysis && (
          <pre style={S.pre}>{rpt.llm_analysis}</pre>
        )}

        {lists.map(([k, rows]) => (
          <div key={k} style={{ marginTop: 16 }}>
            <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 6 }}>
              {k.replace(/_/g, " ").toUpperCase()}  ({rows.length})
            </div>
            {typeof rows[0] === "object" && rows[0] !== null ? (
              <div style={{ overflowX: "auto" as const }}>
                <table style={S.tbl}>
                  <thead>
                    <tr>{Object.keys(rows[0] as Record<string, unknown>).slice(0,8).map(col => (
                      <th key={col} style={S.th}>{col.toUpperCase()}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 20).map((row, i) => (
                      <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : "var(--surface)" + "88" }}>
                        {Object.values(row as Record<string, unknown>).slice(0,8).map((val, j) => (
                          <td key={j} style={S.td}>{safeStr(val)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {rows.slice(0, 30).map((r, i) => (
                  <span key={i} style={{ padding: "3px 8px", background: "var(--bg)",
                    border: "1px solid var(--border)", borderRadius: 4, fontSize: 11, color: "var(--text)" }}>
                    {safeStr(r)}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>ANALYSIS  /  AGENT REPORTS</div>
      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading agent reports...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error}</div>}

        {!loading && !error && (
          <>
            <div style={S.tabs}>
              {AGENTS.map(a => (
                <button key={a} onClick={() => setOpen(a)} style={S.tab(open === a)}>
                  {a.toUpperCase()}
                </button>
              ))}
              <button onClick={() => setOpen("all")} style={S.tab(open === "all")}>ALL</button>
            </div>

            {open === "all"
              ? AGENTS.map(a => renderReport(a, reports[a]))
              : renderReport(open, reports[open])
            }
          </>
        )}
      </div>
    </div>
  );
}
