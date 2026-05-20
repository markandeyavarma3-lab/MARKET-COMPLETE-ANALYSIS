"use client";
import { useState, useEffect } from "react";

interface ChainRow {
  strike:      number;
  call_ltp:    number | null;
  call_oi:     number | null;
  call_iv:     number | null;
  put_ltp:     number | null;
  put_oi:      number | null;
  put_iv:      number | null;
}
interface GexRow {
  strike:   number;
  call_gex: number;
  put_gex:  number;
  net_gex:  number;
}
interface OptionsData {
  date:          string;
  expiry:        string;
  pcr:           number | null;
  call_oi:       number;
  put_oi:        number;
  max_pain:      number | null;
  chain:         ChainRow[];
  gex:           GexRow[];
  total_net_gex: number;
  gex_date:      string;
  error?:        string;
}

function fmtOI(v: number | null): string {
  if (v == null) return "--";
  const n = Number(v);
  if (n >= 1e7) return (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return (n / 1e5).toFixed(1) + "L";
  return n.toLocaleString();
}
function fmtLTP(v: number | null): string {
  if (v == null) return "--";
  return Number(v).toFixed(2);
}
function fmtIV(v: number | null): string {
  if (v == null) return "--";
  return Number(v).toFixed(1) + "%";
}
function fmtGex(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (abs >= 1e6) return (v / 1e6).toFixed(2) + "M";
  return v.toFixed(0);
}

export default function OptionsPanel() {
  const [data, setData]     = useState<OptionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]       = useState<"chain" | "gex">("chain");

  useEffect(() => {
    fetch("/api/options")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="panel">
      <div className="panel-title">OPTIONS</div>
      <div className="c-dim small">Loading options data...</div>
    </div>
  );
  if (!data || data.error) return (
    <div className="panel">
      <div className="panel-title">OPTIONS</div>
      <div className="c-bear small">{data?.error ?? "No options data. Run: py phase2_greeks_calculator.py --daily"}</div>
    </div>
  );

  const pcrColor = data.pcr == null ? "var(--text)"
                 : data.pcr > 1.3   ? "var(--bull)"
                 : data.pcr < 0.7   ? "var(--bear)"
                 : "var(--warn)";
  const pcrLabel = data.pcr == null ? "--"
                 : data.pcr > 1.3   ? "BULLISH"
                 : data.pcr < 0.7   ? "BEARISH"
                 : "NEUTRAL";
  const gexColor = data.total_net_gex > 0 ? "var(--bull)" : "var(--bear)";
  const gexLabel = data.total_net_gex > 0 ? "LONG GAMMA" : "SHORT GAMMA";

  // Find max OI for bar scaling
  const maxCallOI = Math.max(...data.chain.map(r => r.call_oi ?? 0), 1);
  const maxPutOI  = Math.max(...data.chain.map(r => r.put_oi  ?? 0), 1);
  const maxGex    = Math.max(...data.gex.map(r => Math.abs(r.net_gex)), 1);

  return (
    <div className="panel">
      <div className="panel-title">
        <span style={{ color: "var(--accent)" }}>&diams;</span> OPTIONS &mdash; NIFTY CHAIN
        <span className="ml" style={{ fontSize: 10, color: "var(--dim)" }}>
          {data.date} &nbsp;|&nbsp; Expiry: {data.expiry}
        </span>
      </div>

      {/* Summary stats */}
      <div className="stat-grid sg4" style={{ marginBottom: 12 }}>
        <div className="stat-box">
          <div className="stat-lbl">PCR</div>
          <div className="stat-val" style={{ color: pcrColor }}>
            {data.pcr?.toFixed(3) ?? "--"}
          </div>
          <div style={{ fontSize: 9, color: pcrColor }}>{pcrLabel}</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">MAX PAIN</div>
          <div className="stat-val c-warn">
            {data.max_pain?.toLocaleString() ?? "--"}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">NET GEX</div>
          <div className="stat-val" style={{ color: gexColor }}>
            {fmtGex(data.total_net_gex)}
          </div>
          <div style={{ fontSize: 9, color: gexColor }}>{gexLabel}</div>
        </div>
        <div className="stat-box">
          <div className="stat-lbl">CALL OI</div>
          <div className="stat-val c-bear">{fmtOI(data.call_oi)}</div>
          <div className="stat-lbl" style={{ marginTop: 2 }}>PUT OI</div>
          <div className="stat-val c-bull">{fmtOI(data.put_oi)}</div>
        </div>
      </div>

      {/* Tab switch */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {(["chain", "gex"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "3px 10px", fontSize: 10, cursor: "pointer",
              background: tab === t ? "var(--accent)" : "var(--surface)",
              color:      tab === t ? "#000"          : "var(--dim)",
              border:     "1px solid var(--border)", borderRadius: 3,
              fontFamily: "monospace", letterSpacing: "0.08em",
            }}
          >
            {t === "chain" ? "CHAIN" : "GEX BY STRIKE"}
          </button>
        ))}
      </div>

      {/* Options chain */}
      {tab === "chain" && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--dim)", fontSize: 10 }}>
                <th style={{ textAlign: "right",  padding: "3px 6px" }}>CALL OI</th>
                <th style={{ textAlign: "right",  padding: "3px 6px" }}>IV</th>
                <th style={{ textAlign: "right",  padding: "3px 6px" }}>LTP</th>
                <th style={{ textAlign: "center", padding: "3px 8px", color: "var(--accent)", minWidth: 80 }}>STRIKE</th>
                <th style={{ textAlign: "left",   padding: "3px 6px" }}>LTP</th>
                <th style={{ textAlign: "left",   padding: "3px 6px" }}>IV</th>
                <th style={{ textAlign: "left",   padding: "3px 6px" }}>PUT OI</th>
              </tr>
            </thead>
            <tbody>
              {data.chain.map((row, i) => {
                const isMaxPain = row.strike === data.max_pain;
                const callBarW  = Math.round(((row.call_oi ?? 0) / maxCallOI) * 60);
                const putBarW   = Math.round(((row.put_oi  ?? 0) / maxPutOI)  * 60);
                return (
                  <tr key={i} style={{
                    borderBottom:    "1px solid var(--border-faint, #2a2a2a)",
                    background:      isMaxPain ? "rgba(255,200,0,0.07)" : undefined,
                    color:           "var(--text)",
                  }}>
                    {/* Call side */}
                    <td style={{ textAlign: "right", padding: "3px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                        <span style={{ color: "var(--bear)" }}>{fmtOI(row.call_oi)}</span>
                        <div style={{ width: callBarW, height: 6, background: "var(--bear)", opacity: 0.6, borderRadius: 2 }} />
                      </div>
                    </td>
                    <td style={{ textAlign: "right", padding: "3px 6px", color: "var(--dim)" }}>{fmtIV(row.call_iv)}</td>
                    <td style={{ textAlign: "right", padding: "3px 6px" }}>{fmtLTP(row.call_ltp)}</td>
                    {/* Strike */}
                    <td style={{ textAlign: "center", padding: "3px 8px",
                                 color: isMaxPain ? "var(--warn)" : "var(--accent)",
                                 fontWeight: isMaxPain ? 700 : 600 }}>
                      {row.strike.toLocaleString()}
                      {isMaxPain && <span style={{ fontSize: 9, marginLeft: 4 }}>MAX PAIN</span>}
                    </td>
                    {/* Put side */}
                    <td style={{ textAlign: "left", padding: "3px 6px" }}>{fmtLTP(row.put_ltp)}</td>
                    <td style={{ textAlign: "left",  padding: "3px 6px", color: "var(--dim)" }}>{fmtIV(row.put_iv)}</td>
                    <td style={{ textAlign: "left",  padding: "3px 6px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <div style={{ width: putBarW, height: 6, background: "var(--bull)", opacity: 0.6, borderRadius: 2 }} />
                        <span style={{ color: "var(--bull)" }}>{fmtOI(row.put_oi)}</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* GEX by strike */}
      {tab === "gex" && (
        <div>
          <div style={{ fontSize: 10, color: "var(--dim)", marginBottom: 6 }}>
            GEX date: {data.gex_date} &nbsp;|&nbsp;
            Positive GEX = dealers long gamma (dampens moves) &nbsp;|&nbsp;
            Negative GEX = short gamma (amplifies moves)
          </div>
          {data.gex.length === 0 ? (
            <div className="c-dim small">No GEX data. Run: py phase2_greeks_calculator.py --daily</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--dim)", fontSize: 10 }}>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>STRIKE</th>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>CALL GEX</th>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>PUT GEX</th>
                  <th style={{ textAlign: "right",  padding: "3px 6px" }}>NET GEX</th>
                  <th style={{ textAlign: "left",   padding: "3px 8px" }}>BAR</th>
                </tr>
              </thead>
              <tbody>
                {[...data.gex].sort((a, b) => Number(a.strike) - Number(b.strike)).map((row, i) => {
                  const net    = Number(row.net_gex);
                  const barW   = Math.round((Math.abs(net) / maxGex) * 80);
                  const barClr = net >= 0 ? "var(--bull)" : "var(--bear)";
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-faint, #2a2a2a)" }}>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: "var(--accent)", fontWeight: 600 }}>
                        {Number(row.strike).toLocaleString()}
                      </td>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: "var(--bull)" }}>{fmtGex(Number(row.call_gex))}</td>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: "var(--bear)" }}>{fmtGex(Number(row.put_gex))}</td>
                      <td style={{ textAlign: "right",  padding: "3px 6px", color: barClr, fontWeight: 600 }}>{fmtGex(net)}</td>
                      <td style={{ padding: "3px 8px" }}>
                        <div style={{ width: barW, height: 6, background: barClr, borderRadius: 2 }} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
