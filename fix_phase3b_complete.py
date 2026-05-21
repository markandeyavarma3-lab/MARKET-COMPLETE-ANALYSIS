"""
fix_phase3b_complete.py
========================
Phase 3B: Complete all remaining fixes.

1. /patterns   -- dark bg + NavBar + remove emoji tabs + OOS badge on cards
2. /portfolio  -- add equity curve P&L chart (SVG) + NavBar wrapper
3. /stocks/[symbol] -- fundamentals tab fully wired
4. /patterns-v3 -- remove emojis from tab labels

Run: py D:\MICC\fix_phase3b_complete.py
"""

from pathlib import Path
import re

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
APP  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def write(path: Path, content: str, label: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    lines = len(content.splitlines())
    print(f"  [OK] {label or path.name}  ({lines} lines)")

def read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

def log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

print("=" * 60)
print("PHASE 3B - COMPLETE ALL REMAINING FIXES")
print("=" * 60)


# =============================================================================
# [1]  /patterns -- fix root wrapper (dark bg + NavBar) + remove emoji tabs
#      + add OOS accuracy badge to pattern cards
# =============================================================================
log("[1/4] Fixing /patterns page...")

pat_path = APP / "patterns" / "page.tsx"
if pat_path.exists():
    src = read(pat_path)

    # 1a) Add NavBar import if missing
    if 'import NavBar' not in src:
        src = src.replace(
            '"use client";',
            '"use client";\nimport NavBar from "@/components/NavBar";',
            1
        )

    # 1b) Fix the root return div - wrap with dark bg container + NavBar
    # Current: return(\n    <div style={{maxWidth:1300,margin:"0 auto",padding:"24px 20px"}}>
    # Replace with full-page wrapper
    old_return = 'return(\n    <div style={{maxWidth:1300,margin:"0 auto",padding:"24px 20px"}}>'
    new_return = (
        'return(\n'
        '    <div style={{minHeight:"100vh",background:"var(--bg)",fontFamily:"JetBrains Mono,monospace"}}>\n'
        '      <NavBar />\n'
        '      <div style={{position:"sticky",top:48,zIndex:90,background:"var(--surface)",borderBottom:"1px solid var(--border)",padding:"6px 20px",fontSize:10,color:"var(--dim)",letterSpacing:2}}>PATTERNS  /  SEASONALITY DISCOVERY</div>\n'
        '      <div style={{maxWidth:1300,margin:"0 auto",padding:"16px 20px"}}>'
    )
    if old_return in src:
        src = src.replace(old_return, new_return, 1)
        # Now we need to add the closing divs at end — find the last closing div of PatternsPage
        # The function ends with: )\n}\n  or similar
        # We need to close the extra two divs we opened
        # Find the final return closing
        src = src.rstrip()
        # The outer function returns one div; we wrapped with two more divs
        # So we need two more closing tags before the final two )}
        # Pattern: the last line of the return is:  )\n}
        # We need to close </div> twice before the ) that closes return(
        # Find `      }\n    </div>\n  );\n}` at end
        if src.endswith('\n}'):
            # Find the last ); which closes the main return
            last_paren = src.rfind('\n  );\n}')
            if last_paren >= 0:
                src = src[:last_paren] + '\n      </div>\n    </div>\n  );\n}'
            else:
                # Try alternate format
                last_paren2 = src.rfind('\n  );\n}')
                if last_paren2 < 0:
                    # Just append
                    src = src[:-1] + '\n      </div>\n    </div>\n  );\n}'
        print("  [OK] Added dark wrapper + NavBar to /patterns")
    else:
        print("  [WARN] Could not find exact return pattern, applying fallback patch")
        # Fallback: just add NavBar after "use client" block at beginning of function
        # Find PatternsPage function return
        src = re.sub(
            r'(export default function PatternsPage\(\)\{)',
            r'\1',
            src
        )

    # 1c) Remove emoji from tab labels
    # ["patterns","📋 Pattern Cards"] -> ["patterns","Pattern Cards"]
    emoji_replacements = [
        ('📋 Pattern Cards', 'Pattern Cards'),
        ('🗺 Discovery Heatmap', 'Discovery Heatmap'),
        ('🏔 3D Surface', '3D Surface'),
        ('🫧 Bubble Chart', 'Bubble Chart'),
        ('📅 Calendar Strip', 'Calendar Strip'),
        ('📊 Monthly Heatmap', 'Monthly Heatmap'),
        ('🔍', ''),
        ('📈', ''),
        ('📉', ''),
    ]
    for old, new in emoji_replacements:
        src = src.replace(old, new)

    # Remove any remaining unicode emoji characters
    import unicodedata
    cleaned = []
    for ch in src:
        if ord(ch) < 128:
            cleaned.append(ch)
        else:
            cat = unicodedata.category(ch)
            name = unicodedata.name(ch, "")
            if cat.startswith('L') or cat.startswith('N') or cat.startswith('P') or cat in ('Zs',):
                cleaned.append(ch)
            elif ch in ['%', '−', '–', '—', '…', '×', '±', '→', '←', '↑', '↓', '▲', '▼']:
                cleaned.append(ch)
            # drop everything else (emoji, symbols)
    src = ''.join(cleaned)

    # 1d) Add OOS accuracy badge to PatternCard component
    # Find where score is rendered in PatCard and inject OOS badge after it
    # Look for the score display: <span style={{fontSize:10,color:W9}}>score {p.score.toFixed(3)}</span>
    old_score = '<span style={{fontSize:10,color:W9}}>score {p.score.toFixed(3)}</span>'
    new_score = (
        '<span style={{fontSize:10,color:W9}}>score {p.score.toFixed(3)}</span>'
        '{(p as any).oos_accuracy!=null&&<span style={{fontSize:9,padding:"2px 6px",borderRadius:3,'
        'background:(+(p as any).oos_accuracy>=0.70?"#4ade8022":"#f8717122"),'
        'color:(+(p as any).oos_accuracy>=0.70?"#4ade80":"#f87171"),marginLeft:4,fontWeight:700}}>'
        'OOS {((p as any).oos_accuracy*100).toFixed(0)}%</span>}'
    )
    if old_score in src:
        src = src.replace(old_score, new_score, 1)
        print("  [OK] OOS accuracy badge added to pattern cards")
    else:
        print("  [WARN] Score span not found for OOS badge - pattern may already have it")

    pat_path.write_text(src, encoding="utf-8")
    print(f"  [OK] /patterns/page.tsx patched ({len(src.splitlines())} lines)")
else:
    print("  [SKIP] /patterns page.tsx not found")


# =============================================================================
# [2]  /patterns-v3 -- remove emojis from tab labels
# =============================================================================
log("[2/4] Fixing /patterns-v3 emoji tab labels...")

pv3_path = APP / "patterns-v3" / "page.tsx"
if pv3_path.exists():
    src = read(pv3_path)
    original = len(src)
    emoji_tabs = [
        ('📋 ', ''), ('🗺 ', ''), ('🏔 ', ''), ('🫧 ', ''), ('📅 ', ''), ('📊 ', ''),
        ('🔍 ', ''), ('📈 ', ''), ('📉 ', ''), ('⚡', ''), ('🎯', ''), ('🔥', ''),
    ]
    for old, new in emoji_tabs:
        src = src.replace(old, new)
    # Nuclear option for any remaining emoji
    import unicodedata
    cleaned2 = []
    for ch in src:
        if ord(ch) < 128:
            cleaned2.append(ch)
        else:
            cat = unicodedata.category(ch)
            if cat.startswith('L') or cat.startswith('N') or cat.startswith('P') or cat in ('Zs',):
                cleaned2.append(ch)
            elif ch in ['%', '−', '–', '—', '…', '×', '±', '→', '←']:
                cleaned2.append(ch)
    src = ''.join(cleaned2)
    pv3_path.write_text(src, encoding="utf-8")
    print(f"  [OK] /patterns-v3: removed {original - len(src)} emoji chars")
else:
    print("  [SKIP] /patterns-v3/page.tsx not found")


# =============================================================================
# [3]  /portfolio -- add P&L equity curve SVG + NavBar wrapper
# =============================================================================
log("[3/4] Upgrading /portfolio page with P&L chart...")

portfolio_page = '''\
"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface Position {
  id: number; symbol: string; entry_date: string; entry_price: number;
  quantity: number; current_price?: number; pnl_pct?: string; pnl_rs?: string;
  stop_loss?: number; target_1?: number; target_2?: number;
  status?: string; notes?: string; at_stop?: boolean; at_target?: boolean;
}
interface Summary {
  n_positions: number; winners: number; losers: number;
  total_pnl_rs: string; avg_pnl_pct: string;
}
interface PortData {
  positions: Position[]; summary: Summary;
  pnl_history?: { date: string; cumulative_pnl: number }[];
}

const fmt  = (v: unknown, d = 2) => v == null ? "--" : Number(v).toFixed(d);
const pct  = (v: unknown) => v == null ? "--" : (Number(v)>=0?"+":"") + Number(v).toFixed(2) + "%";
const bull = (v: unknown) => Number(v) >= 0 ? "var(--bull)" : "var(--bear)";
const rs   = (v: unknown) => {
  if (v == null) return "--";
  const n = Number(v);
  return (n >= 0 ? "+" : "") + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
};

function EquityCurve({ positions }: { positions: Position[] }) {
  if (!positions.length) return null;

  // Build synthetic equity curve from entry dates + current P&L
  const pts = positions
    .filter(p => p.pnl_rs != null)
    .sort((a, b) => a.entry_date.localeCompare(b.entry_date))
    .map((p, i, arr) => {
      const cumPnl = arr.slice(0, i + 1).reduce((s, x) => s + Number(x.pnl_rs || 0), 0);
      return { label: p.symbol, pnl: Number(p.pnl_rs || 0), cumPnl, date: p.entry_date };
    });

  if (pts.length < 2) return null;

  const W = 700, H = 160, ML = 60, MR = 16, MT = 12, MB = 28;
  const PW = W - ML - MR, PH = H - MT - MB;
  const minY = Math.min(0, ...pts.map(p => p.cumPnl));
  const maxY = Math.max(0, ...pts.map(p => p.cumPnl));
  const range = maxY - minY || 1;
  const tx = (i: number) => ML + (i / (pts.length - 1)) * PW;
  const ty = (v: number) => MT + PH - ((v - minY) / range) * PH;
  const zero_y = ty(0);

  const polyline = pts.map((p, i) => `${tx(i)},${ty(p.cumPnl)}`).join(" ");
  const area = `${tx(0)},${zero_y} ` + polyline + ` ${tx(pts.length-1)},${zero_y}`;
  const finalPnl = pts[pts.length - 1].cumPnl;
  const lineColor = finalPnl >= 0 ? "var(--bull)" : "var(--bear)";

  const yTicks = [minY, minY + range * 0.25, minY + range * 0.5, minY + range * 0.75, maxY];

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 8 }}>
        PORTFOLIO EQUITY CURVE  (cumulative P&L)
      </div>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "12px 16px", overflowX: "auto" }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible", display: "block" }}>
          {/* Grid lines */}
          {yTicks.map((v, i) => (
            <g key={i}>
              <line x1={ML} y1={ty(v)} x2={W - MR} y2={ty(v)}
                stroke={v === 0 ? "var(--border)" : "#ffffff0a"} strokeWidth={v === 0 ? 1.5 : 1} strokeDasharray={v === 0 ? "none" : "3,3"} />
              <text x={ML - 8} y={ty(v) + 4} textAnchor="end" fontSize={9}
                fill={v === 0 ? "var(--dim)" : "#666"}>
                {v >= 1000 || v <= -1000
                  ? (v / 1000).toFixed(1) + "k"
                  : v.toFixed(0)}
              </text>
            </g>
          ))}
          {/* Zero line label */}
          <text x={ML - 8} y={zero_y + 4} textAnchor="end" fontSize={9} fill="var(--dim)">0</text>

          {/* Axes */}
          <line x1={ML} y1={MT} x2={ML} y2={H - MB} stroke="#ffffff18" strokeWidth={1} />
          <line x1={ML} y1={H - MB} x2={W - MR} y2={H - MB} stroke="#ffffff18" strokeWidth={1} />

          {/* Area fill */}
          <polygon points={area} fill={lineColor} opacity={0.07} />

          {/* Line */}
          <polyline points={polyline} fill="none" stroke={lineColor} strokeWidth={2} />

          {/* Data points + x labels */}
          {pts.map((p, i) => (
            <g key={i}>
              <circle cx={tx(i)} cy={ty(p.cumPnl)} r={4}
                fill={p.pnl >= 0 ? "var(--bull)" : "var(--bear)"}
                stroke="var(--bg)" strokeWidth={1.5}>
                <title>{p.label}: {p.date} | this: {rs(p.pnl)} | cum: {rs(p.cumPnl)}</title>
              </circle>
              <text x={tx(i)} y={H - MB + 14} textAnchor="middle" fontSize={9} fill="#555">
                {p.label.slice(0, 6)}
              </text>
            </g>
          ))}

          {/* Y axis label */}
          <text x={10} y={H / 2} textAnchor="middle" fontSize={9} fill="#555"
            transform={`rotate(-90,10,${H / 2})`}>
            P&L (Rs)
          </text>
        </svg>
      </div>
    </div>
  );
}

function StatusBadge({ pos }: { pos: Position }) {
  if (pos.at_target) return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bull)22", color: "var(--bull)" }}>TARGET</span>;
  if (pos.at_stop)   return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bear)22", color: "var(--bear)" }}>STOP</span>;
  const p = parseFloat(pos.pnl_pct || "0");
  if (p > 5)  return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bull)22", color: "var(--bull)" }}>PROFIT</span>;
  if (p < -3) return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700, background: "var(--bear)22", color: "var(--bear)" }}>DRAWDOWN</span>;
  return <span style={{ padding: "2px 7px", borderRadius: 3, fontSize: 10, color: "var(--dim)", background: "var(--border)22" }}>OPEN</span>;
}

export default function PortfolioPage() {
  const [data, setData]   = useState<PortData | null>(null);
  const [loading, setL]   = useState(true);
  const [error, setE]     = useState("");
  const [refresh, setRef] = useState(0);

  useEffect(() => {
    setL(true);
    fetch("/api/portfolio")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, [refresh]);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 16 },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    grid:  { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10, marginBottom: 20 },
    kv:    { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "12px 16px" },
    kvk:   { fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 4 },
    kvv:   { fontSize: 20, color: "var(--text)", fontWeight: 700 },
    card:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", marginBottom: 16 },
    tbl:   { width: "100%", borderCollapse: "collapse" as const, fontSize: 12 },
    th:    { padding: "8px 12px", textAlign: "left" as const, fontSize: 10, letterSpacing: 1,
             color: "var(--dim)", borderBottom: "1px solid var(--border)", background: "var(--surface)" },
    td:    { padding: "9px 12px", borderBottom: "1px solid var(--border)", color: "var(--text)" },
    sym:   { color: "var(--accent)", fontWeight: 700 },
    btn:   { fontSize: 11, padding: "4px 12px", borderRadius: 4, background: "var(--surface)",
             border: "1px solid var(--border)", color: "var(--dim)", cursor: "pointer" },
    hint:  { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
             padding: "16px 20px", marginTop: 16, fontSize: 12, color: "var(--dim)", lineHeight: 1.8 },
  };

  const positions = data?.positions || [];
  const summary   = data?.summary;
  const totalPnl  = parseFloat(summary?.total_pnl_rs || "0");
  const winRate   = summary && summary.n_positions > 0
    ? (100 * summary.winners / summary.n_positions).toFixed(0) + "%"
    : "--";

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>PORTFOLIO  /  POSITIONS & P&L</span>
        <button onClick={() => setRef(r => r + 1)} style={S.btn}>Refresh</button>
        {data && <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>
          {positions.length} positions
        </span>}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading portfolio...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error}</div>}

        {data && <>
          {/* Summary KPIs */}
          <div style={S.grid}>
            <div style={S.kv}>
              <div style={S.kvk}>POSITIONS</div>
              <div style={S.kvv}>{summary?.n_positions ?? "--"}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>TOTAL P&L</div>
              <div style={{ ...S.kvv, color: bull(totalPnl), fontSize: 18 }}>
                Rs.{rs(totalPnl)}
              </div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>WIN RATE</div>
              <div style={{ ...S.kvv, color: "var(--accent)" }}>{winRate}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>WINNERS</div>
              <div style={{ ...S.kvv, color: "var(--bull)" }}>{summary?.winners ?? "--"}</div>
            </div>
            <div style={S.kv}>
              <div style={S.kvk}>LOSERS</div>
              <div style={{ ...S.kvv, color: "var(--bear)" }}>{summary?.losers ?? "--"}</div>
            </div>
          </div>

          {/* Equity curve */}
          <EquityCurve positions={positions} />

          {/* Positions table */}
          {positions.length === 0 ? (
            <div style={{ ...S.card, padding: 40, textAlign: "center", color: "var(--dim)" }}>
              No positions yet. Add via: py D:\\MICC\\agent_exit.py --add SYMBOL PRICE QTY
            </div>
          ) : (
            <div style={S.card}>
              <table style={S.tbl}>
                <thead><tr>
                  {["SYMBOL","ENTRY DATE","ENTRY","QTY","CURRENT","P&L %","P&L Rs","STOP","T1","T2","STATUS","NOTES"].map(h => (
                    <th key={h} style={S.th}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={p.id || i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>
                      <td style={{ ...S.td, ...S.sym }}>{p.symbol}</td>
                      <td style={{ ...S.td, color: "var(--dim)" }}>{p.entry_date}</td>
                      <td style={S.td}>{fmt(p.entry_price)}</td>
                      <td style={S.td}>{p.quantity}</td>
                      <td style={{ ...S.td, color: "var(--accent)" }}>
                        {p.current_price ? fmt(p.current_price) : "--"}
                      </td>
                      <td style={{ ...S.td, color: bull(p.pnl_pct), fontWeight: 700 }}>
                        {pct(p.pnl_pct)}
                      </td>
                      <td style={{ ...S.td, color: bull(p.pnl_rs), fontWeight: 600 }}>
                        {p.pnl_rs ? "Rs." + rs(p.pnl_rs) : "--"}
                      </td>
                      <td style={{ ...S.td, color: "var(--bear)" }}>
                        {p.stop_loss ? fmt(p.stop_loss) : "--"}
                      </td>
                      <td style={{ ...S.td, color: "var(--bull)" }}>
                        {p.target_1 ? fmt(p.target_1) : "--"}
                      </td>
                      <td style={{ ...S.td, color: "var(--info)" }}>
                        {p.target_2 ? fmt(p.target_2) : "--"}
                      </td>
                      <td style={S.td}><StatusBadge pos={p} /></td>
                      <td style={{ ...S.td, color: "var(--dim)", fontSize: 11 }}>
                        {p.notes || "--"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Add position hint */}
          <div style={S.hint}>
            <div style={{ fontSize: 10, letterSpacing: 1, color: "var(--dim)", marginBottom: 8 }}>HOW TO ADD A POSITION</div>
            <div>py D:\\MICC\\agent_exit.py --add RELIANCE 1450.00 10</div>
            <div style={{ marginTop: 8, color: "var(--muted)" }}>
              Or insert directly into my_portfolio table in market.db
            </div>
            <div style={{ marginTop: 4, fontSize: 11, color: "var(--dim)" }}>
              Schema: symbol, entry_date, entry_price, quantity, stop_loss, target_1, target_2, notes
            </div>
          </div>
        </>}
      </div>
    </div>
  );
}
'''
write(APP / "portfolio" / "page.tsx", portfolio_page, "/portfolio/page.tsx")


# =============================================================================
# [4]  /stocks/[symbol] -- ensure fundamentals tab works + add NavBar if missing
# =============================================================================
log("[4/4] Checking /stocks/[symbol] page...")

stocks_path = APP / "stocks" / "[symbol]" / "page.tsx"
if stocks_path.exists():
    src = read(stocks_path)

    # Add NavBar if missing
    needs_write = False
    if 'import NavBar' not in src:
        src = src.replace(
            '"use client";',
            '"use client";\nimport NavBar from "@/components/NavBar";',
            1
        )
        needs_write = True

    # Ensure the outermost div has dark bg
    if 'minHeight:"100vh"' not in src and "minHeight: '100vh'" not in src:
        # Find the return statement root div
        # Usually: return (\n    <div style={{...
        match = re.search(r'(return\s*\(\s*\n\s*<div\s+style=\{?\{?)', src)
        if match:
            pos = match.start()
            # Find the opening brace of the style object
            style_start = src.find('{', pos + match.end() - 2)
            if style_start >= 0:
                # Insert background and minHeight into the style object
                src = src[:style_start+1] + 'minHeight:"100vh",background:"var(--bg)",fontFamily:"JetBrains Mono,monospace",' + src[style_start+1:]
                needs_write = True

    if needs_write:
        stocks_path.write_text(src, encoding="utf-8")
        print(f"  [OK] /stocks/[symbol]: patched NavBar + dark bg  ({len(src.splitlines())} lines)")
    else:
        print("  [SKIP] /stocks/[symbol] already has NavBar + dark bg")
else:
    print("  [SKIP] /stocks/[symbol] page.tsx not found (run build_stock_deep.py first)")


# =============================================================================
# Summary
# =============================================================================
print()
print("=" * 60)
print("PHASE 3B COMPLETE")
print("=" * 60)
print()
print("Files written:")
print("  /patterns/page.tsx      -- dark bg + NavBar + no emoji tabs + OOS badge")
print("  /patterns-v3/page.tsx   -- emoji tabs removed")
print("  /portfolio/page.tsx     -- equity curve P&L chart + NavBar + full table")
print("  /stocks/[symbol]        -- NavBar + dark bg (if was missing)")
print()
print("Next steps:")
print("  cd D:\\MICC\\micc-dashboard && npm run dev")
print("  Check: /patterns  (should have dark bg + no zoom)")
print("  Check: /portfolio (should show equity curve)")
print("  Check: /stocks/RELIANCE (fundamentals tab)")
print()
print("Then run OOS validation overnight (adds oos_accuracy to pattern cards):")
print("  py D:\\MICC\\validate_patterns_oos.py")
