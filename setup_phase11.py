# -*- coding: utf-8 -*-
"""
setup_phase11.py  --  Run from D:\\MICC
Builds the Calendar Patterns dashboard.
Run AFTER build_calendar_patterns.py has finished.
Run: py D:\\MICC\\setup_phase11.py
"""

from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
APP  = DASH / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# [1] /api/patterns/route.ts
# =============================================================================
print("\n[1/3] /api/patterns/route.ts")

write(APP / "api" / "patterns" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 20000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[patterns]', r.stderr?.slice(0,300)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out.replace(/:\s*NaN\b/g,': null').replace(/:\s*Infinity\b/g,': null'))
  } catch(e) { console.error('[patterns]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym       = (searchParams.get('symbol') || '').toUpperCase().trim()
  const direction = searchParams.get('direction') || 'both'   // up | down | both
  const minAcc    = parseFloat(searchParams.get('min_acc') || '0.70')
  const minYears  = parseInt(searchParams.get('min_years') || '3')

  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  // Check if patterns exist for this symbol
  const check = qdb(
    `SELECT COUNT(*) as n FROM calendar_patterns WHERE symbol=?`, [sym]
  )
  const total_n = (check[0] as Record<string,unknown>)?.n as number || 0

  if (total_n === 0) {
    return NextResponse.json({
      ok: false,
      error: `No calendar patterns for ${sym}. Run: py D:\\MICC\\build_calendar_patterns.py --test`,
      not_computed: true,
    }, { status: 404 })
  }

  // Build direction filter
  const dirFilter = direction === 'both' ? "direction IN ('up','down')"
                  : direction === 'up'   ? "direction='up'"
                  :                        "direction='down'"

  // Fetch patterns
  const patterns = qdb(`
    SELECT
      direction, window_days, start_slot, end_slot,
      start_label, end_label,
      n_years, n_hit, accuracy,
      avg_return, avg_return_all,
      min_return, max_return, std_return, median_return,
      best_year, worst_year, confidence
    FROM calendar_patterns
    WHERE symbol=?
      AND ${dirFilter}
      AND accuracy >= ?
      AND n_years >= ?
    ORDER BY accuracy DESC, n_years DESC
    LIMIT 200
  `, [sym, minAcc, minYears])

  // Summary stats
  const summary = qdb(`
    SELECT
      direction,
      COUNT(*) as n_patterns,
      AVG(accuracy) as avg_acc,
      MAX(accuracy) as max_acc,
      AVG(n_years) as avg_years
    FROM calendar_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction
  `, [sym, minAcc, minYears])

  // Distribution: how many patterns by accuracy bucket
  const accDist = qdb(`
    SELECT
      direction,
      SUM(CASE WHEN accuracy >= 0.90 THEN 1 ELSE 0 END) as acc_90,
      SUM(CASE WHEN accuracy >= 0.85 AND accuracy < 0.90 THEN 1 ELSE 0 END) as acc_85,
      SUM(CASE WHEN accuracy >= 0.80 AND accuracy < 0.85 THEN 1 ELSE 0 END) as acc_80,
      SUM(CASE WHEN accuracy >= 0.75 AND accuracy < 0.80 THEN 1 ELSE 0 END) as acc_75,
      SUM(CASE WHEN accuracy >= 0.70 AND accuracy < 0.75 THEN 1 ELSE 0 END) as acc_70
    FROM calendar_patterns WHERE symbol=? GROUP BY direction
  `, [sym])

  // By window distribution
  const byWindow = qdb(`
    SELECT direction, window_days,
           COUNT(*) as n, AVG(accuracy) as avg_acc, MAX(accuracy) as max_acc
    FROM calendar_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction, window_days ORDER BY direction, window_days
  `, [sym, minAcc, minYears])

  // Latest price for context
  const price = qdb(
    `SELECT close, date FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`, [sym]
  )
  const priceIdx = price.length === 0 ? qdb(
    `SELECT close, date FROM market_snapshot WHERE index_name=? ORDER BY date DESC LIMIT 1`, [sym]
  ) : []

  // What trading day of year are we on right now?
  const currentDayOfYear = qdb(`
    SELECT COUNT(*) as day_of_year
    FROM stock_data
    WHERE symbol=?
      AND date >= date(MAX(date), 'start of year')
      AND date <= MAX(date)
  `, [sym])

  return NextResponse.json({
    ok: true,
    symbol: sym,
    total_patterns: total_n,
    patterns,
    summary,
    acc_distribution: accDist,
    by_window: byWindow,
    latest_price: price[0] || priceIdx[0] || null,
    current_day_of_year: (currentDayOfYear[0] as Record<string,unknown>)?.day_of_year || null,
    filters: { min_acc: minAcc, min_years: minYears, direction },
  })
}
""")


# =============================================================================
# [2] /patterns/page.tsx
# =============================================================================
print("\n[2/3] /patterns/page.tsx")

write(APP / "patterns" / "page.tsx", r"""
"use client";
import React, { useState, useCallback, useRef } from "react";

// ── Types ──────────────────────────────────────────────────────────────────
interface Pattern {
  direction:      "up"|"down";
  window_days:    number;
  start_slot:     number;
  end_slot:       number;
  start_label:    string;
  end_label:      string;
  n_years:        number;
  n_hit:          number;
  accuracy:       number;
  avg_return:     number;
  avg_return_all: number;
  min_return:     number;
  max_return:     number;
  std_return:     number;
  median_return:  number;
  best_year:      number;
  worst_year:     number;
  confidence:     string;
}
interface Summary {
  direction:   string;
  n_patterns:  number;
  avg_acc:     number;
  max_acc:     number;
  avg_years:   number;
}
interface AccDist {
  direction: string;
  acc_90:number; acc_85:number; acc_80:number; acc_75:number; acc_70:number;
}
interface ByWindow {
  direction:string; window_days:number; n:number; avg_acc:number; max_acc:number;
}
interface PatternData {
  ok:              boolean;
  error?:          string;
  not_computed?:   boolean;
  symbol:          string;
  total_patterns:  number;
  patterns:        Pattern[];
  summary:         Summary[];
  acc_distribution:AccDist[];
  by_window:       ByWindow[];
  latest_price:    {close:number;date:string}|null;
  current_day_of_year: number|null;
  filters:         {min_acc:number;min_years:number;direction:string};
}
interface Sug { symbol:string; name:string; sector:string; type:string; }

// ── Constants ──────────────────────────────────────────────────────────────
const G="#4ade80",R="#f87171",CY="#22d3ee",YL="#facc15",OR="#f97316";
const W9="#94a3b8",WHT="#e2e8f0";
const DIM="var(--text-tertiary)",PRI="var(--text-primary)",BOR="var(--border-color)",SUR="var(--surface-card)";

const pct=(v:unknown,d=1)=>v==null?"--":`${(+(v as number))>=0?"+":""}${(+(v as number)).toFixed(d)}%`;
const num=(v:unknown,d=2)=>v==null?"--":(+(v as number)).toFixed(d);
const col=(v:unknown)=>(+(v as number)??0)>=0?G:R;

function confColor(c:string){return c==="VERY HIGH"?G:c==="HIGH"?"#4ade80bb":c==="GOOD"?YL:c==="MODERATE"?OR:W9;}

// ── Autocomplete ──────────────────────────────────────────────────────────
function AInput({value,onChange,onSelect,placeholder}:{
  value:string;onChange:(v:string)=>void;onSelect:(s:string)=>void;placeholder:string;
}){
  const [sugg,setSugg]=useState<Sug[]>([]);
  const [show,setShow]=useState(false);
  const [hi,setHi]=useState(-1);
  const tmr=useRef<ReturnType<typeof setTimeout>|null>(null);
  const fetch_=useCallback(async(q:string)=>{
    if(q.length<1){setSugg([]);return;}
    try{const r=await fetch(`/api/search?q=${encodeURIComponent(q.toUpperCase())}&type=stock`,{cache:"no-store"});const d=await r.json();setSugg(d.results||[]);setShow(true);}catch{setSugg([]);}
  },[]);
  const change=(v:string)=>{onChange(v);setHi(-1);if(tmr.current)clearTimeout(tmr.current);tmr.current=setTimeout(()=>fetch_(v),180);};
  const pick=(s:string)=>{onChange(s);onSelect(s);setShow(false);setSugg([]);setHi(-1);};
  const onKey=(e:React.KeyboardEvent)=>{
    if(e.key==="ArrowDown"){e.preventDefault();setHi(i=>Math.min(i+1,sugg.length-1));}
    else if(e.key==="ArrowUp"){e.preventDefault();setHi(i=>Math.max(i-1,-1));}
    else if(e.key==="Enter"){e.preventDefault();if(hi>=0&&sugg[hi])pick(sugg[hi].symbol);else{onSelect(value);setShow(false);}}
    else if(e.key==="Escape")setShow(false);
  };
  return(
    <div style={{position:"relative",flex:1}}>
      <input value={value} onChange={e=>change(e.target.value.toUpperCase())} onKeyDown={onKey}
        onBlur={()=>setTimeout(()=>setShow(false),200)} placeholder={placeholder} autoFocus
        style={{width:"100%",background:SUR,border:`1px solid ${BOR}`,color:PRI,
          borderRadius:show&&sugg.length>0?"8px 8px 0 0":"8px",padding:"12px 16px",fontSize:14,boxSizing:"border-box"}}/>
      {show&&sugg.length>0&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,background:"#0d1520",
          border:`1px solid ${BOR}`,borderTop:"none",borderRadius:"0 0 8px 8px",maxHeight:280,overflowY:"auto",
          boxShadow:"0 8px 32px rgba(0,0,0,0.7)"}}>
          {sugg.map((s,i)=>(
            <div key={s.symbol} onMouseDown={()=>pick(s.symbol)} style={{padding:"9px 14px",cursor:"pointer",
              display:"flex",alignItems:"center",gap:10,
              background:i===hi?`${CY}18`:"transparent",
              borderBottom:i<sugg.length-1?`1px solid ${BOR}22`:"none"}}>
              <span style={{color:CY,fontWeight:800,fontSize:13,minWidth:90,fontFamily:"monospace"}}>{s.symbol}</span>
              <span style={{color:WHT,fontSize:12,flex:1}}>{s.name!==s.symbol?s.name:""}</span>
              {s.sector&&<span style={{color:W9,fontSize:10}}>{s.sector}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────
function Card({title,children,accent}:{title?:string;children:React.ReactNode;accent?:string}){
  return(
    <div style={{background:SUR,border:`1px solid ${accent||BOR}`,borderRadius:8,marginBottom:14,overflow:"hidden"}}>
      {title&&<div style={{padding:"10px 16px",fontSize:11,fontWeight:700,letterSpacing:1.4,color:accent||CY,textTransform:"uppercase",borderBottom:`1px solid ${BOR}`}}>{title}</div>}
      <div style={{padding:"14px 16px"}}>{children}</div>
    </div>
  );
}

// ── Accuracy Distribution Bar ─────────────────────────────────────────────
function AccDistBar({dist,dir}:{dist:AccDist|undefined;dir:"up"|"down"}){
  if(!dist) return null;
  const AC=dir==="up"?G:R;
  const total=dist.acc_90+dist.acc_85+dist.acc_80+dist.acc_75+dist.acc_70;
  if(!total) return null;
  const buckets=[
    {label:">=90%",val:dist.acc_90,color:G},
    {label:"85-90%",val:dist.acc_85,color:"#4ade80bb"},
    {label:"80-85%",val:dist.acc_80,color:YL},
    {label:"75-80%",val:dist.acc_75,color:OR},
    {label:"70-75%",val:dist.acc_70,color:W9},
  ];
  return(
    <div style={{marginBottom:12}}>
      <div style={{fontSize:11,color:W9,fontWeight:600,marginBottom:6}}>
        {dir==="up"?"UP":"DOWN"} Pattern Accuracy Distribution ({total} total)
      </div>
      <div style={{display:"flex",height:24,borderRadius:4,overflow:"hidden",gap:1}}>
        {buckets.map(b=>b.val>0&&(
          <div key={b.label} title={`${b.label}: ${b.val}`}
            style={{flex:b.val,background:b.color,opacity:0.85,display:"flex",alignItems:"center",justifyContent:"center",fontSize:9,fontWeight:700,color:"#000",minWidth:b.val>0?20:0}}>
            {b.val>0?b.val:""}
          </div>
        ))}
      </div>
      <div style={{display:"flex",gap:12,marginTop:5,flexWrap:"wrap"}}>
        {buckets.map(b=><span key={b.label} style={{fontSize:10,color:b.color}}>
          <span style={{fontWeight:700}}>{b.val}</span> {b.label}
        </span>)}
      </div>
    </div>
  );
}

// ── Window Heatmap ────────────────────────────────────────────────────────
function WindowHeatmap({byWindow,dir}:{byWindow:ByWindow[];dir:"up"|"down"}){
  const filtered=byWindow.filter(b=>b.direction===dir);
  if(!filtered.length) return <div style={{color:DIM,fontSize:12}}>No patterns</div>;
  const maxN=Math.max(...filtered.map(b=>b.n));
  return(
    <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
      {filtered.map(b=>{
        const intensity=b.n/maxN;
        const AC=dir==="up"?G:R;
        return(
          <div key={b.window_days} style={{
            background:`${AC}${Math.floor(intensity*60+20).toString(16).padStart(2,"0")}`,
            border:`1px solid ${AC}44`,borderRadius:6,padding:"8px 12px",minWidth:80,textAlign:"center",
          }}>
            <div style={{fontSize:12,fontWeight:700,color:WHT}}>{b.window_days}d</div>
            <div style={{fontSize:11,color:AC,fontWeight:700}}>{b.n} patterns</div>
            <div style={{fontSize:10,color:W9}}>avg {(b.avg_acc*100).toFixed(0)}%</div>
            <div style={{fontSize:10,color:W9}}>max {(b.max_acc*100).toFixed(0)}%</div>
          </div>
        );
      })}
    </div>
  );
}

// ── Timeline Chart (slot position along year) ─────────────────────────────
function TimelineChart({patterns,dir}:{patterns:Pattern[];dir:"up"|"down"}){
  const filtered=patterns.filter(p=>p.direction===dir).slice(0,60);
  if(!filtered.length) return null;
  const AC=dir==="up"?G:R;
  const W=600,H=180,ML=10,MR=10,MT=20,MB=30;
  const PW=W-ML-MR;
  const MAX_SLOT=252;
  const tx=(slot:number)=>ML+(slot/MAX_SLOT)*PW;

  // Group by accuracy bucket for y-position
  const byConf:Record<string,number>={"VERY HIGH":0,"HIGH":1,"GOOD":2,"MODERATE":3,"LOW":4};
  const rowH=(H-MT-MB)/5;

  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>Each bar = one pattern. X-axis = position in trading year (1..252). Y = confidence level. Hover to see details.</div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {/* Y axis labels */}
        {Object.entries(byConf).map(([label,row])=>(
          <text key={label} x={ML-2} y={MT+row*rowH+rowH/2+4} textAnchor="start" fontSize={8} fill={W9}>{label.slice(0,4)}</text>
        ))}
        {/* X axis */}
        <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
        {[1,63,126,189,252].map(slot=>{
          const months=["Jan","Apr","Jul","Oct","Dec"];
          const idx=Math.floor(slot/63);
          return(
            <g key={slot}>
              <line x1={tx(slot)} y1={H-MB} x2={tx(slot)} y2={H-MB+4} stroke="#ffffff30" strokeWidth={1}/>
              <text x={tx(slot)} y={H-MB+14} textAnchor="middle" fontSize={9} fill={W9}>{months[Math.min(idx,4)]}</text>
            </g>
          );
        })}

        {/* Patterns as bars */}
        {filtered.map((p,i)=>{
          const row=byConf[p.confidence]??3;
          const y=MT+row*rowH+2;
          const bh=rowH-4;
          const x1=tx(p.start_slot);
          const x2=tx(Math.min(p.end_slot,MAX_SLOT));
          const bw=Math.max(2,x2-x1);
          const opacity=0.5+p.accuracy*0.5;
          return(
            <rect key={i} x={x1} y={y} width={bw} height={bh}
              fill={AC} opacity={opacity} rx={1}>
              <title>{p.start_label}-{p.end_label} {p.window_days}d {(p.accuracy*100).toFixed(0)}% ({p.n_hit}/{p.n_years}yr) avg{pct(p.avg_return_all)}</title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}

// ── Pattern Cards ─────────────────────────────────────────────────────────
function PatternCard({p}:{p:Pattern}){
  const AC=p.direction==="up"?G:R;
  const barW=Math.min(100,p.accuracy*100);
  const confC=confColor(p.confidence);

  return(
    <div style={{
      padding:"14px 16px",marginBottom:10,
      background:`${AC}0c`,border:`1px solid ${AC}25`,
      borderRadius:8,borderLeft:`4px solid ${AC}`,
    }}>
      {/* Header row */}
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:8,flexWrap:"wrap"}}>
        <div style={{fontWeight:900,fontSize:18,color:WHT,minWidth:44}}>{p.window_days}d</div>
        <div style={{fontWeight:600,fontSize:13,color:W9}}>
          {p.start_label} &rarr; {p.end_label}
        </div>
        <div style={{flex:1}}>
          <div style={{display:"flex",alignItems:"baseline",gap:8}}>
            <span style={{fontWeight:900,fontSize:22,color:confC}}>{(p.accuracy*100).toFixed(0)}%</span>
            <span style={{fontSize:12,color:DIM}}>accurate</span>
            <span style={{fontSize:13,color:WHT,fontWeight:600}}>
              ({p.n_hit}/{p.n_years} years went {p.direction.toUpperCase()})
            </span>
          </div>
          {/* Accuracy bar */}
          <div style={{height:6,background:`${BOR}33`,borderRadius:3,marginTop:4,maxWidth:320}}>
            <div style={{height:6,width:`${barW}%`,background:confC,borderRadius:3,transition:"width 0.4s"}}/>
          </div>
        </div>
        <div style={{fontSize:10,fontWeight:700,padding:"2px 8px",borderRadius:3,background:`${confC}22`,color:confC,letterSpacing:1,whiteSpace:"nowrap"}}>{p.confidence}</div>
      </div>

      {/* Stats grid */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:8}}>
        {[
          {l:"Avg Return (all years)",v:pct(p.avg_return_all),c:col(p.avg_return_all)},
          {l:`Avg When ${p.direction.toUpperCase()}`,v:pct(p.avg_return),c:p.direction==="up"?G:R},
          {l:"Median Return",v:pct(p.median_return),c:col(p.median_return)},
          {l:"Best Year Return",v:pct(p.max_return),c:G},
          {l:"Worst Year Return",v:pct(p.min_return),c:R},
          {l:"Std Dev",v:pct(p.std_return)},
          {l:"Best Year",v:String(p.best_year||"--")},
          {l:"Worst Year",v:String(p.worst_year||"--")},
        ].map(({l,v,c})=>(
          <div key={l} style={{background:`${BOR}22`,borderRadius:5,padding:"7px 10px"}}>
            <div style={{fontSize:9,color:DIM,fontWeight:700,marginBottom:2,textTransform:"uppercase",letterSpacing:0.8}}>{l}</div>
            <div style={{fontSize:14,fontWeight:800,color:c||PRI}}>{v}</div>
          </div>
        ))}
      </div>

      {/* Mini return bar chart (min to max) */}
      <div style={{marginTop:10}}>
        <div style={{fontSize:10,color:W9,marginBottom:4}}>Return range: worst to best</div>
        <div style={{position:"relative",height:12,background:`${BOR}22`,borderRadius:6}}>
          {(()=>{
            const mn=p.min_return,mx=p.max_return,rng=mx-mn||1;
            const zeroPos=(-mn/rng)*100;
            const avgPos=(p.avg_return_all-mn)/rng*100;
            return(
              <>
                <div style={{position:"absolute",left:`${Math.min(100,Math.max(0,zeroPos))}%`,top:0,bottom:0,width:1,background:W9,opacity:0.5}}/>
                <div style={{position:"absolute",left:`${Math.min(100,Math.max(0,avgPos-1))}%`,top:0,bottom:0,width:2,background:YL,borderRadius:1}}/>
                <div style={{
                  position:"absolute",
                  left:`${Math.max(0,-mn/rng*100)}%`,
                  width:`${Math.min(100,p.avg_return_all/rng*100)}%`,
                  top:"20%",bottom:"20%",
                  background:p.avg_return_all>=0?`${G}88`:`${R}88`,
                  borderRadius:3,
                }}/>
              </>
            );
          })()}
        </div>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:9,color:W9,marginTop:2}}>
          <span style={{color:R}}>{pct(p.min_return)}</span>
          <span style={{color:YL}}>avg {pct(p.avg_return_all)}</span>
          <span style={{color:G}}>{pct(p.max_return)}</span>
        </div>
      </div>
    </div>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────
function FilterBar({minAcc,setMinAcc,minYears,setMinYears,dir,setDir,windowFilter,setWindowFilter,sortBy,setSortBy}:{
  minAcc:number;setMinAcc:(v:number)=>void;
  minYears:number;setMinYears:(v:number)=>void;
  dir:string;setDir:(v:string)=>void;
  windowFilter:number;setWindowFilter:(v:number)=>void;
  sortBy:string;setSortBy:(v:string)=>void;
}){
  const WINDOWS=[0,5,7,10,12,15,18,20,25,30,35,40,45,50,60,75,90];
  return(
    <div style={{display:"flex",gap:12,flexWrap:"wrap",alignItems:"center",marginBottom:14,padding:"12px 14px",background:`${BOR}22`,borderRadius:8}}>
      <div>
        <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:4}}>Min Accuracy</div>
        <div style={{display:"flex",gap:4}}>
          {[0.70,0.75,0.80,0.85,0.90].map(v=>(
            <button key={v} onClick={()=>setMinAcc(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:minAcc===v?CY:"transparent",color:minAcc===v?"#000":W9}}>{(v*100).toFixed(0)}%</button>
          ))}
        </div>
      </div>
      <div>
        <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:4}}>Min Years</div>
        <div style={{display:"flex",gap:4}}>
          {[3,5,7,10,15].map(v=>(
            <button key={v} onClick={()=>setMinYears(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:minYears===v?CY:"transparent",color:minYears===v?"#000":W9}}>{v}+</button>
          ))}
        </div>
      </div>
      <div>
        <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:4}}>Direction</div>
        <div style={{display:"flex",gap:4}}>
          {[["both","Both"],["up","UP Only"],["down","DOWN Only"]].map(([v,l])=>(
            <button key={v} onClick={()=>setDir(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:dir===v?CY:"transparent",color:dir===v?"#000":W9}}>{l}</button>
          ))}
        </div>
      </div>
      <div>
        <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:4}}>Window</div>
        <select value={windowFilter} onChange={e=>setWindowFilter(+e.target.value)}
          style={{background:"transparent",border:`1px solid ${BOR}`,color:PRI,borderRadius:4,padding:"3px 8px",fontSize:11}}>
          <option value={0}>All</option>
          {WINDOWS.slice(1).map(w=><option key={w} value={w}>{w}d</option>)}
        </select>
      </div>
      <div>
        <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:4}}>Sort By</div>
        <div style={{display:"flex",gap:4}}>
          {[["accuracy","Accuracy"],["n_hit","Hits"],["window_days","Window"],["avg_return_all","Avg Ret"]].map(([v,l])=>(
            <button key={v} onClick={()=>setSortBy(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:sortBy===v?CY:"transparent",color:sortBy===v?"#000":W9}}>{l}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════
export default function PatternsPage(){
  const [symInput,setSymInput] = useState("");
  const [data,setData]         = useState<PatternData|null>(null);
  const [loading,setLoading]   = useState(false);
  const [error,setError]       = useState<string|null>(null);
  const [minAcc,setMinAcc]     = useState(0.70);
  const [minYears,setMinYears] = useState(3);
  const [dir,setDir]           = useState("both");
  const [windowFilter,setWindowFilter] = useState(0);
  const [sortBy,setSortBy]     = useState("accuracy");
  const [activeDir,setActiveDir] = useState<"up"|"down"|"both">("both");

  const load = useCallback(async(sym:string) => {
    if(!sym.trim()) return;
    setLoading(true); setError(null); setData(null);
    try {
      const r = await fetch(
        `/api/patterns?symbol=${encodeURIComponent(sym.trim().toUpperCase())}&min_acc=${minAcc}&min_years=${minYears}&direction=${dir}`,
        {cache:"no-store"}
      );
      const d = await r.json();
      if(!d.ok) throw new Error(d.error||"API error");
      setData(d);
    } catch(e:unknown){ setError(String(e)); }
    finally { setLoading(false); }
  },[minAcc,minYears,dir]);

  // Apply client-side filters
  const filteredPatterns = (data?.patterns||[])
    .filter(p => activeDir==="both" || p.direction===activeDir)
    .filter(p => windowFilter===0 || p.window_days===windowFilter)
    .sort((a,b) => {
      if(sortBy==="accuracy")     return b.accuracy-a.accuracy;
      if(sortBy==="n_hit")        return b.n_hit-a.n_hit;
      if(sortBy==="window_days")  return a.window_days-b.window_days;
      if(sortBy==="avg_return_all") return b.avg_return_all-a.avg_return_all;
      return 0;
    });

  const upPatterns   = filteredPatterns.filter(p=>p.direction==="up");
  const downPatterns = filteredPatterns.filter(p=>p.direction==="down");

  const upSum   = data?.summary.find(s=>s.direction==="up");
  const dnSum   = data?.summary.find(s=>s.direction==="down");
  const upDist  = data?.acc_distribution.find(s=>s.direction==="up");
  const dnDist  = data?.acc_distribution.find(s=>s.direction==="down");

  return(
    <div style={{maxWidth:1200,margin:"0 auto",padding:"20px 16px"}}>
      {/* Header */}
      <div style={{marginBottom:16}}>
        <h1 style={{margin:0,fontSize:24,fontWeight:900,letterSpacing:-0.5}}>CALENDAR PATTERNS</h1>
        <div style={{color:DIM,fontSize:12,marginTop:3}}>
          Recurring calendar durations where a stock historically goes UP or DOWN -- computed from all available years
        </div>
      </div>

      {/* Search */}
      <div style={{display:"flex",gap:8,marginBottom:14}}>
        <AInput value={symInput} onChange={setSymInput}
          onSelect={s=>{setSymInput(s);load(s);}}
          placeholder="Type stock name or symbol (e.g. HDFC Bank, Reliance, TCS)..."
        />
        <button onClick={()=>load(symInput)} disabled={loading} style={{
          background:CY,color:"#000",border:"none",borderRadius:8,
          padding:"12px 22px",fontWeight:800,cursor:"pointer",fontSize:14,
          opacity:loading?0.6:1,minWidth:110,
        }}>{loading?"Loading...":"Find Patterns"}</button>
      </div>

      {/* Filters */}
      <FilterBar minAcc={minAcc} setMinAcc={setMinAcc} minYears={minYears} setMinYears={setMinYears}
        dir={dir} setDir={setDir} windowFilter={windowFilter} setWindowFilter={setWindowFilter}
        sortBy={sortBy} setSortBy={setSortBy}
      />

      {error && (
        <div style={{color:R,fontSize:13,marginBottom:12,padding:"10px 14px",background:`${R}11`,borderRadius:6,border:`1px solid ${R}33`}}>
          {error}
          {(data as unknown as {not_computed?:boolean})?.not_computed && (
            <div style={{marginTop:6,fontSize:12,color:W9}}>
              Run this first: <code style={{color:CY}}>py D:\MICC\build_calendar_patterns.py --test</code> to test with a few stocks,
              or <code style={{color:CY}}>py D:\MICC\build_calendar_patterns.py</code> to process all stocks.
            </div>
          )}
        </div>
      )}

      {loading && <div style={{padding:40,textAlign:"center",color:DIM}}>Loading patterns for {symInput}...</div>}

      {data && !loading && (
        <div>
          {/* Summary header */}
          <div style={{display:"flex",gap:12,flexWrap:"wrap",marginBottom:16}}>
            {/* Symbol info */}
            <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"14px 18px",flex:1,minWidth:200}}>
              <div style={{fontSize:22,fontWeight:900,color:CY,marginBottom:4}}>{data.symbol}</div>
              {data.latest_price&&<div style={{fontSize:13,color:W9}}>Price: <span style={{color:WHT,fontWeight:700}}>{(data.latest_price.close||0).toLocaleString("en-IN",{maximumFractionDigits:2})}</span> &bull; {data.latest_price.date}</div>}
              <div style={{fontSize:12,color:DIM,marginTop:4}}>{data.total_patterns} total patterns in DB</div>
            </div>

            {/* UP summary */}
            {upSum&&<div style={{background:`${G}0f`,border:`1px solid ${G}33`,borderRadius:8,padding:"14px 18px",flex:1,minWidth:180}}>
              <div style={{fontSize:12,fontWeight:700,color:G,letterSpacing:1,marginBottom:6}}>UP PATTERNS</div>
              <div style={{fontSize:26,fontWeight:900,color:G}}>{upSum.n_patterns}</div>
              <div style={{fontSize:12,color:W9}}>Avg accuracy: <span style={{color:G,fontWeight:700}}>{(upSum.avg_acc*100).toFixed(1)}%</span></div>
              <div style={{fontSize:12,color:W9}}>Best: <span style={{color:G,fontWeight:700}}>{(upSum.max_acc*100).toFixed(1)}%</span></div>
            </div>}

            {/* DOWN summary */}
            {dnSum&&<div style={{background:`${R}0f`,border:`1px solid ${R}33`,borderRadius:8,padding:"14px 18px",flex:1,minWidth:180}}>
              <div style={{fontSize:12,fontWeight:700,color:R,letterSpacing:1,marginBottom:6}}>DOWN PATTERNS</div>
              <div style={{fontSize:26,fontWeight:900,color:R}}>{dnSum.n_patterns}</div>
              <div style={{fontSize:12,color:W9}}>Avg accuracy: <span style={{color:R,fontWeight:700}}>{(dnSum.avg_acc*100).toFixed(1)}%</span></div>
              <div style={{fontSize:12,color:W9}}>Best: <span style={{color:R,fontWeight:700}}>{(dnSum.max_acc*100).toFixed(1)}%</span></div>
            </div>}
          </div>

          {/* Accuracy distributions */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"14px 16px"}}>
              <AccDistBar dist={upDist} dir="up"/>
            </div>
            <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"14px 16px"}}>
              <AccDistBar dist={dnDist} dir="down"/>
            </div>
          </div>

          {/* Window heatmaps */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            <div style={{background:SUR,border:`1px solid ${G}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:G,letterSpacing:1.2,marginBottom:10}}>UP PATTERNS BY WINDOW</div>
              <WindowHeatmap byWindow={data.by_window} dir="up"/>
            </div>
            <div style={{background:SUR,border:`1px solid ${R}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:R,letterSpacing:1.2,marginBottom:10}}>DOWN PATTERNS BY WINDOW</div>
              <WindowHeatmap byWindow={data.by_window} dir="down"/>
            </div>
          </div>

          {/* Timeline charts */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            <div style={{background:SUR,border:`1px solid ${G}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:G,letterSpacing:1.2,marginBottom:8}}>UP PATTERNS -- POSITION IN YEAR</div>
              <TimelineChart patterns={filteredPatterns} dir="up"/>
            </div>
            <div style={{background:SUR,border:`1px solid ${R}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:R,letterSpacing:1.2,marginBottom:8}}>DOWN PATTERNS -- POSITION IN YEAR</div>
              <TimelineChart patterns={filteredPatterns} dir="down"/>
            </div>
          </div>

          {/* Direction tabs */}
          <div style={{display:"flex",gap:6,marginBottom:12}}>
            {([["both",`All (${filteredPatterns.length})`],["up",`UP (${upPatterns.length})`],["down",`DOWN (${downPatterns.length})`]] as const).map(([v,l])=>(
              <button key={v} onClick={()=>setActiveDir(v)} style={{
                padding:"7px 16px",borderRadius:6,fontSize:12,fontWeight:700,cursor:"pointer",border:"1px solid",
                background:activeDir===v?(v==="down"?R:v==="up"?G:CY):"transparent",
                color:activeDir===v?"#000":DIM,
                borderColor:activeDir===v?(v==="down"?R:v==="up"?G:CY):BOR,
              }}>{l}</button>
            ))}
          </div>

          {/* Pattern cards */}
          {filteredPatterns.length===0?(
            <div style={{color:DIM,fontSize:13,padding:"30px 0",textAlign:"center"}}>
              No patterns match the current filters. Try lowering the accuracy threshold.
            </div>
          ):(
            <div>
              {activeDir==="both"&&(
                <>
                  {upPatterns.length>0&&(
                    <div style={{marginBottom:20}}>
                      <div style={{fontSize:13,fontWeight:700,color:G,letterSpacing:1,marginBottom:10}}>
                        UP PATTERNS ({upPatterns.length}) -- Historically rises in these windows
                      </div>
                      {upPatterns.map((p,i)=><PatternCard key={`up-${i}`} p={p}/>)}
                    </div>
                  )}
                  {downPatterns.length>0&&(
                    <div>
                      <div style={{fontSize:13,fontWeight:700,color:R,letterSpacing:1,marginBottom:10}}>
                        DOWN PATTERNS ({downPatterns.length}) -- Historically falls in these windows
                      </div>
                      {downPatterns.map((p,i)=><PatternCard key={`dn-${i}`} p={p}/>)}
                    </div>
                  )}
                </>
              )}
              {activeDir==="up"&&upPatterns.map((p,i)=><PatternCard key={i} p={p}/>)}
              {activeDir==="down"&&downPatterns.map((p,i)=><PatternCard key={i} p={p}/>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
""")


# =============================================================================
# [3] Patch NavBar to add PATTERNS link
# =============================================================================
print("\n[3/3] Patching NavBar...")

nb_path = None
for p in (DASH / "src").rglob("NavBar.tsx"):
    nb_path = p; break

if nb_path and nb_path.exists():
    nb = nb_path.read_text(encoding="utf-8")
    if "/patterns" not in nb:
        nb = nb.replace(
            '{ href: "/analysis",   label: "ANALYTICS"  },',
            '{ href: "/analysis",   label: "ANALYTICS"  },\n  { href: "/patterns",   label: "PATTERNS"   },'
        )
        nb_path.write_text(nb, encoding="utf-8", newline="\n")
        print("  [OK] Added PATTERNS to NavBar")
    else:
        print("  PATTERNS already in NavBar")
else:
    print("  [WARN] NavBar not found")

print("\n" + "="*60)
print("PHASE 11 COMPLETE")
print("="*60)
print("""
STEP 1 -- Test the builder on a few stocks first (fast):
  py D:\\MICC\\build_calendar_patterns.py --test

STEP 2 -- If test looks good, run full build (3-5 hours):
  py D:\\MICC\\build_calendar_patterns.py

STEP 3 -- Build the dashboard:
  py D:\\MICC\\setup_phase11.py   (already done if you're reading this)

STEP 4 -- Restart dashboard:
  cd D:\\MICC\\micc-dashboard && npm run dev

STEP 5 -- Open:
  localhost:3000/patterns
  Search HDFCBANK -> see all windows where it historically goes UP/DOWN
  Each pattern shows:
    - Window length (e.g. 20 days)
    - Calendar period (e.g. Jan 15 -> Feb 07)
    - Accuracy: 85% (17/20 years went UP)
    - Avg return, best/worst year, std dev
    - Return range bar chart
  Filters: accuracy threshold, min years, direction, window size, sort
  Charts: accuracy distribution, window heatmap, year-position timeline

The --test flag processes 5 symbols (~30 seconds) so you can verify
the output looks right before running the full 3-5 hour job.
""")
