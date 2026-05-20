"use client";
import NavBar from "@/components/NavBar";

import SymbolSearch from "@/components/SymbolSearch";

import { useState, useEffect, useCallback, useRef } from "react";

//  Types 
interface Pattern {
  symbol: string; anchor_mm_dd: string; window_days: number; direction: string;
  n_obs: number; accuracy: number; mean_ret: number; median_ret: number;
  std_ret: number; p10: number; p25: number; p75: number; p90: number;
  best_ret: number; worst_ret: number; score: number; consistency: number;
  edge_ratio: number; t_stat: number; p_value: number;
  early_accuracy: number; recent_accuracy: number; degradation: number;
  recent_mean: number; recent_vs_all: number;
}
interface DetailRow { year: number; ret: number; }
interface Detail extends Pattern {
  best_years: DetailRow[]; worst_years: DetailRow[]; all_returns: DetailRow[];
}

//  Helpers 
const pct  = (v: number | null | undefined, d = 2) =>
  v == null ? "" : `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(d)}%`;
const num  = (v: number | null | undefined, d = 2) =>
  v == null ? "" : Number(v).toFixed(d);
const clr  = (v: number | null | undefined, invert = false) => {
  if (v == null) return "var(--muted)";
  const pos = invert ? v < 0 : v > 0;
  return pos ? "var(--pos)" : v === 0 ? "var(--muted)" : "var(--neg)";
};
const sigClr = (pval: number | null | undefined) => {
  if (pval == null) return "var(--muted)";
  return pval < 0.05 ? "var(--pos)" : pval < 0.10 ? "var(--warn)" : "var(--muted)";
};
const degClr = (deg: number | null | undefined) => {
  if (deg == null) return "var(--muted)";
  return deg > 5 ? "var(--pos)" : deg > 0 ? "#86efac" : deg > -5 ? "var(--warn)" : "var(--neg)";
};
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const monthName = (mm_dd: string) => {
  const m = parseInt(mm_dd.split("-")[0]) - 1;
  return MONTHS[m] || mm_dd;
};

//  Stat chip 
function Chip({ label, value, color, small }: {
  label: string; value: string; color?: string; small?: boolean;
}) {
  return (
    <div style={{
      background: "var(--bg)", borderRadius: 8, padding: small ? "5px 10px" : "8px 14px",
      textAlign: "center", minWidth: small ? 70 : 80,
    }}>
      <div style={{ fontSize: small ? 13 : 15, fontWeight: 800,
        color: color || "var(--text)" }}>{value}</div>
      <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

//  Degradation bar 
function DegBar({ early, recent }: { early: number; recent: number }) {
  const change = recent - early;
  return (
    <div style={{ fontSize: 11, color: "var(--muted)" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 3 }}>
        <span style={{ minWidth: 50 }}>Early</span>
        <div style={{ flex: 1, background: "var(--card)", borderRadius: 4, height: 6 }}>
          <div style={{ width: `${Math.min(early, 100)}%`, height: "100%",
            background: "var(--accent)", borderRadius: 4 }} />
        </div>
        <span style={{ color: "var(--accent)", minWidth: 36 }}>{early.toFixed(0)}%</span>
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ minWidth: 50 }}>Recent</span>
        <div style={{ flex: 1, background: "var(--card)", borderRadius: 4, height: 6 }}>
          <div style={{ width: `${Math.min(recent, 100)}%`, height: "100%",
            background: degClr(change), borderRadius: 4 }} />
        </div>
        <span style={{ color: degClr(change), minWidth: 36 }}>{recent.toFixed(0)}%</span>
      </div>
      <div style={{ marginTop: 4, color: degClr(change), fontWeight: 700 }}>
        {change >= 0 ? "" : ""} {Math.abs(change).toFixed(1)}% {change >= 0 ? "strengthening" : "fading"}
      </div>
    </div>
  );
}

