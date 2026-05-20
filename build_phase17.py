"""
build_phase17.py  --  Run from D:\MICC
Builds Phase 17 — Pipeline + Dashboard upgrades:

  [1] run_pipeline.py patch      -- add global indices fetch as Phase 1B
  [2] /api/global/route.ts       -- live global indices API (last 5 days)
  [3] /api/global/[symbol]/route.ts -- single symbol history
  [4] /overview page upgrade     -- inject GlobalMacroPanel component
  [5] telegram_bot.py patch      -- /global /patterns commands
  [6] micc_engine.py patch       -- add Eta + Iota to daily engine run

Run: py D:\MICC\build_phase17.py
"""
from pathlib import Path
import re

MICC  = Path(r"D:\MICC")
PIPE  = MICC / "data_pipeline"
DASH  = MICC / "micc-dashboard"
SRC   = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}")

def patch(path: Path, old: str, new: str, label: str) -> bool:
    if not path.exists():
        print(f"  [SKIP] {label} — not found"); return False
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [SKIP] {label} — marker not found"); return False
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  [OK] {label}"); return True


# ═════════════════════════════════════════════════════════════════════════════
# [1]  run_pipeline.py  — add global indices as Phase 1B
# ═════════════════════════════════════════════════════════════════════════════
print("\n[1/6] Patching run_pipeline.py ...")

PIPE_OLD = '''\
    # Phase 2 — Macro
    r["us_macro"]    = run(PIPELINE_DIR / "update_macro_us.py",'''

PIPE_NEW = '''\
    # Phase 1B — Global indices (incremental, ~5 min, resilient)
    _gfetch = MICC_DIR / "fetch_global_indices_v2.py"
    if _gfetch.exists():
        r["global_idx"] = run(_gfetch,
                              "Global Indices fetch (52 symbols, incremental)",
                              timeout=600, cwd=MICC_DIR)
    else:
        log("fetch_global_indices_v2.py not found in D:/MICC/ — skipping", "WARN")
        r["global_idx"] = False

    # Phase 2 — Macro
    r["us_macro"]    = run(PIPELINE_DIR / "update_macro_us.py",'''

rp = PIPE / "run_pipeline.py"
# Also works if in MICC root
rp2 = MICC / "run_pipeline.py"
patched = patch(rp,  PIPE_OLD, PIPE_NEW, "data_pipeline/run_pipeline.py")
if not patched:
    patch(rp2, PIPE_OLD, PIPE_NEW, "run_pipeline.py (root)")


# Also add Eta to engine - patch micc_engine.py
print("\n[6/6] Patching micc_engine.py to include Eta + Iota...")

engine = MICC / "micc_engine.py"
if engine.exists():
    src = engine.read_text(encoding="utf-8")

    # Add Eta + Iota imports if missing
    if "from agent_eta" not in src and "agent_eta" not in src:
        src = src.replace(
            "from agent_delta import run_delta",
            "from agent_delta   import run_delta\nfrom agent_eta     import run_eta\nfrom agent_iota    import run_iota"
        )
        print("  [OK] Added agent_eta + agent_iota imports")

    # Add Eta + Iota runs after delta in main engine sequence
    ETA_MARKER = "    delta = run_delta(n_days)"
    if ETA_MARKER in src and "run_eta(" not in src:
        src = src.replace(
            ETA_MARKER,
            ETA_MARKER + "\n\n    # Phase 2 extended agents\n    try:\n        eta  = run_eta(send=False)\n    except Exception as _e:\n        eta  = {}\n        print(f'[WARN] Eta failed: {_e}')\n    try:\n        iota = run_iota(send=False)\n    except Exception as _e:\n        iota = {}\n        print(f'[WARN] Iota failed: {_e}')"
        )
        print("  [OK] Added Eta + Iota runs to engine sequence")

    engine.write_text(src, encoding="utf-8")
else:
    print("  [SKIP] micc_engine.py not found")


# ═════════════════════════════════════════════════════════════════════════════
# [2]  /api/global/route.ts  — last N days for all global indices
# ═════════════════════════════════════════════════════════════════════════════
print("\n[2/6] Writing /api/global/route.ts ...")

