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
    { cwd: DA, encoding: "utf-8", timeout: 20000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200));
  return JSON.parse(sanitize(r.stdout.trim() || "[]"));
}

export async function GET(
  req: Request,
  { params }: { params: { symbol: string } }
) {
  const sym  = (params.symbol || "").toUpperCase();
  const url  = new URL(req.url);
  const days = Math.min(parseInt(url.searchParams.get("days") || "252"), 2000);
  const from_ = url.searchParams.get("from") || "";

  if (!sym) return NextResponse.json({ error: "No symbol" }, { status: 400 });

  try {
    let where = "WHERE symbol = ?";
    const p: any[] = [sym];
    if (from_) { where += " AND date >= ?"; p.push(from_); }

    const rows = qdb(`
      SELECT date, open, high, low, close, pct_change
      FROM global_indices_daily
      ${where}
      ORDER BY date DESC
      LIMIT ${days}
    `, p);

    rows.reverse(); // chronological

    // Compute running stats
    const closes = rows.map((r: any) => r.close).filter(Boolean);
    const returns_ = rows.map((r: any) => r.pct_change).filter((v: any) => v != null);
    const mx = closes.length ? Math.max(...closes) : null;
    const mn = closes.length ? Math.min(...closes) : null;
    const last = closes[closes.length - 1];
    const first = closes[0];
    const totalRet = first && last ? Math.round((last / first - 1) * 10000) / 100 : null;
    const avgRet   = returns_.length
      ? Math.round(returns_.reduce((a: number, b: number) => a + b, 0) / returns_.length * 100) / 100
      : null;

    return NextResponse.json({
      symbol: sym,
      rows,
      stats: {
        n: rows.length,
        first_date: rows[0]?.date,
        last_date:  rows[rows.length - 1]?.date,
        last_close: last,
        high_period: mx,
        low_period:  mn,
        total_ret_pct: totalRet,
        avg_daily_ret: avgRet,
      }
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
