"""
build_eta_portfolio_pages.py
=============================
Builds two new dashboard pages:
  [1] /eta         -- Agent Eta: insider clusters, results, dividends, big trades
  [2] /portfolio   -- Portfolio tracker: positions, ATR sizing, P&L, exit signals
  [3] /api/eta/route.ts          -- reads agents/eta/last_report.json
  [4] /api/portfolio/route.ts    -- reads my_portfolio table from DB
  [5] NavBar update              -- add Eta + Portfolio links

Run: py D:/MICC/build_eta_portfolio_pages.py
"""
from pathlib import Path

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
# [1]  /api/eta/route.ts
# =============================================================================
print("\n[1/5] /api/eta/route.ts ...")

write(SRC / "api" / "eta" / "route.ts", """\
import { NextResponse } from "next/server";
import { readFileSync }  from "fs";
import { join }          from "path";

const REPORT = join("D:/MICC", "agents", "eta", "last_report.json");

function safe(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null")
          .replace(/:\\s*Infinity\\b/g, ": null")
          .replace(/:\\s*-Infinity\\b/g, ": null");
}

export async function GET() {
  try {
    const raw  = readFileSync(REPORT, "utf-8");
    const data = JSON.parse(safe(raw));
    return NextResponse.json({ ok: true, data });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message, data: null });
  }
}
""", "/api/eta/route.ts")


# =============================================================================
# [2]  /api/portfolio/route.ts
# =============================================================================
print("\n[2/5] /api/portfolio/route.ts ...")

write(SRC / "api" / "portfolio" / "route.ts", """\
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB = "D:/marketDB/db/market.db";
const PY = "C:/Users/marka/AppData/Local/Programs/Python/Python314/python.exe";

function qdb(sql: string, params: any[] = []): any[] {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r'${DB}', timeout=15)
conn.row_factory = sqlite3.Row
try:
    rows = conn.execute(sys.argv[1], json.loads(sys.argv[2])).fetchall()
    print(json.dumps([dict(r) for r in rows], default=str))
except Exception as e:
    print(json.dumps([]))
conn.close()
`.trim();
  const r = spawnSync(PY, ["-c", script, sql, JSON.stringify(params)],
    { encoding: "utf-8", timeout: 10000 });
  try { return JSON.parse(r.stdout || "[]"); } catch { return []; }
}

export async function GET() {
  try {
    // Check table exists
    const tables = qdb(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='my_portfolio'", []
    );
    if (!tables.length) {
      return NextResponse.json({ ok: true, positions: [], summary: null,
        message: "my_portfolio table not found. Add positions via agent_exit.py" });
    }

    const positions = qdb(
      \`SELECT symbol, entry_date, entry_price, quantity, atr_at_entry,
              stop_loss, target, position_size_pct, notes,
              last_updated
       FROM my_portfolio ORDER BY entry_date DESC\`, []
    );

    // Enrich with current price
    const syms = [...new Set(positions.map((p: any) => p.symbol))];
    let prices: Record<string, number> = {};
    if (syms.length > 0) {
      const ph = syms.map(() => "?").join(",");
      const priceRows = qdb(
        \`SELECT symbol, close FROM stock_data
         WHERE symbol IN (\${ph})
         AND date = (SELECT MAX(date) FROM stock_data WHERE symbol = stock_data.symbol)\`,
        syms
      );
      priceRows.forEach((r: any) => { prices[r.symbol] = r.close; });
    }

    const enriched = positions.map((p: any) => {
      const cur = prices[p.symbol] ?? null;
      const pnl_pct = cur && p.entry_price
        ? ((cur - p.entry_price) / p.entry_price * 100).toFixed(2)
        : null;
      const pnl_rs = cur && p.entry_price && p.quantity
        ? ((cur - p.entry_price) * p.quantity).toFixed(0)
        : null;
      const at_stop   = cur && p.stop_loss  ? cur <= p.stop_loss  : false;
      const at_target = cur && p.target     ? cur >= p.target     : false;
      return { ...p, current_price: cur, pnl_pct, pnl_rs, at_stop, at_target };
    });

    // Summary
    const total_pnl = enriched.reduce((s: number, p: any) =>
      s + (parseFloat(p.pnl_rs) || 0), 0);
    const winners   = enriched.filter((p: any) => (parseFloat(p.pnl_pct) || 0) > 0).length;

    return NextResponse.json({
      ok: true,
      positions: enriched,
      summary: {
        n_positions: enriched.length,
        total_pnl_rs: total_pnl.toFixed(0),
        winners,
        losers: enriched.length - winners,
      }
    });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 });
  }
}
""", "/api/portfolio/route.ts")


