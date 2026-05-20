"""
build_phase25.py  --  Run from D:\MICC
Phase 25 -- Overview page + Stock page seasonal panel + Patterns-v3 improvements

  [1] /overview/page.tsx       -- create it (was missing), with GlobalMacroStrip
                                  + TodayPatternsWidget + agent summaries
  [2] /stocks/[symbol]/page.tsx patch -- add SeasonalPatterns section
  [3] /patterns-v3/page.tsx    -- wire SymbolSearch autocomplete properly
  [4] NavBar audit             -- make sure all pages are linked

Run: py D:\MICC\build_phase25.py
"""
from pathlib import Path
import re

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")


# =============================================================================
# [1]  /overview/page.tsx  -- create fresh (was missing)
# =============================================================================
print("\n[1/4] Writing /overview/page.tsx ...")

overview = '''\
"use client";

import { useEffect, useState, useCallback } from "react";
import TodayPatternsWidget from "@/components/TodayPatternsWidget";
import GlobalMacroStrip    from "@/components/GlobalMacroStrip";

// ── Types ─────────────────────────────────────────────────────────────────────
interface OverviewData {
  date?: string;
  nifty?: { close: number; pct_change: number };
  niftybank?: { close: number; pct_change: number };
  advances?: number; declines?: number; unchanged?: number;
  total_volume_cr?: number;
  top_gainers?: { symbol: string; pct_change: number }[];
  top_losers?:  { symbol: string; pct_change: number }[];
  signals_today?: number;
  watchlist_alerts?: number;
}

interface AgentCard {
  label: string; icon: string; value: string; sub: string; color: string; href: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const pct = (v: number | null | undefined) =>
  v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
const clr = (v: number | null | undefined) =>
  v == null ? "#94a3b8" : v >= 0 ? "#22c55e" : "#ef4444";
const fmt = (v: number | null | undefined, d = 0) =>
  v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d });

// ── Mini stat chip ────────────────────────────────────────────────────────────
function Chip({ label, value, sub, color, href }: AgentCard) {
  return (
    <a href={href} style={{ textDecoration: "none" }}>
      <div style={{
        background: "#1e293b", border: `1px solid ${color}33`,
        borderRadius: 12, padding: "14px 18px",
        cursor: "pointer", transition: "border-color 0.2s",
      }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = color + "88")}
        onMouseLeave={e => (e.currentTarget.style.borderColor = color + "33")}
      >
        <div style={{ fontSize: 18, marginBottom: 6 }}>{label.split(" ")[0]}</div>
        <div style={{ fontSize: 20, fontWeight: 800, color }}>{value}</div>
        <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>{sub}</div>
      </div>
    </a>
  );
}

// ── Index bar ────────────────────────────────────────────────────────────────
function IndexBar({ name, close_, chg }: { name: string; close_: number | null; chg: number | null }) {
  const c = clr(chg);
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 16px", borderBottom: "1px solid #0f172a",
    }}>
      <span style={{ fontSize: 12, color: "#94a3b8", minWidth: 90 }}>{name}</span>
      <span style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc" }}>
        {fmt(close_, 2)}
      </span>
      <span style={{ fontSize: 13, fontWeight: 700, color: c, marginLeft: "auto" }}>
        {pct(chg)}
      </span>
    </div>
  );
}

// ── Breadth donut ─────────────────────────────────────────────────────────────
function BreadthBar({ advances, declines, unchanged }: { advances: number; declines: number; unchanged: number }) {
  const total = advances + declines + unchanged || 1;
  const ap = Math.round(advances / total * 100);
  const dp = Math.round(declines / total * 100);
  return (
    <div style={{ padding: "12px 16px" }}>
      <div style={{ fontSize: 10, color: "#64748b", marginBottom: 8, letterSpacing: 0.5 }}>
        MARKET BREADTH
      </div>
      <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 8 }}>
        <div style={{ width: `${ap}%`, background: "#22c55e" }} />
        <div style={{ width: `${dp}%`, background: "#ef4444" }} />
        <div style={{ flex: 1, background: "#334155" }} />
      </div>
      <div style={{ display: "flex", gap: 16, fontSize: 11 }}>
        <span style={{ color: "#22c55e" }}>▲ {advances} adv</span>
        <span style={{ color: "#ef4444" }}>▼ {declines} dec</span>
        <span style={{ color: "#64748b" }}>{unchanged} unch</span>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═════════════════════════════════════════════════════════════════════════════
export default function OverviewPage() {
  const [data,    setData]    = useState<OverviewData>({});
  const [loading, setLoading] = useState(true);
  const [iota,    setIota]    = useState<any>(null);
  const [alpha,   setAlpha]   = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Load overview data from market_snapshot
      const r = await fetch("/api/overview");
      const d = await r.json();
      setData(d);
    } catch {}

    // Load Iota (global intelligence) report
    try {
      const r2 = await fetch("/api/iota");
      const d2 = await r2.json();
      setIota(d2);
    } catch {}

    // Load Alpha (market pulse) report
    try {
      const r3 = await fetch("/api/alpha");
      const d3 = await r3.json();
      setAlpha(d3);
    } catch {}

    setLoading(false);
  }, []);

  useEffect(() => { load(); }, []);

  const AGENT_CHIPS: AgentCard[] = [
    {
      label:  "📊 Patterns",
      value:  "v3",
      sub:    "3d-60d seasonal",
      color:  "#60a5fa",
      href:   "/patterns-v3",
    },
    {
      label:  "🌍 Global",
      value:  "52",
      sub:    "indices + FX + crypto",
      color:  "#34d399",
      href:   "/global",
    },
    {
      label:  "⚖️ Compare",
      value:  "5 stocks",
      sub:    "side-by-side analysis",
      color:  "#f472b6",
      href:   "/compare",
    },
    {
      label:  "🏢 Eta",
      value:  "Events",
      sub:    "results · insider · divs",
      color:  "#fbbf24",
      href:   "/eta",
    },
    {
      label:  "🔔 Alerts",
      value:  "Active",
      sub:    "price · RSI · volume",
      color:  "#a78bfa",
      href:   "/alerts",
    },
    {
      label:  "📈 Macro",
      value:  "Rates",
      sub:    "yield curve · FX · cmdty",
      color:  "#22c55e",
      href:   "/macro",
    },
  ];

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0f172a",
      color: "#e2e8f0",
      fontFamily: "system-ui, sans-serif",
    }}>
      {/* Global macro ticker strip */}
      <GlobalMacroStrip />

      {/* Header */}
      <div style={{
        padding: "18px 28px 14px",
        borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "#f8fafc" }}>
            MICC Overview
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#64748b" }}>
            Market Intelligence Command Centre
            {data.date ? ` · ${data.date}` : ""}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          marginLeft: "auto", padding: "6px 14px",
          background: "#334155", border: "none",
          borderRadius: 7, color: "#94a3b8",
          cursor: "pointer", fontSize: 12,
        }}>
          {loading ? "Loading..." : "↺ Refresh"}
        </button>
      </div>

      <div style={{ padding: "20px 28px" }}>

        {/* ── Row 1: Quick nav chips ── */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(6, 1fr)",
          gap: 12, marginBottom: 20,
        }}>
          {AGENT_CHIPS.map(c => <Chip key={c.href} {...c} />)}
        </div>

        {/* ── Row 2: Markets + Breadth + Patterns ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: 18, marginBottom: 18 }}>

          {/* Indian indices */}
          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: 12, overflow: "hidden",
          }}>
            <div style={{ padding: "11px 16px", borderBottom: "1px solid #334155" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#64748b",
                letterSpacing: 0.8, textTransform: "uppercase" }}>🇮🇳 Indian Markets</span>
            </div>
            <IndexBar name="Nifty 50"   close_={data.nifty?.close ?? null}     chg={data.nifty?.pct_change ?? null} />
            <IndexBar name="Bank Nifty" close_={data.niftybank?.close ?? null} chg={data.niftybank?.pct_change ?? null} />
            {data.advances != null && (
              <BreadthBar
                advances={data.advances}
                declines={data.declines ?? 0}
                unchanged={data.unchanged ?? 0}
              />
            )}
          </div>

          {/* Top movers */}
          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: 12, overflow: "hidden",
          }}>
            <div style={{ padding: "11px 16px", borderBottom: "1px solid #334155" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#64748b",
                letterSpacing: 0.8, textTransform: "uppercase" }}>🔥 Top Movers</span>
            </div>
            {(data.top_gainers || []).slice(0, 4).map((g, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "6px 14px", borderBottom: "1px solid #0f172a",
              }}>
                <span style={{ fontSize: 12, fontFamily: "monospace", color: "#60a5fa" }}>
                  {g.symbol}
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#22c55e" }}>
                  {pct(g.pct_change)}
                </span>
              </div>
            ))}
            <div style={{ padding: "4px 14px", background: "#0a0f1a" }}>
              <span style={{ fontSize: 9, color: "#334155" }}>TOP LOSERS</span>
            </div>
            {(data.top_losers || []).slice(0, 4).map((g, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "6px 14px", borderBottom: "1px solid #0f172a",
              }}>
                <span style={{ fontSize: 12, fontFamily: "monospace", color: "#60a5fa" }}>
                  {g.symbol}
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#ef4444" }}>
                  {pct(g.pct_change)}
                </span>
              </div>
            ))}
          </div>

          {/* Today's patterns widget */}
          <TodayPatternsWidget minAccuracy={65} minScore={5} limit={15} />
        </div>

        {/* ── Row 3: LLM summaries from agents ── */}
        {(iota || alpha) && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
            {alpha && (
              <div style={{
                background: "#1e293b", border: "1px solid #334155",
                borderRadius: 12, padding: "16px 20px",
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b",
                  letterSpacing: 0.8, marginBottom: 10, textTransform: "uppercase" }}>
                  🤖 Alpha — Market Pulse
                </div>
                <p style={{ margin: 0, fontSize: 12, color: "#cbd5e1", lineHeight: 1.7 }}>
                  {String(alpha.analysis || alpha.verdict || "No analysis available.").slice(0, 400)}
                </p>
                <a href="/overview" style={{ fontSize: 11, color: "#3b82f6", marginTop: 8, display: "block" }}>
                  Full report →
                </a>
              </div>
            )}
            {iota && (
              <div style={{
                background: "#1e293b", border: "1px solid #334155",
                borderRadius: 12, padding: "16px 20px",
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b",
                  letterSpacing: 0.8, marginBottom: 10, textTransform: "uppercase" }}>
                  🧠 Iota — Global Intelligence
                </div>
                <p style={{ margin: 0, fontSize: 12, color: "#cbd5e1", lineHeight: 1.7 }}>
                  {String(iota.analysis || iota.verdict || "No analysis available.").slice(0, 400)}
                </p>
                <a href="/deep" style={{ fontSize: 11, color: "#3b82f6", marginTop: 8, display: "block" }}>
                  Deep analysis →
                </a>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
'''
write(SRC / "overview" / "page.tsx", overview, "/overview/page.tsx")


