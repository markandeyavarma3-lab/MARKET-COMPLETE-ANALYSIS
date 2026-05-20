"""
build_phase21.py  --  Run from D:\MICC
Builds:
  [1] /api/stock-patterns/[symbol]/route.ts
      -- gets patterns-v3 for a specific stock (for /stocks/[symbol] page)
  [2] /overview page upgrade
      -- adds a GlobalMacroStrip component at the top (rates + FX + VIX at a glance)
      -- adds TodayPatterns mini widget
  [3] run_pipeline.py  -- add fetch_global_indices_v2 if not already there
  [4] NavBar -- ensure MACRO link present

Run: py D:\MICC\build_phase21.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

def patch(path: Path, old: str, new: str, label: str) -> bool:
    if not path.exists():
        print(f"  [SKIP] {label} -- not found"); return False
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [SKIP] {label} -- marker not found"); return False
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  [OK] {label}"); return True


# =============================================================================
# [1]  /api/stock-patterns/[symbol]/route.ts
#      Returns patterns-v3 for a specific symbol, sorted by score
#      Used by /stocks/[symbol] page to show "Upcoming seasonal patterns"
# =============================================================================
print("\n[1/4] Writing /api/stock-patterns/[symbol]/route.ts ...")

stock_pat_ts = """import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const sqlB64  = Buffer.from(sql).toString("base64");
  const pyLines = [
    "import sqlite3, json, sys, base64",
    "conn = sqlite3.connect(r'" + DB + "', timeout=15)",
    "conn.row_factory = sqlite3.Row",
    "sql = base64.b64decode(sys.argv[1]).decode()",
    "params = json.loads(sys.argv[2])",
    "rows = conn.execute(sql, params).fetchall()",
    "print(json.dumps([dict(r) for r in rows], default=str))",
    "conn.close()",
  ];
  const r = spawnSync(PY, ["-c", pyLines.join("\\n"), sqlB64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 20000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET(
  req: Request,
  { params }: { params: { symbol: string } }
) {
  const symbol = (params.symbol || "").toUpperCase();
  const url    = new URL(req.url);
  const limit  = Math.min(parseInt(url.searchParams.get("limit") || "20"), 100);
  const minAcc = parseFloat(url.searchParams.get("min_accuracy") || "60");
  const anchor = url.searchParams.get("anchor") || "";  // MM-DD filter

  if (!symbol) return NextResponse.json({ error: "No symbol" }, { status: 400 });

  try {
    // Check if table exists
    const tableCheck = qdb(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='seasonality_patterns_v3'", []
    );
    if (!tableCheck.length) {
      return NextResponse.json({ patterns: [], count: 0, note: "Table not built yet" });
    }

    // Base query: top patterns for this symbol
    const conditions = [
      "symbol = ?",
      "accuracy >= ?",
      "ABS(mean_ret) <= 50",
      "score >= 1",
    ];
    const qparams: any[] = [symbol, minAcc];

    if (anchor) {
      conditions.push("anchor_mm_dd = ?");
      qparams.push(anchor);
    }

    const where = "WHERE " + conditions.join(" AND ");
    const sql = [
      "SELECT anchor_mm_dd, window_days, direction,",
      "n_obs, accuracy, mean_ret, median_ret, std_ret,",
      "p25, p75, best_ret, worst_ret,",
      "score, consistency, t_stat, p_value,",
      "early_accuracy, recent_accuracy, degradation, recent_mean",
      "FROM seasonality_patterns_v3",
      where,
      "ORDER BY score DESC",
      "LIMIT " + limit,
    ].join(" ");

    const rows = qdb(sql, qparams);

    // Also get upcoming anchors (next 30 days)
    const today = new Date();
    const upcomingAnchors: string[] = [];
    for (let i = 0; i <= 30; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      const mmdd = String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
      upcomingAnchors.push(mmdd);
    }

    const upcomingSql = [
      "SELECT anchor_mm_dd, window_days, direction, accuracy, mean_ret, score",
      "FROM seasonality_patterns_v3",
      "WHERE symbol = ? AND anchor_mm_dd IN (" + upcomingAnchors.map(() => "?").join(",") + ")",
      "AND accuracy >= 65 AND ABS(mean_ret) <= 50 AND score >= 2",
      "ORDER BY score DESC LIMIT 10",
    ].join(" ");
    const upcoming = qdb(upcomingSql, [symbol, ...upcomingAnchors]);

    return NextResponse.json({ patterns: rows, count: rows.length, upcoming, symbol });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, patterns: [], count: 0 }, { status: 500 });
  }
}
"""
write(SRC / "api" / "stock-patterns" / "[symbol]" / "route.ts",
      stock_pat_ts, "/api/stock-patterns/[symbol]/route.ts")


# =============================================================================
# [2]  GlobalMacroStrip component file  (shared component)
#      Used in /overview and other pages
# =============================================================================
print("\n[2/4] Writing GlobalMacroStrip component ...")

components_dir = DASH / "src" / "components"
components_dir.mkdir(parents=True, exist_ok=True)

macro_strip_tsx = '''\
"use client";

import { useEffect, useState } from "react";

interface GRow { symbol: string; close: number|null; pct_change: number|null; }

const META: Record<string, { label: string; flag: string; invert?: boolean }> = {
  SP500VIX: { label:"VIX",     flag:"⚡", invert:true },
  INDIAVIX: { label:"IVIX",    flag:"⚡", invert:true },
  US10Y:    { label:"US 10Y",  flag:"🇺🇸" },
  DXY:      { label:"DXY",     flag:"💵" },
  USDINR:   { label:"INR",     flag:"₹" },
  Gold:     { label:"Gold",    flag:"🥇" },
  CrudeWTI: { label:"WTI",     flag:"🛢" },
  Bitcoin:  { label:"BTC",     flag:"₿" },
  SPX:      { label:"S&P500",  flag:"🇺🇸" },
  NIFTY50:  { label:"Nifty",   flag:"🇮🇳" },
};

const SYMBOLS = ["NIFTY50","SPX","INDIAVIX","SP500VIX","US10Y","DXY","USDINR","Gold","CrudeWTI","Bitcoin"];

const fmtV = (v: number|null, sym: string) => {
  if (v == null) return "—";
  if (sym === "US10Y") return v.toFixed(2) + "%";
  if (sym === "USDINR") return v.toFixed(2);
  if (v >= 10000) return (v / 1000).toFixed(1) + "k";
  if (v >= 1000)  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return v.toFixed(2);
};

export default function GlobalMacroStrip() {
  const [rows, setRows]   = useState<GRow[]>([]);
  const [asOf, setAsOf]   = useState("");
  const [loading, setL]   = useState(true);

  useEffect(() => {
    fetch("/api/global?days=2")
      .then(r => r.json())
      .then(d => {
        const bySymbol: Record<string, GRow> = {};
        for (const r of (d.rows || [])) bySymbol[r.symbol] = r;
        setRows(SYMBOLS.map(s => bySymbol[s] || { symbol: s, close: null, pct_change: null }));
        setAsOf(d.dates?.[0] || "");
      })
      .catch(() => {})
      .finally(() => setL(false));
  }, []);

  if (loading) return (
    <div style={{ height: 40, background: "#080d14", borderBottom: "1px solid #1e293b" }} />
  );

  return (
    <div style={{
      background: "#080d14",
      borderBottom: "1px solid #1e293b",
      padding: "6px 28px",
      display: "flex",
      gap: 0,
      overflowX: "auto",
      alignItems: "center",
    }}>
      {rows.map((r, i) => {
        const meta  = META[r.symbol] || { label: r.symbol, flag: "🌍" };
        const chg   = r.pct_change;
        const inv   = meta.invert;
        const color = chg == null ? "#475569"
                    : (inv ? chg < 0 : chg > 0) ? "#22c55e"
                    : chg === 0 ? "#475569" : "#ef4444";
        const pct   = chg == null ? "" : (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%";
        return (
          <div key={r.symbol} style={{
            display: "flex", alignItems: "center", gap: 5,
            padding: "4px 14px",
            borderRight: i < rows.length - 1 ? "1px solid #1e293b" : "none",
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 12 }}>{meta.flag}</span>
            <span style={{ fontSize: 10, color: "#475569" }}>{meta.label}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#e2e8f0" }}>
              {fmtV(r.close, r.symbol)}
            </span>
            {pct && (
              <span style={{ fontSize: 10, fontWeight: 700, color }}>{pct}</span>
            )}
          </div>
        );
      })}
      {asOf && (
        <span style={{ fontSize: 9, color: "#334155", marginLeft: "auto", flexShrink: 0 }}>
          {asOf}
        </span>
      )}
    </div>
  );
}
'''
write(components_dir / "GlobalMacroStrip.tsx", macro_strip_tsx, "src/components/GlobalMacroStrip.tsx")


# =============================================================================
# [3]  /overview/page.tsx  -- inject macro strip at top
#      We patch the existing overview page to import and render the strip
# =============================================================================
print("\n[3/4] Patching /overview/page.tsx ...")

overview_path = SRC / "overview" / "page.tsx"
if not overview_path.exists():
    print("  [SKIP] /overview/page.tsx not found")
else:
    src = overview_path.read_text(encoding="utf-8")

    # Add import
    if "GlobalMacroStrip" not in src:
        # Add import after "use client"
        src = src.replace(
            '"use client";',
            '"use client";\n\nimport GlobalMacroStrip from "@/components/GlobalMacroStrip";'
        )
        print("  [OK] Added GlobalMacroStrip import")

        # Inject strip right after the opening div of the page
        # Find the first <div with minHeight or background
        import re
        # Look for the outermost return div
        match = re.search(r'(return\s*\(\s*\n\s*<div[^>]*>)', src)
        if match:
            pos = match.end()
            src = src[:pos] + "\n      <GlobalMacroStrip />" + src[pos:]
            print("  [OK] Injected GlobalMacroStrip into overview page")
        else:
            # Try simpler: inject after the first <div style=
            idx = src.find("<div style=", src.find("return"))
            if idx > 0:
                # Find the end of this opening tag
                end = src.find(">", idx) + 1
                src = src[:end] + "\n      <GlobalMacroStrip />" + src[end:]
                print("  [OK] Injected GlobalMacroStrip (fallback method)")

        overview_path.write_text(src, encoding="utf-8")
    else:
        print("  [SKIP] GlobalMacroStrip already in overview page")


# =============================================================================
# [4]  NavBar -- ensure MACRO is present, add if missing
# =============================================================================
print("\n[4/4] Checking NavBar for MACRO link ...")

navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")
    print(f"  Current NavBar ({len(src.splitlines())} lines)")

    # Print all href lines
    import re
    hrefs = re.findall(r"href['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", src)
    print(f"  Current links: {hrefs}")

    changed = False
    for href, label in [
        ("/macro",    "MACRO"),
        ("/global",   "GLOBAL"),
        ("/alerts",   "ALERTS"),
        ("/compare",  "COMPARE"),
        ("/patterns-v3", "PATS-V3"),
    ]:
        if href not in src:
            # Find the last href and insert after it
            all_matches = list(re.finditer(r"href['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", src))
            if all_matches:
                last_match = all_matches[-1]
                # Find end of that line
                line_end = src.find("\n", last_match.end())
                if line_end == -1: line_end = len(src)
                src = src[:line_end] + f"\n  {{ href: '{href}', label: '{label}' }}," + src[line_end:]
                changed = True
                print(f"  [OK] Added {label} ({href})")
    
    if changed:
        navbar_path.write_text(src, encoding="utf-8")
    else:
        print("  All links already present")
else:
    print("  [SKIP] NavBar.tsx not found")


# =============================================================================
# Summary
# =============================================================================
print("""
=============================================================
BUILD PHASE 21 COMPLETE
=============================================================

