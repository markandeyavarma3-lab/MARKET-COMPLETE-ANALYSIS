"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface Position {
  id: number; symbol: string; entry_date: string; entry_price: number;
  quantity: number; current_price?: number; pnl_pct?: string; pnl_rs?: string;
  stop_loss?: number; target_1?: number; target_2?: number;
  status?: string; notes?: string; at_stop?: boolean; at_target?: boolean;
}
interface Summary {
  n_positions: number; winners: number; losers: number;
  total_pnl_rs: string; avg_pnl_pct: string;
}
interface PortData {
  positions: Position[]; summary: Summary;
  pnl_history?: { date: string; cumulative_pnl: number }[];
}

const fmt  = (v: unknown, d = 2) => v == null ? "--" : Number(v).toFixed(d);
const pct  = (v: unknown) => v == null ? "--" : (Number(v)>=0?"+":"") + Number(v).toFixed(2) + "%";
const bull = (v: unknown) => Number(v) >= 0 ? "var(--bull)" : "var(--bear)";
const rs   = (v: unknown) => {
  if (v == null) return "--";
  const n = Number(v);
  function CorrHeatmap() {
    if (!corrData || !corrData.symbols || corrData.symbols.length < 2) {
      return <div style={{ padding: 40, textAlign: "center", color: "var(--dim)", fontSize: 12 }}>
        Need 2+ open positions for correlation matrix.
      </div>;
    }
    const { symbols, matrix } = corrData;
    const n = symbols.length;
    const cellSize = Math.min(80, Math.floor(560 / n));
    const W = cellSize * n + 120;
    const H = cellSize * n + 80;
    const getCorr = (a: string, b: string) =>
      matrix.find(m => m.symA === a && m.symB === b)?.corr ?? null;
    const corrColor = (c: number | null) => {
      if (c === null) return "var(--muted)";
      if (c >= 0.7)  return "#f87171";  // high positive = bad (concentrated)
      if (c >= 0.3)  return "#fbbf24";  // moderate
      if (c >= -0.3) return "#34d399";  // low = good diversification
      return "#60a5fa";                  // negative = excellent hedge
    };
    return (
      <div>
        <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 12 }}>
          POSITION CORRELATION MATRIX  (90d daily returns)
        </div>
        <div style={{ overflowX: "auto" }}>
          <svg width={W} height={H} style={{ fontFamily: "JetBrains Mono, monospace" }}>
            {/* Column headers */}
            {symbols.map((sym, j) => (
              <text key={j} x={120 + j * cellSize + cellSize/2} y={60}
                textAnchor="middle" fontSize={10} fill="var(--dim)"
                transform={`rotate(-45, ${120 + j*cellSize + cellSize/2}, 60)`}>
                {sym.slice(0,8)}
              </text>
            ))}
            {/* Row labels + cells */}
            {symbols.map((symA, i) => (
              <g key={i}>
                <text x={110} y={80 + i * cellSize + cellSize/2 + 4}
                  textAnchor="end" fontSize={10} fill="var(--dim)">{symA.slice(0,8)}</text>
                {symbols.map((symB, j) => {
                  const c = getCorr(symA, symB);
                  const bg = corrColor(c);
                  return (
                    <g key={j}>
                      <rect x={120 + j*cellSize} y={70 + i*cellSize}
                        width={cellSize-2} height={cellSize-2} fill={bg} opacity={0.85} rx={2} />
                      <text x={120 + j*cellSize + cellSize/2} y={70 + i*cellSize + cellSize/2 + 4}
                        textAnchor="middle" fontSize={Math.max(9, cellSize/6)} fill="#000" fontWeight={600}>
                        {c !== null ? c.toFixed(2) : "--"}
                      </text>
                    </g>
                  );
                })}
              </g>
            ))}
          </svg>
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 10, color: "var(--dim)" }}>
          <span><span style={{ color: "#34d399" }}>GREEN</span>  low correlation (good diversification)</span>
          <span><span style={{ color: "#fbbf24" }}>YELLOW</span> moderate correlation</span>
          <span><span style={{ color: "#f87171" }}>RED</span>    high correlation (concentrated risk)</span>
          <span><span style={{ color: "#60a5fa" }}>BLUE</span>   negative correlation (hedge)</span>
        </div>
      </div>
    );
  }

  return (n >= 0 ? "+" : "") + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
};

