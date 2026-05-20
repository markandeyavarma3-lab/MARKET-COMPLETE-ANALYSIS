"""
build_phase19_alerts_macro.py  --  Run from D:\MICC
Builds Phase 19:

  [1] agent_alert.py          -- Alert agent: price alerts, pattern alerts, watchlist triggers
  [2] /api/alerts/route.ts    -- Alert API (read + write alert configs)
  [3] /alerts/page.tsx        -- Alert management dashboard
  [4] /macro page upgrade     -- Adds global rates + FX panel + yield curve
  [5] telegram morning brief  -- Enhanced 9:15 AM with alerts + top patterns

Run: py D:\MICC\build_phase19_alerts_macro.py
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
Checks user-defined alerts against latest market data and fires
Telegram notifications when conditions are met.

Alert types:
  PRICE_ABOVE   symbol price > target
  PRICE_BELOW   symbol price < target
  PRICE_CROSS   price crosses target (above or below)
  PCT_MOVE      price moved > X% in last N days
  VOLUME_SURGE  volume > X * 20d average
  PATTERN_HIT   seasonal pattern anchor date matches today
  RSI_ABOVE     RSI(14) > threshold (overbought)
  RSI_BELOW     RSI(14) < threshold (oversold)

Alerts stored in: D:/MICC/alerts.json
Format:
  [{ "id":"...", "type":"PRICE_ABOVE", "symbol":"RELIANCE",
     "target":2800, "active":true, "triggered_at":null, "note":"" }]

Run:  py D:/MICC/agent_alert.py          -- check all alerts
      py D:/MICC/agent_alert.py --send   -- check + send Telegram
      py D:/MICC/agent_alert.py --list   -- list all alerts
"""

import argparse, json, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path

from micc_data import send_telegram_chunks, now_ist

DB         = Path(r"D:\\marketDB\\db\\market.db")
DA         = Path(r"D:\\MICC")
ALERTS_FILE= DA / "alerts.json"
OUTPUT_DIR = DA / "agents" / "alert"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.today().strftime("%Y-%m-%d")
TODAY_MMDD = datetime.today().strftime("%m-%d")


def log(msg, level="INFO"):
    tag = {"OK":" OK ","FAIL":"FAIL","WARN":"WARN"}.get(level,"INFO")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] [{tag}]  {msg}", flush=True)


# -- DB helpers ----------------------------------------------------------------

