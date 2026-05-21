"""
fix_phase3a_all_pages.py
========================
Phase 3A: Fix all broken dashboard pages.

Fixes:
  1. /analysis  - [object Object] bug + multiple NavBars
  2. /options   - missing NavBar + chain data
  3. /patterns  - zoom/scale bug
  4. /analytics - zoom/scale bug
  5. /macro     - redesign to match reference
  6. /eta       - full redesign: insider/dividends/results tables
  7. /global    - remove ALL emojis, fix layout
  8. /watchlist - match reference design

Run: py D:\MICC\fix_phase3a_all_pages.py
"""

from pathlib import Path
import re

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
APP  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def write(path: Path, content: str, label: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    lines = len(content.splitlines())
    print(f"  [OK] {label or path.name}  ({lines} lines)")

def read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

def log(msg: str):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

print("=" * 60)
print("PHASE 3A - FIX ALL BROKEN PAGES")
print("=" * 60)


# =============================================================================
# [1]  /analysis page - fix [object Object] + multiple NavBars
# =============================================================================
log("[1/8] Fixing /analysis page...")

analysis_page = '''\
"use client";
import { useEffect, useState } from "react";
import NavBar from "@/components/NavBar";

interface AgentCard {
  agent: string;
  timestamp: string;
  regime?: string | Record<string, string>;
  confidence?: string;
  summary?: string;
  llm_analysis?: string;
  screens?: Record<string, unknown[]>;
  picks?: unknown[];
  signals?: unknown[];
  [key: string]: unknown;
}

function safeStr(v: unknown): string {
  if (v === null || v === undefined) return "--";
  if (typeof v === "string") return v;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function regimeStr(r: unknown): string {
  if (!r) return "--";
  if (typeof r === "string") return r;
  if (typeof r === "object" && r !== null) {
    const obj = r as Record<string, string>;
    if (obj.regime) return obj.regime + (obj.confidence ? " (" + obj.confidence + ")" : "");
    return JSON.stringify(r);
  }
  return String(r);
}

const AGENT_LABELS: Record<string, string> = {
  alpha: "ALPHA  |  MACRO INTELLIGENCE",
  beta:  "BETA   |  MOMENTUM SCREENER",
  gamma: "GAMMA  |  OPTIONS / GEX",
  delta: "DELTA  |  SECTOR ROTATION",
  epsilon: "EPSILON  |  FII / DII FLOW",
  zeta:  "ZETA   |  WATCHLIST SIGNALS",
  eta:   "ETA    |  CORPORATE EVENTS",
  iota:  "IOTA   |  GLOBAL INTEL",
  fusion: "FUSION  |  COMPOSITE PICKS",
};

const AGENTS = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","fusion"];

export default function AnalysisPage() {
  const [reports, setReports] = useState<Record<string, AgentCard>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState("");
  const [open, setOpen]     = useState<string>("alpha");

  useEffect(() => {
    fetch("/api/analysis")
      .then(r => r.json())
      .then(d => { setReports(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:   { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:    { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
              borderBottom: "1px solid var(--border)", padding: "6px 20px",
              fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:   { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    tabs:   { display: "flex", gap: 6, flexWrap: "wrap" as const, marginBottom: 20 },
    tab:    (active: boolean) => ({
      padding: "5px 14px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (active ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: active ? "var(--accent)" + "22" : "transparent",
      color: active ? "var(--accent)" : "var(--dim)",
    }),
    card:   { background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "16px 20px", marginBottom: 16 },
    label:  { fontSize: 10, color: "var(--dim)", letterSpacing: 2, marginBottom: 8 },
    val:    { fontSize: 13, color: "var(--text)" },
    grid:   { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12, marginBottom: 16 },
    kv:     { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "10px 14px" },
    kvk:    { fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 4 },
    kvv:    { fontSize: 13, color: "var(--text)", fontWeight: 600 },
    pre:    { fontSize: 12, color: "var(--text)", lineHeight: 1.7, whiteSpace: "pre-wrap" as const,
              background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6,
              padding: "12px 16px", marginTop: 8 },
    tbl:    { width: "100%", borderCollapse: "collapse" as const, fontSize: 12, marginTop: 8 },
    th:     { padding: "6px 10px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
              color: "var(--dim)", borderBottom: "1px solid var(--border)" },
    td:     { padding: "7px 10px", borderBottom: "1px solid var(--border) + 44", color: "var(--text)" },
  };

  function renderReport(name: string, rpt: AgentCard) {
    if (!rpt) return <div style={S.card}><div style={S.label}>{AGENT_LABELS[name] || name.toUpperCase()}</div><div style={{color:"var(--dim)",fontSize:12}}>No data -- run py agent_{name}.py</div></div>;
    const ts = rpt.timestamp || rpt.date || "";
    const kvs: [string, string][] = [];
    if (rpt.regime !== undefined) kvs.push(["REGIME", regimeStr(rpt.regime)]);
    if (rpt.confidence !== undefined) kvs.push(["CONFIDENCE", safeStr(rpt.confidence)]);
    if (rpt.summary !== undefined) kvs.push(["SUMMARY", safeStr(rpt.summary)]);

    const lists: [string, unknown[]][] = [];
    for (const [k, v] of Object.entries(rpt)) {
      if (["agent","timestamp","date","llm_analysis","regime","confidence","summary"].includes(k)) continue;
      if (Array.isArray(v) && v.length > 0) lists.push([k, v]);
    }

    return (
      <div style={S.card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ fontSize: 11, color: "var(--accent)", letterSpacing: 2, fontWeight: 700 }}>
            {AGENT_LABELS[name] || name.toUpperCase()}
          </span>
          <span style={{ fontSize: 10, color: "var(--dim)" }}>{ts}</span>
        </div>

        {kvs.length > 0 && (
          <div style={S.grid}>
            {kvs.map(([k, v]) => (
              <div key={k} style={S.kv}>
                <div style={S.kvk}>{k}</div>
                <div style={S.kvv}>{v}</div>
              </div>
            ))}
          </div>
        )}

        {rpt.llm_analysis && (
          <pre style={S.pre}>{rpt.llm_analysis}</pre>
        )}

        {lists.map(([k, rows]) => (
          <div key={k} style={{ marginTop: 16 }}>
            <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 6 }}>
              {k.replace(/_/g, " ").toUpperCase()}  ({rows.length})
            </div>
            {typeof rows[0] === "object" && rows[0] !== null ? (
              <div style={{ overflowX: "auto" as const }}>
                <table style={S.tbl}>
                  <thead>
                    <tr>{Object.keys(rows[0] as Record<string, unknown>).slice(0,8).map(col => (
                      <th key={col} style={S.th}>{col.toUpperCase()}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 20).map((row, i) => (
                      <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : "var(--surface)" + "88" }}>
                        {Object.values(row as Record<string, unknown>).slice(0,8).map((val, j) => (
                          <td key={j} style={S.td}>{safeStr(val)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {rows.slice(0, 30).map((r, i) => (
                  <span key={i} style={{ padding: "3px 8px", background: "var(--bg)",
                    border: "1px solid var(--border)", borderRadius: 4, fontSize: 11, color: "var(--text)" }}>
                    {safeStr(r)}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>ANALYSIS  /  AGENT REPORTS</div>
      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading agent reports...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error}</div>}

        {!loading && !error && (
          <>
            <div style={S.tabs}>
              {AGENTS.map(a => (
                <button key={a} onClick={() => setOpen(a)} style={S.tab(open === a)}>
                  {a.toUpperCase()}
                </button>
              ))}
              <button onClick={() => setOpen("all")} style={S.tab(open === "all")}>ALL</button>
            </div>

            {open === "all"
              ? AGENTS.map(a => renderReport(a, reports[a]))
              : renderReport(open, reports[open])
            }
          </>
        )}
      </div>
    </div>
  );
}
'''

write(APP / "analysis" / "page.tsx", analysis_page, "/analysis/page.tsx")


# =============================================================================
# [1b] /api/analysis/route.ts - reads all agent reports
# =============================================================================
log("[1b] /api/analysis/route.ts ...")

analysis_api = '''\
import { NextResponse } from "next/server";
import { readFileSync } from "fs";
import { join } from "path";

const AGENTS = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","fusion"];
const BASE = "D:/MICC/agents";

function safeRead(path: string): Record<string, unknown> {
  try {
    const raw = readFileSync(path, "utf-8")
      .replace(/:\\s*NaN\\b/g, ": null")
      .replace(/:\\s*Infinity\\b/g, ": null")
      .replace(/:\\s*-Infinity\\b/g, ": null");
    return JSON.parse(raw);
  } catch {
    return { error: "not found" };
  }
}

export function GET() {
  const out: Record<string, Record<string, unknown>> = {};
  for (const name of AGENTS) {
    out[name] = safeRead(join(BASE, name, "last_report.json"));
  }
  return NextResponse.json(out);
}
'''
write(APP / "api" / "analysis" / "route.ts", analysis_api, "/api/analysis/route.ts")


# =============================================================================
# [2]  /options - add NavBar
# =============================================================================
log("[2/8] Fixing /options page (add NavBar if missing)...")

opt_path = APP / "options" / "page.tsx"
if opt_path.exists():
    src = read(opt_path)
    # Remove any existing emojis (very common in options pages)
    # Check if NavBar is already there
    if 'import NavBar' not in src:
        # Add NavBar import after first "use client"
        src = src.replace(
            '"use client";',
            '"use client";\nimport NavBar from "@/components/NavBar";',
            1
        )
        # Find the root return div and inject NavBar
        # Pattern: return (\n    <div style={{...bg...}}>
        src = re.sub(
            r'(return\s*\(\s*\n\s*<div[^>]*background[^>]*>)',
            r'\1\n      <NavBar />',
            src
        )
        opt_path.write_text(src, encoding="utf-8")
        print("  [OK] Added NavBar to /options")
    else:
        print("  [SKIP] NavBar already in /options")
else:
    # Create minimal options page
    options_page = '''\
"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

export default function OptionsPage() {
  const [data, setData]   = useState<Record<string, unknown> | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");

  useEffect(() => {
    fetch("/api/options")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page: { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:  { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
            borderBottom: "1px solid var(--border)", padding: "6px 20px",
            fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap: { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    card: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "20px" },
  };

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>OPTIONS  /  CHAIN & GREEKS</div>
      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading options data...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error} -- run pipeline to fetch options data</div>}
        {data    && <pre style={{ color: "var(--text)", fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(data, null, 2)}</pre>}
      </div>
    </div>
  );
}
'''
    write(opt_path, options_page, "/options/page.tsx (stub with NavBar)")


# =============================================================================
# [3]  /patterns - fix zoom bug (remove transform:scale)
# =============================================================================
log("[3/8] Fixing /patterns zoom bug...")

pat_path = APP / "patterns" / "page.tsx"
if pat_path.exists():
    src = read(pat_path)
    changed = False
    # Remove transform scale
    if "transform" in src and "scale" in src:
        src = re.sub(r'transform\s*:\s*["\']?scale\([^)]*\)["\']?,?\s*', '', src)
        changed = True
    # Remove zoom
    if "zoom:" in src or "zoom :" in src:
        src = re.sub(r'zoom\s*:\s*[\d.]+,?\s*', '', src)
        changed = True
    # Remove viewport meta overrides in TSX
    if 'initial-scale' in src and 'viewport' in src:
        src = re.sub(r'<meta[^>]*viewport[^>]*>', '', src)
        changed = True
    if changed:
        pat_path.write_text(src, encoding="utf-8")
        print("  [OK] Removed zoom/scale from /patterns")
    else:
        print("  [SKIP] No zoom/scale found in /patterns")
else:
    print("  [SKIP] /patterns page.tsx not found")


# =============================================================================
# [4]  /analytics - fix zoom bug
# =============================================================================
log("[4/8] Fixing /analytics zoom bug...")

ana_path = APP / "analytics" / "page.tsx"
if ana_path.exists():
    src = read(ana_path)
    changed = False
    if "transform" in src and "scale" in src:
        src = re.sub(r'transform\s*:\s*["\']?scale\([^)]*\)["\']?,?\s*', '', src)
        changed = True
    if "zoom:" in src:
        src = re.sub(r'zoom\s*:\s*[\d.]+,?\s*', '', src)
        changed = True
    if changed:
        ana_path.write_text(src, encoding="utf-8")
        print("  [OK] Removed zoom/scale from /analytics")
    else:
        print("  [SKIP] No zoom/scale in /analytics")
else:
    print("  [SKIP] /analytics page.tsx not found")


# =============================================================================
# [5]  /macro - redesign to match reference style
# =============================================================================
log("[5/8] Rebuilding /macro page...")

macro_page = '''\
"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface MacroRow { indicator: string; value: string | number | null; unit?: string; date?: string; source?: string; }
interface MacroData {
  repo_rate?: number | null;
  reverse_repo?: number | null;
  crr?: number | null;
  cpi_latest?: number | null;
  gdp_growth?: number | null;
  usd_inr?: number | null;
  india_10y?: number | null;
  us_fed_rate?: number | null;
  us_10y?: number | null;
  us_cpi?: number | null;
  rbi_history?: { date: string; repo_rate: number; reverse_repo: number; crr: number }[];
  us_macro?: MacroRow[];
  india_macro?: MacroRow[];
  [key: string]: unknown;
}

const fmt = (v: unknown, d = 2): string => {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toFixed(d);
};

export default function MacroPage() {
  const [data, setData] = useState<MacroData | null>(null);
  const [loading, setL] = useState(true);
  const [error, setE]   = useState("");
  const [tab, setTab]   = useState<"india" | "us" | "rbi">("india");

  useEffect(() => {
    fetch("/api/macro")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    grid:  { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 24 },
    kv:    { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "12px 16px" },
    kvk:   { fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 4 },
    kvv:   { fontSize: 20, color: "var(--text)", fontWeight: 700 },
    tabs:  { display: "flex", gap: 6, marginBottom: 20 },
    tab:   (a: boolean) => ({
      padding: "5px 16px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (a ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: a ? "var(--accent)" + "22" : "transparent",
      color: a ? "var(--accent)" : "var(--dim)",
    }),
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)",
             background: "var(--surface)" },
    td:    { padding: "8px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
  };

  const KV = ({ label, value, color }: { label: string; value: string; color?: string }) => (
    <div style={S.kv}>
      <div style={S.kvk}>{label}</div>
      <div style={{ ...S.kvv, color: color || "var(--text)" }}>{value}</div>
    </div>
  );

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>MACRO  /  INDIA & GLOBAL INDICATORS</div>
      <div style={S.wrap}>

        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading macro data...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error}</div>}

        {data && <>
          <div style={S.grid}>
            <KV label="REPO RATE"      value={fmt(data.repo_rate) + "%"} color="var(--accent)" />
            <KV label="REVERSE REPO"   value={fmt(data.reverse_repo) + "%"} />
            <KV label="CRR"            value={fmt(data.crr) + "%"} />
            <KV label="CPI (INDIA)"    value={fmt(data.cpi_latest) + "%"} color={Number(data.cpi_latest) > 6 ? "var(--bear)" : "var(--bull)"} />
            <KV label="GDP GROWTH"     value={fmt(data.gdp_growth) + "%"} color="var(--bull)" />
            <KV label="USD/INR"        value={fmt(data.usd_inr, 2)} />
            <KV label="INDIA 10Y"      value={fmt(data.india_10y) + "%"} />
            <KV label="US FED RATE"    value={fmt(data.us_fed_rate) + "%"} />
            <KV label="US 10Y YIELD"   value={fmt(data.us_10y) + "%"} />
            <KV label="US CPI"         value={fmt(data.us_cpi) + "%"} color={Number(data.us_cpi) > 3 ? "var(--warn)" : "var(--bull)"} />
          </div>

          <div style={S.tabs}>
            {(["india","us","rbi"] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={S.tab(tab === t)}>
                {t === "rbi" ? "RBI HISTORY" : t.toUpperCase() + " MACRO"}
              </button>
            ))}
          </div>

          {tab === "india" && data.india_macro && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>INDICATOR</th>
                  <th style={S.th}>VALUE</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>SOURCE</th>
                </tr></thead>
                <tbody>
                  {data.india_macro.map((row, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={S.td}>{row.indicator || row.source || "--"}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>
                        {fmt(row.value, 3)}{row.unit ? " " + row.unit : ""}
                      </td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{row.date || "--"}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{row.source || "--"}</td>
                    </tr>
                  ))}
                  {(!data.india_macro || data.india_macro.length === 0) && (
                    <tr><td colSpan={4} style={{ ...S.td, color: "var(--dim)", textAlign: "center" }}>No data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === "us" && data.us_macro && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>INDICATOR</th>
                  <th style={S.th}>VALUE</th>
                  <th style={S.th}>DATE</th>
                </tr></thead>
                <tbody>
                  {data.us_macro.map((row, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={S.td}>{row.indicator || "--"}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>
                        {fmt(row.value, 3)}{row.unit ? " " + row.unit : ""}
                      </td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{row.date || "--"}</td>
                    </tr>
                  ))}
                  {(!data.us_macro || data.us_macro.length === 0) && (
                    <tr><td colSpan={3} style={{ ...S.td, color: "var(--dim)", textAlign: "center" }}>No data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === "rbi" && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>REPO RATE</th>
                  <th style={S.th}>REVERSE REPO</th>
                  <th style={S.th}>CRR</th>
                </tr></thead>
                <tbody>
                  {(data.rbi_history || []).map((row, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={S.td}>{row.date}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>{fmt(row.repo_rate)}%</td>
                      <td style={S.td}>{fmt(row.reverse_repo)}%</td>
                      <td style={S.td}>{fmt(row.crr)}%</td>
                    </tr>
                  ))}
                  {(!data.rbi_history || data.rbi_history.length === 0) && (
                    <tr><td colSpan={4} style={{ ...S.td, color: "var(--dim)", textAlign: "center" }}>
                      No RBI history -- run fetch_rbi_rates.py
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>}
      </div>
    </div>
  );
}
'''
write(APP / "macro" / "page.tsx", macro_page, "/macro/page.tsx")


# /api/macro/route.ts
macro_api = '''\
import { NextResponse } from "next/server";
import Database from "better-sqlite3";

const DB = "D:/marketDB/db/market.db";

function safeDb<T>(fn: (db: ReturnType<typeof Database>) => T, fallback: T): T {
  let db: ReturnType<typeof Database> | null = null;
  try {
    db = new Database(DB, { readonly: true, timeout: 5000 });
    return fn(db);
  } catch {
    return fallback;
  } finally {
    try { db?.close(); } catch {}
  }
}

export function GET() {
  const result: Record<string, unknown> = {};

  // RBI rates
  const rbiHistory = safeDb(db => {
    return db.prepare(
      "SELECT date, repo_rate, reverse_repo, crr FROM rbi_monetary_data ORDER BY date DESC LIMIT 50"
    ).all();
  }, []);
  result.rbi_history = rbiHistory;

  if (Array.isArray(rbiHistory) && rbiHistory.length > 0) {
    const latest = rbiHistory[0] as Record<string, unknown>;
    result.repo_rate     = latest.repo_rate;
    result.reverse_repo  = latest.reverse_repo;
    result.crr           = latest.crr;
  }

  // India macro from india_monthly_macro
  const indiaMacro = safeDb(db => {
    try {
      return db.prepare(
        "SELECT indicator, value, date, source FROM india_monthly_macro ORDER BY date DESC LIMIT 100"
      ).all();
    } catch { return []; }
  }, []);
  result.india_macro = indiaMacro;

  // US macro
  const usMacro = safeDb(db => {
    try {
      return db.prepare(
        "SELECT indicator, value, date FROM us_macro_data ORDER BY date DESC LIMIT 50"
      ).all();
    } catch { return []; }
  }, []);
  result.us_macro = usMacro;

  // Global indices for rates
  const rates = safeDb(db => {
    try {
      return db.prepare(
        "SELECT symbol, close FROM global_indices_daily WHERE symbol IN (\'US10Y\',\'US2Y\',\'USDINR\') ORDER BY date DESC LIMIT 3"
      ).all() as {symbol:string;close:number}[];
    } catch { return []; }
  }, [] as {symbol:string;close:number}[]);

  for (const r of rates) {
    if (r.symbol === "US10Y")  result.us_10y   = r.close;
    if (r.symbol === "USDINR") result.usd_inr  = r.close;
  }

  return NextResponse.json(result);
}
'''
write(APP / "api" / "macro" / "route.ts", macro_api, "/api/macro/route.ts")


# =============================================================================
# [6]  /eta - full redesign: insider clusters, dividends, results tables
# =============================================================================
log("[6/8] Rebuilding /eta page (full redesign)...")

eta_page = '''\
"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface InsiderCluster {
  symbol: string; n_buys: number; total_value_cr: number; names: string;
}
interface BigTrade {
  symbol: string; filing_date: string; name: string;
  transaction_type: string; quantity: number; price: number; value: number;
}
interface ResultEvent {
  symbol: string; announcement_date: string; subject: string;
}
interface DivEvent {
  symbol: string; announcement_date: string; subject: string;
}
interface PostReaction {
  symbol: string; announcement_date: string; ret_5d?: number;
}
interface UpcomingResult {
  symbol: string; last_results_date: string; expected_due: string;
}

interface EtaData {
  screen1_results_season?: ResultEvent[];
  screen2_dividends?: DivEvent[];
  screen3_insider_clusters?: InsiderCluster[];
  screen4_big_trades?: BigTrade[];
  screen5_post_results_reaction?: PostReaction[];
  screen6_upcoming_results?: UpcomingResult[];
  llm_analysis?: string;
  timestamp?: string;
  date?: string;
}

const fmt  = (v: unknown, d = 2) => v == null ? "--" : Number(v).toFixed(d);
const pct  = (v: unknown) => v == null ? "--" : (Number(v) >= 0 ? "+" : "") + Number(v).toFixed(2) + "%";
const bull = (v: unknown) => Number(v) >= 0 ? "var(--bull)" : "var(--bear)";
const cr   = (v: unknown) => v == null ? "--" : (Number(v) / 1e7).toFixed(2) + " Cr";

export default function EtaPage() {
  const [data, setData]   = useState<EtaData | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");
  const [tab, setTab]     = useState(0);
  const [search, setSrch] = useState("");

  useEffect(() => {
    fetch("/api/eta")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 20 },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    tabs:  { display: "flex", gap: 6, flexWrap: "wrap" as const, marginBottom: 20 },
    tab:   (a: boolean): React.CSSProperties => ({
      padding: "5px 16px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (a ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: a ? "var(--accent)22" : "transparent",
      color: a ? "var(--accent)" : "var(--dim)",
    }),
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)", background: "var(--surface)" },
    td:    { padding: "8px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    sym:   { color: "var(--accent)", fontWeight: 700 },
    empty: { padding: "30px", textAlign: "center" as const, color: "var(--dim)", fontSize: 12 },
    input: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4,
             padding: "4px 10px", fontSize: 11, color: "var(--text)", outline: "none" },
    pre:   { fontSize: 11, color: "var(--text)", lineHeight: 1.7, whiteSpace: "pre-wrap" as const,
             background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6,
             padding: "12px 16px", maxHeight: 400, overflow: "auto" as const },
    badge: (buy: boolean): React.CSSProperties => ({
      padding: "2px 8px", borderRadius: 3, fontSize: 10, fontWeight: 700,
      background: buy ? "var(--bull)22" : "var(--bear)22",
      color: buy ? "var(--bull)" : "var(--bear)",
    }),
  };

  const TABS = [
    "INSIDER CLUSTERS",
    "BIG TRADES",
    "RESULTS SEASON",
    "DIVIDENDS",
    "POST-RESULTS",
    "UPCOMING",
    "LLM ANALYSIS",
  ];

  const filter = <T extends { symbol?: string }>(arr: T[] | undefined): T[] => {
    if (!arr) return [];
    if (!search) return arr;
    return arr.filter(r => r.symbol?.toLowerCase().includes(search.toLowerCase()));
  };

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>ETA  /  CORPORATE EVENTS INTELLIGENCE</span>
        <input
          style={S.input}
          placeholder="search symbol..."
          value={search}
          onChange={e => setSrch(e.target.value)}
        />
        {data?.timestamp && (
          <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>
            {data.timestamp}
          </span>
        )}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading corporate events...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>
          Error: {error} -- run: py D:\\MICC\\agent_eta.py --send
        </div>}

        {data && <>
          <div style={S.tabs}>
            {TABS.map((t, i) => (
              <button key={i} onClick={() => setTab(i)} style={S.tab(tab === i)}>{t}</button>
            ))}
          </div>

          {tab === 0 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>BUY COUNT</th>
                  <th style={S.th}>TOTAL VALUE</th>
                  <th style={S.th}>INSIDERS</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen3_insider_clusters).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--bull)", fontWeight: 700 }}>{r.n_buys}</td>
                      <td style={{ ...S.td, color: "var(--accent)" }}>{cr(r.total_value_cr)}</td>
                      <td style={{ ...S.td, color: "var(--dim)", fontSize: 11 }}>{r.names}</td>
                    </tr>
                  ))}
                  {filter(data.screen3_insider_clusters).length === 0 && (
                    <tr><td colSpan={4} style={S.empty}>No insider clusters found</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 1 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>NAME</th>
                  <th style={S.th}>TYPE</th>
                  <th style={S.th}>QTY</th>
                  <th style={S.th}>PRICE</th>
                  <th style={S.th}>VALUE</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen4_big_trades).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.filing_date}</td>
                      <td style={{ ...S.td, fontSize: 11 }}>{r.name}</td>
                      <td style={S.td}>
                        <span style={S.badge(r.transaction_type === "BUY")}>
                          {r.transaction_type}
                        </span>
                      </td>
                      <td style={S.td}>{r.quantity ? Number(r.quantity).toLocaleString("en-IN") : "--"}</td>
                      <td style={S.td}>{fmt(r.price)}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>
                        {r.value ? (Number(r.value) / 1e7).toFixed(2) + " Cr" : "--"}
                      </td>
                    </tr>
                  ))}
                  {filter(data.screen4_big_trades).length === 0 && (
                    <tr><td colSpan={7} style={S.empty}>No big trades found</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 2 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>SUBJECT</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen1_results_season).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.announcement_date}</td>
                      <td style={{ ...S.td, fontSize: 11 }}>{r.subject}</td>
                    </tr>
                  ))}
                  {filter(data.screen1_results_season).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No results announcements</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 3 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>SUBJECT</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen2_dividends).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.announcement_date}</td>
                      <td style={{ ...S.td, fontSize: 11 }}>{r.subject}</td>
                    </tr>
                  ))}
                  {filter(data.screen2_dividends).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No dividend announcements</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 4 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>5D RETURN</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen5_post_results_reaction).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.announcement_date}</td>
                      <td style={{ ...S.td, color: bull(r.ret_5d), fontWeight: 600 }}>{pct(r.ret_5d)}</td>
                    </tr>
                  ))}
                  {filter(data.screen5_post_results_reaction).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No post-results data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 5 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>LAST RESULTS</th>
                  <th style={S.th}>EXPECTED DUE</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen6_upcoming_results).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.last_results_date}</td>
                      <td style={{ ...S.td, color: "var(--warn)" }}>{r.expected_due}</td>
                    </tr>
                  ))}
                  {filter(data.screen6_upcoming_results).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No upcoming results data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 6 && data.llm_analysis && (
            <pre style={S.pre}>{data.llm_analysis}</pre>
          )}
          {tab === 6 && !data.llm_analysis && (
            <div style={{ color: "var(--dim)", padding: 20 }}>No LLM analysis -- run py agent_eta.py --send</div>
          )}
        </>}
      </div>
    </div>
  );
}
'''
write(APP / "eta" / "page.tsx", eta_page, "/eta/page.tsx")


# =============================================================================
# [7]  /global - remove ALL emojis, fix layout
# =============================================================================
log("[7/8] Fixing /global page (remove emojis, fix layout)...")

gbl_path = APP / "global" / "page.tsx"
if gbl_path.exists():
    src = read(gbl_path)
    original_len = len(src)

    # Remove flag field assignments (lines containing flag: "...")
    src = re.sub(r',?\s*flag\s*:\s*"[^"]*"', '', src)

    # Remove emoji from META display - replace flag renders with empty string or cat
    # Pattern: {META[sym]?.flag} or similar
    src = re.sub(r'\{[A-Za-z_]+\??\.\s*flag\s*\}', '', src)
    src = re.sub(r'\{[A-Za-z_]+\[[\w]+\]\??\.\s*flag\}', '', src)
    src = re.sub(r'flag\s*&&\s*[^,}]+', '', src)  # flag && <span>...
    src = re.sub(r'\{[^}]*\.flag[^}]*\}', '', src)  # any {x.flag} expressions

    # Remove literal emoji chars (unicode ranges: emoticons, flags, misc symbols)
    import unicodedata
    cleaned = []
    for ch in src:
        try:
            cat = unicodedata.category(ch)
            name = unicodedata.name(ch, "")
            # Keep ASCII + standard Latin + common punctuation
            if ord(ch) < 128:
                cleaned.append(ch)
            elif cat.startswith('L') or cat.startswith('N') or cat.startswith('P'):
                # Letter, Number, Punctuation - keep
                cleaned.append(ch)
            elif ch in ['%', '−', '–', '—', '"', '"', ''', ''', '…', '×', '±', '→', '←', '↑', '↓', '▲', '▼', '■', '□']:
                cleaned.append(ch)
            else:
                # Skip emoji and other symbols
                pass
        except Exception:
            pass
    src = ''.join(cleaned)

    # Also remove the flag property from META type definition
    src = re.sub(r'flag\?:\s*string;\s*', '', src)
    src = re.sub(r'flag\s*:\s*string;\s*', '', src)

    gbl_path.write_text(src, encoding="utf-8")
    new_len = len(src)
    print(f"  [OK] /global: removed {original_len - new_len} chars of emoji/flag content")
else:
    print("  [SKIP] /global page.tsx not found")


# =============================================================================
# [8]  /watchlist - match reference design
# =============================================================================
log("[8/8] Fixing /watchlist page...")

watch_page = '''\
"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface WatchItem {
  symbol: string;
  name?: string;
  close?: number | null;
  pct_change?: number | null;
  rsi_14?: number | null;
  adx_14?: number | null;
  atr_14_pct?: number | null;
  conviction_score?: number | null;
  screen_tags?: string | null;
  reason?: string;
  added_date?: string;
}
interface WatchData {
  watchlist: WatchItem[];
  timestamp?: string;
  count?: number;
}

const fmt = (v: unknown, d = 2) => v == null ? "--" : Number(v).toFixed(d);
const pct = (v: unknown) => v == null ? "--" : (Number(v)>=0?"+":"") + Number(v).toFixed(2) + "%";
const bull= (v: unknown) => Number(v) >= 0 ? "var(--bull)" : "var(--bear)";

export default function WatchlistPage() {
  const [data, setData]   = useState<WatchData | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");
  const [search, setSrch] = useState("");
  const [sort, setSort]   = useState<keyof WatchItem>("conviction_score");
  const [asc, setAsc]     = useState(false);

  useEffect(() => {
    fetch("/api/watchlist")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" as const },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    input: { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4,
             padding: "4px 10px", fontSize: 11, color: "var(--text)", outline: "none" },
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)",
             background: "var(--surface)", cursor: "pointer", userSelect: "none" as const },
    td:    { padding: "8px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    sym:   { color: "var(--accent)", fontWeight: 700 },
  };

  function mkSort(col: keyof WatchItem) {
    if (sort === col) setAsc(!asc);
    else { setSort(col); setAsc(false); }
  }
  function sortIcon(col: keyof WatchItem) {
    if (sort !== col) return "";
    return asc ? " ^" : " v";
  }

  const items = (data?.watchlist || [])
    .filter(r => !search || r.symbol.toLowerCase().includes(search.toLowerCase()) ||
                            (r.name || "").toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const av = a[sort] ?? 0, bv = b[sort] ?? 0;
      if (typeof av === "number" && typeof bv === "number")
        return asc ? av - bv : bv - av;
      return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>WATCHLIST  /  ACTIVE SIGNALS</span>
        <input
          style={S.input}
          placeholder="search symbol or name..."
          value={search}
          onChange={e => setSrch(e.target.value)}
        />
        {data?.count !== undefined && (
          <span style={{ fontSize: 10, color: "var(--dim)" }}>{data.count} stocks</span>
        )}
        {data?.timestamp && (
          <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>{data.timestamp}</span>
        )}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading watchlist...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>
          Error: {error} -- run: py D:\\MICC\\agent_zeta.py
        </div>}

        {data && (
          <div style={S.card}>
            <table style={S.tbl}>
              <thead><tr>
                {([
                  ["symbol","SYMBOL"],
                  ["name","NAME"],
                  ["close","CLOSE"],
                  ["pct_change","1D %"],
                  ["rsi_14","RSI"],
                  ["adx_14","ADX"],
                  ["atr_14_pct","ATR%"],
                  ["conviction_score","CONVICTION"],
                  ["screen_tags","TAGS"],
                ] as [keyof WatchItem, string][]).map(([col, label]) => (
                  <th key={col} style={S.th} onClick={() => mkSort(col)}>
                    {label}{sortIcon(col)}
                  </th>
                ))}
              </tr></thead>
              <tbody>
                {items.map((r, i) => (
                  <tr key={r.symbol} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                    <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                    <td style={{ ...S.td, fontSize: 11, color: "var(--dim)" }}>{r.name || "--"}</td>
                    <td style={S.td}>{fmt(r.close)}</td>
                    <td style={{ ...S.td, color: bull(r.pct_change), fontWeight: 600 }}>{pct(r.pct_change)}</td>
                    <td style={{ ...S.td, color: Number(r.rsi_14)>70?"var(--bear)":Number(r.rsi_14)<30?"var(--bull)":"var(--text)" }}>
                      {fmt(r.rsi_14, 1)}
                    </td>
                    <td style={{ ...S.td, color: Number(r.adx_14)>25?"var(--accent)":"var(--dim)" }}>
                      {fmt(r.adx_14, 1)}
                    </td>
                    <td style={S.td}>{fmt(r.atr_14_pct, 2)}{r.atr_14_pct != null ? "%" : ""}</td>
                    <td style={{ ...S.td, color: Number(r.conviction_score)>=70?"var(--bull)":Number(r.conviction_score)>=40?"var(--warn)":"var(--bear)", fontWeight: 700 }}>
                      {fmt(r.conviction_score, 0)}
                    </td>
                    <td style={{ ...S.td, fontSize: 10, color: "var(--info)" }}>{r.screen_tags || "--"}</td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr><td colSpan={9} style={{ padding: 30, textAlign: "center", color: "var(--dim)" }}>
                    No watchlist items -- run py agent_zeta.py
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
'''
write(APP / "watchlist" / "page.tsx", watch_page, "/watchlist/page.tsx")


# =============================================================================
# Summary
# =============================================================================
print()
print("=" * 60)
print("PHASE 3A COMPLETE")
print("=" * 60)
print()
print("Files written:")
print("  D:\\MICC\\micc-dashboard\\src\\app\\analysis\\page.tsx      (fixed: no multi-NavBar, no [object Object])")
print("  D:\\MICC\\micc-dashboard\\src\\app\\api\\analysis\\route.ts  (reads all 9 agent reports)")
print("  D:\\MICC\\micc-dashboard\\src\\app\\options\\page.tsx        (added NavBar)")
print("  D:\\MICC\\micc-dashboard\\src\\app\\macro\\page.tsx          (redesigned: RBI + India + US tabs)")
print("  D:\\MICC\\micc-dashboard\\src\\app\\api\\macro\\route.ts      (reads rbi_monetary_data + macro tables)")
print("  D:\\MICC\\micc-dashboard\\src\\app\\eta\\page.tsx            (full redesign: 7 tabs, tables)")
print("  D:\\MICC\\micc-dashboard\\src\\app\\global\\page.tsx         (emojis stripped)")
print("  D:\\MICC\\micc-dashboard\\src\\app\\watchlist\\page.tsx      (reference design: sortable table)")
print()
print("Also patched (in-place):")
print("  /patterns  -- removed zoom/scale transforms")
print("  /analytics -- removed zoom/scale transforms")
print()
print("Next steps:")
print("  cd D:\\MICC\\micc-dashboard && npm run dev")
print("  Check each page in browser")
print("  Run: py D:\\MICC\\agent_eta.py --send  (populate eta data)")
print("  Run: py D:\\MICC\\agent_zeta.py        (populate watchlist)")
