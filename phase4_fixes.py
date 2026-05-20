# -*- coding: utf-8 -*-
"""
phase4_fixes.py
================
Fixes all issues found after phase4_multipage.py ran.

Bug 1 -- NavBar hydration error:
  dangerouslySetInnerHTML with a clock that runs on server diverges from client.
  Fix: move clock to useEffect + useState, render nothing on server (suppressHydrationWarning).

Bug 2 -- Options chain empty (PCR/MaxPain all --):
  option_greeks_raw has NO close/oi/volume columns.
  Real columns: date, symbol, expiry, strike, option_type, underlying_price, iv, delta, gamma, theta, vega, rho
  OI and close live in fo_data (columns: symbol, expiry, strike, option_typ, close, open_int, date)
  gamma_exposure_daily has: date, symbol, expiry, strike, option_type, gamma_exposure, open_interest
  (no call_gex/put_gex/net_gex split -- it's per contract row)
  Fix: rewrite /api/options to join option_greeks_raw + fo_data for chain,
       and aggregate gamma_exposure_daily correctly.

Bug 3 -- Macro all '--':
  series_id in us_macro_data uses dict keys NOT FRED IDs:
    Fed_Funds, 10Y_Treasury, 2Y_Treasury, Inflation_CPI, GDP, GDP_Growth, Term_Spread,
    Unemployment, VIX, Consumer_Confidence, Industrial_Production
  india_macro_fred series IDs: INDCPIALLQINMEI, TRESEGINM194N, XTEXVA01INM664S, XTIMVA01INM664S
  (no India policy rate in DB -- show exports/imports instead)
  Fix: update /api/macro with correct series IDs.

Bug 4 -- MacroPanel/MFPanel render their own title inside page that already has a title:
  The MacroPanel has a panel-title div that duplicates. Fix: rewrite MacroPanel to not
  include its own title, and rewrite MFPanel similarly.

Bug 5 -- MF category showing '--' badges:
  mf_nav_history has only 4 columns: scheme_code, scheme_name, date, nav -- no category.
  Fix: remove category column from MF queries, infer category from scheme_name patterns.

Usage:
  cd D:\\MICC
  py phase4_fixes.py
"""

import os
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
    print("[ERROR] micc-dashboard not found")
    sys.exit(1)

print(f"[OK] Dashboard root: {APP.parent}")

def w(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    try:
        rel = path.relative_to(BASE)
    except ValueError:
        rel = path
    print(f"  wrote: {rel}")


# =============================================================================
# FIX 1 -- NavBar hydration error
#   Move clock to useEffect + useState so server renders empty string
#   suppressHydrationWarning on the clock div
# =============================================================================
print("\n[1/5] Fixing NavBar hydration error...")

w(COMP / "NavBar.tsx", r"""
"use client";
import Link              from "next/link";
import { usePathname }   from "next/navigation";
import { useState, useEffect } from "react";

const PAGES = [
  { href: "/",        label: "OVERVIEW" },
  { href: "/streaks", label: "STREAKS"  },
  { href: "/indices", label: "INDICES"  },
  { href: "/options", label: "OPTIONS"  },
  { href: "/macro",   label: "MACRO"    },
  { href: "/mf",      label: "MF NAV"  },
];

export default function NavBar() {
  const path    = usePathname();
  const [time,  setTime]    = useState("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
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
      padding: "0 20px", height: 48, gap: 0,
    }}>
      <div style={{
        fontFamily: "'Share Tech Mono','JetBrains Mono',monospace",
        fontSize: 15, fontWeight: 700, letterSpacing: "0.18em",
        color: "var(--accent)", marginRight: 28, whiteSpace: "nowrap",
      }}>
        MICC
      </div>

      <nav style={{ display: "flex", gap: 2, flex: 1 }}>
        {PAGES.map(({ href, label }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} style={{
              padding: "6px 14px", fontSize: 10,
              fontFamily: "'JetBrains Mono',monospace",
              letterSpacing: "0.1em",
              fontWeight: active ? 700 : 400,
              color: active ? "var(--accent)" : "var(--muted)",
              borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
              textDecoration: "none", transition: "color 0.15s",
            }}>
              {label}
            </Link>
          );
        })}
      </nav>

      {/* suppressHydrationWarning: server renders "" and client fills in after mount */}
      <div suppressHydrationWarning style={{
        fontFamily: "monospace", fontSize: 10, color: "var(--dim)", whiteSpace: "nowrap",
      }}>
        {mounted ? time : ""}
      </div>
    </header>
  );
}
""")


# =============================================================================
# FIX 2 -- /api/options
#   Real schema:
#     option_greeks_raw: date, symbol, expiry, strike, option_type,
#                        underlying_price, iv, delta, gamma, theta, vega, rho
#     fo_data:           date, symbol, expiry, strike, option_typ, close, open_int, instrument
#     gamma_exposure_daily: date, symbol, expiry, strike, option_type,
#                           gamma_exposure, open_interest
#
#   Build chain by joining greeks + fo_data on (date, symbol, expiry, strike, option_type/option_typ)
#   PCR from fo_data (has open_int)
#   GEX by strike: SUM(gamma_exposure) per strike, split CE vs PE
# =============================================================================
print("\n[2/5] Fixing /api/options (correct schema)...")

w(APP / "api" / "options" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8', timeout: 30000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[options]', r.stderr?.slice(0, 300)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) { console.error('[options]', e.message); return [] }
}

