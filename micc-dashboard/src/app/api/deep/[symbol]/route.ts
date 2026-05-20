import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[deep/sym]', r.stderr?.slice(0,300)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    // NaN sanitization — handles corr_3y: NaN and any other float NaN from SQLite
    const clean = out
      .replace(/:\s*NaN\b/g,    ': null')
      .replace(/:\s*Infinity\b/g,': null')
      .replace(/:\s*-Infinity\b/g,': null')
    return JSON.parse(clean)
  } catch(e) { console.error('[deep/sym]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(
  _req: Request,
  { params }: { params: { symbol: string } }
) {
  const sym = (params.symbol ?? '').toUpperCase().replace(/[^A-Z0-9& ]/g, '')
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  try {
    // Kappa cached report
    const reportPath = path.join(DA, 'agents', 'kappa', `${sym}_report.json`)
    let report: Record<string, unknown> | null = null
    if (fs.existsSync(reportPath)) {
      try { report = JSON.parse(fs.readFileSync(reportPath, 'utf-8')) } catch { report = null }
    }

    const windowStats = qdb(`
      SELECT window_days, n_windows, mean_return, std_return,
             p5, p25, p75, p95, prob_positive, prob_gt10, prob_lt_neg10,
             sharpe_ratio, ann_return_equiv
      FROM window_stats WHERE symbol=? ORDER BY window_days
    `, [sym])

    const seasonality = qdb(`
      SELECT period_value, n_obs, mean_return_pct, median_return_pct
      FROM symbol_seasonality WHERE symbol=? AND period_type='month'
      ORDER BY period_value
    `, [sym])

    // CORRECT columns: benchmark (not symbol_b), corr_1y (not correlation_20d)
    const correlations = qdb(`
      SELECT benchmark                            AS symbol_b,
             IFNULL(corr_1y,  0)                 AS correlation_20d,
             IFNULL(corr_3y,  0)                 AS correlation_60d,
             IFNULL(beta_1y,  0)                 AS beta_20d
      FROM symbol_correlations
      WHERE symbol=? AND benchmark IS NOT NULL
      ORDER BY ABS(IFNULL(corr_1y, 0)) DESC
      LIMIT 15
    `, [sym])

    const regimeStats = qdb(`
      SELECT regime, n_windows, mean_return, std_return, prob_positive, p5, p95
      FROM window_regime_stats WHERE symbol=? AND window_days=20
      ORDER BY regime
    `, [sym])

    const seriesStats = qdb(`
      SELECT cagr_pct, ann_volatility_pct, max_drawdown_pct,
             sharpe_ratio, sortino_ratio, calmar_ratio,
             n_trading_days, mdd_start_date, mdd_trough_date, mdd_recovery_days
      FROM symbol_series_stats WHERE symbol=? LIMIT 1
    `, [sym])

    // CORRECT columns: bb_position (not bb_pct)
    const technicals = qdb(`
      SELECT rsi_14, rsi_21,
             macd_line, IFNULL(macd_signal, 0)    AS macd_signal,
             IFNULL(bb_position, 0)               AS bb_pct,
             IFNULL(bb_width_pct, 0)              AS bb_width_pct,
             atr_14_pct, adx_14,
             pct_above_sma20, pct_above_sma50,
             IFNULL(vol_surge_20d, 1)              AS vol_surge_20d,
             as_of_date
      FROM symbol_technicals WHERE symbol=?
      ORDER BY as_of_date DESC LIMIT 1
    `, [sym])

    const priceRow = qdb(`
      SELECT close, date, volume
      FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1
    `, [sym])

    const insider = qdb(`
      SELECT filing_date, name, category, transaction_type, quantity, price, value
      FROM insider_trading WHERE symbol=? AND transaction_type IN ('BUY','SELL')
      ORDER BY filing_date DESC LIMIT 10
    `, [sym])

    const announcements = qdb(`
      SELECT announcement_date, subject
      FROM corporate_announcements WHERE symbol=?
      ORDER BY announcement_date DESC LIMIT 8
    `, [sym])

    // Series stats for index if not found as stock
    const indexPrice = priceRow.length === 0 ? qdb(`
      SELECT closing_index_value AS close, date
      FROM market_snapshot WHERE index_name=? ORDER BY date DESC LIMIT 1
    `, [sym]) : []

    return NextResponse.json({
      ok: true, symbol: sym,
      report,
      has_cached_report: !!report,
      technicals:     technicals[0]   || null,
      window_stats:   windowStats,
      seasonality,
      correlations,
      regime_stats:   regimeStats,
      series_stats:   seriesStats[0]  || null,
      latest_price:   priceRow[0]     || indexPrice[0] || null,
      insider_trades: insider,
      announcements,
    })
  } catch(e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
