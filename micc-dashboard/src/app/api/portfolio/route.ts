import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB  = "D:/marketDB/db/market.db";
const PY  = "C:/Users/marka/AppData/Local/Programs/Python/Python314/python.exe";

function qdb(sql: string, params: any[] = []): any[] {
  const script = [
    "import sqlite3, json, sys",
    "conn = sqlite3.connect(r'" + DB + "', timeout=15)",
    "conn.row_factory = sqlite3.Row",
    "try:",
    "    rows = conn.execute(sys.argv[1], json.loads(sys.argv[2])).fetchall()",
    "    print(json.dumps([dict(r) for r in rows], default=str))",
    "except Exception as e:",
    "    print('[]')",
    "conn.close()",
  ].join("\n");
  const r = spawnSync(PY, ["-c", script, sql, JSON.stringify(params)],
    { encoding: "utf-8", timeout: 10000 });
  try { return JSON.parse(r.stdout || "[]"); } catch { return []; }
}

export async function GET() {
  try {
    const tables = qdb(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='my_portfolio'", []
    );
    if (!tables.length) {
      return NextResponse.json({ ok: true, positions: [], summary: null,
        message: "my_portfolio table not found." });
    }

    const positions = qdb(
      "SELECT id, symbol, entry_date, entry_price, quantity, position_size, " +
      "atr_at_entry, stop_loss, target_1, target_2, risk_per_trade, " +
      "status, exit_date, exit_price, pnl, pnl_pct, notes, added_at " +
      "FROM my_portfolio ORDER BY added_at DESC",
      []
    );

    // Enrich OPEN positions with live price from stock_data
    const openSyms: string[] = [
      ...new Set(
        positions.filter((p: any) => p.status === "OPEN" || !p.status)
                 .map((p: any) => p.symbol)
      )
    ] as string[];

    const livePrice: Record<string, number> = {};
    if (openSyms.length > 0) {
      const ph = openSyms.map(() => "?").join(",");
      const pr = qdb(
        "SELECT symbol, close FROM stock_data " +
        "WHERE symbol IN (" + ph + ") " +
        "AND date = (SELECT MAX(date) FROM stock_data s2 WHERE s2.symbol = stock_data.symbol)",
        openSyms
      );
      pr.forEach((r: any) => { livePrice[r.symbol] = parseFloat(r.close); });
    }

    const enriched = positions.map((p: any) => {
      const isOpen = p.status === "OPEN" || !p.exit_price;
      const cur    = isOpen ? (livePrice[p.symbol] ?? null) : parseFloat(p.exit_price);
      const ep     = parseFloat(p.entry_price) || 0;
      const qty    = parseFloat(p.quantity)    || 0;

      // Use stored pnl if closed, else compute live
      const live_pnl_pct = cur && ep ? ((cur - ep) / ep * 100) : null;
      const live_pnl_rs  = cur && ep && qty ? ((cur - ep) * qty) : null;

      const display_pnl_pct = isOpen ? live_pnl_pct : parseFloat(p.pnl_pct);
      const display_pnl_rs  = isOpen ? live_pnl_rs  : parseFloat(p.pnl);

      const at_stop    = cur && p.stop_loss ? cur <= parseFloat(p.stop_loss)  : false;
      const at_target1 = cur && p.target_1  ? cur >= parseFloat(p.target_1)   : false;
      const at_target2 = cur && p.target_2  ? cur >= parseFloat(p.target_2)   : false;

      return {
        ...p,
        current_price:   cur,
        live_pnl_pct:    live_pnl_pct    != null ? parseFloat(live_pnl_pct.toFixed(2))    : null,
        live_pnl_rs:     live_pnl_rs     != null ? parseFloat(live_pnl_rs.toFixed(0))     : null,
        display_pnl_pct: display_pnl_pct != null ? parseFloat(display_pnl_pct.toFixed(2)) : null,
        display_pnl_rs:  display_pnl_rs  != null ? parseFloat(display_pnl_rs.toFixed(0))  : null,
        at_stop, at_target1, at_target2,
      };
    });

    const open     = enriched.filter((p: any) => p.status === "OPEN" || !p.exit_price);
    const closed   = enriched.filter((p: any) => p.exit_price);
    const total_live_pnl = open.reduce((s: number, p: any) => s + (p.live_pnl_rs || 0), 0);
    const total_closed_pnl = closed.reduce((s: number, p: any) => s + (parseFloat(p.pnl) || 0), 0);
    const winners  = open.filter((p: any) => (p.live_pnl_pct || 0) > 0).length;

    return NextResponse.json({
      ok: true,
      positions: enriched,
      summary: {
        n_open:           open.length,
        n_closed:         closed.length,
        live_pnl_rs:      parseFloat(total_live_pnl.toFixed(0)),
        closed_pnl_rs:    parseFloat(total_closed_pnl.toFixed(0)),
        open_winners:     winners,
        open_losers:      open.length - winners,
        win_rate_pct:     open.length > 0
                            ? parseFloat((100 * winners / open.length).toFixed(1)) : 0,
      }
    });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 });
  }
}
