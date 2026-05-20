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
  const r = spawnSync(PY,["-c",script,payload],{cwd:DA,encoding:"utf-8",timeout:20000});
  if(r.status!==0){console.error("[analytics]",r.stderr?.slice(0,200));return[];}
  try{return JSON.parse(san(r.stdout.trim()||"[]"));}catch{return[];}
}

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const limit  = parseInt(url.searchParams.get("limit") || "500");
  const filter = url.searchParams.get("filter") || "all";  // all|quality|value|growth

  // Build WHERE clause based on filter
  let where = "WHERE f.pe_ratio IS NOT NULL";
  if (filter === "quality") {
    where += " AND f.roce >= 15 AND f.roe >= 15 AND f.debt_equity <= 1 AND f.promoter_pct >= 50";
  } else if (filter === "value") {
    where += " AND f.pe_ratio <= 20 AND f.pb_ratio <= 3";
  } else if (filter === "growth") {
    where += " AND f.revenue_growth >= 15 AND f.profit_growth >= 15";
  }

  const stocks = qdb(`
    SELECT
      f.symbol,
      ROUND(CAST(f.pe_ratio      AS REAL),1) AS pe,
      ROUND(CAST(f.pb_ratio      AS REAL),1) AS pb,
      ROUND(CAST(f.ps_ratio      AS REAL),1) AS ps,
      ROUND(CAST(f.roe           AS REAL),1) AS roe,
      ROUND(CAST(f.roce          AS REAL),1) AS roce,
      ROUND(CAST(f.roa           AS REAL),1) AS roa,
      ROUND(CAST(f.debt_equity   AS REAL),1) AS de,
      ROUND(CAST(f.promoter_pct  AS REAL),1) AS promoter,
      ROUND(CAST(f.fii_pct       AS REAL),1) AS fii,
      ROUND(CAST(f.dii_pct       AS REAL),1) AS dii,
      ROUND(CAST(f.market_cap_cr AS REAL),0) AS mcap,
      ROUND(CAST(f.revenue_growth AS REAL),1) AS rev_growth,
      ROUND(CAST(f.profit_growth  AS REAL),1) AS prof_growth,
      ROUND(CAST(f.current_ratio  AS REAL),2) AS curr_ratio,
      ROUND(CAST(f.eps           AS REAL),2)  AS eps,
      ROUND(CAST(f.div_yield     AS REAL),2)  AS div_yield,
      ROUND(CAST(f.beta          AS REAL),2)  AS beta,
      f.current_price,
      f.high_52w,
      f.low_52w,
      f.source,
      ROUND(CAST(c.conviction_score AS REAL),1) AS conviction,
      t.rsi_14,
      t.adx_14,
      ROUND(CAST(t.pct_from_52w_high AS REAL),1) AS pct_52h
    FROM screener_fundamentals_v2 f
    LEFT JOIN symbol_conviction c ON c.symbol = f.symbol
    LEFT JOIN symbol_technicals t ON t.symbol = f.symbol
    ${where}
    ORDER BY CAST(f.market_cap_cr AS REAL) DESC NULLS LAST
    LIMIT ?
  `, [limit]);

  // RBI rate history for chart
  const rbi = qdb(
    "SELECT date, repo_rate, reverse_repo, crr FROM rbi_monetary_data " +
    "WHERE repo_rate IS NOT NULL ORDER BY date ASC"
  );

  // Nifty history for overlay (monthly)
  const nifty = qdb(
    "SELECT date, closing_index_value AS close FROM market_snapshot " +
    "WHERE index_name='NIFTY 50' ORDER BY date ASC"
  );

  // Summary stats
  const stats = qdb(`
    SELECT
      COUNT(*) AS total,
      COALESCE(ROUND(AVG(CASE WHEN pe_ratio BETWEEN 1 AND 200 THEN pe_ratio END),1),0) AS avg_pe,
      COALESCE(ROUND(AVG(CASE WHEN roe IS NOT NULL THEN roe END),1),0) AS avg_roe,
      COALESCE(ROUND(AVG(CASE WHEN roce IS NOT NULL THEN roce END),1),0) AS avg_roce,
      COALESCE(ROUND(AVG(CASE WHEN promoter_pct IS NOT NULL THEN promoter_pct END),1),0) AS avg_promoter,
      SUM(CASE WHEN roce >= 15 AND roe >= 15 AND debt_equity <= 1 THEN 1 END) AS quality_count,
      SUM(CASE WHEN pe_ratio <= 20 AND pb_ratio <= 3 THEN 1 END) AS value_count,
      SUM(CASE WHEN revenue_growth >= 15 AND profit_growth >= 15 THEN 1 END) AS growth_count
    FROM screener_fundamentals_v2
    WHERE pe_ratio IS NOT NULL
  `)[0];

  return NextResponse.json({
    stocks,
    rbi,
    nifty: nifty.slice(-252),  // last 1 year
    stats,
    filter,
    generated_at: new Date().toISOString(),
  });
}
