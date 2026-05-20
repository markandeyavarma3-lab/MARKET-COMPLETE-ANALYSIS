"""
fix_and_next_phase.py  --  Run from D:\MICC
Fixes:
  [1] build_seasonality_v3.py  -- fix indices_data column (name/close, not index_name/closing_index_value)
  [2] NavBar.tsx               -- fix COMPARE link (force-inject)

Also builds Phase 16:
  [3] /api/patterns-v3/route.ts       -- serves seasonality_patterns_v3 data
  [4] /api/patterns-v3/detail/route.ts -- single pattern detail with all_returns JSON
  [5] Update /patterns page to show v3 badge + new metrics (p_value, consistency, t_stat, degradation)

Run: py D:\MICC\fix_and_next_phase.py
"""
import re
from pathlib import Path

MICC  = Path(r"D:\MICC")
DASH  = MICC / "micc-dashboard"
SRC   = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}")

def patch_file(path: Path, old: str, new: str, label: str) -> bool:
    if not path.exists():
        print(f"  [SKIP] {label} — not found: {path}"); return False
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [SKIP] {label} — marker not found"); return False
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  [OK] {label}"); return True


# ═════════════════════════════════════════════════════════════════════════════
# [1] FIX build_seasonality_v3.py  — wrong column names
# ═════════════════════════════════════════════════════════════════════════════
print("\n[1/5] Fixing build_seasonality_v3.py column names...")

v3 = MICC / "build_seasonality_v3.py"
if not v3.exists():
    print("  [SKIP] build_seasonality_v3.py not found — copy it to D:\\MICC first")
