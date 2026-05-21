import { NextResponse } from "next/server";
import Database from "better-sqlite3";

const DB = "D:/marketDB/db/market.db";

function safeDb<T>(fn: (db: ReturnType<typeof Database>) => T, fallback: T): T {
  let db: ReturnType<typeof Database> | null = null;
  try {
    db = new Database(DB, { readonly: true, timeout: 5000 });
    return fn(db);
  } catch {
    return fallback;
  } finally {
    try { db?.close(); } catch {}
  }
}

export function GET() {
  const result: Record<string, unknown> = {};

  // RBI rates
  const rbiHistory = safeDb(db => {
    return db.prepare(
      "SELECT date, repo_rate, reverse_repo, crr FROM rbi_monetary_data ORDER BY date DESC LIMIT 50"
    ).all();
  }, []);
  result.rbi_history = rbiHistory;

  if (Array.isArray(rbiHistory) && rbiHistory.length > 0) {
    const latest = rbiHistory[0] as Record<string, unknown>;
    result.repo_rate     = latest.repo_rate;
    result.reverse_repo  = latest.reverse_repo;
    result.crr           = latest.crr;
  }

  // India macro from india_monthly_macro
  const indiaMacro = safeDb(db => {
    try {
      return db.prepare(
        "SELECT indicator, value, date, source FROM india_monthly_macro ORDER BY date DESC LIMIT 100"
      ).all();
    } catch { return []; }
  }, []);
  result.india_macro = indiaMacro;

  // US macro
  const usMacro = safeDb(db => {
    try {
      return db.prepare(
        "SELECT indicator, value, date FROM us_macro_data ORDER BY date DESC LIMIT 50"
      ).all();
    } catch { return []; }
  }, []);
  result.us_macro = usMacro;

  // Global indices for rates
  const rates = safeDb(db => {
    try {
      return db.prepare(
        "SELECT symbol, close FROM global_indices_daily WHERE symbol IN ('US10Y','US2Y','USDINR') ORDER BY date DESC LIMIT 3"
      ).all() as {symbol:string;close:number}[];
    } catch { return []; }
  }, [] as {symbol:string;close:number}[]);

  for (const r of rates) {
    if (r.symbol === "US10Y")  result.us_10y   = r.close;
    if (r.symbol === "USDINR") result.usd_inr  = r.close;
  }

  return NextResponse.json(result);
}
