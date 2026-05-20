import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'
function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) return []
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out.replace(/:\s*NaN\b/g,': null').replace(/:\s*Infinity\b/g,': null'))
  } catch { return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym    = (searchParams.get('symbol') || '').trim()
  const atype  = searchParams.get('asset_type') || 'stock'
  const month  = parseInt(searchParams.get('month') || '1')
  const day    = parseInt(searchParams.get('day')   || '1')
  const window = parseInt(searchParams.get('window') || '20')
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  let priceRows: unknown[] = []
  if (atype === 'stock') {
    priceRows = qdb(`SELECT date, close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date ASC`, [sym])
  } else if (atype === 'index') {
    priceRows = qdb(`SELECT date, closing_index_value as close FROM market_snapshot WHERE index_name=? AND closing_index_value IS NOT NULL ORDER BY date ASC`, [sym])
  } else {
    priceRows = qdb(`SELECT date, close FROM global_indices_daily WHERE symbol=? AND close IS NOT NULL ORDER BY date ASC`, [sym])
  }

  if (!priceRows.length) return NextResponse.json({ ok: false, error: 'No price data' }, { status: 404 })

  const byYear: Record<number, {date:string;close:number}[]> = {}
  for (const r of priceRows as {date:string;close:number}[]) {
    const yr = parseInt(r.date.slice(0,4))
    if (!byYear[yr]) byYear[yr] = []
    byYear[yr].push(r)
  }

  const yearPaths: Record<number, number[]> = {}
  const targetMD = `${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`

  for (const [yrStr, pts] of Object.entries(byYear)) {
    const yr = parseInt(yrStr)
    if (pts.length < 50) continue
    let bestIdx = -1, bestDelta = 999
    for (let i = 0; i < pts.length; i++) {
      const md = pts[i].date.slice(5)
      const diff = Math.abs(new Date(`2024-${md}`).getTime() - new Date(`2024-${targetMD}`).getTime()) / 86400000
      if (diff < bestDelta) { bestDelta = diff; bestIdx = i }
    }
    if (bestIdx < 0 || bestDelta > 15) continue
    const endIdx = bestIdx + window
    if (endIdx >= pts.length) continue
    const startPrice = pts[bestIdx].close
    const pathArr: number[] = []
    for (let i = bestIdx; i <= bestIdx + window && i < pts.length; i++) {
      pathArr.push(((pts[i].close - startPrice) / startPrice) * 100)
    }
    yearPaths[yr] = pathArr
  }

  return NextResponse.json({ ok: true, symbol: sym, month, day, window_days: window, year_paths: yearPaths })
}
