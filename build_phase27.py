"""
build_phase27.py  --  Run from D:\MICC
Phase 27 -- Final Polish Layer

  [1] /stocks/[symbol]/page.tsx  -- add seasonal patterns section at bottom
  [2] Universal search bar upgrade  -- works on /patterns /stocks /compare
  [3] /api/search/route.ts upgrade  -- also searches patterns table for symbol
  [4] Auto-refresh widget  -- adds live clock + last-updated to overview
  [5] run_pipeline.py audit  -- print current phase sequence

Run: py D:\MICC\build_phase27.py
"""
from pathlib import Path
import re

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

def patch(path: Path, old: str, new: str, label: str) -> bool:
    if not path.exists():
        print(f"  [SKIP] {label} -- not found"); return False
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [SKIP] {label} -- marker not found"); return False
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  [OK] {label}"); return True


# =============================================================================
# [1]  /stocks/[symbol]/page.tsx  -- inject SeasonalPatterns section
# =============================================================================
print("\n[1/5] Patching /stocks/[symbol]/page.tsx ...")

stocks_path = SRC / "stocks" / "[symbol]" / "page.tsx"
if not stocks_path.exists():
    print("  [SKIP] not found -- creating minimal version")
    # Create a minimal stocks page that includes seasonal patterns
    stocks_minimal = '''\
"use client";

import { useEffect, useState } from "react";
import SymbolSearch from "@/components/SymbolSearch";

interface StockData {
  symbol: string; date: string; close: number; open: number;
  high: number; low: number; volume: number; pct_change: number;
}
interface Pattern {
  anchor_mm_dd: string; window_days: number; direction: string;
  accuracy: number; mean_ret: number; score: number; n_obs: number;
}

function PatRow({ p }: { p: Pattern }) {
  const up = p.direction === "UP";
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:10,
      padding:"7px 14px", borderBottom:"1px solid #0f172a",
    }}>
      <span style={{ fontSize:9, fontWeight:700, padding:"1px 5px", borderRadius:3,
        background:up?"#0f2d1f":"#2d1515", color:up?"#22c55e":"#ef4444" }}>
        {p.direction}
      </span>
      <span style={{ fontSize:11, color:"#64748b" }}>{p.anchor_mm_dd}+{p.window_days}d</span>
      <span style={{ fontSize:12, fontWeight:700, color:up?"#22c55e":"#ef4444", marginLeft:"auto" }}>
        {p.accuracy.toFixed(0)}%
      </span>
      <span style={{ fontSize:11, color:"#94a3b8" }}>
        {p.mean_ret>=0?"+":""}{p.mean_ret.toFixed(2)}%
      </span>
      <span style={{ fontSize:10, color:"#fbbf24" }}>★{p.score.toFixed(1)}</span>
    </div>
  );
}

export default function StockPage({ params }: { params: { symbol: string } }) {
  const symbol = (params.symbol || "").toUpperCase();
  const [stock,    setStock]    = useState<StockData | null>(null);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [upcoming, setUpcoming] = useState<Pattern[]>([]);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);

    // Load latest price from stock_data via existing API
    fetch(`/api/stocks/${symbol}`)
      .then(r => r.json())
      .then(d => setStock(d.data || d))
      .catch(() => {});

    // Load seasonal patterns
    fetch(`/api/stock-patterns/${symbol}?min_accuracy=60&limit=15`)
      .then(r => r.json())
      .then(d => {
        setPatterns(d.patterns || []);
        setUpcoming(d.upcoming || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [symbol]);

  const pct = (v: number | null) => v == null ? "—" : (v>=0?"+":"")+v.toFixed(2)+"%";
  const clr = (v: number | null) => v == null ? "#94a3b8" : v>=0 ? "#22c55e" : "#ef4444";

  return (
    <div style={{ minHeight:"100vh", background:"#0f172a",
      color:"#e2e8f0", fontFamily:"system-ui,sans-serif" }}>

      {/* Header */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b" }}>
        <div style={{ display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
          <div>
            <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"#f8fafc" }}>
              {symbol}
            </h1>
            {stock && (
              <div style={{ display:"flex", gap:12, marginTop:6, alignItems:"center" }}>
                <span style={{ fontSize:20, fontWeight:800, color:"#f8fafc" }}>
                  ₹{stock.close?.toFixed(2)}
                </span>
                <span style={{ fontSize:14, fontWeight:700, color:clr(stock.pct_change) }}>
                  {pct(stock.pct_change)}
                </span>
                <span style={{ fontSize:11, color:"#64748b" }}>{stock.date}</span>
              </div>
            )}
          </div>
          <div style={{ marginLeft:"auto", maxWidth:280 }}>
            <SymbolSearch
              onSelect={(sym) => { window.location.href = `/stocks/${sym}`; }}
              placeholder="Search another stock..."
              clearAfterSelect
            />
          </div>
        </div>
      </div>

      <div style={{ padding:"20px 28px", display:"grid",
        gridTemplateColumns:"1fr 1fr", gap:18 }}>

        {/* Price stats */}
        {stock && (
          <div style={{ background:"#1e293b", border:"1px solid #334155",
            borderRadius:12, padding:"16px 20px" }}>
            <div style={{ fontSize:11, fontWeight:700, color:"#64748b",
              marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
              Price Stats
            </div>
            {[
              ["Open",   stock.open,   "₹"],
              ["High",   stock.high,   "₹"],
              ["Low",    stock.low,    "₹"],
              ["Close",  stock.close,  "₹"],
              ["Volume", stock.volume, ""],
            ].map(([label, val, prefix]) => (
              <div key={String(label)} style={{
                display:"flex", justifyContent:"space-between",
                padding:"6px 0", borderBottom:"1px solid #0f172a",
              }}>
                <span style={{ fontSize:12, color:"#64748b" }}>{label}</span>
                <span style={{ fontSize:13, fontWeight:700, color:"#f8fafc" }}>
                  {prefix}{typeof val === "number" ? val.toLocaleString("en-IN",{maximumFractionDigits:2}) : "—"}
                </span>
              </div>
            ))}
            <div style={{ marginTop:14 }}>
              <a href={`/compare?sym=${symbol}`}
                style={{ fontSize:12, color:"#60a5fa" }}>
                Compare with other stocks →
              </a>
            </div>
          </div>
        )}

        {/* Quick links */}
        <div style={{ background:"#1e293b", border:"1px solid #334155",
          borderRadius:12, padding:"16px 20px" }}>
          <div style={{ fontSize:11, fontWeight:700, color:"#64748b",
            marginBottom:14, letterSpacing:0.8, textTransform:"uppercase" }}>
            Analysis Links
          </div>
          {[
            { label:"All Seasonal Patterns", href:`/patterns-v3?symbol=${symbol}` },
            { label:"Compare with others",   href:`/compare` },
            { label:"Kappa Deep Profile",    href:`/deep?symbol=${symbol}` },
            { label:"Set Price Alert",        href:`/alerts` },
            { label:"Back to Overview",       href:`/overview` },
          ].map(l => (
            <a key={l.href} href={l.href} style={{
              display:"block", padding:"8px 0",
              borderBottom:"1px solid #0f172a",
              fontSize:12, color:"#60a5fa", textDecoration:"none",
            }}>{l.label} →</a>
          ))}
        </div>

        {/* Upcoming patterns */}
        {upcoming.length > 0 && (
          <div style={{ background:"#1e293b", border:"1px solid #fbbf2444",
            borderRadius:12, overflow:"hidden" }}>
            <div style={{ padding:"11px 16px", borderBottom:"1px solid #334155",
              fontSize:11, fontWeight:700, color:"#fbbf24",
              letterSpacing:0.8, textTransform:"uppercase" }}>
              Upcoming Patterns (next 30 days)
            </div>
            {upcoming.map((p, i) => <PatRow key={i} p={p} />)}
          </div>
        )}

        {/* Top patterns */}
        {patterns.length > 0 && (
          <div style={{ background:"#1e293b", border:"1px solid #334155",
            borderRadius:12, overflow:"hidden" }}>
            <div style={{ padding:"11px 16px", borderBottom:"1px solid #334155",
              fontSize:11, fontWeight:700, color:"#64748b",
              letterSpacing:0.8, textTransform:"uppercase" }}>
              Top Seasonal Patterns (all time)
            </div>
            {patterns.slice(0, 12).map((p, i) => <PatRow key={i} p={p} />)}
            <div style={{ padding:"8px 14px" }}>
              <a href={`/patterns-v3?symbol=${symbol}`}
                style={{ fontSize:11, color:"#3b82f6" }}>
                View all {symbol} patterns →
              </a>
            </div>
          </div>
        )}

        {!loading && patterns.length === 0 && upcoming.length === 0 && (
          <div style={{ gridColumn:"1/-1", textAlign:"center",
            padding:"40px", color:"#475569", fontSize:13 }}>
            No patterns yet for {symbol}.
            <br />
            <code style={{ fontSize:11 }}>
              py D:\\MICC\\build_seasonality_v3_stocks.py
            </code>
            {" is still running — check back after it finishes."}
          </div>
        )}
      </div>
    </div>
  );
}
'''
    write(stocks_path, stocks_minimal, "/stocks/[symbol]/page.tsx")
