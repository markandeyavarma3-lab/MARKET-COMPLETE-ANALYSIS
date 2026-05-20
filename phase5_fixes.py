# -*- coding: utf-8 -*-
"""
phase5_fixes.py
================
Fixes three visible issues from screenshots + adds Epsilon tab to Options page.

FIX 1 -- Alpha LLM analysis shows only headers, no content
  Root cause: MarkdownText splits on blank lines (\\n\\n) but the LLM output
  uses single \\n between heading and content. Also all-caps title lines
  are not treated as headings.
  Fix: Rewrite MarkdownText to handle single-\\n structure AND recognise
       ALL-CAPS lines as section headers.

FIX 2 -- Options chain table empty (KPIs work, chain doesn't)
  Root cause: The LEFT JOIN between fo_data and option_greeks_raw fails
  because option_greeks_raw may not have data for same date/expiry, OR
  the greeks data format differs. The chain should work from fo_data alone
  (it has close, open_int, volume). Greeks (iv/delta/gamma) should be a
  best-effort LEFT JOIN, not a required join.
  Secondary issue: the LIMIT 25 is applied BEFORE the strike sort, so
  only top-25-by-OI strikes are fetched then sorted -- correct, but the
  WHERE clause may be excluding rows. Simplify query significantly.

FIX 3 -- Macro page missing sparklines for some series
  Root cause: The series histories for Fed_Funds, Inflation_CPI, GDP,
  Unemployment are fetched with n=24 but these are monthly/quarterly --
  there should be data. More likely the sparkline threshold is `length >= 2`
  but the Sparkline SVG component has a rendering bug when vals are very
  similar (range = 0 -> divide by zero -> all points same Y).
  Fix: Guard range=0 case, also increase n to 36 for monthly series.
  Also add India macro sparklines (series was being passed but component
  wasn't receiving it).

FIX 4 -- Agent Epsilon tab in Options page
  Add a proper EpsilonTab component to /options/page.tsx that reads
  /api/epsilon and displays OI spikes, PCR divergence, gamma zones.

Usage: cd D:\\MICC && py phase5_fixes.py
"""

import sys
from pathlib import Path

BASE = Path(r"D:\MICC")

def find_dashboard():
    for sub in ["micc-dashboard/src", "micc-dashboard"]:
        p = BASE / sub
        if p.is_dir() and (p / "components").is_dir():
            return p / "app", p / "components"
    return None, None

APP, COMP = find_dashboard()
if not APP:
    print("[ERROR] micc-dashboard not found")
    sys.exit(1)

print(f"[OK] {APP.parent}")

