"""
build_phase19_fixed.py  --  Run from D:\MICC
Fixed: backtick template literal no longer embedded raw in Python strings.
All TypeScript files written via Path.write_text() with pure string concat.

Builds:
  [1] agent_alert.py           -- Alert agent (price/RSI/volume/pattern alerts)
  [2] /api/alerts/route.ts     -- CRUD for alerts.json
  [3] /alerts/page.tsx         -- Alert management UI
  [4] /api/macro-global/route.ts -- Global rates + FX + commodities API
  [5] NavBar + telegram patches

Run: py D:\MICC\build_phase19_fixed.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")


# =============================================================================
# [1]  agent_alert.py
# =============================================================================
print("\n[1/5] Writing D:\\MICC\\agent_alert.py ...")

ALERT_AGENT = '''\
# -*- coding: utf-8 -*-
"""
MICC Agent Alert -- Price + Pattern + Watchlist Alerts
=======================================================
Alert types:
  PRICE_ABOVE    symbol price > target
  PRICE_BELOW    symbol price < target
  PCT_MOVE       price moved > X% in last N days
  VOLUME_SURGE   volume > X * 20d average
  PATTERN_HIT    seasonal pattern active today (accuracy >= target)
  RSI_ABOVE      RSI(14) > threshold (overbought)
  RSI_BELOW      RSI(14) < threshold (oversold)

Alerts stored in: D:/MICC/alerts.json

Run:
  py D:/MICC/agent_alert.py          -- check all + Telegram if fired
  py D:/MICC/agent_alert.py --send   -- always send summary
  py D:/MICC/agent_alert.py --list   -- list all alerts
  py D:/MICC/agent_alert.py --add PRICE_ABOVE RELIANCE 2800 "note"
