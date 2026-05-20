# -*- coding: utf-8 -*-
"""
build_fusion_page.py  --  Run from D:\MICC

Builds:
  [1] /api/fusion/route.ts   -- reads agents/fusion/last_report.json
                                 + enriches with live technicals from DB
  [2] /fusion/page.tsx       -- top picks table with 7-layer breakdown

Style: matches exact MICC globals.css design system
  --bg #090b0f  --surface #0d1117  --border #1e2530
  --accent #00d4aa  --bull #26c485  --bear #f85149
  --warn #e3b341  --info #58a6ff  --dim #768390
  Font: JetBrains Mono / monospace

Run: py D:\MICC\build_fusion_page.py
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
# [1]  /api/fusion/route.ts
# =============================================================================
print("\n[1/2] Writing /api/fusion/route.ts ...")

api = r"""
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { readFileSync } from "fs";
import { Buffer }       from "buffer";

const DA = "D:/MICC";
const DB = "D:/marketDB/db/market.db";
const PY = "py";

function sanitize(s: string) {
  return s.replace(/:[ \t]*NaN\b/g, ": null").replace(/:[ \t]*-?Infinity\b/g, ": null");
}

function qdb(sql: string, params: (string | number)[] = []): any[] {
  const payload = Buffer.from(JSON.stringify({ sql, params })).toString("base64");
  const script = `
import sqlite3,json,base64,sys
d=json.loads(base64.b64decode(sys.argv[1]))
conn=sqlite3.connect(r'${DB}',timeout=15)
conn.row_factory=sqlite3.Row
rows=conn.execute(d['sql'],d['params']).fetchall()
print(json.dumps([dict(r) for r in rows],default=str))
conn.close()`.trim();
  const r = spawnSync(PY, ["-c", script, payload], {
    cwd: DA, encoding: "utf-8", timeout: 20000,
  });
  if (r.status !== 0) { console.error("[fusion]", r.stderr?.slice(0, 200)); return []; }
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

function readJson(relPath: string): any {
  try {
    const raw = readFileSync(`${DA}/${relPath}`, "utf-8");
    return JSON.parse(sanitize(raw));
  } catch { return null; }
}

export const dynamic = "force-dynamic";

export async function GET() {
  // ── Read fusion report ────────────────────────────────────────────────────
  const report = readJson("agents/fusion/last_report.json");

  if (!report) {
    return NextResponse.json({
      picks: [], meta: null, regime: "UNKNOWN", nifty: 0,
      error: "agents/fusion/last_report.json not found. Run: py D:/MICC/agent_fusion.py",
      generated_at: new Date().toISOString(),
    });
  }

  // ── Normalise picks array ─────────────────────────────────────────────────
  // agent_fusion may write: report.picks or report.fused_picks or report.top_picks
  const rawPicks: any[] =
    report.picks ?? report.fused_picks ?? report.top_picks ?? [];

  // Collect all symbols for bulk DB lookup
  const syms = rawPicks.map((p: any) => p.symbol).filter(Boolean);
  if (syms.length === 0) {
    return NextResponse.json({
      picks: [], meta: report.meta ?? report.summary ?? null,
      regime: "UNKNOWN", nifty: 0,
      error: "No picks in fusion report",
      generated_at: new Date().toISOString(),
    });
  }

  const placeholders = syms.map(() => "?").join(",");

  // ── Bulk fetch technicals ──────────────────────────────────────────────────
  const techs = qdb(
    `SELECT symbol, rsi_14, adx_14, macd_line, macd_signal,
            ROUND(CAST(atr_14_pct AS REAL),2) AS atr_14_pct,
            ROUND(CAST(pct_from_52w_high AS REAL),1) AS pct_52h,
            ROUND(CAST(pct_above_sma20 AS REAL),1) AS pct_sma20
     FROM symbol_technicals WHERE symbol IN (${placeholders})`,
    syms
  );
  const techMap: Record<string, any> = {};
  for (const t of techs) techMap[t.symbol] = t;

  // ── Bulk fetch latest prices ───────────────────────────────────────────────
  const prices = qdb(
    `SELECT symbol, close, date FROM stock_data
     WHERE date = (SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)
       AND symbol IN (${placeholders}) AND close IS NOT NULL`,
    syms
  );
  const priceMap: Record<string, any> = {};
  for (const p of prices) priceMap[p.symbol] = p;

  // ── Fetch today's seasonal pattern per symbol ─────────────────────────────
  const pats = qdb(
    `SELECT symbol, direction,
            ROUND(CAST(mean_ret AS REAL),2) AS mean_ret,
            ROUND(CAST(accuracy AS REAL)*100,1) AS win_pct,
            window_days
     FROM seasonality_patterns_v3
     WHERE anchor_mm_dd = strftime('%m-%d','now','localtime')
       AND fdr_reject = 1 AND n_obs >= 10
       AND symbol IN (${placeholders})
     ORDER BY CAST(score_v2 AS REAL) DESC`,
    syms
  );
  const patMap: Record<string, any> = {};
  for (const p of pats) { if (!patMap[p.symbol]) patMap[p.symbol] = p; }

  // ── Nifty / regime ────────────────────────────────────────────────────────
  const nr = qdb(
    `SELECT closing_index_value AS close FROM market_snapshot
     WHERE index_name='NIFTY 50' ORDER BY date DESC LIMIT 1`
  );
  const nifty  = parseFloat(nr[0]?.close ?? "0");
  const regime = nifty > 22000 ? "BULLISH" : nifty > 18000 ? "SIDEWAYS" : nifty > 0 ? "BEARISH" : "UNKNOWN";

  // ── Merge everything ──────────────────────────────────────────────────────
  const picks = rawPicks.map((p: any) => {
    const t = techMap[p.symbol]  ?? {};
    const pr = priceMap[p.symbol] ?? {};
    const pat = patMap[p.symbol] ?? null;
    return {
      symbol:          p.symbol,
      total_score:     parseFloat(p.total_score ?? p.score ?? 0),
      n_layers:        parseInt(p.n_layers ?? p.layers ?? 0),
      layers_fired:    p.layers_fired ?? p.active_layers ?? p.layers ?? [],
      reasons:         p.reasons ?? p.reason ?? [],
      // per-layer scores (agent_fusion may or may not include these)
      beta_score:      parseFloat(p.beta_score      ?? p.layer_scores?.beta      ?? 0),
      regime_score:    parseFloat(p.regime_score    ?? p.layer_scores?.regime    ?? 0),
      insider_score:   parseFloat(p.insider_score   ?? p.layer_scores?.insider   ?? 0),
      watchlist_score: parseFloat(p.watchlist_score ?? p.layer_scores?.watchlist ?? 0),
      seasonal_score:  parseFloat(p.seasonal_score  ?? p.layer_scores?.seasonal  ?? 0),
      conviction_score:parseFloat(p.conviction_score?? p.layer_scores?.conviction?? 0),
      quant_score:     parseFloat(p.quant_score     ?? p.layer_scores?.quant     ?? 0),
      // live enrichment
      rsi_14:      t.rsi_14      ?? null,
      adx_14:      t.adx_14      ?? null,
      atr_pct:     t.atr_14_pct  ?? null,
      pct_52h:     t.pct_52h     ?? null,
      pct_sma20:   t.pct_sma20   ?? null,
      macd_bull:   (t.macd_line ?? 0) > (t.macd_signal ?? 0),
      price:       pr.close      ?? null,
      price_date:  pr.date       ?? null,
      today_pat:   pat,
    };
  });

  // Sort by total_score desc
  picks.sort((a: any, b: any) => b.total_score - a.total_score);

  return NextResponse.json({
    picks,
    meta:         report.meta ?? report.summary ?? null,
    report_date:  report.date ?? report.generated_at ?? null,
    regime,
    nifty,
    n_total:      picks.length,
    generated_at: new Date().toISOString(),
  });
}
""".lstrip()

write(SRC / "api" / "fusion" / "route.ts", api, "/api/fusion/route.ts")


# =============================================================================
# [2]  /fusion/page.tsx
# =============================================================================
print("\n[2/2] Writing /fusion/page.tsx ...")

page = r"""
"use client";
import { useEffect, useState, useMemo } from "react";
import NavBar from "@/components/NavBar";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Pick {
  symbol:           string;
  total_score:      number;
  n_layers:         number;
  layers_fired:     string[] | string;
  reasons:          string[] | string;
  beta_score:       number;
  regime_score:     number;
  insider_score:    number;
  watchlist_score:  number;
  seasonal_score:   number;
  conviction_score: number;
  quant_score:      number;
  rsi_14:           number | null;
  adx_14:           number | null;
  atr_pct:          number | null;
  pct_52h:          number | null;
  macd_bull:        boolean;
  price:            number | null;
  today_pat:        { direction: string; mean_ret: number; win_pct: number; window_days: number } | null;
}

interface Resp {
  picks:       Pick[];
  meta:        any;
  report_date: string | null;
  regime:      string;
  nifty:       number;
  n_total:     number;
  error?:      string;
  generated_at:string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fn = (v: number | null, dec = 2) =>
  v == null ? "--" : v.toLocaleString("en-IN", { maximumFractionDigits: dec });

const scoreColor = (s: number) =>
  s >= 6 ? "var(--bull)" : s >= 4 ? "var(--accent)" : s >= 2 ? "var(--warn)" : "var(--dim)";

const LAYERS = [
  { k: "beta",       label: "Beta",       color: "var(--info)"   },
  { k: "regime",     label: "Regime",     color: "var(--warn)"   },
  { k: "insider",    label: "Insider",    color: "var(--bear)"   },
  { k: "watchlist",  label: "Watch",      color: "#a371f7"       },
  { k: "seasonal",   label: "Seasonal",   color: "var(--bull)"   },
  { k: "conviction", label: "Conviction", color: "var(--accent)" },
  { k: "quant",      label: "Quant",      color: "#ffa657"       },
];

function parseLayers(raw: string[] | string): string[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw.map(l => String(l).toLowerCase());
  return String(raw).toLowerCase().split(/[,|;\s]+/).filter(Boolean);
}

function parseReasons(raw: string[] | string): string[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw.map(String);
  return [String(raw)];
}

// ── Sub-components ────────────────────────────────────────────────────────────
function ScoreBar({ score, max = 7 }: { score: number; max?: number }) {
  const pct = Math.min(100, Math.round((score / max) * 100));
  const col = scoreColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 60, height: 5, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: col, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 12, color: col, fontWeight: 700, minWidth: 24 }}>
        {score.toFixed(1)}
      </span>
    </div>
  );
}

