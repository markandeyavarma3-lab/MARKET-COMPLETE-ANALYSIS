"use client";

import { useEffect, useState } from "react";

interface Pat {
  symbol: string; anchor_mm_dd: string; window_days: number;
  direction: string; accuracy: number; mean_ret: number; score: number;
  n_obs: number; degradation: number; recent_mean: number;
}

export default function TodayPatternsWidget({
  minAccuracy = 65,
  minScore    = 5,
  limit       = 15,
  compact     = false,
}: {
  minAccuracy?: number;
  minScore?:    number;
  limit?:       number;
  compact?:     boolean;
}) {
  const [pats,   setPats]   = useState<Pat[]>([]);
  const [date,   setDate]   = useState("");
  const [total,  setTotal]  = useState(0);
  const [loading,setLoading]= useState(true);
  const [dir,    setDir]    = useState<""|"UP"|"DOWN">("");

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({
      min_accuracy: String(minAccuracy),
      min_score:    String(minScore),
      limit:        String(limit),
    });
    if (dir) params.set("direction", dir);

    fetch("/api/patterns-v3/today?" + params)
      .then(r => r.json())
      .then(d => {
        setPats(d.rows || []);
        setDate(d.date || "");
        setTotal(d.total_today || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [dir, minAccuracy, minScore, limit]);

  const up   = pats.filter(p => p.direction === "UP").length;
  const down = pats.filter(p => p.direction === "DOWN").length;

  if (loading) return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155",
      borderRadius: 12, padding: "16px 20px",
    }}>
      <div style={{ color: "#64748b", fontSize: 12 }}>Loading today's patterns...</div>
    </div>
  );

  return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155",
      borderRadius: 12, overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid #334155",
        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
      }}>
        <span style={{ fontSize: 14 }}>🔬</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8",
          letterSpacing: 0.8, textTransform: "uppercase" }}>
          Seasonal Patterns Today
        </span>
        {date && (
          <span style={{ fontSize: 11, color: "#475569" }}>({date})</span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {total > 0 && (
            <span style={{ fontSize: 10, color: "#475569" }}>{total} total</span>
          )}
          {[["", "All"], ["UP", "UP"], ["DOWN", "DOWN"]].map(([v, l]) => (
            <button key={v} onClick={() => setDir(v as any)} style={{
              fontSize: 10, fontWeight: 700, padding: "2px 8px",
              borderRadius: 4, border: "none", cursor: "pointer",
              background: dir === v ? (v === "UP" ? "#0f2d1f" : v === "DOWN" ? "#2d1515" : "#334155")
                                     : "#0f172a",
              color: dir === v ? (v === "UP" ? "#22c55e" : v === "DOWN" ? "#ef4444" : "#f8fafc")
                                : "#475569",
            }}>{l}</button>
          ))}
        </div>
      </div>

      {/* Summary strip */}
      {!compact && (
        <div style={{
          padding: "8px 16px", background: "#0f172a",
          display: "flex", gap: 16, fontSize: 11,
        }}>
          <span style={{ color: "#22c55e" }}>▲ {up} bullish</span>
          <span style={{ color: "#ef4444" }}>▼ {down} bearish</span>
          <span style={{ color: "#64748b" }}>
            avg score {pats.length ? (pats.reduce((s,p)=>s+p.score,0)/pats.length).toFixed(1) : "—"}
          </span>
        </div>
      )}

      {/* Pattern list */}
      {pats.length === 0 ? (
        <div style={{ padding: "20px 16px", color: "#475569", fontSize: 12, textAlign: "center" }}>
          {total === 0
            ? "No patterns found for today. Stock builder may still be running."
            : "No patterns match current filters. Try lowering thresholds."}
        </div>
      ) : (
        <div style={{ maxHeight: compact ? 200 : 380, overflowY: "auto" }}>
          {pats.map((p, i) => {
            const up = p.direction === "UP";
            const lineClr = up ? "#22c55e" : "#ef4444";
            const fading  = p.degradation < -10;
            const rising  = p.degradation > 10;
            return (
              <a key={i} href={"/patterns-v3?symbol=" + p.symbol}
                style={{ textDecoration: "none", display: "block" }}>
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: compact ? "5px 16px" : "7px 16px",
                  borderBottom: "1px solid #0f172a",
                  transition: "background 0.1s",
                  cursor: "pointer",
                }}>
                  <span style={{
                    fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 3,
                    background: up ? "#0f2d1f" : "#2d1515", color: lineClr,
                    flexShrink: 0,
                  }}>{p.direction}</span>

                  <span style={{
                    fontFamily: "monospace", fontWeight: 700, fontSize: 12,
                    color: "#60a5fa", minWidth: compact ? 90 : 110,
                  }}>{p.symbol}</span>

                  {!compact && (
                    <span style={{ fontSize: 11, color: "#475569", minWidth: 60 }}>
                      {p.anchor_mm_dd}+{p.window_days}d
                    </span>
                  )}

                  <span style={{ fontSize: 12, fontWeight: 700, color: lineClr }}>
                    {p.accuracy.toFixed(0)}%
                  </span>

                  <span style={{ fontSize: 11, color: lineClr }}>
                    {p.mean_ret >= 0 ? "+" : ""}{p.mean_ret.toFixed(2)}%
                  </span>

                  <span style={{ fontSize: 10, color: "#fbbf24", marginLeft: "auto" }}>
                    ★{p.score.toFixed(1)}
                  </span>

                  {!compact && (fading || rising) && (
                    <span style={{ fontSize: 9, color: fading ? "#ef4444" : "#22c55e" }}>
                      {fading ? "↓fading" : "↑rising"}
                    </span>
                  )}
                </div>
              </a>
            );
          })}
        </div>
      )}

      {pats.length > 0 && !compact && (
        <div style={{ padding: "8px 16px", borderTop: "1px solid #334155" }}>
          <a href="/patterns-v3" style={{ fontSize: 11, color: "#3b82f6" }}>
            View all patterns →
          </a>
        </div>
      )}
    </div>
  );
}