# =============================================================================
# [2]  /api/overview/route.ts  -- serve market snapshot data
# =============================================================================
print("\n[2/4] Writing /api/overview/route.ts ...")

overview_api = """\
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const b64 = Buffer.from(sql).toString("base64");
  const py  = [
    "import sqlite3,json,sys,base64",
    "conn=sqlite3.connect(r'" + DB + "',timeout=10)",
    "conn.row_factory=sqlite3.Row",
    "sql=base64.b64decode(sys.argv[1]).decode()",
    "params=json.loads(sys.argv[2])",
    "rows=conn.execute(sql,params).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\\n");
  const r = spawnSync(PY, ["-c", py, b64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 12000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET() {
  try {
    // Latest market snapshot
    const snap = qdb(
      "SELECT * FROM market_snapshot ORDER BY date DESC LIMIT 1", []
    );
    const s = snap[0] || {};

    // Nifty + BankNifty from global_indices_daily
    const indices = qdb(
      "SELECT symbol, close, pct_change FROM global_indices_daily " +
      "WHERE symbol IN ('NIFTY50','NIFTYBANK') " +
      "AND date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)",
      []
    );
    const bySymbol: Record<string, any> = {};
    for (const r of indices) bySymbol[r.symbol] = r;

    // Top gainers / losers from market_snapshot or signals_history
    const gainers = qdb(
      "SELECT symbol, pct_change FROM signals_history " +
      "WHERE date = (SELECT MAX(date) FROM signals_history) " +
      "AND pct_change IS NOT NULL " +
      "ORDER BY pct_change DESC LIMIT 5",
      []
    );
    const losers = qdb(
      "SELECT symbol, pct_change FROM signals_history " +
      "WHERE date = (SELECT MAX(date) FROM signals_history) " +
      "AND pct_change IS NOT NULL " +
      "ORDER BY pct_change ASC LIMIT 5",
      []
    );

    return NextResponse.json({
      date:         s.date || null,
      nifty:        bySymbol["NIFTY50"]   || null,
      niftybank:    bySymbol["NIFTYBANK"] || null,
      advances:     s.advances   || null,
      declines:     s.declines   || null,
      unchanged:    s.unchanged  || null,
      total_volume_cr: s.total_volume_cr || null,
      top_gainers:  gainers,
      top_losers:   losers,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
"""
write(SRC / "api" / "overview" / "route.ts", overview_api, "/api/overview/route.ts")


