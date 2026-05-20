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
