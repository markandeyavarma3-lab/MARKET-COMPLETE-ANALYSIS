# -*- coding: utf-8 -*-
"""
build_conviction_page.py  --  Run from D:\MICC
Phase 1: /conviction page

  [1] /api/conviction/route.ts   -- queries symbol_conviction + enrichment
  [2] /conviction/page.tsx       -- primary daily screening table

Tables used:
  symbol_conviction  (2181 rows: symbol, conviction_score, beta_score,
                      regime_score, insider_score, watchlist_score,
                      seasonal_score, quant_score, n_layers,
                      active_tags, last_updated)
  symbol_technicals  (rsi_14, adx_14, macd_line, macd_signal, atr_14_pct)
  stock_data         (latest close)
  signals_history    (today's pattern tags)
  seasonality_patterns_v3 (today's active pattern)

Run:  py D:\MICC\build_conviction_page.py
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
# [1]  /api/conviction/route.ts
# =============================================================================
print("\n[1/2] Writing /api/conviction/route.ts ...")

api = r"""
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";
const PY = "py";

function sanitize(s: string) {
  return s
    .replace(/:[ \t]*NaN\b/g, ": null")
    .replace(/:[ \t]*-?Infinity\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const payload = JSON.stringify({ sql, params });
  const b64 = Buffer.from(payload).toString("base64");
  const py = [
    "import sqlite3,json,sys,base64",
    "conn=sqlite3.connect(r'" + DB + "',timeout=15)",
    "conn.row_factory=sqlite3.Row",
    "d=json.loads(base64.b64decode(sys.argv[1]).decode())",
    "rows=conn.execute(d['sql'],d['params']).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\\n");
  const r = spawnSync(PY, ["-c", py, b64], { cwd: DA, encoding: "utf-8", timeout: 20000 });
  if (r.status !== 0) {
    console.error("[conviction api]", r.stderr?.slice(0, 200));
    return [];
  }
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); }
  catch { return []; }
}

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url     = new URL(req.url);
  const minScore = parseFloat(url.searchParams.get("min") || "0");
  const sortBy   = url.searchParams.get("sort") || "conviction_score";
  const limit    = parseInt(url.searchParams.get("limit") || "200");

  // --- Main conviction table with enrichment ---
  const allowedSort = [
    "conviction_score","beta_score","regime_score","insider_score",
    "watchlist_score","seasonal_score","quant_score","n_layers","symbol"
  ];
  const sortCol = allowedSort.includes(sortBy) ? sortBy : "conviction_score";

  const rows = qdb(`
    SELECT
      c.symbol,
      ROUND(CAST(c.conviction_score AS REAL),1)  AS conviction_score,
      ROUND(CAST(c.beta_score       AS REAL),1)  AS beta_score,
      ROUND(CAST(c.regime_score     AS REAL),1)  AS regime_score,
      ROUND(CAST(c.insider_score    AS REAL),1)  AS insider_score,
      ROUND(CAST(c.watchlist_score  AS REAL),1)  AS watchlist_score,
      ROUND(CAST(c.seasonal_score   AS REAL),1)  AS seasonal_score,
      ROUND(CAST(c.quant_score      AS REAL),1)  AS quant_score,
      CAST(c.n_layers AS INTEGER)                AS n_layers,
      IFNULL(c.active_tags,'')                   AS active_tags,
      c.last_updated,
      t.rsi_14,
      t.adx_14,
      t.macd_line,
      t.macd_signal,
      ROUND(CAST(t.atr_14_pct AS REAL),2)        AS atr_14_pct,
      sd.close                                    AS latest_close,
      sd.date                                     AS price_date
    FROM symbol_conviction c
    LEFT JOIN symbol_technicals t ON t.symbol = c.symbol
    LEFT JOIN (
      SELECT symbol, close, date
      FROM stock_data
      WHERE (symbol, date) IN (
        SELECT symbol, MAX(date) FROM stock_data
        WHERE close IS NOT NULL
        GROUP BY symbol
      )
    ) sd ON sd.symbol = c.symbol
    WHERE CAST(c.conviction_score AS REAL) >= ?
    ORDER BY CAST(c.${sortCol} AS REAL) DESC
    LIMIT ?
  `, [minScore, limit]);

  // --- Today's seasonal patterns (top hit per symbol) ---
  const todayPatterns = qdb(`
    SELECT symbol,
           direction,
           ROUND(CAST(mean_return_pct AS REAL),2) AS mean_ret,
           ROUND(CAST(score_v2 AS REAL),2)        AS score,
           ROUND(CAST(win_rate AS REAL)*100,1)     AS win_pct,
           period_label
    FROM seasonality_patterns_v3
    WHERE is_today = 1
      AND fdr_reject = 1
      AND n_obs >= 10
    ORDER BY score_v2 DESC
  `);

  const patMap: Record<string, any> = {};
  for (const p of todayPatterns) {
    if (!patMap[p.symbol]) patMap[p.symbol] = p;
  }

  // --- Today's signal tags from signals_history ---
  const todaySignals = qdb(`
    SELECT symbol, screen_tags, score
    FROM signals_history
    WHERE run_date = (SELECT MAX(run_date) FROM signals_history)
  `);
  const sigMap: Record<string, string> = {};
  for (const s of todaySignals) {
    sigMap[s.symbol] = s.screen_tags || "";
  }

  // --- Regime ---
  const regimeRow = qdb(`
    SELECT close
    FROM market_snapshot
    WHERE index_name = 'NIFTY 50'
    ORDER BY date DESC LIMIT 1
  `);
  const nifty = regimeRow[0]?.close ?? 0;
  const regime = nifty > 0
    ? (nifty > 22000 ? "BULLISH" : nifty > 18000 ? "SIDEWAYS" : "BEARISH")
    : "UNKNOWN";

  // Enrich rows
  const enriched = rows.map((r: any) => ({
    ...r,
    today_pattern:   patMap[r.symbol] ?? null,
    today_signals:   sigMap[r.symbol] ?? "",
    macd_bullish:    (r.macd_line ?? 0) > (r.macd_signal ?? 0),
  }));

  return NextResponse.json({
    rows:     enriched,
    total:    enriched.length,
    regime,
    nifty,
    generated_at: new Date().toISOString(),
  });
}
""".lstrip()

write(SRC / "api" / "conviction" / "route.ts", api, "/api/conviction/route.ts")


# =============================================================================
# [2]  /conviction/page.tsx
# =============================================================================
print("\n[2/2] Writing /conviction/page.tsx ...")

page = r"""
"use client";
import { useEffect, useState, useMemo } from "react";

