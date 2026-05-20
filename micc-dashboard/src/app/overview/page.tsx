"use client";
import NavBar from "@/components/NavBar";

import { useEffect, useState, useCallback } from "react";
import TodayPatternsWidget from "@/components/TodayPatternsWidget";
import GlobalMacroStrip    from "@/components/GlobalMacroStrip";

// ── Types ─────────────────────────────────────────────────────────────────────
interface OverviewData {
  date?: string;
  nifty?: { close: number; pct_change: number };
  niftybank?: { close: number; pct_change: number };
  advances?: number; declines?: number; unchanged?: number;
  total_volume_cr?: number;
  top_gainers?: { symbol: string; pct_change: number }[];
  top_losers?:  { symbol: string; pct_change: number }[];
  signals_today?: number;
  watchlist_alerts?: number;
}

interface AgentCard {
  label: string; icon: string; value: string; sub: string; color: string; href: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const pct = (v: number | null | undefined) =>
  v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
const clr = (v: number | null | undefined) =>
  v == null ? "var(--muted)" : v >= 0 ? "var(--pos)" : "var(--neg)";
const fmt = (v: number | null | undefined, d = 0) =>
  v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d });

// ── Mini stat chip ────────────────────────────────────────────────────────────
function Chip({ label, value, sub, color, href }: AgentCard) {
  return (
    <a href={href} style={{ textDecoration: "none" }}>
      <div style={{
        background: "var(--card)", border: `1px solid ${color}33`,
        borderRadius: 6, padding: "14px 18px",
        cursor: "pointer", transition: "border-color 0.2s",
      }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = color + "88")}
        onMouseLeave={e => (e.currentTarget.style.borderColor = color + "33")}
      >
        <div style={{ fontSize: 18, marginBottom: 6 }}>{label.split(" ")[0]}</div>
        <div style={{ fontSize: 20, fontWeight: 800, color }}>{value}</div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{sub}</div>
      </div>
    </a>
  );
}

// ── Index bar ────────────────────────────────────────────────────────────────
function IndexBar({ name, close_, chg }: { name: string; close_: number | null; chg: number | null }) {
  const c = clr(chg);
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 16px", borderBottom: "1px solid #0f172a",
    }}>
      <span style={{ fontSize: 12, color: "var(--muted)", minWidth: 90 }}>{name}</span>
      <span style={{ fontSize: 16, fontWeight: 800, color: "var(--text)" }}>
        {fmt(close_, 2)}
      </span>
      <span style={{ fontSize: 13, fontWeight: 700, color: c, marginLeft: "auto" }}>
        {pct(chg)}
      </span>
    </div>
  );
}

// ── Breadth donut ─────────────────────────────────────────────────────────────
function BreadthBar({ advances, declines, unchanged }: { advances: number; declines: number; unchanged: number }) {
  const total = advances + declines + unchanged || 1;
  const ap = Math.round(advances / total * 100);
  const dp = Math.round(declines / total * 100);
  return (
    <div style={{ padding: "12px 16px" }}>
      <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 8, letterSpacing: 0.5 }}>
        MARKET BREADTH
      </div>
      <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 8 }}>
        <div style={{ width: `${ap}%`, background: "var(--pos)" }} />
        <div style={{ width: `${dp}%`, background: "var(--neg)" }} />
        <div style={{ flex: 1, background: "var(--border2)" }} />
      </div>
      <div style={{ display: "flex", gap: 16, fontSize: 11 }}>
        <span style={{ color: "var(--pos)" }}>▲ {advances} adv</span>
        <span style={{ color: "var(--neg)" }}>▼ {declines} dec</span>
        <span style={{ color: "var(--muted)" }}>{unchanged} unch</span>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═════════════════════════════════════════════════════════════════════════════
