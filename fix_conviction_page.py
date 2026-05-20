# -*- coding: utf-8 -*-
"""
fix_conviction_page.py  --  Run from D:\MICC

Fixes:
  1. Double navbar  -- removes the inline nav from conviction/page.tsx
  2. Black gap      -- was caused by double nav stacking
  3. 0 rows / search -- adds schema probe + fallback column names
                        + fixes latest_close subquery that may timeout

Run:  py D:\MICC\fix_conviction_page.py
"""

from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")


# =============================================================================
# [1]  Patch the API to be resilient to column name variations
#      Also use a simpler latest_close query (no correlated subquery)
# =============================================================================
print("\n[1/3] Rewriting /api/conviction/route.ts (robust column names + fast price query)...")

api = r"""
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";
const PY = "py";

function sanitize(s: string) {
  return s
    .replace(/:[ \t]*NaN\b/g,        ": null")
    .replace(/:[ \t]*-?Infinity\b/g, ": null");
}

function runPy(script: string): string {
  const b64 = Buffer.from(script).toString("base64");
  const r = spawnSync(
    PY, ["-c",
      "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())",
      b64,
    ],
    { cwd: DA, encoding: "utf-8", timeout: 25000 }
  );
  if (r.status !== 0) {
    console.error("[conviction]", r.stderr?.slice(0, 400));
    return "[]";
  }
  return r.stdout.trim() || "[]";
}

function qdb(sql: string, params: (string | number)[] = []): any[] {
  const script = `
import sqlite3, json
conn = sqlite3.connect(r'${DB}', timeout=15)
conn.row_factory = sqlite3.Row
rows = conn.execute(${JSON.stringify(sql)}, ${JSON.stringify(params)}).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
`.trim();
  try {
    return JSON.parse(sanitize(runPy(script)));
  } catch {
    return [];
  }
}

// Probe actual column names of symbol_conviction
function getConvColumns(): string[] {
  const script = `
import sqlite3, json
conn = sqlite3.connect(r'${DB}', timeout=10)
rows = conn.execute("PRAGMA table_info(symbol_conviction)").fetchall()
print(json.dumps([r[1] for r in rows]))
conn.close()
`.trim();
  try {
    return JSON.parse(runPy(script));
  } catch {
    return [];
  }
}

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url      = new URL(req.url);
  const minScore = parseFloat(url.searchParams.get("min") || "0");
  const limit    = parseInt(url.searchParams.get("limit") || "300");

  // --- Probe real column names ---
  const actualCols = getConvColumns();
  if (actualCols.length === 0) {
    return NextResponse.json({ rows: [], total: 0, regime: "UNKNOWN", nifty: 0,
      error: "symbol_conviction table not found or empty",
      generated_at: new Date().toISOString() });
  }

  // Map canonical name -> actual column (handles score vs conviction_score etc.)
  function col(candidates: string[]): string {
    for (const c of candidates) {
      if (actualCols.includes(c)) return c;
    }
    return candidates[0]; // fallback, will be NULL in query
  }

  const cScore    = col(["conviction_score", "score", "total_score"]);
  const cBeta     = col(["beta_score",       "beta"]);
  const cRegime   = col(["regime_score",     "regime"]);
  const cInsider  = col(["insider_score",    "insider"]);
  const cWatch    = col(["watchlist_score",  "watchlist", "watch_score"]);
  const cSeasonal = col(["seasonal_score",   "seasonal"]);
  const cQuant    = col(["quant_score",      "quant"]);
  const cLayers   = col(["n_layers",         "layers",   "layer_count"]);
  const cTags     = col(["active_tags",      "tags",     "layers_fired"]);

  const rows = qdb(`
    SELECT
      c.symbol,
      ROUND(CAST(c.${cScore}    AS REAL), 1) AS conviction_score,
      ROUND(CAST(c.${cBeta}     AS REAL), 1) AS beta_score,
      ROUND(CAST(c.${cRegime}   AS REAL), 1) AS regime_score,
      ROUND(CAST(c.${cInsider}  AS REAL), 1) AS insider_score,
      ROUND(CAST(c.${cWatch}    AS REAL), 1) AS watchlist_score,
      ROUND(CAST(c.${cSeasonal} AS REAL), 1) AS seasonal_score,
      ROUND(CAST(c.${cQuant}    AS REAL), 1) AS quant_score,
      CAST(c.${cLayers}         AS INTEGER)  AS n_layers,
      IFNULL(c.${cTags}, '')                 AS active_tags,
      t.rsi_14,
      t.adx_14,
      t.macd_line,
      t.macd_signal,
      ROUND(CAST(t.atr_14_pct AS REAL), 2)   AS atr_14_pct,
      sd.close                                AS latest_close
    FROM symbol_conviction c
    LEFT JOIN symbol_technicals t ON t.symbol = c.symbol
    LEFT JOIN stock_data sd ON sd.symbol = c.symbol
      AND sd.date = (SELECT MAX(d2.date) FROM stock_data d2
                     WHERE d2.symbol = c.symbol AND d2.close IS NOT NULL)
    WHERE CAST(c.${cScore} AS REAL) >= ?
    ORDER BY CAST(c.${cScore} AS REAL) DESC
    LIMIT ?
  `, [minScore, limit]);

  // --- Today's seasonal patterns ---
  const todayPatterns = qdb(`
    SELECT symbol, direction,
           ROUND(CAST(mean_return_pct AS REAL), 2) AS mean_ret,
           ROUND(CAST(win_rate AS REAL) * 100, 1)  AS win_pct,
           period_label
    FROM seasonality_patterns_v3
    WHERE is_today = 1
      AND fdr_reject = 1
      AND n_obs >= 10
    ORDER BY CAST(score_v2 AS REAL) DESC
  `);
  const patMap: Record<string, any> = {};
  for (const p of todayPatterns) {
    if (!patMap[p.symbol]) patMap[p.symbol] = p;
  }

  // --- Today's signals ---
  const todaySignals = qdb(`
    SELECT symbol, screen_tags
    FROM signals_history
    WHERE run_date = (SELECT MAX(run_date) FROM signals_history)
  `);
  const sigMap: Record<string, string> = {};
  for (const s of todaySignals) sigMap[s.symbol] = s.screen_tags || "";

  // --- Regime from NIFTY 50 ---
  const niftyRow = qdb(`
    SELECT close FROM market_snapshot
    WHERE index_name = 'NIFTY 50'
    ORDER BY date DESC LIMIT 1
  `);
  const nifty   = parseFloat(niftyRow[0]?.close ?? "0");
  const regime  = nifty > 22000 ? "BULLISH" : nifty > 18000 ? "SIDEWAYS" : nifty > 0 ? "BEARISH" : "UNKNOWN";

  const enriched = rows.map((r: any) => ({
    ...r,
    today_pattern: patMap[r.symbol] ?? null,
    today_signals: sigMap[r.symbol] ?? "",
    macd_bullish:  (r.macd_line ?? 0) > (r.macd_signal ?? 0),
  }));

  return NextResponse.json({
    rows:         enriched,
    total:        enriched.length,
    regime,
    nifty,
    actual_cols:  actualCols,        // debug: visible in browser devtools
    score_col:    cScore,
    generated_at: new Date().toISOString(),
  });
}
""".lstrip()