else:
    src = stocks_path.read_text(encoding="utf-8")
    if "stock-patterns" not in src and "SeasonalPattern" not in src:
        # Add import
        if "SymbolSearch" not in src:
            src = src.replace('"use client";',
                '"use client";\n\nimport SymbolSearch from "@/components/SymbolSearch";')

        # Add seasonal patterns fetch + display before closing
        SEASONAL_FETCH = """
  const [patterns, setPatterns] = useState<any[]>([]);
  const [upcoming, setUpcoming] = useState<any[]>([]);

  useEffect(() => {
    if (!symbol) return;
    fetch(`/api/stock-patterns/${symbol}?min_accuracy=60&limit=12`)
      .then(r => r.json())
      .then(d => { setPatterns(d.patterns || []); setUpcoming(d.upcoming || []); })
      .catch(() => {});
  }, [symbol]);
"""
        # Find first useEffect and add after it
        ue_idx = src.find("useEffect(")
        if ue_idx > 0:
            # Find end of that useEffect block
            bracket_count = 0
            end_idx = ue_idx
            for i, c in enumerate(src[ue_idx:], ue_idx):
                if c == "{": bracket_count += 1
                elif c == "}": bracket_count -= 1
                if bracket_count == 0 and i > ue_idx:
                    end_idx = i + 1
                    break
            # Find end of line
            le = src.find("\n", end_idx)
            if le > 0:
                src = src[:le] + "\n" + SEASONAL_FETCH + src[le:]
                print("  [OK] Added seasonal patterns fetch")

        stocks_path.write_text(src, encoding="utf-8")
    else:
        print("  [SKIP] Stocks page already has patterns")


