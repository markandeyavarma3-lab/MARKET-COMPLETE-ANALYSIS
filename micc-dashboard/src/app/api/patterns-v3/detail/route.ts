import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qone(sql: string, params: any[]): any | null {
  const sqlB64  = Buffer.from(sql).toString("base64");
  const pyLines = [
    "import sqlite3, json, sys, base64",
    "conn = sqlite3.connect(r'" + DB + "', timeout=15)",
    "conn.row_factory = sqlite3.Row",
    "sql = base64.b64decode(sys.argv[1]).decode()",
    "params = json.loads(sys.argv[2])",
    "row = conn.execute(sql, params).fetchone()",
    "print(json.dumps(dict(row) if row else None, default=str))",
    "conn.close()",
  ];
  const r = spawnSync(PY, ["-c", pyLines.join("\n"), sqlB64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200));
  const txt = r.stdout.trim();
  if (!txt || txt === "null") return null;
  return JSON.parse(sanitize(txt));
}

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "").toUpperCase();
  const anchor = url.searchParams.get("anchor") || "";
  const window_ = parseInt(url.searchParams.get("window") || "0");
  const dir    = (url.searchParams.get("direction") || "").toUpperCase();

  if (!symbol || !anchor || !window_ || !dir)
    return NextResponse.json({ error: "Need symbol, anchor, window, direction" }, { status: 400 });

  try {
    const row = qone(
      "SELECT * FROM seasonality_patterns_v3 WHERE symbol=? AND anchor_mm_dd=? AND window_days=? AND direction=?",
      [symbol, anchor, window_, dir]
    );
    if (!row) return NextResponse.json({ error: "Pattern not found" }, { status: 404 });

    try { row.best_years  = JSON.parse(row.best_years  || "[]"); } catch {}
    try { row.worst_years = JSON.parse(row.worst_years || "[]"); } catch {}
    try { row.all_returns = JSON.parse(row.all_returns || "[]"); } catch {}

    return NextResponse.json(row);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