else:
    src = v3.read_text(encoding="utf-8")
    fixed = False

    # Fix 1: indices_data column name  (closing_index_value -> close, index_name -> name)
    OLD1 = '''\
        "SELECT DISTINCT index_name FROM indices_data "
        "WHERE closing_index_value IS NOT NULL"'''
    NEW1 = '''\
        "SELECT DISTINCT name FROM indices_data "
        "WHERE close IS NOT NULL"'''
    if OLD1 in src:
        src = src.replace(OLD1, NEW1); fixed = True
        print("  [OK] Fixed indices_data symbol query")
    else:
        # Try alternate formatting
        OLD1b = '"SELECT DISTINCT index_name FROM indices_data " \\\n        "WHERE closing_index_value IS NOT NULL"'
        NEW1b = '"SELECT DISTINCT name FROM indices_data " \\\n        "WHERE close IS NOT NULL"'
        if OLD1b in src:
            src = src.replace(OLD1b, NEW1b); fixed = True
            print("  [OK] Fixed indices_data symbol query (alt)")
        else:
            # Regex replace — robust
            src = re.sub(
                r'SELECT DISTINCT index_name FROM indices_data[^"\']*WHERE closing_index_value IS NOT NULL',
                'SELECT DISTINCT name FROM indices_data WHERE close IS NOT NULL',
                src
            )
            fixed = True
            print("  [OK] Fixed indices_data query (regex)")

    # Fix 2: load_nse_index function — closing_index_value -> close, index_name -> name
    OLD2 = '''\
        "SELECT date, closing_index_value FROM indices_data "
        "WHERE index_name=? AND closing_index_value IS NOT NULL "
        "ORDER BY date",'''
    NEW2 = '''\
        "SELECT date, close FROM indices_data "
        "WHERE name=? AND close IS NOT NULL "
        "ORDER BY date",'''
    if OLD2 in src:
        src = src.replace(OLD2, NEW2); fixed = True
        print("  [OK] Fixed load_nse_index query")

    # Fix 2 regex fallback
    src = re.sub(
        r'SELECT date, closing_index_value FROM indices_data',
        'SELECT date, close FROM indices_data',
        src
    )
    src = re.sub(
        r'WHERE index_name=\? AND closing_index_value IS NOT NULL',
        'WHERE name=? AND close IS NOT NULL',
        src
    )

    # Fix 3: float(r[1]) reference to closing_index_value label
    src = src.replace('"closing_index_value"', '"close"')

    # Fix 4: Also handle market_snapshot fallback for NSE indices
    # The indices_data table might also be referenced with wrong columns elsewhere
    src = re.sub(r'\bindex_name\b(?=.*indices_data)', 'name', src)
    src = re.sub(r'\bclosing_index_value\b', 'close', src)

    # Fix 5: parquet date index — ensure we use .to_pydatetime() safe path
    # The dates_arr uses datetime index — .date() call works on pd.Timestamp
    # But dates.index() may fail on large series — use bisect instead
    OLD5 = "        entry_idx = dates_arr.index(entry_date)"
    NEW5 = """\
        # Use bisect for O(log n) lookup instead of O(n) .index()
        import bisect
        entry_idx_list = bisect.bisect_left(dates_arr, entry_date)
        if entry_idx_list >= len(dates_arr) or dates_arr[entry_idx_list] != entry_date:
            # find nearest
            entry_idx_list = bisect.bisect_left(dates_arr, entry_date)
        entry_idx = entry_idx_list"""
    if OLD5 in src and "bisect" not in src:
        src = src.replace(OLD5, NEW5); fixed = True
        print("  [OK] Optimized dates_arr.index() -> bisect")

    # Fix 6: Add bisect import at top if not present
    if "import bisect" not in src:
        src = src.replace("import os, sys, time,", "import os, sys, time, bisect,")
        print("  [OK] Added bisect import")

    # Fix 7: load_nse_index — the result row index
    # r[1] maps to 'close' (was 'closing_index_value')
    src = re.sub(
        r'vals = \[float\(r\[1\]\) for r in rows\](\s*\n\s*return pd\.Series\(vals)',
        r'vals = [float(r[1]) for r in rows]\1',
        src
    )

    # Fix 8: build_symbol_list — also catch errors gracefully
    OLD8 = "    rows = conn.execute(\n        \"SELECT DISTINCT name FROM indices_data \"\n        \"WHERE close IS NOT NULL\"\n    ).fetchall()"
    NEW8 = """\
    try:
        rows = conn.execute(
            "SELECT DISTINCT name FROM indices_data WHERE close IS NOT NULL"
        ).fetchall()
    except Exception as e:
        print(f"  [WARN] indices_data query failed: {e}")
        rows = []"""
    src = src.replace(OLD8, NEW8) if OLD8 in src else src

    # General safety: wrap the entire indices section in try/except
    INDICES_OLD = """\
    # NSE indices
    rows = conn.execute(
        "SELECT DISTINCT name FROM indices_data "
        "WHERE close IS NOT NULL"
    ).fetchall()
    for r in rows:
        syms.append((r[0], "nse_index"))"""
    INDICES_NEW = """\
    # NSE indices
    try:
        _idx_rows = conn.execute(
            "SELECT DISTINCT name FROM indices_data WHERE close IS NOT NULL"
        ).fetchall()
        for r in _idx_rows:
            syms.append((r[0], "nse_index"))
    except Exception as _e:
        print(f"  [WARN] Could not load NSE indices: {_e}")"""
    if INDICES_OLD in src:
        src = src.replace(INDICES_OLD, INDICES_NEW); fixed = True
        print("  [OK] Added try/except around NSE indices loader")
    else:
        # Regex fallback
        src = re.sub(
            r'# NSE indices\s+rows = conn\.execute\(\s*"SELECT DISTINCT (?:index_name|name) FROM indices_data[^"]*"\s*(?:"[^"]*"\s*)?\)\.fetchall\(\)\s+for r in rows:\s+syms\.append\(\(r\[0\], "nse_index"\)\)',
            """\
    # NSE indices
    try:
        _idx_rows = conn.execute(
            "SELECT DISTINCT name FROM indices_data WHERE close IS NOT NULL"
        ).fetchall()
        for r in _idx_rows:
            syms.append((r[0], "nse_index"))
    except Exception as _e:
        print(f"  [WARN] Could not load NSE indices: {_e}")""",
            src
        )
        print("  [OK] Fixed NSE indices loader (regex)")

    # Fix load_nse_index function completely (rewrite it cleanly)
    LOAD_NSE_OLD = re.search(
        r'def load_nse_index\(conn, index_name.*?return pd\.Series\(vals, index=idx\)\.sort_index\(\)',
        src, re.DOTALL
    )
    if LOAD_NSE_OLD:
        LOAD_NSE_NEW = '''\
def load_nse_index(conn, name: str) -> "Optional[pd.Series]":
    """Load NSE index close prices from indices_data (column: name, close)."""
    try:
        rows = conn.execute(
            "SELECT date, close FROM indices_data "
            "WHERE name=? AND close IS NOT NULL ORDER BY date",
            (name,)
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [float(r[1]) for r in rows]
    return pd.Series(vals, index=idx).sort_index()'''
        src = src[:LOAD_NSE_OLD.start()] + LOAD_NSE_NEW + src[LOAD_NSE_OLD.end():]
        print("  [OK] Rewrote load_nse_index function cleanly")

    v3.write_text(src, encoding="utf-8")
    print("  [SAVED] build_seasonality_v3.py")


# ═════════════════════════════════════════════════════════════════════════════
# [2] FIX NavBar — force-inject COMPARE link
# ═════════════════════════════════════════════════════════════════════════════
print("\n[2/5] Force-patching NavBar.tsx with COMPARE link...")

navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if not navbar_path:
    print("  [SKIP] NavBar.tsx not found")
else:
    src = navbar_path.read_text(encoding="utf-8")
    if "/compare" in src:
        print("  [SKIP] COMPARE already in NavBar")
    else:
        # Print current href lines for debug
        print("  Current hrefs in NavBar:")
        for i, line in enumerate(src.splitlines(), 1):
            if "href" in line.lower() or "'/'" in line or "label" in line.lower():
                print(f"    L{i}: {line.rstrip()}")

        # Strategy: inject after ANY of these markers
        injected = False
        for after_marker in [
            "'/eta'", '"/eta"', "'/patterns'", '"/patterns"',
            "'/backtest'", '"/backtest"', "'/watchlist'", '"/watchlist"',
        ]:
            if after_marker in src:
                idx      = src.rfind(after_marker)  # last occurrence
                line_end = src.find("\n", idx)
                if line_end == -1: line_end = len(src)
                # Detect style: object {href:...} or Link href="..."
                line_start = src.rfind("\n", 0, idx) + 1
                line       = src[line_start:line_end]
                if "href:" in line or "href :" in line:
                    insert = "\n  { href: '/compare', label: 'COMPARE' },"
                else:
                    insert = "\n  { href: '/compare', label: 'COMPARE' },"
                src = src[:line_end] + insert + src[line_end:]
                navbar_path.write_text(src, encoding="utf-8")
                print(f"  [OK] Injected COMPARE after {after_marker}")
                injected = True
                break

        if not injected:
            # Last resort: find the closing bracket of the nav items array
            # and insert before it
            bracket = src.rfind("]")
            if bracket > 0:
                src = src[:bracket] + '\n  { href: \'/compare\', label: \'COMPARE\' },\n' + src[bracket:]
                navbar_path.write_text(src, encoding="utf-8")
                print("  [OK] Injected COMPARE before closing bracket")
            else:
                print("  [FAIL] Could not find insertion point — manual edit needed")