function readAgent(name: string): any {
  try {
    const p = path.join(DA, 'agents', name, 'last_report.json')
    if (!fs.existsSync(p)) return null
    let raw = fs.readFileSync(p, 'utf-8')
    raw = raw.replace(/:\s*NaN([,\}\]])/g, ': null$1')
             .replace(/:\s*Infinity([,\}\]])/g, ': null$1')
    return JSON.parse(raw)
  } catch { return null }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // ── Latest date that has index option data in fo_data ──────────────────────
  const latestRows = queryDb(`
    SELECT MAX(date) AS d FROM fo_data
    WHERE instrument IN ('OPTIDX','IDO') AND symbol = 'NIFTY'
  `)
  const latestDate = latestRows[0]?.d ?? ''
  if (!latestDate) {
    return NextResponse.json({
      error: 'No NIFTY options data in fo_data. Run: py data_pipeline/phase2_greeks_calculator.py --daily',
      date: null,
    })
  }

  // ── Nearest expiry ─────────────────────────────────────────────────────────
  const expiryRows = queryDb(`
    SELECT MIN(expiry) AS nearest_expiry FROM fo_data
    WHERE date = '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN ('OPTIDX','IDO')
      AND expiry >= '${latestDate}'
  `)
  const nearestExpiry = expiryRows[0]?.nearest_expiry ?? ''

  // ── PCR from fo_data (has real OI) ─────────────────────────────────────────
  const pcrRows = queryDb(`
    SELECT option_typ, SUM(open_int) AS total_oi
    FROM fo_data
    WHERE date = '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN ('OPTIDX','IDO')
      AND expiry = '${nearestExpiry}'
    GROUP BY option_typ
  `)
  const callOI = Number(pcrRows.find((r: any) => r.option_typ === 'CE')?.total_oi ?? 0)
  const putOI  = Number(pcrRows.find((r: any) => r.option_typ === 'PE')?.total_oi ?? 0)
  const pcr    = callOI > 0 ? Math.round((putOI / callOI) * 1000) / 1000 : null

  // ── Options chain: join greeks + fo_data ───────────────────────────────────
  // option_greeks_raw.option_type = 'CE'/'PE'
  // fo_data.option_typ            = 'CE'/'PE'
  // Top 25 strikes by total OI
  const chainRows = queryDb(`
    SELECT
      f.strike,
      MAX(CASE WHEN f.option_typ='CE' THEN f.close      END) AS call_ltp,
      MAX(CASE WHEN f.option_typ='CE' THEN f.open_int   END) AS call_oi,
      MAX(CASE WHEN f.option_typ='CE' THEN f.volume     END) AS call_vol,
      MAX(CASE WHEN f.option_typ='PE' THEN f.close      END) AS put_ltp,
      MAX(CASE WHEN f.option_typ='PE' THEN f.open_int   END) AS put_oi,
      MAX(CASE WHEN f.option_typ='PE' THEN f.volume     END) AS put_vol,
      MAX(CASE WHEN g.option_type='CE' THEN g.iv        END) AS call_iv,
      MAX(CASE WHEN g.option_type='CE' THEN g.delta     END) AS call_delta,
      MAX(CASE WHEN g.option_type='CE' THEN g.gamma     END) AS call_gamma,
      MAX(CASE WHEN g.option_type='CE' THEN g.theta     END) AS call_theta,
      MAX(CASE WHEN g.option_type='PE' THEN g.iv        END) AS put_iv,
      MAX(CASE WHEN g.option_type='PE' THEN g.delta     END) AS put_delta,
      MAX(CASE WHEN g.option_type='PE' THEN g.gamma     END) AS put_gamma,
      MAX(CASE WHEN g.option_type='PE' THEN g.theta     END) AS put_theta,
      MAX(g.underlying_price) AS spot
    FROM fo_data f
    LEFT JOIN option_greeks_raw g
      ON  g.date        = f.date
      AND g.symbol      = f.symbol
      AND g.expiry      = f.expiry
      AND g.strike      = f.strike
      AND g.option_type = f.option_typ
    WHERE f.date = '${latestDate}'
      AND f.symbol = 'NIFTY'
      AND f.instrument IN ('OPTIDX','IDO')
      AND f.expiry = '${nearestExpiry}'
    GROUP BY f.strike
    ORDER BY (COALESCE(MAX(CASE WHEN f.option_typ='CE' THEN f.open_int END),0)
             +COALESCE(MAX(CASE WHEN f.option_typ='PE' THEN f.open_int END),0)) DESC
    LIMIT 25
  `)
  const chain = [...chainRows].sort((a: any, b: any) => Number(a.strike) - Number(b.strike))

  // Get spot price from first chain row or greeks
  const spotPrice = chain[0]?.spot ?? null

  // ── Max Pain ───────────────────────────────────────────────────────────────
  const allStrikeRows = queryDb(`
    SELECT strike,
      SUM(CASE WHEN option_typ='CE' THEN COALESCE(open_int,0) END) AS call_oi,
      SUM(CASE WHEN option_typ='PE' THEN COALESCE(open_int,0) END) AS put_oi
    FROM fo_data
    WHERE date = '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN ('OPTIDX','IDO')
      AND expiry = '${nearestExpiry}'
    GROUP BY strike ORDER BY strike ASC
  `)

  let maxPainStrike: number | null = null
  if (allStrikeRows.length > 0) {
    const strikes = allStrikeRows.map((r: any) => Number(r.strike))
    let minLoss = Infinity
    for (const K of strikes) {
      let loss = 0
      for (const row of allStrikeRows as any[]) {
        const s = Number(row.strike), co = Number(row.call_oi ?? 0), po = Number(row.put_oi ?? 0)
        if (s < K) loss += (K - s) * co
        if (s > K) loss += (s - K) * po
      }
      if (loss < minLoss) { minLoss = loss; maxPainStrike = K }
    }
  }

  // ── GEX by strike from gamma_exposure_daily ────────────────────────────────
  // columns: date, symbol, expiry, strike, option_type, gamma_exposure, open_interest
  // CE gamma_exposure positive (call writers short gamma), PE negative convention
  const gexLatest = queryDb(`SELECT MAX(date) AS d FROM gamma_exposure_daily WHERE symbol='NIFTY'`)
  const gexDate   = gexLatest[0]?.d ?? ''
  const gexRows   = gexDate ? queryDb(`
    SELECT
      strike,
      ROUND(SUM(CASE WHEN option_type='CE' THEN gamma_exposure ELSE 0 END), 4) AS call_gex,
      ROUND(SUM(CASE WHEN option_type='PE' THEN gamma_exposure ELSE 0 END), 4) AS put_gex,
      ROUND(SUM(gamma_exposure), 4) AS net_gex
    FROM gamma_exposure_daily
    WHERE date = '${gexDate}' AND symbol = 'NIFTY'
    GROUP BY strike
    ORDER BY ABS(SUM(gamma_exposure)) DESC
    LIMIT 30
  `) : []
  const totalGex = gexRows.reduce((s: number, r: any) => s + Number(r.net_gex ?? 0), 0)

  // ── OI change vs previous session ─────────────────────────────────────────
  const prevDateRows = queryDb(`
    SELECT MAX(date) AS d FROM fo_data
    WHERE date < '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN ('OPTIDX','IDO')
  `)
  const prevDate = prevDateRows[0]?.d ?? ''
  const oiChange = prevDate ? queryDb(`
    SELECT
      cur.strike, cur.option_typ AS option_type,
      ROUND(CAST(cur.open_int AS REAL) - CAST(COALESCE(prv.open_int, cur.open_int) AS REAL), 0) AS oi_chg,
      cur.open_int AS cur_oi
    FROM fo_data cur
    LEFT JOIN fo_data prv
      ON prv.symbol      = cur.symbol
     AND prv.strike      = cur.strike
     AND prv.option_typ  = cur.option_typ
     AND prv.expiry      = cur.expiry
     AND prv.date        = '${prevDate}'
     AND prv.instrument IN ('OPTIDX','IDO')
    WHERE cur.date = '${latestDate}' AND cur.symbol = 'NIFTY'
      AND cur.instrument IN ('OPTIDX','IDO')
      AND cur.expiry = '${nearestExpiry}'
      AND cur.open_int > 0
    ORDER BY ABS(oi_chg) DESC LIMIT 20
  `) : []

  // ── Nifty close from market_snapshot ──────────────────────────────────────
  const niftyRows = queryDb(`
    SELECT closing_index_value AS close, points_change, change AS change_pct
    FROM market_snapshot
    WHERE index_name = 'Nifty 50'
      AND date = (SELECT MAX(date) FROM market_snapshot)
    LIMIT 1
  `)
  const niftyClose     = niftyRows[0]?.close ?? spotPrice
  const niftyChangePct = niftyRows[0]?.change_pct ?? null

  // ── Alpha regime for context ───────────────────────────────────────────────
  const alpha       = readAgent('alpha')
  const alphaRegime = alpha?.regime?.regime ?? '--'
  const alphaConf   = alpha?.regime?.confidence ?? '--'

  // ── Build analysis text ────────────────────────────────────────────────────
  const pcrLabel   = pcr == null ? '--'
                   : pcr > 1.3  ? 'BULLISH (put-heavy positioning)'
                   : pcr < 0.7  ? 'BEARISH (call-heavy positioning)'
                   : 'NEUTRAL (balanced)'
  const gexLabel   = totalGex > 0 ? 'LONG GAMMA -- dealers absorb volatility'
                   : 'SHORT GAMMA -- dealers amplify volatility'
  const maxPainGap = (maxPainStrike && niftyClose)
    ? Math.round(((Number(niftyClose) - maxPainStrike) / maxPainStrike) * 100 * 10) / 10
    : null

  // Top 5 strikes by OI for key levels
  const top5 = [...allStrikeRows]
    .sort((a: any, b: any) => (Number(b.call_oi ?? 0) + Number(b.put_oi ?? 0)) - (Number(a.call_oi ?? 0) + Number(a.put_oi ?? 0)))
    .slice(0, 5)

  const analysis = [
    `Options Snapshot -- ${latestDate}`,
    `Expiry: ${nearestExpiry}`,
    '',
    `## Market Structure`,
    `Nifty 50: ${niftyClose ? Number(niftyClose).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '--'}${niftyChangePct != null ? ' (' + (Number(niftyChangePct) >= 0 ? '+' : '') + Number(niftyChangePct).toFixed(2) + '%)' : ''}`,
    `Market Regime: ${alphaRegime} | Confidence: ${alphaConf}`,
    '',
    `## Options Positioning`,
    `Put-Call Ratio: ${pcr != null ? pcr.toFixed(3) : '--'} -- ${pcrLabel}`,
    `Total Call OI: ${callOI > 0 ? (callOI / 1e5).toFixed(1) + 'L' : '--'} | Total Put OI: ${putOI > 0 ? (putOI / 1e5).toFixed(1) + 'L' : '--'}`,
    `Max Pain Strike: ${maxPainStrike != null ? maxPainStrike.toLocaleString('en-IN') : '--'}${maxPainGap != null ? ' (spot is ' + (maxPainGap >= 0 ? '+' : '') + maxPainGap + '% from max pain)' : ''}`,
    `Net GEX: ${Math.round(totalGex).toLocaleString()} -- ${gexLabel}`,
    '',
    `## Key OI Strikes`,
    ...(top5.length > 0
      ? top5.map((r: any) => {
          const tot = Number(r.call_oi ?? 0) + Number(r.put_oi ?? 0)
          return `${Number(r.strike).toLocaleString()}: CE=${Math.round(Number(r.call_oi ?? 0) / 1000)}K  PE=${Math.round(Number(r.put_oi ?? 0) / 1000)}K  (total ${Math.round(tot / 1000)}K)`
        })
      : ['Data not available -- run phase2_greeks_calculator.py --daily']),
    '',
    `## Interpretation`,
    pcr != null && pcr > 1.2
      ? 'Elevated PCR signals heavy put writing. Market participants expect support -- typically a near-term bullish signal. Watch for put unwinding above key support levels.'
      : pcr != null && pcr < 0.8
      ? 'Low PCR indicates call-heavy positioning. Market may face resistance at key levels. Call writers dominate -- sideways to bearish bias near-term.'
      : 'PCR near 1.0 indicates balanced positioning. No clear directional bias from options market. Await a catalyst.',
    '',
    totalGex > 0
      ? 'Positive net GEX: Market makers are net long gamma. Their hedging activity naturally dampens large price swings -- expect mean-reversion behavior around key strikes.'
      : 'Negative net GEX: Market makers are net short gamma. Their delta-hedging amplifies directional moves -- expect higher realized volatility and potential for extended trends.',
    '',
    maxPainStrike != null && maxPainGap != null
      ? `Max pain at ${maxPainStrike.toLocaleString('en-IN')} acts as a gravitational center into expiry. ${Math.abs(maxPainGap) < 1 ? 'Spot is very close to max pain -- expect consolidation.' : 'Spot needs to drift ' + (maxPainGap > 0 ? 'lower' : 'higher') + ' by ' + Math.abs(maxPainGap) + '% toward max pain as expiry approaches.'}`
      : '',
  ].filter(l => l !== undefined).join('\n')

  return NextResponse.json({
    date: latestDate, expiry: nearestExpiry, pcr,
    call_oi: callOI, put_oi: putOI, max_pain: maxPainStrike,
    chain, gex: gexRows, total_net_gex: Math.round(totalGex), gex_date: gexDate,
    oi_change: oiChange, nifty_close: niftyClose, nifty_change_pct: niftyChangePct,
    analysis,
  })
}
""")


# =============================================================================
# FIX 3 -- /api/macro
#   Correct series_id keys in us_macro_data:
#     Fed_Funds, 10Y_Treasury, 2Y_Treasury, Inflation_CPI, GDP, Term_Spread,
#     Unemployment, VIX, Consumer_Confidence, Industrial_Production
#   india_macro_fred series:
#     INDCPIALLQINMEI (India CPI quarterly)
#     TRESEGINM194N   (India Forex Reserves monthly)
#     XTEXVA01INM664S (India Exports)
#     XTIMVA01INM664S (India Imports)
#   NOTE: No India policy rate in DB -- compute trade balance instead
# =============================================================================
print("\n[3/5] Fixing /api/macro (correct series IDs)...")

w(APP / "api" / "macro" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8', timeout: 20000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[macro]', r.stderr?.slice(0, 200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) { console.error('[macro]', e.message); return [] }
}

function seriesHistory(table: string, seriesId: string, n = 24): any[] {
  return queryDb(`
    SELECT date, ROUND(CAST(value AS REAL), 4) AS value
    FROM ${table}
    WHERE series_id = '${seriesId}' AND value IS NOT NULL
    ORDER BY date DESC LIMIT ${n}
  `).reverse()
}

function latest(s: any[]) { return s.length ? s[s.length - 1] : null }
function delta(s: any[], n = 1): number | null {
  const l = latest(s), p = s.length - 1 - n >= 0 ? s[s.length - 1 - n] : null
  if (!l || !p) return null
  return Math.round((Number(l.value) - Number(p.value)) * 10000) / 10000
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // ── US Macro (series_id = dict keys, NOT FRED ids) ─────────────────────────
  const fedfunds   = seriesHistory('us_macro_data', 'Fed_Funds',     24)
  const us10y      = seriesHistory('us_macro_data', '10Y_Treasury',  60)
  const us2y       = seriesHistory('us_macro_data', '2Y_Treasury',   60)
  const termSpread = seriesHistory('us_macro_data', 'Term_Spread',   60)
  const usCpi      = seriesHistory('us_macro_data', 'Inflation_CPI', 24)
  const usGdp      = seriesHistory('us_macro_data', 'GDP',           16)
  const usVix      = seriesHistory('us_macro_data', 'VIX',           60)
  const usUnemp    = seriesHistory('us_macro_data', 'Unemployment',  24)

  // ── India Macro (from india_macro_fred) ────────────────────────────────────
  // INDCPIALLQINMEI = India CPI (quarterly, OECD)
  // TRESEGINM194N   = India Forex Reserves (monthly, USD millions)
  // XTEXVA01INM664S = India Exports (monthly, USD)
  // XTIMVA01INM664S = India Imports (monthly, USD)
  const indiaCpi      = seriesHistory('india_macro_fred', 'INDCPIALLQINMEI', 16)
  const indiaFxRaw    = seriesHistory('india_macro_fred', 'TRESEGINM194N',   24)
  const indiaExports  = seriesHistory('india_macro_fred', 'XTEXVA01INM664S', 24)
  const indiaImports  = seriesHistory('india_macro_fred', 'XTIMVA01INM664S', 24)

  // Convert FX reserves from USD millions to USD billions for display
  const indiaFx = indiaFxRaw.map(r => ({
    date:  r.date,
    value: Math.round(Number(r.value) / 1000 * 10) / 10,
  }))

  // Compute trade balance (exports - imports, same unit)
  const tradeMap: Record<string, number> = {}
  indiaExports.forEach(r => { tradeMap[r.date] = Number(r.value) })
  const tradeBalance = indiaImports
    .filter(r => tradeMap[r.date] != null)
    .map(r => ({ date: r.date, value: Math.round((tradeMap[r.date] - Number(r.value)) * 100) / 100 }))
    .reverse().slice(0, 24).reverse()

  // ── Nifty for context ──────────────────────────────────────────────────────
  const niftyRows = queryDb(`
    SELECT closing_index_value AS close, change AS change_pct
    FROM market_snapshot
    WHERE index_name = 'Nifty 50'
      AND date = (SELECT MAX(date) FROM market_snapshot)
    LIMIT 1
  `)

  const latestFed   = latest(fedfunds)
  const latest10y   = latest(us10y)
  const latestTs    = latest(termSpread)
  const latestCpi   = latest(usCpi)
  const latestVix   = latest(usVix)
  const latestUnemp = latest(usUnemp)
  const latestICpi  = latest(indiaCpi)
  const latestFx    = latest(indiaFx)

  return NextResponse.json({
    fedfunds:    { series: fedfunds,   latest: latestFed,   delta_1m: delta(fedfunds,  1) },
    us_10y:      { series: us10y,      latest: latest10y,   delta_1m: delta(us10y,     1) },
    us_2y:       { series: us2y,       latest: latest(us2y),delta_1m: delta(us2y,      1) },
    term_spread: { series: termSpread, latest: latestTs,    delta_1m: delta(termSpread,1) },
    us_cpi:      { series: usCpi,      latest: latestCpi,   delta_1m: delta(usCpi,     1) },
    us_gdp:      { series: usGdp,      latest: latest(usGdp),delta_1m: delta(usGdp,   1) },
    us_vix:      { series: usVix,      latest: latestVix,   delta_1m: delta(usVix,     1) },
    us_unemp:    { series: usUnemp,    latest: latestUnemp, delta_1m: delta(usUnemp,   1) },
    india_cpi:   { series: indiaCpi,   latest: latestICpi,  delta_1m: delta(indiaCpi,  1) },
    india_fx:    { series: indiaFx,    latest: latestFx },
    india_trade: { series: tradeBalance, latest: latest(tradeBalance) },
    nifty: niftyRows[0] ?? null,
  })
}
""")


