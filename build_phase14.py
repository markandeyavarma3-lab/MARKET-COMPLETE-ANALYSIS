"""
build_phase14.py  --  Run from D:\MICC
Builds:
  [1] /app/api/eta/route.ts          -- reads agents/eta/last_report.json
  [2] /app/eta/page.tsx              -- full Eta dashboard page
  [3] NavBar.tsx                     -- adds ETA link
  [4] telegram_bot.py patch          -- adds /eta /deep /kappa commands

Run: py D:\MICC\build_phase14.py
"""
import re
from pathlib import Path

MICC  = Path(r"D:\MICC")
DASH  = MICC / "micc-dashboard"
SRC   = DASH / "src" / "app"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}")

def patch(path: Path, old: str, new: str, label: str):
    if not path.exists():
        print(f"  [SKIP] {label} — file not found: {path}")
        return False
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [SKIP] {label} — marker not found")
        return False
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  [OK] {label}")
    return True


# ═════════════════════════════════════════════════════════════════════════════
# [1] API ROUTE  /api/eta/route.ts
# ═════════════════════════════════════════════════════════════════════════════

print("\n[1/4] Writing /api/eta/route.ts ...")

ETA_ROUTE = '''\
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import path             from "path";
import fs               from "fs";

const DA = "D:/MICC";
const REPORT = path.join(DA, "agents", "eta", "last_report.json");

function sanitize(s: string): string {
  return s.replace(/:\s*NaN\b/g, ": null")
          .replace(/:\s*Infinity\b/g, ": null")
          .replace(/:\s*-Infinity\b/g, ": null");
}

export async function GET() {
  try {
    if (!fs.existsSync(REPORT)) {
      return NextResponse.json({ error: "No Eta report found. Run: py agent_eta.py" }, { status: 404 });
    }
    const raw  = fs.readFileSync(REPORT, "utf-8");
    const data = JSON.parse(sanitize(raw));
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
'''
write(SRC / "api" / "eta" / "route.ts", ETA_ROUTE, "/api/eta/route.ts")


# ═════════════════════════════════════════════════════════════════════════════
# [2] ETA DASHBOARD PAGE  /eta/page.tsx
# ═════════════════════════════════════════════════════════════════════════════

print("\n[2/4] Writing /eta/page.tsx ...")

