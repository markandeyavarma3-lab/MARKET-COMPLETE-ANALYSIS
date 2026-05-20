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
  const sqlB64   = Buffer.from(sql).toString("base64");
  const pyLines  = [
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
    { cwd: DA, encoding: "utf-8", timeout: 30000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET(req: Request) {
  const url      = new URL(req.url);
  const symbol   = (url.searchParams.get("symbol") || "").toUpperCase();
  const win      = url.searchParams.get("window")    || "";
  const dir      = (url.searchParams.get("direction") || "").toUpperCase();
  const month    = url.searchParams.get("month")     || "";
  const anchor   = url.searchParams.get("anchor")    || "";
  const sort     = url.searchParams.get("sort")      || "score";
  const limit    = Math.min(parseInt(url.searchParams.get("limit") || "100"), 500);
  const minAcc   = parseFloat(url.searchParams.get("min_accuracy") || "60");
  const minScore = parseFloat(url.searchParams.get("min_score")    || "1");
  const maxMean  = parseFloat(url.searchParams.get("max_mean_ret") || "50");

  try {
    const conditions: string[] = ["accuracy >= ?", "score >= ?", "ABS(mean_ret) <= ?"];
    const params: any[]        = [minAcc, minScore, maxMean];

    if (symbol) { conditions.push("symbol = ?");             params.push(symbol); }
    if (win)    { conditions.push("window_days = ?");         params.push(parseInt(win)); }
    if (dir)    { conditions.push("direction = ?");           params.push(dir); }
    if (anchor) { conditions.push("anchor_mm_dd = ?");        params.push(anchor); }
    if (month)  { conditions.push("anchor_mm_dd LIKE ?");     params.push(month + "-%"); }

    const SORTS: Record<string, string> = {
      score:"score", accuracy:"accuracy", mean_ret:"ABS(mean_ret)",
      consistency:"consistency", t_stat:"ABS(t_stat)", p_value:"p_value",
      n_obs:"n_obs", degradation:"degradation",
    };
    const sortCol = SORTS[sort] || "score";
    const sortDir = sort === "p_value" ? "ASC" : "DESC";
    const where   = "WHERE " + conditions.join(" AND ");

    const sql = [
      "SELECT symbol, anchor_mm_dd, window_days, direction,",
      "n_obs, accuracy, mean_ret, median_ret, std_ret,",
      "p10, p25, p75, p90, best_ret, worst_ret,",
      "score, consistency, edge_ratio, t_stat, p_value,",
      "early_accuracy, recent_accuracy, degradation, recent_mean, recent_vs_all",
      "FROM seasonality_patterns_v3",
      where,
      "ORDER BY " + sortCol + " " + sortDir,
      "LIMIT " + limit,
    ].join(" ");

    const rows = qdb(sql, params);
    return NextResponse.json({ count: rows.length, rows });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, count: 0, rows: [] }, { status: 500 });
  }
}
