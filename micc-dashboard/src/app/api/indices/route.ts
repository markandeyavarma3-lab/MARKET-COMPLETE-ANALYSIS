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
    if (r.status !== 0) { console.error('[indices]', r.stderr?.slice(0,200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out.replace(/:\s*NaN/g,': null').replace(/:\s*Infinity/g,': null').replace(/:\s*-Infinity/g,': null')) : []
  } catch (e: any) { console.error('[indices]', e.message); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const days = Math.min(parseInt(searchParams.get('days') || '7'), 365)

  const rows = queryDb(`
    WITH latest_date AS (SELECT MAX(date) AS max_date FROM market_snapshot),
    start_date AS (SELECT date(max_date, '-${days + 14} days') AS s FROM latest_date),
    date_range AS (
      SELECT DISTINCT date FROM market_snapshot
      WHERE date >= (SELECT s FROM start_date) ORDER BY date ASC
    ),
    window_start AS (
      SELECT MIN(date) AS wd FROM (
        SELECT date FROM date_range ORDER BY date DESC LIMIT ${days + 1}
      )
    ),
    window_end AS (SELECT MAX(date) AS wd FROM date_range),
    start_snap AS (
      SELECT index_name, closing_index_value AS start_close, pe AS start_pe
      FROM market_snapshot WHERE date = (SELECT wd FROM window_start)
    ),
    end_snap AS (
      SELECT index_name, closing_index_value AS end_close, pe AS end_pe, pb, div_yield
      FROM market_snapshot WHERE date = (SELECT wd FROM window_end)
    )
    SELECT
      e.index_name  AS name,
      ROUND(s.start_close,2) AS start_close,
      ROUND(e.end_close,  2) AS end_close,
      ROUND((e.end_close - s.start_close) / s.start_close * 100, 2) AS pct_change,
      ROUND(e.end_pe,   2) AS pe,
      ROUND(e.pb,       2) AS pb,
      ROUND(e.div_yield,2) AS div_yield
    FROM end_snap e
    JOIN start_snap s ON e.index_name = s.index_name
    WHERE s.start_close > 0 AND e.end_close > 0
      AND e.index_name NOT LIKE '%Inverse%'
      AND e.index_name NOT LIKE '%1x%'
      AND e.index_name NOT LIKE 'India VIX%'
      AND e.index_name NOT LIKE 'INDIA VIX%'
    ORDER BY pct_change DESC
  `)

  return NextResponse.json({
    gainers: rows.slice(0, 25),
    losers:  [...rows].reverse().slice(0, 25),
    all:     rows,
    days,
    total:   rows.length,
  })
}