ETA_PAGE = '''\
"use client";

import { useEffect, useState } from "react";

// ── types ────────────────────────────────────────────────────────────────────
interface ResultItem   { symbol: string; date: string; subject: string; }
interface DivItem      { symbol: string; date: string; event_type: string; subject: string; }
interface ClusterItem  { symbol: string; buy_count: number; total_value_cr: number; insiders: string; }
interface BigTrade     { symbol: string; transaction: string; value_cr: number; name: string; date: string; price?: number; }
interface ReactionItem { symbol: string; date: string; ret_5d: number; }
interface UpcomingItem { symbol: string; last_results: string; days_since: number; est_due_in: number; }

interface EtaReport {
  date: string;
  generated_at: string;
  results_season: ResultItem[];
  dividend_calendar: DivItem[];
  insider_cluster: ClusterItem[];
  big_insider_trades: BigTrade[];
  post_results_reaction: ReactionItem[];
  upcoming_results: UpcomingItem[];
  analysis: string;
  error?: string;
}

// ── helpers ──────────────────────────────────────────────────────────────────
const fmt_cr = (v: number | null | undefined) =>
  v == null ? "—" : `₹${Number(v).toFixed(1)}Cr`;

const pct_color = (v: number | null | undefined) => {
  if (v == null) return "#94a3b8";
  return v > 0 ? "#22c55e" : v < 0 ? "#ef4444" : "#94a3b8";
};

const event_badge: Record<string, string> = {
  DIVIDEND: "#3b82f6",
  BONUS:    "#a855f7",
  SPLIT:    "#f59e0b",
};

// ── sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ icon, title, count }: { icon: string; title: string; count: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#e2e8f0", letterSpacing: 1 }}>
        {title}
      </h2>
      <span style={{
        marginLeft: "auto", fontSize: 12, fontWeight: 700,
        background: "#334155", color: "#94a3b8",
        borderRadius: 999, padding: "2px 10px",
      }}>{count}</span>
    </div>
  );
}

function SymBadge({ symbol }: { symbol: string }) {
  return (
    <span style={{
      fontFamily: "monospace", fontWeight: 700, fontSize: 13,
      background: "#1e3a5f", color: "#60a5fa",
      borderRadius: 6, padding: "2px 8px", marginRight: 6,
    }}>{symbol}</span>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155",
      borderRadius: 12, padding: "18px 20px", ...style,
    }}>{children}</div>
  );
}

// ── Results Season ────────────────────────────────────────────────────────────
function ResultsSection({ items }: { items: ResultItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const show = expanded ? items : items.slice(0, 8);
  return (
    <Card>
      <SectionHeader icon="📊" title="RESULTS REPORTED (30d)" count={items.length} />
      <div style={{ display: "grid", gap: 6 }}>
        {show.map((r, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "7px 10px", background: "#0f172a",
            borderRadius: 8, borderLeft: "3px solid #3b82f6",
          }}>
            <SymBadge symbol={r.symbol} />
            <span style={{ fontSize: 12, color: "#64748b", minWidth: 90 }}>{r.date}</span>
            <span style={{ fontSize: 12, color: "#94a3b8", flex: 1 }}
              title={r.subject}>{r.subject.slice(0, 60)}{r.subject.length > 60 ? "…" : ""}</span>
          </div>
        ))}
      </div>
      {items.length > 8 && (
        <button onClick={() => setExpanded(!expanded)} style={{
          marginTop: 10, fontSize: 12, color: "#60a5fa",
          background: "none", border: "none", cursor: "pointer", padding: 0,
        }}>{expanded ? "▲ Show less" : `▼ Show all ${items.length}`}</button>
      )}
    </Card>
  );
}

// ── Dividend / Bonus / Split ──────────────────────────────────────────────────
function DividendSection({ items }: { items: DivItem[] }) {
  const divs   = items.filter(x => x.event_type === "DIVIDEND");
  const others = items.filter(x => x.event_type !== "DIVIDEND");
  return (
    <Card>
      <SectionHeader icon="💰" title="CORPORATE ACTIONS" count={items.length} />
      {[...divs, ...others].map((d, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "7px 10px", marginBottom: 5,
          background: "#0f172a", borderRadius: 8,
          borderLeft: `3px solid ${event_badge[d.event_type] || "#64748b"}`,
        }}>
          <SymBadge symbol={d.symbol} />
          <span style={{
            fontSize: 11, fontWeight: 700, color: event_badge[d.event_type] || "#94a3b8",
            minWidth: 68,
          }}>{d.event_type}</span>
          <span style={{ fontSize: 12, color: "#64748b", minWidth: 90 }}>{d.date}</span>
          <span style={{ fontSize: 12, color: "#94a3b8", flex: 1 }}
            title={d.subject}>{d.subject.slice(0, 55)}{d.subject.length > 55 ? "…" : ""}</span>
        </div>
      ))}
    </Card>
  );
}

// ── Insider Cluster ────────────────────────────────────────────────────────────
function InsiderClusterSection({ items }: { items: ClusterItem[] }) {
  return (
    <Card>
      <SectionHeader icon="👥" title="INSIDER CLUSTER BUYING" count={items.length} />
      {items.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No clusters detected.</p>}
      <div style={{ display: "grid", gap: 8 }}>
        {items.map((c, i) => (
          <div key={i} style={{
            background: "#0f172a", borderRadius: 10,
            padding: "10px 14px",
            borderLeft: "3px solid #22c55e",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <SymBadge symbol={c.symbol} />
              <span style={{ fontSize: 13, color: "#22c55e", fontWeight: 700 }}>
                {c.buy_count} insiders
              </span>
              <span style={{ marginLeft: "auto", fontSize: 13, color: "#fbbf24", fontWeight: 700 }}>
                {fmt_cr(c.total_value_cr)}
              </span>
            </div>
            <div style={{ fontSize: 11, color: "#64748b" }}>{c.insiders}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ── Big Insider Trades ────────────────────────────────────────────────────────
function BigTradesSection({ items }: { items: BigTrade[] }) {
  return (
    <Card>
      <SectionHeader icon="🐋" title="BIG INSIDER TRADES (>₹1Cr)" count={items.length} />
      {items.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No big trades.</p>}
      <div style={{ display: "grid", gap: 6 }}>
        {items.map((t, i) => {
          const isBuy  = t.transaction?.toUpperCase().includes("BUY");
          const isSell = t.transaction?.toUpperCase().includes("SELL");
          const clr    = isBuy ? "#22c55e" : isSell ? "#ef4444" : "#94a3b8";
          return (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "8px 12px", background: "#0f172a",
              borderRadius: 8, borderLeft: `3px solid ${clr}`,
            }}>
              <SymBadge symbol={t.symbol} />
              <span style={{ fontSize: 12, fontWeight: 700, color: clr, minWidth: 40 }}>
                {t.transaction}
              </span>
              <span style={{ fontSize: 13, color: "#fbbf24", fontWeight: 700, minWidth: 70 }}>
                {fmt_cr(t.value_cr)}
              </span>
              {t.price != null && (
                <span style={{ fontSize: 11, color: "#64748b" }}>@ ₹{t.price}</span>
              )}
              <span style={{ fontSize: 11, color: "#64748b", marginLeft: "auto" }}>
                {t.date} · {t.name?.slice(0, 25)}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── Post-Results Reaction ──────────────────────────────────────────────────────
function ReactionsSection({ items }: { items: ReactionItem[] }) {
  if (!items.length) return null;
  const positive = items.filter(x => x.ret_5d > 0).length;
  return (
    <Card>
      <SectionHeader icon="⚡" title="POST-RESULTS PRICE REACTION (5d)" count={items.length} />
      <div style={{ display: "flex", gap: 20, marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: "#22c55e" }}>
          ✅ Positive: {positive}
        </span>
        <span style={{ fontSize: 13, color: "#ef4444" }}>
          ❌ Negative: {items.length - positive}
        </span>
      </div>
      <div style={{ display: "grid", gap: 5 }}>
        {items.map((r, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "6px 10px", background: "#0f172a", borderRadius: 7,
            borderLeft: `3px solid ${pct_color(r.ret_5d)}`,
          }}>
            <SymBadge symbol={r.symbol} />
            <span style={{ fontSize: 12, color: "#64748b" }}>{r.date}</span>
            <span style={{
              marginLeft: "auto", fontSize: 13, fontWeight: 700,
              color: pct_color(r.ret_5d),
            }}>{r.ret_5d > 0 ? "+" : ""}{r.ret_5d?.toFixed(2)}%</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ── Upcoming Results Calendar ─────────────────────────────────────────────────
function UpcomingSection({ items }: { items: UpcomingItem[] }) {
  return (
    <Card>
      <SectionHeader icon="📅" title="RESULTS DUE SOON" count={items.length} />
      {items.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No upcoming results detected.</p>}
      <div style={{ display: "grid", gap: 6 }}>
        {items.map((u, i) => {
          const urgency = u.est_due_in <= 3 ? "#ef4444"
                        : u.est_due_in <= 7  ? "#f59e0b"
                        :                      "#64748b";
          return (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "7px 12px", background: "#0f172a",
              borderRadius: 8, borderLeft: `3px solid ${urgency}`,
            }}>
              <SymBadge symbol={u.symbol} />
              <span style={{ fontSize: 12, color: "#64748b" }}>
                Last: {u.last_results}
              </span>
              <span style={{
                marginLeft: "auto", fontWeight: 700, fontSize: 13, color: urgency,
              }}>
                {u.est_due_in === 0 ? "TODAY" : `~${u.est_due_in}d`}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── Analysis Box ──────────────────────────────────────────────────────────────
function AnalysisBox({ text }: { text: string }) {
  if (!text) return null;
  // Split by CAPS headers
  const lines = text.split("\n");
  return (
    <Card style={{ borderColor: "#7c3aed" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 18 }}>🧠</span>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#e2e8f0", letterSpacing: 1 }}>
          LLM ANALYSIS
        </h2>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#7c3aed" }}>Eta Agent</span>
      </div>
      <div style={{ lineHeight: 1.7 }}>
        {lines.map((line, i) => {
          const isHeader = /^[A-Z][A-Z\s:]{4,}$/.test(line.trim());
          return (
            <p key={i} style={{
              margin: "4px 0",
              fontSize: isHeader ? 13 : 13,
              fontWeight: isHeader ? 700 : 400,
              color: isHeader ? "#a78bfa" : "#cbd5e1",
              letterSpacing: isHeader ? 1 : 0,
            }}>{line || <br />}</p>
          );
        })}
      </div>
    </Card>
  );
}

// ── MAIN PAGE ─────────────────────────────────────────────────────────────────
export default function EtaPage() {
  const [data, setData]       = useState<EtaReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/eta")
      .then(r => r.json())
      .then(d => {
        if (d.error) setError(d.error);
        else setData(d);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "#0f172a", display: "flex",
      alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>⚙️</div>
        <p style={{ color: "#60a5fa", fontSize: 14 }}>Loading corporate events…</p>
      </div>
    </div>
  );

  if (error) return (
    <div style={{ minHeight: "100vh", background: "#0f172a", display: "flex",
      alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center", maxWidth: 480 }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>⚠️</div>
        <p style={{ color: "#ef4444", fontSize: 14, marginBottom: 12 }}>{error}</p>
        <code style={{ fontSize: 12, color: "#64748b" }}>
          Run: py D:\\MICC\\agent_eta.py
        </code>
      </div>
    </div>
  );

  if (!data) return null;

  // summary stats
  const posReactions = data.post_results_reaction.filter(x => x.ret_5d > 0).length;
  const totalReactions = data.post_results_reaction.length;
  const sentimentPct = totalReactions > 0
    ? Math.round(posReactions / totalReactions * 100) : null;

  return (
    <div style={{
      minHeight: "100vh", background: "#0f172a",
      color: "#e2e8f0", fontFamily: "system-ui, sans-serif",
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: "20px 28px 14px", borderBottom: "1px solid #1e293b",
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "#f8fafc" }}>
            🏢 Agent Eta — Corporate Events
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#64748b" }}>
            {data.generated_at || data.date}
          </p>
        </div>

        {/* Quick stats strip */}
        <div style={{ display: "flex", gap: 12, marginLeft: "auto", flexWrap: "wrap" }}>
          {[
            { label: "Results",  value: data.results_season.length,       color: "#3b82f6" },
            { label: "Actions",  value: data.dividend_calendar.length,    color: "#a855f7" },
            { label: "Clusters", value: data.insider_cluster.length,      color: "#22c55e" },
            { label: "Big Trades",value: data.big_insider_trades.length,  color: "#f59e0b" },
            { label: "Due Soon", value: data.upcoming_results.length,     color: "#ef4444" },
            ...(sentimentPct != null ? [{ label: "Sentiment", value: `${sentimentPct}%+`, color: sentimentPct >= 50 ? "#22c55e" : "#ef4444" }] : []),
          ].map((s, i) => (
            <div key={i} style={{
              textAlign: "center", padding: "8px 14px",
              background: "#1e293b", borderRadius: 10,
              border: `1px solid ${s.color}33`,
            }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: s.color }}>
                {s.value}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Body: 2-col layout ── */}
      <div style={{
        padding: "20px 28px",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 18,
        maxWidth: 1400,
      }}>
        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <ResultsSection    items={data.results_season} />
          <InsiderClusterSection items={data.insider_cluster} />
          <ReactionsSection  items={data.post_results_reaction} />
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <UpcomingSection   items={data.upcoming_results} />
          <BigTradesSection  items={data.big_insider_trades} />
          <DividendSection   items={data.dividend_calendar} />
          <AnalysisBox       text={String(data.analysis ?? "")} />
        </div>
      </div>
    </div>
  );
}
'''
write(SRC / "eta" / "page.tsx", ETA_PAGE, "/eta/page.tsx")


