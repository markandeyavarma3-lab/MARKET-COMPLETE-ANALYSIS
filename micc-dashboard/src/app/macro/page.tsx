"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface MacroRow { indicator: string; value: string | number | null; unit?: string; date?: string; source?: string; }
interface MacroData {
  repo_rate?: number | null;
  reverse_repo?: number | null;
  crr?: number | null;
  cpi_latest?: number | null;
  gdp_growth?: number | null;
  usd_inr?: number | null;
  india_10y?: number | null;
  us_fed_rate?: number | null;
  us_10y?: number | null;
  us_cpi?: number | null;
  rbi_history?: { date: string; repo_rate: number; reverse_repo: number; crr: number }[];
  us_macro?: MacroRow[];
  india_macro?: MacroRow[];
  [key: string]: unknown;
}

const fmt = (v: unknown, d = 2): string => {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toFixed(d);
};

export default function MacroPage() {
  const [data, setData] = useState<MacroData | null>(null);
  const [loading, setL] = useState(true);
  const [error, setE]   = useState("");
  const [tab, setTab]   = useState<"india" | "us" | "rbi">("india");

  useEffect(() => {
    fetch("/api/macro")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    grid:  { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 24 },
    kv:    { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "12px 16px" },
    kvk:   { fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 4 },
    kvv:   { fontSize: 20, color: "var(--text)", fontWeight: 700 },
    tabs:  { display: "flex", gap: 6, marginBottom: 20 },
    tab:   (a: boolean) => ({
      padding: "5px 16px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (a ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: a ? "var(--accent)" + "22" : "transparent",
      color: a ? "var(--accent)" : "var(--dim)",
    }),
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)",
             background: "var(--surface)" },
    td:    { padding: "8px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
  };

  const KV = ({ label, value, color }: { label: string; value: string; color?: string }) => (
    <div style={S.kv}>
      <div style={S.kvk}>{label}</div>
      <div style={{ ...S.kvv, color: color || "var(--text)" }}>{value}</div>
    </div>
  );

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>MACRO  /  INDIA & GLOBAL INDICATORS</div>
      <div style={S.wrap}>

        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading macro data...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error}</div>}

        {data && <>
          <div style={S.grid}>
            <KV label="REPO RATE"      value={fmt(data.repo_rate) + "%"} color="var(--accent)" />
            <KV label="REVERSE REPO"   value={fmt(data.reverse_repo) + "%"} />
            <KV label="CRR"            value={fmt(data.crr) + "%"} />
            <KV label="CPI (INDIA)"    value={fmt(data.cpi_latest) + "%"} color={Number(data.cpi_latest) > 6 ? "var(--bear)" : "var(--bull)"} />
            <KV label="GDP GROWTH"     value={fmt(data.gdp_growth) + "%"} color="var(--bull)" />
            <KV label="USD/INR"        value={fmt(data.usd_inr, 2)} />
            <KV label="INDIA 10Y"      value={fmt(data.india_10y) + "%"} />
            <KV label="US FED RATE"    value={fmt(data.us_fed_rate) + "%"} />
            <KV label="US 10Y YIELD"   value={fmt(data.us_10y) + "%"} />
            <KV label="US CPI"         value={fmt(data.us_cpi) + "%"} color={Number(data.us_cpi) > 3 ? "var(--warn)" : "var(--bull)"} />
          </div>

          <div style={S.tabs}>
            {(["india","us","rbi"] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={S.tab(tab === t)}>
                {t === "rbi" ? "RBI HISTORY" : t.toUpperCase() + " MACRO"}
              </button>
            ))}
          </div>

          {tab === "india" && data.india_macro && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>INDICATOR</th>
                  <th style={S.th}>VALUE</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>SOURCE</th>
                </tr></thead>
                <tbody>
                  {data.india_macro.map((row, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={S.td}>{row.indicator || row.source || "--"}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>
                        {fmt(row.value, 3)}{row.unit ? " " + row.unit : ""}
                      </td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{row.date || "--"}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{row.source || "--"}</td>
                    </tr>
                  ))}
                  {(!data.india_macro || data.india_macro.length === 0) && (
                    <tr><td colSpan={4} style={{ ...S.td, color: "var(--dim)", textAlign: "center" }}>No data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === "us" && data.us_macro && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>INDICATOR</th>
                  <th style={S.th}>VALUE</th>
                  <th style={S.th}>DATE</th>
                </tr></thead>
                <tbody>
                  {data.us_macro.map((row, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={S.td}>{row.indicator || "--"}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>
                        {fmt(row.value, 3)}{row.unit ? " " + row.unit : ""}
                      </td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{row.date || "--"}</td>
                    </tr>
                  ))}
                  {(!data.us_macro || data.us_macro.length === 0) && (
                    <tr><td colSpan={3} style={{ ...S.td, color: "var(--dim)", textAlign: "center" }}>No data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === "rbi" && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>REPO RATE</th>
                  <th style={S.th}>REVERSE REPO</th>
                  <th style={S.th}>CRR</th>
                </tr></thead>
                <tbody>
                  {(data.rbi_history || []).map((row, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={S.td}>{row.date}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>{fmt(row.repo_rate)}%</td>
                      <td style={S.td}>{fmt(row.reverse_repo)}%</td>
                      <td style={S.td}>{fmt(row.crr)}%</td>
                    </tr>
                  ))}
                  {(!data.rbi_history || data.rbi_history.length === 0) && (
                    <tr><td colSpan={4} style={{ ...S.td, color: "var(--dim)", textAlign: "center" }}>
                      No RBI history -- run fetch_rbi_rates.py
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>}
      </div>
    </div>
  );
}