"""

import argparse, json, sqlite3, sys, uuid
from datetime import datetime
from pathlib import Path

from micc_data import send_telegram_chunks, now_ist

DB          = Path(r"D:\\marketDB\\db\\market.db")
DA          = Path(r"D:\\MICC")
ALERTS_FILE = DA / "alerts.json"
OUTPUT_DIR  = DA / "agents" / "alert"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY      = datetime.today().strftime("%Y-%m-%d")
TODAY_MMDD = datetime.today().strftime("%m-%d")


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] [{tag}]  {msg}", flush=True)


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #

def _conn():
    return sqlite3.connect(DB, timeout=10)

def get_latest_price(symbol: str):
    try:
        c = _conn()
        r = c.execute(
            "SELECT close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        c.close()
        return float(r[0]) if r else None
    except Exception:
        return None

def get_latest_volume(symbol: str):
    try:
        c = _conn()
        rows = c.execute(
            "SELECT volume FROM stock_data WHERE symbol=? AND volume IS NOT NULL ORDER BY date DESC LIMIT 21",
            (symbol.upper(),)
        ).fetchall()
        c.close()
        if not rows:
            return None, None
        vols = [float(r[0]) for r in rows]
        return vols[0], sum(vols[1:]) / max(len(vols) - 1, 1)
    except Exception:
        return None, None

def get_pct_move(symbol: str, days: int):
    try:
        c = _conn()
        rows = c.execute(
            "SELECT close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT ?",
            (symbol.upper(), days + 1)
        ).fetchall()
        c.close()
        if len(rows) < 2:
            return None
        return (float(rows[0][0]) / float(rows[-1][0]) - 1) * 100
    except Exception:
        return None

def get_rsi(symbol: str):
    try:
        c = _conn()
        r = c.execute(
            "SELECT rsi_14 FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        c.close()
        return float(r[0]) if r and r[0] is not None else None
    except Exception:
        return None

def get_todays_patterns(min_accuracy=68.0, min_score=1.5):
    try:
        c = _conn()
        tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        tbl = "seasonality_patterns_v3" if "seasonality_patterns_v3" in tables else "seasonality_patterns"
        rows = c.execute(
            "SELECT symbol, window_days, direction, accuracy, mean_ret, score "
            "FROM " + tbl + " WHERE anchor_mm_dd=? AND accuracy>=? AND score>=? "
            "ORDER BY score DESC LIMIT 20",
            (TODAY_MMDD, min_accuracy, min_score)
        ).fetchall()
        c.close()
        return [{"symbol": r[0], "window": r[1], "direction": r[2],
                 "accuracy": r[3], "mean_ret": r[4], "score": r[5]} for r in rows]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Alert file I/O
# --------------------------------------------------------------------------- #

def load_alerts():
    if not ALERTS_FILE.exists():
        return []
    try:
        return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_alerts(alerts):
    ALERTS_FILE.write_text(json.dumps(alerts, indent=2, default=str), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Check one alert
# --------------------------------------------------------------------------- #

def check_alert(alert: dict):
    sym    = alert.get("symbol", "").upper()
    typ    = alert.get("type", "")
    target = float(alert.get("target", 0))
    note   = alert.get("note", "")
    days   = int(alert.get("days", 5))
    suffix = ("  [" + note + "]") if note else ""

    if typ == "PRICE_ABOVE":
        price = get_latest_price(sym)
        if price and price > target:
            return True, f"PRICE ABOVE: {sym} @ {price:.2f} > {target:.2f}{suffix}"

    elif typ == "PRICE_BELOW":
        price = get_latest_price(sym)
        if price and price < target:
            return True, f"PRICE BELOW: {sym} @ {price:.2f} < {target:.2f}{suffix}"

    elif typ == "PCT_MOVE":
        move = get_pct_move(sym, days)
        if move is not None and abs(move) >= target:
            return True, f"PCT MOVE: {sym} {move:+.1f}% in {days}d (threshold {target:.1f}%){suffix}"

    elif typ == "VOLUME_SURGE":
        vol, avg = get_latest_volume(sym)
        if vol and avg and avg > 0:
            ratio = vol / avg
            if ratio >= target:
                return True, f"VOL SURGE: {sym} {ratio:.1f}x 20d avg (threshold {target:.1f}x){suffix}"

    elif typ == "RSI_ABOVE":
        rsi = get_rsi(sym)
        if rsi is not None and rsi > target:
            return True, f"RSI OVERBOUGHT: {sym} RSI={rsi:.1f} > {target:.0f}{suffix}"

    elif typ == "RSI_BELOW":
        rsi = get_rsi(sym)
        if rsi is not None and rsi < target:
            return True, f"RSI OVERSOLD: {sym} RSI={rsi:.1f} < {target:.0f}{suffix}"

    elif typ == "PATTERN_HIT":
        patterns = get_todays_patterns(min_accuracy=target, min_score=1.0)
        hits = [p for p in patterns if p["symbol"].upper() == sym]
        if hits:
            p = hits[0]
            return True, (f"PATTERN: {sym} {p['direction']} {p['window']}d  "
                          f"acc={p['accuracy']:.0f}%  mean={p['mean_ret']:+.2f}%{suffix}")

    return False, ""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def run_alerts(send: bool = False):
    print("=" * 55)
    print("  AGENT ALERT -- Price + Pattern + Watchlist")
    print("=" * 55)

    alerts = load_alerts()
    log(f"Loaded {len(alerts)} alerts")

    fired = []
    for alert in alerts:
        if not alert.get("active", True):
            continue
        triggered, msg = check_alert(alert)
        if triggered:
            alert["triggered_at"] = now_ist()
            alert["last_message"] = msg
            if alert.get("one_shot", True):
                alert["active"] = False
            fired.append((alert, msg))
            log(f"FIRED: {msg}", "OK")

    save_alerts(alerts)

    patterns = get_todays_patterns(min_accuracy=70.0, min_score=2.0)
    log(f"Patterns today ({TODAY_MMDD}): {len(patterns)}")

    report = {
        "date": TODAY, "generated_at": now_ist(),
        "alerts_checked": len(alerts), "alerts_fired": len(fired),
        "fired": [{"alert": a, "message": m} for a, m in fired],
        "patterns_today": patterns,
    }
    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log(f"Saved: {out}")

    print(f"\\n  Alerts checked: {len(alerts)}")
    print(f"  Alerts fired:   {len(fired)}")
    print(f"  Patterns today: {len(patterns)}")
    print("=" * 55)

    if send and (fired or patterns):
        lines = [f"*MICC Alerts -- {TODAY}*", ""]
        if fired:
            lines.append("*TRIGGERED:*")
            for _, msg in fired:
                lines.append(f"  {msg}")
            lines.append("")
        if patterns:
            lines.append(f"*PATTERNS TODAY ({TODAY_MMDD}):*")
            for p in patterns[:8]:
                ico = "UP" if p["direction"] == "UP" else "DN"
                lines.append(
                    f"  {ico} `{p['symbol']:<14}` {p['window']}d  "
                    f"{p['accuracy']:.0f}%  {p['mean_ret']:+.2f}%  s={p['score']:.1f}"
                )
        ok = send_telegram_chunks("\\n".join(lines))
        log(f"Telegram: {'OK' if ok else 'FAILED'}")

    return report


def add_alert(type_: str, symbol: str, target: float,
              note: str = "", days: int = 5, one_shot: bool = True):
    alerts = load_alerts()
    alerts.append({
        "id": str(uuid.uuid4())[:8], "type": type_.upper(),
        "symbol": symbol.upper(), "target": target,
        "note": note, "days": days, "one_shot": one_shot,
        "active": True, "created_at": now_ist(),
        "triggered_at": None, "last_message": None,
    })
    save_alerts(alerts)
    log(f"Added: {type_.upper()} {symbol.upper()} target={target} note={note!r}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--add",  nargs="+", help="TYPE SYMBOL TARGET [NOTE]")
    args = ap.parse_args()

    if args.list:
        for a in load_alerts():
            st = "ACTIVE" if a.get("active") else "FIRED"
            print(f"  [{st}] {a['type']:<15} {a['symbol']:<14} target={a['target']}  {a.get('note','')}")
        sys.exit(0)

    if args.add:
        if len(args.add) < 3:
            print("Usage: --add TYPE SYMBOL TARGET [NOTE]"); sys.exit(1)
        add_alert(args.add[0], args.add[1], float(args.add[2]),
                  note=" ".join(args.add[3:]) if len(args.add) > 3 else "")
        sys.exit(0)

    run_alerts(send=args.send)
'''
write(MICC / "agent_alert.py", ALERT_AGENT, "agent_alert.py")


# =============================================================================
# [2]  /api/alerts/route.ts
# =============================================================================
print("\n[2/5] Writing /api/alerts/route.ts ...")

ALERTS_API = """\
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
"""
write(SRC / "api" / "alerts" / "route.ts", ALERTS_API, "/api/alerts/route.ts")


# =============================================================================
# [3]  /alerts/page.tsx
# =============================================================================
print("\n[3/5] Writing /alerts/page.tsx ...")

ALERTS_PAGE = """\
"use client";

