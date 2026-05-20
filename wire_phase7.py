"""
wire_phase7.py  --  Run from D:\MICC
Does everything setup_phase7.py missed (it crashed at shutil.copy2).
agent_backtest.py is already at D:\MICC\ and working.
This script only:
  1. Creates micc-dashboard/src/app/api/backtest/route.ts
  2. Creates micc-dashboard/src/app/backtest/page.tsx
  3. Adds BACKTEST to NavBar.tsx
  4. Adds /backtest command to telegram_bot.py
"""

from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"

def read(p):  return Path(p).read_text(encoding="utf-8")
def write(p, t): Path(p).write_text(t, encoding="utf-8"); print(f"  [OK] {p}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. API route
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 1. /api/backtest/route.ts ===")
api_dir = DASH / "src" / "app" / "api" / "backtest"
api_dir.mkdir(parents=True, exist_ok=True)

write(api_dir / "route.ts", """\
import { NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs';

const DA = 'D:/MICC';

export async function GET() {
  try {
    const p = path.join(DA, 'agents', 'backtest', 'last_report.json');
    if (!fs.existsSync(p)) {
      return NextResponse.json(
        { error: 'No backtest report. Run: py agent_backtest.py' },
        { status: 404 }
      );
    }
    return NextResponse.json(JSON.parse(fs.readFileSync(p, 'utf-8')));
  } catch (e: unknown) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
""")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dashboard page
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 2. /backtest/page.tsx ===")
page_dir = DASH / "src" / "app" / "backtest"
page_dir.mkdir(parents=True, exist_ok=True)

write(page_dir / "page.tsx", '''\
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

function HitBar({ value }: { value: number }) {
  const color = value >= 60 ? C.green : value >= 50 ? C.yellow : C.red;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <div style={{ flex: 1, height: 6, background: "var(--bg-secondary)", borderRadius: 3 }}>
        <div style={{ width: `${Math.min(value, 100)}%`, height: "100%",
          background: color, borderRadius: 3 }} />
      </div>
      <span style={{ color, fontSize: "0.72rem", minWidth: 38, textAlign: "right" }}>
        {value?.toFixed(1)}%
      </span>
    </div>
  );
}

function Ret({ v }: { v: number | undefined | null }) {
  if (v == null) return <span style={{ color: C.dim }}>-</span>;
  const c = v > 0 ? C.green : v < 0 ? C.red : C.dim;
  return <span style={{ color: c }}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Block = Record<string, any>;

function StatTable({ rows }: { rows: Block[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.72rem" }}>
      <thead>
        <tr style={{ color: C.dim, borderBottom: `1px solid ${C.border}` }}>
          {["", "N", "1D HIT", "3D HIT", "5D HIT", "10D HIT", "5D AVG", "5D BEST", "5D WORST"]
            .map(h => (
              <th key={h} style={{ textAlign: "left", padding: "0.2rem 0.5rem",
                fontWeight: 600, letterSpacing: "0.05em" }}>{h}</th>
            ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r: Block, i: number) => (
          <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
            <td style={{ padding: "0.25rem 0.5rem", color: C.cyan, fontWeight: 600 }}>{r.label}</td>
            <td style={{ padding: "0.25rem 0.5rem", color: C.dim }}>{r.n}</td>
            {[r.h1_hit_rate, r.h3_hit_rate, r.h5_hit_rate, r.h10_hit_rate].map((v: number, j: number) => (
              <td key={j} style={{ padding: "0.25rem 0.5rem" }}>
                <span style={{ color: v >= 60 ? C.green : v >= 50 ? C.yellow : C.red }}>
                  {v != null ? `${v}%` : "-"}
                </span>
              </td>
            ))}
            <td style={{ padding: "0.25rem 0.5rem" }}><Ret v={r.h5_avg_ret} /></td>
            <td style={{ padding: "0.25rem 0.5rem" }}><Ret v={r.h5_best} /></td>
            <td style={{ padding: "0.25rem 0.5rem" }}><Ret v={r.h5_worst} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function BacktestPage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData]     = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const [tab, setTab]       = useState("overview");

  useEffect(() => {
    fetch("/api/backtest")
      .then(r => r.json())
      .then(d => { if (d.error) setError(d.error); else setData(d); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "60vh", color: C.dim, fontSize: "0.8rem" }}>
      LOADING BACKTEST...
    </div>
  );

  if (error || !data) return (
    <div style={{ padding: "2rem", color: C.red, fontSize: "0.8rem" }}>
      {error || "No data"}<br />
      <span style={{ color: C.dim }}>Run: py D:\MICC\agent_backtest.py</span>
    </div>
  );

  const ov   = data.stats?.overall ?? {};
  const TABS = ["overview", "screens", "regime", "symbols", "monthly"];

  return (
    <div style={{ padding: "1.5rem", maxWidth: 1400, margin: "0 auto" }}>

      {/* Header */}
      <h1 style={{ fontSize: "1rem", fontWeight: 700, letterSpacing: "0.08em",
        color: C.primary, marginBottom: "0.25rem" }}>
        SIGNAL BACKTESTER
      </h1>
      <div style={{ fontSize: "0.7rem", color: C.dim, marginBottom: "1.5rem" }}>
        {data.n_signals} signals | {data.date_range} | {data.generated_at}
      </div>

      {/* KPI cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)",
        gap: "0.75rem", marginBottom: "1.5rem" }}>
        {HORIZONS.map(h => {
          const hr  = ov[`h${h}_hit_rate`];
          const avg = ov[`h${h}_avg_ret`];
          const col = hr >= 60 ? C.green : hr >= 50 ? C.yellow : C.red;
          return (
            <div key={h} style={{ background: "var(--card-bg)",
              border: `1px solid ${C.border}`, borderRadius: 4, padding: "0.75rem 1rem" }}>
              <div style={{ color: C.dim, fontSize: "0.65rem",
                letterSpacing: "0.08em" }}>{h}D FORWARD</div>
              <div style={{ color: col, fontSize: "1.6rem",
                fontWeight: 700, margin: "0.3rem 0" }}>
                {hr != null ? `${hr}%` : "N/A"}
              </div>
              <div style={{ color: C.dim, fontSize: "0.65rem" }}>hit rate</div>
              <div style={{ color: avg > 0 ? C.green : avg < 0 ? C.red : C.dim,
                fontSize: "0.75rem", marginTop: "0.3rem" }}>
                avg {avg != null ? `${avg > 0 ? "+" : ""}${avg}%` : "N/A"}
              </div>
            </div>
          );
        })}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem",
        borderBottom: `1px solid ${C.border}` }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: "transparent", border: "none", cursor: "pointer",
            color: tab === t ? C.cyan : C.dim,
            borderBottom: tab === t ? `2px solid ${C.cyan}` : "2px solid transparent",
            padding: "0.4rem 0.75rem", fontSize: "0.72rem",
            fontFamily: "var(--font-mono)", letterSpacing: "0.05em",
            fontWeight: tab === t ? 700 : 400,
          }}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {/* OVERVIEW */}
      {tab === "overview" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div>
            <Card title="HIT RATE BY HORIZON">
              {HORIZONS.map(h => {
                const hr  = ov[`h${h}_hit_rate`] ?? 0;
                const avg = ov[`h${h}_avg_ret`];
                return (
                  <div key={h} style={{ marginBottom: "0.7rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between",
                      fontSize: "0.7rem", color: C.dim, marginBottom: "0.15rem" }}>
                      <span>{h}-day forward return</span>
                      <span style={{ color: C.primary }}>avg <Ret v={avg} /></span>
                    </div>
                    <HitBar value={hr} />
                  </div>
                );
              })}
            </Card>

            <Card title="SCREEN PERFORMANCE (5d hit rate)">
              {(data.stats?.by_screen ?? [])
                .slice()
                .sort((a: Block, b: Block) => (b.h5_hit_rate ?? 0) - (a.h5_hit_rate ?? 0))
                .map((s: Block, i: number) => (
                  <div key={i} style={{ marginBottom: "0.6rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between",
                      fontSize: "0.7rem", marginBottom: "0.1rem" }}>
                      <span style={{ color: C.primary }}>{s.label}</span>
                      <span style={{ color: C.dim }}>n={s.n} | avg <Ret v={s.h5_avg_ret} /></span>
                    </div>
                    <HitBar value={s.h5_hit_rate ?? 0} />
                  </div>
                ))}
            </Card>
          </div>

          <Card title="LLM ANALYSIS">
            <MarkdownText text={data.analysis} maxHeight={480} />
          </Card>
        </div>
      )}

      {/* SCREENS */}
      {tab === "screens" && (
        <div>
          <Card title="BY SCREEN">
            <StatTable rows={data.stats?.by_screen ?? []} />
          </Card>
          <Card title="BY COMPOSITE SCORE BUCKET">
            <StatTable rows={data.stats?.by_score ?? []} />
          </Card>
        </div>
      )}

      {/* REGIME */}
      {tab === "regime" && (
        <Card title="BY MARKET REGIME">
          <StatTable rows={data.stats?.by_regime ?? []} />
        </Card>
      )}

      {/* SYMBOLS */}
      {tab === "symbols" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          {[
            { title: "TOP 10 PERFORMERS (avg 5d)", key: "top_performers", color: C.green },
            { title: "WORST 10 PERFORMERS (avg 5d)", key: "worst_performers", color: C.yellow },
          ].map(({ title, key, color }) => (
            <Card key={key} title={title}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.72rem" }}>
                <thead>
                  <tr style={{ color: C.dim, borderBottom: `1px solid ${C.border}` }}>
                    <th style={{ textAlign: "left", padding: "0.2rem 0.5rem" }}>SYMBOL</th>
                    <th style={{ textAlign: "left", padding: "0.2rem 0.5rem" }}>AVG 5D RET</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.stats?.[key] ?? []).map((r: Block, i: number) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${C.border}22` }}>
                      <td style={{ padding: "0.25rem 0.5rem", color }}>{r.symbol}</td>
                      <td style={{ padding: "0.25rem 0.5rem" }}><Ret v={r.avg_fwd_5d} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ))}
        </div>
      )}

      {/* MONTHLY */}
      {tab === "monthly" && (
        <Card title="MONTHLY HIT RATE TREND (5d forward)">
          {(data.stats?.monthly_trend ?? []).length === 0
            ? <div style={{ color: C.dim, fontSize: "0.72rem" }}>No monthly data yet.</div>
            : (data.stats.monthly_trend as Block[]).map((m: Block, i: number) => (
                <div key={i} style={{ display: "flex", alignItems: "center",
                  gap: "0.75rem", marginBottom: "0.5rem" }}>
                  <span style={{ color: C.dim, fontSize: "0.7rem", minWidth: 65 }}>{m.month}</span>
                  <div style={{ flex: 1 }}><HitBar value={m.hit_rate ?? 0} /></div>
                  <span style={{ color: C.dim, fontSize: "0.68rem", minWidth: 45 }}>n={m.n}</span>
                  <Ret v={m.avg_ret} />
                </div>
              ))
          }
        </Card>
      )}

    </div>
  );
}
''')


# ─────────────────────────────────────────────────────────────────────────────
# 3. NavBar
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 3. NavBar.tsx ===")
navbar = None
for p in DASH.rglob("NavBar.tsx"):
    navbar = p; break

if not navbar:
    print("  [WARN] NavBar.tsx not found")
else:
    src = read(navbar)
    if "backtest" in src.lower():
        print("  Already has BACKTEST")
    else:
        # try inserting after watchlist, then after mf, then after last nav item
        inserted = False
        for anchor in [
            "{ href: '/watchlist', label: 'WATCHLIST' },",
            "{ href: '/mf', label: 'MF NAV' },",
            "{ href: \"/mf\", label: \"MF NAV\" },",
        ]:
            if anchor in src:
                src = src.replace(anchor,
                    anchor + "\n  { href: '/backtest', label: 'BACKTEST' },")
                write(navbar, src)
                inserted = True
                break
        if not inserted:
            print("  [WARN] Could not find anchor. Add manually:")
            print("  { href: '/backtest', label: 'BACKTEST' }")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Telegram /backtest
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== 4. telegram_bot.py /backtest ===")
bot = BASE / "telegram_bot.py"
if not bot.exists():
    print("  [WARN] telegram_bot.py not found")
else:
    src = read(bot)
    if "cmd_backtest" in src:
        print("  Already exists")
    else:
        CMD = '''
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
    ov    = r.get("stats", {}).get("overall", {})
    n     = r.get("n_signals", 0)
    dr    = r.get("date_range", "?")
    lines = [f"*MICC Backtest -- {n} signals*", f"_{dr}_", ""]
    for h in [1, 3, 5, 10]:
        hr  = ov.get(f"h{h}_hit_rate", "?")
        avg = ov.get(f"h{h}_avg_ret",  "?")
        lines.append(f"  `{h}d` hit={hr}% | avg={avg}%")
    lines.append("")
    lines.append("*BY SCREEN (5d):*")
    for s in r.get("stats", {}).get("by_screen", []):
        lines.append(f"  `{s[\'label\'][:12]}` {s.get(\'h5_hit_rate\',\'?\')}%"
                     f" (avg {s.get(\'h5_avg_ret\',\'?\')}%)")
    await update.message.reply_text("\\n".join(lines)[:4000], parse_mode="Markdown")

'''
        if "def main():" in src:
            src = src.replace("def main():", CMD + "def main():")
            # register handler
            for pat in [
                'app.add_handler(CommandHandler("backtest"',
                'app.add_handler(CommandHandler("watch"',
                'app.add_handler(CommandHandler("status"',
            ]:
                if pat in src:
                    if "backtest" not in pat:
                        src = src.replace(pat,
                            'app.add_handler(CommandHandler("backtest", cmd_backtest))\n    ' + pat)
                    break
            write(bot, src)
            print("  Added /backtest")
        else:
            print("  [WARN] def main() not found in telegram_bot.py")


print("\n" + "="*50)
print("DONE. Restart Next.js to see /backtest page.")
print("="*50)
