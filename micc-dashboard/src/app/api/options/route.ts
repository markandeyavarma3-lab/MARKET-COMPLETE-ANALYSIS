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
    return out ? JSON.parse(out.replace(/:\s*NaN/g,': null').replace(/:\s*Infinity/g,': null').replace(/:\s*-Infinity/g,': null')) : []
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
      SUM(CASE WHEN option_typ = 'CE' THEN COALESCE(f.volume,   0) END)  AS call_vol,
      MAX(CASE WHEN option_typ = 'CE' THEN close END)                   AS call_ltp,
      SUM(CASE WHEN option_typ = 'PE' THEN COALESCE(open_int, 0) END)  AS put_oi,
      SUM(CASE WHEN option_typ = 'PE' THEN COALESCE(f.volume,   0) END)  AS put_vol,
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