function LayerDots({ fired, scores }: { fired: string[]; scores: Record<string, number> }) {
  return (
    <div style={{ display: "flex", gap: 3 }}>
      {LAYERS.map(({ k, label, color }) => {
        const on = fired.some(f => f.includes(k.slice(0, 4)));
        return (
          <div key={k} title={`${label}${scores[k] ? `: ${scores[k].toFixed(1)}` : ""}`} style={{
            width: 14, height: 14, borderRadius: "50%", fontSize: 8,
            fontFamily: "monospace", fontWeight: 700,
            background: on ? color : "var(--border)",
            color: on ? "#000" : "var(--muted)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            {k[0].toUpperCase()}
          </div>
        );
      })}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function FusionPage() {
  const [data,       setData]       = useState<Resp | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [search,     setSearch]     = useState("");
  const [minLayers,  setMinLayers]  = useState(0);
  const [sortBy,     setSortBy]     = useState<keyof Pick>("total_score");
  const [sortAsc,    setSortAsc]    = useState(false);
  const [showLayers, setShowLayers] = useState(false);
  const [expanded,   setExpanded]   = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch("/api/fusion")
      .then(r => r.json())
      .then((d: Resp) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const rows = useMemo(() => {
    if (!data?.picks) return [];
    let r = [...data.picks];
    if (search) { const q = search.toUpperCase(); r = r.filter(x => x.symbol.includes(q)); }
    if (minLayers > 0) r = r.filter(x => x.n_layers >= minLayers);
    const m = sortAsc ? 1 : -1;
    return r.sort((a, b) => {
      const av = (a as any)[sortBy], bv = (b as any)[sortBy];
      return typeof av === "string" ? m * av.localeCompare(bv) : m * ((+av || 0) - (+bv || 0));
    });
  }, [data, search, minLayers, sortBy, sortAsc]);

  function Th({ col, label, right }: { col: keyof Pick; label: string; right?: boolean }) {
    const active = sortBy === col;
    return (
      <th onClick={() => { if (sortBy === col) setSortAsc(a => !a); else { setSortBy(col); setSortAsc(false); } }}
        style={{
          padding: "8px 10px", cursor: "pointer", userSelect: "none",
          textAlign: right ? "right" : "left",
          color: active ? "var(--accent)" : "var(--dim)",
          fontFamily: "monospace", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
          background: "var(--surface)",
          borderBottom: `2px solid ${active ? "var(--accent)" : "var(--border)"}`,
          whiteSpace: "nowrap",
        }}>
        {label}{active ? (sortAsc ? " ^" : " v") : ""}
      </th>
    );
  }

  const rc = data?.regime === "BULLISH" ? "var(--bull)" :
             data?.regime === "BEARISH" ? "var(--bear)" : "var(--warn)";

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      <NavBar />

      {/* Sub-header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "6px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface)",
      }}>
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>
          Fusion Agent -- Cross-agent top picks
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {data?.report_date && (
            <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>
              Report: {data.report_date.slice(0, 10)}
            </span>
          )}
          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>
            {data ? new Date(data.generated_at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }) + " IST" : ""}
          </span>
        </div>
      </div>

      <div style={{ padding: "14px 20px", maxWidth: 1500, margin: "0 auto" }}>

        {/* Header row */}
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginBottom: 14 }}>
          <div>
            <div style={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700,
                          letterSpacing: "0.12em", color: "var(--accent)" }}>
              FUSION PICKS
            </div>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginTop: 2 }}>
              {rows.length} picks shown{data ? ` / ${data.n_total} total` : ""}
            </div>
          </div>

          {/* Regime */}
          <div style={{ padding: "5px 12px", background: "var(--surface)",
                        border: `1px solid ${rc}`, borderRadius: 4 }}>
            <div style={{ fontFamily: "monospace", fontSize: 8, color: "var(--dim)", letterSpacing: "0.1em" }}>REGIME</div>
            <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 700, color: rc }}>
              {data?.regime ?? "--"}
            </div>
          </div>

          {/* Nifty */}
          <div style={{ padding: "5px 12px", background: "var(--surface)",
                        border: "1px solid var(--border)", borderRadius: 4 }}>
            <div style={{ fontFamily: "monospace", fontSize: 8, color: "var(--dim)" }}>NIFTY 50</div>
            <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
              {fn(data?.nifty ?? null, 0)}
            </div>
          </div>

          {/* Meta stats from fusion report */}
          {data?.meta && typeof data.meta === "object" && Object.entries(data.meta).slice(0, 4).map(([k, v]) => (
            <div key={k} style={{ padding: "5px 12px", background: "var(--surface)",
                                   border: "1px solid var(--border)", borderRadius: 4 }}>
              <div style={{ fontFamily: "monospace", fontSize: 8, color: "var(--dim)", letterSpacing: "0.08em" }}>
                {k.replace(/_/g, " ").toUpperCase()}
              </div>
              <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                {String(v)}
              </div>
            </div>
          ))}
        </div>

        {/* Layer legend */}
        <div style={{ display: "flex", gap: 14, marginBottom: 12, flexWrap: "wrap" }}>
          {LAYERS.map(({ k, label, color }) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 9, height: 9, borderRadius: "50%", background: color }} />
              <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>
                {k[0].toUpperCase()}={label}
              </span>
            </div>
          ))}
        </div>

        {/* Controls */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Symbol..."
            style={{ background: "var(--surface)", border: "1px solid var(--border)",
                     borderRadius: 4, color: "var(--text)", fontFamily: "monospace",
                     fontSize: 12, padding: "5px 10px", width: 130, outline: "none" }} />

          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>MIN LAYERS</span>
          {[0, 2, 3, 4, 5].map(v => (
            <button key={v} onClick={() => setMinLayers(v)} style={{
              padding: "4px 9px", fontFamily: "monospace", fontSize: 10, cursor: "pointer", borderRadius: 4,
              background: minLayers === v ? "var(--accent)" : "var(--surface)",
              color:      minLayers === v ? "#000" : "var(--dim)",
              border:     `1px solid ${minLayers === v ? "var(--accent)" : "var(--border)"}`,
            }}>{v === 0 ? "ALL" : `${v}+`}</button>
          ))}

          <button onClick={() => setShowLayers(v => !v)} style={{
            marginLeft: "auto", padding: "4px 10px", fontFamily: "monospace", fontSize: 10,
            cursor: "pointer", borderRadius: 4,
            background: showLayers ? "var(--accent)" : "var(--surface)",
            color:      showLayers ? "#000" : "var(--dim)",
            border:     `1px solid ${showLayers ? "var(--accent)" : "var(--border)"}`,
          }}>
            {showLayers ? "HIDE LAYERS" : "SHOW LAYERS"}
          </button>
        </div>

        {/* Error */}
        {data?.error && (
          <div style={{ padding: "10px 14px", background: "rgba(248,81,73,0.08)",
                        border: "1px solid var(--bear)", borderRadius: 4,
                        fontFamily: "monospace", fontSize: 11, color: "var(--bear)", marginBottom: 12 }}>
            {data.error}
          </div>
        )}

        {/* Table */}
        {loading ? (
          <div style={{ padding: 60, textAlign: "center", fontFamily: "monospace",
                        fontSize: 12, color: "var(--dim)" }}>Loading fusion picks...</div>
        ) : (
          <div style={{ borderRadius: 6, border: "1px solid var(--border)", overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ padding: "8px 10px", background: "var(--surface)", width: 30,
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)", textAlign: "left" }}>#</th>
                  <Th col="symbol"      label="SYMBOL" />
                  <Th col="total_score" label="SCORE" />
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>LAYERS</th>
                  {showLayers && <>
                    <Th col="beta_score"       label="BETA"  right />
                    <Th col="regime_score"     label="RGM"   right />
                    <Th col="insider_score"    label="INS"   right />
                    <Th col="watchlist_score"  label="WTCH"  right />
                    <Th col="seasonal_score"   label="SEAS"  right />
                    <Th col="conviction_score" label="CONV"  right />
                    <Th col="quant_score"      label="QANT"  right />
                  </>}
                  <Th col="n_layers" label="N" right />
                  <Th col="rsi_14"   label="RSI"  right />
                  <Th col="adx_14"   label="ADX"  right />
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)",
                                textAlign: "center" }}>MACD</th>
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>TODAY PAT</th>
                  <Th col="price" label="PRICE" right />
                  <th style={{ padding: "8px 10px", background: "var(--surface)",
                                borderBottom: "2px solid var(--border)",
                                fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>REASONS</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const fired   = parseLayers(row.layers_fired);
                  const reasons = parseReasons(row.reasons);
                  const scores  = {
                    beta: row.beta_score, regime: row.regime_score,
                    insider: row.insider_score, watchlist: row.watchlist_score,
                    seasonal: row.seasonal_score, conviction: row.conviction_score,
                    quant: row.quant_score,
                  };
                  const rsiC  = row.rsi_14 == null ? "var(--dim)"
                              : row.rsi_14 > 70 ? "var(--bear)"
                              : row.rsi_14 < 30 ? "var(--bull)" : "var(--text)";
                  const isExp = expanded === row.symbol;

                  return (
                    <>
                      <tr key={row.symbol}
                        onClick={() => setExpanded(isExp ? null : row.symbol)}
                        style={{
                          borderBottom: isExp ? "none" : "1px solid var(--border)",
                          cursor: "pointer",
                          background: isExp ? "rgba(0,212,170,0.04)" : "transparent",
                        }}
                        onMouseEnter={e => { if (!isExp) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.02)"; }}
                        onMouseLeave={e => { if (!isExp) (e.currentTarget as HTMLElement).style.background = "transparent"; }}>

                        {/* # */}
                        <td style={{ padding: "7px 10px", fontFamily: "monospace", fontSize: 11, color: "var(--dim)" }}>
                          {i + 1}
                        </td>

                        {/* Symbol */}
                        <td style={{ padding: "7px 10px" }}>
                          <a href={`/stocks/${row.symbol}`}
                            onClick={e => e.stopPropagation()}
                            style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700,
                                     color: "var(--text)", textDecoration: "none" }}>
                            {row.symbol}
                          </a>
                        </td>

                        {/* Score */}
                        <td style={{ padding: "7px 10px" }}>
                          <ScoreBar score={row.total_score} />
                        </td>

                        {/* Layer dots */}
                        <td style={{ padding: "7px 10px" }}>
                          <LayerDots fired={fired} scores={scores} />
                        </td>

                        {/* Per-layer cols */}
                        {showLayers && (
                          <>
                            {(["beta_score","regime_score","insider_score",
                               "watchlist_score","seasonal_score","conviction_score",
                               "quant_score"] as (keyof Pick)[]).map(k => {
                              const v = row[k] as number;
                              return (
                                <td key={k} style={{ padding: "7px 10px", textAlign: "right",
                                                     fontFamily: "monospace", fontSize: 11 }}>
                                  {v > 0
                                    ? <span style={{ color: scoreColor(v) }}>{v.toFixed(1)}</span>
                                    : <span style={{ color: "var(--border)" }}>--</span>}
                                </td>
                              );
                            })}
                          </>
                        )}

                        {/* N layers */}
                        <td style={{ padding: "7px 10px", textAlign: "right",
                                     fontFamily: "monospace", fontSize: 12,
                                     color: row.n_layers >= 5 ? "var(--bull)"
                                          : row.n_layers >= 3 ? "var(--warn)" : "var(--dim)" }}>
                          {row.n_layers}
                        </td>

                        {/* RSI */}
                        <td style={{ padding: "7px 10px", textAlign: "right",
                                     fontFamily: "monospace", fontSize: 12, color: rsiC }}>
                          {row.rsi_14 != null ? row.rsi_14.toFixed(0) : "--"}
                        </td>

                        {/* ADX */}
                        <td style={{ padding: "7px 10px", textAlign: "right",
                                     fontFamily: "monospace", fontSize: 12,
                                     color: (row.adx_14 ?? 0) > 25 ? "var(--bull)" : "var(--dim)" }}>
                          {row.adx_14 != null ? row.adx_14.toFixed(0) : "--"}
                        </td>

                        {/* MACD */}
                        <td style={{ padding: "7px 10px", textAlign: "center" }}>
                          <span style={{ fontFamily: "monospace", fontSize: 10, padding: "2px 6px", borderRadius: 3,
                                         background: row.macd_bull ? "rgba(38,196,133,0.12)" : "rgba(248,81,73,0.12)",
                                         color: row.macd_bull ? "var(--bull)" : "var(--bear)" }}>
                            {row.macd_bull ? "BULL" : "BEAR"}
                          </span>
                        </td>

                        {/* Today pattern */}
                        <td style={{ padding: "7px 10px", minWidth: 120 }}>
                          {row.today_pat ? (
                            <span style={{ fontFamily: "monospace", fontSize: 10 }}>
                              <span style={{ color: row.today_pat.direction === "UP" ? "var(--bull)" : "var(--bear)",
                                             fontWeight: 700, marginRight: 3 }}>
                                {row.today_pat.direction}
                              </span>
                              <span style={{ color: row.today_pat.mean_ret > 0 ? "var(--bull)" : "var(--bear)" }}>
                                {row.today_pat.mean_ret > 0 ? "+" : ""}{row.today_pat.mean_ret}%
                              </span>
                              <span style={{ color: "var(--dim)" }}> {row.today_pat.win_pct}%w</span>
                            </span>
                          ) : (
                            <span style={{ color: "var(--border)", fontFamily: "monospace", fontSize: 10 }}>--</span>
                          )}
                        </td>

                        {/* Price */}
                        <td style={{ padding: "7px 10px", textAlign: "right",
                                     fontFamily: "monospace", fontSize: 12, color: "var(--text)" }}>
                          {fn(row.price, 2)}
                        </td>

                        {/* Reasons (truncated) */}
                        <td style={{ padding: "7px 10px", maxWidth: 220 }}>
                          <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)",
                                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {reasons.slice(0, 2).join(" | ")}
                            {reasons.length > 2 && <span style={{ color: "var(--muted)" }}> +{reasons.length - 2}</span>}
                          </div>
                        </td>
                      </tr>

                      {/* Expanded row: full reasons + all layer scores */}
                      {isExp && (
                        <tr key={`${row.symbol}-exp`}
                          style={{ borderBottom: "1px solid var(--border)", background: "rgba(0,212,170,0.04)" }}>
                          <td colSpan={99} style={{ padding: "8px 20px 14px 44px" }}>
                            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>

                              {/* All reasons */}
                              <div style={{ minWidth: 280 }}>
                                <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                                              letterSpacing: "0.1em", marginBottom: 6 }}>REASONS</div>
                                {reasons.length > 0 ? reasons.map((r, idx) => (
                                  <div key={idx} style={{ fontFamily: "monospace", fontSize: 11,
                                                           color: "var(--text)", marginBottom: 3 }}>
                                    <span style={{ color: "var(--accent)", marginRight: 6 }}>{idx + 1}.</span>
                                    {r}
                                  </div>
                                )) : (
                                  <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--dim)" }}>
                                    No reasons recorded
                                  </span>
                                )}
                              </div>

                              {/* Layer breakdown */}
                              <div>
                                <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                                              letterSpacing: "0.1em", marginBottom: 6 }}>LAYER SCORES</div>
                                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                                  {LAYERS.map(({ k, label, color }) => {
                                    const v = (scores as any)[k] as number;
                                    const on = fired.some(f => f.includes(k.slice(0, 4)));
                                    return (
                                      <div key={k} style={{
                                        padding: "4px 10px", borderRadius: 4,
                                        background: on ? `${color}18` : "var(--surface)",
                                        border: `1px solid ${on ? color : "var(--border)"}`,
                                      }}>
                                        <div style={{ fontFamily: "monospace", fontSize: 8,
                                                       color: on ? color : "var(--dim)",
                                                       letterSpacing: "0.08em" }}>{label.toUpperCase()}</div>
                                        <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700,
                                                       color: on ? color : "var(--muted)" }}>
                                          {v > 0 ? v.toFixed(1) : "--"}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>

                              {/* Technicals */}
                              <div>
                                <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                                              letterSpacing: "0.1em", marginBottom: 6 }}>TECHNICALS</div>
                                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                                  {[
                                    { l: "RSI",     v: row.rsi_14?.toFixed(0)  ?? "--", c: row.rsi_14 && row.rsi_14 < 30 ? "var(--bull)" : row.rsi_14 && row.rsi_14 > 70 ? "var(--bear)" : "var(--text)" },
                                    { l: "ADX",     v: row.adx_14?.toFixed(0)  ?? "--", c: (row.adx_14 ?? 0) > 25 ? "var(--bull)" : "var(--dim)" },
                                    { l: "ATR%",    v: row.atr_pct?.toFixed(2) ?? "--", c: "var(--text)" },
                                    { l: "52W HI%", v: row.pct_52h?.toFixed(1) ?? "--", c: (row.pct_52h ?? -99) > -5 ? "var(--bull)" : "var(--dim)" },
                                    { l: "MACD",    v: row.macd_bull ? "BULL" : "BEAR", c: row.macd_bull ? "var(--bull)" : "var(--bear)" },
                                  ].map(({ l, v, c }) => (
                                    <div key={l} style={{ padding: "4px 10px", borderRadius: 4,
                                                           background: "var(--surface)", border: "1px solid var(--border)" }}>
                                      <div style={{ fontFamily: "monospace", fontSize: 8,
                                                     color: "var(--dim)", letterSpacing: "0.08em" }}>{l}</div>
                                      <div style={{ fontFamily: "monospace", fontSize: 13,
                                                     fontWeight: 700, color: c }}>{v}</div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>

            {rows.length === 0 && !loading && (
              <div style={{ padding: 40, textAlign: "center", fontFamily: "monospace",
                            fontSize: 12, color: "var(--dim)" }}>
                {data?.error ? "Run agent_fusion.py to generate picks." : "No picks match filters."}
              </div>
            )}
          </div>
        )}

        {/* Stats bar */}
        {data && (
          <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
            {([
              ["TOTAL",    data.n_total],
              ["SHOWING",  rows.length],
              ["5+ LAYERS",data.picks.filter(p => p.n_layers >= 5).length],
              ["3+ LAYERS",data.picks.filter(p => p.n_layers >= 3).length],
              ["W/ PATTERN",data.picks.filter(p => p.today_pat != null).length],
            ] as [string, number][]).map(([l, v]) => (
              <div key={l} style={{ padding: "5px 12px", background: "var(--surface)",
                                     border: "1px solid var(--border)", borderRadius: 4 }}>
                <div style={{ fontFamily: "monospace", fontSize: 8, color: "var(--dim)",
                               letterSpacing: "0.1em" }}>{l}</div>
                <div style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700,
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

write(SRC / "fusion" / "page.tsx", page, "/fusion/page.tsx")


# ── Add FUSION to NavBar ───────────────────────────────────────────────────
print("\n[3/3] Adding FUSION to NavBar...")
import re
for nb in (DASH / "src").rglob("NavBar.tsx"):
    src = nb.read_text(encoding="utf-8")
    if "/fusion" not in src:
        src = re.sub(
            r"(\{ href: \"/conviction\".*?\},?)",
            r'\1\n  { href: "/fusion",     label: "FUSION"     },',
            src, count=1
        )
        nb.write_text(src, encoding="utf-8")
        print("  [OK] FUSION added to NavBar")
    else:
        print("  [OK] FUSION already in NavBar")

print("""
======================================================================
  /fusion PAGE BUILT
======================================================================

  FILES:
    src/app/api/fusion/route.ts   -- reads agents/fusion/last_report.json
    src/app/fusion/page.tsx       -- top picks with layer breakdown
    NavBar.tsx                    -- FUSION link added

  FEATURES:
    - Score bar (0-7, one per layer)
    - Layer dots B/R/I/W/S/C/Q (filled = fired)
    - Click row to expand: full reasons + all layer scores + technicals
    - SHOW LAYERS toggle for per-layer score columns
    - MIN LAYERS filter (ALL / 2+ / 3+ / 4+ / 5+)
    - Today's seasonal pattern enriched from DB
    - Meta stats from fusion report header

  NOTE: If picks shows 0, run first:
    py D:\\MICC\\agent_fusion.py

  RESTART:
    cd D:\\MICC\\micc-dashboard && npm run dev
  OPEN:
    http://localhost:3000/fusion
""")
