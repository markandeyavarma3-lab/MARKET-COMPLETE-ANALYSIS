"use client";
import NavBar from "@/components/NavBar";

import { useEffect, useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface GlobalRow {
  symbol: string; date: string; close: number | null; pct_change: number | null;
  ret_5d?: number | null;
}
interface HistRow { date: string; close: number; pct_change: number | null; }

// ── Universe metadata (category + display name) ───────────────────────────────
const META: Record<string, { name: string; cat: string; flag?: string }> = {
  SPX:         { name: "S&P 500",         cat: "US",        flag: "🇺🇸" },
  NDX:         { name: "Nasdaq 100",       cat: "US",        flag: "🇺🇸" },
  DJIA:        { name: "Dow Jones",        cat: "US",        flag: "🇺🇸" },
  RUT:         { name: "Russell 2000",     cat: "US",        flag: "🇺🇸" },
  SP500VIX:    { name: "VIX",              cat: "Volatility",flag: "⚡" },
  INDIAVIX:    { name: "India VIX",        cat: "Volatility",flag: "⚡" },
  NIFTY50:     { name: "Nifty 50",         cat: "India",     flag: "🇮🇳" },
  NIFTYBANK:   { name: "Nifty Bank",       cat: "India",     flag: "🇮🇳" },
  SENSEX:      { name: "Sensex",           cat: "India",     flag: "🇮🇳" },
  NIFTYIT:     { name: "Nifty IT",         cat: "India",     flag: "🇮🇳" },
  NIFTYMID100: { name: "Nifty Midcap",     cat: "India",     flag: "🇮🇳" },
  NIFTYFMCG:   { name: "Nifty FMCG",       cat: "India",     flag: "🇮🇳" },
  NIFTYAUTO:   { name: "Nifty Auto",        cat: "India",     flag: "🇮🇳" },
  DAX:         { name: "DAX",              cat: "Europe",    flag: "🇩🇪" },
  FTSE100:     { name: "FTSE 100",         cat: "Europe",    flag: "🇬🇧" },
  CAC40:       { name: "CAC 40",           cat: "Europe",    flag: "🇫🇷" },
  EUROSTOXX50: { name: "Euro Stoxx 50",    cat: "Europe",    flag: "🇪🇺" },
  AEX:         { name: "AEX",              cat: "Europe",    flag: "🇳🇱" },
  SMI:         { name: "SMI",              cat: "Europe",    flag: "🇨🇭" },
  IBEX35:      { name: "IBEX 35",          cat: "Europe",    flag: "🇪🇸" },
  MIB:         { name: "FTSE MIB",         cat: "Europe",    flag: "🇮🇹" },
  Nikkei225:   { name: "Nikkei 225",       cat: "Asia",      flag: "🇯🇵" },
  HangSeng:    { name: "Hang Seng",        cat: "Asia",      flag: "🇭🇰" },
  Shanghai:    { name: "Shanghai",         cat: "Asia",      flag: "🇨🇳" },
  CSI300:      { name: "CSI 300",          cat: "Asia",      flag: "🇨🇳" },
  Kospi:       { name: "KOSPI",            cat: "Asia",      flag: "🇰🇷" },
  ASX200:      { name: "ASX 200",          cat: "Asia",      flag: "🇦🇺" },
  Taiwan:      { name: "Taiwan",           cat: "Asia",      flag: "🇹🇼" },
  Straits:     { name: "Straits Times",    cat: "Asia",      flag: "🇸🇬" },
  Jakarta:     { name: "Jakarta",          cat: "Asia",      flag: "🇮🇩" },
  Bovespa:     { name: "Bovespa",          cat: "LatAm",     flag: "🇧🇷" },
  IPC:         { name: "IPC Mexico",       cat: "LatAm",     flag: "🇲🇽" },
  Gold:        { name: "Gold",             cat: "Commodity", flag: "🥇" },
  Silver:      { name: "Silver",           cat: "Commodity", flag: "🥈" },
  CrudeWTI:    { name: "Crude WTI",        cat: "Commodity", flag: "🛢" },
  BrentCrude:  { name: "Brent Crude",      cat: "Commodity", flag: "🛢" },
  NatGas:      { name: "Natural Gas",      cat: "Commodity", flag: "🔥" },
  Copper:      { name: "Copper",           cat: "Commodity", flag: "🟤" },
  Wheat:       { name: "Wheat",            cat: "Commodity", flag: "🌾" },
  Palladium:   { name: "Palladium",        cat: "Commodity", flag: "⚗️" },
  DXY:         { name: "DXY (USD Index)",  cat: "FX",        flag: "💵" },
  USDINR:      { name: "USD/INR",          cat: "FX",        flag: "₹"  },
  EURUSD:      { name: "EUR/USD",          cat: "FX",        flag: "🇪🇺" },
  USDJPY:      { name: "USD/JPY",          cat: "FX",        flag: "🇯🇵" },
  GBPUSD:      { name: "GBP/USD",          cat: "FX",        flag: "🇬🇧" },
  USDCNY:      { name: "USD/CNY",          cat: "FX",        flag: "🇨🇳" },
  USDBRL:      { name: "USD/BRL",          cat: "FX",        flag: "🇧🇷" },
  US10Y:       { name: "US 10Y Yield",     cat: "Rates",     flag: "📈" },
  US2Y:        { name: "US 2Y Yield",      cat: "Rates",     flag: "📈" },
  US30Y:       { name: "US 30Y Yield",     cat: "Rates",     flag: "📈" },
  Bitcoin:     { name: "Bitcoin",          cat: "Crypto",    flag: "₿"  },
  Ethereum:    { name: "Ethereum",         cat: "Crypto",    flag: "Ξ"  },
};

const CATS = ["All","US","India","Europe","Asia","LatAm","Commodity","FX","Rates","Volatility","Crypto"];

// ── Helpers ───────────────────────────────────────────────────────────────────
const pct  = (v: number | null | undefined) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
const clr  = (v: number | null | undefined, invert = false) =>
  v == null ? "var(--muted)" : (invert ? v < 0 : v > 0) ? "var(--pos)" : v === 0 ? "var(--muted)" : "var(--neg)";
const fmtClose = (v: number | null, sym: string) => {
  if (v == null) return "—";
  const cat = META[sym]?.cat;
  if (cat === "Rates") return `${v.toFixed(2)}%`;
  if (["USDINR","EURUSD","USDJPY","GBPUSD","USDCNY","USDBRL"].includes(sym))
    return v.toFixed(4);
  return v >= 1000 ? v.toLocaleString("en-IN", { maximumFractionDigits: 0 })
       : v >= 100  ? v.toFixed(2)
       : v.toFixed(4);
};

// ── Mini sparkline SVG ────────────────────────────────────────────────────────
function Spark({ hist, color }: { hist: number[]; color: string }) {
  if (!hist || hist.length < 2) return <span style={{ color: "var(--border2)" }}>—</span>;
  const W = 60, H = 20;
  const mn = Math.min(...hist), mx = Math.max(...hist), rng = mx - mn || 1;
  const pts = hist.map((v, i) =>
    `${(i / (hist.length - 1)) * W},${H - ((v - mn) / rng) * H}`
  ).join(" ");
  return (
    <svg width={W} height={H} style={{ verticalAlign: "middle" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

// ── Global index row ──────────────────────────────────────────────────────────
function IndexRow({
  row, onClick, selected,
}: {
  row: GlobalRow; onClick: () => void; selected: boolean;
}) {
  const meta  = META[row.symbol] || { name: row.symbol, cat: "Other", flag: "🌍" };
  const dClr  = clr(row.pct_change);
  const wClr  = clr(row.ret_5d);
  const isVix = meta.cat === "Volatility";

  return (
    <tr onClick={onClick} style={{
      borderBottom: "1px solid #1e293b", cursor: "pointer",
      background: selected ? "rgba(88,166,255,0.1)" : "transparent",
      transition: "background 0.15s",
    }}>
      <td style={{ padding: "8px 10px", fontFamily: "monospace", color: "var(--accent)", fontSize: 12, fontWeight: 700 }}>
        {meta.flag} {row.symbol}
      </td>
      <td style={{ padding: "8px 10px", color: "var(--muted)", fontSize: 12 }}>
        {meta.name}
      </td>
      <td style={{ padding: "8px 10px", color: "var(--muted)", fontSize: 11 }}>
        <span style={{
          background: "var(--card)", borderRadius: 4,
          padding: "1px 6px", fontSize: 10,
        }}>{meta.cat}</span>
      </td>
      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, fontSize: 13, color: "var(--text)" }}>
        {fmtClose(row.close, row.symbol)}
      </td>
      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, fontSize: 13,
        color: isVix ? clr(row.pct_change, true) : dClr }}>
        {pct(row.pct_change)}
      </td>
      <td style={{ padding: "8px 10px", textAlign: "right", fontSize: 12,
        color: isVix ? clr(row.ret_5d, true) : wClr }}>
        {pct(row.ret_5d)}
      </td>
      <td style={{ padding: "8px 10px", fontSize: 11, color: "var(--muted)" }}>{row.date}</td>
    </tr>
  );
}

// ── Mini chart for selected symbol ────────────────────────────────────────────
function SymbolChart({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const [hist, setHist]     = useState<HistRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState<number | null>(null);
  const [lockA, setLockA]   = useState<number | null>(null);
  const [lockB, setLockB]   = useState<number | null>(null);
  const meta = META[symbol] || { name: symbol, cat: "Other", flag: "🌍" };

  useEffect(() => {
    setLoading(true);
    fetch(`/api/global/${symbol}?days=252`)
      .then(r => r.json())
      .then(d => { setHist(d.rows || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return (
    <div style={{ padding: 20, color: "var(--muted)", fontSize: 13 }}>Loading {symbol}…</div>
  );

  if (!hist.length) return (
    <div style={{ padding: 20, color: "var(--muted)" }}>No data for {symbol}</div>
  );

  const closes = hist.map(h => h.close).filter(Boolean) as number[];
  const W = 560, H = 140, PAD = 36;
  const mn  = Math.min(...closes), mx = Math.max(...closes), rng = mx - mn || 1;
  const pts = hist.map((h, i) => {
    const x = PAD + (i / (hist.length - 1)) * (W - 2 * PAD);
    const y = H - PAD - ((h.close - mn) / rng) * (H - 2 * PAD);
    return `${x},${y}`;
  }).join(" ");

  const handleClick = (i: number) => {
    if (lockA === null) { setLockA(i); return; }
    if (lockB === null && i !== lockA) { setLockB(i); return; }
    setLockA(null); setLockB(null);
  };

  const last = hist[hist.length - 1];
  const firstClose = hist[0]?.close;
  const totalRet = firstClose && last?.close
    ? ((last.close / firstClose - 1) * 100).toFixed(2) : null;

  const deltaVal = lockA != null && lockB != null
    ? ((hist[lockB]?.close / hist[lockA]?.close - 1) * 100).toFixed(2)
    : null;

  return (
    <div style={{
      background: "var(--card)", border: "1px solid #334155",
      borderRadius: 4, padding: "16px 20px", marginBottom: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 16 }}>{meta.flag}</span>
        <span style={{ fontWeight: 800, fontSize: 15, color: "var(--text)" }}>
          {symbol} — {meta.name}
        </span>
        <span style={{ fontSize: 13, color: "var(--accent)", marginLeft: 8 }}>
          {fmtClose(last?.close, symbol)}
        </span>
        {totalRet && (
          <span style={{ fontSize: 12, color: parseFloat(totalRet) >= 0 ? "var(--pos)" : "var(--neg)" }}>
            ({parseFloat(totalRet) >= 0 ? "+" : ""}{totalRet}% 1y)
          </span>
        )}
        <button onClick={onClose} style={{
          marginLeft: "auto", background: "none", border: "none",
          color: "var(--muted)", cursor: "pointer", fontSize: 18,
        }}>✕</button>
      </div>

      <svg width={W} height={H} style={{ cursor: "crosshair", overflow: "visible" }}
        onMouseLeave={() => setHovered(null)}>
        {/* Chart line */}
        <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={1.5} />

        {/* Hover + lock dots */}
        {hist.map((h, i) => {
          const x = PAD + (i / (hist.length - 1)) * (W - 2 * PAD);
          const y = H - PAD - ((h.close - mn) / rng) * (H - 2 * PAD);
          const isA = lockA === i, isB = lockB === i, isH = hovered === i;
          if (!isA && !isB && !isH) return null;
          return (
            <circle key={i} cx={x} cy={y} r={isH ? 3 : 5}
              fill={isA ? "var(--warn)" : isB ? "var(--purple)" : "var(--accent)"}
              stroke="var(--bg)" strokeWidth={1}
            />
          );
        })}

        {/* Invisible hit area */}
        {hist.map((h, i) => {
          const x = PAD + (i / (hist.length - 1)) * (W - 2 * PAD);
          const y = H - PAD - ((h.close - mn) / rng) * (H - 2 * PAD);
          return (
            <rect key={i} x={x - 6} y={0} width={12} height={H}
              fill="transparent"
              onMouseEnter={() => setHovered(i)}
              onClick={() => handleClick(i)}
            />
          );
        })}

        {/* Y axis labels */}
        {[0, 0.5, 1].map(f => {
          const val = mn + f * rng;
          const y   = H - PAD - f * (H - 2 * PAD);
          return (
            <text key={f} x={PAD - 4} y={y + 4}
              fontSize={9} fill="var(--muted)" textAnchor="end">
              {val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(1)}
            </text>
          );
        })}
      </svg>

      {/* Tooltip + lock info */}
      <div style={{ fontSize: 12, marginTop: 6, display: "flex", gap: 16, flexWrap: "wrap" }}>
        {hovered != null && (
          <span style={{ color: "var(--accent)" }}>
            {hist[hovered]?.date}  {fmtClose(hist[hovered]?.close, symbol)}
            {"  "}
            <span style={{ color: clr(hist[hovered]?.pct_change) }}>
              {pct(hist[hovered]?.pct_change)}
            </span>
          </span>
        )}
        {lockA != null && (
          <span style={{ color: "var(--warn)" }}>
            A: {hist[lockA]?.date} {fmtClose(hist[lockA]?.close, symbol)}
          </span>
        )}
        {lockB != null && (
          <span style={{ color: "var(--purple)" }}>
            B: {hist[lockB]?.date} {fmtClose(hist[lockB]?.close, symbol)}
          </span>
        )}
        {deltaVal && (
          <span style={{ fontWeight: 700, color: parseFloat(deltaVal) >= 0 ? "var(--pos)" : "var(--neg)" }}>
            Δ {parseFloat(deltaVal) >= 0 ? "+" : ""}{deltaVal}%
          </span>
        )}
        {(lockA != null || lockB != null) && (
          <button onClick={() => { setLockA(null); setLockB(null); }}
            style={{ fontSize: 10, color: "var(--muted)", background: "none",
              border: "none", cursor: "pointer" }}>✕ clear</button>
        )}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═════════════════════════════════════════════════════════════════════════════
export default function GlobalPage() {
  const [rows,     setRows]     = useState<GlobalRow[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [cat,      setCat]      = useState("All");
  const [sort,     setSort]     = useState<"pct_change" | "ret_5d" | "symbol" | "cat">("cat");
  const [sortDir,  setSortDir]  = useState<1 | -1>(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [search,   setSearch]   = useState("");
  const [lastUpd,  setLastUpd]  = useState("");

  const load = useCallback(() => {
    setLoading(true);
    fetch("/api/global?days=5")
      .then(r => r.json())
      .then(d => {
        setRows(d.rows || []);
        setLastUpd(d.dates?.[0] || "");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, []);

  // Filter + sort
  const filtered = rows
    .filter(r => {
      const m = META[r.symbol] || { cat: "Other" };
      if (cat !== "All" && m.cat !== cat) return false;
      if (search && !r.symbol.toLowerCase().includes(search.toLowerCase())
        && !(META[r.symbol]?.name || "").toLowerCase().includes(search.toLowerCase()))
        return false;
      return true;
    })
    .sort((a, b) => {
      const av = sort === "pct_change" ? (a.pct_change ?? -999)
               : sort === "ret_5d"     ? (a.ret_5d ?? -999)
               : sort === "symbol"     ? a.symbol
               : (META[a.symbol]?.cat || "");
      const bv = sort === "pct_change" ? (b.pct_change ?? -999)
               : sort === "ret_5d"     ? (b.ret_5d ?? -999)
               : sort === "symbol"     ? b.symbol
               : (META[b.symbol]?.cat || "");
      return av < bv ? -sortDir : av > bv ? sortDir : 0;
    });

  // Summary stats
  const risers  = rows.filter(r => (r.pct_change ?? 0) > 0).length;
  const fallers = rows.filter(r => (r.pct_change ?? 0) < 0).length;
  const avgChg  = rows.length
    ? rows.reduce((s, r) => s + (r.pct_change ?? 0), 0) / rows.length : 0;
  const topGainer = [...rows].sort((a, b) => (b.pct_change ?? -99) - (a.pct_change ?? -99))[0];
  const topLoser  = [...rows].sort((a, b) => (a.pct_change ?? 99)  - (b.pct_change ?? 99))[0];

  const toggleSort = (col: typeof sort) => {
    if (sort === col) setSortDir(d => (d === 1 ? -1 : 1));
    else { setSort(col); setSortDir(-1); }
  };
  const sortArrow = (col: string) => sort === col ? (sortDir === -1 ? " ▼" : " ▲") : "";

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg)",
      color: "var(--text)", fontFamily: "'Space Grotesk',sans-serif",
    }}>
      <NavBar />
      {/* ── Header ── */}
      <div style={{
        padding: "18px 28px 14px", borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", flexWrap: "wrap", gap: 16,
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "var(--text)" }}>
            🌍 Global Markets
          </h1>
          <p style={{ margin: "3px 0 0", fontSize: 11, color: "var(--muted)" }}>
            52 symbols · Equities · Commodities · FX · Rates · Crypto
            {lastUpd && ` · Last: ${lastUpd}`}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          padding: "6px 14px", background: "var(--border2)", border: "none",
          borderRadius: 7, color: "var(--muted)", cursor: "pointer", fontSize: 12,
        }}>↺ Refresh</button>

        {/* Summary chips */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, flexWrap: "wrap" }}>
          {[
            { label: "Total",  value: rows.length,  color: "var(--accent)" },
            { label: "Rising", value: risers,        color: "var(--pos)" },
            { label: "Falling",value: fallers,       color: "var(--neg)" },
            { label: "Avg Chg",value: `${avgChg >= 0 ? "+" : ""}${avgChg.toFixed(2)}%`,
              color: avgChg >= 0 ? "var(--pos)" : "var(--neg)" },
          ].map((s, i) => (
            <div key={i} style={{
              textAlign: "center", padding: "6px 12px",
              background: "var(--card)", borderRadius: 8,
              border: `1px solid ${s.color}33`,
            }}>
              <div style={{ fontSize: 15, fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 10, color: "var(--muted)" }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Top movers strip ── */}
      {topGainer && topLoser && (
        <div style={{
          padding: "8px 28px", background: "var(--bg)",
          display: "flex", gap: 20, fontSize: 12, borderBottom: "1px solid #1e293b",
        }}>
          <span style={{ color: "var(--muted)" }}>Top mover:</span>
          <span style={{ color: "var(--pos)", fontWeight: 700 }}>
            {META[topGainer.symbol]?.flag} {topGainer.symbol} {pct(topGainer.pct_change)}
          </span>
          <span style={{ color: "var(--muted)" }}>Biggest drop:</span>
          <span style={{ color: "var(--neg)", fontWeight: 700 }}>
            {META[topLoser.symbol]?.flag} {topLoser.symbol} {pct(topLoser.pct_change)}
          </span>
        </div>
      )}

      <div style={{ padding: "16px 28px" }}>
        {/* ── Selected chart ── */}
        {selected && (
          <SymbolChart symbol={selected} onClose={() => setSelected(null)} />
        )}

        {/* ── Category tabs + search ── */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14, alignItems: "center" }}>
          {CATS.map(c => (
            <button key={c} onClick={() => setCat(c)} style={{
              padding: "5px 12px", borderRadius: 999, fontSize: 11, fontWeight: 700,
              background: cat === c ? "var(--accent)" : "var(--card)",
              color: cat === c ? "#fff" : "var(--muted)",
              border: "none", cursor: "pointer",
            }}>{c}</button>
          ))}
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            style={{
              marginLeft: "auto", padding: "5px 12px",
              background: "var(--card)", border: "1px solid #334155",
              borderRadius: 7, color: "var(--text)", fontSize: 12, outline: "none", width: 140,
            }}
          />
        </div>

        {/* ── Table ── */}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #334155" }}>
                {[
                  ["symbol",     "Symbol",    "left"],
                  ["name",       "Name",      "left"],
                  ["cat",        "Category",  "left"],
                  ["close",      "Price",     "right"],
                  ["pct_change", "Day %",     "right"],
                  ["ret_5d",     "5d %",      "right"],
                  ["date",       "Date",      "right"],
                ].map(([col, label, align]) => (
                  <th key={col}
                    onClick={() => ["symbol","pct_change","ret_5d","cat"].includes(col)
                      ? toggleSort(col as any) : undefined}
                    style={{
                      padding: "8px 10px", textAlign: align as any,
                      color: "var(--muted)", fontSize: 11, fontWeight: 600,
                      cursor: ["symbol","pct_change","ret_5d","cat"].includes(col)
                        ? "pointer" : "default",
                      userSelect: "none",
                    }}>
                    {label}{sortArrow(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #1e293b" }}>
                      {Array.from({ length: 7 }).map((_, j) => (
                        <td key={j} style={{ padding: "10px", height: 36 }}>
                          <div style={{
                            background: "var(--card)", borderRadius: 4,
                            height: 12, opacity: 0.5,
                          }} />
                        </td>
                      ))}
                    </tr>
                  ))
                : filtered.map(r => (
                    <IndexRow
                      key={r.symbol}
                      row={r}
                      selected={selected === r.symbol}
                      onClick={() => setSelected(s => s === r.symbol ? null : r.symbol)}
                    />
                  ))
              }
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 && (
          <div style={{ padding: "40px 0", textAlign: "center", color: "var(--muted)" }}>
            No symbols match filters. Try <strong style={{ color: "var(--accent)" }}>All</strong> category.
          </div>
        )}
      </div>
    </div>
  );
}
