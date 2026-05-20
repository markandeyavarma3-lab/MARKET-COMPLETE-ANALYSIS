import { NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs';

const DA = 'D:/MICC';

export async function GET() {
  try {
    const p = path.join(DA, 'agents', 'backtest', 'last_report.json');
    if (!fs.existsSync(p)) {
      return NextResponse.json(
        { error: 'No backtest report. Run: py agent_backtest.py' },
        { status: 404 }
      );
    }
    return NextResponse.json(JSON.parse(fs.readFileSync(p, 'utf-8')));
  } catch (e: unknown) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