export default function OverviewPage() {
  const [data,    setData]    = useState<OverviewData>({});
  const [loading, setLoading] = useState(true);
  const [iota,    setIota]    = useState<any>(null);
  const [alpha,   setAlpha]   = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Load overview data from market_snapshot
      const r = await fetch("/api/overview");
      const d = await r.json();
      setData(d);
    } catch {}

    // Load Iota (global intelligence) report
    try {
      const r2 = await fetch("/api/iota");
      const d2 = await r2.json();
      setIota(d2);
    } catch {}

    // Load Alpha (market pulse) report
    try {
      const r3 = await fetch("/api/alpha");
      const d3 = await r3.json();
      setAlpha(d3);
    } catch {}

    setLoading(false);
  }, []);

  useEffect(() => { load(); }, []);

  const AGENT_CHIPS: AgentCard[] = [
    {
      label:  "📊 Patterns",
      value:  "v3",
      sub:    "3d-60d seasonal",
      color:  "var(--accent)",
      href:   "/patterns-v3",
    },
    {
      label:  "🌍 Global",
      value:  "52",
      sub:    "indices + FX + crypto",
      color:  "var(--pos)",
      href:   "/global",
    },
    {
      label:  "⚖️ Compare",
      value:  "5 stocks",
      sub:    "side-by-side analysis",
      color:  "#f472b6",
      href:   "/compare",
    },
    {
      label:  "🏢 Eta",
      value:  "Events",
      sub:    "results · insider · divs",
      color:  "var(--warn)",
      href:   "/eta",
    },
    {
      label:  "🔔 Alerts",
      value:  "Active",
      sub:    "price · RSI · volume",
      color:  "var(--purple)",
      href:   "/alerts",
    },
    {
      label:  "📈 Macro",
      value:  "Rates",
      sub:    "yield curve · FX · cmdty",
      color:  "var(--pos)",
      href:   "/macro",
    },
  ];

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      color: "var(--text)",
      fontFamily: "monospace",
    }}>
      <NavBar />
      {/* Global macro ticker strip */}
      <GlobalMacroStrip />

      {/* Header */}
      <div style={{
        padding: "18px 28px 14px",
        borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "var(--text)" }}>
            MICC Overview
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--muted)" }}>
            Market Intelligence Command Centre
            {data.date ? ` · ${data.date}` : ""}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          marginLeft: "auto", padding: "6px 14px",
          background: "var(--border2)", border: "none",
          borderRadius: 7, color: "var(--muted)",
          cursor: "pointer", fontSize: 12,
        }}>
          {loading ? "Loading..." : "↺ Refresh"}
        </button>
      </div>

      <div style={{ padding: "20px 28px" }}>

        {/* ── Row 1: Quick nav chips ── */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(6, 1fr)",
          gap: 12, marginBottom: 20,
        }}>
          {AGENT_CHIPS.map(c => <Chip key={c.href} {...c} />)}
        </div>

        {/* ── Row 2: Markets + Breadth + Patterns ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: 18, marginBottom: 18 }}>

          {/* Indian indices */}
          <div style={{
            background: "var(--card)", border: "1px solid #334155",
            borderRadius: 6, overflow: "hidden",
          }}>
            <div style={{ padding: "11px 16px", borderBottom: "1px solid #334155" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)",
                letterSpacing: 0.8, textTransform: "uppercase" }}>🇮🇳 Indian Markets</span>
            </div>
            <IndexBar name="Nifty 50"   close_={data.nifty?.close ?? null}     chg={data.nifty?.pct_change ?? null} />
            <IndexBar name="Bank Nifty" close_={data.niftybank?.close ?? null} chg={data.niftybank?.pct_change ?? null} />
            {data.advances != null && (
              <BreadthBar
                advances={data.advances}
                declines={data.declines ?? 0}
                unchanged={data.unchanged ?? 0}
              />
            )}
          </div>

          {/* Top movers */}
          <div style={{
            background: "var(--card)", border: "1px solid #334155",
            borderRadius: 6, overflow: "hidden",
          }}>
            <div style={{ padding: "11px 16px", borderBottom: "1px solid #334155" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)",
                letterSpacing: 0.8, textTransform: "uppercase" }}>🔥 Top Movers</span>
            </div>
            {(data.top_gainers || []).slice(0, 4).map((g, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "6px 14px", borderBottom: "1px solid #0f172a",
              }}>
                <span style={{ fontSize: 12, fontFamily: "monospace", color: "var(--accent)" }}>
                  {g.symbol}
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--pos)" }}>
                  {pct(g.pct_change)}
                </span>
              </div>
            ))}
            <div style={{ padding: "4px 14px", background: "var(--bg)" }}>
              <span style={{ fontSize: 9, color: "var(--border2)" }}>TOP LOSERS</span>
            </div>
            {(data.top_losers || []).slice(0, 4).map((g, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                padding: "6px 14px", borderBottom: "1px solid #0f172a",
              }}>
                <span style={{ fontSize: 12, fontFamily: "monospace", color: "var(--accent)" }}>
                  {g.symbol}
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--neg)" }}>
                  {pct(g.pct_change)}
                </span>
              </div>
            ))}
          </div>

          {/* Today's patterns widget */}
          <TodayPatternsWidget minAccuracy={65} minScore={5} limit={15} />
        </div>

        {/* ── Row 3: LLM summaries from agents ── */}
        {(iota || alpha) && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
            {alpha && (
              <div style={{
                background: "var(--card)", border: "1px solid #334155",
                borderRadius: 6, padding: "16px 20px",
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)",
                  letterSpacing: 0.8, marginBottom: 10, textTransform: "uppercase" }}>
                  🤖 Alpha — Market Pulse
                </div>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text)", lineHeight: 1.7 }}>
                  {String(alpha.analysis || alpha.verdict || "No analysis available.").slice(0, 400)}
                </p>
                <a href="/overview" style={{ fontSize: 11, color: "var(--accent)", marginTop: 8, display: "block" }}>
                  Full report →
                </a>
              </div>
            )}
            {iota && (
              <div style={{
                background: "var(--card)", border: "1px solid #334155",
                borderRadius: 6, padding: "16px 20px",
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)",
                  letterSpacing: 0.8, marginBottom: 10, textTransform: "uppercase" }}>
                  🧠 Iota — Global Intelligence
                </div>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text)", lineHeight: 1.7 }}>
                  {String(iota.analysis || iota.verdict || "No analysis available.").slice(0, 400)}
                </p>
                <a href="/deep" style={{ fontSize: 11, color: "var(--accent)", marginTop: 8, display: "block" }}>
                  Deep analysis →
                </a>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
