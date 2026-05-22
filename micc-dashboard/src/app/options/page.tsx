"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface StrikeRow {
  strike: number; call_oi: number; put_oi: number;
  call_vol: number; put_vol: number; call_iv?: number; put_iv?: number;
}
interface ParticipantRow {
  category: string;
  fut_idx_long: number; fut_idx_short: number;
  opt_idx_call_long: number; opt_idx_call_short: number;
  opt_idx_put_long: number; opt_idx_put_short: number;
}
interface OptionsData {
  latest_date?: string; expiry?: string; spot?: number;
  pcr?: number; max_pain?: number; total_call_oi?: number; total_put_oi?: number;
  strikes?: StrikeRow[]; participant_oi?: ParticipantRow[];
  nifty_close?: number; nifty_change_pct?: number;
  atm_iv?: number; iv_rank?: number;
}

const fmt  = (v: unknown, d = 0) => v == null ? "--" : Number(v).toFixed(d);
const fmtK = (v: unknown) => {
  if (v == null) return "--";
  const n = Number(v);
  return n >= 1e6 ? (n/1e6).toFixed(1)+"M" : n >= 1e3 ? (n/1e3).toFixed(0)+"K" : String(n);
};

function OIBar({ callOI, putOI, strike, spot }: {
  callOI: number; putOI: number; strike: number; spot?: number;
}) {
  const total = (callOI + putOI) || 1;
  const callPct = (callOI / total) * 100;
  const putPct  = (putOI  / total) * 100;
  const isATM   = spot != null && Math.abs(strike - spot) / spot < 0.01;
  return (
    <div style={{ display: "flex", height: 16, borderRadius: 2, overflow: "hidden",
      border: isATM ? "1px solid var(--accent)" : "none", minWidth: 80 }}>
      <div style={{ width: callPct+"%", background: "var(--bear)", opacity: 0.8 }} />
      <div style={{ width: putPct+"%",  background: "var(--bull)", opacity: 0.8 }} />
    </div>
  );
}

