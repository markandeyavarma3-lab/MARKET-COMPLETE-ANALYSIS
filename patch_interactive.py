"""
MICC Dashboard - Interactive Upgrade
Run from DATA-ANALYSIS:  py patch_interactive.py

New features:
1. Alpha: Top/Bottom 10 indices with duration bar (1D,5D,7D,10D,20D,1M,3M)
2. Beta + Gamma: duration bar (reads from cached agent JSON window)
3. Streak leaderboard: more columns (volume, screens breakdown) + filter options
4. New API route: /api/indices for per-duration index data from SQLite
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))

def find_paths():
    for sub in ["micc-dashboard/src", "micc-dashboard"]:
        p = os.path.join(BASE, sub)
        if os.path.isdir(p):
            if os.path.isdir(os.path.join(p, "components")):
                return os.path.join(p, "app"), os.path.join(p, "components"), os.path.join(p, "lib")
    return None

paths = find_paths()
if not paths:
    print("[ERROR] micc-dashboard not found. Run: py build_dashboard.py")
    sys.exit(1)

APP, COMP, LIB = paths
print(f"[INFO] Patching: {APP}")

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.lstrip("\n"))
    print(f"  wrote: {os.path.relpath(path, BASE)}")

# ── New API route: /api/indices?days=N ────────────────────────────────────────
os.makedirs(os.path.join(APP, "api", "indices"), exist_ok=True)
w(os.path.join(APP, "api", "indices", "route.ts"), """
import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string) {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout: 30000,
      cwd: DA,
    })
    if (result.status !== 0) throw new Error(result.stderr || 'bridge error')
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) {
    console.error('[indices api]', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const days = Math.min(parseInt(searchParams.get('days') || '7'), 365)

  // Get indices performance over last N trading days from market_snapshot
  const rows = queryDb(`
    WITH date_range AS (
      SELECT DISTINCT date
      FROM market_snapshot
      ORDER BY date DESC
      LIMIT ${days + 1}
    ),
    start_snap AS (
      SELECT index_name, close as start_close
      FROM market_snapshot
      WHERE date = (SELECT MIN(date) FROM date_range)
    ),
    end_snap AS (
      SELECT index_name, close as end_close
      FROM market_snapshot
      WHERE date = (SELECT MAX(date) FROM date_range)
    )
    SELECT
      e.index_name as name,
      s.start_close,
      e.end_close,
      ROUND((e.end_close - s.start_close) / s.start_close * 100, 2) as pct_change
    FROM end_snap e
    JOIN start_snap s ON e.index_name = s.index_name
    WHERE s.start_close > 0 AND e.end_close > 0
      AND e.index_name NOT LIKE '%Inverse%'
      AND e.index_name NOT LIKE '%1x%'
      AND e.index_name NOT LIKE 'India VIX%'
    ORDER BY pct_change DESC
  `)

  const gainers = rows.slice(0, 10)
  const losers  = [...rows].reverse().slice(0, 10)

  return NextResponse.json({ gainers, losers, days, total: rows.length })
}
""")

# ── New API route: /api/streak-extended ───────────────────────────────────────
os.makedirs(os.path.join(APP, "api", "streak-extended"), exist_ok=True)
w(os.path.join(APP, "api", "streak-extended", "route.ts"), """
import { NextResponse } from 'next/server'
import { spawnSync } from 'child_process'
import path from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string) {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const result = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8',
      timeout: 30000,
      cwd: DA,
    })
    if (result.status !== 0) throw new Error(result.stderr || 'bridge error')
    const out = result.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) {
    console.error('[streak-ext api]', e.message)
    return []
  }
}

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const days    = Math.min(parseInt(searchParams.get('days') || '30'), 90)
  const sortBy  = searchParams.get('sort') || 'streak'  // streak | score | pct_chg | deliv
  const minDays = parseInt(searchParams.get('min') || '2')
  const screen  = searchParams.get('screen') || ''  // filter by screen tag

  const screenFilter = screen ? `AND screen_tags LIKE '%${screen}%'` : ''

  const orderMap: Record<string, string> = {
    streak: 'streak_days DESC, avg_score DESC',
    score:  'avg_score DESC, streak_days DESC',
    pct:    'avg_pct DESC, streak_days DESC',
    deliv:  'avg_deliv DESC, streak_days DESC',
  }
  const orderBy = orderMap[sortBy] || orderMap['streak']

  const rows = queryDb(`
    SELECT
      symbol,
      COUNT(DISTINCT run_date)              AS streak_days,
      MAX(run_date)                         AS last_seen,
      MIN(run_date)                         AS first_seen,
      ROUND(AVG(CAST(score AS REAL)), 2)    AS avg_score,
      MAX(CAST(score AS REAL))              AS max_score,
      ROUND(AVG(CAST(pct_chg AS REAL)), 2) AS avg_pct,
      MAX(CAST(pct_chg AS REAL))           AS max_pct,
      ROUND(AVG(CAST(avg_deliv_pct AS REAL)), 1) AS avg_deliv,
      SUM(CASE WHEN earnings_flag = 1 THEN 1 ELSE 0 END) AS eps_days,
      GROUP_CONCAT(DISTINCT screen_tags)    AS all_tags,
      COUNT(DISTINCT regime)                AS regime_count,
      MAX(regime)                           AS latest_regime
    FROM signals_history
    WHERE run_date >= date('now', '-${days} days')
    ${screenFilter}
    GROUP BY symbol
    HAVING streak_days >= ${minDays}
    ORDER BY ${orderBy}
    LIMIT 25
  `)

  // Get available screen tags for filter UI
  const tags = queryDb(`
    SELECT DISTINCT screen_tags, COUNT(*) as cnt
    FROM signals_history
    WHERE run_date >= date('now', '-30 days') AND screen_tags IS NOT NULL
    GROUP BY screen_tags
    ORDER BY cnt DESC
    LIMIT 20
  `)

  const stats = queryDb(`
    SELECT COUNT(*) as total_rows,
           COUNT(DISTINCT symbol) as unique_symbols,
           COUNT(DISTINCT run_date) as unique_dates,
           MAX(run_date) as latest_date
    FROM signals_history
  `)

  return NextResponse.json({ rows, tags, stats: stats[0] || {}, days, sortBy })
}
""")

print("[1/4] API routes written")

# ── DurationBar component ─────────────────────────────────────────────────────
w(os.path.join(COMP, "DurationBar.tsx"), """
"use client";