# ═════════════════════════════════════════════════════════════════════════════
# [3] NAVBAR — add ETA link
# ═════════════════════════════════════════════════════════════════════════════

print("\n[3/4] Patching NavBar.tsx ...")

navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if not navbar_path:
    print("  [SKIP] NavBar.tsx not found")
else:
    src = navbar_path.read_text(encoding="utf-8")
    if "eta" in src.lower():
        print("  [SKIP] ETA already in NavBar")
    else:
        # Find the last nav item by locating patterns / backtest / watchlist
        for marker in [
            "{ href: '/backtest'",
            "{ href: '/watchlist'",
            "{ href: '/patterns'",
            "/patterns'",
            "/backtest'",
            "/watchlist'",
        ]:
            if marker in src:
                # Find end of line
                idx = src.index(marker)
                line_end = src.find("\n", idx)
                if line_end == -1: line_end = len(src)
                # What style is used? object or JSX link?
                if marker.startswith("{ href:"):
                    to_insert = "\n  { href: '/eta', label: 'ETA' },"
                else:
                    # find what the pattern looks like and replicate style
                    to_insert = "\n  { href: '/eta', label: 'ETA' },"
                src = src[:line_end] + to_insert + src[line_end:]
                navbar_path.write_text(src, encoding="utf-8")
                print(f"  [OK] Added ETA after '{marker}'")
                break
        else:
            # Fallback: print lines with href for manual review
            print("  [WARN] Could not find insertion point. Lines with href:")
            for i, l in enumerate(src.splitlines(), 1):
                if "href" in l.lower():
                    print(f"    {i}: {l.strip()}")


