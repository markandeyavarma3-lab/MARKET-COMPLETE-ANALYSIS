import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout: 15000,
      cwd: DA,
    })
    if (result.status !== 0) return []
    const out = result.stdout.trim()
    return out ? JSON.parse(out.replace(/:\s*NaN/g,': null').replace(/:\s*Infinity/g,': null').replace(/:\s*-Infinity/g,': null')) : []
  } catch { return [] }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  const tables = [
    { label: 'market_snapshot',  sql: "SELECT MAX(date) AS d FROM market_snapshot" },
    { label: 'indices_data',     sql: "SELECT MAX(date) AS d FROM indices_data" },
    { label: 'stock_delivery',   sql: "SELECT MAX(date) AS d FROM stock_delivery" },
    { label: 'fii_dii_data',     sql: "SELECT MAX(date) AS d FROM fii_dii_data" },
    { label: 'fo_data',          sql: "SELECT MAX(date) AS d FROM fo_data" },
    { label: 'global_data',      sql: "SELECT MAX(date) AS d FROM global_data" },
    { label: 'signals_history',  sql: "SELECT MAX(run_date) AS d FROM signals_history" },
  ]

  const status = tables.map(({ label, sql }) => {
    const rows = queryDb(sql)
    return { table: label, latest_date: rows[0]?.d || 'N/A' }
  })

  return NextResponse.json({ status, checked_at: new Date().toISOString() })
}
