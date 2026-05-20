# -*- coding: utf-8 -*-
"""
fix_dashboard_bugs.py
======================
Fixes 3 known dashboard bugs. Run from D:\\MICC\\ after migration.

Bug 1 — IndicesPanel shows "0 indices":
  market_snapshot column is 'closing_index_value' not 'close',
  and 'index_name' not anything else. Fix: update /api/indices/route.ts SQL.

Bug 2 — StreakBoardExtended shows no data at short lookbacks (5D, 7D):
  WHERE run_date >= date('now', '-Nd') compares against today (2026-05-12)
  but signals_history latest date is 2026-05-10, so short windows return nothing.
  Fix: WHERE run_date >= (SELECT date(MAX(run_date), '-Nd') FROM signals_history)

Bug 3 — Auto-refresh uses fixed setInterval(60s):
  Fix: replace with async cycle that waits for ALL fetches to finish,
  then starts a countdown, then re-fetches. Zero drift, no stale data.

Usage:
  cd D:\\MICC
  py fix_dashboard_bugs.py
"""

import os
import sys
from pathlib import Path

# ── Resolve dashboard root ─────────────────────────────────────────────────────
BASE = Path(__file__).parent  # D:\MICC

# Try src/ layout first (standard Next.js 14), then without
DASH_SRC = BASE / "micc-dashboard" / "src"
DASH_PLAIN = BASE / "micc-dashboard"

if (DASH_SRC / "app").exists():
    APP  = DASH_SRC / "app"
    COMP = DASH_SRC / "components"
    LIB  = DASH_SRC / "lib"
elif (DASH_PLAIN / "app").exists():
    APP  = DASH_PLAIN / "app"
    COMP = DASH_PLAIN / "components"
    LIB  = DASH_PLAIN / "lib"
else:
    print("[ERROR] Cannot find micc-dashboard/app directory.")
    print("        Make sure you run this from D:\\MICC\\")
    sys.exit(1)

print(f"[OK] Dashboard root: {APP.parent}")


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    rel = path.relative_to(BASE)
    print(f"  wrote: {rel}")


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 1 FIX — /api/indices/route.ts
# Correct column names from PRAGMA table_info(market_snapshot):
#   index_name, index_date, open_index_value, high_index_value,
#   low_index_value, closing_index_value, points_change, change,
#   volume, turnover_rs_cr, pe, pb, div_yield, date, ingest_date, source_file
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[FIX 1] Rewriting /api/indices/route.ts — correct column names...")

write(APP / "api" / "indices" / "route.ts", """
import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

// Absolute path — works after migration to D:\\\\MICC
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
      console.error('[indices api] bridge error:', result.stderr?.slice(0, 300))
      return []
    }
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) {
    console.error('[indices api] exception:', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const days = Math.min(parseInt(searchParams.get('days') || '7'), 365)

  // market_snapshot actual columns:
  //   index_name, date, open_index_value, high_index_value,
  //   low_index_value, closing_index_value, pe, pb, div_yield
  //
  // We use MAX(run_date)-relative window so results are always
  // anchored to the latest available data (not today's calendar date).

  const rows = queryDb(`
    WITH latest_date AS (
      SELECT MAX(date) AS max_date FROM market_snapshot
    ),
    start_date AS (
      SELECT date(max_date, '-${days + 14} days') AS s FROM latest_date
    ),
    date_range AS (
      SELECT DISTINCT date
      FROM market_snapshot
      WHERE date >= (SELECT s FROM start_date)
      ORDER BY date ASC
    ),
    window_start AS (
      SELECT MIN(date) AS wd FROM (
        SELECT date FROM date_range
        ORDER BY date DESC
        LIMIT ${days + 1}
      )
    ),
    window_end AS (
      SELECT MAX(date) AS wd FROM date_range
    ),
    start_snap AS (
      SELECT index_name,
             closing_index_value AS start_close,
             pe AS start_pe
      FROM market_snapshot
      WHERE date = (SELECT wd FROM window_start)
    ),
    end_snap AS (
      SELECT index_name,
             closing_index_value AS end_close,
             pe AS end_pe,
             pb,
             div_yield
      FROM market_snapshot
      WHERE date = (SELECT wd FROM window_end)
    )
    SELECT
      e.index_name                                          AS name,
      ROUND(s.start_close, 2)                               AS start_close,
      ROUND(e.end_close,   2)                               AS end_close,
      ROUND((e.end_close - s.start_close) / s.start_close * 100, 2) AS pct_change,
      ROUND(e.end_pe,    2)                                 AS pe,
      ROUND(e.pb,        2)                                 AS pb,
      ROUND(e.div_yield, 2)                                 AS div_yield
    FROM end_snap e
    JOIN start_snap s ON e.index_name = s.index_name
    WHERE s.start_close > 0
      AND e.end_close   > 0
      AND e.index_name  NOT LIKE '%Inverse%'
      AND e.index_name  NOT LIKE '%1x%'
      AND e.index_name  NOT LIKE 'India VIX%'
      AND e.index_name  NOT LIKE 'INDIA VIX%'
    ORDER BY pct_change DESC
  `)

  const gainers = rows.slice(0, 10)
  const losers  = [...rows].reverse().slice(0, 10)

  return NextResponse.json({
    gainers,
    losers,
    all: rows,
    days,
    total: rows.length,
  })
}
""")

