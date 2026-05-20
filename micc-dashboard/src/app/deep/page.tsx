"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import MarkdownText from "@/components/MarkdownText";

interface Screen1Row { symbol: string; prob_positive: number; mean_return: number; p5_worst: number; p95_best: number; n_windows: number; }
interface Screen2Row { symbol: string; sharpe_ratio: number; mean_return: number; p5_floor: number; }
interface Screen3Row { symbol: string; p5_floor: number; mean_return: number; downside_capture: number; prob_positive: number; }
interface Screen4Row { symbol: string; bull_mean: number; bear_mean: number; sensitivity: number; current_regime_mean: number; }
interface GlobalRow  { symbol: string; close: number; date: string; ret_5d: number | null; }
interface IotaData {
  ok: boolean; error?: string;
  report: {
    date: string; timestamp: string; current_regime: string;
    vix: number; nifty_20d_return: number;
    screen1_best_probability: Screen1Row[];
    screen2_risk_adjusted:    Screen2Row[];
    screen3_worst_case:       Screen3Row[];
    screen4_regime_movers:    Screen4Row[];
    screen5_global: {
      global_risk: string; vix: number; spx_5d: number;
      dxy_5d: number; gold_5d: number;
      spx_correlated_stocks: { symbol: string; correlation: number }[];
      gold_correlated_stocks: { symbol: string; correlation: number }[];
      dxy_sensitive_stocks:   { symbol: string; correlation: number }[];
    };
    screen6_index_stats: {
      index_name: string;
      window_stats: { window_days: number; mean_return: number; prob_positive: number; p5: number; p95: number; sharpe: number; }[];
    }[];
    llm_analysis: string;
  };
  global_snapshot: Record<string, GlobalRow>;
}

const C = {
  green: "var(--accent-green)", red: "var(--accent-red)",
  cyan: "var(--accent-cyan)", yellow: "var(--accent-yellow)",
  orange: "var(--accent-orange, #f97316)",
  dim: "var(--text-tertiary)", primary: "var(--text-primary)",
  border: "var(--border-color)", surface: "var(--surface-card)",
};

const pct  = (v: unknown, d = 1) => v == null ? "--" : `${(+v) >= 0 ? "+" : ""}${(+v).toFixed(d)}%`;
const num  = (v: unknown, d = 2) => v == null ? "--" : (+v).toFixed(d);
const col  = (v: unknown) => (+v ?? 0) >= 0 ? C.green : C.red;
const rCol = (r: string) => r?.includes("BULL") ? C.green : r?.includes("BEAR") ? C.red : C.yellow;
const rkCol = (r: string) => r === "LOW" ? C.green : r === "HIGH" || r === "CRISIS" ? C.red : C.yellow;

