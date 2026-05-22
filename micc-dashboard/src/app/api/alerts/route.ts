import { NextResponse } from "next/server";
import { readFileSync, writeFileSync, existsSync } from "fs";
import Database from "better-sqlite3";

const DB         = "D:/marketDB/db/market.db";
const ALERTS_FILE = "D:/MICC/alerts.json";

function loadAlerts(): Record<string, unknown>[] {
  try {
    if (!existsSync(ALERTS_FILE)) return [];
    const raw = JSON.parse(readFileSync(ALERTS_FILE, "utf-8"));
    if (Array.isArray(raw)) return raw;
    // Old format: {RSI_BELOW: {NIFTY50: 35}, PRICE_ABOVE: {RELIANCE: 1450}}
    const out: Record<string, unknown>[] = [];
    let id = 1;
    for (const [type, syms] of Object.entries(raw)) {
      if (typeof syms === "object" && syms !== null) {
        for (const [symbol, threshold] of Object.entries(syms as Record<string,unknown>)) {
          out.push({ id: String(id++), type, symbol, threshold,
            enabled: true, fired_count: 0, last_fired_date: null });
        }
      }
    }
    return out;
  } catch { return []; }
}

function saveAlerts(alerts: Record<string, unknown>[]) {
  writeFileSync(ALERTS_FILE, JSON.stringify(alerts, null, 2), "utf-8");
}

export function GET() {
  const alerts = loadAlerts();
  let fired_today: unknown[] = [];
  let db: ReturnType<typeof Database> | null = null;
  try {
    db = new Database(DB, { readonly: true, timeout: 5000 });
    // Check for alert_history table
    const tables = db.prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='alert_history'"
    ).all();
    if (tables.length > 0) {
      fired_today = db.prepare(
        "SELECT symbol, alert_type AS type, message, fired_at, value"
        " FROM alert_history"
        " WHERE DATE(fired_at)=DATE('now')"
        " ORDER BY fired_at DESC LIMIT 50"
      ).all();
    }
  } catch { /* no alert_history table yet */ }
  finally { try { db?.close(); } catch {} }

  return NextResponse.json({
    alerts,
    fired_today,
    fired_count:   (fired_today as unknown[]).length,
    total_alerts:  alerts.length,
  });
}

export async function POST(req: Request) {
  try {
    const body = await req.json() as { symbol: string; type: string; threshold?: number };
    const alerts = loadAlerts();
    const id = String(Date.now());
    alerts.push({
      id,
      symbol:         body.symbol.toUpperCase(),
      type:           body.type,
      threshold:      body.threshold ?? null,
      enabled:        true,
      fired_count:    0,
      last_fired_date: null,
      created_at:     new Date().toISOString(),
    });
    saveAlerts(alerts);
    return NextResponse.json({ ok: true, id });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 400 });
  }
}

export function DELETE(req: Request) {
  try {
    const url = new URL(req.url);
    const id  = url.searchParams.get("id");
    if (!id) return NextResponse.json({ ok: false, error: "id required" }, { status: 400 });
    const alerts  = loadAlerts();
    const updated = alerts.filter(a => (a as Record<string,unknown>).id !== id);
    saveAlerts(updated);
    return NextResponse.json({ ok: true, deleted: alerts.length - updated.length });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 400 });
  }
}