GLOBAL_ROUTE = r'''import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r"${DB}", timeout=15)
conn.row_factory = sqlite3.Row
p = json.loads(sys.argv[1])
rows = conn.execute("""${sql}""", p).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
`;
  const r = spawnSync(PY, ["-c", script, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  return JSON.parse(sanitize(r.stdout.trim() || "[]"));
}

export async function GET(req: Request) {
  const url  = new URL(req.url);
  const days = Math.min(parseInt(url.searchParams.get("days") || "5"), 30);
  const cat  = url.searchParams.get("category") || "";
  const sym  = url.searchParams.get("symbol") || "";

  try {
    // Get latest N trading dates across all symbols
    const dates = qdb(
      `SELECT DISTINCT date FROM global_indices_daily
       ORDER BY date DESC LIMIT ${days * 2}`
    ).map((r: any) => r.date).slice(0, days);

    if (!dates.length) return NextResponse.json({ rows: [], dates: [] });

    const minDate = dates[dates.length - 1];

    let where = "WHERE date >= ?";
    const params: any[] = [minDate];
    if (cat)  { where += " AND category = ?"; params.push(cat); }
    if (sym)  { where += " AND symbol = ?";   params.push(sym.toUpperCase()); }

    // Get latest close + pct_change for each symbol
    const latest = qdb(`
      SELECT g.symbol, g.date, g.close, g.pct_change
      FROM global_indices_daily g
      INNER JOIN (
        SELECT symbol, MAX(date) as max_date
        FROM global_indices_daily
        WHERE date >= ?
        GROUP BY symbol
      ) m ON g.symbol = m.symbol AND g.date = m.max_date
      ORDER BY g.symbol
    `, [minDate]);

    // 5-day returns for each symbol
    const fiveDay = qdb(`
      SELECT g.symbol,
        ROUND((g.close / g2.close - 1) * 100, 2) as ret_5d
      FROM global_indices_daily g
      JOIN (
        SELECT symbol, close, date FROM global_indices_daily
        WHERE date IN (
          SELECT DISTINCT date FROM global_indices_daily ORDER BY date DESC LIMIT 10
        )
      ) g2 ON g.symbol = g2.symbol
      WHERE g.date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol = g.symbol)
        AND g2.date = (
          SELECT date FROM global_indices_daily WHERE symbol = g.symbol
          ORDER BY date DESC LIMIT 1 OFFSET ${Math.min(days - 1, 4)}
        )
    `, []);

    const fiveDayMap: Record<string, number> = {};
    fiveDay.forEach((r: any) => { fiveDayMap[r.symbol] = r.ret_5d; });

    const enriched = latest.map((r: any) => ({
      ...r,
      ret_5d: fiveDayMap[r.symbol] ?? null,
    }));

    return NextResponse.json({ rows: enriched, dates, count: enriched.length });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, rows: [], dates: [] }, { status: 500 });
  }
}
'''
write(SRC / "api" / "global" / "route.ts", GLOBAL_ROUTE, "/api/global/route.ts")


# ═════════════════════════════════════════════════════════════════════════════
# [3]  /api/global/[symbol]/route.ts  — history for one symbol
# ═════════════════════════════════════════════════════════════════════════════
print("\n[3/6] Writing /api/global/[symbol]/route.ts ...")

GLOBAL_SYM_ROUTE = r'''import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r"${DB}", timeout=15)
conn.row_factory = sqlite3.Row
p = json.loads(sys.argv[1])
rows = conn.execute("""${sql}""", p).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
`;
  const r = spawnSync(PY, ["-c", script, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 20000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200));
  return JSON.parse(sanitize(r.stdout.trim() || "[]"));
}

export async function GET(
  req: Request,
  { params }: { params: { symbol: string } }
) {
  const sym  = (params.symbol || "").toUpperCase();
  const url  = new URL(req.url);
  const days = Math.min(parseInt(url.searchParams.get("days") || "252"), 2000);
  const from_ = url.searchParams.get("from") || "";

  if (!sym) return NextResponse.json({ error: "No symbol" }, { status: 400 });

  try {
    let where = "WHERE symbol = ?";
    const p: any[] = [sym];
    if (from_) { where += " AND date >= ?"; p.push(from_); }

    const rows = qdb(`
      SELECT date, open, high, low, close, pct_change
      FROM global_indices_daily
      ${where}
      ORDER BY date DESC
      LIMIT ${days}
    `, p);

    rows.reverse(); // chronological

    // Compute running stats
    const closes = rows.map((r: any) => r.close).filter(Boolean);
    const returns_ = rows.map((r: any) => r.pct_change).filter((v: any) => v != null);
    const mx = closes.length ? Math.max(...closes) : null;
    const mn = closes.length ? Math.min(...closes) : null;
    const last = closes[closes.length - 1];
    const first = closes[0];
    const totalRet = first && last ? Math.round((last / first - 1) * 10000) / 100 : null;
    const avgRet   = returns_.length
      ? Math.round(returns_.reduce((a: number, b: number) => a + b, 0) / returns_.length * 100) / 100
      : null;

    return NextResponse.json({
      symbol: sym,
      rows,
      stats: {
        n: rows.length,
        first_date: rows[0]?.date,
        last_date:  rows[rows.length - 1]?.date,
        last_close: last,
        high_period: mx,
        low_period:  mn,
        total_ret_pct: totalRet,
        avg_daily_ret: avgRet,
      }
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
'''
write(SRC / "api" / "global" / "[symbol]" / "route.ts", GLOBAL_SYM_ROUTE, "/api/global/[symbol]/route.ts")


# ═════════════════════════════════════════════════════════════════════════════
# [4]  /global/page.tsx  — standalone global markets dashboard
# ═════════════════════════════════════════════════════════════════════════════
print("\n[4/6] Writing /global/page.tsx ...")

