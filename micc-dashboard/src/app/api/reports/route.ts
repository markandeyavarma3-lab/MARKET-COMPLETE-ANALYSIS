import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const DA = 'D:/MICC'

function sanitiseJson(raw: string): string {
  // Replace ALL bare NaN / Infinity occurrences with null
  // These appear in Python JSON output when numpy produces NaN values.
  // We use word boundaries to avoid touching strings that contain "NaN".
  return raw
    .replace(/\bNaN\b/g, 'null')
    .replace(/\bInfinity\b/g, 'null')
    .replace(/-Infinity\b/g, 'null')
}

function readAgent(name: string): any {
  try {
    const p = path.join(DA, 'agents', name, 'last_report.json')
    if (!fs.existsSync(p)) {
      return { _error: `agents/${name}/last_report.json not found. Run: py agent_${name}.py` }
    }
    const raw = fs.readFileSync(p, 'utf-8')
    return JSON.parse(sanitiseJson(raw))
  } catch (e: any) {
    return { _error: `${name}: ${e.message}` }
  }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  return NextResponse.json({
    alpha: readAgent('alpha'),
    beta:  readAgent('beta'),
    gamma: readAgent('gamma'),
    delta: readAgent('delta'),
    ts:    Date.now(),
  })
}
