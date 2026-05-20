# -*- coding: utf-8 -*-
"""
phase4_multipage.py
====================
MICC Phase 4 - Multi-page dashboard restructure.

Pages created:
  /            app/page.tsx          Overview: Alpha+Beta+Gamma+Delta summaries + nav links
  /streaks     app/streaks/page.tsx  Streak Leaderboard (improved: conviction, consistency, hot picks)
  /indices     app/indices/page.tsx  Index Performance (top 25 each side + full table)
  /options     app/options/page.tsx  Options chain + GEX + OI change + analysis panel
  /macro       app/macro/page.tsx    Macro dashboard (US + India)
  /mf          app/mf/page.tsx       MF NAV tracker

Shared:
  components/NavBar.tsx              Sticky top nav across all pages

API updates:
  api/indices/route.ts               Returns top 25 (was 10)
  api/streak-extended/route.ts       Conviction score, consistency %, regime filter,
                                     removed broken min_days, added hot picks
  api/options/route.ts               Volume/Delta/Theta columns, OI change vs prev day,
                                     built-in analysis text

Usage:
  cd D:\\MICC
  py phase4_multipage.py

Rules (always respected):
  - 'py' not 'python'
  - No get_conn() in agent files
  - Zero emoji / Unicode in TSX - pure ASCII only
  - fo_data queries always filtered by date
  - DA = 'D:/MICC', DB = 'D:/marketDB/db/market.db'
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
    print("[ERROR] micc-dashboard not found at D:/MICC/micc-dashboard/")
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
# 1. NavBar component
# =============================================================================
print("\n[1/8] Writing NavBar...")

w(COMP / "NavBar.tsx", r"""
"use client";
import Link         from "next/link";
import { usePathname } from "next/navigation";

const PAGES = [
  { href: "/",        label: "OVERVIEW"  },
  { href: "/streaks", label: "STREAKS"   },
  { href: "/indices", label: "INDICES"   },
  { href: "/options", label: "OPTIONS"   },
  { href: "/macro",   label: "MACRO"     },
  { href: "/mf",      label: "MF NAV"    },
];

export default function NavBar() {
  const path = usePathname();
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
      <div id="nav-time" style={{
        fontFamily: "monospace", fontSize: 10, color: "var(--dim)", whiteSpace: "nowrap",
      }} />
      <script dangerouslySetInnerHTML={{ __html: `
        (function(){
          function tick(){
            var el=document.getElementById('nav-time');
            if(el) el.textContent=new Date().toLocaleTimeString('en-IN',{
              hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'Asia/Kolkata'
            })+' IST';
          }
          tick(); setInterval(tick,1000);
        })();
      `}} />
    </header>
  );
}
""")

# =============================================================================
# 2. API: /api/indices — top 25
# =============================================================================
print("\n[2/8] Updating API routes...")

w(APP / "api" / "indices" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8', timeout: 30000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[indices]', r.stderr?.slice(0,200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) { console.error('[indices]', e.message); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const days = Math.min(parseInt(searchParams.get('days') || '7'), 365)

  const rows = queryDb(`
    WITH latest_date AS (SELECT MAX(date) AS max_date FROM market_snapshot),
    start_date AS (SELECT date(max_date, '-${days + 14} days') AS s FROM latest_date),
    date_range AS (
      SELECT DISTINCT date FROM market_snapshot
      WHERE date >= (SELECT s FROM start_date) ORDER BY date ASC
    ),
    window_start AS (
      SELECT MIN(date) AS wd FROM (
        SELECT date FROM date_range ORDER BY date DESC LIMIT ${days + 1}
      )
    ),
    window_end AS (SELECT MAX(date) AS wd FROM date_range),
    start_snap AS (
      SELECT index_name, closing_index_value AS start_close, pe AS start_pe
      FROM market_snapshot WHERE date = (SELECT wd FROM window_start)
    ),
    end_snap AS (
      SELECT index_name, closing_index_value AS end_close, pe AS end_pe, pb, div_yield
      FROM market_snapshot WHERE date = (SELECT wd FROM window_end)
    )
    SELECT
      e.index_name  AS name,
      ROUND(s.start_close,2) AS start_close,
      ROUND(e.end_close,  2) AS end_close,
      ROUND((e.end_close - s.start_close) / s.start_close * 100, 2) AS pct_change,
      ROUND(e.end_pe,   2) AS pe,
      ROUND(e.pb,       2) AS pb,
      ROUND(e.div_yield,2) AS div_yield
    FROM end_snap e
    JOIN start_snap s ON e.index_name = s.index_name
    WHERE s.start_close > 0 AND e.end_close > 0
      AND e.index_name NOT LIKE '%Inverse%'
      AND e.index_name NOT LIKE '%1x%'
      AND e.index_name NOT LIKE 'India VIX%'
      AND e.index_name NOT LIKE 'INDIA VIX%'
    ORDER BY pct_change DESC
  `)

  return NextResponse.json({
    gainers: rows.slice(0, 25),
    losers:  [...rows].reverse().slice(0, 25),
    all:     rows,
    days,
    total:   rows.length,
  })
}
""")

