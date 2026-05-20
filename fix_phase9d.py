# -*- coding: utf-8 -*-
"""
fix_phase9d.py  --  Run from D:\MICC
==============================================
Fixes TWO things:

1. Watchlist 404 -- diagnoses why and regenerates the page
2. Phase 9D pages -- /deep /deep/[symbol] /compare /eta
   + correct NavBar patch (adds DEEP, ETA, WATCHLIST if missing)
   + API routes for all new pages

Run: py D:\MICC\fix_phase9d.py
"""

from pathlib import Path
import re

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
SRC  = DASH / "src"
APP  = SRC / "app"
COMP = SRC / "components"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# =============================================================================
# DIAGNOSTIC
# =============================================================================
print("\n" + "=" * 60)
print("PHASE 9D FIX + WATCHLIST REPAIR")
print("=" * 60)

print("\n[DIAG] Checking existing page files...")
pages_to_check = [
    APP / "watchlist" / "page.tsx",
    APP / "backtest"  / "page.tsx",
    APP / "deep"      / "page.tsx",
    APP / "eta"       / "page.tsx",
    APP / "compare"   / "page.tsx",
]
for p in pages_to_check:
    status = "EXISTS" if p.exists() else "MISSING"
    print(f"  {status}: {p.relative_to(BASE)}")

# Find NavBar
navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p
    break
if navbar_path:
    print(f"\n[DIAG] NavBar: {navbar_path.relative_to(BASE)}")
    nb_src = read(navbar_path)
    for line in nb_src.splitlines():
        if "href" in line and ("/" in line):
            print(f"  {line.strip()}")
else:
    print("\n[WARN] NavBar.tsx not found!")


# =============================================================================
# [1] FIX NAVBAR -- definitive rewrite with all current links
# =============================================================================
print("\n[1/6] Rewriting NavBar.tsx with all links...")

write(COMP / "NavBar.tsx", r"""
"use client";
import Link            from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const PAGES = [
  { href: "/",          label: "OVERVIEW"  },
  { href: "/streaks",   label: "STREAKS"   },
  { href: "/indices",   label: "INDICES"   },
  { href: "/options",   label: "OPTIONS"   },
  { href: "/macro",     label: "MACRO"     },
  { href: "/mf",        label: "MF NAV"   },
  { href: "/watchlist", label: "WATCHLIST" },
  { href: "/backtest",  label: "BACKTEST"  },
  { href: "/eta",       label: "ETA"       },
  { href: "/deep",      label: "DEEP"      },
  { href: "/compare",   label: "COMPARE"   },
];

export default function NavBar() {
  const path = usePathname();
  const [time, setTime] = useState("");

  useEffect(() => {
    function tick() {
      setTime(
        new Date().toLocaleTimeString("en-IN", {
          hour: "2-digit", minute: "2-digit", second: "2-digit",
          timeZone: "Asia/Kolkata",
        }) + " IST"
      );
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 100,
      background: "var(--bg)", borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center",
      padding: "0 16px", height: 48, gap: 0, overflowX: "auto",
    }}>
      <div style={{
        fontFamily: "'Share Tech Mono','JetBrains Mono',monospace",
        fontSize: 15, fontWeight: 700, letterSpacing: "0.18em",
        color: "var(--accent)", marginRight: 20, whiteSpace: "nowrap",
        flexShrink: 0,
      }}>
        MICC
      </div>
      <nav style={{ display: "flex", gap: 1, flex: 1 }}>
        {PAGES.map(({ href, label }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} style={{
              padding: "6px 11px", fontSize: 10,
              fontFamily: "'JetBrains Mono',monospace",
              letterSpacing: "0.08em",
              fontWeight: active ? 700 : 400,
              color: active ? "var(--accent)" : "var(--muted)",
              borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
              textDecoration: "none", transition: "color 0.15s",
              whiteSpace: "nowrap",
            }}>
              {label}
            </Link>
          );
        })}
      </nav>
      <div style={{
        fontFamily: "monospace", fontSize: 10,
        color: "var(--dim)", whiteSpace: "nowrap", flexShrink: 0,
      }} suppressHydrationWarning>{time}</div>
    </header>
  );
}
""")


# =============================================================================
# [2] FIX WATCHLIST 404 -- rewrite page.tsx with "use client" as first line
# =============================================================================
print("\n[2/6] Fixing watchlist page.tsx...")

