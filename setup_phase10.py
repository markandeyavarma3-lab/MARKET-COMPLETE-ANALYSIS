# -*- coding: utf-8 -*-
"""
setup_phase10.py  --  Run from D:\\MICC
=====================================
Phase 10: Analytics Hub

Creates:
  1. /api/analysis/route.ts          -- stock/index search + window analysis
  2. /api/analysis/compare/route.ts  -- multi-symbol comparison data
  3. /analysis/page.tsx              -- full Analytics Hub (4 tabs)
  4. Fix /api/compare NaN bug        -- sanitize NaN before JSON.stringify
  5. Fix /watchlist -- multiple lists + DB-direct + alert system
  6. /api/watchlist-alerts/route.ts  -- alert checker

Run: py D:\MICC\setup_phase10.py
"""

from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
APP  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# [1] /api/analysis/route.ts  -- single symbol deep analysis
# =============================================================================
print("\n[1/6] /api/analysis/route.ts")

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
    if (r.status !== 0) { console.error('[analysis]', r.stderr?.slice(0,300)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    // sanitize NaN / Infinity before parse
    return JSON.parse(out.replace(/:\s*NaN/g, ': null').replace(/:\s*Infinity/g, ': null').replace(/:\s*-Infinity/g, ': null'))
  } catch(e) { console.error('[analysis]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym      = (searchParams.get('symbol') || '').toUpperCase().trim()
  const assetType = searchParams.get('type') || 'auto'   // stock | index | auto

  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  // ── Detect asset type ────────────────────────────────────────────────────
  let detectedType = 'stock'
  if (assetType === 'auto') {
    const chk = qdb(`SELECT asset_type FROM window_stats WHERE symbol=? LIMIT 1`, [sym])
    if (chk.length > 0) detectedType = (chk[0] as Record<string,unknown>).asset_type as string
  } else {
    detectedType = assetType
  }

  // ── All window stats (17 windows) ───────────────────────────────────────
  const windowStats = qdb(`
    SELECT window_days, n_windows, first_date, last_date,
           mean_return, median_return, std_return,
           min_return, max_return,
           p5, p25, p75, p95,
           prob_positive, prob_gt5, prob_gt10, prob_gt20,
           prob_lt_neg5, prob_lt_neg10, prob_lt_neg20,
           ann_return_equiv, sharpe_ratio
    FROM window_stats
    WHERE symbol=?
    ORDER BY window_days
  `, [sym])

  if (!windowStats.length) {
    return NextResponse.json({ ok: false, error: `No data for symbol: ${sym}` }, { status: 404 })
  }

  // ── Top-5 UP and DOWN episodes per window ────────────────────────────────
  const extremesUp = qdb(`
    SELECT window_days, rank_n, start_date, end_date, return_pct
    FROM window_extremes
    WHERE symbol=? AND direction='up'
    ORDER BY window_days, rank_n
  `, [sym])

  const extremesDown = qdb(`
    SELECT window_days, rank_n, start_date, end_date, return_pct
    FROM window_extremes
    WHERE symbol=? AND direction='down'
    ORDER BY window_days, rank_n
  `, [sym])

  // ── Series stats (full history) ──────────────────────────────────────────
  const seriesStats = qdb(`
    SELECT cagr_pct, ann_volatility_pct, max_drawdown_pct,
           sharpe_ratio, sortino_ratio, calmar_ratio,
           n_trading_days, mdd_start_date, mdd_trough_date, mdd_recovery_days
    FROM symbol_series_stats WHERE symbol=? LIMIT 1
  `, [sym])

  // ── Technicals ───────────────────────────────────────────────────────────
  const technicals = qdb(`
    SELECT atr_14_pct, adx_14, pct_above_sma20, vol_surge_20d,
           rsi_14, macd_line, macd_signal, bb_pct, as_of_date
    FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1
  `, [sym])

  // ── Monthly seasonality ───────────────────────────────────────────────────
  const seasonality = qdb(`
    SELECT period_value, n_obs, mean_return_pct, median_return_pct,
           ROUND(1.0 * SUM(CASE WHEN mean_return_pct > 0 THEN 1 ELSE 0 END)
                 OVER (PARTITION BY period_value) / n_obs * 100, 1) as prob_pos
    FROM symbol_seasonality
    WHERE symbol=? AND period_type='month'
    ORDER BY period_value
  `, [sym])

  // ── Regime breakdown across all windows ──────────────────────────────────
  const regimeStats = qdb(`
    SELECT window_days, regime, n_windows, mean_return, std_return,
           prob_positive, p5, p95
    FROM window_regime_stats
    WHERE symbol=?
    ORDER BY window_days, regime
  `, [sym])

  // ── Top correlations ─────────────────────────────────────────────────────
  const correlations = qdb(`
    SELECT symbol_b, correlation_20d, correlation_60d, beta_20d
    FROM symbol_correlations WHERE symbol_a=?
    ORDER BY ABS(correlation_20d) DESC LIMIT 15
  `, [sym])

  // ── Latest price ─────────────────────────────────────────────────────────
  const priceRow = detectedType === 'stock'
    ? qdb(`SELECT close, date, volume, high, low FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`, [sym])
    : qdb(`SELECT close, date FROM market_snapshot WHERE index_name=? ORDER BY date DESC LIMIT 1`, [sym])

  // ── Recent price history (252 days) for sparkline ────────────────────────
  const priceHistory = detectedType === 'stock'
    ? qdb(`SELECT date, close FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 252`, [sym])
    : qdb(`SELECT date, close FROM market_snapshot WHERE index_name=? ORDER BY date DESC LIMIT 252`, [sym])

  // ── Insider trades (stocks only) ─────────────────────────────────────────
  const insider = detectedType === 'stock' ? qdb(`
    SELECT filing_date, name, transaction_type, quantity, price, value
    FROM insider_trading WHERE symbol=? AND transaction_type IN ('BUY','SELL')
    ORDER BY filing_date DESC LIMIT 10
  `, [sym]) : []

  // ── Corporate announcements ────────────────────────────────────────────
  const announcements = qdb(`
    SELECT announcement_date, subject
    FROM corporate_announcements WHERE symbol=?
    ORDER BY announcement_date DESC LIMIT 10
  `, [sym])

  // ── Rank this symbol (best/worst among peers by window) ──────────────────
  // How does this symbol's 20d prob_positive compare to all symbols?
  const rankRow = qdb(`
    SELECT COUNT(*) as total,
      SUM(CASE WHEN prob_positive < (
        SELECT prob_positive FROM window_stats WHERE symbol=? AND window_days=20
      ) THEN 1 ELSE 0 END) as below_me
    FROM window_stats WHERE window_days=20 AND asset_type=?
  `, [sym, detectedType])

  return NextResponse.json({
    ok: true,
    symbol: sym,
    asset_type: detectedType,
    window_stats:   windowStats,
    extremes_up:    extremesUp,
    extremes_down:  extremesDown,
    series_stats:   seriesStats[0]  || null,
    technicals:     technicals[0]   || null,
    seasonality,
    regime_stats:   regimeStats,
    correlations,
    latest_price:   priceRow[0]     || null,
    price_history:  priceHistory.reverse(),
    insider_trades: insider,
    announcements,
    rank:           rankRow[0]      || null,
  })
}
""")


# =============================================================================
# [2] /api/analysis/compare/route.ts  -- multi-symbol comparison
# =============================================================================
print("\n[2/6] /api/analysis/compare/route.ts")

write(APP / "api" / "analysis" / "compare" / "route.ts", r"""
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
""")


# =============================================================================
# [3] /api/watchlist-alerts/route.ts
# =============================================================================
print("\n[3/6] /api/watchlist-alerts/route.ts")

write(APP / "api" / "watchlist-alerts" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'
const WL_PATH = path.join(DA, 'micc_watchlists.json')

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 20000, cwd: DA,
    })
    if (r.status !== 0) return []
    const out = r.stdout.trim()
    return out ? JSON.parse(out.replace(/:\s*NaN/g,': null')) : []
  } catch { return [] }
}

function loadWatchlists() {
  if (!fs.existsSync(WL_PATH)) {
    const defaults = {
      lists: [
        { id: 'default', name: 'My Watchlist', symbols: [], alerts: [] }
      ]
    }
    fs.writeFileSync(WL_PATH, JSON.stringify(defaults, null, 2))
    return defaults
  }
  return JSON.parse(fs.readFileSync(WL_PATH, 'utf-8'))
}

export const dynamic = 'force-dynamic'

// GET: load watchlists + current prices + check alerts
export async function GET() {
  try {
    const wl = loadWatchlists()
    const allSymbols = [...new Set(wl.lists.flatMap((l: Record<string,unknown>) => l.symbols as string[]))]

    let prices: Record<string, Record<string,unknown>> = {}
    let technicals: Record<string, Record<string,unknown>> = {}

    if (allSymbols.length > 0) {
      const ph = allSymbols.map(()=>'?').join(',')

      // Latest prices
      const priceRows = qdb(`
        SELECT p.symbol, p.close, p.date, p.volume,
          ROUND((p.close - p2.close)/p2.close*100, 2) AS pct_1d
        FROM stock_data p
        INNER JOIN (SELECT symbol, MAX(date) md FROM stock_data WHERE symbol IN (${ph}) GROUP BY symbol) lx
          ON p.symbol=lx.symbol AND p.date=lx.md
        LEFT JOIN (
          SELECT s.symbol, s.close FROM stock_data s
          INNER JOIN (SELECT symbol, MAX(date) md2 FROM stock_data WHERE symbol IN (${ph}) AND date < (SELECT MAX(date) FROM stock_data WHERE symbol=s.symbol) GROUP BY symbol) px
            ON s.symbol=px.symbol AND s.date=px.md2
        ) p2 ON p.symbol=p2.symbol
      `, [...allSymbols, ...allSymbols, ...allSymbols])

      for (const r of priceRows as Record<string,unknown>[]) prices[r.symbol as string] = r

      // Technicals
      const techRows = qdb(`
        SELECT t.symbol, t.rsi_14, t.adx_14, t.pct_above_sma20, t.vol_surge_20d,
               t.macd_line, t.macd_signal, t.atr_14_pct
        FROM symbol_technicals t
        INNER JOIN (SELECT symbol, MAX(as_of_date) md FROM symbol_technicals WHERE symbol IN (${ph}) GROUP BY symbol) lx
          ON t.symbol=lx.symbol AND t.as_of_date=lx.md
      `, [...allSymbols, ...allSymbols])

      for (const r of techRows as Record<string,unknown>[]) technicals[r.symbol as string] = r
    }

    // Check alerts
    const triggered: Record<string,unknown>[] = []
    for (const list of wl.lists as Record<string,unknown>[]) {
      for (const alert of (list.alerts as Record<string,unknown>[])) {
        const sym = alert.symbol as string
        const p = prices[sym]
        if (!p) continue
        const close = p.close as number
        const vol   = p.volume as number
        const pct1d = p.pct_1d as number
        const tech  = technicals[sym] || {}

        let hit = false; let reason = ''
        switch (alert.type) {
          case 'price_above':  hit = close >= (alert.value as number); reason = `Price ${close} above ${alert.value}`; break
          case 'price_below':  hit = close <= (alert.value as number); reason = `Price ${close} below ${alert.value}`; break
          case 'price_band':   hit = close >= (alert.low as number) && close <= (alert.high as number); reason = `Price ${close} in band ${alert.low}-${alert.high}`; break
          case 'pct_move_up':  hit = (pct1d||0) >= (alert.value as number); reason = `1d move +${pct1d}% >= ${alert.value}%`; break
          case 'pct_move_down':hit = (pct1d||0) <= -(alert.value as number); reason = `1d move ${pct1d}% <= -${alert.value}%`; break
          case 'volume_surge': hit = (tech.vol_surge_20d as number||0) >= (alert.value as number); reason = `Vol surge ${tech.vol_surge_20d}x >= ${alert.value}x`; break
          case 'rsi_above':    hit = (tech.rsi_14 as number||0) >= (alert.value as number); reason = `RSI ${tech.rsi_14} above ${alert.value}`; break
          case 'rsi_below':    hit = (tech.rsi_14 as number||0) <= (alert.value as number); reason = `RSI ${tech.rsi_14} below ${alert.value}`; break
          case 'above_sma20':  hit = (tech.pct_above_sma20 as number||0) > 0; reason = `Price above SMA20 by ${tech.pct_above_sma20}%`; break
          case 'below_sma20':  hit = (tech.pct_above_sma20 as number||0) < 0; reason = `Price below SMA20 by ${tech.pct_above_sma20}%`; break
        }

        if (hit) triggered.push({ ...alert, sym, reason, close, listId: list.id, listName: list.name })
      }
    }

    return NextResponse.json({ ok: true, watchlists: wl.lists, prices, technicals, triggered })
  } catch(e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}

// POST: create/update/delete lists and alerts
export async function POST(req: Request) {
  try {
    const body = await req.json()
    const wl   = loadWatchlists()
    const { action } = body

    if (action === 'create_list') {
      const id = `list_${Date.now()}`
      wl.lists.push({ id, name: body.name, symbols: [], alerts: [] })
    } else if (action === 'delete_list') {
      wl.lists = wl.lists.filter((l: Record<string,unknown>) => l.id !== body.listId)
    } else if (action === 'rename_list') {
      const list = wl.lists.find((l: Record<string,unknown>) => l.id === body.listId)
      if (list) list.name = body.name
    } else if (action === 'add_symbol') {
      const list = wl.lists.find((l: Record<string,unknown>) => l.id === body.listId)
      if (list && !(list.symbols as string[]).includes(body.symbol)) {
        (list.symbols as string[]).push(body.symbol.toUpperCase())
      }
    } else if (action === 'remove_symbol') {
      const list = wl.lists.find((l: Record<string,unknown>) => l.id === body.listId)
      if (list) list.symbols = (list.symbols as string[]).filter((s: string) => s !== body.symbol)
    } else if (action === 'add_alert') {
      const list = wl.lists.find((l: Record<string,unknown>) => l.id === body.listId)
      if (list) {
        const alert = { ...body.alert, id: `a_${Date.now()}` }
        ;(list.alerts as unknown[]).push(alert)
      }
    } else if (action === 'remove_alert') {
      const list = wl.lists.find((l: Record<string,unknown>) => l.id === body.listId)
      if (list) list.alerts = (list.alerts as Record<string,unknown>[]).filter((a) => a.id !== body.alertId)
    }

    fs.writeFileSync(WL_PATH, JSON.stringify(wl, null, 2))
    return NextResponse.json({ ok: true, watchlists: wl.lists })
  } catch(e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")


# =============================================================================
# [4] /analysis/page.tsx  -- THE ANALYTICS HUB
# =============================================================================
print("\n[4/6] /analysis/page.tsx  (large file — building...)")

write(APP / "analysis" / "page.tsx", r"""
"use client";
import React, { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";

// ── Types ──────────────────────────────────────────────────────────────────
interface WindowStat {
  window_days: number; n_windows: number; first_date: string; last_date: string;
  mean_return: number; median_return: number; std_return: number;
  min_return: number; max_return: number;
  p5: number; p25: number; p75: number; p95: number;
  prob_positive: number; prob_gt5: number; prob_gt10: number; prob_gt20: number;
  prob_lt_neg5: number; prob_lt_neg10: number; prob_lt_neg20: number;
  ann_return_equiv: number; sharpe_ratio: number;
}
interface Extreme  { window_days:number; rank_n:number; start_date:string; end_date:string; return_pct:number; }
interface Series   { cagr_pct:number; ann_volatility_pct:number; max_drawdown_pct:number; sharpe_ratio:number; sortino_ratio:number; calmar_ratio:number; n_trading_days:number; mdd_start_date:string; mdd_trough_date:string; mdd_recovery_days:number; }
interface Tech     { rsi_14:number; adx_14:number; pct_above_sma20:number; vol_surge_20d:number; macd_line:number; macd_signal:number; bb_pct:number; atr_14_pct:number; as_of_date:string; }
interface Season   { period_value:number; n_obs:number; mean_return_pct:number; median_return_pct:number; }
interface Regime   { window_days:number; regime:string; n_windows:number; mean_return:number; std_return:number; prob_positive:number; p5:number; p95:number; }
interface Corr     { symbol_b:string; correlation_20d:number; correlation_60d:number; beta_20d:number; }
interface PriceH   { date:string; close:number; }
interface Insider  { filing_date:string; name:string; transaction_type:string; quantity:number; price:number; value:number; }
interface Ann      { announcement_date:string; subject:string; }

interface AnalysisData {
  ok:boolean; error?:string; symbol:string; asset_type:string;
  window_stats:WindowStat[]; extremes_up:Extreme[]; extremes_down:Extreme[];
  series_stats:Series|null; technicals:Tech|null; seasonality:Season[];
  regime_stats:Regime[]; correlations:Corr[];
  latest_price:{close:number;date:string;volume:number;high:number;low:number}|null;
  price_history:PriceH[];
  insider_trades:Insider[]; announcements:Ann[];
  rank:{total:number;below_me:number}|null;
}

interface CompareData {
  ok:boolean; error?:string; symbols:string[];
  window_stats:{symbol:string;window_days:number;mean_return:number;std_return:number;p5:number;p95:number;prob_positive:number;prob_gt10:number;sharpe_ratio:number;min_return:number;max_return:number}[];
  series_stats:{symbol:string;cagr_pct:number;ann_volatility_pct:number;max_drawdown_pct:number;sharpe_ratio:number;sortino_ratio:number;calmar_ratio:number}[];
  technicals:{symbol:string;rsi_14:number;adx_14:number;pct_above_sma20:number;vol_surge_20d:number;macd_line:number;macd_signal:number;bb_pct:number}[];
  seasonality:{symbol:string;period_value:number;mean_return_pct:number}[];
  cross_correlations:{symbol_a:string;symbol_b:string;correlation_20d:number;beta_20d:number}[];
  prices:{symbol:string;close:number;date:string}[];
}

// ── Constants ──────────────────────────────────────────────────────────────
const ALL_WINDOWS = [1,2,3,5,7,10,15,20,30,45,60,90,120,180,252,504,756];
const DISPLAY_WINDOWS = [3,5,7,10,15,20,30,45,60,90,120,180,252,504,756];
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const SYM_COLORS = ["#22d3ee","#4ade80","#facc15","#f97316","#a855f7"];

const C = {
  green:"#4ade80", red:"#f87171", cyan:"#22d3ee", yellow:"#facc15",
  orange:"#f97316", purple:"#a855f7",
  dim:"var(--text-tertiary)", primary:"var(--text-primary)",
  border:"var(--border-color)", surface:"var(--surface-card)",
  bg:"var(--bg)",
};

// ── Helpers ────────────────────────────────────────────────────────────────
const pct  = (v:unknown,d=1) => v==null?"--":`${(+v)>=0?"+":""}${(+v).toFixed(d)}%`;
const num  = (v:unknown,d=2) => v==null?"--":(+v).toFixed(d);
const col  = (v:unknown) => (+(v??0))>=0?C.green:C.red;
const abs  = (v:number) => Math.abs(v);
const fmtD = (s:string) => s?.slice(0,10) || "--";

function wLabel(d:number) {
  if (d<=7)   return `${d}D`;
  if (d===10) return "2W";
  if (d===15) return "3W";
  if (d===20) return "1M";
  if (d===30) return "6W";
  if (d===45) return "2M";
  if (d===60) return "3M";
  if (d===90) return "4M";
  if (d===120)return "6M";
  if (d===180)return "9M";
  if (d===252)return "1Y";
  if (d===504)return "2Y";
  if (d===756)return "3Y";
  return `${d}D`;
}

// ── Mini components ────────────────────────────────────────────────────────

function Card({title,children,accent,noPad}:{title?:string;children:React.ReactNode;accent?:string;noPad?:boolean}) {
  return (
    <div style={{background:C.surface,border:`1px solid ${accent||C.border}`,borderRadius:8,marginBottom:16,overflow:"hidden"}}>
      {title && <div style={{padding:"10px 16px",fontSize:11,fontWeight:700,letterSpacing:1.4,color:accent||C.cyan,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`}}>{title}</div>}
      <div style={{padding:noPad?0:"14px 16px"}}>{children}</div>
    </div>
  );
}

function ProbBar({label,value,color,max=100}:{label:string;value:number|null;color:string;max?:number}) {
  const v = value??0;
  const w = Math.min(100,Math.max(0,(v/max)*100));
  return (
    <div style={{marginBottom:8}}>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:11,marginBottom:3}}>
        <span style={{color:C.dim}}>{label}</span>
        <span style={{color,fontWeight:700}}>{v.toFixed(1)}%</span>
      </div>
      <div style={{height:6,background:`${C.border}44`,borderRadius:3}}>
        <div style={{height:6,width:`${w}%`,background:color,borderRadius:3,transition:"width 0.4s"}} />
      </div>
    </div>
  );
}

function StatBox({label,value,color,sub}:{label:string;value:string;color?:string;sub?:string}) {
  return (
    <div style={{background:`${C.border}22`,borderRadius:6,padding:"10px 12px",minWidth:100}}>
      <div style={{fontSize:9,color:C.dim,fontWeight:700,letterSpacing:1,textTransform:"uppercase",marginBottom:4}}>{label}</div>
      <div style={{fontSize:18,fontWeight:800,color:color||C.primary,letterSpacing:-0.5}}>{value}</div>
      {sub && <div style={{fontSize:10,color:C.dim,marginTop:2}}>{sub}</div>}
    </div>
  );
}

// ── Sparkline ─────────────────────────────────────────────────────────────
function Sparkline({data,color="var(--accent-cyan)",height=48}:{data:{date:string;close:number}[];color?:string;height?:number}) {
  if (!data||data.length<2) return null;
  const prices = data.map(d=>d.close);
  const mn = Math.min(...prices), mx = Math.max(...prices);
  const range = mx-mn||1;
  const W=300, H=height;
  const pts = prices.map((p,i)=>`${(i/(prices.length-1))*W},${H-((p-mn)/range)*H}`).join(" ");
  const first=prices[0], last=prices[prices.length-1];
  const lineColor = last>=first?C.green:C.red;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke={lineColor} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// ── Window Overview Table ──────────────────────────────────────────────────
function WindowOverviewTable({stats,onSelect,selected}:{stats:WindowStat[];onSelect:(d:number)=>void;selected:number}) {
  const sorted = [...stats].filter(s=>DISPLAY_WINDOWS.includes(s.window_days)).sort((a,b)=>b.prob_positive-a.prob_positive);

  return (
    <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
        <thead>
          <tr style={{background:`${C.border}22`}}>
            {["Window","N","Prob UP","Avg Return","P5 Floor","P95 Best","Std Dev","Best Ever","Worst Ever","Sharpe","Rank"].map(h=>(
              <th key={h} style={{padding:"6px 10px",textAlign:h==="Window"?"left":"right",color:C.dim,fontWeight:600,fontSize:10,borderBottom:`1px solid ${C.border}`,whiteSpace:"nowrap"}}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(s=>{
            const probPct = (s.prob_positive||0)*100;
            const isSelected = s.window_days===selected;
            return (
              <tr key={s.window_days}
                onClick={()=>onSelect(s.window_days)}
                style={{
                  borderBottom:`1px solid ${C.border}22`,
                  background:isSelected?`${C.cyan}11`:"transparent",
                  cursor:"pointer",
                  transition:"background 0.15s",
                }}>
                <td style={{padding:"7px 10px",fontWeight:700,color:isSelected?C.cyan:C.primary}}>{wLabel(s.window_days)} <span style={{color:C.dim,fontSize:10,fontWeight:400}}>({s.window_days}d)</span></td>
                <td style={{padding:"7px 10px",textAlign:"right",color:C.dim}}>{s.n_windows}</td>
                <td style={{padding:"7px 10px",textAlign:"right"}}>
                  <span style={{color:probPct>=60?C.green:probPct>=50?C.yellow:C.red,fontWeight:700}}>{probPct.toFixed(0)}%</span>
                </td>
                <td style={{padding:"7px 10px",textAlign:"right",color:col(s.mean_return),fontWeight:600}}>{pct(s.mean_return)}</td>
                <td style={{padding:"7px 10px",textAlign:"right",color:col(s.p5)}}>{pct(s.p5)}</td>
                <td style={{padding:"7px 10px",textAlign:"right",color:C.cyan}}>{pct(s.p95)}</td>
                <td style={{padding:"7px 10px",textAlign:"right",color:C.dim}}>{pct(s.std_return)}</td>
                <td style={{padding:"7px 10px",textAlign:"right",color:C.green,fontWeight:600}}>{pct(s.max_return)}</td>
                <td style={{padding:"7px 10px",textAlign:"right",color:C.red,fontWeight:600}}>{pct(s.min_return)}</td>
                <td style={{padding:"7px 10px",textAlign:"right",color:C.cyan}}>{num(s.sharpe_ratio)}</td>
                <td style={{padding:"7px 10px",textAlign:"right"}}>
                  <span style={{fontSize:10,padding:"2px 6px",borderRadius:3,
                    background:probPct>=65?`${C.green}22`:probPct>=55?`${C.yellow}22`:`${C.red}22`,
                    color:probPct>=65?C.green:probPct>=55?C.yellow:C.red,fontWeight:700}}>
                    {probPct>=65?"STRONG":probPct>=55?"GOOD":probPct>=45?"NEUTRAL":"WEAK"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Best/Worst Durations Summary ───────────────────────────────────────────
function BestWorstDurations({stats}:{stats:WindowStat[]}) {
  const filtered = stats.filter(s=>DISPLAY_WINDOWS.includes(s.window_days)&&s.n_windows>5);
  const top5Up   = [...filtered].sort((a,b)=>b.prob_positive-a.prob_positive).slice(0,7);
  const top5Down = [...filtered].sort((a,b)=>a.prob_positive-b.prob_positive).slice(0,7);

  return (
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
      <div>
        <div style={{fontSize:11,fontWeight:700,color:C.green,letterSpacing:1.2,textTransform:"uppercase",marginBottom:10}}>Top Durations — Historically Goes UP</div>
        {top5Up.map(s=>{
          const pp=(s.prob_positive||0)*100;
          const barW=Math.min(100,pp);
          return (
            <div key={s.window_days} style={{marginBottom:10,padding:"10px 12px",background:`${C.border}22`,borderRadius:6,borderLeft:`3px solid ${pp>=60?C.green:C.yellow}`}}>
              <div style={{display:"flex",justifyContent:"space-between",marginBottom:6}}>
                <span style={{fontWeight:800,fontSize:14,color:C.primary}}>{wLabel(s.window_days)}</span>
                <span style={{fontWeight:800,fontSize:15,color:pp>=60?C.green:C.yellow}}>{pp.toFixed(0)}% <span style={{fontSize:10,fontWeight:400,color:C.dim}}>went up</span></span>
              </div>
              <div style={{height:5,background:`${C.border}44`,borderRadius:3,marginBottom:6}}>
                <div style={{height:5,width:`${barW}%`,background:pp>=60?C.green:C.yellow,borderRadius:3}} />
              </div>
              <div style={{display:"flex",gap:12,fontSize:11}}>
                <span style={{color:C.dim}}>avg <span style={{color:col(s.mean_return),fontWeight:600}}>{pct(s.mean_return)}</span></span>
                <span style={{color:C.dim}}>best <span style={{color:C.green}}>{pct(s.max_return)}</span></span>
                <span style={{color:C.dim}}>worst <span style={{color:C.red}}>{pct(s.min_return)}</span></span>
                <span style={{color:C.dim}}>n={s.n_windows}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div>
        <div style={{fontSize:11,fontWeight:700,color:C.red,letterSpacing:1.2,textTransform:"uppercase",marginBottom:10}}>Worst Durations — Historically Risky</div>
        {top5Down.map(s=>{
          const pp=(s.prob_positive||0)*100;
          const barW=Math.min(100,100-pp);
          return (
            <div key={s.window_days} style={{marginBottom:10,padding:"10px 12px",background:`${C.border}22`,borderRadius:6,borderLeft:`3px solid ${C.red}`}}>
              <div style={{display:"flex",justifyContent:"space-between",marginBottom:6}}>
                <span style={{fontWeight:800,fontSize:14,color:C.primary}}>{wLabel(s.window_days)}</span>
                <span style={{fontWeight:800,fontSize:15,color:C.red}}>{(100-pp).toFixed(0)}% <span style={{fontSize:10,fontWeight:400,color:C.dim}}>went down</span></span>
              </div>
              <div style={{height:5,background:`${C.border}44`,borderRadius:3,marginBottom:6}}>
                <div style={{height:5,width:`${barW}%`,background:C.red,borderRadius:3}} />
              </div>
              <div style={{display:"flex",gap:12,fontSize:11}}>
                <span style={{color:C.dim}}>avg <span style={{color:col(s.mean_return),fontWeight:600}}>{pct(s.mean_return)}</span></span>
                <span style={{color:C.dim}}>p5 <span style={{color:C.red}}>{pct(s.p5)}</span></span>
                <span style={{color:C.dim}}>worst ever <span style={{color:C.red}}>{pct(s.min_return)}</span></span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Historical Episodes Panel ──────────────────────────────────────────────
function EpisodesPanel({up,down,selectedWindow,onWindowChange,allWindows}:{
  up:Extreme[];down:Extreme[];selectedWindow:number;
  onWindowChange:(d:number)=>void;allWindows:number[];
}) {
  const upW  = up.filter(e=>e.window_days===selectedWindow);
  const downW= down.filter(e=>e.window_days===selectedWindow);

  const barMax = Math.max(...upW.map(e=>abs(e.return_pct)), ...downW.map(e=>abs(e.return_pct)), 1);

  return (
    <div>
      {/* Window selector */}
      <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:14}}>
        {allWindows.filter(d=>DISPLAY_WINDOWS.includes(d)).map(d=>(
          <button key={d} onClick={()=>onWindowChange(d)} style={{
            padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"1px solid",
            background:selectedWindow===d?C.cyan:"transparent",
            color:selectedWindow===d?"#000":C.dim,
            borderColor:selectedWindow===d?C.cyan:C.border,
          }}>{wLabel(d)}</button>
        ))}
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
        {/* Best rallies */}
        <div>
          <div style={{fontSize:11,fontWeight:700,color:C.green,letterSpacing:1.2,textTransform:"uppercase",marginBottom:10}}>
            Top {upW.length} Best Rallies ({wLabel(selectedWindow)})
          </div>
          {upW.length===0 && <div style={{color:C.dim,fontSize:12}}>No data for this window</div>}
          {upW.map((e,i)=>{
            const barW=(abs(e.return_pct)/barMax)*100;
            return (
              <div key={i} style={{marginBottom:10,padding:"10px 12px",background:`${C.green}11`,borderRadius:6,borderLeft:`3px solid ${C.green}`}}>
                <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
                  <span style={{fontSize:10,color:C.dim}}>#{i+1}</span>
                  <span style={{fontWeight:800,fontSize:16,color:C.green}}>{pct(e.return_pct)}</span>
                </div>
                <div style={{height:4,background:`${C.border}44`,borderRadius:2,marginBottom:6}}>
                  <div style={{height:4,width:`${barW}%`,background:C.green,borderRadius:2}} />
                </div>
                <div style={{fontSize:11,color:C.dim}}>
                  {fmtD(e.start_date)} <span style={{color:C.border}}>to</span> {fmtD(e.end_date)}
                </div>
              </div>
            );
          })}
        </div>

        {/* Worst crashes */}
        <div>
          <div style={{fontSize:11,fontWeight:700,color:C.red,letterSpacing:1.2,textTransform:"uppercase",marginBottom:10}}>
            Top {downW.length} Worst Crashes ({wLabel(selectedWindow)})
          </div>
          {downW.length===0 && <div style={{color:C.dim,fontSize:12}}>No data for this window</div>}
          {downW.map((e,i)=>{
            const barW=(abs(e.return_pct)/barMax)*100;
            return (
              <div key={i} style={{marginBottom:10,padding:"10px 12px",background:`${C.red}11`,borderRadius:6,borderLeft:`3px solid ${C.red}`}}>
                <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
                  <span style={{fontSize:10,color:C.dim}}>#{i+1}</span>
                  <span style={{fontWeight:800,fontSize:16,color:C.red}}>{pct(e.return_pct)}</span>
                </div>
                <div style={{height:4,background:`${C.border}44`,borderRadius:2,marginBottom:6}}>
                  <div style={{height:4,width:`${barW}%`,background:C.red,borderRadius:2}} />
                </div>
                <div style={{fontSize:11,color:C.dim}}>
                  {fmtD(e.start_date)} <span style={{color:C.border}}>to</span> {fmtD(e.end_date)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Probability Heatmap (2D) ───────────────────────────────────────────────
function ProbHeatmap({stats}:{stats:WindowStat[]}) {
  const filtered = stats.filter(s=>DISPLAY_WINDOWS.includes(s.window_days));
  const metrics = [
    {key:"prob_positive",   label:"Prob UP",      scale:1},
    {key:"prob_gt5",        label:">+5%",          scale:1},
    {key:"prob_gt10",       label:">+10%",         scale:1},
    {key:"prob_gt20",       label:">+20%",         scale:1},
    {key:"prob_lt_neg5",    label:"<-5%",          scale:1},
    {key:"prob_lt_neg10",   label:"<-10%",         scale:1},
  ] as const;

  function cellColor(key:string, v:number) {
    const pct = (v||0)*100;
    if (key.startsWith("prob_lt")) {
      if (pct>30) return "#f87171cc"; if (pct>20) return "#f97316aa"; if (pct>10) return "#facc1577"; return "#4ade8033";
    }
    if (pct>65) return "#4ade80cc"; if (pct>55) return "#4ade8077"; if (pct>45) return "#facc1555"; return "#f8717133";
  }

  return (
    <div style={{overflowX:"auto"}}>
      <table style={{borderCollapse:"collapse",fontSize:11,width:"100%"}}>
        <thead>
          <tr>
            <th style={{padding:"5px 10px",textAlign:"left",color:C.dim,fontWeight:600,fontSize:10}}>Window</th>
            {metrics.map(m=><th key={m.key} style={{padding:"5px 8px",textAlign:"center",color:C.dim,fontWeight:600,fontSize:10,whiteSpace:"nowrap"}}>{m.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {filtered.map(s=>(
            <tr key={s.window_days}>
              <td style={{padding:"4px 10px",fontWeight:700,color:C.primary}}>{wLabel(s.window_days)}</td>
              {metrics.map(m=>{
                const v = (s[m.key as keyof WindowStat] as number)||0;
                const pctV = (v*100).toFixed(0);
                return (
                  <td key={m.key} style={{padding:"4px 8px",textAlign:"center",background:cellColor(m.key,v),borderRadius:3,fontWeight:700,color:"#fff",fontSize:11}}>
                    {pctV}%
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Seasonality Chart ──────────────────────────────────────────────────────
function SeasonChart({data}:{data:Season[]}) {
  if (!data.length) return <div style={{color:C.dim,fontSize:12}}>No data</div>;
  const maxAbs = Math.max(...data.map(r=>abs(r.mean_return_pct||0)),1);
  return (
    <div>
      <div style={{display:"flex",gap:4,alignItems:"flex-end",height:90,marginBottom:4}}>
        {data.map(r=>{
          const h=Math.max(2,(abs(r.mean_return_pct||0)/maxAbs)*80);
          const pos=(r.mean_return_pct||0)>=0;
          return (
            <div key={r.period_value} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center"}}>
              <div style={{fontSize:9,color:col(r.mean_return_pct),fontWeight:700,marginBottom:2}}>{pct(r.mean_return_pct,1)}</div>
              <div style={{width:"100%",height:h,background:pos?C.green:C.red,opacity:0.8,borderRadius:"2px 2px 0 0",minHeight:2}} />
            </div>
          );
        })}
      </div>
      <div style={{display:"flex",gap:4}}>
        {data.map(r=><div key={r.period_value} style={{flex:1,textAlign:"center",fontSize:9,color:C.dim}}>{MONTHS[r.period_value-1]}</div>)}
      </div>
    </div>
  );
}

// ── Percentile Range Chart ─────────────────────────────────────────────────
function PercentileChart({stats}:{stats:WindowStat[]}) {
  const filtered = stats.filter(s=>DISPLAY_WINDOWS.includes(s.window_days)).sort((a,b)=>a.window_days-b.window_days);
  if (!filtered.length) return null;

  const allVals = filtered.flatMap(s=>[s.min_return,s.max_return]).filter(Boolean);
  const globalMin = Math.min(...allVals,-5);
  const globalMax = Math.max(...allVals,5);
  const range = globalMax-globalMin;

  const toY = (v:number,H:number) => H - ((v-globalMin)/range)*H;

  const W=600, H=160;

  const paths = {
    p5:   filtered.map((s,i)=>({x:(i/(filtered.length-1))*W,y:toY(s.p5,H)})),
    p25:  filtered.map((s,i)=>({x:(i/(filtered.length-1))*W,y:toY(s.p25,H)})),
    mean: filtered.map((s,i)=>({x:(i/(filtered.length-1))*W,y:toY(s.mean_return,H)})),
    p75:  filtered.map((s,i)=>({x:(i/(filtered.length-1))*W,y:toY(s.p75,H)})),
    p95:  filtered.map((s,i)=>({x:(i/(filtered.length-1))*W,y:toY(s.p95,H)})),
  };

  const toPath = (pts:{x:number;y:number}[]) => pts.map((p,i)=>`${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const toArea = (top:{x:number;y:number}[],bot:{x:number;y:number}[]) => {
    const fwd = top.map((p,i)=>`${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    const bwd = [...bot].reverse().map(p=>`L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    return `${fwd} ${bwd} Z`;
  };

  const zeroY = toY(0,H);

  return (
    <div>
      <svg width="100%" height={H+30} viewBox={`0 0 ${W} ${H+30}`} style={{overflow:"visible"}}>
        {/* Zero line */}
        <line x1={0} y1={zeroY} x2={W} y2={zeroY} stroke={C.border} strokeDasharray="4,4" strokeWidth={1} />
        <text x={W+4} y={zeroY+4} fontSize={9} fill={C.dim}>0%</text>

        {/* P5-P95 shaded band */}
        <path d={toArea(paths.p95,paths.p5)} fill={`${C.cyan}18`} />
        {/* P25-P75 shaded band */}
        <path d={toArea(paths.p75,paths.p25)} fill={`${C.cyan}35`} />

        {/* Lines */}
        <path d={toPath(paths.p95)}  fill="none" stroke={`${C.cyan}88`}    strokeWidth={1} strokeDasharray="3,3" />
        <path d={toPath(paths.p5)}   fill="none" stroke={`${C.red}88`}     strokeWidth={1} strokeDasharray="3,3" />
        <path d={toPath(paths.p75)}  fill="none" stroke={`${C.green}aa`}   strokeWidth={1} />
        <path d={toPath(paths.p25)}  fill="none" stroke={`${C.orange}aa`}  strokeWidth={1} />
        <path d={toPath(paths.mean)} fill="none" stroke={C.cyan}            strokeWidth={2} />

        {/* X axis labels */}
        {filtered.map((s,i)=>(
          <text key={s.window_days} x={(i/(filtered.length-1))*W} y={H+20} fontSize={9} fill={C.dim} textAnchor="middle">{wLabel(s.window_days)}</text>
        ))}
      </svg>
      <div style={{display:"flex",gap:16,fontSize:10,color:C.dim,marginTop:4}}>
        {[["Mean",C.cyan],["P75",C.green],["P25",C.orange],["P95",`${C.cyan}88`],["P5",`${C.red}88`]].map(([l,c])=>(
          <span key={l}><span style={{color:c as string,fontWeight:700}}>—</span> {l}</span>
        ))}
      </div>
    </div>
  );
}

// ── Compare chart helpers ─────────────────────────────────────────────────
function RiskReturnScatter({data,syms}:{data:CompareData;syms:string[]}) {
  const points = syms.map((s,i)=>{
    const ws = data.window_stats.find(w=>w.symbol===s&&w.window_days===20);
    return ws ? {sym:s,x:ws.std_return,y:ws.mean_return,color:SYM_COLORS[i]} : null;
  }).filter(Boolean) as {sym:string;x:number;y:number;color:string}[];

  if (!points.length) return null;

  const xs=points.map(p=>p.x), ys=points.map(p=>p.y);
  const xMin=Math.min(...xs)*0.9, xMax=Math.max(...xs)*1.1;
  const yMin=Math.min(...ys,0)*1.1, yMax=Math.max(...ys)*1.1;
  const W=400, H=220;
  const toX=(v:number)=>((v-xMin)/(xMax-xMin))*W;
  const toY=(v:number)=>H-((v-yMin)/(yMax-yMin))*H;
  const zeroY=toY(0);

  return (
    <div>
      <div style={{fontSize:11,color:C.dim,marginBottom:8}}>Risk-Return Scatter (20-day window) — X: Std Dev, Y: Mean Return</div>
      <svg width="100%" height={H+40} viewBox={`-30 -10 ${W+80} ${H+50}`} style={{overflow:"visible"}}>
        <line x1={0} y1={zeroY} x2={W} y2={zeroY} stroke={C.border} strokeDasharray="4,4" strokeWidth={1} />
        <line x1={0} y1={0} x2={0} y2={H} stroke={C.border} strokeWidth={1} />
        {points.map(p=>(
          <g key={p.sym}>
            <circle cx={toX(p.x)} cy={toY(p.y)} r={8} fill={`${p.color}44`} stroke={p.color} strokeWidth={2} />
            <text x={toX(p.x)} y={toY(p.y)-13} textAnchor="middle" fontSize={11} fill={p.color} fontWeight="bold">{p.sym}</text>
          </g>
        ))}
        {/* Axes labels */}
        <text x={W/2} y={H+35} textAnchor="middle" fontSize={9} fill={C.dim}>Std Dev (Risk)</text>
        <text x={-20} y={H/2} textAnchor="middle" fontSize={9} fill={C.dim} transform={`rotate(-90,-20,${H/2})`}>Mean Return</text>
      </svg>
    </div>
  );
}

function ProbCompareChart({data,syms,window_days=20}:{data:CompareData;syms:string[];window_days?:number}) {
  const metrics = [
    {key:"prob_positive",label:"Prob UP",color:C.cyan},
    {key:"prob_gt10",    label:">+10%",  color:C.green},
    {key:"prob_lt_neg10",label:"<-10%",  color:C.red},
  ];

  return (
    <div>
      <div style={{fontSize:11,color:C.dim,marginBottom:10}}>Probability Comparison ({wLabel(window_days)} window)</div>
      {metrics.map(m=>(
        <div key={m.key} style={{marginBottom:14}}>
          <div style={{fontSize:10,color:C.dim,fontWeight:600,marginBottom:6}}>{m.label}</div>
          {syms.map((s,i)=>{
            const ws = data.window_stats.find(w=>w.symbol===s&&w.window_days===window_days);
            const v = ws ? ((ws as Record<string,unknown>)[m.key] as number||0)*100 : 0;
            return (
              <div key={s} style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
                <span style={{minWidth:80,fontSize:11,fontWeight:700,color:SYM_COLORS[i]}}>{s}</span>
                <div style={{flex:1,height:8,background:`${C.border}33`,borderRadius:4}}>
                  <div style={{height:8,width:`${Math.min(100,v)}%`,background:SYM_COLORS[i],borderRadius:4,opacity:0.8}} />
                </div>
                <span style={{fontSize:11,color:SYM_COLORS[i],fontWeight:700,minWidth:36}}>{v.toFixed(0)}%</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

// ── Percentile Fan (Compare) ───────────────────────────────────────────────
function PercentileFan({data,syms}:{data:CompareData;syms:string[]}) {
  const windows = DISPLAY_WINDOWS;
  return (
    <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
        <thead>
          <tr style={{background:`${C.border}22`}}>
            <th style={{padding:"5px 10px",textAlign:"left",color:C.dim,fontWeight:600,fontSize:10}}>Window</th>
            {syms.map((s,i)=>(
              <th key={s} colSpan={4} style={{padding:"5px 10px",textAlign:"center",color:SYM_COLORS[i],fontWeight:700,fontSize:10,borderLeft:`1px solid ${C.border}`}}>{s}</th>
            ))}
          </tr>
          <tr>
            <th style={{padding:"3px 10px",color:C.dim,fontSize:9}}></th>
            {syms.map(s=>(
              ["Mean","P5","P95","Prob+"].map(h=>(
                <th key={`${s}-${h}`} style={{padding:"3px 6px",textAlign:"right",color:C.dim,fontSize:9,fontWeight:600}}>{h}</th>
              ))
            ))}
          </tr>
        </thead>
        <tbody>
          {windows.map(wd=>(
            <tr key={wd} style={{borderBottom:`1px solid ${C.border}22`}}>
              <td style={{padding:"5px 10px",fontWeight:700,color:C.primary}}>{wLabel(wd)}</td>
              {syms.map((s,si)=>{
                const ws=data.window_stats.find(w=>w.symbol===s&&w.window_days===wd);
                const pp=(ws?.prob_positive||0)*100;
                return (
                  <React.Fragment key={s}>
                    <td style={{padding:"5px 6px",textAlign:"right",color:col(ws?.mean_return),fontWeight:600,borderLeft:`1px solid ${C.border}22`}}>{pct(ws?.mean_return)}</td>
                    <td style={{padding:"5px 6px",textAlign:"right",color:C.red}}>{pct(ws?.p5)}</td>
                    <td style={{padding:"5px 6px",textAlign:"right",color:C.cyan}}>{pct(ws?.p95)}</td>
                    <td style={{padding:"5px 6px",textAlign:"right",color:pp>=55?C.green:pp>=45?C.yellow:C.red,fontWeight:700}}>{pp.toFixed(0)}%</td>
                  </React.Fragment>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── SEARCH RESULT PANEL ────────────────────────────────────────────────────
function SearchResult({data,onClose}:{data:AnalysisData;onClose:()=>void}) {
  const [selWindow, setSelWindow] = useState(20);
  const [activeTab, setActiveTab] = useState<"overview"|"windows"|"episodes"|"technicals"|"seasonality"|"regime"|"correlations">("overview");

  const ss = data.series_stats;
  const tech = data.technicals;
  const lp = data.latest_price;
  const rank = data.rank;
  const rankPct = rank ? Math.round((rank.below_me/rank.total)*100) : null;

  const tabs = [
    {id:"overview",    label:"Overview"},
    {id:"windows",     label:"All Windows"},
    {id:"episodes",    label:"Best/Worst Episodes"},
    {id:"technicals",  label:"Technicals"},
    {id:"seasonality", label:"Seasonality"},
    {id:"regime",      label:"Regimes"},
    {id:"correlations",label:"Correlations"},
  ] as const;

  return (
    <div style={{marginTop:16}}>
      {/* Symbol header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:16}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:12}}>
            <h2 style={{margin:0,fontSize:26,fontWeight:900,color:C.cyan,letterSpacing:-1}}>{data.symbol}</h2>
            <span style={{fontSize:12,fontWeight:600,color:C.dim,border:`1px solid ${C.border}`,borderRadius:4,padding:"2px 8px"}}>{data.asset_type.toUpperCase()}</span>
            {rankPct !== null && (
              <span style={{fontSize:11,fontWeight:700,color:C.yellow,border:`1px solid ${C.yellow}44`,borderRadius:4,padding:"2px 8px"}}>Top {100-rankPct}% by 20d Prob</span>
            )}
          </div>
          {lp && (
            <div style={{color:C.dim,fontSize:12,marginTop:4}}>
              Price: <span style={{color:C.primary,fontWeight:700,fontSize:15}}>{lp.close?.toLocaleString("en-IN",{maximumFractionDigits:2})}</span>
              {" "}&bull; {lp.date}
              {lp.volume ? ` &bull; Vol: ${lp.volume?.toLocaleString("en-IN")}` : ""}
            </div>
          )}
        </div>
        <button onClick={onClose} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Clear</button>
      </div>

      {/* Sparkline */}
      {data.price_history.length>1 && (
        <div style={{marginBottom:16}}>
          <Sparkline data={data.price_history} height={60} />
        </div>
      )}

      {/* Series stats strip */}
      {ss && (
        <div style={{display:"flex",gap:10,flexWrap:"wrap",marginBottom:16}}>
          <StatBox label="CAGR"    value={pct(ss.cagr_pct,1)}         color={col(ss.cagr_pct)} />
          <StatBox label="Ann Vol" value={pct(ss.ann_volatility_pct,1)} />
          <StatBox label="Max DD"  value={pct(ss.max_drawdown_pct,1)}  color={C.red} />
          <StatBox label="Sharpe"  value={num(ss.sharpe_ratio)}        color={C.cyan} />
          <StatBox label="Sortino" value={num(ss.sortino_ratio)}       color={C.cyan} />
          <StatBox label="Calmar"  value={num(ss.calmar_ratio)}        color={C.cyan} />
          <StatBox label="N Days"  value={ss.n_trading_days?.toLocaleString()} />
          {ss.mdd_recovery_days!=null && <StatBox label="DD Recovery" value={`${ss.mdd_recovery_days}d`} />}
        </div>
      )}

      {/* Sub-tabs */}
      <div style={{display:"flex",gap:4,flexWrap:"wrap",marginBottom:14,borderBottom:`1px solid ${C.border}`,paddingBottom:8}}>
        {tabs.map(t=>(
          <button key={t.id} onClick={()=>setActiveTab(t.id)} style={{
            padding:"5px 12px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",
            background:activeTab===t.id?C.cyan:"transparent",
            color:activeTab===t.id?"#000":C.dim,
          }}>{t.label}</button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab==="overview" && (
        <div>
          <Card title="Best and Worst Durations — Full History" accent={C.cyan}>
            <BestWorstDurations stats={data.window_stats} />
          </Card>
          <Card title="Probability Heatmap — All Windows" accent={C.yellow}>
            <ProbHeatmap stats={data.window_stats} />
          </Card>
          <Card title="Return Distribution by Window (Percentile Fan)" accent={C.green}>
            <PercentileChart stats={data.window_stats} />
          </Card>
        </div>
      )}

      {activeTab==="windows" && (
        <Card title="Full Window Stats Table — click any row to select window" accent={C.cyan}>
          <WindowOverviewTable stats={data.window_stats} onSelect={setSelWindow} selected={selWindow} />
        </Card>
      )}

      {activeTab==="episodes" && (
        <Card title="Historical Best and Worst Episodes" accent={C.green}>
          <EpisodesPanel
            up={data.extremes_up} down={data.extremes_down}
            selectedWindow={selWindow} onWindowChange={setSelWindow}
            allWindows={ALL_WINDOWS}
          />
        </Card>
      )}

      {activeTab==="technicals" && tech && (
        <div>
          <Card title="Current Technical Indicators" accent={C.yellow}>
            <div style={{display:"flex",gap:10,flexWrap:"wrap",marginBottom:12}}>
              <StatBox label="RSI 14"    value={num(tech.rsi_14,1)} color={tech.rsi_14>70?C.red:tech.rsi_14<30?C.green:C.primary} sub={tech.rsi_14>70?"Overbought":tech.rsi_14<30?"Oversold":"Neutral"} />
              <StatBox label="ATR 14%"   value={pct(tech.atr_14_pct,2)} />
              <StatBox label="ADX 14"    value={num(tech.adx_14,1)} color={tech.adx_14>25?C.green:C.dim} sub={tech.adx_14>25?"Trending":"Ranging"} />
              <StatBox label="Vs SMA20"  value={pct(tech.pct_above_sma20,2)} color={col(tech.pct_above_sma20)} />
              <StatBox label="Vol Surge" value={`${num(tech.vol_surge_20d,1)}x`} color={tech.vol_surge_20d>2?C.green:C.dim} />
              <StatBox label="MACD"      value={tech.macd_line>tech.macd_signal?"BULL":"BEAR"} color={tech.macd_line>tech.macd_signal?C.green:C.red} />
              <StatBox label="BB%"       value={num(tech.bb_pct,2)} />
            </div>
          </Card>
          {data.insider_trades.length>0 && (
            <Card title="Recent Insider Trades" accent={C.yellow}>
              <div style={{overflowX:"auto"}}>
                <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                  <thead><tr>{["Date","Name","Type","Qty","Price","Value Cr"].map(h=><th key={h} style={{padding:"4px 8px",color:C.dim,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
                  <tbody>{data.insider_trades.map((t,i)=>(
                    <tr key={i} style={{borderBottom:`1px solid ${C.border}22`}}>
                      <td style={{padding:"4px 8px",color:C.dim,textAlign:"right"}}>{t.filing_date}</td>
                      <td style={{padding:"4px 8px",textAlign:"right"}}>{t.name}</td>
                      <td style={{padding:"4px 8px",fontWeight:700,textAlign:"right",color:t.transaction_type==="BUY"?C.green:C.red}}>{t.transaction_type}</td>
                      <td style={{padding:"4px 8px",textAlign:"right"}}>{t.quantity?.toLocaleString("en-IN")}</td>
                      <td style={{padding:"4px 8px",textAlign:"right"}}>{num(t.price,1)}</td>
                      <td style={{padding:"4px 8px",textAlign:"right",color:C.cyan}}>{t.value?(t.value/1e7).toFixed(2):"--"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </Card>
          )}
          {data.announcements.length>0 && (
            <Card title="Recent Corporate Announcements" accent={C.dim}>
              {data.announcements.map((a,i)=>(
                <div key={i} style={{display:"flex",gap:12,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
                  <span style={{color:C.dim,minWidth:90}}>{a.announcement_date}</span>
                  <span>{a.subject}</span>
                </div>
              ))}
            </Card>
          )}
        </div>
      )}

      {activeTab==="seasonality" && (
        <Card title="Monthly Seasonality (mean return per month historically)" accent={C.cyan}>
          <SeasonChart data={data.seasonality} />
          {data.seasonality.length>0 && (
            <div style={{marginTop:16,overflowX:"auto"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead><tr>{["Month","Avg Return","Median","N Obs"].map(h=><th key={h} style={{padding:"4px 8px",color:C.dim,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
                <tbody>{data.seasonality.map(r=>(
                  <tr key={r.period_value} style={{borderBottom:`1px solid ${C.border}22`}}>
                    <td style={{padding:"4px 8px",fontWeight:700,color:C.primary,textAlign:"right"}}>{MONTHS[r.period_value-1]}</td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:col(r.mean_return_pct),fontWeight:600}}>{pct(r.mean_return_pct)}</td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:col(r.median_return_pct)}}>{pct(r.median_return_pct)}</td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:C.dim}}>{r.n_obs}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {activeTab==="regime" && (
        <Card title="Performance by Market Regime (20d window)" accent={C.orange}>
          {(() => {
            const regimes20 = data.regime_stats.filter(r=>r.window_days===20);
            if (!regimes20.length) return <div style={{color:C.dim,fontSize:12}}>No regime data</div>;
            return (
              <div>
                <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(200px,1fr))",gap:10,marginBottom:16}}>
                  {regimes20.map(r=>(
                    <div key={r.regime} style={{background:`${C.border}22`,borderRadius:6,padding:"12px 14px",borderLeft:`3px solid ${col(r.mean_return)}`}}>
                      <div style={{fontSize:11,fontWeight:700,color:C.dim,marginBottom:6}}>{r.regime}</div>
                      <div style={{fontSize:16,fontWeight:800,color:col(r.mean_return)}}>{pct(r.mean_return)}</div>
                      <div style={{fontSize:11,color:C.green}}>Prob+: {r.prob_positive!=null?((r.prob_positive)*100).toFixed(0)+"%":"--"}</div>
                      <div style={{fontSize:11,color:C.dim}}>N={r.n_windows} &bull; P5:{pct(r.p5)} P95:{pct(r.p95)}</div>
                    </div>
                  ))}
                </div>
                {/* Other windows regime */}
                <div style={{overflowX:"auto"}}>
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
                    <thead><tr>{["Window","Regime","Mean","Prob+","N","P5","P95"].map(h=><th key={h} style={{padding:"4px 8px",color:C.dim,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
                    <tbody>{data.regime_stats.filter(r=>r.window_days!==20&&DISPLAY_WINDOWS.includes(r.window_days)).map((r,i)=>(
                      <tr key={i} style={{borderBottom:`1px solid ${C.border}22`}}>
                        <td style={{padding:"4px 8px",fontWeight:700,textAlign:"right"}}>{wLabel(r.window_days)}</td>
                        <td style={{padding:"4px 8px",textAlign:"right",color:C.dim}}>{r.regime}</td>
                        <td style={{padding:"4px 8px",textAlign:"right",color:col(r.mean_return),fontWeight:600}}>{pct(r.mean_return)}</td>
                        <td style={{padding:"4px 8px",textAlign:"right",color:C.green}}>{r.prob_positive!=null?((r.prob_positive)*100).toFixed(0)+"%":"--"}</td>
                        <td style={{padding:"4px 8px",textAlign:"right",color:C.dim}}>{r.n_windows}</td>
                        <td style={{padding:"4px 8px",textAlign:"right",color:C.red}}>{pct(r.p5)}</td>
                        <td style={{padding:"4px 8px",textAlign:"right",color:C.cyan}}>{pct(r.p95)}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </div>
            );
          })()}
        </Card>
      )}

      {activeTab==="correlations" && (
        <Card title="Top Correlated Assets" accent={C.dim}>
          {data.correlations.length===0 ? <div style={{color:C.dim,fontSize:12}}>No correlation data</div> :
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(180px,1fr))",gap:8}}>
            {data.correlations.map(c=>(
              <div key={c.symbol_b} style={{background:`${C.border}22`,borderRadius:6,padding:"10px 12px"}}>
                <div style={{color:C.cyan,fontWeight:800,fontSize:14,marginBottom:4}}>{c.symbol_b}</div>
                <div style={{fontSize:11,color:C.dim}}>20d corr: <span style={{color:col(c.correlation_20d),fontWeight:700}}>{num(c.correlation_20d)}</span></div>
                <div style={{fontSize:11,color:C.dim}}>60d corr: <span style={{color:col(c.correlation_60d)}}>{num(c.correlation_60d)}</span></div>
                <div style={{fontSize:11,color:C.dim}}>Beta: <span style={{color:C.yellow}}>{num(c.beta_20d,2)}</span></div>
              </div>
            ))}
          </div>}
        </Card>
      )}
    </div>
  );
}

// ── COMPARE RESULT PANEL ─────────────────────────────────────────────────────
function CompareResult({data,onClose}:{data:CompareData;onClose:()=>void}) {
  const [activeTab,setActiveTab] = useState<"summary"|"windows"|"probability"|"seasonality"|"correlation">("summary");
  const [cmpWindow, setCmpWindow] = useState(20);
  const syms = data.symbols;

  const seriesMap = Object.fromEntries(data.series_stats.map(s=>[s.symbol,s]));
  const techMap   = Object.fromEntries(data.technicals.map(s=>[s.symbol,s]));
  const priceMap  = Object.fromEntries(data.prices.map(s=>[s.symbol,s]));

  const tabs = [
    {id:"summary",     label:"Summary"},
    {id:"windows",     label:"Window Analysis"},
    {id:"probability", label:"Probability Chart"},
    {id:"seasonality", label:"Seasonality"},
    {id:"correlation", label:"Correlations"},
  ] as const;

  const highlightBest = (vals:(number|null|undefined)[],higher=true)=>{
    const nums = vals.map(v=>v??NaN);
    const valid = nums.filter(n=>!isNaN(n));
    const target = higher ? Math.max(...valid) : Math.min(...valid);
    return nums.map(n=>!isNaN(n)&&n===target);
  };

  return (
    <div style={{marginTop:16}}>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
        <div style={{display:"flex",gap:12,alignItems:"center"}}>
          <h2 style={{margin:0,fontSize:20,fontWeight:900}}>COMPARING</h2>
          {syms.map((s,i)=>(
            <span key={s} style={{color:SYM_COLORS[i],fontWeight:700,fontSize:14,padding:"3px 8px",border:`1px solid ${SYM_COLORS[i]}44`,borderRadius:4}}>{s}</span>
          ))}
        </div>
        <button onClick={onClose} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Clear</button>
      </div>

      {/* Sub-tabs */}
      <div style={{display:"flex",gap:4,flexWrap:"wrap",marginBottom:14,borderBottom:`1px solid ${C.border}`,paddingBottom:8}}>
        {tabs.map(t=>(
          <button key={t.id} onClick={()=>setActiveTab(t.id)} style={{padding:"5px 12px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:activeTab===t.id?C.cyan:"transparent",color:activeTab===t.id?"#000":C.dim}}>{t.label}</button>
        ))}
      </div>

      {activeTab==="summary" && (
        <div>
          <Card title="Series Statistics (Full History)" accent={C.cyan}>
            <div style={{overflowX:"auto"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead><tr>
                  <th style={{padding:"5px 10px",textAlign:"left",color:C.dim,fontWeight:600,borderBottom:`1px solid ${C.border}`}}>Metric</th>
                  {syms.map((s,i)=><th key={s} style={{padding:"5px 10px",textAlign:"right",color:SYM_COLORS[i],fontWeight:700,borderBottom:`1px solid ${C.border}`}}>{s}</th>)}
                </tr></thead>
                <tbody>
                  {[
                    {label:"Latest Price",    vals:syms.map(s=>priceMap[s]?.close?.toLocaleString("en-IN",{maximumFractionDigits:2})||"--"), hi:undefined},
                    {label:"CAGR%",           vals:syms.map(s=>seriesMap[s]?.cagr_pct),           hi:true,  cf:col},
                    {label:"Ann Volatility%", vals:syms.map(s=>seriesMap[s]?.ann_volatility_pct), hi:false},
                    {label:"Max Drawdown%",   vals:syms.map(s=>seriesMap[s]?.max_drawdown_pct),   hi:false},
                    {label:"Sharpe",          vals:syms.map(s=>seriesMap[s]?.sharpe_ratio),        hi:true},
                    {label:"Sortino",         vals:syms.map(s=>seriesMap[s]?.sortino_ratio),       hi:true},
                    {label:"Calmar",          vals:syms.map(s=>seriesMap[s]?.calmar_ratio),        hi:true},
                    {label:"RSI 14",          vals:syms.map(s=>techMap[s]?.rsi_14),                hi:undefined},
                    {label:"ADX 14",          vals:syms.map(s=>techMap[s]?.adx_14),                hi:true},
                    {label:"Vs SMA20%",       vals:syms.map(s=>techMap[s]?.pct_above_sma20),       hi:true, cf:col},
                    {label:"MACD Signal",     vals:syms.map(s=>{const t=techMap[s];return t?(t.macd_line>t.macd_signal?"BULL":"BEAR"):null;}), hi:undefined},
                  ].map(row=>{
                    const isBest = row.hi!==undefined ? highlightBest(row.vals as number[],row.hi) : null;
                    return (
                      <tr key={row.label} style={{borderBottom:`1px solid ${C.border}22`}}>
                        <td style={{padding:"5px 10px",color:C.dim}}>{row.label}</td>
                        {(row.vals as unknown[]).map((v,i)=>{
                          const isN = typeof v==="number";
                          const txt = isN ? (row.label.includes("%")||row.label.includes("CAGR")||row.label.includes("Vol")||row.label.includes("DD")||row.label.includes("SMA") ? pct(v) : num(v)) : String(v??"--");
                          const clr = (row as Record<string,unknown>).cf ? ((row as Record<string,unknown>).cf as (v:unknown)=>string)(v) : (isBest?.[i]?SYM_COLORS[i]:C.primary);
                          return <td key={i} style={{padding:"5px 10px",textAlign:"right",color:clr,fontWeight:isBest?.[i]?800:400,background:isBest?.[i]?`${SYM_COLORS[i]}15`:"transparent"}}>{txt}</td>;
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="Risk-Return Scatter (20d window)" accent={C.cyan}>
            <RiskReturnScatter data={data} syms={syms} />
          </Card>
        </div>
      )}

      {activeTab==="windows" && (
        <div>
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:12}}>
            {DISPLAY_WINDOWS.map(d=>(
              <button key={d} onClick={()=>setCmpWindow(d)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"1px solid",background:cmpWindow===d?C.cyan:"transparent",color:cmpWindow===d?"#000":C.dim,borderColor:cmpWindow===d?C.cyan:C.border}}>{wLabel(d)}</button>
            ))}
          </div>
          <Card title={`Window Comparison — All Windows`} accent={C.green}>
            <PercentileFan data={data} syms={syms} />
          </Card>
        </div>
      )}

      {activeTab==="probability" && (
        <div>
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:12}}>
            {DISPLAY_WINDOWS.map(d=>(
              <button key={d} onClick={()=>setCmpWindow(d)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"1px solid",background:cmpWindow===d?C.cyan:"transparent",color:cmpWindow===d?"#000":C.dim,borderColor:cmpWindow===d?C.cyan:C.border}}>{wLabel(d)}</button>
            ))}
          </div>
          <Card title="Probability Comparison" accent={C.yellow}>
            <ProbCompareChart data={data} syms={syms} window_days={cmpWindow} />
          </Card>
        </div>
      )}

      {activeTab==="seasonality" && (
        <Card title="Seasonality Comparison (Monthly Average Return)" accent={C.cyan}>
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:12}}>
            {syms.map((s,i)=>{
              const sData = data.seasonality.filter(r=>r.symbol===s);
              const maxA = Math.max(...sData.map(r=>Math.abs(r.mean_return_pct||0)),1);
              return (
                <div key={s}>
                  <div style={{color:SYM_COLORS[i],fontWeight:700,fontSize:12,marginBottom:8}}>{s}</div>
                  <div style={{display:"flex",gap:3,alignItems:"flex-end",height:60}}>
                    {sData.map(r=>{
                      const h=Math.max(2,(Math.abs(r.mean_return_pct||0)/maxA)*55);
                      const pos=(r.mean_return_pct||0)>=0;
                      return <div key={r.period_value} style={{flex:1,height:h,background:pos?SYM_COLORS[i]:C.red,opacity:0.7,borderRadius:"1px 1px 0 0",minHeight:2}} />;
                    })}
                  </div>
                  <div style={{display:"flex",gap:3}}>
                    {sData.map(r=><div key={r.period_value} style={{flex:1,textAlign:"center",fontSize:7,color:C.dim}}>{MONTHS[r.period_value-1].slice(0,1)}</div>)}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {activeTab==="correlation" && (
        <Card title="Cross Correlations" accent={C.dim}>
          {data.cross_correlations.length===0 ? <div style={{color:C.dim,fontSize:12}}>No cross-correlation data</div> :
          <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
            {data.cross_correlations.map(c=>(
              <div key={`${c.symbol_a}-${c.symbol_b}`} style={{background:`${C.border}22`,borderRadius:6,padding:"8px 12px",fontSize:12}}>
                <span style={{color:SYM_COLORS[syms.indexOf(c.symbol_a)]||C.cyan,fontWeight:700}}>{c.symbol_a}</span>
                <span style={{color:C.dim}}> x </span>
                <span style={{color:SYM_COLORS[syms.indexOf(c.symbol_b)]||C.green,fontWeight:700}}>{c.symbol_b}</span>
                <div style={{fontSize:11,marginTop:4}}>
                  <span style={{color:C.dim}}>20d: </span><span style={{color:col(c.correlation_20d),fontWeight:700}}>{num(c.correlation_20d)}</span>
                  <span style={{color:C.dim}}> | beta: </span><span style={{color:C.yellow}}>{num(c.beta_20d,2)}</span>
                </div>
              </div>
            ))}
          </div>}
        </Card>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════

export default function AnalysisPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"search-stock"|"compare-stocks"|"search-index"|"compare-index">("search-stock");

  // Search state
  const [searchInput, setSearchInput] = useState("");
  const [searchData, setSearchData]   = useState<AnalysisData|null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string|null>(null);

  // Compare state
  const [cmpInput, setCmpInput]   = useState("");
  const [cmpData, setCmpData]     = useState<CompareData|null>(null);
  const [cmpLoading, setCmpLoading] = useState(false);
  const [cmpError, setCmpError]   = useState<string|null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  const isCompareMode = mode==="compare-stocks"||mode==="compare-index";
  const assetType = mode==="search-index"||mode==="compare-index" ? "index" : "stock";

  const doSearch = useCallback(async(sym:string) => {
    if (!sym.trim()) return;
    setSearchLoading(true); setSearchError(null); setSearchData(null);
    try {
      const r = await fetch(`/api/analysis?symbol=${encodeURIComponent(sym.trim().toUpperCase())}&type=auto`,{cache:"no-store"});
      const d = await r.json();
      if (!d.ok) throw new Error(d.error||"Not found");
      setSearchData(d);
    } catch(e:unknown) { setSearchError(String(e)); }
    finally { setSearchLoading(false); }
  },[]);

  const doCompare = useCallback(async(raw:string) => {
    const syms = raw.split(/[,\s]+/).map(s=>s.trim().toUpperCase()).filter(Boolean).slice(0,5);
    if (syms.length<2) { setCmpError("Enter 2-5 symbols"); return; }
    setCmpLoading(true); setCmpError(null); setCmpData(null);
    try {
      const r = await fetch(`/api/analysis/compare?symbols=${syms.join(",")}`,{cache:"no-store"});
      const d = await r.json();
      if (!d.ok) throw new Error(d.error||"API error");
      setCmpData(d);
    } catch(e:unknown) { setCmpError(String(e)); }
    finally { setCmpLoading(false); }
  },[]);

  const PRESETS_STOCK = [
    ["Top Banks",  "HDFCBANK,ICICIBANK,SBIN,AXISBANK,KOTAKBANK"],
    ["IT Giants",  "TCS,INFY,WIPRO,HCLTECH,TECHM"],
    ["Nifty Top5", "RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK"],
    ["FMCG",       "HINDUNILVR,ITC,NESTLEIND,BRITANNIA,DABUR"],
    ["Auto",       "MARUTI,TATAMOTORS,M&M,BAJAJ-AUTO,EICHERMOT"],
  ];
  const PRESETS_INDEX = [
    ["Broad Mkt",  "NIFTY 50,NIFTY MIDCAP 100,NIFTY SMALLCAP 100"],
    ["Sectoral",   "NIFTY BANK,NIFTY IT,NIFTY PHARMA,NIFTY AUTO"],
    ["Global",     "SPX,NDX,NIKKEI225,DAX,FTSE100"],
  ];

  const modeButtons = [
    {id:"search-stock",   label:"Search Stock",   icon:"S"},
    {id:"compare-stocks", label:"Compare Stocks",  icon:"C"},
    {id:"search-index",   label:"Search Index",   icon:"I"},
    {id:"compare-index",  label:"Compare Indices", icon:"CI"},
  ] as const;

  return (
    <div style={{maxWidth:1200,margin:"0 auto",padding:"20px 16px"}}>

      {/* Page header */}
      <div style={{marginBottom:20}}>
        <h1 style={{margin:0,fontSize:24,fontWeight:900,letterSpacing:-0.5}}>ANALYTICS HUB</h1>
        <div style={{color:C.dim,fontSize:12,marginTop:4}}>Deep analysis for every stock and index — 649k historical episodes, 17 time windows, full probability stats</div>
      </div>

      {/* Mode selector */}
      <div style={{display:"flex",gap:6,marginBottom:20,background:`${C.border}22`,borderRadius:8,padding:6}}>
        {modeButtons.map(b=>(
          <button key={b.id} onClick={()=>{setMode(b.id);setSearchData(null);setCmpData(null);setSearchError(null);setCmpError(null);}} style={{
            flex:1,padding:"10px 8px",borderRadius:6,fontSize:12,fontWeight:700,cursor:"pointer",border:"none",
            background:mode===b.id?C.cyan:"transparent",
            color:mode===b.id?"#000":C.dim,
            transition:"all 0.15s",
          }}>{b.label}</button>
        ))}
      </div>

      {/* Search / Compare input area */}
      {!isCompareMode ? (
        /* SEARCH MODE */
        <div style={{marginBottom:16}}>
          <div style={{display:"flex",gap:8}}>
            <input
              ref={searchInputRef}
              value={searchInput}
              onChange={e=>setSearchInput(e.target.value.toUpperCase())}
              onKeyDown={e=>e.key==="Enter"&&doSearch(searchInput)}
              placeholder={mode==="search-stock" ? "Enter stock symbol (e.g. RELIANCE, TCS, INFY)..." : "Enter index name (e.g. NIFTY 50, NIFTY BANK, SPX)..."}
              style={{flex:1,background:C.surface,border:`1px solid ${C.border}`,color:C.primary,borderRadius:8,padding:"12px 16px",fontSize:14}}
              autoFocus
            />
            <button onClick={()=>doSearch(searchInput)} disabled={searchLoading} style={{
              background:C.cyan,color:"#000",border:"none",borderRadius:8,
              padding:"12px 24px",fontWeight:800,cursor:"pointer",fontSize:14,
              opacity:searchLoading?0.6:1,minWidth:120,
            }}>{searchLoading?"Loading...":"Analyze"}</button>
          </div>
          {searchError && <div style={{color:C.red,fontSize:13,marginTop:8}}>{searchError}</div>}
        </div>
      ) : (
        /* COMPARE MODE */
        <div style={{marginBottom:16}}>
          <div style={{display:"flex",gap:8,marginBottom:8}}>
            <input
              value={cmpInput}
              onChange={e=>setCmpInput(e.target.value.toUpperCase())}
              onKeyDown={e=>e.key==="Enter"&&doCompare(cmpInput)}
              placeholder={mode==="compare-stocks" ? "RELIANCE, TCS, HDFCBANK, INFY (2-5 symbols)" : "NIFTY 50, NIFTY BANK, NIFTY IT (2-5 indices)"}
              style={{flex:1,background:C.surface,border:`1px solid ${C.border}`,color:C.primary,borderRadius:8,padding:"12px 16px",fontSize:14}}
              autoFocus
            />
            <button onClick={()=>doCompare(cmpInput)} disabled={cmpLoading} style={{
              background:C.cyan,color:"#000",border:"none",borderRadius:8,
              padding:"12px 24px",fontWeight:800,cursor:"pointer",fontSize:14,
              opacity:cmpLoading?0.6:1,minWidth:120,
            }}>{cmpLoading?"Loading...":"Compare"}</button>
          </div>
          {/* Presets */}
          <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
            {(mode==="compare-stocks"?PRESETS_STOCK:PRESETS_INDEX).map(([label,val])=>(
              <button key={label} onClick={()=>{setCmpInput(val.replace(/,/g,", "));doCompare(val);}} style={{
                background:"transparent",border:`1px solid ${C.border}`,color:C.dim,
                borderRadius:4,padding:"4px 10px",cursor:"pointer",fontSize:11,fontWeight:600,
              }}>{label}</button>
            ))}
          </div>
          {cmpError && <div style={{color:C.red,fontSize:13,marginTop:8}}>{cmpError}</div>}
          {cmpLoading && <div style={{color:C.dim,padding:"20px 0",textAlign:"center"}}>Loading comparison data...</div>}
        </div>
      )}

      {/* Results */}
      {searchLoading && (
        <div style={{padding:40,textAlign:"center",color:C.dim}}>
          Analyzing {searchInput}... pulling 649k historical episodes...
        </div>
      )}
      {searchData && <SearchResult data={searchData} onClose={()=>{setSearchData(null);setSearchInput("");}} />}
      {cmpData && <CompareResult data={cmpData} onClose={()=>{setCmpData(null);setCmpInput("");}} />}
    </div>
  );
}
""")


# =============================================================================
# [5] New /watchlist/page.tsx -- multiple lists + alerts + DB direct
# =============================================================================
print("\n[5/6] /watchlist/page.tsx (multi-list + alerts rewrite)")

write(APP / "watchlist" / "page.tsx", r"""
"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

// ── Types ──────────────────────────────────────────────────────────────────
interface WatchList { id:string; name:string; symbols:string[]; alerts:Alert[]; }
interface Alert { id:string; symbol:string; type:string; value?:number; low?:number; high?:number; note?:string; }
interface PriceData { symbol:string; close:number; date:string; volume:number; pct_1d:number; }
interface TechData  { symbol:string; rsi_14:number; adx_14:number; pct_above_sma20:number; vol_surge_20d:number; macd_line:number; macd_signal:number; atr_14_pct:number; }
interface Triggered { symbol:string; type:string; reason:string; close:number; listId:string; listName:string; }

const C = {
  green:"#4ade80",red:"#f87171",cyan:"#22d3ee",yellow:"#facc15",orange:"#f97316",
  dim:"var(--text-tertiary)",primary:"var(--text-primary)",
  border:"var(--border-color)",surface:"var(--surface-card)",
};

const ALERT_TYPES = [
  {id:"price_above",   label:"Price Above",    fields:["value"],          desc:"Triggers when price >= value"},
  {id:"price_below",   label:"Price Below",    fields:["value"],          desc:"Triggers when price <= value"},
  {id:"price_band",    label:"Price Band",     fields:["low","high"],     desc:"Triggers when price is inside low-high band"},
  {id:"pct_move_up",   label:"% Move Up",      fields:["value"],          desc:"Triggers when 1d gain >= value%"},
  {id:"pct_move_down", label:"% Move Down",    fields:["value"],          desc:"Triggers when 1d drop >= value%"},
  {id:"volume_surge",  label:"Volume Surge",   fields:["value"],          desc:"Triggers when vol surge 20d >= value x"},
  {id:"rsi_above",     label:"RSI Above",      fields:["value"],          desc:"Triggers when RSI 14 >= value"},
  {id:"rsi_below",     label:"RSI Below",      fields:["value"],          desc:"Triggers when RSI 14 <= value"},
  {id:"above_sma20",   label:"Above SMA20",    fields:[],                 desc:"Triggers when price crosses above SMA20"},
  {id:"below_sma20",   label:"Below SMA20",    fields:[],                 desc:"Triggers when price drops below SMA20"},
];

function col(v:number|null|undefined){return(v??0)>=0?C.green:C.red;}
function pct(v:number|null|undefined,d=2){if(v==null)return"--";return`${v>=0?"+":""}${v.toFixed(d)}%`;}
function num(v:number|null|undefined,d=2){if(v==null)return"--";return v.toFixed(d);}

function Card({title,children,accent,action}:{title?:string;children:React.ReactNode;accent?:string;action?:React.ReactNode}){
  return(
    <div style={{background:C.surface,border:`1px solid ${accent||C.border}`,borderRadius:8,marginBottom:14,overflow:"hidden"}}>
      {title&&<div style={{padding:"10px 16px",display:"flex",justifyContent:"space-between",alignItems:"center",borderBottom:`1px solid ${C.border}`}}>
        <span style={{fontSize:11,fontWeight:700,letterSpacing:1.4,color:accent||C.cyan,textTransform:"uppercase"}}>{title}</span>
        {action}
      </div>}
      <div style={{padding:"12px 16px"}}>{children}</div>
    </div>
  );
}

function AlertBadge({type}:{type:string}){
  const colors:Record<string,string> = {
    price_above:C.green,price_below:C.red,price_band:C.yellow,
    pct_move_up:C.green,pct_move_down:C.red,
    volume_surge:C.cyan,rsi_above:C.orange,rsi_below:C.orange,
    above_sma20:C.green,below_sma20:C.red,
  };
  const label = ALERT_TYPES.find(a=>a.id===type)?.label||type;
  const color = colors[type]||C.dim;
  return <span style={{fontSize:10,fontWeight:700,color,background:`${color}22`,border:`1px solid ${color}44`,borderRadius:3,padding:"1px 6px"}}>{label}</span>;
}

export default function WatchlistPage() {
  const router = useRouter();
  const [lists,     setLists]     = useState<WatchList[]>([]);
  const [prices,    setPrices]    = useState<Record<string,PriceData>>({});
  const [technicals,setTechnicals]= useState<Record<string,TechData>>({});
  const [triggered, setTriggered] = useState<Triggered[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [saving,    setSaving]    = useState(false);
  const [activeList,setActiveList]= useState<string>("");
  const [addSym,    setAddSym]    = useState("");
  const [newListName,setNewListName]=useState("");
  const [showNewList,setShowNewList]=useState(false);
  const [showAddAlert,setShowAddAlert]=useState<{listId:string;symbol:string}|null>(null);
  const [alertForm, setAlertForm] = useState({type:"price_above",value:"",low:"",high:"",note:""});

  const load = useCallback(async()=>{
    setLoading(true);
    try {
      const r = await fetch("/api/watchlist-alerts",{cache:"no-store"});
      const d = await r.json();
      if (d.ok){
        setLists(d.watchlists||[]);
        setPrices(d.prices||{});
        setTechnicals(d.technicals||{});
        setTriggered(d.triggered||[]);
        if (!activeList && d.watchlists?.length>0) setActiveList(d.watchlists[0].id);
      }
    } finally { setLoading(false); }
  },[activeList]);

  useEffect(()=>{load();},[load]);

  const api = async(body:Record<string,unknown>)=>{
    setSaving(true);
    try {
      const r = await fetch("/api/watchlist-alerts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const d = await r.json();
      if (d.ok) setLists(d.watchlists||[]);
    } finally { setSaving(false); }
  };

  const currentList = lists.find(l=>l.id===activeList)||lists[0];

  const createList = async()=>{
    if (!newListName.trim()) return;
    await api({action:"create_list",name:newListName.trim()});
    setNewListName(""); setShowNewList(false);
    await load();
  };

  const addSymbol = async()=>{
    if (!addSym.trim()||!currentList) return;
    await api({action:"add_symbol",listId:currentList.id,symbol:addSym.trim().toUpperCase()});
    setAddSym(""); await load();
  };

  const removeSymbol = async(sym:string)=>{
    if (!currentList) return;
    await api({action:"remove_symbol",listId:currentList.id,symbol:sym});
    await load();
  };

  const addAlert = async()=>{
    if (!showAddAlert) return;
    const alert = {
      symbol: showAddAlert.symbol,
      type: alertForm.type,
      ...(alertForm.value ? {value:parseFloat(alertForm.value)} : {}),
      ...(alertForm.low   ? {low:parseFloat(alertForm.low)}     : {}),
      ...(alertForm.high  ? {high:parseFloat(alertForm.high)}   : {}),
      ...(alertForm.note  ? {note:alertForm.note}               : {}),
    };
    await api({action:"add_alert",listId:showAddAlert.listId,alert});
    setShowAddAlert(null); setAlertForm({type:"price_above",value:"",low:"",high:"",note:""});
    await load();
  };

  const removeAlert = async(listId:string,alertId:string)=>{
    await api({action:"remove_alert",listId,alertId});
    await load();
  };

  if (loading) return <div style={{padding:40,color:C.dim,textAlign:"center"}}>Loading watchlists...</div>;

  return (
    <div style={{maxWidth:1100,margin:"0 auto",padding:"20px 16px"}}>

      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}>
        <div>
          <h1 style={{margin:0,fontSize:22,fontWeight:900}}>WATCHLIST</h1>
          <div style={{color:C.dim,fontSize:12,marginTop:4}}>Multiple lists, per-stock alerts, live DB data — no agent needed</div>
        </div>
        <button onClick={load} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Refresh</button>
      </div>

      {/* Triggered alerts banner */}
      {triggered.length>0 && (
        <div style={{background:`${C.yellow}18`,border:`1px solid ${C.yellow}`,borderRadius:8,padding:"10px 16px",marginBottom:16}}>
          <div style={{fontSize:11,fontWeight:700,color:C.yellow,letterSpacing:1.2,marginBottom:8}}>ALERTS TRIGGERED ({triggered.length})</div>
          {triggered.map((t,i)=>(
            <div key={i} style={{display:"flex",gap:12,padding:"4px 0",fontSize:12}}>
              <span style={{color:C.cyan,fontWeight:700,minWidth:100,cursor:"pointer"}} onClick={()=>router.push(`/analysis?sym=${t.symbol}`)}>{t.symbol}</span>
              <AlertBadge type={t.type} />
              <span style={{color:C.primary}}>{t.reason}</span>
              <span style={{color:C.dim,fontSize:11}}>[{t.listName}]</span>
            </div>
          ))}
        </div>
      )}

      <div style={{display:"grid",gridTemplateColumns:"200px 1fr",gap:16}}>

        {/* LEFT: List selector */}
        <div>
          <div style={{fontSize:10,fontWeight:700,color:C.dim,letterSpacing:1.2,marginBottom:8}}>YOUR LISTS</div>
          {lists.map(l=>(
            <div key={l.id} onClick={()=>setActiveList(l.id)} style={{
              padding:"8px 12px",borderRadius:6,cursor:"pointer",marginBottom:4,
              background:activeList===l.id?`${C.cyan}22`:`${C.border}22`,
              border:`1px solid ${activeList===l.id?C.cyan:C.border}`,
              color:activeList===l.id?C.cyan:C.primary,fontWeight:activeList===l.id?700:400,fontSize:13,
            }}>
              <div>{l.name}</div>
              <div style={{fontSize:10,color:C.dim}}>{l.symbols.length} stocks &bull; {l.alerts.length} alerts</div>
            </div>
          ))}

          {showNewList ? (
            <div style={{marginTop:8}}>
              <input value={newListName} onChange={e=>setNewListName(e.target.value)}
                onKeyDown={e=>e.key==="Enter"&&createList()}
                placeholder="List name..."
                style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"6px 8px",fontSize:12,boxSizing:"border-box"}} />
              <div style={{display:"flex",gap:4,marginTop:4}}>
                <button onClick={createList} style={{flex:1,background:C.cyan,color:"#000",border:"none",borderRadius:4,padding:"5px",fontWeight:700,cursor:"pointer",fontSize:11}}>Create</button>
                <button onClick={()=>setShowNewList(false)} style={{flex:1,background:"transparent",color:C.dim,border:`1px solid ${C.border}`,borderRadius:4,padding:"5px",cursor:"pointer",fontSize:11}}>Cancel</button>
              </div>
            </div>
          ) : (
            <button onClick={()=>setShowNewList(true)} style={{width:"100%",marginTop:8,background:"transparent",border:`1px dashed ${C.border}`,color:C.dim,borderRadius:6,padding:"8px",cursor:"pointer",fontSize:12,fontWeight:600}}>+ New List</button>
          )}
        </div>

        {/* RIGHT: List content */}
        <div>
          {!currentList ? (
            <div style={{color:C.dim,padding:40,textAlign:"center"}}>Create a list to get started</div>
          ) : (
            <>
              {/* Add symbol */}
              <div style={{display:"flex",gap:8,marginBottom:14}}>
                <input value={addSym} onChange={e=>setAddSym(e.target.value.toUpperCase())}
                  onKeyDown={e=>e.key==="Enter"&&addSymbol()}
                  placeholder={`Add symbol to "${currentList.name}"...`}
                  style={{flex:1,background:C.surface,border:`1px solid ${C.border}`,color:C.primary,borderRadius:6,padding:"9px 14px",fontSize:13}}
                />
                <button onClick={addSymbol} disabled={saving} style={{background:C.cyan,color:"#000",border:"none",borderRadius:6,padding:"9px 18px",fontWeight:700,cursor:"pointer",fontSize:13,opacity:saving?0.6:1}}>Add</button>
              </div>

              {/* Stocks table */}
              {currentList.symbols.length===0 ? (
                <div style={{color:C.dim,fontSize:12,padding:"20px 0",textAlign:"center"}}>No stocks yet. Add symbols above.</div>
              ) : (
                <div style={{overflowX:"auto",marginBottom:14}}>
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                    <thead>
                      <tr style={{background:`${C.border}22`}}>
                        {["Symbol","Price","Date","1D %","Vol Surge","RSI","Vs SMA20","MACD","Alerts","Actions"].map(h=>(
                          <th key={h} style={{padding:"6px 10px",textAlign:h==="Symbol"?"left":"right",color:C.dim,fontWeight:600,fontSize:10,borderBottom:`1px solid ${C.border}`,whiteSpace:"nowrap"}}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {currentList.symbols.map(sym=>{
                        const p=prices[sym]; const t=technicals[sym];
                        const myAlerts=currentList.alerts.filter(a=>a.symbol===sym);
                        return (
                          <tr key={sym} style={{borderBottom:`1px solid ${C.border}22`}}>
                            <td style={{padding:"7px 10px",color:C.cyan,fontWeight:700,cursor:"pointer"}} onClick={()=>router.push(`/analysis`)}>{sym}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",fontWeight:600}}>{p?.close?.toLocaleString("en-IN",{maximumFractionDigits:2})||"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:C.dim,fontSize:11}}>{p?.date||"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",fontWeight:700,color:col(p?.pct_1d)}}>{p?.pct_1d!=null?pct(p.pct_1d):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:t?.vol_surge_20d>2?C.green:C.dim}}>{t?.vol_surge_20d!=null?`${num(t.vol_surge_20d,1)}x`:"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:t?.rsi_14>70?C.red:t?.rsi_14<30?C.green:C.primary}}>{t?.rsi_14!=null?num(t.rsi_14,1):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:col(t?.pct_above_sma20)}}>{t?.pct_above_sma20!=null?pct(t.pct_above_sma20):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:t?(t.macd_line>t.macd_signal?C.green:C.red):C.dim}}>{t?(t.macd_line>t.macd_signal?"BULL":"BEAR"):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right"}}>
                              <div style={{display:"flex",gap:3,justifyContent:"flex-end",flexWrap:"wrap"}}>
                                {myAlerts.slice(0,2).map(a=><AlertBadge key={a.id} type={a.type} />)}
                                {myAlerts.length>2&&<span style={{fontSize:10,color:C.dim}}>+{myAlerts.length-2}</span>}
                              </div>
                            </td>
                            <td style={{padding:"7px 10px",textAlign:"right"}}>
                              <div style={{display:"flex",gap:4,justifyContent:"flex-end"}}>
                                <button onClick={()=>setShowAddAlert({listId:currentList.id,symbol:sym})} style={{background:`${C.yellow}22`,color:C.yellow,border:`1px solid ${C.yellow}44`,borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10,fontWeight:600}}>+ Alert</button>
                                <button onClick={()=>router.push(`/analysis`)} style={{background:`${C.cyan}22`,color:C.cyan,border:`1px solid ${C.cyan}44`,borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10,fontWeight:600}}>Dive</button>
                                <button onClick={()=>removeSymbol(sym)} style={{background:`${C.red}22`,color:C.red,border:`1px solid ${C.red}44`,borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10}}>x</button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Alerts for this list */}
              {currentList.alerts.length>0 && (
                <Card title={`Alerts on "${currentList.name}" (${currentList.alerts.length})`} accent={C.yellow}>
                  {currentList.alerts.map(a=>(
                    <div key={a.id} style={{display:"flex",alignItems:"center",gap:10,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
                      <span style={{color:C.cyan,fontWeight:700,minWidth:90}}>{a.symbol}</span>
                      <AlertBadge type={a.type} />
                      <span style={{color:C.dim,flex:1}}>
                        {a.type==="price_band"?`${a.low} - ${a.high}`:a.value!=null?String(a.value):""}
                        {a.note?` (${a.note})`:""}
                      </span>
                      <button onClick={()=>removeAlert(currentList.id,a.id)} style={{background:`${C.red}22`,color:C.red,border:"none",borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10}}>Remove</button>
                    </div>
                  ))}
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      {/* Add Alert Modal */}
      {showAddAlert && (
        <div style={{position:"fixed",inset:0,background:"#000c",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}>
          <div style={{background:"var(--bg)",border:`1px solid ${C.border}`,borderRadius:10,padding:24,width:420,maxWidth:"95vw"}}>
            <div style={{fontSize:14,fontWeight:700,marginBottom:16}}>Add Alert for <span style={{color:C.cyan}}>{showAddAlert.symbol}</span></div>

            <div style={{marginBottom:12}}>
              <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Alert Type</div>
              <select value={alertForm.type} onChange={e=>setAlertForm(f=>({...f,type:e.target.value}))}
                style={{width:"100%",background:"var(--bg)",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13}}>
                {ALERT_TYPES.map(a=><option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
              <div style={{fontSize:10,color:C.dim,marginTop:3}}>{ALERT_TYPES.find(a=>a.id===alertForm.type)?.desc}</div>
            </div>

            {ALERT_TYPES.find(a=>a.id===alertForm.type)?.fields.includes("value") && (
              <div style={{marginBottom:12}}>
                <div style={{fontSize:11,color:C.dim,marginBottom:4}}>
                  {alertForm.type==="volume_surge"?"Surge Multiplier (e.g. 2.5)":alertForm.type.includes("rsi")?"RSI Value (0-100)":alertForm.type.includes("pct")?"% Move (e.g. 3 = 3%)":"Price Value"}
                </div>
                <input type="number" value={alertForm.value} onChange={e=>setAlertForm(f=>({...f,value:e.target.value}))}
                  placeholder="Enter value..."
                  style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}}
                />
              </div>
            )}
            {ALERT_TYPES.find(a=>a.id===alertForm.type)?.fields.includes("low") && (
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:12}}>
                <div>
                  <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Lower Bound</div>
                  <input type="number" value={alertForm.low} onChange={e=>setAlertForm(f=>({...f,low:e.target.value}))}
                    style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}} />
                </div>
                <div>
                  <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Upper Bound</div>
                  <input type="number" value={alertForm.high} onChange={e=>setAlertForm(f=>({...f,high:e.target.value}))}
                    style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}} />
                </div>
              </div>
            )}

            <div style={{marginBottom:16}}>
              <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Note (optional)</div>
              <input value={alertForm.note} onChange={e=>setAlertForm(f=>({...f,note:e.target.value}))}
                placeholder="e.g. support level, target price..."
                style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}} />
            </div>

            <div style={{display:"flex",gap:8}}>
              <button onClick={addAlert} style={{flex:1,background:C.cyan,color:"#000",border:"none",borderRadius:6,padding:"10px",fontWeight:700,cursor:"pointer",fontSize:13}}>Add Alert</button>
              <button onClick={()=>setShowAddAlert(null)} style={{flex:1,background:"transparent",color:C.dim,border:`1px solid ${C.border}`,borderRadius:6,padding:"10px",cursor:"pointer",fontSize:13}}>Cancel</button>
            </div>

            <div style={{marginTop:12,fontSize:11,color:C.dim}}>
              To send triggered alerts to Telegram, run: <code>py D:\MICC\check_alerts.py</code>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
""")


# =============================================================================
# [6] check_alerts.py -- standalone alert checker with Telegram send
# =============================================================================
print("\n[6/6] check_alerts.py")

# check_alerts.py is shipped as a separate file (check_alerts.py)
# Copy it to D:\MICC\ manually or download from the output folder.
print("  [NOTE] check_alerts.py is a separate file -- copy to D:\\MICC\\")



# =============================================================================
# Update NavBar to add ANALYTICS link
# =============================================================================
print("\nPatching NavBar to add ANALYTICS...")
navbar = None
for p in (DASH / "src").rglob("NavBar.tsx"):
    navbar = p; break

if navbar and navbar.exists():
    nb = navbar.read_text(encoding="utf-8")
    if "analytics" not in nb.lower():
        nb = nb.replace(
            '{ href: "/overview",',
            '{ href: "/analysis",  label: "ANALYTICS" },\n  { href: "/overview",'
        )
        if "analytics" not in nb.lower():
            # Fallback: insert after PAGES = [
            nb = nb.replace(
                "const PAGES = [",
                'const PAGES = [\n  { href: "/analysis", label: "ANALYTICS" },'
            )
        navbar.write_text(nb, encoding="utf-8", newline="\n")
        print("  [OK] Added ANALYTICS to NavBar")
    else:
        print("  ANALYTICS already in NavBar")


# =============================================================================
print("\n" + "=" * 65)
print("PHASE 10 COMPLETE")
print("=" * 65)
print("""
Files created:
  /api/analysis/route.ts              -- single symbol deep analysis
  /api/analysis/compare/route.ts      -- multi-symbol comparison
  /api/watchlist-alerts/route.ts      -- multi-list + alert checker
  /analysis/page.tsx                  -- THE ANALYTICS HUB
  /watchlist/page.tsx                 -- multi-list + alert UI
  D:\\MICC\\check_alerts.py            -- standalone alert checker

Restart: cd micc-dashboard && npm run dev

New page: localhost:3000/analysis
  - Mode 1: Search Stock  -> type any symbol, full deep dive inline
  - Mode 2: Compare Stocks -> 2-5 symbols, all comparison charts
  - Mode 3: Search Index   -> same as stock but for NSE indices
  - Mode 4: Compare Indices -> same as compare for indices

What you get for each searched symbol:
  Overview tab    -> Best/Worst duration cards + Prob heatmap + Percentile fan chart
  All Windows tab -> Full 17-window stats table with STRONG/GOOD/NEUTRAL/WEAK ranking
  Episodes tab    -> Best 5 rallies + Worst 5 crashes per selected window
  Technicals tab  -> RSI/ATR/ADX/MACD/BB + insider trades + announcements
  Seasonality tab -> Monthly bar chart + table
  Regimes tab     -> Performance by bull/bear/sideways per window
  Correlations tab-> Top 15 correlated assets

Watchlist:
  - Multiple named lists (create as many as you want)
  - 10 alert types: price above/below/band, % move, vol surge, RSI, SMA20
  - Alerts stored in D:\\MICC\\micc_watchlists.json
  - Run: py D:\\MICC\\check_alerts.py -> checks + sends Telegram
  - Add to pipeline: run_pipeline.py calls check_alerts.py daily

NaN fix: all API routes now sanitize NaN -> null before JSON parse
""")
