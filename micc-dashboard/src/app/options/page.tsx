"use client";
import NavBar from "@/components/NavBar";
import { useState, useEffect } from "react";
import MarkdownText  from "@/components/MarkdownText";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function fmtOI(v: any): string {
  const n = Number(v);
  if (!v || isNaN(n)) return "--";
  if (n >= 1e7) return (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return (n / 1e5).toFixed(1) + "L";
  if (n >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(0);
}
function fmtGex(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toFixed(0);
}

// ─────────────────────────────────────────────────────────────────────────────
// EpsilonTab — reads /api/epsilon
// ─────────────────────────────────────────────────────────────────────────────
function EpsilonTab() {
  const [epData,  setEpData]  = useState<any>(null);
  const [epLoad,  setEpLoad]  = useState(true);

  useEffect(() => {
    fetch("/api/epsilon", { cache: "no-store" })
      .then(r => r.json())
      .then(d => { setEpData(d); setEpLoad(false); })
      .catch(() => setEpLoad(false));
  }, []);

  if (epLoad) return (
    <div style={{ color: "var(--dim)", fontFamily: "monospace", padding: 24 }}>
      Loading Epsilon signals...
    </div>
  );
  if (!epData || epData.error) return (
    <div style={{ color: "var(--neg)", fontFamily: "monospace", padding: 24 }}>
      {epData?.error ?? "No Epsilon report."}<br />
      Run: py D:\MICC\agent_epsilon.py --send
    </div>
  );

  const spikes = epData.oi_spikes        ?? [];
  const pcrdiv = epData.pcr_divergence   ?? [];
  const gamma  = epData.gamma_near_price ?? [];
  const ns     = epData.nifty_summary    ?? {};
  const ai     = epData.analysis         ?? "";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
      <div>
        {/* Nifty summary strip */}
        {ns.date && (
          <div style={{
            padding: "8px 14px", background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 6,
            fontFamily: "monospace", fontSize: 11,
            display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap",
          }}>
            <span><span style={{ color: "var(--dim)" }}>DATE: </span><span>{ns.date}</span></span>
            <span><span style={{ color: "var(--dim)" }}>EXPIRY: </span><span>{ns.expiry}</span></span>
            <span><span style={{ color: "var(--dim)" }}>PCR: </span>
              <span style={{ color: "var(--warn)" }}>{ns.pcr ?? "--"}</span></span>
            <span><span style={{ color: "var(--dim)" }}>MAX PAIN: </span>
              <span style={{ color: "var(--warn)" }}>{ns.max_pain?.toLocaleString("en-IN") ?? "--"}</span></span>
            <span><span style={{ color: "var(--dim)" }}>GEX: </span>
              <span style={{ color: (ns.net_gex ?? 0) > 0 ? "var(--pos)" : "var(--neg)" }}>
                {(ns.net_gex ?? 0) > 0 ? "LONG" : "SHORT"} ({ns.net_gex?.toLocaleString() ?? "--"})
              </span></span>
          </div>
        )}

        {/* OI Spikes */}
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
            letterSpacing: "0.1em", marginBottom: 8,
            borderBottom: "1px solid var(--border)", paddingBottom: 3,
          }}>
            OI SPIKES -- UNUSUAL BUILDUP VS 5-DAY AVG
          </div>
          {spikes.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
              No OI spikes detected. Run: py agent_epsilon.py
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                  <th style={{ padding: "4px 8px", textAlign: "left"  }}>SYMBOL</th>
                  <th style={{ padding: "4px 8px", textAlign: "left"  }}>TYPE</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>TODAY OI</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>5D AVG OI</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>SPIKE</th>
                  <th style={{ padding: "4px 8px", textAlign: "left"  }}>SIGNAL</th>
                </tr>
              </thead>
              <tbody>
                {spikes.map((r: any, i: number) => {
                  const isBear = r.option_typ === "CE";
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 8px", fontWeight: 600 }}>
                        <a href={`/stocks/${r.symbol}`}
                           style={{ color: "var(--accent)", textDecoration: "none" }}>
                          {r.symbol}
                        </a>
                      </td>
                      <td style={{ padding: "5px 8px",
                                   color: isBear ? "var(--neg)" : "var(--pos)", fontWeight: 600 }}>
                        {r.option_typ}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right" }}>{fmtOI(r.today_oi)}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                        {fmtOI(r.avg_oi)}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right",
                                   color: "var(--warn)", fontWeight: 700 }}>
                        {r.spike_ratio != null ? `${r.spike_ratio}x` : "--"}
                      </td>
                      <td style={{ padding: "5px 8px", fontSize: 10,
                                   color: isBear ? "var(--neg)" : "var(--pos)" }}>
                        {(r.signal ?? "--").replace("_", " ")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* PCR Divergence */}
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
            letterSpacing: "0.1em", marginBottom: 8,
            borderBottom: "1px solid var(--border)", paddingBottom: 3,
          }}>
            PCR DIVERGENCE -- SENTIMENT SHIFT FROM 5-DAY BASELINE
          </div>
          {pcrdiv.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
              No significant PCR divergence today.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                  <th style={{ padding: "4px 8px", textAlign: "left"  }}>SYMBOL</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>TODAY PCR</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>5D AVG</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>DIVERGENCE</th>
                  <th style={{ padding: "4px 8px", textAlign: "left"  }}>SIGNAL</th>
                </tr>
              </thead>
              <tbody>
                {pcrdiv.map((r: any, i: number) => {
                  const isBull = r.signal === "BULLISH_SHIFT";
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 8px", fontWeight: 600 }}>
                        <a href={`/stocks/${r.symbol}`}
                           style={{ color: "var(--accent)", textDecoration: "none" }}>
                          {r.symbol}
                        </a>
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right" }}>
                        {r.today_pcr?.toFixed(3) ?? "--"}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                        {r.avg_pcr?.toFixed(3) ?? "--"}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right",
                                   color: isBull ? "var(--pos)" : "var(--neg)", fontWeight: 600 }}>
                        {r.divergence != null
                          ? (r.divergence >= 0 ? "+" : "") + r.divergence.toFixed(3)
                          : "--"}
                      </td>
                      <td style={{ padding: "5px 8px", fontSize: 10,
                                   color: isBull ? "var(--pos)" : "var(--neg)" }}>
                        {(r.signal ?? "--").replace("_", " ")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* High Gamma Near Price */}
        <div>
          <div style={{
            fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
            letterSpacing: "0.1em", marginBottom: 8,
            borderBottom: "1px solid var(--border)", paddingBottom: 3,
          }}>
            HIGH GAMMA NEAR PRICE -- VOLATILITY ZONES WITHIN 1.5% OF SPOT
          </div>
          {gamma.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
              No high-gamma strikes near price. Run: py agent_epsilon.py
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                  <th style={{ padding: "4px 8px", textAlign: "left"  }}>SYMBOL</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>STRIKE</th>
                  <th style={{ padding: "4px 8px", textAlign: "left"  }}>TYPE</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>DIST%</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>GAMMA</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>IV%</th>
                  <th style={{ padding: "4px 8px", textAlign: "right" }}>DELTA</th>
                </tr>
              </thead>
              <tbody>
                {gamma.map((r: any, i: number) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "5px 8px", fontWeight: 600 }}>
                      <a href={`/stocks/${r.symbol}`}
                         style={{ color: "var(--accent)", textDecoration: "none" }}>
                        {r.symbol}
                      </a>
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--info)" }}>
                      {Number(r.strike).toLocaleString("en-IN")}
                    </td>
                    <td style={{ padding: "5px 8px",
                                 color: r.option_type === "CE" ? "var(--neg)" : "var(--pos)" }}>
                      {r.option_type}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right",
                                 color: Math.abs(r.dist_pct ?? 0) < 0.5 ? "var(--warn)" : "var(--dim)" }}>
                      {r.dist_pct != null
                        ? (r.dist_pct >= 0 ? "+" : "") + r.dist_pct.toFixed(2) + "%"
                        : "--"}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right",
                                 color: "var(--accent)", fontWeight: 600 }}>
                      {r.gamma?.toFixed(5) ?? "--"}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                      {r.iv != null ? r.iv.toFixed(1) + "%" : "--"}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                      {r.delta?.toFixed(3) ?? "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Right: AI analysis */}
      <div>
        <div style={{
          fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
          letterSpacing: "0.1em", marginBottom: 8,
          borderBottom: "1px solid var(--border)", paddingBottom: 3,
        }}>
          AI ANALYSIS
        </div>
        {ai ? (
          <MarkdownText text={ai} maxHeight={600} />
        ) : (
          <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
            No AI analysis. Run: py agent_epsilon.py --send
          </div>
        )}
        {epData.timestamp && (
          <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", marginTop: 8 }}>
            Generated: {epData.timestamp}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Options Page
// ─────────────────────────────────────────────────────────────────────────────
export default function OptionsPage() {
  const [data,    setData]    = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab,     setTab]     = useState<"chain" | "gex" | "oichange" | "epsilon">("chain");

  useEffect(() => {
    fetch("/api/options", { cache: "no-store" })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <NavBar />
            <div style={{ padding: 40, color: "var(--dim)", fontFamily: "monospace" }}>
        Loading options data...
      </div>
    </div>
  );
  if (!data || data.error) return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
            <div style={{ padding: 40, color: "var(--neg)", fontFamily: "monospace" }}>
        {data?.error ?? "No options data."}<br />
        Run: py D:\MICC\data_pipeline\phase2_greeks_calculator.py --daily
      </div>
    </div>
  );

  const pcrC = data.pcr == null  ? "var(--text)"
             : data.pcr > 1.3    ? "var(--pos)"
             : data.pcr < 0.7    ? "var(--neg)" : "var(--warn)";
  const pcrL = data.pcr == null  ? "--"
             : data.pcr > 1.3    ? "BULLISH"
             : data.pcr < 0.7    ? "BEARISH" : "NEUTRAL";
  const gexC = (data.total_net_gex ?? 0) > 0 ? "var(--pos)" : "var(--neg)";
  const gexL = (data.total_net_gex ?? 0) > 0 ? "LONG GAMMA" : "SHORT GAMMA";

  const maxCOI = Math.max(...(data.chain ?? []).map((r: any) => Number(r.call_oi ?? 0)), 1);
  const maxPOI = Math.max(...(data.chain ?? []).map((r: any) => Number(r.put_oi  ?? 0)), 1);
  const maxGex = Math.max(...(data.gex   ?? []).map((r: any) => Math.abs(Number(r.net_gex))), 1);

  const TABS = [
    { id: "chain",   label: "OPTIONS CHAIN"   },
    { id: "gex",     label: "GEX BY STRIKE"   },
    { id: "oichange",label: "OI CHANGE"        },
    { id: "epsilon", label: "EPSILON SIGNALS"  },
  ] as const;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
            <div style={{ padding: "16px 20px", maxWidth: 1600, margin: "0 auto" }}>

        {/* Title */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700,
                        letterSpacing: "0.12em", color: "var(--info)" }}>
            OPTIONS INTELLIGENCE -- NIFTY
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginTop: 2 }}>
            Date: {data.date} &nbsp;|&nbsp; Expiry: {data.expiry}
            {data.nifty_close && (
              <span> &nbsp;|&nbsp; Nifty: {Number(data.nifty_close).toLocaleString("en-IN")}
                {data.nifty_change_pct != null && (
                  <span style={{ color: Number(data.nifty_change_pct) >= 0 ? "var(--pos)" : "var(--neg)" }}>
                    &nbsp;({Number(data.nifty_change_pct) >= 0 ? "+" : ""}{Number(data.nifty_change_pct).toFixed(2)}%)
                  </span>
                )}
              </span>
            )}
          </div>
        </div>

        {/* KPI cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 10, marginBottom: 16 }}>
          {[
            { label: "PCR",      value: data.pcr?.toFixed(3) ?? "--",       sub: pcrL,      color: pcrC },
            { label: "MAX PAIN", value: data.max_pain?.toLocaleString("en-IN") ?? "--",
                                  sub: "strike",                                               color: "var(--warn)" },
            { label: "NET GEX",  value: fmtGex(data.total_net_gex ?? 0),   sub: gexL,      color: gexC },
            { label: "CALL OI",  value: fmtOI(data.call_oi),                sub: "total calls", color: "var(--neg)" },
            { label: "PUT OI",   value: fmtOI(data.put_oi),                 sub: "total puts",  color: "var(--pos)" },
          ].map(({ label, value, sub, color }) => (
            <div key={label} style={{
              padding: "12px 14px", background: "var(--surface)",
              border: "1px solid var(--border)", borderRadius: 6,
            }}>
              <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
                            letterSpacing: "0.1em", marginBottom: 4 }}>{label}</div>
              <div style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700, color }}>{value}</div>
              <div style={{ fontFamily: "monospace", fontSize: 9, color, marginTop: 3 }}>{sub}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
          {/* Left: tabbed content */}
          <div>
            {/* Tab buttons */}
            <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
              {TABS.map(t => (
                <button key={t.id} onClick={() => setTab(t.id)} style={{
                  padding: "4px 12px", fontSize: 10, cursor: "pointer", fontFamily: "monospace",
                  background: tab === t.id ? "var(--info)" : "var(--surface)",
                  color:      tab === t.id ? "#000"        : "var(--muted)",
                  border: "1px solid var(--border)", borderRadius: 4,
                }}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* OPTIONS CHAIN */}
            {tab === "chain" && (
              (data.chain ?? []).length === 0 ? (
                <div style={{ color: "var(--muted)", fontFamily: "monospace", padding: 20 }}>
                  No chain data. Check /api/options debug field for instrument info.
                </div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                      <th style={{ textAlign: "right",  padding: "4px 5px" }}>CALL OI</th>
                      <th style={{ textAlign: "right",  padding: "4px 5px" }}>VOL</th>
                      <th style={{ textAlign: "right",  padding: "4px 5px" }}>IV</th>
                      <th style={{ textAlign: "right",  padding: "4px 5px" }}>DELTA</th>
                      <th style={{ textAlign: "right",  padding: "4px 5px" }}>LTP</th>
                      <th style={{ textAlign: "center", padding: "4px 10px", color: "var(--info)", minWidth: 90 }}>
                        STRIKE
                      </th>
                      <th style={{ textAlign: "left",   padding: "4px 5px" }}>LTP</th>
                      <th style={{ textAlign: "left",   padding: "4px 5px" }}>DELTA</th>
                      <th style={{ textAlign: "left",   padding: "4px 5px" }}>IV</th>
                      <th style={{ textAlign: "left",   padding: "4px 5px" }}>VOL</th>
                      <th style={{ textAlign: "left",   padding: "4px 5px" }}>PUT OI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.chain ?? []).map((row: any, i: number) => {
                      const isMP = row.strike === data.max_pain;
                      const cW   = Math.round((Number(row.call_oi ?? 0) / maxCOI) * 60);
                      const pW   = Math.round((Number(row.put_oi  ?? 0) / maxPOI) * 60);
                      return (
                        <tr key={i} style={{
                          borderBottom: "1px solid var(--border)",
                          background: isMP ? "rgba(227,179,65,0.07)" : undefined,
                        }}>
                          <td style={{ textAlign: "right", padding: "4px 5px" }}>
                            <div style={{ display: "flex", alignItems: "center",
                                          justifyContent: "flex-end", gap: 3 }}>
                              <span style={{ color: "var(--neg)" }}>{fmtOI(row.call_oi)}</span>
                              <div style={{ width: cW, height: 5, background: "var(--neg)",
                                            opacity: 0.5, borderRadius: 2 }} />
                            </div>
                          </td>
                          <td style={{ textAlign: "right", padding: "4px 5px",
                                       color: "var(--dim)", fontSize: 10 }}>
                            {fmtOI(row.call_vol)}
                          </td>
                          <td style={{ textAlign: "right", padding: "4px 5px", color: "var(--dim)" }}>
                            {row.call_iv != null ? Number(row.call_iv).toFixed(1) + "%" : "--"}
                          </td>
                          <td style={{ textAlign: "right", padding: "4px 5px", color: "var(--dim)" }}>
                            {row.call_delta != null ? Number(row.call_delta).toFixed(2) : "--"}
                          </td>
                          <td style={{ textAlign: "right", padding: "4px 5px" }}>
                            {row.call_ltp != null ? Number(row.call_ltp).toFixed(2) : "--"}
                          </td>
                          <td style={{ textAlign: "center", padding: "4px 10px",
                                       color: isMP ? "var(--warn)" : "var(--info)",
                                       fontWeight: isMP ? 700 : 600, fontSize: 12 }}>
                            {Number(row.strike).toLocaleString("en-IN")}
                            {isMP && <div style={{ fontSize: 8, color: "var(--warn)" }}>MAX PAIN</div>}
                          </td>
                          <td style={{ padding: "4px 5px" }}>
                            {row.put_ltp != null ? Number(row.put_ltp).toFixed(2) : "--"}
                          </td>
                          <td style={{ padding: "4px 5px", color: "var(--dim)" }}>
                            {row.put_delta != null ? Number(row.put_delta).toFixed(2) : "--"}
                          </td>
                          <td style={{ padding: "4px 5px", color: "var(--dim)" }}>
                            {row.put_iv != null ? Number(row.put_iv).toFixed(1) + "%" : "--"}
                          </td>
                          <td style={{ padding: "4px 5px", color: "var(--dim)", fontSize: 10 }}>
                            {fmtOI(row.put_vol)}
                          </td>
                          <td style={{ padding: "4px 5px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
                              <div style={{ width: pW, height: 5, background: "var(--pos)",
                                            opacity: 0.5, borderRadius: 2 }} />
                              <span style={{ color: "var(--pos)" }}>{fmtOI(row.put_oi)}</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )
            )}

            {/* GEX BY STRIKE */}
            {tab === "gex" && (
              <div>
                <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginBottom: 8 }}>
                  GEX date: {data.gex_date} &nbsp;|&nbsp;
                  +ve = dealers long gamma (dampens) &nbsp;|&nbsp; -ve = short gamma (amplifies)
                </div>
                {(data.gex ?? []).length === 0 ? (
                  <div style={{ color: "var(--muted)", fontFamily: "monospace" }}>
                    No GEX data. Run: py phase2_greeks_calculator.py --daily
                  </div>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
                    <thead>
                      <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                        <th style={{ textAlign: "right", padding: "4px 8px" }}>STRIKE</th>
                        <th style={{ textAlign: "right", padding: "4px 8px" }}>CALL GEX</th>
                        <th style={{ textAlign: "right", padding: "4px 8px" }}>PUT GEX</th>
                        <th style={{ textAlign: "right", padding: "4px 8px" }}>NET GEX</th>
                        <th style={{ textAlign: "left",  padding: "4px 8px", minWidth: 120 }}>BAR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...(data.gex ?? [])].sort((a: any, b: any) =>
                        Number(a.strike) - Number(b.strike)
                      ).map((row: any, i: number) => {
                        const net  = Number(row.net_gex);
                        const bw   = Math.round((Math.abs(net) / maxGex) * 110);
                        const c    = net >= 0 ? "var(--pos)" : "var(--neg)";
                        return (
                          <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                            <td style={{ textAlign: "right", padding: "4px 8px",
                                         color: "var(--info)", fontWeight: 600 }}>
                              {Number(row.strike).toLocaleString("en-IN")}
                            </td>
                            <td style={{ textAlign: "right", padding: "4px 8px", color: "var(--pos)" }}>
                              {fmtGex(Number(row.call_gex))}
                            </td>
                            <td style={{ textAlign: "right", padding: "4px 8px", color: "var(--neg)" }}>
                              {fmtGex(Number(row.put_gex))}
                            </td>
                            <td style={{ textAlign: "right", padding: "4px 8px",
                                         color: c, fontWeight: 600 }}>
                              {fmtGex(net)}
                            </td>
                            <td style={{ padding: "4px 8px" }}>
                              <div style={{ width: bw, height: 6, background: c, borderRadius: 2 }} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* OI CHANGE */}
            {tab === "oichange" && (
              <div>
                <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginBottom: 8 }}>
                  OI change vs prev session -- fresh call OI = resistance, fresh put OI = support
                </div>
                {(data.oi_change ?? []).length === 0 ? (
                  <div style={{ color: "var(--muted)", fontFamily: "monospace" }}>
                    OI change not available (need 2 dates in fo_data for NIFTY).
                  </div>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
                    <thead>
                      <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                        <th style={{ textAlign: "right", padding: "4px 8px" }}>STRIKE</th>
                        <th style={{ textAlign: "left",  padding: "4px 8px" }}>TYPE</th>
                        <th style={{ textAlign: "right", padding: "4px 8px" }}>CUR OI</th>
                        <th style={{ textAlign: "right", padding: "4px 8px" }}>OI CHG</th>
                        <th style={{ textAlign: "left",  padding: "4px 8px" }}>SIGNAL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.oi_change ?? []).map((row: any, i: number) => {
                        const chg    = Number(row.oi_chg);
                        const isCall = row.option_type === "CE";
                        const sig    = chg > 0 && isCall  ? "RESISTANCE BUILD"
                                     : chg > 0 && !isCall ? "SUPPORT BUILD"
                                     : chg < 0 && isCall  ? "CALL UNWINDING"
                                     : chg < 0 && !isCall ? "PUT UNWINDING"
                                     : "--";
                        const sigC   = chg > 0 && isCall  ? "var(--neg)"
                                     : chg > 0 && !isCall ? "var(--pos)" : "var(--dim)";
                        return (
                          <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                            <td style={{ textAlign: "right", padding: "4px 8px",
                                         color: "var(--info)", fontWeight: 600 }}>
                              {Number(row.strike).toLocaleString("en-IN")}
                            </td>
                            <td style={{ padding: "4px 8px",
                                         color: isCall ? "var(--neg)" : "var(--pos)", fontWeight: 600 }}>
                              {row.option_type}
                            </td>
                            <td style={{ textAlign: "right", padding: "4px 8px", color: "var(--dim)" }}>
                              {fmtOI(row.cur_oi)}
                            </td>
                            <td style={{ textAlign: "right", padding: "4px 8px",
                                         color: chg > 0 ? "var(--pos)" : "var(--neg)", fontWeight: 600 }}>
                              {chg > 0 ? "+" : ""}{fmtOI(Math.abs(chg))}
                            </td>
                            <td style={{ padding: "4px 8px", fontSize: 10, color: sigC }}>{sig}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* EPSILON SIGNALS */}
            {tab === "epsilon" && <EpsilonTab />}
          </div>

          {/* Right: Analysis panel */}
          <div>
            <div style={{
              fontFamily: "monospace", fontSize: 9, color: "var(--dim)",
              letterSpacing: "0.1em", marginBottom: 8,
              borderBottom: "1px solid var(--border)", paddingBottom: 4,
            }}>
              ANALYSIS
            </div>
            {data.analysis ? (
              <MarkdownText text={data.analysis} maxHeight={700} />
            ) : (
              <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11 }}>
                No analysis available.
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