function Card({ title, children, accent }: { title: string; children: React.ReactNode; accent?: string; }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${accent || C.border}`, borderRadius: 8, padding: "16px 20px", marginBottom: 18 }}>
      
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: accent || C.cyan, textTransform: "uppercase", marginBottom: 12, borderBottom: `1px solid ${C.border}`, paddingBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

function STable({ rows, cols, onSym }: {
  rows: Record<string, unknown>[];
  cols: { k: string; label: string; fmt?: (v: unknown) => string; c?: (v: unknown) => string }[];
  onSym?: (s: string) => void;
}) {
  if (!rows?.length) return <div style={{ color: C.dim, fontSize: 12, padding: "8px 0" }}>No data</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>{cols.map(c => <th key={c.k} style={{ padding: "4px 8px", textAlign: c.k === "symbol" ? "left" : "right", color: C.dim, fontWeight: 600, borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap" }}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
              {cols.map(c => {
                const v = row[c.k];
                const txt = c.fmt ? c.fmt(v) : String(v ?? "--");
                const clr = c.c ? c.c(v) : c.k === "symbol" ? C.cyan : C.primary;
                return <td key={c.k} style={{ padding: "5px 8px", color: clr, fontWeight: c.k === "symbol" ? 700 : 400, textAlign: c.k === "symbol" ? "left" : "right", cursor: c.k === "symbol" && onSym ? "pointer" : "default" }} onClick={c.k === "symbol" && onSym ? () => onSym(String(v)) : undefined}>{txt}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SCREENS = ["Best Probability", "Risk-Adjusted", "Worst-Case Floor", "Regime Movers", "Global Macro", "Index Stats"];

export default function DeepPage() {
  const router = useRouter();
  const [data, setData] = useState<IotaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [symInput, setSymInput] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch("/api/deep", { cache: "no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "API error");
      setData(d);
    } catch (e: unknown) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const go = (sym: string) => router.push(`/deep/${sym.trim().toUpperCase()}`);

  if (loading) return <div style={{ padding: 40, color: C.dim, textAlign: "center" }}>Loading Deep Analysis Room...</div>;
  if (error)   return <div style={{ padding: 40, color: C.red }}>Error: {error}</div>;

  const rpt = data?.report;
  if (!rpt?.date) return (
    <div style={{ padding: 40, color: C.yellow }}>
      No Iota report found.<br />Run: <code>py D:\MICC\agent_iota.py</code>
    </div>
  );

  const s5 = rpt.screen5_global;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>DEEP ANALYSIS ROOM</h1>
          <div style={{ color: C.dim, fontSize: 12, marginTop: 4 }}>Agent Iota &bull; {rpt.date}</div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            { label: rpt.current_regime, color: rCol(rpt.current_regime) },
            { label: `VIX ${rpt.vix ?? "--"}`, color: (rpt.vix ?? 0) > 20 ? C.red : C.green },
            { label: `Nifty 20d ${pct(rpt.nifty_20d_return)}`, color: col(rpt.nifty_20d_return) },
          ].map(({ label, color }) => (
            <span key={label} style={{ background: `${color}22`, color, border: `1px solid ${color}44`, borderRadius: 4, padding: "3px 8px", fontSize: 11, fontWeight: 700 }}>{label}</span>
          ))}
        </div>
      </div>

      {/* Symbol jump */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <input value={symInput} onChange={e => setSymInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && symInput && go(symInput)}
          placeholder="Jump to stock/index deep dive... (Enter)"
          style={{ background: C.surface, border: `1px solid ${C.border}`, color: C.primary, borderRadius: 6, padding: "8px 14px", fontSize: 13, flex: 1, maxWidth: 340 }}
        />
        <button onClick={() => symInput && go(symInput)} style={{ background: C.cyan, color: "#000", border: "none", borderRadius: 6, padding: "8px 18px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>Deep Dive</button>
        <button onClick={() => router.push("/compare")} style={{ background: "transparent", color: C.yellow, border: `1px solid ${C.yellow}`, borderRadius: 6, padding: "8px 16px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>Compare</button>
        <button onClick={load} style={{ background: "transparent", color: C.dim, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 12px", cursor: "pointer", fontSize: 12 }}>Refresh</button>
      </div>

      {/* Global bar */}
      {data?.global_snapshot && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
          {["SPX","NDX","VIX","DXY","GOLD","USDINR"].map(sym => {
            const d = data.global_snapshot[sym] as GlobalRow | undefined;
            return (
              <div key={sym} style={{ background: `${C.border}33`, borderRadius: 6, padding: "8px 12px", minWidth: 88, textAlign: "center" }}>
                <div style={{ fontSize: 10, color: C.dim, fontWeight: 700 }}>{sym}</div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{d ? (d.close > 1000 ? Math.round(d.close).toLocaleString() : (+d.close).toFixed(2)) : "--"}</div>
                <div style={{ fontSize: 11, color: d?.ret_5d != null ? col(d.ret_5d) : C.dim }}>{d?.ret_5d != null ? pct(d.ret_5d) : "5d --"}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Global macro summary strip */}
      {s5 && (
        <Card title="Global Macro" accent={rkCol(s5.global_risk)}>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ background: `${rkCol(s5.global_risk)}22`, color: rkCol(s5.global_risk), border: `1px solid ${rkCol(s5.global_risk)}44`, borderRadius: 4, padding: "3px 8px", fontSize: 11, fontWeight: 700 }}>Risk: {s5.global_risk}</span>
            {[["SPX 5d", s5.spx_5d], ["DXY 5d", s5.dxy_5d], ["Gold 5d", s5.gold_5d], ["VIX", s5.vix]].map(([label, val]) => (
              <div key={label as string} style={{ fontSize: 12 }}>
                <span style={{ color: C.dim }}>{label}: </span>
                <span style={{ color: col(val), fontWeight: 600 }}>{pct(val)}</span>
              </div>
            ))}
          </div>
          {s5.spx_correlated_stocks?.length > 0 && (
            <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <span style={{ color: C.dim, fontSize: 11 }}>SPX-corr: </span>
              {s5.spx_correlated_stocks.slice(0, 8).map(s => (
                <span key={s.symbol} style={{ color: C.cyan, cursor: "pointer", fontSize: 12, fontWeight: 700 }} onClick={() => go(s.symbol)}>{s.symbol}</span>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Screen tabs */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 14 }}>
        {SCREENS.map((name, i) => (
          <button key={i} onClick={() => setActive(i)} style={{ padding: "6px 13px", borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: "pointer", border: "1px solid", background: active === i ? C.cyan : "transparent", color: active === i ? "#000" : C.dim, borderColor: active === i ? C.cyan : C.border }}>S{i + 1}: {name}</button>
        ))}
      </div>

      {active === 0 && <Card title="Screen 1 - Best Probability Stocks (20d)" accent={C.green}><STable rows={rpt.screen1_best_probability as unknown as Record<string, unknown>[]} cols={[ {k:"symbol",label:"Symbol"}, {k:"prob_positive",label:"Prob+",fmt:v=>`${v}%`,c:()=>C.green}, {k:"mean_return",label:"Mean",fmt:v=>pct(v),c:col}, {k:"p5_worst",label:"P5 Floor",fmt:v=>pct(v),c:col}, {k:"p95_best",label:"P95 Best",fmt:v=>pct(v),c:()=>C.cyan}, {k:"n_windows",label:"N",fmt:v=>String(v)}, ]} onSym={go} /></Card>}
      {active === 1 && <Card title="Screen 2 - Risk-Adjusted Gems (Sharpe-ranked)" accent={C.cyan}><STable rows={rpt.screen2_risk_adjusted as unknown as Record<string, unknown>[]} cols={[ {k:"symbol",label:"Symbol"}, {k:"sharpe_ratio",label:"Sharpe",fmt:v=>num(v),c:()=>C.cyan}, {k:"mean_return",label:"Mean",fmt:v=>pct(v),c:col}, {k:"p5_floor",label:"P5 Floor",fmt:v=>pct(v),c:col}, ]} onSym={go} /></Card>}
      {active === 2 && <Card title="Screen 3 - Worst-Case Protected (P5 Floor > -5%)" accent={C.yellow}><STable rows={rpt.screen3_worst_case as unknown as Record<string, unknown>[]} cols={[ {k:"symbol",label:"Symbol"}, {k:"p5_floor",label:"P5 Floor",fmt:v=>pct(v),c:col}, {k:"mean_return",label:"Mean",fmt:v=>pct(v),c:col}, {k:"downside_capture",label:"DD Capt%",fmt:v=>pct(v),c:()=>C.yellow}, {k:"prob_positive",label:"Prob+",fmt:v=>`${v}%`}, ]} onSym={go} /></Card>}
      {active === 3 && <Card title="Screen 4 - Regime Sensitivity" accent={C.orange}><STable rows={rpt.screen4_regime_movers as unknown as Record<string, unknown>[]} cols={[ {k:"symbol",label:"Symbol"}, {k:"bull_mean",label:"Bull Mean",fmt:v=>pct(v),c:()=>C.green}, {k:"bear_mean",label:"Bear Mean",fmt:v=>pct(v),c:()=>C.red}, {k:"sensitivity",label:"Sensitivity",fmt:v=>num(v,1)}, {k:"current_regime_mean",label:"Now Mean",fmt:v=>pct(v),c:col}, ]} onSym={go} /></Card>}
      {active === 4 && (
        <Card title="Screen 5 - Global Macro Pulse" accent={C.yellow}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
            {[["SPX CORRELATED", s5?.spx_correlated_stocks, C.cyan], ["GOLD CORRELATED", s5?.gold_correlated_stocks, C.yellow], ["DXY SENSITIVE", s5?.dxy_sensitive_stocks, C.orange]].map(([title, arr, color]) => (
              <div key={title as string}>
                <div style={{ color: C.dim, fontSize: 11, fontWeight: 700, marginBottom: 8 }}>{title as string}</div>
                {(arr as {symbol:string;correlation:number}[] | undefined)?.slice(0,10).map(s => (
                  <div key={s.symbol} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12 }}>
                    <span style={{ color: color as string, cursor: "pointer" }} onClick={() => go(s.symbol)}>{s.symbol}</span>
                    <span style={{ color: C.dim }}>{num(s.correlation)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Card>
      )}
      {active === 5 && (
        <Card title="Screen 6 - Index Deep Stats" accent={C.cyan}>
          {(rpt.screen6_index_stats || []).map(idx => (
            <div key={idx.index_name} style={{ marginBottom: 18 }}>
              <div style={{ color: C.cyan, fontWeight: 700, fontSize: 13, marginBottom: 6, cursor: "pointer" }} onClick={() => go(idx.index_name.replace(/ /g, "_"))}>{idx.index_name}</div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead><tr>{["Win","Mean%","P5%","P95%","Prob+","Sharpe"].map(h => <th key={h} style={{ padding: "3px 8px", textAlign: "right", color: C.dim, fontWeight: 600 }}>{h}</th>)}</tr></thead>
                <tbody>
                  {(idx.window_stats || []).map(w => (
                    <tr key={w.window_days}>
                      <td style={{ padding: "3px 8px", color: C.dim, textAlign: "right" }}>{w.window_days}d</td>
                      <td style={{ padding: "3px 8px", color: col(w.mean_return), textAlign: "right" }}>{pct(w.mean_return)}</td>
                      <td style={{ padding: "3px 8px", color: col(w.p5), textAlign: "right" }}>{pct(w.p5)}</td>
                      <td style={{ padding: "3px 8px", color: col(w.p95), textAlign: "right" }}>{pct(w.p95)}</td>
                      <td style={{ padding: "3px 8px", color: C.green, textAlign: "right" }}>{w.prob_positive}%</td>
                      <td style={{ padding: "3px 8px", color: C.cyan, textAlign: "right" }}>{num(w.sharpe)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </Card>
      )}

      {rpt.llm_analysis && <Card title="Iota Intelligence Synthesis" accent={C.cyan}><MarkdownText text={rpt.llm_analysis} /></Card>}
    </div>
  );
}