// ── Types ────────────────────────────────────────────────────────────────────
interface ConvRow {
  symbol:          string;
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
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const C = {
  bg:      "#0d1117",
  surface: "#161b22",
  border:  "#21262d",
  text:    "#e6edf3",
  dim:     "#8b949e",
  accent:  "#58a6ff",
  bull:    "#3fb950",
  bear:    "#f85149",
  warn:    "#e3b341",
  cyan:    "#39d353",
  purple:  "#a371f7",
};

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

// Layer tag definitions
const LAYER_META: Record<string, { label: string; color: string; key: keyof ConvRow }> = {
  B: { label: "Beta",     color: "#58a6ff", key: "beta_score"      },
  R: { label: "Regime",   color: "#e3b341", key: "regime_score"    },
  I: { label: "Insider",  color: "#f85149", key: "insider_score"   },
  W: { label: "Watch",    color: "#a371f7", key: "watchlist_score" },
  S: { label: "Seasonal", color: "#39d353", key: "seasonal_score"  },
  C: { label: "Convict",  color: "#3fb950", key: "quant_score"     },
  Q: { label: "Quant",    color: "#ffa657", key: "quant_score"     },
};

// Parse active_tags like "B,I,S" or "Beta,Seasonal"
function parseTags(raw: string): string[] {
  if (!raw) return [];
  return raw.split(/[,|]/).map(t => t.trim()).filter(Boolean);
}

// Score bar
function ScoreBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.min(100, Math.round((score / max) * 100));
  const col = convColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 70, height: 6, background: C.border, borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: col, borderRadius: 3 }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 12, color: col, fontWeight: 700, minWidth: 32 }}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

