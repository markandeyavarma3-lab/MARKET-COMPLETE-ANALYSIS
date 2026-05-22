import { NextResponse } from "next/server";
import { readFileSync, existsSync } from "fs";
import Database from "better-sqlite3";

const DB   = "D:/marketDB/db/market.db";
const MICC = "D:/MICC";

function readJson(path: string): Record<string, unknown> {
  try {
    if (!existsSync(path)) return {};
    return JSON.parse(readFileSync(path, "utf-8")
      .replace(/:\s*NaN\b/g, ":null")
      .replace(/:\s*Infinity\b/g, ":null"));
  } catch { return {}; }
}

function safeDb<T>(fn: (db: ReturnType<typeof Database>) => T, fallback: T): T {
  let db: ReturnType<typeof Database> | null = null;
  try {
    db = new Database(DB, { readonly: true, timeout: 5000 });
    return fn(db);
  } catch { return fallback; }
  finally { try { db?.close(); } catch {} }
}

export function GET() {
  // HMM regime
  const hmm = readJson(`${MICC}/agents/hmm/last_report.json`);

  // Fusion top picks
  const fusion = readJson(`${MICC}/agents/fusion/last_report.json`);
  const picks  = (fusion.picks as unknown[] || []).slice(0, 8);

  // Global markets snapshot
  const SYMBOLS = ["NIFTY50","NIFTYBANK","SPX","NDX","VIX","IndiaVIX",
                    "DXY","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"];
  const markets = safeDb(db => {
    const ph   = SYMBOLS.map(() => "?").join(",");
    return db.prepare(
      "SELECT g.symbol, g.close, g.pct_change FROM global_indices_daily g"
      " INNER JOIN (SELECT symbol, MAX(date) AS md FROM global_indices_daily"
      `  WHERE symbol IN (${ph}) GROUP BY symbol) mx`
      " ON mx.symbol=g.symbol AND mx.md=g.date"
      `  WHERE g.symbol IN (${ph})`"
    ).all(...SYMBOLS, ...SYMBOLS);
  }, []);

  // XGB top picks
  const xgbPicks = safeDb(db => {
    try {
      return db.prepare(
        "SELECT x.symbol, x.xgb_score, COALESCE(c.conviction_score,0) AS conviction"
        " FROM symbol_conviction_xgb x"
        " LEFT JOIN symbol_conviction c ON c.symbol=x.symbol"
        " WHERE x.xgb_score >= 55"
        " ORDER BY x.xgb_score DESC LIMIT 8"
      ).all();
    } catch { return []; }
  }, []);

  // Today's OOS-validated patterns
  const mmdd = new Date().toLocaleDateString("en-CA", {
    month: "2-digit", day: "2-digit" }).replace("-", "-");
  const todayDate = new Date();
  const anchor    = `${String(todayDate.getMonth()+1).padStart(2,"0")}-${String(todayDate.getDate()).padStart(2,"0")}`;
  const patterns  = safeDb(db => {
    try {
      return db.prepare(
        "SELECT symbol, window_days, direction, accuracy, mean_ret, score_v2"
        " FROM seasonality_patterns_v3"
        " WHERE anchor_mm_dd=? AND fdr_reject=1 AND (overfit=0 OR overfit IS NULL)"
        "   AND score_v2 > 1.0"
        " ORDER BY score_v2 DESC LIMIT 30"
      ).all(anchor);
    } catch { return []; }
  }, []);
  // Dedup by symbol
  const seen = new Set<string>();
  const patsDeduped = (patterns as {symbol:string}[]).filter(p => {
    if (seen.has(p.symbol)) return false;
    seen.add(p.symbol); return true;
  }).slice(0, 6);

  // Insider clusters
  const insiders = safeDb(db => {
    try {
      const cutoff = new Date(Date.now() - 30*24*3600*1000).toISOString().slice(0,10);
      return db.prepare(
        "SELECT symbol, COUNT(*) AS n_buys, SUM(CAST(value AS REAL)) AS total_value"
        " FROM insider_trading"
        " WHERE transaction_type='BUY' AND filing_date >= ?"
        " GROUP BY symbol HAVING n_buys >= 2"
        " ORDER BY n_buys DESC, total_value DESC LIMIT 5"
      ).all(cutoff);
    } catch { return []; }
  }, []);

  return NextResponse.json({
    hmm,
    fusion_picks:  picks,
    markets,
    xgb_picks:     xgbPicks,
    patterns:      patsDeduped,
    insider_clusters: insiders,
    generated_at:  new Date().toISOString(),
  });
}