import { useState, useEffect, useCallback } from "react";

interface Alert {
  id: string; type: string; symbol: string; target: number;
  note: string; days: number; one_shot: boolean; active: boolean;
  created_at: string; triggered_at: string|null; last_message: string|null;
}
interface SR { symbol: string; name: string; type: string; }

const ALERT_TYPES = [
  { v:"PRICE_ABOVE",   l:"Price Above",    d:"Price crosses above target" },
  { v:"PRICE_BELOW",   l:"Price Below",    d:"Price drops below target" },
  { v:"PCT_MOVE",      l:"% Move (N days)",d:"Price moves > target% in N days" },
  { v:"VOLUME_SURGE",  l:"Volume Surge",   d:"Volume > target x 20d average" },
  { v:"RSI_ABOVE",     l:"RSI Overbought", d:"RSI(14) > target" },
  { v:"RSI_BELOW",     l:"RSI Oversold",   d:"RSI(14) < target" },
  { v:"PATTERN_HIT",   l:"Pattern Hit",    d:"Seasonal pattern active today (acc >= target%)" },
];
const TYPE_CLR: Record<string,string> = {
  PRICE_ABOVE:"#22c55e", PRICE_BELOW:"#ef4444", PCT_MOVE:"#fbbf24",
  VOLUME_SURGE:"#a78bfa", RSI_ABOVE:"#f97316", RSI_BELOW:"#60a5fa", PATTERN_HIT:"#34d399",
};

const inp = (extra?: object) => ({
  padding:"8px 12px", background:"#0f172a", border:"1px solid #334155",
  borderRadius:7, color:"#f8fafc", fontSize:13, outline:"none",
  width:"100%", boxSizing:"border-box" as const, ...extra,
});