const DURATIONS = [
  { label: "1D",  days: 1  },
  { label: "3D",  days: 3  },
  { label: "5D",  days: 5  },
  { label: "7D",  days: 7  },
  { label: "10D", days: 10 },
  { label: "14D", days: 14 },
  { label: "20D", days: 20 },
  { label: "1M",  days: 22 },
  { label: "2M",  days: 44 },
  { label: "3M",  days: 66 },
  { label: "6M",  days: 132 },
];

export default function DurationBar({
  value,
  onChange,
}: {
  value: number;
  onChange: (days: number) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {DURATIONS.map((d) => (
        <button
          key={d.days}
          onClick={() => onChange(d.days)}
          style={{
            padding: "3px 9px",
            borderRadius: 4,
            border: "1px solid",
            borderColor: value === d.days ? "var(--accent)" : "var(--border2)",
            background: value === d.days ? "rgba(88,166,255,.15)" : "var(--surface)",
            color: value === d.days ? "var(--accent)" : "var(--muted)",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            fontWeight: value === d.days ? 700 : 400,
            cursor: "pointer",
            transition: "all .15s",
          }}
        >
          {d.label}
        </button>
      ))}
    </div>
  );
}
""")

# ── IndicesPanel component (replaces the static top/bottom in AlphaPanel) ─────
w(os.path.join(COMP, "IndicesPanel.tsx"), """
"use client";
import { useState, useEffect, useCallback } from "react";
import DurationBar from "./DurationBar";
import { fmtPct, colorPct } from "@/lib/utils";

interface IndexRow {
  name: string;
  pct_change: number;
  start_close: number;
  end_close: number;
}