# API: /api/streak-extended — improved
w(APP / "api" / "streak-extended" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8', timeout: 30000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[streak]', r.stderr?.slice(0,200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) { console.error('[streak]', e.message); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const days   = Math.min(parseInt(searchParams.get('days')   || '30'), 180)
  const sortBy = searchParams.get('sort')   || 'streak'
  const screen = searchParams.get('screen') || ''
  const regime = searchParams.get('regime') || ''
  const limit  = Math.min(parseInt(searchParams.get('limit')  || '30'), 100)

  const screenFilter = screen ? `AND screen_tags LIKE '%${screen.replace(/'/g,"''")}%'` : ''
  const regimeFilter = regime ? `AND regime = '${regime.replace(/'/g,"''")}'` : ''

  const orderMap: Record<string,string> = {
    streak:      'streak_days DESC, conviction DESC',
    conviction:  'conviction DESC, streak_days DESC',
    score:       'avg_score DESC, streak_days DESC',
    pct:         'avg_pct DESC, streak_days DESC',
    deliv:       'avg_deliv DESC, streak_days DESC',
    consistency: 'consistency DESC, streak_days DESC',
  }
  const orderBy = orderMap[sortBy] || orderMap['streak']

  const rows = queryDb(`
    WITH max_date AS (SELECT MAX(run_date) AS md FROM signals_history)
    SELECT
      symbol,
      COUNT(DISTINCT run_date)                    AS streak_days,
      MAX(run_date)                               AS last_seen,
      MIN(run_date)                               AS first_seen,
      ROUND(AVG(CAST(score          AS REAL)),2)  AS avg_score,
      MAX(CAST(score                AS REAL))     AS max_score,
      ROUND(AVG(CAST(pct_chg       AS REAL)),2)  AS avg_pct,
      MAX(CAST(pct_chg             AS REAL))     AS max_pct,
      MIN(CAST(pct_chg             AS REAL))     AS min_pct,
      ROUND(AVG(CAST(avg_deliv_pct AS REAL)),1)  AS avg_deliv,
      MAX(CAST(avg_deliv_pct       AS REAL))     AS max_deliv,
      SUM(CASE WHEN earnings_flag=1 THEN 1 ELSE 0 END) AS eps_days,
      GROUP_CONCAT(DISTINCT screen_tags)          AS all_tags,
      COUNT(DISTINCT regime)                      AS regime_count,
      MAX(regime)                                 AS latest_regime,
      ROUND(
        COUNT(DISTINCT run_date) * AVG(CAST(score AS REAL))
        + AVG(CAST(avg_deliv_pct AS REAL)) * 0.1, 2
      )                                           AS conviction,
      ROUND(
        COUNT(DISTINCT run_date) * 100.0 /
        NULLIF((SELECT COUNT(DISTINCT run_date) FROM signals_history
                WHERE run_date >= date((SELECT md FROM max_date),'-${days} days')),0),1
      )                                           AS consistency
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_date),'-${days} days')
    ${screenFilter}
    ${regimeFilter}
    GROUP BY symbol
    HAVING streak_days >= 2
    ORDER BY ${orderBy}
    LIMIT ${limit}
  `)

  const tags = queryDb(`
    WITH max_date AS (SELECT MAX(run_date) AS md FROM signals_history)
    SELECT DISTINCT screen_tags, COUNT(*) AS cnt
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_date),'-30 days')
      AND screen_tags IS NOT NULL
    GROUP BY screen_tags ORDER BY cnt DESC LIMIT 20
  `)

  const regimes = queryDb(`
    WITH max_date AS (SELECT MAX(run_date) AS md FROM signals_history)
    SELECT DISTINCT regime, COUNT(*) AS cnt
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_date),'-${days} days')
      AND regime IS NOT NULL
    GROUP BY regime ORDER BY cnt DESC
  `)

  const stats = queryDb(`
    SELECT COUNT(*) AS total_rows,
           COUNT(DISTINCT symbol)   AS unique_symbols,
           COUNT(DISTINCT run_date) AS unique_dates,
           MAX(run_date) AS latest_date,
           MIN(run_date) AS earliest_date
    FROM signals_history
  `)

  const hot = queryDb(`
    WITH max_date AS (SELECT MAX(run_date) AS md FROM signals_history)
    SELECT symbol,
           COUNT(DISTINCT run_date) AS days,
           ROUND(AVG(CAST(score AS REAL)),1) AS avg_score,
           GROUP_CONCAT(DISTINCT screen_tags) AS tags
    FROM signals_history
    WHERE run_date >= date((SELECT md FROM max_date),'-7 days')
    GROUP BY symbol HAVING days >= 3
    ORDER BY days DESC, avg_score DESC LIMIT 5
  `)

  return NextResponse.json({ rows, tags, regimes, stats: stats[0] || {}, days, sortBy, hot })
}
""")

# API: /api/options — with analysis + OI change
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
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[options]', r.stderr?.slice(0,200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) { console.error('[options]', e.message); return [] }
}

function readAgent(name: string): any {
  try {
    const p = path.join(DA, 'agents', name, 'last_report.json')
    if (!fs.existsSync(p)) return null
    let raw = fs.readFileSync(p, 'utf-8')
    raw = raw.replace(/:\s*NaN([,\}\]])/g,': null$1')
             .replace(/:\s*Infinity([,\}\]])/g,': null$1')
    return JSON.parse(raw)
  } catch { return null }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  const latestRows = queryDb(`SELECT MAX(date) AS d FROM option_greeks_raw`)
  const latestDate = latestRows[0]?.d ?? ''
  if (!latestDate) return NextResponse.json({ error: 'No data in option_greeks_raw', date: null })

  const expiryRows = queryDb(`
    SELECT MIN(expiry) AS nearest_expiry FROM option_greeks_raw
    WHERE date='${latestDate}' AND symbol LIKE 'NIFTY%' AND expiry>='${latestDate}'
  `)
  const nearestExpiry = expiryRows[0]?.nearest_expiry ?? ''

  const pcrRows = queryDb(`
    SELECT option_type, SUM(oi) AS total_oi FROM option_greeks_raw
    WHERE date='${latestDate}' AND symbol LIKE 'NIFTY%' AND expiry='${nearestExpiry}'
    GROUP BY option_type
  `)
  const callOI = Number(pcrRows.find((r:any)=>r.option_type==='CE')?.total_oi??0)
  const putOI  = Number(pcrRows.find((r:any)=>r.option_type==='PE')?.total_oi??0)
  const pcr    = callOI>0 ? Math.round((putOI/callOI)*1000)/1000 : null

  const chainRows = queryDb(`
    SELECT strike,
      MAX(CASE WHEN option_type='CE' THEN close  END) AS call_ltp,
      MAX(CASE WHEN option_type='CE' THEN oi     END) AS call_oi,
      MAX(CASE WHEN option_type='CE' THEN volume END) AS call_vol,
      MAX(CASE WHEN option_type='CE' THEN iv     END) AS call_iv,
      MAX(CASE WHEN option_type='CE' THEN delta  END) AS call_delta,
      MAX(CASE WHEN option_type='CE' THEN gamma  END) AS call_gamma,
      MAX(CASE WHEN option_type='CE' THEN theta  END) AS call_theta,
      MAX(CASE WHEN option_type='PE' THEN close  END) AS put_ltp,
      MAX(CASE WHEN option_type='PE' THEN oi     END) AS put_oi,
      MAX(CASE WHEN option_type='PE' THEN volume END) AS put_vol,
      MAX(CASE WHEN option_type='PE' THEN iv     END) AS put_iv,
      MAX(CASE WHEN option_type='PE' THEN delta  END) AS put_delta,
      MAX(CASE WHEN option_type='PE' THEN gamma  END) AS put_gamma,
      MAX(CASE WHEN option_type='PE' THEN theta  END) AS put_theta
    FROM option_greeks_raw
    WHERE date='${latestDate}' AND symbol LIKE 'NIFTY%' AND expiry='${nearestExpiry}'
    GROUP BY strike
    ORDER BY (COALESCE(call_oi,0)+COALESCE(put_oi,0)) DESC LIMIT 25
  `)
  const chain = [...chainRows].sort((a:any,b:any)=>Number(a.strike)-Number(b.strike))

  const allStrikeRows = queryDb(`
    SELECT strike,
      SUM(CASE WHEN option_type='CE' THEN COALESCE(oi,0) END) AS call_oi,
      SUM(CASE WHEN option_type='PE' THEN COALESCE(oi,0) END) AS put_oi
    FROM option_greeks_raw
    WHERE date='${latestDate}' AND symbol LIKE 'NIFTY%' AND expiry='${nearestExpiry}'
    GROUP BY strike ORDER BY strike ASC
  `)

  let maxPainStrike: number|null = null
  if (allStrikeRows.length>0) {
    const strikes = allStrikeRows.map((r:any)=>Number(r.strike))
    let minLoss = Infinity
    for (const K of strikes) {
      let loss = 0
      for (const row of allStrikeRows as any[]) {
        const s=Number(row.strike), co=Number(row.call_oi??0), po=Number(row.put_oi??0)
        if (s<K) loss += (K-s)*co
        if (s>K) loss += (s-K)*po
      }
      if (loss<minLoss) { minLoss=loss; maxPainStrike=K }
    }
  }

  const gexLatest = queryDb(`SELECT MAX(date) AS d FROM gamma_exposure_daily`)
  const gexDate   = gexLatest[0]?.d ?? ''
  const gexRows   = gexDate ? queryDb(`
    SELECT strike,
      ROUND(SUM(call_gex),2) AS call_gex,
      ROUND(SUM(put_gex), 2) AS put_gex,
      ROUND(SUM(net_gex), 2) AS net_gex
    FROM gamma_exposure_daily WHERE date='${gexDate}'
    GROUP BY strike ORDER BY ABS(net_gex) DESC LIMIT 25
  `) : []
  const totalGex = gexRows.reduce((s:number,r:any)=>s+Number(r.net_gex??0),0)

  const prevDateRows = queryDb(`SELECT MAX(date) AS d FROM option_greeks_raw WHERE date<'${latestDate}'`)
  const prevDate = prevDateRows[0]?.d ?? ''
  const oiChange = prevDate ? queryDb(`
    SELECT cur.strike, cur.option_type,
      ROUND(CAST(cur.oi AS REAL)-CAST(COALESCE(prv.oi,cur.oi) AS REAL),0) AS oi_chg,
      cur.oi AS cur_oi
    FROM option_greeks_raw cur
    LEFT JOIN option_greeks_raw prv
      ON cur.symbol=prv.symbol AND cur.strike=prv.strike
     AND cur.option_type=prv.option_type AND cur.expiry=prv.expiry
     AND prv.date='${prevDate}'
    WHERE cur.date='${latestDate}' AND cur.symbol LIKE 'NIFTY%'
      AND cur.expiry='${nearestExpiry}'
    ORDER BY ABS(oi_chg) DESC LIMIT 20
  `) : []

  const niftyRows = queryDb(`
    SELECT closing_index_value AS close, points_change, change AS change_pct
    FROM market_snapshot
    WHERE index_name='Nifty 50' AND date=(SELECT MAX(date) FROM market_snapshot)
    LIMIT 1
  `)
  const niftyClose    = niftyRows[0]?.close ?? null
  const niftyChangePct = niftyRows[0]?.change_pct ?? null

  const alpha       = readAgent('alpha')
  const alphaRegime = alpha?.regime?.regime ?? '--'
  const alphaConf   = alpha?.regime?.confidence ?? '--'

  const pcrLabel = pcr==null?'--': pcr>1.3?'BULLISH (put-heavy)': pcr<0.7?'BEARISH (call-heavy)':'NEUTRAL'
  const gexLabel = totalGex>0?'LONG GAMMA (dealers absorb moves)':'SHORT GAMMA (dealers amplify moves)'
  const maxPainGap = (maxPainStrike&&niftyClose)
    ? Math.round(((Number(niftyClose)-maxPainStrike)/maxPainStrike)*100*10)/10 : null

  const analysis = [
    `Options Snapshot -- ${latestDate} | Expiry: ${nearestExpiry}`,
    '',
    `## Market Structure`,
    `Nifty 50: ${niftyClose?Number(niftyClose).toLocaleString('en-IN'):'--'}` +
      (niftyChangePct!=null?` (${Number(niftyChangePct)>=0?'+':''}${Number(niftyChangePct).toFixed(2)}%)`:''),
    `Regime: ${alphaRegime} | Confidence: ${alphaConf}`,
    '',
    `## Options Positioning`,
    `PCR: ${pcr?.toFixed(3)??'--'} -- ${pcrLabel}`,
    `Max Pain: ${maxPainStrike?.toLocaleString('en-IN')??'--'}${maxPainGap!=null?` (Nifty is ${maxPainGap>0?'+':''}${maxPainGap}% from max pain)`:''}`,
    `Net GEX: ${Math.round(totalGex).toLocaleString()} -- ${gexLabel}`,
    `Call OI: ${(callOI/1e5).toFixed(1)}L | Put OI: ${(putOI/1e5).toFixed(1)}L`,
    '',
    `## Key OI Concentrations`,
    ...(chain.slice(0,5).map((r:any)=>{
      const tot=Number(r.call_oi??0)+Number(r.put_oi??0)
      return `Strike ${Number(r.strike).toLocaleString()}: CE=${Math.round(Number(r.call_oi??0)/1000)}K  PE=${Math.round(Number(r.put_oi??0)/1000)}K  Total=${Math.round(tot/1000)}K`
    })),
    '',
    `## Interpretation`,
    pcr!=null&&pcr>1.2
      ? 'Elevated PCR signals put-heavy positioning -- writers expect support. Typically bullish for near-term.'
      : pcr!=null&&pcr<0.8
      ? 'Low PCR -- call-heavy market. Expect resistance or sideways consolidation near-term.'
      : 'PCR near 1.0 signals balanced positioning. Await directional trigger.',
    '',
    totalGex>0
      ? 'Positive net GEX: dealer hedging creates natural damping -- large moves get absorbed.'
      : 'Negative net GEX: dealer hedging amplifies direction. Expect higher volatility.',
    '',
    maxPainStrike!=null
      ? `Max pain at ${maxPainStrike?.toLocaleString()} acts as a gravitational level into expiry. Expect drift toward this level as expiry approaches.`
      : '',
  ].filter(l=>l!==undefined).join('\n')

  return NextResponse.json({
    date: latestDate, expiry: nearestExpiry, pcr,
    call_oi: callOI, put_oi: putOI, max_pain: maxPainStrike,
    chain, gex: gexRows, total_net_gex: Math.round(totalGex), gex_date: gexDate,
    oi_change: oiChange, nifty_close: niftyClose, nifty_change_pct: niftyChangePct,
    analysis,
  })
}
""")

