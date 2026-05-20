"use client";
import { useState, useEffect, useCallback } from "react";
import DurationBar from "./DurationBar";

interface StreakRow {
  symbol: string;
  streak_days: number;
  last_seen: string;
  first_seen: string;
  avg_score: number;
  max_score: number;
  avg_pct: number;
  max_pct: number;
  avg_deliv: number;
  eps_days: number;
  all_tags: string;
  latest_regime: string;
}

const SORT_OPTIONS = [
  { value: "streak", label: "Streak Days" },
  { value: "score",  label: "Avg Score"   },
  { value: "pct",    label: "Avg Return"  },
  { value: "deliv",  label: "Avg Delivery"},
];

const SCREEN_FILTERS = [
  { value: "",            label: "All Screens" },
  { value: "momentum",    label: "Momentum"    },
  { value: "breakout",    label: "Breakout"    },
  { value: "delivery",    label: "Delivery"    },
  { value: "consistency", label: "Consistency" },
  { value: "composite",   label: "Composite"   },
];

function colorScore(s: number) {
  if (s >= 7) return "var(--pos)";
  if (s >= 4) return "var(--accent)";
  return "var(--muted)";
}

export default function StreakBoardExtended() {
  const [days,    setDays]    = useState(30);
  const [sortBy,  setSortBy]  = useState("streak");
  const [screen,  setScreen]  = useState("");
  const [minDays, setMinDays] = useState(2);
  const [data,    setData]    = useState<{ rows: StreakRow[]; stats: any; days: number } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (d: number, s: string, sc: string, m: number) => {
    setLoading(true);
    try {
      const url = "/api/streak-extended?days=" + d + "&sort=" + s + "&screen=" + sc + "&min=" + m;
      const r = await fetch(url, { cache: "no-store" });
      setData(await r.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days, sortBy, screen, minDays); }, []);

  const refresh = () => load(days, sortBy, screen, minDays);
  const stats = data?.stats || {};
  const rows  = data?.rows  || [];
  const maxS  = Math.max(...rows.map(r => r.streak_days), 1);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          Streak Leaderboard <span className="card-accent">-- signals_history</span>
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
            <span className="pill pill-neut" style={{ fontSize: 9 }}>latest: {stats.latest_date}</span>
          )}
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 14, alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>LOOKBACK</span>
          <DurationBar value={days} onChange={(d) => { setDays(d); load(d, sortBy, screen, minDays); }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>SORT BY</span>
          <div style={{ display: "flex", gap: 4 }}>
            {SORT_OPTIONS.map(o => (
              <button key={o.value} onClick={() => { setSortBy(o.value); load(days, o.value, screen, minDays); }}
                style={{
                  padding: "3px 9px", borderRadius: 4, border: "1px solid",
                  borderColor: sortBy === o.value ? "var(--accent)" : "var(--border2)",
                  background: sortBy === o.value ? "rgba(88,166,255,.15)" : "var(--surface)",
                  color: sortBy === o.value ? "var(--accent)" : "var(--muted)",
                  fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                }}>
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>SCREEN FILTER</span>
          <div style={{ display: "flex", gap: 4 }}>
            {SCREEN_FILTERS.map(o => (
              <button key={o.value} onClick={() => { setScreen(o.value); load(days, sortBy, o.value, minDays); }}
                style={{
                  padding: "3px 9px", borderRadius: 4, border: "1px solid",
                  borderColor: screen === o.value ? "var(--purple)" : "var(--border2)",
                  background: screen === o.value ? "rgba(188,140,255,.15)" : "var(--surface)",
                  color: screen === o.value ? "var(--purple)" : "var(--muted)",
                  fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                }}>
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontFamily: "monospace", fontSize: 9, color: "var(--muted)" }}>MIN DAYS</span>
          <div style={{ display: "flex", gap: 4 }}>
            {[2, 3, 4, 5].map(m => (
              <button key={m} onClick={() => { setMinDays(m); load(days, sortBy, screen, m); }}
                style={{
                  padding: "3px 9px", borderRadius: 4, border: "1px solid",
                  borderColor: minDays === m ? "var(--warn)" : "var(--border2)",
                  background: minDays === m ? "rgba(210,153,34,.15)" : "var(--surface)",
                  color: minDays === m ? "var(--warn)" : "var(--muted)",
                  fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                }}>
                {m}+
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 30 }}>
          <div className="spinner" />
        </div>
      ) : rows.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: 12, padding: 12 }}>
          No data matching filters. Try reducing Min Days or changing screen filter.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>Streak</th>
                <th style={{ minWidth: 120 }}>Consistency</th>
                <th>Avg Score</th>
                <th>Max Score</th>
                <th>Avg Ret%</th>
                <th>Max Ret%</th>
                <th>Avg Deliv%</th>
                <th>EPS Days</th>
                <th>Screens</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const pct  = (r.streak_days / maxS) * 100;
                const rank = i === 0 ? "#1" : i === 1 ? "#2" : i === 2 ? "#3" : String(i + 1);
                const tags = (r.all_tags || "").split(",").map((t: string) => t.trim()).filter(Boolean);
                const uniqueTags = [...new Set(tags)].slice(0, 5);
                const tagColors: Record<string, string> = {
                  momentum: "var(--accent)", breakout: "var(--warn)", breakouts: "var(--warn)",
                  delivery: "var(--purple)", consistency: "var(--cyan)", composite: "var(--pos)",
                };
                return (
                  <tr key={r.symbol}>
                    <td style={{ color: "var(--muted)", fontWeight: i < 3 ? 700 : 400 }}>{rank}</td>
                    <td style={{ fontWeight: 700, fontSize: 12, color: "var(--text)" }}>{r.symbol}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700, color: "var(--orange)" }}>
                      {r.streak_days}d
                    </td>
                    <td>
                      <div style={{ height: 6, background: "var(--border2)", borderRadius: 3, overflow: "hidden", minWidth: 100 }}>
                        <div style={{ width: pct + "%", height: "100%", background: "var(--pos)", borderRadius: 3 }} />
                      </div>
                      <div style={{ fontSize: 9, color: "var(--muted)", marginTop: 2 }}>
                        {r.first_seen} to {r.last_seen}
                      </div>
                    </td>
                    <td style={{ fontFamily: "monospace", color: colorScore(r.avg_score) }}>
                      {(r.avg_score || 0).toFixed(1)}
                    </td>
                    <td style={{ fontFamily: "monospace", color: colorScore(r.max_score) }}>
                      {(r.max_score || 0).toFixed(1)}
                    </td>
                    <td style={{ fontFamily: "monospace", color: (r.avg_pct || 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>
                      {r.avg_pct != null ? ((r.avg_pct >= 0 ? "+" : "") + r.avg_pct.toFixed(2) + "%") : "--"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: "var(--pos)" }}>
                      {r.max_pct != null ? "+" + r.max_pct.toFixed(2) + "%" : "--"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: (r.avg_deliv || 0) > 50 ? "var(--pos)" : "var(--muted)" }}>
                      {r.avg_deliv != null ? r.avg_deliv.toFixed(1) + "%" : "--"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: (r.eps_days || 0) > 0 ? "var(--purple)" : "var(--muted)" }}>
                      {r.eps_days || 0}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                        {uniqueTags.map((t, j) => {
                          const c = tagColors[t.toLowerCase()] || "var(--muted)";
                          return (
                            <span key={j} style={{
                              background: c, color: "#000", borderRadius: 3,
                              padding: "1px 4px", fontFamily: "monospace",
                              fontSize: 8, fontWeight: 700, opacity: 0.85,
                            }}>
                              {t.toUpperCase().slice(0, 5)}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 10 }}>{r.last_seen}</td>
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
