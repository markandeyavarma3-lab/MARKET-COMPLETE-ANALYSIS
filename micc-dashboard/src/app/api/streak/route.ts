import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string) {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout: 20000,
      cwd: DA,
    })
    if (result.status !== 0) throw new Error(result.stderr || 'bridge error')
    const out = result.stdout.trim()
    if (!out) return []
    return JSON.parse(out)
  } catch (e: any) {
    console.error('[streak api]', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // signals_history columns: id, run_date, symbol, score, screen_tags, pct_chg, avg_deliv_pct, earnings_flag, regime
  // NO standalone "streak" column - streak = COUNT(DISTINCT run_date) per symbol in last 30 days
  const streak = queryDb(`
    SELECT
      symbol,
      COUNT(DISTINCT run_date)    AS streak_days,
      MAX(run_date)               AS last_seen,
      ROUND(AVG(CAST(score AS REAL)), 2) AS avg_score,
      MAX(run_date)               AS max_date,
      MIN(run_date)               AS min_date,
      GROUP_CONCAT(DISTINCT screen_tags) AS all_tags
    FROM signals_history
    WHERE run_date >= date('now', '-30 days')
    GROUP BY symbol
    HAVING COUNT(DISTINCT run_date) >= 2
    ORDER BY streak_days DESC, avg_score DESC
    LIMIT 15
  `)

  const stats = queryDb(`
    SELECT
      COUNT(*)                    AS total_rows,
      COUNT(DISTINCT symbol)      AS unique_symbols,
      COUNT(DISTINCT run_date)    AS unique_dates,
      MAX(run_date)               AS latest_date
    FROM signals_history
  `)

  return NextResponse.json({ streak, stats: stats[0] || {} })
}
