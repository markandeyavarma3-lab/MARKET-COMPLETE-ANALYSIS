"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

const S = {
  page:    { padding: "28px 32px", fontFamily: "monospace", maxWidth: 1200,
             margin: "0 auto", color: "var(--text)" },
  hdr:     { fontSize: 22, fontWeight: 700, color: "var(--accent)",
             letterSpacing: 1, marginBottom: 4 },
  sub:     { fontSize: 12, color: "var(--muted)", marginBottom: 28 },
  grid:    { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 },
  card:    { background: "var(--card)", border: "1px solid var(--border)",
             borderRadius: 8, padding: "18px 20px" },
  cardHdr: { fontSize: 11, fontWeight: 700, color: "var(--accent)",
             letterSpacing: 2, textTransform: "uppercase" as const,
             marginBottom: 14, borderBottom: "1px solid var(--border)",
             paddingBottom: 8 },
  row:     { display: "flex", alignItems: "center", gap: 10,
             padding: "7px 0", borderBottom: "1px solid #0f172a",
             fontSize: 12 },
  sym:     { fontWeight: 700, color: "var(--text)", minWidth: 110,
             fontFamily: "monospace" },
  pill:    (c: string) => ({
             fontSize: 10, fontWeight: 700, padding: "2px 7px",
             borderRadius: 4, background: c + "22", color: c }),
  muted:   { color: "var(--muted)", fontSize: 11 },
  pos:     { color: "var(--pos)", fontWeight: 700 },
  neg:     { color: "var(--neg)", fontWeight: 700 },
  warn:    { color: "var(--warn)", fontWeight: 700 },
  empty:   { color: "var(--dim)", fontSize: 12, padding: "12px 0" },
  badge:   (n: number) => ({
             display: "inline-block", marginLeft: 8, fontSize: 10,
             background: "var(--accent)", color: "#000",
             borderRadius: 10, padding: "1px 7px", fontWeight: 700,
             opacity: n > 0 ? 1 : 0.3 }),
};

function Section({ title, count, children }: any) {
  return (
    <div style={S.card}>
      <NavBar />
      <div style={S.cardHdr}>
        {title}<span style={S.badge(count)}>{count}</span>
      </div>
      {children}
    </div>
  );
}

