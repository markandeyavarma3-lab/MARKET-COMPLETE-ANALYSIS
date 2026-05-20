"use client";
import { useState, useEffect } from "react";

function inferCategory(name: string): string {
  const n = (name ?? "").toLowerCase();
  if (n.includes("liquid") || n.includes("overnight") || n.includes("money market")) return "Liquid";
  if (n.includes("elss") || n.includes("tax saver"))                                  return "ELSS";
  if (n.includes("small cap") || n.includes("smallcap"))                              return "Small Cap";
  if (n.includes("mid cap") || n.includes("midcap"))                                  return "Mid Cap";
  if (n.includes("large & mid") || n.includes("large and mid"))                       return "Large & Mid";
  if (n.includes("large cap") || n.includes("largecap") || n.includes("bluechip"))   return "Large Cap";
  if (n.includes("balanced") || n.includes("hybrid") || n.includes("aggressive"))    return "Hybrid";
  if (n.includes("gilt") || n.includes("g-sec") || n.includes("gsec") ||
      n.includes("bond") || n.includes("income") || n.includes("debt"))              return "Debt";
  if (n.includes("international") || n.includes("global") || n.includes("usa") ||
      n.includes("nasdaq") || n.includes("s&p"))                                      return "Intl";
  if (n.includes("gold") || n.includes("silver"))                                     return "Commodity";
  return "Other";
}

const CAT_COLORS: Record<string,string> = {
  "Liquid":    "#58a6ff",
  "ELSS":      "#26c485",
  "Small Cap": "#f0883e",
  "Mid Cap":   "#e3b341",
  "Large & Mid":"#79c0ff",
  "Large Cap": "#56d364",
  "Hybrid":    "#d2a8ff",
  "Debt":      "#8b949e",
  "Intl":      "#ffa657",
  "Commodity": "#f78166",
  "Other":     "#6e7681",
};

function CatBadge({ name }: { name: string }) {
  const cat   = inferCategory(name);
  const color = CAT_COLORS[cat] ?? "#6e7681";
  return (
    <span style={{
      fontSize: 8, padding: "1px 5px", marginLeft: 5,
      background: color + "22", border: `1px solid ${color}55`,
      borderRadius: 3, color, fontFamily: "monospace", whiteSpace: "nowrap",
    }}>{cat.toUpperCase()}</span>
  );
}

function fmtNav(v: number): string {
  return Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}
function fmtPct(v: number | null | undefined): string {
  if (v == null) return "--";
  return (v > 0 ? "+" : "") + Number(v).toFixed(3) + "%";
}
function truncate(s: string, n: number): string {
  return s && s.length > n ? s.slice(0, n - 1) + "." : (s ?? "--");
}

