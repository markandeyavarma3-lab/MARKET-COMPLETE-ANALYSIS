import { NextResponse } from "next/server";
import fs   from "fs";
import path from "path";

const REPORT = "D:/MICC/agents/alpha/last_report.json";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

export async function GET() {
  try {
    if (!fs.existsSync(REPORT)) {
      return NextResponse.json({ error: "Run: py D:/MICC/agent_alpha.py" }, { status: 404 });
    }
    return NextResponse.json(JSON.parse(sanitize(fs.readFileSync(REPORT, "utf-8"))));
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