function EquityCurve({ positions }: { positions: Position[] }) {
  if (!positions.length) return null;

  // Build synthetic equity curve from entry dates + current P&L
  const pts = positions
    .filter(p => p.pnl_rs != null)
    .sort((a, b) => a.entry_date.localeCompare(b.entry_date))
    .map((p, i, arr) => {
      const cumPnl = arr.slice(0, i + 1).reduce((s, x) => s + Number(x.pnl_rs || 0), 0);
      return { label: p.symbol, pnl: Number(p.pnl_rs || 0), cumPnl, date: p.entry_date };
    });

  if (pts.length < 2) return null;

  const W = 700, H = 160, ML = 60, MR = 16, MT = 12, MB = 28;
  const PW = W - ML - MR, PH = H - MT - MB;
  const minY = Math.min(0, ...pts.map(p => p.cumPnl));
  const maxY = Math.max(0, ...pts.map(p => p.cumPnl));
  const range = maxY - minY || 1;
  const tx = (i: number) => ML + (i / (pts.length - 1)) * PW;
  const ty = (v: number) => MT + PH - ((v - minY) / range) * PH;
  const zero_y = ty(0);

  const polyline = pts.map((p, i) => `${tx(i)},${ty(p.cumPnl)}`).join(" ");
  const area = `${tx(0)},${zero_y} ` + polyline + ` ${tx(pts.length-1)},${zero_y}`;
  const finalPnl = pts[pts.length - 1].cumPnl;
  const lineColor = finalPnl >= 0 ? "var(--bull)" : "var(--bear)";

  const yTicks = [minY, minY + range * 0.25, minY + range * 0.5, minY + range * 0.75, maxY];

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 8 }}>
        PORTFOLIO EQUITY CURVE  (cumulative P&L)
      </div>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "12px 16px", overflowX: "auto" }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible", display: "block" }}>
          {/* Grid lines */}
          {yTicks.map((v, i) => (
            <g key={i}>
              <line x1={ML} y1={ty(v)} x2={W - MR} y2={ty(v)}
                stroke={v === 0 ? "var(--border)" : "#ffffff0a"} strokeWidth={v === 0 ? 1.5 : 1} strokeDasharray={v === 0 ? "none" : "3,3"} />
              <text x={ML - 8} y={ty(v) + 4} textAnchor="end" fontSize={9}
                fill={v === 0 ? "var(--dim)" : "#666"}>
                {v >= 1000 || v <= -1000
                  ? (v / 1000).toFixed(1) + "k"
                  : v.toFixed(0)}
              </text>
            </g>
          ))}
          {/* Zero line label */}
          <text x={ML - 8} y={zero_y + 4} textAnchor="end" fontSize={9} fill="var(--dim)">0</text>

          {/* Axes */}
          <line x1={ML} y1={MT} x2={ML} y2={H - MB} stroke="#ffffff18" strokeWidth={1} />
          <line x1={ML} y1={H - MB} x2={W - MR} y2={H - MB} stroke="#ffffff18" strokeWidth={1} />

          {/* Area fill */}
          <polygon points={area} fill={lineColor} opacity={0.07} />

          {/* Line */}
          <polyline points={polyline} fill="none" stroke={lineColor} strokeWidth={2} />

          {/* Data points + x labels */}
          {pts.map((p, i) => (
            <g key={i}>
              <circle cx={tx(i)} cy={ty(p.cumPnl)} r={4}
                fill={p.pnl >= 0 ? "var(--bull)" : "var(--bear)"}
                stroke="var(--bg)" strokeWidth={1.5}>
                <title>{p.label}: {p.date} | this: {rs(p.pnl)} | cum: {rs(p.cumPnl)}</title>
              </circle>
              <text x={tx(i)} y={H - MB + 14} textAnchor="middle" fontSize={9} fill="#555">
                {p.label.slice(0, 6)}
              </text>
            </g>
          ))}

          {/* Y axis label */}
          <text x={10} y={H / 2} textAnchor="middle" fontSize={9} fill="#555"
            transform={`rotate(-90,10,${H / 2})`}>
            P&L (Rs)
          </text>
        </svg>
      </div>
    </div>
  );
}

function StatusBadge({ pos }: { pos: Position }) {
  if (pos.at_target) return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bull)22", color: "var(--bull)" }}>TARGET</span>;
  if (pos.at_stop)   return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bear)22", color: "var(--bear)" }}>STOP</span>;
  const p = parseFloat(pos.pnl_pct || "0");
  if (p > 5)  return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bull)22", color: "var(--bull)" }}>PROFIT</span>;
  if (p < -3) return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bear)22", color: "var(--bear)" }}>DRAWDOWN</span>;
  return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, color: "var(--dim)", background: "var(--border)22" }}>OPEN</span>;
}