# ═════════════════════════════════════════════════════════════════════════════
# [4] TELEGRAM BOT — add /eta /deep /kappa commands
# ═════════════════════════════════════════════════════════════════════════════

print("\n[4/4] Patching telegram_bot.py ...")

BOT = MICC / "telegram_bot.py"
if not BOT.exists():
    print("  [SKIP] telegram_bot.py not found")
else:
    src = BOT.read_text(encoding="utf-8")
    changed = False

    # ── Add ETA_REPORT / KAPPA / IOTA / DEEP paths near top ──────────────────
    PATHS_MARKER = "GAMMA_REPORT = Path"
    PATHS_INSERT = """\
ETA_REPORT   = Path("agents/eta/last_report.json")
IOTA_REPORT  = Path("agents/iota/last_report.json")
KAPPA_DIR    = Path("agents/kappa")
"""
    if "ETA_REPORT" not in src:
        src = src.replace(PATHS_MARKER, PATHS_INSERT + PATHS_MARKER)
        changed = True
        print("  [OK] Added ETA/IOTA/KAPPA report paths")
    else:
        print("  [SKIP] Report paths already present")

    # ── mkdir for new dirs ────────────────────────────────────────────────────
    MKDIR_MARKER = 'Path("agents/alpha").mkdir'
    MKDIR_INSERT = '''\
Path("agents/eta").mkdir(parents=True, exist_ok=True)
Path("agents/iota").mkdir(parents=True, exist_ok=True)
Path("agents/kappa").mkdir(parents=True, exist_ok=True)
'''
    if 'Path("agents/eta").mkdir' not in src:
        src = src.replace(MKDIR_MARKER, MKDIR_INSERT + MKDIR_MARKER)
        changed = True

    # ── /eta command ──────────────────────────────────────────────────────────
    ETA_CMD = '''

async def cmd_eta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send Eta (corporate events) report."""
    rep = load_json(ETA_REPORT)
    if not rep:
        await update.message.reply_text(
            "⚠️ No Eta report found.\\nRun: `py D:\\\\MICC\\\\agent_eta.py --send`",
            parse_mode="Markdown"
        )
        return

    lines = [f"*MICC Eta — Corporate Events {rep.get('date','')}*", ""]

    clusters = rep.get("insider_cluster", [])[:4]
    if clusters:
        lines.append("*INSIDER CLUSTERS:*")
        for c in clusters:
            lines.append(f"  `{c['symbol']}` {c['buy_count']} insiders | ₹{c.get('total_value_cr',0):.1f}Cr")
        lines.append("")

    big = rep.get("big_insider_trades", [])[:5]
    if big:
        lines.append("*BIG TRADES:*")
        for b in big:
            lines.append(f"  `{b['symbol']}` {b['transaction']} ₹{b.get('value_cr',0):.1f}Cr")
        lines.append("")

    results = rep.get("results_season", [])[:6]
    if results:
        total = len(rep.get("results_season", []))
        lines.append(f"*RESULTS REPORTED ({total}):*")
        for r in results:
            lines.append(f"  `{r['symbol']}` {r['date']}")
        lines.append("")

    upcoming = rep.get("upcoming_results", [])[:6]
    if upcoming:
        lines.append("*DUE SOON:*")
        for u in upcoming:
            lines.append(f"  `{u['symbol']}` ~{u['est_due_in']}d")
        lines.append("")

    analysis = str(rep.get("analysis", "")).strip()
    if analysis:
        lines.append("*INTEL:*")
        trimmed = analysis[:400]
        dot = trimmed.rfind(".")
        if dot > 100: trimmed = trimmed[:dot+1]
        lines.append(trimmed)

    msg = "\\n".join(lines)
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")
'''

    # ── /deep command ─────────────────────────────────────────────────────────
    DEEP_CMD = '''

async def cmd_deep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send deep profile for a symbol. Usage: /deep RELIANCE"""
    import subprocess, sys
    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/deep SYMBOL`\\nExample: `/deep RELIANCE`", parse_mode="Markdown")
        return
    symbol = args[0].upper().strip()
    await update.message.reply_text(f"⚙️ Running deep analysis for `{symbol}`…", parse_mode="Markdown")

    try:
        result = subprocess.run(
            [sys.executable, r"D:\\MICC\\agent_kappa.py", symbol, "--send"],
            capture_output=True, text=True, timeout=120,
            cwd=r"D:\\MICC"
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "Unknown error")[:300]
            await update.message.reply_text(f"❌ Error:\\n`{err}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"✅ Deep report for `{symbol}` sent!", parse_mode="Markdown")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⏱ Timed out (>120s). Try again.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", parse_mode="Markdown")
'''

    # ── /kappa command ────────────────────────────────────────────────────────
    KAPPA_CMD = '''

async def cmd_kappa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send Kappa deep profile for a symbol. Usage: /kappa SYMBOL"""
    await cmd_deep(update, context)  # same as /deep
'''

    # Insert new commands before main()
    MAIN_MARKER = "def main():"
    if "async def cmd_eta" not in src:
        src = src.replace(MAIN_MARKER, ETA_CMD + "\n" + MAIN_MARKER)
        changed = True
        print("  [OK] Added /eta command")

    if "async def cmd_deep" not in src:
        src = src.replace(MAIN_MARKER, DEEP_CMD + "\n" + MAIN_MARKER)
        changed = True
        print("  [OK] Added /deep command")

    if "async def cmd_kappa" not in src:
        src = src.replace(MAIN_MARKER, KAPPA_CMD + "\n" + MAIN_MARKER)
        changed = True
        print("  [OK] Added /kappa command")

    # ── Register handlers ─────────────────────────────────────────────────────
    HANDLER_MARKER = 'app.add_handler(CommandHandler("watch"'
    HANDLER_INSERT = '''\
    app.add_handler(CommandHandler("eta",   cmd_eta))
    app.add_handler(CommandHandler("deep",  cmd_deep))
    app.add_handler(CommandHandler("kappa", cmd_kappa))
'''
    if '"eta"' not in src:
        src = src.replace(HANDLER_MARKER, HANDLER_INSERT + "    " + HANDLER_MARKER)
        changed = True
        print("  [OK] Registered /eta /deep /kappa handlers")
    else:
        print("  [SKIP] Handlers already registered")

    # ── Update commands print line ─────────────────────────────────────────────
    OLD_CMDS = 'Commands: /start /report /alpha /beta /gamma /delta /streak /options /index /stock /hot /status'
    NEW_CMDS = 'Commands: /start /report /alpha /beta /gamma /delta /eta /streak /options /index /stock /hot /deep /kappa /watch /status'
    if OLD_CMDS in src:
        src = src.replace(OLD_CMDS, NEW_CMDS)
        changed = True

    if changed:
        BOT.write_text(src, encoding="utf-8")
        print("  [OK] telegram_bot.py saved")
    else:
        print("  [SKIP] No changes needed")