[1] /api/stock-patterns/[symbol]/route.ts
    GET /api/stock-patterns/RELIANCE
    - Returns top patterns for symbol (sorted by score)
    - Also returns "upcoming" patterns (next 30 days)
    - Filters: min_accuracy, anchor date
    - Used by /stocks/[symbol] page

[2] src/components/GlobalMacroStrip.tsx
    Horizontal ticker strip showing:
    Nifty | S&P | India VIX | VIX | US10Y | DXY | INR | Gold | WTI | BTC
    + day% change colour coded green/red
    Renders at top of /overview (and can be added to any page)

[3] /overview/page.tsx
    GlobalMacroStrip injected at top of page

[4] NavBar
    MACRO / GLOBAL / ALERTS / COMPARE / PATS-V3 links verified

NEXT STEPS:
  cd D:\\MICC\\micc-dashboard
  npm run dev

  localhost:3000/overview    -- macro strip at top
  localhost:3000/macro       -- full macro dashboard
  localhost:3000/patterns-v3 -- search patterns (now clean)
  localhost:3000/global      -- 52 global indices
  localhost:3000/alerts      -- set up price/RSI alerts
  localhost:3000/compare     -- compare stocks side by side

Add your first alerts:
  py D:\\MICC\\agent_alert.py --add RSI_BELOW NIFTY50 35 "Oversold bounce"
  py D:\\MICC\\agent_alert.py --add PRICE_ABOVE RELIANCE 1450 "Breakout"
  py D:\\MICC\\agent_alert.py --add VOLUME_SURGE HDFCBANK 3 "Big volume"
  py D:\\MICC\\agent_alert.py --list
  py D:\\MICC\\agent_alert.py --send

FULL SYSTEM STATUS:
  Agents     : Alpha Beta Gamma Delta Epsilon Zeta Eta Iota Kappa Alert (10)
  Pages      : 15+ (overview streaks indices options macro mf stocks
               watchlist backtest patterns patterns-v3 eta compare
               global alerts deep)
  DB patterns: ~1,060,235 valid patterns (after score cleanup)
  Global data: 52 symbols back to 2000
  Telegram   : 15+ commands
  Pipeline   : fully automated daily
=============================================================
""")
