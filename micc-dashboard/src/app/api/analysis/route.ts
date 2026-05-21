import { NextResponse } from "next/server";
import { readFileSync } from "fs";
import { join } from "path";

const AGENTS = ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","fusion"];
const BASE = "D:/MICC/agents";

function safeRead(path: string): Record<string, unknown> {
  try {
    const raw = readFileSync(path, "utf-8")
      .replace(/:\s*NaN\b/g, ": null")
      .replace(/:\s*Infinity\b/g, ": null")
      .replace(/:\s*-Infinity\b/g, ": null");
    return JSON.parse(raw);
  } catch {
    return { error: "not found" };
  }
}

export function GET() {
  const out: Record<string, Record<string, unknown>> = {};
  for (const name of AGENTS) {
    out[name] = safeRead(join(BASE, name, "last_report.json"));
  }
  return NextResponse.json(out);
}