export default function AlertsPage() {
  const [alerts,  setAlerts]  = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [saving,  setSaving]  = useState(false);
  const [form, setForm] = useState({ type:"PRICE_ABOVE", symbol:"", target:"", note:"", days:5, one_shot:true });
  const [searchQ, setSearchQ] = useState("");
  const [searchR, setSearchR] = useState<SR[]>([]);

  const reload = useCallback(async () => {
    setLoading(true);
    try { const r = await fetch("/api/alerts"); const d = await r.json(); setAlerts(d.alerts||[]); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { reload(); }, []);

  useEffect(() => {
    if (!searchQ.trim()) { setSearchR([]); return; }
    const t = setTimeout(async () => {
      try { const r = await fetch("/api/search?q="+encodeURIComponent(searchQ)+"&limit=8"); const d = await r.json(); setSearchR(d.results||[]); } catch {}
    }, 200);
    return () => clearTimeout(t);
  }, [searchQ]);

  const addAlert = async () => {
    if (!form.symbol || !form.target) return;
    setSaving(true);
    try {
      await fetch("/api/alerts", { method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ type:form.type, symbol:form.symbol.toUpperCase(),
          target:parseFloat(form.target), note:form.note, days:form.days, one_shot:form.one_shot }) });
      setShowAdd(false);
      setForm({ type:"PRICE_ABOVE", symbol:"", target:"", note:"", days:5, one_shot:true });
      setSearchQ(""); setSearchR([]); reload();
    } catch {} finally { setSaving(false); }
  };

  const del = async (id: string) => {
    await fetch("/api/alerts", { method:"DELETE", headers:{"Content-Type":"application/json"}, body:JSON.stringify({id}) });
    reload();
  };

  const toggle = async (id: string, active: boolean) => {
    await fetch("/api/alerts", { method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({id,active}) });
    reload();
  };

  const active  = alerts.filter(a => a.active);
  const fired   = alerts.filter(a => !a.active && a.triggered_at);
  const paused  = alerts.filter(a => !a.active && !a.triggered_at);

  return (
    <div style={{ minHeight:"100vh", background:"#0f172a", color:"#e2e8f0", fontFamily:"system-ui,sans-serif" }}>

      {/* Header */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", flexWrap:"wrap", gap:16 }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"#f8fafc" }}>Alerts</h1>
          <p style={{ margin:"4px 0 0", fontSize:12, color:"#64748b" }}>
            Price, RSI, volume, pattern triggers sent to Telegram
          </p>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:10, alignItems:"center" }}>
          {[{l:"Active",v:active.length,c:"#22c55e"},{l:"Fired",v:fired.length,c:"#fbbf24"},{l:"Paused",v:paused.length,c:"#64748b"}].map(s=>(
            <div key={s.l} style={{ textAlign:"center", padding:"7px 14px",
              background:"#1e293b", borderRadius:8, border:`1px solid ${s.c}33` }}>
              <div style={{ fontSize:18, fontWeight:800, color:s.c }}>{s.v}</div>
              <div style={{ fontSize:10, color:"#64748b" }}>{s.l}</div>
            </div>
          ))}
          <button onClick={()=>setShowAdd(o=>!o)} style={{
            padding:"9px 18px", background:"#3b82f6", color:"#fff",
            border:"none", borderRadius:8, cursor:"pointer", fontSize:13, fontWeight:700,
          }}>+ Add Alert</button>
        </div>
      </div>

      <div style={{ padding:"20px 28px" }}>

        {/* Add form */}
        {showAdd && (
          <div style={{ background:"#1e293b", border:"1px solid #3b82f6", borderRadius:12, padding:"20px", marginBottom:20 }}>
            <h3 style={{ margin:"0 0 16px", fontSize:14, fontWeight:700, color:"#60a5fa" }}>New Alert</h3>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12 }}>

              <div>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:4 }}>TYPE</div>
                <select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))} style={inp()}>
                  {ALERT_TYPES.map(t=><option key={t.v} value={t.v}>{t.l}</option>)}
                </select>
                <div style={{ fontSize:10, color:"#475569", marginTop:4 }}>
                  {ALERT_TYPES.find(t=>t.v===form.type)?.d}
                </div>
              </div>

              <div style={{ position:"relative" }}>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:4 }}>SYMBOL</div>
                <input value={searchQ||form.symbol}
                  onChange={e=>{setSearchQ(e.target.value);setForm(f=>({...f,symbol:e.target.value.toUpperCase()}));}}
                  placeholder="e.g. RELIANCE or HDFC Bank" style={inp()} />
                {searchR.length>0 && searchQ && (
                  <div style={{ position:"absolute", top:"100%", left:0, right:0, zIndex:100,
                    background:"#1e293b", border:"1px solid #334155", borderRadius:7,
                    boxShadow:"0 8px 24px rgba(0,0,0,0.5)", overflow:"hidden" }}>
                    {searchR.map(r=>(
                      <div key={r.symbol} onMouseDown={()=>{setForm(f=>({...f,symbol:r.symbol}));setSearchQ("");setSearchR([]);}}
                        style={{ padding:"8px 12px", cursor:"pointer", fontSize:12,
                          borderBottom:"1px solid #0f172a", display:"flex", gap:10 }}>
                        <span style={{ fontFamily:"monospace", fontWeight:700, color:"#60a5fa" }}>{r.symbol}</span>
                        <span style={{ color:"#64748b" }}>{r.name!==r.symbol?r.name:""}</span>
                        <span style={{ marginLeft:"auto", fontSize:10, color:"#334155" }}>{r.type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:4 }}>
                  TARGET ({form.type==="VOLUME_SURGE"?"x avg":form.type==="PCT_MOVE"?"%":form.type.startsWith("RSI")?"RSI value":"price"})
                </div>
                <input type="number" value={form.target} onChange={e=>setForm(f=>({...f,target:e.target.value}))}
                  placeholder={form.type==="VOLUME_SURGE"?"e.g. 3":form.type==="PCT_MOVE"?"e.g. 5":"e.g. 2800"} style={inp()} />
              </div>

              {form.type==="PCT_MOVE" && (
                <div>
                  <div style={{ fontSize:10, color:"#64748b", marginBottom:4 }}>LOOKBACK DAYS</div>
                  <input type="number" value={form.days} onChange={e=>setForm(f=>({...f,days:parseInt(e.target.value)||5}))} style={inp()} />
                </div>
              )}

              <div style={{ gridColumn:"1/-1" }}>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:4 }}>NOTE (optional)</div>
                <input value={form.note} onChange={e=>setForm(f=>({...f,note:e.target.value}))}
                  placeholder="e.g. Resistance level, earnings play" style={inp()} />
              </div>

              <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                <input type="checkbox" id="os" checked={form.one_shot} onChange={e=>setForm(f=>({...f,one_shot:e.target.checked}))} />
                <label htmlFor="os" style={{ fontSize:12, color:"#94a3b8", cursor:"pointer" }}>
                  One-shot (deactivate after firing)
                </label>
              </div>
            </div>

            <div style={{ display:"flex", gap:8, marginTop:14 }}>
              <button onClick={addAlert} disabled={saving||!form.symbol||!form.target}
                style={{ padding:"8px 20px", background:"#22c55e", color:"#fff",
                  border:"none", borderRadius:7, cursor:"pointer", fontSize:13, fontWeight:700 }}>
                {saving?"Saving...":"Add Alert"}
              </button>
              <button onClick={()=>setShowAdd(false)}
                style={{ padding:"8px 16px", background:"#334155", color:"#94a3b8",
                  border:"none", borderRadius:7, cursor:"pointer", fontSize:13 }}>Cancel</button>
            </div>
          </div>
        )}

        {/* Quick-add examples */}
        <div style={{ marginBottom:20, padding:"12px 16px", background:"#1e293b", borderRadius:10 }}>
          <div style={{ fontSize:10, color:"#64748b", marginBottom:8, textTransform:"uppercase", letterSpacing:0.5 }}>
            Quick-add examples
          </div>
          <div style={{ display:"flex", gap:7, flexWrap:"wrap" }}>
            {[
              {type:"RSI_BELOW",   symbol:"NIFTY50",  target:35,  note:"Oversold"},
              {type:"PRICE_ABOVE", symbol:"RELIANCE",  target:1400,note:"Breakout"},
              {type:"VOLUME_SURGE",symbol:"HDFCBANK",  target:3,   note:"Big vol"},
              {type:"PCT_MOVE",    symbol:"SBIN",      target:5,   note:"5% move",days:3},
              {type:"PATTERN_HIT", symbol:"INFY",      target:70,  note:"Pattern 70%+"},
              {type:"RSI_ABOVE",   symbol:"Bitcoin",   target:80,  note:"BTC overbought"},
            ].map((ex,i)=>(
              <button key={i} onClick={async ()=>{
                await fetch("/api/alerts",{method:"POST",headers:{"Content-Type":"application/json"},
                  body:JSON.stringify({...ex,active:true,one_shot:true,days:ex.days||5})});
                reload();
              }} style={{ fontSize:11, padding:"4px 12px", background:"#0f172a",
                border:"1px solid #334155", borderRadius:6, cursor:"pointer", color:"#94a3b8" }}>
                {ex.type.replace(/_/g," ")} {ex.symbol} {ex.target}{ex.note?" ("+ex.note+")":""}
              </button>
            ))}
          </div>
        </div>

        {/* Alert groups */}
        {loading ? (
          <div style={{ color:"#64748b", fontSize:13 }}>Loading...</div>
        ) : alerts.length===0 ? (
          <div style={{ textAlign:"center", padding:"60px 0", color:"#475569" }}>
            <div style={{ fontSize:40, marginBottom:12 }}>No alerts yet</div>
            <p style={{ fontSize:13 }}>Click Add Alert or use quick-add examples above.</p>
            <code style={{ fontSize:11, color:"#475569" }}>
              py D:\\MICC\\agent_alert.py --send
            </code>
          </div>
        ) : (
          [{label:"Active Alerts",  items:active,  accent:"#22c55e"},
           {label:"Fired Alerts",   items:fired,   accent:"#fbbf24"},
           {label:"Paused Alerts",  items:paused,  accent:"#64748b"},
          ].filter(g=>g.items.length>0).map(g=>(
            <div key={g.label} style={{ marginBottom:22 }}>
              <h3 style={{ fontSize:11, fontWeight:700, color:g.accent,
                letterSpacing:1, marginBottom:10, textTransform:"uppercase" }}>
                {g.label} ({g.items.length})
              </h3>
              {g.items.map(a=>(
                <div key={a.id} style={{
                  background:"#1e293b",
                  border:`1px solid ${a.active?(TYPE_CLR[a.type]||"#334155")+"55":"#334155"}`,
                  borderRadius:10, padding:"11px 16px", marginBottom:7,
                  display:"flex", alignItems:"center", gap:12, flexWrap:"wrap",
                }}>
                  <span style={{
                    fontSize:10, fontWeight:700, padding:"2px 8px", borderRadius:4,
                    background:(TYPE_CLR[a.type]||"#94a3b8")+"22",
                    color:TYPE_CLR[a.type]||"#94a3b8",
                  }}>{a.type.replace(/_/g," ")}</span>
                  <span style={{ fontFamily:"monospace", fontWeight:800, color:"#60a5fa", fontSize:13 }}>{a.symbol}</span>
                  <span style={{ fontSize:13, color:"#e2e8f0", fontWeight:700 }}>target: {a.target}</span>
                  {a.note && <span style={{ fontSize:11, color:"#64748b" }}>{a.note}</span>}
                  {a.triggered_at && <span style={{ fontSize:10, color:"#fbbf24" }}>Fired: {a.triggered_at}</span>}
                  {a.last_message && <span style={{ fontSize:11, color:"#94a3b8", flex:1 }}>{a.last_message}</span>}
                  <div style={{ display:"flex", gap:6, marginLeft:"auto" }}>
                    <button onClick={()=>toggle(a.id,!a.active)} style={{
                      padding:"4px 10px", fontSize:11,
                      background:a.active?"#334155":"#1e3a5f",
                      color:a.active?"#64748b":"#60a5fa",
                      border:"1px solid #334155", borderRadius:5, cursor:"pointer",
                    }}>{a.active?"Pause":"Resume"}</button>
                    <button onClick={()=>del(a.id)} style={{
                      padding:"4px 10px", fontSize:11,
                      background:"#2d1515", color:"#ef4444",
                      border:"1px solid #ef444433", borderRadius:5, cursor:"pointer",
                    }}>Delete</button>
                  </div>
                </div>
              ))}
            </div>
          ))
        )}

        <div style={{ marginTop:20, padding:"13px 16px", background:"#1e293b", borderRadius:10 }}>
          <div style={{ fontSize:11, color:"#94a3b8", marginBottom:6, fontWeight:700 }}>Run alerts manually</div>
          <code style={{ fontSize:12, color:"#60a5fa", display:"block", marginBottom:4 }}>
            py D:\\MICC\\agent_alert.py --send
          </code>
          <code style={{ fontSize:12, color:"#60a5fa", display:"block", marginBottom:4 }}>
            py D:\\MICC\\agent_alert.py --add PRICE_ABOVE RELIANCE 2800 "note"
          </code>
          <div style={{ fontSize:11, color:"#475569", marginTop:6 }}>
            Runs automatically in daily pipeline (already patched in run_pipeline.py)
          </div>
        </div>
      </div>
    </div>
  );
}
"""
write(SRC / "alerts" / "page.tsx", ALERTS_PAGE, "/alerts/page.tsx")


# =============================================================================
# [4]  /api/macro-global/route.ts  -- no backtick template issue
#      We write TypeScript that uses function-based DB calls, not embedded templates
# =============================================================================
print("\n[4/5] Writing /api/macro-global/route.ts ...")

# Build the TypeScript without backtick+sql concat by using the spawnSync
# pattern where the SQL is passed as argv, not embedded in a template literal
MACRO_GLOBAL = """\
import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import fs               from "fs";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

