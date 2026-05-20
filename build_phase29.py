#!/usr/bin/env python3
"""
build_phase29.py — MICC Phase 29: Conviction Score System
==========================================================
Writes:
  1. D:\MICC\dashboard\app\api\conviction\route.ts
  2. D:\MICC\dashboard\app\conviction\page.tsx

Then adds /conviction to the navbar.

Run: py build_phase29.py
Location: D:\MICC\build_phase29.py
"""

from pathlib import Path

DA = Path(r"D:\MICC")
DASH = DA / "dashboard"
API_DIR  = DASH / "app" / "api" / "conviction"
PAGE_DIR = DASH / "app" / "conviction"

API_DIR.mkdir(parents=True, exist_ok=True)
PAGE_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1. API ROUTE
# ──────────────────────────────────────────────────────────────────────────────

API_ROUTE = r'''import { NextRequest, NextResponse } from "next/server";
import { spawnSync } from "child_process";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";

function runBridge(script: string): string {
  const r = spawnSync("py", ["-c", script], {
    encoding: "utf8",
    timeout: 30000,
    cwd: DA,
  });
  if (r.error) throw r.error;
  return r.stdout.trim();
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const limit  = parseInt(searchParams.get("limit")  || "100", 10);
  const minScore = parseFloat(searchParams.get("min") || "0");
  const layer  = searchParams.get("layer") || "";
  const search = (searchParams.get("q") || "").toUpperCase();

  const script = `
import sqlite3, json, math

def s(v):
    if v is None: return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 2)
    except: return None

conn = sqlite3.connect(r"${DB}", timeout=15)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Main conviction data
q = """
  SELECT c.symbol, c.conviction_score, c.momentum_score, c.seasonality_score,
         c.quality_score, c.delivery_score, c.insider_score, c.news_score,
         c.fundamental_score, c.signal_count, c.top_reason, c.computed_date,
         st.close, st.volume,
         sf.roce, sf.roe, sf.debt_equity,
         sq.f_score, sq.data_quarters
  FROM symbol_conviction c
  LEFT JOIN (
      SELECT symbol, close, volume FROM stock_data
      WHERE date = (SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)
        AND close IS NOT NULL
  ) st ON st.symbol = c.symbol
  LEFT JOIN screener_fundamentals sf ON sf.symbol = c.symbol
  LEFT JOIN symbol_quality_scores sq ON sq.symbol = c.symbol
  WHERE c.conviction_score >= ${minScore}
  ${search ? f"AND c.symbol LIKE '%{search}%'" : ""}
  ORDER BY c.conviction_score DESC
  LIMIT ${limit}
"""
rows = cur.execute(q).fetchall()

results = []
for r in rows:
    results.append({
        "symbol":       r["symbol"],
        "score":        s(r["conviction_score"]),
        "momentum":     s(r["momentum_score"]),
        "seasonality":  s(r["seasonality_score"]),
        "quality":      s(r["quality_score"]),
        "delivery":     s(r["delivery_score"]),
        "insider":      s(r["insider_score"]),
        "news":         s(r["news_score"]),
        "fundamental":  s(r["fundamental_score"]),
        "signals":      r["signal_count"],
        "top_reason":   r["top_reason"],
        "close":        s(r["close"]),
        "volume":       r["volume"],
        "roce":         s(r["roce"]),
        "roe":          s(r["roe"]),
        "debt_equity":  s(r["debt_equity"]),
        "f_score":      r["f_score"],
        "as_of":        r["computed_date"],
    })

# Summary stats
stats = cur.execute("""
  SELECT COUNT(*) as total,
         AVG(conviction_score) as avg_score,
         SUM(CASE WHEN conviction_score >= 70 THEN 1 ELSE 0 END) as high,
         SUM(CASE WHEN conviction_score >= 50 AND conviction_score < 70 THEN 1 ELSE 0 END) as med,
         SUM(CASE WHEN conviction_score < 50 THEN 1 ELSE 0 END) as low,
         MAX(computed_date) as as_of
  FROM symbol_conviction
""").fetchone()

# Top reason distribution
reasons = cur.execute("""
  SELECT top_reason, COUNT(*) as cnt
  FROM symbol_conviction
  GROUP BY top_reason
  ORDER BY cnt DESC
""").fetchall()

conn.close()
print(json.dumps({
    "rows": results,
    "stats": {
        "total":     stats["total"],
        "avg_score": s(stats["avg_score"]),
        "high":      stats["high"],
        "med":       stats["med"],
        "low":       stats["low"],
        "as_of":     stats["as_of"],
    },
    "top_reasons": [{"reason": r["top_reason"], "count": r["cnt"]} for r in reasons]
}))
`;

  try {
    const raw = runBridge(script);
    const data = JSON.parse(raw);
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message, rows: [], stats: null }, { status: 500 });
  }
}
''';

