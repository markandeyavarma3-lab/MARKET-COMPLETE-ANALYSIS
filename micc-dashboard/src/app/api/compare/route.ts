import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import path             from "path";
import fs               from "fs";

const DA     = "D:/MICC";
const KAPPA  = path.join(DA, "agents", "kappa");
const PY_CMD = "py";

function sanitize(s: string): string {
  return s.replace(/:\s*NaN\b/g, ": null")
          .replace(/:\s*Infinity\b/g, ": null")
          .replace(/:\s*-Infinity\b/g, ": null");
}

function loadCached(symbol: string) {
  const p = path.join(KAPPA, `${symbol.toUpperCase()}_report.json`);
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(sanitize(fs.readFileSync(p, "utf-8")));
  } catch { return null; }
}

function runKappa(symbol: string) {
  const res = spawnSync(PY_CMD, ["agent_kappa.py", symbol], {
    cwd: DA, encoding: "utf-8", timeout: 120000,
  });
  if (res.status !== 0) {
    throw new Error(res.stderr?.slice(0, 400) || "kappa failed");
  }
}

export async function GET(req: Request) {
  const url     = new URL(req.url);
  const symbols = (url.searchParams.get("symbols") || "").toUpperCase().split(",").map(s => s.trim()).filter(Boolean);
  const force   = url.searchParams.get("force") === "1";

  if (symbols.length < 1)
    return NextResponse.json({ error: "Pass ?symbols=A,B,C (1–5 symbols)" }, { status: 400 });
  if (symbols.length > 5)
    return NextResponse.json({ error: "Max 5 symbols" }, { status: 400 });

  const results: Record<string, any> = {};
  const errors:  Record<string, string> = {};

  for (const sym of symbols) {
    let cached = force ? null : loadCached(sym);
    if (!cached) {
      try { runKappa(sym); cached = loadCached(sym); }
      catch (e: any) { errors[sym] = e.message; continue; }
    }
    if (cached) results[sym] = cached;
    else errors[sym] = "Report not generated";
  }

  return NextResponse.json({ symbols, results, errors });
}
