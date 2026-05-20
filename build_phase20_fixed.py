"""
build_phase20_fixed.py  --  Run from D:\MICC
Fixed: no backslash escape issues in Python strings.
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
# [1]  fix_pattern_scores.py
# =============================================================================
print("\n[1/4] Writing fix_pattern_scores.py ...")

fix_scores_lines = [
    '"""',
    'fix_pattern_scores.py  --  Run ONCE from D:\\MICC',
    'Removes patterns where |mean_ret| > 50% (price-level artifacts).',
    'Run: py D:\\MICC\\fix_pattern_scores.py',
    '"""',
    'import sqlite3',
    'from pathlib import Path',
    '',
    'DB = Path(r"D:\\marketDB\\db\\market.db")',
    'conn = sqlite3.connect(DB, timeout=30)',
    '',
    'print("Checking seasonality_patterns_v3 for outlier mean_ret...")',
    '',
    'bad = conn.execute(',
    '    "SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE ABS(mean_ret) > 50"',
    ').fetchone()[0]',
    'total = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]',
    'print(f"  Total rows:   {total:,}")',
    'print(f"  Outlier rows: {bad:,}  (|mean_ret| > 50%)")',
    '',
    'if bad == 0:',
    '    print("  No outliers -- nothing to do.")',
    '    conn.close()',
    '    raise SystemExit(0)',
    '',
    'rows = conn.execute(',
    '    "SELECT symbol, COUNT(*), AVG(ABS(mean_ret)), MAX(ABS(mean_ret)) "',
    '    "FROM seasonality_patterns_v3 WHERE ABS(mean_ret) > 50 "',
    '    "GROUP BY symbol ORDER BY AVG(ABS(mean_ret)) DESC LIMIT 20"',
    ').fetchall()',
    'print("\\nTop symbols with outlier returns:")',
    'for sym, cnt, avg_ret, max_ret in rows:',
    '    print(f"  {sym:<35} {cnt:>6,} rows  avg={avg_ret:.1f}%  max={max_ret:.1f}%")',
    '',
    'ans = input(f"\\nDelete {bad:,} outlier rows? [y/n]: ").strip().lower()',
    'if ans != "y":',
    '    print("  Aborted.")',
    '    conn.close()',
    '    raise SystemExit(0)',
    '',
    'conn.execute("DELETE FROM seasonality_patterns_v3 WHERE ABS(mean_ret) > 50")',
    'conn.commit()',
    'remaining = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]',
    'conn.close()',
    '',
    'print(f"\\nDeleted {bad:,} outlier rows")',
    'print(f"Remaining: {remaining:,} valid patterns")',
    'print("Done. Restart dashboard -- /patterns-v3 will show clean data.")',
]
write(MICC / "fix_pattern_scores.py", "\n".join(fix_scores_lines), "fix_pattern_scores.py")


# =============================================================================
# [2]  /api/patterns-v3/route.ts
# =============================================================================
print("\n[2/4] Writing /api/patterns-v3/route.ts ...")