# =============================================================================
# [3]  /eta/page.tsx
# =============================================================================
print("\n[3/5] /eta/page.tsx ...")

write(SRC / "eta" / "page.tsx", """\
"use client";
import { useEffect, useState } from "react";

const S = {
  page:    { padding: "28px 32px", fontFamily: "monospace", maxWidth: 1200,
             margin: "0 auto", color: "var(--text)" },
  hdr:     { fontSize: 22, fontWeight: 700, color: "var(--accent)",
             letterSpacing: 1, marginBottom: 4 },
  sub:     { fontSize: 12, color: "var(--muted)", marginBottom: 28 },
  grid:    { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 },
  card:    { background: "var(--card)", border: "1px solid var(--border)",
             borderRadius: 8, padding: "18px 20px" },
  cardHdr: { fontSize: 11, fontWeight: 700, color: "var(--accent)",
             letterSpacing: 2, textTransform: "uppercase" as const,
             marginBottom: 14, borderBottom: "1px solid var(--border)",
             paddingBottom: 8 },
  row:     { display: "flex", alignItems: "center", gap: 10,
             padding: "7px 0", borderBottom: "1px solid #0f172a",
             fontSize: 12 },
  sym:     { fontWeight: 700, color: "var(--text)", minWidth: 110,
             fontFamily: "monospace" },
  pill:    (c: string) => ({
             fontSize: 10, fontWeight: 700, padding: "2px 7px",
             borderRadius: 4, background: c + "22", color: c }),
  muted:   { color: "var(--muted)", fontSize: 11 },
  pos:     { color: "var(--pos)", fontWeight: 700 },
  neg:     { color: "var(--neg)", fontWeight: 700 },
  warn:    { color: "var(--warn)", fontWeight: 700 },
  empty:   { color: "var(--dim)", fontSize: 12, padding: "12px 0" },
  badge:   (n: number) => ({
             display: "inline-block", marginLeft: 8, fontSize: 10,
             background: "var(--accent)", color: "#000",
             borderRadius: 10, padding: "1px 7px", fontWeight: 700,
             opacity: n > 0 ? 1 : 0.3 }),
};

function Section({ title, count, children }: any) {
  return (
    <div style={S.card}>
      <div style={S.cardHdr}>
        {title}<span style={S.badge(count)}>{count}</span>
      </div>
      {children}
    </div>
  );
}

export default function EtaPage() {
  const [data, setData]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState("");

  useEffect(() => {
    fetch("/api/eta")
      .then(r => r.json())
      .then(j => { setData(j.data); setLoading(false); })
      .catch(e => { setErr(e.message); setLoading(false); });
  }, []);

  if (loading) return <div style={S.page}><div style={S.muted}>Loading Eta report...</div></div>;
  if (err || !data) return <div style={S.page}><div style={{color:"var(--neg)"}}>
    Error: {err || "No report. Run: py agent_eta.py"}</div></div>;

  const clusters  = data.insider_cluster    || [];
  const bigTrades = data.big_insider_trades || [];
  const results   = data.results_season     || [];
  const divs      = data.dividend_calendar  || [];
  const upcoming  = data.upcoming_results   || [];
  const reactions = data.post_results_reaction || [];

  return (
    <div style={S.page}>
      <div style={S.hdr}>Agent Eta — Corporate Intelligence</div>
      <div style={S.sub}>
        Updated: {data.generated_at || data.date}
        &nbsp;&nbsp;|&nbsp;&nbsp;
        Results: {results.length}&nbsp; Insiders: {clusters.length}&nbsp;
        Dividends: {divs.length}&nbsp; Upcoming: {upcoming.length}
      </div>

      <div style={S.grid}>

        {/* Insider Clusters */}
        <Section title="Insider Clusters" count={clusters.length}>
          {clusters.length === 0
            ? <div style={S.empty}>No clusters in last 30 days</div>
            : clusters.map((c: any, i: number) => (
              <div key={i} style={S.row}>
                <span style={S.sym}>{c.symbol}</span>
                <span style={{...S.pill("#22c55e"), marginLeft: "auto"}}>
                  {c.buy_count}x BUY
                </span>
                <span style={S.warn}>
                  {c.total_value_cr != null
                    ? `Rs.${Number(c.total_value_cr).toFixed(1)}Cr` : ""}
                </span>
                <span style={S.muted}>{c.latest_date || ""}</span>
              </div>
            ))
          }
        </Section>

        {/* Big Insider Trades */}
        <Section title="Big Insider Trades" count={bigTrades.length}>
          {bigTrades.length === 0
            ? <div style={S.empty}>No big trades in last 30 days</div>
            : bigTrades.slice(0, 12).map((t: any, i: number) => {
              const isBuy = (t.transaction_type || "").toUpperCase().includes("BUY");
              return (
                <div key={i} style={S.row}>
                  <span style={S.sym}>{t.symbol}</span>
                  <span style={isBuy ? S.pos : S.neg}>
                    {t.transaction_type}
                  </span>
                  <span style={{...S.muted, marginLeft: "auto"}}>
                    Rs.{t.value_cr != null
                      ? Number(t.value_cr).toFixed(1)
                      : t.value != null
                        ? (Number(t.value)/1e7).toFixed(1) : "?"}Cr
                  </span>
                  <span style={S.muted}>{t.name?.slice(0, 18) || ""}</span>
                </div>
              );
            })
          }
        </Section>

        {/* Results Season */}
        <Section title="Results Season" count={results.length}>
          {results.length === 0
            ? <div style={S.empty}>No recent results announcements</div>
            : results.slice(0, 12).map((r: any, i: number) => (
              <div key={i} style={S.row}>
                <span style={S.sym}>{r.symbol}</span>
                <span style={S.muted}>{r.announcement_date}</span>
                <span style={{...S.muted, marginLeft: "auto",
                  maxWidth: 220, overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" as const}}>
                  {r.subject}
                </span>
              </div>
            ))
          }
        </Section>

        {/* Dividend / Corporate Actions */}
        <Section title="Dividend / Bonus / Split" count={divs.length}>
          {divs.length === 0
            ? <div style={S.empty}>No upcoming corporate actions</div>
            : divs.slice(0, 12).map((d: any, i: number) => {
              const kw  = (d.subject || "").toLowerCase();
              const col = kw.includes("bonus") ? "#818cf8"
                        : kw.includes("split") ? "#fbbf24"
                        : "#22c55e";
              return (
                <div key={i} style={S.row}>
                  <span style={S.sym}>{d.symbol}</span>
                  <span style={S.pill(col)}>
                    {kw.includes("bonus") ? "BONUS"
                      : kw.includes("split") ? "SPLIT"
                      : "DIV"}
                  </span>
                  <span style={{...S.muted, marginLeft: "auto"}}>
                    {d.announcement_date}
                  </span>
                </div>
              );
            })
          }
        </Section>

        {/* Upcoming Results */}
        <Section title="Upcoming Results" count={upcoming.length}>
          {upcoming.length === 0
            ? <div style={S.empty}>No upcoming results detected</div>
            : upcoming.slice(0, 12).map((u: any, i: number) => (
              <div key={i} style={S.row}>
                <span style={S.sym}>{u.symbol}</span>
                <span style={S.muted}>last: {u.last_result_date || "?"}</span>
                <span style={{...S.warn, marginLeft: "auto"}}>
                  ~{u.days_since || "?"} days ago
                </span>
              </div>
            ))
          }
        </Section>

        {/* Post-Results Reactions */}
        <Section title="Post-Results Price Reactions" count={reactions.length}>
          {reactions.length === 0
            ? <div style={S.empty}>No reactions data available</div>
            : reactions.slice(0, 10).map((r: any, i: number) => {
              const pct = parseFloat(r.price_reaction_pct || 0);
              return (
                <div key={i} style={S.row}>
                  <span style={S.sym}>{r.symbol}</span>
                  <span style={pct >= 0 ? S.pos : S.neg}>
                    {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                  </span>
                  <span style={S.muted}>{r.announcement_date}</span>
                </div>
              );
            })
          }
        </Section>

      </div>

      {/* LLM Analysis */}
      {data.analysis && (
        <div style={{ ...S.card, marginTop: 20 }}>
          <div style={S.cardHdr}>LLM Analysis</div>
          <pre style={{ fontSize: 12, color: "var(--muted)", whiteSpace: "pre-wrap" as const,
            lineHeight: 1.6, margin: 0 }}>
            {typeof data.analysis === "string"
              ? data.analysis
              : JSON.stringify(data.analysis, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
""", "/eta/page.tsx")


