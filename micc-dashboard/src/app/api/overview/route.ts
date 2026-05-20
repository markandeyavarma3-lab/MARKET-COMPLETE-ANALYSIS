import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const b64 = Buffer.from(sql).toString("base64");
  const py  = [
    "import sqlite3,json,sys,base64",
    "conn=sqlite3.connect(r'" + DB + "',timeout=10)",
    "conn.row_factory=sqlite3.Row",
    "sql=base64.b64decode(sys.argv[1]).decode()",
    "params=json.loads(sys.argv[2])",
    "rows=conn.execute(sql,params).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\n");
  const r = spawnSync(PY, ["-c", py, b64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 12000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET() {
  try {
    // Latest market snapshot
    const snap = qdb(
      "SELECT * FROM market_snapshot ORDER BY date DESC LIMIT 1", []
    );
    const s = snap[0] || {};

    // Nifty + BankNifty from global_indices_daily
    const indices = qdb(
      "SELECT symbol, close, pct_change FROM global_indices_daily " +
      "WHERE symbol IN ('NIFTY50','NIFTYBANK') " +
      "AND date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)",
      []
    );
    const bySymbol: Record<string, any> = {};
    for (const r of indices) bySymbol[r.symbol] = r;

    // Top gainers / losers from market_snapshot or signals_history
    const gainers = qdb(
      "SELECT symbol, pct_change FROM signals_history " +
      "WHERE date = (SELECT MAX(date) FROM signals_history) " +
      "AND pct_change IS NOT NULL " +
      "ORDER BY pct_change DESC LIMIT 5",
      []
    );
    const losers = qdb(
      "SELECT symbol, pct_change FROM signals_history " +
      "WHERE date = (SELECT MAX(date) FROM signals_history) " +
      "AND pct_change IS NOT NULL " +
      "ORDER BY pct_change ASC LIMIT 5",
      []
    );

    return NextResponse.json({
      date:         s.date || null,
      nifty:        bySymbol["NIFTY50"]   || null,
      niftybank:    bySymbol["NIFTYBANK"] || null,
      advances:     s.advances   || null,
      declines:     s.declines   || null,
      unchanged:    s.unchanged  || null,
      total_volume_cr: s.total_volume_cr || null,
      top_gainers:  gainers,
      top_losers:   losers,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
