# -*- coding: utf-8 -*-
"""
fix_api_columns.py  --  Run from D:\\MICC
Fixes two broken column names in /api/analysis/route.ts:
  - bb_pct        -> bb_position  (actual column in symbol_technicals)
  - symbol_b      -> benchmark    (actual column in symbol_correlations)
  - correlation_20d -> corr_1y    (actual column)
  - correlation_60d -> corr_3y    (actual column)
  - beta_20d      -> beta_1y      (actual column)

Also fixes NSE indices getting 0 patterns in build_seasonality_v2
  - indices_data has only 106 rows for 2026 — NOT enough history
  - Real NSE index history is in market_snapshot (closing_index_value)
  - We need to update get_all_symbols() to use market_snapshot for indices

Run: py D:\\MICC\\fix_api_columns.py
"""

from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
APP  = DASH / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# [1] Fix /api/analysis/route.ts  — correct column names
# =============================================================================
print("\n[1/2] Rewriting /api/analysis/route.ts with correct column names...")

write(APP / "api" / "analysis" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 30000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[analysis]', r.stderr?.slice(0,400)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out
      .replace(/:\s*NaN\b/g,': null')
      .replace(/:\s*Infinity\b/g,': null')
      .replace(/:\s*-Infinity\b/g,': null'))
  } catch(e) { console.error('[analysis]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym = (searchParams.get('symbol') || '').toUpperCase().trim()
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  const chk = qdb(`SELECT asset_type FROM window_stats WHERE symbol=? LIMIT 1`, [sym])
  const detectedType = chk.length > 0
    ? (chk[0] as Record<string,unknown>).asset_type as string
    : 'stock'

  const windowStats = qdb(`
    SELECT window_days, n_windows, first_date, last_date,
           mean_return, median_return, std_return, min_return, max_return,
           p5, p25, p75, p95,
           prob_positive, prob_gt5, prob_gt10, prob_gt20,
           prob_lt_neg5, prob_lt_neg10, prob_lt_neg20,
           ann_return_equiv, sharpe_ratio
    FROM window_stats WHERE symbol=? ORDER BY window_days
  `, [sym])

  if (!windowStats.length) {
    return NextResponse.json({ ok: false, error: `No data for: ${sym}` }, { status: 404 })
  }

  const extremesUp = qdb(`
    SELECT window_days, rank_n, start_date, end_date, return_pct
    FROM window_extremes WHERE symbol=? AND direction='up'
    ORDER BY window_days, rank_n
  `, [sym])

  const extremesDown = qdb(`
    SELECT window_days, rank_n, start_date, end_date, return_pct
    FROM window_extremes WHERE symbol=? AND direction='down'
    ORDER BY window_days, rank_n
  `, [sym])

  const seriesStats = qdb(`
    SELECT cagr_pct, ann_volatility_pct, max_drawdown_pct,
           sharpe_ratio, sortino_ratio, calmar_ratio,
           n_trading_days, mdd_start_date, mdd_trough_date, mdd_recovery_days
    FROM symbol_series_stats WHERE symbol=? LIMIT 1
  `, [sym])

  // FIXED: actual columns are bb_position, bb_width_pct (not bb_pct)
  // Also no macd_signal in table if null — use IFNULL
  const technicals = qdb(`
    SELECT rsi_14, rsi_21,
           macd_line, IFNULL(macd_signal, 0) as macd_signal,
           IFNULL(bb_position, 0) as bb_pct,
           IFNULL(bb_width_pct, 0) as bb_width_pct,
           atr_14_pct, adx_14,
           pct_above_sma20, pct_above_sma50, pct_above_sma200,
           IFNULL(vol_surge_20d, 1) as vol_surge_20d,
           as_of_date
    FROM symbol_technicals
    WHERE symbol=?
    ORDER BY as_of_date DESC LIMIT 1
  `, [sym])

  const seasonality = qdb(`
    SELECT period_value, n_obs, mean_return_pct, median_return_pct
    FROM symbol_seasonality
    WHERE symbol=? AND period_type='month'
    ORDER BY period_value
  `, [sym])

  const regimeStats = qdb(`
    SELECT window_days, regime, n_windows, mean_return, std_return,
           prob_positive, p5, p95
    FROM window_regime_stats WHERE symbol=?
    ORDER BY window_days, regime
  `, [sym])

  // FIXED: actual columns are benchmark (not symbol_b), corr_1y (not correlation_20d),
  //        corr_3y (not correlation_60d), beta_1y (not beta_20d)
  const correlations = qdb(`
    SELECT benchmark as symbol_b,
           IFNULL(corr_1y,  0) as correlation_20d,
           IFNULL(corr_3y,  0) as correlation_60d,
           IFNULL(beta_1y,  0) as beta_20d
    FROM symbol_correlations
    WHERE symbol=? AND benchmark IS NOT NULL
    ORDER BY ABS(IFNULL(corr_1y, 0)) DESC
    LIMIT 15
  `, [sym])

  const priceRow = detectedType === 'stock'
    ? qdb(`SELECT close, date, volume, high, low FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`, [sym])
    : qdb(`SELECT closing_index_value as close, date FROM market_snapshot WHERE index_name=? AND closing_index_value IS NOT NULL ORDER BY date DESC LIMIT 1`, [sym])

  const priceHistRaw = detectedType === 'stock'
    ? qdb(`SELECT date, close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 252`, [sym])
    : qdb(`SELECT date, closing_index_value as close FROM market_snapshot WHERE index_name=? AND closing_index_value IS NOT NULL ORDER BY date DESC LIMIT 252`, [sym])

  const insider = detectedType === 'stock' ? qdb(`
    SELECT filing_date, name, transaction_type, quantity, price, value
    FROM insider_trading WHERE symbol=? AND transaction_type IN ('BUY','SELL')
    ORDER BY filing_date DESC LIMIT 10
  `, [sym]) : []

  const announcements = qdb(`
    SELECT announcement_date, subject
    FROM corporate_announcements WHERE symbol=?
    ORDER BY announcement_date DESC LIMIT 10
  `, [sym])

  const rankRow = qdb(`
    SELECT COUNT(*) as total,
      SUM(CASE WHEN prob_positive < (
        SELECT prob_positive FROM window_stats WHERE symbol=? AND window_days=20
      ) THEN 1 ELSE 0 END) as below_me
    FROM window_stats WHERE window_days=20 AND asset_type=?
  `, [sym, detectedType])

  return NextResponse.json({
    ok: true, symbol: sym, asset_type: detectedType,
    window_stats:   windowStats,
    extremes_up:    extremesUp,
    extremes_down:  extremesDown,
    series_stats:   seriesStats[0]  || null,
    technicals:     technicals[0]   || null,
    seasonality,
    regime_stats:   regimeStats,
    correlations,
    latest_price:   priceRow[0]     || null,
    price_history:  (priceHistRaw as Record<string,unknown>[]).reverse(),
    insider_trades: insider,
    announcements,
    rank:           rankRow[0]      || null,
  })
}
""")


# =============================================================================
# [2] Fix build_seasonality_v2.py — add market_snapshot as NSE index source
# =============================================================================
print("\n[2/2] Fixing NSE indices in build_seasonality_v2.py...")

sv2 = BASE / "build_seasonality_v2.py"
if not sv2.exists():
    print("  [WARN] build_seasonality_v2.py not found at D:\\MICC\\")
    print("  Copy it there first, then run this script again.")
else:
    txt = sv2.read_text(encoding="utf-8")

    OLD = '''    # 2. NSE indices from indices_data (index_name + close)
    idx_rows = conn.execute("""
        SELECT DISTINCT index_name
        FROM indices_data
        WHERE index_name IS NOT NULL AND close IS NOT NULL AND close > 0
        ORDER BY index_name
    """).fetchall()
    for (idx_name,) in idx_rows:
        # Skip if already covered as stock
        if not any(s[0] == idx_name for s in symbols):
            symbols.append((idx_name, 'index', 'indices_data', 'index_name', 'close'))'''

    NEW = '''    # 2. NSE indices from market_snapshot (closing_index_value column)
    #    indices_data only has recent data (2026) — market_snapshot goes back further
    idx_rows = conn.execute("""
        SELECT DISTINCT index_name
        FROM market_snapshot
        WHERE index_name IS NOT NULL AND closing_index_value IS NOT NULL
          AND closing_index_value > 0
        ORDER BY index_name
    """).fetchall()
    for (idx_name,) in idx_rows:
        if not any(s[0] == idx_name for s in symbols):
            symbols.append((idx_name, 'index', 'market_snapshot',
                            'index_name', 'closing_index_value'))'''

    if OLD in txt:
        txt = txt.replace(OLD, NEW)
        sv2.write_text(txt, encoding="utf-8", newline="\n")
        print("  Fixed: market_snapshot now used for NSE indices")
        print("  Run: py D:\\MICC\\build_seasonality_v2.py --yes  (will ask [r]eset or [c]ontinue)")
        print("  Choose [r] to reset and add NSE indices, or [c] to just add the missing ones")
    else:
        print("  Already patched or different code structure")
        print("  Manual fix: in get_all_symbols(), change indices_data source to:")
        print("    market_snapshot, index_name col, closing_index_value price col")


print("""
=============================================================
DONE
=============================================================
Two root-cause fixes:

[1] /api/analysis/route.ts — CORRECTED column names:
    symbol_technicals:
      bb_pct        -> bb_position   (actual column name)
    symbol_correlations:
      symbol_b      -> benchmark     (actual column name)
      correlation_20d -> corr_1y     (actual column)
      correlation_60d -> corr_3y     (actual column)
      beta_20d      -> beta_1y       (actual column)

[2] build_seasonality_v2.py — NSE indices source fixed:
    indices_data only had 106 rows (2026 only)
    -> Now uses market_snapshot (4,809 rows, goes back years)
    -> market_snapshot.closing_index_value is the correct price column

After running this:
  1. Restart dashboard: cd micc-dashboard && npm run dev
  2. Test /analysis?symbol=HDFCBANK
     -> Technicals should show (bb_position, rsi, macd etc)
     -> Correlations should show (benchmark correlations)
  3. Re-run patterns builder for NSE indices:
     py D:\\MICC\\build_seasonality_v2.py --yes
     Choose [c] to continue (adds NSE index patterns)
""")