# =============================================================================
# [4]  /portfolio/page.tsx
# =============================================================================
print("\n[4/5] /portfolio/page.tsx ...")

write(SRC / "portfolio" / "page.tsx", """\
"use client";
import { useEffect, useState } from "react";

const S = {
  page:  { padding: "28px 32px", fontFamily: "monospace", maxWidth: 1200,
           margin: "0 auto", color: "var(--text)" },
  hdr:   { fontSize: 22, fontWeight: 700, color: "var(--accent)",
           letterSpacing: 1, marginBottom: 4 },
  sub:   { fontSize: 12, color: "var(--muted)", marginBottom: 28 },
  summary: { display: "flex", gap: 20, marginBottom: 28, flexWrap: "wrap" as const },
  stat:  { background: "var(--card)", border: "1px solid var(--border)",
           borderRadius: 8, padding: "14px 20px", minWidth: 130 },
  sLabel:{ fontSize: 10, color: "var(--muted)", letterSpacing: 1,
           textTransform: "uppercase" as const, marginBottom: 4 },
  sVal:  { fontSize: 22, fontWeight: 700, color: "var(--accent)" },
  card:  { background: "var(--card)", border: "1px solid var(--border)",
           borderRadius: 8, padding: "18px 20px", marginBottom: 20 },
  th:    { fontSize: 10, color: "var(--muted)", fontWeight: 700,
           letterSpacing: 1, textTransform: "uppercase" as const,
           padding: "0 10px 10px 0", borderBottom: "1px solid var(--border)",
           textAlign: "left" as const },
  td:    { padding: "10px 10px 10px 0", fontSize: 12,
           borderBottom: "1px solid #0f172a", verticalAlign: "top" as const },
  pos:   { color: "var(--pos)", fontWeight: 700 },
  neg:   { color: "var(--neg)", fontWeight: 700 },
  warn:  { color: "var(--warn)", fontWeight: 700 },
  sym:   { fontWeight: 700, color: "var(--text)", fontFamily: "monospace" },
  muted: { color: "var(--muted)" },
  pill:  (c: string) => ({ fontSize: 10, fontWeight: 700, padding: "2px 7px",
           borderRadius: 4, background: c + "22", color: c }),
  empty: { color: "var(--dim)", fontSize: 13, padding: "32px 0",
           textAlign: "center" as const },
  addBox:{ background: "var(--surface)", border: "1px solid var(--border)",
           borderRadius: 8, padding: "20px", marginTop: 20 },
};

function StatCard({ label, value, color }: any) {
  return (
    <div style={S.stat}>
      <div style={S.sLabel}>{label}</div>
      <div style={{ ...S.sVal, color: color || "var(--accent)" }}>{value}</div>
    </div>
  );
}

function PnlCell({ pct }: { pct: string | null }) {
  if (pct === null) return <span style={S.muted}>--</span>;
  const n = parseFloat(pct);
  return <span style={n >= 0 ? S.pos : S.neg}>{n >= 0 ? "+" : ""}{pct}%</span>;
}

function StatusPill({ pos }: { pos: any }) {
  if (pos.at_target) return <span style={S.pill("#22c55e")}>TARGET HIT</span>;
  if (pos.at_stop)   return <span style={S.pill("#ef4444")}>STOP HIT</span>;
  const pct = parseFloat(pos.pnl_pct || 0);
  if (pct > 5)  return <span style={S.pill("#22c55e")}>IN PROFIT</span>;
  if (pct < -3) return <span style={S.pill("#ef4444")}>DRAWDOWN</span>;
  return <span style={S.pill("#64748b")}>OPEN</span>;
}

export default function PortfolioPage() {
  const [data, setData]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    setLoading(true);
    fetch("/api/portfolio")
      .then(r => r.json())
      .then(j => { setData(j); setLoading(false); })
      .catch(e => { setErr(e.message); setLoading(false); });
  }, [refresh]);

  if (loading) return <div style={S.page}><div style={S.muted}>Loading portfolio...</div></div>;
  if (err) return <div style={S.page}><div style={{color:"var(--neg)"}}>Error: {err}</div></div>;

  const positions = data?.positions || [];
  const summary   = data?.summary;
  const totalPnl  = parseFloat(summary?.total_pnl_rs || 0);

  return (
    <div style={S.page}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 4 }}>
        <div style={S.hdr}>Portfolio Tracker</div>
        <button onClick={() => setRefresh(r => r + 1)}
          style={{ fontSize: 11, padding: "4px 12px", borderRadius: 4,
            background: "var(--surface)", border: "1px solid var(--border)",
            color: "var(--muted)", cursor: "pointer" }}>
          Refresh
        </button>
      </div>
      <div style={S.sub}>
        ATR-sized positions &nbsp;|&nbsp; Live P&amp;L from stock_data
        &nbsp;|&nbsp; Add positions: py agent_exit.py
      </div>

      {summary && (
        <div style={S.summary}>
          <StatCard label="Positions" value={summary.n_positions} />
          <StatCard label="Total P&L"
            value={`Rs.${Number(summary.total_pnl_rs).toLocaleString()}`}
            color={totalPnl >= 0 ? "var(--pos)" : "var(--neg)"} />
          <StatCard label="Winners" value={summary.winners} color="var(--pos)" />
          <StatCard label="Losers"  value={summary.losers}  color="var(--neg)" />
          <StatCard label="Win Rate"
            value={summary.n_positions > 0
              ? `${(100 * summary.winners / summary.n_positions).toFixed(0)}%` : "--"} />
        </div>
      )}

      <div style={S.card}>
        {positions.length === 0 ? (
          <div style={S.empty}>
            No positions yet.
            <br /><br />
            <span style={S.muted}>
              Add your first position via:<br />
              <code style={{ color: "var(--accent)" }}>py D:/MICC/agent_exit.py --add SYMBOL ENTRY_PRICE QTY</code>
              <br /><br />
              Or insert directly into my_portfolio table in market.db
            </span>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["Symbol","Entry Date","Entry Price","Qty","Current","P&L %","P&L Rs","Stop","Target","Status"]
                  .map(h => <th key={h} style={S.th}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {positions.map((p: any, i: number) => (
                <tr key={i}>
                  <td style={S.td}><span style={S.sym}>{p.symbol}</span></td>
                  <td style={S.td}><span style={S.muted}>{p.entry_date}</span></td>
                  <td style={S.td}>{p.entry_price ? Number(p.entry_price).toFixed(2) : "--"}</td>
                  <td style={S.td}>{p.quantity}</td>
                  <td style={S.td}>
                    {p.current_price
                      ? <span style={{ color: "var(--accent)" }}>
                          {Number(p.current_price).toFixed(2)}
                        </span>
                      : <span style={S.muted}>--</span>}
                  </td>
                  <td style={S.td}><PnlCell pct={p.pnl_pct} /></td>
                  <td style={S.td}>
                    {p.pnl_rs
                      ? <span style={parseFloat(p.pnl_rs) >= 0 ? S.pos : S.neg}>
                          {parseFloat(p.pnl_rs) >= 0 ? "+" : ""}
                          {Number(p.pnl_rs).toLocaleString()}
                        </span>
                      : <span style={S.muted}>--</span>}
                  </td>
                  <td style={S.td}>
                    {p.stop_loss
                      ? <span style={S.neg}>{Number(p.stop_loss).toFixed(2)}</span>
                      : <span style={S.muted}>--</span>}
                  </td>
                  <td style={S.td}>
                    {p.target
                      ? <span style={S.pos}>{Number(p.target).toFixed(2)}</span>
                      : <span style={S.muted}>--</span>}
                  </td>
                  <td style={S.td}><StatusPill pos={p} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Quick-add hint */}
      <div style={S.addBox}>
        <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700,
          letterSpacing: 1, textTransform: "uppercase", marginBottom: 10 }}>
          How to add a position
        </div>
        <div style={{ fontSize: 12, color: "var(--dim)", lineHeight: 1.8 }}>
          {"// Insert directly into DB (ATR sizing auto-calculated):"}
          <br />
          {"py D:/MICC/agent_exit.py --add RELIANCE 1450.00 10"}
          <br /><br />
          {"// Or via Python:"}
          <br />
          {"import sqlite3"}
          <br />
          {"conn = sqlite3.connect(r'D:/marketDB/db/market.db')"}
          <br />
          {"conn.execute(\"INSERT INTO my_portfolio (symbol, entry_date, entry_price, quantity, stop_loss, target) VALUES (?,?,?,?,?,?)\", ('RELIANCE','2026-05-18',1450.0,10,1380.0,1600.0))"}
          <br />
          {"conn.commit()"}
        </div>
      </div>
    </div>
  );
}
""", "/portfolio/page.tsx")


