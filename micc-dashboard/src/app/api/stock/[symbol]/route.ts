import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DA = "D:/MICC";
const PY = "py";

function san(s: string) {
  return s.replace(/:[ \t]*NaN\b/g,": null").replace(/:[ \t]*-?Infinity\b/g,": null");
}
function qdb(sql: string, params: (string|number)[] = []): any[] {
  const payload = Buffer.from(JSON.stringify({ sql, params })).toString("base64");
  const script = [
    "import sqlite3,json,base64,sys",
    "d=json.loads(base64.b64decode(sys.argv[1]))",
    "conn=sqlite3.connect(r'D:/marketDB/db/market.db',timeout=15)",
    "conn.row_factory=sqlite3.Row",
    "rows=conn.execute(d['sql'],d['params']).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\n");
  const r = spawnSync(PY,["-c",script,payload],{cwd:DA,encoding:"utf-8",timeout:25000});
  if(r.status!==0){console.error("[stock-api]",r.stderr?.slice(0,200));return[];}
  try{return JSON.parse(san(r.stdout.trim()||"[]"));}catch{return[];}
}

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: { symbol: string } }
) {
  const sym = params.symbol.toUpperCase();

  // Price history (2 years)
  const price = qdb(
    "SELECT date, open, high, low, close, volume FROM stock_data " +
    "WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 504",
    [sym]
  );

  // Technicals
  const tech = qdb(
    "SELECT * FROM symbol_technicals WHERE symbol=?", [sym]
  )[0] ?? null;

  // Fundamentals
  const fund = qdb(
    "SELECT * FROM screener_fundamentals_v2 WHERE symbol=?", [sym]
  )[0] ?? null;

  // Conviction
  const conv = qdb(
    "SELECT * FROM symbol_conviction WHERE symbol=?", [sym]
  )[0] ?? null;

  // Seasonality: next 30 days patterns
  const seas = qdb(
    "SELECT anchor_mm_dd, window_days, direction, " +
    "ROUND(CAST(mean_ret AS REAL),2) AS mean_ret, " +
    "ROUND(CAST(accuracy AS REAL)*100,1) AS win_pct, " +
    "ROUND(CAST(score_v2 AS REAL),2) AS score " +
    "FROM seasonality_patterns_v3 " +
    "WHERE symbol=? AND fdr_reject=1 AND n_obs>=10 " +
    "AND score_v2 > 0 " +
    "ORDER BY CAST(score_v2 AS REAL) DESC LIMIT 20",
    [sym]
  );

  // Insider trades (last 6 months)
  const insider = qdb(
    "SELECT filing_date, name, category, transaction_type, quantity, price, value " +
    "FROM insider_trading WHERE symbol=? " +
    "AND transaction_type IN ('BUY','SELL') " +
    "ORDER BY filing_date DESC LIMIT 10",
    [sym]
  );

  // Corporate announcements (last 3 months)
  const announcements = qdb(
    "SELECT announcement_date, subject FROM corporate_announcements " +
    "WHERE symbol=? ORDER BY announcement_date DESC LIMIT 8",
    [sym]
  );

  // Latest RBI repo rate
  const rbi = qdb(
    "SELECT date, repo_rate FROM rbi_monetary_data " +
    "WHERE repo_rate IS NOT NULL ORDER BY date DESC LIMIT 1"
  )[0] ?? null;

  // Delivery data (last 30 days)
  const delivery = qdb(
    "SELECT date, volume, delivery_qty, delivery_pct FROM stock_delivery " +
    "WHERE symbol=? ORDER BY date DESC LIMIT 30",
    [sym]
  );

  // Sector peers (same sector, top 5 by conviction)
  const peers = qdb(
    "SELECT c.symbol, " +
    "ROUND(CAST(c.conviction_score AS REAL),1) AS conviction, " +
    "f.pe_ratio, f.roce, f.roe, f.market_cap_cr " +
    "FROM symbol_conviction c " +
    "LEFT JOIN screener_fundamentals_v2 f ON f.symbol=c.symbol " +
    "WHERE c.symbol != ? " +
    "ORDER BY CAST(c.conviction_score AS REAL) DESC LIMIT 8",
    [sym]
  );

  // Quality score computation
  let qualityScore = 0;
  let qualityMax   = 0;
  if (fund) {
    const checks = [
      [fund.roce,           ">=", 15],
      [fund.roe,            ">=", 15],
      [fund.debt_equity,    "<=", 1],
      [fund.promoter_pct,   ">=", 50],
      [fund.current_ratio,  ">=", 1.5],
      [fund.revenue_growth, ">=", 10],
      [fund.profit_growth,  ">=", 10],
      [fund.interest_coverage, ">=", 3],
    ] as [number|null, string, number][];
    for (const [val, op, thresh] of checks) {
      if (val != null) {
        qualityMax++;
        if (op === ">=" && val >= thresh) qualityScore++;
        if (op === "<=" && val <= thresh) qualityScore++;
      }
    }
  }

  return NextResponse.json({
    symbol: sym,
    price:  price.reverse(),  // chronological
    tech,
    fund,
    conv,
    seas,
    insider,
    announcements,
    rbi,
    delivery: delivery.reverse(),
    peers,
    quality: { score: qualityScore, max: qualityMax,
               grade: qualityMax === 0 ? "N/A" :
                      qualityScore >= qualityMax*0.8 ? "A" :
                      qualityScore >= qualityMax*0.6 ? "B" :
                      qualityScore >= qualityMax*0.4 ? "C" : "D" },
    generated_at: new Date().toISOString(),
  });
}
