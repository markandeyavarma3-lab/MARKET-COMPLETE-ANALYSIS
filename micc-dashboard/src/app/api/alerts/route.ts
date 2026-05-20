import { NextResponse } from "next/server";
import fs   from "fs";

const ALERTS_FILE = "D:/MICC/alerts.json";

function load(): any[] {
  try {
    if (!fs.existsSync(ALERTS_FILE)) return [];
    return JSON.parse(fs.readFileSync(ALERTS_FILE, "utf-8"));
  } catch { return []; }
}
function save(data: any[]) {
  fs.writeFileSync(ALERTS_FILE, JSON.stringify(data, null, 2));
}

export async function GET() {
  return NextResponse.json({ alerts: load() });
}

export async function POST(req: Request) {
  try {
    const body   = await req.json();
    const alerts = load();
    const id     = Math.random().toString(36).slice(2, 10);
    alerts.push({
      id, active: true,
      created_at: new Date().toISOString(),
      triggered_at: null, last_message: null,
      one_shot: body.one_shot ?? true,
      ...body,
    });
    save(alerts);
    return NextResponse.json({ ok: true, id });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}

export async function DELETE(req: Request) {
  try {
    const { id } = await req.json();
    save(load().filter((a: any) => a.id !== id));
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}

export async function PATCH(req: Request) {
  try {
    const { id, ...updates } = await req.json();
    save(load().map((a: any) => a.id === id ? { ...a, ...updates } : a));
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