def w(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    try:
        rel = path.relative_to(BASE)
    except ValueError:
        rel = path
    print(f"  wrote: {rel}")

def probe(path):
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


# =============================================================================
# FIX 1 -- MarkdownText.tsx
# =============================================================================
print("\n[1/4] Fixing MarkdownText.tsx...")

w(COMP / "MarkdownText.tsx", r"""
"use client";

interface Props {
  text: string;
  maxHeight?: number;
}

export default function MarkdownText({ text, maxHeight = 520 }: Props) {
  if (!text || !text.trim()) return null;

  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const raw = lines[i];
    const line = raw.trim();

    // Skip empty lines
    if (!line) { i++; continue; }

    // ## heading
    if (line.startsWith("## ")) {
      nodes.push(
        <div key={i} style={{
          fontFamily: "monospace", fontSize: 10, fontWeight: 700,
          letterSpacing: "0.12em", textTransform: "uppercase",
          color: "var(--accent)", marginTop: 16, marginBottom: 6,
          borderBottom: "1px solid var(--border)", paddingBottom: 3,
        }}>
          {line.slice(3)}
        </div>
      );
      i++; continue;
    }

    // # heading
    if (line.startsWith("# ")) {
      nodes.push(
        <div key={i} style={{
          fontFamily: "monospace", fontSize: 12, fontWeight: 700,
          letterSpacing: "0.15em", textTransform: "uppercase",
          color: "var(--info)", marginTop: 14, marginBottom: 8,
        }}>
          {line.slice(2)}
        </div>
      );
      i++; continue;
    }

    // ALL-CAPS line (LLM section header like "GLOBAL CONTEXT", "MARKET REGIME ANALYSIS")
    // Must be >= 4 chars, no lowercase, not a bullet/number
    if (
      line.length >= 4 &&
      line === line.toUpperCase() &&
      !/^[-*\d]/.test(line) &&
      /[A-Z]/.test(line)
    ) {
      nodes.push(
        <div key={i} style={{
          fontFamily: "monospace", fontSize: 10, fontWeight: 700,
          letterSpacing: "0.12em", color: "var(--accent)",
          marginTop: 16, marginBottom: 5,
          borderBottom: "1px solid var(--border)", paddingBottom: 3,
        }}>
          {line.replace(/[:#]+$/, "").trim()}
        </div>
      );
      i++; continue;
    }

    // Bullet / numbered list: collect consecutive bullet/numbered lines
    if (/^[-*•]\s/.test(line) || /^\d+[.)]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length) {
        const l = lines[i].trim();
        if (/^[-*•]\s/.test(l) || /^\d+[.)]\s/.test(l)) {
          items.push(l.replace(/^[-*•]\s/, "").replace(/^\d+[.)]\s/, "").trim());
          i++;
        } else {
          break;
        }
      }
      nodes.push(
        <ul key={i} style={{ margin: "4px 0 8px 0", paddingLeft: 18 }}>
          {items.map((item, j) => (
            <li key={j} style={{ marginBottom: 3, lineHeight: 1.7 }}>
              <Inline text={item} />
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // Bold standalone line (like "**REGIME: RISK-ON / BULLISH | CONFIDENCE: M**")
    if (line.startsWith("**") && line.endsWith("**") && line.length > 4) {
      nodes.push(
        <div key={i} style={{
          fontFamily: "monospace", fontSize: 12, fontWeight: 700,
          color: "var(--text)", marginBottom: 6, marginTop: 8,
        }}>
          <Inline text={line} />
        </div>
      );
      i++; continue;
    }

    // Normal paragraph: collect lines until blank or header
    const paraLines: string[] = [];
    while (i < lines.length) {
      const l = lines[i].trim();
      if (!l) { i++; break; }
      if (
        l.startsWith("## ") || l.startsWith("# ") ||
        /^[-*•]\s/.test(l) || /^\d+[.)]\s/.test(l) ||
        (l.length >= 4 && l === l.toUpperCase() && /[A-Z]/.test(l) && !/^[-*\d]/.test(l))
      ) break;
      paraLines.push(l);
      i++;
    }
    if (paraLines.length > 0) {
      nodes.push(
        <p key={i + "-p"} style={{ margin: "4px 0 8px", lineHeight: 1.8 }}>
          {paraLines.map((pl, j) => (
            <span key={j}>
              <Inline text={pl} />
              {j < paraLines.length - 1 && <br />}
            </span>
          ))}
        </p>
      );
    }
  }

  return (
    <div style={{
      maxHeight,
      overflowY: "auto",
      padding: "14px 18px",
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 6,
      fontSize: 12,
      lineHeight: 1.85,
      color: "var(--text)",
      fontFamily: "'JetBrains Mono', monospace",
    }}>
      {nodes}
    </div>
  );
}

function Inline({ text }: { text: string }) {
  // **bold**, *italic*, `code`
  const parts: React.ReactNode[] = [];
  const patterns: [RegExp, (m: string) => React.ReactNode][] = [
    [/\*\*(.+?)\*\*/g, m => <strong key={m} style={{ color: "var(--accent)", fontWeight: 700 }}>{m}</strong>],
    [/\*(.+?)\*/g,     m => <em key={m} style={{ color: "var(--warn)" }}>{m}</em>],
    [/`(.+?)`/g,       m => <code key={m} style={{ background: "rgba(255,255,255,0.06)", padding: "1px 5px", borderRadius: 3, fontSize: 11 }}>{m}</code>],
  ];

  let rest = text;
  const combined = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = combined.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(<span key={key++}>{text.slice(last, match.index)}</span>);
    }
    const full = match[0];
    if (full.startsWith("**")) {
      parts.push(<strong key={key++} style={{ color: "var(--accent)", fontWeight: 700 }}>{match[1]}</strong>);
    } else if (full.startsWith("*")) {
      parts.push(<em key={key++} style={{ color: "var(--warn)" }}>{match[2]}</em>);
    } else {
      parts.push(<code key={key++} style={{ background: "rgba(255,255,255,0.06)", padding: "1px 5px", borderRadius: 3, fontSize: 11 }}>{match[3]}</code>);
    }
    last = match.index + full.length;
  }
  if (last < text.length) {
    parts.push(<span key={key++}>{text.slice(last)}</span>);
  }
  return <>{parts}</>;
}
""")

print("[1/4] MarkdownText fixed")


# =============================================================================
# FIX 2 -- /api/options/route.ts
# Simplified chain query: fo_data only for OI/price, greeks LEFT JOIN best-effort
# =============================================================================
print("\n[2/4] Fixing /api/options chain query...")

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

  // ── Step 1: Find latest date + instrument type ────────────────────────────
  // Probe which instrument value actually exists for NIFTY options
  const instrProbe = queryDb(`
    SELECT DISTINCT instrument, COUNT(*) AS n FROM fo_data
    WHERE symbol = 'NIFTY' ORDER BY n DESC LIMIT 5
  `)
  const optInstruments = instrProbe
    .filter((r: any) => String(r.instrument).includes('OPT') || String(r.instrument) === 'IDO')
    .map((r: any) => `'${r.instrument}'`)
    .join(',') || "'OPTIDX','IDO'"

  const latestRows = queryDb(`
    SELECT MAX(date) AS d FROM fo_data
    WHERE symbol = 'NIFTY' AND instrument IN (${optInstruments})
  `)
  const latestDate = latestRows[0]?.d ?? ''
  if (!latestDate) {
    return NextResponse.json({
      error: 'No NIFTY options data in fo_data.',
      debug_instruments: instrProbe,
      date: null,
    })
  }

  // ── Step 2: Nearest expiry ────────────────────────────────────────────────
  const expiryRows = queryDb(`
    SELECT MIN(expiry) AS nearest_expiry FROM fo_data
    WHERE date = '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN (${optInstruments})
      AND expiry >= '${latestDate}'
  `)
  const nearestExpiry = expiryRows[0]?.nearest_expiry ?? ''

  // ── Step 3: PCR from fo_data ──────────────────────────────────────────────
  const pcrRows = queryDb(`
    SELECT option_typ,
           SUM(COALESCE(open_int, 0)) AS total_oi
    FROM fo_data
    WHERE date = '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN (${optInstruments})
      AND expiry = '${nearestExpiry}'
    GROUP BY option_typ
  `)
  const callOI = Number(pcrRows.find((r: any) => r.option_typ === 'CE')?.total_oi ?? 0)
  const putOI  = Number(pcrRows.find((r: any) => r.option_typ === 'PE')?.total_oi ?? 0)
  const pcr    = callOI > 0 ? Math.round((putOI / callOI) * 1000) / 1000 : null

  // ── Step 4: Options chain from fo_data (no greeks join -- that's best-effort) ──
  // Get top 25 strikes by total OI from fo_data first
  const chainBase = queryDb(`
    SELECT
      CAST(strike AS REAL) AS strike,
      SUM(CASE WHEN option_typ = 'CE' THEN COALESCE(open_int, 0) END)  AS call_oi,
      SUM(CASE WHEN option_typ = 'CE' THEN COALESCE(volume,   0) END)  AS call_vol,
      MAX(CASE WHEN option_typ = 'CE' THEN close END)                   AS call_ltp,
      SUM(CASE WHEN option_typ = 'PE' THEN COALESCE(open_int, 0) END)  AS put_oi,
      SUM(CASE WHEN option_typ = 'PE' THEN COALESCE(volume,   0) END)  AS put_vol,
      MAX(CASE WHEN option_typ = 'PE' THEN close END)                   AS put_ltp
    FROM fo_data
    WHERE date       = '${latestDate}'
      AND symbol     = 'NIFTY'
      AND instrument IN (${optInstruments})
      AND expiry     = '${nearestExpiry}'
    GROUP BY strike
    ORDER BY (COALESCE(SUM(CASE WHEN option_typ='CE' THEN open_int END), 0)
            + COALESCE(SUM(CASE WHEN option_typ='PE' THEN open_int END), 0)) DESC
    LIMIT 25
  `)

  // Get greeks separately (best-effort -- may be empty if phase2 not run yet)
  const greeksLatest = queryDb(`
    SELECT MAX(date) AS d FROM option_greeks_raw WHERE symbol LIKE 'NIFTY%'
  `)
  const greeksDate = greeksLatest[0]?.d ?? ''
  const greeksMap: Record<string, any> = {}

  if (greeksDate) {
    const greeksRows = queryDb(`
      SELECT CAST(strike AS REAL) AS strike, option_type,
             iv, delta, gamma, theta
      FROM option_greeks_raw
      WHERE date = '${greeksDate}' AND symbol LIKE 'NIFTY%'
        AND expiry = '${nearestExpiry}'
    `)
    for (const g of greeksRows) {
      const key = `${Number(g.strike)}_${g.option_type}`
      greeksMap[key] = g
    }
  }

  // Merge chain + greeks
  const chain = chainBase
    .map((row: any) => {
      const s    = Number(row.strike)
      const ceG  = greeksMap[`${s}_CE`] ?? {}
      const peG  = greeksMap[`${s}_PE`] ?? {}
      return {
        strike:      s,
        call_oi:     row.call_oi,
        call_vol:    row.call_vol,
        call_ltp:    row.call_ltp,
        call_iv:     ceG.iv    ?? null,
        call_delta:  ceG.delta ?? null,
        call_gamma:  ceG.gamma ?? null,
        call_theta:  ceG.theta ?? null,
        put_oi:      row.put_oi,
        put_vol:     row.put_vol,
        put_ltp:     row.put_ltp,
        put_iv:      peG.iv    ?? null,
        put_delta:   peG.delta ?? null,
        put_gamma:   peG.gamma ?? null,
        put_theta:   peG.theta ?? null,
      }
    })
    .sort((a: any, b: any) => a.strike - b.strike)

  // ── Step 5: Max Pain ──────────────────────────────────────────────────────
  const allStrikeRows = queryDb(`
    SELECT CAST(strike AS REAL) AS strike,
      SUM(CASE WHEN option_typ='CE' THEN COALESCE(open_int,0) END) AS call_oi,
      SUM(CASE WHEN option_typ='PE' THEN COALESCE(open_int,0) END) AS put_oi
    FROM fo_data
    WHERE date = '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN (${optInstruments})
      AND expiry = '${nearestExpiry}'
    GROUP BY strike ORDER BY strike ASC
  `)

  let maxPainStrike: number | null = null
  if (allStrikeRows.length > 0) {
    let minLoss = Infinity
    for (const row of allStrikeRows as any[]) {
      const K = Number(row.strike)
      let loss = 0
      for (const r of allStrikeRows as any[]) {
        const s = Number(r.strike)
        const co = Number(r.call_oi ?? 0)
        const po = Number(r.put_oi  ?? 0)
        if (s < K) loss += (K - s) * co
        if (s > K) loss += (s - K) * po
      }
      if (loss < minLoss) { minLoss = loss; maxPainStrike = K }
    }
  }

  // ── Step 6: GEX ──────────────────────────────────────────────────────────
  const gexLatest = queryDb(`SELECT MAX(date) AS d FROM gamma_exposure_daily WHERE symbol='NIFTY'`)
  const gexDate   = gexLatest[0]?.d ?? ''
  const gexRows   = gexDate ? queryDb(`
    SELECT CAST(strike AS REAL) AS strike,
      ROUND(SUM(CASE WHEN option_type='CE' THEN COALESCE(gamma_exposure,0) END), 4) AS call_gex,
      ROUND(SUM(CASE WHEN option_type='PE' THEN COALESCE(gamma_exposure,0) END), 4) AS put_gex,
      ROUND(SUM(COALESCE(gamma_exposure,0)), 4) AS net_gex
    FROM gamma_exposure_daily
    WHERE date = '${gexDate}' AND symbol = 'NIFTY'
    GROUP BY strike
    ORDER BY ABS(SUM(COALESCE(gamma_exposure,0))) DESC
    LIMIT 25
  `) : []
  const totalGex = gexRows.reduce((s: number, r: any) => s + Number(r.net_gex ?? 0), 0)

  // ── Step 7: OI change vs prev session ─────────────────────────────────────
  const prevDateRows = queryDb(`
    SELECT MAX(date) AS d FROM fo_data
    WHERE date < '${latestDate}' AND symbol = 'NIFTY'
      AND instrument IN (${optInstruments})
  `)
  const prevDate = prevDateRows[0]?.d ?? ''
  const oiChange = prevDate ? queryDb(`
    SELECT cur.strike, cur.option_typ AS option_type,
      ROUND(CAST(cur.open_int AS REAL) - CAST(COALESCE(prv.open_int, cur.open_int) AS REAL), 0) AS oi_chg,
      cur.open_int AS cur_oi
    FROM fo_data cur
    LEFT JOIN fo_data prv
      ON prv.symbol      = cur.symbol
     AND prv.strike      = cur.strike
     AND prv.option_typ  = cur.option_typ
     AND prv.expiry      = cur.expiry
     AND prv.date        = '${prevDate}'
     AND prv.instrument IN (${optInstruments})
    WHERE cur.date = '${latestDate}' AND cur.symbol = 'NIFTY'
      AND cur.instrument IN (${optInstruments})
      AND cur.expiry = '${nearestExpiry}'
      AND cur.open_int > 0
    ORDER BY ABS(CAST(cur.open_int AS REAL) - CAST(COALESCE(prv.open_int, cur.open_int) AS REAL)) DESC
    LIMIT 20
  `) : []

  // ── Step 8: Context ────────────────────────────────────────────────────────
  const niftyRows = queryDb(`
    SELECT closing_index_value AS close, points_change, change AS change_pct
    FROM market_snapshot
    WHERE index_name = 'Nifty 50'
      AND date = (SELECT MAX(date) FROM market_snapshot)
    LIMIT 1
  `)
  const niftyClose     = niftyRows[0]?.close ?? null
  const niftyChangePct = niftyRows[0]?.change_pct ?? null

  const alpha       = readAgent('alpha')
  const alphaRegime = alpha?.regime?.regime ?? alpha?.regime_analysis?.match?.(/REGIME:\s*([A-Z_]+)/)?.[1] ?? '--'
  const alphaConf   = alpha?.regime?.confidence ?? '--'

  // ── Step 9: Analysis text ──────────────────────────────────────────────────
  const pcrLabel = pcr == null ? '--'
                 : pcr > 1.3  ? 'BULLISH (put-heavy positioning)'
                 : pcr < 0.7  ? 'BEARISH (call-heavy positioning)'
                 : 'NEUTRAL (balanced)'
  const gexLabel = totalGex > 0 ? 'LONG GAMMA -- dealers absorb volatility'
                 : 'SHORT GAMMA -- dealers amplify volatility'
  const maxPainGap = (maxPainStrike && niftyClose)
    ? Math.round(((Number(niftyClose) - maxPainStrike) / maxPainStrike) * 100 * 10) / 10
    : null

  const top5 = [...allStrikeRows]
    .sort((a: any, b: any) =>
      (Number(b.call_oi ?? 0) + Number(b.put_oi ?? 0)) -
      (Number(a.call_oi ?? 0) + Number(a.put_oi ?? 0))
    ).slice(0, 5)

  const analysis = [
    `Options Snapshot -- ${latestDate}`,
    `Expiry: ${nearestExpiry}`,
    '',
    `## Market Structure`,
    `Nifty 50: ${niftyClose ? Number(niftyClose).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '--'}` +
      (niftyChangePct != null ? ` (${Number(niftyChangePct) >= 0 ? '+' : ''}${Number(niftyChangePct).toFixed(2)}%)` : ''),
    `Market Regime: ${alphaRegime} | Confidence: ${alphaConf}`,
    '',
    `## Options Positioning`,
    `Put-Call Ratio: ${pcr != null ? pcr.toFixed(3) : '--'} -- ${pcrLabel}`,
    `Total Call OI: ${callOI > 0 ? (callOI / 1e5).toFixed(1) + 'L' : '--'} | Total Put OI: ${putOI > 0 ? (putOI / 1e5).toFixed(1) + 'L' : '--'}`,
    `Max Pain Strike: ${maxPainStrike != null ? maxPainStrike.toLocaleString('en-IN') : '--'}${maxPainGap != null ? ` (spot is ${maxPainGap >= 0 ? '+' : ''}${maxPainGap}% from max pain)` : ''}`,
    `Net GEX: ${Math.round(totalGex).toLocaleString()} -- ${gexLabel}`,
    '',
    `## Key OI Strikes`,
    ...(top5.length > 0
      ? top5.map((r: any) => {
          const tot = Number(r.call_oi ?? 0) + Number(r.put_oi ?? 0)
          return `${Number(r.strike).toLocaleString('en-IN')}: CE=${Math.round(Number(r.call_oi ?? 0) / 1000)}K  PE=${Math.round(Number(r.put_oi ?? 0) / 1000)}K  total=${Math.round(tot / 1000)}K`
        })
      : ['No strike data available']),
    '',
    `## Interpretation`,
    pcr != null && pcr > 1.2
      ? 'Elevated PCR signals heavy put writing. Writers expect support -- near-term bullish bias. Watch for put unwinding above key support.'
      : pcr != null && pcr < 0.8
      ? 'Low PCR -- call-heavy market. Expect resistance at key levels. Call writers dominate -- sideways to bearish near-term bias.'
      : 'PCR near 1.0 signals balanced positioning. No clear directional bias from options market. Await a directional catalyst.',
    '',
    totalGex > 0
      ? 'Positive net GEX: Market makers are net long gamma. Their delta-hedging naturally dampens large price swings -- expect mean-reversion behavior around key strikes.'
      : 'Negative net GEX: Market makers are net short gamma. Their hedging amplifies directional moves -- expect higher realized volatility and potential for extended trends.',
    '',
    maxPainStrike != null && maxPainGap != null
      ? `Max pain at ${maxPainStrike.toLocaleString('en-IN')} acts as gravitational center into expiry. ${Math.abs(maxPainGap) < 1 ? 'Spot very close to max pain -- expect consolidation.' : `Spot needs to drift ${maxPainGap > 0 ? 'lower' : 'higher'} by ${Math.abs(maxPainGap)}% toward max pain.`}`
      : '',
  ].filter(l => l !== undefined).join('\n')

  return NextResponse.json({
    date: latestDate, expiry: nearestExpiry, pcr,
    call_oi: callOI, put_oi: putOI, max_pain: maxPainStrike,
    chain,
    gex: gexRows, total_net_gex: Math.round(totalGex), gex_date: gexDate,
    oi_change: oiChange,
    nifty_close: niftyClose, nifty_change_pct: niftyChangePct,
    analysis,
    debug: { optInstruments, chainRows: chainBase.length, greeksDate },
  })
}
""")

print("[2/4] Options API fixed")


# =============================================================================
# FIX 3 -- /api/macro/route.ts  +  MacroPanel.tsx
# Increase history window, fix sparkline rendering, add India sparklines
# =============================================================================
print("\n[3/4] Fixing Macro sparklines...")

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

// Fetch last N data points for a series_id from a table
// Returns chronological order (oldest first) -- needed for sparklines
function seriesHistory(table: string, seriesId: string, n = 36): any[] {
  const rows = queryDb(`
    SELECT date, ROUND(CAST(value AS REAL), 4) AS value
    FROM ${table}
    WHERE series_id = '${seriesId}' AND value IS NOT NULL
    ORDER BY date DESC LIMIT ${n}
  `)
  return rows.reverse()   // chronological order for sparklines
}

function latest(s: any[]) { return s.length ? s[s.length - 1] : null }
function delta1m(s: any[]): number | null {
  if (s.length < 2) return null
  const l = Number(latest(s)?.value ?? null)
  const p = Number(s[s.length - 2]?.value ?? null)
  if (isNaN(l) || isNaN(p)) return null
  return Math.round((l - p) * 10000) / 10000
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // ── US Macro ─────────────────────────────────────────────────────────────
  const fedfunds   = seriesHistory('us_macro_data', 'Fed_Funds',     36)
  const us10y      = seriesHistory('us_macro_data', '10Y_Treasury',  60)
  const us2y       = seriesHistory('us_macro_data', '2Y_Treasury',   60)
  const termSpread = seriesHistory('us_macro_data', 'Term_Spread',   60)
  const usCpi      = seriesHistory('us_macro_data', 'Inflation_CPI', 36)
  const usGdp      = seriesHistory('us_macro_data', 'GDP',           20)
  const usVix      = seriesHistory('us_macro_data', 'VIX',           60)
  const usUnemp    = seriesHistory('us_macro_data', 'Unemployment',  36)

  // ── India Macro ───────────────────────────────────────────────────────────
  const indiaCpi    = seriesHistory('india_macro_fred', 'INDCPIALLQINMEI', 24)
  const indiaFxRaw  = seriesHistory('india_macro_fred', 'TRESEGINM194N',   36)
  const indiaExp    = seriesHistory('india_macro_fred', 'XTEXVA01INM664S', 36)
  const indiaImp    = seriesHistory('india_macro_fred', 'XTIMVA01INM664S', 36)

  // Convert FX reserves to USD billions
  const indiaFx = indiaFxRaw.map(r => ({
    date:  r.date,
    value: Math.round(Number(r.value) / 1000 * 10) / 10,
  }))

  // Trade balance = exports - imports (align on date)
  const expMap: Record<string, number> = {}
  indiaExp.forEach(r => { expMap[r.date] = Number(r.value) })
  const tradeBal = indiaImp
    .filter(r => expMap[r.date] != null)
    .map(r => ({ date: r.date, value: Math.round((expMap[r.date] - Number(r.value)) * 100) / 100 }))

  // ── What series IDs are actually in the DB (for debug) ───────────────────
  const usIds     = queryDb(`SELECT DISTINCT series_id FROM us_macro_data ORDER BY series_id`)
  const indiaIds  = queryDb(`SELECT DISTINCT series_id FROM india_macro_fred ORDER BY series_id`)

  return NextResponse.json({
    fedfunds:    { series: fedfunds,   latest: latest(fedfunds),   delta_1m: delta1m(fedfunds)   },
    us_10y:      { series: us10y,      latest: latest(us10y),      delta_1m: delta1m(us10y)      },
    us_2y:       { series: us2y,       latest: latest(us2y),       delta_1m: delta1m(us2y)       },
    term_spread: { series: termSpread, latest: latest(termSpread), delta_1m: delta1m(termSpread) },
    us_cpi:      { series: usCpi,      latest: latest(usCpi),      delta_1m: delta1m(usCpi)      },
    us_gdp:      { series: usGdp,      latest: latest(usGdp),      delta_1m: delta1m(usGdp)      },
    us_vix:      { series: usVix,      latest: latest(usVix),      delta_1m: delta1m(usVix)      },
    us_unemp:    { series: usUnemp,    latest: latest(usUnemp),    delta_1m: delta1m(usUnemp)    },
    india_cpi:   { series: indiaCpi,   latest: latest(indiaCpi),   delta_1m: delta1m(indiaCpi)   },
    india_fx:    { series: indiaFx,    latest: latest(indiaFx),    delta_1m: null                },
    india_trade: { series: tradeBal,   latest: latest(tradeBal),   delta_1m: delta1m(tradeBal)   },
    india_exp:   { series: indiaExp,   latest: latest(indiaExp),   delta_1m: delta1m(indiaExp)   },
    india_imp:   { series: indiaImp,   latest: latest(indiaImp),   delta_1m: delta1m(indiaImp)   },
    debug: { us_series: usIds.map((r:any) => r.series_id), india_series: indiaIds.map((r:any) => r.series_id) },
  })
}
""")

