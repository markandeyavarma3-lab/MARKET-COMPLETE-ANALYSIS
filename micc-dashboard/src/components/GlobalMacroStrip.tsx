"use client";

import { useEffect, useState } from "react";

interface GRow { symbol: string; close: number|null; pct_change: number|null; }

const META: Record<string, { label: string; flag: string; invert?: boolean }> = {
  SP500VIX: { label:"VIX",     flag:"⚡", invert:true },
  INDIAVIX: { label:"IVIX",    flag:"⚡", invert:true },
  US10Y:    { label:"US 10Y",  flag:"🇺🇸" },
  DXY:      { label:"DXY",     flag:"💵" },
  USDINR:   { label:"INR",     flag:"₹" },
  Gold:     { label:"Gold",    flag:"🥇" },
  CrudeWTI: { label:"WTI",     flag:"🛢" },
  Bitcoin:  { label:"BTC",     flag:"₿" },
  SPX:      { label:"S&P500",  flag:"🇺🇸" },
  NIFTY50:  { label:"Nifty",   flag:"🇮🇳" },
};

const SYMBOLS = ["NIFTY50","SPX","INDIAVIX","SP500VIX","US10Y","DXY","USDINR","Gold","CrudeWTI","Bitcoin"];

const fmtV = (v: number|null, sym: string) => {
  if (v == null) return "—";
  if (sym === "US10Y") return v.toFixed(2) + "%";
  if (sym === "USDINR") return v.toFixed(2);
  if (v >= 10000) return (v / 1000).toFixed(1) + "k";
  if (v >= 1000)  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return v.toFixed(2);
};

export default function GlobalMacroStrip() {
  const [rows, setRows]   = useState<GRow[]>([]);
  const [asOf, setAsOf]   = useState("");
  const [loading, setL]   = useState(true);

  useEffect(() => {
    fetch("/api/global?days=2")
      .then(r => r.json())
      .then(d => {
        const bySymbol: Record<string, GRow> = {};
        for (const r of (d.rows || [])) bySymbol[r.symbol] = r;
        setRows(SYMBOLS.map(s => bySymbol[s] || { symbol: s, close: null, pct_change: null }));
        setAsOf(d.dates?.[0] || "");
      })
      .catch(() => {})
      .finally(() => setL(false));
  }, []);

  if (loading) return (
    <div style={{ height: 40, background: "#080d14", borderBottom: "1px solid #1e293b" }} />
  );

  return (
    <div style={{
      background: "#080d14",
      borderBottom: "1px solid #1e293b",
      padding: "6px 28px",
      display: "flex",
      gap: 0,
      overflowX: "auto",
      alignItems: "center",
    }}>
      {rows.map((r, i) => {
        const meta  = META[r.symbol] || { label: r.symbol, flag: "🌍" };
        const chg   = r.pct_change;
        const inv   = meta.invert;
        const color = chg == null ? "#475569"
                    : (inv ? chg < 0 : chg > 0) ? "#22c55e"
                    : chg === 0 ? "#475569" : "#ef4444";
        const pct   = chg == null ? "" : (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%";
        return (
          <div key={r.symbol} style={{
            display: "flex", alignItems: "center", gap: 5,
            padding: "4px 14px",
            borderRight: i < rows.length - 1 ? "1px solid #1e293b" : "none",
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 12 }}>{meta.flag}</span>
            <span style={{ fontSize: 10, color: "#475569" }}>{meta.label}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#e2e8f0" }}>
              {fmtV(r.close, r.symbol)}
            </span>
            {pct && (
              <span style={{ fontSize: 10, fontWeight: 700, color }}>{pct}</span>
            )}
          </div>
        );
      })}
      {asOf && (
        <span style={{ fontSize: 9, color: "#334155", marginLeft: "auto", flexShrink: 0 }}>
          {asOf}
        </span>
      )}
    </div>
  );
}