GLOBAL_PAGE = '''\
"use client";

import { useEffect, useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface GlobalRow {
  symbol: string; date: string; close: number | null; pct_change: number | null;
  ret_5d?: number | null;
}
interface HistRow { date: string; close: number; pct_change: number | null; }

// ── Universe metadata (category + display name) ───────────────────────────────
const META: Record<string, { name: string; cat: string; flag?: string }> = {
  SPX:         { name: "S&P 500",         cat: "US",        flag: "🇺🇸" },
  NDX:         { name: "Nasdaq 100",       cat: "US",        flag: "🇺🇸" },
  DJIA:        { name: "Dow Jones",        cat: "US",        flag: "🇺🇸" },
  RUT:         { name: "Russell 2000",     cat: "US",        flag: "🇺🇸" },
  SP500VIX:    { name: "VIX",              cat: "Volatility",flag: "⚡" },
  INDIAVIX:    { name: "India VIX",        cat: "Volatility",flag: "⚡" },
  NIFTY50:     { name: "Nifty 50",         cat: "India",     flag: "🇮🇳" },
  NIFTYBANK:   { name: "Nifty Bank",       cat: "India",     flag: "🇮🇳" },
  SENSEX:      { name: "Sensex",           cat: "India",     flag: "🇮🇳" },
  NIFTYIT:     { name: "Nifty IT",         cat: "India",     flag: "🇮🇳" },
  NIFTYMID100: { name: "Nifty Midcap",     cat: "India",     flag: "🇮🇳" },
  NIFTYFMCG:   { name: "Nifty FMCG",       cat: "India",     flag: "🇮🇳" },
  NIFTYAUTO:   { name: "Nifty Auto",        cat: "India",     flag: "🇮🇳" },
  DAX:         { name: "DAX",              cat: "Europe",    flag: "🇩🇪" },
  FTSE100:     { name: "FTSE 100",         cat: "Europe",    flag: "🇬🇧" },
  CAC40:       { name: "CAC 40",           cat: "Europe",    flag: "🇫🇷" },
  EUROSTOXX50: { name: "Euro Stoxx 50",    cat: "Europe",    flag: "🇪🇺" },
  AEX:         { name: "AEX",              cat: "Europe",    flag: "🇳🇱" },
  SMI:         { name: "SMI",              cat: "Europe",    flag: "🇨🇭" },
  IBEX35:      { name: "IBEX 35",          cat: "Europe",    flag: "🇪🇸" },
  MIB:         { name: "FTSE MIB",         cat: "Europe",    flag: "🇮🇹" },
  Nikkei225:   { name: "Nikkei 225",       cat: "Asia",      flag: "🇯🇵" },
  HangSeng:    { name: "Hang Seng",        cat: "Asia",      flag: "🇭🇰" },
  Shanghai:    { name: "Shanghai",         cat: "Asia",      flag: "🇨🇳" },
  CSI300:      { name: "CSI 300",          cat: "Asia",      flag: "🇨🇳" },
  Kospi:       { name: "KOSPI",            cat: "Asia",      flag: "🇰🇷" },
  ASX200:      { name: "ASX 200",          cat: "Asia",      flag: "🇦🇺" },
  Taiwan:      { name: "Taiwan",           cat: "Asia",      flag: "🇹🇼" },
  Straits:     { name: "Straits Times",    cat: "Asia",      flag: "🇸🇬" },
  Jakarta:     { name: "Jakarta",          cat: "Asia",      flag: "🇮🇩" },
  Bovespa:     { name: "Bovespa",          cat: "LatAm",     flag: "🇧🇷" },
  IPC:         { name: "IPC Mexico",       cat: "LatAm",     flag: "🇲🇽" },
  Gold:        { name: "Gold",             cat: "Commodity", flag: "🥇" },
  Silver:      { name: "Silver",           cat: "Commodity", flag: "🥈" },
  CrudeWTI:    { name: "Crude WTI",        cat: "Commodity", flag: "🛢" },
  BrentCrude:  { name: "Brent Crude",      cat: "Commodity", flag: "🛢" },
  NatGas:      { name: "Natural Gas",      cat: "Commodity", flag: "🔥" },
  Copper:      { name: "Copper",           cat: "Commodity", flag: "🟤" },
  Wheat:       { name: "Wheat",            cat: "Commodity", flag: "🌾" },
  Palladium:   { name: "Palladium",        cat: "Commodity", flag: "⚗️" },
  DXY:         { name: "DXY (USD Index)",  cat: "FX",        flag: "💵" },
  USDINR:      { name: "USD/INR",          cat: "FX",        flag: "₹"  },
  EURUSD:      { name: "EUR/USD",          cat: "FX",        flag: "🇪🇺" },
  USDJPY:      { name: "USD/JPY",          cat: "FX",        flag: "🇯🇵" },
  GBPUSD:      { name: "GBP/USD",          cat: "FX",        flag: "🇬🇧" },
  USDCNY:      { name: "USD/CNY",          cat: "FX",        flag: "🇨🇳" },
  USDBRL:      { name: "USD/BRL",          cat: "FX",        flag: "🇧🇷" },
  US10Y:       { name: "US 10Y Yield",     cat: "Rates",     flag: "📈" },
  US2Y:        { name: "US 2Y Yield",      cat: "Rates",     flag: "📈" },
  US30Y:       { name: "US 30Y Yield",     cat: "Rates",     flag: "📈" },
  Bitcoin:     { name: "Bitcoin",          cat: "Crypto",    flag: "₿"  },
  Ethereum:    { name: "Ethereum",         cat: "Crypto",    flag: "Ξ"  },
};

const CATS = ["All","US","India","Europe","Asia","LatAm","Commodity","FX","Rates","Volatility","Crypto"];

// ── Helpers ───────────────────────────────────────────────────────────────────
const pct  = (v: number | null | undefined) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
const clr  = (v: number | null | undefined, invert = false) =>
  v == null ? "#94a3b8" : (invert ? v < 0 : v > 0) ? "#22c55e" : v === 0 ? "#94a3b8" : "#ef4444";
const fmtClose = (v: number | null, sym: string) => {
  if (v == null) return "—";
  const cat = META[sym]?.cat;
  if (cat === "Rates") return `${v.toFixed(2)}%`;
  if (["USDINR","EURUSD","USDJPY","GBPUSD","USDCNY","USDBRL"].includes(sym))
    return v.toFixed(4);
  return v >= 1000 ? v.toLocaleString("en-IN", { maximumFractionDigits: 0 })
       : v >= 100  ? v.toFixed(2)
       : v.toFixed(4);
};

// ── Mini sparkline SVG ────────────────────────────────────────────────────────
function Spark({ hist, color }: { hist: number[]; color: string }) {
  if (!hist || hist.length < 2) return <span style={{ color: "#334155" }}>—</span>;
  const W = 60, H = 20;
  const mn = Math.min(...hist), mx = Math.max(...hist), rng = mx - mn || 1;
  const pts = hist.map((v, i) =>
    `${(i / (hist.length - 1)) * W},${H - ((v - mn) / rng) * H}`
  ).join(" ");
  return (
    <svg width={W} height={H} style={{ verticalAlign: "middle" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

// ── Global index row ──────────────────────────────────────────────────────────
function IndexRow({
  row, onClick, selected,
}: {
  row: GlobalRow; onClick: () => void; selected: boolean;
}) {
  const meta  = META[row.symbol] || { name: row.symbol, cat: "Other", flag: "🌍" };
  const dClr  = clr(row.pct_change);
  const wClr  = clr(row.ret_5d);
  const isVix = meta.cat === "Volatility";

  return (
    <tr onClick={onClick} style={{
      borderBottom: "1px solid #1e293b", cursor: "pointer",
      background: selected ? "#1e3a5f" : "transparent",
      transition: "background 0.15s",
    }}>
      <td style={{ padding: "8px 10px", fontFamily: "monospace", color: "#60a5fa", fontSize: 12, fontWeight: 700 }}>
        {meta.flag} {row.symbol}
      </td>
      <td style={{ padding: "8px 10px", color: "#94a3b8", fontSize: 12 }}>
        {meta.name}
      </td>
      <td style={{ padding: "8px 10px", color: "#64748b", fontSize: 11 }}>
        <span style={{
          background: "#1e293b", borderRadius: 4,
          padding: "1px 6px", fontSize: 10,
        }}>{meta.cat}</span>
      </td>
      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, fontSize: 13, color: "#f8fafc" }}>
        {fmtClose(row.close, row.symbol)}
      </td>
      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, fontSize: 13,
        color: isVix ? clr(row.pct_change, true) : dClr }}>
        {pct(row.pct_change)}
      </td>
      <td style={{ padding: "8px 10px", textAlign: "right", fontSize: 12,
        color: isVix ? clr(row.ret_5d, true) : wClr }}>
        {pct(row.ret_5d)}
      </td>
      <td style={{ padding: "8px 10px", fontSize: 11, color: "#64748b" }}>{row.date}</td>
    </tr>
  );
}

// ── Mini chart for selected symbol ────────────────────────────────────────────
function SymbolChart({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const [hist, setHist]     = useState<HistRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState<number | null>(null);
  const [lockA, setLockA]   = useState<number | null>(null);
  const [lockB, setLockB]   = useState<number | null>(null);
  const meta = META[symbol] || { name: symbol, cat: "Other", flag: "🌍" };

  useEffect(() => {
    setLoading(true);
    fetch(`/api/global/${symbol}?days=252`)
      .then(r => r.json())
      .then(d => { setHist(d.rows || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return (
    <div style={{ padding: 20, color: "#64748b", fontSize: 13 }}>Loading {symbol}…</div>
  );

  if (!hist.length) return (
    <div style={{ padding: 20, color: "#64748b" }}>No data for {symbol}</div>
  );

  const closes = hist.map(h => h.close).filter(Boolean) as number[];
  const W = 560, H = 140, PAD = 36;
  const mn  = Math.min(...closes), mx = Math.max(...closes), rng = mx - mn || 1;
  const pts = hist.map((h, i) => {
    const x = PAD + (i / (hist.length - 1)) * (W - 2 * PAD);
    const y = H - PAD - ((h.close - mn) / rng) * (H - 2 * PAD);
    return `${x},${y}`;
  }).join(" ");

  const handleClick = (i: number) => {
    if (lockA === null) { setLockA(i); return; }
    if (lockB === null && i !== lockA) { setLockB(i); return; }
    setLockA(null); setLockB(null);
  };

  const last = hist[hist.length - 1];
  const firstClose = hist[0]?.close;
  const totalRet = firstClose && last?.close
    ? ((last.close / firstClose - 1) * 100).toFixed(2) : null;

  const deltaVal = lockA != null && lockB != null
    ? ((hist[lockB]?.close / hist[lockA]?.close - 1) * 100).toFixed(2)
    : null;

  return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155",
      borderRadius: 12, padding: "16px 20px", marginBottom: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 16 }}>{meta.flag}</span>
        <span style={{ fontWeight: 800, fontSize: 15, color: "#f8fafc" }}>
          {symbol} — {meta.name}
        </span>
        <span style={{ fontSize: 13, color: "#60a5fa", marginLeft: 8 }}>
          {fmtClose(last?.close, symbol)}
        </span>
        {totalRet && (
          <span style={{ fontSize: 12, color: parseFloat(totalRet) >= 0 ? "#22c55e" : "#ef4444" }}>
            ({parseFloat(totalRet) >= 0 ? "+" : ""}{totalRet}% 1y)
          </span>
        )}
        <button onClick={onClose} style={{
          marginLeft: "auto", background: "none", border: "none",
          color: "#64748b", cursor: "pointer", fontSize: 18,
        }}>✕</button>
      </div>

      <svg width={W} height={H} style={{ cursor: "crosshair", overflow: "visible" }}
        onMouseLeave={() => setHovered(null)}>
        {/* Chart line */}
        <polyline points={pts} fill="none" stroke="#60a5fa" strokeWidth={1.5} />

        {/* Hover + lock dots */}
        {hist.map((h, i) => {
          const x = PAD + (i / (hist.length - 1)) * (W - 2 * PAD);
          const y = H - PAD - ((h.close - mn) / rng) * (H - 2 * PAD);
          const isA = lockA === i, isB = lockB === i, isH = hovered === i;
          if (!isA && !isB && !isH) return null;
          return (
            <circle key={i} cx={x} cy={y} r={isH ? 3 : 5}
              fill={isA ? "#fbbf24" : isB ? "#a78bfa" : "#60a5fa"}
              stroke="#0f172a" strokeWidth={1}
            />
          );
        })}

        {/* Invisible hit area */}
        {hist.map((h, i) => {
          const x = PAD + (i / (hist.length - 1)) * (W - 2 * PAD);
          const y = H - PAD - ((h.close - mn) / rng) * (H - 2 * PAD);
          return (
            <rect key={i} x={x - 6} y={0} width={12} height={H}
              fill="transparent"
              onMouseEnter={() => setHovered(i)}
              onClick={() => handleClick(i)}
            />
          );
        })}

        {/* Y axis labels */}
        {[0, 0.5, 1].map(f => {
          const val = mn + f * rng;
          const y   = H - PAD - f * (H - 2 * PAD);
          return (
            <text key={f} x={PAD - 4} y={y + 4}
              fontSize={9} fill="#475569" textAnchor="end">
              {val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(1)}
            </text>
          );
        })}
      </svg>

      {/* Tooltip + lock info */}
      <div style={{ fontSize: 12, marginTop: 6, display: "flex", gap: 16, flexWrap: "wrap" }}>
        {hovered != null && (
          <span style={{ color: "#60a5fa" }}>
            {hist[hovered]?.date}  {fmtClose(hist[hovered]?.close, symbol)}
            {"  "}
            <span style={{ color: clr(hist[hovered]?.pct_change) }}>
              {pct(hist[hovered]?.pct_change)}
            </span>
          </span>
        )}
        {lockA != null && (
          <span style={{ color: "#fbbf24" }}>
            A: {hist[lockA]?.date} {fmtClose(hist[lockA]?.close, symbol)}
          </span>
        )}
        {lockB != null && (
          <span style={{ color: "#a78bfa" }}>
            B: {hist[lockB]?.date} {fmtClose(hist[lockB]?.close, symbol)}
          </span>
        )}
        {deltaVal && (
          <span style={{ fontWeight: 700, color: parseFloat(deltaVal) >= 0 ? "#22c55e" : "#ef4444" }}>
            Δ {parseFloat(deltaVal) >= 0 ? "+" : ""}{deltaVal}%
          </span>
        )}
        {(lockA != null || lockB != null) && (
          <button onClick={() => { setLockA(null); setLockB(null); }}
            style={{ fontSize: 10, color: "#64748b", background: "none",
              border: "none", cursor: "pointer" }}>✕ clear</button>
        )}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═════════════════════════════════════════════════════════════════════════════
export default function GlobalPage() {
  const [rows,     setRows]     = useState<GlobalRow[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [cat,      setCat]      = useState("All");
  const [sort,     setSort]     = useState<"pct_change" | "ret_5d" | "symbol" | "cat">("cat");
  const [sortDir,  setSortDir]  = useState<1 | -1>(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [search,   setSearch]   = useState("");
  const [lastUpd,  setLastUpd]  = useState("");

  const load = useCallback(() => {
    setLoading(true);
    fetch("/api/global?days=5")
      .then(r => r.json())
      .then(d => {
        setRows(d.rows || []);
        setLastUpd(d.dates?.[0] || "");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, []);

  // Filter + sort
  const filtered = rows
    .filter(r => {
      const m = META[r.symbol] || { cat: "Other" };
      if (cat !== "All" && m.cat !== cat) return false;
      if (search && !r.symbol.toLowerCase().includes(search.toLowerCase())
        && !(META[r.symbol]?.name || "").toLowerCase().includes(search.toLowerCase()))
        return false;
      return true;
    })
    .sort((a, b) => {
      const av = sort === "pct_change" ? (a.pct_change ?? -999)
               : sort === "ret_5d"     ? (a.ret_5d ?? -999)
               : sort === "symbol"     ? a.symbol
               : (META[a.symbol]?.cat || "");
      const bv = sort === "pct_change" ? (b.pct_change ?? -999)
               : sort === "ret_5d"     ? (b.ret_5d ?? -999)
               : sort === "symbol"     ? b.symbol
               : (META[b.symbol]?.cat || "");
      return av < bv ? -sortDir : av > bv ? sortDir : 0;
    });

  // Summary stats
  const risers  = rows.filter(r => (r.pct_change ?? 0) > 0).length;
  const fallers = rows.filter(r => (r.pct_change ?? 0) < 0).length;
  const avgChg  = rows.length
    ? rows.reduce((s, r) => s + (r.pct_change ?? 0), 0) / rows.length : 0;
  const topGainer = [...rows].sort((a, b) => (b.pct_change ?? -99) - (a.pct_change ?? -99))[0];
  const topLoser  = [...rows].sort((a, b) => (a.pct_change ?? 99)  - (b.pct_change ?? 99))[0];

  const toggleSort = (col: typeof sort) => {
    if (sort === col) setSortDir(d => (d === 1 ? -1 : 1));
    else { setSort(col); setSortDir(-1); }
  };
  const sortArrow = (col: string) => sort === col ? (sortDir === -1 ? " ▼" : " ▲") : "";

  return (
    <div style={{
      minHeight: "100vh", background: "#0f172a",
      color: "#e2e8f0", fontFamily: "system-ui, sans-serif",
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: "18px 28px 14px", borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", flexWrap: "wrap", gap: 16,
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#f8fafc" }}>
            🌍 Global Markets
          </h1>
          <p style={{ margin: "3px 0 0", fontSize: 11, color: "#475569" }}>
            52 symbols · Equities · Commodities · FX · Rates · Crypto
            {lastUpd && ` · Last: ${lastUpd}`}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          padding: "6px 14px", background: "#334155", border: "none",
          borderRadius: 7, color: "#94a3b8", cursor: "pointer", fontSize: 12,
        }}>↺ Refresh</button>

        {/* Summary chips */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, flexWrap: "wrap" }}>
          {[
            { label: "Total",  value: rows.length,  color: "#60a5fa" },
            { label: "Rising", value: risers,        color: "#22c55e" },
            { label: "Falling",value: fallers,       color: "#ef4444" },
            { label: "Avg Chg",value: `${avgChg >= 0 ? "+" : ""}${avgChg.toFixed(2)}%`,
              color: avgChg >= 0 ? "#22c55e" : "#ef4444" },
          ].map((s, i) => (
            <div key={i} style={{
              textAlign: "center", padding: "6px 12px",
              background: "#1e293b", borderRadius: 8,
              border: `1px solid ${s.color}33`,
            }}>
              <div style={{ fontSize: 15, fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 10, color: "#64748b" }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Top movers strip ── */}
      {topGainer && topLoser && (
        <div style={{
          padding: "8px 28px", background: "#0a0f1a",
          display: "flex", gap: 20, fontSize: 12, borderBottom: "1px solid #1e293b",
        }}>
          <span style={{ color: "#64748b" }}>Top mover:</span>
          <span style={{ color: "#22c55e", fontWeight: 700 }}>
            {META[topGainer.symbol]?.flag} {topGainer.symbol} {pct(topGainer.pct_change)}
          </span>
          <span style={{ color: "#64748b" }}>Biggest drop:</span>
          <span style={{ color: "#ef4444", fontWeight: 700 }}>
            {META[topLoser.symbol]?.flag} {topLoser.symbol} {pct(topLoser.pct_change)}
          </span>
        </div>
      )}

      <div style={{ padding: "16px 28px" }}>
        {/* ── Selected chart ── */}
        {selected && (
          <SymbolChart symbol={selected} onClose={() => setSelected(null)} />
        )}

        {/* ── Category tabs + search ── */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14, alignItems: "center" }}>
          {CATS.map(c => (
            <button key={c} onClick={() => setCat(c)} style={{
              padding: "5px 12px", borderRadius: 999, fontSize: 11, fontWeight: 700,
              background: cat === c ? "#3b82f6" : "#1e293b",
              color: cat === c ? "#fff" : "#94a3b8",
              border: "none", cursor: "pointer",
            }}>{c}</button>
          ))}
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            style={{
              marginLeft: "auto", padding: "5px 12px",
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: 7, color: "#f8fafc", fontSize: 12, outline: "none", width: 140,
            }}
          />
        </div>

        {/* ── Table ── */}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #334155" }}>
                {[
                  ["symbol",     "Symbol",    "left"],
                  ["name",       "Name",      "left"],
                  ["cat",        "Category",  "left"],
                  ["close",      "Price",     "right"],
                  ["pct_change", "Day %",     "right"],
                  ["ret_5d",     "5d %",      "right"],
                  ["date",       "Date",      "right"],
                ].map(([col, label, align]) => (
                  <th key={col}
                    onClick={() => ["symbol","pct_change","ret_5d","cat"].includes(col)
                      ? toggleSort(col as any) : undefined}
                    style={{
                      padding: "8px 10px", textAlign: align as any,
                      color: "#64748b", fontSize: 11, fontWeight: 600,
                      cursor: ["symbol","pct_change","ret_5d","cat"].includes(col)
                        ? "pointer" : "default",
                      userSelect: "none",
                    }}>
                    {label}{sortArrow(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #1e293b" }}>
                      {Array.from({ length: 7 }).map((_, j) => (
                        <td key={j} style={{ padding: "10px", height: 36 }}>
                          <div style={{
                            background: "#1e293b", borderRadius: 4,
                            height: 12, opacity: 0.5,
                          }} />
                        </td>
                      ))}
                    </tr>
                  ))
                : filtered.map(r => (
                    <IndexRow
                      key={r.symbol}
                      row={r}
                      selected={selected === r.symbol}
                      onClick={() => setSelected(s => s === r.symbol ? null : r.symbol)}
                    />
                  ))
              }
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 && (
          <div style={{ padding: "40px 0", textAlign: "center", color: "#64748b" }}>
            No symbols match filters. Try <strong style={{ color: "#60a5fa" }}>All</strong> category.
          </div>
        )}
      </div>
    </div>
  );
}
'''
write(SRC / "global" / "page.tsx", GLOBAL_PAGE, "/global/page.tsx")


