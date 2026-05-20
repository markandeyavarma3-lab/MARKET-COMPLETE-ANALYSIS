"use client";
import { useState, useEffect, useCallback } from "react";
import AlphaPanel        from "@/components/AlphaPanel";
import BetaPanel         from "@/components/BetaPanel";
import GammaPanel        from "@/components/GammaPanel";
import DeltaPanel        from "@/components/DeltaPanel";
import RefreshController from "@/components/RefreshController";

interface Reports { alpha?: any; beta?: any; gamma?: any; delta?: any; ts?: number }

const NAV_CARDS = [
  { href: "/streaks", label: "STREAK LEADERBOARD", desc: "Multi-screen conviction + regime filter", color: "var(--accent)" },
  { href: "/indices", label: "INDEX PERFORMANCE",  desc: "144 indices, top 25 each, full table",   color: "var(--pos)"    },
  { href: "/options", label: "OPTIONS CHAIN",      desc: "Nifty PCR, GEX, Max Pain, OI change",    color: "var(--info)"   },
  { href: "/macro",   label: "MACRO DASHBOARD",    desc: "Fed, US 10Y, India CPI, FX reserves",    color: "var(--warn)"   },
  { href: "/mf",      label: "MF NAV TRACKER",     desc: "Top funds by NAV, gainers, categories",  color: "var(--bull)"   },
]

export default function Home() {
  const [reports,  setReports]  = useState<Reports>({});
  const [lastTime, setLastTime] = useState("");
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  const fetchReports = useCallback(async () => {
    try {
      const r = await fetch("/api/reports", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setReports(data);
      setLastTime(new Date().toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Kolkata",
      }));
      setError("");
    } catch (e: any) { setError(e.message || "Fetch failed"); }
  }, []);

  const triggerRefresh = useCallback(async () => {
    setLoading(true); await fetchReports(); setLoading(false);
  }, [fetchReports]);

  useEffect(() => { triggerRefresh(); }, []); // eslint-disable-line

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      
      
      {/* Sub-header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "8px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface)",
      }}>
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)" }}>
          Market Intelligence Command Center -- Overview
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {error    && <span style={{ color:"var(--neg)", fontSize:10, fontFamily:"monospace" }}>{error}</span>}
          {loading && !error && <span style={{ color:"var(--accent)", fontSize:10, fontFamily:"monospace" }}>Loading...</span>}
          {lastTime && !loading && <span style={{ color:"var(--dim)", fontSize:10, fontFamily:"monospace" }}>Updated {lastTime}</span>}
          <RefreshController onRefresh={triggerRefresh} intervalSec={90} autoStart={false} />
        </div>
      </div>

      <div style={{ padding: "16px 20px", maxWidth: 1600, margin: "0 auto" }}>
        <div style={{ marginBottom: 14 }}>
          <AlphaPanel data={reports.alpha ?? null} />
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:14, marginBottom:14 }}>
          <BetaPanel  data={reports.beta  ?? null} />
          <GammaPanel data={reports.gamma ?? null} />
        </div>
        <div style={{ marginBottom: 18 }}>
          <DeltaPanel data={reports.delta ?? null} />
        </div>

        {/* Quick-nav cards */}
        <div style={{
          borderTop: "1px solid var(--border)", paddingTop: 14,
          display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 10,
        }}>
          {NAV_CARDS.map(({ href, label, desc, color }) => (
            <a key={href} href={href} style={{ textDecoration:"none" }}>
              <div
                style={{
                  padding:"14px 16px", background:"var(--surface)",
                  border:"1px solid var(--border)", borderRadius:6, cursor:"pointer",
                  transition:"border-color 0.15s",
                }}
                onMouseEnter={e=>(e.currentTarget.style.borderColor=color)}
                onMouseLeave={e=>(e.currentTarget.style.borderColor="var(--border)")}
              >
                <div style={{
                  fontFamily:"monospace", fontSize:10, fontWeight:700,
                  letterSpacing:"0.1em", color, marginBottom:6,
                }}>{label}</div>
                <div style={{ fontFamily:"monospace", fontSize:10, color:"var(--dim)" }}>{desc}</div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}