write(APP / "watchlist" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import MarkdownText from "@/components/MarkdownText";

interface PriceRow    { symbol: string; close: number; date: string; pct_chg: number; }
interface AlertDef    { symbol: string; condition: string; level: number; }
interface AlertResult { symbol: string; condition: string; level: number; price: number; pct_from: number; }
interface BreakoutRow { symbol: string; close: number; high_52w: number; pct_from_52h: number; }
interface SurgeRow    { symbol: string; close: number; vol_surge: number; deliv_pct: number; }
interface SLRow       { symbol: string; close: number; ma20: number; pct_vs_ma: number; }
interface ReentryRow  { symbol: string; close: number; pullback_pct: number; near_ma10: boolean; }
interface StreakRow    { symbol: string; streak: number; score: number; tags: string; }
interface WatchlistData {
  date: string | null;
  watchlist: { symbols: string[]; alerts: AlertDef[]; notes: Record<string, string> };
  prices: PriceRow[];
  triggered_alerts: AlertResult[];
  breakout_watch: BreakoutRow[];
  vol_delivery_surge: SurgeRow[];
  stoploss_watch: SLRow[];
  reentry_radar: ReentryRow[];
  watchlist_streaks: StreakRow[];
  analysis: string;
}

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

function pct(v: number | null | undefined) {
  if (v == null) return "--";
  return `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`;
}
function col(v: number | null | undefined) { return (v ?? 0) >= 0 ? C.green : C.red; }

function Card({ title, count, children, accent }: {
  title: string; count?: number; children: React.ReactNode; accent?: string;
}) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${accent || C.border}`,
      borderRadius: 8, padding: "16px 20px", marginBottom: 18,
    }}>
      <div style={{
        display: "flex", justifyContent: "space-between",
        borderBottom: `1px solid ${C.border}`, paddingBottom: 8, marginBottom: 12,
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5,
          color: accent || C.cyan, textTransform: "uppercase" }}>{title}</span>
        {count !== undefined && <span style={{ fontSize: 11, color: C.dim }}>{count}</span>}
      </div>
      {children}
    </div>
  );
}

export default function WatchlistPage() {
  const router = useRouter();
  const [data, setData] = useState<WatchlistData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addSym, setAddSym] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch("/api/watchlist", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setData(d);
    } catch (e: unknown) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addSymbol = async () => {
    const sym = addSym.trim().toUpperCase();
    if (!sym) return;
    setSaving(true);
    try {
      await fetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "add_symbol", symbol: sym }),
      });
      setAddSym("");
      await load();
    } finally { setSaving(false); }
  };

  const removeSymbol = async (sym: string) => {
    setSaving(true);
    try {
      await fetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "remove_symbol", symbol: sym }),
      });
      await load();
    } finally { setSaving(false); }
  };

  if (loading) return (
    <div style={{ padding: 40, color: C.dim, textAlign: "center" }}>Loading watchlist...</div>
  );
  if (error) return (
    <div style={{ padding: 40, color: C.red }}>
      Error: {error}
      <br /><span style={{ fontSize: 12, color: C.dim }}>
        Run: py D:\MICC\agent_zeta.py to generate watchlist data
      </span>
    </div>
  );

  const d = data!;
  const syms = d.watchlist?.symbols || [];

  return (
    <div style={{ maxWidth: 1050, margin: "0 auto", padding: "24px 16px" }}>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>WATCHLIST</h1>
          <div style={{ color: C.dim, fontSize: 12, marginTop: 4 }}>
            Agent Zeta &bull; {d.date || "No report yet"} &bull; {syms.length} symbols
          </div>
        </div>
        <button onClick={load} style={{
          background: "transparent", border: `1px solid ${C.border}`,
          color: C.dim, borderRadius: 6, padding: "6px 12px", cursor: "pointer", fontSize: 12,
        }}>Refresh</button>
      </div>

      {/* Add symbol */}
      <Card title="Manage Symbols" accent={C.cyan}>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <input
            value={addSym}
            onChange={e => setAddSym(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === "Enter" && addSymbol()}
            placeholder="Add symbol (e.g. RELIANCE)"
            style={{
              background: "transparent", border: `1px solid ${C.border}`, color: C.primary,
              borderRadius: 6, padding: "8px 12px", fontSize: 13, width: 240,
            }}
          />
          <button onClick={addSymbol} disabled={saving} style={{
            background: C.cyan, color: "#000", border: "none",
            borderRadius: 6, padding: "8px 16px", fontWeight: 700,
            cursor: "pointer", fontSize: 13, opacity: saving ? 0.6 : 1,
          }}>Add</button>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {syms.map(sym => (
            <div key={sym} style={{
              display: "flex", alignItems: "center", gap: 6,
              background: `${C.border}33`, borderRadius: 6, padding: "5px 10px",
            }}>
              <span
                style={{ color: C.cyan, fontWeight: 700, fontSize: 13, cursor: "pointer" }}
                onClick={() => router.push(`/deep/${sym}`)}
              >{sym}</span>
              <button onClick={() => removeSymbol(sym)} style={{
                background: "transparent", border: "none", color: C.dim,
                cursor: "pointer", fontSize: 14, padding: "0 2px", lineHeight: 1,
              }}>x</button>
            </div>
          ))}
          {syms.length === 0 && (
            <span style={{ color: C.dim, fontSize: 12 }}>
              No symbols yet. Edit D:\MICC\micc_watchlist.json or add above.
            </span>
          )}
        </div>
      </Card>

      {/* Prices */}
      {d.prices && d.prices.length > 0 && (
        <Card title="Current Prices" count={d.prices.length} accent={C.cyan}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {["Symbol", "Close", "Date", "1D %"].map(h => (
                    <th key={h} style={{ padding: "4px 8px", color: C.dim, textAlign: "right",
                      fontWeight: 600, borderBottom: `1px solid ${C.border}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.prices.map((r, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
                    <td style={{ padding: "5px 8px", color: C.cyan, fontWeight: 700,
                      cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</td>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>
                      {r.close?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: C.dim }}>{r.date}</td>
                    <td style={{ padding: "5px 8px", textAlign: "right",
                      fontWeight: 700, color: col(r.pct_chg) }}>{pct(r.pct_chg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Triggered alerts */}
      {d.triggered_alerts && d.triggered_alerts.length > 0 && (
        <Card title="Triggered Alerts" count={d.triggered_alerts.length} accent={C.yellow}>
          {d.triggered_alerts.map((a, i) => (
            <div key={i} style={{
              display: "flex", gap: 12, padding: "5px 0",
              borderBottom: `1px solid ${C.border}22`, fontSize: 12,
            }}>
              <span style={{ color: C.yellow, fontWeight: 700, minWidth: 100 }}>{a.symbol}</span>
              <span style={{ color: C.dim }}>{a.condition} {a.level}</span>
              <span style={{ color: col(a.pct_from) }}>{pct(a.pct_from)} from level</span>
            </div>
          ))}
        </Card>
      )}

      {/* Breakout watch */}
      {d.breakout_watch && d.breakout_watch.length > 0 && (
        <Card title="Breakout Watch (near 52w high)" count={d.breakout_watch.length} accent={C.green}>
          {d.breakout_watch.slice(0, 10).map((r, i) => (
            <div key={i} style={{
              display: "flex", gap: 16, padding: "5px 0",
              borderBottom: `1px solid ${C.border}22`, fontSize: 12,
            }}>
              <span style={{ color: C.green, fontWeight: 700, minWidth: 100,
                cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
              <span>Close: {r.close?.toFixed(2)}</span>
              <span style={{ color: C.dim }}>52w High: {r.high_52w?.toFixed(2)}</span>
              <span style={{ color: col(r.pct_from_52h) }}>{pct(r.pct_from_52h)} from high</span>
            </div>
          ))}
        </Card>
      )}

      {/* Vol/delivery surge */}
      {d.vol_delivery_surge && d.vol_delivery_surge.length > 0 && (
        <Card title="Vol + Delivery Surge" count={d.vol_delivery_surge.length} accent={C.cyan}>
          {d.vol_delivery_surge.slice(0, 10).map((r, i) => (
            <div key={i} style={{
              display: "flex", gap: 16, padding: "5px 0",
              borderBottom: `1px solid ${C.border}22`, fontSize: 12,
            }}>
              <span style={{ color: C.cyan, fontWeight: 700, minWidth: 100,
                cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
              <span>Close: {r.close?.toFixed(2)}</span>
              <span style={{ color: C.green }}>Vol: {r.vol_surge?.toFixed(1)}x</span>
              <span style={{ color: C.yellow }}>Deliv: {r.deliv_pct?.toFixed(1)}%</span>
            </div>
          ))}
        </Card>
      )}

      {/* Stop-loss watch */}
      {d.stoploss_watch && d.stoploss_watch.length > 0 && (
        <Card title="Stop-Loss Watch (below SMA20)" count={d.stoploss_watch.length} accent={C.red}>
          {d.stoploss_watch.slice(0, 10).map((r, i) => (
            <div key={i} style={{
              display: "flex", gap: 16, padding: "5px 0",
              borderBottom: `1px solid ${C.border}22`, fontSize: 12,
            }}>
              <span style={{ color: C.red, fontWeight: 700, minWidth: 100,
                cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
              <span>Close: {r.close?.toFixed(2)}</span>
              <span style={{ color: C.dim }}>SMA20: {r.ma20?.toFixed(2)}</span>
              <span style={{ color: C.red }}>{pct(r.pct_vs_ma)} vs SMA20</span>
            </div>
          ))}
        </Card>
      )}

      {/* Re-entry radar */}
      {d.reentry_radar && d.reentry_radar.length > 0 && (
        <Card title="Re-entry Radar (5-20% pullback from peak)" count={d.reentry_radar.length} accent={C.yellow}>
          {d.reentry_radar.slice(0, 10).map((r, i) => (
            <div key={i} style={{
              display: "flex", gap: 16, padding: "5px 0",
              borderBottom: `1px solid ${C.border}22`, fontSize: 12,
            }}>
              <span style={{ color: C.yellow, fontWeight: 700, minWidth: 100,
                cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
              <span>Close: {r.close?.toFixed(2)}</span>
              <span style={{ color: C.red }}>Pullback: {r.pullback_pct?.toFixed(1)}%</span>
              <span style={{ color: r.near_ma10 ? C.green : C.dim }}>
                {r.near_ma10 ? "Near MA10" : ""}
              </span>
            </div>
          ))}
        </Card>
      )}

      {/* Watchlist streaks */}
      {d.watchlist_streaks && d.watchlist_streaks.length > 0 && (
        <Card title="Screener Streaks" count={d.watchlist_streaks.length} accent={C.cyan}>
          {d.watchlist_streaks.slice(0, 10).map((r, i) => (
            <div key={i} style={{
              display: "flex", gap: 16, padding: "5px 0",
              borderBottom: `1px solid ${C.border}22`, fontSize: 12,
            }}>
              <span style={{ color: C.cyan, fontWeight: 700, minWidth: 100,
                cursor: "pointer" }} onClick={() => router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
              <span style={{ color: C.green }}>{r.streak}d streak</span>
              <span style={{ color: C.dim }}>score: {r.score}</span>
              <span style={{ color: C.dim, fontSize: 11 }}>{r.tags}</span>
            </div>
          ))}
        </Card>
      )}

      {/* Analysis */}
      {d.analysis ? (
        <Card title="Zeta Intelligence" accent={C.cyan}>
          <MarkdownText text={d.analysis} />
        </Card>
      ) : (
        <Card title="Zeta Intelligence" accent={C.dim}>
          <div style={{ color: C.dim, fontSize: 12 }}>
            No analysis yet. Run: <code>py D:\MICC\agent_zeta.py</code>
          </div>
        </Card>
      )}
    </div>
  );
}
""")


# =============================================================================
# [3] API ROUTES for Phase 9D pages
# =============================================================================
print("\n[3/6] Writing API routes...")

# /api/deep
write(APP / "api" / "deep" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'

function queryDb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
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
    const reportPath = path.join(DA, 'agents', 'iota', 'last_report.json')
    let report: Record<string, unknown> = {}
    if (fs.existsSync(reportPath)) {
      report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'))
    }

    // Fresh global snapshot
    const globalRows = queryDb(`
      SELECT g1.symbol, g1.close, g1.date,
        ROUND((g1.close - g2.close) / g2.close * 100, 2) AS ret_5d
      FROM global_indices_daily g1
      LEFT JOIN (
        SELECT symbol, close, date FROM global_indices_daily g
        WHERE date = (
          SELECT date FROM global_indices_daily
          WHERE symbol = g.symbol ORDER BY date DESC LIMIT 1 OFFSET 5
        )
      ) g2 ON g1.symbol = g2.symbol
      WHERE g1.symbol IN ('SPX','NDX','VIX','DXY','GOLD','USDINR','NIKKEI225','DAX','FTSE100')
        AND g1.date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol = g1.symbol)
    `)

    const latestGlobal: Record<string, unknown> = {}
    for (const row of globalRows as Record<string, unknown>[]) {
      latestGlobal[row.symbol as string] = row
    }

    return NextResponse.json({
      ok: true,
      report,
      global_snapshot: latestGlobal,
      current_regime: report.current_regime || 'UNKNOWN',
      report_date: report.date || null,
    })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")

# /api/deep/[symbol]
write(APP / "api" / "deep" / "[symbol]" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'

function queryDb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
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
  const sym = (params.symbol ?? '').toUpperCase().replace(/[^A-Z0-9&]/g, '')
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  try {
    const reportPath = path.join(DA, 'agents', 'kappa', `${sym}_report.json`)
    let report: Record<string, unknown> | null = null
    if (fs.existsSync(reportPath)) {
      report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'))
    }

    const windowStats = queryDb(
      `SELECT window_days, n_windows, mean_return, std_return,
              p5, p25, p75, p95, prob_positive, prob_gt10, prob_lt_neg10,
              sharpe_ratio, ann_return_equiv
       FROM window_stats WHERE symbol=? ORDER BY window_days`, [sym]
    )
    const seasonality = queryDb(
      `SELECT period_value, n_obs, mean_return_pct, median_return_pct
       FROM symbol_seasonality WHERE symbol=? AND period_type='month'
       ORDER BY period_value`, [sym]
    )
    const correlations = queryDb(
      `SELECT symbol_b, correlation_20d, correlation_60d, beta_20d
       FROM symbol_correlations WHERE symbol_a=?
       ORDER BY ABS(correlation_20d) DESC LIMIT 12`, [sym]
    )
    const regimeStats = queryDb(
      `SELECT regime, n_windows, mean_return, std_return, prob_positive, p5, p95
       FROM window_regime_stats WHERE symbol=? AND window_days=20
       ORDER BY regime`, [sym]
    )
    const seriesStats = queryDb(
      `SELECT cagr_pct, ann_volatility_pct, max_drawdown_pct,
              sharpe_ratio, sortino_ratio, calmar_ratio,
              n_trading_days, mdd_start_date, mdd_trough_date, mdd_recovery_days
       FROM symbol_series_stats WHERE symbol=? LIMIT 1`, [sym]
    )
    const technicals = queryDb(
      `SELECT atr_14_pct, adx_14, pct_above_sma20, vol_surge_20d,
              rsi_14, macd_line, macd_signal, bb_pct, as_of_date
       FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1`, [sym]
    )
    const priceRow = queryDb(
      `SELECT close, date, volume FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`, [sym]
    )
    const insider = queryDb(
      `SELECT filing_date, name, category, transaction_type, quantity, price, value
       FROM insider_trading WHERE symbol=? AND transaction_type IN ('BUY','SELL')
       ORDER BY filing_date DESC LIMIT 10`, [sym]
    )
    const announcements = queryDb(
      `SELECT announcement_date, subject FROM corporate_announcements
       WHERE symbol=? ORDER BY announcement_date DESC LIMIT 8`, [sym]
    )

    // Also check market_snapshot for indices
    const indexPrice = priceRow.length === 0 ? queryDb(
      `SELECT close, date FROM market_snapshot WHERE index_name=?
       ORDER BY date DESC LIMIT 1`, [sym.replace(/_/g, ' ')]
    ) : []

    return NextResponse.json({
      ok: true, symbol: sym,
      report,
      has_cached_report: !!report,
      technicals:     technicals[0]   || null,
      window_stats:   windowStats,
      seasonality,
      correlations,
      regime_stats:   regimeStats,
      series_stats:   seriesStats[0]  || null,
      latest_price:   priceRow[0]     || indexPrice[0] || null,
      insider_trades: insider,
      announcements,
    })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")

# /api/compare
write(APP / "api" / "compare" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
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
    .map(s => s.trim().toUpperCase().replace(/[^A-Z0-9&]/g, ''))
    .filter(Boolean).slice(0, 5)

  if (symbols.length < 2) {
    return NextResponse.json({ ok: false, error: 'Need 2-5 symbols' }, { status: 400 })
  }

  const ph = symbols.map(() => '?').join(',')

  try {
    const seriesStats = queryDb(
      `SELECT symbol, cagr_pct, ann_volatility_pct, max_drawdown_pct,
              sharpe_ratio, sortino_ratio, calmar_ratio, n_trading_days
       FROM symbol_series_stats WHERE symbol IN (${ph})`, symbols
    )
    const windowStats = queryDb(
      `SELECT symbol, window_days, mean_return, std_return,
              p5, p95, prob_positive, prob_gt10, sharpe_ratio
       FROM window_stats WHERE symbol IN (${ph}) AND window_days IN (5,10,20,60)
       ORDER BY symbol, window_days`, symbols
    )
    const technicals = queryDb(
      `SELECT t.symbol, t.atr_14_pct, t.adx_14, t.pct_above_sma20,
              t.vol_surge_20d, t.rsi_14, t.macd_line, t.macd_signal,
              t.bb_pct, t.as_of_date
       FROM symbol_technicals t
       INNER JOIN (
         SELECT symbol, MAX(as_of_date) AS md FROM symbol_technicals
         WHERE symbol IN (${ph}) GROUP BY symbol
       ) lx ON t.symbol=lx.symbol AND t.as_of_date=lx.md`,
      [...symbols, ...symbols]
    )
    const prices = queryDb(
      `SELECT p.symbol, p.close, p.date, p.volume
       FROM stock_data p
       INNER JOIN (
         SELECT symbol, MAX(date) AS md FROM stock_data
         WHERE symbol IN (${ph}) GROUP BY symbol
       ) lx ON p.symbol=lx.symbol AND p.date=lx.md`,
      [...symbols, ...symbols]
    )
    const regimeStats = queryDb(
      `SELECT symbol, regime, n_windows, mean_return, prob_positive, p5, p95
       FROM window_regime_stats WHERE symbol IN (${ph}) AND window_days=20
       ORDER BY symbol, regime`, symbols
    )
    const seasonality = queryDb(
      `SELECT symbol, period_value, mean_return_pct, n_obs
       FROM symbol_seasonality WHERE symbol IN (${ph}) AND period_type='month'
       ORDER BY symbol, period_value`, symbols
    )
    const crossCorr = queryDb(
      `SELECT symbol_a, symbol_b, correlation_20d, correlation_60d, beta_20d
       FROM symbol_correlations
       WHERE symbol_a IN (${ph}) AND symbol_b IN (${ph})`,
      [...symbols, ...symbols]
    )
    const recentSignals = queryDb(
      `SELECT symbol, COUNT(DISTINCT run_date) AS days_seen,
              MAX(run_date) AS last_seen, AVG(CAST(score AS REAL)) AS avg_score
       FROM signals_history WHERE symbol IN (${ph})
         AND run_date >= date('now','-30 days')
       GROUP BY symbol`, symbols
    )

    return NextResponse.json({
      ok: true, symbols,
      series_stats: seriesStats,
      window_stats: windowStats,
      technicals, prices,
      regime_stats: regimeStats,
      seasonality,
      cross_correlations: crossCorr,
      recent_signals: recentSignals,
    })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")

# /api/eta
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

print("  API routes done: /api/deep /api/deep/[symbol] /api/compare /api/eta")


# =============================================================================
# [4] /deep/page.tsx  -- Iota Deep Analysis Room
# =============================================================================
print("\n[4/6] Writing /deep/page.tsx...")

write(APP / "deep" / "page.tsx", r"""
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
""")


# =============================================================================
# [5] /deep/[symbol]/page.tsx  -- Kappa per-symbol
# =============================================================================
print("\n[5/6] Writing /deep/[symbol]/page.tsx...")

write(APP / "deep" / "[symbol]" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import MarkdownText from "@/components/MarkdownText";

interface WindowRow { window_days:number; n_windows:number; mean_return:number; std_return:number; p5:number; p25:number; p75:number; p95:number; prob_positive:number; prob_gt10:number; prob_lt_neg10:number; sharpe_ratio:number; ann_return_equiv:number; }
interface SeasonRow { period_value:number; n_obs:number; mean_return_pct:number; median_return_pct:number; }
interface CorrRow   { symbol_b:string; correlation_20d:number; correlation_60d:number; beta_20d:number; }
interface RegRow    { regime:string; n_windows:number; mean_return:number; std_return:number; prob_positive:number; p5:number; p95:number; }
interface Tech      { atr_14_pct:number; adx_14:number; pct_above_sma20:number; vol_surge_20d:number; rsi_14:number; macd_line:number; macd_signal:number; bb_pct:number; as_of_date:string; }
interface Series    { cagr_pct:number; ann_volatility_pct:number; max_drawdown_pct:number; sharpe_ratio:number; sortino_ratio:number; calmar_ratio:number; n_trading_days:number; mdd_start_date:string; mdd_trough_date:string; mdd_recovery_days:number; }
interface Insider   { filing_date:string; name:string; category:string; transaction_type:string; quantity:number; price:number; value:number; }
interface Ann       { announcement_date:string; subject:string; }
interface KappaData {
  ok:boolean; error?:string; symbol:string; has_cached_report:boolean;
  report: { asset_type:string; llm_verdict:string; llm_source:string; timestamp:string; } | null;
  technicals:Tech|null; window_stats:WindowRow[]; seasonality:SeasonRow[];
  correlations:CorrRow[]; regime_stats:RegRow[]; series_stats:Series|null;
  latest_price:{close:number;date:string;volume:number}|null;
  insider_trades:Insider[]; announcements:Ann[];
}

const C = { green:"var(--accent-green)",red:"var(--accent-red)",cyan:"var(--accent-cyan)",yellow:"var(--accent-yellow)",orange:"var(--accent-orange,#f97316)",dim:"var(--text-tertiary)",primary:"var(--text-primary)",border:"var(--border-color)",surface:"var(--surface-card)" };
const pct = (v:unknown,d=2)=>v==null?"--":`${(+v)>=0?"+":""}${(+v).toFixed(d)}%`;
const num = (v:unknown,d=2)=>v==null?"--":(+v).toFixed(d);
const col = (v:unknown)=>(+v??0)>=0?C.green:C.red;
const MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function Card({title,children,accent}:{title:string;children:React.ReactNode;accent?:string}) {
  return <div style={{background:C.surface,border:`1px solid ${accent||C.border}`,borderRadius:8,padding:"16px 20px",marginBottom:18}}><div style={{fontSize:11,fontWeight:700,letterSpacing:1.5,color:accent||C.cyan,textTransform:"uppercase",marginBottom:12,borderBottom:`1px solid ${C.border}`,paddingBottom:8}}>{title}</div>{children}</div>;
}
function Grid({items}:{items:{label:string;value:string;color?:string}[]}) {
  return <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:10}}>{items.map(({label,value,color})=><div key={label} style={{background:`${C.border}22`,borderRadius:6,padding:"10px 12px"}}><div style={{fontSize:10,color:C.dim,fontWeight:700,marginBottom:4}}>{label}</div><div style={{fontSize:16,fontWeight:800,color:color||C.primary}}>{value}</div></div>)}</div>;
}

export default function DeepSymbolPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const router = useRouter();
  const [data, setData] = useState<KappaData|null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string|null>(null);

  const load = useCallback(async () => {
    if (!symbol) return;
    setLoading(true); setError(null);
    try {
      const r = await fetch(`/api/deep/${symbol}`, { cache: "no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error||"API error");
      setData(d);
    } catch(e:unknown) { setError(String(e)); }
    finally { setLoading(false); }
  }, [symbol]);

  useEffect(()=>{ load(); },[load]);

  if (loading) return <div style={{padding:40,color:C.dim,textAlign:"center"}}>Loading {symbol}...</div>;
  if (error)   return <div style={{padding:40,color:C.red}}>Error: {error}</div>;
  if (!data)   return <div style={{padding:40,color:C.yellow}}>No data for {symbol}</div>;

  const ss=data.series_stats, tech=data.technicals, lp=data.latest_price, kv=data.report;
  const seriesItems = ss ? [
    {label:"CAGR",    value:pct(ss.cagr_pct,1),         color:col(ss.cagr_pct)},
    {label:"Ann Vol", value:pct(ss.ann_volatility_pct,1)},
    {label:"Max DD",  value:pct(ss.max_drawdown_pct,1),  color:C.red},
    {label:"Sharpe",  value:num(ss.sharpe_ratio),        color:C.cyan},
    {label:"Sortino", value:num(ss.sortino_ratio),       color:C.cyan},
    {label:"Calmar",  value:num(ss.calmar_ratio),        color:C.cyan},
    {label:"N Days",  value:String(ss.n_trading_days)},
    {label:"DD Days", value:ss.mdd_recovery_days!=null?String(ss.mdd_recovery_days):"--"},
  ] : [];
  const techItems = tech ? [
    {label:"RSI 14",   value:num(tech.rsi_14,1),       color:tech.rsi_14>70?C.red:tech.rsi_14<30?C.green:C.primary},
    {label:"ATR 14%",  value:pct(tech.atr_14_pct,2)},
    {label:"ADX 14",   value:num(tech.adx_14,1),       color:tech.adx_14>25?C.green:C.dim},
    {label:"Vs SMA20", value:pct(tech.pct_above_sma20,2), color:col(tech.pct_above_sma20)},
    {label:"Vol Surge",value:num(tech.vol_surge_20d,1)+"x"},
    {label:"MACD",     value:tech.macd_line>tech.macd_signal?"BULL":"BEAR", color:tech.macd_line>tech.macd_signal?C.green:C.red},
    {label:"BB%",      value:num(tech.bb_pct,2)},
  ] : [];
  const DISPLAY=[5,10,20,60,120];
  const wRows=data.window_stats.filter(r=>DISPLAY.includes(r.window_days));
  const maxAbs=Math.max(...data.seasonality.map(r=>Math.abs(r.mean_return_pct||0)),1);

  return (
    <div style={{maxWidth:1050,margin:"0 auto",padding:"24px 16px"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:12}}>
            <button onClick={()=>router.push("/deep")} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:4,padding:"4px 10px",cursor:"pointer",fontSize:11}}>Back to Room</button>
            <h1 style={{margin:0,fontSize:24,fontWeight:900,color:C.cyan}}>{data.symbol}</h1>
            {kv?.asset_type && <span style={{fontSize:11,fontWeight:700,color:C.dim,border:`1px solid ${C.border}`,borderRadius:4,padding:"2px 8px"}}>{kv.asset_type.toUpperCase()}</span>}
          </div>
          {lp && <div style={{color:C.dim,fontSize:12,marginTop:6}}>Last: <span style={{color:C.primary,fontWeight:700}}>{lp.close?.toLocaleString("en-IN",{maximumFractionDigits:2})}</span> &bull; {lp.date} &bull; Vol: {lp.volume?.toLocaleString("en-IN")}</div>}
        </div>
        <div style={{display:"flex",gap:8}}>
          {!data.has_cached_report && <span style={{fontSize:11,color:C.yellow,border:`1px solid ${C.yellow}44`,borderRadius:4,padding:"3px 8px"}}>Live DB - run: py agent_kappa.py {data.symbol}</span>}
          <button onClick={()=>router.push(`/compare?symbols=${data.symbol}`)} style={{background:"transparent",color:C.yellow,border:`1px solid ${C.yellow}`,borderRadius:6,padding:"6px 12px",fontWeight:700,cursor:"pointer",fontSize:12}}>Compare</button>
          <button onClick={load} style={{background:"transparent",color:C.dim,border:`1px solid ${C.border}`,borderRadius:6,padding:"6px 10px",cursor:"pointer",fontSize:11}}>Refresh</button>
        </div>
      </div>

      {seriesItems.length>0 && <Card title="Full-History Series Stats" accent={C.cyan}><Grid items={seriesItems} />{ss?.mdd_start_date && <div style={{marginTop:12,fontSize:12,color:C.dim}}>Max Drawdown: {ss.mdd_start_date} to {ss.mdd_trough_date}{ss.mdd_recovery_days!=null?` (${ss.mdd_recovery_days}d to recover)`:""}</div>}</Card>}
      {techItems.length>0 && <Card title="Current Technicals" accent={C.yellow}><Grid items={techItems} /></Card>}

      <Card title="Rolling Window Behavior" accent={C.green}>
        {wRows.length===0 ? <div style={{color:C.dim,fontSize:12}}>No window data (run phase9b_build_window_stats.py)</div> :
        <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead><tr>{["Win","N","Mean%","Std%","P5%","P95%","Prob+",">10%","<-10%","Sharpe","Ann%"].map(h=><th key={h} style={{padding:"4px 8px",textAlign:"right",color:C.dim,fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
          <tbody>{wRows.map(r=><tr key={r.window_days} style={{borderBottom:`1px solid ${C.border}22`}}>
            <td style={{padding:"5px 8px",color:C.cyan,fontWeight:700,textAlign:"right"}}>{r.window_days}d</td>
            <td style={{padding:"5px 8px",color:C.dim,textAlign:"right"}}>{r.n_windows}</td>
            <td style={{padding:"5px 8px",color:col(r.mean_return),textAlign:"right"}}>{pct(r.mean_return)}</td>
            <td style={{padding:"5px 8px",color:C.dim,textAlign:"right"}}>{pct(r.std_return)}</td>
            <td style={{padding:"5px 8px",color:col(r.p5),textAlign:"right"}}>{pct(r.p5)}</td>
            <td style={{padding:"5px 8px",color:col(r.p95),textAlign:"right"}}>{pct(r.p95)}</td>
            <td style={{padding:"5px 8px",color:C.green,textAlign:"right"}}>{r.prob_positive}%</td>
            <td style={{padding:"5px 8px",color:C.cyan,textAlign:"right"}}>{r.prob_gt10}%</td>
            <td style={{padding:"5px 8px",color:C.red,textAlign:"right"}}>{r.prob_lt_neg10}%</td>
            <td style={{padding:"5px 8px",color:C.cyan,textAlign:"right"}}>{num(r.sharpe_ratio)}</td>
            <td style={{padding:"5px 8px",color:col(r.ann_return_equiv),textAlign:"right"}}>{pct(r.ann_return_equiv,1)}</td>
          </tr>)}</tbody>
        </table></div>}
      </Card>

      <Card title="Regime Breakdown (20d Window)" accent={C.orange}>
        {data.regime_stats.length===0 ? <div style={{color:C.dim,fontSize:12}}>No regime data</div> :
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(190px,1fr))",gap:10}}>
          {data.regime_stats.map(r=><div key={r.regime} style={{background:`${C.border}22`,borderRadius:6,padding:"10px 12px"}}>
            <div style={{fontSize:11,fontWeight:700,color:C.dim,marginBottom:6}}>{r.regime}</div>
            <div style={{fontSize:12,color:col(r.mean_return)}}>Mean: {pct(r.mean_return)}</div>
            <div style={{fontSize:12,color:C.green}}>Prob+: {r.prob_positive!=null?(r.prob_positive*100).toFixed(0)+"%":"--"}</div>
            <div style={{fontSize:12,color:C.dim}}>N: {r.n_windows} &bull; P5:{pct(r.p5)} P95:{pct(r.p95)}</div>
          </div>)}
        </div>}
      </Card>

      <Card title="Monthly Seasonality" accent={C.cyan}>
        {data.seasonality.length===0 ? <div style={{color:C.dim,fontSize:12}}>No seasonality data</div> :
        <div style={{display:"flex",gap:6,alignItems:"flex-end",height:110}}>
          {data.seasonality.map(r=>{const h=Math.abs((r.mean_return_pct||0)/maxAbs)*80;const pos=(r.mean_return_pct||0)>=0;return(
            <div key={r.period_value} style={{flex:1,textAlign:"center"}}>
              <div style={{fontSize:9,color:col(r.mean_return_pct),fontWeight:700,marginBottom:2}}>{pct(r.mean_return_pct,1)}</div>
              <div style={{height:h,background:pos?C.green:C.red,opacity:0.7,borderRadius:"2px 2px 0 0",minHeight:2}} />
              <div style={{fontSize:9,color:C.dim,marginTop:2}}>{MONTHS[(r.period_value-1)%12]}</div>
            </div>
          );})}
        </div>}
      </Card>

      {data.correlations.length>0 && <Card title="Top Correlations" accent={C.dim}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(170px,1fr))",gap:8}}>
          {data.correlations.slice(0,12).map(c=><div key={c.symbol_b} style={{background:`${C.border}22`,borderRadius:6,padding:"8px 12px",cursor:"pointer"}} onClick={()=>router.push(`/deep/${c.symbol_b}`)}>
            <div style={{color:C.cyan,fontWeight:700,fontSize:13}}>{c.symbol_b}</div>
            <div style={{fontSize:11,color:C.dim}}>20d: <span style={{color:col(c.correlation_20d)}}>{num(c.correlation_20d)}</span> &bull; beta {num(c.beta_20d,2)}</div>
          </div>)}
        </div>
      </Card>}

      {data.insider_trades.length>0 && <Card title="Insider Trades (Recent)" accent={C.yellow}>
        <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead><tr>{["Date","Name","Category","Type","Qty","Price","Value Cr"].map(h=><th key={h} style={{padding:"4px 8px",color:C.dim,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
          <tbody>{data.insider_trades.map((t,i)=><tr key={i} style={{borderBottom:`1px solid ${C.border}22`}}>
            <td style={{padding:"4px 8px",color:C.dim,textAlign:"right"}}>{t.filing_date}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{t.name}</td>
            <td style={{padding:"4px 8px",color:C.dim,textAlign:"right"}}>{t.category}</td>
            <td style={{padding:"4px 8px",fontWeight:700,textAlign:"right",color:t.transaction_type==="BUY"?C.green:C.red}}>{t.transaction_type}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{t.quantity?.toLocaleString("en-IN")}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{num(t.price,1)}</td>
            <td style={{padding:"4px 8px",textAlign:"right",color:C.cyan}}>{t.value?(t.value/1e7).toFixed(2):"--"}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>}

      {data.announcements.length>0 && <Card title="Corporate Announcements" accent={C.dim}>
        {data.announcements.map((a,i)=><div key={i} style={{display:"flex",gap:12,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
          <span style={{color:C.dim,minWidth:90}}>{a.announcement_date}</span>
          <span style={{color:C.primary}}>{a.subject}</span>
        </div>)}
      </Card>}

      {kv?.llm_verdict && <Card title={`Kappa AI Verdict (${kv.llm_source||"LLM"})`} accent={C.cyan}><MarkdownText text={kv.llm_verdict} /></Card>}
    </div>
  );
}
""")


# =============================================================================
# [6] /compare/page.tsx  -- Lambda
# =============================================================================
print("\n[6/6] Writing /compare/page.tsx...")

write(APP / "compare" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

interface SeriesRow { symbol:string; cagr_pct:number; ann_volatility_pct:number; max_drawdown_pct:number; sharpe_ratio:number; sortino_ratio:number; calmar_ratio:number; n_trading_days:number; }
interface WindowRow { symbol:string; window_days:number; mean_return:number; std_return:number; p5:number; p95:number; prob_positive:number; prob_gt10:number; sharpe_ratio:number; }
interface TechRow   { symbol:string; rsi_14:number; adx_14:number; pct_above_sma20:number; vol_surge_20d:number; macd_line:number; macd_signal:number; bb_pct:number; atr_14_pct:number; }
interface PriceRow  { symbol:string; close:number; date:string; volume:number; }
interface SigRow    { symbol:string; days_seen:number; last_seen:string; avg_score:number; }
interface CompData  { ok:boolean; error?:string; symbols:string[]; series_stats:SeriesRow[]; window_stats:WindowRow[]; technicals:TechRow[]; prices:PriceRow[]; recent_signals:SigRow[]; cross_correlations:{symbol_a:string;symbol_b:string;correlation_20d:number;beta_20d:number}[]; }

const COLORS = ["var(--accent-cyan)","var(--accent-green)","var(--accent-yellow)","#f97316","#a855f7"];
const C = { dim:"var(--text-tertiary)",primary:"var(--text-primary)",border:"var(--border-color)",surface:"var(--surface-card)",green:"var(--accent-green)",red:"var(--accent-red)",cyan:"var(--accent-cyan)" };
const pct = (v:unknown,d=1)=>v==null?"--":`${(+v)>=0?"+":""}${(+v).toFixed(d)}%`;
const num = (v:unknown,d=2)=>v==null?"--":(+v).toFixed(d);
const col = (v:unknown)=>(+v??0)>=0?C.green:C.red;

function best(vals:(number|null|undefined)[],hi=true){const ns=vals.map(v=>v??(hi?-Infinity:Infinity));const t=hi?Math.max(...ns):Math.min(...ns);return ns.map(n=>isFinite(n)&&n===t);}

function Card({title,children}:{title:string;children:React.ReactNode}){return <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:8,padding:"16px 20px",marginBottom:18}}><div style={{fontSize:11,fontWeight:700,letterSpacing:1.5,color:C.cyan,textTransform:"uppercase",marginBottom:12,borderBottom:`1px solid ${C.border}`,paddingBottom:8}}>{title}</div>{children}</div>;}

function CTable({title,syms,rows}:{title:string;syms:string[];rows:{metric:string;vals:(string|number|null|undefined)[];hi?:boolean;cf?:(v:unknown)=>string}[]}){
  return <Card title={title}>
    <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
      <thead><tr><th style={{padding:"4px 10px",textAlign:"left",color:C.dim,fontWeight:600,borderBottom:`1px solid ${C.border}`}}>Metric</th>{syms.map((s,i)=><th key={s} style={{padding:"4px 10px",textAlign:"right",color:COLORS[i],fontWeight:700,borderBottom:`1px solid ${C.border}`}}>{s}</th>)}</tr></thead>
      <tbody>{rows.map(row=>{const ib=row.hi!==undefined?best(row.vals as number[],row.hi):null;return(<tr key={row.metric} style={{borderBottom:`1px solid ${C.border}22`}}>
        <td style={{padding:"5px 10px",color:C.dim}}>{row.metric}</td>
        {row.vals.map((v,i)=>{
          const isNum=typeof v==="number";
          const txt=isNum?(row.metric.includes("%")||row.metric.includes("Return")||row.metric.includes("CAGR")||row.metric.includes("Vol")||row.metric.includes("DD")||row.metric.includes("Prob")?pct(v):num(v)):String(v??"--");
          const clr=row.cf?row.cf(v):(ib?.[i]?COLORS[i]:C.primary);
          return <td key={i} style={{padding:"5px 10px",textAlign:"right",color:clr,fontWeight:ib?.[i]?800:400,background:ib?.[i]?`${COLORS[i]}11`:"transparent"}}>{txt}</td>;
        })}
      </tr>);})}</tbody>
    </table></div>
  </Card>;
}

const PRESETS = [
  ["Banks",      "HDFCBANK,ICICIBANK,SBIN,AXISBANK,KOTAKBANK"],
  ["IT Giants",  "TCS,INFY,WIPRO,HCLTECH,TECHM"],
  ["Nifty Top5", "RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK"],
  ["FMCG",       "HINDUNILVR,ITC,NESTLEIND,BRITANNIA,DABUR"],
  ["Indices",    "NIFTY 50,NIFTY BANK,NIFTY IT,NIFTY MIDCAP 100,NIFTY SMALLCAP 100"],
];

export default function ComparePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [input,   setInput]   = useState("");
  const [data,    setData]    = useState<CompData|null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string|null>(null);

  const doCompare = useCallback(async (rawSyms: string) => {
    const symbols = rawSyms.split(/[,\s]+/).map(s=>s.trim().toUpperCase()).filter(Boolean).slice(0,5);
    if (symbols.length<2) { setError("Enter 2-5 symbols separated by commas"); return; }
    setLoading(true); setError(null);
    try {
      const r = await fetch(`/api/compare?symbols=${symbols.join(",")}`, { cache:"no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error||"API error");
      setData(d);
    } catch(e:unknown) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(()=>{
    const s=searchParams.get("symbols")||searchParams.get("s")||"";
    if (s) { setInput(s.replace(/,/g,", ")); doCompare(s); }
  },[searchParams, doCompare]);

  const symList = data?.symbols || [];
  const getS = (sym:string) => data?.series_stats.find(r=>r.symbol===sym);
  const getW = (sym:string,d:number) => data?.window_stats.find(r=>r.symbol===sym&&r.window_days===d);
  const getT = (sym:string) => data?.technicals.find(r=>r.symbol===sym);
  const getP = (sym:string) => data?.prices.find(r=>r.symbol===sym);
  const getSig = (sym:string) => data?.recent_signals.find(r=>r.symbol===sym);

  return (
    <div style={{maxWidth:1100,margin:"0 auto",padding:"24px 16px"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:24}}>
        <h1 style={{margin:0,fontSize:22,fontWeight:800}}>COMPARE</h1>
        <button onClick={()=>router.push("/deep")} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Back to Deep Room</button>
      </div>

      <Card title="Symbol Selection (2-5 symbols)">
        <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10}}>
          <input value={input} onChange={e=>setInput(e.target.value.toUpperCase())}
            onKeyDown={e=>e.key==="Enter"&&doCompare(input)}
            placeholder="RELIANCE, HDFCBANK, TCS, INFY"
            style={{background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:6,padding:"9px 14px",fontSize:13,flex:1,minWidth:280}}
          />
          <button onClick={()=>doCompare(input)} style={{background:C.cyan,color:"#000",border:"none",borderRadius:6,padding:"9px 20px",fontWeight:700,cursor:"pointer",fontSize:13}}>Compare</button>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          {PRESETS.map(([label,val])=>(
            <button key={label} onClick={()=>{setInput(val.replace(/,/g,", "));doCompare(val);}} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:4,padding:"4px 10px",cursor:"pointer",fontSize:11,fontWeight:600}}>{label}</button>
          ))}
        </div>
      </Card>

      {error && <div style={{color:C.red,padding:"8px 0",fontSize:13}}>{error}</div>}
      {loading && <div style={{color:C.dim,padding:"20px 0",textAlign:"center"}}>Comparing...</div>}

      {data && !loading && (<>
        <div style={{display:"flex",gap:16,marginBottom:16}}>
          {symList.map((s,i)=><div key={s} style={{display:"flex",alignItems:"center",gap:6}}>
            <div style={{width:12,height:12,borderRadius:2,background:COLORS[i]}} />
            <span style={{color:COLORS[i],fontWeight:700,fontSize:14,cursor:"pointer"}} onClick={()=>router.push(`/deep/${s}`)}>{s}</span>
          </div>)}
        </div>

        <CTable title="Series Statistics (Full History)" syms={symList} rows={[
          {metric:"CAGR%",           vals:symList.map(s=>getS(s)?.cagr_pct),             hi:true,  cf:col},
          {metric:"Ann Volatility%", vals:symList.map(s=>getS(s)?.ann_volatility_pct),   hi:false},
          {metric:"Max Drawdown%",   vals:symList.map(s=>getS(s)?.max_drawdown_pct),     hi:false},
          {metric:"Sharpe",          vals:symList.map(s=>getS(s)?.sharpe_ratio),         hi:true},
          {metric:"Sortino",         vals:symList.map(s=>getS(s)?.sortino_ratio),        hi:true},
          {metric:"Calmar",          vals:symList.map(s=>getS(s)?.calmar_ratio),         hi:true},
          {metric:"N Trading Days",  vals:symList.map(s=>getS(s)?.n_trading_days),       hi:true},
        ]} />

        <CTable title="Rolling Window Returns" syms={symList} rows={[
          {metric:"5d Mean%",        vals:symList.map(s=>getW(s,5)?.mean_return),        hi:true, cf:col},
          {metric:"5d Prob+",        vals:symList.map(s=>getW(s,5)?.prob_positive),      hi:true},
          {metric:"10d Mean%",       vals:symList.map(s=>getW(s,10)?.mean_return),       hi:true, cf:col},
          {metric:"10d Prob+",       vals:symList.map(s=>getW(s,10)?.prob_positive),     hi:true},
          {metric:"20d Mean%",       vals:symList.map(s=>getW(s,20)?.mean_return),       hi:true, cf:col},
          {metric:"20d Prob+",       vals:symList.map(s=>getW(s,20)?.prob_positive),     hi:true},
          {metric:"20d P5 Floor%",   vals:symList.map(s=>getW(s,20)?.p5),               hi:true},
          {metric:"20d Sharpe",      vals:symList.map(s=>getW(s,20)?.sharpe_ratio),      hi:true},
          {metric:"60d Mean%",       vals:symList.map(s=>getW(s,60)?.mean_return),       hi:true, cf:col},
          {metric:"60d Prob+",       vals:symList.map(s=>getW(s,60)?.prob_positive),     hi:true},
        ]} />

        <CTable title="Current Technicals" syms={symList} rows={[
          {metric:"Latest Price",  vals:symList.map(s=>getP(s)?.close?.toLocaleString("en-IN",{maximumFractionDigits:2})||"--")},
          {metric:"Price Date",    vals:symList.map(s=>getP(s)?.date||"--")},
          {metric:"RSI 14",        vals:symList.map(s=>getT(s)?.rsi_14)},
          {metric:"ADX 14",        vals:symList.map(s=>getT(s)?.adx_14),          hi:true},
          {metric:"Vs SMA20%",     vals:symList.map(s=>getT(s)?.pct_above_sma20), hi:true, cf:col},
          {metric:"Vol Surge 20d", vals:symList.map(s=>getT(s)?.vol_surge_20d)},
          {metric:"ATR 14%",       vals:symList.map(s=>getT(s)?.atr_14_pct)},
          {metric:"MACD Signal",   vals:symList.map(s=>{const t=getT(s);return t?(t.macd_line>t.macd_signal?"BULL":"BEAR"):null;})},
          {metric:"BB%",           vals:symList.map(s=>getT(s)?.bb_pct)},
        ]} />

        <CTable title="Screener History (30d)" syms={symList} rows={[
          {metric:"Screen Days",   vals:symList.map(s=>getSig(s)?.days_seen),   hi:true},
          {metric:"Avg Score",     vals:symList.map(s=>getSig(s)?.avg_score),   hi:true},
          {metric:"Last Seen",     vals:symList.map(s=>getSig(s)?.last_seen||"--")},
        ]} />

        {data.cross_correlations.length>0 && <Card title="Cross Correlations (20d)">
          <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
            {data.cross_correlations.map(c=><div key={`${c.symbol_a}-${c.symbol_b}`} style={{background:`${C.border}22`,borderRadius:6,padding:"8px 12px",fontSize:12}}>
              <span style={{color:C.cyan,fontWeight:700}}>{c.symbol_a}</span>
              <span style={{color:C.dim}}> x </span>
              <span style={{color:C.cyan,fontWeight:700}}>{c.symbol_b}</span>
              <span style={{color:C.dim}}> = </span>
              <span style={{color:col(c.correlation_20d),fontWeight:700}}>{num(c.correlation_20d)}</span>
              <span style={{color:C.dim}}> (beta {num(c.beta_20d,2)})</span>
            </div>)}
          </div>
        </Card>}
      </>)}
    </div>
  );
}
""")


# =============================================================================
# ALSO write /eta page (needed for NavBar link)
# =============================================================================
if not (APP / "eta" / "page.tsx").exists():
    print("\n[+] Writing /eta/page.tsx...")
    write(APP / "eta" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import MarkdownText from "@/components/MarkdownText";

interface EtaReport {
  agent:string; date:string; timestamp:string;
  screen1_results_season:{symbol:string;announcement_date:string;subject:string}[];
  screen2_dividends:{symbol:string;announcement_date:string;subject:string}[];
  screen3_insider_clusters:{symbol:string;n_buys:number;total_value_cr:number;names:string}[];
  screen4_big_trades:{symbol:string;filing_date:string;name:string;transaction_type:string;quantity:number;price:number;value:number}[];
  screen5_post_results_reaction:{symbol:string;announcement_date:string;price_before:number;price_after:number;reaction_pct:number}[];
  screen6_upcoming_results:{symbol:string;last_results_date:string;expected_due:string}[];
  llm_analysis:string;
}

const C = {green:"var(--accent-green)",red:"var(--accent-red)",cyan:"var(--accent-cyan)",yellow:"var(--accent-yellow)",dim:"var(--text-tertiary)",primary:"var(--text-primary)",border:"var(--border-color)",surface:"var(--surface-card)"};
const pct=(v:unknown)=>v==null?"--":`${(+v)>=0?"+":""}${(+v).toFixed(2)}%`;
const num=(v:unknown,d=2)=>v==null?"--":(+v).toFixed(d);
const col=(v:unknown)=>(+v??0)>=0?C.green:C.red;

function Card({title,count,children,accent}:{title:string;count?:number;children:React.ReactNode;accent?:string}){
  return <div style={{background:C.surface,border:`1px solid ${accent||C.border}`,borderRadius:8,padding:"16px 20px",marginBottom:18}}>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:12,borderBottom:`1px solid ${C.border}`,paddingBottom:8}}>
      <span style={{fontSize:11,fontWeight:700,letterSpacing:1.5,color:accent||C.cyan,textTransform:"uppercase"}}>{title}</span>
      {count!==undefined&&<span style={{fontSize:11,color:C.dim}}>{count} items</span>}
    </div>
    {children}
  </div>;
}

export default function EtaPage() {
  const router = useRouter();
  const [rpt, setRpt] = useState<EtaReport|null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string|null>(null);

  const load = useCallback(async()=>{
    setLoading(true); setError(null);
    try {
      const r = await fetch("/api/eta",{cache:"no-store"});
      const d = await r.json();
      if (!d.ok) throw new Error(d.error||"API error");
      setRpt(d.report);
    } catch(e:unknown) { setError(String(e)); }
    finally { setLoading(false); }
  },[]);
  useEffect(()=>{ load(); },[load]);

  if (loading) return <div style={{padding:40,color:C.dim,textAlign:"center"}}>Loading Eta...</div>;
  if (error) return <div style={{padding:40,color:C.red}}>{error}<br /><code style={{fontSize:12}}>Run: py D:\MICC\agent_eta.py</code></div>;
  if (!rpt)  return <div style={{padding:40,color:C.yellow}}>No Eta report. Run: <code>py D:\MICC\agent_eta.py</code></div>;

  const Row=({sym,date,text,color}:{sym:string;date?:string;text:string;color:string})=>(
    <div style={{display:"flex",gap:12,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
      <span style={{color,fontWeight:700,minWidth:110,cursor:"pointer"}} onClick={()=>router.push(`/deep/${sym}`)}>{sym}</span>
      {date&&<span style={{color:C.dim,minWidth:90}}>{date}</span>}
      <span style={{color:C.primary}}>{text}</span>
    </div>
  );

  return (
    <div style={{maxWidth:1050,margin:"0 auto",padding:"24px 16px"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:24}}>
        <div>
          <h1 style={{margin:0,fontSize:22,fontWeight:800}}>CORPORATE EVENTS</h1>
          <div style={{color:C.dim,fontSize:12,marginTop:4}}>Agent Eta &bull; {rpt.date} &bull; {rpt.timestamp?.split("T")[1]?.slice(0,8)||""}</div>
        </div>
        <button onClick={load} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Refresh</button>
      </div>

      <Card title="Results Season" count={rpt.screen1_results_season?.length} accent={C.cyan}>
        {rpt.screen1_results_season?.slice(0,20).map((r,i)=><Row key={i} sym={r.symbol} date={r.announcement_date} text={r.subject} color={C.cyan} />)}
        {!rpt.screen1_results_season?.length&&<div style={{color:C.dim,fontSize:12}}>No results in lookback period</div>}
      </Card>

      <Card title="Dividends / Bonus / Splits" count={rpt.screen2_dividends?.length} accent={C.green}>
        {rpt.screen2_dividends?.slice(0,20).map((r,i)=><Row key={i} sym={r.symbol} date={r.announcement_date} text={r.subject} color={C.green} />)}
        {!rpt.screen2_dividends?.length&&<div style={{color:C.dim,fontSize:12}}>No dividend/bonus/split events</div>}
      </Card>

      <Card title="Insider Cluster Buying (3+ insiders same stock)" count={rpt.screen3_insider_clusters?.length} accent={C.yellow}>
        {rpt.screen3_insider_clusters?.map((r,i)=><div key={i} style={{padding:"8px 0",borderBottom:`1px solid ${C.border}22`}}>
          <div style={{display:"flex",gap:16,alignItems:"baseline"}}>
            <span style={{color:C.yellow,fontWeight:800,fontSize:14,cursor:"pointer"}} onClick={()=>router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
            <span style={{color:C.green,fontSize:12}}>{r.n_buys} insiders</span>
            <span style={{color:C.cyan,fontSize:12}}>Rs {num(r.total_value_cr,1)} Cr</span>
          </div>
          <div style={{color:C.dim,fontSize:11,marginTop:3}}>{r.names}</div>
        </div>)}
        {!rpt.screen3_insider_clusters?.length&&<div style={{color:C.dim,fontSize:12}}>No insider clusters found</div>}
      </Card>

      <Card title="Big Insider Trades (above 1 Cr)" count={rpt.screen4_big_trades?.length} accent={C.yellow}>
        <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead><tr>{["Symbol","Date","Name","Type","Qty","Price","Value Cr"].map(h=><th key={h} style={{padding:"4px 8px",color:C.dim,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
          <tbody>{rpt.screen4_big_trades?.slice(0,20).map((t,i)=><tr key={i} style={{borderBottom:`1px solid ${C.border}22`}}>
            <td style={{padding:"4px 8px",color:C.cyan,fontWeight:700,cursor:"pointer"}} onClick={()=>router.push(`/deep/${t.symbol}`)}>{t.symbol}</td>
            <td style={{padding:"4px 8px",color:C.dim,textAlign:"right"}}>{t.filing_date}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{t.name}</td>
            <td style={{padding:"4px 8px",fontWeight:700,textAlign:"right",color:t.transaction_type==="BUY"?C.green:C.red}}>{t.transaction_type}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{t.quantity?.toLocaleString("en-IN")}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{num(t.price,1)}</td>
            <td style={{padding:"4px 8px",textAlign:"right",color:C.cyan}}>{t.value?(t.value/1e7).toFixed(2):"--"}</td>
          </tr>)}</tbody>
        </table></div>
        {!rpt.screen4_big_trades?.length&&<div style={{color:C.dim,fontSize:12}}>No big insider trades</div>}
      </Card>

      <Card title="Post-Results Price Reaction" count={rpt.screen5_post_results_reaction?.length} accent={C.cyan}>
        {rpt.screen5_post_results_reaction?.slice(0,15).map((r,i)=><div key={i} style={{display:"flex",gap:12,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
          <span style={{color:C.cyan,fontWeight:700,minWidth:110,cursor:"pointer"}} onClick={()=>router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
          <span style={{color:C.dim,minWidth:90}}>{r.announcement_date}</span>
          <span style={{color:col(r.reaction_pct),fontWeight:700}}>{pct(r.reaction_pct)}</span>
          <span style={{color:C.dim}}>{num(r.price_before,1)} to {num(r.price_after,1)}</span>
        </div>)}
        {!rpt.screen5_post_results_reaction?.length&&<div style={{color:C.dim,fontSize:12}}>No post-results reactions found</div>}
      </Card>

      <Card title="Upcoming Results Calendar" count={rpt.screen6_upcoming_results?.length} accent={C.green}>
        {rpt.screen6_upcoming_results?.slice(0,20).map((r,i)=><div key={i} style={{display:"flex",gap:12,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
          <span style={{color:C.green,fontWeight:700,minWidth:110,cursor:"pointer"}} onClick={()=>router.push(`/deep/${r.symbol}`)}>{r.symbol}</span>
          <span style={{color:C.dim,minWidth:110}}>Last: {r.last_results_date}</span>
          <span style={{color:C.yellow}}>Due: {r.expected_due}</span>
        </div>)}
        {!rpt.screen6_upcoming_results?.length&&<div style={{color:C.dim,fontSize:12}}>No upcoming results predicted</div>}
      </Card>

      {rpt.llm_analysis&&<Card title="Eta Intelligence Synthesis" accent={C.cyan}><MarkdownText text={rpt.llm_analysis} /></Card>}
    </div>
  );
}
""")


# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 60)
print("FIX COMPLETE")
print("=" * 60)
print("""
Pages written:
  /watchlist        -- FIXED (was 404)
  /deep             -- NEW (Iota room, 6 screens)
  /deep/[symbol]    -- NEW (Kappa per-symbol deep dive)
  /compare          -- NEW (Lambda multi-symbol compare)
  /eta              -- NEW (corporate events)

API routes:
  /api/deep         -- Iota last_report.json + DB
  /api/deep/[symbol]-- Kappa report + live DB
  /api/compare      -- multi-symbol comparison
  /api/eta          -- Eta last_report.json

NavBar:
  Rewritten with ALL 11 links including WATCHLIST/BACKTEST/ETA/DEEP/COMPARE

Restart Next.js:
  cd D:\\MICC\\micc-dashboard && npm run dev

Then open:
  localhost:3000/watchlist                -- watchlist (now fixed)
  localhost:3000/deep                     -- Iota room
  localhost:3000/deep/RELIANCE            -- Kappa profile
  localhost:3000/compare                  -- Lambda compare
  localhost:3000/eta                      -- Eta corporate events

Before visiting /deep, make sure Iota ran:
  py D:\\MICC\\agent_iota.py

Before visiting /eta:
  py D:\\MICC\\agent_eta.py

/deep/[symbol] works without Kappa (pulls live DB).
For full LLM verdict, run: py D:\\MICC\\agent_kappa.py RELIANCE
""")