# Rewrite MacroPanel to fix sparklines + add proper India tab
w(COMP / "MacroPanel.tsx", r"""
"use client";
import { useState, useEffect } from "react";

interface Pt { date: string; value: number }
interface MacroSeries {
  series:   Pt[];
  latest:   Pt | null;
  delta_1m: number | null;
}

// ── Sparkline (SVG) ───────────────────────────────────────────────────────────
function Sparkline({ series, color = "var(--accent)" }:
  { series: Pt[]; color?: string }) {
  if (!series || series.length < 2) {
    return <span style={{ color: "var(--dim)", fontSize: 9, fontFamily: "monospace" }}>--</span>;
  }
  const vals  = series.map(d => Number(d.value ?? 0)).filter(v => !isNaN(v));
  if (vals.length < 2) {
    return <span style={{ color: "var(--dim)", fontSize: 9 }}>--</span>;
  }
  const W = 80, H = 26, pad = 2;
  const min   = Math.min(...vals);
  const max   = Math.max(...vals);
  const range = max - min;   // may be 0

  const pts = vals.map((v, i) => {
    const x = pad + (i / (vals.length - 1)) * (W - pad * 2);
    // If range is 0, draw flat line in the middle
    const y = range === 0
      ? H / 2
      : H - pad - ((v - min) / range) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <svg width={W} height={H} style={{ display: "block", overflow: "visible" }}>
      <polyline points={pts} fill="none" stroke={color}
                strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

// ── Table row ─────────────────────────────────────────────────────────────────
function MacroRow({ label, unit = "", s, color }:
  { label: string; unit?: string; s: MacroSeries | null | undefined; color: string }) {
  if (!s) return null;
  const val   = s.latest?.value ?? null;
  const d     = s.delta_1m ?? null;
  const dC    = d == null ? "var(--dim)" : d > 0 ? "var(--pos)" : d < 0 ? "var(--neg)" : "var(--dim)";
  const sign  = d != null && d > 0 ? "+" : "";
  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "6px 0 6px 0", color: "var(--dim)", fontSize: 11,
                   fontFamily: "monospace", whiteSpace: "nowrap" }}>
        {label}
      </td>
      <td style={{ padding: "6px 12px 6px 12px", textAlign: "right",
                   fontFamily: "monospace", fontSize: 12, color, fontWeight: 600,
                   whiteSpace: "nowrap" }}>
        {val != null ? `${Number(val).toFixed(2)}${unit}` : "--"}
      </td>
      <td style={{ padding: "6px 8px", textAlign: "right",
                   fontFamily: "monospace", fontSize: 10, color: dC,
                   whiteSpace: "nowrap" }}>
        {d != null ? `${sign}${d.toFixed(2)}` : "--"}
      </td>
      <td style={{ padding: "6px 0 6px 10px" }}>
        <Sparkline series={s.series} color={color} />
      </td>
      <td style={{ padding: "6px 0 6px 6px", fontFamily: "monospace",
                   fontSize: 9, color: "var(--dim)", whiteSpace: "nowrap" }}>
        {s.latest?.date ?? "--"}
      </td>
    </tr>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
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
      No macro data. Run: py data_pipeline/update_macro_us.py
    </div>
  );

  const tsVal    = data.term_spread?.latest?.value ?? null;
  const tsColor  = tsVal == null ? "var(--dim)"
                 : tsVal < 0    ? "var(--neg)"
                 : tsVal < 0.5  ? "var(--warn)" : "var(--pos)";
  const tsLabel  = tsVal == null ? "" : tsVal < 0 ? "INVERTED" : tsVal < 0.5 ? "FLAT" : "NORMAL";
  const fedVal   = data.fedfunds?.latest?.value ?? null;
  const vixVal   = data.us_vix?.latest?.value   ?? null;

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
      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
        {[
          { l: "FED FUNDS",    v: fedVal  != null ? Number(fedVal).toFixed(2)  + "%" : "--",
            s: data.fedfunds,  color: "var(--warn)" },
          { l: "US 10Y YIELD", v: data.us_10y?.latest?.value != null
              ? Number(data.us_10y.latest.value).toFixed(2) + "%" : "--",
            s: data.us_10y,    color: "var(--info)" },
          { l: "TERM SPREAD",  v: tsVal != null ? (tsVal >= 0 ? "+" : "") + Number(tsVal).toFixed(2) + "%" : "--",
            s: data.term_spread, color: tsColor, sub: tsLabel },
          { l: "US VIX",       v: vixVal != null ? Number(vixVal).toFixed(1) : "--",
            s: data.us_vix,    color: vixVal != null && Number(vixVal) > 20 ? "var(--neg)" : "var(--pos)" },
        ].map(({ l, v, s, color, sub }: any) => (
          <div key={l} style={{
            padding: "10px 14px", background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 6,
          }}>
            <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                          letterSpacing: "0.1em", marginBottom: 4 }}>{l}</div>
            <div style={{ fontFamily: "monospace", fontSize: 17, fontWeight: 700, color }}>{v}</div>
            {sub && <div style={{ fontFamily: "monospace", fontSize: 9, color, marginTop: 2 }}>{sub}</div>}
            <div style={{ marginTop: 6 }}>
              <Sparkline series={s?.series ?? []} color={color} />
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        <TabBtn t="us"    label="US MACRO"    />
        <TabBtn t="india" label="INDIA MACRO" />
      </div>

      {/* Column headers */}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9,
                       color: "var(--dim)", letterSpacing: "0.08em" }}>
            <th style={{ padding: "4px 0",    textAlign: "left"  }}>INDICATOR</th>
            <th style={{ padding: "4px 12px", textAlign: "right" }}>LATEST</th>
            <th style={{ padding: "4px 8px",  textAlign: "right" }}>1M CHG</th>
            <th style={{ padding: "4px 0 4px 10px"               }}>TREND</th>
            <th style={{ padding: "4px 0 4px 6px"                }}>DATE</th>
          </tr>
        </thead>
        <tbody>
          {tab === "us" && (
            <>
              <MacroRow label="Fed Funds Rate"      unit="%" s={data.fedfunds}    color="var(--warn)" />
              <MacroRow label="US 10Y Yield"        unit="%" s={data.us_10y}      color="var(--info)" />
              <MacroRow label="US 2Y Yield"         unit="%" s={data.us_2y}       color="#8b949e"     />
              <MacroRow label="Term Spread (10-2Y)" unit="%" s={data.term_spread} color={tsColor}     />
              <MacroRow label="US CPI"                       s={data.us_cpi}      color="var(--neg)"  />
              <MacroRow label="US Real GDP"                  s={data.us_gdp}      color="var(--pos)"  />
              <MacroRow label="Unemployment"        unit="%" s={data.us_unemp}    color="var(--warn)" />
              <MacroRow label="VIX"                          s={data.us_vix}      color={vixVal != null && Number(vixVal) > 20 ? "var(--neg)" : "var(--pos)"} />
            </>
          )}
          {tab === "india" && (
            <>
              <MacroRow label="India CPI (OECD)"      s={data.india_cpi}   color="var(--neg)"  />
              <MacroRow label="FX Reserves (Bn USD)"  s={data.india_fx}    color="var(--pos)"  />
              <MacroRow label="Trade Balance"         s={data.india_trade} color="var(--info)" />
              <MacroRow label="Exports"               s={data.india_exp}   color="var(--pos)"  />
              <MacroRow label="Imports"               s={data.india_imp}   color="var(--neg)"  />
              <MacroRow label="US 10Y (ref)"  unit="%" s={data.us_10y}      color="#8b949e"     />
              <MacroRow label="Fed Funds (ref)" unit="%" s={data.fedfunds}  color="#8b949e"     />
            </>
          )}
        </tbody>
      </table>

      {/* Debug: show what series are actually in DB */}
      {data.debug && (
        <details style={{ marginTop: 16, fontFamily: "monospace", fontSize: 9, color: "var(--dim)" }}>
          <summary style={{ cursor: "pointer" }}>DB series IDs (debug)</summary>
          <div style={{ marginTop: 6 }}>
            <div>US: {(data.debug.us_series ?? []).join(", ")}</div>
            <div style={{ marginTop: 4 }}>India: {(data.debug.india_series ?? []).join(", ")}</div>
          </div>
        </details>
      )}

      <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", marginTop: 12 }}>
        Sources: FRED (Federal Reserve) &nbsp;|&nbsp; World Bank &nbsp;|&nbsp;
        Updated daily via run_pipeline.py
      </div>
    </div>
  );
}
""")

