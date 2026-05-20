"""
setup_phase6.py  --  Run from D:\MICC
Wires Agent Zeta into the full MICC stack:
  1. Copies agent_zeta.py to D:\MICC\
  2. Creates dashboard /watchlist page (API route + page.tsx)
  3. Adds /watch and /alert commands to telegram_bot.py
  4. Adds Zeta to run_pipeline.py (Phase 11)
  5. Adds Zeta to micc_engine.py synthesis
"""

import re, shutil
from pathlib import Path

BASE   = Path(r"D:\MICC")
DASH   = BASE / "micc-dashboard"
DA_SRC = Path(__file__).parent  # where this script lives (same dir as agent_zeta.py)

def read(p):  return Path(p).read_text(encoding="utf-8")
def write(p, t): Path(p).write_text(t, encoding="utf-8"); print(f"  [OK] {p}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Copy agent_zeta.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 1: Install agent_zeta.py ===")
src_zeta = DA_SRC / "agent_zeta.py"
dst_zeta = BASE / "agent_zeta.py"
if src_zeta.exists():
    shutil.copy2(src_zeta, dst_zeta)
    print(f"  Copied: {dst_zeta}")
else:
    print(f"  [WARN] {src_zeta} not found. Copy agent_zeta.py to D:\\MICC manually.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Create /api/watchlist/route.ts
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 2: Create /api/watchlist/route.ts ===")

api_dir = DASH / "src" / "app" / "api" / "watchlist"
api_dir.mkdir(parents=True, exist_ok=True)

WATCHLIST_ROUTE = '''\
import { NextResponse } from 'next/server';
import { spawnSync } from 'child_process';
import path from 'path';
import fs from 'fs';

const DA = 'D:/MICC';
const DB = 'D:/marketDB/db/market.db';

function runBridge(sql: string, params: unknown[] = []) {
  const res = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
    input: JSON.stringify({ sql, params }),
    encoding: 'utf-8',
    timeout: 30000,
  });
  if (res.stderr) console.error('[watchlist]', res.stderr.trim());
  try { return JSON.parse(res.stdout || '[]'); }
  catch { return []; }
}

export async function GET() {
  try {
    // Load last Zeta report
    const reportPath = path.join(DA, 'agents', 'zeta', 'last_report.json');
    let report: Record<string, unknown> = {};
    if (fs.existsSync(reportPath)) {
      report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
    }

    // Load watchlist file
    const wlPath = path.join(DA, 'micc_watchlist.json');
    let watchlist: Record<string, unknown> = { symbols: [], alerts: [], notes: {} };
    if (fs.existsSync(wlPath)) {
      watchlist = JSON.parse(fs.readFileSync(wlPath, 'utf-8'));
    }

    // Get latest prices for watchlist symbols
    const syms: string[] = (watchlist.symbols as string[]) || [];
    let prices: Record<string, unknown>[] = [];
    if (syms.length > 0) {
      const placeholders = syms.map(() => '?').join(',');
      prices = runBridge(
        `SELECT s.symbol, s.close, s.date,
                s.high - s.low as day_range,
                (s.close - prev.close) / prev.close * 100 as pct_chg
         FROM stock_data s
         LEFT JOIN stock_data prev
           ON prev.symbol = s.symbol
          AND prev.date = (
            SELECT MAX(date) FROM stock_data
            WHERE symbol = s.symbol AND date < s.date AND close IS NOT NULL
          )
         WHERE s.symbol IN (${placeholders})
           AND s.date = (SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)
           AND s.close IS NOT NULL`,
        syms
      );
    }

    return NextResponse.json({
      date:          report.date   || null,
      generated_at:  report.generated_at || null,
      watchlist:     watchlist,
      prices:        prices,
      triggered_alerts:   report.triggered_alerts   || [],
      breakout_watch:     report.breakout_watch      || [],
      vol_delivery_surge: report.vol_delivery_surge  || [],
      stoploss_watch:     report.stoploss_watch       || [],
      reentry_radar:      report.reentry_radar        || [],
      watchlist_streaks:  report.watchlist_streaks    || [],
      analysis:           report.analysis             || '',
    });
  } catch (e: unknown) {
    console.error('[watchlist] error:', e);
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

// POST: add/remove symbol or alert
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const wlPath = path.join(DA, 'micc_watchlist.json');
    let wl: Record<string, unknown[]> = { symbols: [], alerts: [], notes: [] };
    if (fs.existsSync(wlPath)) {
      wl = JSON.parse(fs.readFileSync(wlPath, 'utf-8'));
    }

    const action = body.action;
    if (action === 'add_symbol') {
      const sym = String(body.symbol).toUpperCase().trim();
      if (sym && !(wl.symbols as string[]).includes(sym)) {
        (wl.symbols as string[]).push(sym);
      }
    } else if (action === 'remove_symbol') {
      const sym = String(body.symbol).toUpperCase().trim();
      wl.symbols = (wl.symbols as string[]).filter(s => s !== sym);
    } else if (action === 'add_alert') {
      (wl.alerts as unknown[]).push(body.alert);
    } else if (action === 'remove_alert') {
      const idx = parseInt(body.index);
      (wl.alerts as unknown[]).splice(idx, 1);
    }

    fs.writeFileSync(wlPath, JSON.stringify(wl, null, 2), 'utf-8');
    return NextResponse.json({ ok: true, watchlist: wl });
  } catch (e: unknown) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
'''

write(api_dir / "route.ts", WATCHLIST_ROUTE)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Create /watchlist/page.tsx
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 3: Create /watchlist/page.tsx ===")

page_dir = DASH / "src" / "app" / "watchlist"
page_dir.mkdir(parents=True, exist_ok=True)

WATCHLIST_PAGE = '''\
"use client";
import React, { useEffect, useState, useCallback } from "react";
import MarkdownText from "@/components/MarkdownText";

interface WatchlistData {
  date: string | null;
  generated_at: string | null;
  watchlist: { symbols: string[]; alerts: AlertDef[]; notes: Record<string, string> };
  prices: PriceRow[];
  triggered_alerts: AlertResult[];
  breakout_watch: BreakoutRow[];
  vol_delivery_surge: SurgeRow[];
  stoploss_watch: SLRow[];
  reentry_radar: ReentryRow[];
  watchlist_streaks: StreakRow[];
  analysis: string;
}
interface PriceRow    { symbol: string; close: number; date: string; pct_chg: number; }
interface AlertDef    { symbol: string; condition: string; level: number; }
interface AlertResult { symbol: string; condition: string; level: number; price: number; pct_from: number; }
interface BreakoutRow { symbol: string; close: number; high_52w: number; pct_from_52h: number; }
interface SurgeRow    { symbol: string; close: number; vol_surge: number; deliv_pct: number; }
interface SLRow       { symbol: string; close: number; ma20: number; pct_vs_ma: number; }
interface ReentryRow  { symbol: string; close: number; pullback_pct: number; near_ma10: boolean; }
interface StreakRow    { symbol: string; streak: number; score: number; tags: string; }

const C = {
  green:  "var(--accent-green)",
  red:    "var(--accent-red)",
  cyan:   "var(--accent-cyan)",
  yellow: "var(--accent-yellow)",
  dim:    "var(--text-tertiary)",
  primary:"var(--text-primary)",
  border: "var(--border)",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--card-bg)", border: `1px solid ${C.border}`,
      borderRadius: 4, padding: "1rem", marginBottom: "1rem" }}>
      <div style={{ color: C.cyan, fontSize: "0.7rem", fontWeight: 700,
        letterSpacing: "0.1em", marginBottom: "0.75rem" }}>{title}</div>
      {children}
    </div>
  );
}

function Tbl({ headers, rows }: { headers: string[]; rows: React.ReactNode[][] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.72rem" }}>
      <thead>
        <tr>{headers.map(h => (
          <th key={h} style={{ textAlign: "left", color: C.dim, padding: "0.2rem 0.5rem",
            borderBottom: `1px solid ${C.border}`, fontWeight: 600, letterSpacing: "0.05em" }}>
            {h}
          </th>
        ))}</tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
            {row.map((cell, j) => (
              <td key={j} style={{ padding: "0.25rem 0.5rem", color: C.primary }}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function pct(v: number) {
  const col = v > 0 ? C.green : v < 0 ? C.red : C.dim;
  return <span style={{ color: col }}>{v > 0 ? "+" : ""}{v?.toFixed(2)}%</span>;
}

function StreakBar({ n }: { n: number }) {
  return (
    <span style={{ display: "inline-flex", gap: 2 }}>
      {Array.from({ length: Math.min(n, 10) }).map((_, i) => (
        <span key={i} style={{ width: 6, height: 12, background: C.cyan,
          opacity: 0.3 + (i / 10) * 0.7, display: "inline-block" }} />
      ))}
      <span style={{ color: C.dim, marginLeft: 4 }}>{n}d</span>
    </span>
  );
}

export default function WatchlistPage() {
  const [data, setData] = useState<WatchlistData | null>(null);
  const [loading, setLoading] = useState(true);
  const [newSym, setNewSym] = useState("");
  const [alertSym, setAlertSym] = useState("");
  const [alertLevel, setAlertLevel] = useState("");
  const [alertCond, setAlertCond] = useState<"above"|"below">("above");
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/watchlist");
      setData(await res.json());
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { reload(); }, [reload]);

  async function postAction(body: Record<string, unknown>) {
    setSaving(true);
    await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await reload();
    setSaving(false);
  }

  async function addSymbol() {
    const sym = newSym.trim().toUpperCase();
    if (!sym) return;
    await postAction({ action: "add_symbol", symbol: sym });
    setNewSym("");
  }

  async function addAlert() {
    const sym = alertSym.trim().toUpperCase();
    const lv = parseFloat(alertLevel);
    if (!sym || isNaN(lv)) return;
    await postAction({ action: "add_alert", alert: { symbol: sym, condition: alertCond, level: lv } });
    setAlertSym(""); setAlertLevel("");
  }

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "60vh", color: C.dim, fontSize: "0.8rem" }}>
      LOADING WATCHLIST...
    </div>
  );

  const d = data!;
  const syms = d.watchlist?.symbols || [];
  const alerts = d.watchlist?.alerts || [];

  const inputStyle: React.CSSProperties = {
    background: "var(--bg-secondary)", border: `1px solid ${C.border}`,
    color: C.primary, padding: "0.3rem 0.6rem", fontSize: "0.72rem",
    fontFamily: "var(--font-mono)", outline: "none", borderRadius: 2,
  };
  const btnStyle: React.CSSProperties = {
    background: "transparent", border: `1px solid ${C.cyan}`,
    color: C.cyan, padding: "0.3rem 0.8rem", fontSize: "0.7rem",
    cursor: saving ? "wait" : "pointer", letterSpacing: "0.05em",
    fontFamily: "var(--font-mono)", borderRadius: 2,
  };

  return (
    <div style={{ padding: "1.5rem", maxWidth: 1400, margin: "0 auto" }}>
      <h1 style={{ fontSize: "1rem", fontWeight: 700, letterSpacing: "0.08em",
        color: C.primary, marginBottom: "0.25rem" }}>
        WATCHLIST INTELLIGENCE
      </h1>
      <div style={{ fontSize: "0.7rem", color: C.dim, marginBottom: "1.5rem" }}>
        {d.date ? `Date: ${d.date}` : "No Zeta report yet"}
        {d.generated_at ? ` | Generated: ${d.generated_at}` : ""}
        {" | Run: py D:\\MICC\\agent_zeta.py --send"}
      </div>

      {/* Triggered Alerts Banner */}
      {d.triggered_alerts.length > 0 && (
        <div style={{ background: "#ff443322", border: `1px solid ${C.red}`,
          padding: "0.75rem 1rem", marginBottom: "1rem", borderRadius: 4 }}>
          <span style={{ color: C.red, fontWeight: 700, fontSize: "0.75rem" }}>
            PRICE ALERTS TRIGGERED ({d.triggered_alerts.length})
          </span>
          {d.triggered_alerts.map((a, i) => (
            <span key={i} style={{ marginLeft: "1rem", fontSize: "0.72rem", color: C.primary }}>
              {a.symbol} {a.condition.toUpperCase()} {a.level} @ <strong>{a.price}</strong>
              <span style={{ color: a.pct_from > 0 ? C.green : C.red }}> ({a.pct_from > 0 ? "+" : ""}{a.pct_from?.toFixed(1)}%)</span>
            </span>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        {/* LEFT COLUMN */}
        <div>
          {/* Watchlist symbols + current prices */}
          <Card title="WATCHLIST">
            {syms.length === 0 ? (
              <div style={{ color: C.dim, fontSize: "0.72rem" }}>No symbols yet. Add below.</div>
            ) : (
              <Tbl
                headers={["SYMBOL", "PRICE", "CHG%", "DATE", ""]}
                rows={syms.map(sym => {
                  const p = d.prices?.find(x => x.symbol === sym);
                  return [
                    <span style={{ color: C.cyan, fontWeight: 600 }}>{sym}</span>,
                    p ? <span>{p.close?.toFixed(2)}</span> : <span style={{ color: C.dim }}>-</span>,
                    p ? pct(p.pct_chg) : <span style={{ color: C.dim }}>-</span>,
                    <span style={{ color: C.dim }}>{p?.date || "-"}</span>,
                    <span
                      style={{ color: C.red, cursor: "pointer", fontSize: "0.65rem" }}
                      onClick={() => postAction({ action: "remove_symbol", symbol: sym })}
                    >remove</span>,
                  ];
                })}
              />
            )}
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
              <input style={inputStyle} placeholder="SYMBOL"
                value={newSym} onChange={e => setNewSym(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === "Enter" && addSymbol()} />
              <button style={btnStyle} onClick={addSymbol}>ADD</button>
            </div>
          </Card>

          {/* Watchlist streaks */}
          {d.watchlist_streaks.length > 0 && (
            <Card title="BETA SCREEN STREAKS">
              <Tbl
                headers={["SYMBOL", "STREAK", "SCORE", "SCREENS"]}
                rows={d.watchlist_streaks.map(s => [
                  <span style={{ color: C.cyan }}>{s.symbol}</span>,
                  <StreakBar n={s.streak} />,
                  <span style={{ color: s.score >= 3 ? C.green : C.dim }}>{s.score}</span>,
                  <span style={{ color: C.dim, fontSize: "0.65rem" }}>{s.tags?.slice(0,30)}</span>,
                ])}
              />
            </Card>
          )}

          {/* Stop-loss watch */}
          {d.stoploss_watch.length > 0 && (
            <Card title="STOP-LOSS WATCH">
              <Tbl
                headers={["SYMBOL", "CLOSE", "MA20", "VS MA20"]}
                rows={d.stoploss_watch.map(s => [
                  <span style={{ color: C.yellow }}>{s.symbol}</span>,
                  <span>{s.close?.toFixed(2)}</span>,
                  <span style={{ color: C.dim }}>{s.ma20?.toFixed(2)}</span>,
                  pct(s.pct_vs_ma),
                ])}
              />
            </Card>
          )}

          {/* Price alerts management */}
          <Card title="PRICE ALERTS">
            {alerts.length === 0 ? (
              <div style={{ color: C.dim, fontSize: "0.72rem", marginBottom: "0.5rem" }}>No alerts set.</div>
            ) : (
              <Tbl
                headers={["SYMBOL", "CONDITION", "LEVEL", ""]}
                rows={alerts.map((a, i) => [
                  <span style={{ color: C.cyan }}>{a.symbol}</span>,
                  <span style={{ color: a.condition === "above" ? C.green : C.red }}>
                    {a.condition.toUpperCase()}
                  </span>,
                  <span>{a.level}</span>,
                  <span
                    style={{ color: C.red, cursor: "pointer", fontSize: "0.65rem" }}
                    onClick={() => postAction({ action: "remove_alert", index: i })}
                  >remove</span>,
                ])}
              />
            )}
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
              <input style={inputStyle} placeholder="SYMBOL" value={alertSym}
                onChange={e => setAlertSym(e.target.value.toUpperCase())} />
              <select style={{ ...inputStyle, cursor: "pointer" }}
                value={alertCond} onChange={e => setAlertCond(e.target.value as "above"|"below")}>
                <option value="above">ABOVE</option>
                <option value="below">BELOW</option>
              </select>
              <input style={{ ...inputStyle, width: 80 }} placeholder="LEVEL"
                value={alertLevel} onChange={e => setAlertLevel(e.target.value)} />
              <button style={btnStyle} onClick={addAlert}>SET ALERT</button>
            </div>
          </Card>
        </div>

        {/* RIGHT COLUMN */}
        <div>
          {/* Breakout Watch */}
          <Card title="BREAKOUT WATCH (within 3% of 52w high)">
            {d.breakout_watch.length === 0
              ? <div style={{ color: C.dim, fontSize: "0.72rem" }}>No breakout setups today.</div>
              : <Tbl
                  headers={["SYMBOL", "CLOSE", "52W HIGH", "DIST%"]}
                  rows={d.breakout_watch.slice(0,12).map(b => [
                    <span style={{ color: C.cyan, fontWeight: 600 }}>{b.symbol}</span>,
                    <span>{b.close?.toFixed(2)}</span>,
                    <span style={{ color: C.dim }}>{b.high_52w?.toFixed(2)}</span>,
                    <span style={{ color: C.yellow }}>-{b.pct_from_52h?.toFixed(2)}%</span>,
                  ])}
                />
            }
          </Card>

          {/* Volume + Delivery Surge */}
          <Card title="VOL + DELIVERY SURGE (2x+ average)">
            {d.vol_delivery_surge.length === 0
              ? <div style={{ color: C.dim, fontSize: "0.72rem" }}>No surges today.</div>
              : <Tbl
                  headers={["SYMBOL", "CLOSE", "VOL SURGE", "DELIV%"]}
                  rows={d.vol_delivery_surge.slice(0,12).map(s => [
                    <span style={{ color: C.green, fontWeight: 600 }}>{s.symbol}</span>,
                    <span>{s.close?.toFixed(2)}</span>,
                    <span style={{ color: s.vol_surge >= 3 ? C.green : C.yellow }}>
                      {s.vol_surge?.toFixed(1)}x
                    </span>,
                    <span style={{ color: s.deliv_pct >= 50 ? C.green : C.dim }}>
                      {s.deliv_pct?.toFixed(1)}%
                    </span>,
                  ])}
                />
            }
          </Card>

          {/* Re-entry Radar */}
          <Card title="RE-ENTRY RADAR (prev hot, 5-20% pullback)">
            {d.reentry_radar.length === 0
              ? <div style={{ color: C.dim, fontSize: "0.72rem" }}>No re-entry setups.</div>
              : <Tbl
                  headers={["SYMBOL", "CLOSE", "PULLBACK", "NEAR MA10"]}
                  rows={d.reentry_radar.slice(0,12).map(r => [
                    <span style={{ color: C.yellow, fontWeight: 600 }}>{r.symbol}</span>,
                    <span>{r.close?.toFixed(2)}</span>,
                    pct(-r.pullback_pct),
                    r.near_ma10
                      ? <span style={{ color: C.green }}>YES</span>
                      : <span style={{ color: C.dim }}>no</span>,
                  ])}
                />
            }
          </Card>

          {/* Analysis */}
          <Card title="ZETA INTELLIGENCE">
            {d.analysis
              ? <MarkdownText text={d.analysis} maxHeight={400} />
              : <div style={{ color: C.dim, fontSize: "0.72rem" }}>
                  Run py D:\MICC\agent_zeta.py to generate analysis.
                </div>
            }
          </Card>
        </div>
      </div>
    </div>
  );
}
'''

write(page_dir / "page.tsx", WATCHLIST_PAGE)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Add WATCHLIST link to NavBar.tsx
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 4: Add WATCHLIST to NavBar ===")

navbar = None
for p in DASH.rglob("NavBar.tsx"):
    navbar = p; break

if not navbar:
    print("  [WARN] NavBar.tsx not found")
else:
    src = read(navbar)
    OLD_NAV = "{ href: '/mf', label: 'MF NAV' },"
    NEW_NAV = "{ href: '/mf', label: 'MF NAV' },\n  { href: '/watchlist', label: 'WATCHLIST' },"
    if OLD_NAV in src and "watchlist" not in src:
        src = src.replace(OLD_NAV, NEW_NAV)
        write(navbar, src)
        print("  Added WATCHLIST nav link")
    elif "watchlist" in src.lower():
        print("  WATCHLIST already in NavBar")
    else:
        print("  [WARN] Could not find nav items pattern. Add manually.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Add /watch command to telegram_bot.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 5: Add /watch to telegram_bot.py ===")

bot = BASE / "telegram_bot.py"
if not bot.exists():
    print(f"  [WARN] {bot} not found")
else:
    src = read(bot)

    WATCH_HANDLER = '''

async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show watchlist status from last Zeta report."""
    zeta_path = Path("agents/zeta/last_report.json")
    if not zeta_path.exists():
        await update.message.reply_text(
            "No Zeta report found. Run: py agent_zeta.py --send"
        )
        return

    try:
        report = json.loads(zeta_path.read_text(encoding="utf-8"))
    except Exception as e:
        await update.message.reply_text(f"Error loading Zeta report: {e}")
        return

    d = report.get("date", "?")
    syms = report.get("watchlist_symbols", [])
    breakouts = report.get("breakout_watch", [])[:5]
    surges = report.get("vol_delivery_surge", [])[:5]
    alerts = report.get("triggered_alerts", [])
    reentries = report.get("reentry_radar", [])[:5]
    streaks = report.get("watchlist_streaks", [])[:8]

    lines = [f"*WATCHLIST INTEL -- {d}*", ""]

    if alerts:
        lines.append("*ALERTS TRIGGERED:*")
        for a in alerts:
            lines.append(f"  `{a['symbol']}` {a['condition'].upper()} {a['level']} @ `{a['price']}`")
        lines.append("")

    if syms:
        lines.append(f"*WATCHING:* {' | '.join(f'`{s}`' for s in syms[:12])}")
        lines.append("")

    if streaks:
        lines.append("*STREAKS:*")
        for s in streaks:
            bar = "=" * min(s["streak"], 8)
            lines.append(f"  `{s['symbol']}` [{bar}] {s['streak']}d")
        lines.append("")

    if breakouts:
        lines.append("*NEAR 52w HIGH:*")
        for b in breakouts:
            lines.append(f"  `{b['symbol']}` @ {b['close']} (-{b['pct_from_52h']}% from 52wH)")
        lines.append("")

    if surges:
        lines.append("*VOL SURGES:*")
        for s in surges:
            lines.append(f"  `{s['symbol']}` {s['vol_surge']}x vol | {s['deliv_pct']}% deliv")
        lines.append("")

    if reentries:
        lines.append("*RE-ENTRY:*")
        for r in reentries:
            near = " [near MA10]" if r.get("near_ma10") else ""
            lines.append(f"  `{r['symbol']}` -{r['pullback_pct']}%{near}")

    text = "\\n".join(lines)
    await update.message.reply_text(text[:4000], parse_mode="Markdown")

'''

    # Insert before the main app setup
    INSERT_BEFORE = "def main():"
    if "cmd_watch" not in src and INSERT_BEFORE in src:
        src = src.replace(INSERT_BEFORE, WATCH_HANDLER + INSERT_BEFORE)

        # Also register the handler — find where other handlers are added
        OLD_HANDLER_REG = 'app.add_handler(CommandHandler("status"'
        NEW_HANDLER_REG = ('app.add_handler(CommandHandler("watch", cmd_watch))\n    '
                           + OLD_HANDLER_REG)
        if OLD_HANDLER_REG in src and "watch" not in src.split(OLD_HANDLER_REG)[0][-200:]:
            src = src.replace(OLD_HANDLER_REG, NEW_HANDLER_REG)

        write(bot, src)
        print("  Added /watch command to telegram_bot.py")
    elif "cmd_watch" in src:
        print("  /watch already exists in telegram_bot.py")
    else:
        print("  [WARN] Could not find insertion point. Add /watch manually.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Add Zeta to run_pipeline.py as Phase 11
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 6: Add Zeta to run_pipeline.py ===")

pipeline = BASE / "data_pipeline" / "run_pipeline.py"
if not pipeline.exists():
    print(f"  [WARN] {pipeline} not found")
else:
    src = read(pipeline)
    # Find where epsilon is called or engine is called
    OLD_PHASE = 'py micc_engine.py' if 'micc_engine.py' not in src else None

    # Find the last phase call pattern
    ZETA_PHASE = '''
    # ── Phase 11: Agent Zeta (Watchlist Intelligence) ──────────────────────
    if args.with_engine:
        print("\\n[Phase 11] Agent Zeta...")
        import subprocess
        result = subprocess.run(
            ["py", str(Path(DA) / "agent_zeta.py"), "--send"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            print(f"  [WARN] Zeta failed: {result.stderr[:200]}")
        else:
            print("  Zeta: OK")
'''

    # Insert before the final health check or at end of with_engine block
    INSERT_BEFORE_PATTERNS = [
        "# ── Health check",
        "print(\"\\n\" + \"=\"*60)",
        "print(f\"\\n[PIPELINE COMPLETE]",
    ]
    inserted = False
    for pat in INSERT_BEFORE_PATTERNS:
        if pat in src and "agent_zeta" not in src:
            src = src.replace(pat, ZETA_PHASE + "\n    " + pat, 1)
            inserted = True
            break

    if inserted:
        write(pipeline, src)
        print("  Added Zeta as Phase 11 in run_pipeline.py")
    elif "agent_zeta" in src:
        print("  Zeta already in pipeline")
    else:
        print("  [WARN] Could not find insertion point. Add Zeta manually to run_pipeline.py")
        print("  After the engine call, add:  subprocess.run(['py', 'D:/MICC/agent_zeta.py', '--send'])")


print("\n" + "="*60)
print("PHASE 6 SETUP COMPLETE")
print("="*60)
print()
print("Files created / modified:")
print("  D:\\MICC\\agent_zeta.py               -- Agent Zeta")
print("  micc-dashboard/src/app/watchlist/page.tsx       -- Dashboard page")
print("  micc-dashboard/src/app/api/watchlist/route.ts   -- API endpoint")
print("  D:\\MICC\\micc-dashboard NavBar.tsx    -- WATCHLIST nav link added")
print("  D:\\MICC\\telegram_bot.py             -- /watch command added")
print("  D:\\MICC\\data_pipeline\\run_pipeline.py -- Phase 11 added")
print()
print("Test steps:")
print("  1. py D:\\MICC\\agent_zeta.py          -- dry run")
print("  2. py D:\\MICC\\agent_zeta.py --send   -- with Telegram")
print("  3. Restart Next.js -> visit localhost:3000/watchlist")
print("  4. Add symbols via the watchlist UI or edit micc_watchlist.json directly")
print()
print("Add symbols to watchlist (example):")
print('  Edit D:\\MICC\\micc_watchlist.json:')
print('  { "symbols": ["RELIANCE","INFY","HDFC"], "alerts": [], "notes": {} }')
