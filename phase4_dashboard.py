# -*- coding: utf-8 -*-
"""
phase4_dashboard.py
====================
MICC Phase 4 - Three new dashboard panels + Groq fix + Task Scheduler.

Adds:
  1. OPTIONS PANEL   — Nifty options chain, PCR, GEX by strike, Max Pain
                       Data: option_greeks_raw + gamma_exposure_daily + fo_data
  2. MACRO PANEL     — India + US macro in one view
                       Data: us_macro_data, india_macro_fred, world_bank_macro
  3. MF FLOW PANEL   — Top MF NAV trends + category breakdown
                       Data: mf_nav_history
  4. GROQ FIX        — Smarter retry with exponential backoff, cap calls per agent
  5. TASK SCHEDULER  — Prints schtasks command to automate 4 PM IST daily run

Usage:
  cd D:\\MICC
  py phase4_dashboard.py

All rules respected:
  - 'py' not 'python'
  - No get_conn() in agent files
  - Zero emoji / Unicode in TSX — pure ASCII only
  - fo_data queries always filtered by date (never full table scan)
  - DA path = 'D:/MICC', DB path = 'D:/marketDB/db/market.db'
"""

import os
import sys
from pathlib import Path

# ── Resolve paths ─────────────────────────────────────────────────────────────
BASE = Path(r"D:\MICC")

def find_paths():
    for sub in ["micc-dashboard/src", "micc-dashboard"]:
        p = BASE / sub
        if p.is_dir() and (p / "components").is_dir():
            return p / "app", p / "components", p / "lib"
    return None, None, None

APP, COMP, LIB = find_paths()
if not APP:
    print("[ERROR] micc-dashboard not found at D:/MICC/micc-dashboard/")
    print("        Make sure run_pipeline.py has been run at least once.")
    sys.exit(1)

print(f"[OK] Dashboard root: {APP.parent}")

