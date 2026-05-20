import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 45000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[calwin]', r.stderr?.slice(0, 400)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out.replace(/:\s*NaN/g, ': null').replace(/:\s*Infinity/g, ': null')) : []
  } catch(e) { console.error('[calwin]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

// Calendar windows to analyze (month-day pairs, window lengths)
// These are the "same calendar period repeated each year" windows
const CALENDAR_WINDOWS = [
  // (label, start_mmdd, end_mmdd, approx_days)
  { label: "Jan",       start_mm: 1,  start_dd: 1,  end_mm: 1,  end_dd: 31,  days: 21 },
  { label: "Feb",       start_mm: 2,  start_dd: 1,  end_mm: 2,  end_dd: 28,  days: 20 },
  { label: "Mar",       start_mm: 3,  start_dd: 1,  end_mm: 3,  end_dd: 31,  days: 21 },
  { label: "Apr",       start_mm: 4,  start_dd: 1,  end_mm: 4,  end_dd: 30,  days: 21 },
  { label: "May",       start_mm: 5,  start_dd: 1,  end_mm: 5,  end_dd: 31,  days: 21 },
  { label: "Jun",       start_mm: 6,  start_dd: 1,  end_mm: 6,  end_dd: 30,  days: 21 },
  { label: "Jul",       start_mm: 7,  start_dd: 1,  end_mm: 7,  end_dd: 31,  days: 21 },
  { label: "Aug",       start_mm: 8,  start_dd: 1,  end_mm: 8,  end_dd: 31,  days: 21 },
  { label: "Sep",       start_mm: 9,  start_dd: 1,  end_mm: 9,  end_dd: 30,  days: 21 },
  { label: "Oct",       start_mm: 10, start_dd: 1,  end_mm: 10, end_dd: 31,  days: 21 },
  { label: "Nov",       start_mm: 11, start_dd: 1,  end_mm: 11, end_dd: 30,  days: 21 },
  { label: "Dec",       start_mm: 12, start_dd: 1,  end_mm: 12, end_dd: 31,  days: 21 },
  { label: "Q1",        start_mm: 1,  start_dd: 1,  end_mm: 3,  end_dd: 31,  days: 63 },
  { label: "Q2",        start_mm: 4,  start_dd: 1,  end_mm: 6,  end_dd: 30,  days: 63 },
  { label: "Q3",        start_mm: 7,  start_dd: 1,  end_mm: 9,  end_dd: 30,  days: 63 },
  { label: "Q4",        start_mm: 10, start_dd: 1,  end_mm: 12, end_dd: 31,  days: 63 },
  { label: "Jan-Mar",   start_mm: 1,  start_dd: 15, end_mm: 3,  end_dd: 15,  days: 42 },
  { label: "Mar-May",   start_mm: 3,  start_dd: 15, end_mm: 5,  end_dd: 15,  days: 42 },
  { label: "May-Jul",   start_mm: 5,  start_dd: 15, end_mm: 7,  end_dd: 15,  days: 42 },
  { label: "Jul-Sep",   start_mm: 7,  start_dd: 15, end_mm: 9,  end_dd: 15,  days: 42 },
  { label: "Sep-Nov",   start_mm: 9,  start_dd: 15, end_mm: 11, end_dd: 15,  days: 42 },
  { label: "Nov-Jan",   start_mm: 11, start_dd: 15, end_mm: 1,  end_dd: 15,  days: 42 },
  { label: "Budget Ses",start_mm: 1,  start_dd: 25, end_mm: 2,  end_dd: 15,  days: 15 },
  { label: "Result Q1", start_mm: 4,  start_dd: 10, end_mm: 5,  end_dd: 20,  days: 28 },
  { label: "Result Q2", start_mm: 7,  start_dd: 10, end_mm: 8,  end_dd: 20,  days: 28 },
  { label: "Result Q3", start_mm: 10, start_dd: 10, end_mm: 11, end_dd: 20,  days: 28 },
  { label: "Diwali Win",start_mm: 10, start_dd: 15, end_mm: 11, end_dd: 15,  days: 21 },
  { label: "H1",        start_mm: 1,  start_dd: 1,  end_mm: 6,  end_dd: 30,  days: 126 },
  { label: "H2",        start_mm: 7,  start_dd: 1,  end_mm: 12, end_dd: 31,  days: 126 },
  { label: "Full Year", start_mm: 1,  start_dd: 1,  end_mm: 12, end_dd: 31,  days: 252 },
]

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym = (searchParams.get('symbol') || '').toUpperCase().trim()
  const assetType = searchParams.get('type') || 'stock'

  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  // Get full price history
  const table = assetType === 'stock' ? 'stock_data' : 'market_snapshot'
  const col   = assetType === 'stock' ? 'symbol'     : 'index_name'
  const priceRows = qdb(
    `SELECT date, close FROM ${table} WHERE ${col}=? AND close IS NOT NULL ORDER BY date ASC`,
    [sym]
  ) as { date: string; close: number }[]

  if (priceRows.length < 252) {
    return NextResponse.json({ ok: false, error: `Not enough data for ${sym} (${priceRows.length} rows)` })
  }

  // Build date->close lookup
  const priceMap: Record<string, number> = {}
  for (const r of priceRows) priceMap[r.date] = r.close

  // Get all unique years in the data
  const years = [...new Set(priceRows.map(r => parseInt(r.date.slice(0, 4))))].sort()

  // For each calendar window, find the nearest trading day start/end in each year
  const results = []

  for (const cw of CALENDAR_WINDOWS) {
    const yearResults: { year: number; start_date: string; end_date: string; return_pct: number; up: boolean }[] = []

    for (const year of years) {
      // Find nearest trading day ON OR AFTER start date
      const startTarget = `${year}-${String(cw.start_mm).padStart(2,'0')}-${String(cw.start_dd).padStart(2,'0')}`
      const endYear = (cw.end_mm < cw.start_mm) ? year + 1 : year  // handle Nov-Jan wrap
      const endTarget   = `${endYear}-${String(cw.end_mm).padStart(2,'0')}-${String(cw.end_dd).padStart(2,'0')}`

      // Find nearest available trading day at or after start
      let startDate = ''
      let endDate   = ''
      for (const r of priceRows) {
        if (!startDate && r.date >= startTarget) startDate = r.date
        if (!endDate   && r.date >= endTarget)   endDate   = r.date
        if (startDate && endDate) break
      }

      if (!startDate || !endDate || startDate >= endDate) continue
      if (endYear > Math.max(...years)) continue  // skip incomplete wrap years

      const p0 = priceMap[startDate]
      const p1 = priceMap[endDate]
      if (!p0 || !p1) continue

      const ret = ((p1 - p0) / p0) * 100
      yearResults.push({ year, start_date: startDate, end_date: endDate, return_pct: parseFloat(ret.toFixed(2)), up: ret > 0 })
    }

    if (yearResults.length < 3) continue

    const nYears  = yearResults.length
    const nUp     = yearResults.filter(y => y.up).length
    const nDown   = nYears - nUp
    const accuracy = nUp / nYears
    const avgReturn = yearResults.reduce((s, y) => s + y.return_pct, 0) / nYears
    const avgUpReturn   = yearResults.filter(y => y.up).reduce((s, y) => s + y.return_pct, 0) / (nUp || 1)
    const avgDownReturn = yearResults.filter(y => !y.up).reduce((s, y) => s + y.return_pct, 0) / (nDown || 1)
    const maxUp   = Math.max(...yearResults.map(y => y.return_pct))
    const maxDown = Math.min(...yearResults.map(y => y.return_pct))
    const stdDev  = Math.sqrt(yearResults.reduce((s, y) => s + Math.pow(y.return_pct - avgReturn, 2), 0) / nYears)

    results.push({
      label: cw.label,
      start_mm: cw.start_mm, start_dd: cw.start_dd,
      end_mm:   cw.end_mm,   end_dd:   cw.end_dd,
      days: cw.days,
      n_years:   nYears,
      n_up:      nUp,
      n_down:    nDown,
      accuracy:  parseFloat(accuracy.toFixed(4)),
      avg_return:     parseFloat(avgReturn.toFixed(2)),
      avg_up_return:  parseFloat(avgUpReturn.toFixed(2)),
      avg_down_return:parseFloat(avgDownReturn.toFixed(2)),
      max_up:   parseFloat(maxUp.toFixed(2)),
      max_down: parseFloat(maxDown.toFixed(2)),
      std_dev:  parseFloat(stdDev.toFixed(2)),
      year_data: yearResults,   // full year-by-year breakdown
    })
  }

  // Sort: highest accuracy first
  results.sort((a, b) => b.accuracy - a.accuracy)

  return NextResponse.json({
    ok: true, symbol: sym, asset_type: assetType,
    total_years: years.length,
    year_range: `${years[0]}-${years[years.length - 1]}`,
    windows: results,
    top_bullish: results.filter(r => r.accuracy >= 0.70).slice(0, 10),
    top_bearish: results.filter(r => r.accuracy <= 0.30).slice(0, 10),
  })
}