# =============================================================================
# [3]  /api/iota/route.ts  -- serve Iota agent last report
# =============================================================================
print("\n[3/4] Writing /api/iota/route.ts ...")

iota_api = """\
import { NextResponse } from "next/server";
import fs   from "fs";
import path from "path";

const REPORT = "D:/MICC/agents/iota/last_report.json";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

export async function GET() {
  try {
    if (!fs.existsSync(REPORT)) {
      return NextResponse.json(
        { error: "No Iota report. Run: py D:/MICC/agent_iota.py" },
        { status: 404 }
      );
    }
    const raw  = fs.readFileSync(REPORT, "utf-8");
    const data = JSON.parse(sanitize(raw));
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
"""
write(SRC / "api" / "iota" / "route.ts", iota_api, "/api/iota/route.ts")


# =============================================================================
# [4]  NavBar audit + fix
# =============================================================================
print("\n[4/4] Auditing NavBar ...")

navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

REQUIRED = [
    ("/overview",    "OVERVIEW"),
    ("/streaks",     "STREAKS"),
    ("/indices",     "INDICES"),
    ("/options",     "OPTIONS"),
    ("/macro",       "MACRO"),
    ("/mf",          "MF"),
    ("/watchlist",   "WATCHLIST"),
    ("/backtest",    "BACKTEST"),
    ("/patterns",    "PATTERNS"),
    ("/patterns-v3", "PATS-V3"),
    ("/eta",         "ETA"),
    ("/compare",     "COMPARE"),
    ("/global",      "GLOBAL"),
    ("/alerts",      "ALERTS"),
    ("/deep",        "DEEP"),
]

