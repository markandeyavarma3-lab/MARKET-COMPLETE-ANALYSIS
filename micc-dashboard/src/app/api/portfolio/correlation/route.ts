import { NextResponse } from "next/server";
import Database from "better-sqlite3";

const DB = "D:/marketDB/db/market.db";

export function GET() {
  let db: ReturnType<typeof Database> | null = null;
  try {
    db = new Database(DB, { readonly: true, timeout: 8000 });

    // Get open positions
    const positions = db.prepare(
      "SELECT symbol FROM my_portfolio WHERE status='OPEN'"
    ).all() as { symbol: string }[];
    const syms = positions.map(p => p.symbol);

    if (syms.length < 2) {
      return NextResponse.json({ symbols: syms, matrix: [], message: "Need 2+ open positions" });
    }

    // Fetch 90d of returns for each symbol from parquet via stock_data
    const ph = syms.map(() => "?").join(",");
    const priceRows = db.prepare(
      "SELECT symbol, date, close FROM stock_data"
      " WHERE symbol IN (" + ph + ")"
      "   AND date >= date('now', '-120 days')"
      "   AND close IS NOT NULL"
      " ORDER BY symbol, date"
    ).all(...syms) as { symbol: string; date: string; close: number }[];

    // Build return series per symbol
    const bySymbol: Record<string, number[]> = {};
    const dateIndex: Record<string, Record<string, number>> = {};
    for (const row of priceRows) {
      if (!bySymbol[row.symbol]) bySymbol[row.symbol] = [];
      if (!dateIndex[row.date]) dateIndex[row.date] = {};
      dateIndex[row.date][row.symbol] = row.close;
    }
    const dates = Object.keys(dateIndex).sort();

    // Compute daily returns
    const returns: Record<string, number[]> = {};
    for (const sym of syms) returns[sym] = [];
    for (let i = 1; i < dates.length; i++) {
      const prev = dateIndex[dates[i-1]];
      const curr = dateIndex[dates[i]];
      for (const sym of syms) {
        if (prev[sym] && curr[sym]) {
          returns[sym].push((curr[sym] - prev[sym]) / prev[sym]);
        } else {
          returns[sym].push(NaN);
        }
      }
    }

    // Compute pairwise correlations
    function corr(a: number[], b: number[]): number {
      const pairs = a.map((v, i) => [v, b[i]]).filter(p => !isNaN(p[0]) && !isNaN(p[1]));
      if (pairs.length < 10) return NaN;
      const n  = pairs.length;
      const ma = pairs.reduce((s, p) => s + p[0], 0) / n;
      const mb = pairs.reduce((s, p) => s + p[1], 0) / n;
      const num = pairs.reduce((s, p) => s + (p[0]-ma)*(p[1]-mb), 0);
      const da  = Math.sqrt(pairs.reduce((s, p) => s + (p[0]-ma)**2, 0));
      const db2 = Math.sqrt(pairs.reduce((s, p) => s + (p[1]-mb)**2, 0));
      if (da === 0 || db2 === 0) return NaN;
      return Math.round(num / (da * db2) * 100) / 100;
    }

    const matrix: { symA: string; symB: string; corr: number | null }[] = [];
    for (let i = 0; i < syms.length; i++) {
      for (let j = 0; j < syms.length; j++) {
        const c = i === j ? 1.0 : corr(returns[syms[i]], returns[syms[j]]);
        matrix.push({ symA: syms[i], symB: syms[j], corr: isNaN(c) ? null : c });
      }
    }

    return NextResponse.json({ symbols: syms, matrix, n_days: dates.length - 1 });
  } catch (e) {
    return NextResponse.json({ symbols: [], matrix: [], error: String(e) });
  } finally {
    try { db?.close(); } catch {}
  }
}