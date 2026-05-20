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
    if (r.status !== 0) { console.error('[mf]', r.stderr?.slice(0, 200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out.replace(/:\s*NaN/g,': null').replace(/:\s*Infinity/g,': null').replace(/:\s*-Infinity/g,': null')) : []
  } catch (e: any) { console.error('[mf]', e.message); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  // mf_nav_history columns: scheme_code, scheme_name, date, nav
  const latestRows = queryDb(`SELECT MAX(date) AS d FROM mf_nav_history`)
  const latestDate = latestRows[0]?.d ?? ''
  if (!latestDate) {
    return NextResponse.json({ error: 'No data in mf_nav_history', date: null })
  }

  const prevDateRows = queryDb(`SELECT MAX(date) AS d FROM mf_nav_history WHERE date < '${latestDate}'`)
  const prevDate = prevDateRows[0]?.d ?? ''

  // Top 20 by NAV
  const topRows = prevDate ? queryDb(`
    SELECT
      n.scheme_code AS code,
      n.scheme_name AS name,
      ROUND(CAST(n.nav AS REAL), 4) AS nav,
      ROUND((CAST(n.nav AS REAL) - CAST(p.nav AS REAL)) / NULLIF(CAST(p.nav AS REAL),0) * 100, 4) AS change_pct,
      ROUND(CAST(p.nav AS REAL), 4) AS prev_nav,
      n.date
    FROM mf_nav_history n
    LEFT JOIN mf_nav_history p
      ON n.scheme_code = p.scheme_code AND p.date = '${prevDate}'
    WHERE n.date = '${latestDate}'
    ORDER BY CAST(n.nav AS REAL) DESC
    LIMIT 20
  `) : queryDb(`
    SELECT scheme_code AS code, scheme_name AS name,
           ROUND(CAST(nav AS REAL),4) AS nav,
           NULL AS change_pct, NULL AS prev_nav, date
    FROM mf_nav_history
    WHERE date = '${latestDate}'
    ORDER BY CAST(nav AS REAL) DESC LIMIT 20
  `)

  // Top gainers
  const gainers = prevDate ? queryDb(`
    SELECT
      n.scheme_code AS code,
      n.scheme_name AS name,
      ROUND(CAST(n.nav AS REAL), 4) AS nav,
      ROUND((CAST(n.nav AS REAL) - CAST(p.nav AS REAL)) / NULLIF(CAST(p.nav AS REAL),0) * 100, 4) AS change_pct
    FROM mf_nav_history n
    JOIN mf_nav_history p
      ON n.scheme_code = p.scheme_code AND p.date = '${prevDate}'
    WHERE n.date = '${latestDate}' AND CAST(p.nav AS REAL) > 0
    ORDER BY change_pct DESC LIMIT 15
  `) : []

  // Stats
  const stats = queryDb(`
    SELECT
      COUNT(*) AS total_funds,
      COUNT(DISTINCT date) AS date_count,
      MAX(date) AS latest_date,
      MIN(date) AS earliest_date,
      ROUND(AVG(CAST(nav AS REAL)),2) AS avg_nav,
      ROUND(MAX(CAST(nav AS REAL)),2) AS max_nav,
      ROUND(MIN(CAST(nav AS REAL)),2) AS min_nav
    FROM mf_nav_history
  `)

  return NextResponse.json({
    date: latestDate, prev_date: prevDate,
    top_funds: topRows, gainers,
    stats: stats[0] ?? {},
  })
}