//  Year return chart (SVG bar chart with hover) 
function YearChart({ data, direction }: { data: DetailRow[]; direction: string }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [lockA,   setLockA]   = useState<number | null>(null);
  const [lockB,   setLockB]   = useState<number | null>(null);
  if (!data || data.length === 0) return null;

  const W = 520, H = 140, PAD = 30;
  const vals = data.map(d => d.ret);
  const mn   = Math.min(...vals, 0);
  const mx   = Math.max(...vals, 0);
  const rng  = mx - mn || 1;
  const bw   = Math.max(4, (W - 2 * PAD) / data.length - 2);
  const zero = H - PAD - ((0 - mn) / rng) * (H - 2 * PAD);

  const handleClick = (idx: number) => {
    if (lockA === null) { setLockA(idx); return; }
    if (lockB === null && idx !== lockA) { setLockB(idx); return; }
    setLockA(null); setLockB(null);
  };

  const deltaA = lockA != null ? data[lockA] : null;
  const deltaB = lockB != null ? data[lockB] : null;
  const delta  = deltaA && deltaB ? deltaB.ret - deltaA.ret : null;

  return (
    <div style={{ userSelect: "none" }}>
      <svg width={W} height={H} style={{ overflow: "visible", cursor: "crosshair" }}>
        {/* Zero line */}
        <line x1={PAD} y1={zero} x2={W - PAD} y2={zero}
          stroke="var(--border2)" strokeWidth={1} strokeDasharray="4,3" />

        {data.map((d, i) => {
          const x   = PAD + i * ((W - 2 * PAD) / data.length);
          const bh  = Math.abs((d.ret / rng) * (H - 2 * PAD));
          const y   = d.ret >= 0 ? zero - bh : zero;
          const isA = lockA === i, isB = lockB === i, isH = hovered === i;
          const base = direction === "UP"
            ? (d.ret > 0 ? "var(--pos)" : "var(--neg)")
            : (d.ret < 0 ? "var(--pos)" : "var(--neg)");
          const fill = isA ? "var(--warn)" : isB ? "var(--purple)" : isH ? "var(--accent)" : base;
          return (
            <g key={i}>
              <rect x={x} y={y} width={bw} height={Math.max(bh, 2)}
                fill={fill} opacity={0.85} rx={1}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => handleClick(i)}
                style={{ cursor: "pointer" }}
              />
              {(isH || isA || isB) && (
                <text x={x + bw / 2} y={y - 4} fontSize={9} fill={fill}
                  textAnchor="middle">{d.year}</text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Tooltip */}
      {hovered != null && (
        <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
          <span style={{ fontWeight: 700, color: "var(--text)" }}>{data[hovered]?.year}</span>
          {"  "}
          <span style={{ color: clr(data[hovered]?.ret), fontWeight: 700 }}>
            {pct(data[hovered]?.ret)}
          </span>
        </div>
      )}

      {/* Lock info */}
      {(lockA != null || lockB != null) && (
        <div style={{ fontSize: 11, marginTop: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
          {lockA != null && (
            <span style={{ color: "var(--warn)" }}>A: {data[lockA]?.year} {pct(data[lockA]?.ret)}</span>
          )}
          {lockB != null && (
            <span style={{ color: "var(--purple)" }}>B: {data[lockB]?.year} {pct(data[lockB]?.ret)}</span>
          )}
          {delta != null && (
            <span style={{ color: "var(--pos)", fontWeight: 700 }}> {pct(delta)}</span>
          )}
          <button onClick={() => { setLockA(null); setLockB(null); }}
            style={{ fontSize: 10, color: "var(--muted)", background: "none",
              border: "none", cursor: "pointer" }}> clear</button>
        </div>
      )}
    </div>
  );
}

//  Expanded Pattern Card 
function PatternCard({ p, idx }: { p: Pattern; idx: number }) {
  const [open,   setOpen]   = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(false);
  const isUp = p.direction === "UP";

  const loadDetail = useCallback(async () => {
    if (detail) return;
    setLoading(true);
    try {
      const r = await fetch(
        `/api/patterns-v3/detail?symbol=${p.symbol}&anchor=${p.anchor_mm_dd}`
        + `&window=${p.window_days}&direction=${p.direction}`
      );
      const d = await r.json();
      if (!d.error) setDetail(d);
    } catch {}
    setLoading(false);
  }, [p, detail]);

  const toggle = () => {
    if (!open) loadDetail();
    setOpen(o => !o);
  };

  const dirClr = isUp ? "var(--pos)" : "var(--neg)";
  const sigOk  = p.p_value < 0.05;

  return (
    <div style={{
      background: "var(--card)", border: `1px solid ${open ? dirClr + "55" : "var(--border2)"}`,
      borderRadius: 6, marginBottom: 8,
      transition: "border-color 0.2s",
    }}>
      {/*  Header row  */}
      <div onClick={toggle} style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "12px 16px", cursor: "pointer", flexWrap: "wrap",
      }}>
        <span style={{ fontSize: 12, color: "var(--muted)", minWidth: 28 }}>#{idx + 1}</span>
        <span style={{
          fontFamily: "monospace", fontWeight: 800, fontSize: 14, color: "var(--accent)", minWidth: 100,
        }}>{p.symbol}</span>
        <span style={{ fontSize: 12, color: "var(--muted)", minWidth: 52 }}>{p.anchor_mm_dd}</span>
        <span style={{
          fontSize: 11, fontWeight: 700, color: dirClr,
          background: dirClr + "22", borderRadius: 4, padding: "2px 8px", minWidth: 42,
        }}>{p.window_days}d {p.direction}</span>

        {/* Score */}
        <span style={{ fontSize: 14, fontWeight: 800, color: "var(--warn)", minWidth: 55 }}>
           {p.score?.toFixed(2)}
        </span>

        {/* Accuracy */}
        <span style={{ fontSize: 13, fontWeight: 700, color: dirClr }}>
          {p.accuracy?.toFixed(1)}%
        </span>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>{p.n_obs} yrs</span>

        {/* Mean return */}
        <span style={{ fontSize: 13, fontWeight: 700, color: clr(p.mean_ret), marginLeft: 4 }}>
          {pct(p.mean_ret)}
        </span>

        {/* p-value badge */}
        <span style={{
          fontSize: 10, fontWeight: 700,
          color: sigClr(p.p_value),
          background: sigClr(p.p_value) + "22",
          borderRadius: 4, padding: "1px 6px",
        }}>
          {sigOk ? " sig" : `p=${p.p_value?.toFixed(3)}`}
        </span>

        {/* Degradation */}
        {Math.abs(p.degradation) > 3 && (
          <span style={{ fontSize: 10, color: degClr(p.degradation) }}>
            {p.degradation >= 0 ? "" : ""} {Math.abs(p.degradation).toFixed(0)}%
          </span>
        )}

        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>
          {open ? "" : ""}
        </span>
      </div>

      {/*  Expanded content  */}
      {open && (
        <div style={{ padding: "0 16px 16px", borderTop: "1px solid #334155" }}>
          {loading && (
            <p style={{ color: "var(--muted)", fontSize: 12, padding: "12px 0" }}>
              Loading detail
            </p>
          )}

          {/* Stat grid */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
            <Chip label="Accuracy"    value={`${p.accuracy?.toFixed(1)}%`} color={dirClr} />
            <Chip label="Mean Ret"    value={pct(p.mean_ret)} color={clr(p.mean_ret)} />
            <Chip label="Score"       value={p.score?.toFixed(3)} color="var(--warn)" />
            <Chip label="Consistency" value={p.consistency?.toFixed(3)} color="var(--purple)" small />
            <Chip label="t-stat"      value={num(p.t_stat)} color={sigClr(p.p_value)} small />
            <Chip label="p-value"     value={p.p_value?.toFixed(4)} color={sigClr(p.p_value)} small />
            <Chip label="Edge Ratio"  value={num(p.edge_ratio)} small />
            <Chip label="Std Dev"     value={pct(p.std_ret)} small />
            <Chip label="P10"         value={pct(p.p10)} color={clr(p.p10)} small />
            <Chip label="P90"         value={pct(p.p90)} color={clr(p.p90)} small />
            <Chip label="Best"        value={pct(p.best_ret)} color="var(--pos)" small />
            <Chip label="Worst"       value={pct(p.worst_ret)} color="var(--neg)" small />
            <Chip label="Recent Mean" value={pct(p.recent_mean)} color={clr(p.recent_mean)} small />
          </div>

          {/* Degradation analysis */}
          <div style={{
            marginTop: 14, padding: "12px 14px",
            background: "var(--bg)", borderRadius: 8,
          }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>
              PATTERN TREND (early vs recent accuracy)
            </div>
            <DegBar early={p.early_accuracy} recent={p.recent_accuracy} />
          </div>

          {/* Year chart */}
          {detail && detail.all_returns && detail.all_returns.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>
                YEAR-BY-YEAR RETURNS (click to lock A/B, see delta)
              </div>
              <YearChart data={detail.all_returns} direction={p.direction} />
            </div>
          )}

          {/* Best / worst years */}
          {detail && (
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr",
              gap: 10, marginTop: 14,
            }}>
              <div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
                   BEST YEARS
                </div>
                {detail.best_years?.map((y, i) => (
                  <div key={i} style={{
                    display: "flex", justifyContent: "space-between",
                    padding: "3px 8px", background: "var(--bg)",
                    borderRadius: 5, marginBottom: 3,
                  }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>{y.year}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--pos)" }}>
                      {pct(y.ret)}
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
                   WORST YEARS
                </div>
                {detail.worst_years?.map((y, i) => (
                  <div key={i} style={{
                    display: "flex", justifyContent: "space-between",
                    padding: "3px 8px", background: "var(--bg)",
                    borderRadius: 5, marginBottom: 3,
                  }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>{y.year}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--neg)" }}>
                      {pct(y.ret)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// 
// MAIN PAGE
// 
export default function PatternsV3Page() {
  const [symbol,   setSymbol]   = useState("");
  const [inputSym, setInputSym] = useState("");
  const [minAcc,   setMinAcc]   = useState(62);
  const [minScore, setMinScore] = useState(1.0);
  const [direction, setDir]     = useState("");
  const [sortBy,   setSort]     = useState("score");
  const [window_,  setWindow]   = useState("");
  const [limit,    setLimit]    = useState(100);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [total,    setTotal]    = useState(0);
  const [error,    setError]    = useState("");

  const fetch_ = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({
        min_accuracy: String(minAcc),
        min_score:    String(minScore),
        sort:         sortBy,
        limit:        String(limit),
      });
      if (symbol)    params.set("symbol",    symbol.toUpperCase());
      if (direction) params.set("direction", direction);
      if (window_)   params.set("window",    window_);

      const r = await fetch(`/api/patterns-v3?${params}`);
      const d = await r.json();
      if (d.error) { setError(d.error); setPatterns([]); }
      else { setPatterns(d.rows || []); setTotal(d.count || 0); }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [symbol, minAcc, minScore, direction, sortBy, window_, limit]);

  useEffect(() => { fetch_(); }, []);

  // Stats from current results
  const upCount   = patterns.filter(p => p.direction === "UP").length;
  const downCount = patterns.filter(p => p.direction === "DOWN").length;
  const avgAcc    = patterns.length
    ? patterns.reduce((s, p) => s + p.accuracy, 0) / patterns.length : 0;
  const avgScore  = patterns.length
    ? patterns.reduce((s, p) => s + p.score, 0) / patterns.length : 0;
  const sigCount  = patterns.filter(p => p.p_value < 0.05).length;

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg)",
      color: "var(--text)", fontFamily: "'Space Grotesk',sans-serif",
    }}>
      <NavBar />
      {/*  Header  */}
      <div style={{
        padding: "18px 28px 14px", borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "var(--text)" }}>
             Seasonality Patterns v3
          </h1>
          <p style={{ margin: "3px 0 0", fontSize: 11, color: "var(--muted)" }}>
            Windows 3d60d  Statistical significance  Trend decay detection
          </p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, flexWrap: "wrap" }}>
          {[
            { label: "Results",    value: total,              color: "var(--accent)"  },
            { label: "UP",         value: upCount,            color: "var(--pos)"  },
            { label: "DOWN",       value: downCount,          color: "var(--neg)"  },
            { label: "Significant",value: `${sigCount}`,      color: "var(--warn)"  },
            { label: "Avg Acc",    value: `${avgAcc.toFixed(1)}%`, color: "var(--purple)" },
            { label: "Avg Score",  value: avgScore.toFixed(2),color: "var(--text)"  },
          ].map((s, i) => (
            <div key={i} style={{
              textAlign: "center", padding: "7px 12px",
              background: "var(--card)", borderRadius: 8,
              border: `1px solid ${s.color}33`,
            }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 10, color: "var(--muted)" }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/*  Filters  */}
      <div style={{
        padding: "14px 28px", borderBottom: "1px solid #1e293b",
        display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end",
      }}>
        {/* Symbol search */}
        <div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>SYMBOL</div>
            <div style={{ display: "flex", gap: 6 }}>
              <SymbolSearch
                value={inputSym}
                onSelect={(sym) => { setInputSym(sym); setSymbol(sym); }}
                placeholder="Symbol or company name..."
                width={240}
              />
              {symbol && (
                <button onClick={() => { setSymbol(""); setInputSym(""); }}
                  style={{ padding: "7px 10px", background: "var(--border2)",
                    color: "var(--muted)", border: "none", borderRadius: 7,
                    cursor: "pointer", fontSize: 12 }}>x</button>
              )}
            </div>
          </div>

        {/* Min accuracy */}
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>
            MIN ACCURACY: {minAcc}%
          </div>
          <input type="range" min={55} max={90} value={minAcc}
            onChange={e => setMinAcc(Number(e.target.value))}
            style={{ width: 100, accentColor: "var(--accent)" }} />
        </div>

        {/* Min score */}
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>
            MIN SCORE: {minScore.toFixed(1)}
          </div>
          <input type="range" min={0} max={10} step={0.5} value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
            style={{ width: 100, accentColor: "var(--accent)" }} />
        </div>

        {/* Direction */}
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>DIRECTION</div>
          <select value={direction} onChange={e => setDir(e.target.value)}
            style={{ padding: "7px 10px", background: "var(--card)",
              border: "1px solid #334155", borderRadius: 7,
              color: "var(--text)", fontSize: 13 }}>
            <option value="">All</option>
            <option value="UP">UP</option>
            <option value="DOWN">DOWN</option>
          </select>
        </div>

        {/* Window */}
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>WINDOW (DAYS)</div>
          <select value={window_} onChange={e => setWindow(e.target.value)}
            style={{ padding: "7px 10px", background: "var(--card)",
              border: "1px solid #334155", borderRadius: 7,
              color: "var(--text)", fontSize: 13 }}>
            <option value="">All (360d)</option>
            {[3,4,5,6,7,8,9,10,12,14,15,20,25,30,40,50,60].map(w => (
              <option key={w} value={w}>{w}d</option>
            ))}
          </select>
        </div>

        {/* Sort */}
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>SORT BY</div>
          <select value={sortBy} onChange={e => setSort(e.target.value)}
            style={{ padding: "7px 10px", background: "var(--card)",
              border: "1px solid #334155", borderRadius: 7,
              color: "var(--text)", fontSize: 13 }}>
            <option value="score">Score</option>
            <option value="accuracy">Accuracy</option>
            <option value="mean_ret">Mean Return</option>
            <option value="consistency">Consistency</option>
            <option value="t_stat">t-stat</option>
            <option value="p_value">p-value (best)</option>
            <option value="n_obs">Most Years</option>
            <option value="degradation">Strengthening</option>
          </select>
        </div>

        {/* Limit */}
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>SHOW</div>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))}
            style={{ padding: "7px 10px", background: "var(--card)",
              border: "1px solid #334155", borderRadius: 7,
              color: "var(--text)", fontSize: 13 }}>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
            <option value={500}>500</option>
          </select>
        </div>

        <button onClick={fetch_} disabled={loading}
          style={{
            padding: "8px 20px", background: loading ? "var(--border2)" : "var(--pos)",
            color: "#fff", border: "none", borderRadius: 8,
            cursor: loading ? "not-allowed" : "pointer",
            fontSize: 13, fontWeight: 700, alignSelf: "flex-end",
          }}>
          {loading ? " Loading" : " Search"}
        </button>
      </div>

      {/*  Error  */}
      {error && (
        <div style={{ padding: "12px 28px" }}>
          <div style={{
            background: "#2d1515", borderRadius: 8, padding: "10px 14px",
            color: "var(--neg)", fontSize: 13,
          }}>
             {error}
            {error.includes("no such table") && (
              <span style={{ color: "var(--muted)" }}>
                {"  Run: "}
                <code>py D:\MICC\build_seasonality_v3.py</code>
              </span>
            )}
          </div>
        </div>
      )}

      {/*  Results  */}
      <div style={{ padding: "16px 28px" }}>
        {!loading && patterns.length === 0 && !error && (
          <div style={{ textAlign: "center", padding: "60px 0" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}></div>
            <p style={{ color: "var(--muted)" }}>
              No patterns found. Try lowering min accuracy / score, or run the builder first.
            </p>
            <code style={{ fontSize: 12, color: "var(--muted)" }}>
              py D:\MICC\build_seasonality_v3.py
            </code>
          </div>
        )}
        {patterns.map((p, i) => <PatternCard key={`${p.symbol}-${p.anchor_mm_dd}-${p.window_days}-${p.direction}`} p={p} idx={i} />)}
      </div>
    </div>
  );
}
