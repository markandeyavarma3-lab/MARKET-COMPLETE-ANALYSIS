"""
build_phase15_compare.py  --  Run from D:\MICC
Builds:
  [1] /app/api/compare/route.ts   -- on-demand kappa comparison via API
  [2] /app/compare/page.tsx       -- /compare dashboard page
  [3] NavBar.tsx                  -- adds COMPARE link

Run: py D:\MICC\build_phase15_compare.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}")

def patch_navbar(link_href: str, link_label: str):
    navbar_path = None
    for p in DASH.rglob("NavBar.tsx"):
        navbar_path = p; break
    if not navbar_path:
        print("  [SKIP] NavBar.tsx not found"); return
    src = navbar_path.read_text(encoding="utf-8")
    if link_href in src:
        print(f"  [SKIP] {link_label} already in NavBar"); return
    for marker in [
        "{ href: '/eta'",
        "{ href: '/backtest'",
        "{ href: '/patterns'",
        "/eta'", "/backtest'", "/patterns'",
    ]:
        if marker in src:
            idx      = src.index(marker)
            line_end = src.find("\n", idx)
            if line_end == -1: line_end = len(src)
            to_insert = f"\n  {{ href: '{link_href}', label: '{link_label}' }},"
            src = src[:line_end] + to_insert + src[line_end:]
            navbar_path.write_text(src, encoding="utf-8")
            print(f"  [OK] Added {link_label} to NavBar")
            return
    print(f"  [WARN] Could not find insertion point for {link_label}")


# ═════════════════════════════════════════════════════════════════════════════
# [1] API ROUTE  /api/compare/route.ts
# ═════════════════════════════════════════════════════════════════════════════

print("\n[1/3] Writing /api/compare/route.ts ...")

COMPARE_ROUTE = r'''import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import path             from "path";
import fs               from "fs";

const DA     = "D:/MICC";
const KAPPA  = path.join(DA, "agents", "kappa");
const PY_CMD = "py";

function sanitize(s: string): string {
  return s.replace(/:\s*NaN\b/g, ": null")
          .replace(/:\s*Infinity\b/g, ": null")
          .replace(/:\s*-Infinity\b/g, ": null");
}

function loadCached(symbol: string) {
  const p = path.join(KAPPA, `${symbol.toUpperCase()}_report.json`);
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(sanitize(fs.readFileSync(p, "utf-8")));
  } catch { return null; }
}

function runKappa(symbol: string) {
  const res = spawnSync(PY_CMD, ["agent_kappa.py", symbol], {
    cwd: DA, encoding: "utf-8", timeout: 120000,
  });
  if (res.status !== 0) {
    throw new Error(res.stderr?.slice(0, 400) || "kappa failed");
  }
}

export async function GET(req: Request) {
  const url     = new URL(req.url);
  const symbols = (url.searchParams.get("symbols") || "").toUpperCase().split(",").map(s => s.trim()).filter(Boolean);
  const force   = url.searchParams.get("force") === "1";

  if (symbols.length < 1)
    return NextResponse.json({ error: "Pass ?symbols=A,B,C (1–5 symbols)" }, { status: 400 });
  if (symbols.length > 5)
    return NextResponse.json({ error: "Max 5 symbols" }, { status: 400 });

  const results: Record<string, any> = {};
  const errors:  Record<string, string> = {};

  for (const sym of symbols) {
    let cached = force ? null : loadCached(sym);
    if (!cached) {
      try { runKappa(sym); cached = loadCached(sym); }
      catch (e: any) { errors[sym] = e.message; continue; }
    }
    if (cached) results[sym] = cached;
    else errors[sym] = "Report not generated";
  }

  return NextResponse.json({ symbols, results, errors });
}
'''
write(SRC / "api" / "compare" / "route.ts", COMPARE_ROUTE, "/api/compare/route.ts")


# ═════════════════════════════════════════════════════════════════════════════
# [2] COMPARE PAGE  /compare/page.tsx
# ═════════════════════════════════════════════════════════════════════════════

print("\n[2/3] Writing /compare/page.tsx ...")

COMPARE_PAGE = '''\
"use client";

import { useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface SeriesStats {
  cagr_pct: number | null;
  ann_volatility_pct: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  calmar_ratio: number | null;
  skewness: number | null;
  kurtosis: number | null;
  n_trading_days: number | null;
  hi_52w: number | null;
  lo_52w: number | null;
  dist_from_52w_hi: number | null;
}
interface WindowRow {
  window_days: number;
  mean: number | null;
  std: number | null;
  p5: number | null;
  p25: number | null;
  p75: number | null;
  p95: number | null;
  prob_positive: number | null;
  prob_gt10: number | null;
  sharpe: number | null;
}
interface RegimeStat {
  regime: string;
  mean: number | null;
  prob_positive: number | null;
  n_windows: number | null;
}
interface Seasonality {
  best_month: { month: string; avg_return: number } | null;
  worst_month: { month: string; avg_return: number } | null;
  best_weekday: { day: string; avg_return: number } | null;
  worst_weekday: { day: string; avg_return: number } | null;
}
interface Technicals {
  rsi_14: number | null;
  macd_signal: string | null;
  adx: number | null;
  dist_sma200: number | null;
  pct_above_sma20: number | null;
  atr_14_pct: number | null;
}
interface KappaReport {
  symbol: string;
  asset_type: string;
  date: string;
  series_stats: SeriesStats;
  window_table: WindowRow[];
  regime_stats_20d: RegimeStat[];
  seasonality: Seasonality;
  technicals: Technicals;
  correlations: Record<string, number | null>;
  llm_verdict: string;
}

// ── Palette ───────────────────────────────────────────────────────────────────
const COLORS = ["#60a5fa", "#34d399", "#f472b6", "#fbbf24", "#a78bfa"];

// ── Helpers ───────────────────────────────────────────────────────────────────
const n  = (v: number | null | undefined, dec = 2) =>
  v == null ? "—" : Number(v).toFixed(dec);
const pct = (v: number | null | undefined, dec = 2) =>
  v == null ? "—" : `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(dec)}%`;
const clr = (v: number | null | undefined) =>
  v == null ? "#94a3b8" : Number(v) >= 0 ? "#22c55e" : "#ef4444";

// ── Mini bar chart for a metric across symbols ────────────────────────────────
function MetricBar({
  label, values, colors, fmt, higherBetter = true,
}: {
  label: string;
  values: (number | null)[];
  colors: string[];
  fmt: (v: number | null) => string;
  higherBetter?: boolean;
}) {
  const valid = values.filter(v => v != null) as number[];
  if (!valid.length) return null;
  const mn  = Math.min(...valid);
  const mx  = Math.max(...valid);
  const rng = mx - mn || 1;

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4, letterSpacing: 1 }}>{label}</div>
      {values.map((v, i) => {
        if (v == null) return null;
        const frac  = (v - mn) / rng;
        const width = higherBetter ? frac * 100 : (1 - frac) * 100;
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
            <div style={{ width: `${Math.max(width, 2)}%`, height: 8, borderRadius: 4,
              background: colors[i], opacity: 0.85, transition: "width 0.4s" }} />
            <span style={{ fontSize: 12, color: colors[i], fontWeight: 700, minWidth: 60 }}>
              {fmt(v)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Window table comparison for one window ────────────────────────────────────
function WindowCompare({
  window, reports, symbols, colors,
}: {
  window: number;
  reports: KappaReport[];
  symbols: string[];
  colors: string[];
}) {
  const rows = reports.map(r => r.window_table?.find(w => w.window_days === window));
  const metrics = [
    { label: "Mean Return", key: "mean",          fmt: pct, higherBetter: true  },
    { label: "Prob Positive", key: "prob_positive", fmt: (v: number | null) => v == null ? "—" : `${v}%`, higherBetter: true },
    { label: "Std Dev",    key: "std",             fmt: pct, higherBetter: false },
    { label: "P5 (downside)", key: "p5",           fmt: pct, higherBetter: false },
    { label: "P95 (upside)", key: "p95",            fmt: pct, higherBetter: true  },
    { label: "Sharpe",     key: "sharpe",           fmt: (v: number | null) => n(v), higherBetter: true },
  ];

  return (
    <div style={{ padding: "14px 0" }}>
      <div style={{ fontSize: 12, color: "#94a3b8", fontWeight: 700, marginBottom: 12 }}>
        {window}d WINDOW
      </div>
      {metrics.map(m => (
        <MetricBar
          key={m.key}
          label={m.label}
          values={rows.map(r => r ? (r as any)[m.key] as number | null : null)}
          colors={colors}
          fmt={m.fmt}
          higherBetter={m.higherBetter}
        />
      ))}
    </div>
  );
}

// ── Regime table ──────────────────────────────────────────────────────────────
function RegimeCompare({ reports, symbols, colors }: { reports: KappaReport[]; symbols: string[]; colors: string[] }) {
  const regimes = ["bull", "bear", "sideways", "all"];
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "6px 10px", color: "#64748b" }}>Regime</th>
            {symbols.map((s, i) => (
              <th key={i} style={{ textAlign: "right", padding: "6px 10px", color: colors[i] }}>{s}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {regimes.map(regime => (
            <tr key={regime} style={{ borderTop: "1px solid #1e293b" }}>
              <td style={{ padding: "6px 10px", color: "#94a3b8", fontWeight: 600, textTransform: "capitalize" }}>
                {regime}
              </td>
              {reports.map((r, i) => {
                const row = r.regime_stats_20d?.find(x => x.regime === regime);
                const v   = row?.mean;
                return (
                  <td key={i} style={{ padding: "6px 10px", textAlign: "right", color: clr(v), fontWeight: 700 }}>
                    {pct(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Correlation heatmap row ───────────────────────────────────────────────────
function CorrRow({ label, values, colors }: { label: string; values: (number | null)[]; colors: string[] }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}>
      <span style={{ fontSize: 11, color: "#64748b", minWidth: 70 }}>{label}</span>
      {values.map((v, i) => {
        const abs  = v == null ? 0 : Math.abs(v);
        const bg   = v == null ? "#1e293b"
                   : v > 0    ? `rgba(34,197,94,${abs * 0.7})`
                   :             `rgba(239,68,68,${abs * 0.7})`;
        return (
          <div key={i} style={{
            minWidth: 56, textAlign: "center",
            padding: "4px 8px", borderRadius: 6,
            background: bg, fontSize: 12,
            color: abs > 0.3 ? "#f8fafc" : "#64748b",
            fontWeight: 700,
          }}>{v == null ? "—" : v.toFixed(2)}</div>
        );
      })}
    </div>
  );
}

// ── Technicals table ──────────────────────────────────────────────────────────
function TechRow({ label, values, colors, fmt, higherBetter }: {
  label: string;
  values: (string | number | null)[];
  colors: string[];
  fmt?: (v: any) => string;
  higherBetter?: boolean;
}) {
  const f = fmt || ((v: any) => v == null ? "—" : String(v));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
      <span style={{ fontSize: 11, color: "#64748b", minWidth: 90 }}>{label}</span>
      {values.map((v, i) => (
        <span key={i} style={{
          fontSize: 12, fontWeight: 700,
          color: colors[i], minWidth: 70,
        }}>{f(v)}</span>
      ))}
    </div>
  );
}

// ── Card wrapper ──────────────────────────────────────────────────────────────
function Card({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155",
      borderRadius: 12, padding: "16px 20px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "#e2e8f0", letterSpacing: 1 }}>
          {title}
        </h3>
      </div>
      {children}
    </div>
  );
}

// ── LLM Verdict panel ─────────────────────────────────────────────────────────
function VerdictPanel({ symbol, verdict, color }: { symbol: string; verdict: string; color: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{
      background: "#0f172a", border: `1px solid ${color}44`,
      borderRadius: 10, padding: "10px 14px", marginBottom: 8,
    }}>
      <div style={{ display: "flex", alignItems: "center", cursor: "pointer" }}
        onClick={() => setOpen(o => !o)}>
        <span style={{ fontWeight: 700, color, fontSize: 13, fontFamily: "monospace" }}>{symbol}</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#64748b" }}>
          {open ? "▲ collapse" : "▼ expand"}
        </span>
      </div>
      {open && (
        <p style={{ margin: "10px 0 0", fontSize: 12, color: "#cbd5e1", lineHeight: 1.7 }}>
          {verdict}
        </p>
      )}
    </div>
  );
}

// ── Symbol input pill ─────────────────────────────────────────────────────────
function SymbolPill({
  symbol, color, onRemove,
}: { symbol: string; color: string; onRemove: () => void }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: `${color}22`, border: `1px solid ${color}55`,
      borderRadius: 999, padding: "4px 12px",
      fontFamily: "monospace", fontWeight: 700, fontSize: 13, color,
    }}>
      {symbol}
      <button onClick={onRemove} style={{
        background: "none", border: "none", cursor: "pointer",
        color: "#64748b", fontSize: 14, lineHeight: 1, padding: 0,
      }}>×</button>
    </span>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═════════════════════════════════════════════════════════════════════════════
export default function ComparePage() {
  const [input,    setInput]    = useState("");
  const [symbols,  setSymbols]  = useState<string[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [reports,  setReports]  = useState<Record<string, KappaReport>>({});
  const [errors,   setErrors]   = useState<Record<string, string>>({});
  const [activeWin, setActiveWin] = useState(20);
  const [status,   setStatus]   = useState("");

  const WINDOWS = [5, 10, 20, 30, 60, 90];

  const addSymbol = useCallback(() => {
    const s = input.trim().toUpperCase();
    if (!s || symbols.includes(s) || symbols.length >= 5) return;
    setSymbols(prev => [...prev, s]);
    setInput("");
  }, [input, symbols]);

  const removeSymbol = useCallback((s: string) => {
    setSymbols(prev => prev.filter(x => x !== s));
    setReports(prev => { const r = { ...prev }; delete r[s]; return r; });
  }, []);

  const runCompare = useCallback(async (force = false) => {
    if (symbols.length < 1) return;
    setLoading(true);
    setStatus("Running Kappa agent for each symbol (may take ~30s per new symbol)…");
    setErrors({});
    try {
      const res  = await fetch(`/api/compare?symbols=${symbols.join(",")}&force=${force ? 1 : 0}`);
      const data = await res.json();
      setReports(data.results || {});
      setErrors(data.errors   || {});
      const loaded = Object.keys(data.results || {}).length;
      setStatus(`Loaded ${loaded}/${symbols.length} symbol${loaded !== 1 ? "s" : ""}.${
        Object.keys(data.errors || {}).length ? " Some failed — see errors below." : ""
      }`);
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [symbols]);

  const loaded  = symbols.filter(s => reports[s]);
  const colors  = symbols.map((_, i) => COLORS[i % COLORS.length]);
  const lColors = loaded.map(s => colors[symbols.indexOf(s)]);

  // Correlation benchmarks (common ones)
  const corrBenchmarks = ["SPX", "GOLD", "DXY", "VIX", "USDINR", "NIFTY50"];

  return (
    <div style={{
      minHeight: "100vh", background: "#0f172a",
      color: "#e2e8f0", fontFamily: "system-ui, sans-serif",
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: "20px 28px 14px", borderBottom: "1px solid #1e293b",
      }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "#f8fafc" }}>
          ⚖️ Compare Stocks
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#64748b" }}>
          Side-by-side deep profile comparison — up to 5 symbols
        </p>
      </div>

      {/* ── Input bar ── */}
      <div style={{ padding: "18px 28px", borderBottom: "1px solid #1e293b" }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {symbols.map((s, i) => (
            <SymbolPill key={s} symbol={s} color={COLORS[i % COLORS.length]}
              onRemove={() => removeSymbol(s)} />
          ))}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => { if (e.key === "Enter") addSymbol(); }}
            placeholder={symbols.length >= 5 ? "Max 5 symbols" : "Type symbol + Enter (e.g. RELIANCE)"}
            disabled={symbols.length >= 5}
            style={{
              flex: 1, maxWidth: 260, padding: "8px 14px",
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: 8, color: "#f8fafc", fontSize: 14,
              outline: "none",
            }}
          />
          <button onClick={addSymbol} disabled={!input.trim() || symbols.length >= 5}
            style={{
              padding: "8px 16px", background: "#3b82f6", color: "#fff",
              border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 700,
            }}>+ Add</button>
          <button onClick={() => runCompare(false)}
            disabled={loading || symbols.length < 1}
            style={{
              padding: "8px 20px",
              background: loading ? "#334155" : "#22c55e",
              color: "#fff", border: "none", borderRadius: 8,
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: 13, fontWeight: 700,
            }}>
            {loading ? "⚙️ Running…" : "▶ Compare"}
          </button>
          <button onClick={() => runCompare(true)}
            disabled={loading || symbols.length < 1}
            title="Force re-run Kappa (ignore cache)"
            style={{
              padding: "8px 14px", background: "#334155",
              color: "#94a3b8", border: "1px solid #475569",
              borderRadius: 8, cursor: "pointer", fontSize: 12,
            }}>↺ Refresh</button>
        </div>

        {status && (
          <p style={{ margin: "10px 0 0", fontSize: 12,
            color: loading ? "#fbbf24" : "#64748b" }}>{status}</p>
        )}

        {/* Quick-add popular */}
        <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: "#475569" }}>Quick add:</span>
          {["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "NIFTY50"].map(s => (
            <button key={s} onClick={() => {
              if (!symbols.includes(s) && symbols.length < 5) {
                setSymbols(prev => [...prev, s]);
              }
            }} style={{
              fontSize: 11, fontFamily: "monospace",
              background: symbols.includes(s) ? "#1e293b" : "#0f172a",
              color: symbols.includes(s) ? "#475569" : "#60a5fa",
              border: "1px solid #334155", borderRadius: 6,
              padding: "2px 8px", cursor: "pointer",
            }}>{s}</button>
          ))}
        </div>

        {/* Errors */}
        {Object.entries(errors).map(([sym, err]) => (
          <div key={sym} style={{
            marginTop: 8, padding: "6px 12px",
            background: "#2d1515", borderRadius: 8,
            fontSize: 12, color: "#ef4444",
          }}>⚠️ <strong>{sym}</strong>: {err}</div>
        ))}
      </div>

      {/* ── Results ── */}
      {loaded.length > 0 && (
        <div style={{ padding: "20px 28px" }}>

          {/* Symbol legend */}
          <div style={{ display: "flex", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
            {loaded.map((s, i) => (
              <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 14, height: 14, borderRadius: 3, background: lColors[i] }} />
                <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 14, color: lColors[i] }}>{s}</span>
                <span style={{ fontSize: 11, color: "#64748b" }}>
                  ({reports[s]?.asset_type || "stock"} · {reports[s]?.date})
                </span>
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>

            {/* ── Key Stats ── */}
            <Card icon="📈" title="KEY STATS">
              {[
                { label: "CAGR", vals: loaded.map(s => reports[s]?.series_stats?.cagr_pct ?? null), fmt: pct, hb: true },
                { label: "Ann Volatility", vals: loaded.map(s => reports[s]?.series_stats?.ann_volatility_pct ?? null), fmt: pct, hb: false },
                { label: "Max Drawdown", vals: loaded.map(s => reports[s]?.series_stats?.max_drawdown_pct ?? null), fmt: pct, hb: false },
                { label: "Sharpe", vals: loaded.map(s => reports[s]?.series_stats?.sharpe_ratio ?? null), fmt: (v: number|null) => n(v), hb: true },
                { label: "Sortino", vals: loaded.map(s => reports[s]?.series_stats?.sortino_ratio ?? null), fmt: (v: number|null) => n(v), hb: true },
                { label: "Calmar", vals: loaded.map(s => reports[s]?.series_stats?.calmar_ratio ?? null), fmt: (v: number|null) => n(v), hb: true },
              ].map(m => (
                <MetricBar key={m.label} label={m.label} values={m.vals}
                  colors={lColors} fmt={m.fmt} higherBetter={m.hb} />
              ))}
            </Card>

            {/* ── Technicals ── */}
            <Card icon="🔧" title="TECHNICALS">
              <TechRow label="RSI 14"
                values={loaded.map(s => reports[s]?.technicals?.rsi_14 ?? null)}
                colors={lColors}
                fmt={(v: number|null) => v == null ? "—" : `${v.toFixed(1)}`}
              />
              <TechRow label="MACD Signal"
                values={loaded.map(s => reports[s]?.technicals?.macd_signal ?? null)}
                colors={lColors}
              />
              <TechRow label="ADX 14"
                values={loaded.map(s => reports[s]?.technicals?.adx ?? null)}
                colors={lColors}
                fmt={(v: number|null) => v == null ? "—" : `${v.toFixed(1)}`}
              />
              <TechRow label="Dist SMA200"
                values={loaded.map(s => reports[s]?.technicals?.dist_sma200 ?? null)}
                colors={lColors}
                fmt={pct}
              />
              <TechRow label="ATR 14%"
                values={loaded.map(s => reports[s]?.technicals?.atr_14_pct ?? null)}
                colors={lColors}
                fmt={pct}
              />
              <div style={{ borderTop: "1px solid #334155", marginTop: 10, paddingTop: 10 }}>
                <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6 }}>52W RANGE</div>
                {loaded.map((s, i) => {
                  const st  = reports[s]?.series_stats;
                  const dist = st?.dist_from_52w_hi;
                  return (
                    <div key={s} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontSize: 11, color: lColors[i], fontFamily: "monospace", minWidth: 80 }}>{s}</span>
                      <span style={{ fontSize: 11, color: "#94a3b8" }}>
                        {st?.lo_52w?.toFixed(0) ?? "?"} – {st?.hi_52w?.toFixed(0) ?? "?"}
                      </span>
                      {dist != null && (
                        <span style={{ fontSize: 11, color: "#ef4444", marginLeft: "auto" }}>
                          {dist.toFixed(1)}% from high
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>

            {/* ── Window stats ── */}
            <Card icon="🗓" title="WINDOW BEHAVIOR">
              <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
                {WINDOWS.map(w => (
                  <button key={w} onClick={() => setActiveWin(w)} style={{
                    padding: "4px 12px", borderRadius: 999, fontSize: 12, fontWeight: 700,
                    background: activeWin === w ? "#3b82f6" : "#334155",
                    color: activeWin === w ? "#fff" : "#94a3b8",
                    border: "none", cursor: "pointer",
                  }}>{w}d</button>
                ))}
              </div>
              <WindowCompare
                window={activeWin}
                reports={loaded.map(s => reports[s])}
                symbols={loaded}
                colors={lColors}
              />
            </Card>

            {/* ── Regime stats ── */}
            <Card icon="🌊" title="REGIME STATS (20d mean return)">
              <RegimeCompare
                reports={loaded.map(s => reports[s])}
                symbols={loaded}
                colors={lColors}
              />
            </Card>

            {/* ── Seasonality ── */}
            <Card icon="📆" title="SEASONALITY">
              {[
                { label: "Best Month",    key: "best_month",    sub: "month",   sub2: "avg_return" },
                { label: "Worst Month",   key: "worst_month",   sub: "month",   sub2: "avg_return" },
                { label: "Best Weekday",  key: "best_weekday",  sub: "day",     sub2: "avg_return" },
                { label: "Worst Weekday", key: "worst_weekday", sub: "day",     sub2: "avg_return" },
              ].map(m => (
                <div key={m.key} style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>{m.label}</div>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {loaded.map((s, i) => {
                      const seas = reports[s]?.seasonality?.[m.key as keyof Seasonality] as any;
                      return (
                        <div key={s} style={{
                          fontSize: 12, fontWeight: 700, color: lColors[i],
                          background: "#0f172a", borderRadius: 6,
                          padding: "3px 10px",
                        }}>
                          {seas ? `${seas[m.sub]} (${seas[m.sub2]?.toFixed(1) ?? "?"}%)` : "—"}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </Card>

            {/* ── Correlations ── */}
            <Card icon="🔗" title="CORRELATIONS">
              <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
                <span style={{ minWidth: 70 }} />
                {loaded.map((s, i) => (
                  <span key={s} style={{ minWidth: 56, fontSize: 11, fontWeight: 700,
                    color: lColors[i], fontFamily: "monospace", textAlign: "center" }}>{s}</span>
                ))}
              </div>
              {corrBenchmarks.map(bm => {
                const vals = loaded.map(s => {
                  const c = reports[s]?.correlations || {};
                  return (c[bm] ?? c[bm.toLowerCase()] ?? null) as number | null;
                });
                if (vals.every(v => v == null)) return null;
                return <CorrRow key={bm} label={bm} values={vals} colors={lColors} />;
              })}
              {/* Inter-symbol correlation hint */}
              {loaded.length >= 2 && (
                <p style={{ margin: "12px 0 0", fontSize: 11, color: "#475569" }}>
                  ℹ️ Values show correlation of each symbol to global benchmarks (1y window).
                </p>
              )}
            </Card>

          </div>

          {/* ── LLM Verdicts ── */}
          <div style={{ marginTop: 18 }}>
            <Card icon="🧠" title="LLM VERDICTS">
              {loaded.map((s, i) => (
                <VerdictPanel key={s} symbol={s}
                  verdict={String(reports[s]?.llm_verdict || "No verdict available.")}
                  color={lColors[i]} />
              ))}
            </Card>
          </div>

        </div>
      )}

      {/* ── Empty state ── */}
      {loaded.length === 0 && !loading && symbols.length > 0 && (
        <div style={{ padding: "60px 28px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
          <p style={{ color: "#64748b", fontSize: 14 }}>
            Press <strong style={{ color: "#22c55e" }}>▶ Compare</strong> to run analysis
          </p>
        </div>
      )}

      {loaded.length === 0 && !loading && symbols.length === 0 && (
        <div style={{ padding: "80px 28px", textAlign: "center" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚖️</div>
          <h2 style={{ color: "#e2e8f0", marginBottom: 8 }}>Compare up to 5 stocks side-by-side</h2>
          <p style={{ color: "#64748b", fontSize: 14, maxWidth: 440, margin: "0 auto 20px" }}>
            Type a symbol and press Enter or click Add. Then press Compare.
            Uses cached Kappa reports when available — or runs fresh analysis.
          </p>
          <p style={{ color: "#475569", fontSize: 12 }}>
            Metrics: CAGR · Sharpe · Drawdown · Window behavior · Regime stats · Seasonality · Correlations · LLM verdict
          </p>
        </div>
      )}
    </div>
  );
}
'''
write(SRC / "compare" / "page.tsx", COMPARE_PAGE, "/compare/page.tsx")


# ═════════════════════════════════════════════════════════════════════════════
# [3] NAVBAR — add COMPARE link
# ═════════════════════════════════════════════════════════════════════════════

print("\n[3/3] Patching NavBar.tsx ...")
patch_navbar("/compare", "COMPARE")


# ═════════════════════════════════════════════════════════════════════════════
# DONE
# ═════════════════════════════════════════════════════════════════════════════

print("""
=============================================================
BUILD PHASE 15 (COMPARE PAGE) COMPLETE
=============================================================