export default function PortfolioPage() {
  const [data, setData]   = useState<PortData | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");
  const [refresh, setRef] = useState(0);
  const [corrData, setCorrData] = useState<{symbols:string[];matrix:{symA:string;symB:string;corr:number|null}[]}|null>(null);
  const [activeTab, setActiveTab] = useState<"positions"|"chart"|"correlation">("positions");

  useEffect(() => {
    setL(true);
    fetch("/api/portfolio")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
    fetch("/api/portfolio/correlation")
      .then(r => r.json())
      .then(d => setCorrData(d))
      .catch(() => {});
  }, [refresh]);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 16 },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    grid:  { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10, marginBottom: 20 },
    kv:    { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "12px 16px" },
    kvk:   { fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 4 },
    kvv:   { fontSize: 20, color: "var(--text)", fontWeight: 700 },
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", marginBottom: 16 },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)", background: "var(--surface)" },
    td:    { padding: "9px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    sym:   { color: "var(--accent)", fontWeight: 700 },
    btn:   { fontSize: 11, padding: "4px 12px", borderRadius: 4, background: "var(--surface)",
             border: "1px solid var(--border)", color: "var(--dim)", cursor: "pointer" },
    hint:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
             padding: "16px 20px", marginTop: 16, fontSize: 12, color: "var(--dim)", lineHeight: 1.8 },
  };

  const positions = data?.positions || [];
  const summary   = data?.summary;
  const totalPnl  = parseFloat(summary?.total_pnl_rs || "0");
  const winRate   = summary && summary.n_positions > 0
    ? (100 * summary.winners / summary.n_positions).toFixed(0) + "%"
    : "--";

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>PORTFOLIO  /  POSITIONS & P&L</span>
        {["positions","chart","correlation"].map(t => (
          <button key={t} onClick={() => setActiveTab(t as typeof activeTab)}
            style={{ padding:"3px 10px", fontSize:10, letterSpacing:1, cursor:"pointer",
              border:"1px solid "+(activeTab===t?"var(--accent)":"var(--border)"),
              borderRadius:4, background:activeTab===t?"var(--accent)22":"transparent",
              color:activeTab===t?"var(--accent)":"var(--dim)" }}>
            {t.toUpperCase()}
          </button>
        ))}
        <button onClick={() => setRef(r => r + 1)} style={S.btn}>Refresh</button>
        {data && <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>
          {positions.length} positions
        </span>}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading portfolio...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error}</div>}

        {data && <>
          {/* Summary KPIs */}
          <div style={S.grid}>
            <div style={S.kv}>
              <div style={S.kvk}>POSITIONS</div>
              <div style={S.kvv}>{summary?.n_positions ?? "--"}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>TOTAL P&L</div>
              <div style={{ ...S.kvv, color: bull(totalPnl), fontSize: 18 }}>
                Rs.{rs(totalPnl)}
              </div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>WIN RATE</div>
              <div style={{ ...S.kvv, color: "var(--accent)" }}>{winRate}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>WINNERS</div>
              <div style={{ ...S.kvv, color: "var(--bull)" }}>{summary?.winners ?? "--"}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>LOSERS</div>
              <div style={{ ...S.kvv, color: "var(--bear)" }}>{summary?.losers ?? "--"}</div>
            </div>
          </div>

          {activeTab === "chart" && <EquityCurve positions={positions} />}

          {activeTab === "positions" && positions.length === 0 ? (
            <div style={{ ...S.card, padding: 40, textAlign: "center", color: "var(--dim)" }}>
              No positions yet. Add via: py D:\MICC\agent_exit.py --add SYMBOL PRICE QTY
            </div>
          ) : (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  {["SYMBOL","ENTRY DATE","ENTRY","QTY","CURRENT","P&L %","P&L Rs","STOP","T1","T2","STATUS","NOTES"].map(h => (
                    <th key={h} style={S.th}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={p.id || i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{p.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{p.entry_date}</td>
                      <td style={S.td}>{fmt(p.entry_price)}</td>
                      <td style={S.td}>{p.quantity}</td>
                      <td style={{ ...S.td, color: "var(--accent)" }}>
                        {p.current_price ? fmt(p.current_price) : "--"}
                      </td>
                      <td style={{ ...S.td, color: bull(p.pnl_pct), fontWeight: 700 }}>
                        {pct(p.pnl_pct)}
                      </td>
                      <td style={{ ...S.td, color: bull(p.pnl_rs), fontWeight: 600 }}>
                        {p.pnl_rs ? "Rs." + rs(p.pnl_rs) : "--"}
                      </td>
                      <td style={{ ...S.td, color: "var(--bear)" }}>
                        {p.stop_loss ? fmt(p.stop_loss) : "--"}
                      </td>
                      <td style={{ ...S.td, color: "var(--bull)" }}>
                        {p.target_1 ? fmt(p.target_1) : "--"}
                      </td>
                      <td style={{ ...S.td, color: "var(--info)" }}>
                        {p.target_2 ? fmt(p.target_2) : "--"}
                      </td>
                      <td style={S.td}><StatusBadge pos={p} /></td>
                      <td style={{ ...S.td, color: "var(--dim)", fontSize: 11 }}>
                        {p.notes || "--"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === "positions" && <div style={S.hint}>
            <div style={{ fontSize: 10, letterSpacing: 1, color: "var(--dim)", marginBottom: 8 }}>HOW TO ADD A POSITION</div>
            <div>py D:\MICC\agent_exit.py --add RELIANCE 1450.00 10</div>
            <div style={{ marginTop: 8, color: "var(--muted)" }}>
              Or insert directly into my_portfolio table in market.db
            </div>
            <div style={{ marginTop: 4, fontSize: 11, color: "var(--dim)" }}>
              Schema: symbol, entry_date, entry_price, quantity, stop_loss, target_1, target_2, notes
            </div>
          </div>
        </>}
      </div>
    </div>
  );
}
