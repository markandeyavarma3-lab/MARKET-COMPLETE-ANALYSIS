"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState, useCallback } from "react";

const V = {
  page:   { padding: "28px 32px", fontFamily: "monospace", maxWidth: 1300,
            margin: "0 auto", color: "var(--text)" },
  hdr:    { fontSize: 22, fontWeight: 700, color: "var(--accent)", letterSpacing: 1, marginBottom: 4 },
  sub:    { fontSize: 12, color: "var(--muted)", marginBottom: 24 },
  row:    { display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" as const },
  stat:   { background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8,
            padding: "14px 20px", minWidth: 130 },
  sl:     { fontSize: 10, color: "var(--muted)", letterSpacing: 1,
            textTransform: "uppercase" as const, marginBottom: 4 },
  sv:     { fontSize: 22, fontWeight: 700 },
  card:   { background: "var(--card)", border: "1px solid var(--border)",
            borderRadius: 8, padding: "18px 20px", marginBottom: 20, overflowX: "auto" as const },
  th:     { fontSize: 10, color: "var(--muted)", fontWeight: 700, letterSpacing: 1,
            textTransform: "uppercase" as const, padding: "0 12px 10px 0",
            borderBottom: "1px solid var(--border)", textAlign: "left" as const,
            whiteSpace: "nowrap" as const },
  td:     { padding: "10px 12px 10px 0", fontSize: 12,
            borderBottom: "1px solid #0f172a", verticalAlign: "middle" as const,
            whiteSpace: "nowrap" as const },
  sym:    { fontWeight: 700, color: "var(--text)", fontFamily: "monospace", fontSize: 13 },
  pos:    { color: "var(--pos)", fontWeight: 700 },
  neg:    { color: "var(--neg)", fontWeight: 700 },
  warn:   { color: "var(--warn)", fontWeight: 700 },
  muted:  { color: "var(--muted)", fontSize: 11 },
  pill:   (c: string) => ({ fontSize: 10, fontWeight: 700, padding: "2px 8px",
            borderRadius: 4, background: c + "22", color: c, display: "inline-block" }),
  btn:    { fontSize: 11, padding: "5px 14px", borderRadius: 4, cursor: "pointer",
            background: "var(--surface)", border: "1px solid var(--border)",
            color: "var(--muted)" },
  empty:  { color: "var(--dim)", fontSize: 13, padding: "40px 0", textAlign: "center" as const },
  hint:   { background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 8, padding: "18px 20px", marginTop: 16,
            fontSize: 12, color: "var(--dim)", lineHeight: 1.9 },
};

function Stat({ label, value, color }: any) {
  return (
    <div style={V.stat}>
      <NavBar />
      <div style={V.sl}>{label}</div>
      <div style={{ ...V.sv, color: color || "var(--accent)" }}>{value ?? "--"}</div>
    </div>
  );
}

function Pnl({ v }: { v: number | null }) {
  if (v == null) return <span style={V.muted}>--</span>;
  return <span style={v >= 0 ? V.pos : V.neg}>{v >= 0 ? "+" : ""}{v.toFixed ? v.toFixed(2) : v}%</span>;
}

function Status({ p }: { p: any }) {
  if (p.status === "CLOSED" || p.exit_price)
    return <span style={V.pill("#64748b")}>CLOSED</span>;
  if (p.at_target2) return <span style={V.pill("#818cf8")}>T2 HIT</span>;
  if (p.at_target1) return <span style={V.pill("#22c55e")}>T1 HIT</span>;
  if (p.at_stop)    return <span style={V.pill("#ef4444")}>STOP</span>;
  const pct = p.live_pnl_pct || 0;
  if (pct > 5)  return <span style={V.pill("#22c55e")}>PROFIT</span>;
  if (pct < -3) return <span style={V.pill("#ef4444")}>DRAWDOWN</span>;
  return <span style={V.pill("#64748b")}>OPEN</span>;
}

export default function PortfolioPage() {
  const [data,    setData]    = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab,     setTab]     = useState<"open"|"closed">("open");
  const [ts,      setTs]      = useState("");

  const load = useCallback(() => {
    setLoading(true);
    fetch("/api/portfolio")
      .then(r => r.json())
      .then(j => { setData(j); setLoading(false); setTs(new Date().toLocaleTimeString()); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const positions  = data?.positions || [];
  const summary    = data?.summary;
  const open       = positions.filter((p: any) => p.status === "OPEN" || !p.exit_price);
  const closed     = positions.filter((p: any) => p.exit_price);
  const shown      = tab === "open" ? open : closed;
  const livePnl    = summary?.live_pnl_rs ?? 0;
  const closedPnl  = summary?.closed_pnl_rs ?? 0;

  return (
    <div style={V.page}>

      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 4 }}>
        <div style={V.hdr}>Portfolio</div>
        <button style={V.btn} onClick={load}>Refresh</button>
        {ts && <span style={V.muted}>updated {ts}</span>}
      </div>
      <div style={V.sub}>
        Live P&amp;L from stock_data &nbsp;|&nbsp; Stops &amp; targets from my_portfolio
        &nbsp;|&nbsp; Add: py agent_exit.py --add SYMBOL PRICE QTY
      </div>

      {/* Summary stats */}
      {summary && (
        <div style={V.row}>
          <Stat label="Open"       value={summary.n_open} />
          <Stat label="Closed"     value={summary.n_closed} color="var(--muted)" />
          <Stat label="Live P&L"
            value={`Rs.${Number(livePnl).toLocaleString()}`}
            color={livePnl >= 0 ? "var(--pos)" : "var(--neg)"} />
          <Stat label="Closed P&L"
            value={`Rs.${Number(closedPnl).toLocaleString()}`}
            color={closedPnl >= 0 ? "var(--pos)" : "var(--neg)"} />
          <Stat label="Winners"    value={summary.open_winners} color="var(--pos)" />
          <Stat label="Losers"     value={summary.open_losers}  color="var(--neg)" />
          <Stat label="Win Rate"   value={`${summary.win_rate_pct}%`} />
        </div>
      )}

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["open","closed"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            ...V.btn, fontWeight: tab === t ? 700 : 400,
            borderColor: tab === t ? "var(--accent)" : "var(--border)",
            color: tab === t ? "var(--accent)" : "var(--muted)",
          }}>
            {t === "open" ? `Open (${open.length})` : `Closed (${closed.length})`}
          </button>
        ))}
      </div>

      <div style={V.card}>
        {loading ? (
          <div style={V.muted}>Loading...</div>
        ) : shown.length === 0 ? (
          <div style={V.empty}>
            No {tab} positions.
            {tab === "open" && (
              <div style={{ marginTop: 12 }}>
                <div style={V.hint}>
                  <b style={{ color: "var(--accent)" }}>Add a position:</b><br />
                  py D:/MICC/agent_exit.py --add RELIANCE 1453 10<br /><br />
                  <b style={{ color: "var(--accent)" }}>Or via Python:</b><br />
                  {`import sqlite3, datetime`}<br />
                  {`conn = sqlite3.connect(r'D:/marketDB/db/market.db')`}<br />
                  {`conn.execute("INSERT INTO my_portfolio (symbol,entry_date,entry_price,quantity,stop_loss,target_1,notes) VALUES ('RELIANCE','2026-05-18',1453,10,1385,1600,'My note')")`}<br />
                  {`conn.commit()`}
                </div>
              </div>
            )}
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {tab === "open"
                  ? ["Symbol","Entry Date","Entry","Qty","Live Price","P&L %","P&L Rs","Stop","T1","T2","Risk/Trade","Status"]
                  : ["Symbol","Entry","Exit Date","Exit Price","Qty","P&L %","P&L Rs","Notes"]
                }.map(h => <th key={h} style={V.th}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {shown.map((p: any, i: number) => tab === "open" ? (
                <tr key={i}>
                  <td style={V.td}><span style={V.sym}>{p.symbol}</span></td>
                  <td style={V.td}><span style={V.muted}>{p.entry_date}</span></td>
                  <td style={V.td}>{p.entry_price ? Number(p.entry_price).toFixed(2) : "--"}</td>
                  <td style={V.td}>{p.quantity}</td>
                  <td style={V.td}>
                    {p.current_price
                      ? <span style={{ color: "var(--accent)", fontWeight: 700 }}>
                          {Number(p.current_price).toFixed(2)}
                        </span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}><Pnl v={p.live_pnl_pct} /></td>
                  <td style={V.td}>
                    {p.live_pnl_rs != null
                      ? <span style={p.live_pnl_rs >= 0 ? V.pos : V.neg}>
                          {p.live_pnl_rs >= 0 ? "+" : ""}
                          {Number(p.live_pnl_rs).toLocaleString()}
                        </span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}>
                    {p.stop_loss
                      ? <span style={V.neg}>{Number(p.stop_loss).toFixed(2)}</span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}>
                    {p.target_1
                      ? <span style={V.pos}>{Number(p.target_1).toFixed(2)}</span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}>
                    {p.target_2
                      ? <span style={V.pos}>{Number(p.target_2).toFixed(2)}</span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}>
                    {p.risk_per_trade
                      ? <span style={V.warn}>{Number(p.risk_per_trade).toLocaleString()}</span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}><Status p={p} /></td>
                </tr>
              ) : (
                <tr key={i}>
                  <td style={V.td}><span style={V.sym}>{p.symbol}</span></td>
                  <td style={V.td}><span style={V.muted}>{p.entry_date}</span></td>
                  <td style={V.td}><span style={V.muted}>{p.exit_date}</span></td>
                  <td style={V.td}>{p.exit_price ? Number(p.exit_price).toFixed(2) : "--"}</td>
                  <td style={V.td}>{p.quantity}</td>
                  <td style={V.td}>
                    {p.pnl_pct != null
                      ? <span style={parseFloat(p.pnl_pct) >= 0 ? V.pos : V.neg}>
                          {parseFloat(p.pnl_pct) >= 0 ? "+" : ""}{Number(p.pnl_pct).toFixed(2)}%
                        </span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}>
                    {p.pnl != null
                      ? <span style={parseFloat(p.pnl) >= 0 ? V.pos : V.neg}>
                          {Number(p.pnl).toLocaleString()}
                        </span>
                      : <span style={V.muted}>--</span>}
                  </td>
                  <td style={V.td}><span style={V.muted}>{p.notes || "--"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