[1] /api/compare/route.ts
    - GET ?symbols=RELIANCE,HDFCBANK,ICICIBANK
    - ?force=1 to re-run Kappa (skip cache)
    - Reads from agents/kappa/<SYM>_report.json
    - Runs py agent_kappa.py <SYM> automatically if no cache

[2] /compare/page.tsx
    - Search bar: type + Enter to add symbols (max 5)
    - Quick-add: RELIANCE HDFCBANK ICICIBANK INFY TCS NIFTY50
    - ▶ Compare button: loads cached or runs fresh Kappa
    - ↺ Refresh: force re-run all symbols
    - 6 comparison panels:
        📈 Key Stats (CAGR / Vol / DD / Sharpe / Sortino / Calmar)
        🔧 Technicals (RSI / MACD / ADX / SMA200 / ATR / 52w range)
        🗓 Window Behavior (5/10/20/30/60/90d — switchable)
        🌊 Regime Stats (bull/bear/sideways/all)
        📆 Seasonality (best/worst month + weekday)
        🔗 Correlations (SPX/Gold/DXY/VIX/USDINR/NIFTY50)
    - 🧠 LLM Verdicts (collapsible per symbol)
    - Visual: color-coded bars, heatmap cells for correlations

[3] NavBar.tsx — COMPARE link added

NEXT STEPS:
  cd D:\\MICC\\micc-dashboard && npm run dev
  Open: localhost:3000/compare

  Try: RELIANCE + HDFCBANK + ICICIBANK -> Compare
  (first run takes ~30s per symbol if no cached report)

QUEUE REMAINING:
  - Smaller windows (1/2/3/4d) in seasonality builder
  - Backtest analysis in PatCard expanded view
  - Indian indices fetch + re-run seasonality
=============================================================
""")
