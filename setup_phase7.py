"""
setup_phase7.py  --  Run from D:\MICC
Creates:
  1. micc-dashboard/src/app/api/backtest/route.ts
  2. micc-dashboard/src/app/backtest/page.tsx
  3. Adds BACKTEST to NavBar
  4. Adds /backtest command to telegram_bot.py
  5. Copies agent_backtest.py to D:\MICC\
"""

import shutil
from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
SRC  = Path(__file__).parent   # same dir as agent_backtest.py

def read(p):  return Path(p).read_text(encoding="utf-8")
def write(p, t): Path(p).write_text(t, encoding="utf-8"); print(f"  [OK] {p}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Copy agent_backtest.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 1: Install agent_backtest.py ===")
src_bt = SRC / "agent_backtest.py"
dst_bt = BASE / "agent_backtest.py"
if src_bt.exists():
    shutil.copy2(src_bt, dst_bt)
    print(f"  Copied to {dst_bt}")
else:
    print(f"  [WARN] agent_backtest.py not found next to this script")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: API route
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 2: Create /api/backtest/route.ts ===")

api_dir = DASH / "src" / "app" / "api" / "backtest"
api_dir.mkdir(parents=True, exist_ok=True)

ROUTE = r"""import { NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs';

const DA = 'D:/MICC';

export async function GET() {
  try {
    const reportPath = path.join(DA, 'agents', 'backtest', 'last_report.json');
    if (!fs.existsSync(reportPath)) {
      return NextResponse.json({ error: 'No backtest report found. Run: py agent_backtest.py' },
                                { status: 404 });
    }
    const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
    return NextResponse.json(report);
  } catch (e: unknown) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
"""
write(api_dir / "route.ts", ROUTE)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Dashboard page
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 3: Create /backtest/page.tsx ===")

page_dir = DASH / "src" / "app" / "backtest"
page_dir.mkdir(parents=True, exist_ok=True)

