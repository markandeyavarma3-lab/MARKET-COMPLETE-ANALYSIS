import { NextResponse } from "next/server";
import fs   from "fs";
import path from "path";

const REPORT = "D:/MICC/agents/iota/last_report.json";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

export async function GET() {
  try {
    if (!fs.existsSync(REPORT)) {
      return NextResponse.json(
        { error: "No Iota report. Run: py D:/MICC/agent_iota.py" },
        { status: 404 }
      );
    }
    const raw  = fs.readFileSync(REPORT, "utf-8");
    const data = JSON.parse(sanitize(raw));
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
