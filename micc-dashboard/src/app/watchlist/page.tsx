"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface WatchItem {
  symbol: string;
  name?: string;
  close?: number | null;
  pct_change?: number | null;
  rsi_14?: number | null;
  adx_14?: number | null;
  atr_14_pct?: number | null;
  conviction_score?: number | null;
  screen_tags?: string | null;
  reason?: string;
  added_date?: string;
}
interface WatchData {
  watchlist: WatchItem[];
  timestamp?: string;
  count?: number;
}

const fmt = (v: unknown, d = 2) => v == null ? "--" : Number(v).toFixed(d);
const pct = (v: unknown) => v == null ? "--" : (Number(v)>=0?"+":"") + Number(v).toFixed(2) + "%";
const bull= (v: unknown) => Number(v) >= 0 ? "var(--bull)" : "var(--bear)";

export default function WatchlistPage() {
  const [data, setData]   = useState<WatchData | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");
  const [search, setSrch] = useState("");
  const [sort, setSort]   = useState<keyof WatchItem>("conviction_score");
  const [asc, setAsc]     = useState(false);

  useEffect(() => {
    fetch("/api/watchlist")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" as const },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    input: { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4,
             padding: "4px 10px", fontSize: 11, color: "var(--text)", outline: "none" },
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)",
             background: "var(--surface)", cursor: "pointer", userSelect: "none" as const },
    td:    { padding: "8px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    sym:   { color: "var(--accent)", fontWeight: 700 },
  };

  function mkSort(col: keyof WatchItem) {
    if (sort === col) setAsc(!asc);
    else { setSort(col); setAsc(false); }
  }
  function sortIcon(col: keyof WatchItem) {
    if (sort !== col) return "";
    return asc ? " ^" : " v";
  }

  const items = (data?.watchlist || [])
    .filter(r => !search || r.symbol.toLowerCase().includes(search.toLowerCase()) ||
                            (r.name || "").toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const av = a[sort] ?? 0, bv = b[sort] ?? 0;
      if (typeof av === "number" && typeof bv === "number")
        return asc ? av - bv : bv - av;
      return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>WATCHLIST  /  ACTIVE SIGNALS</span>
        <input
          style={S.input}
          placeholder="search symbol or name..."
          value={search}
          onChange={e => setSrch(e.target.value)}
        />
        {data?.count !== undefined && (
          <span style={{ fontSize: 10, color: "var(--dim)" }}>{data.count} stocks</span>
        )}
        {data?.timestamp && (
          <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>{data.timestamp}</span>
        )}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading watchlist...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>
          Error: {error} -- run: py D:\MICC\agent_zeta.py
        </div>}

        {data && (
          <div style={S.card}>
            <table style={S.tbl}>
              <thead><tr>
                {([
                  ["symbol","SYMBOL"],
                  ["name","NAME"],
                  ["close","CLOSE"],
                  ["pct_change","1D %"],
                  ["rsi_14","RSI"],
                  ["adx_14","ADX"],
                  ["atr_14_pct","ATR%"],
                  ["conviction_score","CONVICTION"],
                  ["screen_tags","TAGS"],
                ] as [keyof WatchItem, string][]).map(([col, label]) => (
                  <th key={col} style={S.th} onClick={() => mkSort(col)}>
                    {label}{sortIcon(col)}
                  </th>
                ))}
              </tr></thead>
              <tbody>
                {items.map((r, i) => (
                  <tr key={r.symbol} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                    <td style={{ ...S.td, ...S.sym }}>{r.symbol}</td>
                    <td style={{ ...S.td, fontSize: 11, color: "var(--dim)" }}>{r.name || "--"}</td>
                    <td style={S.td}>{fmt(r.close)}</td>
                    <td style={{ ...S.td, color: bull(r.pct_change), fontWeight: 600 }}>{pct(r.pct_change)}</td>
                    <td style={{ ...S.td, color: Number(r.rsi_14)>70?"var(--bear)":Number(r.rsi_14)<30?"var(--bull)":"var(--text)" }}>
                      {fmt(r.rsi_14, 1)}
                    </td>
                    <td style={{ ...S.td, color: Number(r.adx_14)>25?"var(--accent)":"var(--dim)" }}>
                      {fmt(r.adx_14, 1)}
                    </td>
                    <td style={S.td}>{fmt(r.atr_14_pct, 2)}{r.atr_14_pct != null ? "%" : ""}</td>
                    <td style={{ ...S.td, color: Number(r.conviction_score)>=70?"var(--bull)":Number(r.conviction_score)>=40?"var(--warn)":"var(--bear)", fontWeight: 700 }}>
                      {fmt(r.conviction_score, 0)}
                    </td>
                    <td style={{ ...S.td, fontSize: 10, color: "var(--info)" }}>{r.screen_tags || "--"}</td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr><td colSpan={9} style={{ padding: 30, textAlign: "center", color: "var(--dim)" }}>
                    No watchlist items -- run py agent_zeta.py
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
