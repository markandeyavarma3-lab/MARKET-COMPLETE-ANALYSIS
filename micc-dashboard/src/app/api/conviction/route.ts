import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";
const PY = "py";

function qdb(sql: string, params: (string|number)[] = []): any[] {
  // Build a self-contained Python script that takes SQL+params as b64 JSON
  const payload = Buffer.from(JSON.stringify({ sql, params })).toString("base64");
  const pyScript = `
import sqlite3, json, base64, sys
d = json.loads(base64.b64decode(sys.argv[1]))
conn = sqlite3.connect(r'D:/marketDB/db/market.db', timeout=15)
conn.row_factory = sqlite3.Row
rows = conn.execute(d['sql'], d['params']).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
`.trim();
  const r = spawnSync(PY, ["-c", pyScript, payload], {
    cwd: DA, encoding: "utf-8", timeout: 20000,
  });
  if (r.status !== 0) { console.error("[conv]", r.stderr?.slice(0, 200)); return []; }
  try {
    return JSON.parse(
      r.stdout.trim().replace(/:[ \t]*NaN\b/g, ": null").replace(/:[ \t]*Infinity\b/g, ": null") || "[]"
    );
  } catch { return []; }
}

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url   = new URL(req.url);
  const minS  = parseFloat(url.searchParams.get("min")   || "0");
  const lim   = parseInt  (url.searchParams.get("limit") || "300");

  // ── Main conviction rows ──────────────────────────────────────────────────
  // Real cols: conviction_score, momentum_score, seasonality_score,
  //   quality_score, delivery_score, insider_score, news_score,
  //   fundamental_score, signal_count, top_reason
  const rows = qdb(`
    SELECT
      c.symbol,
      ROUND(CAST(c.conviction_score   AS REAL),1) AS conviction_score,
      ROUND(CAST(c.momentum_score     AS REAL),1) AS momentum_score,
      ROUND(CAST(c.seasonality_score  AS REAL),1) AS seasonality_score,
      ROUND(CAST(c.quality_score      AS REAL),1) AS quality_score,
      ROUND(CAST(c.delivery_score     AS REAL),1) AS delivery_score,
      ROUND(CAST(c.insider_score      AS REAL),1) AS insider_score,
      ROUND(CAST(c.news_score         AS REAL),1) AS news_score,
      ROUND(CAST(c.fundamental_score  AS REAL),1) AS fundamental_score,
      CAST(c.signal_count             AS INTEGER) AS signal_count,
      IFNULL(c.top_reason,'')                     AS top_reason,
      t.rsi_14,
      t.adx_14,
      t.macd_line,
      t.macd_signal,
      ROUND(CAST(t.atr_14_pct        AS REAL),2)  AS atr_14_pct,
      ROUND(CAST(t.pct_from_52w_high AS REAL),1)  AS pct_from_52w_high,
      sd.close                                     AS latest_close
    FROM symbol_conviction c
    LEFT JOIN symbol_technicals t ON t.symbol = c.symbol
    LEFT JOIN (
      SELECT symbol, close
      FROM stock_data
      WHERE date = (SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)
        AND close IS NOT NULL
    ) sd ON sd.symbol = c.symbol
    WHERE CAST(c.conviction_score AS REAL) >= ?
    ORDER BY CAST(c.conviction_score AS REAL) DESC
    LIMIT ?
  `, [minS, lim]);

  // ── Today's seasonal patterns ─────────────────────────────────────────────
  // No is_today col. Compute today's anchor: strftime('%m-%d', 'now', 'localtime')
  // Real cols: symbol, anchor_mm_dd, window_days, direction, mean_ret,
  //   accuracy, score_v2, fdr_reject
  const pats = qdb(`
    SELECT symbol, direction, anchor_mm_dd, window_days,
      ROUND(CAST(mean_ret  AS REAL),2) AS mean_ret,
      ROUND(CAST(accuracy  AS REAL)*100,1) AS win_pct,
      ROUND(CAST(score_v2  AS REAL),2) AS score
    FROM seasonality_patterns_v3
    WHERE anchor_mm_dd = strftime('%m-%d','now','localtime')
      AND fdr_reject = 1
      AND n_obs >= 10
    ORDER BY CAST(score_v2 AS REAL) DESC
    LIMIT 500
  `);
  const patMap: Record<string,any> = {};
  for (const p of pats) { if (!patMap[p.symbol]) patMap[p.symbol] = p; }

  // ── Today's signals ───────────────────────────────────────────────────────
  const sigs = qdb(`
    SELECT symbol, screen_tags FROM signals_history
    WHERE run_date = (SELECT MAX(run_date) FROM signals_history)
  `);
  const sigMap: Record<string,string> = {};
  for (const s of sigs) sigMap[s.symbol] = s.screen_tags || "";

  // ── Regime from NIFTY 50 ──────────────────────────────────────────────────
  const nr = qdb(`
    SELECT closing_index_value AS close FROM market_snapshot
    WHERE index_name = 'NIFTY 50' ORDER BY date DESC LIMIT 1
  `);
  const nifty  = parseFloat(nr[0]?.close ?? "0");
  const regime = nifty > 22000 ? "BULLISH" : nifty > 18000 ? "SIDEWAYS" : nifty > 0 ? "BEARISH" : "UNKNOWN";

  const enriched = rows.map((r: any) => ({
    ...r,
    today_pattern: patMap[r.symbol] ?? null,
    today_signals: sigMap[r.symbol] ?? "",
    macd_bullish:  (r.macd_line ?? 0) > (r.macd_signal ?? 0),
    // build active_tags from non-zero scores
    active_tags: [
      r.momentum_score    > 0 ? "M" : "",
      r.seasonality_score > 0 ? "S" : "",
      r.quality_score     > 0 ? "Q" : "",
      r.delivery_score    > 0 ? "D" : "",
      r.insider_score     > 0 ? "I" : "",
      r.news_score        > 0 ? "N" : "",
      r.fundamental_score > 0 ? "F" : "",
    ].filter(Boolean).join(","),
    n_layers: [
      r.momentum_score, r.seasonality_score, r.quality_score,
      r.delivery_score, r.insider_score, r.news_score, r.fundamental_score,
    ].filter((v: number) => v > 0).length,
  }));

  return NextResponse.json({
    rows: enriched, total: enriched.length, regime, nifty,
    generated_at: new Date().toISOString(),
  });
}