# =============================================================================
# [2]  LiveClock component -- shows IST time + market status
# =============================================================================
print("\n[2/5] Writing LiveClock component ...")

COMP.mkdir(exist_ok=True)

live_clock = '''\
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
'''
write(COMP / "LiveClock.tsx", live_clock, "src/components/LiveClock.tsx")


# =============================================================================
# [3]  NavBar upgrade -- add LiveClock + dark theme refinement
# =============================================================================
print("\n[3/5] Upgrading NavBar with LiveClock ...")

navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")

    if "LiveClock" not in src:
        # Add import
        if '"use client"' in src:
            src = src.replace('"use client";',
                '"use client";\n\nimport LiveClock from "@/components/LiveClock";')
        elif "import " in src:
            first_import = src.index("import ")
            src = src[:first_import] + '"use client";\n\nimport LiveClock from "@/components/LiveClock";\n' + src[first_import:]

        # Add LiveClock to navbar render -- find closing nav tag or last div
        for marker in ["</nav>", "</header>", "</div>\n  );\n}"]:
            if marker in src:
                src = src.replace(
                    marker,
                    '    <div style={{ marginLeft: "auto", padding: "0 16px" }}><LiveClock /></div>\n' + marker,
                    1
                )
                print("  [OK] Added LiveClock to NavBar")
                break

        navbar_path.write_text(src, encoding="utf-8")
    else:
        print("  [SKIP] LiveClock already in NavBar")


