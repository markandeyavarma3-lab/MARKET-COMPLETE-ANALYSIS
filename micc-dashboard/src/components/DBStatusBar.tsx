"use client";
import { useEffect, useState } from "react";

interface TableStatus {
  table: string;
  latest_date: string;
}

export default function DBStatusBar() {
  const [status,  setStatus]  = useState<TableStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/db-status", { cache: "no-store" })
      .then(r => r.json())
      .then(d => { setStatus(d.status || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return null;

  // Check if market_snapshot is stale (older than 3 days)
  const snap = status.find(s => s.table === "market_snapshot");
  const snapDate = snap?.latest_date || "N/A";
  const daysSince = snapDate !== "N/A"
    ? Math.floor((Date.now() - new Date(snapDate).getTime()) / 86400000)
    : 99;
  const isStale = daysSince > 3;

  return (
    <div style={{
      display: "flex",
      flexWrap: "wrap",
      gap: 6,
      padding: "6px 12px",
      background: isStale ? "rgba(255,170,0,0.07)" : "rgba(0,255,128,0.04)",
      border: `1px solid ${isStale ? "var(--warn)" : "var(--border)"}`,
      borderRadius: 5,
      marginBottom: 10,
      alignItems: "center",
    }}>
      {isStale && (
        <span style={{
          fontFamily: "monospace", fontSize: 10,
          color: "var(--warn)", marginRight: 8, fontWeight: 700,
        }}>
          DATA STALE — run: py micc_engine.py 7 --send
        </span>
      )}
      {status.map(({ table, latest_date }) => (
        <span key={table} style={{
          fontFamily: "monospace", fontSize: 9,
          color: "var(--muted)",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 3,
          padding: "2px 6px",
        }}>
          <span style={{ color: "var(--dim)" }}>{table.replace("_", " ")}:</span>
          {" "}{latest_date}
        </span>
      ))}
    </div>
  );
}
