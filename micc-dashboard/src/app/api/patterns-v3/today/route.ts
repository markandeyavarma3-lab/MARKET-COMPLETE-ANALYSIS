import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB  = "D:/marketDB/db/market.db";
const PY  = "py";
const DA  = "D:/MICC";

// Simple in-process cache (resets on server restart)
let _cache: { date: string; data: any[] } | null = null;

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const b64 = Buffer.from(sql).toString("base64");
  const py  = [
    "import sqlite3,json,sys,base64",
    "conn=sqlite3.connect(r'" + DB + "',timeout=15)",
    "conn.row_factory=sqlite3.Row",
    "sql=base64.b64decode(sys.argv[1]).decode()",
    "params=json.loads(sys.argv[2])",
    "rows=conn.execute(sql,params).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\n");
  const r = spawnSync(PY, ["-c", py, b64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 20000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET(req: Request) {
  const url      = new URL(req.url);
  const minAcc   = parseFloat(url.searchParams.get("min_accuracy") || "65");
  const minScore = parseFloat(url.searchParams.get("min_score")    || "5");
  const limit    = Math.min(parseInt(url.searchParams.get("limit") || "20"), 100);
  const dir      = (url.searchParams.get("direction") || "").toUpperCase();

  const today = new Date();
  const mmdd  = String(today.getMonth() + 1).padStart(2, "0") + "-" +
                String(today.getDate()).padStart(2, "0");

  // Return cache if same day
  if (_cache && _cache.date === mmdd) {
    const filtered = _cache.data
      .filter(r => !dir || r.direction === dir)
      .filter(r => r.accuracy >= minAcc && r.score >= minScore)
      .slice(0, limit);
    return NextResponse.json({ date: mmdd, count: filtered.length, rows: filtered, cached: true });
  }

  try {
    const sql = [
      "SELECT symbol, anchor_mm_dd, window_days, direction,",
      "n_obs, accuracy, mean_ret, median_ret, std_ret,",
      "score, consistency, t_stat, p_value,",
      "early_accuracy, recent_accuracy, degradation, recent_mean",
      "FROM seasonality_patterns_v3",
      "WHERE anchor_mm_dd = ?",
      "AND ABS(mean_ret) <= 50",
      "ORDER BY score DESC",
      "LIMIT 200",
    ].join(" ");

    const rows = qdb(sql, [mmdd]);

    // Cache all 200, filter on request
    _cache = { date: mmdd, data: rows };

    const filtered = rows
      .filter((r: any) => !dir || r.direction === dir)
      .filter((r: any) => r.accuracy >= minAcc && r.score >= minScore)
      .slice(0, limit);

    return NextResponse.json({
      date: mmdd, count: filtered.length, rows: filtered,
      total_today: rows.length, cached: false,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, date: mmdd, rows: [] }, { status: 500 });
  }
}