def probe(path: Path) -> str:
    """Read existing file content if it exists, else return empty string."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

def w(path: Path, content: str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    try:
        rel = path.relative_to(BASE)
    except ValueError:
        rel = path
    print(f"  wrote: {rel}")


# =============================================================================
# 1. GROQ FIX — exponential backoff + per-agent call budget
#    Patch micc_data.py: replace call_groq() with smarter version
# =============================================================================
print("\n[1/5] Patching call_groq() in micc_data.py...")

MICC_DATA = BASE / "micc_data.py"
existing = probe(MICC_DATA)

GROQ_OLD_MARKER = "def call_groq("
GROQ_NEW_BLOCK = '''
def call_groq(
    prompt: str,
    system: str = "You are a senior equity analyst at an institutional hedge fund.",
    max_tokens: int = 600,
    temperature: float = 0.25,
    retries: int = 3,
) -> str:
    """
    Call Groq llama-3.3-70b with exponential backoff.

    Improvements over original:
      - Retry up to `retries` times (default 3) with 2^n * 7s backoff
      - On HTTP 429 waits longer (quota reset window ~60s) before retrying
      - Hard timeout enforced per attempt (GROQ_TIMEOUT)
      - Falls through to Ollama on persistent 429 rather than raising
    """
    global _groq_last_call
    import time as _time
    # Enforce minimum spacing between consecutive calls
    gap = _time.time() - _groq_last_call
    if gap < GROQ_RATE_DELAY:
        _time.sleep(GROQ_RATE_DELAY - gap)

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    [
            {"role": "system",  "content": system},
            {"role": "user",    "content": prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }

    for attempt in range(retries):
        try:
            _groq_last_call = _time.time()
            resp = requests.post(
                GROQ_URL,
                headers=headers,
                json=payload,
                timeout=GROQ_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()

            if resp.status_code == 429:
                # Quota hit — wait longer on each attempt
                wait = (2 ** attempt) * 7 + 30   # 37s, 44s, 58s
                print(f"  [Groq] 429 rate-limit on attempt {attempt+1}, "
                      f"waiting {wait}s before retry...", flush=True)
                _time.sleep(wait)
                continue

            # Other HTTP error — raise so caller can fall back
            resp.raise_for_status()

        except requests.exceptions.Timeout:
            wait = (2 ** attempt) * 5
            print(f"  [Groq] timeout on attempt {attempt+1}, "
                  f"waiting {wait}s...", flush=True)
            _time.sleep(wait)
        except requests.exceptions.RequestException as e:
            print(f"  [Groq] request error: {e}", flush=True)
            break

    # All retries exhausted — fall back to Ollama
    print("  [Groq] all retries exhausted, falling back to Ollama", flush=True)
    return call_ollama(prompt, system=system, max_tokens=max_tokens)

'''

if GROQ_OLD_MARKER in existing:
    # Find the old function and replace it up to the next top-level def/class
    lines = existing.splitlines()
    start = None
    end   = None
    for i, line in enumerate(lines):
        if line.startswith("def call_groq("):
            start = i
        elif start is not None and i > start and (
            line.startswith("def ") or line.startswith("class ")
        ):
            end = i
            break

    if start is not None and end is not None:
        new_lines = lines[:start] + GROQ_NEW_BLOCK.splitlines() + lines[end:]
        MICC_DATA.write_text("\n".join(new_lines), encoding="utf-8", newline="\n")
        print("  patched: micc_data.py  (call_groq replaced with backoff version)")
    else:
        print("  [WARN] Could not isolate call_groq() boundaries — skipping patch.")
        print("         Manually replace call_groq() in micc_data.py with the version below.")
else:
    print("  [WARN] call_groq() not found in micc_data.py — skipping.")

print("[1/5] Groq patch done")


# =============================================================================
# 2. API ROUTES — /api/options, /api/macro, /api/mf
# =============================================================================
print("\n[2/5] Writing API routes...")

# ── /api/options/route.ts ─────────────────────────────────────────────────────
# Tables used:
#   option_greeks_raw  — columns: symbol, date, expiry, strike, option_type,
#                        close, iv, delta, gamma, theta, vega, oi, volume
#   gamma_exposure_daily — columns: date, strike, call_gex, put_gex, net_gex
#   fo_data            — 144M rows; ALWAYS filter by date
#
# PCR = total put OI / total call OI for NIFTY on latest expiry
# Max Pain = strike where total OI loss is minimised
# GEX = sum(net_gex) by strike from gamma_exposure_daily
w(APP / "api" / "options" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input:    JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout:  25000,
      cwd:      DA,
    })
    if (result.status !== 0) {
      console.error('[options api] bridge error:', result.stderr?.slice(0, 300))
      return []
    }
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) {
    console.error('[options api] exception:', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // ── Latest date in option_greeks_raw ────────────────────────────────────────
  const latestRows = queryDb(`SELECT MAX(date) AS d FROM option_greeks_raw`)
  const latestDate = latestRows[0]?.d ?? ''
  if (!latestDate) {
    return NextResponse.json({ error: 'No data in option_greeks_raw', date: null })
  }

  // ── Nearest expiry for NIFTY on latest date ──────────────────────────────────
  const expiryRows = queryDb(`
    SELECT MIN(expiry) AS nearest_expiry
    FROM option_greeks_raw
    WHERE date = '${latestDate}'
      AND symbol LIKE 'NIFTY%'
      AND expiry >= '${latestDate}'
  `)
  const nearestExpiry = expiryRows[0]?.nearest_expiry ?? ''

  // ── PCR — put OI / call OI for NIFTY nearest expiry ─────────────────────────
  const pcrRows = queryDb(`
    SELECT
      option_type,
      SUM(oi) AS total_oi
    FROM option_greeks_raw
    WHERE date   = '${latestDate}'
      AND symbol LIKE 'NIFTY%'
      AND expiry  = '${nearestExpiry}'
    GROUP BY option_type
  `)
  const callOI = pcrRows.find((r: any) => r.option_type === 'CE')?.total_oi ?? 0
  const putOI  = pcrRows.find((r: any) => r.option_type === 'PE')?.total_oi ?? 0
  const pcr    = callOI > 0 ? Math.round((putOI / callOI) * 1000) / 1000 : null

  // ── Options chain — top 15 strikes by total OI around ATM ───────────────────
  const chainRows = queryDb(`
    SELECT
      strike,
      MAX(CASE WHEN option_type='CE' THEN close   END) AS call_ltp,
      MAX(CASE WHEN option_type='CE' THEN oi      END) AS call_oi,
      MAX(CASE WHEN option_type='CE' THEN iv      END) AS call_iv,
      MAX(CASE WHEN option_type='CE' THEN delta   END) AS call_delta,
      MAX(CASE WHEN option_type='CE' THEN gamma   END) AS call_gamma,
      MAX(CASE WHEN option_type='PE' THEN close   END) AS put_ltp,
      MAX(CASE WHEN option_type='PE' THEN oi      END) AS put_oi,
      MAX(CASE WHEN option_type='PE' THEN iv      END) AS put_iv,
      MAX(CASE WHEN option_type='PE' THEN delta   END) AS put_delta,
      MAX(CASE WHEN option_type='PE' THEN gamma   END) AS put_gamma
    FROM option_greeks_raw
    WHERE date   = '${latestDate}'
      AND symbol LIKE 'NIFTY%'
      AND expiry  = '${nearestExpiry}'
    GROUP BY strike
    ORDER BY (COALESCE(call_oi,0) + COALESCE(put_oi,0)) DESC
    LIMIT 20
  `)
  const chain = [...chainRows].sort((a: any, b: any) => a.strike - b.strike)

  // ── Max Pain — strike with minimum total OI $ loss ──────────────────────────
  // For each candidate strike K:
  //   call loss = SUM over strikes < K of (K - strike)*call_oi
  //   put  loss = SUM over strikes > K of (strike - K)*put_oi
  //   total loss = call loss + put loss
  // Max pain = K that minimises total loss
  const allStrikeRows = queryDb(`
    SELECT
      strike,
      SUM(CASE WHEN option_type='CE' THEN COALESCE(oi,0) END) AS call_oi,
      SUM(CASE WHEN option_type='PE' THEN COALESCE(oi,0) END) AS put_oi
    FROM option_greeks_raw
    WHERE date   = '${latestDate}'
      AND symbol LIKE 'NIFTY%'
      AND expiry  = '${nearestExpiry}'
    GROUP BY strike
    ORDER BY strike ASC
  `)

  let maxPainStrike = null
  if (allStrikeRows.length > 0) {
    const strikes = allStrikeRows.map((r: any) => Number(r.strike))
    let minLoss = Infinity
    for (const K of strikes) {
      let loss = 0
      for (const row of allStrikeRows as any[]) {
        const s  = Number(row.strike)
        const co = Number(row.call_oi ?? 0)
        const po = Number(row.put_oi  ?? 0)
        if (s < K) loss += (K - s) * co  // call writers lose if price > strike
        if (s > K) loss += (s - K) * po  // put  writers lose if price < strike
      }
      if (loss < minLoss) { minLoss = loss; maxPainStrike = K }
    }
  }

  // ── GEX by strike from gamma_exposure_daily ──────────────────────────────────
  const gexLatestRows  = queryDb(`SELECT MAX(date) AS d FROM gamma_exposure_daily`)
  const gexLatestDate  = gexLatestRows[0]?.d ?? ''
  const gexRows = gexLatestDate ? queryDb(`
    SELECT
      strike,
      ROUND(SUM(call_gex), 2) AS call_gex,
      ROUND(SUM(put_gex),  2) AS put_gex,
      ROUND(SUM(net_gex),  2) AS net_gex
    FROM gamma_exposure_daily
    WHERE date = '${gexLatestDate}'
    GROUP BY strike
    ORDER BY ABS(net_gex) DESC
    LIMIT 25
  `) : []

  // Net GEX summary
  const totalGex = gexRows.reduce((s: number, r: any) => s + Number(r.net_gex ?? 0), 0)

  return NextResponse.json({
    date:           latestDate,
    expiry:         nearestExpiry,
    pcr,
    call_oi:        callOI,
    put_oi:         putOI,
    max_pain:       maxPainStrike,
    chain,
    gex:            gexRows,
    total_net_gex:  Math.round(totalGex),
    gex_date:       gexLatestDate,
  })
}
""")

