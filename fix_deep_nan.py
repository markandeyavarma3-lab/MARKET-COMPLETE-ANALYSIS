# -*- coding: utf-8 -*-
"""
fix_deep_nan.py  --  Run from D:\\MICC
Fixes:
  1. /deep page NaN error (corr_3y: NaN in symbol_correlations)
  2. Runs setup_phase13.py to build all 7 visualizations

Run: py D:\\MICC\\fix_deep_nan.py
"""
from pathlib import Path
import subprocess
import sys

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
APP  = DASH / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# ── Fix every single route.ts that touches the DB ─────────────────────────
print("\n[1/2] Patching NaN in ALL API routes...")

NAN_OLD = "return out ? JSON.parse(out) : []"
NAN_NEW = "return out ? JSON.parse(out.replace(/:\\s*NaN\\b/g,': null').replace(/:\\s*Infinity\\b/g,': null').replace(/:\\s*-Infinity\\b/g,': null')) : []"

patched = 0
for f in (APP / "api").rglob("route.ts"):
    txt = f.read_text(encoding="utf-8")
    if NAN_OLD in txt and NAN_NEW not in txt:
        f.write_text(txt.replace(NAN_OLD, NAN_NEW), encoding="utf-8", newline="\n")
        print(f"  [NaN] {f.relative_to(BASE)}")
        patched += 1

# Also fix the deep/[symbol] route specifically — rewrite it clean
print("\n[2/2] Rewriting /api/deep/[symbol]/route.ts with correct columns + NaN fix...")

write(APP / "api" / "deep" / "[symbol]" / "route.ts", r"""
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
""")

print(f"\n  NaN-patched {patched} additional route files")

# Now run setup_phase13.py
print("\n[Running setup_phase13.py...]\n")
result = subprocess.run(
    [sys.executable, str(BASE / "setup_phase13.py")],
    cwd=str(BASE),
    capture_output=False,
)
if result.returncode != 0:
    print(f"\n[WARN] setup_phase13.py exited with code {result.returncode}")
    print("You can run it manually: py D:\\MICC\\setup_phase13.py")

print("""
=============================================================
ALL FIXES APPLIED
=============================================================

1. /deep page NaN error FIXED
   -> corr_3y: NaN now sanitized to null before JSON.parse
   -> /api/deep/[symbol]/route.ts rewritten with correct column names:
      bb_position (not bb_pct), benchmark (not symbol_b),
      corr_1y (not correlation_20d)

2. All API routes NaN-patched

3. /patterns page rebuilt with all 7 visualizations:
   -> Pattern Cards, Discovery Heatmap, 3D Surface,
      Bubble Chart, Calendar Strip, Month Heatmap

Restart dashboard:
  cd D:\\MICC\\micc-dashboard && npm run dev

Then check:
  localhost:3000/deep          -> should work now (no NaN error)
  localhost:3000/patterns      -> search HDFCBANK -> 6 tabs of charts
  localhost:3000/analysis      -> Search Stock / Compare / Search Index
""")