print("[2/8] API routes done")


# =============================================================================
# 3. MAIN PAGE (overview)
# =============================================================================
print("\n[3/8] Writing main overview page...")

w(APP / "page.tsx", r"""
"use client";
import { useState, useEffect, useCallback } from "react";
import NavBar            from "@/components/NavBar";
import AlphaPanel        from "@/components/AlphaPanel";
import BetaPanel         from "@/components/BetaPanel";
import GammaPanel        from "@/components/GammaPanel";
import DeltaPanel        from "@/components/DeltaPanel";
import RefreshController from "@/components/RefreshController";

interface Reports { alpha?: any; beta?: any; gamma?: any; delta?: any; ts?: number }

const NAV_CARDS = [
  { href: "/streaks", label: "STREAK LEADERBOARD", desc: "Multi-screen conviction + regime filter", color: "var(--accent)" },
  { href: "/indices", label: "INDEX PERFORMANCE",  desc: "144 indices, top 25 each, full table",   color: "var(--pos)"    },
  { href: "/options", label: "OPTIONS CHAIN",      desc: "Nifty PCR, GEX, Max Pain, OI change",    color: "var(--info)"   },
  { href: "/macro",   label: "MACRO DASHBOARD",    desc: "Fed, US 10Y, India CPI, FX reserves",    color: "var(--warn)"   },
  { href: "/mf",      label: "MF NAV TRACKER",     desc: "Top funds by NAV, gainers, categories",  color: "var(--bull)"   },
]

export default function Home() {
  const [reports,  setReports]  = useState<Reports>({});
  const [lastTime, setLastTime] = useState("");
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  const fetchReports = useCallback(async () => {
    try {
      const r = await fetch("/api/reports", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setReports(data);
      setLastTime(new Date().toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Kolkata",
      }));
      setError("");
    } catch (e: any) { setError(e.message || "Fetch failed"); }
  }, []);

  const triggerRefresh = useCallback(async () => {
    setLoading(true); await fetchReports(); setLoading(false);
  }, [fetchReports]);

  useEffect(() => { triggerRefresh(); }, []); // eslint-disable-line

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <NavBar />

      {/* Sub-header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "8px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface)",
      }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>
          Market Intelligence Command Center -- Overview
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {error    && <span style={{ color:"var(--neg)", fontSize:10, fontFamily:"monospace" }}>{error}</span>}
          {loading && !error && <span style={{ color:"var(--accent)", fontSize:10, fontFamily:"monospace" }}>Loading...</span>}
          {lastTime && !loading && <span style={{ color:"var(--dim)", fontSize:10, fontFamily:"monospace" }}>Updated {lastTime}</span>}
          <RefreshController onRefresh={triggerRefresh} intervalSec={90} autoStart={false} />
        </div>
      </div>

      <div style={{ padding: "16px 20px", maxWidth: 1600, margin: "0 auto" }}>
        <div style={{ marginBottom: 14 }}>
          <AlphaPanel data={reports.alpha ?? null} />
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:14, marginBottom:14 }}>
          <BetaPanel  data={reports.beta  ?? null} />
          <GammaPanel data={reports.gamma ?? null} />
        </div>
        <div style={{ marginBottom: 18 }}>
          <DeltaPanel data={reports.delta ?? null} />
        </div>

        {/* Quick-nav cards */}
        <div style={{
          borderTop: "1px solid var(--border)", paddingTop: 14,
          display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 10,
        }}>
          {NAV_CARDS.map(({ href, label, desc, color }) => (
            <a key={href} href={href} style={{ textDecoration:"none" }}>
              <div
                style={{
                  padding:"14px 16px", background:"var(--surface)",
                  border:"1px solid var(--border)", borderRadius:6, cursor:"pointer",
                  transition:"border-color 0.15s",
                }}
                onMouseEnter={e=>(e.currentTarget.style.borderColor=color)}
                onMouseLeave={e=>(e.currentTarget.style.borderColor="var(--border)")}
              >
                <div style={{
                  fontFamily:"monospace", fontSize:10, fontWeight:700,
                  letterSpacing:"0.1em", color, marginBottom:6,
                }}>{label}</div>
                <div style={{ fontFamily:"monospace", fontSize:10, color:"var(--dim)" }}>{desc}</div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
""")