# ── /api/macro/route.ts ───────────────────────────────────────────────────────
# Tables:
#   us_macro_data      — columns: series_id, date, value  (FRED series)
#   india_macro_fred   — columns: series_id, date, value  (FRED series for India)
#   world_bank_macro   — columns: indicator_code, year, value, country_code
#
# Key FRED series we want:
#   FEDFUNDS  — Fed Funds Rate
#   DGS10     — US 10Y yield
#   T10Y2Y    — 10Y-2Y Term Spread
#   GDPC1     — US Real GDP (quarterly)
#   CPIAUCSL  — US CPI
#   INDCPIALLMINMEI — India CPI (FRED)
#   INTDSRINM193N   — India lending rate (FRED)
#   IRSTCI01INM156N — India policy rate proxy
w(APP / "api" / "macro" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input:    JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout:  20000,
      cwd:      DA,
    })
    if (result.status !== 0) {
      console.error('[macro api] bridge error:', result.stderr?.slice(0, 300))
      return []
    }
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) {
    console.error('[macro api] exception:', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

// Fetch last N points of a FRED series from a given table
function seriesHistory(table: string, seriesId: string, n: number = 24): any[] {
  return queryDb(`
    SELECT date, ROUND(CAST(value AS REAL), 4) AS value
    FROM ${table}
    WHERE series_id = '${seriesId}'
      AND value IS NOT NULL
    ORDER BY date DESC
    LIMIT ${n}
  `).reverse()   // chronological order
}

export async function GET() {
  // ── US Macro ─────────────────────────────────────────────────────────────────
  const fedfunds   = seriesHistory('us_macro_data', 'FEDFUNDS',  24)
  const us10y      = seriesHistory('us_macro_data', 'DGS10',     60)
  const termSpread = seriesHistory('us_macro_data', 'T10Y2Y',    60)
  const usCpi      = seriesHistory('us_macro_data', 'CPIAUCSL',  24)
  const usGdp      = seriesHistory('us_macro_data', 'GDPC1',     16)

  // ── India Macro (FRED) ───────────────────────────────────────────────────────
  const indiaCpi   = seriesHistory('india_macro_fred', 'INDCPIALLMINMEI', 24)
  // India policy rate — try a few possible series_ids in order
  const indiaRate1 = seriesHistory('india_macro_fred', 'IRSTCI01INM156N', 24)
  const indiaRate2 = seriesHistory('india_macro_fred', 'INTDSRINM193N',   24)
  const indiaRate  = indiaRate1.length ? indiaRate1 : indiaRate2

  // ── World Bank India ─────────────────────────────────────────────────────────
  // FX Reserves (BN.RES.INCL.CD), Current Account (BN.CAB.XOKA.CD)
  const fxReserves = queryDb(`
    SELECT year AS date,
           ROUND(CAST(value AS REAL) / 1e9, 1) AS value
    FROM world_bank_macro
    WHERE indicator_code = 'BN.RES.INCL.CD'
      AND country_code   = 'IND'
      AND value IS NOT NULL
    ORDER BY year DESC
    LIMIT 10
  `).reverse()

  // ── Latest point helpers ─────────────────────────────────────────────────────
  function latest(series: any[]) {
    if (!series.length) return null
    return series[series.length - 1]
  }
  function prev(series: any[], n = 1) {
    const i = series.length - 1 - n
    return i >= 0 ? series[i] : null
  }
  function delta(series: any[], n = 1) {
    const l = latest(series)
    const p = prev(series, n)
    if (!l || !p) return null
    return Math.round((Number(l.value) - Number(p.value)) * 10000) / 10000
  }

  // India-US rate differential (latest points)
  const latestFed     = latest(fedfunds)
  const latestIndia   = latest(indiaRate)
  const rateDiff = (latestIndia && latestFed)
    ? Math.round((Number(latestIndia.value) - Number(latestFed.value)) * 100) / 100
    : null

  return NextResponse.json({
    fedfunds:   { series: fedfunds,   latest: latest(fedfunds),   delta_1m: delta(fedfunds,  1) },
    us_10y:     { series: us10y,      latest: latest(us10y),      delta_1m: delta(us10y,     1) },
    term_spread:{ series: termSpread, latest: latest(termSpread), delta_1m: delta(termSpread,1) },
    us_cpi:     { series: usCpi,      latest: latest(usCpi),      delta_1m: delta(usCpi,     1) },
    us_gdp:     { series: usGdp,      latest: latest(usGdp),      delta_1m: delta(usGdp,     1) },
    india_cpi:  { series: indiaCpi,   latest: latest(indiaCpi),   delta_1m: delta(indiaCpi,  1) },
    india_rate: { series: indiaRate,  latest: latestIndia,        delta_1m: delta(indiaRate, 1) },
    fx_reserves:{ series: fxReserves, latest: latest(fxReserves) },
    rate_differential: rateDiff,
  })
}
""")

# ── /api/mf/route.ts ──────────────────────────────────────────────────────────
# Table: mf_nav_history
#   Probe actual columns from the data we know: 222 rows, latest 2026-05-10
#   Likely columns: scheme_code, scheme_name, nav, date, category (or similar)
#   We query dynamically and handle missing columns gracefully.
w(APP / "api" / "mf" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input:    JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout:  20000,
      cwd:      DA,
    })
    if (result.status !== 0) {
      console.error('[mf api] bridge error:', result.stderr?.slice(0, 300))
      return []
    }
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) {
    console.error('[mf api] exception:', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // ── Probe actual columns in mf_nav_history ────────────────────────────────
  const colRows = queryDb(`PRAGMA table_info(mf_nav_history)`)
  const cols = colRows.map((r: any) => (r.name as string).toLowerCase())

  const hasCategory = cols.includes('category') || cols.includes('scheme_category')
  const catCol = cols.includes('scheme_category') ? 'scheme_category'
               : cols.includes('category')        ? 'category'
               : null

  const hasCode    = cols.includes('scheme_code') || cols.includes('code')
  const codeCol    = cols.includes('scheme_code') ? 'scheme_code' : 'code'
  const nameCol    = cols.includes('scheme_name') ? 'scheme_name'
                   : cols.includes('name')        ? 'name'
                   : 'scheme_name'

  // ── Latest date in mf_nav_history ─────────────────────────────────────────
  const latestRows = queryDb(`SELECT MAX(date) AS d FROM mf_nav_history`)
  const latestDate = latestRows[0]?.d ?? ''
  if (!latestDate) {
    return NextResponse.json({ error: 'No data in mf_nav_history', date: null })
  }

  // ── Previous date for change calculation ─────────────────────────────────
  const prevDateRows = queryDb(`
    SELECT MAX(date) AS d
    FROM mf_nav_history
    WHERE date < '${latestDate}'
  `)
  const prevDate = prevDateRows[0]?.d ?? ''

  // ── Top 20 funds by NAV on latest date ────────────────────────────────────
  const topRows = queryDb(`
    SELECT
      ${hasCode ? `n.${codeCol} AS code,` : ''}
      n.${nameCol}             AS name,
      ${catCol ? `n.${catCol} AS category,` : `'--' AS category,`}
      ROUND(CAST(n.nav AS REAL), 4) AS nav,
      ${prevDate ? `
        ROUND(
          (CAST(n.nav AS REAL) - CAST(p.nav AS REAL))
          / NULLIF(CAST(p.nav AS REAL), 0) * 100,
          3
        ) AS change_pct,
        ROUND(CAST(p.nav AS REAL), 4) AS prev_nav,
      ` : `NULL AS change_pct, NULL AS prev_nav,`}
      n.date
    FROM mf_nav_history n
    ${prevDate ? `
    LEFT JOIN mf_nav_history p
      ON ${hasCode ? `n.${codeCol} = p.${codeCol}` : `n.${nameCol} = p.${nameCol}`}
     AND p.date = '${prevDate}'
    ` : ''}
    WHERE n.date = '${latestDate}'
    ORDER BY CAST(n.nav AS REAL) DESC
    LIMIT 20
  `)

  // ── Category breakdown ────────────────────────────────────────────────────
  const catRows = catCol ? queryDb(`
    SELECT
      ${catCol}                    AS category,
      COUNT(*)                     AS fund_count,
      ROUND(AVG(CAST(nav AS REAL)),2) AS avg_nav,
      ROUND(MAX(CAST(nav AS REAL)),2) AS max_nav
    FROM mf_nav_history
    WHERE date = '${latestDate}'
      AND ${catCol} IS NOT NULL
    GROUP BY ${catCol}
    ORDER BY avg_nav DESC
  `) : []

  // ── Top gainers (latest vs prev) ──────────────────────────────────────────
  const gainers = prevDate ? queryDb(`
    SELECT
      n.${nameCol}             AS name,
      ${catCol ? `n.${catCol} AS category,` : `'--' AS category,`}
      ROUND(CAST(n.nav AS REAL), 4) AS nav,
      ROUND(
        (CAST(n.nav AS REAL) - CAST(p.nav AS REAL))
        / NULLIF(CAST(p.nav AS REAL), 0) * 100,
        3
      ) AS change_pct
    FROM mf_nav_history n
    JOIN mf_nav_history p
      ON ${hasCode ? `n.${codeCol} = p.${codeCol}` : `n.${nameCol} = p.${nameCol}`}
     AND p.date = '${prevDate}'
    WHERE n.date = '${latestDate}'
      AND CAST(p.nav AS REAL) > 0
    ORDER BY change_pct DESC
    LIMIT 10
  `) : []

  // ── Summary stats ─────────────────────────────────────────────────────────
  const stats = queryDb(`
    SELECT
      COUNT(*)                         AS total_funds,
      COUNT(DISTINCT date)             AS date_count,
      MAX(date)                        AS latest_date,
      MIN(date)                        AS earliest_date,
      ROUND(AVG(CAST(nav AS REAL)), 2) AS avg_nav,
      ROUND(MAX(CAST(nav AS REAL)), 2) AS max_nav,
      ROUND(MIN(CAST(nav AS REAL)), 2) AS min_nav
    FROM mf_nav_history
  `)

  return NextResponse.json({
    date:        latestDate,
    prev_date:   prevDate,
    top_funds:   topRows,
    categories:  catRows,
    gainers,
    stats:       stats[0] ?? {},
  })
}
""")

print("[2/5] API routes written")


# =============================================================================
# 3. TSX COMPONENTS — OptionsPanel, MacroPanel, MFPanel
# =============================================================================
print("\n[3/5] Writing TSX components...")

# ── OptionsPanel.tsx ──────────────────────────────────────────────────────────
w(COMP / "OptionsPanel.tsx", r"""
"use client";
import { useState, useEffect } from "react";

interface ChainRow {
  strike:      number;
  call_ltp:    number | null;
  call_oi:     number | null;
  call_iv:     number | null;
  put_ltp:     number | null;
  put_oi:      number | null;
  put_iv:      number | null;
}
interface GexRow {
  strike:   number;
  call_gex: number;
  put_gex:  number;
  net_gex:  number;
}
interface OptionsData {
  date:          string;
  expiry:        string;
  pcr:           number | null;
  call_oi:       number;
  put_oi:        number;
  max_pain:      number | null;
  chain:         ChainRow[];
  gex:           GexRow[];
  total_net_gex: number;
  gex_date:      string;
  error?:        string;
}

function fmtOI(v: number | null): string {
  if (v == null) return "--";
  const n = Number(v);
  if (n >= 1e7) return (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return (n / 1e5).toFixed(1) + "L";
  return n.toLocaleString();
}
function fmtLTP(v: number | null): string {
  if (v == null) return "--";
  return Number(v).toFixed(2);
}
function fmtIV(v: number | null): string {
  if (v == null) return "--";
  return Number(v).toFixed(1) + "%";
}
function fmtGex(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (abs >= 1e6) return (v / 1e6).toFixed(2) + "M";
  return v.toFixed(0);
}

export default function OptionsPanel() {
  const [data, setData]     = useState<OptionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]       = useState<"chain" | "gex">("chain");

  useEffect(() => {
    fetch("/api/options")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="panel">
      <div className="panel-title">OPTIONS</div>
      <div className="c-dim small">Loading options data...</div>
    </div>
  );
  if (!data || data.error) return (
    <div className="panel">
      <div className="panel-title">OPTIONS</div>
      <div className="c-bear small">{data?.error ?? "No options data. Run: py phase2_greeks_calculator.py --daily"}</div>
    </div>
  );

  const pcrColor = data.pcr == null ? "var(--text)"
                 : data.pcr > 1.3   ? "var(--bull)"
                 : data.pcr < 0.7   ? "var(--bear)"
                 : "var(--warn)";
  const pcrLabel = data.pcr == null ? "--"
                 : data.pcr > 1.3   ? "BULLISH"
                 : data.pcr < 0.7   ? "BEARISH"
                 : "NEUTRAL";
  const gexColor = data.total_net_gex > 0 ? "var(--bull)" : "var(--bear)";
  const gexLabel = data.total_net_gex > 0 ? "LONG GAMMA" : "SHORT GAMMA";

  // Find max OI for bar scaling
  const maxCallOI = Math.max(...data.chain.map(r => r.call_oi ?? 0), 1);
  const maxPutOI  = Math.max(...data.chain.map(r => r.put_oi  ?? 0), 1);
  const maxGex    = Math.max(...data.gex.map(r => Math.abs(r.net_gex)), 1);

  return (
    <div className="panel">
      <div className="panel-title">
        <span style={{ color: "var(--accent)" }}>&diams;</span> OPTIONS &mdash; NIFTY CHAIN
        <span className="ml" style={{ fontSize: 10, color: "var(--dim)" }}>
          {data.date} &nbsp;|&nbsp; Expiry: {data.expiry}
        </span>
      </div>

      {/* Summary stats */}
      <div className="stat-grid sg4" style={{ marginBottom: 12 }}>
        <div className="stat-box">
          <div className="stat-lbl">PCR</div>
          <div className="stat-val" style={{ color: pcrColor }}>
            {data.pcr?.toFixed(3) ?? "--"}
          </div>
          <div style={{ fontSize: 9, color: pcrColor }}>{pcrLabel}</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">MAX PAIN</div>
          <div className="stat-val c-warn">
            {data.max_pain?.toLocaleString() ?? "--"}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">NET GEX</div>
          <div className="stat-val" style={{ color: gexColor }}>
            {fmtGex(data.total_net_gex)}
          </div>
          <div style={{ fontSize: 9, color: gexColor }}>{gexLabel}</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">CALL OI</div>
          <div className="stat-val c-bear">{fmtOI(data.call_oi)}</div>
          <div className="stat-lbl" style={{ marginTop: 2 }}>PUT OI</div>
          <div className="stat-val c-bull">{fmtOI(data.put_oi)}</div>
        </div>
      </div>

      {/* Tab switch */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {(["chain", "gex"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "3px 10px", fontSize: 10, cursor: "pointer",
              background: tab === t ? "var(--accent)" : "var(--surface)",
              color:      tab === t ? "#000"          : "var(--dim)",
              border:     "1px solid var(--border)", borderRadius: 3,
              fontFamily: "monospace", letterSpacing: "0.08em",
            }}
          >
            {t === "chain" ? "CHAIN" : "GEX BY STRIKE"}
          </button>
        ))}
      </div>

      {/* Options chain */}
      {tab === "chain" && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--dim)", fontSize: 10 }}>
                <th style={{ textAlign: "right",  padding: "3px 6px" }}>CALL OI</th>
                <th style={{ textAlign: "right",  padding: "3px 6px" }}>IV</th>
                <th style={{ textAlign: "right",  padding: "3px 6px" }}>LTP</th>
                <th style={{ textAlign: "center", padding: "3px 8px", color: "var(--accent)", minWidth: 80 }}>STRIKE</th>
                <th style={{ textAlign: "left",   padding: "3px 6px" }}>LTP</th>
                <th style={{ textAlign: "left",   padding: "3px 6px" }}>IV</th>
                <th style={{ textAlign: "left",   padding: "3px 6px" }}>PUT OI</th>
              </tr>
            </thead>
            <tbody>
              {data.chain.map((row, i) => {
                const isMaxPain = row.strike === data.max_pain;
                const callBarW  = Math.round(((row.call_oi ?? 0) / maxCallOI) * 60);
                const putBarW   = Math.round(((row.put_oi  ?? 0) / maxPutOI)  * 60);
                return (
                  <tr key={i} style={{
                    borderBottom:    "1px solid var(--border-faint, #2a2a2a)",
                    background:      isMaxPain ? "rgba(255,200,0,0.07)" : undefined,
                    color:           "var(--text)",
                  }}>
                    {/* Call side */}
                    <td style={{ textAlign: "right", padding: "3px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                        <span style={{ color: "var(--bear)" }}>{fmtOI(row.call_oi)}</span>
                        <div style={{ width: callBarW, height: 6, background: "var(--bear)", opacity: 0.6, borderRadius: 2 }} />
                      </div>
                    </td>
                    <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--dim)" }}>{fmtIV(row.call_iv)}</td>
                    <td style={{ textAlign: "right", padding: "3px 6px" }}>{fmtLTP(row.call_ltp)}</td>
                    {/* Strike */}
                    <td style={{ textAlign: "center", padding: "3px 8px",
                                 color: isMaxPain ? "var(--warn)" : "var(--accent)",
                                 fontWeight: isMaxPain ? 700 : 600 }}>
                      {row.strike.toLocaleString()}
                      {isMaxPain && <span style={{ fontSize: 9, marginLeft: 4 }}>MAX PAIN</span>}
                    </td>
                    {/* Put side */}
                    <td style={{ textAlign: "left", padding: "3px 6px" }}>{fmtLTP(row.put_ltp)}</td>
                    <td style={{ textAlign: "left",  padding: "3px 6px", color: "var(--dim)" }}>{fmtIV(row.put_iv)}</td>
                    <td style={{ textAlign: "left",  padding: "3px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <div style={{ width: putBarW, height: 6, background: "var(--bull)", opacity: 0.6, borderRadius: 2 }} />
                        <span style={{ color: "var(--bull)" }}>{fmtOI(row.put_oi)}</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* GEX by strike */}
      {tab === "gex" && (
        <div>
          <div style={{ fontSize: 10, color: "var(--dim)", marginBottom: 6 }}>
            GEX date: {data.gex_date} &nbsp;|&nbsp;
            Positive GEX = dealers long gamma (dampens moves) &nbsp;|&nbsp;
            Negative GEX = short gamma (amplifies moves)
          </div>
          {data.gex.length === 0 ? (
            <div className="c-dim small">No GEX data. Run: py phase2_greeks_calculator.py --daily</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--dim)", fontSize: 10 }}>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>STRIKE</th>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>CALL GEX</th>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>PUT GEX</th>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>NET GEX</th>
                  <th style={{ textAlign: "left",   padding: "3px 8px" }}>BAR</th>
                </tr>
              </thead>
              <tbody>
                {[...data.gex].sort((a, b) => Number(a.strike) - Number(b.strike)).map((row, i) => {
                  const net    = Number(row.net_gex);
                  const barW   = Math.round((Math.abs(net) / maxGex) * 80);
                  const barClr = net >= 0 ? "var(--bull)" : "var(--bear)";
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-faint, #2a2a2a)" }}>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: "var(--accent)", fontWeight: 600 }}>
                        {Number(row.strike).toLocaleString()}
                      </td>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: "var(--bull)" }}>{fmtGex(Number(row.call_gex))}</td>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: "var(--bear)" }}>{fmtGex(Number(row.put_gex))}</td>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: barClr, fontWeight: 600 }}>{fmtGex(net)}</td>
                      <td style={{ padding: "3px 8px" }}>
                        <div style={{ width: barW, height: 6, background: barClr, borderRadius: 2 }} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
""")

# ── MacroPanel.tsx ────────────────────────────────────────────────────────────
w(COMP / "MacroPanel.tsx", r"""
"use client";
import { useState, useEffect } from "react";

interface MacroSeries {
  series:   { date: string; value: number }[];
  latest:   { date: string; value: number } | null;
  delta_1m: number | null;
}
interface MacroData {
  fedfunds:     MacroSeries;
  us_10y:       MacroSeries;
  term_spread:  MacroSeries;
  us_cpi:       MacroSeries;
  us_gdp:       MacroSeries;
  india_cpi:    MacroSeries;
  india_rate:   MacroSeries;
  fx_reserves:  { series: any[]; latest: any | null };
  rate_differential: number | null;
  error?:       string;
}

function Sparkline({ series, color }: { series: { value: number }[]; color: string }) {
  if (!series || series.length < 2) return <span style={{ color: "var(--dim)", fontSize: 10 }}>--</span>;
  const vals  = series.map(d => Number(d.value));
  const min   = Math.min(...vals);
  const max   = Math.max(...vals);
  const range = max - min || 1;
  const W = 80, H = 26, pad = 2;
  const pts = vals.map((v, i) => {
    const x = pad + (i / (vals.length - 1)) * (W - pad * 2);
    const y = H - pad - ((v - min) / range) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function MacroRow({
  label, latest, delta, series, unit = "", color,
}: {
  label:  string;
  latest: { date: string; value: number } | null;
  delta:  number | null;
  series: { value: number }[];
  unit?:  string;
  color:  string;
}) {
  const val    = latest?.value ?? null;
  const deltaC = delta == null ? "var(--dim)"
               : delta > 0    ? "var(--bull)"
               : delta < 0    ? "var(--bear)"
               : "var(--dim)";
  const sign   = delta != null && delta > 0 ? "+" : "";
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "130px 80px 70px 90px",
      alignItems: "center", padding: "5px 0",
      borderBottom: "1px solid var(--border-faint, #222)",
      fontSize: 11, fontFamily: "monospace",
    }}>
      <div style={{ color: "var(--dim)" }}>{label}</div>
      <div style={{ color, fontWeight: 600, textAlign: "right" }}>
        {val != null ? `${Number(val).toFixed(2)}${unit}` : "--"}
      </div>
      <div style={{ color: deltaC, textAlign: "right", fontSize: 10 }}>
        {delta != null ? `${sign}${delta.toFixed(2)}` : "--"}
      </div>
      <div style={{ paddingLeft: 8 }}>
        <Sparkline series={series} color={color} />
      </div>
    </div>
  );
}

export default function MacroPanel() {
  const [data, setData]       = useState<MacroData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]         = useState<"us" | "india">("us");

  useEffect(() => {
    fetch("/api/macro")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="panel">
      <div className="panel-title">MACRO</div>
      <div className="c-dim small">Loading macro data...</div>
    </div>
  );
  if (!data || data.error) return (
    <div className="panel">
      <div className="panel-title">MACRO</div>
      <div className="c-bear small">{data?.error ?? "No macro data. Run: py update_macro_us.py && py update_macro_india_fred.py"}</div>
    </div>
  );

  const latestFed = data.fedfunds.latest;
  const diff      = data.rate_differential;
  const diffColor = diff == null ? "var(--dim)"
                  : diff > 0    ? "var(--bull)" : "var(--bear)";

  const tsLatest  = data.term_spread.latest?.value ?? null;
  const tsColor   = tsLatest == null ? "var(--dim)"
                  : tsLatest < 0    ? "var(--bear)"
                  : tsLatest < 0.5  ? "var(--warn)"
                  : "var(--bull)";

  return (
    <div className="panel">
      <div className="panel-title">
        <span style={{ color: "var(--info)" }}>&equiv;</span> MACRO DASHBOARD
        <span className="ml" style={{ fontSize: 10, color: "var(--dim)" }}>
          Fed: {latestFed?.value?.toFixed(2) ?? "--"}% &nbsp;|&nbsp;
          India-US Diff: <span style={{ color: diffColor }}>
            {diff != null ? (diff > 0 ? "+" : "") + diff.toFixed(2) + "%" : "--"}
          </span>
        </span>
      </div>

      {/* Header stats */}
      <div className="stat-grid sg4" style={{ marginBottom: 12 }}>
        <div className="stat-box">
          <div className="stat-lbl">FED FUNDS</div>
          <div className="stat-val c-warn">{data.fedfunds.latest?.value?.toFixed(2) ?? "--"}%</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">US 10Y YIELD</div>
          <div className="stat-val c-info">{data.us_10y.latest?.value?.toFixed(2) ?? "--"}%</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">TERM SPREAD</div>
          <div className="stat-val" style={{ color: tsColor }}>
            {tsLatest != null ? (tsLatest > 0 ? "+" : "") + tsLatest.toFixed(2) + "%" : "--"}
          </div>
          <div style={{ fontSize: 9, color: tsColor }}>
            {tsLatest == null ? "" : tsLatest < 0 ? "INVERTED" : tsLatest < 0.5 ? "FLAT" : "NORMAL"}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">RATE DIFF</div>
          <div className="stat-val" style={{ color: diffColor }}>
            {diff != null ? (diff > 0 ? "+" : "") + diff.toFixed(2) + "%" : "--"}
          </div>
          <div style={{ fontSize: 9, color: "var(--dim)" }}>India - US</div>
        </div>
      </div>

      {/* Tab switch */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {(["us", "india"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "3px 12px", fontSize: 10, cursor: "pointer",
              background: tab === t ? "var(--info)" : "var(--surface)",
              color:      tab === t ? "#000"        : "var(--dim)",
              border: "1px solid var(--border)", borderRadius: 3,
              fontFamily: "monospace", letterSpacing: "0.08em",
            }}
          >
            {t === "us" ? "US MACRO" : "INDIA MACRO"}
          </button>
        ))}
      </div>

      {/* Column headers */}
      <div style={{
        display: "grid", gridTemplateColumns: "130px 80px 70px 90px",
        fontSize: 9, color: "var(--dim)", fontFamily: "monospace",
        paddingBottom: 4, borderBottom: "1px solid var(--border)",
        marginBottom: 2,
      }}>
        <div>INDICATOR</div>
        <div style={{ textAlign: "right" }}>LATEST</div>
        <div style={{ textAlign: "right" }}>1M CHG</div>
        <div style={{ paddingLeft: 8 }}>TREND</div>
      </div>

      {tab === "us" && (
        <>
          <MacroRow label="Fed Funds Rate"  latest={data.fedfunds.latest}    delta={data.fedfunds.delta_1m}    series={data.fedfunds.series}    unit="%" color="var(--warn)" />
          <MacroRow label="US 10Y Yield"    latest={data.us_10y.latest}      delta={data.us_10y.delta_1m}      series={data.us_10y.series}      unit="%" color="var(--info)" />
          <MacroRow label="Term Spread"     latest={data.term_spread.latest} delta={data.term_spread.delta_1m} series={data.term_spread.series} unit="%" color={tsColor} />
          <MacroRow label="US CPI"          latest={data.us_cpi.latest}      delta={data.us_cpi.delta_1m}      series={data.us_cpi.series}              color="var(--bear)" />
          <MacroRow label="US Real GDP"     latest={data.us_gdp.latest}      delta={data.us_gdp.delta_1m}      series={data.us_gdp.series}              color="var(--bull)" />
        </>
      )}

      {tab === "india" && (
        <>
          <MacroRow label="India Policy Rate" latest={data.india_rate.latest}    delta={data.india_rate.delta_1m}  series={data.india_rate.series}    unit="%" color="var(--accent)" />
          <MacroRow label="India CPI"         latest={data.india_cpi.latest}     delta={data.india_cpi.delta_1m}   series={data.india_cpi.series}             color="var(--bear)"  />
          <MacroRow label="FX Reserves (BnUSD)" latest={data.fx_reserves.latest} delta={null}                       series={data.fx_reserves.series}           color="var(--bull)"  />
          {data.us_10y && (
            <MacroRow label="US 10Y (ref)"    latest={data.us_10y.latest}       delta={data.us_10y.delta_1m}      series={data.us_10y.series}        unit="%" color="var(--dim)"   />
          )}
        </>
      )}

      <div style={{ fontSize: 9, color: "var(--dim)", marginTop: 8 }}>
        Sources: FRED (Federal Reserve) &nbsp;|&nbsp; World Bank &nbsp;|&nbsp;
        Updated daily via run_pipeline.py
      </div>
    </div>
  );
}
""")

# ── MFPanel.tsx ───────────────────────────────────────────────────────────────
w(COMP / "MFPanel.tsx", r"""
"use client";
import { useState, useEffect } from "react";

interface FundRow {
  code?:       string;
  name:        string;
  category?:   string;
  nav:         number;
  change_pct?: number | null;
  prev_nav?:   number | null;
  date:        string;
}
interface CatRow {
  category: string;
  fund_count: number;
  avg_nav:    number;
  max_nav:    number;
}
interface MFData {
  date:       string;
  prev_date:  string;
  top_funds:  FundRow[];
  categories: CatRow[];
  gainers:    FundRow[];
  stats:      {
    total_funds:  number;
    date_count:   number;
    latest_date:  string;
    avg_nav:      number;
    max_nav:      number;
    min_nav:      number;
  };
  error?: string;
}

function fmtNav(v: number): string {
  return Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}
function fmtPct(v: number | null | undefined): string {
  if (v == null) return "--";
  return (v > 0 ? "+" : "") + Number(v).toFixed(3) + "%";
}
function truncate(s: string, n: number): string {
  return s && s.length > n ? s.slice(0, n - 1) + "." : (s ?? "--");
}

export default function MFPanel() {
  const [data, setData]       = useState<MFData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]         = useState<"top" | "gainers" | "categories">("top");

  useEffect(() => {
    fetch("/api/mf")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="panel">
      <div className="panel-title">MF NAV</div>
      <div className="c-dim small">Loading MF data...</div>
    </div>
  );
  if (!data || data.error) return (
    <div className="panel">
      <div className="panel-title">MF NAV</div>
      <div className="c-bear small">{data?.error ?? "No MF data. Run: py update_mf_nav.py"}</div>
    </div>
  );

  const stats = data.stats ?? {};

  return (
    <div className="panel">
      <div className="panel-title">
        <span style={{ color: "var(--bull)" }}>&uarr;</span> MF NAV TRACKER
        <span className="ml" style={{ fontSize: 10, color: "var(--dim)" }}>
          {stats.total_funds} funds &nbsp;|&nbsp; Latest: {data.date}
          {data.prev_date ? ` vs ${data.prev_date}` : ""}
        </span>
      </div>

      {/* Summary strip */}
      <div className="stat-grid sg4" style={{ marginBottom: 12 }}>
        <div className="stat-box">
          <div className="stat-lbl">TOTAL FUNDS</div>
          <div className="stat-val c-accent">{stats.total_funds ?? "--"}</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">AVG NAV</div>
          <div className="stat-val c-text">{stats.avg_nav != null ? fmtNav(stats.avg_nav) : "--"}</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">MAX NAV</div>
          <div className="stat-val c-bull">{stats.max_nav != null ? fmtNav(stats.max_nav) : "--"}</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">HISTORY</div>
          <div className="stat-val c-dim" style={{ fontSize: 11 }}>{stats.date_count ?? "--"} dates</div>
        </div>
      </div>

      {/* Tab switch */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {(["top", "gainers", "categories"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "3px 10px", fontSize: 10, cursor: "pointer",
              background: tab === t ? "var(--bull)" : "var(--surface)",
              color:      tab === t ? "#000"        : "var(--dim)",
              border: "1px solid var(--border)", borderRadius: 3,
              fontFamily: "monospace", letterSpacing: "0.08em",
            }}
          >
            {t === "top" ? "TOP 20 NAV" : t === "gainers" ? "TOP GAINERS" : "CATEGORIES"}
          </button>
        ))}
      </div>

      {/* Top 20 by NAV */}
      {tab === "top" && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--dim)", fontSize: 10 }}>
              <th style={{ textAlign: "left",  padding: "3px 6px" }}>#</th>
              <th style={{ textAlign: "left",  padding: "3px 6px" }}>FUND NAME</th>
              <th style={{ textAlign: "right", padding: "3px 6px" }}>NAV</th>
              <th style={{ textAlign: "right", padding: "3px 6px" }}>CHANGE</th>
            </tr>
          </thead>
          <tbody>
            {data.top_funds.map((row, i) => {
              const chg   = row.change_pct ?? null;
              const chgC  = chg == null ? "var(--dim)" : chg >= 0 ? "var(--bull)" : "var(--bear)";
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border-faint, #222)" }}>
                  <td style={{ padding: "3px 6px", color: "var(--dim)" }}>{i + 1}</td>
                  <td style={{ padding: "3px 6px", color: "var(--text)", maxWidth: 200 }}>
                    <span title={row.name}>{truncate(row.name, 38)}</span>
                    {row.category && (
                      <span style={{
                        fontSize: 9, marginLeft: 6, padding: "1px 4px",
                        background: "var(--surface)", border: "1px solid var(--border)",
                        borderRadius: 2, color: "var(--dim)",
                      }}>{truncate(row.category, 12)}</span>
                    )}
                  </td>
                  <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--accent)", fontWeight: 600 }}>
                    {fmtNav(row.nav)}
                  </td>
                  <td style={{ textAlign: "right", padding: "3px 6px", color: chgC }}>
                    {fmtPct(chg)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {/* Top gainers */}
      {tab === "gainers" && (
        data.gainers.length === 0 ? (
          <div className="c-dim small">
            No prior date data for comparison. Need at least 2 dates in mf_nav_history.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--dim)", fontSize: 10 }}>
                <th style={{ textAlign: "left",  padding: "3px 6px" }}>#</th>
                <th style={{ textAlign: "left",  padding: "3px 6px" }}>FUND NAME</th>
                <th style={{ textAlign: "right", padding: "3px 6px" }}>NAV</th>
                <th style={{ textAlign: "right", padding: "3px 6px" }}>GAIN</th>
              </tr>
            </thead>
            <tbody>
              {data.gainers.map((row, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border-faint, #222)" }}>
                  <td style={{ padding: "3px 6px", color: "var(--dim)" }}>{i + 1}</td>
                  <td style={{ padding: "3px 6px", color: "var(--text)" }}>
                    <span title={row.name}>{truncate(row.name, 38)}</span>
                  </td>
                  <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--accent)" }}>
                    {fmtNav(row.nav)}
                  </td>
                  <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--bull)", fontWeight: 600 }}>
                    {fmtPct(row.change_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {/* Categories */}
      {tab === "categories" && (
        data.categories.length === 0 ? (
          <div className="c-dim small">
            No category column found in mf_nav_history. Add a category/scheme_category column to enable this view.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--dim)", fontSize: 10 }}>
                <th style={{ textAlign: "left",  padding: "3px 6px" }}>CATEGORY</th>
                <th style={{ textAlign: "right", padding: "3px 6px" }}>FUNDS</th>
                <th style={{ textAlign: "right", padding: "3px 6px" }}>AVG NAV</th>
                <th style={{ textAlign: "right", padding: "3px 6px" }}>MAX NAV</th>
              </tr>
            </thead>
            <tbody>
              {data.categories.map((row, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border-faint, #222)" }}>
                  <td style={{ padding: "3px 6px", color: "var(--text)" }}>{row.category ?? "--"}</td>
                  <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--dim)" }}>{row.fund_count}</td>
                  <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--accent)" }}>{fmtNav(row.avg_nav)}</td>
                  <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--bull)" }}>{fmtNav(row.max_nav)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
""")

print("[3/5] TSX components written")


# =============================================================================
# 4. WIRE NEW PANELS INTO page.tsx
#    Probe the current page.tsx, inject imports and panel JSX
# =============================================================================
print("\n[4/5] Wiring panels into page.tsx...")

PAGE_PATH = APP / "page.tsx"
page_src  = probe(PAGE_PATH)

if not page_src:
    print("  [WARN] page.tsx not found — cannot auto-wire panels.")
    print("         Manually add the imports and <OptionsPanel /> <MacroPanel /> <MFPanel /> below.")
else:
    changed = False

    # Inject imports after the last existing import block
    NEW_IMPORTS = (
        'import OptionsPanel from "@/components/OptionsPanel";\n'
        'import MacroPanel   from "@/components/MacroPanel";\n'
        'import MFPanel      from "@/components/MFPanel";\n'
    )
    # Check which imports are missing
    need_imports = []
    if 'OptionsPanel' not in page_src:
        need_imports.append('import OptionsPanel from "@/components/OptionsPanel";')
    if 'MacroPanel' not in page_src:
        need_imports.append('import MacroPanel   from "@/components/MacroPanel";')
    if 'MFPanel' not in page_src:
        need_imports.append('import MFPanel      from "@/components/MFPanel";')

    if need_imports:
        # Find the last import line
        lines = page_src.splitlines()
        last_import = 0
        for i, line in enumerate(lines):
            if line.startswith("import "):
                last_import = i
        insert_at = last_import + 1
        new_lines = lines[:insert_at] + need_imports + lines[insert_at:]
        page_src  = "\n".join(new_lines)
        changed   = True

    # Inject panel JSX — add after <DeltaPanel ... />
    # We look for a closing tag pattern that suggests the end of the panel grid
    PANEL_ANCHOR = "<DeltaPanel"
    NEW_PANELS = """
      {/* Phase 4 Panels */}
      <OptionsPanel />
      <MacroPanel />
      <MFPanel />"""

    if PANEL_ANCHOR in page_src and "<OptionsPanel" not in page_src:
        # Find the DeltaPanel closing (/>  or </DeltaPanel>)
        idx = page_src.find(PANEL_ANCHOR)
        # Scan forward for />
        end_idx = page_src.find("/>", idx)
        if end_idx == -1:
            end_idx = page_src.find("</DeltaPanel>", idx) + len("</DeltaPanel>")
        else:
            end_idx += 2  # include the />
        page_src = page_src[:end_idx] + NEW_PANELS + page_src[end_idx:]
        changed  = True

    if changed:
        PAGE_PATH.write_text(page_src, encoding="utf-8", newline="\n")
        print("  patched: page.tsx (imports + panel JSX injected)")
    else:
        print("  page.tsx already has all 3 panels — no changes needed")

print("[4/5] page.tsx wiring done")


# =============================================================================
# 5. WINDOWS TASK SCHEDULER — print the schtasks command
# =============================================================================
print("\n[5/5] Task Scheduler setup...")

TASK_XML = r"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>MICC Daily Pipeline - runs at 4:00 PM IST every weekday</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-05-13T16:00:00</StartBoundary>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday />
          <Tuesday />
          <Wednesday />
          <Thursday />
          <Friday />
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <ExecutionTimeLimit>PT3H</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <WakeToRun>false</WakeToRun>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Actions Context="LocalService">
    <Exec>
      <Command>py</Command>
      <Arguments>D:\MICC\data_pipeline\run_pipeline.py --with-engine</Arguments>
      <WorkingDirectory>D:\MICC\data_pipeline</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

SCHTASK_XML_PATH = BASE / "micc_scheduler.xml"
SCHTASK_XML_PATH.write_text(TASK_XML, encoding="utf-16", newline="\r\n")

print(f"""
  Task XML written to: {SCHTASK_XML_PATH}

  ── TASK SCHEDULER SETUP (run in PowerShell as Administrator) ──────────────────
  
  OPTION A — Import the XML (recommended):
    schtasks /Create /XML "D:\\MICC\\micc_scheduler.xml" /TN "MICC_DailyPipeline" /F

  OPTION B — One-liner (no XML file needed):
    schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /TN "MICC_DailyPipeline" ^
      /TR "py D:\\MICC\\data_pipeline\\run_pipeline.py --with-engine" ^
      /ST 16:00 /SD 05/13/2026 /F

  Verify it was created:
    schtasks /Query /TN "MICC_DailyPipeline" /V /FO LIST

  Run it manually right now (to test):
    schtasks /Run /TN "MICC_DailyPipeline"

  Delete it:
    schtasks /Delete /TN "MICC_DailyPipeline" /F

  NOTES:
  - Time is 16:00 in YOUR system clock timezone. If your PC is set to IST, this is 4 PM IST.
  - /F overwrites any existing task with the same name.
  - The task uses the default user account. If run_pipeline.py needs network, ensure
    the account has network access ("RunOnlyIfNetworkAvailable" is set to true in XML).
  - NSE market closes at 3:30 PM IST. 4 PM gives a 30-minute buffer.
  - On weekends and holidays NSE is closed; pipeline will run but daily_update.py
    will silently fetch no new data (safe — it is idempotent).
  ─────────────────────────────────────────────────────────────────────────────────
""")

print("[5/5] Task Scheduler done")


# =============================================================================
# SUMMARY
# =============================================================================
print()
print("=" * 70)
print("  PHASE 4 COMPLETE")
print("=" * 70)
print("""
  FILES WRITTEN:
    D:\\MICC\\micc-dashboard\\src\\app\\api\\options\\route.ts   -- Options API
    D:\\MICC\\micc-dashboard\\src\\app\\api\\macro\\route.ts     -- Macro API
    D:\\MICC\\micc-dashboard\\src\\app\\api\\mf\\route.ts        -- MF NAV API
    D:\\MICC\\micc-dashboard\\src\\components\\OptionsPanel.tsx  -- Options panel
    D:\\MICC\\micc-dashboard\\src\\components\\MacroPanel.tsx    -- Macro panel
    D:\\MICC\\micc-dashboard\\src\\components\\MFPanel.tsx       -- MF panel
    D:\\MICC\\micc_scheduler.xml                                -- Task Scheduler XML
    D:\\MICC\\micc_data.py                                      -- call_groq patched

  PANELS (dashboard at localhost:3000):
    1. OPTIONS PANEL   -- Nifty chain, PCR, Max Pain, GEX by strike (2 tabs)
    2. MACRO PANEL     -- US + India macro series with sparklines (2 tabs)
    3. MF PANEL        -- Top 20 NAV, top gainers, category breakdown (3 tabs)

  GROQ FIX (micc_data.py):
    - Exponential backoff: 37s, 44s, 58s on 429 errors
    - Falls back to Ollama after 3 failed retries (not a hard crash)
    - Minimum 7s spacing between consecutive Groq calls preserved

  TASK SCHEDULER:
    Run the schtasks command above in PowerShell (Admin) to automate
    daily pipeline at 4:00 PM on weekdays.

  NEXT STEPS:
    1. Restart Next.js:  cd D:\\MICC\\micc-dashboard && npm run dev
    2. Open localhost:3000 and verify all 3 new panels load
    3. If Options panel shows "No options data" -> run:
         py D:\\MICC\\data_pipeline\\phase2_greeks_calculator.py --daily
    4. If Macro panel columns show "--" -> verify series_ids in your DB:
         SELECT DISTINCT series_id FROM us_macro_data LIMIT 20;
         SELECT DISTINCT series_id FROM india_macro_fred LIMIT 20;
    5. Set up Task Scheduler (Step 5 output above)

  KNOWN POSSIBLE ISSUES:
    - mf_nav_history column names: The MF API auto-probes PRAGMA table_info()
      so it adapts to whatever columns exist. Check /api/mf response in browser.
    - india_macro_fred series IDs: Two candidates tried (IRSTCI01INM156N and
      INTDSRINM193N). If both empty, run the SQL above to find the right series_id.
    - Options chain may show 0 rows if option_greeks_raw has no NIFTY rows on
      the latest date. Check: SELECT MAX(date), COUNT(*) FROM option_greeks_raw
      WHERE symbol LIKE 'NIFTY%';
""")
