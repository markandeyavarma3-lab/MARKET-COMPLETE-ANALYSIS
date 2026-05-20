"""
MICC Dashboard - Comprehensive Data Fix
Run from DATA-ANALYSIS:  py patch_v2.py

Fixes ALL data mapping issues found by probing agent source code:
1. AlphaPanel: regime.latest_close/window_pct, breadth.by_day[-1], cap_rotation.largecap_avg_pct
   global_context.tickers.{DXY/Gold/etc}.{close,pct_chg}, top10_gainers[].pct_change
2. Streak leaderboard: uses COUNT(DISTINCT run_date) as days - no "streak" column in DB
3. LLM analysis: bigger box (400px), scrollable
4. Beta: shows 1698 because parquet filter excludes ETFs + requires 2 days data - that is correct
5. route.ts: fixes regex escape in NaN replace
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))

def find_paths():
    for sub in ["micc-dashboard/src", "micc-dashboard"]:
        p = os.path.join(BASE, sub)
        if os.path.isdir(p):
            # Check for src structure
            if os.path.isdir(os.path.join(p, "components")):
                return (
                    os.path.join(p, "app"),
                    os.path.join(p, "components"),
                    os.path.join(p, "lib"),
                )
    return None

paths = find_paths()
if not paths:
    print("[ERROR] micc-dashboard not found. Run: py build_dashboard.py")
    sys.exit(1)

APP, COMP, LIB = paths
print(f"[INFO] Patching: {APP}")

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.lstrip("\n"))
    print(f"  wrote: {os.path.relpath(path, BASE)}")

# ── Fix API route - NaN replace regex was broken ─────────────────────────────
w(os.path.join(APP, "api", "reports", "route.ts"), """
import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const DA = 'D:/MICC'

