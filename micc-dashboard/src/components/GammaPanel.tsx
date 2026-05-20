import { fmtCr, colorCr } from "@/lib/utils";

export default function GammaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Gamma -- FII/DII Flows</span>
      </div>
      <div style={{ color: "var(--neg)", fontFamily: "monospace", fontSize: 12, padding: 8 }}>
        {data?._error || "No gamma report found."}
      </div>
    </div>
  );

  const eqFlow   = data.eq_flow || {};
  const metrics  = eqFlow.metrics || {};
  const flowTbl  = eqFlow.flow_table || [];
  const score    = Number(data.flow_score ?? 0) || 0;
  const regime   = data.regime || "--";
  const barPct   = Math.min(score, 100);
  const sColor   = score >= 60 ? "var(--pos)" : score >= 40 ? "var(--warn)" : "var(--neg)";
  const sLabel   = score >= 60 ? "BULLISH" : score >= 40 ? "NEUTRAL" : "BEARISH";
  const fiiToday = Number(flowTbl[0]?.fii_net_cr ?? flowTbl[0]?.fii_net ?? 0) || 0;
  const diiToday = Number(flowTbl[0]?.dii_net_cr ?? flowTbl[0]?.dii_net ?? 0) || 0;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Gamma <span className="card-accent">-- FII/DII Intelligence</span>
        </span>
        <span className="pill pill-neut" style={{ fontSize: 9 }}>REGIME: {regime}</span>
      </div>

      {/* Flow Score - pure div, no SVG */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        marginBottom: 14,
        padding: "12px 14px",
        background: "var(--surface)",
        borderRadius: 6,
        border: "1px solid var(--border)",
      }}>
        <div style={{ minWidth: 80 }}>
          <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)", marginBottom: 4, letterSpacing: ".06em" }}>
            FLOW SCORE
          </div>
          <div style={{ fontSize: 36, fontWeight: 700, color: sColor, lineHeight: 1 }}>
            {score.toFixed(0)}
          </div>
          <div style={{ fontSize: 10, color: sColor, fontWeight: 600, marginTop: 4 }}>
            {sLabel}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ height: 12, background: "var(--border2)", borderRadius: 6, overflow: "hidden", marginBottom: 4 }}>
            <div style={{ width: barPct + "%", height: "100%", background: sColor, borderRadius: 6 }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 9, color: "var(--neg)" }}>0 BEARISH</span>
            <span style={{ fontSize: 9, color: "var(--warn)" }}>50 NEUTRAL</span>
            <span style={{ fontSize: 9, color: "var(--pos)" }}>100 BULLISH</span>
          </div>
          <div style={{ display: "flex", gap: 20, marginTop: 10 }}>
            <div>
              <div style={{ fontSize: 9, color: "var(--muted)", fontFamily: "monospace" }}>TODAY FII</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: fiiToday >= 0 ? "var(--pos)" : "var(--neg)" }}>
                {fmtCr(fiiToday)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 9, color: "var(--muted)", fontFamily: "monospace" }}>TODAY DII</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: diiToday >= 0 ? "var(--accent)" : "var(--warn)" }}>
                {fmtCr(diiToday)}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))" }}>
        <div className="kpi">
          <div className="kpi-label">FII Cumul.</div>
          <div className="kpi-value" style={{ fontSize: 13, color: colorCr(metrics.fii_cumulative_cr) }}>
            {fmtCr(metrics.fii_cumulative_cr)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">DII Cumul.</div>
          <div className="kpi-value" style={{ fontSize: 13, color: colorCr(metrics.dii_cumulative_cr) }}>
            {fmtCr(metrics.dii_cumulative_cr)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">FII Trend</div>
          <div className="kpi-value" style={{ fontSize: 12 }}>{metrics.fii_trend || "--"}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">FII Buy Days</div>
          <div className="kpi-value" style={{ color: "var(--pos)" }}>{metrics.fii_buy_days ?? 0}</div>
          <div className="kpi-sub">Consec: {metrics.fii_consec_buy_days ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">FII Sell Days</div>
          <div className="kpi-value" style={{ color: "var(--neg)" }}>{metrics.fii_sell_days ?? 0}</div>
          <div className="kpi-sub">Consec: {metrics.fii_consec_sell_days ?? 0}</div>
        </div>
      </div>

      {flowTbl.length > 1 && (
        <>
          <div className="section-label">Recent Flows</div>
          <div style={{ overflowX: "auto", marginBottom: 14 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>FII Net</th>
                  <th>DII Net</th>
                  <th>Combined</th>
                </tr>
              </thead>
              <tbody>
                {flowTbl.slice(0, 10).map((r: any, i: number) => {
                  const f = Number(r.fii_net_cr ?? r.fii_net ?? 0) || 0;
                  const d = Number(r.dii_net_cr ?? r.dii_net ?? 0) || 0;
                  const n = f + d;
                  return (
                    <tr key={i}>
                      <td style={{ color: "var(--muted)" }}>{r.date || r.trade_date}</td>
                      <td style={{ color: f >= 0 ? "var(--pos)" : "var(--neg)" }}>{fmtCr(f)}</td>
                      <td style={{ color: d >= 0 ? "var(--accent)" : "var(--warn)" }}>{fmtCr(d)}</td>
                      <td style={{ color: n >= 0 ? "var(--pos)" : "var(--neg)", fontWeight: 600 }}>
                        {fmtCr(n)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {data.analysis && (
        <>
          <div className="section-label">LLM Analysis</div>
          <div className="analysis-box">{data.analysis}</div>
        </>
      )}
    </div>
  );
}