export default function MFPanel() {
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [tab,    setTab]    = useState<"top" | "gainers" | "categories">("top");

  useEffect(() => {
    fetch("/api/mf", { cache: "no-store" })
      .then(r => r.json()).then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ padding: 40, color: "var(--dim)", fontFamily: "monospace" }}>
      Loading MF data...
    </div>
  );
  if (!data || data.error) return (
    <div style={{ padding: 40, color: "var(--neg)", fontFamily: "monospace" }}>
      {data?.error ?? "No MF data."}<br />
      Run: py data_pipeline/update_mf_nav.py
    </div>
  );

  const stats = data.stats ?? {};

  // Build category breakdown from top_funds (inferred)
  const catMap: Record<string, { count: number; total: number; max: number }> = {};
  for (const f of (data.top_funds ?? [])) {
    const cat = inferCategory(f.name ?? "");
    if (!catMap[cat]) catMap[cat] = { count: 0, total: 0, max: 0 };
    catMap[cat].count++;
    catMap[cat].total += Number(f.nav ?? 0);
    catMap[cat].max    = Math.max(catMap[cat].max, Number(f.nav ?? 0));
  }
  const categories = Object.entries(catMap)
    .map(([cat, v]) => ({ category: cat, count: v.count, avg_nav: Math.round(v.total / v.count * 100) / 100, max_nav: v.max }))
    .sort((a, b) => b.avg_nav - a.avg_nav);

  function TabBtn({ t, label }: { t: "top" | "gainers" | "categories"; label: string }) {
    const active = tab === t;
    return (
      <button onClick={() => setTab(t)} style={{
        padding: "3px 12px", fontSize: 10, cursor: "pointer", fontFamily: "monospace",
        background: active ? "rgba(38,196,133,0.15)" : "var(--surface)",
        color: active ? "#26c485" : "var(--muted)",
        border: `1px solid ${active ? "#26c485" : "var(--border)"}`,
        borderRadius: 4,
      }}>{label}</button>
    );
  }

  return (
    <div>
      {/* Stats strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 14 }}>
        {[
          { l: "TOTAL FUNDS",  v: String(stats.total_funds ?? "--"),  c: "var(--accent)" },
          { l: "AVG NAV",      v: stats.avg_nav  != null ? fmtNav(stats.avg_nav)  : "--", c: "var(--text)" },
          { l: "MAX NAV",      v: stats.max_nav  != null ? fmtNav(stats.max_nav)  : "--", c: "var(--bull)" },
          { l: "DATES",        v: String(stats.date_count ?? "--") + " dates",             c: "var(--dim)"  },
        ].map(({ l, v, c }) => (
          <div key={l} style={{ padding: "10px 14px", background: "var(--surface)",
                                border: "1px solid var(--border)", borderRadius: 6 }}>
            <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                          letterSpacing: "0.1em", marginBottom: 4 }}>{l}</div>
            <div style={{ fontFamily: "monospace", fontSize: 15, fontWeight: 700, color: c }}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginBottom: 10 }}>
        Latest: {data.date}
        {data.prev_date ? ` vs ${data.prev_date}` : ""}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <TabBtn t="top"        label="TOP 20 BY NAV"  />
        <TabBtn t="gainers"    label="TOP GAINERS"    />
        <TabBtn t="categories" label="CATEGORIES"     />
      </div>

      {/* Top 20 by NAV */}
      {tab === "top" && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
              <th style={{ padding: "4px 6px", textAlign: "right", width: 28 }}>#</th>
              <th style={{ padding: "4px 8px", textAlign: "left" }}>FUND NAME</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>NAV</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>CHANGE</th>
            </tr>
          </thead>
          <tbody>
            {(data.top_funds ?? []).map((row: any, i: number) => {
              const chg   = row.change_pct ?? null;
              const chgC  = chg == null ? "var(--dim)" : Number(chg) >= 0 ? "var(--pos)" : "var(--neg)";
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "5px 6px", color: "var(--dim)", textAlign: "right" }}>{i + 1}</td>
                  <td style={{ padding: "5px 8px", color: "var(--text)", maxWidth: 320 }}>
                    <span title={row.name}>{truncate(row.name, 48)}</span>
                    <CatBadge name={row.name} />
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)", fontWeight: 600 }}>
                    {fmtNav(row.nav)}
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: chgC }}>
                    {fmtPct(chg)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {/* Top gainers */}
      {tab === "gainers" && (
        (data.gainers ?? []).length === 0 ? (
          <div style={{ color: "var(--muted)", fontFamily: "monospace", padding: 20 }}>
            No prior date data for comparison. Need at least 2 dates in mf_nav_history.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                <th style={{ padding: "4px 6px", textAlign: "right", width: 28 }}>#</th>
                <th style={{ padding: "4px 8px", textAlign: "left" }}>FUND NAME</th>
                <th style={{ padding: "4px 8px", textAlign: "right" }}>NAV</th>
                <th style={{ padding: "4px 8px", textAlign: "right" }}>GAIN</th>
              </tr>
            </thead>
            <tbody>
              {(data.gainers ?? []).map((row: any, i: number) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "5px 6px", color: "var(--dim)", textAlign: "right" }}>{i + 1}</td>
                  <td style={{ padding: "5px 8px", color: "var(--text)" }}>
                    <span title={row.name}>{truncate(row.name, 48)}</span>
                    <CatBadge name={row.name} />
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)" }}>{fmtNav(row.nav)}</td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--pos)", fontWeight: 600 }}>
                    {fmtPct(row.change_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {/* Categories (inferred from name) */}
      {tab === "categories" && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
              <th style={{ padding: "4px 8px", textAlign: "left" }}>CATEGORY</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>FUNDS</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>AVG NAV</th>
              <th style={{ padding: "4px 8px", textAlign: "right" }}>MAX NAV</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((row, i) => {
              const color = CAT_COLORS[row.category] ?? "#6e7681";
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "5px 8px" }}>
                    <span style={{ color, fontWeight: 600 }}>{row.category}</span>
                  </td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>{row.count}</td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)" }}>{fmtNav(row.avg_nav)}</td>
                  <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--pos)" }}>{fmtNav(row.max_nav)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
