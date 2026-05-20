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
    return out ? JSON.parse(out.replace(/:\s*NaN/g,': null').replace(/:\s*Infinity/g,': null').replace(/:\s*-Infinity/g,': null')) : []
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
