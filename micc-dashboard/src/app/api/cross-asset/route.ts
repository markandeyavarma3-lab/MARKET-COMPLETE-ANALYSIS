import { NextResponse } from "next/server";
import { spawnSync } from "child_process";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";
const PY = "C:/Users/marka/AppData/Local/Programs/Python/Python314/python.exe";

export async function GET() {
  const script = [
    "import sqlite3, json",
    "conn = sqlite3.connect(r\"D:/marketDB/db/market.db\", timeout=15)",
    "conn.row_factory = sqlite3.Row",
    "rows = conn.execute('SELECT * FROM cross_asset_signals WHERE date=(SELECT MAX(date) FROM cross_asset_signals) ORDER BY signal_name').fetchall()",
    "hist = conn.execute('SELECT signal_name, signal_type, COUNT(*) as n, AVG(nifty_fwd_10d) as avg10, AVG(CASE WHEN nifty_fwd_10d>0 THEN 1.0 ELSE 0.0 END) as hr FROM cross_asset_signals WHERE nifty_fwd_10d IS NOT NULL GROUP BY signal_name, signal_type').fetchall()",
    "conn.close()",
    "print(json.dumps({'signals':[dict(r) for r in rows],'history':[dict(r) for r in hist]},default=str))",
  ].join("\n");
  const r = spawnSync(PY, ["-c", script], { encoding: "utf8", timeout: 15000, cwd: DA });
  try { return NextResponse.json(JSON.parse(r.stdout.trim())); }
  catch (e: any) { return NextResponse.json({ error: e.message, signals: [], history: [] }, { status: 500 }); }
}