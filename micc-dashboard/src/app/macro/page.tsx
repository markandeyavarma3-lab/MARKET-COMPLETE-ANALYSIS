"use client";
import NavBar from "@/components/NavBar";

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
  US10Y:"",US2Y:"",US30Y:"",
  DXY:"",USDINR:"",EURUSD:"",USDJPY:"",GBPUSD:"",
  Gold:"",CrudeWTI:"",Silver:"",NatGas:"",Copper:"",
  SP500VIX:"",INDIAVIX:"",Bitcoin:"",Ethereum:"",
  SPX:"",NDX:"",NIFTY50:"",Nikkei225:"",DAX:"",
};

const fmtClose = (v:number|null, sym:string) => {
  if (v==null) return "";
  if (["US10Y","US2Y","US30Y"].includes(sym)) return v.toFixed(2)+"%";
  if (["USDINR","EURUSD","USDJPY","GBPUSD"].includes(sym)) return v.toFixed(4);
  if (v>=10000) return v.toLocaleString("en-US",{maximumFractionDigits:0});
  if (v>=100) return v.toFixed(2);
  return v.toFixed(4);
};
const pct = (v:number|null) => v==null?"":(v>=0?"+":"")+v.toFixed(2)+"%";
const clr = (v:number|null, inv=false) =>
  v==null?"var(--muted)":(inv?v<0:v>0)?"var(--pos)":v===0?"var(--muted)":"var(--neg)";