(API_DIR / "route.ts").write_text(API_ROUTE, encoding="utf-8")
print("✅ API route written")

# ──────────────────────────────────────────────────────────────────────────────
# 2. PAGE.TSX
# ──────────────────────────────────────────────────────────────────────────────

PAGE_TSX = '''"use client";
import { useEffect, useState, useMemo } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

interface ConvictionRow {
  symbol: string;
  score: number | null;
  momentum: number | null;
  seasonality: number | null;
  quality: number | null;
  delivery: number | null;
  insider: number | null;
  news: number | null;
  fundamental: number | null;
  signals: number;
  top_reason: string;
  close: number | null;
  volume: number | null;
  roce: number | null;
  roe: number | null;
  debt_equity: number | null;
  f_score: number | null;
  as_of: string;
}

interface Stats {
  total: number;
  avg_score: number;
  high: number;
  med: number;
  low: number;
  as_of: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const LAYERS = [
  { key: "momentum",    label: "Mom",    color: "#6366f1", tip: "Price/ADX/Volume momentum" },
  { key: "seasonality", label: "Season", color: "#f59e0b", tip: "Historical seasonal edge" },
  { key: "quality",     label: "F-Score",color: "#10b981", tip: "Piotroski F-Score (0-9)" },
  { key: "delivery",    label: "Deliv",  color: "#3b82f6", tip: "Delivery % trend" },
  { key: "insider",     label: "Insider",color: "#ec4899", tip: "Insider buying last 30d" },
  { key: "news",        label: "News",   color: "#8b5cf6", tip: "News presence this week" },
  { key: "fundamental", label: "Fund",   color: "#14b8a6", tip: "ROCE/ROE percentile rank" },
];

function scoreColor(v: number | null): string {
  if (v === null) return "#374151";
  if (v >= 70) return "#10b981";
  if (v >= 50) return "#f59e0b";
  return "#ef4444";
}

function scoreLabel(v: number | null): string {
  if (v === null) return "–";
  if (v >= 70) return "HIGH";
  if (v >= 50) return "MED";
  return "LOW";
}

function fmt(v: number | null, dec = 1): string {
  if (v === null || v === undefined) return "–";
  return v.toFixed(dec);
}

function fmtVol(v: number | null): string {
  if (!v) return "–";
  if (v >= 1e7) return (v / 1e7).toFixed(1) + "Cr";
  if (v >= 1e5) return (v / 1e5).toFixed(1) + "L";
  return v.toLocaleString();
}

// ── Mini Score Bar ────────────────────────────────────────────────────────────

function ScoreBar({ value, color }: { value: number | null; color: string }) {
  const pct = value ?? 0;
  return (
    <div style={{ width: "100%", background: "#1f2937", borderRadius: 4, height: 6, overflow: "hidden" }}>
      <div style={{
        width: `${pct}%`, height: "100%",
        background: color,
        borderRadius: 4,
        transition: "width 0.4s ease",
      }} />
    </div>
  );
}

// ── Radar (SVG mini chart) ────────────────────────────────────────────────────

function RadarMini({ row }: { row: ConvictionRow }) {
  const vals = LAYERS.map(l => (row[l.key as keyof ConvictionRow] as number | null) ?? 0);
  const n = vals.length;
  const cx = 40, cy = 40, r = 32;
  const pts = vals.map((v, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const pct = v / 100;
    return [cx + r * pct * Math.cos(angle), cy + r * pct * Math.sin(angle)];
  });
  const poly = pts.map(p => p.join(",")).join(" ");
  const axes = Array.from({ length: n }, (_, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  });

  return (
    <svg width={80} height={80} viewBox="0 0 80 80">
      {[0.25, 0.5, 0.75, 1].map(f => (
        <polygon key={f}
          points={axes.map(([x, y]) => `${cx + (x - cx) * f},${cy + (y - cy) * f}`).join(" ")}
          fill="none" stroke="#374151" strokeWidth={0.5}
        />
      ))}
      {axes.map(([x, y], i) => (
        <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#374151" strokeWidth={0.5} />
      ))}
      <polygon points={poly} fill="rgba(99,102,241,0.3)" stroke="#6366f1" strokeWidth={1.5} />
    </svg>
  );
}

// ── Expanded Row ──────────────────────────────────────────────────────────────

function ExpandedRow({ row }: { row: ConvictionRow }) {
  return (
    <div style={{
      background: "#111827", border: "1px solid #374151", borderRadius: 8,
      padding: "12px 16px", margin: "4px 0",
      display: "grid", gridTemplateColumns: "80px 1fr 1fr", gap: 16
    }}>
      <RadarMini row={row} />
      <div>
        <div style={{ color: "#9ca3af", fontSize: 11, marginBottom: 6 }}>LAYER SCORES</div>
        {LAYERS.map(l => {
          const v = row[l.key as keyof ConvictionRow] as number | null;
          return (
            <div key={l.key} style={{ marginBottom: 4 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span style={{ color: "#d1d5db", fontSize: 11 }} title={l.tip}>{l.label}</span>
                <span style={{ color: l.color, fontSize: 11, fontWeight: 600 }}>{v !== null ? v.toFixed(0) : "–"}</span>
              </div>
              <ScoreBar value={v} color={l.color} />
            </div>
          );
        })}
      </div>
      <div>
        <div style={{ color: "#9ca3af", fontSize: 11, marginBottom: 6 }}>FUNDAMENTALS</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {[
            ["ROCE", fmt(row.roce, 1) + "%"],
            ["ROE",  fmt(row.roe, 1) + "%"],
            ["D/E",  fmt(row.debt_equity, 2)],
            ["F-Score", row.f_score !== null ? `${row.f_score}/9` : "–"],
            ["Close", row.close !== null ? `₹${fmt(row.close, 1)}` : "–"],
            ["Volume", fmtVol(row.volume)],
            ["Signals", `${row.signals}/7`],
            ["As of", row.as_of?.slice(0, 10) || "–"],
          ].map(([k, v]) => (
            <div key={k} style={{ background: "#1f2937", borderRadius: 6, padding: "6px 10px" }}>
              <div style={{ color: "#6b7280", fontSize: 10 }}>{k}</div>
              <div style={{ color: "#f9fafb", fontSize: 13, fontWeight: 600 }}>{v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ConvictionPage() {
  const [rows, setRows]         = useState<ConvictionRow[]>([]);
  const [stats, setStats]       = useState<Stats | null>(null);
  const [reasons, setReasons]   = useState<{reason:string;count:number}[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState("");
  const [search, setSearch]     = useState("");
  const [minScore, setMinScore] = useState(0);
  const [sortCol, setSortCol]   = useState("score");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [activeLayer, setActiveLayer] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/conviction?limit=200&min=${minScore}`)
      .then(r => r.json())
      .then(d => {
        setRows(d.rows || []);
        setStats(d.stats || null);
        setReasons(d.top_reasons || []);
        setError("");
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [minScore]);

  const filtered = useMemo(() => {
    let r = rows;
    if (search) r = r.filter(x => x.symbol.includes(search.toUpperCase()));
    if (activeLayer) r = r.filter(x => x[activeLayer as keyof ConvictionRow] !== null);
    r = [...r].sort((a, b) => {
      const av = (a[sortCol as keyof ConvictionRow] as number) ?? -1;
      const bv = (b[sortCol as keyof ConvictionRow] as number) ?? -1;
      return bv - av;
    });
    return r;
  }, [rows, search, sortCol, activeLayer]);

  const Th = ({ col, label }: { col: string; label: string }) => (
    <th
      onClick={() => setSortCol(col)}
      style={{
        cursor: "pointer", padding: "8px 10px", textAlign: "right",
        color: sortCol === col ? "#6366f1" : "#6b7280",
        fontWeight: sortCol === col ? 700 : 400, fontSize: 11,
        userSelect: "none", whiteSpace: "nowrap",
      }}
    >{label}{sortCol === col ? " ↓" : ""}</th>
  );

  return (
    <div style={{
      minHeight: "100vh", background: "#0d1117", color: "#f9fafb",
      fontFamily: "'Inter', 'Segoe UI', sans-serif", padding: "24px 20px"
    }}>
      {/* HEADER */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
          <span style={{ fontSize: 24 }}>⚡</span>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#f9fafb" }}>
            Conviction Score
          </h1>
          <span style={{ background: "#1e3a5f", color: "#60a5fa", fontSize: 11, padding: "2px 10px", borderRadius: 20, fontWeight: 600 }}>
            PHASE 29
          </span>
        </div>
        <p style={{ margin: 0, color: "#9ca3af", fontSize: 13 }}>
          Unified 0-100 signal fusion · 7 layers: Momentum · Seasonality · F-Score · Delivery · Insider · News · Fundamentals
        </p>
      </div>

      {/* STATS BAR */}
      {stats && (
        <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
          {[
            { label: "Total Symbols", value: stats.total, color: "#f9fafb" },
            { label: "Avg Score",     value: fmt(stats.avg_score), color: "#6366f1" },
            { label: "🟢 High (≥70)", value: stats.high, color: "#10b981" },
            { label: "🟡 Med (50-70)", value: stats.med, color: "#f59e0b" },
            { label: "🔴 Low (<50)",  value: stats.low, color: "#ef4444" },
            { label: "As Of",         value: stats.as_of?.slice(0, 10) || "–", color: "#9ca3af" },
          ].map(s => (
            <div key={s.label} style={{
              background: "#161b22", border: "1px solid #30363d",
              borderRadius: 8, padding: "10px 16px", flex: 1, minWidth: 100,
            }}>
              <div style={{ color: "#6b7280", fontSize: 10, textTransform: "uppercase", letterSpacing: 1 }}>{s.label}</div>
              <div style={{ color: s.color, fontSize: 18, fontWeight: 700 }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* LAYER FILTER PILLS */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {LAYERS.map(l => (
          <button key={l.key}
            onClick={() => setActiveLayer(activeLayer === l.key ? null : l.key)}
            title={l.tip}
            style={{
              background: activeLayer === l.key ? l.color : "#1f2937",
              color: activeLayer === l.key ? "#fff" : "#9ca3af",
              border: `1px solid ${activeLayer === l.key ? l.color : "#374151"}`,
              borderRadius: 20, padding: "4px 14px", fontSize: 12,
              cursor: "pointer", fontWeight: 600, transition: "all 0.2s",
            }}
          >{l.label}</button>
        ))}
      </div>

      {/* CONTROLS */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <input
          placeholder="Search symbol..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            background: "#161b22", border: "1px solid #30363d", borderRadius: 8,
            color: "#f9fafb", padding: "8px 14px", fontSize: 13, width: 180,
            outline: "none",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#9ca3af", fontSize: 13 }}>
          <span>Min score:</span>
          {[0, 30, 50, 70].map(v => (
            <button key={v}
              onClick={() => setMinScore(v)}
              style={{
                background: minScore === v ? "#6366f1" : "#1f2937",
                color: minScore === v ? "#fff" : "#9ca3af",
                border: "1px solid #374151", borderRadius: 6,
                padding: "4px 12px", fontSize: 12, cursor: "pointer",
              }}
            >{v}+</button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", color: "#9ca3af", fontSize: 12, alignSelf: "center" }}>
          Showing {filtered.length} symbols
        </div>
      </div>

      {/* ERROR */}
      {error && (
        <div style={{ background: "#2d1b1b", border: "1px solid #7f1d1d", borderRadius: 8, padding: 16, marginBottom: 16, color: "#fca5a5", fontSize: 13 }}>
          ⚠️ {error}
        </div>
      )}

      {/* LOADING */}
      {loading && (
        <div style={{ textAlign: "center", padding: 60, color: "#6b7280" }}>
          ⚡ Computing conviction scores...
        </div>
      )}

      {/* TABLE */}
      {!loading && (
        <div style={{ overflowX: "auto", borderRadius: 10, border: "1px solid #30363d" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#161b22", borderBottom: "1px solid #30363d" }}>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#6b7280", fontSize: 11, fontWeight: 400 }}>#</th>
                <th style={{ padding: "8px 12px", textAlign: "left", color: "#6b7280", fontSize: 11, fontWeight: 400 }}>SYMBOL</th>
                <Th col="score"        label="CONVICTION" />
                <Th col="momentum"     label="MOM" />
                <Th col="seasonality"  label="SEASON" />
                <Th col="quality"      label="QUALITY" />
                <Th col="delivery"     label="DELIV" />
                <Th col="insider"      label="INSIDER" />
                <Th col="news"         label="NEWS" />
                <Th col="fundamental"  label="FUND" />
                <th style={{ padding: "8px 10px", textAlign: "left", color: "#6b7280", fontSize: 11, fontWeight: 400 }}>TOP SIGNAL</th>
                <th style={{ padding: "8px 10px", textAlign: "right", color: "#6b7280", fontSize: 11, fontWeight: 400 }}>CLOSE</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, i) => (
                <>
                  <tr
                    key={row.symbol}
                    onClick={() => setExpanded(expanded === row.symbol ? null : row.symbol)}
                    style={{
                      borderBottom: "1px solid #1f2937",
                      cursor: "pointer",
                      background: expanded === row.symbol ? "#1a1f2e" : i % 2 === 0 ? "#0d1117" : "#111827",
                      transition: "background 0.15s",
                    }}
                    onMouseEnter={e => { if (expanded !== row.symbol) (e.currentTarget as HTMLElement).style.background = "#1a1f2e"; }}
                    onMouseLeave={e => { if (expanded !== row.symbol) (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? "#0d1117" : "#111827"; }}
                  >
                    <td style={{ padding: "7px 12px", color: "#6b7280", fontSize: 11 }}>{i + 1}</td>
                    <td style={{ padding: "7px 12px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ color: "#e2e8f0", fontWeight: 700, fontSize: 13 }}>{row.symbol}</span>
                        <span style={{ fontSize: 9, color: "#6b7280" }}>{row.signals}/7</span>
                      </div>
                    </td>
                    <td style={{ padding: "7px 10px", textAlign: "right" }}>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
                        <span style={{ color: scoreColor(row.score), fontWeight: 700, fontSize: 15 }}>
                          {fmt(row.score, 1)}
                        </span>
                        <span style={{
                          fontSize: 9, fontWeight: 700,
                          color: scoreColor(row.score),
                          background: `${scoreColor(row.score)}22`,
                          padding: "1px 6px", borderRadius: 4,
                        }}>{scoreLabel(row.score)}</span>
                      </div>
                    </td>
                    {LAYERS.map(l => {
                      const v = row[l.key as keyof ConvictionRow] as number | null;
                      return (
                        <td key={l.key} style={{ padding: "7px 10px", textAlign: "right" }}>
                          {v !== null ? (
                            <span style={{ color: l.color, fontSize: 12 }}>{v.toFixed(0)}</span>
                          ) : (
                            <span style={{ color: "#374151", fontSize: 12 }}>–</span>
                          )}
                        </td>
                      );
                    })}
                    <td style={{ padding: "7px 10px" }}>
                      <span style={{
                        fontSize: 10, fontWeight: 600,
                        color: LAYERS.find(l => l.key === row.top_reason)?.color || "#9ca3af",
                        background: "#1f2937", padding: "2px 8px", borderRadius: 10,
                      }}>
                        {LAYERS.find(l => l.key === row.top_reason)?.label || row.top_reason || "–"}
                      </span>
                    </td>
                    <td style={{ padding: "7px 12px", textAlign: "right", color: "#e2e8f0", fontSize: 12 }}>
                      {row.close ? `₹${fmt(row.close, 1)}` : "–"}
                    </td>
                  </tr>
                  {expanded === row.symbol && (
                    <tr key={`exp-${row.symbol}`}>
                      <td colSpan={13} style={{ padding: "8px 12px", background: "#0d1117" }}>
                        <ExpandedRow row={row} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && !loading && (
            <div style={{ textAlign: "center", padding: 40, color: "#6b7280" }}>
              No symbols match your filters.
            </div>
          )}
        </div>
      )}

      {/* TOP REASON DISTRIBUTION */}
      {reasons.length > 0 && (
        <div style={{ marginTop: 24, background: "#161b22", border: "1px solid #30363d", borderRadius: 10, padding: 16 }}>
          <div style={{ color: "#9ca3af", fontSize: 11, marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
            Top Driving Signal Distribution
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {reasons.map(({ reason, count }) => {
              const layer = LAYERS.find(l => l.key === reason);
              return (
                <div key={reason} style={{
                  background: "#1f2937", borderRadius: 8, padding: "8px 14px",
                  borderLeft: `3px solid ${layer?.color || "#374151"}`
                }}>
                  <div style={{ color: layer?.color || "#9ca3af", fontSize: 12, fontWeight: 700 }}>{layer?.label || reason}</div>
                  <div style={{ color: "#6b7280", fontSize: 11 }}>{count} symbols</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
''';