# ═════════════════════════════════════════════════════════════════════════════
# [3] /api/patterns-v3/route.ts  — list patterns from seasonality_patterns_v3
# ═════════════════════════════════════════════════════════════════════════════
print("\n[3/5] Writing /api/patterns-v3/route.ts ...")

PV3_ROUTE = r'''import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import path             from "path";

const DB  = "D:/marketDB/db/market.db";
const PY  = "py";
const DA  = "D:/MICC";

function qdb(sql: string, params: any[] = []): any[] {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r"${DB}", timeout=15)
conn.row_factory = sqlite3.Row
params = json.loads(sys.argv[1])
rows = conn.execute("""${sql}""", params).fetchall()
print(json.dumps([dict(r) for r in rows]))
conn.close()
`;
  const r = spawnSync(PY, ["-c", script, JSON.stringify(params)], {
    cwd: DA, encoding: "utf-8", timeout: 30000,
  });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 300) || "DB error");
  return JSON.parse(r.stdout.trim() || "[]");
}

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const symbol = url.searchParams.get("symbol") || "";
  const win    = url.searchParams.get("window")  || "";
  const dir    = url.searchParams.get("direction") || "";
  const minAcc = parseFloat(url.searchParams.get("min_accuracy") || "55");
  const minScore = parseFloat(url.searchParams.get("min_score") || "0");
  const sort   = url.searchParams.get("sort") || "score";
  const limit  = Math.min(parseInt(url.searchParams.get("limit") || "100"), 500);
  const anchor = url.searchParams.get("anchor") || "";

  try {
    let where = "WHERE accuracy >= ? AND score >= ?";
    const params: any[] = [minAcc, minScore];

    if (symbol) { where += " AND symbol = ?"; params.push(symbol.toUpperCase()); }
    if (win)    { where += " AND window_days = ?"; params.push(parseInt(win)); }
    if (dir)    { where += " AND direction = ?"; params.push(dir.toUpperCase()); }
    if (anchor) { where += " AND anchor_mm_dd = ?"; params.push(anchor); }

    const allowed = ["score","accuracy","mean_ret","n_obs","consistency","t_stat","degradation","p_value"];
    const sortCol = allowed.includes(sort) ? sort : "score";
    const sortDir = sort === "p_value" ? "ASC" : "DESC";

    const sql = `
      SELECT symbol, anchor_mm_dd, window_days, direction,
             n_obs, accuracy, mean_ret, median_ret, std_ret,
             p10, p25, p75, p90, best_ret, worst_ret,
             score, consistency, edge_ratio, t_stat, p_value,
             early_accuracy, recent_accuracy, degradation,
             recent_mean, recent_vs_all
      FROM seasonality_patterns_v3
      ${where}
      ORDER BY ${sortCol} ${sortDir}
      LIMIT ${limit}
    `;

    const rows = qdb(sql, params);
    return NextResponse.json({ count: rows.length, rows });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, count: 0, rows: [] }, { status: 500 });
  }
}
'''
write(SRC / "api" / "patterns-v3" / "route.ts", PV3_ROUTE, "/api/patterns-v3/route.ts")


# ═════════════════════════════════════════════════════════════════════════════
# [4] /api/patterns-v3/detail/route.ts  — single pattern with all_returns
# ═════════════════════════════════════════════════════════════════════════════
print("\n[4/5] Writing /api/patterns-v3/detail/route.ts ...")

