import { fmtNum } from "@/lib/utils";

function RiskBar({ score }: { score: number }) {
  const s     = Math.min(Math.max(Number(score) || 0, 0), 100);
  const color = s >= 70 ? "var(--neg)" : s >= 40 ? "var(--warn)" : "var(--pos)";
  const label = s >= 70 ? "HIGH RISK" : s >= 40 ? "MODERATE" : "LOW RISK";
  return (
    <div style={{ padding: "12px 14px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)", letterSpacing: ".08em" }}>
          RISK SCORE
        </span>
        <span style={{ fontFamily: "monospace", fontSize: 10, color: color, fontWeight: 700 }}>{label}</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 40, fontWeight: 700, color: color, lineHeight: 1 }}>{s}</span>
        <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)" }}>/100</span>
      </div>
      <div style={{ height: 8, background: "var(--border2)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: s + "%", height: "100%", background: color, borderRadius: 4 }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3 }}>
        <span style={{ fontSize: 9, color: "var(--pos)" }}>LOW 0</span>
        <span style={{ fontSize: 9, color: "var(--warn)" }}>40</span>
        <span style={{ fontSize: 9, color: "var(--neg)" }}>70 HIGH</span>
      </div>
    </div>
  );
}

export default function DeltaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Delta -- Risk Engine</span>
      </div>
      <div style={{ color: "var(--neg)", fontFamily: "monospace", fontSize: 12, padding: 8 }}>
        {data?._error || "No delta report found."}
      </div>
    </div>
  );

  const rFlags = data.risk_flags  || [];
  const gFlags = data.green_flags || [];
  const ins    = data.insider_activity || [];
  const corps  = data.corporate_actions || [];
  const regime = data.regime || "--";

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Delta <span className="card-accent">-- Risk Engine and Insider Alerts</span>
        </span>
        <span className="pill pill-neut" style={{ fontSize: 9 }}>REGIME: {regime}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 14, marginBottom: 14 }}>
        <RiskBar score={Number(data.risk_score) || 0} />
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", alignContent: "start", margin: 0 }}>
          <div className="kpi">
            <div className="kpi-label">VIX</div>
            <div className="kpi-value" style={{ color: (Number(data.vix) || 0) > 20 ? "var(--neg)" : "var(--pos)" }}>
              {fmtNum(data.vix, 2)}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-label">High PE Count</div>
            <div className="kpi-value" style={{ color: (Number(data.high_pe_count) || 0) > 20 ? "var(--warn)" : "var(--text)" }}>
              {data.high_pe_count ?? 0}
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Quality Universe</div>
            <div className="kpi-value" style={{ color: "var(--pos)" }}>{data.quality_count ?? 0}</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Corp. Actions</div>
            <div className="kpi-value">{corps.length}</div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
        <div>
          <div className="section-label">Risk Flags</div>
          {rFlags.length === 0
            ? <div style={{ fontSize: 11, color: "var(--muted)" }}>None detected</div>
            : rFlags.map((f: string, i: number) => (
              <div key={i} style={{ padding: "3px 0", color: "var(--neg)", fontSize: 12 }}>
                [WARN] {f}
              </div>
            ))
          }
        </div>
        <div>
          <div className="section-label">Green Flags</div>
          {gFlags.length === 0
            ? <div style={{ fontSize: 11, color: "var(--muted)" }}>None</div>
            : gFlags.map((f: string, i: number) => (
              <div key={i} style={{ padding: "3px 0", color: "var(--pos)", fontSize: 12 }}>
                [OK] {f}
              </div>
            ))
          }
        </div>
      </div>

      {ins.length > 0 && (
        <>
          <div className="section-label">Insider Activity</div>
          <div style={{ overflowX: "auto", marginBottom: 14 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Qty</th>
                  <th>Value (Cr)</th>
                </tr>
              </thead>
              <tbody>
                {ins.slice(0, 10).map((r: any, i: number) => {
                  const isBuy = (r.transaction_type || "").toLowerCase().includes("buy");
                  return (
                    <tr key={i}>
                      <td style={{ color: "var(--muted)" }}>{r.filing_date}</td>
                      <td style={{ fontWeight: 700 }}>{r.symbol}</td>
                      <td style={{
                        color: "var(--muted)",
                        maxWidth: 110,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}>
                        {r.name}
                      </td>
                      <td>
                        <span className={"pill " + (isBuy ? "pill-bull" : "pill-bear")} style={{ fontSize: 9 }}>
                          {r.transaction_type}
                        </span>
                      </td>
                      <td style={{ color: "var(--muted)" }}>
                        {(r.quantity || 0).toLocaleString()}
                      </td>
                      <td style={{ color: isBuy ? "var(--pos)" : "var(--neg)" }}>
                        {r.value != null ? "Rs." + Number(r.value).toFixed(1) : "--"}
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
