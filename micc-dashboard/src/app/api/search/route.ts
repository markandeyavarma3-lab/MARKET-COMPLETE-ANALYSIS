import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function qdb(sql: string, params: any[] = []): any[] {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r"D:/marketDB/db/market.db", timeout=10)
conn.row_factory = sqlite3.Row
p = json.loads(sys.argv[1])
rows = conn.execute("""` + sql + `""", p).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
`;
  const r = spawnSync(PY, ["-c", script, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 8000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(r.stdout.trim() || "[]"); } catch { return []; }
}

export async function GET(req: Request) {
  const url   = new URL(req.url);
  const q     = (url.searchParams.get("q") || "").trim().toUpperCase();
  const limit = Math.min(parseInt(url.searchParams.get("limit") || "15"), 30);

  if (!q || q.length < 1) return NextResponse.json({ results: [] });

  const pattern = `%${q}%`;

  try {
    const stocks = qdb(`
      SELECT DISTINCT symbol,
             COALESCE(company_name, symbol) as name,
             'stock' as type
      FROM stock_registry
      WHERE (UPPER(symbol) LIKE ? OR UPPER(company_name) LIKE ?)
        AND symbol IS NOT NULL
      ORDER BY
        CASE WHEN UPPER(symbol) = ? THEN 0
             WHEN UPPER(symbol) LIKE ? THEN 1
             ELSE 2 END,
        symbol
      LIMIT ?
    `, [pattern, pattern, q, q + "%", limit]);

    const indices = qdb(`
      SELECT DISTINCT name as symbol, name, 'index' as type
      FROM indices_data WHERE UPPER(name) LIKE ? LIMIT 5
    `, [pattern]);

    const globals = qdb(`
      SELECT DISTINCT symbol, symbol as name, 'global' as type
      FROM global_indices_daily WHERE UPPER(symbol) LIKE ? LIMIT 5
    `, [pattern]);

    const seen = new Set<string>();
    const results: any[] = [];
    for (const row of [...stocks, ...indices, ...globals]) {
      const key = (row.symbol || "").toUpperCase();
      if (!seen.has(key) && key) {
        seen.add(key);
        results.push({ symbol: row.symbol, name: row.name || row.symbol, type: row.type });
      }
    }
    return NextResponse.json({ results: results.slice(0, limit) });
  } catch (e: any) {
    return NextResponse.json({ results: [], error: e.message });
  }
}
