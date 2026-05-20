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
    return out ? JSON.parse(out.replace(/:\s*NaN/g,': null').replace(/:\s*Infinity/g,': null').replace(/:\s*-Infinity/g,': null')) : []
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