pv3_ts = """import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

function qdb(sql: string, params: any[] = []): any[] {
  const sqlB64   = Buffer.from(sql).toString("base64");
  const pyLines  = [
    "import sqlite3, json, sys, base64",
    "conn = sqlite3.connect(r'" + DB + "', timeout=15)",
    "conn.row_factory = sqlite3.Row",
    "sql = base64.b64decode(sys.argv[1]).decode()",
    "params = json.loads(sys.argv[2])",
    "rows = conn.execute(sql, params).fetchall()",
    "print(json.dumps([dict(r) for r in rows], default=str))",
    "conn.close()",
  ];
  const r = spawnSync(PY, ["-c", pyLines.join("\\n"), sqlB64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 30000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200) || "DB error");
  try { return JSON.parse(sanitize(r.stdout.trim() || "[]")); } catch { return []; }
}

export async function GET(req: Request) {
  const url      = new URL(req.url);
  const symbol   = (url.searchParams.get("symbol") || "").toUpperCase();
  const win      = url.searchParams.get("window")    || "";
  const dir      = (url.searchParams.get("direction") || "").toUpperCase();
  const month    = url.searchParams.get("month")     || "";
  const anchor   = url.searchParams.get("anchor")    || "";
  const sort     = url.searchParams.get("sort")      || "score";
  const limit    = Math.min(parseInt(url.searchParams.get("limit") || "100"), 500);
  const minAcc   = parseFloat(url.searchParams.get("min_accuracy") || "60");
  const minScore = parseFloat(url.searchParams.get("min_score")    || "1");
  const maxMean  = parseFloat(url.searchParams.get("max_mean_ret") || "50");

  try {
    const conditions: string[] = ["accuracy >= ?", "score >= ?", "ABS(mean_ret) <= ?"];
    const params: any[]        = [minAcc, minScore, maxMean];

    if (symbol) { conditions.push("symbol = ?");             params.push(symbol); }
    if (win)    { conditions.push("window_days = ?");         params.push(parseInt(win)); }
    if (dir)    { conditions.push("direction = ?");           params.push(dir); }
    if (anchor) { conditions.push("anchor_mm_dd = ?");        params.push(anchor); }
    if (month)  { conditions.push("anchor_mm_dd LIKE ?");     params.push(month + "-%"); }

    const SORTS: Record<string, string> = {
      score:"score", accuracy:"accuracy", mean_ret:"ABS(mean_ret)",
      consistency:"consistency", t_stat:"ABS(t_stat)", p_value:"p_value",
      n_obs:"n_obs", degradation:"degradation",
    };
    const sortCol = SORTS[sort] || "score";
    const sortDir = sort === "p_value" ? "ASC" : "DESC";
    const where   = "WHERE " + conditions.join(" AND ");

    const sql = [
      "SELECT symbol, anchor_mm_dd, window_days, direction,",
      "n_obs, accuracy, mean_ret, median_ret, std_ret,",
      "p10, p25, p75, p90, best_ret, worst_ret,",
      "score, consistency, edge_ratio, t_stat, p_value,",
      "early_accuracy, recent_accuracy, degradation, recent_mean, recent_vs_all",
      "FROM seasonality_patterns_v3",
      where,
      "ORDER BY " + sortCol + " " + sortDir,
      "LIMIT " + limit,
    ].join(" ");

    const rows = qdb(sql, params);
    return NextResponse.json({ count: rows.length, rows });
  } catch (e: any) {
    return NextResponse.json({ error: e.message, count: 0, rows: [] }, { status: 500 });
  }
}
"""
write(SRC / "api" / "patterns-v3" / "route.ts", pv3_ts, "/api/patterns-v3/route.ts")


# =============================================================================
# [3]  /macro/page.tsx
# =============================================================================
print("\n[3/4] Writing /macro/page.tsx ...")

