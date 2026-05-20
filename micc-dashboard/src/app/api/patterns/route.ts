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
    if (r.status !== 0) { console.error('[patterns]', r.stderr?.slice(0,300)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out.replace(/:\s*NaN\b/g,': null').replace(/:\s*Infinity\b/g,': null'))
  } catch(e) { console.error('[patterns]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym        = (searchParams.get('symbol') || '').trim()
  const direction  = searchParams.get('direction') || 'both'
  const minAcc     = parseFloat(searchParams.get('min_acc')   || '0.70')
  const minYears   = parseInt(searchParams.get('min_years')   || '5')
  const minReturn  = parseFloat(searchParams.get('min_ret')   || '0')
  const windowF    = parseInt(searchParams.get('window')      || '0')
  const confF      = searchParams.get('confidence') || ''
  const degF       = searchParams.get('degradation') || ''
  const sortBy     = searchParams.get('sort') || 'score'

  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  // Check table exists
  const tblCheck = qdb(
    `SELECT COUNT(*) as n FROM sqlite_master WHERE type='table' AND name='seasonality_patterns'`
  )
  const tblExists = (tblCheck[0] as Record<string,unknown>)?.n as number > 0
  if (!tblExists) {
    return NextResponse.json({
      ok: false, not_built: true,
      error: 'seasonality_patterns table not found. Run build_seasonality_v2.py first.',
    }, { status: 404 })
  }

  // Check patterns exist for this symbol
  const chk = qdb(`SELECT COUNT(*) as n FROM seasonality_patterns WHERE symbol=?`, [sym])
  const total_n = (chk[0] as Record<string,unknown>)?.n as number || 0
  if (total_n === 0) {
    return NextResponse.json({
      ok: false, not_computed: true,
      error: `No seasonality patterns for "${sym}". Run build_seasonality_v2.py to compute.`,
    }, { status: 404 })
  }

  // Build dynamic filters
  const filters: string[] = [
    `symbol=?`, `accuracy >= ?`, `n_years >= ?`,
    `ABS(avg_return_all) >= ?`,
  ]
  const params: unknown[] = [sym, minAcc, minYears, minReturn]

  if (direction !== 'both') { filters.push(`direction=?`); params.push(direction); }
  if (windowF > 0)           { filters.push(`window_days=?`); params.push(windowF); }
  if (confF)                 { filters.push(`year_confidence=?`); params.push(confF); }
  if (degF)                  { filters.push(`degradation_flag=?`); params.push(degF); }

  const whereClause = filters.join(' AND ')

  const sortMap: Record<string, string> = {
    score:    'score DESC',
    accuracy: 'accuracy DESC, n_years DESC',
    n_years:  'n_years DESC, accuracy DESC',
    avg_ret:  'ABS(avg_return_all) DESC',
    window:   'window_days ASC, accuracy DESC',
  }
  const orderClause = sortMap[sortBy] || 'score DESC'

  const patterns = qdb(`
    SELECT direction, window_days, anchor_month, anchor_day,
           start_label, end_label, n_years, n_hit, accuracy,
           avg_return_all, avg_return_hit, median_return,
           std_return, min_return, max_return, p25_return, p75_return,
           score, year_confidence, degradation_flag,
           first_half_accuracy, last_half_accuracy,
           success_years, failure_years, yearly_returns,
           best_year, worst_year
    FROM seasonality_patterns
    WHERE ${whereClause}
    ORDER BY ${orderClause}
    LIMIT 300
  `, params)

  // Summary stats
  const summary = qdb(`
    SELECT direction,
           COUNT(*) as n,
           AVG(accuracy) as avg_acc,
           MAX(accuracy) as max_acc,
           AVG(score) as avg_score,
           MAX(score) as max_score,
           AVG(n_years) as avg_years,
           SUM(CASE WHEN year_confidence='GREEN'  THEN 1 ELSE 0 END) as green_n,
           SUM(CASE WHEN year_confidence='YELLOW' THEN 1 ELSE 0 END) as yellow_n,
           SUM(CASE WHEN year_confidence='RED'    THEN 1 ELSE 0 END) as red_n,
           SUM(CASE WHEN year_confidence='DANGER' THEN 1 ELSE 0 END) as danger_n,
           SUM(CASE WHEN degradation_flag='DEGRADING'  THEN 1 ELSE 0 END) as degrading_n,
           SUM(CASE WHEN degradation_flag='IMPROVING'  THEN 1 ELSE 0 END) as improving_n,
           SUM(CASE WHEN degradation_flag='STABLE'     THEN 1 ELSE 0 END) as stable_n
    FROM seasonality_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction
  `, [sym, minAcc, minYears])

  // By window distribution
  const byWindow = qdb(`
    SELECT direction, window_days,
           COUNT(*) as n, AVG(accuracy) as avg_acc,
           MAX(accuracy) as max_acc, AVG(score) as avg_score
    FROM seasonality_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction, window_days
    ORDER BY direction, window_days
  `, [sym, minAcc, minYears])

  // By month distribution (which months have most patterns)
  const byMonth = qdb(`
    SELECT direction, anchor_month,
           COUNT(*) as n, AVG(accuracy) as avg_acc
    FROM seasonality_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction, anchor_month
    ORDER BY direction, anchor_month
  `, [sym, minAcc, minYears])

  // Asset info
  const assetInfo = qdb(`
    SELECT asset_type FROM seasonality_patterns WHERE symbol=? LIMIT 1
  `, [sym])

  // Latest price
  const assetType = (assetInfo[0] as Record<string,unknown>)?.asset_type as string || 'stock'
  let price: unknown[] = []
  if (assetType === 'stock') {
    price = qdb(`SELECT close, date FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`, [sym])
  } else if (assetType === 'index') {
    price = qdb(`SELECT close, date FROM indices_data WHERE index_name=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1`, [sym])
  } else {
    price = qdb(`SELECT close, date FROM global_indices_daily WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1`, [sym])
  }

  return NextResponse.json({
    ok: true, symbol: sym,
    asset_type: assetType,
    total_patterns: total_n,
    patterns,
    summary,
    by_window: byWindow,
    by_month: byMonth,
    latest_price: price[0] || null,
    active_filters: { min_acc: minAcc, min_years: minYears, direction, window: windowF },
  })
}