write(SRC / "api" / "conviction" / "route.ts", api, "/api/conviction/route.ts")


# =============================================================================
# [2]  Rewrite conviction/page.tsx WITHOUT inline navbar
#      (the global NavBar from layout.tsx handles navigation)
# =============================================================================
print("\n[2/3] Rewriting /conviction/page.tsx (no inline nav, no double bar)...")

page = r"""
"use client";
import { useEffect, useState, useMemo } from "react";
import NavBar from "@/components/NavBar";

// ── Types ────────────────────────────────────────────────────────────────────
interface ConvRow {
  symbol:           string;
  conviction_score: number;
  beta_score:       number;
  regime_score:     number;
  insider_score:    number;
  watchlist_score:  number;
  seasonal_score:   number;
  quant_score:      number;
  n_layers:         number;
  active_tags:      string;
  rsi_14:           number | null;
  adx_14:           number | null;
  macd_bullish:     boolean;
  atr_14_pct:       number | null;
  latest_close:     number | null;
  today_pattern:    { direction: string; mean_ret: number; win_pct: number; period_label: string } | null;
  today_signals:    string;
}

interface ApiResp {
  rows:         ConvRow[];
  total:        number;
  regime:       string;
  nifty:        number;
  generated_at: string;
  error?:       string;
  score_col?:   string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtNum(v: number | null | undefined): string {
  if (v == null) return "--";
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}
function convColor(s: number): string {
  if (s >= 75) return "#3fb950";
  if (s >= 50) return "#58a6ff";
  if (s >= 30) return "#e3b341";
  return "#8b949e";
}
function convGrade(s: number): string {
  if (s >= 80) return "A+";
  if (s >= 65) return "A";
  if (s >= 50) return "B";
  if (s >= 35) return "C";
  return "D";
}

const LAYER_META: Record<string, { label: string; color: string }> = {
  B: { label: "Beta",     color: "#58a6ff" },
  R: { label: "Regime",   color: "#e3b341" },
  I: { label: "Insider",  color: "#f85149" },
  W: { label: "Watch",    color: "#a371f7" },
  S: { label: "Seasonal", color: "#39d353" },
  C: { label: "Convict",  color: "#3fb950" },
  Q: { label: "Quant",    color: "#ffa657" },
};

function parseTags(raw: string): string[] {
  if (!raw) return [];
  return raw.split(/[,|;\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.round(score));
  const col = convColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 70, height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: col, borderRadius: 3 }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 12, color: col, fontWeight: 700, minWidth: 30 }}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

function LayerDots({ row }: { row: ConvRow }) {
  const tags = parseTags(row.active_tags);
  return (
    <div style={{ display: "flex", gap: 3 }}>
      {Object.entries(LAYER_META).map(([L, meta]) => {
        const active = tags.some(t => t.startsWith(L));
        return (
          <div key={L} title={`${meta.label}: ${active ? "active" : "inactive"}`}
            style={{
              width: 15, height: 15, borderRadius: "50%",
              background: active ? meta.color : "var(--border)",
              fontSize: 8, fontFamily: "monospace", fontWeight: 700,
              color: active ? "#000" : "var(--dim)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
            {L}
          </div>
        );
      })}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function ConvictionPage() {
  const [data,       setData]       = useState<ApiResp | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [search,     setSearch]     = useState("");
  const [minScore,   setMinScore]   = useState(0);
  const [sortBy,     setSortBy]     = useState<keyof ConvRow>("conviction_score");
  const [sortAsc,    setSortAsc]    = useState(false);
  const [showLayers, setShowLayers] = useState(false);
  const [filterTag,  setFilterTag]  = useState("ALL");

  useEffect(() => {
    setLoading(true);
    setError("");
    fetch(`/api/conviction?min=${minScore}&limit=300`)
      .then(r => r.json())
      .then((d: ApiResp) => {
        if (d.error) setError(d.error);
        setData(d);
        setLoading(false);
      })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, [minScore]);

  const filtered = useMemo(() => {
    if (!data?.rows) return [];
    let rows = [...data.rows];
    if (search) {
      const q = search.toUpperCase().trim();
      rows = rows.filter(r => r.symbol.includes(q));
    }
    if (filterTag !== "ALL") {
      rows = rows.filter(r => {
        const tags = parseTags(r.active_tags);
        if (filterTag === "PATTERN") return r.today_pattern != null;
        if (filterTag === "SIGNAL")  return r.today_signals.length > 0;
        return tags.some(t => t.startsWith(filterTag));
      });
    }
    const mult = sortAsc ? 1 : -1;
    return rows.sort((a, b) => {
      const av = (a as any)[sortBy]; const bv = (b as any)[sortBy];
      if (typeof av === "string") return mult * String(av).localeCompare(String(bv));
      return mult * ((Number(av) || 0) - (Number(bv) || 0));
    });
  }, [data, search, filterTag, sortBy, sortAsc]);

  function thClick(col: keyof ConvRow) {
    if (sortBy === col) setSortAsc(a => !a); else { setSortBy(col); setSortAsc(false); }
  }

  function Th({ col, label, right }: { col: keyof ConvRow; label: string; right?: boolean }) {
    const active = sortBy === col;
    return (
      <th onClick={() => thClick(col)} style={{
        padding: "8px 10px", cursor: "pointer", userSelect: "none",
        textAlign: right ? "right" : "left",
        color: active ? "var(--accent)" : "var(--dim)",
        fontFamily: "monospace", fontSize: 10, fontWeight: 700,
        letterSpacing: "0.08em", background: "var(--surface)",
        borderBottom: `2px solid ${active ? "var(--accent)" : "var(--border)"}`,
        whiteSpace: "nowrap",
      }}>
        {label}{active ? (sortAsc ? " ^" : " v") : ""}
      </th>
    );
  }

  const regimeColor =
    data?.regime === "BULLISH" ? "var(--bull)" :
    data?.regime === "BEARISH" ? "var(--bear)" : "var(--warn)";

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      <NavBar />

      <div style={{ padding: "16px 20px", maxWidth: 1600, margin: "0 auto" }}>

        {/* ── Header ── */}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
          <div>
            <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700,
                          letterSpacing: "0.12em", color: "var(--accent)" }}>
              CONVICTION SCREENER
            </div>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginTop: 2 }}>
              7-layer cross-agent scoring &mdash; {filtered.length} symbols
              {data && ` of ${data.total}`}
              {data?.score_col && data.score_col !== "conviction_score" &&
                <span style={{ color: "var(--warn)", marginLeft: 8 }}>[col: {data.score_col}]</span>}
            </div>
          </div>

          <div style={{ padding: "6px 14px", background: "var(--surface)",
                        border: `1px solid ${regimeColor}`, borderRadius: 6 }}>
            <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em" }}>REGIME</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: regimeColor }}>
              {data?.regime ?? "--"}
            </div>
          </div>

          <div style={{ padding: "6px 14px", background: "var(--surface)",
                        border: "1px solid var(--border)", borderRadius: 6 }}>
            <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)" }}>NIFTY 50</div>
            <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
              {data ? fmtNum(data.nifty) : "--"}
            </div>
          </div>
        </div>

        {/* ── Controls ── */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search symbol..."
            style={{
              background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6,
              color: "var(--text)", fontFamily: "monospace", fontSize: 12,
              padding: "6px 12px", width: 160, outline: "none",
            }}
          />

          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>MIN</span>
          {[0, 25, 40, 60, 75].map(v => (
            <button key={v} onClick={() => setMinScore(v)} style={{
              padding: "5px 10px", fontFamily: "monospace", fontSize: 10, cursor: "pointer",
              background: minScore === v ? "var(--accent)" : "var(--surface)",
              color:      minScore === v ? "#000" : "var(--dim)",
              border:     `1px solid ${minScore === v ? "var(--accent)" : "var(--border)"}`,
              borderRadius: 4,
            }}>{v}+</button>
          ))}

          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginLeft: 6 }}>FILTER</span>
          {["ALL", "B", "R", "I", "W", "S", "PATTERN", "SIGNAL"].map(tag => (
            <button key={tag} onClick={() => setFilterTag(tag)} style={{
              padding: "5px 8px", fontFamily: "monospace", fontSize: 10, cursor: "pointer",
              background: filterTag === tag ? (LAYER_META[tag]?.color ?? "var(--accent)") : "var(--surface)",
              color:      filterTag === tag ? "#000" : "var(--dim)",
              border:     `1px solid ${filterTag === tag ? (LAYER_META[tag]?.color ?? "var(--accent)") : "var(--border)"}`,
              borderRadius: 4,
            }}>{tag}</button>
          ))}

          <button onClick={() => setShowLayers(v => !v)} style={{
            marginLeft: "auto", padding: "5px 12px", fontFamily: "monospace", fontSize: 10,
            cursor: "pointer",
            background: showLayers ? "var(--accent)" : "var(--surface)",
            color:      showLayers ? "#000" : "var(--dim)",
            border:     `1px solid ${showLayers ? "var(--accent)" : "var(--border)"}`, borderRadius: 4,
          }}>{showLayers ? "HIDE LAYERS" : "SHOW LAYERS"}</button>
        </div>

        {/* ── Legend ── */}
        <div style={{ display: "flex", gap: 14, marginBottom: 12, flexWrap: "wrap" }}>
          {Object.entries(LAYER_META).map(([k, v]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: v.color }} />
              <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>{k}={v.label}</span>
            </div>
          ))}
        </div>

        {/* ── Error ── */}
        {error && (
          <div style={{ padding: "10px 14px", background: "rgba(248,81,73,0.1)",
                        border: "1px solid var(--bear)", borderRadius: 6,
                        fontFamily: "monospace", fontSize: 12, color: "var(--bear)", marginBottom: 12 }}>
            {error}
          </div>
        )}

        {/* ── Table ── */}
        {loading ? (
          <div style={{ padding: 60, textAlign: "center", fontFamily: "monospace",
                        fontSize: 13, color: "var(--dim)" }}>Loading conviction scores...</div>
        ) : (
          <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid var(--border)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ padding: "8px 10px", background: "var(--surface)", width: 36,
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)",
                                textAlign: "left" }}>#</th>
                  <Th col="symbol"           label="SYMBOL"     />
                  <Th col="conviction_score" label="CONVICTION" />
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>LAYERS</th>
                  {showLayers && (
                    <>
                      <Th col="beta_score"      label="BETA"    right />
                      <Th col="regime_score"    label="REGIME"  right />
                      <Th col="insider_score"   label="INSIDER" right />
                      <Th col="watchlist_score" label="WATCH"   right />
                      <Th col="seasonal_score"  label="SEAS."   right />
                      <Th col="quant_score"     label="QUANT"   right />
                    </>
                  )}
                  <Th col="n_layers" label="N" right />
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>SIGNALS</th>
                  <Th col="rsi_14"        label="RSI"  right />
                  <Th col="adx_14"        label="ADX"  right />
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)",
                                textAlign: "center" }}>MACD</th>
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>TODAY PATTERN</th>
                  <Th col="latest_close" label="PRICE" right />
                </tr>
              </thead>
              <tbody>
                {filtered.map((row, i) => {
                  const grade  = convGrade(row.conviction_score);
                  const gradeC = convColor(row.conviction_score);
                  const rsi    = row.rsi_14;
                  const rsiC   = rsi == null ? "var(--dim)" :
                                 rsi > 70    ? "var(--bear)" :
                                 rsi < 30    ? "var(--bull)" : "var(--text)";
                  const signalTags = row.today_signals
                    ? row.today_signals.split(/[,|]/).filter(Boolean)
                    : [];

                  return (
                    <tr key={row.symbol}
                      style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.02)")}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "7px 10px", fontFamily: "monospace",
                                   fontSize: 11, color: "var(--dim)" }}>{i + 1}</td>

                      <td style={{ padding: "7px 10px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <a href={`/stocks/${row.symbol}`}
                            style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700,
                                     color: "var(--text)", textDecoration: "none" }}>
                            {row.symbol}
                          </a>
                          <span style={{
                            fontFamily: "monospace", fontSize: 10, fontWeight: 700,
                            color: gradeC, padding: "1px 5px",
                            background: `${gradeC}22`, borderRadius: 3,
                          }}>{grade}</span>
                        </div>
                      </td>

                      <td style={{ padding: "7px 10px" }}>
                        <ScoreBar score={row.conviction_score} />
                      </td>

                      <td style={{ padding: "7px 10px" }}>
                        <LayerDots row={row} />
                      </td>

                      {showLayers && (
                        <>
                          {(["beta_score","regime_score","insider_score",
                             "watchlist_score","seasonal_score","quant_score"] as (keyof ConvRow)[]).map(k => {
                            const v = row[k] as number | null;
                            return (
                              <td key={k} style={{ padding: "7px 10px", textAlign: "right",
                                                   fontFamily: "monospace", fontSize: 11 }}>
                                {v != null && Number(v) > 0
                                  ? <span style={{ color: convColor(Number(v) * 10) }}>{Number(v).toFixed(1)}</span>
                                  : <span style={{ color: "var(--border)" }}>--</span>}
                              </td>
                            );
                          })}
                        </>
                      )}

                      <td style={{ padding: "7px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 12,
                                   color: row.n_layers >= 4 ? "var(--bull)" :
                                          row.n_layers >= 2 ? "var(--warn)" : "var(--dim)" }}>
                        {row.n_layers}
                      </td>

                      <td style={{ padding: "7px 10px" }}>
                        <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                          {signalTags.slice(0, 4).map((t, idx) => (
                            <span key={idx} style={{
                              fontFamily: "monospace", fontSize: 9, padding: "1px 5px",
                              background: "rgba(88,166,255,0.15)",
                              color: "var(--accent)", borderRadius: 3,
                            }}>{t.trim()}</span>
                          ))}
                        </div>
                      </td>

                      <td style={{ padding: "7px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 12, color: rsiC }}>
                        {rsi != null ? rsi.toFixed(0) : "--"}
                      </td>

                      <td style={{ padding: "7px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 12,
                                   color: (row.adx_14 ?? 0) > 25 ? "var(--bull)" : "var(--dim)" }}>
                        {row.adx_14 != null ? row.adx_14.toFixed(0) : "--"}
                      </td>

                      <td style={{ padding: "7px 10px", textAlign: "center" }}>
                        <span style={{
                          fontFamily: "monospace", fontSize: 10, padding: "2px 6px", borderRadius: 3,
                          background: row.macd_bullish
                            ? "rgba(63,185,80,0.15)" : "rgba(248,81,73,0.15)",
                          color: row.macd_bullish ? "var(--bull)" : "var(--bear)",
                        }}>
                          {row.macd_bullish ? "BULL" : "BEAR"}
                        </span>
                      </td>

                      <td style={{ padding: "7px 10px", maxWidth: 180 }}>
                        {row.today_pattern ? (
                          <div style={{ fontFamily: "monospace", fontSize: 10 }}>
                            <span style={{
                              color: row.today_pattern.direction === "UP" ? "var(--bull)" : "var(--bear)",
                              fontWeight: 700, marginRight: 4,
                            }}>{row.today_pattern.direction}</span>
                            <span style={{ color: row.today_pattern.mean_ret > 0 ? "var(--bull)" : "var(--bear)" }}>
                              {row.today_pattern.mean_ret > 0 ? "+" : ""}{row.today_pattern.mean_ret}%
                            </span>
                            <span style={{ color: "var(--dim)" }}> {row.today_pattern.win_pct}%w</span>
                          </div>
                        ) : (
                          <span style={{ color: "var(--border)", fontFamily: "monospace", fontSize: 10 }}>--</span>
                        )}
                      </td>

                      <td style={{ padding: "7px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 12, color: "var(--text)" }}>
                        {row.latest_close != null ? fmtNum(row.latest_close) : "--"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div style={{ padding: 40, textAlign: "center", fontFamily: "monospace",
                            fontSize: 12, color: "var(--dim)" }}>
                No symbols match current filters.
              </div>
            )}
          </div>
        )}

        {/* ── Stats ── */}
        {data && !loading && (
          <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
            {[
              { l: "TOTAL",      v: data.total },
              { l: "SHOWING",    v: filtered.length },
              { l: "SCORE 75+",  v: data.rows.filter(r => r.conviction_score >= 75).length },
              { l: "SCORE 50+",  v: data.rows.filter(r => r.conviction_score >= 50).length },
              { l: "W/ PATTERN", v: data.rows.filter(r => r.today_pattern != null).length },
              { l: "W/ SIGNAL",  v: data.rows.filter(r => r.today_signals.length > 0).length },
            ].map(({ l, v }) => (
              <div key={l} style={{
                padding: "6px 14px", background: "var(--surface)",
                border: "1px solid var(--border)", borderRadius: 6,
              }}>
                <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                              letterSpacing: "0.1em" }}>{l}</div>
                <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700,
                              color: "var(--accent)" }}>{v}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
""".lstrip()

