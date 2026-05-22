import { NextResponse } from "next/server";
import { readFileSync, existsSync } from "fs";

const REPORT = "D:/MICC/agents/eta/last_report.json";

export function GET() {
  try {
    if (!existsSync(REPORT)) {
      return NextResponse.json({
        screen1_results_season: [], screen2_dividends: [],
        screen3_insider_clusters: [], screen4_big_trades: [],
        screen5_post_results_reaction: [], screen6_upcoming_results: [],
        llm_analysis: null, error: "Run agent_eta.py first"
      });
    }
    const raw  = readFileSync(REPORT, "utf-8")
      .replace(/:\s*NaN\b/g, ":null")
      .replace(/:\s*Infinity\b/g, ":null");
    const data = JSON.parse(raw);
    // Normalize: support both old schema and new schema
    const normalized = {
      ...data,
      screen1_results_season:
        data.screen1_results_season ?? data.results_season ?? [],
      screen2_dividends:
        data.screen2_dividends ?? data.dividend_calendar ?? [],
      screen3_insider_clusters:
        data.screen3_insider_clusters ?? data.insider_cluster ?? [],
      screen4_big_trades:
        data.screen4_big_trades ?? data.big_insider_trades ?? [],
      screen5_post_results_reaction:
        data.screen5_post_results_reaction ?? data.post_results_reaction ?? [],
      screen6_upcoming_results:
        data.screen6_upcoming_results ?? data.upcoming_results ?? [],
      llm_analysis:
        data.llm_analysis ?? data.analysis ?? null,
    };
    return NextResponse.json(normalized);
  } catch (e) {
    return NextResponse.json({ error: String(e), screen3_insider_clusters: [] });
  }
}