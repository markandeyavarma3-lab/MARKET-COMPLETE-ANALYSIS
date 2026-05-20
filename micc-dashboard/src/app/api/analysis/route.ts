import { NextResponse } from "next/server";
import fs   from "fs";
import path from "path";

const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function loadReport(name: string): any | null {
  const p = path.join(DA, "agents", name, "last_report.json");
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(sanitize(fs.readFileSync(p, "utf-8")));
  } catch { return null; }
}

export async function GET() {
  const agents = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","kappa","alert"];
  const reports: Record<string, any> = {};

  for (const name of agents) {
    const r = loadReport(name);
    if (r) {
      // Extract just the key summary fields to keep response small
      reports[name] = {
        generated_at: r.generated_at || r.date || null,
        date:         r.date || null,
        // Agent-specific summary fields
        analysis:     r.analysis     || r.verdict     || r.llm_verdict || null,
        signals:      r.signals      || r.top_signals  || null,
        score:        r.score        || r.market_score || null,
        regime:       r.regime       || r.market_regime || null,
        // Count fields
        alerts_fired:    r.alerts_fired    || null,
        patterns_today:  r.patterns_today  ? r.patterns_today.length : null,
        insider_clusters: r.insider_cluster ? r.insider_cluster.length : null,
        big_trades:      r.big_insider_trades ? r.big_insider_trades.length : null,
      };
    }
  }

  // Signals history -- top signals from today
  return NextResponse.json({
    reports,
    agents_available: Object.keys(reports),
    agents_missing:   agents.filter(a => !reports[a]),
  });
}