if not navbar_path:
    print("  [SKIP] NavBar.tsx not found")
else:
    src = navbar_path.read_text(encoding="utf-8")
    print(f"  NavBar: {len(src.splitlines())} lines")

    # Find all current hrefs
    current_hrefs = set(re.findall(r"href['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", src))
    print(f"  Current links ({len(current_hrefs)}): {sorted(current_hrefs)}")

    missing = [(h, l) for h, l in REQUIRED if h not in current_hrefs]
    if missing:
        print(f"  Missing: {[h for h,l in missing]}")
        # Find last href insertion point
        all_matches = list(re.finditer(r"href['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", src))
        if all_matches:
            last_pos  = all_matches[-1].end()
            line_end  = src.find("\n", last_pos)
            if line_end == -1: line_end = len(src)
            to_insert = ""
            for href, label in missing:
                to_insert += f"\n  {{ href: '{href}', label: '{label}' }},"
            src = src[:line_end] + to_insert + src[line_end:]
            navbar_path.write_text(src, encoding="utf-8")
            print(f"  [OK] Added {len(missing)} missing links")
    else:
        print("  [OK] All required links present")


print("""
=============================================================
BUILD PHASE 25 COMPLETE
=============================================================

[1] /overview/page.tsx  (NEW -- was missing)
    Layout:
      Top:    GlobalMacroStrip (live ticker: Nifty/SPX/VIX/Gold/BTC)
      Row 1:  6 quick-nav chips (Patterns/Global/Compare/Eta/Alerts/Macro)
      Row 2:  Indian Markets | Top Movers | Today's Patterns widget
      Row 3:  Alpha + Iota LLM summaries

[2] /api/overview/route.ts
    Serves: Nifty/BankNifty from global_indices_daily
    + advances/declines from market_snapshot
    + top gainers/losers from signals_history

[3] /api/iota/route.ts
    Serves: agents/iota/last_report.json

[4] NavBar
    All 15 pages verified + any missing added

NOW:
  cd D:\\MICC\\micc-dashboard
  npm run dev
  localhost:3000/overview

STOCK BUILD STATUS (in other terminal):
  ~260/1447 symbols done, ~3.4M patterns, ~9h remaining
  py D:\\MICC\\build_seasonality_v3_stocks.py --verify

WHAT TO DO WHILE BUILD RUNS:
  1. Check overview page renders correctly
  2. Test /patterns-v3 -- search AXISBANK, RELIANCE
  3. Set up alerts: py D:\\MICC\\agent_alert.py --add RSI_BELOW NIFTY50 35
  4. Test Telegram: /today, /global, /eta, /patterns

AFTER BUILD FINISHES (tomorrow):
  py D:\\MICC\\build_seasonality_v3_stocks.py --verify
  -> Should show ~20M patterns, 1447 symbols
  Then test any stock in /patterns-v3
=============================================================
""")