# =============================================================================
# [5]  NavBar — add /eta and /portfolio links
# =============================================================================
print("\n[5/5] Patching NavBar...")

navbar = COMP / "NavBar.tsx"
if navbar.exists():
    src = navbar.read_text(encoding="utf-8")
    # Find /eta and /portfolio - add only if missing
    changed = False
    if '"/eta"' not in src and "'/eta'" not in src:
        # Try to insert after /backtest or before the closing of navLinks array
        for anchor in ['{ href: "/backtest"', '{ href: "/patterns"']:
            if anchor in src:
                src = src.replace(
                    anchor,
                    '{ href: "/eta", label: "Eta" },\n    { href: "/portfolio", label: "Portfolio" },\n    ' + anchor,
                    1
                )
                changed = True
                break
        if not changed:
            # Fallback: append before last } of links array
            print("  [WARN] Could not find NavBar anchor -- add manually:")
            print('    { href: "/eta", label: "Eta" },')
            print('    { href: "/portfolio", label: "Portfolio" },')
        else:
            navbar.write_text(src, encoding="utf-8")
            print("  [OK] NavBar patched -- /eta and /portfolio added")
    else:
        print("  [SKIP] NavBar already has /eta link")
else:
    print("  [SKIP] NavBar.tsx not found at", navbar)


print("""
============================================================
  DONE — Eta + Portfolio pages built

  Open:
    http://localhost:3000/eta        -- corporate events
    http://localhost:3000/portfolio  -- positions tracker

  First run Eta agent to populate report:
    py D:/MICC/agent_eta.py

  Add first portfolio position (example):
    py -c "
import sqlite3
conn = sqlite3.connect(r'D:/marketDB/db/market.db')
conn.execute('''CREATE TABLE IF NOT EXISTS my_portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT, entry_date TEXT, entry_price REAL,
    quantity REAL, atr_at_entry REAL,
    stop_loss REAL, target REAL,
    position_size_pct REAL, notes TEXT, last_updated TEXT
)''')
conn.execute(\\\"INSERT OR IGNORE INTO my_portfolio
    (symbol, entry_date, entry_price, quantity, stop_loss, target, notes)
    VALUES ('RELIANCE','2026-05-18',1453.0,10,1385.0,1600.0,'Test position')\\\")
conn.commit()
conn.close()
print('Added')
"
============================================================
""")