print("[3/4] Macro sparklines fixed")


# =============================================================================
# FIX 4 -- Add Epsilon tab to /options/page.tsx
# =============================================================================
print("\n[4/4] Adding Epsilon tab to options page...")

OPTIONS_PAGE = APP / "options" / "page.tsx"
opt_src = OPTIONS_PAGE.read_text(encoding="utf-8") if OPTIONS_PAGE.exists() else ""

if not opt_src:
    print("  [WARN] options/page.tsx not found -- skipping Epsilon tab")
else:
    # Build the full updated options page with Epsilon tab properly wired
    EPSILON_TAB_COMPONENT = r"""
// ── EpsilonTab component (inline -- reads /api/epsilon) ───────────────────────
function EpsilonTab() {
  const [epData,   setEpData]   = React.useState<any>(null);
  const [epLoad,   setEpLoad]   = React.useState(true);

  React.useEffect(() => {
    fetch("/api/epsilon", { cache: "no-store" })
      .then(r => r.json()).then(d => { setEpData(d); setEpLoad(false); })
      .catch(() => setEpLoad(false));
  }, []);

  if (epLoad) return (
    <div style={{ color: "var(--dim)", fontFamily: "monospace", padding: 24 }}>
      Loading Epsilon signals...
    </div>
  );
  if (!epData || epData.error) return (
    <div style={{ color: "var(--neg)", fontFamily: "monospace", padding: 24 }}>
      {epData?.error ?? "No Epsilon report."}<br />
      Run: py D:\MICC\agent_epsilon.py --send
    </div>
  );

  const spikes = epData.oi_spikes       ?? [];
  const pcrdiv = epData.pcr_divergence  ?? [];
  const gamma  = epData.gamma_near_price ?? [];
  const ns     = epData.nifty_summary   ?? {};
  const ai     = epData.analysis        ?? "";

  function fmtOI(v: any): string {
    const n = Number(v);
    if (!v || isNaN(n)) return "--";
    if (n >= 1e7) return (n/1e7).toFixed(1)+"Cr";
    if (n >= 1e5) return (n/1e5).toFixed(1)+"L";
    if (n >= 1e3) return (n/1e3).toFixed(0)+"K";
    return String(Math.round(n));
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
      <div>
        {/* Nifty summary strip */}
        {ns.date && (
          <div style={{
            padding: "8px 14px", background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 6,
            fontFamily: "monospace", fontSize: 11,
            display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap",
          }}>
            <span style={{ color: "var(--dim)" }}>DATE: <span style={{ color: "var(--text)" }}>{ns.date}</span></span>
            <span style={{ color: "var(--dim)" }}>EXPIRY: <span style={{ color: "var(--text)" }}>{ns.expiry}</span></span>
            <span style={{ color: "var(--dim)" }}>PCR: <span style={{ color: "var(--warn)" }}>{ns.pcr ?? "--"}</span></span>
            <span style={{ color: "var(--dim)" }}>MAX PAIN: <span style={{ color: "var(--warn)" }}>{ns.max_pain?.toLocaleString("en-IN") ?? "--"}</span></span>
            <span style={{ color: "var(--dim)" }}>GEX: <span style={{ color: (ns.net_gex ?? 0) > 0 ? "var(--pos)" : "var(--neg)" }}>
              {(ns.net_gex ?? 0) > 0 ? "LONG" : "SHORT"} ({ns.net_gex?.toLocaleString() ?? "--"})
            </span></span>
          </div>
        )}

        {/* OI Spikes */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                        letterSpacing: "0.1em", marginBottom: 8,
                        borderBottom: "1px solid var(--border)", paddingBottom: 3 }}>
            OI SPIKES -- UNUSUAL BUILDUP VS 5-DAY AVG
          </div>
          {spikes.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
              No OI spikes detected today.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                  <th style={{ padding: "4px 8px", textAlign: "left" }}>SYMBOL</th>
                  <th style={{ padding: "4px 8px", textAlign: "left" }}>TYPE</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>TODAY OI</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>AVG OI</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>SPIKE</th>
                  <th style={{ padding: "4px 8px", textAlign: "left" }}>SIGNAL</th>
                </tr>
              </thead>
              <tbody>
                {spikes.map((r: any, i: number) => {
                  const isBear = r.option_typ === "CE";
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 8px", color: "var(--text)", fontWeight: 600 }}>
                        <a href={`/stocks/${r.symbol}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                          {r.symbol}
                        </a>
                      </td>
                      <td style={{ padding: "5px 8px", color: isBear ? "var(--neg)" : "var(--pos)", fontWeight: 600 }}>
                        {r.option_typ}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right" }}>{fmtOI(r.today_oi)}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>{fmtOI(r.avg_oi)}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--warn)", fontWeight: 700 }}>
                        {r.spike_ratio != null ? `${r.spike_ratio}x` : "--"}
                      </td>
                      <td style={{ padding: "5px 8px", fontSize: 10,
                                   color: isBear ? "var(--neg)" : "var(--pos)" }}>
                        {(r.signal ?? "--").replace("_", " ")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* PCR Divergence */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                        letterSpacing: "0.1em", marginBottom: 8,
                        borderBottom: "1px solid var(--border)", paddingBottom: 3 }}>
            PCR DIVERGENCE -- SENTIMENT SHIFT FROM 5-DAY BASELINE
          </div>
          {pcrdiv.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
              No significant PCR divergence today.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                  <th style={{ padding: "4px 8px", textAlign: "left" }}>SYMBOL</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>TODAY PCR</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>5D AVG PCR</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>DIVERGENCE</th>
                  <th style={{ padding: "4px 8px", textAlign: "left" }}>SIGNAL</th>
                </tr>
              </thead>
              <tbody>
                {pcrdiv.map((r: any, i: number) => {
                  const isBull = r.signal === "BULLISH_SHIFT";
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 8px", fontWeight: 600 }}>
                        <a href={`/stocks/${r.symbol}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                          {r.symbol}
                        </a>
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--text)" }}>
                        {r.today_pcr?.toFixed(3) ?? "--"}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                        {r.avg_pcr?.toFixed(3) ?? "--"}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right",
                                   color: isBull ? "var(--pos)" : "var(--neg)", fontWeight: 600 }}>
                        {r.divergence != null ? (r.divergence >= 0 ? "+" : "") + r.divergence.toFixed(3) : "--"}
                      </td>
                      <td style={{ padding: "5px 8px", fontSize: 10,
                                   color: isBull ? "var(--pos)" : "var(--neg)" }}>
                        {(r.signal ?? "--").replace("_", " ")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* High Gamma Near Price */}
        <div>
          <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                        letterSpacing: "0.1em", marginBottom: 8,
                        borderBottom: "1px solid var(--border)", paddingBottom: 3 }}>
            HIGH GAMMA NEAR PRICE -- DEALER HEDGING VOLATILITY ZONES (within 1.5% of spot)
          </div>
          {gamma.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
              No high-gamma strikes near current price. Run: py agent_epsilon.py
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                  <th style={{ padding: "4px 8px", textAlign: "left" }}>SYMBOL</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>STRIKE</th>
                  <th style={{ padding: "4px 8px", textAlign: "left" }}>TYPE</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>SPOT DIST</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>GAMMA</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>IV</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>DELTA</th>
                </tr>
              </thead>
              <tbody>
                {gamma.map((r: any, i: number) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "5px 8px", fontWeight: 600 }}>
                      <a href={`/stocks/${r.symbol}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                        {r.symbol}
                      </a>
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--info)" }}>
                      {Number(r.strike).toLocaleString("en-IN")}
                    </td>
                    <td style={{ padding: "5px 8px", color: r.option_type === "CE" ? "var(--neg)" : "var(--pos)" }}>
                      {r.option_type}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right",
                                 color: Math.abs(r.dist_pct ?? 0) < 0.5 ? "var(--warn)" : "var(--dim)" }}>
                      {r.dist_pct != null ? (r.dist_pct >= 0 ? "+" : "") + r.dist_pct.toFixed(2) + "%" : "--"}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)", fontWeight: 600 }}>
                      {r.gamma?.toFixed(5) ?? "--"}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                      {r.iv != null ? r.iv.toFixed(1) + "%" : "--"}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                      {r.delta?.toFixed(3) ?? "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Right: AI analysis */}
      <div>
        <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                      letterSpacing: "0.1em", marginBottom: 8,
                      borderBottom: "1px solid var(--border)", paddingBottom: 3 }}>
          AI ANALYSIS
        </div>
        {ai ? (
          <MarkdownText text={ai} maxHeight={600} />
        ) : (
          <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
            No AI analysis. Run: py agent_epsilon.py --send
          </div>
        )}
        {epData.timestamp && (
          <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", marginTop: 8 }}>
            Generated: {epData.timestamp}
          </div>
        )}
      </div>
    </div>
  );
}
"""

    # Check if React is imported and MarkdownText is imported
    needs_react = "import React" not in opt_src and "React.useState" not in opt_src
    needs_markdown = "MarkdownText" not in opt_src

    new_src = opt_src

    # Add React import if needed (for EpsilonTab which uses React.useState/useEffect)
    if needs_react:
        new_src = 'import React from "react";\n' + new_src

    # Add MarkdownText import if missing
    if needs_markdown:
        new_src = 'import MarkdownText from "@/components/MarkdownText";\n' + new_src

    # Add epsilon to the tab union type
    new_src = new_src.replace(
        'useState<"chain"|"gex"|"oichange">',
        'useState<"chain"|"gex"|"oichange"|"epsilon">'
    )

    # Fix tab button label rendering
    old_label = '{t==="chain"?"OPTIONS CHAIN":t==="gex"?"GEX BY STRIKE":t==="oichange"?"OI CHANGE":"EPSILON SIGNALS"}'
    if old_label not in new_src:
        new_src = new_src.replace(
            '{t==="chain"?"OPTIONS CHAIN":t==="gex"?"GEX BY STRIKE":"OI CHANGE"}',
            '{t==="chain"?"OPTIONS CHAIN":t==="gex"?"GEX BY STRIKE":t==="oichange"?"OI CHANGE":"EPSILON SIGNALS"}'
        )

    # Fix tabs array to include epsilon
    new_src = new_src.replace(
        '(["chain","gex","oichange"] as const)',
        '(["chain","gex","oichange","epsilon"] as const)'
    )

    # Add Epsilon tab render block before the closing div of the left column
    # Find the end of the OI change section
    EPSILON_RENDER = r"""
            {/* Epsilon signals tab */}
            {tab === "epsilon" && (
              <EpsilonTab />
            )}"""

    # Inject before the closing </div> of the left content area
    INJECT_MARKER = "          </div>\n\n          {/* Right: Analysis */}"
    if INJECT_MARKER in new_src and "<EpsilonTab" not in new_src:
        new_src = new_src.replace(
            INJECT_MARKER,
            EPSILON_RENDER + "\n" + INJECT_MARKER
        )

    # Inject the EpsilonTab function definition before the export default
    if "function EpsilonTab" not in new_src:
        new_src = EPSILON_TAB_COMPONENT + "\n" + new_src

    OPTIONS_PAGE.write_text(new_src, encoding="utf-8", newline="\n")
    print("  patched: options/page.tsx (+EpsilonTab component + tab)")