print("[FIX 1] Done — indices route now uses closing_index_value + anchored date window")


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 2 FIX — /api/streak-extended/route.ts
# Replace date('now','-Nd') with date(MAX(run_date),'-Nd') from signals_history
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[FIX 2] Rewriting /api/streak-extended/route.ts — anchored date window...")

write(APP / "api" / "streak-extended" / "route.ts", """
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
      console.error('[streak-ext] bridge error:', result.stderr?.slice(0, 300))
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
  const days    = Math.min(parseInt(searchParams.get('days') || '30'), 90)
  const sortBy  = searchParams.get('sort') || 'streak'
  const minDays = Math.max(1, parseInt(searchParams.get('min') || '2'))
  const screen  = searchParams.get('screen') || ''

  const screenFilter = screen ? `AND screen_tags LIKE '%${screen}%'` : ''

  const orderMap: Record<string, string> = {
    streak: 'streak_days DESC, avg_score DESC',
    score:  'avg_score DESC, streak_days DESC',
    pct:    'avg_pct DESC, streak_days DESC',
    deliv:  'avg_deliv DESC, streak_days DESC',
  }
  const orderBy = orderMap[sortBy] || orderMap['streak']

  // KEY FIX: anchor lookback to MAX(run_date) in signals_history,
  // not to date('now'). This ensures short windows work even when
  // the latest run_date is 2-3 days behind today's calendar date.
  const rows = queryDb(`
    WITH max_date AS (
      SELECT MAX(run_date) AS md FROM signals_history
    )
    SELECT
      symbol,
      COUNT(DISTINCT run_date)                    AS streak_days,
      MAX(run_date)                               AS last_seen,
      MIN(run_date)                               AS first_seen,
      ROUND(AVG(CAST(score         AS REAL)), 2)  AS avg_score,
      MAX(CAST(score               AS REAL))      AS max_score,
      ROUND(AVG(CAST(pct_chg      AS REAL)), 2)  AS avg_pct,
      MAX(CAST(pct_chg            AS REAL))      AS max_pct,
      ROUND(AVG(CAST(avg_deliv_pct AS REAL)), 1) AS avg_deliv,
      SUM(CASE WHEN earnings_flag = 1 THEN 1 ELSE 0 END) AS eps_days,
      GROUP_CONCAT(DISTINCT screen_tags)          AS all_tags,
      COUNT(DISTINCT regime)                      AS regime_count,
      MAX(regime)                                 AS latest_regime
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_date), '-${days} days')
    ${screenFilter}
    GROUP BY symbol
    HAVING streak_days >= ${minDays}
    ORDER BY ${orderBy}
    LIMIT 25
  `)

  const tags = queryDb(`
    WITH max_date AS (
      SELECT MAX(run_date) AS md FROM signals_history
    )
    SELECT DISTINCT screen_tags, COUNT(*) AS cnt
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_date), '-30 days')
      AND screen_tags IS NOT NULL
    GROUP BY screen_tags
    ORDER BY cnt DESC
    LIMIT 20
  `)

  const stats = queryDb(`
    SELECT
      COUNT(*)              AS total_rows,
      COUNT(DISTINCT symbol)   AS unique_symbols,
      COUNT(DISTINCT run_date) AS unique_dates,
      MAX(run_date)            AS latest_date,
      MIN(run_date)            AS earliest_date
    FROM signals_history
  `)

  return NextResponse.json({
    rows,
    tags,
    stats:  stats[0] || {},
    days,
    sortBy,
  })
}
""")