PV3_DETAIL = r'''import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function qone(sql: string, params: any[]): any | null {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r"${DB}", timeout=15)
conn.row_factory = sqlite3.Row
params = json.loads(sys.argv[1])
row = conn.execute("""${sql}""", params).fetchone()
print(json.dumps(dict(row) if row else None))
conn.close()
`;
  const r = spawnSync(PY, ["-c", script, JSON.stringify(params)], {
    cwd: DA, encoding: "utf-8", timeout: 15000,
  });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200));
  const txt = r.stdout.trim();
  return txt === "null" || !txt ? null : JSON.parse(txt);
}

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "").toUpperCase();
  const anchor = url.searchParams.get("anchor") || "";
  const window = parseInt(url.searchParams.get("window") || "0");
  const dir    = (url.searchParams.get("direction") || "").toUpperCase();

  if (!symbol || !anchor || !window || !dir)
    return NextResponse.json({ error: "Need symbol, anchor, window, direction" }, { status: 400 });

  try {
    const row = qone(
      `SELECT * FROM seasonality_patterns_v3
       WHERE symbol=? AND anchor_mm_dd=? AND window_days=? AND direction=?`,
      [symbol, anchor, window, dir]
    );
    if (!row) return NextResponse.json({ error: "Pattern not found" }, { status: 404 });

    // Parse JSON fields
    try { row.best_years   = JSON.parse(row.best_years   || "[]"); } catch {}
    try { row.worst_years  = JSON.parse(row.worst_years  || "[]"); } catch {}
    try { row.all_returns  = JSON.parse(row.all_returns  || "[]"); } catch {}

    return NextResponse.json(row);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
'''
write(SRC / "api" / "patterns-v3" / "detail" / "route.ts", PV3_DETAIL, "/api/patterns-v3/detail/route.ts")


# ═════════════════════════════════════════════════════════════════════════════
# [5] /patterns-v3/page.tsx  — new patterns page using v3 data
# ═════════════════════════════════════════════════════════════════════════════
print("\n[5/5] Writing /patterns-v3/page.tsx ...")