function readAgent(name: string) {
  try {
    const p = path.join(DA, 'agents', name, 'last_report.json')
    if (!fs.existsSync(p)) {
      return { _error: `agents/${name}/last_report.json not found. Run: py micc_engine.py` }
    }
    let raw = fs.readFileSync(p, 'utf-8')
    // Fix bare NaN/Infinity before JSON.parse
    raw = raw.replace(/: NaN/g, ': null')
    raw = raw.replace(/: Infinity/g, ': null')
    raw = raw.replace(/: -Infinity/g, ': null')
    raw = raw.replace(/NaN,/g, 'null,')
    raw = raw.replace(/NaN}/g, 'null}')
    raw = raw.replace(/NaN]/g, 'null]')
    return JSON.parse(raw)
  } catch (e: any) {
    return { _error: `${name}: ${e.message}` }
  }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  return NextResponse.json({
    alpha: readAgent('alpha'),
    beta:  readAgent('beta'),
    gamma: readAgent('gamma'),
    delta: readAgent('delta'),
    ts: Date.now(),
  })
}
""")

# ── Fix streak API - signals_history has no "streak" col, use COUNT(run_date) ─
w(os.path.join(APP, "api", "streak", "route.ts"), """
import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string) {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout: 20000,
      cwd: DA,
    })
    if (result.status !== 0) throw new Error(result.stderr || 'bridge error')
    const out = result.stdout.trim()
    if (!out) return []
    return JSON.parse(out)
  } catch (e: any) {
    console.error('[streak api]', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // signals_history columns: id, run_date, symbol, score, screen_tags, pct_chg, avg_deliv_pct, earnings_flag, regime
  // NO standalone "streak" column - streak = COUNT(DISTINCT run_date) per symbol in last 30 days
  const streak = queryDb(`
    SELECT
      symbol,
      COUNT(DISTINCT run_date)    AS streak_days,
      MAX(run_date)               AS last_seen,
      ROUND(AVG(CAST(score AS REAL)), 2) AS avg_score,
      MAX(run_date)               AS max_date,
      MIN(run_date)               AS min_date,
      GROUP_CONCAT(DISTINCT screen_tags) AS all_tags
    FROM signals_history
    WHERE run_date >= date('now', '-30 days')
    GROUP BY symbol
    HAVING COUNT(DISTINCT run_date) >= 2
    ORDER BY streak_days DESC, avg_score DESC
    LIMIT 15
  `)

  const stats = queryDb(`
    SELECT
      COUNT(*)                    AS total_rows,
      COUNT(DISTINCT symbol)      AS unique_symbols,
      COUNT(DISTINCT run_date)    AS unique_dates,
      MAX(run_date)               AS latest_date
    FROM signals_history
  `)

  return NextResponse.json({ streak, stats: stats[0] || {} })
}
""")

print("[1/3] API routes fixed")

# ── Fix AlphaPanel with exact key mapping from agent_alpha.py source ──────────
# regime dict keys: latest_close, return_1d_pct, window_pct, vol_ann_pct, pe, pb,
#                   volume_ratio, regime, confidence, above_ma20, above_ma50
# breadth dict keys: by_day (list of {date,advancing,declining,unchanged,total,pct_adv,ad_ratio})
#                    avg_pct_adv, total_days
# cap_rotation keys: largecap_avg_pct, midcap_avg_pct, smallcap_avg_pct, signal
# global_context keys: tickers (dict of {DXY,Crude Oil,Gold,S&P 500,USD/INR} -> {close,pct_chg})
#                      summary, available
# top10_gainers/losers: [{index, pct_change, ...}]
# regime_analysis: string (raw LLM output)
# end_date: "YYYY-MM-DD"

w(os.path.join(COMP, "AlphaPanel.tsx"), """
import { fmtNum, fmtPct, colorPct, regimeCls } from "@/lib/utils";

export default function AlphaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header"><span className="card-title">Alpha -- Macro and Regime</span></div>
      <div style={{ color: "var(--neg)", fontFamily: "monospace", fontSize: 12, padding: 8 }}>
        {data?._error || "No alpha report. Run: py micc_engine.py"}
      </div>
    </div>
  );

  // ── Exact keys from agent_alpha.py ──────────────────────────────────────────
  const reg  = data.regime || {};           // { latest_close, window_pct, vol_ann_pct, pe, pb, regime, confidence, above_ma20, return_1d_pct }
  const brd  = data.breadth || {};          // { by_day: [{advancing, declining, total, ad_ratio}], avg_pct_adv }
  const rot  = data.cap_rotation || {};     // { largecap_avg_pct, midcap_avg_pct, smallcap_avg_pct, signal }
  const gctx = data.global_context || {};   // { tickers: { "DXY": {close, pct_chg}, ... }, summary }
  const date = data.end_date || (data.timestamp || "").slice(0, 10) || "--";
  const regime = reg.regime || "";
  const rcls = regimeCls(regime);

  // Breadth: last day in by_day array
  const byDay  = brd.by_day || [];
  const lastBd = byDay.length > 0 ? byDay[byDay.length - 1] : {};
  const adv    = lastBd.advancing ?? "--";
  const dec    = lastBd.declining ?? "--";
  const tot    = lastBd.total ?? "--";
  const adR    = lastBd.ad_ratio;
  const unch   = lastBd.unchanged ?? 0;

  // Global tickers: { "DXY": {close, pct_chg}, "Crude Oil": {...}, "Gold": {...}, ... }
  const tickers = gctx.tickers || {};
  const tickerNames = ["DXY", "Crude Oil", "Gold", "S&P 500", "USD/INR", "Nasdaq"];
  const tickerItems = tickerNames.filter(k => tickers[k] != null).map(k => [k, tickers[k]]);
  // Also grab any extra tickers not in the above list
  Object.entries(tickers).forEach(([k]) => {
    if (!tickerNames.includes(k)) tickerItems.push([k, tickers[k]]);
  });

  // LLM text - regime_analysis is a raw string from LLM
  const llmText = typeof data.regime_analysis === "string"
    ? data.regime_analysis
    : (data.regime_analysis?.analysis || "");

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Alpha <span className="card-accent">-- Macro and Regime</span></span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)" }}>{date}</span>
          {regime && <span className={"pill " + rcls} style={{ fontSize: 11 }}>{regime}</span>}
          {reg.confidence && <span className="pill pill-neut" style={{ fontSize: 9 }}>{reg.confidence}</span>}
        </div>
      </div>

      {/* KPI Row */}
      <div className="kpi-grid">
        <div className="kpi">
          <div className="kpi-label">Nifty 50</div>
          <div className="kpi-value" style={{ fontSize: 20 }}>{fmtNum(reg.latest_close, 2)}</div>
          <div className="kpi-sub" style={{ color: colorPct(reg.window_pct) }}>
            {fmtPct(reg.window_pct)} window | {fmtPct(reg.return_1d_pct)} 1d
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Volatility (Ann.)</div>
          <div className="kpi-value" style={{
            color: (Number(reg.vol_ann_pct) || 0) > 20 ? "var(--neg)"
                 : (Number(reg.vol_ann_pct) || 0) < 12 ? "var(--pos)" : "var(--warn)"
          }}>
            {fmtNum(reg.vol_ann_pct, 1)}%
          </div>
          <div className="kpi-sub">Vol ratio: {fmtNum(reg.volume_ratio, 2)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">MA Positioning</div>
          <div className="kpi-value" style={{ fontSize: 13, color: reg.above_ma20 ? "var(--pos)" : "var(--neg)" }}>
            {reg.above_ma20 ? "Above MA20" : "Below MA20"}
          </div>
          <div className="kpi-sub" style={{ color: reg.above_ma50 ? "var(--pos)" : "var(--neg)" }}>
            {reg.above_ma50 ? "Above MA50" : "Below MA50"}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Nifty PE / PB</div>
          <div className="kpi-value" style={{ color: (Number(reg.pe) || 0) > 25 ? "var(--warn)" : "var(--text)" }}>
            {fmtNum(reg.pe, 1)}
          </div>
          <div className="kpi-sub">PB: {fmtNum(reg.pb, 2)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Advances (Today)</div>
          <div className="kpi-value" style={{ color: "var(--pos)" }}>{adv}</div>
          <div className="kpi-sub">of {tot} | Unch: {unch}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Declines</div>
          <div className="kpi-value" style={{ color: "var(--neg)" }}>{dec}</div>
          <div className="kpi-sub">A/D: {adR ? Number(adR).toFixed(2) : "--"}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Breadth (Avg)</div>
          <div className="kpi-value" style={{ color: (Number(brd.avg_pct_adv) || 0) > 55 ? "var(--pos)" : "var(--warn)" }}>
            {fmtNum(brd.avg_pct_adv, 1)}%
          </div>
          <div className="kpi-sub">advancing {brd.total_days}d avg</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Largecap</div>
          <div className="kpi-value" style={{ color: colorPct(rot.largecap_avg_pct) }}>
            {fmtPct(rot.largecap_avg_pct)}
          </div>
          <div className="kpi-sub" style={{ color: colorPct(rot.midcap_avg_pct) }}>
            Mid: {fmtPct(rot.midcap_avg_pct)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Smallcap</div>
          <div className="kpi-value" style={{ color: colorPct(rot.smallcap_avg_pct) }}>
            {fmtPct(rot.smallcap_avg_pct)}
          </div>
          <div className="kpi-sub">{rot.signal ? rot.signal.split("--")[0].trim() : "--"}</div>
        </div>
      </div>

      {/* Rotation signal banner */}
      {rot.signal && (
        <div style={{
          padding: "7px 12px", marginBottom: 14,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 5,
          fontFamily: "monospace", fontSize: 11,
          color: rot.signal.includes("RISK_ON") ? "var(--pos)"
               : rot.signal.includes("RISK_OFF") ? "var(--warn)" : "var(--muted)",
        }}>
          Rotation Signal: {rot.signal}
        </div>
      )}

      {/* Global Tickers */}
      {tickerItems.length > 0 && (
        <>
          <div className="section-label">Global Context</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
            {tickerItems.slice(0, 8).map(([k, v]: any) => {
              const close  = typeof v === "object" ? (v?.close ?? v?.value ?? "--") : v;
              const pct    = typeof v === "object" ? (v?.pct_chg ?? null) : null;
              return (
                <div key={k} style={{
                  background: "var(--surface)", border: "1px solid var(--border)",
                  borderRadius: 5, padding: "6px 12px", minWidth: 95,
                }}>
                  <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)", textTransform: "uppercase", marginBottom: 3 }}>{k}</div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{close}</div>
                  {pct != null && (
                    <div style={{ fontFamily: "monospace", fontSize: 10, color: colorPct(pct) }}>{fmtPct(pct)}</div>
                  )}
                </div>
              );
            })}
          </div>
          {gctx.summary && (
            <div style={{
              padding: "7px 12px", marginBottom: 14,
              background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 5,
              fontFamily: "monospace", fontSize: 11, color: "var(--muted)",
            }}>
              {gctx.summary}
            </div>
          )}
        </>
      )}

      {/* Top / Bottom Movers - pct_change key (not pct_chg) */}
      {(data.top10_gainers?.length > 0 || data.top10_losers?.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <div>
            <div className="section-label">Top Indices (Window)</div>
            {(data.top10_gainers || []).slice(0, 7).map((r: any, i: number) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
                <span style={{ fontSize: 11 }}>{(r.index || r.name || "--").slice(0, 26)}</span>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--pos)" }}>
                  {r.pct_change != null ? "+" + Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
          <div>
            <div className="section-label">Bottom Indices (Window)</div>
            {(data.top10_losers || []).slice(0, 7).map((r: any, i: number) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
                <span style={{ fontSize: 11 }}>{(r.index || r.name || "--").slice(0, 26)}</span>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--neg)" }}>
                  {r.pct_change != null ? Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* LLM Analysis - full height, scrollable */}
      {llmText && (
        <>
          <div className="section-label">LLM Regime Analysis</div>
          <AnalysisBox text={llmText} />
        </>
      )}
    </div>
  );
}

function AnalysisBox({ text }: { text: string }) {
  return (
    <div style={{
      fontSize: 12,
      lineHeight: 1.8,
      color: "var(--text)",
      padding: "14px 16px",
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 6,
      whiteSpace: "pre-wrap",
      maxHeight: 420,
      overflowY: "auto",
      fontFamily: "'Space Grotesk', sans-serif",
    }}>
      {text}
    </div>
  );
}
""")

# ── Fix StreakBoard with correct column names ─────────────────────────────────
w(os.path.join(COMP, "StreakBoard.tsx"), """
export default function StreakBoard({ data }: { data: any }) {
  const rows  = data?.streak || [];
  const stats = data?.stats  || {};
  const maxS  = Math.max(...rows.map((r: any) => Number(r.streak_days) || 0), 1);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Streak Leaderboard <span className="card-accent">-- signals_history (30d)</span>
        </span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {(Number(stats.total_rows) || 0).toLocaleString()} rows
          </span>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {stats.unique_symbols || 0} symbols
          </span>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {stats.unique_dates || 0} dates
          </span>
          {stats.latest_date && (
            <span className="pill pill-neut" style={{ fontSize: 9 }}>
              latest: {stats.latest_date}
            </span>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: 12, padding: 16 }}>
          No streak data found in last 30 days. Run py micc_engine.py to populate signals_history.
          <br />
          <span style={{ fontSize: 11, marginTop: 6, display: "block" }}>
            DB has {(Number(stats.total_rows) || 0).toLocaleString()} total rows
            across {stats.unique_dates || 0} dates --
            but none within last 30 days. Run: py backfill_signals_history.py
          </span>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>Appearances (30d)</th>
                <th style={{ minWidth: 160 }}>Consistency Bar</th>
                <th>Avg Score</th>
                <th>Last Seen</th>
                <th>Tags</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any, i: number) => {
                const days   = Number(r.streak_days) || 0;
                const pct    = (days / maxS) * 100;
                const aScore = Number(r.avg_score) || 0;
                const rank   = i === 0 ? "#1" : i === 1 ? "#2" : i === 2 ? "#3" : String(i + 1);
                // Parse tags - GROUP_CONCAT gives comma-separated, may have duplicates
                const rawTags = (r.all_tags || "").toString().split(",")
                  .map((t: string) => t.trim())
                  .filter(Boolean);
                const uniqueTags = [...new Set(rawTags)].slice(0, 4);
                return (
                  <tr key={r.symbol}>
                    <td style={{ color: "var(--muted)", fontWeight: i < 3 ? 700 : 400 }}>{rank}</td>
                    <td style={{ fontWeight: 700, fontSize: 12 }}>{r.symbol}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700, color: "var(--orange)" }}>
                      {days}d
                    </td>
                    <td>
                      <div style={{ height: 6, background: "var(--border2)", borderRadius: 3, overflow: "hidden" }}>
                        <div style={{ width: pct + "%", height: "100%", background: "var(--pos)", borderRadius: 3 }} />
                      </div>
                      <div style={{ fontSize: 9, color: "var(--muted)", marginTop: 2 }}>
                        {Math.round(pct)}% of max
                      </div>
                    </td>
                    <td style={{
                      fontFamily: "monospace",
                      color: aScore >= 7 ? "var(--pos)" : aScore >= 4 ? "var(--accent)" : "var(--muted)"
                    }}>
                      {aScore.toFixed(1)}
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 10 }}>{r.last_seen}</td>
                    <td>
                      <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                        {uniqueTags.map((t: string, j: number) => (
                          <span key={j} style={{
                            background: "var(--accent)",
                            color: "#000",
                            borderRadius: 3,
                            padding: "1px 4px",
                            fontFamily: "monospace",
                            fontSize: 8,
                            fontWeight: 700,
                            opacity: 0.8,
                          }}>
                            {t.toUpperCase().slice(0, 5)}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
""")

# ── Update globals.css - bigger analysis boxes ─────────────────────────────────
css_path = os.path.join(APP, "globals.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    # Update analysis-box max-height
    for old, new in [("max-height: 180px;", "max-height: 420px;"),
                     ("max-height: 280px;", "max-height: 420px;")]:
        if old in css:
            css = css.replace(old, new)
    with open(css_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(css)
    print("  patched: globals.css (analysis box height -> 420px)")

print("[2/3] Components patched")

# ── Verify no ASCII issues in written TSX ────────────────────────────────────
import ast as pyast
try:
    with open(os.path.join(COMP, "AlphaPanel.tsx"), "rb") as f:
        content = f.read()
    non_ascii = [i for i, b in enumerate(content) if b > 127]
    if non_ascii:
        print(f"  [WARN] AlphaPanel.tsx has {len(non_ascii)} non-ASCII bytes at positions: {non_ascii[:5]}")
    else:
        print("  AlphaPanel.tsx: pure ASCII OK")
except Exception as e:
    print(f"  [WARN] could not verify: {e}")

print("""
[3/3] Patch complete!

SUMMARY OF FIXES:
  AlphaPanel  -- correct keys: regime.latest_close, breadth.by_day[-1].advancing,
                 cap_rotation.largecap_avg_pct, global_context.tickers.DXY.close,
                 top10_gainers[].pct_change, end_date
  StreakBoard  -- fixed query: streak_days = COUNT(DISTINCT run_date), no "streak" column
  API route   -- fixed NaN regex replace
  Analysis    -- boxes now 420px tall and scrollable

WHY 1698 SYMBOLS IN BETA (not 2100):
  Beta reads parquet files, skips ETFs, requires price > Rs.10 and >=2 data points.
  1698 is the real tradable EQ universe after filtering junk. This is correct.
  The DB has 2100+ but many are SME/ETF/suspended stocks.

WHY DATE SHOWS 2026-04-29:
  agents/*/last_report.json files are from April 29.
  Run: py micc_engine.py  to regenerate with today's data.
  Scheduler should do this at 9:15AM IST automatically.
""")