# =============================================================================
# 4. STREAKS PAGE
# =============================================================================
print("\n[4/8] Writing streaks page...")

w(APP / "streaks" / "page.tsx", r"""
"use client";
import { useState, useEffect, useCallback } from "react";
import NavBar from "@/components/NavBar";

const DURATIONS = [
  {l:"7D",d:7},{l:"14D",d:14},{l:"20D",d:20},{l:"1M",d:30},{l:"2M",d:60},{l:"3M",d:90},
];
const SORTS = [
  {l:"Streak",v:"streak"},{l:"Conviction",v:"conviction"},{l:"Avg Score",v:"score"},
  {l:"Avg Return",v:"pct"},{l:"Delivery",v:"deliv"},{l:"Consistency",v:"consistency"},
];
const LIMITS = [20,30,50,100];

function grade(c: number):{g:string;color:string} {
  if (c>=20) return {g:"A+",color:"#26c485"};
  if (c>=12) return {g:"A", color:"#58a6ff"};
  if (c>=7)  return {g:"B", color:"#e3b341"};
  if (c>=3)  return {g:"C", color:"#f0883e"};
  return         {g:"D", color:"#f85149"};
}

function TagBadge({tag}:{tag:string}) {
  const s = tag.toLowerCase();
  const c = s.includes("mom")?"#58a6ff":s.includes("del")?"#26c485":
            s.includes("brk")||s.includes("break")?"#e3b341":s.includes("con")?"#f0883e":"#8b949e";
  return (
    <span style={{
      fontSize:8, padding:"1px 5px", marginLeft:3,
      background:c+"22", border:`1px solid ${c}66`,
      borderRadius:3, color:c, fontFamily:"monospace", whiteSpace:"nowrap",
    }}>{tag.toUpperCase().slice(0,6)}</span>
  );
}

export default function StreaksPage() {
  const [days,   setDays]   = useState(30);
  const [sortBy, setSortBy] = useState("streak");
  const [screen, setScreen] = useState("");
  const [regime, setRegime] = useState("");
  const [limit,  setLimit]  = useState(30);
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [expand, setExpand] = useState<string|null>(null);

  const load = useCallback(async()=>{
    setLoading(true);
    try {
      const qs = new URLSearchParams({
        days:String(days),sort:sortBy,screen,regime,limit:String(limit),
      });
      const r = await fetch(`/api/streak-extended?${qs}`,{cache:"no-store"});
      setData(await r.json());
    } catch(e){ console.error(e); }
    finally { setLoading(false); }
  },[days,sortBy,screen,regime,limit]);

  useEffect(()=>{load();},[load]);

  const rows    = data?.rows    ??[];
  const tags    = data?.tags    ??[];
  const regimes = data?.regimes ??[];
  const stats   = data?.stats   ??{};
  const hot     = data?.hot     ??[];
  const maxConv = Math.max(...rows.map((r:any)=>Number(r.conviction??0)),1);

  function Btn({active,color,onClick,children}:{active:boolean;color:string;onClick:()=>void;children:any}) {
    return (
      <button onClick={onClick} style={{
        padding:"3px 10px", fontSize:10, cursor:"pointer", fontFamily:"monospace",
        background: active?color+"22":"var(--surface)",
        color:      active?color:"var(--muted)",
        border:`1px solid ${active?color:"var(--border)"}`,
        borderRadius:4,
      }}>{children}</button>
    );
  }

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"baseline",gap:16,marginBottom:12}}>
          <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,letterSpacing:"0.12em",color:"var(--accent)"}}>
            STREAK LEADERBOARD
          </div>
          <div style={{fontSize:10,fontFamily:"monospace",color:"var(--dim)"}}>
            {stats.total_rows} rows &nbsp;|&nbsp;
            {stats.unique_symbols} symbols &nbsp;|&nbsp;
            {stats.unique_dates} dates &nbsp;|&nbsp;
            latest: {stats.latest_date??"--"}
          </div>
        </div>

        {/* HOT strip */}
        {hot.length>0 && (
          <div style={{display:"flex",gap:8,marginBottom:12,flexWrap:"wrap",alignItems:"center"}}>
            <span style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em"}}>HOT 7D:</span>
            {hot.map((h:any)=>(
              <div key={h.symbol} style={{
                padding:"3px 10px",
                background:"rgba(88,166,255,0.08)",border:"1px solid rgba(88,166,255,0.3)",
                borderRadius:4,fontFamily:"monospace",fontSize:11,
              }}>
                <span style={{color:"var(--accent)",fontWeight:700}}>{h.symbol}</span>
                <span style={{color:"var(--dim)",fontSize:10,marginLeft:8}}>{h.days}d  score {h.avg_score}</span>
              </div>
            ))}
          </div>
        )}

        {/* Filters row */}
        <div style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:14,alignItems:"flex-start"}}>

          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>LOOKBACK</div>
            <div style={{display:"flex",gap:4}}>
              {DURATIONS.map(({l,d})=>(
                <Btn key={d} active={days===d} color="var(--accent)" onClick={()=>setDays(d)}>{l}</Btn>
              ))}
            </div>
          </div>

          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>SORT BY</div>
            <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
              {SORTS.map(({l,v})=>(
                <Btn key={v} active={sortBy===v} color="var(--info)" onClick={()=>setSortBy(v)}>{l}</Btn>
              ))}
            </div>
          </div>

          {tags.length>0 && (
            <div>
              <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>SCREEN</div>
              <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
                <Btn active={screen===""} color="#26c485" onClick={()=>setScreen("")}>All</Btn>
                {tags.slice(0,8).map((t:any)=>(
                  <Btn key={t.screen_tags} active={screen===t.screen_tags} color="#26c485"
                       onClick={()=>setScreen(t.screen_tags)}>
                    {(t.screen_tags??"").slice(0,10)}
                  </Btn>
                ))}
              </div>
            </div>
          )}

          {regimes.length>1 && (
            <div>
              <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>REGIME</div>
              <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
                <Btn active={regime===""} color="#e3b341" onClick={()=>setRegime("")}>All</Btn>
                {regimes.map((rg:any)=>(
                  <Btn key={rg.regime} active={regime===rg.regime} color="#e3b341"
                       onClick={()=>setRegime(rg.regime)}>
                    {(rg.regime??"").slice(0,12)}
                  </Btn>
                ))}
              </div>
            </div>
          )}

          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>SHOW</div>
            <div style={{display:"flex",gap:4}}>
              {LIMITS.map(n=>(
                <Btn key={n} active={limit===n} color="#f0883e" onClick={()=>setLimit(n)}>{n}</Btn>
              ))}
            </div>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div style={{color:"var(--dim)",fontFamily:"monospace",fontSize:12,padding:40,textAlign:"center"}}>Loading...</div>
        ) : rows.length===0 ? (
          <div style={{color:"var(--muted)",fontFamily:"monospace",fontSize:12,padding:40,textAlign:"center"}}>
            No results. Try wider lookback or fewer filters.
          </div>
        ) : (
          <div style={{overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
              <thead>
                <tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)",letterSpacing:"0.08em"}}>
                  <th style={{textAlign:"left",  padding:"6px 8px",width:28}}>#</th>
                  <th style={{textAlign:"left",  padding:"6px 8px",minWidth:110}}>SYMBOL</th>
                  <th style={{textAlign:"center",padding:"6px 8px"}}>STREAK</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>CONVICTION</th>
                  <th style={{textAlign:"center",padding:"6px 8px",minWidth:100}}>CONSISTENCY</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>AVG SCORE</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>MAX SCORE</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>AVG RET%</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>MAX RET%</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>DELIV%</th>
                  <th style={{textAlign:"left",  padding:"6px 8px"}}>SCREENS</th>
                  <th style={{textAlign:"left",  padding:"6px 8px"}}>REGIME</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>LAST SEEN</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row:any,i:number)=>{
                  const cvG  = grade(Number(row.conviction??0));
                  const tags = (row.all_tags??"").split(",").filter(Boolean);
                  const isExp= expand===row.symbol;
                  const cnsty= Number(row.consistency??0);
                  const cBar = Math.round((Number(row.conviction??0)/maxConv)*100);
                  return (
                    <>
                      <tr key={row.symbol} onClick={()=>setExpand(isExp?null:row.symbol)}
                          style={{borderBottom:"1px solid var(--border)",cursor:"pointer",
                                  background:isExp?"rgba(88,166,255,0.05)":undefined}}>
                        <td style={{padding:"7px 8px",color:"var(--dim)"}}>{i+1}</td>
                        <td style={{padding:"7px 8px"}}>
                          <span style={{color:"var(--text)",fontWeight:700,fontSize:12}}>{row.symbol}</span>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"center"}}>
                          <span style={{color:"var(--accent)",fontWeight:700}}>{row.streak_days}d</span>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right"}}>
                          <span style={{color:cvG.color,fontWeight:700,marginRight:5}}>{cvG.g}</span>
                          <span style={{color:"var(--dim)",fontSize:10}}>{Number(row.conviction??0).toFixed(1)}</span>
                          <div style={{height:3,marginTop:3,background:"var(--border)",borderRadius:2}}>
                            <div style={{width:cBar+"%",height:"100%",background:cvG.color,borderRadius:2}}/>
                          </div>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"center"}}>
                          <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:5}}>
                            <div style={{width:50,height:5,background:"var(--border)",borderRadius:2,overflow:"hidden"}}>
                              <div style={{
                                width:Math.min(cnsty,100)+"%",height:"100%",borderRadius:2,
                                background:cnsty>=60?"#26c485":cnsty>=40?"#e3b341":"#f0883e",
                              }}/>
                            </div>
                            <span style={{color:"var(--dim)",fontSize:10}}>{cnsty.toFixed(0)}%</span>
                          </div>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right"}}>{Number(row.avg_score??0).toFixed(1)}</td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--accent)"}}>{Number(row.max_score??0).toFixed(1)}</td>
                        <td style={{padding:"7px 8px",textAlign:"right",
                            color:Number(row.avg_pct)>=0?"var(--pos)":"var(--neg)"}}>
                          {Number(row.avg_pct??0)>=0?"+":""}{Number(row.avg_pct??0).toFixed(2)}%
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--pos)"}}>
                          +{Number(row.max_pct??0).toFixed(2)}%
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--info)"}}>
                          {row.avg_deliv!=null?Number(row.avg_deliv).toFixed(1)+"%":"--"}
                        </td>
                        <td style={{padding:"7px 8px"}}>
                          {tags.slice(0,3).map((t:string)=><TagBadge key={t} tag={t}/>)}
                        </td>
                        <td style={{padding:"7px 8px",color:"var(--dim)",fontSize:10}}>
                          {(row.latest_regime??"--").slice(0,12)}
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--dim)"}}>{row.last_seen}</td>
                      </tr>
                      {isExp && (
                        <tr key={row.symbol+"_exp"} style={{background:"rgba(88,166,255,0.04)"}}>
                          <td colSpan={13} style={{padding:"10px 16px 12px"}}>
                            <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:12,fontSize:10,marginBottom:8}}>
                              {[
                                {l:"WINDOW",       v:`${row.first_seen} - ${row.last_seen}`,        c:"var(--text)" },
                                {l:"MIN RETURN",   v:`${Number(row.min_pct??0).toFixed(2)}%`,        c:"var(--neg)"  },
                                {l:"MAX DELIVERY", v:`${row.max_deliv!=null?Number(row.max_deliv).toFixed(1)+"%" :"--"}`, c:"var(--info)" },
                                {l:"EPS DAYS",     v:String(row.eps_days??0),                         c:Number(row.eps_days)>0?"var(--warn)":"var(--dim)"},
                                {l:"REGIMES SEEN", v:String(row.regime_count??1),                      c:"var(--text)" },
                              ].map(({l,v,c})=>(
                                <div key={l}>
                                  <div style={{color:"var(--dim)",marginBottom:3}}>{l}</div>
                                  <div style={{color:c,fontWeight:600}}>{v}</div>
                                </div>
                              ))}
                            </div>
                            <div>{tags.map((t:string)=><TagBadge key={t} tag={t}/>)}</div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
""")

