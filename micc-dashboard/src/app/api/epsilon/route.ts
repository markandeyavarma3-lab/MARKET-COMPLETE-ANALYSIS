import { NextResponse } from 'next/server'
import fs               from 'fs'
import path             from 'path'

const DA = 'D:/MICC'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const p = path.join(DA, 'agents', 'epsilon', 'last_report.json')
    if (!fs.existsSync(p)) {
      return NextResponse.json({
        error: 'No epsilon report. Run: py D:\\MICC\\agent_epsilon.py --send'
      })
    }
    let raw = fs.readFileSync(p, 'utf-8')
    raw = raw.replace(/:\s*NaN([,\}\]])/g,      ': null$1')
             .replace(/:\s*Infinity([,\}\]])/g,  ': null$1')
             .replace(/:\s*-Infinity([,\}\]])/g, ': null$1')
    return NextResponse.json(JSON.parse(raw))
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