macro_page = '''\
"use client";

import { useEffect, useState, useCallback } from "react";

interface GRow { symbol: string; date: string; close: number|null; pct_change: number|null; }
interface RHist { date: string; close: number; }
interface MacroG {
  rates: GRow[]; fx: GRow[]; commodities: GRow[];
  volatility: GRow[]; crypto: GRow[]; equities: GRow[];
  yield_spread: number|null;
  rates_history: Record<string, RHist[]>;
  as_of: string|null; error?: string;
}
interface Pat { symbol:string; window_days:number; direction:string; accuracy:number; mean_ret:number; score:number; }

const NAMES: Record<string,string> = {
  US10Y:"US 10Y",US2Y:"US 2Y",US30Y:"US 30Y",
  DXY:"DXY",USDINR:"USD/INR",EURUSD:"EUR/USD",USDJPY:"USD/JPY",GBPUSD:"GBP/USD",
  Gold:"Gold",CrudeWTI:"Crude WTI",Silver:"Silver",NatGas:"Nat Gas",Copper:"Copper",
  SP500VIX:"VIX",INDIAVIX:"India VIX",Bitcoin:"BTC",Ethereum:"ETH",
  SPX:"S&P 500",NDX:"Nasdaq",NIFTY50:"Nifty 50",Nikkei225:"Nikkei",DAX:"DAX",
};
const FLAGS: Record<string,string> = {
  US10Y:"🇺🇸",US2Y:"🇺🇸",US30Y:"🇺🇸",
  DXY:"💵",USDINR:"₹",EURUSD:"🇪🇺",USDJPY:"🇯🇵",GBPUSD:"🇬🇧",
  Gold:"🥇",CrudeWTI:"🛢",Silver:"🥈",NatGas:"🔥",Copper:"🟤",
  SP500VIX:"⚡",INDIAVIX:"⚡",Bitcoin:"₿",Ethereum:"Ξ",
  SPX:"🇺🇸",NDX:"🇺🇸",NIFTY50:"🇮🇳",Nikkei225:"🇯🇵",DAX:"🇩🇪",
};

const fmtClose = (v:number|null, sym:string) => {
  if (v==null) return "—";
  if (["US10Y","US2Y","US30Y"].includes(sym)) return v.toFixed(2)+"%";
  if (["USDINR","EURUSD","USDJPY","GBPUSD"].includes(sym)) return v.toFixed(4);
  if (v>=10000) return v.toLocaleString("en-US",{maximumFractionDigits:0});
  if (v>=100) return v.toFixed(2);
  return v.toFixed(4);
};
const pct = (v:number|null) => v==null?"—":(v>=0?"+":"")+v.toFixed(2)+"%";
const clr = (v:number|null, inv=false) =>
  v==null?"#94a3b8":(inv?v<0:v>0)?"#22c55e":v===0?"#94a3b8":"#ef4444";

function Panel({ title, icon, children }: { title:string; icon:string; children:React.ReactNode }) {
  return (
    <div style={{ background:"#1e293b", border:"1px solid #334155", borderRadius:12, overflow:"hidden" }}>
      <div style={{ padding:"11px 16px", borderBottom:"1px solid #334155",
        display:"flex", alignItems:"center", gap:8 }}>
        <span>{icon}</span>
        <span style={{ fontSize:11, fontWeight:700, color:"#64748b", letterSpacing:0.8, textTransform:"uppercase" }}>
          {title}
        </span>
      </div>
      {children}
    </div>
  );
}

function GRowComp({ row, inv }: { row:GRow; inv?:boolean }) {
  const dc = clr(row.pct_change, inv);
  return (
    <div style={{ display:"flex", alignItems:"center", gap:8,
      padding:"7px 14px", borderBottom:"1px solid #0f172a" }}>
      <span style={{ fontSize:12 }}>{FLAGS[row.symbol]||"🌍"}</span>
      <span style={{ fontSize:12, color:"#94a3b8", flex:1 }}>{NAMES[row.symbol]||row.symbol}</span>
      <span style={{ fontWeight:700, fontSize:13, color:"#f8fafc" }}>{fmtClose(row.close, row.symbol)}</span>
      <span style={{ fontSize:12, fontWeight:700, color:dc, minWidth:60, textAlign:"right" }}>{pct(row.pct_change)}</span>
    </div>
  );
}

function YieldCurve({ rates, spread }: { rates:GRow[]; spread:number|null }) {
  const TENORS = [
    { sym:"US2Y",  l:"2Y",  v:rates.find(r=>r.symbol==="US2Y")?.close??null },
    { sym:"US10Y", l:"10Y", v:rates.find(r=>r.symbol==="US10Y")?.close??null },
    { sym:"US30Y", l:"30Y", v:rates.find(r=>r.symbol==="US30Y")?.close??null },
  ];
  const vals = TENORS.map(t=>t.v).filter(v=>v!=null) as number[];
  if (!vals.length) return null;
  const mn=Math.min(...vals)-0.2, mx=Math.max(...vals)+0.2, rng=mx-mn||1;
  const W=260, H=80, P=28;
  const pts = TENORS.map((t,i) => ({
    x: P + (i/(TENORS.length-1))*(W-2*P),
    y: H - P - (((t.v??mn)-mn)/rng)*(H-2*P),
    ...t,
  }));
  const poly = pts.map(p=>p.x+","+p.y).join(" ");
  const inv  = (TENORS[0].v??0) > (TENORS[2].v??0);
  const lineClr = inv ? "#ef4444" : "#22c55e";
  return (
    <div style={{ padding:"12px 14px", background:"#0f172a", borderRadius:8, marginBottom:10 }}>
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8 }}>
        <span style={{ fontSize:11, fontWeight:700, color:"#64748b" }}>YIELD CURVE</span>
        {spread!=null && (
          <span style={{
            fontSize:10, fontWeight:700, padding:"1px 7px", borderRadius:4,
            background:inv?"#2d1515":"#0f2d1f", color:inv?"#ef4444":"#22c55e",
          }}>
            {inv?"INVERTED":"NORMAL"} 10Y-2Y: {spread>=0?"+":""}{spread.toFixed(2)}%
          </span>
        )}
      </div>
      <svg width={W} height={H}>
        <polyline points={poly} fill="none" stroke={lineClr} strokeWidth={2} />
        {pts.map((p,i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={4} fill={lineClr} />
            <text x={p.x} y={H-4} fontSize={9} fill="#475569" textAnchor="middle">{p.l}</text>
            {p.v!=null && (
              <text x={p.x} y={p.y-8} fontSize={9} fill={lineClr} textAnchor="middle">
                {p.v.toFixed(2)}%
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

function RateChart({ sym, data, color }: { sym:string; data:RHist[]; color:string }) {
  const [hov, setHov] = useState<number|null>(null);
  if (!data||data.length<2) return null;
  const W=260,H=55,P=6;
  const vals=data.map(d=>d.close);
  const mn=Math.min(...vals), mx=Math.max(...vals), rng=mx-mn||0.01;
  const pts=data.map((d,i) => ({
    x: P+(i/(data.length-1))*(W-2*P),
    y: H-P-((d.close-mn)/rng)*(H-2*P),
    ...d,
  }));
  const poly=pts.map(p=>p.x+","+p.y).join(" ");
  const last=data[data.length-1], first=data[0];
  const chg=last.close-first.close;
  return (
    <div style={{ marginBottom:8 }}>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:2 }}>
        <span style={{ fontSize:10, color:"#64748b" }}>{NAMES[sym]||sym}</span>
        <span style={{ fontSize:10, fontWeight:700, color:clr(chg) }}>
          {last.close.toFixed(2)}% ({chg>=0?"+":""}{chg.toFixed(2)})
        </span>
      </div>
      <svg width={W} height={H} style={{ cursor:"crosshair" }} onMouseLeave={()=>setHov(null)}>
        <polyline points={poly} fill="none" stroke={color} strokeWidth={1.5} />
        {hov!=null && pts[hov] && (
          <>
            <line x1={pts[hov].x} y1={0} x2={pts[hov].x} y2={H}
              stroke="#334155" strokeWidth={1} strokeDasharray="3,2" />
            <circle cx={pts[hov].x} cy={pts[hov].y} r={3} fill={color} />
            <text x={Math.min(pts[hov].x+4,W-80)} y={pts[hov].y-4} fontSize={8} fill="#f8fafc">
              {data[hov].date}  {data[hov].close.toFixed(2)}%
            </text>
          </>
        )}
        {pts.map((p,i) => (
          <rect key={i} x={p.x-4} y={0} width={8} height={H}
            fill="transparent" onMouseEnter={()=>setHov(i)} />
        ))}
      </svg>
    </div>
  );
}

function TodayPats() {
  const [pats, setPats] = useState<Pat[]>([]);
  const today = new Date();
  const mmdd  = String(today.getMonth()+1).padStart(2,"0")+"-"+String(today.getDate()).padStart(2,"0");
  useEffect(() => {
    fetch("/api/patterns-v3?anchor="+mmdd+"&min_accuracy=68&min_score=3&limit=8&sort=score")
      .then(r=>r.json()).then(d=>setPats(d.rows||[])).catch(()=>{});
  }, []);
  if (!pats.length) return null;
  return (
    <Panel title={"Patterns Today ("+mmdd+")"} icon="🔬">
      {pats.map((p,i) => {
        const up=p.direction==="UP";
        return (
          <div key={i} style={{ display:"flex", alignItems:"center", gap:8,
            padding:"7px 14px", borderBottom:"1px solid #0f172a" }}>
            <span style={{
              fontSize:9, fontWeight:700, padding:"1px 5px", borderRadius:3,
              background:up?"#0f2d1f":"#2d1515", color:up?"#22c55e":"#ef4444",
            }}>{p.direction}</span>
            <span style={{ fontFamily:"monospace", fontSize:12, fontWeight:700, color:"#60a5fa" }}>
              {p.symbol}
            </span>
            <span style={{ fontSize:11, color:"#64748b" }}>{p.window_days}d</span>
            <span style={{ marginLeft:"auto", fontSize:12, fontWeight:700,
              color:up?"#22c55e":"#ef4444" }}>{p.accuracy.toFixed(0)}%</span>
            <span style={{ fontSize:11, color:"#94a3b8" }}>
              {p.mean_ret>=0?"+":""}{p.mean_ret.toFixed(2)}%
            </span>
          </div>
        );
      })}
      <div style={{ padding:"8px 14px" }}>
        <a href="/patterns-v3" style={{ fontSize:11, color:"#3b82f6" }}>View all →</a>
      </div>
    </Panel>
  );
}

export default function MacroPage() {
  const [g, setG]         = useState<MacroG|null>(null);
  const [loading, setL]   = useState(true);

  const load = useCallback(() => {
    setL(true);
    fetch("/api/macro-global")
      .then(r=>r.json()).then(d=>setG(d)).catch(()=>{})
      .finally(()=>setL(false));
  }, []);

  useEffect(()=>{ load(); },[]);

  const RCOLS = ["#60a5fa","#22c55e","#f472b6"];

  return (
    <div style={{ minHeight:"100vh", background:"#0f172a", color:"#e2e8f0", fontFamily:"system-ui,sans-serif" }}>
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"#f8fafc" }}>Macro Dashboard</h1>
          <p style={{ margin:"4px 0 0", fontSize:12, color:"#64748b" }}>
            Rates · FX · Commodities · Crypto · Seasonal patterns
            {g?.as_of ? " · As of "+g.as_of : ""}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          marginLeft:"auto", padding:"6px 14px", background:"#334155",
          border:"none", borderRadius:7, color:"#94a3b8", cursor:"pointer", fontSize:12,
        }}>{loading?"Loading...":"↺ Refresh"}</button>
      </div>

      <div style={{ padding:"20px 28px", display:"grid",
        gridTemplateColumns:"1fr 1fr 1fr", gap:18 }}>

        {/* Left: rates */}
        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <Panel title="US Rates + Yield Curve" icon="📈">
            <div style={{ padding:"12px 14px" }}>
              <YieldCurve rates={g?.rates||[]} spread={g?.yield_spread??null} />
              {["US2Y","US10Y","US30Y"].map((s,i) => (
                <RateChart key={s} sym={s} data={g?.rates_history?.[s]||[]} color={RCOLS[i]} />
              ))}
            </div>
          </Panel>
          <Panel title="Volatility" icon="⚡">
            {(g?.volatility||[]).map((r,i)=><GRowComp key={i} row={r} inv />)}
          </Panel>
        </div>

        {/* Middle: FX + commodities + crypto */}
        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <Panel title="FX / Currencies" icon="💱">
            {(g?.fx||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
          <Panel title="Commodities" icon="🛢">
            {(g?.commodities||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
          <Panel title="Crypto" icon="₿">
            {(g?.crypto||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
        </div>

        {/* Right: equities + patterns */}
        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <Panel title="Global Equities" icon="🌍">
            {(g?.equities||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
          <TodayPats />
        </div>

      </div>

      {g?.error && (
        <div style={{ padding:"0 28px 20px" }}>
          <div style={{ padding:"10px 14px", background:"#2d1515",
            borderRadius:8, color:"#ef4444", fontSize:12 }}>
            Error: {g.error}
          </div>
        </div>
      )}
    </div>
  );
}
'''
write(SRC / "macro" / "page.tsx", macro_page, "/macro/page.tsx")


