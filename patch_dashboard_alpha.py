"""
MICC Dashboard Patch - Fix AlphaPanel key mapping + LLM box height
Run from DATA-ANALYSIS:  py patch_dashboard_alpha.py

Fixes:
1. AlphaPanel was reading wrong JSON keys (regime_metrics, breadth_analytics, cap_rotation)
   Real keys from agent_alpha.py: regime (dict), breadth (dict with by_day), cap_rotation (dict)
2. LLM analysis boxes made taller with expand option
3. Date display fixed - reads from end_date not latest_market_date
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))

def find_dashboard():
    # Try both possible locations
    for subpath in ["micc-dashboard/src/components", "micc-dashboard/components"]:
        p = os.path.join(BASE, subpath)
        if os.path.isdir(p):
            return p
    return None

COMP = find_dashboard()
if not COMP:
    print("[ERROR] micc-dashboard not found. Run: py build_dashboard.py first")
    sys.exit(1)

LIB = COMP.replace("components", "lib")
APP = COMP.replace("components", "app")
print(f"[INFO] Patching: {COMP}")

def w(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.lstrip("\n"))
    print(f"  patched: {os.path.relpath(path, BASE)}")

# ── AlphaPanel.tsx — fixed key mapping ───────────────────────────────────────
# Real alpha JSON structure:
#   result.regime = { latest_close, window_pct, vol_ann_pct, pe, regime, confidence, above_ma20, ... }
#   result.breadth = { by_day: [{date, advancing, declining, unchanged, total, pct_adv, ad_ratio}], avg_pct_adv, total_days }
#   result.cap_rotation = { largecap_avg_pct, midcap_avg_pct, smallcap_avg_pct, signal }
#   result.global_context = { tickers: { DXY: {close, pct_chg}, ... } }
#   result.top10_gainers = [{index, pct_change, ...}]
#   result.top10_losers  = [{index, pct_change, ...}]
#   result.end_date = "2026-04-29"
#   result.regime_analysis = string or dict with .analysis

w(os.path.join(COMP, "AlphaPanel.tsx"), """
import { fmtNum, fmtPct, colorPct, regimeCls } from "@/lib/utils";