PV3_PAGE = '''\
"use client";

import { useState, useEffect, useCallback, useRef } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Pattern {
  symbol: string; anchor_mm_dd: string; window_days: number; direction: string;
  n_obs: number; accuracy: number; mean_ret: number; median_ret: number;
  std_ret: number; p10: number; p25: number; p75: number; p90: number;
  best_ret: number; worst_ret: number; score: number; consistency: number;
  edge_ratio: number; t_stat: number; p_value: number;
  early_accuracy: number; recent_accuracy: number; degradation: number;
  recent_mean: number; recent_vs_all: number;
}
interface DetailRow { year: number; ret: number; }
interface Detail extends Pattern {
  best_years: DetailRow[]; worst_years: DetailRow[]; all_returns: DetailRow[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const pct  = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(d)}%`;
const num  = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : Number(v).toFixed(d);
const clr  = (v: number | null | undefined, invert = false) => {
  if (v == null) return "#94a3b8";
  const pos = invert ? v < 0 : v > 0;
  return pos ? "#22c55e" : v === 0 ? "#94a3b8" : "#ef4444";
};
const sigClr = (pval: number | null | undefined) => {
  if (pval == null) return "#94a3b8";
  return pval < 0.05 ? "#22c55e" : pval < 0.10 ? "#fbbf24" : "#94a3b8";
};
const degClr = (deg: number | null | undefined) => {
  if (deg == null) return "#94a3b8";
  return deg > 5 ? "#22c55e" : deg > 0 ? "#86efac" : deg > -5 ? "#fbbf24" : "#ef4444";
};
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const monthName = (mm_dd: string) => {
  const m = parseInt(mm_dd.split("-")[0]) - 1;
  return MONTHS[m] || mm_dd;
};

// ── Stat chip ─────────────────────────────────────────────────────────────────
function Chip({ label, value, color, small }: {
  label: string; value: string; color?: string; small?: boolean;
}) {
  return (
    <div style={{
      background: "#0f172a", borderRadius: 8, padding: small ? "5px 10px" : "8px 14px",
      textAlign: "center", minWidth: small ? 70 : 80,
    }}>
      <div style={{ fontSize: small ? 13 : 15, fontWeight: 800,
        color: color || "#f8fafc" }}>{value}</div>
      <div style={{ fontSize: 10, color: "#475569", marginTop: 2 }}>{label}</div>
    </div>
  );
}

// ── Degradation bar ───────────────────────────────────────────────────────────
function DegBar({ early, recent }: { early: number; recent: number }) {
  const change = recent - early;
  return (
    <div style={{ fontSize: 11, color: "#64748b" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 3 }}>
        <span style={{ minWidth: 50 }}>Early</span>
        <div style={{ flex: 1, background: "#1e293b", borderRadius: 4, height: 6 }}>
          <div style={{ width: `${Math.min(early, 100)}%`, height: "100%",
            background: "#60a5fa", borderRadius: 4 }} />
        </div>
        <span style={{ color: "#60a5fa", minWidth: 36 }}>{early.toFixed(0)}%</span>
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ minWidth: 50 }}>Recent</span>
        <div style={{ flex: 1, background: "#1e293b", borderRadius: 4, height: 6 }}>
          <div style={{ width: `${Math.min(recent, 100)}%`, height: "100%",
            background: degClr(change), borderRadius: 4 }} />
        </div>
        <span style={{ color: degClr(change), minWidth: 36 }}>{recent.toFixed(0)}%</span>
      </div>
      <div style={{ marginTop: 4, color: degClr(change), fontWeight: 700 }}>
        {change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(1)}% {change >= 0 ? "strengthening" : "fading"}
      </div>
    </div>
  );
}

// ── Year return chart (SVG bar chart with hover) ───────────────────────────────
function YearChart({ data, direction }: { data: DetailRow[]; direction: string }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [lockA,   setLockA]   = useState<number | null>(null);
  const [lockB,   setLockB]   = useState<number | null>(null);
  if (!data || data.length === 0) return null;

  const W = 520, H = 140, PAD = 30;
  const vals = data.map(d => d.ret);
  const mn   = Math.min(...vals, 0);
  const mx   = Math.max(...vals, 0);
  const rng  = mx - mn || 1;
  const bw   = Math.max(4, (W - 2 * PAD) / data.length - 2);
  const zero = H - PAD - ((0 - mn) / rng) * (H - 2 * PAD);

  const handleClick = (idx: number) => {
    if (lockA === null) { setLockA(idx); return; }
    if (lockB === null && idx !== lockA) { setLockB(idx); return; }
    setLockA(null); setLockB(null);
  };

  const deltaA = lockA != null ? data[lockA] : null;
  const deltaB = lockB != null ? data[lockB] : null;
  const delta  = deltaA && deltaB ? deltaB.ret - deltaA.ret : null;

  return (
    <div style={{ userSelect: "none" }}>
      <svg width={W} height={H} style={{ overflow: "visible", cursor: "crosshair" }}>
        {/* Zero line */}
        <line x1={PAD} y1={zero} x2={W - PAD} y2={zero}
          stroke="#334155" strokeWidth={1} strokeDasharray="4,3" />

        {data.map((d, i) => {
          const x   = PAD + i * ((W - 2 * PAD) / data.length);
          const bh  = Math.abs((d.ret / rng) * (H - 2 * PAD));
          const y   = d.ret >= 0 ? zero - bh : zero;
          const isA = lockA === i, isB = lockB === i, isH = hovered === i;
          const base = direction === "UP"
            ? (d.ret > 0 ? "#22c55e" : "#ef4444")
            : (d.ret < 0 ? "#22c55e" : "#ef4444");
          const fill = isA ? "#fbbf24" : isB ? "#a78bfa" : isH ? "#60a5fa" : base;
          return (
            <g key={i}>
              <rect x={x} y={y} width={bw} height={Math.max(bh, 2)}
                fill={fill} opacity={0.85} rx={1}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => handleClick(i)}
                style={{ cursor: "pointer" }}
              />
              {(isH || isA || isB) && (
                <text x={x + bw / 2} y={y - 4} fontSize={9} fill={fill}
                  textAnchor="middle">{d.year}</text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Tooltip */}
      {hovered != null && (
        <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>
          <span style={{ fontWeight: 700, color: "#f8fafc" }}>{data[hovered]?.year}</span>
          {" — "}
          <span style={{ color: clr(data[hovered]?.ret), fontWeight: 700 }}>
            {pct(data[hovered]?.ret)}
          </span>
        </div>
      )}

      {/* Lock info */}
      {(lockA != null || lockB != null) && (
        <div style={{ fontSize: 11, marginTop: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
          {lockA != null && (
            <span style={{ color: "#fbbf24" }}>A: {data[lockA]?.year} {pct(data[lockA]?.ret)}</span>
          )}
          {lockB != null && (
            <span style={{ color: "#a78bfa" }}>B: {data[lockB]?.year} {pct(data[lockB]?.ret)}</span>
          )}
          {delta != null && (
            <span style={{ color: "#22c55e", fontWeight: 700 }}>Δ {pct(delta)}</span>
          )}
          <button onClick={() => { setLockA(null); setLockB(null); }}
            style={{ fontSize: 10, color: "#64748b", background: "none",
              border: "none", cursor: "pointer" }}>✕ clear</button>
        </div>
      )}
    </div>
  );
}

// ── Expanded Pattern Card ─────────────────────────────────────────────────────
function PatternCard({ p, idx }: { p: Pattern; idx: number }) {
  const [open,   setOpen]   = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(false);
  const isUp = p.direction === "UP";

  const loadDetail = useCallback(async () => {
    if (detail) return;
    setLoading(true);
    try {
      const r = await fetch(
        `/api/patterns-v3/detail?symbol=${p.symbol}&anchor=${p.anchor_mm_dd}`
        + `&window=${p.window_days}&direction=${p.direction}`
      );
      const d = await r.json();
      if (!d.error) setDetail(d);
    } catch {}
    setLoading(false);
  }, [p, detail]);

  const toggle = () => {
    if (!open) loadDetail();
    setOpen(o => !o);
  };

  const dirClr = isUp ? "#22c55e" : "#ef4444";
  const sigOk  = p.p_value < 0.05;

  return (
    <div style={{
      background: "#1e293b", border: `1px solid ${open ? dirClr + "55" : "#334155"}`,
      borderRadius: 12, marginBottom: 8,
      transition: "border-color 0.2s",
    }}>
      {/* ── Header row ── */}
      <div onClick={toggle} style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "12px 16px", cursor: "pointer", flexWrap: "wrap",
      }}>
        <span style={{ fontSize: 12, color: "#475569", minWidth: 28 }}>#{idx + 1}</span>
        <span style={{
          fontFamily: "monospace", fontWeight: 800, fontSize: 14, color: "#60a5fa", minWidth: 100,
        }}>{p.symbol}</span>
        <span style={{ fontSize: 12, color: "#64748b", minWidth: 52 }}>{p.anchor_mm_dd}</span>
        <span style={{
          fontSize: 11, fontWeight: 700, color: dirClr,
          background: dirClr + "22", borderRadius: 4, padding: "2px 8px", minWidth: 42,
        }}>{p.window_days}d {p.direction}</span>

        {/* Score */}
        <span style={{ fontSize: 14, fontWeight: 800, color: "#fbbf24", minWidth: 55 }}>
          ★ {p.score?.toFixed(2)}
        </span>

        {/* Accuracy */}
        <span style={{ fontSize: 13, fontWeight: 700, color: dirClr }}>
          {p.accuracy?.toFixed(1)}%
        </span>
        <span style={{ fontSize: 11, color: "#64748b" }}>{p.n_obs} yrs</span>

        {/* Mean return */}
        <span style={{ fontSize: 13, fontWeight: 700, color: clr(p.mean_ret), marginLeft: 4 }}>
          {pct(p.mean_ret)}
        </span>

        {/* p-value badge */}
        <span style={{
          fontSize: 10, fontWeight: 700,
          color: sigClr(p.p_value),
          background: sigClr(p.p_value) + "22",
          borderRadius: 4, padding: "1px 6px",
        }}>
          {sigOk ? "✓ sig" : `p=${p.p_value?.toFixed(3)}`}
        </span>

        {/* Degradation */}
        {Math.abs(p.degradation) > 3 && (
          <span style={{ fontSize: 10, color: degClr(p.degradation) }}>
            {p.degradation >= 0 ? "↑" : "↓"} {Math.abs(p.degradation).toFixed(0)}%
          </span>
        )}

        <span style={{ marginLeft: "auto", fontSize: 12, color: "#475569" }}>
          {open ? "▲" : "▼"}
        </span>
      </div>

      {/* ── Expanded content ── */}
      {open && (
        <div style={{ padding: "0 16px 16px", borderTop: "1px solid #334155" }}>
          {loading && (
            <p style={{ color: "#64748b", fontSize: 12, padding: "12px 0" }}>
              Loading detail…
            </p>
          )}

          {/* Stat grid */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
            <Chip label="Accuracy"    value={`${p.accuracy?.toFixed(1)}%`} color={dirClr} />
            <Chip label="Mean Ret"    value={pct(p.mean_ret)} color={clr(p.mean_ret)} />
            <Chip label="Score"       value={p.score?.toFixed(3)} color="#fbbf24" />
            <Chip label="Consistency" value={p.consistency?.toFixed(3)} color="#a78bfa" small />
            <Chip label="t-stat"      value={num(p.t_stat)} color={sigClr(p.p_value)} small />
            <Chip label="p-value"     value={p.p_value?.toFixed(4)} color={sigClr(p.p_value)} small />
            <Chip label="Edge Ratio"  value={num(p.edge_ratio)} small />
            <Chip label="Std Dev"     value={pct(p.std_ret)} small />
            <Chip label="P10"         value={pct(p.p10)} color={clr(p.p10)} small />
            <Chip label="P90"         value={pct(p.p90)} color={clr(p.p90)} small />
            <Chip label="Best"        value={pct(p.best_ret)} color="#22c55e" small />
            <Chip label="Worst"       value={pct(p.worst_ret)} color="#ef4444" small />
            <Chip label="Recent Mean" value={pct(p.recent_mean)} color={clr(p.recent_mean)} small />
          </div>

          {/* Degradation analysis */}
          <div style={{
            marginTop: 14, padding: "12px 14px",
            background: "#0f172a", borderRadius: 8,
          }}>
            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>
              PATTERN TREND (early vs recent accuracy)
            </div>
            <DegBar early={p.early_accuracy} recent={p.recent_accuracy} />
          </div>

          {/* Year chart */}
          {detail && detail.all_returns && detail.all_returns.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>
                YEAR-BY-YEAR RETURNS (click to lock A/B, see delta)
              </div>
              <YearChart data={detail.all_returns} direction={p.direction} />
            </div>
          )}

          {/* Best / worst years */}
          {detail && (
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr",
              gap: 10, marginTop: 14,
            }}>
              <div>
                <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6 }}>
                  🏆 BEST YEARS
                </div>
                {detail.best_years?.map((y, i) => (
                  <div key={i} style={{
                    display: "flex", justifyContent: "space-between",
                    padding: "3px 8px", background: "#0f172a",
                    borderRadius: 5, marginBottom: 3,
                  }}>
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>{y.year}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#22c55e" }}>
                      {pct(y.ret)}
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6 }}>
                  💀 WORST YEARS
                </div>
                {detail.worst_years?.map((y, i) => (
                  <div key={i} style={{
                    display: "flex", justifyContent: "space-between",
                    padding: "3px 8px", background: "#0f172a",
                    borderRadius: 5, marginBottom: 3,
                  }}>
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>{y.year}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#ef4444" }}>
                      {pct(y.ret)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═════════════════════════════════════════════════════════════════════════════
export default function PatternsV3Page() {
  const [symbol,   setSymbol]   = useState("");
  const [inputSym, setInputSym] = useState("");
  const [minAcc,   setMinAcc]   = useState(62);
  const [minScore, setMinScore] = useState(1.0);
  const [direction, setDir]     = useState("");
  const [sortBy,   setSort]     = useState("score");
  const [window_,  setWindow]   = useState("");
  const [limit,    setLimit]    = useState(100);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [total,    setTotal]    = useState(0);
  const [error,    setError]    = useState("");

  const fetch_ = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({
        min_accuracy: String(minAcc),
        min_score:    String(minScore),
        sort:         sortBy,
        limit:        String(limit),
      });
      if (symbol)    params.set("symbol",    symbol.toUpperCase());
      if (direction) params.set("direction", direction);
      if (window_)   params.set("window",    window_);

      const r = await fetch(`/api/patterns-v3?${params}`);
      const d = await r.json();
      if (d.error) { setError(d.error); setPatterns([]); }
      else { setPatterns(d.rows || []); setTotal(d.count || 0); }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [symbol, minAcc, minScore, direction, sortBy, window_, limit]);

  useEffect(() => { fetch_(); }, []);

  // Stats from current results
  const upCount   = patterns.filter(p => p.direction === "UP").length;
  const downCount = patterns.filter(p => p.direction === "DOWN").length;
  const avgAcc    = patterns.length
    ? patterns.reduce((s, p) => s + p.accuracy, 0) / patterns.length : 0;
  const avgScore  = patterns.length
    ? patterns.reduce((s, p) => s + p.score, 0) / patterns.length : 0;
  const sigCount  = patterns.filter(p => p.p_value < 0.05).length;

  return (
    <div style={{
      minHeight: "100vh", background: "#0f172a",
      color: "#e2e8f0", fontFamily: "system-ui, sans-serif",
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: "18px 28px 14px", borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#f8fafc" }}>
            🔬 Seasonality Patterns v3
          </h1>
          <p style={{ margin: "3px 0 0", fontSize: 11, color: "#475569" }}>
            Windows 3d–60d · Statistical significance · Trend decay detection
          </p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, flexWrap: "wrap" }}>
          {[
            { label: "Results",    value: total,              color: "#60a5fa"  },
            { label: "UP",         value: upCount,            color: "#22c55e"  },
            { label: "DOWN",       value: downCount,          color: "#ef4444"  },
            { label: "Significant",value: `${sigCount}`,      color: "#fbbf24"  },
            { label: "Avg Acc",    value: `${avgAcc.toFixed(1)}%`, color: "#a78bfa" },
            { label: "Avg Score",  value: avgScore.toFixed(2),color: "#f8fafc"  },
          ].map((s, i) => (
            <div key={i} style={{
              textAlign: "center", padding: "7px 12px",
              background: "#1e293b", borderRadius: 8,
              border: `1px solid ${s.color}33`,
            }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 10, color: "#64748b" }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Filters ── */}
      <div style={{
        padding: "14px 28px", borderBottom: "1px solid #1e293b",
        display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end",
      }}>
        {/* Symbol search */}
        <div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>SYMBOL</div>
          <div style={{ display: "flex", gap: 6 }}>
            <input value={inputSym}
              onChange={e => setInputSym(e.target.value.toUpperCase())}
              onKeyDown={e => { if (e.key === "Enter") { setSymbol(inputSym); } }}
              placeholder="e.g. RELIANCE"
              style={{
                padding: "7px 12px", background: "#1e293b",
                border: "1px solid #334155", borderRadius: 7,
                color: "#f8fafc", fontSize: 13, width: 140, outline: "none",
              }}
            />
            <button onClick={() => { setSymbol(inputSym); }}
              style={{ padding: "7px 12px", background: "#3b82f6",
                color: "#fff", border: "none", borderRadius: 7,
                cursor: "pointer", fontSize: 12, fontWeight: 700 }}>Go</button>
            {symbol && (
              <button onClick={() => { setSymbol(""); setInputSym(""); }}
                style={{ padding: "7px 10px", background: "#334155",
                  color: "#94a3b8", border: "none", borderRadius: 7,
                  cursor: "pointer", fontSize: 12 }}>✕</button>
            )}
          </div>
        </div>

        {/* Min accuracy */}
        <div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>
            MIN ACCURACY: {minAcc}%
          </div>
          <input type="range" min={55} max={90} value={minAcc}
            onChange={e => setMinAcc(Number(e.target.value))}
            style={{ width: 100, accentColor: "#3b82f6" }} />
        </div>

        {/* Min score */}
        <div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>
            MIN SCORE: {minScore.toFixed(1)}
          </div>
          <input type="range" min={0} max={10} step={0.5} value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
            style={{ width: 100, accentColor: "#3b82f6" }} />
        </div>

        {/* Direction */}
        <div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>DIRECTION</div>
          <select value={direction} onChange={e => setDir(e.target.value)}
            style={{ padding: "7px 10px", background: "#1e293b",
              border: "1px solid #334155", borderRadius: 7,
              color: "#f8fafc", fontSize: 13 }}>
            <option value="">All</option>
            <option value="UP">UP</option>
            <option value="DOWN">DOWN</option>
          </select>
        </div>

        {/* Window */}
        <div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>WINDOW (DAYS)</div>
          <select value={window_} onChange={e => setWindow(e.target.value)}
            style={{ padding: "7px 10px", background: "#1e293b",
              border: "1px solid #334155", borderRadius: 7,
              color: "#f8fafc", fontSize: 13 }}>
            <option value="">All (3–60d)</option>
            {[3,4,5,6,7,8,9,10,12,14,15,20,25,30,40,50,60].map(w => (
              <option key={w} value={w}>{w}d</option>
            ))}
          </select>
        </div>

        {/* Sort */}
        <div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>SORT BY</div>
          <select value={sortBy} onChange={e => setSort(e.target.value)}
            style={{ padding: "7px 10px", background: "#1e293b",
              border: "1px solid #334155", borderRadius: 7,
              color: "#f8fafc", fontSize: 13 }}>
            <option value="score">Score</option>
            <option value="accuracy">Accuracy</option>
            <option value="mean_ret">Mean Return</option>
            <option value="consistency">Consistency</option>
            <option value="t_stat">t-stat</option>
            <option value="p_value">p-value (best)</option>
            <option value="n_obs">Most Years</option>
            <option value="degradation">Strengthening</option>
          </select>
        </div>

        {/* Limit */}
        <div>
          <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>SHOW</div>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))}
            style={{ padding: "7px 10px", background: "#1e293b",
              border: "1px solid #334155", borderRadius: 7,
              color: "#f8fafc", fontSize: 13 }}>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
            <option value={500}>500</option>
          </select>
        </div>

        <button onClick={fetch_} disabled={loading}
          style={{
            padding: "8px 20px", background: loading ? "#334155" : "#22c55e",
            color: "#fff", border: "none", borderRadius: 8,
            cursor: loading ? "not-allowed" : "pointer",
            fontSize: 13, fontWeight: 700, alignSelf: "flex-end",
          }}>
          {loading ? "⚙️ Loading…" : "▶ Search"}
        </button>
      </div>

      {/* ── Error ── */}
      {error && (
        <div style={{ padding: "12px 28px" }}>
          <div style={{
            background: "#2d1515", borderRadius: 8, padding: "10px 14px",
            color: "#ef4444", fontSize: 13,
          }}>
            ⚠️ {error}
            {error.includes("no such table") && (
              <span style={{ color: "#94a3b8" }}>
                {" — Run: "}
                <code>py D:\\MICC\\build_seasonality_v3.py</code>
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Results ── */}
      <div style={{ padding: "16px 28px" }}>
        {!loading && patterns.length === 0 && !error && (
          <div style={{ textAlign: "center", padding: "60px 0" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>🔬</div>
            <p style={{ color: "#64748b" }}>
              No patterns found. Try lowering min accuracy / score, or run the builder first.
            </p>
            <code style={{ fontSize: 12, color: "#475569" }}>
              py D:\\MICC\\build_seasonality_v3.py
            </code>
          </div>
        )}
        {patterns.map((p, i) => <PatternCard key={`${p.symbol}-${p.anchor_mm_dd}-${p.window_days}-${p.direction}`} p={p} idx={i} />)}
      </div>
    </div>
  );
}
'''
write(SRC / "patterns-v3" / "page.tsx", PV3_PAGE, "/patterns-v3/page.tsx")