# =============================================================================
# 5. INDICES PAGE
# =============================================================================
print("\n[5/8] Writing indices page...")

w(APP / "indices" / "page.tsx", r"""
"use client";
import { useState, useEffect, useCallback } from "react";
import NavBar from "@/components/NavBar";

const DURATIONS = [
  {l:"1D",d:1},{l:"3D",d:3},{l:"5D",d:5},{l:"7D",d:7},
  {l:"10D",d:10},{l:"14D",d:14},{l:"20D",d:20},
  {l:"1M",d:22},{l:"2M",d:44},{l:"3M",d:66},{l:"6M",d:132},
];

function IRow({rank,row,color}:{rank:number;row:any;color:string}) {
  const pct  = Number(row.pct_change);
  const barW = Math.min((Math.abs(pct)/20)*100,100);
  return (
    <tr style={{borderBottom:"1px solid var(--border)"}}>
      <td style={{padding:"5px 6px",color:"var(--dim)",textAlign:"right",fontFamily:"monospace",fontSize:10}}>{rank}</td>
      <td style={{padding:"5px 8px",color:"var(--text)",fontSize:11}}>{row.name}</td>
      <td style={{padding:"5px 6px",textAlign:"right",color:"var(--dim)",fontFamily:"monospace",fontSize:10}}>
        {row.end_close!=null?Number(row.end_close).toLocaleString("en-IN",{maximumFractionDigits:2}):"--"}
      </td>
      <td style={{padding:"5px 4px",textAlign:"right",color:"var(--dim)",fontFamily:"monospace",fontSize:10}}>
        {row.pe!=null?Number(row.pe).toFixed(1):"--"}
      </td>
      <td style={{padding:"5px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color,fontWeight:600}}>
        {pct>=0?"+":""}{pct.toFixed(2)}%
      </td>
      <td style={{padding:"5px 8px",width:90}}>
        <div style={{width:90,height:5,background:"var(--border)",borderRadius:2,overflow:"hidden"}}>
          <div style={{width:barW+"%",height:"100%",background:color,borderRadius:2}}/>
        </div>
      </td>
    </tr>
  );
}

export default function IndicesPage() {
  const [days,   setDays]   = useState(7);
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [tab,    setTab]    = useState<"split"|"all">("split");

  const load = useCallback(async(d:number)=>{
    setLoading(true);
    try {
      const r = await fetch(`/api/indices?days=${d}`,{cache:"no-store"});
      setData(await r.json());
    } catch(e){console.error(e);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load(days);},[days,load]);

  const gainers = data?.gainers??[];
  const losers  = data?.losers ??[];
  const all     = data?.all    ??[];

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",
                     marginBottom:14,flexWrap:"wrap",gap:10}}>
          <div>
            <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,
                         letterSpacing:"0.12em",color:"var(--pos)"}}>INDEX PERFORMANCE</div>
            <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginTop:2}}>
              {data?.total??"--"} indices &nbsp;|&nbsp; {data?.days??"--"}D window
            </div>
          </div>
          <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
            {DURATIONS.map(({l,d})=>(
              <button key={d} onClick={()=>setDays(d)} style={{
                padding:"4px 10px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
                background:days===d?"rgba(38,196,133,0.15)":"var(--surface)",
                color:days===d?"#26c485":"var(--muted)",
                border:`1px solid ${days===d?"#26c485":"var(--border)"}`,
                borderRadius:4,
              }}>{l}</button>
            ))}
          </div>
        </div>

        <div style={{display:"flex",gap:6,marginBottom:14}}>
          {(["split","all"] as const).map(t=>(
            <button key={t} onClick={()=>setTab(t)} style={{
              padding:"4px 14px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
              background:tab===t?"var(--pos)":"var(--surface)",
              color:tab===t?"#000":"var(--muted)",
              border:"1px solid var(--border)",borderRadius:4,
            }}>
              {t==="split"?"TOP 25 GAINERS / BOTTOM 25 DECLINERS":`FULL TABLE (${all.length})`}
            </button>
          ))}
        </div>

        {loading ? (
          <div style={{color:"var(--dim)",fontFamily:"monospace",padding:40,textAlign:"center"}}>Loading...</div>
        ) : tab==="split" ? (
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:20}}>
            {/* Gainers */}
            <div>
              <div style={{fontFamily:"monospace",fontSize:10,color:"var(--pos)",letterSpacing:"0.1em",
                           marginBottom:8,borderBottom:"1px solid var(--border)",paddingBottom:4}}>
                TOP {gainers.length} GAINERS
              </div>
              <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead>
                  <tr style={{fontSize:9,color:"var(--dim)",borderBottom:"1px solid var(--border)"}}>
                    <th style={{padding:"3px 6px",textAlign:"right",width:28}}>#</th>
                    <th style={{padding:"3px 8px",textAlign:"left"}}>INDEX</th>
                    <th style={{padding:"3px 6px",textAlign:"right"}}>CLOSE</th>
                    <th style={{padding:"3px 4px",textAlign:"right"}}>PE</th>
                    <th style={{padding:"3px 8px",textAlign:"right"}}>CHG%</th>
                    <th style={{padding:"3px 8px",width:90}}></th>
                  </tr>
                </thead>
                <tbody>
                  {gainers.map((r:any,i:number)=><IRow key={r.name} rank={i+1} row={r} color="var(--pos)"/>)}
                </tbody>
              </table>
            </div>
            {/* Decliners */}
            <div>
              <div style={{fontFamily:"monospace",fontSize:10,color:"var(--neg)",letterSpacing:"0.1em",
                           marginBottom:8,borderBottom:"1px solid var(--border)",paddingBottom:4}}>
                BOTTOM {losers.length} DECLINERS
              </div>
              <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead>
                  <tr style={{fontSize:9,color:"var(--dim)",borderBottom:"1px solid var(--border)"}}>
                    <th style={{padding:"3px 6px",textAlign:"right",width:28}}>#</th>
                    <th style={{padding:"3px 8px",textAlign:"left"}}>INDEX</th>
                    <th style={{padding:"3px 6px",textAlign:"right"}}>CLOSE</th>
                    <th style={{padding:"3px 4px",textAlign:"right"}}>PE</th>
                    <th style={{padding:"3px 8px",textAlign:"right"}}>CHG%</th>
                    <th style={{padding:"3px 8px",width:90}}></th>
                  </tr>
                </thead>
                <tbody>
                  {losers.map((r:any,i:number)=><IRow key={r.name} rank={i+1} row={r} color="var(--neg)"/>)}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
            <thead>
              <tr style={{fontSize:9,color:"var(--dim)",borderBottom:"2px solid var(--border)",letterSpacing:"0.08em"}}>
                <th style={{padding:"5px 6px",textAlign:"right",width:28}}>#</th>
                <th style={{padding:"5px 8px",textAlign:"left"}}>INDEX NAME</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>CLOSE</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>PE</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>PB</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>CHG%</th>
                <th style={{padding:"5px 8px",width:120}}></th>
              </tr>
            </thead>
            <tbody>
              {all.map((r:any,i:number)=>{
                const pct=Number(r.pct_change);
                const color=pct>=0?"var(--pos)":"var(--neg)";
                const barW=Math.min((Math.abs(pct)/20)*100,100);
                return (
                  <tr key={r.name} style={{borderBottom:"1px solid var(--border)"}}>
                    <td style={{padding:"4px 6px",color:"var(--dim)",textAlign:"right"}}>{i+1}</td>
                    <td style={{padding:"4px 8px",color:"var(--text)"}}>{r.name}</td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:"var(--dim)"}}>
                      {Number(r.end_close).toLocaleString("en-IN",{maximumFractionDigits:2})}
                    </td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:"var(--dim)"}}>
                      {r.pe!=null?Number(r.pe).toFixed(1):"--"}
                    </td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:"var(--dim)"}}>
                      {r.pb!=null?Number(r.pb).toFixed(2):"--"}
                    </td>
                    <td style={{padding:"4px 8px",textAlign:"right",color,fontWeight:600}}>
                      {pct>=0?"+":""}{pct.toFixed(2)}%
                    </td>
                    <td style={{padding:"4px 8px"}}>
                      <div style={{width:120,height:5,background:"var(--border)",borderRadius:2,overflow:"hidden"}}>
                        <div style={{width:barW+"%",height:"100%",background:color,borderRadius:2}}/>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
""")

