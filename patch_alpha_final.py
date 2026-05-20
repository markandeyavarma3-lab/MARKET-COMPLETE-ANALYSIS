"""
MICC Dashboard - Alpha Panel Final Fix
Run from DATA-ANALYSIS:  py patch_alpha_final.py

Based on ACTUAL keys from agents/alpha/last_report.json:
  regime_metrics.nifty50_close, .return_1d_pct, .volatility_20d_annualized_pct, .pe, .pb
  breadth_analytics.advancing, .declining, .total_indices, .advance_decline_ratio, .breadth_pct_advancing
  cap_rotation.largecap_avg_change, .midcap_avg_change, .smallcap_avg_change, .rotation_signal
  regime_analysis = string
  latest_market_date = "YYYY-MM-DD"
  data_quality = dict
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))

def find_comp():
    for sub in ["micc-dashboard/src/components", "micc-dashboard/components"]:
        p = os.path.join(BASE, sub)
        if os.path.isdir(p):
            return p
    return None

COMP = find_comp()
if not COMP:
    print("[ERROR] micc-dashboard not found. Run: py build_dashboard.py")
    sys.exit(1)

def w(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.lstrip("\n"))
    print(f"  wrote: {os.path.relpath(path, BASE)}")

w(os.path.join(COMP, "AlphaPanel.tsx"), """
import { fmtNum, fmtPct, colorPct, regimeCls } from "@/lib/utils";

export default function AlphaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header"><span className="card-title">Alpha -- Macro and Regime</span></div>
      <div style={{ color:"var(--neg)", fontFamily:"monospace", fontSize:12, padding:8 }}>
        {data?._error || "No alpha report. Run: py micc_engine.py"}
      </div>
    </div>
  );

  // EXACT keys from agents/alpha/last_report.json
  const rm  = data.regime_metrics   || {};  // nifty50_close, return_1d_pct, return_5d_pct, return_20d_pct,
                                             // ma20, ma50, above_ma20, above_ma50,
                                             // volatility_20d_annualized_pct, pe, pb,
                                             // up_days_last5, down_days_last5, volume_ratio_5d_vs_20d
  const ba  = data.breadth_analytics || {}; // advancing, declining, unchanged, total_indices,
                                             // advance_decline_ratio, breadth_pct_advancing,
                                             // top3_performers, bottom3_performers, avg_pe_all_indices
  const cr  = data.cap_rotation      || {}; // largecap_avg_change, midcap_avg_change,
                                             // smallcap_avg_change, rotation_signal
  const date   = data.latest_market_date || (data.timestamp || "").slice(0,10) || "--";
  const llm    = typeof data.regime_analysis === "string" ? data.regime_analysis : "";

  // Derive regime label from LLM text (starts with "REGIME: X CONFIDENCE: Y")
  const regimeMatch = llm.match(/REGIME:\\s*([A-Z_]+)/);
  const confMatch   = llm.match(/CONFIDENCE:\\s*([A-Z])/);
  const regime      = regimeMatch ? regimeMatch[1] : "";
  const confidence  = confMatch   ? confMatch[1]   : "";
  const rcls        = regimeCls(regime);

  const top3  = ba.top3_performers    || [];
  const bot3  = ba.bottom3_performers || [];

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
          <div className="kpi-sub">{(cr.rotation_signal || "--").slice(0, 20)}</div>
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

      {(top3.length > 0 || bot3.length > 0) && (
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:14 }}>
          <div>
            <div className="section-label">Top Indices</div>
            {top3.slice(0,6).map((r:any,i:number) => (
              <div key={i} style={{ display:"flex", justifyContent:"space-between", padding:"4px 0", borderBottom:"1px solid var(--border)" }}>
                <span style={{ fontSize:11 }}>{(r.index||r.name||r.index_name||"--").slice(0,26)}</span>
                <span style={{ fontFamily:"monospace", fontSize:11, color:"var(--pos)" }}>
                  {r.pct_change != null ? "+" + Number(r.pct_change).toFixed(2) + "%"
                   : r.change_pct != null ? "+" + Number(r.change_pct).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
          <div>
            <div className="section-label">Bottom Indices</div>
            {bot3.slice(0,6).map((r:any,i:number) => (
              <div key={i} style={{ display:"flex", justifyContent:"space-between", padding:"4px 0", borderBottom:"1px solid var(--border)" }}>
                <span style={{ fontSize:11 }}>{(r.index||r.name||r.index_name||"--").slice(0,26)}</span>
                <span style={{ fontFamily:"monospace", fontSize:11, color:"var(--neg)" }}>
                  {r.pct_change != null ? Number(r.pct_change).toFixed(2) + "%"
                   : r.change_pct != null ? Number(r.change_pct).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {llm && (
        <>
          <div className="section-label">LLM Regime Analysis</div>
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

print("""
Done. AlphaPanel now uses exact keys from agents/alpha/last_report.json:
  regime_metrics.nifty50_close       -> Nifty 50 value
  regime_metrics.return_1d_pct       -> 1d change
  regime_metrics.volatility_20d_annualized_pct -> volatility
  regime_metrics.pe / .pb            -> valuation
  regime_metrics.above_ma20/50       -> MA positioning
  breadth_analytics.advancing        -> advances count
  breadth_analytics.declining        -> declines count
  breadth_analytics.advance_decline_ratio -> A/D ratio
  breadth_analytics.breadth_pct_advancing -> breadth %
  cap_rotation.largecap_avg_change   -> largecap %
  cap_rotation.midcap_avg_change     -> midcap %
  cap_rotation.smallcap_avg_change   -> smallcap %
  cap_rotation.rotation_signal       -> signal banner
  regime_analysis (string)           -> LLM text, regime parsed from it
  latest_market_date                 -> header date
""")
