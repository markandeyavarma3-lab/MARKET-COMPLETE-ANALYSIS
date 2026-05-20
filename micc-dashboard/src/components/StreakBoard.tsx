export default function StreakBoard({ data }: { data: any }) {
  const rows  = data?.streak || [];
  const stats = data?.stats  || {};
  const maxS  = Math.max(...rows.map((r: any) => Number(r.streak_days) || 0), 1);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Streak Leaderboard <span className="card-accent">-- signals_history (30d)</span>
        </span>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {(Number(stats.total_rows) || 0).toLocaleString()} rows
          </span>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {stats.unique_symbols || 0} symbols
          </span>
          <span className="pill pill-neut" style={{ fontSize: 9 }}>
            {stats.unique_dates || 0} dates
          </span>
          {stats.latest_date && (
            <span className="pill pill-neut" style={{ fontSize: 9 }}>
              latest: {stats.latest_date}
            </span>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: 12, padding: 16 }}>
          No streak data found in last 30 days. Run py micc_engine.py to populate signals_history.
          <br />
          <span style={{ fontSize: 11, marginTop: 6, display: "block" }}>
            DB has {(Number(stats.total_rows) || 0).toLocaleString()} total rows
            across {stats.unique_dates || 0} dates --
            but none within last 30 days. Run: py backfill_signals_history.py
          </span>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>Appearances (30d)</th>
                <th style={{ minWidth: 160 }}>Consistency Bar</th>
                <th>Avg Score</th>
                <th>Last Seen</th>
                <th>Tags</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any, i: number) => {
                const days   = Number(r.streak_days) || 0;
                const pct    = (days / maxS) * 100;
                const aScore = Number(r.avg_score) || 0;
                const rank   = i === 0 ? "#1" : i === 1 ? "#2" : i === 2 ? "#3" : String(i + 1);
                // Parse tags - GROUP_CONCAT gives comma-separated, may have duplicates
                const rawTags = (r.all_tags || "").toString().split(",")
                  .map((t: string) => t.trim())
                  .filter(Boolean);
                const uniqueTags = [...new Set(rawTags)].slice(0, 4);
                return (
                  <tr key={r.symbol}>
                    <td style={{ color: "var(--muted)", fontWeight: i < 3 ? 700 : 400 }}>{rank}</td>
                    <td style={{ fontWeight: 700, fontSize: 12 }}>{r.symbol}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700, color: "var(--orange)" }}>
                      {days}d
                    </td>
                    <td>
                      <div style={{ height: 6, background: "var(--border2)", borderRadius: 3, overflow: "hidden" }}>
                        <div style={{ width: pct + "%", height: "100%", background: "var(--pos)", borderRadius: 3 }} />
                      </div>
                      <div style={{ fontSize: 9, color: "var(--muted)", marginTop: 2 }}>
                        {Math.round(pct)}% of max
                      </div>
                    </td>
                    <td style={{
                      fontFamily: "monospace",
                      color: aScore >= 7 ? "var(--pos)" : aScore >= 4 ? "var(--accent)" : "var(--muted)"
                    }}>
                      {aScore.toFixed(1)}
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 10 }}>{r.last_seen}</td>
                    <td>
                      <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                        {uniqueTags.map((t: string, j: number) => (
                          <span key={j} style={{
                            background: "var(--accent)",
                            color: "#000",
                            borderRadius: 3,
                            padding: "1px 4px",
                            fontFamily: "monospace",
                            fontSize: 8,
                            fontWeight: 700,
                            opacity: 0.8,
                          }}>
                            {t.toUpperCase().slice(0, 5)}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
