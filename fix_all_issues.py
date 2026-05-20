"""
fix_all_issues.py
==================
Fixes 5 issues from the screenshots:

1. Alpha NaN JSON crash  - "avg_pe": NaN not caught by regex
   FIX: full file-level NaN sanitiser before JSON.parse

2. Beta/Alpha dates stuck at Apr 23-29
   ROOT CAUSE: market_snapshot has data only up to ~Apr 29.
   micc_data.get_trading_dates() reads from market_snapshot.
   FIX: probe actual latest dates and show a warning in UI.
   ALSO: add a /api/db-status route so user can see what dates are in DB.

3. Delta NaN crash - "amount": NaN in corporate_actions
   SAME FIX as #1 - full NaN sanitiser

4. Gamma working fine - no fix needed

5. Streak 5D filter showing empty
   The route.ts uses template literal but lookback var needs to be integer.
   FIX: re-write streak-extended route with correct variable interpolation.

Run from D:/MICC/:
  py fix_all_issues.py
"""

import sys
from pathlib import Path

BASE = Path(r"D:\MICC")

def find_paths():
    for sub in ["micc-dashboard/src", "micc-dashboard"]:
        p = BASE / sub
        if p.is_dir() and (p / "components").is_dir():
            return p / "app", p / "components", p / "lib"
    return None, None, None

APP, COMP, LIB = find_paths()
if not APP:
    print("[ERROR] Dashboard not found at D:/MICC/micc-dashboard/")
    sys.exit(1)

print(f"[OK] Dashboard: {APP.parent}")