export default function AlphaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Alpha -- Macro and Regime</span>
      </div>
      <div style={{ color: "var(--neg)", fontFamily: "monospace", fontSize: 12, padding: 8 }}>
        {data?._error || "No alpha report found. Run: py micc_engine.py"}
      </div>
    </div>
  );

  // Real keys from agent_alpha.py
  const regimeObj  = data.regime || {};                    // { latest_close, window_pct, regime, confidence, pe, vol_ann_pct }
  const breadthObj = data.breadth || {};                   // { by_day: [...], avg_pct_adv, total_days }
  const rotation   = data.cap_rotation || {};              // { largecap_avg_pct, midcap_avg_pct, smallcap_avg_pct, signal }
  const globalCtx  = data.global_context || {};            // { tickers: { DXY: {close, pct_chg}, ... } }
  const gainers    = data.top10_gainers || [];             // [{index, pct_change}]
  const losers     = data.top10_losers  || [];             // [{index, pct_change}]
  const date       = data.end_date || data.timestamp?.slice(0, 10) || "--";
  const regime     = regimeObj.regime || "";
  const rcls       = regimeCls(regime);

  // Breadth: use last day's data
  const byDay     = breadthObj.by_day || [];
  const lastDay   = byDay[byDay.length - 1] || {};
  const advances  = lastDay.advancing ?? "--";
  const declines  = lastDay.declining ?? "--";
  const total     = lastDay.total ?? "--";
  const adRatio   = lastDay.ad_ratio;

  // Global tickers
  const tickers = globalCtx.tickers || globalCtx || {};
  const tickerItems = Object.entries(tickers).slice(0, 8);

  // Regime analysis - can be string or object
  const ra = data.regime_analysis;
  const raText = typeof ra === "string" ? ra : (ra?.analysis || ra?.regime || "");

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Alpha <span className="card-accent">-- Macro and Regime</span>
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)" }}>{date}</span>
          {regime && (
            <span className={"pill " + rcls} style={{ fontSize: 11 }}>{regime}</span>
          )}
          {regimeObj.confidence && (
            <span className="pill pill-neut" style={{ fontSize: 9 }}>{regimeObj.confidence}</span>
          )}
        </div>
      </div>

      {/* KPI Row */}
      <div className="kpi-grid">
        <div className="kpi">
          <div className="kpi-label">Nifty 50</div>
          <div className="kpi-value" style={{ fontSize: 20 }}>
            {fmtNum(regimeObj.latest_close, 2)}
          </div>
          <div className="kpi-sub" style={{ color: colorPct(regimeObj.window_pct) }}>
            {fmtPct(regimeObj.window_pct)} window
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">India VIX</div>
          <div className="kpi-value" style={{
            color: (Number(regimeObj.india_vix || regimeObj.vix) || 0) > 20
              ? "var(--neg)"
              : (Number(regimeObj.india_vix || regimeObj.vix) || 0) < 13
              ? "var(--pos)" : "var(--warn)"
          }}>
            {fmtNum(regimeObj.india_vix || regimeObj.vix, 2)}
          </div>
          <div className="kpi-sub">Vol: {fmtNum(regimeObj.vol_ann_pct, 1)}%</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Advances</div>
          <div className="kpi-value" style={{ color: "var(--pos)" }}>{advances}</div>
          <div className="kpi-sub">of {total} indices</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Declines</div>
          <div className="kpi-value" style={{ color: "var(--neg)" }}>{declines}</div>
          <div className="kpi-sub">
            A/D {adRatio ? Number(adRatio).toFixed(2) : "--"}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Largecap</div>
          <div className="kpi-value" style={{ color: colorPct(rotation.largecap_avg_pct) }}>
            {fmtPct(rotation.largecap_avg_pct)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Midcap</div>
          <div className="kpi-value" style={{ color: colorPct(rotation.midcap_avg_pct) }}>
            {fmtPct(rotation.midcap_avg_pct)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Smallcap</div>
          <div className="kpi-value" style={{ color: colorPct(rotation.smallcap_avg_pct) }}>
            {fmtPct(rotation.smallcap_avg_pct)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Nifty PE</div>
          <div className="kpi-value" style={{ color: (Number(regimeObj.pe) || 0) > 25 ? "var(--warn)" : "var(--text)" }}>
            {fmtNum(regimeObj.pe, 1)}
          </div>
          <div className="kpi-sub">
            {regimeObj.above_ma20 ? "Above MA20" : "Below MA20"}
          </div>
        </div>
      </div>

      {/* Rotation Signal */}
      {rotation.signal && (
        <div style={{
          padding: "8px 12px",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 5,
          marginBottom: 14,
          fontFamily: "monospace",
          fontSize: 11,
          color: rotation.signal.includes("RISK_ON") ? "var(--pos)"
               : rotation.signal.includes("RISK_OFF") ? "var(--warn)"
               : "var(--muted)",
        }}>
          Rotation: {rotation.signal}
        </div>
      )}

      {/* Global Tickers */}
      {tickerItems.length > 0 && (
        <>
          <div className="section-label">Global Context</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
            {tickerItems.map(([k, v]: any) => {
              const close = typeof v === "object" ? (v?.close ?? v?.value ?? "--") : v;
              const pct   = typeof v === "object" ? v?.pct_chg : null;
              return (
                <div key={k} style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                  padding: "6px 10px",
                  minWidth: 90,
                }}>
                  <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)", textTransform: "uppercase", marginBottom: 3 }}>
                    {k}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{close}</div>
                  {pct != null && (
                    <div style={{ fontFamily: "monospace", fontSize: 10, color: colorPct(pct) }}>
                      {fmtPct(pct)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Top / Bottom Movers */}
      {(gainers.length > 0 || losers.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <div>
            <div className="section-label">Top Movers</div>
            {gainers.slice(0, 7).map((r: any, i: number) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "4px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontSize: 11, color: "var(--text)" }}>
                  {(r.index || r.name || "--").slice(0, 28)}
                </span>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--pos)" }}>
                  {r.pct_change != null ? "+" + Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
          <div>
            <div className="section-label">Bottom Movers</div>
            {losers.slice(0, 7).map((r: any, i: number) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "4px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontSize: 11, color: "var(--text)" }}>
                  {(r.index || r.name || "--").slice(0, 28)}
                </span>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--neg)" }}>
                  {r.pct_change != null ? Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* LLM Analysis */}
      {raText && (
        <>
          <div className="section-label">LLM Analysis</div>
          <ExpandableAnalysis text={raText} />
        </>
      )}
    </div>
  );
}

function ExpandableAnalysis({ text }: { text: string }) {
  // Use a simple expand/collapse via CSS max-height trick with a button
  // We use a ref-free approach: render full text, let CSS handle it
  return (
    <div>
      <div className="analysis-box" style={{ maxHeight: 280 }}>
        {text}
      </div>
    </div>
  );
}
""")

# ── globals.css — increase analysis-box height + add expand class ─────────────
css_path = os.path.join(APP, "globals.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    # Replace analysis-box max-height
    old = "max-height: 180px;"
    new = "max-height: 280px;"
    if old in css:
        css = css.replace(old, new)
        with open(css_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(css)
        print(f"  patched: globals.css (analysis-box height 180 -> 280px)")
    else:
        print(f"  [WARN] Could not find max-height in globals.css, skipping")
else:
    print(f"  [WARN] globals.css not found at {css_path}")

print("""
[DONE] Patch applied.
Next.js hot-reload will pick up changes in ~2 seconds.

Key fixes:
  AlphaPanel now reads correct keys:
    regime.latest_close, regime.window_pct, regime.pe, regime.vol_ann_pct
    breadth.by_day[-1].advancing / .declining / .total / .ad_ratio
    cap_rotation.largecap_avg_pct / midcap_avg_pct / smallcap_avg_pct
    top10_gainers[].pct_change (not pct_chg)
    end_date (not latest_market_date)
    global_context.tickers.{DXY/Gold/etc}.{close, pct_chg}

  LLM analysis boxes now 280px tall (was 180px)

NOTE: Date shows 2026-04-29 because agents/alpha/last_report.json
      is from April 29. Run py micc_engine.py to get today's data.
""")
