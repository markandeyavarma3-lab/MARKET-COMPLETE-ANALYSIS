# -*- coding: utf-8 -*-
"""
fix_search_duplicates.py  --  Run from D:\\MICC
Fixes duplicate results in /api/search/route.ts
Run: py D:\\MICC\\fix_search_duplicates.py
"""
from pathlib import Path

BASE = Path(r"D:\MICC")
APP  = BASE / "micc-dashboard" / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

print("\nFixing /api/search/route.ts...")

write(APP / "api" / "search" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 15000, cwd: DA,
    })
    if (r.status !== 0) return []
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out)
  } catch { return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const q    = (searchParams.get('q') || '').toUpperCase().trim()
  const type = searchParams.get('type') || 'stock'

  if (!q || q.length < 1) return NextResponse.json({ results: [] })

  let results: { symbol: string; name: string; sector: string; type: string }[] = []

  if (type === 'stock') {
    // Single deduplicated query using DISTINCT + best source priority
    const rows = qdb(`
      SELECT DISTINCT symbol,
             COALESCE(company_name, symbol) as name,
             COALESCE(sector, '')           as sector
      FROM stock_registry
      WHERE (symbol LIKE ? OR company_name LIKE ?)
        AND symbol IS NOT NULL
      ORDER BY
        CASE WHEN symbol = ? THEN 0
             WHEN symbol LIKE ? THEN 1
             ELSE 2 END,
        symbol
      LIMIT 10
    `, [`${q}%`, `%${q}%`, q, `${q}%`]) as { symbol: string; name: string; sector: string }[]

    // Deduplicate by symbol (keep first occurrence)
    const seen = new Set<string>()
    results = rows
      .filter(r => { if (seen.has(r.symbol)) return false; seen.add(r.symbol); return true; })
      .map(r => ({ symbol: r.symbol, name: r.name || r.symbol, sector: r.sector || '', type: 'stock' }))

  } else {
    // Index search — market_snapshot for NSE, global_indices_daily for global
    const nse = qdb(`
      SELECT DISTINCT index_name as symbol,
             index_name          as name,
             'NSE Index'         as sector
      FROM market_snapshot
      WHERE index_name LIKE ?
      ORDER BY index_name
      LIMIT 6
    `, [`%${q}%`]) as { symbol: string; name: string; sector: string }[]

    const global = qdb(`
      SELECT DISTINCT symbol,
             symbol   as name,
             'Global' as sector
      FROM global_indices_daily
      WHERE symbol LIKE ?
      ORDER BY symbol
      LIMIT 4
    `, [`%${q}%`]) as { symbol: string; name: string; sector: string }[]

    const seen = new Set<string>()
    const combined = [...nse, ...global]
    results = combined
      .filter(r => { if (seen.has(r.symbol)) return false; seen.add(r.symbol); return true; })
      .map(r => ({ ...r, type: r.sector === 'Global' ? 'global' : 'index' }))
  }

  return NextResponse.json({ results })
}
""")

print("\nDone. Restart dashboard: cd micc-dashboard && npm run dev")
