# -*- coding: utf-8 -*-
"""
setup_phase9d.py  --  Run from D:\MICC
Phase 9D: Deep Analysis Room Dashboard

Creates:
  1. /api/deep/route.ts               -- Iota room data (reads last_report.json)
  2. /api/deep/[symbol]/route.ts      -- Kappa per-symbol data
  3. /api/compare/route.ts            -- Lambda: multi-symbol comparison from DB
  4. /api/eta/route.ts                -- Eta corporate events (was pending)
  5. /deep/page.tsx                   -- Iota dashboard (6 screens + LLM)
  6. /deep/[symbol]/page.tsx          -- Kappa deep profile
  7. /compare/page.tsx                -- Lambda side-by-side comparison
  8. /eta/page.tsx                    -- Eta corporate events dashboard
  9. NavBar.tsx patch                 -- DEEP + ETA links
 10. telegram_bot.py patch            -- /eta /deep /kappa commands

Run: py D:\MICC\setup_phase9d.py
"""

from pathlib import Path
import re

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
APP  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# =============================================================================
# [1/10] /api/deep/route.ts  -- Iota last_report.json reader
# =============================================================================
print("\n[1/10] /api/deep/route.ts")

write(APP / "api" / "deep" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'
const DB = 'D:/marketDB/db/market.db'

function queryDb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[deep]', r.stderr?.slice(0, 200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: unknown) { console.error('[deep]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    // Load Iota last report
    const reportPath = path.join(DA, 'agents', 'iota', 'last_report.json')
    let report: Record<string, unknown> = {}
    if (fs.existsSync(reportPath)) {
      report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'))
    }

    // Augment with current regime from global_indices_daily
    const globalSnap = queryDb(`
      SELECT symbol, close, date,
             ROUND((close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date)) /
                   LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date) * 100, 2) AS ret_5d
      FROM global_indices_daily
      WHERE symbol IN ('SPX','NDX','VIX','DXY','GOLD','USDINR','NIKKEI225','DAX','FTSE100')
        AND date >= date('now', '-10 days')
      ORDER BY symbol, date DESC
    `)

    // Latest per symbol
    const latestGlobal: Record<string, unknown> = {}
    for (const row of globalSnap as Record<string, unknown>[]) {
      const sym = row.symbol as string
      if (!latestGlobal[sym]) latestGlobal[sym] = row
    }

    // Nifty 50 20d return from market_snapshot for regime
    const niftyRows = queryDb(`
      SELECT close, date FROM market_snapshot
      WHERE index_name = 'NIFTY 50' AND close > 5000
      ORDER BY date DESC LIMIT 21
    `)
    let regime = report.current_regime || 'UNKNOWN'
    let nifty20d = report.nifty_20d_return || null

    return NextResponse.json({
      ok: true,
      report,
      global_snapshot: latestGlobal,
      nifty_20d_return: nifty20d,
      current_regime: regime,
      report_date: report.date || null,
      report_timestamp: report.timestamp || null,
    })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")


# =============================================================================
# [2/10] /api/deep/[symbol]/route.ts  -- Kappa per-symbol report
# =============================================================================
print("\n[2/10] /api/deep/[symbol]/route.ts")

write(APP / "api" / "deep" / "[symbol]" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'
const DB = 'D:/marketDB/db/market.db'

function queryDb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[deep/sym]', r.stderr?.slice(0, 200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: unknown) { console.error('[deep/sym]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(
  _req: Request,
  { params }: { params: { symbol: string } }
) {
  const sym = (params.symbol ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  try {
    // Try to load cached Kappa report
    const reportPath = path.join(DA, 'agents', 'kappa', `${sym}_report.json`)
    let report: Record<string, unknown> | null = null
    if (fs.existsSync(reportPath)) {
      report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'))
    }

    // Always pull fresh technicals from DB
    const technicals = queryDb(
      `SELECT * FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1`,
      [sym]
    )

    // Window stats (key windows: 5,10,20,60)
    const windowStats = queryDb(
      `SELECT window_days, n_windows, mean_return, std_return,
              p5, p25, p75, p95, prob_positive, prob_gt10, prob_lt_neg10,
              sharpe_ratio, ann_return_equiv
       FROM window_stats WHERE symbol=?
       ORDER BY window_days`,
      [sym]
    )

    // Seasonality (monthly)
    const seasonality = queryDb(
      `SELECT period_value, n_obs, mean_return_pct, median_return_pct
       FROM symbol_seasonality WHERE symbol=? AND period_type='month'
       ORDER BY period_value`,
      [sym]
    )

    // Top correlations
    const correlations = queryDb(
      `SELECT symbol_b, correlation_20d, correlation_60d, beta_20d
       FROM symbol_correlations WHERE symbol_a=?
       ORDER BY ABS(correlation_20d) DESC LIMIT 10`,
      [sym]
    )

    // Regime stats
    const regimeStats = queryDb(
      `SELECT regime, n_windows, mean_return, std_return, prob_positive, p5, p95
       FROM window_regime_stats WHERE symbol=? AND window_days=20
       ORDER BY regime`,
      [sym]
    )

    // Latest price from stock_data
    const priceRow = queryDb(
      `SELECT close, date, volume FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`,
      [sym]
    )

    // Recent insider activity
    const insider = queryDb(
      `SELECT filing_date, name, category, transaction_type, quantity, price, value
       FROM insider_trading WHERE symbol=?
         AND transaction_type IN ('BUY','SELL')
       ORDER BY filing_date DESC LIMIT 10`,
      [sym]
    )

    // Recent corporate announcements
    const announcements = queryDb(
      `SELECT announcement_date, subject FROM corporate_announcements
       WHERE symbol=? ORDER BY announcement_date DESC LIMIT 8`,
      [sym]
    )

    // Series stats
    const seriesStats = queryDb(
      `SELECT cagr_pct, ann_volatility_pct, max_drawdown_pct,
              sharpe_ratio, sortino_ratio, calmar_ratio,
              n_trading_days, mdd_start_date, mdd_trough_date, mdd_recovery_days
       FROM symbol_series_stats WHERE symbol=? LIMIT 1`,
      [sym]
    )

    return NextResponse.json({
      ok: true,
      symbol: sym,
      report,            // null if Kappa not run yet for this symbol
      technicals:        technicals[0] || null,
      window_stats:      windowStats,
      seasonality,
      correlations,
      regime_stats:      regimeStats,
      series_stats:      seriesStats[0] || null,
      latest_price:      priceRow[0] || null,
      insider_trades:    insider,
      announcements,
      has_cached_report: !!report,
    })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")


# =============================================================================
# [3/10] /api/compare/route.ts  -- Lambda multi-symbol comparison
# =============================================================================
print("\n[3/10] /api/compare/route.ts")

write(APP / "api" / "compare" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'
const DB = 'D:/marketDB/db/market.db'

function queryDb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 30000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[compare]', r.stderr?.slice(0, 200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: unknown) { console.error('[compare]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const symsParam = searchParams.get('symbols') || ''
  const symbols = symsParam.split(',')
    .map(s => s.trim().toUpperCase().replace(/[^A-Z0-9]/g, ''))
    .filter(s => s.length > 0)
    .slice(0, 5)

  if (symbols.length < 2) {
    return NextResponse.json({ ok: false, error: 'Need 2-5 symbols' }, { status: 400 })
  }

  const placeholders = symbols.map(() => '?').join(',')

  try {
    // Series stats for all symbols
    const seriesStats = queryDb(
      `SELECT symbol, cagr_pct, ann_volatility_pct, max_drawdown_pct,
              sharpe_ratio, sortino_ratio, calmar_ratio, n_trading_days
       FROM symbol_series_stats WHERE symbol IN (${placeholders})`,
      symbols
    )

    // Window stats for 5d, 10d, 20d, 60d windows
    const windowStats = queryDb(
      `SELECT symbol, window_days, mean_return, std_return,
              p5, p95, prob_positive, prob_gt10, sharpe_ratio
       FROM window_stats
       WHERE symbol IN (${placeholders}) AND window_days IN (5,10,20,60)
       ORDER BY symbol, window_days`,
      symbols
    )

    // Technicals
    const technicals = queryDb(
      `SELECT t.symbol, t.atr_14_pct, t.adx_14, t.pct_above_sma20,
              t.vol_surge_20d, t.rsi_14, t.macd_line, t.macd_signal,
              t.bb_pct, t.as_of_date
       FROM symbol_technicals t
       INNER JOIN (
         SELECT symbol, MAX(as_of_date) as max_date
         FROM symbol_technicals WHERE symbol IN (${placeholders})
         GROUP BY symbol
       ) latest ON t.symbol = latest.symbol AND t.as_of_date = latest.max_date`,
      [...symbols, ...symbols]
    )

    // Latest prices
    const prices = queryDb(
      `SELECT p.symbol, p.close, p.date, p.volume
       FROM stock_data p
       INNER JOIN (
         SELECT symbol, MAX(date) as max_date FROM stock_data
         WHERE symbol IN (${placeholders}) GROUP BY symbol
       ) latest ON p.symbol = latest.symbol AND p.date = latest.max_date`,
      [...symbols, ...symbols]
    )

    // Regime stats for 20d window
    const regimeStats = queryDb(
      `SELECT symbol, regime, n_windows, mean_return, prob_positive, p5, p95
       FROM window_regime_stats
       WHERE symbol IN (${placeholders}) AND window_days=20
       ORDER BY symbol, regime`,
      symbols
    )

    // Seasonality (monthly means)
    const seasonality = queryDb(
      `SELECT symbol, period_value, mean_return_pct, n_obs
       FROM symbol_seasonality
       WHERE symbol IN (${placeholders}) AND period_type='month'
       ORDER BY symbol, period_value`,
      symbols
    )

    // Cross-correlations between the requested symbols
    const crossCorr = queryDb(
      `SELECT symbol_a, symbol_b, correlation_20d, correlation_60d, beta_20d
       FROM symbol_correlations
       WHERE symbol_a IN (${placeholders}) AND symbol_b IN (${placeholders})`,
      [...symbols, ...symbols]
    )

    // Recent signals_history appearances
    const recentSignals = queryDb(
      `SELECT symbol, COUNT(DISTINCT run_date) as days_seen,
              MAX(run_date) as last_seen, AVG(CAST(score AS REAL)) as avg_score
       FROM signals_history
       WHERE symbol IN (${placeholders}) AND run_date >= date('now','-30 days')
       GROUP BY symbol`,
      symbols
    )

    return NextResponse.json({
      ok: true,
      symbols,
      series_stats:    seriesStats,
      window_stats:    windowStats,
      technicals,
      prices,
      regime_stats:    regimeStats,
      seasonality,
      cross_correlations: crossCorr,
      recent_signals:  recentSignals,
    })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")


# =============================================================================
# [4/10] /api/eta/route.ts  -- Eta corporate events (pending since Phase 8)
# =============================================================================
print("\n[4/10] /api/eta/route.ts")

write(APP / "api" / "eta" / "route.ts", r"""
import { NextResponse } from 'next/server'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const reportPath = path.join(DA, 'agents', 'eta', 'last_report.json')
    if (!fs.existsSync(reportPath)) {
      return NextResponse.json({
        ok: false,
        error: 'Eta report not found. Run: py D:/MICC/agent_eta.py',
      }, { status: 404 })
    }
    const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'))
    return NextResponse.json({ ok: true, report })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")


# =============================================================================
# [5/10] /deep/page.tsx  -- Iota Deep Analysis Room dashboard
# =============================================================================
print("\n[5/10] /deep/page.tsx")

write(APP / "deep" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import MarkdownText from "@/components/MarkdownText";

// ── Types ──────────────────────────────────────────────────────────────────

interface Screen1Row {
  symbol: string; prob_positive: number; mean_return: number;
  p5_worst: number; p95_best: number; n_windows: number;
}
interface Screen2Row {
  symbol: string; sharpe_ratio: number; mean_return: number;
  p5_floor: number; win_rate: number;
}
interface Screen3Row {
  symbol: string; p5_floor: number; mean_return: number;
  downside_capture: number; prob_positive: number;
}
interface Screen4Row {
  symbol: string; bull_mean: number; bear_mean: number;
  sensitivity: number; current_regime_mean: number;
}
interface GlobalRow {
  symbol: string; close: number; date: string; ret_5d: number | null;
}
interface IndexStatRow {
  index_name: string;
  window_stats: {
    window_days: number; mean_return: number; prob_positive: number;
    p5: number; p95: number; sharpe: number;
  }[];
}
interface IotaData {
  ok: boolean; error?: string;
  report: {
    date: string; timestamp: string; current_regime: string;
    vix: number; nifty_20d_return: number;
    screen1_best_probability: Screen1Row[];
    screen2_risk_adjusted: Screen2Row[];
    screen3_worst_case: Screen3Row[];
    screen4_regime_movers: Screen4Row[];
    screen5_global: {
      global_risk: string; vix: number; spx_5d: number;
      dxy_5d: number; gold_5d: number;
      spx_correlated_stocks: { symbol: string; correlation: number }[];
      gold_correlated_stocks: { symbol: string; correlation: number }[];
      dxy_sensitive_stocks:   { symbol: string; correlation: number }[];
    };
    screen6_index_stats: IndexStatRow[];
    llm_analysis: string;
  };
  global_snapshot: Record<string, GlobalRow>;
  current_regime: string;
  nifty_20d_return: number;
}

// ── Colour helpers ──────────────────────────────────────────────────────────

const C = {
  green:   "var(--accent-green)",
  red:     "var(--accent-red)",
  cyan:    "var(--accent-cyan)",
  yellow:  "var(--accent-yellow)",
  orange:  "var(--accent-orange, #f97316)",
  dim:     "var(--text-tertiary)",
  primary: "var(--text-primary)",
  border:  "var(--border-color)",
  surface: "var(--surface-card)",
};

function pct(v: number | null | undefined, dec = 1): string {
  if (v == null) return "--";
  return `${v >= 0 ? "+" : ""}${Number(v).toFixed(dec)}%`;
}
function num(v: number | null | undefined, dec = 2): string {
  if (v == null) return "--";
  return Number(v).toFixed(dec);
}
function col(v: number | null | undefined) {
  if (v == null) return C.dim;
  return v >= 0 ? C.green : C.red;
}
function regimeColor(r: string) {
  if (r.includes("BULL")) return C.green;
  if (r.includes("BEAR")) return C.red;
  if (r.includes("STRESS")) return C.red;
  return C.yellow;
}
function riskColor(r: string) {
  if (r === "LOW")    return C.green;
  if (r === "HIGH")   return C.red;
  if (r === "CRISIS") return C.red;
  return C.yellow;
}

// ── Sub-components ──────────────────────────────────────────────────────────

function Card({ title, children, accent }: {
  title: string; children: React.ReactNode; accent?: string;
}) {
  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${accent || C.border}`,
      borderRadius: 8, padding: "16px 20px", marginBottom: 20,
    }}>
      <div style={{
        fontSize: 11, fontWeight: 700, letterSpacing: 1.5,
        color: accent || C.cyan, textTransform: "uppercase",
        marginBottom: 12, borderBottom: `1px solid ${C.border}`, paddingBottom: 8,
      }}>{title}</div>
      {children}
    </div>
  );
}

function Chip({ label, color }: { label: string; color?: string }) {
  return (
    <span style={{
      background: `${color || C.cyan}22`, color: color || C.cyan,
      border: `1px solid ${color || C.cyan}44`,
      borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 700,
    }}>{label}</span>
  );
}

function StatRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 13 }}>
      <span style={{ color: C.dim }}>{label}</span>
      <span style={{ color: color || C.primary, fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function SymbolTable({ rows, cols, onSymbol }: {
  rows: Record<string, unknown>[];
  cols: { key: string; label: string; fmt?: (v: unknown) => string; color?: (v: unknown) => string }[];
  onSymbol?: (s: string) => void;
}) {
  if (!rows || rows.length === 0) {
    return <div style={{ color: C.dim, fontSize: 12, padding: "8px 0" }}>No data</div>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {cols.map(c => (
              <th key={c.key} style={{
                textAlign: c.key === "symbol" ? "left" : "right",
                color: C.dim, fontWeight: 600, padding: "4px 8px",
                borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap",
              }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
              {cols.map(c => {
                const v = row[c.key];
                const txt = c.fmt ? c.fmt(v) : String(v ?? "--");
                const clr = c.color ? c.color(v) : (c.key === "symbol" ? C.cyan : C.primary);
                return (
                  <td key={c.key} style={{
                    padding: "5px 8px", color: clr, fontWeight: c.key === "symbol" ? 700 : 400,
                    textAlign: c.key === "symbol" ? "left" : "right",
                    cursor: c.key === "symbol" && onSymbol ? "pointer" : "default",
                  }}
                    onClick={c.key === "symbol" && onSymbol ? () => onSymbol(String(v)) : undefined}
                  >{txt}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GlobalBar({ snap }: { snap: Record<string, GlobalRow> }) {
  const items = ["SPX", "NDX", "VIX", "DXY", "GOLD", "USDINR"].map(s => ({ sym: s, d: snap[s] }));
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
      {items.map(({ sym, d }) => (
        <div key={sym} style={{
          background: `${C.border}33`, borderRadius: 6, padding: "8px 12px",
          minWidth: 90, textAlign: "center",
        }}>
          <div style={{ fontSize: 10, color: C.dim, fontWeight: 700 }}>{sym}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.primary }}>
            {d ? (d.close > 1000 ? Math.round(d.close).toLocaleString() : Number(d.close).toFixed(2)) : "--"}
          </div>
          <div style={{ fontSize: 11, color: d?.ret_5d != null ? col(d.ret_5d) : C.dim }}>
            {d?.ret_5d != null ? pct(d.ret_5d) : "5d --"}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function DeepPage() {
  const router = useRouter();
  const [data, setData] = useState<IotaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeScreen, setActiveScreen] = useState(0);
  const [symInput, setSymInput] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch("/api/deep", { cache: "no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "API error");
      setData(d);
    } catch (e: unknown) {
      setError(String(e));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const goSymbol = (sym: string) => router.push(`/deep/${sym}`);

  if (loading) return (
    <div style={{ padding: 40, color: C.dim, textAlign: "center" }}>Loading Deep Analysis Room...</div>
  );
  if (error) return (
    <div style={{ padding: 40, color: C.red }}>Error: {error}</div>
  );
  if (!data?.report?.date) return (
    <div style={{ padding: 40, color: C.yellow }}>
      No Iota report found. Run: <code>py D:\MICC\agent_iota.py</code>
    </div>
  );

  const rpt = data.report;
  const screens = [
    "Best Probability", "Risk-Adjusted", "Worst-Case Floor",
    "Regime Movers", "Global Macro", "Index Deep Stats",
  ];

  const s1cols = [
    { key: "symbol",        label: "Symbol" },
    { key: "prob_positive", label: "Prob+",  fmt: (v: unknown) => `${v}%`, color: () => C.green },
    { key: "mean_return",   label: "Mean",   fmt: (v: unknown) => pct(v as number), color: (v: unknown) => col(v as number) },
    { key: "p5_worst",      label: "P5 Floor", fmt: (v: unknown) => pct(v as number), color: (v: unknown) => col(v as number) },
    { key: "p95_best",      label: "P95 Best", fmt: (v: unknown) => pct(v as number), color: () => C.cyan },
    { key: "n_windows",     label: "N",       fmt: (v: unknown) => String(v) },
  ];
  const s2cols = [
    { key: "symbol",       label: "Symbol" },
    { key: "sharpe_ratio", label: "Sharpe", fmt: (v: unknown) => num(v as number), color: () => C.cyan },
    { key: "mean_return",  label: "Mean",   fmt: (v: unknown) => pct(v as number), color: (v: unknown) => col(v as number) },
    { key: "p5_floor",     label: "P5 Floor", fmt: (v: unknown) => pct(v as number), color: (v: unknown) => col(v as number) },
  ];
  const s3cols = [
    { key: "symbol",          label: "Symbol" },
    { key: "p5_floor",        label: "P5 Floor",  fmt: (v: unknown) => pct(v as number), color: (v: unknown) => col(v as number) },
    { key: "mean_return",     label: "Mean",      fmt: (v: unknown) => pct(v as number), color: (v: unknown) => col(v as number) },
    { key: "downside_capture",label: "DD Capture", fmt: (v: unknown) => pct(v as number), color: () => C.yellow },
    { key: "prob_positive",   label: "Prob+",     fmt: (v: unknown) => `${v}%` },
  ];
  const s4cols = [
    { key: "symbol",              label: "Symbol" },
    { key: "bull_mean",           label: "Bull Mean",  fmt: (v: unknown) => pct(v as number), color: () => C.green },
    { key: "bear_mean",           label: "Bear Mean",  fmt: (v: unknown) => pct(v as number), color: () => C.red },
    { key: "sensitivity",         label: "Sensitivity", fmt: (v: unknown) => num(v as number, 1) },
    { key: "current_regime_mean", label: "Now Mean",   fmt: (v: unknown) => pct(v as number), color: (v: unknown) => col(v as number) },
  ];

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>
            DEEP ANALYSIS ROOM
          </h1>
          <div style={{ color: C.dim, fontSize: 12, marginTop: 4 }}>
            Agent Iota &bull; {rpt.date} &bull; {rpt.timestamp?.split("T")[1]?.slice(0, 8) || ""}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Chip label={rpt.current_regime} color={regimeColor(rpt.current_regime)} />
          {rpt.vix != null && (
            <Chip label={`VIX ${rpt.vix}`} color={rpt.vix > 20 ? C.red : C.green} />
          )}
          <Chip
            label={`Nifty 20d ${pct(rpt.nifty_20d_return)}`}
            color={col(rpt.nifty_20d_return)}
          />
        </div>
      </div>

      {/* Symbol jump bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <input
          value={symInput}
          onChange={e => setSymInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && symInput && goSymbol(symInput)}
          placeholder="Jump to symbol... (Enter)"
          style={{
            background: C.surface, border: `1px solid ${C.border}`, color: C.primary,
            borderRadius: 6, padding: "8px 14px", fontSize: 13, width: 260,
          }}
        />
        <button
          onClick={() => symInput && goSymbol(symInput)}
          style={{
            background: C.cyan, color: "#000", border: "none",
            borderRadius: 6, padding: "8px 16px", fontWeight: 700, cursor: "pointer", fontSize: 13,
          }}
        >Deep Dive</button>
        <button
          onClick={() => router.push("/compare")}
          style={{
            background: "transparent", color: C.yellow,
            border: `1px solid ${C.yellow}`, borderRadius: 6,
            padding: "8px 16px", fontWeight: 700, cursor: "pointer", fontSize: 13,
          }}
        >Compare</button>
        <button
          onClick={load}
          style={{
            background: "transparent", color: C.dim,
            border: `1px solid ${C.border}`, borderRadius: 6,
            padding: "8px 12px", cursor: "pointer", fontSize: 12,
          }}
        >Refresh</button>
      </div>

      {/* Global snapshot bar */}
      {data.global_snapshot && Object.keys(data.global_snapshot).length > 0 && (
        <GlobalBar snap={data.global_snapshot as Record<string, GlobalRow>} />
      )}

      {/* Screen 5: Global Macro (always visible as summary) */}
      {rpt.screen5_global && (
        <Card title="Global Macro Pulse" accent={riskColor(rpt.screen5_global.global_risk)}>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            <div>
              <Chip label={`Risk: ${rpt.screen5_global.global_risk}`} color={riskColor(rpt.screen5_global.global_risk)} />
            </div>
            <StatRow label="SPX 5d" value={pct(rpt.screen5_global.spx_5d)} color={col(rpt.screen5_global.spx_5d)} />
            <StatRow label="DXY 5d" value={pct(rpt.screen5_global.dxy_5d)} color={col(rpt.screen5_global.dxy_5d)} />
            <StatRow label="Gold 5d" value={pct(rpt.screen5_global.gold_5d)} color={col(rpt.screen5_global.gold_5d)} />
            <StatRow label="VIX"     value={String(rpt.screen5_global.vix || "--")} color={C.yellow} />
          </div>
          <div style={{ display: "flex", gap: 24, marginTop: 12, flexWrap: "wrap" }}>
            {rpt.screen5_global.spx_correlated_stocks?.slice(0, 6).map((s) => (
              <span
                key={s.symbol}
                style={{ color: C.cyan, cursor: "pointer", fontSize: 12, fontWeight: 700 }}
                onClick={() => goSymbol(s.symbol)}
              >{s.symbol} ({num(s.correlation)})</span>
            ))}
          </div>
        </Card>
      )}

      {/* Screen tabs */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 16 }}>
        {screens.map((name, i) => (
          <button key={i} onClick={() => setActiveScreen(i)} style={{
            padding: "6px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600,
            cursor: "pointer", border: "1px solid",
            background: activeScreen === i ? C.cyan : "transparent",
            color:      activeScreen === i ? "#000" : C.dim,
            borderColor: activeScreen === i ? C.cyan : C.border,
          }}>{`S${i + 1}: ${name}`}</button>
        ))}
      </div>

      {/* Screen content */}
      {activeScreen === 0 && (
        <Card title="Screen 1 - Best Probability Stocks (20d window)" accent={C.green}>
          <SymbolTable rows={rpt.screen1_best_probability as unknown as Record<string, unknown>[]} cols={s1cols} onSymbol={goSymbol} />
        </Card>
      )}
      {activeScreen === 1 && (
        <Card title="Screen 2 - Risk-Adjusted Gems (Sharpe-ranked)" accent={C.cyan}>
          <SymbolTable rows={rpt.screen2_risk_adjusted as unknown as Record<string, unknown>[]} cols={s2cols} onSymbol={goSymbol} />
        </Card>
      )}
      {activeScreen === 2 && (
        <Card title="Screen 3 - Worst-Case Protected (P5 floor > -5%)" accent={C.yellow}>
          <SymbolTable rows={rpt.screen3_worst_case as unknown as Record<string, unknown>[]} cols={s3cols} onSymbol={goSymbol} />
        </Card>
      )}
      {activeScreen === 3 && (
        <Card title="Screen 4 - Regime Sensitivity Movers" accent={C.orange}>
          <SymbolTable rows={rpt.screen4_regime_movers as unknown as Record<string, unknown>[]} cols={s4cols} onSymbol={goSymbol} />
        </Card>
      )}
      {activeScreen === 4 && (
        <Card title="Screen 5 - Global Macro Pulse" accent={C.yellow}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
            <div>
              <div style={{ color: C.dim, fontSize: 11, fontWeight: 700, marginBottom: 8 }}>SPX CORRELATED</div>
              {rpt.screen5_global?.spx_correlated_stocks?.slice(0, 10).map(s => (
                <div key={s.symbol} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12 }}>
                  <span style={{ color: C.cyan, cursor: "pointer" }} onClick={() => goSymbol(s.symbol)}>{s.symbol}</span>
                  <span style={{ color: C.dim }}>{num(s.correlation)}</span>
                </div>
              ))}
            </div>
            <div>
              <div style={{ color: C.dim, fontSize: 11, fontWeight: 700, marginBottom: 8 }}>GOLD CORRELATED</div>
              {rpt.screen5_global?.gold_correlated_stocks?.slice(0, 10).map(s => (
                <div key={s.symbol} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12 }}>
                  <span style={{ color: C.yellow, cursor: "pointer" }} onClick={() => goSymbol(s.symbol)}>{s.symbol}</span>
                  <span style={{ color: C.dim }}>{num(s.correlation)}</span>
                </div>
              ))}
            </div>
            <div>
              <div style={{ color: C.dim, fontSize: 11, fontWeight: 700, marginBottom: 8 }}>DXY SENSITIVE</div>
              {rpt.screen5_global?.dxy_sensitive_stocks?.slice(0, 10).map(s => (
                <div key={s.symbol} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12 }}>
                  <span style={{ color: C.orange, cursor: "pointer" }} onClick={() => goSymbol(s.symbol)}>{s.symbol}</span>
                  <span style={{ color: C.dim }}>{num(s.correlation)}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}
      {activeScreen === 5 && (
        <Card title="Screen 6 - Index Deep Stats" accent={C.cyan}>
          {(rpt.screen6_index_stats || []).map((idx) => (
            <div key={idx.index_name} style={{ marginBottom: 20 }}>
              <div style={{
                color: C.cyan, fontWeight: 700, fontSize: 13, marginBottom: 6,
                cursor: "pointer",
              }}
                onClick={() => goSymbol(idx.index_name.replace(/ /g, "_"))}
              >{idx.index_name}</div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                  <thead>
                    <tr style={{ color: C.dim }}>
                      {["Win", "Mean%", "P5%", "P95%", "Prob+", "Sharpe"].map(h => (
                        <th key={h} style={{ padding: "3px 8px", textAlign: "right", fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(idx.window_stats || []).map((w) => (
                      <tr key={w.window_days} style={{ borderBottom: `1px solid ${C.border}22` }}>
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
            </div>
          ))}
        </Card>
      )}

      {/* LLM Analysis */}
      {rpt.llm_analysis && (
        <Card title="Iota Intelligence Synthesis" accent={C.cyan}>
          <MarkdownText text={rpt.llm_analysis} />
        </Card>
      )}
    </div>
  );
}
""")


# =============================================================================
# [6/10] /deep/[symbol]/page.tsx  -- Kappa per-symbol deep profile
# =============================================================================
print("\n[6/10] /deep/[symbol]/page.tsx")

write(APP / "deep" / "[symbol]" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import MarkdownText from "@/components/MarkdownText";

// ── Types ──────────────────────────────────────────────────────────────────

interface WindowRow {
  window_days: number; n_windows: number; mean_return: number;
  std_return: number; p5: number; p25: number; p75: number; p95: number;
  prob_positive: number; prob_gt10: number; prob_lt_neg10: number;
  sharpe_ratio: number; ann_return_equiv: number;
}
interface SeasonRow {
  period_value: number; n_obs: number; mean_return_pct: number; median_return_pct: number;
}
interface CorrRow {
  symbol_b: string; correlation_20d: number; correlation_60d: number; beta_20d: number;
}
interface RegimeRow {
  regime: string; n_windows: number; mean_return: number;
  std_return: number; prob_positive: number; p5: number; p95: number;
}
interface Technicals {
  atr_14_pct: number; adx_14: number; pct_above_sma20: number;
  vol_surge_20d: number; rsi_14: number; macd_line: number;
  macd_signal: number; bb_pct: number; as_of_date: string;
}
interface SeriesStats {
  cagr_pct: number; ann_volatility_pct: number; max_drawdown_pct: number;
  sharpe_ratio: number; sortino_ratio: number; calmar_ratio: number;
  n_trading_days: number; mdd_start_date: string; mdd_trough_date: string;
  mdd_recovery_days: number;
}
interface InsiderRow {
  filing_date: string; name: string; category: string;
  transaction_type: string; quantity: number; price: number; value: number;
}
interface AnnRow { announcement_date: string; subject: string; }
interface KappaData {
  ok: boolean; error?: string;
  symbol: string;
  has_cached_report: boolean;
  report: {
    asset_type: string; llm_verdict: string; llm_source: string;
    timestamp: string;
    window_table: WindowRow[];
  } | null;
  technicals: Technicals | null;
  window_stats: WindowRow[];
  seasonality: SeasonRow[];
  correlations: CorrRow[];
  regime_stats: RegimeRow[];
  series_stats: SeriesStats | null;
  latest_price: { close: number; date: string; volume: number } | null;
  insider_trades: InsiderRow[];
  announcements: AnnRow[];
}

// ── Colour helpers ──────────────────────────────────────────────────────────

const C = {
  green:   "var(--accent-green)",
  red:     "var(--accent-red)",
  cyan:    "var(--accent-cyan)",
  yellow:  "var(--accent-yellow)",
  orange:  "var(--accent-orange, #f97316)",
  dim:     "var(--text-tertiary)",
  primary: "var(--text-primary)",
  border:  "var(--border-color)",
  surface: "var(--surface-card)",
};

function pct(v: number | null | undefined, dec = 2): string {
  if (v == null) return "--";
  return `${v >= 0 ? "+" : ""}${Number(v).toFixed(dec)}%`;
}
function num(v: number | null | undefined, dec = 2): string {
  if (v == null) return "--";
  return Number(v).toFixed(dec);
}
function col(v: number | null | undefined) {
  if (v == null) return "var(--text-tertiary)";
  return v >= 0 ? C.green : C.red;
}

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ── Sub-components ──────────────────────────────────────────────────────────

function Card({ title, children, accent }: {
  title: string; children: React.ReactNode; accent?: string;
}) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${accent || C.border}`,
      borderRadius: 8, padding: "16px 20px", marginBottom: 18,
    }}>
      <div style={{
        fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: accent || C.cyan,
        textTransform: "uppercase", marginBottom: 12,
        borderBottom: `1px solid ${C.border}`, paddingBottom: 8,
      }}>{title}</div>
      {children}
    </div>
  );
}

function StatGrid({ items }: { items: { label: string; value: string; color?: string }[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 12 }}>
      {items.map(({ label, value, color }) => (
        <div key={label} style={{
          background: `${C.border}22`, borderRadius: 6, padding: "10px 12px",
        }}>
          <div style={{ fontSize: 10, color: C.dim, fontWeight: 700, marginBottom: 4 }}>{label}</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: color || C.primary }}>{value}</div>
        </div>
      ))}
    </div>
  );
}

function WindowTable({ rows }: { rows: WindowRow[] }) {
  const DISPLAY = [5, 10, 20, 60, 120];
  const filtered = rows.filter(r => DISPLAY.includes(r.window_days));
  if (!filtered.length) return <div style={{ color: C.dim, fontSize: 12 }}>No window data</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {["Win", "N", "Mean%", "Std%", "P5%", "P95%", "Prob+", ">10%", "<-10%", "Sharpe", "Ann%"].map(h => (
              <th key={h} style={{
                padding: "4px 8px", textAlign: "right", color: C.dim,
                fontWeight: 600, borderBottom: `1px solid ${C.border}`,
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.map(r => (
            <tr key={r.window_days} style={{ borderBottom: `1px solid ${C.border}22` }}>
              <td style={{ padding: "5px 8px", color: C.cyan, fontWeight: 700, textAlign: "right" }}>{r.window_days}d</td>
              <td style={{ padding: "5px 8px", color: C.dim, textAlign: "right" }}>{r.n_windows}</td>
              <td style={{ padding: "5px 8px", color: col(r.mean_return), textAlign: "right" }}>{pct(r.mean_return)}</td>
              <td style={{ padding: "5px 8px", color: C.dim, textAlign: "right" }}>{pct(r.std_return)}</td>
              <td style={{ padding: "5px 8px", color: col(r.p5), textAlign: "right" }}>{pct(r.p5)}</td>
              <td style={{ padding: "5px 8px", color: col(r.p95), textAlign: "right" }}>{pct(r.p95)}</td>
              <td style={{ padding: "5px 8px", color: C.green, textAlign: "right" }}>{r.prob_positive}%</td>
              <td style={{ padding: "5px 8px", color: C.cyan, textAlign: "right" }}>{r.prob_gt10}%</td>
              <td style={{ padding: "5px 8px", color: C.red, textAlign: "right" }}>{r.prob_lt_neg10}%</td>
              <td style={{ padding: "5px 8px", color: C.cyan, textAlign: "right" }}>{num(r.sharpe_ratio)}</td>
              <td style={{ padding: "5px 8px", color: col(r.ann_return_equiv), textAlign: "right" }}>{pct(r.ann_return_equiv, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SeasonChart({ rows }: { rows: SeasonRow[] }) {
  if (!rows.length) return <div style={{ color: C.dim, fontSize: 12 }}>No seasonality data</div>;
  const maxAbs = Math.max(...rows.map(r => Math.abs(r.mean_return_pct || 0)), 1);
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "flex-end", height: 100 }}>
      {rows.map(r => {
        const h = Math.abs((r.mean_return_pct || 0) / maxAbs) * 70;
        const positive = (r.mean_return_pct || 0) >= 0;
        return (
          <div key={r.period_value} style={{ flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 9, color: col(r.mean_return_pct), fontWeight: 700, marginBottom: 2 }}>
              {pct(r.mean_return_pct, 1)}
            </div>
            <div style={{
              height: h, background: positive ? C.green : C.red,
              opacity: 0.7, borderRadius: "2px 2px 0 0",
              minHeight: 2,
            }} />
            <div style={{ fontSize: 9, color: C.dim, marginTop: 2 }}>
              {MONTHS[(r.period_value - 1) % 12]}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RegimeBreakdown({ rows }: { rows: RegimeRow[] }) {
  if (!rows.length) return <div style={{ color: C.dim, fontSize: 12 }}>No regime data</div>;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
      {rows.map(r => (
        <div key={r.regime} style={{
          background: `${C.border}22`, borderRadius: 6, padding: "10px 12px",
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: C.dim, marginBottom: 6 }}>{r.regime}</div>
          <div style={{ fontSize: 12, color: col(r.mean_return) }}>Mean: {pct(r.mean_return)}</div>
          <div style={{ fontSize: 12, color: C.green }}>Prob+: {r.prob_positive ? `${(r.prob_positive * 100).toFixed(0)}%` : "--"}</div>
          <div style={{ fontSize: 12, color: C.dim }}>N: {r.n_windows}</div>
          <div style={{ fontSize: 11, color: C.dim }}>P5: {pct(r.p5)} | P95: {pct(r.p95)}</div>
        </div>
      ))}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function DeepSymbolPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const router = useRouter();
  const [data, setData] = useState<KappaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!symbol) return;
    setLoading(true); setError(null);
    try {
      const r = await fetch(`/api/deep/${symbol}`, { cache: "no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "API error");
      setData(d);
    } catch (e: unknown) {
      setError(String(e));
    } finally { setLoading(false); }
  }, [symbol]);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div style={{ padding: 40, color: "var(--text-tertiary)", textAlign: "center" }}>
      Loading {symbol}...
    </div>
  );
  if (error) return <div style={{ padding: 40, color: C.red }}>Error: {error}</div>;
  if (!data)  return <div style={{ padding: 40, color: C.yellow }}>No data for {symbol}</div>;

  const { series_stats: ss, technicals: tech, latest_price: lp } = data;
  const kv = data.report;

  const seriesItems = ss ? [
    { label: "CAGR",      value: pct(ss.cagr_pct, 1),         color: col(ss.cagr_pct) },
    { label: "Ann Vol",   value: pct(ss.ann_volatility_pct, 1) },
    { label: "Max DD",    value: pct(ss.max_drawdown_pct, 1),  color: C.red },
    { label: "Sharpe",    value: num(ss.sharpe_ratio),         color: C.cyan },
    { label: "Sortino",   value: num(ss.sortino_ratio),        color: C.cyan },
    { label: "Calmar",    value: num(ss.calmar_ratio),         color: C.cyan },
    { label: "N Days",    value: String(ss.n_trading_days) },
    { label: "DD Days",   value: ss.mdd_recovery_days != null ? String(ss.mdd_recovery_days) : "--" },
  ] : [];

  const techItems = tech ? [
    { label: "RSI 14",      value: num(tech.rsi_14, 1),       color: tech.rsi_14 > 70 ? C.red : tech.rsi_14 < 30 ? C.green : C.primary },
    { label: "ATR 14%",     value: pct(tech.atr_14_pct, 2) },
    { label: "ADX 14",      value: num(tech.adx_14, 1),       color: tech.adx_14 > 25 ? C.green : C.dim },
    { label: "Vs SMA20",    value: pct(tech.pct_above_sma20, 2), color: col(tech.pct_above_sma20) },
    { label: "Vol Surge",   value: num(tech.vol_surge_20d, 1) + "x" },
    { label: "MACD",        value: tech.macd_line > tech.macd_signal ? "BULL" : "BEAR",
      color: tech.macd_line > tech.macd_signal ? C.green : C.red },
    { label: "BB%",         value: num(tech.bb_pct, 2) },
    { label: "As Of",       value: tech.as_of_date?.slice(0, 10) || "--" },
  ] : [];

  return (
    <div style={{ maxWidth: 1050, margin: "0 auto", padding: "24px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button onClick={() => router.push("/deep")} style={{
              background: "transparent", border: `1px solid ${C.border}`,
              color: C.dim, borderRadius: 4, padding: "4px 10px",
              cursor: "pointer", fontSize: 11,
            }}>Back to Room</button>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 900, letterSpacing: -0.5, color: C.cyan }}>
              {data.symbol}
            </h1>
            {kv?.asset_type && (
              <span style={{
                fontSize: 11, fontWeight: 700, color: C.dim,
                border: `1px solid ${C.border}`, borderRadius: 4, padding: "2px 8px",
              }}>{kv.asset_type.toUpperCase()}</span>
            )}
          </div>
          {lp && (
            <div style={{ color: C.dim, fontSize: 12, marginTop: 6 }}>
              Last: <span style={{ color: C.primary, fontWeight: 700 }}>
                {lp.close?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </span>
              {" "}&bull; {lp.date}
              {" "}&bull; Vol: {lp.volume?.toLocaleString("en-IN")}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {!data.has_cached_report && (
            <span style={{
              fontSize: 11, color: C.yellow, border: `1px solid ${C.yellow}44`,
              borderRadius: 4, padding: "3px 8px",
            }}>Live DB only - run: py agent_kappa.py {data.symbol}</span>
          )}
          <button onClick={() => router.push(`/compare?s=${data.symbol}`)} style={{
            background: "transparent", color: C.yellow, border: `1px solid ${C.yellow}`,
            borderRadius: 6, padding: "6px 12px", fontWeight: 700, cursor: "pointer", fontSize: 12,
          }}>Compare</button>
          <button onClick={load} style={{
            background: "transparent", color: C.dim, border: `1px solid ${C.border}`,
            borderRadius: 6, padding: "6px 10px", cursor: "pointer", fontSize: 11,
          }}>Refresh</button>
        </div>
      </div>

      {/* Series stats */}
      {seriesItems.length > 0 && (
        <Card title="Full-History Series Stats" accent={C.cyan}>
          <StatGrid items={seriesItems} />
          {ss?.mdd_start_date && (
            <div style={{ marginTop: 12, fontSize: 12, color: C.dim }}>
              Max Drawdown: {ss.mdd_start_date} to {ss.mdd_trough_date}
              {ss.mdd_recovery_days != null ? ` (${ss.mdd_recovery_days}d to recover)` : ""}
            </div>
          )}
        </Card>
      )}

      {/* Technicals */}
      {techItems.length > 0 && (
        <Card title="Current Technicals" accent={C.yellow}>
          <StatGrid items={techItems} />
        </Card>
      )}

      {/* Window stats */}
      <Card title="Rolling Window Behavior" accent={C.green}>
        <WindowTable rows={data.window_stats} />
      </Card>

      {/* Regime breakdown */}
      <Card title="Regime Breakdown (20d Window)" accent={C.orange}>
        <RegimeBreakdown rows={data.regime_stats} />
      </Card>

      {/* Seasonality */}
      <Card title="Monthly Seasonality" accent={C.cyan}>
        <SeasonChart rows={data.seasonality} />
      </Card>

      {/* Correlations */}
      {data.correlations.length > 0 && (
        <Card title="Top Correlations" accent={C.dim}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
            {data.correlations.slice(0, 12).map(c => (
              <div key={c.symbol_b} style={{
                background: `${C.border}22`, borderRadius: 6, padding: "8px 12px",
                cursor: "pointer",
              }} onClick={() => router.push(`/deep/${c.symbol_b}`)}>
                <div style={{ color: C.cyan, fontWeight: 700, fontSize: 13 }}>{c.symbol_b}</div>
                <div style={{ fontSize: 11, color: C.dim }}>
                  20d: <span style={{ color: col(c.correlation_20d) }}>{num(c.correlation_20d)}</span>
                  {" "}&bull; beta: {num(c.beta_20d, 2)}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Insider trades */}
      {data.insider_trades.length > 0 && (
        <Card title="Insider Trades (Recent)" accent={C.yellow}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {["Date","Name","Category","Type","Qty","Price","Value Cr"].map(h => (
                    <th key={h} style={{ padding: "4px 8px", color: C.dim, textAlign: "right",
                      fontWeight: 600, borderBottom: `1px solid ${C.border}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.insider_trades.map((t, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
                    <td style={{ padding: "4px 8px", color: C.dim, textAlign: "right" }}>{t.filing_date}</td>
                    <td style={{ padding: "4px 8px", color: C.primary, textAlign: "right" }}>{t.name}</td>
                    <td style={{ padding: "4px 8px", color: C.dim, textAlign: "right" }}>{t.category}</td>
                    <td style={{ padding: "4px 8px", fontWeight: 700, textAlign: "right",
                      color: t.transaction_type === "BUY" ? C.green : C.red }}>{t.transaction_type}</td>
                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.quantity?.toLocaleString("en-IN")}</td>
                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{num(t.price, 1)}</td>
                    <td style={{ padding: "4px 8px", textAlign: "right", color: C.cyan }}>
                      {t.value ? (t.value / 1e7).toFixed(2) : "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Announcements */}
      {data.announcements.length > 0 && (
        <Card title="Corporate Announcements (Recent)" accent={C.dim}>
          {data.announcements.map((a, i) => (
            <div key={i} style={{
              display: "flex", gap: 12, padding: "5px 0",
              borderBottom: `1px solid ${C.border}22`, fontSize: 12,
            }}>
              <span style={{ color: C.dim, minWidth: 90 }}>{a.announcement_date}</span>
              <span style={{ color: C.primary }}>{a.subject}</span>
            </div>
          ))}
        </Card>
      )}

      {/* Kappa LLM verdict */}
      {kv?.llm_verdict && (
        <Card title={`Kappa AI Verdict (${kv.llm_source || "LLM"})`} accent={C.cyan}>
          <MarkdownText text={kv.llm_verdict} />
        </Card>
      )}
    </div>
  );
}
""")


# =============================================================================
# [7/10] /compare/page.tsx  -- Lambda multi-symbol comparison
# =============================================================================
print("\n[7/10] /compare/page.tsx")

write(APP / "compare" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

// ── Types ──────────────────────────────────────────────────────────────────

interface SeriesRow {
  symbol: string; cagr_pct: number; ann_volatility_pct: number;
  max_drawdown_pct: number; sharpe_ratio: number; sortino_ratio: number;
  calmar_ratio: number; n_trading_days: number;
}
interface WindowRow {
  symbol: string; window_days: number; mean_return: number; std_return: number;
  p5: number; p95: number; prob_positive: number; prob_gt10: number; sharpe_ratio: number;
}
interface TechRow {
  symbol: string; rsi_14: number; adx_14: number; pct_above_sma20: number;
  vol_surge_20d: number; macd_line: number; macd_signal: number;
  bb_pct: number; atr_14_pct: number; as_of_date: string;
}
interface PriceRow {
  symbol: string; close: number; date: string; volume: number;
}
interface SignalRow {
  symbol: string; days_seen: number; last_seen: string; avg_score: number;
}
interface CompareData {
  ok: boolean; error?: string;
  symbols: string[];
  series_stats: SeriesRow[];
  window_stats: WindowRow[];
  technicals: TechRow[];
  prices: PriceRow[];
  recent_signals: SignalRow[];
  cross_correlations: { symbol_a: string; symbol_b: string; correlation_20d: number; beta_20d: number }[];
}

// ── Constants ──────────────────────────────────────────────────────────────

const COLORS = [
  "var(--accent-cyan)",
  "var(--accent-green)",
  "var(--accent-yellow)",
  "#f97316",
  "#a855f7",
];
const C = {
  dim:     "var(--text-tertiary)",
  primary: "var(--text-primary)",
  border:  "var(--border-color)",
  surface: "var(--surface-card)",
  green:   "var(--accent-green)",
  red:     "var(--accent-red)",
  cyan:    "var(--accent-cyan)",
};

function pct(v: number | null | undefined, dec = 1): string {
  if (v == null) return "--";
  return `${v >= 0 ? "+" : ""}${Number(v).toFixed(dec)}%`;
}
function num(v: number | null | undefined, dec = 2): string {
  if (v == null) return "--";
  return Number(v).toFixed(dec);
}
function col(v: number | null | undefined) {
  return (v ?? 0) >= 0 ? C.green : C.red;
}
function best(vals: (number | null | undefined)[], higherBetter = true) {
  const nums = vals.map(v => v ?? (higherBetter ? -Infinity : Infinity));
  const target = higherBetter ? Math.max(...nums) : Math.min(...nums);
  return nums.map(n => n === target);
}

// ── Sub-components ──────────────────────────────────────────────────────────

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "16px 20px", marginBottom: 18 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: C.cyan, textTransform: "uppercase", marginBottom: 12, borderBottom: `1px solid ${C.border}`, paddingBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

function CompareTable({ title, syms, rows }: {
  title: string;
  syms: string[];
  rows: { metric: string; values: (string | number | null | undefined)[]; higherBetter?: boolean; colorFn?: (v: unknown) => string }[];
}) {
  return (
    <Card title={title}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ padding: "4px 10px", textAlign: "left", color: C.dim, fontWeight: 600, borderBottom: `1px solid ${C.border}` }}>Metric</th>
              {syms.map((s, i) => (
                <th key={s} style={{ padding: "4px 10px", textAlign: "right", color: COLORS[i], fontWeight: 700, borderBottom: `1px solid ${C.border}` }}>{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isBest = row.higherBetter !== undefined ? best(row.values as number[], row.higherBetter) : null;
              return (
                <tr key={row.metric} style={{ borderBottom: `1px solid ${C.border}22` }}>
                  <td style={{ padding: "5px 10px", color: C.dim }}>{row.metric}</td>
                  {row.values.map((v, i) => {
                    const txt = typeof v === "number" ? (row.metric.includes("%") || row.metric.includes("CAGR") || row.metric.includes("Return") || row.metric.includes("Vol") || row.metric.includes("DD") || row.metric.includes("Prob") ? pct(v) : num(v)) : String(v ?? "--");
                    const clr = row.colorFn ? row.colorFn(v) : (isBest?.[i] ? COLORS[i] : C.primary);
                    return (
                      <td key={i} style={{
                        padding: "5px 10px", textAlign: "right", color: clr, fontWeight: isBest?.[i] ? 800 : 400,
                        background: isBest?.[i] ? `${COLORS[i]}11` : "transparent",
                      }}>{txt}</td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function ComparePage() {
  const router     = useRouter();
  const searchParams = useSearchParams();
  const [input, setInput]   = useState(searchParams.get("s") || "");
  const [syms, setSyms]     = useState<string[]>([]);
  const [data, setData]     = useState<CompareData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState<string | null>(null);

  const doCompare = useCallback(async (symbols: string[]) => {
    if (symbols.length < 2) return;
    setLoading(true); setError(null);
    try {
      const r = await fetch(`/api/compare?symbols=${symbols.join(",")}`, { cache: "no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "API error");
      setData(d); setSyms(d.symbols);
    } catch (e: unknown) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const s = searchParams.get("s") || searchParams.get("symbols") || "";
    if (s) {
      const arr = s.split(",").map(x => x.trim().toUpperCase()).filter(Boolean);
      if (arr.length >= 2) { setInput(arr.join(", ")); doCompare(arr); }
    }
  }, [searchParams, doCompare]);

  const handleSubmit = () => {
    const arr = input.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean).slice(0, 5);
    if (arr.length < 2) { setError("Enter 2-5 symbols separated by commas"); return; }
    router.replace(`/compare?symbols=${arr.join(",")}`);
    doCompare(arr);
  };

  // Data assembly
  const symList = data?.symbols || syms;
  const ss = data?.series_stats || [];
  const ws = data?.window_stats || [];
  const tech = data?.technicals || [];
  const prices = data?.prices || [];
  const sigs = data?.recent_signals || [];

  const getS = (sym: string) => ss.find(r => r.symbol === sym);
  const getW = (sym: string, days: number) => ws.find(r => r.symbol === sym && r.window_days === days);
  const getT = (sym: string) => tech.find(r => r.symbol === sym);
  const getP = (sym: string) => prices.find(r => r.symbol === sym);
  const getSig = (sym: string) => sigs.find(r => r.symbol === sym);

  const seriesRows = [
    { metric: "CAGR%", values: symList.map(s => getS(s)?.cagr_pct), higherBetter: true, colorFn: col },
    { metric: "Ann Volatility%", values: symList.map(s => getS(s)?.ann_volatility_pct), higherBetter: false },
    { metric: "Max Drawdown%", values: symList.map(s => getS(s)?.max_drawdown_pct), higherBetter: false },
    { metric: "Sharpe", values: symList.map(s => getS(s)?.sharpe_ratio), higherBetter: true },
    { metric: "Sortino", values: symList.map(s => getS(s)?.sortino_ratio), higherBetter: true },
    { metric: "Calmar", values: symList.map(s => getS(s)?.calmar_ratio), higherBetter: true },
    { metric: "N Days", values: symList.map(s => getS(s)?.n_trading_days), higherBetter: true },
  ];

  const win20Rows = [
    { metric: "20d Mean Return%",     values: symList.map(s => getW(s, 20)?.mean_return), higherBetter: true, colorFn: col },
    { metric: "20d Prob Positive",    values: symList.map(s => getW(s, 20)?.prob_positive), higherBetter: true },
    { metric: "20d P5 (worst-case%)", values: symList.map(s => getW(s, 20)?.p5), higherBetter: true },
    { metric: "20d P95 (best-case%)", values: symList.map(s => getW(s, 20)?.p95), higherBetter: true },
    { metric: "20d Sharpe",           values: symList.map(s => getW(s, 20)?.sharpe_ratio), higherBetter: true },
    { metric: "10d Mean Return%",     values: symList.map(s => getW(s, 10)?.mean_return), higherBetter: true, colorFn: col },
    { metric: "10d Prob Positive",    values: symList.map(s => getW(s, 10)?.prob_positive), higherBetter: true },
    { metric: "5d Mean Return%",      values: symList.map(s => getW(s, 5)?.mean_return), higherBetter: true, colorFn: col },
    { metric: "60d Mean Return%",     values: symList.map(s => getW(s, 60)?.mean_return), higherBetter: true, colorFn: col },
  ];

  const techRows = [
    { metric: "RSI 14",         values: symList.map(s => getT(s)?.rsi_14) },
    { metric: "ADX 14",         values: symList.map(s => getT(s)?.adx_14), higherBetter: true },
    { metric: "Vs SMA20%",      values: symList.map(s => getT(s)?.pct_above_sma20), higherBetter: true, colorFn: col },
    { metric: "Vol Surge 20d",  values: symList.map(s => getT(s)?.vol_surge_20d) },
    { metric: "ATR 14%",        values: symList.map(s => getT(s)?.atr_14_pct) },
    { metric: "BB%",            values: symList.map(s => getT(s)?.bb_pct) },
    { metric: "MACD Signal",    values: symList.map(s => {
      const t = getT(s);
      return t ? (t.macd_line > t.macd_signal ? "BULL" : "BEAR") : null;
    }) },
  ];

  const signalRows = [
    { metric: "Screen Days (30d)", values: symList.map(s => getSig(s)?.days_seen) },
    { metric: "Avg Signal Score",  values: symList.map(s => getSig(s)?.avg_score), higherBetter: true },
    { metric: "Last Seen",         values: symList.map(s => getSig(s)?.last_seen) },
    { metric: "Latest Price",      values: symList.map(s => getP(s)?.close?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) || "--") },
    { metric: "Price Date",        values: symList.map(s => getP(s)?.date || "--") },
  ];

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>COMPARE</h1>
        <button onClick={() => router.push("/deep")} style={{
          background: "transparent", border: `1px solid ${C.border}`,
          color: C.dim, borderRadius: 6, padding: "6px 12px", cursor: "pointer", fontSize: 12,
        }}>Back to Deep Room</button>
      </div>

      {/* Input row */}
      <Card title="Symbol Selection (2-5 symbols)">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === "Enter" && handleSubmit()}
            placeholder="RELIANCE, HDFCBANK, INFY, TCS"
            style={{
              background: "transparent", border: `1px solid ${C.border}`, color: C.primary,
              borderRadius: 6, padding: "9px 14px", fontSize: 13, flex: 1, minWidth: 300,
            }}
          />
          <button onClick={handleSubmit} style={{
            background: C.cyan, color: "#000", border: "none",
            borderRadius: 6, padding: "9px 20px", fontWeight: 700, cursor: "pointer", fontSize: 13,
          }}>Compare</button>
        </div>
        {/* Quick preset groups */}
        <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            ["Banks",      "HDFCBANK, ICICIBANK, SBIN, AXISBANK, KOTAKBANK"],
            ["IT Giants",  "TCS, INFY, WIPRO, HCLTECH, TECHM"],
            ["Nifty Top5", "RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK"],
            ["FMCG",       "HINDUNILVR, ITC, NESTLEIND, BRITANNIA, DABUR"],
          ].map(([label, val]) => (
            <button key={label} onClick={() => { setInput(val); doCompare(val.split(", ")); }} style={{
              background: "transparent", border: `1px solid ${C.border}`,
              color: C.dim, borderRadius: 4, padding: "4px 10px",
              cursor: "pointer", fontSize: 11, fontWeight: 600,
            }}>{label}</button>
          ))}
        </div>
      </Card>

      {error && <div style={{ color: C.red, padding: "8px 0", fontSize: 13 }}>{error}</div>}
      {loading && <div style={{ color: C.dim, padding: "20px 0", textAlign: "center" }}>Comparing {input}...</div>}

      {/* Results */}
      {data && !loading && (
        <>
          {/* Symbol color legend */}
          <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
            {symList.map((s, i) => (
              <div key={s} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 12, height: 12, borderRadius: 2, background: COLORS[i] }} />
                <span
                  style={{ color: COLORS[i], fontWeight: 700, fontSize: 14, cursor: "pointer" }}
                  onClick={() => router.push(`/deep/${s}`)}
                >{s}</span>
              </div>
            ))}
          </div>

          <CompareTable title="Series Statistics (Full History)" syms={symList} rows={seriesRows} />
          <CompareTable title="Rolling Window Behavior" syms={symList} rows={win20Rows} />
          <CompareTable title="Current Technicals" syms={symList} rows={techRows} />
          <CompareTable title="Screener Signal History" syms={symList} rows={signalRows} />

          {/* Cross correlations */}
          {data.cross_correlations.length > 0 && (
            <Card title="Cross Correlations (20d)">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {data.cross_correlations.map(c => (
                  <div key={`${c.symbol_a}-${c.symbol_b}`} style={{
                    background: `${C.border}22`, borderRadius: 6, padding: "8px 12px",
                    fontSize: 12,
                  }}>
                    <span style={{ color: C.cyan, fontWeight: 700 }}>{c.symbol_a}</span>
                    <span style={{ color: C.dim }}> x </span>
                    <span style={{ color: C.cyan, fontWeight: 700 }}>{c.symbol_b}</span>
                    <span style={{ color: C.dim }}> = </span>
                    <span style={{ color: col(c.correlation_20d), fontWeight: 700 }}>{num(c.correlation_20d)}</span>
                    <span style={{ color: C.dim }}> (beta {num(c.beta_20d, 2)})</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
""")


# =============================================================================
# [8/10] /eta/page.tsx  -- Eta corporate events dashboard (pending Phase 8)
# =============================================================================
print("\n[8/10] /eta/page.tsx")

write(APP / "eta" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import MarkdownText from "@/components/MarkdownText";
import { useRouter } from "next/navigation";

// ── Types ──────────────────────────────────────────────────────────────────

interface ResultsRow  { symbol: string; announcement_date: string; subject: string; }
interface DivRow      { symbol: string; announcement_date: string; subject: string; }
interface ClusterRow  { symbol: string; n_buys: number; total_value_cr: number; names: string; }
interface BigTradeRow { symbol: string; filing_date: string; name: string; transaction_type: string; quantity: number; price: number; value: number; }
interface ReactionRow { symbol: string; announcement_date: string; price_before: number; price_after: number; reaction_pct: number; }
interface UpcomingRow { symbol: string; last_results_date: string; expected_due: string; }
interface EtaReport {
  agent: string; date: string; timestamp: string;
  screen1_results_season: ResultsRow[];
  screen2_dividends: DivRow[];
  screen3_insider_clusters: ClusterRow[];
  screen4_big_trades: BigTradeRow[];
  screen5_post_results_reaction: ReactionRow[];
  screen6_upcoming_results: UpcomingRow[];
  llm_analysis: string;
}
interface EtaData { ok: boolean; error?: string; report: EtaReport; }

// ── Helpers ─────────────────────────────────────────────────────────────────

const C = {
  green:   "var(--accent-green)",
  red:     "var(--accent-red)",
  cyan:    "var(--accent-cyan)",
  yellow:  "var(--accent-yellow)",
  dim:     "var(--text-tertiary)",
  primary: "var(--text-primary)",
  border:  "var(--border-color)",
  surface: "var(--surface-card)",
};

function col(v: number | null | undefined) { return (v ?? 0) >= 0 ? C.green : C.red; }
function pct(v: number | null | undefined) {
  if (v == null) return "--";
  return `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`;
}
function num(v: number | null | undefined, d = 2) {
  if (v == null) return "--";
  return Number(v).toFixed(d);
}

// ── Sub-components ──────────────────────────────────────────────────────────

function Card({ title, count, children, accent }: {
  title: string; count?: number; children: React.ReactNode; accent?: string;
}) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${accent || C.border}`, borderRadius: 8, padding: "16px 20px", marginBottom: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12, borderBottom: `1px solid ${C.border}`, paddingBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: accent || C.cyan, textTransform: "uppercase" }}>{title}</span>
        {count !== undefined && <span style={{ fontSize: 11, color: C.dim }}>{count} items</span>}
      </div>
      {children}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function EtaPage() {
  const router = useRouter();
  const [data, setData] = useState<EtaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch("/api/eta", { cache: "no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "API error");
      setData(d);
    } catch (e: unknown) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ padding: 40, color: C.dim, textAlign: "center" }}>Loading Eta...</div>;
  if (error) return <div style={{ padding: 40, color: C.red }}>{error}<br /><code style={{ fontSize: 12 }}>Run: py D:\MICC\agent_eta.py</code></div>;
  if (!data?.report) return <div style={{ padding: 40, color: C.yellow }}>No Eta report. Run: py D:\MICC\agent_eta.py</div>;

  const rpt = data.report;

  return (
    <div style={{ maxWidth: 1050, margin: "0 auto", padding: "24px 16px" }}>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>CORPORATE EVENTS</h1>
          <div style={{ color: C.dim, fontSize: 12, marginTop: 4 }}>Agent Eta &bull; {rpt.date} &bull; {rpt.timestamp?.split("T")[1]?.slice(0, 8) || ""}</div>
        </div>
        <button onClick={load} style={{ background: "transparent", border: `1px solid ${C.border}`, color: C.dim, borderRadius: 6, padding: "6px 12px", cursor: "pointer", fontSize: 12 }}>Refresh</button>
      </div>

      {/* Screen 1: Results season */}
      <Card title="Screen 1 - Results Season" count={rpt.screen1_results_season?.length} accent={C.cyan}>
        {(rpt.screen1_results_season || []).slice(0, 20).map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 12, padding: "5px 0", borderBottom: `1px solid ${C.border}22`, fontSize: 12 }}>
            <span style={{ color: C.cyan, fontWeight: 700, minWidth: 100, cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
            <span style={{ color: C.dim, minWidth: 90 }}>{r.announcement_date}</span>
            <span style={{ color: C.primary }}>{r.subject}</span>
          </div>
        ))}
        {(!rpt.screen1_results_season?.length) && <div style={{ color: C.dim, fontSize: 12 }}>No results found in lookback period</div>}
      </Card>

      {/* Screen 2: Dividends/Bonus/Split */}
      <Card title="Screen 2 - Dividends / Bonus / Splits" count={rpt.screen2_dividends?.length} accent={C.green}>
        {(rpt.screen2_dividends || []).slice(0, 20).map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 12, padding: "5px 0", borderBottom: `1px solid ${C.border}22`, fontSize: 12 }}>
            <span style={{ color: C.green, fontWeight: 700, minWidth: 100, cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
            <span style={{ color: C.dim, minWidth: 90 }}>{r.announcement_date}</span>
            <span style={{ color: C.primary }}>{r.subject}</span>
          </div>
        ))}
        {(!rpt.screen2_dividends?.length) && <div style={{ color: C.dim, fontSize: 12 }}>No dividend/bonus/split events in lookback</div>}
      </Card>

      {/* Screen 3: Insider Clusters */}
      <Card title="Screen 3 - Insider Cluster Buying (3+ insiders)" count={rpt.screen3_insider_clusters?.length} accent={C.yellow}>
        {(rpt.screen3_insider_clusters || []).map((r, i) => (
          <div key={i} style={{ padding: "8px 0", borderBottom: `1px solid ${C.border}22` }}>
            <div style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
              <span style={{ color: C.yellow, fontWeight: 800, fontSize: 14, cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
              <span style={{ color: C.green, fontSize: 12 }}>{r.n_buys} insiders</span>
              <span style={{ color: C.cyan, fontSize: 12 }}>Rs {num(r.total_value_cr, 1)} Cr total</span>
            </div>
            <div style={{ color: C.dim, fontSize: 11, marginTop: 3 }}>{r.names}</div>
          </div>
        ))}
        {(!rpt.screen3_insider_clusters?.length) && <div style={{ color: C.dim, fontSize: 12 }}>No insider clusters found</div>}
      </Card>

      {/* Screen 4: Big insider trades */}
      <Card title="Screen 4 - Big Insider Trades (>1 Cr)" count={rpt.screen4_big_trades?.length} accent={C.yellow}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                {["Symbol","Date","Name","Type","Qty","Price","Value Cr"].map(h => (
                  <th key={h} style={{ padding: "4px 8px", color: C.dim, textAlign: "right", fontWeight: 600, borderBottom: `1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(rpt.screen4_big_trades || []).slice(0, 20).map((t, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
                  <td style={{ padding: "4px 8px", color: C.cyan, fontWeight: 700, cursor: "pointer" }} onClick={() => router.push(`/deep/${t.symbol}`)}>{t.symbol}</td>
                  <td style={{ padding: "4px 8px", color: C.dim, textAlign: "right" }}>{t.filing_date}</td>
                  <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.name}</td>
                  <td style={{ padding: "4px 8px", fontWeight: 700, textAlign: "right", color: t.transaction_type === "BUY" ? C.green : C.red }}>{t.transaction_type}</td>
                  <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.quantity?.toLocaleString("en-IN")}</td>
                  <td style={{ padding: "4px 8px", textAlign: "right" }}>{num(t.price, 1)}</td>
                  <td style={{ padding: "4px 8px", textAlign: "right", color: C.cyan }}>{t.value ? (t.value / 1e7).toFixed(2) : "--"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(!rpt.screen4_big_trades?.length) && <div style={{ color: C.dim, fontSize: 12 }}>No big insider trades in lookback</div>}
      </Card>

      {/* Screen 5: Post-results reaction */}
      <Card title="Screen 5 - Post-Results Price Reaction" count={rpt.screen5_post_results_reaction?.length} accent={C.cyan}>
        {(rpt.screen5_post_results_reaction || []).slice(0, 15).map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 12, padding: "5px 0", borderBottom: `1px solid ${C.border}22`, fontSize: 12 }}>
            <span style={{ color: C.cyan, fontWeight: 700, minWidth: 100, cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
            <span style={{ color: C.dim, minWidth: 90 }}>{r.announcement_date}</span>
            <span style={{ color: col(r.reaction_pct), fontWeight: 700 }}>{pct(r.reaction_pct)}</span>
            <span style={{ color: C.dim }}>{num(r.price_before, 1)} to {num(r.price_after, 1)}</span>
          </div>
        ))}
        {(!rpt.screen5_post_results_reaction?.length) && <div style={{ color: C.dim, fontSize: 12 }}>No post-results reactions found</div>}
      </Card>

      {/* Screen 6: Upcoming results */}
      <Card title="Screen 6 - Upcoming Results Calendar" count={rpt.screen6_upcoming_results?.length} accent={C.green}>
        {(rpt.screen6_upcoming_results || []).slice(0, 20).map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 12, padding: "5px 0", borderBottom: `1px solid ${C.border}22`, fontSize: 12 }}>
            <span style={{ color: C.green, fontWeight: 700, minWidth: 100, cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
            <span style={{ color: C.dim, minWidth: 90 }}>Last: {r.last_results_date}</span>
            <span style={{ color: C.yellow }}>Expected: {r.expected_due}</span>
          </div>
        ))}
        {(!rpt.screen6_upcoming_results?.length) && <div style={{ color: C.dim, fontSize: 12 }}>No upcoming results predicted</div>}
      </Card>

      {/* LLM synthesis */}
      {rpt.llm_analysis && (
        <Card title="Eta Intelligence Synthesis" accent={C.cyan}>
          <MarkdownText text={rpt.llm_analysis} />
        </Card>
      )}
    </div>
  );
}
""")


# =============================================================================
# [9/10] Patch NavBar.tsx -- add DEEP + ETA links
# =============================================================================
print("\n[9/10] Patching NavBar.tsx...")

navbar_candidates = [
    COMP / "NavBar.tsx",
    DASH / "src" / "components" / "NavBar.tsx",
    DASH / "src" / "app" / "components" / "NavBar.tsx",
]

navbar_path = None
for p in navbar_candidates:
    if p.exists():
        navbar_path = p
        break

if navbar_path is None:
    print("  [WARN] NavBar.tsx not found — searching...")
    import subprocess
    result = subprocess.run(
        ["where", "/R", str(DASH / "src"), "NavBar.tsx"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if "NavBar.tsx" in line:
            navbar_path = Path(line.strip())
            break

if navbar_path and navbar_path.exists():
    nb = read(navbar_path)

    # Detect existing nav link pattern for insertion
    # Try to find WATCHLIST or BACKTEST link to insert after
    INSERT_PAIRS = [
        ('WATCHLIST', 'ETA'),
        ('backtest', 'eta'),
        ('/backtest', '/eta'),
    ]

    patched = False

    # Strategy 1: insert ETA after WATCHLIST, DEEP after BACKTEST (or vice versa)
    # Look for the href pattern
    import re

    # Find if DEEP and ETA already exist
    has_deep = '/deep' in nb
    has_eta  = '/eta'  in nb

    if not has_deep or not has_eta:
        # Find the last nav link to append after
        # Look for a pattern like href="/backtest" or href="/watchlist"
        # and add our links after them

        patterns_to_try = [
            # (search_text, insert_after, new_links)
            (
                'href="/watchlist"',
                'href="/watchlist"',
                '  href="/eta"',
            ),
        ]

        # Build the new link blocks based on the existing style
        # Detect link style: look for <a href= or <Link href=
        if 'href="/backtest"' in nb and not has_deep:
            # Insert DEEP after backtest
            nb = nb.replace(
                'href="/backtest"',
                'href="/backtest"',  # no-op; we add after the full element
            )

        # More robust: find the last </a> or </Link> in the nav list area
        # and inject our links before the closing nav tag

        # Find closing nav patterns
        CLOSING_PATTERNS = ['</nav>', '</ul>', '</div>']
        NAV_LINK_PATTERNS = [
            # Look for the watchlist link block and insert ETA right after it
            ('"/watchlist"', '"/eta"', '/eta', 'ETA'),
            ('"/backtest"',  '"/deep"', '/deep', 'DEEP'),
        ]

        # Simpler: regex to find existing links and duplicate the pattern
        link_re = re.search(r'(href="/(\w+)"\s*[^>]*>[^<]*</[^>]+>)', nb)

        if link_re:
            link_template = link_re.group(0)  # e.g. href="/overview">OVERVIEW</a>

        # Least-fragile approach: inject raw strings
        # Find a clear anchor: the watchlist href occurrence
        if '"/watchlist"' in nb and '"/eta"' not in nb:
            # Find the full link element containing watchlist
            # Pattern: anything from before href="/watchlist" to the end of that element
            # Could be <Link href="/watchlist">WATCHLIST</Link> or <a href="/watchlist">...
            for tag_open, tag_close, new_href, new_label in [
                ('<Link href="/watchlist"', '</Link>', '/eta', 'ETA'),
                ('<a href="/watchlist"',    '</a>',    '/eta', 'ETA'),
            ]:
                if tag_open in nb:
                    # Find the closing tag after tag_open
                    start = nb.find(tag_open)
                    end   = nb.find(tag_close, start) + len(tag_close)
                    watchlist_block = nb[start:end]
                    eta_block = watchlist_block.replace('/watchlist', new_href).replace('WATCHLIST', new_label).replace('Watchlist', new_label)
                    nb = nb[:end] + "\n        " + eta_block + nb[end:]
                    patched = True
                    print("  Injected ETA link after WATCHLIST")
                    break

        if '"/backtest"' in nb and '"/deep"' not in nb:
            for tag_open, tag_close, new_href, new_label in [
                ('<Link href="/backtest"', '</Link>', '/deep', 'DEEP'),
                ('<a href="/backtest"',    '</a>',    '/deep', 'DEEP'),
            ]:
                if tag_open in nb:
                    start = nb.find(tag_open)
                    end   = nb.find(tag_close, start) + len(tag_close)
                    backtest_block = nb[start:end]
                    deep_block = backtest_block.replace('/backtest', new_href).replace('BACKTEST', new_label).replace('Backtest', new_label)
                    nb = nb[:end] + "\n        " + deep_block + nb[end:]
                    patched = True
                    print("  Injected DEEP link after BACKTEST")
                    break

        if patched:
            navbar_path.write_text(nb, encoding="utf-8", newline="\n")
            print(f"  [OK] NavBar.tsx patched: {navbar_path}")
        else:
            print(f"  [WARN] Could not auto-patch NavBar. Add manually:")
            print(f"         <Link href='/deep'>DEEP</Link>")
            print(f"         <Link href='/eta'>ETA</Link>")
    else:
        print("  DEEP and ETA links already present in NavBar")
else:
    print("  [WARN] NavBar.tsx not found. Add DEEP and ETA links manually.")


# =============================================================================
# [10/10] Patch telegram_bot.py -- /eta /deep /kappa commands
# =============================================================================
print("\n[10/10] Patching telegram_bot.py...")

bot_path = BASE / "telegram_bot.py"

if not bot_path.exists():
    print("  [WARN] telegram_bot.py not found")
else:
    bot = read(bot_path)

    # Inject /eta command handler if not present
    ETA_CMD = '''
async def cmd_eta(update, context):
    """Send latest Eta (corporate events) report summary."""
    report_path = Path(r"D:\\MICC\\agents\\eta\\last_report.json")
    if not report_path.exists():
        await update.message.reply_text("No Eta report. Run: py agent_eta.py")
        return
    import json
    rpt = json.loads(report_path.read_text(encoding="utf-8"))
    lines = [
        f"*MICC Eta - Corporate Events*",
        f"Date: {rpt.get('date', '?')}",
        "",
        f"*Results Season:* {len(rpt.get('screen1_results_season', []))} companies",
        f"*Dividends/Bonus:* {len(rpt.get('screen2_dividends', []))} events",
        f"*Insider Clusters:* {len(rpt.get('screen3_insider_clusters', []))} stocks",
        f"*Big Trades (>1Cr):* {len(rpt.get('screen4_big_trades', []))} trades",
        f"*Post-Results:* {len(rpt.get('screen5_post_results_reaction', []))} reactions",
        f"*Upcoming Results:* {len(rpt.get('screen6_upcoming_results', []))} predicted",
    ]
    clusters = rpt.get("screen3_insider_clusters", [])[:3]
    if clusters:
        lines.append("")
        lines.append("*Top Insider Clusters:*")
        for c in clusters:
            lines.append(f"  {c.get('symbol')} - {c.get('n_buys')} insiders, Rs {c.get('total_value_cr', 0):.1f} Cr")
    analysis = rpt.get("llm_analysis", "")
    if analysis:
        lines.append("")
        lines.append("*Analysis:*")
        lines.append(analysis[:600])
    await update.message.reply_text("\\n".join(lines), parse_mode="Markdown")

'''

    DEEP_CMD = '''
async def cmd_deep(update, context):
    """Send Iota deep analysis summary."""
    report_path = Path(r"D:\\MICC\\agents\\iota\\last_report.json")
    if not report_path.exists():
        await update.message.reply_text("No Iota report. Run: py agent_iota.py")
        return
    import json
    rpt = json.loads(report_path.read_text(encoding="utf-8"))
    regime = rpt.get("current_regime", "?")
    vix    = rpt.get("vix", "?")
    ret20  = rpt.get("nifty_20d_return", "?")
    s1 = rpt.get("screen1_best_probability", [])[:5]
    s2 = rpt.get("screen2_risk_adjusted", [])[:3]
    s5 = rpt.get("screen5_global", {})
    lines = [
        f"*MICC Deep Analysis Room*",
        f"Date: {rpt.get('date', '?')}",
        f"Regime: {regime} | VIX: {vix} | Nifty20d: {ret20}%",
        "",
        f"*Global:* {s5.get('global_risk', '?')} | SPX5d: {s5.get('spx_5d', '?')}%",
        "",
        "*Top Probability Stocks (20d):*",
    ]
    for s in s1:
        lines.append(f"  {s.get('symbol')} prob={s.get('prob_positive')}% mean={s.get('mean_return')}%")
    lines.append("")
    lines.append("*Top Sharpe Gems:*")
    for s in s2:
        lines.append(f"  {s.get('symbol')} Sharpe={s.get('sharpe_ratio')} mean={s.get('mean_return')}%")
    analysis = rpt.get("llm_analysis", "")
    if analysis:
        lines.append("")
        lines.append(analysis[:500])
    await update.message.reply_text("\\n".join(lines), parse_mode="Markdown")

'''

    KAPPA_CMD = '''
async def cmd_kappa(update, context):
    """Send Kappa deep profile for a symbol. Usage: /kappa RELIANCE"""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /kappa SYMBOL\\nExample: /kappa RELIANCE")
        return
    sym = args[0].upper()
    report_path = Path(rf"D:\\MICC\\agents\\kappa\\{sym}_report.json")
    if not report_path.exists():
        await update.message.reply_text(
            f"No Kappa report for {sym}.\\nRun: py D:\\\\MICC\\\\agent_kappa.py {sym}"
        )
        return
    import json
    rpt = json.loads(report_path.read_text(encoding="utf-8"))
    ss = rpt.get("series_stats", {}) or {}
    tech = rpt.get("technicals", {}) or {}
    lines = [
        f"*Kappa: {sym}*",
        f"Type: {rpt.get('asset_type', '?')} | Date: {rpt.get('date', '?')}",
        "",
        f"CAGR: {ss.get('cagr_pct', '?')}% | Vol: {ss.get('ann_volatility_pct', '?')}%",
        f"MaxDD: {ss.get('max_drawdown_pct', '?')}% | Sharpe: {ss.get('sharpe_ratio', '?')}",
    ]
    verdict = rpt.get("llm_verdict", "")
    if verdict:
        lines.append("")
        lines.append(verdict[:600])
    await update.message.reply_text("\\n".join(lines), parse_mode="Markdown")

'''

    # Inject handlers if not present
    needs_write = False

    if "cmd_eta" not in bot:
        # Find a good insertion point: before main() or before application.run
        for anchor in ["async def main(", "def main(", "if __name__"]:
            if anchor in bot:
                bot = bot.replace(anchor, ETA_CMD + "\n\n" + anchor, 1)
                needs_write = True
                print("  Added cmd_eta handler")
                break

    if "cmd_deep" not in bot:
        for anchor in ["async def main(", "def main(", "if __name__"]:
            if anchor in bot:
                bot = bot.replace(anchor, DEEP_CMD + "\n\n" + anchor, 1)
                needs_write = True
                print("  Added cmd_deep handler")
                break

    if "cmd_kappa" not in bot:
        for anchor in ["async def main(", "def main(", "if __name__"]:
            if anchor in bot:
                bot = bot.replace(anchor, KAPPA_CMD + "\n\n" + anchor, 1)
                needs_write = True
                print("  Added cmd_kappa handler")
                break

    # Register handlers in main() -- add add_handler calls
    # Look for existing handler registration pattern
    HANDLER_REGS = [
        ('cmd_eta',   '/eta',   "application.add_handler(CommandHandler('eta',   cmd_eta))"),
        ('cmd_deep',  '/deep',  "application.add_handler(CommandHandler('deep',  cmd_deep))"),
        ('cmd_kappa', '/kappa', "application.add_handler(CommandHandler('kappa', cmd_kappa))"),
    ]

    for fn_name, cmd_name, handler_line in HANDLER_REGS:
        if f"CommandHandler('{cmd_name.strip('/')}'," not in bot:
            # Find existing handler registration and add after it
            for existing in ["add_handler(CommandHandler('status'", "add_handler(CommandHandler('eta'",
                            "add_handler(CommandHandler('backtest'", "application.run_polling"]:
                if existing in bot and handler_line not in bot:
                    insert_at = bot.find("application.run_polling")
                    if insert_at > 0:
                        bot = bot[:insert_at] + f"    {handler_line}\n    " + bot[insert_at:]
                        needs_write = True
                        print(f"  Registered {cmd_name} command handler")
                        break

    if needs_write:
        bot_path.write_text(bot, encoding="utf-8", newline="\n")
        print(f"  [OK] telegram_bot.py patched")
    else:
        print("  telegram_bot.py already up to date")


# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "=" * 65)
print("PHASE 9D COMPLETE")
print("=" * 65)
print()
print("Files created:")
print("  micc-dashboard/src/app/api/deep/route.ts")
print("  micc-dashboard/src/app/api/deep/[symbol]/route.ts")
print("  micc-dashboard/src/app/api/compare/route.ts")
print("  micc-dashboard/src/app/api/eta/route.ts")
print("  micc-dashboard/src/app/deep/page.tsx")
print("  micc-dashboard/src/app/deep/[symbol]/page.tsx")
print("  micc-dashboard/src/app/compare/page.tsx")
print("  micc-dashboard/src/app/eta/page.tsx")
print("  NavBar.tsx (patched: DEEP + ETA links)")
print("  telegram_bot.py (patched: /eta /deep /kappa commands)")
print()
print("Test sequence:")
print("  1. py D:\\MICC\\agent_iota.py           -- generate Iota report")
print("  2. py D:\\MICC\\agent_eta.py             -- generate Eta report")
print("  3. py D:\\MICC\\agent_kappa.py RELIANCE  -- generate a Kappa report")
print("  4. cd micc-dashboard && npm run dev")
print("  5. localhost:3000/deep                  -- Iota room")
print("  6. localhost:3000/deep/RELIANCE         -- Kappa profile")
print("  7. localhost:3000/compare               -- Lambda compare")
print("  8. localhost:3000/eta                   -- Eta corporate events")
print()
print("Telegram: /deep  /eta  /kappa RELIANCE")
print("=" * 65)
