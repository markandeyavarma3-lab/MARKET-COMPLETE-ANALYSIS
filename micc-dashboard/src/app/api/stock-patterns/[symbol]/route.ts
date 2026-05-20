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
  const sqlB64  = Buffer.from(sql).toString("base64");
  const pyLines = [
    "import sqlite3, json, sys, base64",
    "conn = sqlite3.connect(r'" + DB + "', timeout=15)",
    "conn.row_factory = sqlite3.Row",
    "sql = base64.b64decode(sys.argv[1]).decode()",
    "params = json.loads(sys.argv[2])",
    "rows = conn.execute(sql, params).fetchall()",
    "print(json.dumps([dict(r) for r in rows], default=str))",
    "conn.close()",
  ];
  const r = spawnSync(PY, ["-c", pyLines.join("\n"), sqlB64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 20000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET(
  req: Request,
  { params }: { params: { symbol: string } }
) {
  const symbol = (params.symbol || "").toUpperCase();
  const url    = new URL(req.url);
  const limit  = Math.min(parseInt(url.searchParams.get("limit") || "20"), 100);
  const minAcc = parseFloat(url.searchParams.get("min_accuracy") || "60");
  const anchor = url.searchParams.get("anchor") || "";  // MM-DD filter

  if (!symbol) return NextResponse.json({ error: "No symbol" }, { status: 400 });

  try {
    // Check if table exists
    const tableCheck = qdb(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='seasonality_patterns_v3'", []
    );
    if (!tableCheck.length) {
      return NextResponse.json({ patterns: [], count: 0, note: "Table not built yet" });
    }

    // Base query: top patterns for this symbol
    const conditions = [
      "symbol = ?",
      "accuracy >= ?",
      "ABS(mean_ret) <= 50",
      "score >= 1",
    ];
    const qparams: any[] = [symbol, minAcc];

    if (anchor) {
      conditions.push("anchor_mm_dd = ?");
      qparams.push(anchor);
    }

    const where = "WHERE " + conditions.join(" AND ");
    const sql = [
      "SELECT anchor_mm_dd, window_days, direction,",
      "n_obs, accuracy, mean_ret, median_ret, std_ret,",
      "p25, p75, best_ret, worst_ret,",
      "score, consistency, t_stat, p_value,",
      "early_accuracy, recent_accuracy, degradation, recent_mean",
      "FROM seasonality_patterns_v3",
      where,
      "ORDER BY score DESC",
      "LIMIT " + limit,
    ].join(" ");

    const rows = qdb(sql, qparams);

    // Also get upcoming anchors (next 30 days)
    const today = new Date();
    const upcomingAnchors: string[] = [];
    for (let i = 0; i <= 30; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      const mmdd = String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
      upcomingAnchors.push(mmdd);
    }

    const upcomingSql = [
      "SELECT anchor_mm_dd, window_days, direction, accuracy, mean_ret, score",
      "FROM seasonality_patterns_v3",
      "WHERE symbol = ? AND anchor_mm_dd IN (" + upcomingAnchors.map(() => "?").join(",") + ")",
      "AND accuracy >= 65 AND ABS(mean_ret) <= 50 AND score >= 2",
      "ORDER BY score DESC LIMIT 10",
    ].join(" ");
    const upcoming = qdb(upcomingSql, [symbol, ...upcomingAnchors]);

    return NextResponse.json({ patterns: rows, count: rows.length, upcoming, symbol });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, patterns: [], count: 0 }, { status: 500 });
  }
}
