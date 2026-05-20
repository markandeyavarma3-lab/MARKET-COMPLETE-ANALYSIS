import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";
import fs               from "fs";
import path             from "path";

const DB = "D:/marketDB/db/market.db";
const DA = "D:/MICC";
const PY = "py";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qdb(sql: string): any[] {
  const b64 = Buffer.from(sql).toString("base64");
  const py  = [
    "import sqlite3,json,sys,base64",
    "conn=sqlite3.connect(r'" + DB + "',timeout=10)",
    "conn.row_factory=sqlite3.Row",
    "sql=base64.b64decode(sys.argv[1]).decode()",
    "rows=conn.execute(sql).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\n");
  const r = spawnSync(PY, ["-c", py, b64], { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

function getDBSize(): string {
  try {
    const stat = fs.statSync(DB);
    const mb   = stat.size / 1024 / 1024;
    return mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : mb.toFixed(0) + " MB";
  } catch { return "Unknown"; }
}

function loadReport(name: string): any | null {
  const p = path.join(DA, "agents", name, "last_report.json");
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(sanitize(fs.readFileSync(p, "utf-8")));
  } catch { return null; }
}

export async function GET() {
  try {
    // Table row counts
    const tables = qdb(
      "SELECT name, (SELECT COUNT(*) FROM \" + "\" + "' || name || '\") as n " +
      "FROM sqlite_master WHERE type='table' ORDER BY name"
    );

    // Key table counts
    const counts: Record<string, number> = {};
    const KEY_TABLES = [
      "stock_data", "seasonality_patterns_v3", "seasonality_patterns",
      "global_indices_daily", "signals_history", "stock_delivery",
      "insider_trading", "corporate_announcements", "option_greeks_raw",
      "indices_data", "market_snapshot", "symbol_technicals",
      "window_stats", "mf_nav_history",
    ];

    for (const t of KEY_TABLES) {
      try {
        const r = qdb("SELECT COUNT(*) as n FROM " + t);
        counts[t] = r[0]?.n ?? 0;
      } catch { counts[t] = -1; }
    }

    // Pattern stats
    const patStats = qdb(
      "SELECT COUNT(*) as total, COUNT(DISTINCT symbol) as symbols, " +
      "COUNT(DISTINCT window_days) as windows, AVG(accuracy) as avg_acc, " +
      "MAX(score) as max_score FROM seasonality_patterns_v3"
    )[0] || {};

    // Agent status
    const AGENTS = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","kappa","alert"];
    const agentStatus: Record<string, any> = {};
    for (const a of AGENTS) {
      const r = loadReport(a);
      agentStatus[a] = r ? {
        ready: true,
        date: r.date || r.generated_at || null,
      } : { ready: false, date: null };
    }

    // Alerts count
    let alertCount = 0;
    try {
      const af = path.join(DA, "alerts.json");
      if (fs.existsSync(af)) {
        const alerts = JSON.parse(fs.readFileSync(af, "utf-8"));
        alertCount = alerts.filter((a: any) => a.active).length;
      }
    } catch {}

    // Watchlist count
    let watchlistCount = 0;
    try {
      const wf = path.join(DA, "micc_watchlist.json");
      if (fs.existsSync(wf)) {
        const w = JSON.parse(fs.readFileSync(wf, "utf-8"));
        watchlistCount = Array.isArray(w) ? w.length : Object.keys(w).length;
      }
    } catch {}

    return NextResponse.json({
      db_path:     DB,
      db_size:     getDBSize(),
      table_counts: counts,
      pattern_stats: {
        total:    patStats.total    || 0,
        symbols:  patStats.symbols  || 0,
        windows:  patStats.windows  || 0,
        avg_acc:  patStats.avg_acc  ? Math.round(patStats.avg_acc * 10) / 10 : null,
        max_score:patStats.max_score|| null,
      },
      agent_status:    agentStatus,
      active_alerts:   alertCount,
      watchlist_count: watchlistCount,
      generated_at:    new Date().toISOString(),
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
