"use client";

import LiveClock from "@/components/LiveClock";
import Link            from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const PAGES = [
  { href: "/",            label: "OVERVIEW"   },
  { href: "/analysis",    label: "ANALYTICS"  },
  { href: "/streaks",     label: "STREAKS"    },
  { href: "/indices",     label: "INDICES"    },
  { href: "/options",     label: "OPTIONS"    },
  { href: "/macro",       label: "MACRO"      },
  { href: "/patterns",    label: "PATTERNS"   },
  { href: "/patterns-v3", label: "PATS-V3"    },
  { href: "/global",      label: "GLOBAL"     },
  { href: "/mf",          label: "MF NAV"     },
  { href: "/watchlist",   label: "WATCHLIST"  },
  { href: "/eta",         label: "ETA"        },
  { href: "/alerts",      label: "ALERTS"     },
  { href: "/compare",     label: "COMPARE"    },
  { href: "/conviction",  label: "CONVICTION" },
  { href: "/analytics", label: "ANALYTICS" },
  { href: "/fusion",     label: "FUSION"     },
  { href: "/portfolio",   label: "PORTFOLIO"  },
  { href: "/deep",        label: "DEEP"       },
  { href: "/backtest",    label: "BACKTEST"   },
  { href: "/settings",    label: "SETTINGS"   }
];

export default function NavBar() {
  const path = usePathname();
  const [time, setTime] = useState("");

  useEffect(() => {
    function tick() {
      setTime(
        new Date().toLocaleTimeString("en-IN", {
          hour: "2-digit", minute: "2-digit", second: "2-digit",
          timeZone: "Asia/Kolkata",
        }) + " IST"
      );
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 100,
      background: "var(--bg)", borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center",
      padding: "0 16px", height: 48, gap: 0, overflowX: "auto",
    }}>
      <div style={{
        fontFamily: "'Share Tech Mono','JetBrains Mono',monospace",
        fontSize: 15, fontWeight: 700, letterSpacing: "0.18em",
        color: "var(--accent)", marginRight: 20, whiteSpace: "nowrap", flexShrink: 0,
      }}>
        MICC
      </div>
      <nav style={{ display: "flex", gap: 1, flex: 1 }}>
        {PAGES.map(({ href, label }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} style={{
              padding: "6px 11px", fontSize: 10,
              fontFamily: "'JetBrains Mono',monospace",
              letterSpacing: "0.08em",
              fontWeight: active ? 700 : 400,
              color: active ? "var(--accent)" : "var(--muted)",
              borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
              textDecoration: "none", transition: "color 0.15s",
              whiteSpace: "nowrap",
            }}>
              {label}
            </Link>
          );
        })}
          <div style={{ marginLeft: "auto", padding: "0 16px" }}><LiveClock /></div>
</nav>
      <div style={{
        fontFamily: "monospace", fontSize: 10,
        color: "var(--dim)", whiteSpace: "nowrap", flexShrink: 0,
      }} suppressHydrationWarning>{time}</div>
    </header>
  );
}
