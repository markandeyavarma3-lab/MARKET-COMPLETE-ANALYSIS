import { NextRequest, NextResponse } from "next/server";
import { spawnSync } from "child_process";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";

function runBridge(script: string): string {
  const r = spawnSync("py", ["-c", script], {
    encoding: "utf8",
    timeout: 30000,
    cwd: DA,
  });
  if (r.error) throw r.error;
  return r.stdout.trim();
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const limit  = parseInt(searchParams.get("limit")  || "100", 10);
  const minScore = parseFloat(searchParams.get("min") || "0");
  const layer  = searchParams.get("layer") || "";
  const search = (searchParams.get("q") || "").toUpperCase();

  const script = `
import sqlite3, json, math

def s(v):
    if v is None: return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 2)
    except: return None

conn = sqlite3.connect(r"${DB}", timeout=15)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Main conviction data
q = """
  SELECT c.symbol, c.conviction_score, c.momentum_score, c.seasonality_score,
         c.quality_score, c.delivery_score, c.insider_score, c.news_score,
         c.fundamental_score, c.signal_count, c.top_reason, c.computed_date,
         st.close, st.volume,
         sf.roce, sf.roe, sf.debt_equity,
         sq.f_score, sq.data_quarters
  FROM symbol_conviction c
  LEFT JOIN (
      SELECT symbol, close, volume FROM stock_data
      WHERE date = (SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)
        AND close IS NOT NULL
  ) st ON st.symbol = c.symbol
  LEFT JOIN screener_fundamentals sf ON sf.symbol = c.symbol
  LEFT JOIN symbol_quality_scores sq ON sq.symbol = c.symbol
  WHERE c.conviction_score >= ${minScore}
  ${search ? f"AND c.symbol LIKE '%{search}%'" : ""}
  ORDER BY c.conviction_score DESC
  LIMIT ${limit}
"""
rows = cur.execute(q).fetchall()

results = []
for r in rows:
    results.append({
        "symbol":       r["symbol"],
        "score":        s(r["conviction_score"]),
        "momentum":     s(r["momentum_score"]),
        "seasonality":  s(r["seasonality_score"]),
        "quality":      s(r["quality_score"]),
        "delivery":     s(r["delivery_score"]),
        "insider":      s(r["insider_score"]),
        "news":         s(r["news_score"]),
        "fundamental":  s(r["fundamental_score"]),
        "signals":      r["signal_count"],
        "top_reason":   r["top_reason"],
        "close":        s(r["close"]),
        "volume":       r["volume"],
        "roce":         s(r["roce"]),
        "roe":          s(r["roe"]),
        "debt_equity":  s(r["debt_equity"]),
        "f_score":      r["f_score"],
        "as_of":        r["computed_date"],
    })

# Summary stats
stats = cur.execute("""
  SELECT COUNT(*) as total,
         AVG(conviction_score) as avg_score,
         SUM(CASE WHEN conviction_score >= 70 THEN 1 ELSE 0 END) as high,
         SUM(CASE WHEN conviction_score >= 50 AND conviction_score < 70 THEN 1 ELSE 0 END) as med,
         SUM(CASE WHEN conviction_score < 50 THEN 1 ELSE 0 END) as low,
         MAX(computed_date) as as_of
  FROM symbol_conviction
""").fetchone()

# Top reason distribution
reasons = cur.execute("""
  SELECT top_reason, COUNT(*) as cnt
  FROM symbol_conviction
  GROUP BY top_reason
  ORDER BY cnt DESC
""").fetchall()

conn.close()
print(json.dumps({
    "rows": results,
    "stats": {
        "total":     stats["total"],
        "avg_score": s(stats["avg_score"]),
        "high":      stats["high"],
        "med":       stats["med"],
        "low":       stats["low"],
        "as_of":     stats["as_of"],
    },
    "top_reasons": [{"reason": r["top_reason"], "count": r["cnt"]} for r in reasons]
}))
`;

  try {
    const raw = runBridge(script);
    const data = JSON.parse(raw);
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message, rows: [], stats: null }, { status: 500 });
  }
}
