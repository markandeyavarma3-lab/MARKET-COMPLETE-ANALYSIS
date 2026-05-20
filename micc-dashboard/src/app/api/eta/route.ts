import { NextResponse } from "next/server";
import { readFileSync }  from "fs";
import { join }          from "path";

const REPORT = join("D:/MICC", "agents", "eta", "last_report.json");

function safe(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null")
          .replace(/:\s*Infinity\b/g, ": null")
          .replace(/:\s*-Infinity\b/g, ": null");
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