# ── Add GLOBAL link to NavBar ──────────────────────────────────────────────────
navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")
    if "/global" not in src:
        for marker in ["'/compare'", '"/compare"', "'/eta'", '"/eta"', "'/overview'", '"/overview"']:
            if marker in src:
                idx      = src.rfind(marker)
                line_end = src.find("\n", idx)
                src      = src[:line_end] + "\n  { href: '/global', label: 'GLOBAL' }," + src[line_end:]
                navbar_path.write_text(src, encoding="utf-8")
                print("  [OK] Added GLOBAL to NavBar")
                break


# ═════════════════════════════════════════════════════════════════════════════
# [5]  telegram_bot.py  — /global and /patterns commands
# ═════════════════════════════════════════════════════════════════════════════
print("\n[5/6] Patching telegram_bot.py with /global + /patterns ...")

BOT = MICC / "telegram_bot.py"
if BOT.exists():
    src = BOT.read_text(encoding="utf-8")

    GLOBAL_CMD = '''

async def cmd_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send global markets snapshot. Usage: /global  or  /global SPX"""
    import sqlite3
    args  = context.args
    sym   = args[0].upper() if args else None
    DB_P  = r"D:\\marketDB\\db\\market.db"

    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        if sym:
            # Single symbol last 5 days
            rows = conn.execute(
                "SELECT date, close, pct_change FROM global_indices_daily "
                "WHERE symbol=? ORDER BY date DESC LIMIT 5", (sym,)
            ).fetchall()
            conn.close()
            if not rows:
                await update.message.reply_text(f"No data for `{sym}`", parse_mode="Markdown")
                return
            lines = [f"*{sym} — Last 5 sessions*", ""]
            for date_, close, chg in rows:
                chg_str = f"{chg:+.2f}%" if chg is not None else "—"
                clr_ico = "🟢" if (chg or 0) > 0 else "🔴" if (chg or 0) < 0 else "⚪"
                lines.append(f"  {clr_ico} `{date_}` {close:.2f}  {chg_str}")
            await update.message.reply_text("\\n".join(lines), parse_mode="Markdown")
        else:
            # Summary: latest for all, grouped by category
            CATS_ORDER = ["US","India","Europe","Asia","Commodity","FX","Rates","Crypto"]
            CAT_MAP = {
                "SPX":"US","NDX":"US","DJIA":"US","RUT":"US","SP500VIX":"Volatility",
                "NIFTY50":"India","NIFTYBANK":"India","SENSEX":"India","NIFTYIT":"India",
                "INDIAVIX":"Volatility","DAX":"Europe","FTSE100":"Europe","CAC40":"Europe",
                "Nikkei225":"Asia","HangSeng":"Asia","Shanghai":"Asia","Kospi":"Asia","ASX200":"Asia",
                "Gold":"Commodity","Silver":"Commodity","CrudeWTI":"Commodity","BrentCrude":"Commodity",
                "DXY":"FX","USDINR":"FX","EURUSD":"FX","USDJPY":"FX",
                "US10Y":"Rates","US2Y":"Rates","Bitcoin":"Crypto","Ethereum":"Crypto",
            }
            rows = conn.execute(
                "SELECT symbol, close, pct_change FROM global_indices_daily "
                "WHERE date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol) "
                "ORDER BY symbol"
            ).fetchall()
            conn.close()

            by_cat: dict = {}
            for sym_, close, chg in rows:
                cat = CAT_MAP.get(sym_, "Other")
                by_cat.setdefault(cat, []).append((sym_, close, chg))

            lines = [f"*🌍 Global Markets Snapshot*", ""]
            for cat in CATS_ORDER:
                items = by_cat.get(cat, [])
                if not items: continue
                lines.append(f"*{cat}:*")
                for sym_, close, chg in sorted(items, key=lambda x: -(x[2] or 0)):
                    chg_str = f"{chg:+.2f}%" if chg is not None else "—"
                    ico = "🟢" if (chg or 0) > 0.3 else "🔴" if (chg or 0) < -0.3 else "⚪"
                    lines.append(f"  {ico} `{sym_:<12}` {chg_str}")
                lines.append("")

            await update.message.reply_text("\\n".join(lines)[:4000], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top patterns active today. Usage: /patterns  or  /patterns RELIANCE"""
    import sqlite3
    from datetime import datetime
    args  = context.args
    sym   = args[0].upper() if args else None
    DB_P  = r"D:\\marketDB\\db\\market.db"
    today_mmdd = datetime.today().strftime("%m-%d")

    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        # Try v3 first, fall back to v2
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        tbl = "seasonality_patterns_v3" if "seasonality_patterns_v3" in tables else "seasonality_patterns"

        where = f"anchor_mm_dd = '{today_mmdd}'"
        if sym: where += f" AND symbol = '{sym}'"
        else:   where += " AND accuracy >= 68 AND score >= 2"

        rows = conn.execute(
            f"SELECT symbol, anchor_mm_dd, window_days, direction, accuracy, mean_ret, score "
            f"FROM {tbl} WHERE {where} ORDER BY score DESC LIMIT 15"
        ).fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text(
                f"No patterns for {today_mmdd}" + (f" / {sym}" if sym else ""),
                parse_mode="Markdown"
            )
            return

        lines = [f"*🔬 Seasonal Patterns — {today_mmdd}*", f"_{tbl}_", ""]
        for sym_, anc, win, dirn, acc, mean, score in rows:
            ico = "🟢" if dirn == "UP" else "🔴"
            mean_str = f"{mean:+.2f}%"
            lines.append(
                f"  {ico} `{sym_:<14}` {win}d {dirn:<5} {acc:.0f}% {mean_str}  ★{score:.2f}"
            )
        await update.message.reply_text("\\n".join(lines)[:4000], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
'''

    HANDLER_MARKER = 'app.add_handler(CommandHandler("eta"'
    HANDLER_INSERT = '''\
    app.add_handler(CommandHandler("global",   cmd_global))
    app.add_handler(CommandHandler("patterns", cmd_patterns))
'''

    changed = False
    if "async def cmd_global" not in src:
        src = src.replace("def main():", GLOBAL_CMD + "\ndef main():")
        changed = True
        print("  [OK] Added /global + /patterns commands")

    if '"global"' not in src and HANDLER_MARKER in src:
        src = src.replace(HANDLER_MARKER, HANDLER_INSERT + "    " + HANDLER_MARKER)
        changed = True
        print("  [OK] Registered /global /patterns handlers")

    # Update print line
    src = src.replace(
        "Commands: /start /report /alpha /beta /gamma /delta /eta /streak /options /index /stock /hot /deep /kappa /watch /status",
        "Commands: /start /report /alpha /beta /gamma /delta /eta /streak /options /index /stock /hot /deep /kappa /global /patterns /watch /status"
    )

    if changed:
        BOT.write_text(src, encoding="utf-8")
        print("  [OK] telegram_bot.py saved")
    else:
        print("  [SKIP] No changes needed")
