"""
upgrade_dashboard.py
=====================
Run from D:/MICC/:
  py upgrade_dashboard.py

Fixes and upgrades in this patch:
  1. /api/reports/route.ts  - update path to D:/MICC, ensure NaN handling correct
  2. AlphaPanel.tsx         - render markdown in LLM analysis (bold, headers, bullets)
  3. page.tsx               - wire in RefreshController (cycle-based), remove setInterval
  4. globals.css            - add markdown prose styles

All changes are backward compatible. No agent code touched.
"""

import os, sys
from pathlib import Path

BASE = Path(r"D:\MICC")

def find_paths():
    for sub in ["micc-dashboard/src", "micc-dashboard"]:
        p = BASE / sub
        if p.is_dir() and (p / "components").is_dir():
            return p / "app", p / "components", p / "lib"
    return None, None, None

APP, COMP, LIB = find_paths()
if not APP:
    print("[ERROR] micc-dashboard not found at D:/MICC/micc-dashboard/")
    print("        Make sure you run this from D:/MICC/")
    sys.exit(1)

print(f"[OK] Dashboard found: {APP.parent}")

def w(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    try:
        rel = path.relative_to(BASE)
    except ValueError:
        rel = path
    print(f"  wrote: {rel}")


# =============================================================================
# 1. Fix /api/reports/route.ts — update DA path to D:/MICC
# =============================================================================
print("\n[1/4] Fixing /api/reports/route.ts...")
w(APP / "api" / "reports" / "route.ts", r"""
import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

// Project root — updated to D:/MICC after migration
const DA = 'D:/MICC'

function readAgent(name: string) {
  try {
    const p = path.join(DA, 'agents', name, 'last_report.json')
    if (!fs.existsSync(p)) {
      return {
        _error: `agents/${name}/last_report.json not found. Run: py agent_${name}.py`
      }
    }
    let raw = fs.readFileSync(p, 'utf-8')
    // Sanitise bare NaN/Infinity before JSON.parse
    raw = raw.replace(/:\s*NaN([,\}\]])/g,  ': null$1')
    raw = raw.replace(/:\s*Infinity([,\}\]])/g,  ': null$1')
    raw = raw.replace(/:\s*-Infinity([,\}\]])/g, ': null$1')
    return JSON.parse(raw)
  } catch (e: any) {
    return { _error: `${name}: ${e.message}` }
  }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  return NextResponse.json({
    alpha: readAgent('alpha'),
    beta:  readAgent('beta'),
    gamma: readAgent('gamma'),
    delta: readAgent('delta'),
    ts:    Date.now(),
  })
}
""")

print("[1/4] Done")


# =============================================================================
# 2. MarkdownText component — renders LLM markdown properly
# =============================================================================
print("\n[2/4] Writing MarkdownText component...")
w(COMP / "MarkdownText.tsx", r"""
"use client";
/**
 * MarkdownText
 * Lightweight markdown renderer for LLM analysis output.
 * Handles: ## headers, **bold**, *italic*, bullet lists, numbered lists,
 *          blank-line paragraphs. No external deps.
 */

interface Props {
  text: string;
  maxHeight?: number;
}

export default function MarkdownText({ text, maxHeight = 480 }: Props) {
  if (!text) return null;

  // Split into blocks on blank lines
  const blocks = text.split(/\n{2,}/).map(b => b.trim()).filter(Boolean);

  return (
    <div style={{
      maxHeight,
      overflowY: "auto",
      padding: "14px 18px",
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 6,
      fontSize: 12,
      lineHeight: 1.85,
      color: "var(--text)",
      fontFamily: "'JetBrains Mono', monospace",
    }}>
      {blocks.map((block, i) => <Block key={i} text={block} />)}
    </div>
  );
}

function Block({ text }: { text: string }) {
  const lines = text.split("\n");

  // ## Heading 2
  if (lines[0].startsWith("## ")) {
    return (
      <h3 style={{
        fontFamily: "'Share Tech Mono', monospace",
        fontSize: 11,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: "var(--accent)",
        margin: "18px 0 8px",
        borderBottom: "1px solid var(--border)",
        paddingBottom: 4,
      }}>
        {lines[0].slice(3)}
      </h3>
    );
  }

  // # Heading 1
  if (lines[0].startsWith("# ")) {
    return (
      <h2 style={{
        fontFamily: "'Share Tech Mono', monospace",
        fontSize: 13,
        letterSpacing: "0.15em",
        textTransform: "uppercase",
        color: "var(--info)",
        margin: "20px 0 10px",
      }}>
        {lines[0].slice(2)}
      </h2>
    );
  }

  // Bullet list block (all lines start with - or *)
  const isBullets = lines.every(l => /^[-*]\s/.test(l.trim()) || l.trim() === "");
  if (isBullets) {
    return (
      <ul style={{ paddingLeft: 18, margin: "6px 0" }}>
        {lines.filter(l => l.trim()).map((l, i) => (
          <li key={i} style={{ marginBottom: 4 }}>
            <Inline text={l.replace(/^[-*]\s/, "").trim()} />
          </li>
        ))}
      </ul>
    );
  }

  // Numbered list block
  const isNumbered = lines.every(l => /^\d+[.)]\s/.test(l.trim()) || l.trim() === "");
  if (isNumbered) {
    return (
      <ol style={{ paddingLeft: 20, margin: "6px 0" }}>
        {lines.filter(l => l.trim()).map((l, i) => (
          <li key={i} style={{ marginBottom: 4 }}>
            <Inline text={l.replace(/^\d+[.)]\s/, "").trim()} />
          </li>
        ))}
      </ol>
    );
  }

  // Normal paragraph
  return (
    <p style={{ margin: "8px 0", lineHeight: 1.85 }}>
      {lines.map((line, i) => (
        <span key={i}>
          <Inline text={line} />
          {i < lines.length - 1 && <br />}
        </span>
      ))}
    </p>
  );
}

function Inline({ text }: { text: string }) {
  // Process inline markdown: **bold**, *italic*, `code`
  const parts: React.ReactNode[] = [];
  let rest = text;
  let idx = 0;

  const patterns: [RegExp, (m: string) => React.ReactNode][] = [
    [/\*\*(.+?)\*\*/,  m => <strong key={idx++} style={{ color: "var(--text)", fontWeight: 700 }}>{m.slice(2, -2)}</strong>],
    [/\*(.+?)\*/,       m => <em key={idx++} style={{ color: "var(--warn)", fontStyle: "italic" }}>{m.slice(1, -1)}</em>],
    [/`(.+?)`/,         m => <code key={idx++} style={{
      fontFamily: "'JetBrains Mono', monospace",
      background: "rgba(255,255,255,0.06)",
      padding: "1px 5px",
      borderRadius: 3,
      fontSize: 11,
      color: "var(--accent)",
    }}>{m.slice(1, -1)}</code>],
  ];

  let safety = 0;
  while (rest.length > 0 && safety++ < 200) {
    let earliest = -1;
    let eMatch: RegExpExecArray | null = null;
    let eTransform: ((m: string) => React.ReactNode) | null = null;

    for (const [pat, transform] of patterns) {
      const m = pat.exec(rest);
      if (m && (earliest === -1 || m.index < earliest)) {
        earliest = m.index;
        eMatch = m;
        eTransform = transform;
      }
    }

    if (!eMatch || eTransform === null) {
      parts.push(rest);
      break;
    }

    if (eMatch.index > 0) {
      parts.push(rest.slice(0, eMatch.index));
    }
    parts.push(eTransform(eMatch[0]));
    rest = rest.slice(eMatch.index + eMatch[0].length);
  }

  return <>{parts}</>;
}
""")

print("[2/4] Done")


# =============================================================================
# 3. AlphaPanel.tsx — use MarkdownText for LLM analysis
# =============================================================================
print("\n[3/4] Upgrading AlphaPanel.tsx with MarkdownText renderer...")
w(COMP / "AlphaPanel.tsx", r"""
"use client";
import MarkdownText from "./MarkdownText";
import IndicesPanel from "./IndicesPanel";
import { fmtNum, fmtPct, colorPct, regimeCls } from "@/lib/utils";

export default function AlphaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Alpha <span className="card-accent">-- Macro and Regime</span></span>
      </div>
      <div style={{ color: "var(--neg)", fontFamily: "monospace", fontSize: 12, padding: 8 }}>
        {data?._error || "No alpha report. Run: py agent_alpha.py"}
      </div>
    </div>
  );

  // Exact JSON keys from agent_alpha.py last_report.json
  const reg  = data.regime        || {};   // latest_close, window_pct, return_1d_pct, vol_ann_pct,
                                           // pe, pb, regime, confidence, above_ma20, above_ma50,
                                           // volume_ratio, ma20, ma50
  const brd  = data.breadth       || {};   // by_day:[{advancing,declining,unchanged,total,pct_adv,ad_ratio}],
                                           // avg_pct_adv, total_days
  const rot  = data.cap_rotation  || {};   // largecap_avg_pct, midcap_avg_pct, smallcap_avg_pct, signal
  const gctx = data.global_context || {};  // tickers:{DXY:{close,pct_chg},...}, summary, available

  const date      = data.end_date || (data.timestamp || "").slice(0, 10) || "--";
  const regime    = reg.regime     || "";
  const rcls      = regimeCls(regime);

  // Breadth: latest day
  const byDay  = Array.isArray(brd.by_day) ? brd.by_day : [];
  const lastBd = byDay[byDay.length - 1]  || {};
  const adv    = lastBd.advancing  ?? "--";
  const dec    = lastBd.declining  ?? "--";
  const tot    = lastBd.total      ?? "--";
  const unch   = lastBd.unchanged  ?? 0;
  const adR    = lastBd.ad_ratio;

  // Global tickers
  const tickers     = gctx.tickers || {};
  const tickerOrder = ["DXY", "Crude Oil", "Gold", "S&P 500", "Nasdaq", "USD/INR", "India VIX", "Dow Jones"];
  const tickerItems = tickerOrder
    .filter(k => tickers[k] != null)
    .map(k => ({ key: k, ...tickers[k] }));
  // add any unlisted tickers
  Object.entries(tickers).forEach(([k, v]) => {
    if (!tickerOrder.includes(k)) tickerItems.push({ key: k, ...(v as any) });
  });

  // LLM text
  const ra     = data.regime_analysis;
  const raText = typeof ra === "string" ? ra : (ra?.analysis || ra?.regime || "");

  return (
    <div className="card">
      {/* Header */}
      <div className="card-header">
        <span className="card-title">
          Alpha <span className="card-accent">-- Macro and Regime</span>
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)" }}>{date}</span>
          {regime    && <span className={"pill " + rcls}   style={{ fontSize: 11 }}>{regime}</span>}
          {reg.confidence && <span className="pill pill-neut" style={{ fontSize: 9 }}>CONF: {reg.confidence}</span>}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="kpi-grid">
        <div className="kpi">
          <div className="kpi-label">Nifty 50</div>
          <div className="kpi-value" style={{ fontSize: 20 }}>
            {fmtNum(reg.latest_close, 2)}
          </div>
          <div className="kpi-sub" style={{ display: "flex", gap: 8 }}>
            <span style={{ color: colorPct(reg.return_1d_pct) }}>
              {fmtPct(reg.return_1d_pct)} 1d
            </span>
            <span style={{ color: colorPct(reg.window_pct) }}>
              {fmtPct(reg.window_pct)} window
            </span>
          </div>
        </div>

        <div className="kpi">
          <div className="kpi-label">Volatility (20d Ann.)</div>
          <div className="kpi-value" style={{
            color: (Number(reg.vol_ann_pct) || 0) > 20 ? "var(--neg)"
                 : (Number(reg.vol_ann_pct) || 0) < 12 ? "var(--pos)" : "var(--warn)"
          }}>
            {reg.vol_ann_pct != null ? `${Number(reg.vol_ann_pct).toFixed(1)}%` : "--"}
          </div>
          <div className="kpi-sub">
            Vol ratio 5/20d: {fmtNum(reg.volume_ratio, 2)}
          </div>
        </div>

        <div className="kpi">
          <div className="kpi-label">MA Positioning</div>
          <div className="kpi-value" style={{
            fontSize: 13,
            color: reg.above_ma20 ? "var(--pos)" : "var(--neg)"
          }}>
            {reg.above_ma20 ? "Above MA20" : "Below MA20"}
          </div>
          <div className="kpi-sub" style={{ color: reg.above_ma50 ? "var(--pos)" : "var(--neg)" }}>
            {reg.above_ma50 ? "Above MA50" : "Below MA50"}
          </div>
        </div>

        <div className="kpi">
          <div className="kpi-label">Nifty PE / PB</div>
          <div className="kpi-value" style={{
            color: (Number(reg.pe) || 0) > 25 ? "var(--warn)" : "var(--text)"
          }}>
            {fmtNum(reg.pe, 2)}
          </div>
          <div className="kpi-sub">
            PB: {fmtNum(reg.pb, 2)}
            {reg.ma20 && <span style={{ marginLeft: 8 }}>MA20: {fmtNum(reg.ma20, 0)}</span>}
          </div>
        </div>

        <div className="kpi">
          <div className="kpi-label">Advances</div>
          <div className="kpi-value" style={{ color: "var(--pos)" }}>{adv}</div>
          <div className="kpi-sub">of {tot} indices | Unch: {unch}</div>
        </div>

        <div className="kpi">
          <div className="kpi-label">Declines</div>
          <div className="kpi-value" style={{ color: "var(--neg)" }}>{dec}</div>
          <div className="kpi-sub">A/D: {adR != null ? Number(adR).toFixed(2) : "--"}</div>
        </div>

        <div className="kpi">
          <div className="kpi-label">Breadth (Avg)</div>
          <div className="kpi-value" style={{
            color: (Number(brd.avg_pct_adv) || 0) > 55 ? "var(--pos)" : "var(--warn)"
          }}>
            {brd.avg_pct_adv != null ? `${Number(brd.avg_pct_adv).toFixed(1)}%` : "--"}
          </div>
          <div className="kpi-sub">
            advancing | Unch: {unch}
          </div>
        </div>

        <div className="kpi">
          <div className="kpi-label">Largecap</div>
          <div className="kpi-value" style={{ color: colorPct(rot.largecap_avg_pct) }}>
            {fmtPct(rot.largecap_avg_pct)}
          </div>
          <div className="kpi-sub" style={{ color: colorPct(rot.midcap_avg_pct) }}>
            Mid: {fmtPct(rot.midcap_avg_pct)}
          </div>
        </div>

        <div className="kpi">
          <div className="kpi-label">Smallcap</div>
          <div className="kpi-value" style={{ color: colorPct(rot.smallcap_avg_pct) }}>
            {fmtPct(rot.smallcap_avg_pct)}
          </div>
          <div className="kpi-sub">
            {rot.signal ? rot.signal.split("--")[0].trim() : "--"}
          </div>
        </div>
      </div>

      {/* Cap Rotation Signal */}
      {rot.signal && (
        <div style={{
          padding: "7px 14px", marginBottom: 14,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 5,
          fontFamily: "monospace", fontSize: 11,
          color: rot.signal.includes("RISK_ON") ? "var(--pos)"
               : rot.signal.includes("RISK_OFF") ? "var(--warn)" : "var(--muted)",
        }}>
          Rotation Signal: {rot.signal}
        </div>
      )}

      {/* Global Context Tickers */}
      {tickerItems.length > 0 && (
        <>
          <div className="section-label">Global Context</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
            {tickerItems.slice(0, 8).map(({ key, close, pct_chg, latest_close, pct_1d }: any) => {
              const displayClose = close ?? latest_close ?? "--";
              const displayPct   = pct_chg ?? pct_1d ?? null;
              return (
                <div key={key} style={{
                  background: "var(--surface)", border: "1px solid var(--border)",
                  borderRadius: 5, padding: "6px 12px", minWidth: 90,
                }}>
                  <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)", textTransform: "uppercase", marginBottom: 3 }}>
                    {key}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {displayClose != null ? Number(displayClose).toLocaleString(undefined, { maximumFractionDigits: 2 }) : "--"}
                  </div>
                  {displayPct != null && (
                    <div style={{ fontFamily: "monospace", fontSize: 10, color: colorPct(displayPct) }}>
                      {Number(displayPct) >= 0 ? "+" : ""}{Number(displayPct).toFixed(2)}%
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {gctx.summary && (
            <div style={{
              padding: "7px 12px", marginBottom: 14,
              background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 5,
              fontFamily: "monospace", fontSize: 11, color: "var(--muted)",
            }}>
              {gctx.summary}
            </div>
          )}
        </>
      )}

      {/* Top / Bottom movers from agent JSON */}
      {(data.top10_gainers?.length > 0 || data.top10_losers?.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <div>
            <div className="section-label">Top Indices (Window)</div>
            {(data.top10_gainers || []).slice(0, 7).map((r: any, i: number) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "4px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontSize: 11 }}>
                  {(r.index || r.name || "--").slice(0, 28)}
                </span>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--pos)" }}>
                  {r.pct_change != null ? `+${Number(r.pct_change).toFixed(2)}%` : "--"}
                </span>
              </div>
            ))}
          </div>
          <div>
            <div className="section-label">Bottom Indices (Window)</div>
            {(data.top10_losers || []).slice(0, 7).map((r: any, i: number) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "4px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontSize: 11 }}>
                  {(r.index || r.name || "--").slice(0, 28)}
                </span>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--neg)" }}>
                  {r.pct_change != null ? `${Number(r.pct_change).toFixed(2)}%` : "--"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live Indices Panel (from market_snapshot via /api/indices) */}
      <IndicesPanel />

      {/* LLM Regime Analysis — rendered markdown */}
      {raText && (
        <>
          <div className="section-label" style={{ marginTop: 16 }}>LLM Regime Analysis</div>
          <MarkdownText text={raText} maxHeight={460} />
        </>
      )}
    </div>
  );
}
""")

print("[3/4] Done")


# =============================================================================
# 4. page.tsx — wire RefreshController, remove fixed setInterval
# =============================================================================
print("\n[4/4] Writing upgraded page.tsx with cycle-based refresh...")
w(APP / "page.tsx", r"""
"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import AlphaPanel         from "@/components/AlphaPanel";
import BetaPanel          from "@/components/BetaPanel";
import GammaPanel         from "@/components/GammaPanel";
import DeltaPanel         from "@/components/DeltaPanel";
import StreakBoardExtended from "@/components/StreakBoardExtended";
import RefreshController  from "@/components/RefreshController";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Reports {
  alpha?: any; beta?: any; gamma?: any; delta?: any; ts?: number;
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Home() {
  const [reports,  setReports]  = useState<Reports>({});
  const [lastTime, setLastTime] = useState<string>("");
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  // Fetch all agent reports in one call
  const fetchReports = useCallback(async () => {
    try {
      const r = await fetch("/api/reports", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setReports(data);
      setLastTime(new Date().toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      }));
      setError("");
    } catch (e: any) {
      setError(e.message || "Fetch failed");
    }
  }, []);

  // All fetches bundled for RefreshController
  const triggerAllFetches = useCallback(async () => {
    setLoading(true);
    await fetchReports();
    // IndicesPanel and StreakBoardExtended manage their own state internally
    setLoading(false);
  }, [fetchReports]);

  // Initial load
  useEffect(() => {
    triggerAllFetches();
  }, []); // eslint-disable-line

  const alpha = reports.alpha || null;
  const beta  = reports.beta  || null;
  const gamma = reports.gamma || null;
  const delta = reports.delta || null;

  return (
    <div className="dashboard">
      {/* ── Sticky Header ── */}
      <header className="header">
        <div className="header-logo">MICC</div>
        <div className="header-sub">Market Intelligence Command Center</div>
        <div className="header-right">
          {error && (
            <span style={{ color: "var(--neg)", fontSize: 10, fontFamily: "monospace" }}>
              {error}
            </span>
          )}
          {loading && !error && (
            <span style={{ color: "var(--accent)", fontSize: 10, fontFamily: "monospace" }}>
              Loading...
            </span>
          )}
          {lastTime && !loading && (
            <span style={{ color: "var(--dim)", fontSize: 10, fontFamily: "monospace" }}>
              Updated {lastTime}
            </span>
          )}
          {/* Cycle-based auto-refresh: waits for all fetches, then counts down */}
          <RefreshController
            onRefresh={triggerAllFetches}
            intervalSec={90}
            autoStart={false}
          />
        </div>
      </header>

      {/* ── Alpha: Macro + Regime ── */}
      <div style={{ marginBottom: 14 }}>
        <AlphaPanel data={alpha} />
      </div>

      {/* ── Beta + Gamma: side by side ── */}
      <div className="grid2" style={{ marginBottom: 14 }}>
        <BetaPanel  data={beta}  />
        <GammaPanel data={gamma} />
      </div>

      {/* ── Delta: Risk Engine ── */}
      <div style={{ marginBottom: 14 }}>
        <DeltaPanel data={delta} />
      </div>

      {/* ── Streak Leaderboard ── */}
      <div style={{ marginBottom: 14 }}>
        <StreakBoardExtended />
      </div>
    </div>
  );
}
""")

print("[4/4] Done")


# =============================================================================
print()
print("=" * 60)
print("  UPGRADE COMPLETE")
print("=" * 60)
print()
print("  Changes applied:")
print("  [1] /api/reports/route.ts  - path updated to D:/MICC")
print("  [2] MarkdownText.tsx       - new component (bold/headers/bullets)")
print("  [3] AlphaPanel.tsx         - uses MarkdownText for LLM analysis")
print("  [4] page.tsx               - RefreshController wired in (90s cycle)")
print()
print("  RESTART DASHBOARD:")
print("    cd D:\\MICC\\micc-dashboard")
print("    npm run dev")
print()
print("  Then open http://localhost:3000")
print()
print("  The LLM analysis text will now render with:")
print("    ## headers  -> teal uppercase section titles")
print("    **bold**    -> white bold text")
print("    *italic*    -> amber italic text")
print("    bullet list -> proper bullet list")
print()
print("  Auto-refresh: click RESUME in the header to start 90s cycle.")
print("  Click REFRESH to force an immediate fetch.")
print()
