import { NextResponse } from "next/server";
import Database from "better-sqlite3";

const DB = "D:/marketDB/db/market.db";

export function GET(
  _req: Request,
  { params }: { params: { symbol: string } }
) {
  const sym = params.symbol.toUpperCase();
  let db: ReturnType<typeof Database> | null = null;
  try {
    db = new Database(DB, { readonly: true, timeout: 5000 });
    // Check which news table exists
    const tables = db.prepare(
      "SELECT name FROM sqlite_master WHERE type='table'"
    ).all() as { name: string }[];
    const tnames = new Set(tables.map(t => t.name));

    let rows: unknown[] = [];
    if (tnames.has("news_headlines")) {
      rows = db.prepare(
        "SELECT date, headline, source, sentiment_score, url"
        " FROM news_headlines"
        " WHERE symbols_mentioned LIKE ?"
        " ORDER BY date DESC LIMIT 30"
      ).all("%" + sym + "%");
    } else if (tnames.has("symbol_news_daily")) {
      rows = db.prepare(
        "SELECT date, title AS headline, source, sentiment_score, url"
        " FROM symbol_news_daily"
        " WHERE symbol=?"
        " ORDER BY date DESC LIMIT 30"
      ).all(sym);
    }
    // Also get corporate announcements
    const anns = db.prepare(
      "SELECT announcement_date AS date, subject AS headline,"
      "  'NSE' AS source, NULL AS sentiment_score, NULL AS url"
      " FROM corporate_announcements"
      " WHERE symbol=?"
      " ORDER BY announcement_date DESC LIMIT 20"
    ).all(sym);

    const combined = [...rows, ...anns]
      .sort((a: any, b: any) => (b.date || "").localeCompare(a.date || ""));

    return NextResponse.json({ symbol: sym, news: combined, count: combined.length });
  } catch (e) {
    return NextResponse.json({ symbol: sym, news: [], error: String(e) });
  } finally {
    try { db?.close(); } catch {}
  }
}