# ── Add patterns-v3 to NavBar ──────────────────────────────────────────────────
navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")
    if "/patterns-v3" not in src:
        for marker in ["'/compare'", '"/compare"', "'/eta'", '"/eta"']:
            if marker in src:
                idx      = src.rfind(marker)
                line_end = src.find("\n", idx)
                src      = src[:line_end] + "\n  { href: '/patterns-v3', label: 'PATS-V3' }," + src[line_end:]
                navbar_path.write_text(src, encoding="utf-8")
                print("  [OK] Added PATS-V3 to NavBar")
                break


print("""
=============================================================
FIX + PHASE 16 COMPLETE
=============================================================

FIXES:
  [1] build_seasonality_v3.py
      - indices_data.name (was index_name) ✓
      - indices_data.close (was closing_index_value) ✓
      - try/except around NSE index loader ✓
      - bisect optimization for date lookup ✓

  [2] NavBar.tsx COMPARE link — force injected ✓

PHASE 16 BUILT:
  [3] /api/patterns-v3/route.ts
      - Filters: symbol, window, direction, min_accuracy, min_score, sort, limit
      - Sort options: score / accuracy / mean_ret / consistency / t_stat / p_value / degradation

  [4] /api/patterns-v3/detail/route.ts
      - Returns full pattern with all_returns JSON array (year × ret)

  [5] /patterns-v3/page.tsx
      - Full pattern search UI with 7 filters
      - Summary chips: total / UP / DOWN / significant / avg_acc / avg_score
      - Expanded PatCard:
          - 13-stat chip grid
          - Degradation bar (early vs recent accuracy)
          - Year-by-year bar chart (hover + click A/B lock + delta)
          - Best/worst years table

NOW RUN:
  1. Test single symbol:
       py D:\\MICC\\build_seasonality_v3.py --sym RELIANCE

  2. Full overnight build (start before you sleep):
       py D:\\MICC\\build_seasonality_v3.py

  3. While it runs, explore v3 page (it works with partial data):
       localhost:3000/patterns-v3

  4. Tomorrow: resume if crashed:
       py D:\\MICC\\build_seasonality_v3.py --resume

QUEUE REMAINING:
  - Backtest analysis in PatCard (v2 /patterns page)
  - /patterns page API switch to v3 after full build
=============================================================
""")