# =============================================================================
# 6. OPTIONS PAGE
# =============================================================================
print("\n[6/8] Writing options page...")

w(APP / "options" / "page.tsx", r"""
"use client";
import { useState, useEffect } from "react";
import NavBar       from "@/components/NavBar";
import MarkdownText from "@/components/MarkdownText";

function fmtOI(v:any):string {
  const n=Number(v); if(!v||isNaN(n)) return "--";
  if(n>=1e7) return (n/1e7).toFixed(1)+"Cr";
  if(n>=1e5) return (n/1e5).toFixed(1)+"L";
  if(n>=1e3) return (n/1e3).toFixed(0)+"K";
  return n.toFixed(0);
}
function fmtGex(v:number):string {
  const a=Math.abs(v);
  if(a>=1e9) return (v/1e9).toFixed(2)+"B";
  if(a>=1e6) return (v/1e6).toFixed(2)+"M";
  if(a>=1e3) return (v/1e3).toFixed(1)+"K";
  return v.toFixed(0);
}

export default function OptionsPage() {
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [tab,    setTab]    = useState<"chain"|"gex"|"oichange">("chain");

  useEffect(()=>{
    fetch("/api/options",{cache:"no-store"})
      .then(r=>r.json()).then(d=>{setData(d);setLoading(false);})
      .catch(()=>setLoading(false));
  },[]);

  if(loading) return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:40,color:"var(--dim)",fontFamily:"monospace"}}>Loading options data...</div>
    </div>
  );
  if(!data||data.error) return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:40,color:"var(--neg)",fontFamily:"monospace"}}>
        {data?.error??"No options data."}<br/>
        Run: py D:\MICC\data_pipeline\phase2_greeks_calculator.py --daily
      </div>
    </div>
  );

  const pcrC = data.pcr==null?"var(--text)":data.pcr>1.3?"var(--pos)":data.pcr<0.7?"var(--neg)":"var(--warn)";
  const pcrL = data.pcr==null?"--":data.pcr>1.3?"BULLISH":data.pcr<0.7?"BEARISH":"NEUTRAL";
  const gexC = data.total_net_gex>0?"var(--pos)":"var(--neg)";
  const gexL = data.total_net_gex>0?"LONG GAMMA":"SHORT GAMMA";

  const maxCOI = Math.max(...(data.chain??[]).map((r:any)=>Number(r.call_oi??0)),1);
  const maxPOI = Math.max(...(data.chain??[]).map((r:any)=>Number(r.put_oi ??0)),1);
  const maxGex = Math.max(...(data.gex  ??[]).map((r:any)=>Math.abs(Number(r.net_gex))),1);

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        <div style={{marginBottom:14}}>
          <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,letterSpacing:"0.12em",color:"var(--info)"}}>
            OPTIONS INTELLIGENCE -- NIFTY
          </div>
          <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginTop:2}}>
            Date: {data.date} &nbsp;|&nbsp; Expiry: {data.expiry}
            {data.nifty_close && (
              <span> &nbsp;|&nbsp; Nifty: {Number(data.nifty_close).toLocaleString("en-IN")}
                {data.nifty_change_pct!=null && (
                  <span style={{color:Number(data.nifty_change_pct)>=0?"var(--pos)":"var(--neg)"}}>
                    &nbsp;({Number(data.nifty_change_pct)>=0?"+":""}{Number(data.nifty_change_pct).toFixed(2)}%)
                  </span>
                )}
              </span>
            )}
          </div>
        </div>

        {/* KPIs */}
        <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:10,marginBottom:16}}>
          {[
            {label:"PCR",    value:data.pcr?.toFixed(3)??"--", sub:pcrL,         color:pcrC},
            {label:"MAX PAIN",value:data.max_pain?.toLocaleString("en-IN")??"--",sub:"strike",color:"var(--warn)"},
            {label:"NET GEX", value:fmtGex(data.total_net_gex),                  sub:gexL,  color:gexC},
            {label:"CALL OI", value:fmtOI(data.call_oi),                         sub:"total calls",color:"var(--neg)"},
            {label:"PUT OI",  value:fmtOI(data.put_oi),                          sub:"total puts", color:"var(--pos)"},
          ].map(({label,value,sub,color})=>(
            <div key={label} style={{
              padding:"12px 14px",background:"var(--surface)",
              border:"1px solid var(--border)",borderRadius:6,
            }}>
              <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em",marginBottom:4}}>{label}</div>
              <div style={{fontFamily:"monospace",fontSize:18,fontWeight:700,color}}>{value}</div>
              <div style={{fontFamily:"monospace",fontSize:9,color,marginTop:3}}>{sub}</div>
            </div>
          ))}
        </div>

        <div style={{display:"grid",gridTemplateColumns:"1fr 360px",gap:16}}>
          {/* Left: tabs */}
          <div>
            <div style={{display:"flex",gap:6,marginBottom:12}}>
              {(["chain","gex","oichange"] as const).map(t=>(
                <button key={t} onClick={()=>setTab(t)} style={{
                  padding:"4px 12px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
                  background:tab===t?"var(--info)":"var(--surface)",
                  color:tab===t?"#000":"var(--muted)",
                  border:"1px solid var(--border)",borderRadius:4,
                }}>
                  {t==="chain"?"OPTIONS CHAIN":t==="gex"?"GEX BY STRIKE":"OI CHANGE"}
                </button>
              ))}
            </div>

            {/* CHAIN */}
            {tab==="chain" && (
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
                <thead>
                  <tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)"}}>
                    <th style={{textAlign:"right", padding:"4px 5px"}}>CALL OI</th>
                    <th style={{textAlign:"right", padding:"4px 5px"}}>VOL</th>
                    <th style={{textAlign:"right", padding:"4px 5px"}}>IV</th>
                    <th style={{textAlign:"right", padding:"4px 5px"}}>DELTA</th>
                    <th style={{textAlign:"right", padding:"4px 5px"}}>LTP</th>
                    <th style={{textAlign:"center",padding:"4px 10px",color:"var(--info)",minWidth:90}}>STRIKE</th>
                    <th style={{textAlign:"left",  padding:"4px 5px"}}>LTP</th>
                    <th style={{textAlign:"left",  padding:"4px 5px"}}>DELTA</th>
                    <th style={{textAlign:"left",  padding:"4px 5px"}}>IV</th>
                    <th style={{textAlign:"left",  padding:"4px 5px"}}>VOL</th>
                    <th style={{textAlign:"left",  padding:"4px 5px"}}>PUT OI</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.chain??[]).map((row:any,i:number)=>{
                    const isMP = row.strike===data.max_pain;
                    const cW   = Math.round((Number(row.call_oi??0)/maxCOI)*60);
                    const pW   = Math.round((Number(row.put_oi ??0)/maxPOI)*60);
                    return (
                      <tr key={i} style={{
                        borderBottom:"1px solid var(--border)",
                        background:isMP?"rgba(227,179,65,0.07)":undefined,
                      }}>
                        <td style={{textAlign:"right",padding:"4px 5px"}}>
                          <div style={{display:"flex",alignItems:"center",justifyContent:"flex-end",gap:3}}>
                            <span style={{color:"var(--neg)"}}>{fmtOI(row.call_oi)}</span>
                            <div style={{width:cW,height:5,background:"var(--neg)",opacity:0.5,borderRadius:2}}/>
                          </div>
                        </td>
                        <td style={{textAlign:"right",padding:"4px 5px",color:"var(--dim)",fontSize:10}}>{fmtOI(row.call_vol)}</td>
                        <td style={{textAlign:"right",padding:"4px 5px",color:"var(--dim)"}}>
                          {row.call_iv!=null?Number(row.call_iv).toFixed(1)+"%":"--"}
                        </td>
                        <td style={{textAlign:"right",padding:"4px 5px",color:"var(--dim)"}}>
                          {row.call_delta!=null?Number(row.call_delta).toFixed(2):"--"}
                        </td>
                        <td style={{textAlign:"right",padding:"4px 5px"}}>
                          {row.call_ltp!=null?Number(row.call_ltp).toFixed(2):"--"}
                        </td>
                        <td style={{textAlign:"center",padding:"4px 10px",
                                    color:isMP?"var(--warn)":"var(--info)",
                                    fontWeight:isMP?700:600,fontSize:12}}>
                          {Number(row.strike).toLocaleString("en-IN")}
                          {isMP&&<div style={{fontSize:8,color:"var(--warn)"}}>MAX PAIN</div>}
                        </td>
                        <td style={{padding:"4px 5px"}}>
                          {row.put_ltp!=null?Number(row.put_ltp).toFixed(2):"--"}
                        </td>
                        <td style={{padding:"4px 5px",color:"var(--dim)"}}>
                          {row.put_delta!=null?Number(row.put_delta).toFixed(2):"--"}
                        </td>
                        <td style={{padding:"4px 5px",color:"var(--dim)"}}>
                          {row.put_iv!=null?Number(row.put_iv).toFixed(1)+"%":"--"}
                        </td>
                        <td style={{padding:"4px 5px",color:"var(--dim)",fontSize:10}}>{fmtOI(row.put_vol)}</td>
                        <td style={{padding:"4px 5px"}}>
                          <div style={{display:"flex",alignItems:"center",gap:3}}>
                            <div style={{width:pW,height:5,background:"var(--pos)",opacity:0.5,borderRadius:2}}/>
                            <span style={{color:"var(--pos)"}}>{fmtOI(row.put_oi)}</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            {/* GEX */}
            {tab==="gex" && (
              <div>
                <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginBottom:8}}>
                  GEX date: {data.gex_date} &nbsp;|&nbsp;
                  +ve = dealers long gamma (dampens) &nbsp;|&nbsp; -ve = short gamma (amplifies)
                </div>
                {(data.gex??[]).length===0 ? (
                  <div style={{color:"var(--muted)",fontFamily:"monospace"}}>
                    No GEX data. Run: py phase2_greeks_calculator.py --daily
                  </div>
                ) : (
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
                    <thead>
                      <tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)"}}>
                        <th style={{textAlign:"right",padding:"4px 8px"}}>STRIKE</th>
                        <th style={{textAlign:"right",padding:"4px 8px"}}>CALL GEX</th>
                        <th style={{textAlign:"right",padding:"4px 8px"}}>PUT GEX</th>
                        <th style={{textAlign:"right",padding:"4px 8px"}}>NET GEX</th>
                        <th style={{textAlign:"left", padding:"4px 8px",minWidth:120}}>BAR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...(data.gex??[])].sort((a:any,b:any)=>Number(a.strike)-Number(b.strike)).map((row:any,i:number)=>{
                        const net=Number(row.net_gex);
                        const bw =Math.round((Math.abs(net)/maxGex)*110);
                        const c  =net>=0?"var(--pos)":"var(--neg)";
                        return (
                          <tr key={i} style={{borderBottom:"1px solid var(--border)"}}>
                            <td style={{textAlign:"right",padding:"4px 8px",color:"var(--info)",fontWeight:600}}>
                              {Number(row.strike).toLocaleString("en-IN")}
                            </td>
                            <td style={{textAlign:"right",padding:"4px 8px",color:"var(--pos)"}}>{fmtGex(Number(row.call_gex))}</td>
                            <td style={{textAlign:"right",padding:"4px 8px",color:"var(--neg)"}}>{fmtGex(Number(row.put_gex))}</td>
                            <td style={{textAlign:"right",padding:"4px 8px",color:c,fontWeight:600}}>{fmtGex(net)}</td>
                            <td style={{padding:"4px 8px"}}>
                              <div style={{width:bw,height:6,background:c,borderRadius:2}}/>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* OI CHANGE */}
            {tab==="oichange" && (
              <div>
                <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginBottom:8}}>
                  OI change vs prev session -- fresh call OI = resistance, fresh put OI = support
                </div>
                {(data.oi_change??[]).length===0 ? (
                  <div style={{color:"var(--muted)",fontFamily:"monospace"}}>
                    OI change not available (need 2 dates in option_greeks_raw).
                  </div>
                ) : (
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
                    <thead>
                      <tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)"}}>
                        <th style={{textAlign:"right",padding:"4px 8px"}}>STRIKE</th>
                        <th style={{textAlign:"left", padding:"4px 8px"}}>TYPE</th>
                        <th style={{textAlign:"right",padding:"4px 8px"}}>CUR OI</th>
                        <th style={{textAlign:"right",padding:"4px 8px"}}>OI CHG</th>
                        <th style={{textAlign:"left", padding:"4px 8px"}}>SIGNAL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.oi_change??[]).map((row:any,i:number)=>{
                        const chg=Number(row.oi_chg);
                        const isCall=row.option_type==="CE";
                        const sig=chg>0&&isCall?"RESISTANCE BUILD":chg>0&&!isCall?"SUPPORT BUILD":
                                  chg<0&&isCall?"CALL UNWINDING":chg<0&&!isCall?"PUT UNWINDING":"--";
                        const sigC=chg>0&&isCall?"var(--neg)":chg>0&&!isCall?"var(--pos)":"var(--dim)";
                        return (
                          <tr key={i} style={{borderBottom:"1px solid var(--border)"}}>
                            <td style={{textAlign:"right",padding:"4px 8px",color:"var(--info)",fontWeight:600}}>
                              {Number(row.strike).toLocaleString("en-IN")}
                            </td>
                            <td style={{padding:"4px 8px",color:isCall?"var(--neg)":"var(--pos)"}}>{row.option_type}</td>
                            <td style={{textAlign:"right",padding:"4px 8px",color:"var(--dim)"}}>{fmtOI(row.cur_oi)}</td>
                            <td style={{textAlign:"right",padding:"4px 8px",
                                        color:chg>0?"var(--pos)":"var(--neg)",fontWeight:600}}>
                              {chg>0?"+":""}{fmtOI(Math.abs(chg))}
                            </td>
                            <td style={{padding:"4px 8px",fontSize:10,color:sigC}}>{sig}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>

          {/* Right: Analysis */}
          <div>
            <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em",
                         marginBottom:8,borderBottom:"1px solid var(--border)",paddingBottom:4}}>
              ANALYSIS
            </div>
            {data.analysis ? (
              <MarkdownText text={data.analysis} maxHeight={700} />
            ) : (
              <div style={{color:"var(--dim)",fontFamily:"monospace",fontSize:11}}>No analysis available.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
""")