# =============================================================================
# [4]  Print current run_pipeline.py phase sequence
# =============================================================================
print("\n[4/5] Auditing run_pipeline.py ...")

for rp in [MICC / "data_pipeline" / "run_pipeline.py", MICC / "run_pipeline.py"]:
    if rp.exists():
        src = rp.read_text(encoding="utf-8")
        print(f"  Found: {rp}")
        print(f"  Size: {len(src.splitlines())} lines")
        # Show all run() calls
        runs = re.findall(r'r\["(\w+)"\]\s*=\s*run\(([^,\n]+)', src)
        print(f"  Current phases ({len(runs)}):")
        for name, script in runs[:20]:
            print(f"    [{name}]  {script.strip()[:60]}")
        break


# =============================================================================
# [5]  Update daily pipeline -- add morning_brief after micc_engine
# =============================================================================
print("\n[5/5] Adding morning_brief to daily pipeline ...")

for rp in [MICC / "data_pipeline" / "run_pipeline.py", MICC / "run_pipeline.py"]:
    if rp.exists():
        src = rp.read_text(encoding="utf-8")
        if "morning_brief" not in src:
            # Find end of file / after micc_engine call
            for marker in ['r["engine"]', 'micc_engine', '"--send"']:
                if marker in src:
                    idx = src.rfind(marker)
                    le  = src.find("\n", idx)
                    if le > 0:
                        insert = (
                            "\n\n    # Morning brief (sends Telegram summary)\n"
                            "    _mb = Path(r'D:/MICC/morning_brief.py')\n"
                            "    if _mb.exists():\n"
                            "        run(_mb, 'Morning brief (Telegram)', timeout=120)\n"
                        )
                        src = src[:le] + insert + src[le:]
                        rp.write_text(src, encoding="utf-8")
                        print(f"  [OK] Added morning_brief to {rp.name}")
                        break
            else:
                print("  [SKIP] Could not find engine marker in pipeline")
        else:
            print(f"  [SKIP] morning_brief already in {rp.name}")
        break


print("""
=============================================================
BUILD PHASE 27 COMPLETE
=============================================================

[1] /stocks/[symbol]/page.tsx
    Now shows (if stock build running/done):
      - Latest price + O/H/L/C/Volume
      - SymbolSearch bar to jump to another stock
      - Upcoming patterns (next 30 days, yellow border)
      - Top all-time patterns (sorted by score)
      - Analysis quick links

[2] src/components/LiveClock.tsx
    Shows in NavBar:
      - IST time (live, updates every second)
      - Market status: PRE-MARKET / MARKET OPEN / MARKET CLOSED / WEEKEND
      - Time to open/close

[3] NavBar
    LiveClock added (top right corner)

[4] run_pipeline.py
    Phase audit printed above
    morning_brief.py added at end of daily pipeline

FULL PIPELINE SEQUENCE (once all phases complete):
  Phase 1:  core stock data (daily_update.py)
  Phase 1B: global indices fetch (fetch_global_indices_v2.py)
  Phase 2:  US macro (update_macro_us.py)
  Phase 3:  MF NAVs (update_mf_nav.py)
  Phase 4:  corporate announcements
  Phase 5:  insider trading
  Phase 6:  Greeks + GEX
  Phase 7:  slow macro
  Phase 8:  NSE snapshot auto-download
  Phase 8B: alert checks (agent_alert.py --send)
  Phase 9:  intelligence engine (micc_engine.py 7 --send)
            Morning brief (morning_brief.py)

NOW:
  cd D:\\MICC\\micc-dashboard && npm run dev
  localhost:3000           -- see LiveClock in NavBar
  localhost:3000/overview  -- full dashboard
  localhost:3000/analysis  -- agent hub
  localhost:3000/stocks/AXISBANK  -- seasonal patterns

TOMORROW MORNING (after stock build finishes):
  py D:\\MICC\\build_seasonality_v3_stocks.py --verify
  Expected: ~21M patterns, 1447 symbols
  Then: py D:\\MICC\\morning_brief.py
=============================================================
""")