(PAGE_DIR / "page.tsx").write_text(PAGE_TSX, encoding="utf-8")
print("✅ Conviction page written")

# ──────────────────────────────────────────────────────────────────────────────
# 3. NAVBAR PATCH
# ──────────────────────────────────────────────────────────────────────────────

navbar_candidates = [
    DASH / "components" / "Navbar.tsx",
    DASH / "app" / "components" / "Navbar.tsx",
    DASH / "components" / "navbar.tsx",
]

navbar_path = None
for p in navbar_candidates:
    if p.exists():
        navbar_path = p
        break

if navbar_path:
    text = navbar_path.read_text(encoding="utf-8")
    if "/conviction" not in text:
        # Find a good insertion point — after /alerts or /deep
        for anchor in ['"/alerts"', '"/deep"', '"/watchlist"', '"/backtest"']:
            if anchor in text:
                insert_after = text.index(anchor)
                # Find end of that nav item block (next } or next href)
                # Simple approach: find the closing tag of that nav link
                snippet = '\n          { href: "/conviction", label: "⚡ Conviction" },'
                # Find the line with anchor and add after
                lines = text.splitlines()
                new_lines = []
                inserted = False
                for line in lines:
                    new_lines.append(line)
                    if anchor.strip('"') in line and not inserted:
                        new_lines.append('          { href: "/conviction", label: "⚡ Conviction" },')
                        inserted = True
                if inserted:
                    navbar_path.write_text("\n".join(new_lines), encoding="utf-8")
                    print(f"✅ Navbar patched at {navbar_path}")
                    break
        else:
            print(f"⚠️  Navbar found but couldn't find insertion point. Add /conviction manually.")
    else:
        print("✅ Navbar already has /conviction")
else:
    print("⚠️  Navbar not found — add /conviction manually")

print("\n" + "="*60)
print("PHASE 29 BUILD COMPLETE")
print("="*60)
print("\nFiles written:")
print(f"  {API_DIR / 'route.ts'}")
print(f"  {PAGE_DIR / 'page.tsx'}")
print("\nRun order:")
print("  1. py build_piotroski.py   (populates symbol_quality_scores)")
print("  2. py build_conviction.py  (populates symbol_conviction)")
print("  3. py build_phase29.py     (already done — writes dashboard files)")
print("  4. Visit http://localhost:3000/conviction")