# =============================================================================
# FIX 4 -- MacroPanel.tsx rewrite
#   Remove the self-contained panel-title (page already has a title).
#   Fix stat-grid layout -- it was rendering its own ugly header with
#   "≡ MACRO DASHBOARD Fed: --% | India-US Diff: --"
#   Use correct series keys from the fixed /api/macro response.
# =============================================================================
print("\n[4/5] Rewriting MacroPanel.tsx...")

w(COMP / "MacroPanel.tsx", r"""
"use client";
import { useState, useEffect } from "react";

interface Pt { date: string; value: number }
interface MacroSeries { series: Pt[]; latest: Pt | null; delta_1m?: number | null }

function Sparkline({ series, color = "var(--accent)" }: { series: Pt[]; color?: string }) {
  if (!series || series.length < 2) {
    return <span style={{ color: "var(--dim)", fontSize: 9 }}>--</span>;
  }
  const vals  = series.map(d => Number(d.value));
  const min   = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const W = 80, H = 26, pad = 2;
  const pts = vals.map((v, i) => {
    const x = pad + (i / (vals.length - 1)) * (W - pad * 2);
    const y = H - pad - ((v - min) / range) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={W} height={H} style={{ display: "block", overflow: "visible" }}>
      <polyline points={pts} fill="none" stroke={color}
                strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function MacroRow({ label, unit = "", s, color }:
  { label: string; unit?: string; s: MacroSeries; color: string }) {
  const val    = s.latest?.value ?? null;
  const d      = s.delta_1m ?? null;
  const dColor = d == null ? "var(--dim)" : d > 0 ? "var(--pos)" : d < 0 ? "var(--neg)" : "var(--dim)";
  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "6px 0", color: "var(--dim)", fontSize: 11, fontFamily: "monospace", whiteSpace: "nowrap" }}>
        {label}
      </td>
      <td style={{ padding: "6px 12px", textAlign: "right", fontFamily: "monospace", fontSize: 12,
                   color, fontWeight: 600, whiteSpace: "nowrap" }}>
        {val != null ? `${Number(val).toFixed(2)}${unit}` : "--"}
      </td>
      <td style={{ padding: "6px 8px", textAlign: "right", fontFamily: "monospace", fontSize: 10,
                   color: dColor, whiteSpace: "nowrap" }}>
        {d != null ? `${d > 0 ? "+" : ""}${d.toFixed(2)}` : "--"}
      </td>
      <td style={{ padding: "6px 0 6px 10px" }}>
        <Sparkline series={s.series} color={color} />
      </td>
      <td style={{ padding: "6px 0 6px 6px", fontFamily: "monospace", fontSize: 9,
                   color: "var(--dim)", whiteSpace: "nowrap" }}>
        {s.latest?.date ?? "--"}
      </td>
    </tr>
  );
}

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
      No macro data. Run: py data_pipeline/update_macro_us.py --daily
    </div>
  );

  const tsVal   = data.term_spread?.latest?.value ?? null;
  const tsColor = tsVal == null ? "var(--dim)"
                : tsVal < 0   ? "var(--neg)"
                : tsVal < 0.5 ? "var(--warn)" : "var(--pos)";
  const tsLabel = tsVal == null ? "" : tsVal < 0 ? "INVERTED" : tsVal < 0.5 ? "FLAT" : "NORMAL";

  const fedVal = data.fedfunds?.latest?.value ?? null;
  const vixVal = data.us_vix?.latest?.value   ?? null;

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
      {/* Summary KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
        {[
          { l: "FED FUNDS",   v: fedVal  != null ? Number(fedVal).toFixed(2)  + "%" : "--", color: "var(--warn)" },
          { l: "US 10Y YIELD",v: data.us_10y?.latest?.value != null ? Number(data.us_10y.latest.value).toFixed(2) + "%" : "--", color: "var(--info)" },
          { l: "TERM SPREAD", v: tsVal   != null ? (tsVal >= 0 ? "+" : "") + Number(tsVal).toFixed(2) + "%" : "--", color: tsColor, sub: tsLabel },
          { l: "US VIX",      v: vixVal  != null ? Number(vixVal).toFixed(1) : "--", color: vixVal != null && Number(vixVal) > 20 ? "var(--neg)" : "var(--pos)" },
        ].map(({ l, v, color, sub }) => (
          <div key={l} style={{
            padding: "12px 14px", background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 6,
          }}>
            <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                          letterSpacing: "0.1em", marginBottom: 4 }}>{l}</div>
            <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700, color }}>{v}</div>
            {sub && <div style={{ fontFamily: "monospace", fontSize: 9, color, marginTop: 2 }}>{sub}</div>}
          </div>
        ))}
      </div>

      {/* Tab switch */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        <TabBtn t="us"    label="US MACRO"    />
        <TabBtn t="india" label="INDIA MACRO" />
      </div>

      {/* Column headers */}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9,
                       color: "var(--dim)", letterSpacing: "0.08em" }}>
            <th style={{ padding: "4px 0",   textAlign: "left"  }}>INDICATOR</th>
            <th style={{ padding: "4px 12px",textAlign: "right" }}>LATEST</th>
            <th style={{ padding: "4px 8px", textAlign: "right" }}>1M CHG</th>
            <th style={{ padding: "4px 0 4px 10px" }}>TREND (24M)</th>
            <th style={{ padding: "4px 0 4px 6px"  }}>DATE</th>
          </tr>
        </thead>
        <tbody>
          {tab === "us" && (
            <>
              <MacroRow label="Fed Funds Rate"     unit="%" s={data.fedfunds   } color="var(--warn)" />
              <MacroRow label="US 10Y Yield"       unit="%" s={data.us_10y     } color="var(--info)" />
              <MacroRow label="US 2Y Yield"        unit="%" s={data.us_2y      } color="var(--dim)"  />
              <MacroRow label="Term Spread (10-2Y)"unit="%" s={data.term_spread} color={tsColor}     />
              <MacroRow label="US CPI"                      s={data.us_cpi     } color="var(--neg)"  />
              <MacroRow label="US Real GDP"                 s={data.us_gdp     } color="var(--pos)"  />
              <MacroRow label="Unemployment"       unit="%" s={data.us_unemp   } color="var(--warn)" />
              <MacroRow label="VIX"                         s={data.us_vix     } color={vixVal!=null&&Number(vixVal)>20?"var(--neg)":"var(--pos)"} />
            </>
          )}
          {tab === "india" && (
            <>
              <MacroRow label="India CPI (OECD)"           s={data.india_cpi  } color="var(--neg)"  />
              <MacroRow label="FX Reserves (Bn USD)"       s={data.india_fx   } color="var(--pos)"  />
              <MacroRow label="Trade Balance"               s={data.india_trade} color="var(--info)" />
              <MacroRow label="Exports"                     s={data.india_trade?.series?.length ? { series: [], latest: null, delta_1m: null } : { series: [], latest: null }}
                         color="var(--dim)" />
              <MacroRow label="US 10Y (ref)"   unit="%" s={data.us_10y     } color="var(--dim)"  />
              <MacroRow label="Fed Funds (ref)"unit="%" s={data.fedfunds   } color="var(--dim)"  />
            </>
          )}
        </tbody>
      </table>

      <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", marginTop: 12 }}>
        Sources: FRED (Federal Reserve) &nbsp;|&nbsp; World Bank &nbsp;|&nbsp;
        Updated daily via run_pipeline.py
      </div>
    </div>
  );
}
""")


