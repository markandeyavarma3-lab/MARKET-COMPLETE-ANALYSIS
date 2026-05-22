import { NextResponse } from "next/server";
import Database from "better-sqlite3";

const DB = "D:/marketDB/db/market.db";

function safeDb<T>(fn: (db: ReturnType<typeof Database>) => T, fallback: T): T {
  let db: ReturnType<typeof Database> | null = null;
  try {
    db = new Database(DB, { readonly: true, timeout: 8000 });
    return fn(db);
  } catch { return fallback; }
  finally { try { db?.close(); } catch {} }
}

export function GET() {
  const result: Record<string, unknown> = {};

  // Latest date + nearest expiry
  const dateRow = safeDb(db => db.prepare(
    "SELECT MAX(date) AS d FROM fo_data WHERE symbol='NIFTY'"
  ).get() as { d: string } | undefined, undefined);
  const latestDate = dateRow?.d ?? "";
  result.latest_date = latestDate;

  if (!latestDate) {
    return NextResponse.json({ ...result, error: "No fo_data found" });
  }

  const expiryRow = safeDb(db => db.prepare(
    "SELECT MIN(expiry) AS e FROM fo_data"
    " WHERE symbol='NIFTY' AND date=? AND expiry>=?"
  ).get(latestDate, latestDate) as { e: string } | undefined, undefined);
  const expiry = expiryRow?.e ?? "";
  result.expiry = expiry;

  // Nifty spot from market_snapshot
  const spotRow = safeDb(db => db.prepare(
    "SELECT closing_index_value FROM market_snapshot"
    " WHERE index_name='Nifty 50' ORDER BY date DESC LIMIT 1"
  ).get() as { closing_index_value: number } | undefined, undefined);
  result.nifty_close = spotRow?.closing_index_value;
  result.spot        = spotRow?.closing_index_value;

  // PCR + Max Pain
  const pcrRow = safeDb(db => db.prepare(
    "SELECT"
    "  ROUND(CAST(SUM(CASE WHEN option_typ='PE' THEN open_int ELSE 0 END) AS REAL)"
    "       /NULLIF(SUM(CASE WHEN option_typ='CE' THEN open_int ELSE 0 END),0),2) AS pcr,"
    "  SUM(CASE WHEN option_typ='CE' THEN open_int ELSE 0 END) AS total_call_oi,"
    "  SUM(CASE WHEN option_typ='PE' THEN open_int ELSE 0 END) AS total_put_oi"
    " FROM fo_data"
    " WHERE symbol='NIFTY' AND date=? AND expiry=?"
    " AND instrument IN ('OPTIDX','IDO')"
  ).get(latestDate, expiry) as Record<string,number> | undefined, undefined);
  result.pcr            = pcrRow?.pcr;
  result.total_call_oi  = pcrRow?.total_call_oi;
  result.total_put_oi   = pcrRow?.total_put_oi;

  // Max pain strike
  const strikes = safeDb(db => db.prepare(
    "SELECT strike,"
    "  SUM(CASE WHEN option_typ='CE' THEN open_int ELSE 0 END) AS call_oi,"
    "  SUM(CASE WHEN option_typ='PE' THEN open_int ELSE 0 END) AS put_oi,"
    "  SUM(CASE WHEN option_typ='CE' THEN volume    ELSE 0 END) AS call_vol,"
    "  SUM(CASE WHEN option_typ='PE' THEN volume    ELSE 0 END) AS put_vol"
    " FROM fo_data"
    " WHERE symbol='NIFTY' AND date=? AND expiry=?"
    " AND instrument IN ('OPTIDX','IDO')"
    " GROUP BY strike ORDER BY strike"
  ).all(latestDate, expiry) as { strike: number; call_oi: number; put_oi: number;
    call_vol: number; put_vol: number }[], []);

  // Compute max pain
  let maxPain = 0, minPain = Infinity;
  for (const row of strikes) {
    const s = row.strike;
    let pain = 0;
    for (const r2 of strikes) {
      if (r2.strike > s) pain += r2.call_oi * (r2.strike - s);
      if (r2.strike < s) pain += r2.put_oi  * (s - r2.strike);
    }
    if (pain < minPain) { minPain = pain; maxPain = s; }
  }
  result.max_pain = maxPain || null;
  result.strikes  = strikes;

  // ATM IV from options_iv_history
  const ivRow = safeDb(db => {
    try {
      return db.prepare(
        "SELECT atm_iv, iv_rank FROM options_iv_history"
        " WHERE symbol='NIFTY' ORDER BY date DESC LIMIT 1"
      ).get() as { atm_iv: number; iv_rank: number } | undefined;
    } catch { return undefined; }
  }, undefined);
  result.atm_iv  = ivRow?.atm_iv;
  result.iv_rank = ivRow?.iv_rank;

  // Participant OI
  const partOI = safeDb(db => {
    try {
      return db.prepare(
        "SELECT * FROM participant_oi"
        " WHERE date=(SELECT MAX(date) FROM participant_oi)"
        " ORDER BY category"
      ).all();
    } catch { return []; }
  }, []);
  result.participant_oi = partOI;

  return NextResponse.json(result);
}