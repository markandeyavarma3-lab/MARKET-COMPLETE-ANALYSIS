"use client";

import { useEffect, useState } from "react";

function getMarketStatus(): { status: string; color: string; next: string } {
  const now = new Date();
  // Convert to IST (UTC+5:30)
  const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
  const day  = ist.getUTCDay(); // 0=Sun, 6=Sat
  const h    = ist.getUTCHours();
  const m    = ist.getUTCMinutes();
  const mins = h * 60 + m;

  if (day === 0 || day === 6) {
    return { status: "WEEKEND", color: "#64748b", next: "Mon 09:15" };
  }
  if (mins < 9 * 60 + 15) {
    return { status: "PRE-MARKET", color: "#fbbf24", next: `Opens ${9 * 60 + 15 - mins}m` };
  }
  if (mins <= 15 * 60 + 30) {
    return { status: "MARKET OPEN", color: "#22c55e", next: `Closes ${15 * 60 + 30 - mins}m` };
  }
  return { status: "MARKET CLOSED", color: "#ef4444", next: "Tomorrow 09:15" };
}

export default function LiveClock() {
  const [time,   setTime]   = useState("");
  const [status, setStatus] = useState(getMarketStatus());

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      const ist = new Date(now.getTime() + 5.5 * 60 * 60 * 1000);
      setTime(ist.toUTCString().slice(17, 25) + " IST");
      setStatus(getMarketStatus());
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{ display:"flex", alignItems:"center", gap:10 }}>
      <span style={{
        fontSize: 10, fontWeight: 700, padding: "2px 8px",
        borderRadius: 4, background: status.color + "22", color: status.color,
        letterSpacing: 0.5,
      }}>
        {status.status}
      </span>
      <span style={{ fontSize: 11, color: "#475569", fontFamily: "monospace" }}>
        {time}
      </span>
      <span style={{ fontSize: 10, color: "#334155" }}>
        ({status.next})
      </span>
    </div>
  );
}