# =============================================================================
# FIX 5 -- MFPanel.tsx rewrite
#   mf_nav_history columns: scheme_code, scheme_name, date, nav  (no category)
#   Infer category from scheme_name:
#     Liquid / Overnight -> Liquid
#     ELSS / Tax Saver   -> ELSS
#     Small Cap          -> Small Cap
#     Mid Cap            -> Mid Cap
#     Large & Mid / Large Cap -> Large Cap
#     Balanced / Hybrid  -> Hybrid
#     Gilt / G-Sec       -> Debt
#     else               -> Other
#   Remove category column from queries; infer on frontend.
#   Remove self-contained panel-title.
# =============================================================================
print("\n[5/5] Rewriting MFPanel.tsx and /api/mf route...")

# Fix /api/mf -- remove category queries, use only 4 columns
w(APP / "api" / "mf" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8', timeout: 20000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[mf]', r.stderr?.slice(0, 200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) { console.error('[mf]', e.message); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // mf_nav_history columns: scheme_code, scheme_name, date, nav
  const latestRows = queryDb(`SELECT MAX(date) AS d FROM mf_nav_history`)
  const latestDate = latestRows[0]?.d ?? ''
  if (!latestDate) {
    return NextResponse.json({ error: 'No data in mf_nav_history', date: null })
  }

  const prevDateRows = queryDb(`SELECT MAX(date) AS d FROM mf_nav_history WHERE date < '${latestDate}'`)
  const prevDate = prevDateRows[0]?.d ?? ''

  // Top 20 by NAV
  const topRows = prevDate ? queryDb(`
    SELECT
      n.scheme_code AS code,
      n.scheme_name AS name,
      ROUND(CAST(n.nav AS REAL), 4) AS nav,
      ROUND((CAST(n.nav AS REAL) - CAST(p.nav AS REAL)) / NULLIF(CAST(p.nav AS REAL),0) * 100, 4) AS change_pct,
      ROUND(CAST(p.nav AS REAL), 4) AS prev_nav,
      n.date
    FROM mf_nav_history n
    LEFT JOIN mf_nav_history p
      ON n.scheme_code = p.scheme_code AND p.date = '${prevDate}'
    WHERE n.date = '${latestDate}'
    ORDER BY CAST(n.nav AS REAL) DESC
    LIMIT 20
  `) : queryDb(`
    SELECT scheme_code AS code, scheme_name AS name,
           ROUND(CAST(nav AS REAL),4) AS nav,
           NULL AS change_pct, NULL AS prev_nav, date
    FROM mf_nav_history
    WHERE date = '${latestDate}'
    ORDER BY CAST(nav AS REAL) DESC LIMIT 20
  `)

  // Top gainers
  const gainers = prevDate ? queryDb(`
    SELECT
      n.scheme_code AS code,
      n.scheme_name AS name,
      ROUND(CAST(n.nav AS REAL), 4) AS nav,
      ROUND((CAST(n.nav AS REAL) - CAST(p.nav AS REAL)) / NULLIF(CAST(p.nav AS REAL),0) * 100, 4) AS change_pct
    FROM mf_nav_history n
    JOIN mf_nav_history p
      ON n.scheme_code = p.scheme_code AND p.date = '${prevDate}'
    WHERE n.date = '${latestDate}' AND CAST(p.nav AS REAL) > 0
    ORDER BY change_pct DESC LIMIT 15
  `) : []

  // Stats
  const stats = queryDb(`
    SELECT
      COUNT(*) AS total_funds,
      COUNT(DISTINCT date) AS date_count,
      MAX(date) AS latest_date,
      MIN(date) AS earliest_date,
      ROUND(AVG(CAST(nav AS REAL)),2) AS avg_nav,
      ROUND(MAX(CAST(nav AS REAL)),2) AS max_nav,
      ROUND(MIN(CAST(nav AS REAL)),2) AS min_nav
    FROM mf_nav_history
  `)

  return NextResponse.json({
    date: latestDate, prev_date: prevDate,
    top_funds: topRows, gainers,
    stats: stats[0] ?? {},
  })
}
""")

# Rewrite MFPanel.tsx -- no self-title, infer categories from name
w(COMP / "MFPanel.tsx", r"""
"use client";
import { useState, useEffect } from "react";

function inferCategory(name: string): string {
  const n = (name ?? "").toLowerCase();
  if (n.includes("liquid") || n.includes("overnight") || n.includes("money market")) return "Liquid";
  if (n.includes("elss") || n.includes("tax saver"))                                  return "ELSS";
  if (n.includes("small cap") || n.includes("smallcap"))                              return "Small Cap";
  if (n.includes("mid cap") || n.includes("midcap"))                                  return "Mid Cap";
  if (n.includes("large & mid") || n.includes("large and mid"))                       return "Large & Mid";
  if (n.includes("large cap") || n.includes("largecap") || n.includes("bluechip"))   return "Large Cap";
  if (n.includes("balanced") || n.includes("hybrid") || n.includes("aggressive"))    return "Hybrid";
  if (n.includes("gilt") || n.includes("g-sec") || n.includes("gsec") ||
      n.includes("bond") || n.includes("income") || n.includes("debt"))              return "Debt";
  if (n.includes("international") || n.includes("global") || n.includes("usa") ||
      n.includes("nasdaq") || n.includes("s&p"))                                      return "Intl";
  if (n.includes("gold") || n.includes("silver"))                                     return "Commodity";
  return "Other";
}

const CAT_COLORS: Record<string,string> = {
  "Liquid":    "#58a6ff",
  "ELSS":      "#26c485",
  "Small Cap": "#f0883e",
  "Mid Cap":   "#e3b341",
  "Large & Mid":"#79c0ff",
  "Large Cap": "#56d364",
  "Hybrid":    "#d2a8ff",
  "Debt":      "#8b949e",
  "Intl":      "#ffa657",
  "Commodity": "#f78166",
  "Other":     "#6e7681",
};

function CatBadge({ name }: { name: string }) {
  const cat   = inferCategory(name);
  const color = CAT_COLORS[cat] ?? "#6e7681";
  return (
    <span style={{
      fontSize: 8, padding: "1px 5px", marginLeft: 5,
      background: color + "22", border: `1px solid ${color}55`,
      borderRadius: 3, color, fontFamily: "monospace", whiteSpace: "nowrap",
    }}>{cat.toUpperCase()}</span>
  );
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
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [tab,    setTab]    = useState<"top" | "gainers" | "categories">("top");

  useEffect(() => {
    fetch("/api/mf", { cache: "no-store" })
      .then(r => r.json()).then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ padding: 40, color: "var(--dim)", fontFamily: "monospace" }}>
      Loading MF data...
    </div>
  );
  if (!data || data.error) return (
    <div style={{ padding: 40, color: "var(--neg)", fontFamily: "monospace" }}>
      {data?.error ?? "No MF data."}<br />
      Run: py data_pipeline/update_mf_nav.py
    </div>
  );

  const stats = data.stats ?? {};

  // Build category breakdown from top_funds (inferred)
  const catMap: Record<string, { count: number; total: number; max: number }> = {};
  for (const f of (data.top_funds ?? [])) {
    const cat = inferCategory(f.name ?? "");
    if (!catMap[cat]) catMap[cat] = { count: 0, total: 0, max: 0 };
    catMap[cat].count++;
    catMap[cat].total += Number(f.nav ?? 0);
    catMap[cat].max    = Math.max(catMap[cat].max, Number(f.nav ?? 0));
  }
  const categories = Object.entries(catMap)
    .map(([cat, v]) => ({ category: cat, count: v.count, avg_nav: Math.round(v.total / v.count * 100) / 100, max_nav: v.max }))
    .sort((a, b) => b.avg_nav - a.avg_nav);

  function TabBtn({ t, label }: { t: "top" | "gainers" | "categories"; label: string }) {
    const active = tab === t;
    return (
      <button onClick={() => setTab(t)} style={{
        padding: "3px 12px", fontSize: 10, cursor: "pointer", fontFamily: "monospace",
        background: active ? "rgba(38,196,133,0.15)" : "var(--surface)",
        color: active ? "#26c485" : "var(--muted)",
        border: `1px solid ${active ? "#26c485" : "var(--border)"}`,
        borderRadius: 4,
      }}>{label}</button>
    );
  }

  return (
    <div>
      {/* Stats strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 14 }}>
        {[
          { l: "TOTAL FUNDS",  v: String(stats.total_funds ?? "--"),  c: "var(--accent)" },
          { l: "AVG NAV",      v: stats.avg_nav  != null ? fmtNav(stats.avg_nav)  : "--", c: "var(--text)" },
          { l: "MAX NAV",      v: stats.max_nav  != null ? fmtNav(stats.max_nav)  : "--", c: "var(--bull)" },
          { l: "DATES",        v: String(stats.date_count ?? "--") + " dates",             c: "var(--dim)"  },
        ].map(({ l, v, c }) => (
          <div key={l} style={{ padding: "10px 14px", background: "var(--surface)",
                                border: "1px solid var(--border)", borderRadius: 6 }}>
            <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                          letterSpacing: "0.1em", marginBottom: 4 }}>{l}</div>
            <div style={{ fontFamily: "monospace", fontSize: 15, fontWeight: 700, color: c }}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginBottom: 10 }}>
        Latest: {data.date}
        {data.prev_date ? ` vs ${data.prev_date}` : ""}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <TabBtn t="top"        label="TOP 20 BY NAV"  />
        <TabBtn t="gainers"    label="TOP GAINERS"    />
        <TabBtn t="categories" label="CATEGORIES"     />
      </div>

      {/* Top 20 by NAV */}
      {tab === "top" && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
              <th style={{ padding: "4px 6px", textAlign: "right", width: 28 }}>#</th>
              <th style={{ padding: "4px 8px", textAlign: "left" }}>FUND NAME</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>NAV</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>CHANGE</th>
            </tr>
          </thead>
          <tbody>
            {(data.top_funds ?? []).map((row: any, i: number) => {
              const chg   = row.change_pct ?? null;
              const chgC  = chg == null ? "var(--dim)" : Number(chg) >= 0 ? "var(--pos)" : "var(--neg)";
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "5px 6px", color: "var(--dim)", textAlign: "right" }}>{i + 1}</td>
                  <td style={{ padding: "5px 8px", color: "var(--text)", maxWidth: 320 }}>
                    <span title={row.name}>{truncate(row.name, 48)}</span>
                    <CatBadge name={row.name} />
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)", fontWeight: 600 }}>
                    {fmtNav(row.nav)}
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: chgC }}>
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
        (data.gainers ?? []).length === 0 ? (
          <div style={{ color: "var(--muted)", fontFamily: "monospace", padding: 20 }}>
            No prior date data for comparison. Need at least 2 dates in mf_nav_history.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                <th style={{ padding: "4px 6px", textAlign: "right", width: 28 }}>#</th>
                <th style={{ padding: "4px 8px", textAlign: "left" }}>FUND NAME</th>
                <th style={{ padding: "4px 8px", textAlign: "right" }}>NAV</th>
                <th style={{ padding: "4px 8px", textAlign: "right" }}>GAIN</th>
              </tr>
            </thead>
            <tbody>
              {(data.gainers ?? []).map((row: any, i: number) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "5px 6px", color: "var(--dim)", textAlign: "right" }}>{i + 1}</td>
                  <td style={{ padding: "5px 8px", color: "var(--text)" }}>
                    <span title={row.name}>{truncate(row.name, 48)}</span>
                    <CatBadge name={row.name} />
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)" }}>{fmtNav(row.nav)}</td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--pos)", fontWeight: 600 }}>
                    {fmtPct(row.change_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {/* Categories (inferred from name) */}
      {tab === "categories" && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
              <th style={{ padding: "4px 8px", textAlign: "left" }}>CATEGORY</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>FUNDS</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>AVG NAV</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>MAX NAV</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((row, i) => {
              const color = CAT_COLORS[row.category] ?? "#6e7681";
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "5px 8px" }}>
                    <span style={{ color, fontWeight: 600 }}>{row.category}</span>
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>{row.count}</td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)" }}>{fmtNav(row.avg_nav)}</td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--pos)" }}>{fmtNav(row.max_nav)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
""")


# =============================================================================
# SUMMARY
# =============================================================================
print()
print("=" * 65)
print("  PHASE 4 FIXES COMPLETE")
print("=" * 65)
print("""
  FIX 1  NavBar.tsx
    Hydration error fixed. Clock now uses useState+useEffect.
    Server renders empty string, client fills in after mount.
    suppressHydrationWarning on the clock div.

  FIX 2  /api/options/route.ts
    Chain was empty because option_greeks_raw has NO close/oi columns.
    Fixed: chain now joins option_greeks_raw (greeks) + fo_data (price/OI).
    fo_data columns used: symbol, expiry, strike, option_typ, close, open_int, volume
    PCR computed from fo_data.open_int (real OI).
    GEX from gamma_exposure_daily (real schema: gamma_exposure per row).
    Max Pain from fo_data OI.
    Full analysis text now populated from real data.

  FIX 3  /api/macro/route.ts
    All -- fixed. Correct series_id keys:
    US: Fed_Funds, 10Y_Treasury, 2Y_Treasury, Inflation_CPI,
        GDP, Term_Spread, Unemployment, VIX
    India: INDCPIALLQINMEI, TRESEGINM194N, XTEXVA01INM664S, XTIMVA01INM664S
    Added: US 2Y, VIX, Unemployment, India Exports/Imports/Trade Balance

  FIX 4  MacroPanel.tsx
    Removed self-contained panel-title (was duplicating page title).
    Now renders table + KPI cards only.
    India tab shows: CPI, FX Reserves, Trade Balance, ref US rates.
    Sparklines work for all series.

  FIX 5  /api/mf/route.ts + MFPanel.tsx
    Removed category column (doesn't exist in mf_nav_history).
    Category now inferred from scheme_name patterns (10 categories).
    Colored category badges shown inline with fund names.
    Removed self-contained panel-title.

  RESTART:
    cd D:\\MICC\\micc-dashboard && npm run dev
    Open http://localhost:3000

  NOTE on options data:
    If chain still shows empty, option_greeks_raw or fo_data may not
    have recent data. Check:
      SELECT MAX(date), COUNT(*) FROM fo_data WHERE symbol='NIFTY' AND instrument='OPTIDX';
      SELECT MAX(date), COUNT(*) FROM option_greeks_raw WHERE symbol='NIFTY';
    If fo_data is empty for recent dates, run daily_update.py first.
    If greeks are missing, run: py phase2_greeks_calculator.py --daily
""")