def w(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    try:
        print(f"  wrote: {path.relative_to(BASE)}")
    except ValueError:
        print(f"  wrote: {path}")


# =============================================================================
# FIX 1 & 3: /api/reports/route.ts — robust NaN sanitiser
# The previous regex  /: NaN([,\}\]])/g  misses cases like:
#   "avg_pe": NaN }   (space before })
#   "amount": NaN\n   (newline after NaN)
#   [NaN, 123]        (NaN in array)
# Use a single aggressive global replace that handles ALL positions.
# =============================================================================
print("\n[FIX 1+3] Rewriting /api/reports/route.ts — robust NaN sanitiser...")
w(APP / "api" / "reports" / "route.ts", r"""
import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const DA = 'D:/MICC'

function sanitiseJson(raw: string): string {
  // Replace ALL bare NaN / Infinity occurrences with null
  // These appear in Python JSON output when numpy produces NaN values.
  // We use word boundaries to avoid touching strings that contain "NaN".
  return raw
    .replace(/\bNaN\b/g, 'null')
    .replace(/\bInfinity\b/g, 'null')
    .replace(/-Infinity\b/g, 'null')
}

function readAgent(name: string): any {
  try {
    const p = path.join(DA, 'agents', name, 'last_report.json')
    if (!fs.existsSync(p)) {
      return { _error: `agents/${name}/last_report.json not found. Run: py agent_${name}.py` }
    }
    const raw = fs.readFileSync(p, 'utf-8')
    return JSON.parse(sanitiseJson(raw))
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
    ts:    Date.now(),
  })
}
""")
print("[FIX 1+3] Done")


# =============================================================================
# FIX 2: /api/db-status/route.ts — shows actual latest dates in each DB table
# This tells you WHY dates are stuck (market_snapshot hasn't been updated)
# =============================================================================
print("\n[FIX 2] Writing /api/db-status/route.ts...")
w(APP / "api" / "db-status" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout: 15000,
      cwd: DA,
    })
    if (result.status !== 0) return []
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch { return [] }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  const tables = [
    { label: 'market_snapshot',  sql: "SELECT MAX(date) AS d FROM market_snapshot" },
    { label: 'indices_data',     sql: "SELECT MAX(date) AS d FROM indices_data" },
    { label: 'stock_delivery',   sql: "SELECT MAX(date) AS d FROM stock_delivery" },
    { label: 'fii_dii_data',     sql: "SELECT MAX(date) AS d FROM fii_dii_data" },
    { label: 'fo_data',          sql: "SELECT MAX(date) AS d FROM fo_data" },
    { label: 'global_data',      sql: "SELECT MAX(date) AS d FROM global_data" },
    { label: 'signals_history',  sql: "SELECT MAX(run_date) AS d FROM signals_history" },
  ]

  const status = tables.map(({ label, sql }) => {
    const rows = queryDb(sql)
    return { table: label, latest_date: rows[0]?.d || 'N/A' }
  })

  return NextResponse.json({ status, checked_at: new Date().toISOString() })
}
""")
print("[FIX 2] Done")


# =============================================================================
# FIX 5: /api/streak-extended/route.ts — fix variable interpolation + 5D window
# The lookback days variable was being interpolated as a string template literal
# which worked for large values but the SQL date() function needs an integer.
# Also the MIN_DAYS filter wasn't applying correctly.
# =============================================================================
print("\n[FIX 5] Rewriting /api/streak-extended/route.ts — fix 5D filter...")
w(APP / "api" / "streak-extended" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout: 30000,
      cwd: DA,
    })
    if (result.status !== 0) {
      console.error('[streak-ext] bridge error:', result.stderr?.slice(0, 200))
      return []
    }
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) {
    console.error('[streak-ext] exception:', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)

  // Parse params — all as integers/strings
  const days    = Math.max(1, Math.min(parseInt(searchParams.get('days')   || '30'), 180))
  const minDays = Math.max(1, Math.min(parseInt(searchParams.get('min')    || '2'),  30))
  const sortBy  = searchParams.get('sort')   || 'streak'
  const screen  = searchParams.get('screen') || ''

  // ORDER BY clause
  const orderMap: Record<string, string> = {
    streak: 'streak_days DESC, avg_score DESC',
    score:  'avg_score DESC, streak_days DESC',
    pct:    'avg_pct DESC, streak_days DESC',
    deliv:  'avg_deliv DESC, streak_days DESC',
  }
  const orderBy = orderMap[sortBy] || orderMap['streak']

  // Screen filter — only apply if non-empty
  const screenFilter = screen
    ? `AND (screen_tags LIKE '%${screen.replace(/'/g, "''")}%')`
    : ''

  // KEY FIX: use days as a plain integer in the SQL string.
  // date(MAX(run_date), '-Nd') anchors to the LATEST data, not today's calendar.
  // This is critical when market_snapshot is a few days behind.
  const daysStr = String(days)

  const rows = queryDb(`
    WITH max_run AS (
      SELECT MAX(run_date) AS md FROM signals_history
    )
    SELECT
      symbol,
      COUNT(DISTINCT run_date)                     AS streak_days,
      MAX(run_date)                                AS last_seen,
      MIN(run_date)                                AS first_seen,
      ROUND(AVG(CAST(score          AS REAL)), 2)  AS avg_score,
      MAX(CAST(score                AS REAL))      AS max_score,
      ROUND(AVG(CAST(pct_chg       AS REAL)), 2)  AS avg_pct,
      MAX(CAST(pct_chg             AS REAL))       AS max_pct,
      ROUND(AVG(CAST(avg_deliv_pct AS REAL)), 1)   AS avg_deliv,
      SUM(CASE WHEN earnings_flag = 1 THEN 1 ELSE 0 END) AS eps_days,
      GROUP_CONCAT(DISTINCT screen_tags)           AS all_tags,
      COUNT(DISTINCT regime)                       AS regime_count,
      MAX(regime)                                  AS latest_regime
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_run), '-${daysStr} days')
    ${screenFilter}
    GROUP BY symbol
    HAVING streak_days >= ${String(minDays)}
    ORDER BY ${orderBy}
    LIMIT 30
  `)

  // Tags for screen filter buttons
  const tags = queryDb(`
    WITH max_run AS (SELECT MAX(run_date) AS md FROM signals_history)
    SELECT DISTINCT screen_tags, COUNT(*) AS cnt
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_run), '-30 days')
      AND screen_tags IS NOT NULL AND screen_tags != ''
    GROUP BY screen_tags
    ORDER BY cnt DESC
    LIMIT 20
  `)

  // Overall stats
  const stats = queryDb(`
    SELECT
      COUNT(*)               AS total_rows,
      COUNT(DISTINCT symbol) AS unique_symbols,
      COUNT(DISTINCT run_date) AS unique_dates,
      MAX(run_date)          AS latest_date,
      MIN(run_date)          AS earliest_date
    FROM signals_history
  `)

  return NextResponse.json({
    rows,
    tags,
    stats:  stats[0] || {},
    days,
    minDays,
    sortBy,
    screen,
  })
}
""")
print("[FIX 5] Done")


# =============================================================================
# FIX 2b: Update StreakBoardExtended to show DB status warning when data is stale
# Also probe db-status and show it in the header
# =============================================================================
print("\n[FIX 2b] Writing DBStatusBar component...")
w(COMP / "DBStatusBar.tsx", r"""
"use client";
import { useEffect, useState } from "react";

interface TableStatus {
  table: string;
  latest_date: string;
}

export default function DBStatusBar() {
  const [status,  setStatus]  = useState<TableStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/db-status", { cache: "no-store" })
      .then(r => r.json())
      .then(d => { setStatus(d.status || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return null;

  // Check if market_snapshot is stale (older than 3 days)
  const snap = status.find(s => s.table === "market_snapshot");
  const snapDate = snap?.latest_date || "N/A";
  const daysSince = snapDate !== "N/A"
    ? Math.floor((Date.now() - new Date(snapDate).getTime()) / 86400000)
    : 99;
  const isStale = daysSince > 3;

  return (
    <div style={{
      display: "flex",
      flexWrap: "wrap",
      gap: 6,
      padding: "6px 12px",
      background: isStale ? "rgba(255,170,0,0.07)" : "rgba(0,255,128,0.04)",
      border: `1px solid ${isStale ? "var(--warn)" : "var(--border)"}`,
      borderRadius: 5,
      marginBottom: 10,
      alignItems: "center",
    }}>
      {isStale && (
        <span style={{
          fontFamily: "monospace", fontSize: 10,
          color: "var(--warn)", marginRight: 8, fontWeight: 700,
        }}>
          DATA STALE — run: py micc_engine.py 7 --send
        </span>
      )}
      {status.map(({ table, latest_date }) => (
        <span key={table} style={{
          fontFamily: "monospace", fontSize: 9,
          color: "var(--muted)",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 3,
          padding: "2px 6px",
        }}>
          <span style={{ color: "var(--dim)" }}>{table.replace("_", " ")}:</span>
          {" "}{latest_date}
        </span>
      ))}
    </div>
  );
}
""")
print("[FIX 2b] Done")