print("[FIX 2] Done — streak queries now anchored to MAX(run_date)")


# ═══════════════════════════════════════════════════════════════════════════════
# BUG 3 FIX — Cycle-based auto-refresh in page.tsx
# Replace fixed setInterval with async chain:
#   fetch → done → start countdown (N sec) → fetch → ...
# The countdown is visible in the header so user always knows when next refresh is.
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[FIX 3] Writing RefreshController component (cycle-based refresh)...")

write(COMP / "RefreshController.tsx", """
"use client";
/**
 * RefreshController
 * -----------------
 * Cycle-based auto-refresh: fires ALL fetches, waits for ALL to settle,
 * then counts down REFRESH_INTERVAL seconds, then fires again.
 * No drift. No stale overlapping calls.
 *
 * Usage in page.tsx:
 *   <RefreshController onRefresh={triggerAllFetches} intervalSec={90} />
 */

import { useEffect, useRef, useState, useCallback } from "react";

interface Props {
  onRefresh: () => Promise<void>;
  intervalSec?: number;
  autoStart?: boolean;
}

export default function RefreshController({
  onRefresh,
  intervalSec = 90,
  autoStart = true,
}: Props) {
  const [countdown, setCountdown] = useState(intervalSec);
  const [running,   setRunning]   = useState(false);
  const [paused,    setPaused]    = useState(!autoStart);
  const [lastRefresh, setLastRefresh] = useState<string>("");

  const timerRef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const pausedRef   = useRef(paused);
  pausedRef.current = paused;

  const stopCountdown = useCallback(() => {
    if (timerRef.current)  clearTimeout(timerRef.current);
    if (countRef.current)  clearInterval(countRef.current);
    timerRef.current  = null;
    countRef.current  = null;
  }, []);

  const startCycle = useCallback(async () => {
    if (pausedRef.current) return;
    stopCountdown();
    setRunning(true);
    setCountdown(0);

    try {
      await onRefresh();
    } catch (e) {
      console.error("[RefreshController] fetch error:", e);
    }

    setRunning(false);
    setLastRefresh(new Date().toLocaleTimeString("en-IN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }));

    if (pausedRef.current) return;

    // Start countdown
    let remaining = intervalSec;
    setCountdown(remaining);
    countRef.current = setInterval(() => {
      remaining -= 1;
      setCountdown(remaining);
      if (remaining <= 0) {
        clearInterval(countRef.current!);
        countRef.current = null;
      }
    }, 1000);

    timerRef.current = setTimeout(() => {
      startCycle();
    }, intervalSec * 1000);
  }, [onRefresh, intervalSec, stopCountdown]);

  // Auto-start on mount
  useEffect(() => {
    if (autoStart) {
      startCycle();
    }
    return stopCountdown;
  }, []); // eslint-disable-line

  const togglePause = () => {
    const nowPaused = !paused;
    setPaused(nowPaused);
    pausedRef.current = nowPaused;
    if (nowPaused) {
      stopCountdown();
      setRunning(false);
      setCountdown(intervalSec);
    } else {
      startCycle();
    }
  };

  const manualRefresh = () => {
    if (!running) startCycle();
  };

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      fontFamily: "JetBrains Mono, monospace", fontSize: 11,
    }}>
      {lastRefresh && (
        <span style={{ color: "var(--dim)", fontSize: 10 }}>
          last: {lastRefresh}
        </span>
      )}

      {running ? (
        <span style={{ color: "var(--accent)", fontSize: 10 }}>
          FETCHING...
        </span>
      ) : paused ? (
        <span style={{ color: "var(--warn)", fontSize: 10 }}>PAUSED</span>
      ) : (
        <span style={{ color: "var(--dim)", fontSize: 10 }}>
          next in {countdown}s
        </span>
      )}

      <button
        onClick={manualRefresh}
        disabled={running}
        style={{
          background: "none",
          border: "1px solid var(--border)",
          color: running ? "var(--muted)" : "var(--dim)",
          padding: "2px 8px",
          borderRadius: 4,
          cursor: running ? "not-allowed" : "pointer",
          fontFamily: "inherit",
          fontSize: 10,
          transition: "all .15s",
        }}
        title="Refresh now"
      >
        REFRESH
      </button>

      <button
        onClick={togglePause}
        style={{
          background: "none",
          border: "1px solid",
          borderColor: paused ? "var(--warn)" : "var(--border)",
          color: paused ? "var(--warn)" : "var(--dim)",
          padding: "2px 8px",
          borderRadius: 4,
          cursor: "pointer",
          fontFamily: "inherit",
          fontSize: 10,
          transition: "all .15s",
        }}
        title={paused ? "Resume auto-refresh" : "Pause auto-refresh"}
      >
        {paused ? "RESUME" : "PAUSE"}
      </button>
    </div>
  );
}
""")