// Safe DB query: passes SQL and params as argv, avoids template literal backtick issue
function qdb(sqlB64: string, params: any[] = []): any[] {
  const pyScript = [
    "import sqlite3, json, sys, base64",
    "conn = sqlite3.connect(r'" + DB + "', timeout=10)",
    "conn.row_factory = sqlite3.Row",
    "sql = base64.b64decode(sys.argv[1]).decode()",
    "params = json.loads(sys.argv[2])",
    "rows = conn.execute(sql, params).fetchall()",
    "print(json.dumps([dict(r) for r in rows], default=str))",
    "conn.close()",
  ].join("\\n");
  const r = spawnSync(PY, ["-c", pyScript, sqlB64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

function b64(s: string): string {
  return Buffer.from(s).toString("base64");
}

export async function GET() {
  try {
    const RATE_SYMS  = ["US10Y", "US2Y", "US30Y"];
    const FX_SYMS    = ["DXY", "USDINR", "EURUSD", "USDJPY", "GBPUSD"];
    const CMDTY_SYMS = ["Gold", "CrudeWTI", "Silver", "NatGas", "Copper"];
    const VIX_SYMS   = ["SP500VIX", "INDIAVIX"];
    const CRYPTO_SYMS = ["Bitcoin", "Ethereum"];
    const EQ_SYMS    = ["SPX", "NDX", "NIFTY50", "Nikkei225", "DAX"];
    const allSyms    = [...RATE_SYMS, ...FX_SYMS, ...CMDTY_SYMS, ...VIX_SYMS, ...CRYPTO_SYMS, ...EQ_SYMS];

    const placeholders = allSyms.map(() => "?").join(",");
    const latestSQL = b64(
      "SELECT g.symbol, g.date, g.close, g.pct_change " +
      "FROM global_indices_daily g " +
      "WHERE g.date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol = g.symbol) " +
      "AND g.symbol IN (" + placeholders + ")"
    );
    const latest = qdb(latestSQL, allSyms);

    // 60-day history for rates (yield curve)
    const histSQL = b64(
      "SELECT symbol, date, close FROM global_indices_daily " +
      "WHERE symbol IN ('US2Y','US10Y','US30Y') AND date >= date('now','-90 days') " +
      "ORDER BY symbol, date"
    );
    const ratesHist = qdb(histSQL, []);

    const bySymbol: Record<string, any> = {};
    for (const r of latest) bySymbol[r.symbol] = r;

    const rates     = RATE_SYMS.map(s  => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const fx        = FX_SYMS.map(s    => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const cmdty     = CMDTY_SYMS.map(s => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const vix       = VIX_SYMS.map(s   => ({ symbol:s, ...(bySymbol[s]||{}) }));
    const crypto    = CRYPTO_SYMS.map(s=> ({ symbol:s, ...(bySymbol[s]||{}) }));
    const equities  = EQ_SYMS.map(s    => ({ symbol:s, ...(bySymbol[s]||{}) }));

    const us10y = bySymbol["US10Y"]?.close ?? null;
    const us2y  = bySymbol["US2Y"]?.close  ?? null;
    const spread = (us10y && us2y) ? Math.round((us10y - us2y) * 100) / 100 : null;

    const ratesHistory: Record<string, any[]> = {};
    for (const r of ratesHist) {
      if (!ratesHistory[r.symbol]) ratesHistory[r.symbol] = [];
      ratesHistory[r.symbol].push({ date: r.date, close: r.close });
    }

    return NextResponse.json({
      rates, fx, commodities: cmdty, volatility: vix, crypto, equities,
      yield_spread: spread,
      rates_history: ratesHistory,
      as_of: latest[0]?.date || null,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
"""
write(SRC / "api" / "macro-global" / "route.ts", MACRO_GLOBAL, "/api/macro-global/route.ts")


# =============================================================================
# [5]  NavBar + Telegram patches
# =============================================================================
print("\n[5/5] Patching NavBar + telegram_bot ...")

# NavBar
navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")
    changed = False
    for href, label in [("/alerts", "ALERTS"), ("/global", "GLOBAL")]:
        if href not in src:
            for marker in ["'/eta'", '"/eta"', "'/compare'", '"/compare"', "'/overview'", '"/overview"']:
                if marker in src:
                    idx = src.rfind(marker)
                    le  = src.find("\n", idx)
                    src = src[:le] + f"\n  {{ href: '{href}', label: '{label}' }}," + src[le:]
                    changed = True
                    print(f"  [OK] NavBar: added {label}")
                    break
    if changed:
        navbar_path.write_text(src, encoding="utf-8")
else:
    print("  [SKIP] NavBar.tsx not found")

# Telegram
BOT = MICC / "telegram_bot.py"
if BOT.exists():
    src = BOT.read_text(encoding="utf-8")
    if "cmd_alerts" not in src:
        CMD = '''

async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active alerts. Usage: /alerts"""
    import json, pathlib
    try:
        p = pathlib.Path(r"D:\\MICC\\alerts.json")
        alerts = json.loads(p.read_text()) if p.exists() else []
        active = [a for a in alerts if a.get("active")]
        fired  = [a for a in alerts if not a.get("active") and a.get("triggered_at")]
        lines  = ["*MICC Alerts*", ""]
        if active:
            lines.append(f"*Active ({len(active)}):*")
            for a in active[:10]:
                lines.append(
                    f"  `{a.get('type','')[:12]:<12}` `{a.get('symbol',''):<12}` "
                    f"target={a.get('target','')}  {a.get('note','')}"
                )
            lines.append("")
        if fired:
            lines.append(f"*Fired ({len(fired)}):*")
            for a in fired[-5:]:
                lines.append(f"  `{a.get('symbol','')}` {(a.get('last_message') or '')[:60]}")
        if not active and not fired:
            lines.append("No alerts. Add via /api/alerts or dashboard.")
        await update.message.reply_text("\\n".join(lines)[:4000], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
'''
        src = src.replace("def main():", CMD + "\ndef main():")

        for marker in ['app.add_handler(CommandHandler("eta"',
                       'app.add_handler(CommandHandler("global"',
                       'app.add_handler(CommandHandler("status"']:
            if marker in src:
                src = src.replace(marker,
                    '    app.add_handler(CommandHandler("alerts", cmd_alerts))\n    ' + marker)
                break

        BOT.write_text(src, encoding="utf-8")
        print("  [OK] Telegram: added /alerts command")

# Patch run_pipeline.py
for rp in [MICC / "data_pipeline" / "run_pipeline.py", MICC / "run_pipeline.py"]:
    if rp.exists():
        src = rp.read_text(encoding="utf-8")
        if "agent_alert" not in src:
            OLD = "    # Phase 9"
            NEW = """\
    # Phase 8B -- Alert checks (fires Telegram if triggered)
    _alert = MICC_DIR / "agent_alert.py"
    if _alert.exists():
        r["alerts"] = run(_alert, "Alert checks (price/RSI/pattern)",
                         args=["--send"], timeout=120, cwd=MICC_DIR)

    # Phase 9"""
            if OLD in src:
                rp.write_text(src.replace(OLD, NEW, 1), encoding="utf-8")
                print(f"  [OK] Pipeline: added agent_alert to {rp.name}")
        break

print("""
=============================================================
BUILD PHASE 19 (FIXED) COMPLETE
=============================================================

[1] D:\\MICC\\agent_alert.py
    Usage:
      py agent_alert.py --send             check all + Telegram
      py agent_alert.py --list             list alerts
      py agent_alert.py --add PRICE_ABOVE RELIANCE 2800 "resistance"
      py agent_alert.py --add RSI_BELOW NIFTY50 35 "oversold"
      py agent_alert.py --add VOLUME_SURGE HDFCBANK 3 "big vol"
      py agent_alert.py --add PATTERN_HIT INFY 70 "seasonal"

[2] /api/alerts/route.ts   GET/POST/DELETE/PATCH

[3] /alerts/page.tsx
    - Add alert with symbol autocomplete
    - Quick-add examples
    - Active / Fired / Paused sections
    - Toggle pause / delete

[4] /api/macro-global/route.ts
    FIX: uses base64-encoded SQL + argv (no backtick template literal)
    Returns: rates/fx/commodities/vix/crypto/equities + yield spread + rate history

[5] NavBar: ALERTS + GLOBAL links
    Telegram: /alerts command
    Pipeline: agent_alert.py runs daily with --send

SEASONALITY BUILDER STATUS:
  Running in other terminal
  207 symbols total
  At 10 syms = 18min -> estimate ~6-7h total for full run
  You can let it run overnight -- it auto-checkpoints every 50 symbols

NEXT STEPS:
  cd D:\\MICC\\micc-dashboard && npm run dev
  localhost:3000/alerts
  localhost:3000/global

  Test alerts:
    py D:\\MICC\\agent_alert.py --add RSI_BELOW NIFTY50 35 "oversold"
    py D:\\MICC\\agent_alert.py --send
=============================================================
""")
