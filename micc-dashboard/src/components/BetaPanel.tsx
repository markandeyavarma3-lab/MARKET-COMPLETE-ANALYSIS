import { fmtPct, colorPct } from "@/lib/utils";
import ScoreBar from "@/components/ScoreBar";

const TAG_COLORS: Record<string, string> = {
  momentum:    "var(--accent)",
  delivery:    "var(--purple)",
  breakout:    "var(--warn)",
  breakouts:   "var(--warn)",
  consistency: "var(--cyan)",
  composite:   "var(--pos)",
};

export default function BetaPanel({ data }: { data: any }) {
  if (!data || data._error) return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Beta -- Stock Screener</span>
      </div>
      <div style={{ color: "var(--neg)", fontFamily: "monospace", fontSize: 12, padding: 8 }}>
        {data?._error || "No beta report found."}
      </div>
    </div>
  );

  const screens   = data.screens || {};
  const composite = screens.composite || [];
  const synth     = data.synthesis || {};
  const regime    = data.regime || data.regime_used || "--";
  const earns     = data.earnings_accel || [];
  const sects     = data.sector_rotation || [];

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Beta <span className="card-accent">-- 5-Screen Screener</span>
        </span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>REGIME: {regime}</span>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {data.start_date} to {data.end_date}
          </span>
        </div>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(95px, 1fr))" }}>
        <div className="kpi">
          <div className="kpi-label">Symbols</div>
          <div className="kpi-value">{data.total_symbols ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Picks</div>
          <div className="kpi-value" style={{ color: "var(--pos)" }}>{composite.length}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Profitable</div>
          <div className="kpi-value" style={{ color: "var(--pos)" }}>{synth.profitable_count ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">In Loss</div>
          <div className="kpi-value" style={{ color: "var(--neg)" }}>{synth.loss_count ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Streak</div>
          <div className="kpi-value" style={{ color: "var(--orange)" }}>
            {synth.streak_count ?? synth.streak_stocks ?? 0}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">EPS Beat</div>
          <div className="kpi-value" style={{ color: "var(--purple)" }}>{synth.eps_count ?? 0}</div>
        </div>
      </div>

      <div className="section-label">Composite Picks</div>
      <div style={{ overflowX: "auto", marginBottom: 14 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Score</th>
              <th>Chg%</th>
              <th>Deliv%</th>
              <th>Screens</th>
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {composite.slice(0, 20).map((r: any, i: number) => {
              const tags = (r.screens || r.screen_tags || "")
                .toString()
                .split(",")
                .map((t: string) => t.trim())
                .filter(Boolean);
              const streak = Number(r.streak) || 0;
              const pct = r.pct_chg != null ? Number(r.pct_chg) : null;
              return (
                <tr key={i}>
                  <td style={{ fontWeight: 700 }}>{r.symbol}</td>
                  <td style={{ minWidth: 110 }}>
                    <ScoreBar score={Number(r.score) || 0} max={10} />
                  </td>
                  <td style={{ color: colorPct(pct) }}>
                    {pct != null ? (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%" : "--"}
                  </td>
                  <td style={{ color: "var(--muted)" }}>
                    {r.avg_deliv_pct != null ? Number(r.avg_deliv_pct).toFixed(1) + "%" : "--"}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                      {tags.map((t: string, j: number) => {
                        const c = TAG_COLORS[t.toLowerCase()] || "var(--muted)";
                        return (
                          <span key={j} style={{
                            background: c,
                            color: "#000",
                            borderRadius: 3,
                            padding: "1px 5px",
                            fontFamily: "monospace",
                            fontSize: 9,
                            fontWeight: 700,
                            opacity: 0.85,
                          }}>
                            {t.toUpperCase().slice(0, 4)}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>
                    {streak > 0 && (
                      <span style={{ color: "var(--orange)" }}>{streak}d</span>
                    )}
                    {r.earnings_flag == 1 && (
                      <span style={{ color: "var(--purple)", marginLeft: streak > 0 ? 6 : 0 }}>EPS</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {sects.length > 0 && (
        <>
          <div className="section-label">Sector Rotation</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
            {sects.slice(0, 12).map((s: any, i: number) => (
              <div key={i} style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 5,
                padding: "5px 10px",
              }}>
                <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)" }}>
                  {s.sector || s.name}
                </div>
                <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 600, color: colorPct(s.pct || s.avg_pct) }}>
                  {fmtPct(s.pct || s.avg_pct)}
                </div>
                <div style={{ fontSize: 10, color: "var(--muted)" }}>{s.count} stocks</div>
              </div>
            ))}
          </div>
        </>
      )}

      {earns.length > 0 && (
        <>
          <div className="section-label">Earnings Acceleration</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {earns.slice(0, 12).map((e: any, i: number) => (
              <span key={i} className="pill" style={{
                background: "rgba(188,140,255,.15)",
                color: "var(--purple)",
                border: "1px solid rgba(188,140,255,.3)",
                fontSize: 10,
              }}>
                {e.symbol}{e.eps_accel != null ? " +" + Number(e.eps_accel).toFixed(0) + "%" : ""}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