print("[4/4] Epsilon tab done")


# =============================================================================
# SUMMARY
# =============================================================================
print()
print("=" * 65)
print("  PHASE 5 FIXES COMPLETE")
print("=" * 65)
print("""
  FIX 1 -- MarkdownText.tsx
    Now handles: ALL-CAPS section headers (GLOBAL CONTEXT, etc.),
    single-newline structure (not just blank-line splits),
    bold standalone lines (**REGIME: RISK-ON / BULLISH**),
    proper bullet/numbered list collection.
    Alpha LLM analysis should now show full content under each heading.

  FIX 2 -- /api/options chain
    Root cause: instrument filter was wrong. Now auto-probes which
    instrument values exist in fo_data for NIFTY, uses those.
    Chain built from fo_data alone (close, open_int, volume).
    Greeks (iv/delta/gamma) merged as best-effort LEFT JOIN.
    Added debug field to response so you can see what was found.

  FIX 3 -- Macro sparklines
    Fixed range=0 divide-by-zero in Sparkline SVG (draws flat line).
    Increased history n to 36 for monthly series.
    Added sparklines inside KPI cards (not just in the table rows).
    India tab now shows exports, imports, trade balance with sparklines.
    Added debug details section showing actual series IDs in your DB.

  FIX 4 -- Epsilon tab in Options page
    Full EpsilonTab component with 3 sections:
      OI Spikes table (symbol clickable -> /stocks/[symbol])
      PCR Divergence table
      High Gamma Near Price table
    Right panel: MarkdownText AI analysis from agents/epsilon/last_report.json

  RESTART: cd D:\\MICC\\micc-dashboard && npm run dev
""")