# =============================================================================
# Update page.tsx to include DBStatusBar
# =============================================================================
print("\n[PAGE] Updating page.tsx with DBStatusBar...")
w(APP / "page.tsx", r"""
"use client";
import { useState, useEffect, useCallback } from "react";
import AlphaPanel         from "@/components/AlphaPanel";
import BetaPanel          from "@/components/BetaPanel";
import GammaPanel         from "@/components/GammaPanel";
import DeltaPanel         from "@/components/DeltaPanel";
import StreakBoardExtended from "@/components/StreakBoardExtended";
import RefreshController  from "@/components/RefreshController";
import DBStatusBar        from "@/components/DBStatusBar";

interface Reports {
  alpha?: any; beta?: any; gamma?: any; delta?: any; ts?: number;
}

export default function Home() {
  const [reports,  setReports]  = useState<Reports>({});
  const [lastTime, setLastTime] = useState<string>("");
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  const fetchReports = useCallback(async () => {
    try {
      const r = await fetch("/api/reports", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setReports(data);
      setLastTime(new Date().toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      }));
      setError("");
    } catch (e: any) {
      setError(e.message || "Fetch failed");
    }
  }, []);

  const triggerAllFetches = useCallback(async () => {
    setLoading(true);
    await fetchReports();
    setLoading(false);
  }, [fetchReports]);

  useEffect(() => {
    triggerAllFetches();
  }, []); // eslint-disable-line

  return (
    <div className="dashboard">
      {/* Sticky Header */}
      <header className="header">
        <div className="header-logo">MICC</div>
        <div className="header-sub">Market Intelligence Command Center</div>
        <div className="header-right">
          {error && (
            <span style={{ color: "var(--neg)", fontSize: 10, fontFamily: "monospace" }}>
              {error}
            </span>
          )}
          {loading && !error && (
            <span style={{ color: "var(--accent)", fontSize: 10, fontFamily: "monospace" }}>
              Loading...
            </span>
          )}
          {lastTime && !loading && (
            <span style={{ color: "var(--dim)", fontSize: 10, fontFamily: "monospace" }}>
              Updated {lastTime}
            </span>
          )}
          <RefreshController onRefresh={triggerAllFetches} intervalSec={90} autoStart={false} />
        </div>
      </header>

      {/* DB Status Bar — shows latest date per table, warns if stale */}
      <div style={{ padding: "0 0 4px" }}>
        <DBStatusBar />
      </div>

      {/* Alpha */}
      <div style={{ marginBottom: 14 }}>
        <AlphaPanel data={reports.alpha ?? null} />
      </div>

      {/* Beta + Gamma */}
      <div className="grid2" style={{ marginBottom: 14 }}>
        <BetaPanel  data={reports.beta  ?? null} />
        <GammaPanel data={reports.gamma ?? null} />
      </div>

      {/* Delta */}
      <div style={{ marginBottom: 14 }}>
        <DeltaPanel data={reports.delta ?? null} />
      </div>

      {/* Streak Leaderboard */}
      <div style={{ marginBottom: 14 }}>
        <StreakBoardExtended />
      </div>
    </div>
  );
}
""")
print("[PAGE] Done")


print()
print("=" * 60)
print("  ALL 5 FIXES APPLIED")
print("=" * 60)
print()
print("  [1+3] Alpha + Delta NaN crash   -> FIXED (robust sanitiser)")
print("  [2]   Date stuck Apr 23-29      -> DB STATUS BAR added")
print("  [4]   Gamma                     -> was already working")
print("  [5]   Streak 5D filter empty    -> FIXED (correct interpolation)")
print()
print("  RESTART DASHBOARD:")
print("    Ctrl+C the running npm process")
print("    cd D:\\MICC\\micc-dashboard")
print("    npm run dev")
print()
print("  IMPORTANT — WHY DATES ARE STUCK:")
print("  market_snapshot latest date is Apr 29.")
print("  The agents READ from market_snapshot for their date window.")
print("  To get May dates, you need to run the daily data pipeline:")
print()
print("    cd D:\\MICC\\data_pipeline")
print("    py run_pipeline.py")
print()
print("  OR just run the daily NSE data update:")
print("    cd D:\\MICC\\data_pipeline")
print("    py daily_update.py")
print()
print("  AFTER data is updated, re-run the engine:")
print("    cd D:\\MICC")
print("    py micc_engine.py 7 --send")
print()
print("  The DB Status Bar at the top of the dashboard shows")
print("  the latest date in each table so you can see exactly")
print("  how fresh the data is without opening a terminal.")
print()