# =============================================================================
# 7. MACRO PAGE (wraps MacroPanel)
# =============================================================================
print("\n[7/8] Writing macro page...")

w(APP / "macro" / "page.tsx", r"""
"use client";
import NavBar     from "@/components/NavBar";
import MacroPanel from "@/components/MacroPanel";

export default function MacroPage() {
  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:"16px 20px",maxWidth:1200,margin:"0 auto"}}>
        <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,
                     letterSpacing:"0.12em",color:"var(--warn)",marginBottom:14}}>
          MACRO DASHBOARD
        </div>
        <MacroPanel />
      </div>
    </div>
  );
}
""")

# =============================================================================
# 8. MF PAGE (wraps MFPanel)
# =============================================================================
print("\n[8/8] Writing MF page...")

w(APP / "mf" / "page.tsx", r"""
"use client";
import NavBar  from "@/components/NavBar";
import MFPanel from "@/components/MFPanel";

export default function MFPage() {
  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:"16px 20px",maxWidth:1200,margin:"0 auto"}}>
        <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,
                     letterSpacing:"0.12em",color:"var(--bull)",marginBottom:14}}>
          MUTUAL FUND NAV TRACKER
        </div>
        <MFPanel />
      </div>
    </div>
  );
}
""")


# =============================================================================
# SUMMARY
# =============================================================================
print()
print("=" * 70)
print("  PHASE 4 MULTIPAGE COMPLETE")
print("=" * 70)
print("""
  PAGES CREATED:
    /            -> Overview (Alpha + Beta + Gamma + Delta + 5 nav cards)
    /streaks     -> Streak Leaderboard (improved)
    /indices     -> Index Performance (top 25 + full table)
    /options     -> Options chain + GEX + OI change + analysis
    /macro       -> Macro dashboard
    /mf          -> MF NAV tracker

  SHARED COMPONENTS:
    NavBar.tsx   -> Sticky top nav with active-page highlighting + IST clock

  API UPDATES:
    /api/indices          -> top 25 (was 10), added PE/PB columns
    /api/streak-extended  -> conviction grade, consistency %, regime filter,
                             removed broken min_days, added HOT 7d strip
    /api/options          -> vol/delta/theta in chain, OI change tab,
                             analysis text panel (no LLM call needed)

  STREAK IMPROVEMENTS:
    - Conviction grade A+/A/B/C/D replaces raw score
    - Consistency % bar shows how often symbol appeared in window
    - HOT strip: symbols with 3+ days in last 7
    - Regime filter: see only BULLISH / SIDEWAYS / etc. regimes
    - Row expand (click): shows min return, max delivery, EPS days, window
    - Min Days filter removed (was broken -- anchoring to MAX(run_date) handles it)
    - Show 20/30/50/100 selector

  RESTART:
    cd D:\\MICC\\micc-dashboard && npm run dev
    Open http://localhost:3000

  NAVIGATION:
    MICC -> OVERVIEW -> STREAKS -> INDICES -> OPTIONS -> MACRO -> MF NAV
    Each page is independently loadable.
""")
