"use client";
import { useState, useEffect } from "react";

interface Pt { date: string; value: number }
interface MacroSeries {
  series:   Pt[];
  latest:   Pt | null;
  delta_1m: number | null;
}

// ── Sparkline (SVG) ───────────────────────────────────────────────────────────
function Sparkline({ series, color = "var(--accent)" }:
  { series: Pt[]; color?: string }) {
  if (!series || series.length < 2) {
    return <span style={{ color: "var(--dim)", fontSize: 9, fontFamily: "monospace" }}>--</span>;
  }
  const vals  = series.map(d => Number(d.value ?? 0)).filter(v => !isNaN(v));
  if (vals.length < 2) {
    return <span style={{ color: "var(--dim)", fontSize: 9 }}>--</span>;
  }
  const W = 80, H = 26, pad = 2;
  const min   = Math.min(...vals);
  const max   = Math.max(...vals);
  const range = max - min;   // may be 0

  const pts = vals.map((v, i) => {
    const x = pad + (i / (vals.length - 1)) * (W - pad * 2);
    // If range is 0, draw flat line in the middle
    const y = range === 0
      ? H / 2
      : H - pad - ((v - min) / range) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <svg width={W} height={H} style={{ display: "block", overflow: "visible" }}>
      <polyline points={pts} fill="none" stroke={color}
                strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

// ── Table row ─────────────────────────────────────────────────────────────────
function MacroRow({ label, unit = "", s, color }:
  { label: string; unit?: string; s: MacroSeries | null | undefined; color: string }) {
  if (!s) return null;
  const val   = s.latest?.value ?? null;
  const d     = s.delta_1m ?? null;
  const dC    = d == null ? "var(--dim)" : d > 0 ? "var(--pos)" : d < 0 ? "var(--neg)" : "var(--dim)";
  const sign  = d != null && d > 0 ? "+" : "";
  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "6px 0 6px 0", color: "var(--dim)", fontSize: 11,
                   fontFamily: "monospace", whiteSpace: "nowrap" }}>
        {label}
      </td>
      <td style={{ padding: "6px 12px 6px 12px", textAlign: "right",
                   fontFamily: "monospace", fontSize: 12, color, fontWeight: 600,
                   whiteSpace: "nowrap" }}>
        {val != null ? `${Number(val).toFixed(2)}${unit}` : "--"}
      </td>
      <td style={{ padding: "6px 8px", textAlign: "right",
                   fontFamily: "monospace", fontSize: 10, color: dC,
                   whiteSpace: "nowrap" }}>
        {d != null ? `${sign}${d.toFixed(2)}` : "--"}
      </td>
      <td style={{ padding: "6px 0 6px 10px" }}>
        <Sparkline series={s.series} color={color} />
      </td>
      <td style={{ padding: "6px 0 6px 6px", fontFamily: "monospace",
                   fontSize: 9, color: "var(--dim)", whiteSpace: "nowrap" }}>
        {s.latest?.date ?? "--"}
      </td>
    </tr>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function MacroPanel() {
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [tab,    setTab]    = useState<"us" | "india">("us");

  useEffect(() => {
    fetch("/api/macro", { cache: "no-store" })
      .then(r => r.json()).then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ padding: 40, color: "var(--dim)", fontFamily: "monospace" }}>
      Loading macro data...
    </div>
  );
  if (!data) return (
    <div style={{ padding: 40, color: "var(--neg)", fontFamily: "monospace" }}>
      No macro data. Run: py data_pipeline/update_macro_us.py
    </div>
  );

  const tsVal    = data.term_spread?.latest?.value ?? null;
  const tsColor  = tsVal == null ? "var(--dim)"
                 : tsVal < 0    ? "var(--neg)"
                 : tsVal < 0.5  ? "var(--warn)" : "var(--pos)";
  const tsLabel  = tsVal == null ? "" : tsVal < 0 ? "INVERTED" : tsVal < 0.5 ? "FLAT" : "NORMAL";
  const fedVal   = data.fedfunds?.latest?.value ?? null;
  const vixVal   = data.us_vix?.latest?.value   ?? null;

  function TabBtn({ t, label }: { t: "us" | "india"; label: string }) {
    const active = tab === t;
    return (
      <button onClick={() => setTab(t)} style={{
        padding: "4px 16px", fontSize: 10, cursor: "pointer", fontFamily: "monospace",
        background: active ? "rgba(227,179,65,0.15)" : "var(--surface)",
        color: active ? "#e3b341" : "var(--muted)",
        border: `1px solid ${active ? "#e3b341" : "var(--border)"}`,
        borderRadius: 4,
      }}>{label}</button>
    );
  }

  return (
    <div>
      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
        {[
          { l: "FED FUNDS",    v: fedVal  != null ? Number(fedVal).toFixed(2)  + "%" : "--",
            s: data.fedfunds,  color: "var(--warn)" },
          { l: "US 10Y YIELD", v: data.us_10y?.latest?.value != null
              ? Number(data.us_10y.latest.value).toFixed(2) + "%" : "--",
            s: data.us_10y,    color: "var(--info)" },
          { l: "TERM SPREAD",  v: tsVal != null ? (tsVal >= 0 ? "+" : "") + Number(tsVal).toFixed(2) + "%" : "--",
            s: data.term_spread, color: tsColor, sub: tsLabel },
          { l: "US VIX",       v: vixVal != null ? Number(vixVal).toFixed(1) : "--",
            s: data.us_vix,    color: vixVal != null && Number(vixVal) > 20 ? "var(--neg)" : "var(--pos)" },
        ].map(({ l, v, s, color, sub }: any) => (
          <div key={l} style={{
            padding: "10px 14px", background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 6,
          }}>
            <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                          letterSpacing: "0.1em", marginBottom: 4 }}>{l}</div>
            <div style={{ fontFamily: "monospace", fontSize: 17, fontWeight: 700, color }}>{v}</div>
            {sub && <div style={{ fontFamily: "monospace", fontSize: 9, color, marginTop: 2 }}>{sub}</div>}
            <div style={{ marginTop: 6 }}>
              <Sparkline series={s?.series ?? []} color={color} />
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        <TabBtn t="us"    label="US MACRO"    />
        <TabBtn t="india" label="INDIA MACRO" />
      </div>

      {/* Column headers */}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9,
                       color: "var(--dim)", letterSpacing: "0.08em" }}>
            <th style={{ padding: "4px 0",    textAlign: "left"  }}>INDICATOR</th>
            <th style={{ padding: "4px 12px", textAlign: "right" }}>LATEST</th>
            <th style={{ padding: "4px 8px",  textAlign: "right" }}>1M CHG</th>
            <th style={{ padding: "4px 0 4px 10px"               }}>TREND</th>
            <th style={{ padding: "4px 0 4px 6px"                }}>DATE</th>
          </tr>
        </thead>
        <tbody>
          {tab === "us" && (
            <>
              <MacroRow label="Fed Funds Rate"      unit="%" s={data.fedfunds}    color="var(--warn)" />
              <MacroRow label="US 10Y Yield"        unit="%" s={data.us_10y}      color="var(--info)" />
              <MacroRow label="US 2Y Yield"         unit="%" s={data.us_2y}       color="#8b949e"     />
              <MacroRow label="Term Spread (10-2Y)" unit="%" s={data.term_spread} color={tsColor}     />
              <MacroRow label="US CPI"                       s={data.us_cpi}      color="var(--neg)"  />
              <MacroRow label="US Real GDP"                  s={data.us_gdp}      color="var(--pos)"  />
              <MacroRow label="Unemployment"        unit="%" s={data.us_unemp}    color="var(--warn)" />
              <MacroRow label="VIX"                          s={data.us_vix}      color={vixVal != null && Number(vixVal) > 20 ? "var(--neg)" : "var(--pos)"} />
            </>
          )}
          {tab === "india" && (
            <>
              <MacroRow label="India CPI (OECD)"      s={data.india_cpi}   color="var(--neg)"  />
              <MacroRow label="FX Reserves (Bn USD)"  s={data.india_fx}    color="var(--pos)"  />
              <MacroRow label="Trade Balance"         s={data.india_trade} color="var(--info)" />
              <MacroRow label="Exports"               s={data.india_exp}   color="var(--pos)"  />
              <MacroRow label="Imports"               s={data.india_imp}   color="var(--neg)"  />
              <MacroRow label="US 10Y (ref)"  unit="%" s={data.us_10y}      color="#8b949e"     />
              <MacroRow label="Fed Funds (ref)" unit="%" s={data.fedfunds}  color="#8b949e"     />
            </>
          )}
        </tbody>
      </table>

      {/* Debug: show what series are actually in DB */}
      {data.debug && (
        <details style={{ marginTop: 16, fontFamily: "monospace", fontSize: 9, color: "var(--dim)" }}>
          <summary style={{ cursor: "pointer" }}>DB series IDs (debug)</summary>
          <div style={{ marginTop: 6 }}>
            <div>US: {(data.debug.us_series ?? []).join(", ")}</div>
            <div style={{ marginTop: 4 }}>India: {(data.debug.india_series ?? []).join(", ")}</div>
          </div>
        </details>
      )}

      <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", marginTop: 12 }}>
        Sources: FRED (Federal Reserve) &nbsp;|&nbsp; World Bank &nbsp;|&nbsp;
        Updated daily via run_pipeline.py
      </div>
    </div>
  );
}