export default function IndicesPanel() {
  const [days,    setDays]    = useState(7);
  const [data,    setData]    = useState<{ gainers: IndexRow[]; losers: IndexRow[]; total: number } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (d: number) => {
    setLoading(true);
    try {
      const r = await fetch("/api/indices?days=" + d, { cache: "no-store" });
      setData(await r.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days); }, [days, load]);

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="section-label" style={{ margin: 0, border: "none", padding: 0 }}>
          Index Performance -- {data?.total || 0} indices
        </span>
        <DurationBar value={days} onChange={(d) => { setDays(d); load(d); }} />
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 20 }}>
          <div className="spinner" style={{ width: 20, height: 20 }} />
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div className="section-label">Top 10 Gainers</div>
            {(data?.gainers || []).map((r, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "5px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)", minWidth: 18 }}>
                  {i + 1}
                </span>
                <span style={{ fontSize: 11, flex: 1, color: "var(--text)" }}>
                  {r.name.slice(0, 28)}
                </span>
                <div style={{ minWidth: 80, height: 4, background: "var(--border2)", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{
                    width: Math.min(Math.abs(r.pct_change) / 10 * 100, 100) + "%",
                    height: "100%",
                    background: "var(--pos)",
                    borderRadius: 2,
                  }} />
                </div>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--pos)", minWidth: 60, textAlign: "right" }}>
                  {r.pct_change != null ? "+" + Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
          <div>
            <div className="section-label">Bottom 10 Decliners</div>
            {(data?.losers || []).map((r, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "5px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)", minWidth: 18 }}>
                  {i + 1}
                </span>
                <span style={{ fontSize: 11, flex: 1, color: "var(--text)" }}>
                  {r.name.slice(0, 28)}
                </span>
                <div style={{ minWidth: 80, height: 4, background: "var(--border2)", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{
                    width: Math.min(Math.abs(r.pct_change) / 10 * 100, 100) + "%",
                    height: "100%",
                    background: "var(--neg)",
                    borderRadius: 2,
                  }} />
                </div>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--neg)", minWidth: 60, textAlign: "right" }}>
                  {r.pct_change != null ? Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
""")

# ── StreakBoardExtended component ─────────────────────────────────────────────
w(os.path.join(COMP, "StreakBoardExtended.tsx"), """
"use client";
import { useState, useEffect, useCallback } from "react";
import DurationBar from "./DurationBar";

interface StreakRow {
  symbol: string;
  streak_days: number;
  last_seen: string;
  first_seen: string;
  avg_score: number;
  max_score: number;
  avg_pct: number;
  max_pct: number;
  avg_deliv: number;
  eps_days: number;
  all_tags: string;
  latest_regime: string;
}

const SORT_OPTIONS = [
  { value: "streak", label: "Streak Days" },
  { value: "score",  label: "Avg Score"   },
  { value: "pct",    label: "Avg Return"  },
  { value: "deliv",  label: "Avg Delivery"},
];

const SCREEN_FILTERS = [
  { value: "",            label: "All Screens" },
  { value: "momentum",    label: "Momentum"    },
  { value: "breakout",    label: "Breakout"    },
  { value: "delivery",    label: "Delivery"    },
  { value: "consistency", label: "Consistency" },
  { value: "composite",   label: "Composite"   },
];

function colorScore(s: number) {
  if (s >= 7) return "var(--pos)";
  if (s >= 4) return "var(--accent)";
  return "var(--muted)";
}

export default function StreakBoardExtended() {
  const [days,    setDays]    = useState(30);
  const [sortBy,  setSortBy]  = useState("streak");
  const [screen,  setScreen]  = useState("");
  const [minDays, setMinDays] = useState(2);
  const [data,    setData]    = useState<{ rows: StreakRow[]; stats: any; days: number } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (d: number, s: string, sc: string, m: number) => {
    setLoading(true);
    try {
      const url = "/api/streak-extended?days=" + d + "&sort=" + s + "&screen=" + sc + "&min=" + m;
      const r = await fetch(url, { cache: "no-store" });
      setData(await r.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days, sortBy, screen, minDays); }, []);

  const refresh = () => load(days, sortBy, screen, minDays);
  const stats = data?.stats || {};
  const rows  = data?.rows  || [];
  const maxS  = Math.max(...rows.map(r => r.streak_days), 1);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Streak Leaderboard <span className="card-accent">-- signals_history</span>
        </span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {(Number(stats.total_rows) || 0).toLocaleString()} rows
          </span>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {stats.unique_symbols || 0} symbols
          </span>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {stats.unique_dates || 0} dates
          </span>
          {stats.latest_date && (
            <span className="pill pill-neut" style={{ fontSize: 9 }}>latest: {stats.latest_date}</span>
          )}
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 14, alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>LOOKBACK</span>
          <DurationBar value={days} onChange={(d) => { setDays(d); load(d, sortBy, screen, minDays); }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>SORT BY</span>
          <div style={{ display: "flex", gap: 4 }}>
            {SORT_OPTIONS.map(o => (
              <button key={o.value} onClick={() => { setSortBy(o.value); load(days, o.value, screen, minDays); }}
                style={{
                  padding: "3px 9px", borderRadius: 4, border: "1px solid",
                  borderColor: sortBy === o.value ? "var(--accent)" : "var(--border2)",
                  background: sortBy === o.value ? "rgba(88,166,255,.15)" : "var(--surface)",
                  color: sortBy === o.value ? "var(--accent)" : "var(--muted)",
                  fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                }}>
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>SCREEN FILTER</span>
          <div style={{ display: "flex", gap: 4 }}>
            {SCREEN_FILTERS.map(o => (
              <button key={o.value} onClick={() => { setScreen(o.value); load(days, sortBy, o.value, minDays); }}
                style={{
                  padding: "3px 9px", borderRadius: 4, border: "1px solid",
                  borderColor: screen === o.value ? "var(--purple)" : "var(--border2)",
                  background: screen === o.value ? "rgba(188,140,255,.15)" : "var(--surface)",
                  color: screen === o.value ? "var(--purple)" : "var(--muted)",
                  fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                }}>
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>MIN DAYS</span>
          <div style={{ display: "flex", gap: 4 }}>
            {[2, 3, 4, 5].map(m => (
              <button key={m} onClick={() => { setMinDays(m); load(days, sortBy, screen, m); }}
                style={{
                  padding: "3px 9px", borderRadius: 4, border: "1px solid",
                  borderColor: minDays === m ? "var(--warn)" : "var(--border2)",
                  background: minDays === m ? "rgba(210,153,34,.15)" : "var(--surface)",
                  color: minDays === m ? "var(--warn)" : "var(--muted)",
                  fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                }}>
                {m}+
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 30 }}>
          <div className="spinner" />
        </div>
      ) : rows.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: 12, padding: 12 }}>
          No data matching filters. Try reducing Min Days or changing screen filter.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>Streak</th>
                <th style={{ minWidth: 120 }}>Consistency</th>
                <th>Avg Score</th>
                <th>Max Score</th>
                <th>Avg Ret%</th>
                <th>Max Ret%</th>
                <th>Avg Deliv%</th>
                <th>EPS Days</th>
                <th>Screens</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const pct  = (r.streak_days / maxS) * 100;
                const rank = i === 0 ? "#1" : i === 1 ? "#2" : i === 2 ? "#3" : String(i + 1);
                const tags = (r.all_tags || "").split(",").map((t: string) => t.trim()).filter(Boolean);
                const uniqueTags = [...new Set(tags)].slice(0, 5);
                const tagColors: Record<string, string> = {
                  momentum: "var(--accent)", breakout: "var(--warn)", breakouts: "var(--warn)",
                  delivery: "var(--purple)", consistency: "var(--cyan)", composite: "var(--pos)",
                };
                return (
                  <tr key={r.symbol}>
                    <td style={{ color: "var(--muted)", fontWeight: i < 3 ? 700 : 400 }}>{rank}</td>
                    <td style={{ fontWeight: 700, fontSize: 12, color: "var(--text)" }}>{r.symbol}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700, color: "var(--orange)" }}>
                      {r.streak_days}d
                    </td>
                    <td>
                      <div style={{ height: 6, background: "var(--border2)", borderRadius: 3, overflow: "hidden", minWidth: 100 }}>
                        <div style={{ width: pct + "%", height: "100%", background: "var(--pos)", borderRadius: 3 }} />
                      </div>
                      <div style={{ fontSize: 9, color: "var(--muted)", marginTop: 2 }}>
                        {r.first_seen} to {r.last_seen}
                      </div>
                    </td>
                    <td style={{ fontFamily: "monospace", color: colorScore(r.avg_score) }}>
                      {(r.avg_score || 0).toFixed(1)}
                    </td>
                    <td style={{ fontFamily: "monospace", color: colorScore(r.max_score) }}>
                      {(r.max_score || 0).toFixed(1)}
                    </td>
                    <td style={{ fontFamily: "monospace", color: (r.avg_pct || 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>
                      {r.avg_pct != null ? ((r.avg_pct >= 0 ? "+" : "") + r.avg_pct.toFixed(2) + "%") : "--"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: "var(--pos)" }}>
                      {r.max_pct != null ? "+" + r.max_pct.toFixed(2) + "%" : "--"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: (r.avg_deliv || 0) > 50 ? "var(--pos)" : "var(--muted)" }}>
                      {r.avg_deliv != null ? r.avg_deliv.toFixed(1) + "%" : "--"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: (r.eps_days || 0) > 0 ? "var(--purple)" : "var(--muted)" }}>
                      {r.eps_days || 0}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                        {uniqueTags.map((t, j) => {
                          const c = tagColors[t.toLowerCase()] || "var(--muted)";
                          return (
                            <span key={j} style={{
                              background: c, color: "#000", borderRadius: 3,
                              padding: "1px 4px", fontFamily: "monospace",
                              fontSize: 8, fontWeight: 700, opacity: 0.85,
                            }}>
                              {t.toUpperCase().slice(0, 5)}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 10 }}>{r.last_seen}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
""")

print("[2/4] Components written")

# ── Update AlphaPanel to include IndicesPanel ─────────────────────────────────
w(os.path.join(COMP, "AlphaPanel.tsx"), """
import { fmtNum, fmtPct, colorPct, regimeCls } from "@/lib/utils";
import IndicesPanel from "./IndicesPanel";

export default function AlphaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header"><span className="card-title">Alpha -- Macro and Regime</span></div>
      <div style={{ color:"var(--neg)", fontFamily:"monospace", fontSize:12, padding:8 }}>
        {data?._error || "No alpha report. Run: py micc_engine.py"}
      </div>
    </div>
  );

  const rm  = data.regime_metrics   || {};
  const ba  = data.breadth_analytics || {};
  const cr  = data.cap_rotation      || {};
  const date   = data.latest_market_date || (data.timestamp || "").slice(0,10) || "--";
  const llm    = typeof data.regime_analysis === "string" ? data.regime_analysis : "";

  const regimeMatch = llm.match(/REGIME:\\s*([A-Z_]+)/);
  const confMatch   = llm.match(/CONFIDENCE:\\s*([A-Z])/);
  const regime      = regimeMatch ? regimeMatch[1] : "";
  const confidence  = confMatch   ? confMatch[1]   : "";
  const rcls        = regimeCls(regime);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Alpha <span className="card-accent">-- Macro and Regime</span></span>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontFamily:"monospace", fontSize:10, color:"var(--muted)" }}>{date}</span>
          {regime && <span className={"pill " + rcls} style={{ fontSize:11 }}>{regime}</span>}
          {confidence && <span className="pill pill-neut" style={{ fontSize:9 }}>CONF: {confidence}</span>}
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi">
          <div className="kpi-label">Nifty 50</div>
          <div className="kpi-value" style={{ fontSize:20 }}>{fmtNum(rm.nifty50_close, 2)}</div>
          <div className="kpi-sub" style={{ color:colorPct(rm.return_1d_pct) }}>
            {fmtPct(rm.return_1d_pct)} 1d &nbsp;|&nbsp;
            <span style={{ color:colorPct(rm.return_5d_pct) }}>{fmtPct(rm.return_5d_pct)} 5d</span>
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Volatility (20d Ann.)</div>
          <div className="kpi-value" style={{
            color: (Number(rm.volatility_20d_annualized_pct)||0) > 20 ? "var(--neg)"
                 : (Number(rm.volatility_20d_annualized_pct)||0) < 12 ? "var(--pos)" : "var(--warn)"
          }}>
            {fmtNum(rm.volatility_20d_annualized_pct, 1)}%
          </div>
          <div className="kpi-sub">Vol ratio 5/20d: {fmtNum(rm.volume_ratio_5d_vs_20d, 2)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">MA Positioning</div>
          <div className="kpi-value" style={{ fontSize:13, color: rm.above_ma20 ? "var(--pos)" : "var(--neg)" }}>
            {rm.above_ma20 ? "Above MA20" : "Below MA20"}
          </div>
          <div className="kpi-sub" style={{ color: rm.above_ma50 ? "var(--pos)" : "var(--neg)" }}>
            {rm.above_ma50 ? "Above MA50" : "Below MA50"}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Nifty PE / PB</div>
          <div className="kpi-value" style={{ color:(Number(rm.pe)||0) > 25 ? "var(--warn)" : "var(--text)" }}>
            {fmtNum(rm.pe, 1)}
          </div>
          <div className="kpi-sub">PB: {fmtNum(rm.pb, 2)} | vs20d: {fmtNum(rm.pe_vs_20d_avg, 2)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Advances</div>
          <div className="kpi-value" style={{ color:"var(--pos)" }}>{ba.advancing ?? "--"}</div>
          <div className="kpi-sub">of {ba.total_indices ?? "--"} indices</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Declines</div>
          <div className="kpi-value" style={{ color:"var(--neg)" }}>{ba.declining ?? "--"}</div>
          <div className="kpi-sub">A/D: {ba.advance_decline_ratio ? Number(ba.advance_decline_ratio).toFixed(2) : "--"}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Breadth</div>
          <div className="kpi-value" style={{ color:(Number(ba.breadth_pct_advancing)||0) > 55 ? "var(--pos)" : "var(--warn)" }}>
            {fmtNum(ba.breadth_pct_advancing, 1)}%
          </div>
          <div className="kpi-sub">advancing | Unch: {ba.unchanged ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Largecap</div>
          <div className="kpi-value" style={{ color:colorPct(cr.largecap_avg_change) }}>
            {fmtPct(cr.largecap_avg_change)}
          </div>
          <div className="kpi-sub" style={{ color:colorPct(cr.midcap_avg_change) }}>
            Mid: {fmtPct(cr.midcap_avg_change)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Smallcap</div>
          <div className="kpi-value" style={{ color:colorPct(cr.smallcap_avg_change) }}>
            {fmtPct(cr.smallcap_avg_change)}
          </div>
          <div className="kpi-sub">{(cr.rotation_signal || "--").slice(0, 22)}</div>
        </div>
      </div>

      {cr.rotation_signal && (
        <div style={{
          padding:"7px 12px", marginBottom:14,
          background:"var(--surface)", border:"1px solid var(--border)", borderRadius:5,
          fontFamily:"monospace", fontSize:11,
          color: cr.rotation_signal.includes("RISK_ON") ? "var(--pos)"
               : cr.rotation_signal.includes("RISK_OFF") ? "var(--warn)" : "var(--muted)",
        }}>
          Rotation: {cr.rotation_signal}
        </div>
      )}

      {/* Interactive indices panel with duration bar */}
      <IndicesPanel />

      {llm && (
        <>
          <div className="section-label" style={{ marginTop: 16 }}>LLM Regime Analysis</div>
          <div style={{
            fontSize:12, lineHeight:1.8, color:"var(--text)",
            padding:"14px 16px", background:"var(--surface)",
            border:"1px solid var(--border)", borderRadius:6,
            whiteSpace:"pre-wrap", maxHeight:420, overflowY:"auto",
          }}>
            {llm}
          </div>
        </>
      )}
    </div>
  );
}
""")

# ── Update page.tsx to use StreakBoardExtended ────────────────────────────────
page_path = os.path.join(APP, "page.tsx")
if os.path.exists(page_path):
    with open(page_path, "r", encoding="utf-8") as f:
        page = f.read()
    # Replace StreakBoard import and usage
    page = page.replace(
        'import StreakBoard  from "@/components/StreakBoard";',
        'import StreakBoard  from "@/components/StreakBoardExtended";'
    )
    page = page.replace(
        'import StreakBoard from "@/components/StreakBoard";',
        'import StreakBoard from "@/components/StreakBoardExtended";'
    )
    # Replace usage
    page = page.replace('<StreakBoard data={streak} />', '<StreakBoard />')
    page = page.replace('<StreakBoard data={streak}/>', '<StreakBoard />')
    # Remove streak fetch if present (StreakBoardExtended fetches its own data)
    with open(page_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("  updated: page.tsx (StreakBoard -> StreakBoardExtended)")

print("[3/4] Components patched")

print("""
[4/4] Done! Interactive features added:

ALPHA PANEL:
  - Duration bar: 1D, 3D, 5D, 7D, 10D, 14D, 20D, 1M, 2M, 3M, 6M
  - Top 10 gainers + Bottom 10 decliners with visual bars
  - Data fetched live from market_snapshot SQLite table

STREAK LEADERBOARD:
  - Duration bar: lookback period
  - Sort by: Streak Days, Avg Score, Avg Return, Avg Delivery
  - Screen filter: All / Momentum / Breakout / Delivery / Consistency / Composite
  - Min days filter: 2+ / 3+ / 4+ / 5+
  - New columns: Max Score, Avg Return%, Max Return%, Avg Delivery%, EPS Days, Date range
  - Shows top 25 results

Next.js hot-reload will pick up changes in ~3 seconds.
""")
