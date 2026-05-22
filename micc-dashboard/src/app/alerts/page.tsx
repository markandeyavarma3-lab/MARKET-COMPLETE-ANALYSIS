"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface Alert {
  id?: string; type: string; symbol: string; threshold?: number;
  last_fired_date?: string; fired_count?: number; enabled?: boolean;
  last_value?: number; message?: string;
}
interface FiredAlert {
  symbol: string; type: string; message: string;
  fired_at: string; value?: number;
}
interface AlertsData {
  alerts: Alert[]; fired_today: FiredAlert[];
  fired_count: number; total_alerts: number;
}

const sentColor = (s: string) => s === "PRICE_ABOVE" || s === "RSI_ABOVE" ? "var(--bear)" : "var(--bull)";

export default function AlertsPage() {
  const [data, setData]   = useState<AlertsData | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");
  const [tab, setTab]     = useState<"active"|"fired"|"add">("active");
  const [newSym, setNSym] = useState("");
  const [newType, setNTyp]= useState("PRICE_ABOVE");
  const [newVal, setNVal] = useState("");
  const [saving, setSav]  = useState(false);

  function load() {
    setL(true);
    fetch("/api/alerts")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }
  useEffect(load, []);

  async function addAlert() {
    if (!newSym || !newVal) return;
    setSav(true);
    try {
      await fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: newSym.toUpperCase(), type: newType, threshold: parseFloat(newVal) }),
      });
      setNSym(""); setNVal(""); load();
    } catch (e: unknown) {
      setE(String(e));
    } finally { setSav(false); }
  }

  async function deleteAlert(id: string) {
    await fetch("/api/alerts?id=" + id, { method: "DELETE" });
    load();
  }

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 16 },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1000, margin: "0 auto", padding: "16px 20px" },
    tabs:  { display: "flex", gap: 6, marginBottom: 20 },
    tab:   (a: boolean): React.CSSProperties => ({
      padding: "5px 16px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (a ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: a ? "var(--accent)22" : "transparent",
      color: a ? "var(--accent)" : "var(--dim)",
    }),
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)" },
    td:    { padding: "9px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    input: { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4,
             padding: "6px 10px", fontSize: 12, color: "var(--text)", outline: "none", width: "100%" },
    sel:   { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4,
             padding: "6px 10px", fontSize: 12, color: "var(--text)", outline: "none", width: "100%" },
    btn:   { padding: "6px 16px", borderRadius: 4, fontSize: 11, cursor: "pointer",
             background: "var(--accent)22", border: "1px solid var(--accent)", color: "var(--accent)" },
    del:   { padding: "3px 10px", borderRadius: 3, fontSize: 10, cursor: "pointer",
             background: "var(--bear)11", border: "1px solid var(--bear)44", color: "var(--bear)" },
  };

  const TYPES = ["PRICE_ABOVE","PRICE_BELOW","RSI_ABOVE","RSI_BELOW",
                  "VOLUME_SURGE","BREAKOUT_52W","STOP_HIT"];

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>ALERTS  /  PRICE & SIGNAL TRIGGERS</span>
        {data && <span style={{ fontSize: 10, color: "var(--dim)" }}>
          {data.total_alerts} alerts  |  {data.fired_count} fired today
        </span>}
        <button onClick={load} style={{ ...S.btn, marginLeft: "auto", fontSize: 10, padding: "3px 10px" }}>
          Refresh
        </button>
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading alerts...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 12, marginBottom: 12,
          background: "var(--bear)11", borderRadius: 6 }}>Error: {error}</div>}

        {data && <>
          <div style={S.tabs}>
            <button style={S.tab(tab==="active")} onClick={() => setTab("active")}>
              ACTIVE ({data.total_alerts})
            </button>
            <button style={S.tab(tab==="fired")} onClick={() => setTab("fired")}>
              FIRED TODAY ({data.fired_count})
            </button>
            <button style={S.tab(tab==="add")} onClick={() => setTab("add")}>
              + ADD ALERT
            </button>
          </div>

          {tab === "active" && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  {["SYMBOL","TYPE","THRESHOLD","LAST FIRED","TIMES FIRED","STATUS",""].map(h => (
                    <th key={h} style={S.th}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {(data.alerts || []).map((a, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 700 }}>{a.symbol}</td>
                      <td style={{ ...S.td, color: sentColor(a.type), fontSize: 11 }}>{a.type}</td>
                      <td style={S.td}>{a.threshold ?? "--"}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{a.last_fired_date || "never"}</td>
                      <td style={S.td}>{a.fired_count ?? 0}</td>
                      <td style={S.td}>
                        <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10,
                          background: a.enabled !== false ? "var(--bull)22" : "var(--muted)22",
                          color: a.enabled !== false ? "var(--bull)" : "var(--muted)" }}>
                          {a.enabled !== false ? "ON" : "OFF"}
                        </span>
                      </td>
                      <td style={S.td}>
                        {a.id && (
                          <button style={S.del} onClick={() => deleteAlert(a.id!)}>
                            DEL
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {data.alerts.length === 0 && (
                    <tr><td colSpan={7} style={{ padding: 30, textAlign: "center", color: "var(--dim)" }}>
                      No alerts configured. Add one below.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === "fired" && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  {["TIME","SYMBOL","TYPE","MESSAGE","VALUE"].map(h => (
                    <th key={h} style={S.th}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {(data.fired_today || []).map((f, i) => (
                    <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, color: "var(--dim)", fontSize: 11 }}>
                        {(f.fired_at || "").slice(11,16)}
                      </td>
                      <td style={{ ...S.td, color: "var(--accent)", fontWeight: 700 }}>{f.symbol}</td>
                      <td style={{ ...S.td, color: sentColor(f.type), fontSize: 11 }}>{f.type}</td>
                      <td style={{ ...S.td, fontSize: 11 }}>{f.message}</td>
                      <td style={S.td}>{f.value != null ? Number(f.value).toFixed(2) : "--"}</td>
                    </tr>
                  ))}
                  {data.fired_today.length === 0 && (
                    <tr><td colSpan={5} style={{ padding: 30, textAlign: "center", color: "var(--dim)" }}>
                      No alerts fired today.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === "add" && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "24px" }}>
              <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 16 }}>
                ADD NEW ALERT
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
                <div>
                  <div style={{ fontSize: 10, color: "var(--dim)", marginBottom: 4 }}>SYMBOL</div>
                  <input style={S.input} placeholder="e.g. RELIANCE"
                    value={newSym} onChange={e => setNSym(e.target.value.toUpperCase())} />
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--dim)", marginBottom: 4 }}>TYPE</div>
                  <select style={S.sel} value={newType} onChange={e => setNTyp(e.target.value)}>
                    {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--dim)", marginBottom: 4 }}>THRESHOLD</div>
                  <input style={S.input} placeholder="e.g. 1500"
                    value={newVal} onChange={e => setNVal(e.target.value)} type="number" />
                </div>
                <button style={S.btn} onClick={addAlert} disabled={saving}>
                  {saving ? "..." : "ADD"}
                </button>
              </div>
              <div style={{ marginTop: 20, fontSize: 11, color: "var(--dim)", lineHeight: 1.8 }}>
                <div style={{ marginBottom: 4, color: "var(--text)", fontSize: 10, letterSpacing: 1 }}>ALERT TYPES</div>
                {TYPES.map(t => (
                  <div key={t}><span style={{ color: sentColor(t) }}>{t}</span>
                    {t === "PRICE_ABOVE" && "  -- fires when close > threshold"}
                    {t === "PRICE_BELOW" && "  -- fires when close < threshold"}
                    {t === "RSI_ABOVE"   && "  -- fires when RSI-14 > threshold (e.g. 70 = overbought)"}
                    {t === "RSI_BELOW"   && "  -- fires when RSI-14 < threshold (e.g. 30 = oversold)"}
                    {t === "VOLUME_SURGE"&& "  -- fires when volume > threshold x 20d avg"}
                    {t === "BREAKOUT_52W"&& "  -- fires when close > 52w high (threshold ignored)"}
                    {t === "STOP_HIT"    && "  -- fires when close < threshold (portfolio stop loss)"}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>}
      </div>
    </div>
  );
}