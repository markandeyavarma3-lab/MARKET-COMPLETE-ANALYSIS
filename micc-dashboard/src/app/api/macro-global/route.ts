import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import fs               from "fs";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

// Safe DB query: passes SQL and params as argv, avoids template literal backtick issue
function qdb(sqlB64: string, params: any[] = []): any[] {
  const pyScript = [
    "import sqlite3, json, sys, base64",
    "conn = sqlite3.connect(r'" + DB + "', timeout=10)",
    "conn.row_factory = sqlite3.Row",
    "sql = base64.b64decode(sys.argv[1]).decode()",
    "params = json.loads(sys.argv[2])",
    "rows = conn.execute(sql, params).fetchall()",
    "print(json.dumps([dict(r) for r in rows], default=str))",
    "conn.close()",
  ].join("\n");
  const r = spawnSync(PY, ["-c", pyScript, sqlB64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

function b64(s: string): string {
  return Buffer.from(s).toString("base64");
}

export async function GET() {
  try {
    const RATE_SYMS  = ["US10Y", "US2Y", "US30Y"];
    const FX_SYMS    = ["DXY", "USDINR", "EURUSD", "USDJPY", "GBPUSD"];
    const CMDTY_SYMS = ["Gold", "CrudeWTI", "Silver", "NatGas", "Copper"];
    const VIX_SYMS   = ["SP500VIX", "INDIAVIX"];
    const CRYPTO_SYMS = ["Bitcoin", "Ethereum"];
    const EQ_SYMS    = ["SPX", "NDX", "NIFTY50", "Nikkei225", "DAX"];
    const allSyms    = [...RATE_SYMS, ...FX_SYMS, ...CMDTY_SYMS, ...VIX_SYMS, ...CRYPTO_SYMS, ...EQ_SYMS];

    const placeholders = allSyms.map(() => "?").join(",");
    const latestSQL = b64(
      "SELECT g.symbol, g.date, g.close, g.pct_change " +
      "FROM global_indices_daily g " +
      "WHERE g.date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol = g.symbol) " +
      "AND g.symbol IN (" + placeholders + ")"
    );
    const latest = qdb(latestSQL, allSyms);

    // 60-day history for rates (yield curve)
    const histSQL = b64(
      "SELECT symbol, date, close FROM global_indices_daily " +
      "WHERE symbol IN ('US2Y','US10Y','US30Y') AND date >= date('now','-90 days') " +
      "ORDER BY symbol, date"
    );
    const ratesHist = qdb(histSQL, []);

    const bySymbol: Record<string, any> = {};
    for (const r of latest) bySymbol[r.symbol] = r;

    const rates     = RATE_SYMS.map(s  => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const fx        = FX_SYMS.map(s    => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const cmdty     = CMDTY_SYMS.map(s => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const vix       = VIX_SYMS.map(s   => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const crypto    = CRYPTO_SYMS.map(s=> ({ symbol:s, ...(bySymbol[s]||{}) }));
    const equities  = EQ_SYMS.map(s    => ({ symbol:s, ...(bySymbol[s]||{}) }));

    const us10y = bySymbol["US10Y"]?.close ?? null;
    const us2y  = bySymbol["US2Y"]?.close  ?? null;
    const spread = (us10y && us2y) ? Math.round((us10y - us2y) * 100) / 100 : null;

    const ratesHistory: Record<string, any[]> = {};
    for (const r of ratesHist) {
      if (!ratesHistory[r.symbol]) ratesHistory[r.symbol] = [];
      ratesHistory[r.symbol].push({ date: r.date, close: r.close });
    }

    return NextResponse.json({
      rates, fx, commodities: cmdty, volatility: vix, crypto, equities,
      yield_spread: spread,
      rates_history: ratesHistory,
      as_of: latest[0]?.date || null,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
