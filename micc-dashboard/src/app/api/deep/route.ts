import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'

function sanitize(raw: string): string {
  return raw
    .replace(/:\s*NaN\b/g,      ': null')
    .replace(/:\s*Infinity\b/g,  ': null')
    .replace(/:\s*-Infinity\b/g, ': null')
}

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[deep]', r.stderr?.slice(0,300)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(sanitize(out))
  } catch(e) { console.error('[deep]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    // Load Iota cached report
    const reportPath = path.join(DA, 'agents', 'iota', 'last_report.json')
    let report: Record<string, unknown> | null = null
    if (fs.existsSync(reportPath)) {
      try {
        const raw = fs.readFileSync(reportPath, 'utf-8')
        report = JSON.parse(sanitize(raw))
      } catch(e) {
        console.error('[deep] iota report parse error:', String(e))
        report = null
      }
    }

    // Best probability stocks (20d window)
    const bestProb = qdb(`
      SELECT ws.symbol, ws.asset_type,
             ws.prob_positive, ws.mean_return, ws.p5, ws.p95,
             ws.sharpe_ratio, ws.n_windows,
             ss.cagr_pct, ss.ann_volatility_pct, ss.max_drawdown_pct
      FROM window_stats ws
      LEFT JOIN symbol_series_stats ss ON ws.symbol = ss.symbol
      WHERE ws.window_days = 20
        AND ws.asset_type = 'stock'
        AND ws.n_windows >= 100
      ORDER BY ws.prob_positive DESC
      LIMIT 20
    `)

    // Risk-adjusted gems (high Sharpe)
    const sharpeGems = qdb(`
      SELECT ws.symbol, ws.window_days,
             ws.sharpe_ratio, ws.prob_positive,
             ws.mean_return, ws.std_return,
             ws.p5, ws.p95
      FROM window_stats ws
      WHERE ws.window_days = 20
        AND ws.asset_type = 'stock'
        AND ws.n_windows >= 100
        AND ws.sharpe_ratio IS NOT NULL
      ORDER BY ws.sharpe_ratio DESC
      LIMIT 20
    `)

    // Worst-case protected (p5 floor > -5%)
    const protected_ = qdb(`
      SELECT symbol, window_days, p5, p95,
             prob_positive, mean_return, sharpe_ratio
      FROM window_stats
      WHERE window_days = 20
        AND asset_type = 'stock'
        AND p5 > -5
        AND n_windows >= 100
      ORDER BY p5 DESC
      LIMIT 20
    `)

    // Global macro pulse
    const globalMacro = qdb(`
      SELECT symbol, asset_type,
             prob_positive, mean_return, std_return,
             p5, p95, sharpe_ratio
      FROM window_stats
      WHERE window_days = 20
        AND asset_type IN ('global', 'index')
        AND n_windows >= 20
      ORDER BY prob_positive DESC
      LIMIT 20
    `)

    // Index deep stats — NSE indices
    const indexStats = qdb(`
      SELECT ws.symbol,
             ws.prob_positive, ws.mean_return, ws.std_return,
             ws.p5, ws.p95, ws.sharpe_ratio, ws.n_windows,
             ss.cagr_pct, ss.max_drawdown_pct
      FROM window_stats ws
      LEFT JOIN symbol_series_stats ss ON ws.symbol = ss.symbol
      WHERE ws.window_days = 20
        AND ws.asset_type = 'index'
        AND ws.n_windows >= 20
      ORDER BY ws.prob_positive DESC
      LIMIT 15
    `)

    // Correlations — CORRECT columns: benchmark (not symbol_b)
    // corr_1y (not correlation_20d), IFNULL to avoid NaN
    const correlations = qdb(`
      SELECT symbol,
             benchmark                        AS symbol_b,
             IFNULL(corr_1y,  0)              AS corr_1y,
             IFNULL(corr_3y,  0)              AS corr_3y,
             IFNULL(beta_1y,  0)              AS beta_1y
      FROM symbol_correlations
      WHERE benchmark IS NOT NULL
        AND corr_1y IS NOT NULL
      ORDER BY ABS(IFNULL(corr_1y,0)) DESC
      LIMIT 30
    `)

    // Regime stats for Nifty 50
    const niftyRegime = qdb(`
      SELECT regime, n_windows, mean_return, prob_positive, p5, p95
      FROM window_regime_stats
      WHERE symbol = 'NIFTY 50' AND window_days = 20
      ORDER BY regime
    `)

    return NextResponse.json({
      ok: true,
      has_cached_report: !!report,
      report,
      best_prob:    bestProb,
      sharpe_gems:  sharpeGems,
      protected:    protected_,
      global_macro: globalMacro,
      index_stats:  indexStats,
      correlations,
      nifty_regime: niftyRegime,
      generated_at: new Date().toISOString(),
    })
  } catch(e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
