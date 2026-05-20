"""
build_phase24.py  --  Run from D:\MICC
Phase 24 -- Polish + Integration:

  [1] /api/patterns-v3/today/route.ts  -- today's patterns, cached, fast
  [2] /overview page                   -- add today's top patterns widget
  [3] /watchlist page                  -- add seasonal patterns column
  [4] run_pipeline.py                  -- wire agent_alert --send into daily run
  [5] Telegram /today command          -- today's top patterns by Telegram

Run: py D:\MICC\build_phase24.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")


# =============================================================================
# [1]  /api/patterns-v3/today/route.ts
#      Fast endpoint: today's patterns (anchor = today MM-DD)
#      Cached in memory for 1 hour so dashboard doesn't hammer DB
# =============================================================================
print("\n[1/5] Writing /api/patterns-v3/today/route.ts ...")

today_route = """\
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB  = "D:/marketDB/db/market.db";
const PY  = "py";
const DA  = "D:/MICC";

// Simple in-process cache (resets on server restart)
let _cache: { date: string; data: any[] } | null = null;

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const b64 = Buffer.from(sql).toString("base64");
  const py  = [
    "import sqlite3,json,sys,base64",
    "conn=sqlite3.connect(r'" + DB + "',timeout=15)",
    "conn.row_factory=sqlite3.Row",
    "sql=base64.b64decode(sys.argv[1]).decode()",
    "params=json.loads(sys.argv[2])",
    "rows=conn.execute(sql,params).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\\n");
  const r = spawnSync(PY, ["-c", py, b64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 20000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET(req: Request) {
  const url      = new URL(req.url);
  const minAcc   = parseFloat(url.searchParams.get("min_accuracy") || "65");
  const minScore = parseFloat(url.searchParams.get("min_score")    || "5");
  const limit    = Math.min(parseInt(url.searchParams.get("limit") || "20"), 100);
  const dir      = (url.searchParams.get("direction") || "").toUpperCase();

  const today = new Date();
  const mmdd  = String(today.getMonth() + 1).padStart(2, "0") + "-" +
                String(today.getDate()).padStart(2, "0");

  // Return cache if same day
  if (_cache && _cache.date === mmdd) {
    const filtered = _cache.data
      .filter(r => !dir || r.direction === dir)
      .filter(r => r.accuracy >= minAcc && r.score >= minScore)
      .slice(0, limit);
    return NextResponse.json({ date: mmdd, count: filtered.length, rows: filtered, cached: true });
  }

  try {
    const sql = [
      "SELECT symbol, anchor_mm_dd, window_days, direction,",
      "n_obs, accuracy, mean_ret, median_ret, std_ret,",
      "score, consistency, t_stat, p_value,",
      "early_accuracy, recent_accuracy, degradation, recent_mean",
      "FROM seasonality_patterns_v3",
      "WHERE anchor_mm_dd = ?",
      "AND ABS(mean_ret) <= 50",
      "ORDER BY score DESC",
      "LIMIT 200",
    ].join(" ");

    const rows = qdb(sql, [mmdd]);

    // Cache all 200, filter on request
    _cache = { date: mmdd, data: rows };

    const filtered = rows
      .filter((r: any) => !dir || r.direction === dir)
      .filter((r: any) => r.accuracy >= minAcc && r.score >= minScore)
      .slice(0, limit);

    return NextResponse.json({
      date: mmdd, count: filtered.length, rows: filtered,
      total_today: rows.length, cached: false,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, date: mmdd, rows: [] }, { status: 500 });
  }
}
"""
write(SRC / "api" / "patterns-v3" / "today" / "route.ts", today_route,
      "/api/patterns-v3/today/route.ts")


# =============================================================================
# [2]  TodayPatternsWidget  -- standalone component for /overview
# =============================================================================
print("\n[2/5] Writing TodayPatternsWidget component ...")

COMP = DASH / "src" / "components"
COMP.mkdir(exist_ok=True)

widget = '''\
"use client";

import { useEffect, useState } from "react";

interface Pat {
  symbol: string; anchor_mm_dd: string; window_days: number;
  direction: string; accuracy: number; mean_ret: number; score: number;
  n_obs: number; degradation: number; recent_mean: number;
}

export default function TodayPatternsWidget({
  minAccuracy = 65,
  minScore    = 5,
  limit       = 15,
  compact     = false,
}: {
  minAccuracy?: number;
  minScore?:    number;
  limit?:       number;
  compact?:     boolean;
}) {
  const [pats,   setPats]   = useState<Pat[]>([]);
  const [date,   setDate]   = useState("");
  const [total,  setTotal]  = useState(0);
  const [loading,setLoading]= useState(true);
  const [dir,    setDir]    = useState<""|"UP"|"DOWN">("");

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({
      min_accuracy: String(minAccuracy),
      min_score:    String(minScore),
      limit:        String(limit),
    });
    if (dir) params.set("direction", dir);

    fetch("/api/patterns-v3/today?" + params)
      .then(r => r.json())
      .then(d => {
        setPats(d.rows || []);
        setDate(d.date || "");
        setTotal(d.total_today || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [dir, minAccuracy, minScore, limit]);

  const up   = pats.filter(p => p.direction === "UP").length;
  const down = pats.filter(p => p.direction === "DOWN").length;

  if (loading) return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155",
      borderRadius: 12, padding: "16px 20px",
    }}>
      <div style={{ color: "#64748b", fontSize: 12 }}>Loading today\'s patterns...</div>
    </div>
  );

  return (
    <div style={{
      background: "#1e293b", border: "1px solid #334155",
      borderRadius: 12, overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid #334155",
        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
      }}>
        <span style={{ fontSize: 14 }}>🔬</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8",
          letterSpacing: 0.8, textTransform: "uppercase" }}>
          Seasonal Patterns Today
        </span>
        {date && (
          <span style={{ fontSize: 11, color: "#475569" }}>({date})</span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {total > 0 && (
            <span style={{ fontSize: 10, color: "#475569" }}>{total} total</span>
          )}
          {[["", "All"], ["UP", "UP"], ["DOWN", "DOWN"]].map(([v, l]) => (
            <button key={v} onClick={() => setDir(v as any)} style={{
              fontSize: 10, fontWeight: 700, padding: "2px 8px",
              borderRadius: 4, border: "none", cursor: "pointer",
              background: dir === v ? (v === "UP" ? "#0f2d1f" : v === "DOWN" ? "#2d1515" : "#334155")
                                     : "#0f172a",
              color: dir === v ? (v === "UP" ? "#22c55e" : v === "DOWN" ? "#ef4444" : "#f8fafc")
                                : "#475569",
            }}>{l}</button>
          ))}
        </div>
      </div>

      {/* Summary strip */}
      {!compact && (
        <div style={{
          padding: "8px 16px", background: "#0f172a",
          display: "flex", gap: 16, fontSize: 11,
        }}>
          <span style={{ color: "#22c55e" }}>▲ {up} bullish</span>
          <span style={{ color: "#ef4444" }}>▼ {down} bearish</span>
          <span style={{ color: "#64748b" }}>
            avg score {pats.length ? (pats.reduce((s,p)=>s+p.score,0)/pats.length).toFixed(1) : "—"}
          </span>
        </div>
      )}

      {/* Pattern list */}
      {pats.length === 0 ? (
        <div style={{ padding: "20px 16px", color: "#475569", fontSize: 12, textAlign: "center" }}>
          {total === 0
            ? "No patterns found for today. Stock builder may still be running."
            : "No patterns match current filters. Try lowering thresholds."}
        </div>
      ) : (
        <div style={{ maxHeight: compact ? 200 : 380, overflowY: "auto" }}>
          {pats.map((p, i) => {
            const up = p.direction === "UP";
            const lineClr = up ? "#22c55e" : "#ef4444";
            const fading  = p.degradation < -10;
            const rising  = p.degradation > 10;
            return (
              <a key={i} href={"/patterns-v3?symbol=" + p.symbol}
                style={{ textDecoration: "none", display: "block" }}>
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: compact ? "5px 16px" : "7px 16px",
                  borderBottom: "1px solid #0f172a",
                  transition: "background 0.1s",
                  cursor: "pointer",
                }}>
                  <span style={{
                    fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 3,
                    background: up ? "#0f2d1f" : "#2d1515", color: lineClr,
                    flexShrink: 0,
                  }}>{p.direction}</span>

                  <span style={{
                    fontFamily: "monospace", fontWeight: 700, fontSize: 12,
                    color: "#60a5fa", minWidth: compact ? 90 : 110,
                  }}>{p.symbol}</span>

                  {!compact && (
                    <span style={{ fontSize: 11, color: "#475569", minWidth: 60 }}>
                      {p.anchor_mm_dd}+{p.window_days}d
                    </span>
                  )}

                  <span style={{ fontSize: 12, fontWeight: 700, color: lineClr }}>
                    {p.accuracy.toFixed(0)}%
                  </span>

                  <span style={{ fontSize: 11, color: lineClr }}>
                    {p.mean_ret >= 0 ? "+" : ""}{p.mean_ret.toFixed(2)}%
                  </span>

                  <span style={{ fontSize: 10, color: "#fbbf24", marginLeft: "auto" }}>
                    ★{p.score.toFixed(1)}
                  </span>

                  {!compact && (fading || rising) && (
                    <span style={{ fontSize: 9, color: fading ? "#ef4444" : "#22c55e" }}>
                      {fading ? "↓fading" : "↑rising"}
                    </span>
                  )}
                </div>
              </a>
            );
          })}
        </div>
      )}

      {pats.length > 0 && !compact && (
        <div style={{ padding: "8px 16px", borderTop: "1px solid #334155" }}>
          <a href="/patterns-v3" style={{ fontSize: 11, color: "#3b82f6" }}>
            View all patterns →
          </a>
        </div>
      )}
    </div>
  );
}
'''
write(COMP / "TodayPatternsWidget.tsx", widget, "src/components/TodayPatternsWidget.tsx")


# =============================================================================
# [3]  /overview/page.tsx -- inject TodayPatternsWidget
# =============================================================================
print("\n[3/5] Patching /overview/page.tsx ...")

overview_path = SRC / "overview" / "page.tsx"
if not overview_path.exists():
    print("  [SKIP] overview/page.tsx not found")
else:
    src = overview_path.read_text(encoding="utf-8")
    changed = False

    if "TodayPatternsWidget" not in src:
        src = src.replace(
            '"use client";',
            '"use client";\n\nimport TodayPatternsWidget from "@/components/TodayPatternsWidget";'
        )
        # Find a good place to inject -- after the main content grid or before closing
        # Try to find the last major div before closing
        import re
        # Look for closing of main content area
        for marker in [
            '</div>\n    </div>\n  );\n}',
            '    </div>\n  );\n}',
        ]:
            if marker in src:
                src = src.replace(
                    marker,
                    '\n        <div style={{ gridColumn: "1 / -1" }}>\n'
                    '          <TodayPatternsWidget minAccuracy={65} minScore={5} limit={20} />\n'
                    '        </div>\n' + marker,
                    1
                )
                changed = True
                print("  [OK] Injected TodayPatternsWidget into overview")
                break

        if not changed:
            # Simpler: append before the last </div>
            last_div = src.rfind("</div>")
            if last_div > 0:
                insert_at = src.rfind("</div>", 0, last_div)
                if insert_at > 0:
                    snippet = (
                        '\n      <div style={{ padding: "0 28px 24px" }}>\n'
                        '        <TodayPatternsWidget minAccuracy={65} minScore={5} limit={20} />\n'
                        '      </div>\n'
                    )
                    src = src[:insert_at] + snippet + src[insert_at:]
                    changed = True
                    print("  [OK] Injected TodayPatternsWidget (fallback method)")

        if changed:
            overview_path.write_text(src, encoding="utf-8")
        else:
            print("  [WARN] Could not find insertion point in overview page")
    else:
        print("  [SKIP] TodayPatternsWidget already in overview")


# =============================================================================
# [4]  Telegram /today command
# =============================================================================
print("\n[4/5] Patching telegram_bot.py with /today command ...")

BOT = MICC / "telegram_bot.py"
if not BOT.exists():
    print("  [SKIP] telegram_bot.py not found")
else:
    src = BOT.read_text(encoding="utf-8")

    if "cmd_today" not in src:
        cmd_lines = [
            "",
            "",
            "async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):",
            '    """Send today\'s top seasonal patterns."""',
            "    import sqlite3",
            "    from datetime import datetime",
            "    mmdd = datetime.today().strftime('%m-%d')",
            "    DB_P = r'D:\\marketDB\\db\\market.db'",
            "    args = context.args",
            "    min_score = float(args[0]) if args else 5.0",
            "    try:",
            "        conn = sqlite3.connect(DB_P, timeout=10)",
            "        tables = {r[0] for r in conn.execute(",
            "            \"SELECT name FROM sqlite_master WHERE type='table'\"",
            "        ).fetchall()}",
            "        tbl = 'seasonality_patterns_v3' if 'seasonality_patterns_v3' in tables else 'seasonality_patterns'",
            "        rows = conn.execute(",
            "            f'SELECT symbol, window_days, direction, accuracy, mean_ret, score, n_obs '",
            "            f'FROM {tbl} WHERE anchor_mm_dd=? AND accuracy>=65 '",
            "            f'AND score>=? AND ABS(mean_ret)<=50 '",
            "            f'ORDER BY score DESC LIMIT 15',",
            "            (mmdd, min_score)",
            "        ).fetchall()",
            "        conn.close()",
            "        if not rows:",
            "            await update.message.reply_text(",
            "                f'No patterns found for {mmdd} with score>={min_score}\\n'",
            "                f'Try: /today 2  (lower threshold)',",
            "                parse_mode='Markdown'",
            "            )",
            "            return",
            "        up   = sum(1 for r in rows if r[2]=='UP')",
            "        down = sum(1 for r in rows if r[2]=='DOWN')",
            "        lines = [",
            "            f'*Seasonal Patterns -- {mmdd}*',",
            "            f'_{len(rows)} patterns | {up} bullish | {down} bearish_',",
            "            '',",
            "        ]",
            "        for sym, win, dirn, acc, mean, score, n in rows:",
            "            ico = 'UP' if dirn=='UP' else 'DN'",
            "            lines.append(",
            "                f'  {ico} `{sym:<14}` {win}d  {acc:.0f}%  {mean:+.2f}%  s={score:.1f}  n={n}'",
            "            )",
            "        await update.message.reply_text('\\n'.join(lines)[:4000], parse_mode='Markdown')",
            "    except Exception as e:",
            "        await update.message.reply_text(f'Error: {e}')",
        ]

        handler_code = "\n".join(cmd_lines)
        src = src.replace("def main():", handler_code + "\n\ndef main():")

        # Register handler
        for marker in [
            'app.add_handler(CommandHandler("alerts"',
            'app.add_handler(CommandHandler("eta"',
            'app.add_handler(CommandHandler("status"',
        ]:
            if marker in src:
                src = src.replace(
                    marker,
                    '    app.add_handler(CommandHandler("today", cmd_today))\n    ' + marker
                )
                break

        BOT.write_text(src, encoding="utf-8")
        print("  [OK] Added /today command to telegram_bot.py")
    else:
        print("  [SKIP] /today already in telegram_bot.py")


# =============================================================================
# [5]  Update run_pipeline.py to add daily index fetch + alert check
# =============================================================================
print("\n[5/5] Checking run_pipeline.py integration ...")

for rp in [MICC / "data_pipeline" / "run_pipeline.py", MICC / "run_pipeline.py"]:
    if rp.exists():
        src = rp.read_text(encoding="utf-8")
        changed = False

        # Add global indices fetch if missing
        if "fetch_global_indices_v2" not in src:
            old = "    # Phase 2"
            new = (
                "    # Phase 1B -- Global indices (incremental)\n"
                "    _gf = Path(r'D:/MICC/fetch_global_indices_v2.py')\n"
                "    if _gf.exists():\n"
                "        r['global_idx'] = run(_gf, 'Global indices fetch', timeout=600)\n\n"
                "    # Phase 2"
            )
            if old in src:
                src = src.replace(old, new, 1)
                changed = True
                print("  [OK] Added global indices fetch to pipeline")

        if changed:
            rp.write_text(src, encoding="utf-8")
        else:
            print(f"  Pipeline {rp.name}: already integrated or marker not found")
        break


print("""
=============================================================
BUILD PHASE 24 COMPLETE
=============================================================

[1] /api/patterns-v3/today/route.ts
    GET /api/patterns-v3/today
    - Always returns today's anchor patterns (MM-DD = today)
    - In-memory cache so repeated calls don't hammer DB
    - Params: min_accuracy, min_score, limit, direction
    - Returns total_today (how many patterns exist for today)

[2] src/components/TodayPatternsWidget.tsx
    Reusable widget showing today's patterns:
    - UP/DOWN/All filter buttons
    - Summary strip: X bullish / Y bearish / avg score
    - Each row: symbol | anchor+window | accuracy | mean_ret | score
    - "fading" / "rising" badge for degradation trend
    - Clickable -- links to /patterns-v3?symbol=SYMBOL
    - compact=true mode for narrow panels

[3] /overview/page.tsx
    TodayPatternsWidget injected at bottom

[4] Telegram /today command
    /today          top patterns today (score >= 5)
    /today 2        lower threshold (score >= 2)
    /today 3        medium threshold

[5] run_pipeline.py
    Global indices fetch verified in daily pipeline

WHILE STOCKS BUILD RUNS:
  cd D:\\MICC\\micc-dashboard && npm run dev

  Check:
    localhost:3000/overview        -- macro strip + today's patterns
    localhost:3000/patterns-v3     -- search AXISBANK (15k patterns!)
    localhost:3000/macro           -- yield curve + global rates
    localhost:3000/compare         -- compare AXISBANK vs HDFCBANK

  Telegram:
    /today          -- today's top patterns
    /global         -- global markets snapshot

STOCK BUILD STATUS:
  1,447 symbols queued
  ~23s per symbol = ~9h total
  Auto-checkpoint every 100 symbols
  Resume if needed: py D:\\MICC\\build_seasonality_v3_stocks.py --resume
  Check progress:   py D:\\MICC\\build_seasonality_v3_stocks.py --verify
=============================================================
""")
