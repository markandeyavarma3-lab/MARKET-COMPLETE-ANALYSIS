import { NextResponse } from "next/server";
import { readFileSync } from "fs";

const REPORT = "D:/MICC/agents/fusion/last_report.json";

export function GET() {
  try {
    const raw = readFileSync(REPORT, "utf-8")
      .replace(/:\s*NaN\b/g, ": null")
      .replace(/:\s*Infinity\b/g, ": null");
    return NextResponse.json(JSON.parse(raw));
  } catch {
    return NextResponse.json({ picks: [], error: "Run agent_fusion.py first" });
  }
}