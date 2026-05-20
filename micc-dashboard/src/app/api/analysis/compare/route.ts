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
    if (r.status !== 0) { console.error('[compare]', r.stderr?.slice(0,300)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out.replace(/:\s*NaN/g,': null').replace(/:\s*Infinity/g,': null').replace(/:\s*-Infinity/g,': null'))
  } catch(e) { console.error('[compare]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const symsParam = searchParams.get('symbols') || ''
  const symbols = symsParam.split(',').map(s => s.trim().toUpperCase().replace(/[^A-Z0-9& ]/g,'')).filter(Boolean).slice(0,5)

  if (symbols.length < 2) return NextResponse.json({ ok:false, error:'Need 2-5 symbols' }, { status:400 })

  const ph = symbols.map(()=>'?').join(',')

  // All window stats for all symbols
  const windowStats = qdb(`
    SELECT symbol, window_days, n_windows, mean_return, std_return,
           p5, p25, p75, p95, prob_positive, prob_gt10, prob_lt_neg10,
           sharpe_ratio, ann_return_equiv, min_return, max_return
    FROM window_stats WHERE symbol IN (${ph}) ORDER BY symbol, window_days
  `, symbols)

  // Series stats
  const seriesStats = qdb(`
    SELECT symbol, cagr_pct, ann_volatility_pct, max_drawdown_pct,
           sharpe_ratio, sortino_ratio, calmar_ratio, n_trading_days
    FROM symbol_series_stats WHERE symbol IN (${ph})
  `, symbols)

  // Technicals
  const technicals = qdb(`
    SELECT t.symbol, t.rsi_14, t.adx_14, t.pct_above_sma20,
           t.vol_surge_20d, t.macd_line, t.macd_signal, t.bb_pct, t.atr_14_pct
    FROM symbol_technicals t
    INNER JOIN (SELECT symbol, MAX(as_of_date) md FROM symbol_technicals WHERE symbol IN (${ph}) GROUP BY symbol) lx
      ON t.symbol=lx.symbol AND t.as_of_date=lx.md
  `, [...symbols, ...symbols])

  // Seasonality for heatmap
  const seasonality = qdb(`
    SELECT symbol, period_value, mean_return_pct, n_obs
    FROM symbol_seasonality WHERE symbol IN (${ph}) AND period_type='month'
    ORDER BY symbol, period_value
  `, symbols)

  // Regime stats (20d)
  const regimeStats = qdb(`
    SELECT symbol, regime, mean_return, prob_positive, n_windows
    FROM window_regime_stats WHERE symbol IN (${ph}) AND window_days=20
    ORDER BY symbol, regime
  `, symbols)

  // Cross correlations
  const crossCorr = qdb(`
    SELECT symbol_a, symbol_b, correlation_20d, correlation_60d, beta_20d
    FROM symbol_correlations WHERE symbol_a IN (${ph}) AND symbol_b IN (${ph})
  `, [...symbols, ...symbols])

  // Latest prices
  const prices = qdb(`
    SELECT p.symbol, p.close, p.date
    FROM stock_data p
    INNER JOIN (SELECT symbol, MAX(date) md FROM stock_data WHERE symbol IN (${ph}) GROUP BY symbol) lx
      ON p.symbol=lx.symbol AND p.date=lx.md
  `, [...symbols, ...symbols])

  // Recent signal history
  const signals = qdb(`
    SELECT symbol, COUNT(DISTINCT run_date) days_seen, MAX(run_date) last_seen,
           AVG(CAST(score AS REAL)) avg_score
    FROM signals_history WHERE symbol IN (${ph}) AND run_date >= date('now','-30 days')
    GROUP BY symbol
  `, symbols)

  return NextResponse.json({
    ok: true, symbols,
    window_stats: windowStats,
    series_stats: seriesStats,
    technicals, seasonality,
    regime_stats: regimeStats,
    cross_correlations: crossCorr,
    prices, signals,
  })
}
