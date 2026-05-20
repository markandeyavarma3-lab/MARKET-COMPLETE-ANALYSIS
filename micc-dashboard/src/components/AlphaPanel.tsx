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