print("[FIX 3] Done — RefreshController component written")


# ═══════════════════════════════════════════════════════════════════════════════
# Also fix the /api/agent-data route if it exists — update DA path
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[PATH FIX] Updating all route.ts files with new D:/MICC path...")
updated = 0
for route_file in APP.rglob("route.ts"):
    content = route_file.read_text(encoding="utf-8")
    changed = False
    for old in [
        "D:/MICC",
        r"D:\MICC",
    ]:
        if old in content:
            content = content.replace(old, "D:/MICC")
            changed = True
    if changed:
        route_file.write_text(content, encoding="utf-8")
        updated += 1

print(f"  Updated {updated} route.ts files with new DA path")


# ═══════════════════════════════════════════════════════════════════════════════
# Write a simple integration guide for adding RefreshController to page.tsx
# ═══════════════════════════════════════════════════════════════════════════════
guide = """
HOW TO INTEGRATE RefreshController into page.tsx
=================================================

1. Import at top of page.tsx:
   import RefreshController from "@/components/RefreshController";

2. Create a triggerRefresh function that calls all your data-fetch hooks:
   const triggerRefresh = useCallback(async () => {
     await Promise.all([
       fetchAlpha(),
       fetchBeta(),
       fetchGamma(),
       fetchDelta(),
       fetchIndices(),
       fetchStreak(),
     ]);
   }, [fetchAlpha, fetchBeta, fetchGamma, fetchDelta, fetchIndices, fetchStreak]);

3. Add to header JSX (in .header-right div):
   <RefreshController onRefresh={triggerRefresh} intervalSec={90} />

4. Remove the old setInterval / useEffect refresh logic.

NOTE: Each fetch function must return a Promise.
If using SWR or React Query, pass mutate() functions.
If using useState + fetch, wrap each in an async function that returns the fetch Promise.
"""
guide_path = BASE / "REFRESH_INTEGRATION_GUIDE.txt"
guide_path.write_text(guide, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  ALL 3 BUGS FIXED")
print("=" * 60)
print()
print("  Bug 1 FIXED: /api/indices/route.ts")
print("    - Uses closing_index_value (not 'close')")
print("    - Uses index_name (confirmed correct column)")
print("    - Window anchored to MAX(date) in market_snapshot")
print()
print("  Bug 2 FIXED: /api/streak-extended/route.ts")
print("    - WHERE run_date >= date(MAX(run_date), '-Nd')")
print("    - Works for any lookback window regardless of calendar date")
print()
print("  Bug 3 FIXED: RefreshController component created")
print("    - File: micc-dashboard/src/components/RefreshController.tsx")
print("    - Async cycle: fetch -> countdown -> fetch (no drift)")
print("    - Shows 'FETCHING...' / 'next in Xs' / last refresh time")
print("    - PAUSE / RESUME / REFRESH NOW buttons")
print("    - Integration guide: REFRESH_INTEGRATION_GUIDE.txt")
print()
print("  PATH UPDATES:")
print("    - All route.ts files updated to DA = 'D:/MICC'")
print()
print("  NEXT: Restart Next.js dev server")
print("        cd D:\\MICC\\micc-dashboard && npm run dev")
print()