function Panel({ title, icon, children }: { title:string; icon:string; children:React.ReactNode }) {
  return (
    <div style={{ background:"var(--card)", border:"1px solid #334155", borderRadius:6, overflow:"hidden" }}>
      <div style={{ padding:"11px 16px", borderBottom:"1px solid #334155",
        display:"flex", alignItems:"center", gap:8 }}>
        <span>{icon}</span>
        <span style={{ fontSize:11, fontWeight:700, color:"var(--muted)", letterSpacing:0.8, textTransform:"uppercase" }}>
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
      <span style={{ fontSize:12 }}>{FLAGS[row.symbol]||""}</span>
      <span style={{ fontSize:12, color:"var(--muted)", flex:1 }}>{NAMES[row.symbol]||row.symbol}</span>
      <span style={{ fontWeight:700, fontSize:13, color:"var(--text)" }}>{fmtClose(row.close, row.symbol)}</span>
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
  const lineClr = inv ? "var(--neg)" : "var(--pos)";
  return (
    <div style={{ padding:"12px 14px", background:"var(--bg)", borderRadius:8, marginBottom:10 }}>
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8 }}>
        <span style={{ fontSize:11, fontWeight:700, color:"var(--muted)" }}>YIELD CURVE</span>
        {spread!=null && (
          <span style={{
            fontSize:10, fontWeight:700, padding:"1px 7px", borderRadius:4,
            background:inv?"#2d1515":"#0f2d1f", color:inv?"var(--neg)":"var(--pos)",
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
            <text x={p.x} y={H-4} fontSize={9} fill="var(--muted)" textAnchor="middle">{p.l}</text>
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
        <span style={{ fontSize:10, color:"var(--muted)" }}>{NAMES[sym]||sym}</span>
        <span style={{ fontSize:10, fontWeight:700, color:clr(chg) }}>
          {last.close.toFixed(2)}% ({chg>=0?"+":""}{chg.toFixed(2)})
        </span>
      </div>
      <svg width={W} height={H} style={{ cursor:"crosshair" }} onMouseLeave={()=>setHov(null)}>
        <polyline points={poly} fill="none" stroke={color} strokeWidth={1.5} />
        {hov!=null && pts[hov] && (
          <>
            <line x1={pts[hov].x} y1={0} x2={pts[hov].x} y2={H}
              stroke="var(--border2)" strokeWidth={1} strokeDasharray="3,2" />
            <circle cx={pts[hov].x} cy={pts[hov].y} r={3} fill={color} />
            <text x={Math.min(pts[hov].x+4,W-80)} y={pts[hov].y-4} fontSize={8} fill="var(--text)">
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
    <Panel title={"Patterns Today ("+mmdd+")"} icon="">
      {pats.map((p,i) => {
        const up=p.direction==="UP";
        return (
          <div key={i} style={{ display:"flex", alignItems:"center", gap:8,
            padding:"7px 14px", borderBottom:"1px solid #0f172a" }}>
            <span style={{
              fontSize:9, fontWeight:700, padding:"1px 5px", borderRadius:3,
              background:up?"#0f2d1f":"#2d1515", color:up?"var(--pos)":"var(--neg)",
            }}>{p.direction}</span>
            <span style={{ fontFamily:"monospace", fontSize:12, fontWeight:700, color:"var(--accent)" }}>
              {p.symbol}
            </span>
            <span style={{ fontSize:11, color:"var(--muted)" }}>{p.window_days}d</span>
            <span style={{ marginLeft:"auto", fontSize:12, fontWeight:700,
              color:up?"var(--pos)":"var(--neg)" }}>{p.accuracy.toFixed(0)}%</span>
            <span style={{ fontSize:11, color:"var(--muted)" }}>
              {p.mean_ret>=0?"+":""}{p.mean_ret.toFixed(2)}%
            </span>
          </div>
        );
      })}
      <div style={{ padding:"8px 14px" }}>
        <a href="/patterns-v3" style={{ fontSize:11, color:"var(--accent)" }}>View all </a>
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

  const RCOLS = ["var(--accent)","var(--pos)","#f472b6"];

  return (
    <div style={{ minHeight:"100vh", background:"var(--bg)", color:"var(--text)", fontFamily:"'Space Grotesk',sans-serif" }}>
      <NavBar />
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"var(--text)" }}>Macro Dashboard</h1>
          <p style={{ margin:"4px 0 0", fontSize:12, color:"var(--muted)" }}>
            Rates  FX  Commodities  Crypto  Seasonal patterns
            {g?.as_of ? "  As of "+g.as_of : ""}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          marginLeft:"auto", padding:"6px 14px", background:"var(--border2)",
          border:"none", borderRadius:7, color:"var(--muted)", cursor:"pointer", fontSize:12,
        }}>{loading?"Loading...":" Refresh"}</button>
      </div>

      <div style={{ padding:"20px 28px", display:"grid",
        gridTemplateColumns:"1fr 1fr 1fr", gap:18 }}>

        {/* Left: rates */}
        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <Panel title="US Rates + Yield Curve" icon="">
            <div style={{ padding:"12px 14px" }}>
              <YieldCurve rates={g?.rates||[]} spread={g?.yield_spread??null} />
              {["US2Y","US10Y","US30Y"].map((s,i) => (
                <RateChart key={s} sym={s} data={g?.rates_history?.[s]||[]} color={RCOLS[i]} />
              ))}
            </div>
          </Panel>
          <Panel title="Volatility" icon="">
            {(g?.volatility||[]).map((r,i)=><GRowComp key={i} row={r} inv />)}
          </Panel>
        </div>

        {/* Middle: FX + commodities + crypto */}
        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <Panel title="FX / Currencies" icon="">
            {(g?.fx||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
          <Panel title="Commodities" icon="">
            {(g?.commodities||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
          <Panel title="Crypto" icon="">
            {(g?.crypto||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
        </div>

        {/* Right: equities + patterns */}
        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <Panel title="Global Equities" icon="">
            {(g?.equities||[]).map((r,i)=><GRowComp key={i} row={r} />)}
          </Panel>
          <TodayPats />
        </div>

      </div>

      {g?.error && (
        <div style={{ padding:"0 28px 20px" }}>
          <div style={{ padding:"10px 14px", background:"#2d1515",
            borderRadius:8, color:"var(--neg)", fontSize:12 }}>
            Error: {g.error}
          </div>
        </div>
      )}
    </div>
  );
}