PAGE = '''\
"use client";
import React, { useEffect, useState } from "react";
import MarkdownText from "@/components/MarkdownText";

const HORIZONS = [1, 3, 5, 10];
const C = {
  green:  "var(--accent-green)",
  red:    "var(--accent-red)",
  cyan:   "var(--accent-cyan)",
  yellow: "var(--accent-yellow)",
  dim:    "var(--text-tertiary)",
  primary:"var(--text-primary)",
  border: "var(--border)",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--card-bg)", border: `1px solid ${C.border}`,
      borderRadius: 4, padding: "1rem", marginBottom: "1rem" }}>
      <div style={{ color: C.cyan, fontSize: "0.7rem", fontWeight: 700,
        letterSpacing: "0.1em", marginBottom: "0.75rem" }}>{title}</div>
      {children}
    </div>
  );
}

function HitBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct   = Math.min((value / max) * 100, 100);
  const color = value >= 60 ? C.green : value >= 50 ? C.yellow : C.red;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <div style={{ flex: 1, height: 6, background: "var(--bg-secondary)", borderRadius: 3 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3 }} />
      </div>
      <span style={{ color, fontSize: "0.72rem", minWidth: 36, textAlign: "right" }}>
        {value?.toFixed(1)}%
      </span>
    </div>
  );
}

function RetCell({ v }: { v: number | undefined }) {
  if (v == null) return <span style={{ color: C.dim }}>-</span>;
  const col = v > 0 ? C.green : v < 0 ? C.red : C.dim;
  return <span style={{ color: col }}>{v > 0 ? "+" : ""}{v?.toFixed(2)}%</span>;
}

interface StatsBlock {
  label: string; n: number;
  h1_hit_rate?: number; h1_avg_ret?: number;
  h3_hit_rate?: number; h3_avg_ret?: number;
  h5_hit_rate?: number; h5_avg_ret?: number;
  h10_hit_rate?: number; h10_avg_ret?: number;
  h5_best?: number; h5_worst?: number;
}
interface MonthlyRow { month: string; hit_rate: number; n: number; avg_ret: number; }
interface SymRow     { symbol: string; avg_fwd_5d: number; }
interface Report {
  generated_at: string; date_range: string; n_signals: number;
  analysis: string;
  stats: {
    overall: StatsBlock;
    by_screen: StatsBlock[];
    by_regime: StatsBlock[];
    by_score:  StatsBlock[];
    monthly_trend: MonthlyRow[];
    top_performers: SymRow[];
    worst_performers: SymRow[];
  };
}

export default function BacktestPage() {
  const [data, setData] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const [tab, setTab] = useState<"overview"|"screens"|"regime"|"symbols"|"monthly">("overview");

  useEffect(() => {
    fetch("/api/backtest")
      .then(r => r.json())
      .then(d => { if (d.error) setError(d.error); else setData(d); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
      height:"60vh", color: C.dim, fontSize:"0.8rem" }}>
      LOADING BACKTEST...
    </div>
  );

  if (error || !data) return (
    <div style={{ padding: "2rem", color: C.red, fontSize: "0.8rem" }}>
      {error || "No data"}<br/>
      <span style={{ color: C.dim }}>Run: py D:\\MICC\\agent_backtest.py</span>
    </div>
  );

  const ov = data.stats.overall;
  const TABS = ["overview","screens","regime","symbols","monthly"] as const;

  function StatTable({ rows }: { rows: StatsBlock[] }) {
    return (
      <table style={{ width:"100%", borderCollapse:"collapse", fontSize:"0.72rem" }}>
        <thead>
          <tr style={{ color: C.dim, borderBottom: `1px solid ${C.border}` }}>
            {["SCREEN","N","1D HIT","3D HIT","5D HIT","10D HIT",
              "5D AVG","5D BEST","5D WORST"].map(h => (
              <th key={h} style={{ textAlign:"left", padding:"0.2rem 0.5rem",
                fontWeight:600, letterSpacing:"0.05em" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderBottom:`1px solid ${C.border}22` }}>
              <td style={{ padding:"0.25rem 0.5rem", color: C.cyan, fontWeight:600 }}>{r.label}</td>
              <td style={{ padding:"0.25rem 0.5rem", color: C.dim }}>{r.n}</td>
              {[r.h1_hit_rate, r.h3_hit_rate, r.h5_hit_rate, r.h10_hit_rate].map((v,j) => (
                <td key={j} style={{ padding:"0.25rem 0.5rem" }}>
                  {v != null
                    ? <span style={{ color: v>=60?C.green:v>=50?C.yellow:C.red }}>{v}%</span>
                    : <span style={{ color:C.dim }}>-</span>}
                </td>
              ))}
              <td style={{ padding:"0.25rem 0.5rem" }}><RetCell v={r.h5_avg_ret} /></td>
              <td style={{ padding:"0.25rem 0.5rem" }}><RetCell v={r.h5_best} /></td>
              <td style={{ padding:"0.25rem 0.5rem" }}><RetCell v={r.h5_worst} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <div style={{ padding:"1.5rem", maxWidth:1400, margin:"0 auto" }}>
      {/* Header */}
      <h1 style={{ fontSize:"1rem", fontWeight:700, letterSpacing:"0.08em",
        color: C.primary, marginBottom:"0.25rem" }}>
        SIGNAL BACKTESTER
      </h1>
      <div style={{ fontSize:"0.7rem", color: C.dim, marginBottom:"1.5rem" }}>
        {data.n_signals} signals | {data.date_range} | Generated: {data.generated_at}
      </div>

      {/* KPI row */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:"0.75rem",
        marginBottom:"1.5rem" }}>
        {HORIZONS.map(h => {
          const hr  = (ov as Record<string,number>)[`h${h}_hit_rate`];
          const avg = (ov as Record<string,number>)[`h${h}_avg_ret`];
          const col = hr >= 60 ? C.green : hr >= 50 ? C.yellow : C.red;
          return (
            <div key={h} style={{ background:"var(--card-bg)",
              border:`1px solid ${C.border}`, borderRadius:4, padding:"0.75rem 1rem" }}>
              <div style={{ color:C.dim, fontSize:"0.65rem", letterSpacing:"0.08em" }}>
                {h}D FORWARD
              </div>
              <div style={{ color:col, fontSize:"1.4rem", fontWeight:700, margin:"0.25rem 0" }}>
                {hr != null ? `${hr}%` : "N/A"}
              </div>
              <div style={{ color:C.dim, fontSize:"0.68rem" }}>hit rate</div>
              <div style={{ color: avg>0?C.green:avg<0?C.red:C.dim,
                fontSize:"0.75rem", marginTop:"0.25rem" }}>
                avg {avg != null ? `${avg>0?"+":""}${avg}%` : "N/A"}
              </div>
            </div>
          );
        })}
      </div>

      {/* Tabs */}
      <div style={{ display:"flex", gap:"0.5rem", marginBottom:"1rem", borderBottom:`1px solid ${C.border}` }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background:"transparent", border:"none", cursor:"pointer",
            color: tab===t ? C.cyan : C.dim,
            borderBottom: tab===t ? `2px solid ${C.cyan}` : "2px solid transparent",
            padding:"0.4rem 0.75rem", fontSize:"0.72rem", fontFamily:"var(--font-mono)",
            letterSpacing:"0.05em", fontWeight: tab===t ? 700 : 400,
          }}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Tab: overview */}
      {tab === "overview" && (
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"1rem" }}>
          <div>
            <Card title="HIT RATE BY HORIZON">
              {HORIZONS.map(h => {
                const hr = (ov as Record<string,number>)[`h${h}_hit_rate`];
                return (
                  <div key={h} style={{ marginBottom:"0.6rem" }}>
                    <div style={{ display:"flex", justifyContent:"space-between",
                      fontSize:"0.7rem", color:C.dim, marginBottom:"0.15rem" }}>
                      <span>{h}-day forward</span>
                      <span style={{ color:C.primary }}>
                        avg {(ov as Record<string,number>)[`h${h}_avg_ret`] ?? "N/A"}%
                      </span>
                    </div>
                    <HitBar value={hr ?? 0} />
                  </div>
                );
              })}
            </Card>

            <Card title="BEST SCREEN (5d hit rate)">
              {data.stats.by_screen.sort((a,b)=>(b.h5_hit_rate??0)-(a.h5_hit_rate??0)).map((s,i) => (
                <div key={i} style={{ marginBottom:"0.5rem" }}>
                  <div style={{ display:"flex", justifyContent:"space-between",
                    fontSize:"0.7rem", marginBottom:"0.1rem" }}>
                    <span style={{ color:C.primary }}>{s.label}</span>
                    <span style={{ color:C.dim }}>n={s.n}</span>
                  </div>
                  <HitBar value={s.h5_hit_rate ?? 0} />
                </div>
              ))}
            </Card>
          </div>

          <Card title="ANALYSIS">
            <MarkdownText text={data.analysis} maxHeight={450} />
          </Card>
        </div>
      )}

      {/* Tab: screens */}
      {tab === "screens" && (
        <Card title="PERFORMANCE BY SCREEN">
          <StatTable rows={data.stats.by_screen} />
        </Card>
      )}

      {/* Tab: regime */}
      {tab === "regime" && (
        <div>
          <Card title="PERFORMANCE BY MARKET REGIME">
            <StatTable rows={data.stats.by_regime} />
          </Card>
          <Card title="PERFORMANCE BY COMPOSITE SCORE">
            <StatTable rows={data.stats.by_score} />
          </Card>
        </div>
      )}

      {/* Tab: symbols */}
      {tab === "symbols" && (
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"1rem" }}>
          <Card title="TOP 10 PERFORMERS (avg 5d return)">
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:"0.72rem" }}>
              <thead>
                <tr style={{ color:C.dim, borderBottom:`1px solid ${C.border}` }}>
                  <th style={{ textAlign:"left", padding:"0.2rem 0.5rem" }}>SYMBOL</th>
                  <th style={{ textAlign:"left", padding:"0.2rem 0.5rem" }}>AVG 5D RET</th>
                </tr>
              </thead>
              <tbody>
                {data.stats.top_performers.map((r,i) => (
                  <tr key={i} style={{ borderBottom:`1px solid ${C.border}22` }}>
                    <td style={{ padding:"0.25rem 0.5rem", color:C.cyan }}>{r.symbol}</td>
                    <td style={{ padding:"0.25rem 0.5rem" }}><RetCell v={r.avg_fwd_5d} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title="WORST 10 PERFORMERS (avg 5d return)">
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:"0.72rem" }}>
              <thead>
                <tr style={{ color:C.dim, borderBottom:`1px solid ${C.border}` }}>
                  <th style={{ textAlign:"left", padding:"0.2rem 0.5rem" }}>SYMBOL</th>
                  <th style={{ textAlign:"left", padding:"0.2rem 0.5rem" }}>AVG 5D RET</th>
                </tr>
              </thead>
              <tbody>
                {data.stats.worst_performers.map((r,i) => (
                  <tr key={i} style={{ borderBottom:`1px solid ${C.border}22` }}>
                    <td style={{ padding:"0.25rem 0.5rem", color:C.yellow }}>{r.symbol}</td>
                    <td style={{ padding:"0.25rem 0.5rem" }}><RetCell v={r.avg_fwd_5d} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {/* Tab: monthly */}
      {tab === "monthly" && (
        <Card title="MONTHLY HIT RATE TREND (5d forward)">
          {data.stats.monthly_trend.length === 0
            ? <div style={{ color:C.dim, fontSize:"0.72rem" }}>No monthly data yet.</div>
            : (
              <div>
                {data.stats.monthly_trend.map((m, i) => (
                  <div key={i} style={{ display:"flex", alignItems:"center",
                    gap:"0.75rem", marginBottom:"0.5rem" }}>
                    <span style={{ color:C.dim, fontSize:"0.7rem", minWidth:60 }}>{m.month}</span>
                    <div style={{ flex:1 }}>
                      <HitBar value={m.hit_rate} />
                    </div>
                    <span style={{ color:C.dim, fontSize:"0.68rem", minWidth:40 }}>n={m.n}</span>
                    <RetCell v={m.avg_ret} />
                  </div>
                ))}
              </div>
            )
          }
        </Card>
      )}
    </div>
  );
}
'''
write(page_dir / "page.tsx", PAGE)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: NavBar
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 4: Add BACKTEST to NavBar ===")

