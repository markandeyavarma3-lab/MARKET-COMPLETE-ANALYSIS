"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface InsiderCluster {
  symbol: string; n_buys: number; total_value_cr: number; names: string;
}
interface BigTrade {
  symbol: string; filing_date: string; name: string;
  transaction_type: string; quantity: number; price: number; value: number;
}
interface ResultEvent {
  symbol: string; announcement_date: string; subject: string;
}
interface DivEvent {
  symbol: string; announcement_date: string; subject: string;
}
interface PostReaction {
  symbol: string; announcement_date: string; ret_5d?: number;
}
interface UpcomingResult {
  symbol: string; last_results_date: string; expected_due: string;
}

interface EtaData {
  screen1_results_season?: ResultEvent[];
  screen2_dividends?: DivEvent[];
  screen3_insider_clusters?: InsiderCluster[];
  screen4_big_trades?: BigTrade[];
  screen5_post_results_reaction?: PostReaction[];
  screen6_upcoming_results?: UpcomingResult[];
  llm_analysis?: string;
  timestamp?: string;
  date?: string;
}

const fmt  = (v: unknown, d = 2) => v == null ? "--" : Number(v).toFixed(d);
const pct  = (v: unknown) => v == null ? "--" : (Number(v) >= 0 ? "+" : "") + Number(v).toFixed(2) + "%";
const bull = (v: unknown) => Number(v) >= 0 ? "var(--bull)" : "var(--bear)";
const cr   = (v: unknown) => v == null ? "--" : (Number(v) / 1e7).toFixed(2) + " Cr";

export default function EtaPage() {
  const [data, setData]   = useState<EtaData | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");
  const [tab, setTab]     = useState(0);
  const [search, setSrch] = useState("");

  useEffect(() => {
    fetch("/api/eta")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 20 },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    tabs:  { display: "flex", gap: 6, flexWrap: "wrap" as const, marginBottom: 20 },
    tab:   (a: boolean): React.CSSProperties => ({
      padding: "5px 16px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (a ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: a ? "var(--accent)22" : "transparent",
      color: a ? "var(--accent)" : "var(--dim)",
    }),
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)", background: "var(--surface)" },
    td:    { padding: "8px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    sym:   { color: "var(--accent)", fontWeight: 700 },
    empty: { padding: "30px", textAlign: "center" as const, color: "var(--dim)", fontSize: 12 },
    input: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4,
             padding: "4px 10px", fontSize: 11, color: "var(--text)", outline: "none" },
    pre:   { fontSize: 11, color: "var(--text)", lineHeight: 1.7, whiteSpace: "pre-wrap" as const,
             background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6,
             padding: "12px 16px", maxHeight: 400, overflow: "auto" as const },
    badge: (buy: boolean): React.CSSProperties => ({
      padding: "2px 8px", borderRadius: 3, fontSize: 10, fontWeight: 700,
      background: buy ? "var(--bull)22" : "var(--bear)22",
      color: buy ? "var(--bull)" : "var(--bear)",
    }),
  };

  const TABS = [
    "INSIDER CLUSTERS",
    "BIG TRADES",
    "RESULTS SEASON",
    "DIVIDENDS",
    "POST-RESULTS",
    "UPCOMING",
    "LLM ANALYSIS",
  ];

  const filter = <T extends { symbol?: string }>(arr: T[] | undefined): T[] => {
    if (!arr) return [];
    if (!search) return arr;
    return arr.filter(r => r.symbol?.toLowerCase().includes(search.toLowerCase()));
  };

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>ETA  /  CORPORATE EVENTS INTELLIGENCE</span>
        <input
          style={S.input}
          placeholder="search symbol..."
          value={search}
          onChange={e => setSrch(e.target.value)}
        />
        {data?.timestamp && (
          <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>
            {data.timestamp}
          </span>
        )}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading corporate events...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>
          Error: {error} -- run: py D:\MICC\agent_eta.py --send
        </div>}

        {data && <>
          <div style={S.tabs}>
            {TABS.map((t, i) => (
              <button key={i} onClick={() => setTab(i)} style={S.tab(tab === i)}>{t}</button>
            ))}
          </div>

          {tab === 0 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>BUY COUNT</th>
                  <th style={S.th}>TOTAL VALUE</th>
                  <th style={S.th}>INSIDERS</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen3_insider_clusters).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--bull)", fontWeight: 700 }}>{r.n_buys}</td>
                      <td style={{ ...S.td, color: "var(--accent)" }}>{cr(r.total_value_cr)}</td>
                      <td style={{ ...S.td, color: "var(--dim)", fontSize: 11 }}>{r.names}</td>
                    </tr>
                  ))}
                  {filter(data.screen3_insider_clusters).length === 0 && (
                    <tr><td colSpan={4} style={S.empty}>No insider clusters found</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 1 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>NAME</th>
                  <th style={S.th}>TYPE</th>
                  <th style={S.th}>QTY</th>
                  <th style={S.th}>PRICE</th>
                  <th style={S.th}>VALUE</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen4_big_trades).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.filing_date}</td>
                      <td style={{ ...S.td, fontSize: 11 }}>{r.name}</td>
                      <td style={S.td}>
                        <span style={S.badge(r.transaction_type === "BUY")}>
                          {r.transaction_type}
                        </span>
                      </td>
                      <td style={S.td}>{r.quantity ? Number(r.quantity).toLocaleString("en-IN") : "--"}</td>
                      <td style={S.td}>{fmt(r.price)}</td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 600 }}>
                        {r.value ? (Number(r.value) / 1e7).toFixed(2) + " Cr" : "--"}
                      </td>
                    </tr>
                  ))}
                  {filter(data.screen4_big_trades).length === 0 && (
                    <tr><td colSpan={7} style={S.empty}>No big trades found</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 2 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>SUBJECT</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen1_results_season).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.announcement_date}</td>
                      <td style={{ ...S.td, fontSize: 11 }}>{r.subject}</td>
                    </tr>
                  ))}
                  {filter(data.screen1_results_season).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No results announcements</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 3 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>SUBJECT</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen2_dividends).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.announcement_date}</td>
                      <td style={{ ...S.td, fontSize: 11 }}>{r.subject}</td>
                    </tr>
                  ))}
                  {filter(data.screen2_dividends).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No dividend announcements</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 4 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>DATE</th>
                  <th style={S.th}>5D RETURN</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen5_post_results_reaction).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.announcement_date}</td>
                      <td style={{ ...S.td, color: bull(r.ret_5d), fontWeight: 600 }}>{pct(r.ret_5d)}</td>
                    </tr>
                  ))}
                  {filter(data.screen5_post_results_reaction).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No post-results data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 5 && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>SYMBOL</th>
                  <th style={S.th}>LAST RESULTS</th>
                  <th style={S.th}>EXPECTED DUE</th>
                </tr></thead>
                <tbody>
                  {filter(data.screen6_upcoming_results).map((r, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{r.last_results_date}</td>
                      <td style={{ ...S.td, color: "var(--warn)" }}>{r.expected_due}</td>
                    </tr>
                  ))}
                  {filter(data.screen6_upcoming_results).length === 0 && (
                    <tr><td colSpan={3} style={S.empty}>No upcoming results data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 6 && data.llm_analysis && (
            <pre style={S.pre}>{data.llm_analysis}</pre>
          )}
          {tab === 6 && !data.llm_analysis && (
            <div style={{ color: "var(--dim)", padding: 20 }}>No LLM analysis -- run py agent_eta.py --send</div>
          )}
        </>}
      </div>
    </div>
  );
}