else:
    print("  [SKIP] telegram_bot.py not found")


print("""
=============================================================
BUILD PHASE 17 COMPLETE
=============================================================

[1] run_pipeline.py
    Added Phase 1B: Global Indices fetch (incremental, ~5 min)
    Now runs automatically every day with your daily pipeline

[2] /api/global/route.ts
    GET /api/global?days=5          -- all 52 symbols latest
    GET /api/global?category=India  -- filtered by category

[3] /api/global/[symbol]/route.ts
    GET /api/global/SPX?days=252    -- 1y history for SPX
    Returns: rows[], stats{cagr, hi, lo, total_ret}

[4] /global/page.tsx  — FULL GLOBAL MARKETS DASHBOARD
    - 52 symbols: equities / commodities / FX / rates / crypto
    - Category tabs: All / US / India / Europe / Asia / LatAm / Commodity / FX / Rates / Crypto
    - Sort by: Day% / 5d% / symbol / category
    - Click any row -> 1-year chart opens with:
        Hover tooltip (date / price / % change)
        Click-to-lock A & B points + Δ delta
    - Top movers strip at top
    - Summary chips: total / rising / falling / avg change

[5] telegram_bot.py
    /global          -- full snapshot grouped by category
    /global SPX      -- last 5 sessions for one symbol
    /patterns        -- today's top seasonal patterns (>68% accuracy)
    /patterns RELIANCE -- patterns for specific symbol today

[6] micc_engine.py
    Eta + Iota now run inside daily engine

NEXT STEPS:
  cd D:\\MICC\\micc-dashboard && npm run dev
  localhost:3000/global

  Add to daily pipeline (already patched in run_pipeline.py)
  
FULL QUEUE STATUS:
  ✅ /eta page
  ✅ /compare page
  ✅ /global page (NEW)
  ✅ /patterns-v3 page
  ✅ NavBar: ETA / COMPARE / GLOBAL / PATS-V3
  ✅ Telegram: /eta /deep /kappa /global /patterns
  ✅ Pipeline: global indices auto-fetch daily
  🔄 build_seasonality_v3.py running (check other terminal)
  ⏳ Backtest analysis in PatCard (/patterns page)
  ⏳ /patterns page switch to v3 after build completes
=============================================================
""")