navbar = None
for p in DASH.rglob("NavBar.tsx"):
    navbar = p; break

if not navbar:
    print("  [WARN] NavBar.tsx not found")
else:
    src = read(navbar)
    for old, new in [
        ("{ href: '/watchlist', label: 'WATCHLIST' },",
         "{ href: '/watchlist', label: 'WATCHLIST' },\n  { href: '/backtest', label: 'BACKTEST' },"),
        ("{ href: '/mf', label: 'MF NAV' },",
         "{ href: '/mf', label: 'MF NAV' },\n  { href: '/backtest', label: 'BACKTEST' },"),
    ]:
        if old in src and "backtest" not in src.lower():
            src = src.replace(old, new)
            write(navbar, src)
            print("  Added BACKTEST to NavBar")
            break
    else:
        if "backtest" in src.lower():
            print("  BACKTEST already in NavBar")
        else:
            print("  [WARN] Could not find insertion point")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Telegram /backtest command
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== STEP 5: Add /backtest to telegram_bot.py ===")

bot = BASE / "telegram_bot.py"
if bot.exists():
    src = read(bot)
    if "cmd_backtest" in src:
        print("  Already exists")
    else:
        CMD = r'''

async def cmd_backtest(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show backtest summary."""
    rp = Path("agents/backtest/last_report.json")
    if not rp.exists():
        await update.message.reply_text("No backtest yet. Run: py agent_backtest.py")
        return
    try:
        r = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return

    ov   = r.get("stats", {}).get("overall", {})
    n    = r.get("n_signals", 0)
    dr   = r.get("date_range", "?")
    lines = [f"*MICC Backtest -- {n} signals*", f"_{dr}_", ""]
    for h in [1, 3, 5, 10]:
        hr  = ov.get(f"h{h}_hit_rate", "?")
        avg = ov.get(f"h{h}_avg_ret",  "?")
        lines.append(f"  `{h}d` hit={hr}% | avg={avg}%")
    lines.append("")
    lines.append("*BY SCREEN (5d):*")
    for s in r.get("stats", {}).get("by_screen", []):
        lines.append(f"  `{s['label'][:12]}` {s.get('h5_hit_rate','?')}% "
                     f"(avg {s.get('h5_avg_ret','?')}%)")
    msg = "\n".join(lines)
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")

'''
        if "def main():" in src:
            src = src.replace("def main():", CMD + "def main():")
            # register
            for pat in ['app.add_handler(CommandHandler("watch"',
                        'app.add_handler(CommandHandler("status"']:
                if pat in src:
                    src = src.replace(pat,
                        f'app.add_handler(CommandHandler("backtest", cmd_backtest))\n    {pat}')
                    break
            write(bot, src)
            print("  Added /backtest command")


print("\n" + "="*60)
print("PHASE 7 SETUP COMPLETE")
print("="*60)
print()
print("Run:")
print("  py D:\\MICC\\agent_backtest.py          -- run backtest")
print("  py D:\\MICC\\agent_backtest.py --send   -- with Telegram")
print("  Restart Next.js -> localhost:3000/backtest")
