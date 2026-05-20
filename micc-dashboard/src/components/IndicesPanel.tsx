"use client";
import { useState, useEffect, useCallback } from "react";
import DurationBar from "./DurationBar";
import { fmtPct, colorPct } from "@/lib/utils";

interface IndexRow {
  name: string;
  pct_change: number;
  start_close: number;
  end_close: number;
}

export default function IndicesPanel() {
  const [days,    setDays]    = useState(7);
  const [data,    setData]    = useState<{ gainers: IndexRow[]; losers: IndexRow[]; total: number } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (d: number) => {
    setLoading(true);
    try {
      const r = await fetch("/api/indices?days=" + d, { cache: "no-store" });
      setData(await r.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days); }, [days, load]);

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="section-label" style={{ margin: 0, border: "none", padding: 0 }}>
          Index Performance -- {data?.total || 0} indices
        </span>
        <DurationBar value={days} onChange={(d) => { setDays(d); load(d); }} />
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 20 }}>
          <div className="spinner" style={{ width: 20, height: 20 }} />
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div className="section-label">Top 10 Gainers</div>
            {(data?.gainers || []).map((r, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "5px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)", minWidth: 18 }}>
                  {i + 1}
                </span>
                <span style={{ fontSize: 11, flex: 1, color: "var(--text)" }}>
                  {r.name.slice(0, 28)}
                </span>
                <div style={{ minWidth: 80, height: 4, background: "var(--border2)", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{
                    width: Math.min(Math.abs(r.pct_change) / 10 * 100, 100) + "%",
                    height: "100%",
                    background: "var(--pos)",
                    borderRadius: 2,
                  }} />
                </div>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--pos)", minWidth: 60, textAlign: "right" }}>
                  {r.pct_change != null ? "+" + Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
          <div>
            <div className="section-label">Bottom 10 Decliners</div>
            {(data?.losers || []).map((r, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "5px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--muted)", minWidth: 18 }}>
                  {i + 1}
                </span>
                <span style={{ fontSize: 11, flex: 1, color: "var(--text)" }}>
                  {r.name.slice(0, 28)}
                </span>
                <div style={{ minWidth: 80, height: 4, background: "var(--border2)", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{
                    width: Math.min(Math.abs(r.pct_change) / 10 * 100, 100) + "%",
                    height: "100%",
                    background: "var(--neg)",
                    borderRadius: 2,
                  }} />
                </div>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "var(--neg)", minWidth: 60, textAlign: "right" }}>
                  {r.pct_change != null ? Number(r.pct_change).toFixed(2) + "%" : "--"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