# =============================================================================
# [4]  Telegram: add get_todays_patterns_msg helper
# =============================================================================
print("\n[4/4] Patching telegram_bot.py ...")

BOT = MICC / "telegram_bot.py"
if not BOT.exists():
    print("  [SKIP] telegram_bot.py not found")
else:
    src = BOT.read_text(encoding="utf-8")

    if "get_todays_patterns_msg" not in src:
        helper_lines = [
            "",
            "",
            "def get_todays_patterns_msg() -> str:",
            '    """Get today\'s top seasonal patterns for morning brief."""',
            "    import sqlite3",
            "    from datetime import datetime",
            "    today_mmdd = datetime.today().strftime('%m-%d')",
            "    DB_P = r'D:\\marketDB\\db\\market.db'",
            "    try:",
            "        conn = sqlite3.connect(DB_P, timeout=10)",
            "        tables = {r[0] for r in conn.execute(",
            "            \"SELECT name FROM sqlite_master WHERE type='table'\"",
            "        ).fetchall()}",
            "        tbl = 'seasonality_patterns_v3' if 'seasonality_patterns_v3' in tables else 'seasonality_patterns'",
            "        rows = conn.execute(",
            "            'SELECT symbol, window_days, direction, accuracy, mean_ret, score '",
            "            'FROM ' + tbl + ' WHERE anchor_mm_dd=? AND accuracy>=68 AND score>=3 '",
            "            'AND ABS(mean_ret) <= 50 ORDER BY score DESC LIMIT 10',",
            "            (today_mmdd,)",
            "        ).fetchall()",
            "        conn.close()",
            "        if not rows:",
            "            return '_No high-accuracy patterns for ' + today_mmdd + '_'",
            "        lines = ['*Seasonal Patterns (' + today_mmdd + '):*']",
            "        for sym, win, dirn, acc, mean, score in rows:",
            "            ico = 'UP' if dirn == 'UP' else 'DN'",
            "            lines.append(",
            "                f'  {ico} `{sym:<14}` {win}d  {acc:.0f}%  {mean:+.2f}%  s={score:.1f}'",
            "            )",
            "        return '\\n'.join(lines)",
            "    except Exception as e:",
            "        return '_Patterns error: ' + str(e) + '_'",
            "",
        ]
        helper_code = "\n".join(helper_lines)
        src = src.replace("def main():", helper_code + "\ndef main():")
        print("  [OK] Added get_todays_patterns_msg()")
    else:
        print("  [SKIP] get_todays_patterns_msg already present")

    BOT.write_text(src, encoding="utf-8")
    print("  [OK] telegram_bot.py saved")


print("""
=============================================================
BUILD PHASE 20 (FIXED) COMPLETE
=============================================================

[1] D:\\MICC\\fix_pattern_scores.py
    Cleans |mean_ret| > 50% artifacts from patterns table.
    Run: py D:\\MICC\\fix_pattern_scores.py

[2] /api/patterns-v3/route.ts
    Default: max_mean_ret=50 (blocks artifacts)
    New: month filter, sorted properly

[3] /macro/page.tsx
    3-column layout:
      Left:   Yield curve SVG (INVERTED/NORMAL badge)
              US 2Y/10Y/30Y history charts with hover
              VIX / India VIX
      Middle: FX + Commodities + Crypto
      Right:  Global Equities + Today Patterns panel

[4] telegram_bot.py
    Added get_todays_patterns_msg() helper

RUN NOW:
  py D:\\MICC\\fix_pattern_scores.py
  cd D:\\MICC\\micc-dashboard
  npm run dev

  localhost:3000/macro       -- yield curve + global panels
  localhost:3000/patterns-v3 -- clean 1M patterns
=============================================================
""")