export default function EtaPage() {
  const [data, setData]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState("");

  useEffect(() => {
    fetch("/api/eta")
      .then(r => r.json())
      .then(j => { setData(j.data); setLoading(false); })
      .catch(e => { setErr(e.message); setLoading(false); });
  }, []);

  if (loading) return <div style={S.page}><div style={S.muted}>Loading Eta report...</div></div>;
  if (err || !data) return <div style={S.page}><div style={{color:"var(--neg)"}}>
    Error: {err || "No report. Run: py agent_eta.py"}</div></div>;

  const clusters  = data.insider_cluster    || [];
  const bigTrades = data.big_insider_trades || [];
  const results   = data.results_season     || [];
  const divs      = data.dividend_calendar  || [];
  const upcoming  = data.upcoming_results   || [];
  const reactions = data.post_results_reaction || [];

  return (
    <div style={S.page}>
      <div style={S.hdr}>Agent Eta — Corporate Intelligence</div>
      <div style={S.sub}>
        Updated: {data.generated_at || data.date}
        &nbsp;&nbsp;|&nbsp;&nbsp;
        Results: {results.length}&nbsp; Insiders: {clusters.length}&nbsp;
        Dividends: {divs.length}&nbsp; Upcoming: {upcoming.length}
      </div>

      <div style={S.grid}>

        {/* Insider Clusters */}
        <Section title="Insider Clusters" count={clusters.length}>
          {clusters.length === 0
            ? <div style={S.empty}>No clusters in last 30 days</div>
            : clusters.map((c: any, i: number) => (
              <div key={i} style={S.row}>
                <span style={S.sym}>{c.symbol}</span>
                <span style={{...S.pill("#22c55e"), marginLeft: "auto"}}>
                  {c.buy_count}x BUY
                </span>
                <span style={S.warn}>
                  {c.total_value_cr != null
                    ? `Rs.${Number(c.total_value_cr).toFixed(1)}Cr` : ""}
                </span>
                <span style={S.muted}>{c.latest_date || ""}</span>
              </div>
            ))
          }
        </Section>

        {/* Big Insider Trades */}
        <Section title="Big Insider Trades" count={bigTrades.length}>
          {bigTrades.length === 0
            ? <div style={S.empty}>No big trades in last 30 days</div>
            : bigTrades.slice(0, 12).map((t: any, i: number) => {
              const isBuy = (t.transaction_type || "").toUpperCase().includes("BUY");
              return (
                <div key={i} style={S.row}>
                  <span style={S.sym}>{t.symbol}</span>
                  <span style={isBuy ? S.pos : S.neg}>
                    {t.transaction_type}
                  </span>
                  <span style={{...S.muted, marginLeft: "auto"}}>
                    Rs.{t.value_cr != null
                      ? Number(t.value_cr).toFixed(1)
                      : t.value != null
                        ? (Number(t.value)/1e7).toFixed(1) : "?"}Cr
                  </span>
                  <span style={S.muted}>{t.name?.slice(0, 18) || ""}</span>
                </div>
              );
            })
          }
        </Section>

        {/* Results Season */}
        <Section title="Results Season" count={results.length}>
          {results.length === 0
            ? <div style={S.empty}>No recent results announcements</div>
            : results.slice(0, 12).map((r: any, i: number) => (
              <div key={i} style={S.row}>
                <span style={S.sym}>{r.symbol}</span>
                <span style={S.muted}>{r.announcement_date}</span>
                <span style={{...S.muted, marginLeft: "auto",
                  maxWidth: 220, overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" as const}}>
                  {r.subject}
                </span>
              </div>
            ))
          }
        </Section>

        {/* Dividend / Corporate Actions */}
        <Section title="Dividend / Bonus / Split" count={divs.length}>
          {divs.length === 0
            ? <div style={S.empty}>No upcoming corporate actions</div>
            : divs.slice(0, 12).map((d: any, i: number) => {
              const kw  = (d.subject || "").toLowerCase();
              const col = kw.includes("bonus") ? "#818cf8"
                        : kw.includes("split") ? "#fbbf24"
                        : "#22c55e";
              return (
                <div key={i} style={S.row}>
                  <span style={S.sym}>{d.symbol}</span>
                  <span style={S.pill(col)}>
                    {kw.includes("bonus") ? "BONUS"
                      : kw.includes("split") ? "SPLIT"
                      : "DIV"}
                  </span>
                  <span style={{...S.muted, marginLeft: "auto"}}>
                    {d.announcement_date}
                  </span>
                </div>
              );
            })
          }
        </Section>

        {/* Upcoming Results */}
        <Section title="Upcoming Results" count={upcoming.length}>
          {upcoming.length === 0
            ? <div style={S.empty}>No upcoming results detected</div>
            : upcoming.slice(0, 12).map((u: any, i: number) => (
              <div key={i} style={S.row}>
                <span style={S.sym}>{u.symbol}</span>
                <span style={S.muted}>last: {u.last_result_date || "?"}</span>
                <span style={{...S.warn, marginLeft: "auto"}}>
                  ~{u.days_since || "?"} days ago
                </span>
              </div>
            ))
          }
        </Section>

        {/* Post-Results Reactions */}
        <Section title="Post-Results Price Reactions" count={reactions.length}>
          {reactions.length === 0
            ? <div style={S.empty}>No reactions data available</div>
            : reactions.slice(0, 10).map((r: any, i: number) => {
              const pct = parseFloat(r.price_reaction_pct || 0);
              return (
                <div key={i} style={S.row}>
                  <span style={S.sym}>{r.symbol}</span>
                  <span style={pct >= 0 ? S.pos : S.neg}>
                    {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                  </span>
                  <span style={S.muted}>{r.announcement_date}</span>
                </div>
              );
            })
          }
        </Section>

      </div>

      {/* LLM Analysis */}
      {data.analysis && (
        <div style={{ ...S.card, marginTop: 20 }}>
          <div style={S.cardHdr}>LLM Analysis</div>
          <pre style={{ fontSize: 12, color: "var(--muted)", whiteSpace: "pre-wrap" as const,
            lineHeight: 1.6, margin: 0 }}>
            {typeof data.analysis === "string"
              ? data.analysis
              : JSON.stringify(data.analysis, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