// Mini layer dots
function LayerDots({ row }: { row: ConvRow }) {
  const tags = parseTags(row.active_tags);
  const layers = ["B","R","I","W","S","C","Q"];
  return (
    <div style={{ display: "flex", gap: 3 }}>
      {layers.map(L => {
        const meta = LAYER_META[L];
        const active = tags.some(t => t.startsWith(L) || t.toLowerCase().startsWith(meta.label.toLowerCase()));
        return (
          <div
            key={L}
            title={`${meta.label}: ${active ? "active" : "inactive"}`}
            style={{
              width: 14, height: 14, borderRadius: "50%",
              background: active ? meta.color : C.border,
              border: `1px solid ${active ? meta.color : C.border}`,
              fontSize: 8, fontFamily: "monospace", fontWeight: 700,
              color: active ? "#000" : C.dim,
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "default",
            }}
          >
            {L}
          </div>
        );
      })}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function ConvictionPage() {
  const [data,       setData]       = useState<ApiResp | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [search,     setSearch]     = useState("");
  const [minScore,   setMinScore]   = useState(0);
  const [sortBy,     setSortBy]     = useState<keyof ConvRow>("conviction_score");
  const [sortAsc,    setSortAsc]    = useState(false);
  const [showLayers, setShowLayers] = useState(false);
  const [selected,   setSelected]   = useState<string | null>(null);
  const [filterTag,  setFilterTag]  = useState<string>("ALL");

  useEffect(() => {
    setLoading(true);
    fetch(`/api/conviction?min=${minScore}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, [minScore]);

  const filtered = useMemo(() => {
    if (!data?.rows) return [];
    let rows = data.rows;

    if (search) {
      const q = search.toUpperCase();
      rows = rows.filter(r => r.symbol.includes(q));
    }

    if (filterTag !== "ALL") {
      rows = rows.filter(r => {
        const tags = parseTags(r.active_tags);
        if (filterTag === "PATTERN") return r.today_pattern != null;
        if (filterTag === "SIGNAL")  return r.today_signals.length > 0;
        return tags.some(t =>
          t.startsWith(filterTag) ||
          t.toLowerCase().startsWith((LAYER_META[filterTag]?.label ?? "").toLowerCase())
        );
      });
    }

    const mult = sortAsc ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      const av = (a as any)[sortBy] ?? 0;
      const bv = (b as any)[sortBy] ?? 0;
      if (typeof av === "string") return mult * av.localeCompare(bv);
      return mult * ((Number(av) || 0) - (Number(bv) || 0));
    });

    return rows;
  }, [data, search, filterTag, sortBy, sortAsc]);

  function thClick(col: keyof ConvRow) {
    if (sortBy === col) setSortAsc(a => !a);
    else { setSortBy(col); setSortAsc(false); }
  }

  function Th({ col, label, right }: { col: keyof ConvRow; label: string; right?: boolean }) {
    const active = sortBy === col;
    return (
      <th
        onClick={() => thClick(col)}
        style={{
          padding: "8px 10px", cursor: "pointer", userSelect: "none",
          textAlign: right ? "right" : "left",
          color: active ? C.accent : C.dim,
          fontFamily: "monospace", fontSize: 10, fontWeight: 700,
          letterSpacing: "0.08em", background: C.surface,
          borderBottom: `2px solid ${active ? C.accent : C.border}`,
          whiteSpace: "nowrap",
        }}
      >
        {label}{active ? (sortAsc ? " ^" : " v") : ""}
      </th>
    );
  }

  const regimeColor =
    data?.regime === "BULLISH" ? C.bull :
    data?.regime === "BEARISH" ? C.bear : C.warn;

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, fontFamily: "system-ui, sans-serif" }}>

      {/* ── Nav ── */}
      <div style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "10px 20px",
                    display: "flex", alignItems: "center", gap: 16 }}>
        <a href="/" style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700,
                              color: C.accent, textDecoration: "none" }}>MICC</a>
        {[
          ["/","OVERVIEW"], ["/streaks","STREAKS"], ["/patterns","PATTERNS"],
          ["/watchlist","WATCH"], ["/eta","ETA"], ["/conviction","CONVICTION"],
          ["/portfolio","PORTFOLIO"], ["/alerts","ALERTS"],
        ].map(([href, label]) => (
          <a key={href} href={href} style={{
            fontFamily: "monospace", fontSize: 10, letterSpacing: "0.1em",
            color: href === "/conviction" ? C.text : C.dim,
            textDecoration: "none",
            borderBottom: href === "/conviction" ? `2px solid ${C.accent}` : "2px solid transparent",
            paddingBottom: 2,
          }}>{label}</a>
        ))}
        <div style={{ marginLeft: "auto", fontFamily: "monospace", fontSize: 10, color: C.dim }}>
          {data ? new Date(data.generated_at).toLocaleTimeString("en-IN") : ""}
        </div>
      </div>

      {/* ── Header ── */}
      <div style={{ padding: "16px 20px 0", maxWidth: 1600, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 20, flexWrap: "wrap", marginBottom: 16 }}>
          <div>
            <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700,
                          letterSpacing: "0.12em", color: C.accent }}>
              CONVICTION SCREENER
            </div>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: C.dim, marginTop: 2 }}>
              7-layer cross-agent scoring — {filtered.length} symbols
              {data && ` of ${data.total}`}
            </div>
          </div>

          {/* Regime badge */}
          {data && (
            <div style={{ padding: "6px 14px", background: "rgba(0,0,0,0.3)",
                          border: `1px solid ${regimeColor}`, borderRadius: 6 }}>
              <div style={{ fontFamily: "monospace", fontSize: 9, color: C.dim, letterSpacing: "0.1em" }}>REGIME</div>
              <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: regimeColor }}>
                {data.regime}
              </div>
            </div>
          )}

          {/* NIFTY */}
          {data && (
            <div style={{ padding: "6px 14px", background: "rgba(0,0,0,0.3)",
                          border: `1px solid ${C.border}`, borderRadius: 6 }}>
              <div style={{ fontFamily: "monospace", fontSize: 9, color: C.dim }}>NIFTY 50</div>
              <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: C.text }}>
                {fmtNum(data.nifty)}
              </div>
            </div>
          )}
        </div>

        {/* ── Controls ── */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
          {/* Search */}
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search symbol..."
            style={{
              background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.text, fontFamily: "monospace", fontSize: 12, padding: "6px 12px",
              width: 160, outline: "none",
            }}
          />

          {/* Min score */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontFamily: "monospace", fontSize: 10, color: C.dim }}>MIN SCORE</span>
            {[0, 25, 40, 60, 75].map(v => (
              <button
                key={v}
                onClick={() => setMinScore(v)}
                style={{
                  padding: "5px 10px", fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                  background: minScore === v ? C.accent : C.surface,
                  color:      minScore === v ? "#000" : C.dim,
                  border:     `1px solid ${minScore === v ? C.accent : C.border}`,
                  borderRadius: 4,
                }}
              >{v}+</button>
            ))}
          </div>

          {/* Layer filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ fontFamily: "monospace", fontSize: 10, color: C.dim }}>FILTER</span>
            {["ALL","B","R","I","W","S","PATTERN","SIGNAL"].map(tag => (
              <button
                key={tag}
                onClick={() => setFilterTag(tag)}
                style={{
                  padding: "5px 8px", fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                  background: filterTag === tag ? (LAYER_META[tag]?.color ?? C.accent) : C.surface,
                  color:      filterTag === tag ? "#000" : C.dim,
                  border:     `1px solid ${filterTag === tag ? (LAYER_META[tag]?.color ?? C.accent) : C.border}`,
                  borderRadius: 4,
                }}
              >{tag}</button>
            ))}
          </div>

          {/* Layer columns toggle */}
          <button
            onClick={() => setShowLayers(v => !v)}
            style={{
              marginLeft: "auto", padding: "5px 12px", fontFamily: "monospace", fontSize: 10,
              cursor: "pointer",
              background: showLayers ? C.accent : C.surface,
              color:      showLayers ? "#000" : C.dim,
              border:     `1px solid ${showLayers ? C.accent : C.border}`,
              borderRadius: 4,
            }}
          >{showLayers ? "HIDE LAYERS" : "SHOW LAYERS"}</button>
        </div>

        {/* ── Legend ── */}
        <div style={{ display: "flex", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
          {Object.entries(LAYER_META).map(([k, v]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: v.color }} />
              <span style={{ fontFamily: "monospace", fontSize: 10, color: C.dim }}>{k}={v.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Table ── */}
      <div style={{ padding: "0 20px 40px", maxWidth: 1600, margin: "0 auto" }}>
        {loading && (
          <div style={{ padding: 60, textAlign: "center", fontFamily: "monospace",
                        fontSize: 13, color: C.dim }}>Loading conviction scores...</div>
        )}
        {error && (
          <div style={{ padding: 20, color: C.bear, fontFamily: "monospace", fontSize: 12 }}>
            Error: {error}
          </div>
        )}
        {!loading && !error && (
          <div style={{ overflowX: "auto", borderRadius: 8, border: `1px solid ${C.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ padding: "8px 10px", background: C.surface,
                                borderBottom: `2px solid ${C.border}`,
                                fontFamily: "monospace", fontSize: 10, color: C.dim,
                                textAlign: "left", width: 32 }}>#</th>
                  <Th col="symbol"           label="SYMBOL" />
                  <Th col="conviction_score" label="CONVICTION" />
                  <th style={{ padding: "8px 10px", background: C.surface,
                                borderBottom: `2px solid ${C.border}`,
                                fontFamily: "monospace", fontSize: 10, color: C.dim,
                                textAlign: "left" }}>LAYERS</th>
                  {showLayers && <>
                    <Th col="beta_score"      label="BETA"    right />
                    <Th col="regime_score"    label="REGIME"  right />
                    <Th col="insider_score"   label="INSIDER" right />
                    <Th col="watchlist_score" label="WATCH"   right />
                    <Th col="seasonal_score"  label="SEAS."   right />
                    <Th col="quant_score"     label="QUANT"   right />
                  </>}
                  <Th col="n_layers" label="N" right />
                  <th style={{ padding: "8px 10px", background: C.surface,
                                borderBottom: `2px solid ${C.border}`,
                                fontFamily: "monospace", fontSize: 10, color: C.dim,
                                textAlign: "left" }}>SIGNALS</th>
                  <Th col="rsi_14" label="RSI"  right />
                  <Th col="adx_14" label="ADX"  right />
                  <th style={{ padding: "8px 10px", background: C.surface,
                                borderBottom: `2px solid ${C.border}`,
                                fontFamily: "monospace", fontSize: 10, color: C.dim,
                                textAlign: "center" }}>MACD</th>
                  <th style={{ padding: "8px 10px", background: C.surface,
                                borderBottom: `2px solid ${C.border}`,
                                fontFamily: "monospace", fontSize: 10, color: C.dim,
                                textAlign: "left" }}>TODAY PATTERN</th>
                  <Th col="latest_close" label="PRICE" right />
                </tr>
              </thead>
              <tbody>
                {filtered.map((row, i) => {
                  const grade   = convGrade(row.conviction_score);
                  const gradeC  = convColor(row.conviction_score);
                  const isExp   = selected === row.symbol;
                  const rsi     = row.rsi_14 ?? null;
                  const rsiC    = rsi == null ? C.dim :
                                  rsi > 70 ? C.bear : rsi < 30 ? C.bull : C.text;
                  const signalTags = row.today_signals
                    ? row.today_signals.split(",").filter(Boolean)
                    : [];

                  return (
                    <tr
                      key={row.symbol}
                      onClick={() => setSelected(isExp ? null : row.symbol)}
                      style={{
                        borderBottom: `1px solid ${C.border}`,
                        background: isExp ? "rgba(88,166,255,0.06)" : "transparent",
                        cursor: "pointer",
                        transition: "background 0.1s",
                      }}
                      onMouseEnter={e => { if (!isExp) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.02)"; }}
                      onMouseLeave={e => { if (!isExp) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                    >
                      {/* Rank */}
                      <td style={{ padding: "8px 10px", fontFamily: "monospace", fontSize: 11, color: C.dim }}>
                        {i + 1}
                      </td>

                      {/* Symbol + grade */}
                      <td style={{ padding: "8px 10px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <a
                            href={`/stocks/${row.symbol}`}
                            onClick={e => e.stopPropagation()}
                            style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700,
                                     color: C.text, textDecoration: "none" }}
                          >{row.symbol}</a>
                          <span style={{
                            fontFamily: "monospace", fontSize: 10, fontWeight: 700,
                            color: gradeC, padding: "1px 5px",
                            background: `${gradeC}22`, borderRadius: 3,
                          }}>{grade}</span>
                        </div>
                      </td>

                      {/* Score bar */}
                      <td style={{ padding: "8px 10px" }}>
                        <ScoreBar score={row.conviction_score} />
                      </td>

                      {/* Layer dots */}
                      <td style={{ padding: "8px 10px" }}>
                        <LayerDots row={row} />
                      </td>

                      {/* Per-layer scores (conditional) */}
                      {showLayers && <>
                        {(["beta_score","regime_score","insider_score",
                           "watchlist_score","seasonal_score","quant_score"] as (keyof ConvRow)[]).map(k => {
                          const v = row[k] as number | null;
                          return (
                            <td key={k} style={{ padding: "8px 10px", textAlign: "right",
                                                 fontFamily: "monospace", fontSize: 11 }}>
                              {v != null && v > 0
                                ? <span style={{ color: convColor(v * 10) }}>{(v).toFixed(1)}</span>
                                : <span style={{ color: C.border }}>--</span>}
                            </td>
                          );
                        })}
                      </>}

                      {/* N layers */}
                      <td style={{ padding: "8px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 12,
                                   color: row.n_layers >= 4 ? C.bull :
                                          row.n_layers >= 2 ? C.warn : C.dim }}>
                        {row.n_layers}
                      </td>

                      {/* Signal tags */}
                      <td style={{ padding: "8px 10px" }}>
                        <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                          {signalTags.slice(0, 4).map(t => (
                            <span key={t} style={{
                              fontFamily: "monospace", fontSize: 9, padding: "1px 5px",
                              background: "rgba(88,166,255,0.15)",
                              color: C.accent, borderRadius: 3,
                            }}>{t.trim()}</span>
                          ))}
                        </div>
                      </td>

                      {/* RSI */}
                      <td style={{ padding: "8px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 11, color: rsiC }}>
                        {rsi != null ? rsi.toFixed(0) : "--"}
                      </td>

                      {/* ADX */}
                      <td style={{ padding: "8px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 11,
                                   color: (row.adx_14 ?? 0) > 25 ? C.bull : C.dim }}>
                        {row.adx_14 != null ? row.adx_14.toFixed(0) : "--"}
                      </td>

                      {/* MACD */}
                      <td style={{ padding: "8px 10px", textAlign: "center" }}>
                        <span style={{
                          fontFamily: "monospace", fontSize: 10, padding: "2px 6px",
                          borderRadius: 3,
                          background: row.macd_bullish ? "rgba(63,185,80,0.15)" : "rgba(248,81,73,0.15)",
                          color:       row.macd_bullish ? C.bull : C.bear,
                        }}>
                          {row.macd_bullish ? "BULL" : "BEAR"}
                        </span>
                      </td>

                      {/* Today pattern */}
                      <td style={{ padding: "8px 10px", maxWidth: 200 }}>
                        {row.today_pattern ? (
                          <div style={{ fontFamily: "monospace", fontSize: 10 }}>
                            <span style={{
                              color: row.today_pattern.direction === "UP" ? C.bull : C.bear,
                              fontWeight: 700, marginRight: 4,
                            }}>{row.today_pattern.direction}</span>
                            <span style={{ color: C.dim }}>{row.today_pattern.period_label} </span>
                            <span style={{
                              color: row.today_pattern.mean_ret > 0 ? C.bull : C.bear,
                            }}>{row.today_pattern.mean_ret > 0 ? "+" : ""}{row.today_pattern.mean_ret}%</span>
                            <span style={{ color: C.dim }}> {row.today_pattern.win_pct}%w</span>
                          </div>
                        ) : (
                          <span style={{ color: C.border, fontFamily: "monospace", fontSize: 10 }}>--</span>
                        )}
                      </td>

                      {/* Price */}
                      <td style={{ padding: "8px 10px", textAlign: "right",
                                   fontFamily: "monospace", fontSize: 12, color: C.text }}>
                        {row.latest_close != null ? fmtNum(row.latest_close) : "--"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {filtered.length === 0 && !loading && (
              <div style={{ padding: 40, textAlign: "center", fontFamily: "monospace",
                            fontSize: 12, color: C.dim }}>
                No symbols match current filters.
              </div>
            )}
          </div>
        )}

        {/* ── Stats row ── */}
        {data && !loading && (
          <div style={{ display: "flex", gap: 16, marginTop: 14, flexWrap: "wrap" }}>
            {[
              { l: "TOTAL",     v: data.total },
              { l: "SHOWING",   v: filtered.length },
              { l: "SCORE 75+", v: data.rows.filter(r => r.conviction_score >= 75).length },
              { l: "SCORE 50+", v: data.rows.filter(r => r.conviction_score >= 50).length },
              { l: "W/ PATTERN",v: data.rows.filter(r => r.today_pattern != null).length },
              { l: "W/ SIGNAL", v: data.rows.filter(r => r.today_signals.length > 0).length },
            ].map(({ l, v }) => (
              <div key={l} style={{
                padding: "6px 14px", background: C.surface,
                border: `1px solid ${C.border}`, borderRadius: 6,
              }}>
                <div style={{ fontFamily: "monospace", fontSize: 9, color: C.dim, letterSpacing: "0.1em" }}>{l}</div>
                <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700, color: C.accent }}>{v}</div>
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
# SUMMARY
# =============================================================================
print("""
======================================================================
  /conviction PAGE COMPLETE
======================================================================

  FILES WRITTEN:
    src/app/api/conviction/route.ts   -- API: queries symbol_conviction
    src/app/conviction/page.tsx       -- Primary daily screening table

  FEATURES:
    - Score bar 0-100 with color grading (A+/A/B/C/D)
    - Layer dots: B R I W S C Q  (colored, active = filled)
    - SHOW LAYERS toggle: expands per-layer score columns
    - Filters: min score (0/25/40/60/75), layer tag, pattern/signal
    - Sort: click any column header
    - Today's seasonal pattern (direction, mean%, win%)
    - Today's signal tags from signals_history
    - RSI (red >70, green <30), ADX (green >25), MACD bull/bear
    - Regime badge (BULLISH/SIDEWAYS/BEARISH) from NIFTY 50
    - Clickable symbol -> /stocks/<SYMBOL>

  NOTE: The API uses a subquery for latest close that may be slow
  on first load (~3-5s). Subsequent loads from SQLite cache are fast.

  RESTART:
    cd D:\\MICC\\micc-dashboard && npm run dev

  OPEN:
    http://localhost:3000/conviction

  IF symbol_conviction columns differ from expected, check:
    SELECT name FROM pragma_table_info('symbol_conviction');
  Then adjust route.ts column names accordingly.
""")