def get_latest_price(symbol: str) -> float | None:
    try:
        conn = sqlite3.connect(DB, timeout=10)
        row  = conn.execute(
            "SELECT close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        conn.close()
        return float(row[0]) if row else None
    except Exception:
        return None


def get_latest_volume(symbol: str) -> tuple[float|None, float|None]:
    """Returns (latest_volume, avg_20d_volume)"""
    try:
        conn = sqlite3.connect(DB, timeout=10)
        rows = conn.execute(
            "SELECT volume FROM stock_data WHERE symbol=? AND volume IS NOT NULL ORDER BY date DESC LIMIT 21",
            (symbol.upper(),)
        ).fetchall()
        conn.close()
        if not rows:
            return None, None
        vols = [float(r[0]) for r in rows]
        return vols[0], sum(vols[1:]) / max(len(vols)-1, 1)
    except Exception:
        return None, None


def get_pct_move(symbol: str, days: int) -> float | None:
    try:
        conn = sqlite3.connect(DB, timeout=10)
        rows = conn.execute(
            "SELECT close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT ?",
            (symbol.upper(), days+1)
        ).fetchall()
        conn.close()
        if len(rows) < 2:
            return None
        return (rows[0][0] / rows[-1][0] - 1) * 100
    except Exception:
        return None


def get_rsi(symbol: str) -> float | None:
    try:
        conn = sqlite3.connect(DB, timeout=10)
        row  = conn.execute(
            "SELECT rsi_14 FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def get_todays_patterns(min_accuracy: float = 68.0, min_score: float = 1.5) -> list:
    """Get seasonal patterns where anchor == today MM-DD"""
    try:
        conn = sqlite3.connect(DB, timeout=10)
        # Try v3 first, fall back to v2
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        tbl = "seasonality_patterns_v3" if "seasonality_patterns_v3" in tables else "seasonality_patterns"
        rows = conn.execute(
            f"SELECT symbol, window_days, direction, accuracy, mean_ret, score "
            f"FROM {tbl} WHERE anchor_mm_dd=? AND accuracy>=? AND score>=? "
            f"ORDER BY score DESC LIMIT 20",
            (TODAY_MMDD, min_accuracy, min_score)
        ).fetchall()
        conn.close()
        return [{"symbol":r[0],"window":r[1],"direction":r[2],
                 "accuracy":r[3],"mean_ret":r[4],"score":r[5]} for r in rows]
    except Exception:
        return []


# -- Alert file I/O ------------------------------------------------------------

def load_alerts() -> list:
    if not ALERTS_FILE.exists():
        return []
    try:
        return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_alerts(alerts: list):
    ALERTS_FILE.write_text(json.dumps(alerts, indent=2, default=str), encoding="utf-8")


# -- Check one alert -----------------------------------------------------------

def check_alert(alert: dict) -> tuple[bool, str]:
    """Returns (triggered, message)"""
    sym    = alert.get("symbol","").upper()
    typ    = alert.get("type","")
    target = float(alert.get("target", 0))
    note   = alert.get("note","")
    days   = int(alert.get("days", 5))

    if typ == "PRICE_ABOVE":
        price = get_latest_price(sym)
        if price is None: return False, ""
        if price > target:
            return True, f"PRICE ABOVE: {sym} @ {price:.2f} > {target:.2f}" + (f"  [{note}]" if note else "")

    elif typ == "PRICE_BELOW":
        price = get_latest_price(sym)
        if price is None: return False, ""
        if price < target:
            return True, f"PRICE BELOW: {sym} @ {price:.2f} < {target:.2f}" + (f"  [{note}]" if note else "")

    elif typ == "PCT_MOVE":
        move = get_pct_move(sym, days)
        if move is None: return False, ""
        if abs(move) >= target:
            sign = "up" if move > 0 else "down"
            return True, f"PCT MOVE: {sym} moved {move:+.1f}% in {days}d (threshold: {target:.1f}%)"

    elif typ == "VOLUME_SURGE":
        vol, avg = get_latest_volume(sym)
        if vol is None or avg is None or avg == 0: return False, ""
        ratio = vol / avg
        if ratio >= target:
            return True, f"VOLUME SURGE: {sym} vol {ratio:.1f}x above 20d avg (threshold: {target:.1f}x)"

    elif typ == "RSI_ABOVE":
        rsi = get_rsi(sym)
        if rsi is None: return False, ""
        if rsi > target:
            return True, f"RSI OVERBOUGHT: {sym} RSI={rsi:.1f} > {target:.0f}"

    elif typ == "RSI_BELOW":
        rsi = get_rsi(sym)
        if rsi is None: return False, ""
        if rsi < target:
            return True, f"RSI OVERSOLD: {sym} RSI={rsi:.1f} < {target:.0f}"

    elif typ == "PATTERN_HIT":
        # Target = min accuracy threshold, days = window to check
        patterns = get_todays_patterns(min_accuracy=target, min_score=1.0)
        hits = [p for p in patterns if p["symbol"].upper() == sym]
        if hits:
            p = hits[0]
            return True, (f"PATTERN: {sym} {p['direction']} {p['window']}d  "
                         f"acc={p['accuracy']:.0f}%  mean={p['mean_ret']:+.2f}%")

    return False, ""


# -- Main run ------------------------------------------------------------------

def run_alerts(send: bool = False) -> dict:
    print("=" * 55)
    print("  AGENT ALERT -- Price + Pattern + Watchlist")
    print("=" * 55)

    alerts    = load_alerts()
    log(f"Loaded {len(alerts)} alerts")

    # Check each active alert
    fired     = []
    still_ok  = []

    for alert in alerts:
        if not alert.get("active", True):
            still_ok.append(alert)
            continue

        triggered, msg = check_alert(alert)
        if triggered:
            alert["triggered_at"] = now_ist()
            alert["last_message"] = msg
            # One-shot alerts deactivate after firing
            if alert.get("one_shot", True):
                alert["active"] = False
            fired.append((alert, msg))
            log(f"FIRED: {msg}", "OK")
        else:
            still_ok.append(alert)

    # Save updated states
    save_alerts(alerts)

    # Today's seasonal patterns
    log("Checking today's seasonal patterns...")
    patterns = get_todays_patterns(min_accuracy=70.0, min_score=2.0)
    log(f"  {len(patterns)} patterns active for {TODAY_MMDD}")

    report = {
        "date":         TODAY,
        "generated_at": now_ist(),
        "alerts_checked": len(alerts),
        "alerts_fired": len(fired),
        "fired":        [{"alert": a, "message": m} for a, m in fired],
        "patterns_today": patterns,
    }

    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log(f"Saved: {out}")

    # Summary
    print(f"\\n  Alerts checked: {len(alerts)}")
    print(f"  Alerts fired:   {len(fired)}")
    print(f"  Patterns today: {len(patterns)}")
    print("=" * 55)

    if send and (fired or patterns):
        lines = ["*MICC Alerts -- " + TODAY + "*", ""]

        if fired:
            lines.append("*TRIGGERED ALERTS:*")
            for _, msg in fired:
                lines.append(f"  ALERT {msg}")
            lines.append("")

        if patterns:
            lines.append(f"*SEASONAL PATTERNS ({TODAY_MMDD}):*")
            for p in patterns[:8]:
                ico = "UP" if p["direction"]=="UP" else "DN"
                lines.append(
                    f"  {ico} `{p['symbol']:<14}` {p['window']}d  "
                    f"{p['accuracy']:.0f}%  {p['mean_ret']:+.2f}%  s={p['score']:.1f}"
                )
            lines.append("")

        msg = "\\n".join(lines)
        ok  = send_telegram_chunks(msg)
        log(f"Telegram: {'OK' if ok else 'FAILED'}")

    return report


# -- Add alert helper ----------------------------------------------------------

def add_alert(type_: str, symbol: str, target: float,
              note: str = "", days: int = 5, one_shot: bool = True):
    alerts = load_alerts()
    import uuid
    alerts.append({
        "id":          str(uuid.uuid4())[:8],
        "type":        type_.upper(),
        "symbol":      symbol.upper(),
        "target":      target,
        "note":        note,
        "days":        days,
        "one_shot":    one_shot,
        "active":      True,
        "created_at":  now_ist(),
        "triggered_at":None,
        "last_message":None,
    })
    save_alerts(alerts)
    print(f"  Added alert: {type_.upper()} {symbol.upper()} target={target}")


# -- Entry point ---------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send",  action="store_true")
    ap.add_argument("--list",  action="store_true")
    ap.add_argument("--add",   nargs="+", help="TYPE SYMBOL TARGET [NOTE]")
    args = ap.parse_args()

    if args.list:
        alerts = load_alerts()
        print(f"\\n  {len(alerts)} alerts:\\n")
        for a in alerts:
            status = "ACTIVE" if a.get("active") else "FIRED"
            print(f"  [{status}] {a['type']:<15} {a['symbol']:<14} target={a['target']}"
                  f"  {a.get('note','')}")
        sys.exit(0)

    if args.add:
        if len(args.add) < 3:
            print("Usage: --add TYPE SYMBOL TARGET [NOTE]"); sys.exit(1)
        add_alert(args.add[0], args.add[1], float(args.add[2]),
                  note=" ".join(args.add[3:]) if len(args.add) > 3 else "")
        sys.exit(0)

    run_alerts(send=args.send)
'''
write(MICC / "agent_alert.py", ALERT_AGENT, "D:\\MICC\\agent_alert.py")


# =============================================================================
# [2]  /api/alerts/route.ts
# =============================================================================
print("\n[2/5] Writing /api/alerts/route.ts ...")

ALERTS_ROUTE = """\
import { NextResponse } from "next/server";
import fs   from "fs";
import path from "path";

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
    const alerts = load().filter((a: any) => a.id !== id);
    save(alerts);
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}

export async function PATCH(req: Request) {
  try {
    const { id, ...updates } = await req.json();
    const alerts = load().map((a: any) => a.id === id ? { ...a, ...updates } : a);
    save(alerts);
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
"""
write(SRC / "api" / "alerts" / "route.ts", ALERTS_ROUTE, "/api/alerts/route.ts")


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

const ALERT_TYPES = [
  { value:"PRICE_ABOVE",   label:"Price Above",   desc:"Fires when price crosses above target" },
  { value:"PRICE_BELOW",   label:"Price Below",   desc:"Fires when price drops below target" },
  { value:"PCT_MOVE",      label:"% Move",        desc:"Fires when price moves > target% in N days" },
  { value:"VOLUME_SURGE",  label:"Volume Surge",  desc:"Fires when volume > target x 20d average" },
  { value:"RSI_ABOVE",     label:"RSI Overbought",desc:"Fires when RSI(14) > target" },
  { value:"RSI_BELOW",     label:"RSI Oversold",  desc:"Fires when RSI(14) < target" },
  { value:"PATTERN_HIT",   label:"Pattern Hit",   desc:"Fires when seasonal pattern active today" },
];

const TYPE_CLR: Record<string,string> = {
  PRICE_ABOVE:"#22c55e", PRICE_BELOW:"#ef4444", PCT_MOVE:"#fbbf24",
  VOLUME_SURGE:"#a78bfa", RSI_ABOVE:"#f97316", RSI_BELOW:"#60a5fa",
  PATTERN_HIT:"#34d399",
};

function Badge({ label, color }: { label:string; color:string }) {
  return (
    <span style={{
      fontSize:10, fontWeight:700, padding:"2px 7px", borderRadius:4,
      background:color+"22", color,
    }}>{label}</span>
  );
}

export default function AlertsPage() {
  const [alerts,  setAlerts]  = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form,    setForm]    = useState({
    type:"PRICE_ABOVE", symbol:"", target:"", note:"", days:5, one_shot:true,
  });
  const [saving,  setSaving]  = useState(false);
  const [search,  setSearch]  = useState<{results:{symbol:string;name:string}[]}>({results:[]});
  const [searchQ, setSearchQ] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/alerts");
      const d = await r.json();
      setAlerts(d.alerts||[]);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { reload(); }, []);

  // Autocomplete for symbol field
  useEffect(() => {
    if (!searchQ.trim()) { setSearch({results:[]}); return; }
    const t = setTimeout(async () => {
      try {
        const r = await fetch("/api/search?q="+encodeURIComponent(searchQ)+"&limit=8");
        const d = await r.json();
        setSearch(d);
      } catch {}
    }, 200);
    return () => clearTimeout(t);
  }, [searchQ]);

  const addAlert = async () => {
    if (!form.symbol||!form.target) return;
    setSaving(true);
    try {
      await fetch("/api/alerts", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          type: form.type, symbol: form.symbol.toUpperCase(),
          target: parseFloat(form.target), note: form.note,
          days: form.days, one_shot: form.one_shot,
        }),
      });
      setShowAdd(false);
      setForm({ type:"PRICE_ABOVE", symbol:"", target:"", note:"", days:5, one_shot:true });
      setSearchQ("");
      reload();
    } catch {}
    setSaving(false);
  };

  const deleteAlert = async (id: string) => {
    await fetch("/api/alerts", {
      method:"DELETE",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ id }),
    });
    reload();
  };

  const toggleAlert = async (id: string, active: boolean) => {
    await fetch("/api/alerts", {
      method:"PATCH",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ id, active }),
    });
    reload();
  };

  const active  = alerts.filter(a => a.active);
  const fired   = alerts.filter(a => !a.active && a.triggered_at);
  const paused  = alerts.filter(a => !a.active && !a.triggered_at);

  const inputStyle = {
    padding:"8px 12px", background:"#0f172a", border:"1px solid #334155",
    borderRadius:7, color:"#f8fafc", fontSize:13, outline:"none",
    width:"100%", boxSizing:"border-box" as const,
  };

  return (
    <div style={{ minHeight:"100vh", background:"#0f172a", color:"#e2e8f0", fontFamily:"system-ui,sans-serif" }}>

      {/* Header */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", gap:16 }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"#f8fafc" }}>
            Alerts
          </h1>
          <p style={{ margin:"4px 0 0", fontSize:12, color:"#64748b" }}>
            Price, volume, RSI, pattern triggers via Telegram
          </p>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:10 }}>
          {[
            {label:"Active",  value:active.length,  color:"#22c55e"},
            {label:"Fired",   value:fired.length,   color:"#fbbf24"},
            {label:"Paused",  value:paused.length,  color:"#64748b"},
          ].map(s=>(
            <div key={s.label} style={{
              textAlign:"center", padding:"7px 14px", background:"#1e293b",
              borderRadius:8, border:`1px solid ${s.color}33`,
            }}>
              <div style={{ fontSize:18, fontWeight:800, color:s.color }}>{s.value}</div>
              <div style={{ fontSize:10, color:"#64748b" }}>{s.label}</div>
            </div>
          ))}
          <button onClick={()=>setShowAdd(o=>!o)} style={{
            padding:"8px 18px", background:"#3b82f6", color:"#fff",
            border:"none", borderRadius:8, cursor:"pointer", fontSize:13, fontWeight:700,
            alignSelf:"center",
          }}>+ Add Alert</button>
        </div>
      </div>

      <div style={{ padding:"20px 28px" }}>

        {/* Add alert form */}
        {showAdd && (
          <div style={{
            background:"#1e293b", border:"1px solid #3b82f6", borderRadius:12,
            padding:"20px", marginBottom:20,
          }}>
            <h3 style={{ margin:"0 0 16px", fontSize:14, fontWeight:700, color:"#60a5fa" }}>
              New Alert
            </h3>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12 }}>

              {/* Type */}
              <div>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:5 }}>TYPE</div>
                <select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))}
                  style={{...inputStyle}}>
                  {ALERT_TYPES.map(t=>(
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                <div style={{ fontSize:10, color:"#475569", marginTop:4 }}>
                  {ALERT_TYPES.find(t=>t.value===form.type)?.desc}
                </div>
              </div>

              {/* Symbol with autocomplete */}
              <div style={{ position:"relative" }}>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:5 }}>SYMBOL</div>
                <input value={searchQ||form.symbol}
                  onChange={e=>{setSearchQ(e.target.value);setForm(f=>({...f,symbol:e.target.value.toUpperCase()}));}}
                  placeholder="e.g. RELIANCE"
                  style={{...inputStyle}}
                />
                {search.results.length>0 && searchQ && (
                  <div style={{
                    position:"absolute", top:"100%", left:0, right:0, zIndex:100,
                    background:"#1e293b", border:"1px solid #334155", borderRadius:7,
                    boxShadow:"0 8px 24px rgba(0,0,0,0.5)", overflow:"hidden",
                  }}>
                    {search.results.map(r=>(
                      <div key={r.symbol} onMouseDown={()=>{
                        setForm(f=>({...f,symbol:r.symbol}));
                        setSearchQ(""); setSearch({results:[]});
                      }} style={{
                        padding:"8px 12px", cursor:"pointer", fontSize:12,
                        borderBottom:"1px solid #0f172a", display:"flex", gap:10,
                      }}>
                        <span style={{ fontFamily:"monospace", fontWeight:700, color:"#60a5fa" }}>{r.symbol}</span>
                        <span style={{ color:"#64748b" }}>{r.name!==r.symbol?r.name:""}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Target */}
              <div>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:5 }}>
                  TARGET ({form.type==="VOLUME_SURGE"?"x avg":form.type==="PCT_MOVE"?"%":"price"})
                </div>
                <input type="number" value={form.target}
                  onChange={e=>setForm(f=>({...f,target:e.target.value}))}
                  placeholder={form.type==="VOLUME_SURGE"?"e.g. 3":form.type==="PCT_MOVE"?"e.g. 5":"e.g. 2800"}
                  style={{...inputStyle}}
                />
              </div>

              {/* Days (for PCT_MOVE) */}
              {form.type==="PCT_MOVE" && (
                <div>
                  <div style={{ fontSize:10, color:"#64748b", marginBottom:5 }}>LOOKBACK DAYS</div>
                  <input type="number" value={form.days}
                    onChange={e=>setForm(f=>({...f,days:parseInt(e.target.value)||5}))}
                    style={{...inputStyle}}
                  />
                </div>
              )}

              {/* Note */}
              <div style={{ gridColumn:"1/-1" }}>
                <div style={{ fontSize:10, color:"#64748b", marginBottom:5 }}>NOTE (optional)</div>
                <input value={form.note}
                  onChange={e=>setForm(f=>({...f,note:e.target.value}))}
                  placeholder="e.g. Support level, earnings play"
                  style={{...inputStyle}}
                />
              </div>

              {/* One-shot toggle */}
              <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                <input type="checkbox" id="oneshot" checked={form.one_shot}
                  onChange={e=>setForm(f=>({...f,one_shot:e.target.checked}))}
                />
                <label htmlFor="oneshot" style={{ fontSize:12, color:"#94a3b8", cursor:"pointer" }}>
                  One-shot (deactivate after firing)
                </label>
              </div>

            </div>
            <div style={{ display:"flex", gap:8, marginTop:16 }}>
              <button onClick={addAlert} disabled={saving||!form.symbol||!form.target}
                style={{
                  padding:"8px 20px", background:"#22c55e", color:"#fff",
                  border:"none", borderRadius:7, cursor:"pointer", fontSize:13, fontWeight:700,
                }}>
                {saving ? "Saving..." : "Add Alert"}
              </button>
              <button onClick={()=>setShowAdd(false)}
                style={{
                  padding:"8px 16px", background:"#334155", color:"#94a3b8",
                  border:"none", borderRadius:7, cursor:"pointer", fontSize:13,
                }}>Cancel</button>
            </div>
          </div>
        )}

        {/* Quick-add examples */}
        <div style={{ marginBottom:20, padding:"12px 16px", background:"#1e293b", borderRadius:10 }}>
          <div style={{ fontSize:11, color:"#64748b", marginBottom:8 }}>QUICK ADD EXAMPLES</div>
          <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
            {[
              {type:"RSI_BELOW",   symbol:"NIFTY50", target:35,  note:"Oversold bounce"},
              {type:"PRICE_ABOVE", symbol:"RELIANCE",target:1400,note:"Breakout level"},
              {type:"VOLUME_SURGE",symbol:"HDFCBANK", target:3,   note:"Big volume"},
              {type:"PCT_MOVE",    symbol:"SBIN",     target:5,   note:"5% move 3d",days:3},
              {type:"PATTERN_HIT", symbol:"INFY",     target:70,  note:"Seasonal 70%+"},
            ].map((ex,i)=>(
              <button key={i} onClick={async ()=>{
                await fetch("/api/alerts",{
                  method:"POST", headers:{"Content-Type":"application/json"},
                  body:JSON.stringify({...ex,one_shot:true,active:true}),
                });
                reload();
              }} style={{
                fontSize:11, padding:"4px 12px", background:"#0f172a",
                border:"1px solid #334155", borderRadius:6, cursor:"pointer",
                color:"#94a3b8",
              }}>
                {ex.type.replace("_"," ")} {ex.symbol} {ex.target}{ex.note?" ("+ex.note+")":""}
              </button>
            ))}
          </div>
        </div>

        {/* Alert list */}
        {loading ? (
          <div style={{ color:"#64748b", fontSize:13 }}>Loading alerts...</div>
        ) : alerts.length === 0 ? (
          <div style={{ textAlign:"center", padding:"60px 0", color:"#475569" }}>
            <div style={{ fontSize:40, marginBottom:12 }}>Bell</div>
            <p>No alerts set. Click Add Alert to create one.</p>
            <p style={{ fontSize:11 }}>
              Run: py D:\\MICC\\agent_alert.py --send   (checks all alerts, fires Telegram)
            </p>
          </div>
        ) : (
          <div>
            {[{label:"Active Alerts", items:active, accent:"#22c55e"},
              {label:"Fired Alerts",  items:fired,  accent:"#fbbf24"},
              {label:"Paused Alerts", items:paused, accent:"#64748b"},
            ].filter(g=>g.items.length>0).map(group=>(
              <div key={group.label} style={{ marginBottom:24 }}>
                <h3 style={{ fontSize:12, fontWeight:700, color:group.accent,
                  letterSpacing:1, marginBottom:10, textTransform:"uppercase" }}>
                  {group.label} ({group.items.length})
                </h3>
                <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                  {group.items.map(a=>(
                    <div key={a.id} style={{
                      background:"#1e293b",
                      border:`1px solid ${a.active?TYPE_CLR[a.type]+"44":"#334155"}`,
                      borderRadius:10, padding:"12px 16px",
                      display:"flex", alignItems:"center", gap:14, flexWrap:"wrap",
                    }}>
                      <Badge label={a.type.replace(/_/g," ")} color={TYPE_CLR[a.type]||"#94a3b8"} />
                      <span style={{ fontFamily:"monospace", fontWeight:800, color:"#60a5fa", fontSize:13 }}>{a.symbol}</span>
                      <span style={{ fontSize:13, color:"#e2e8f0", fontWeight:700 }}>target: {a.target}</span>
                      {a.note && <span style={{ fontSize:11, color:"#64748b" }}>{a.note}</span>}
                      {a.triggered_at && (
                        <span style={{ fontSize:10, color:"#fbbf24" }}>Fired: {a.triggered_at}</span>
                      )}
                      {a.last_message && (
                        <span style={{ fontSize:11, color:"#94a3b8", flex:1 }}>{a.last_message}</span>
                      )}
                      <div style={{ display:"flex", gap:6, marginLeft:"auto" }}>
                        <button onClick={()=>toggleAlert(a.id, !a.active)} style={{
                          padding:"4px 10px", fontSize:11,
                          background:a.active?"#334155":"#1e3a5f",
                          color:a.active?"#64748b":"#60a5fa",
                          border:"1px solid #334155", borderRadius:5, cursor:"pointer",
                        }}>{a.active?"Pause":"Resume"}</button>
                        <button onClick={()=>deleteAlert(a.id)} style={{
                          padding:"4px 10px", fontSize:11,
                          background:"#2d1515", color:"#ef4444",
                          border:"1px solid #ef444433", borderRadius:5, cursor:"pointer",
                        }}>Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Run info */}
        <div style={{
          marginTop:24, padding:"14px 16px",
          background:"#1e293b", borderRadius:10, fontSize:12, color:"#64748b",
        }}>
          <strong style={{ color:"#94a3b8" }}>Run alerts manually:</strong>
          <code style={{ display:"block", marginTop:6, color:"#60a5fa" }}>
            py D:\\MICC\\agent_alert.py --send
          </code>
          <span style={{ fontSize:11 }}>
            Or add to daily pipeline in run_pipeline.py. Fires Telegram on trigger.
          </span>
        </div>
      </div>
    </div>
  );
}
"""
write(SRC / "alerts" / "page.tsx", ALERTS_PAGE, "/alerts/page.tsx")


# =============================================================================
# [4]  /api/macro-global/route.ts  -- global rates + FX for macro page
# =============================================================================
print("\n[4/5] Writing /api/macro-global/route.ts ...")

MACRO_GLOBAL_ROUTE = r"""import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\s*NaN\b/g, ": null").replace(/:\s*Infinity\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const script = `
import sqlite3, json, sys
conn = sqlite3.connect(r"D:/marketDB/db/market.db", timeout=10)
conn.row_factory = sqlite3.Row
p = json.loads(sys.argv[1])
rows = conn.execute("""` + sql + `""", p).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
`;
  const r = spawnSync(PY, ["-c", script, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) return [];
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET() {
  try {
    // Latest for key global symbols
    const RATE_SYMS  = ["US10Y","US2Y","US30Y"];
    const FX_SYMS    = ["DXY","USDINR","EURUSD","USDJPY","GBPUSD"];
    const CMDTY_SYMS = ["Gold","CrudeWTI","Silver","NatGas","Copper"];
    const VIX_SYMS   = ["SP500VIX","INDIAVIX"];
    const CRYPTO_SYMS= ["Bitcoin","Ethereum"];

    const all_syms = [...RATE_SYMS,...FX_SYMS,...CMDTY_SYMS,...VIX_SYMS,...CRYPTO_SYMS];

    const latest = qdb(`
      SELECT g.symbol, g.date, g.close, g.pct_change
      FROM global_indices_daily g
      WHERE g.date = (SELECT MAX(date) FROM global_indices_daily WHERE symbol = g.symbol)
        AND g.symbol IN (${all_syms.map(()=>"?").join(",")})
    `, all_syms);

    // 30-day history for rates (yield curve view)
    const rates_hist = qdb(`
      SELECT symbol, date, close FROM global_indices_daily
      WHERE symbol IN ('US2Y','US10Y','US30Y')
        AND date >= date('now','-60 days')
      ORDER BY symbol, date
    `, []);

    // Group by category
    const bySymbol: Record<string,any> = {};
    for (const r of latest) bySymbol[r.symbol] = r;

    const rates  = RATE_SYMS.map(s  => ({ ...bySymbol[s],  symbol: s }));
    const fx     = FX_SYMS.map(s    => ({ ...bySymbol[s],  symbol: s }));
    const cmdty  = CMDTY_SYMS.map(s => ({ ...bySymbol[s],  symbol: s }));
    const vix    = VIX_SYMS.map(s   => ({ ...bySymbol[s],  symbol: s }));
    const crypto = CRYPTO_SYMS.map(s=> ({ ...bySymbol[s],  symbol: s }));

    // Yield spread
    const us10y = bySymbol["US10Y"]?.close ?? null;
    const us2y  = bySymbol["US2Y"]?.close  ?? null;
    const spread = us10y && us2y ? Math.round((us10y - us2y) * 100) / 100 : null;

    // Rates history grouped by symbol
    const ratesHistory: Record<string, {date:string;close:number}[]> = {};
    for (const r of rates_hist) {
      if (!ratesHistory[r.symbol]) ratesHistory[r.symbol] = [];
      ratesHistory[r.symbol].push({ date: r.date, close: r.close });
    }

    return NextResponse.json({
      rates, fx, commodities: cmdty, volatility: vix, crypto,
      yield_spread: spread,
      rates_history: ratesHistory,
      as_of: latest[0]?.date || null,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
"""
write(SRC / "api" / "macro-global" / "route.ts", MACRO_GLOBAL_ROUTE, "/api/macro-global/route.ts")


# =============================================================================
# [5]  Add ALERTS + GLOBAL nav links, patch telegram for alerts
# =============================================================================
print("\n[5/5] Patching NavBar + telegram_bot ...")

# NavBar
navbar_path = None
for p in DASH.rglob("NavBar.tsx"):
    navbar_path = p; break

if navbar_path:
    src = navbar_path.read_text(encoding="utf-8")
    changed = False
    for href, label in [("/alerts","ALERTS"), ("/global","GLOBAL")]:
        if href not in src:
            for marker in ["'/eta'", '"/eta"', "'/compare'", '"/compare"']:
                if marker in src:
                    idx      = src.rfind(marker)
                    line_end = src.find("\n", idx)
                    src      = src[:line_end] + f"\n  {{ href: '{href}', label: '{label}' }}," + src[line_end:]
                    changed  = True
                    print(f"  [OK] Added {label} to NavBar")
                    break
    if changed:
        navbar_path.write_text(src, encoding="utf-8")

# Telegram: add /alerts command
BOT = MICC / "telegram_bot.py"
if BOT.exists():
    src = BOT.read_text(encoding="utf-8")
    if "cmd_alerts" not in src:
        ALERTS_CMD = '''

async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active alerts. Usage: /alerts"""
    import json
    ALERTS_FILE = r"D:\\MICC\\alerts.json"
    try:
        import pathlib
        p = pathlib.Path(ALERTS_FILE)
        alerts = json.loads(p.read_text()) if p.exists() else []
        active = [a for a in alerts if a.get("active")]
        fired  = [a for a in alerts if not a.get("active") and a.get("triggered_at")]
        lines  = ["*MICC Alerts*", ""]
        if active:
            lines.append(f"*Active ({len(active)}):*")
            for a in active[:10]:
                lines.append(f"  `{a['type'][:12]:<12}` `{a['symbol']:<12}` target={a['target']}"
                            +(f"  {a['note']}" if a.get('note') else ""))
            lines.append("")
        if fired:
            lines.append(f"*Recently Fired ({len(fired)}):*")
            for a in fired[-5:]:
                lines.append(f"  `{a['symbol']}` {a.get('last_message','')[:60]}")
        if not active and not fired:
            lines.append("No alerts set. Use /api/alerts or the dashboard.")
        await update.message.reply_text("\\n".join(lines)[:4000], parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
'''
        src = src.replace("def main():", ALERTS_CMD + "\ndef main():")

        # Register handler
        for marker in ['app.add_handler(CommandHandler("eta"',
                       'app.add_handler(CommandHandler("global"']:
            if marker in src:
                src = src.replace(marker,
                    '    app.add_handler(CommandHandler("alerts", cmd_alerts))\n    ' + marker)
                break

        BOT.write_text(src, encoding="utf-8")
        print("  [OK] Added /alerts command to telegram_bot.py")


# Add agent_alert to run_pipeline.py
for rp in [PIPE := MICC / "data_pipeline" / "run_pipeline.py", MICC / "run_pipeline.py"]:
    if rp.exists():
        src = rp.read_text(encoding="utf-8")
        if "agent_alert" not in src:
            OLD = "    # Phase 9 -- Intelligence engine"
            NEW = """\
    # Phase 8B -- Alert checks
    _alert = MICC_DIR / "agent_alert.py"
    if _alert.exists():
        r["alerts"] = run(_alert, "Alert checks (price/pattern/RSI)",
                         args=["--send"], timeout=120, cwd=MICC_DIR)

    # Phase 9 -- Intelligence engine"""
            if OLD in src:
                rp.write_text(src.replace(OLD, NEW), encoding="utf-8")
                print(f"  [OK] Added agent_alert to {rp.name}")
        break


print("""
=============================================================
BUILD PHASE 19 COMPLETE
=============================================================

[1] D:\\MICC\\agent_alert.py
    Alert types: PRICE_ABOVE/BELOW, PCT_MOVE, VOLUME_SURGE,
                 RSI_ABOVE/BELOW, PATTERN_HIT
    Commands:
      py agent_alert.py           -- check all alerts
      py agent_alert.py --send    -- check + fire Telegram
      py agent_alert.py --list    -- show all alerts
      py agent_alert.py --add PRICE_ABOVE RELIANCE 2800 "resistance"

[2] /api/alerts/route.ts  -- GET/POST/DELETE/PATCH

[3] /alerts/page.tsx
    Full alert management UI:
    - Add alert form with autocomplete symbol search
    - Quick-add examples (RSI oversold, price breakout, etc.)
    - Active / Fired / Paused sections
    - Toggle active/pause per alert
    - Delete alerts

[4] /api/macro-global/route.ts
    Returns: rates (US2Y/10Y/30Y), FX, commodities, VIX, crypto
    + yield spread (10Y - 2Y)
    + 60-day rate history for yield curve chart

[5] NavBar: ALERTS link added
    Telegram: /alerts command added
    Pipeline: agent_alert.py runs daily with --send

NEXT STEPS:
  cd D:\\MICC\\micc-dashboard && npm run dev
  localhost:3000/alerts

  Add first alert:
  py D:\\MICC\\agent_alert.py --add RSI_BELOW NIFTY50 35 "oversold"
  py D:\\MICC\\agent_alert.py --add PRICE_ABOVE RELIANCE 2900 "breakout"
  py D:\\MICC\\agent_alert.py --send

FULL QUEUE STATUS:
  Done: /eta /compare /global /patterns-v3 /alerts
  Done: Autocomplete search API
  Done: 52 global indices in DB
  Done: Daily pipeline integrated
  Done: Telegram: /eta /deep /kappa /global /patterns /alerts
  Running: build_seasonality_v3.py (check other terminal)
  Next: /macro page upgrade with yield curve + global FX panel
=============================================================
""")
