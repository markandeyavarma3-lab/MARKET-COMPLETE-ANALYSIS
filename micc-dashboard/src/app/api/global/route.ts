import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r"${DB}", timeout=15)
conn.row_factory = sqlite3.Row
p = json.loads(sys.argv[1])
rows = conn.execute("""${sql}""", p).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
`;
  const r = spawnSync(PY, ["-c", script, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  return JSON.parse(sanitize(r.stdout.trim() || "[]"));
}

export async function GET(req: Request) {
  const url  = new URL(req.url);
  const days = Math.min(parseInt(url.searchParams.get("days") || "5"), 30);
  const cat  = url.searchParams.get("category") || "";
  const sym  = url.searchParams.get("symbol") || "";

  try {
    // Get latest N trading dates across all symbols
    const dates = qdb(
      `SELECT DISTINCT date FROM global_indices_daily
       ORDER BY date DESC LIMIT ${days * 2}`
    ).map((r: any) => r.date).slice(0, days);

    if (!dates.length) return NextResponse.json({ rows: [], dates: [] });

    const minDate = dates[dates.length - 1];

    let where = "WHERE date >= ?";
    const params: any[] = [minDate];
    if (cat)  { where += " AND category = ?"; params.push(cat); }
    if (sym)  { where += " AND symbol = ?";   params.push(sym.toUpperCase()); }

    // Get latest close + pct_change for each symbol
    const latest = qdb(`
      SELECT g.symbol, g.date, g.close, g.pct_change
      FROM global_indices_daily g
      INNER JOIN (
        SELECT symbol, MAX(date) as max_date
        FROM global_indices_daily
        WHERE date >= ?
        GROUP BY symbol
      ) m ON g.symbol = m.symbol AND g.date = m.max_date
      ORDER BY g.symbol
    `, [minDate]);

    // 5-day returns for each symbol
    const fiveDay = qdb(`
      SELECT g.symbol,
        ROUND((g.close / g2.close - 1) * 100, 2) as ret_5d
      FROM global_indices_daily g
      JOIN (
        SELECT symbol, close, date FROM global_indices_daily
        WHERE date IN (
          SELECT DISTINCT date FROM global_indices_daily ORDER BY date DESC LIMIT 10
        )
      ) g2 ON g.symbol = g2.symbol
      WHERE g.date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol = g.symbol)
        AND g2.date = (
          SELECT date FROM global_indices_daily WHERE symbol = g.symbol
          ORDER BY date DESC LIMIT 1 OFFSET ${Math.min(days - 1, 4)}
        )
    `, []);

    const fiveDayMap: Record<string, number> = {};
    fiveDay.forEach((r: any) => { fiveDayMap[r.symbol] = r.ret_5d; });

    const enriched = latest.map((r: any) => ({
      ...r,
      ret_5d: fiveDayMap[r.symbol] ?? null,
    }));

    return NextResponse.json({ rows: enriched, dates, count: enriched.length });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, rows: [], dates: [] }, { status: 500 });
  }
}