# ═════════════════════════════════════════════════════════════════════════════
# DONE
# ═════════════════════════════════════════════════════════════════════════════

print("""
=============================================================
BUILD PHASE 14 COMPLETE
=============================================================

[1] /api/eta/route.ts         -- reads agents/eta/last_report.json
[2] /eta/page.tsx             -- full Corporate Events dashboard
    - Header with 6 quick-stat chips
    - Results Season (expandable, up to 30)
    - Insider Cluster Buying (buy count + total Cr)
    - Big Insider Trades (colored BUY/SELL)
    - Post-Results Price Reaction (% gain/loss)
    - Results Due Soon (urgency color: red/amber/grey)
    - Dividend / Bonus / Split calendar
    - LLM Analysis box (Eta agent)
[3] NavBar.tsx                -- ETA link added
[4] telegram_bot.py           -- /eta /deep /kappa commands added

NEXT STEPS:
  1. Make sure Eta report exists:
       py D:\\MICC\\agent_eta.py

  2. Restart dashboard:
       cd D:\\MICC\\micc-dashboard && npm run dev

  3. Open: localhost:3000/eta

  4. For Telegram commands:
       /eta   -> sends Eta corporate events report
       /deep RELIANCE  -> runs agent_kappa.py RELIANCE --send
       /kappa HDFCBANK -> same as /deep

  5. NEXT in queue: /compare page (Lambda agent)
=============================================================
""")