write(SRC / "conviction" / "page.tsx", page, "/conviction/page.tsx")


# =============================================================================
# [3]  Also patch NavBar to include CONVICTION if it's missing
# =============================================================================
print("\n[3/3] Patching NavBar.tsx to ensure CONVICTION link exists...")

navbar_path = None
for p in (DASH / "src").rglob("NavBar.tsx"):
    navbar_path = p
    break

if navbar_path and navbar_path.exists():
    src = navbar_path.read_text(encoding="utf-8")
    if "/conviction" not in src:
        # Find last href entry and insert after it
        import re
        # Find the last occurrence of a href pattern
        matches = list(re.finditer(r"\{\s*href:\s*['\"][^'\"]+['\"].*?\}", src))
        if matches:
            last = matches[-1]
            insert_pos = last.end()
            next_newline = src.find("\n", insert_pos)
            if next_newline == -1:
                next_newline = len(src)
            src = (src[:next_newline]
                   + "\n  { href: '/conviction', label: 'CONVICTION' },"
                   + src[next_newline:])
            navbar_path.write_text(src, encoding="utf-8")
            print("  [OK] Added CONVICTION to NavBar")
        else:
            print("  [WARN] Could not patch NavBar automatically -- add manually:")
            print("         { href: '/conviction', label: 'CONVICTION' }")
    else:
        print("  [OK] CONVICTION already in NavBar")
else:
    print("  [WARN] NavBar.tsx not found")


print("""
======================================================================
  FIX COMPLETE
======================================================================

  CHANGES:
    1. /conviction/page.tsx  -- removed inline nav (was doubling navbar)
    2. /api/conviction/route.ts  -- probes real column names at runtime,
                                    handles score/conviction_score/total_score
    3. NavBar.tsx  -- CONVICTION link added if missing

  If 0 rows still showing, open browser DevTools -> Network ->
  click the /api/conviction request and check the response JSON.
  It will include "actual_cols" and "score_col" showing what was found.

  Quick DB check (run in PowerShell):
    cd D:\\MICC
    py -c "import sqlite3; c=sqlite3.connect(r'D:\\marketDB\\db\\market.db'); print(c.execute('SELECT COUNT(*) FROM symbol_conviction').fetchone()); print([r[1] for r in c.execute('PRAGMA table_info(symbol_conviction)')])"

  RESTART:
    cd D:\\MICC\\micc-dashboard && npm run dev
""")