export default function OptionsPage() {
  const [data, setData] = useState<OptionsData | null>(null);
  const [loading, setL] = useState(true);
  const [error, setE]   = useState("");
  const [tab, setTab]   = useState<"chain"|"participant"|"analysis">("chain");

  useEffect(() => {
    fetch("/api/options")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 16 },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    grid:  { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px,1fr))", gap: 10, marginBottom: 20 },
    kv:    { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "12px 16px" },
    kvk:   { fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 4 },
    kvv:   { fontSize: 20, fontWeight: 700, color: "var(--text)" },
    tabs:  { display: "flex", gap: 6, marginBottom: 20 },
    tab:   (a: boolean): React.CSSProperties => ({
      padding: "5px 16px", fontSize: 11, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (a ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: a ? "var(--accent)22" : "transparent",
      color: a ? "var(--accent)" : "var(--dim)",
    }),
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 10px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)", background: "var(--surface)" },
    thr:   { padding: "8px 10px", textAlign: "right" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)", background: "var(--surface)" },
    td:    { padding: "7px 10px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    tdr:   { padding: "7px 10px", borderBottom: "1px solid var(--border)",
             color: "var(--text)", textAlign: "right" as const },
  };

  const pcr = data?.pcr;
  const pcrColor = pcr == null ? "var(--text)" : pcr > 1.3 ? "var(--bull)" : pcr < 0.7 ? "var(--bear)" : "var(--warn)";
  const pcrLabel = pcr == null ? "--" : pcr > 1.3 ? "BULLISH" : pcr < 0.7 ? "BEARISH" : "NEUTRAL";

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>OPTIONS  /  NIFTY CHAIN</span>
        {data?.latest_date && <span style={{ fontSize: 10, color: "var(--dim)" }}>{data.latest_date}</span>}
        {data?.expiry      && <span style={{ fontSize: 10, color: "var(--info)" }}>Expiry: {data.expiry}</span>}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading options data...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error} -- run pipeline to fetch options data</div>}

        {data && <>
          {/* KPI grid */}
          <div style={S.grid}>
            <div style={S.kv}>
              <div style={S.kvk}>NIFTY SPOT</div>
              <div style={S.kvv}>{data.nifty_close ? Number(data.nifty_close).toLocaleString("en-IN") : "--"}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>PCR</div>
              <div style={{ ...S.kvv, color: pcrColor }}>{fmt(data.pcr, 2)}</div>
              <div style={{ fontSize: 10, color: pcrColor }}>{pcrLabel}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>MAX PAIN</div>
              <div style={S.kvv}>{data.max_pain ? Number(data.max_pain).toLocaleString("en-IN") : "--"}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>ATM IV</div>
              <div style={S.kvv}>{fmt(data.atm_iv, 1)}{data.atm_iv ? "%" : ""}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>IV RANK</div>
              <div style={{ ...S.kvv, color: Number(data.iv_rank) > 70 ? "var(--bear)" : "var(--bull)" }}>
                {fmt(data.iv_rank, 0)}{data.iv_rank ? "%" : ""}
              </div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>CALL OI</div>
              <div style={{ ...S.kvv, color: "var(--bear)", fontSize: 16 }}>{fmtK(data.total_call_oi)}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>PUT OI</div>
              <div style={{ ...S.kvv, color: "var(--bull)", fontSize: 16 }}>{fmtK(data.total_put_oi)}</div>
            </div>
          </div>

          {/* Tabs */}
          <div style={S.tabs}>
            {(["chain","participant","analysis"] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={S.tab(tab === t)}>
                {t.toUpperCase()}
              </button>
            ))}
          </div>

          {/* OI Chain */}
          {tab === "chain" && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.thr}>CALL OI</th>
                  <th style={S.thr}>CALL VOL</th>
                  <th style={{ ...S.th, textAlign: "center", fontWeight: 700, color: "var(--accent)" }}>STRIKE</th>
                  <th style={S.th}>PUT OI</th>
                  <th style={S.th}>PUT VOL</th>
                  <th style={S.th}>OI RATIO</th>
                </tr></thead>
                <tbody>
                  {(data.strikes || []).map((row, i) => {
                    const isATM = data.spot != null && Math.abs(row.strike - data.spot) / data.spot < 0.01;
                    const rowBg = isATM ? "var(--accent)11" : i%2===0 ? "transparent" : "var(--surface)88";
                    return (
                      <tr key={row.strike} style={{ background: rowBg }}>
                        <td style={{ ...S.tdr, color: "var(--bear)" }}>{fmtK(row.call_oi)}</td>
                        <td style={S.tdr}>{fmtK(row.call_vol)}</td>
                        <td style={{ ...S.td, textAlign: "center", fontWeight: isATM ? 700 : 400,
                          color: isATM ? "var(--accent)" : "var(--text)" }}>
                          {row.strike.toLocaleString("en-IN")}
                        </td>
                        <td style={{ ...S.td, color: "var(--bull)" }}>{fmtK(row.put_oi)}</td>
                        <td style={S.td}>{fmtK(row.put_vol)}</td>
                        <td style={S.td}>
                          <OIBar callOI={row.call_oi} putOI={row.put_oi}
                            strike={row.strike} spot={data.spot} />
                        </td>
                      </tr>
                    );
                  })}
                  {(!data.strikes || data.strikes.length === 0) && (
                    <tr><td colSpan={6} style={{ padding: 30, textAlign: "center", color: "var(--dim)" }}>
                      No options chain data -- run pipeline phase2_greeks_calculator.py
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Participant OI */}
          {tab === "participant" && (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  <th style={S.th}>CATEGORY</th>
                  <th style={S.thr}>FUT IDX LONG</th>
                  <th style={S.thr}>FUT IDX SHORT</th>
                  <th style={S.thr}>NET FUT</th>
                  <th style={S.thr}>CALL LONG</th>
                  <th style={S.thr}>PUT LONG</th>
                  <th style={S.thr}>NET OPT</th>
                </tr></thead>
                <tbody>
                  {(data.participant_oi || []).map((r, i) => {
                    const netFut = (r.fut_idx_long || 0) - (r.fut_idx_short || 0);
                    const netOpt = (r.opt_idx_call_long || 0) - (r.opt_idx_call_short || 0)
                               + (r.opt_idx_put_long  || 0) - (r.opt_idx_put_short  || 0);
                    return (
                      <tr key={r.category} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                        <td style={{ ...S.td, fontWeight: 600, color: "var(--accent)" }}>{r.category}</td>
                        <td style={S.tdr}>{fmtK(r.fut_idx_long)}</td>
                        <td style={S.tdr}>{fmtK(r.fut_idx_short)}</td>
                        <td style={{ ...S.tdr, color: netFut >= 0 ? "var(--bull)" : "var(--bear)", fontWeight: 700 }}>
                          {netFut >= 0 ? "+" : ""}{fmtK(netFut)}
                        </td>
                        <td style={S.tdr}>{fmtK(r.opt_idx_call_long)}</td>
                        <td style={S.tdr}>{fmtK(r.opt_idx_put_long)}</td>
                        <td style={{ ...S.tdr, color: netOpt >= 0 ? "var(--bull)" : "var(--bear)", fontWeight: 700 }}>
                          {netOpt >= 0 ? "+" : ""}{fmtK(netOpt)}
                        </td>
                      </tr>
                    );
                  })}
                  {(!data.participant_oi || data.participant_oi.length === 0) && (
                    <tr><td colSpan={7} style={{ padding: 30, textAlign: "center", color: "var(--dim)" }}>
                      No participant OI -- run: py D:\MICC\data_pipeline\fetch_phase1_data.py --poi
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Analysis */}
          {tab === "analysis" && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "20px" }}>
              <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 12 }}>
                MARKET STRUCTURE ANALYSIS
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                <div>
                  <div style={{ fontSize: 11, color: "var(--dim)", marginBottom: 8 }}>PCR INTERPRETATION</div>
                  <div style={{ fontSize: 13, color: pcrColor, fontWeight: 600, marginBottom: 4 }}>
                    {pcrLabel}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text)", lineHeight: 1.8 }}>
                    {pcr == null ? "No data" :
                      pcr > 1.5 ? "Heavy put buying -- strong bullish hedging, potential reversal zone." :
                      pcr > 1.3 ? "Put-heavy positioning -- markets expect support, mild bullish bias." :
                      pcr < 0.7 ? "Call-heavy positioning -- complacency or bearish outlook from market." :
                      pcr < 0.5 ? "Extreme call buying -- bearish signal, watch for reversal." :
                      "Balanced PCR -- no clear directional bias from options market."
                    }
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: "var(--dim)", marginBottom: 8 }}>MAX PAIN ANALYSIS</div>
                  <div style={{ fontSize: 13, color: "var(--accent)", fontWeight: 600, marginBottom: 4 }}>
                    {data.max_pain ? Number(data.max_pain).toLocaleString("en-IN") : "--"}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text)", lineHeight: 1.8 }}>
                    {data.max_pain && data.nifty_close
                      ? `Spot is ${Number(data.nifty_close) > data.max_pain ? "ABOVE" : "BELOW"} max pain by `
                        + `${Math.abs(Number(data.nifty_close) - data.max_pain).toFixed(0)} points. `
                        + (Math.abs(Number(data.nifty_close) - data.max_pain) > 200
                            ? "Expect gravitational pull toward max pain near expiry."
                            : "Near max pain -- low directional conviction from options market.")
                      : "No data"
                    }
                  </div>
                </div>
              </div>
            </div>
          )}
        </>}
      </div>
    </div>
  );
}