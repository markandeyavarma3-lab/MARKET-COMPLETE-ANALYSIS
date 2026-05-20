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
  const sym = (searchParams.get('symbol') || '').trim()
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  const rows = qdb(`
    SELECT direction, window_days, anchor_month, anchor_day,
           accuracy, avg_return_all, score, n_years, n_hit,
           start_label, end_label, year_confidence
    FROM seasonality_patterns WHERE symbol=?
    ORDER BY anchor_month, anchor_day, window_days
  `, [sym])

  const seasonRows = qdb(`
    SELECT period_value, mean_return_pct, n_obs
    FROM symbol_seasonality
    WHERE symbol=? AND period_type='month'
    ORDER BY period_value
  `, [sym])

  return NextResponse.json({ ok: true, symbol: sym, heatmap_rows: rows, seasonality: seasonRows })
}
