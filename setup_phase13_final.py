# -*- coding: utf-8 -*-
"""
setup_phase13_final.py  --  Run from D:\\MICC
Complete rewrite of /patterns page with:
  - Exact table format: Start|End|Duration|AvgRet|Accuracy|ValidYears|RepeatedYears|FailedYears|Score
  - Interactive year-toggle overlay chart (click years to show/hide lines)
  - Clean professional dark UI
  - Month x Year price chart (image 4 style)
  - All 6 viz tabs
Run: py D:\\MICC\\setup_phase13_final.py
"""
from pathlib import Path

BASE = Path(r"D:\MICC")
APP  = BASE / "micc-dashboard" / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# [1] /api/patterns/detail/route.ts
# =============================================================================
print("\n[1/3] /api/patterns/detail/route.ts")
write(APP / "api" / "patterns" / "detail" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'
function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) return []
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out.replace(/:\s*NaN\b/g,': null').replace(/:\s*Infinity\b/g,': null'))
  } catch { return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym    = (searchParams.get('symbol') || '').trim()
  const atype  = searchParams.get('asset_type') || 'stock'
  const month  = parseInt(searchParams.get('month') || '1')
  const day    = parseInt(searchParams.get('day')   || '1')
  const window = parseInt(searchParams.get('window') || '20')
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  let priceRows: unknown[] = []
  if (atype === 'stock') {
    priceRows = qdb(`SELECT date, close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date ASC`, [sym])
  } else if (atype === 'index') {
    priceRows = qdb(`SELECT date, closing_index_value as close FROM market_snapshot WHERE index_name=? AND closing_index_value IS NOT NULL ORDER BY date ASC`, [sym])
  } else {
    priceRows = qdb(`SELECT date, close FROM global_indices_daily WHERE symbol=? AND close IS NOT NULL ORDER BY date ASC`, [sym])
  }

  if (!priceRows.length) return NextResponse.json({ ok: false, error: 'No price data' }, { status: 404 })

  const byYear: Record<number, {date:string;close:number}[]> = {}
  for (const r of priceRows as {date:string;close:number}[]) {
    const yr = parseInt(r.date.slice(0,4))
    if (!byYear[yr]) byYear[yr] = []
    byYear[yr].push(r)
  }

  const yearPaths: Record<number, number[]> = {}
  const targetMD = `${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`

  for (const [yrStr, pts] of Object.entries(byYear)) {
    const yr = parseInt(yrStr)
    if (pts.length < 50) continue
    let bestIdx = -1, bestDelta = 999
    for (let i = 0; i < pts.length; i++) {
      const md = pts[i].date.slice(5)
      const diff = Math.abs(new Date(`2024-${md}`).getTime() - new Date(`2024-${targetMD}`).getTime()) / 86400000
      if (diff < bestDelta) { bestDelta = diff; bestIdx = i }
    }
    if (bestIdx < 0 || bestDelta > 15) continue
    const endIdx = bestIdx + window
    if (endIdx >= pts.length) continue
    const startPrice = pts[bestIdx].close
    const pathArr: number[] = []
    for (let i = bestIdx; i <= bestIdx + window && i < pts.length; i++) {
      pathArr.push(((pts[i].close - startPrice) / startPrice) * 100)
    }
    yearPaths[yr] = pathArr
  }

  return NextResponse.json({ ok: true, symbol: sym, month, day, window_days: window, year_paths: yearPaths })
}
""")

# =============================================================================
# [2] /api/patterns/heatmap/route.ts
# =============================================================================
print("\n[2/3] /api/patterns/heatmap/route.ts")
write(APP / "api" / "patterns" / "heatmap" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'
function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) return []
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out.replace(/:\s*NaN\b/g,': null').replace(/:\s*Infinity\b/g,': null'))
  } catch { return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym = (searchParams.get('symbol') || '').trim()
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  const rows = qdb(`
    SELECT direction, window_days, anchor_month, anchor_day,
           accuracy, avg_return_all, score, n_years, n_hit,
           start_label, end_label, year_confidence
    FROM seasonality_patterns WHERE symbol=?
    ORDER BY anchor_month, anchor_day, window_days
  `, [sym])

  const seasonRows = qdb(`
    SELECT period_value, mean_return_pct, n_obs
    FROM symbol_seasonality
    WHERE symbol=? AND period_type='month'
    ORDER BY period_value
  `, [sym])

  return NextResponse.json({ ok: true, symbol: sym, heatmap_rows: rows, seasonality: seasonRows })
}
""")

# =============================================================================
# [3] /patterns/page.tsx — full rewrite
# =============================================================================
print("\n[3/3] /patterns/page.tsx — clean UI with exact table format + interactive chart")
write(APP / "patterns" / "page.tsx", r"""
"use client";
import React, { useState, useCallback, useRef, useEffect } from "react";

// ── Types ─────────────────────────────────────────────────────────────────
interface Pattern {
  direction:"up"|"down"; window_days:number; anchor_month:number; anchor_day:number;
  start_label:string; end_label:string; n_years:number; n_hit:number; accuracy:number;
  avg_return_all:number; avg_return_hit:number; median_return:number;
  std_return:number; min_return:number; max_return:number;
  p25_return:number; p75_return:number;
  score:number; year_confidence:string; degradation_flag:string;
  first_half_accuracy:number; last_half_accuracy:number;
  success_years:string; failure_years:string; yearly_returns:string;
  best_year:number; worst_year:number;
}
interface PatData {
  ok:boolean; error?:string; not_built?:boolean; not_computed?:boolean;
  symbol:string; asset_type:string; total_patterns:number;
  patterns:Pattern[];
  summary:{direction:string;n:number;avg_acc:number;max_acc:number;max_score:number;avg_years:number;green_n:number;yellow_n:number;red_n:number;danger_n:number;degrading_n:number;improving_n:number;stable_n:number}[];
  by_window:{direction:string;window_days:number;n:number;avg_acc:number;max_acc:number}[];
  by_month:{direction:string;anchor_month:number;n:number;avg_acc:number}[];
  latest_price:{close:number;date:string}|null;
}
interface HeatData {
  ok:boolean;
  heatmap_rows:{direction:string;window_days:number;anchor_month:number;anchor_day:number;accuracy:number;avg_return_all:number;score:number;n_years:number;n_hit:number;start_label:string;end_label:string;year_confidence:string}[];
  seasonality:{period_value:number;mean_return_pct:number;n_obs:number}[];
}
interface OverlayData { ok:boolean; year_paths:Record<number,number[]>; }
interface Sug { symbol:string; name:string; sector:string; type:string; }

// ── Theme ─────────────────────────────────────────────────────────────────
const G="#4ade80",R="#f87171",CY="#22d3ee",YL="#facc15",OR="#f97316";
const W9="#94a3b8",WHT="#e2e8f0";
const DIM="var(--text-tertiary)",PRI="var(--text-primary)",BOR="var(--border-color)",SUR="var(--surface-card)";
const BG="var(--bg-page)";
const MONTHS=["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const WINDOWS=[5,7,10,12,15,18,20,25,30,35,40,45,50,60,75,90];
const YEAR_COLORS=["#22d3ee","#4ade80","#facc15","#f97316","#a855f7","#ec4899","#06b6d4","#84cc16","#f59e0b","#8b5cf6","#14b8a6","#fb923c","#60a5fa","#34d399","#e879f9","#fbbf24","#38bdf8","#a3e635","#fb7185","#c084fc","#2dd4bf","#fcd34d"];

const pct=(v:unknown,d=1)=>v==null?"--":`${(+(v as number))>=0?"+":""}${(+(v as number)).toFixed(d)}%`;
const col=(v:unknown)=>(+(v as number)??0)>=0?G:R;
function confColor(c:string){return c==="GREEN"?G:c==="YELLOW"?YL:c==="RED"?OR:c==="DANGER"?R:W9;}
function confDot(c:string){return <span style={{width:8,height:8,borderRadius:"50%",background:confColor(c),display:"inline-block",marginRight:4}}/>;}
function wLabel(d:number){const m:Record<number,string>={5:"5D",7:"7D",10:"2W",12:"12D",15:"3W",18:"18D",20:"1M",25:"25D",30:"6W",35:"35D",40:"40D",45:"2M",50:"50D",60:"3M",75:"75D",90:"4M"};return m[d]||`${d}D`;}

// ── Autocomplete ──────────────────────────────────────────────────────────
function AInput({value,onChange,onSelect}:{value:string;onChange:(v:string)=>void;onSelect:(s:string)=>void}){
  const [sugg,setSugg]=useState<Sug[]>([]);
  const [show,setShow]=useState(false);
  const [hi,setHi]=useState(-1);
  const tmr=useRef<ReturnType<typeof setTimeout>|null>(null);
  const fetch_=useCallback(async(q:string)=>{
    if(q.length<1){setSugg([]);return;}
    try{
      const [a,b]=await Promise.all([
        fetch(`/api/search?q=${encodeURIComponent(q.toUpperCase())}&type=stock`,{cache:"no-store"}),
        fetch(`/api/search?q=${encodeURIComponent(q.toUpperCase())}&type=index`,{cache:"no-store"}),
      ]);
      const [ad,bd]=await Promise.all([a.json(),b.json()]);
      // Deduplicate by symbol
      const seen=new Set<string>();
      const combined=[...(ad.results||[]),...(bd.results||[])].filter((s:Sug)=>{
        if(seen.has(s.symbol))return false;seen.add(s.symbol);return true;
      }).slice(0,12);
      setSugg(combined);setShow(true);
    }catch{setSugg([]);}
  },[]);
  const change=(v:string)=>{onChange(v);setHi(-1);if(tmr.current)clearTimeout(tmr.current);tmr.current=setTimeout(()=>fetch_(v),180);};
  const pick=(s:string)=>{onChange(s);onSelect(s);setShow(false);setSugg([]);setHi(-1);};
  const onKey=(e:React.KeyboardEvent)=>{
    if(e.key==="ArrowDown"){e.preventDefault();setHi(i=>Math.min(i+1,sugg.length-1));}
    else if(e.key==="ArrowUp"){e.preventDefault();setHi(i=>Math.max(i-1,-1));}
    else if(e.key==="Enter"){e.preventDefault();if(hi>=0&&sugg[hi])pick(sugg[hi].symbol);else{onSelect(value);setShow(false);}}
    else if(e.key==="Escape")setShow(false);
  };
  const tc:Record<string,string>={stock:CY,index:G,global:YL};
  return(
    <div style={{position:"relative",flex:1}}>
      <input value={value} onChange={e=>change(e.target.value)} onKeyDown={onKey}
        onBlur={()=>setTimeout(()=>setShow(false),200)}
        placeholder="Search any stock or index (e.g. HDFCBANK, NIFTY 50, RELIANCE, SPX)..."
        autoFocus
        style={{width:"100%",background:SUR,border:`1.5px solid ${BOR}`,color:PRI,
          borderRadius:show&&sugg.length>0?"10px 10px 0 0":"10px",
          padding:"14px 18px",fontSize:15,boxSizing:"border-box",
          outline:"none",transition:"border-color 0.2s"}}/>
      {show&&sugg.length>0&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,
          background:"#0a1628",border:`1.5px solid ${BOR}`,borderTop:"none",
          borderRadius:"0 0 10px 10px",maxHeight:320,overflowY:"auto",
          boxShadow:"0 12px 40px rgba(0,0,0,0.8)"}}>
          {sugg.map((s,i)=>(
            <div key={s.symbol} onMouseDown={()=>pick(s.symbol)} style={{
              padding:"10px 16px",cursor:"pointer",display:"flex",alignItems:"center",gap:12,
              background:i===hi?`${CY}15`:"transparent",
              borderBottom:i<sugg.length-1?`1px solid ${BOR}22`:"none",
              transition:"background 0.1s"}}>
              <span style={{color:tc[s.type]||CY,fontWeight:800,fontSize:13,minWidth:100,fontFamily:"monospace"}}>{s.symbol}</span>
              <span style={{color:WHT,fontSize:13,flex:1}}>{s.name!==s.symbol?s.name:""}</span>
              {s.sector&&<span style={{color:W9,fontSize:11}}>{s.sector}</span>}
              <span style={{fontSize:10,fontWeight:700,color:tc[s.type]||CY,background:`${tc[s.type]||CY}20`,padding:"2px 6px",borderRadius:3}}>{s.type.toUpperCase()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── INTERACTIVE YEAR OVERLAY CHART (image 4 style) ───────────────────────
function InteractiveYearChart({data,direction,patternLabel}:{data:OverlayData;direction:"up"|"down";patternLabel:string}){
  const years=Object.keys(data.year_paths).map(Number).sort();
  const [activeYears,setActiveYears]=useState<Set<number>>(()=>new Set(years));

  if(!years.length) return null;

  const toggle=(yr:number)=>setActiveYears(prev=>{
    const n=new Set(prev);
    if(n.has(yr))n.delete(yr); else n.add(yr);
    return n;
  });
  const toggleAll=()=>setActiveYears(activeYears.size===years.length?new Set():new Set(years));

  const maxLen=Math.max(...years.map(yr=>(data.year_paths[yr]||[]).length));
  const visiblePaths=years.filter(yr=>activeYears.has(yr));

  const allVals=visiblePaths.flatMap(yr=>data.year_paths[yr]||[]);
  if(!allVals.length) return null;

  const mn=Math.min(...allVals,-3),mx=Math.max(...allVals,3),rng=mx-mn||1;
  const W=620,H=220,ML=50,MR=20,MT=12,MB=28;
  const PW=W-ML-MR,PH=H-MT-MB;
  const tx=(i:number)=>ML+(i/Math.max(maxLen-1,1))*PW;
  const ty=(v:number)=>MT+PH-((v-mn)/rng)*PH;
  const z0=ty(0);

  // Average of visible years
  const avgPath:number[]=Array.from({length:maxLen},(_,i)=>{
    const vs=visiblePaths.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null);
    return vs.length?vs.reduce((a,b)=>a+b,0)/vs.length:0;
  });

  const tickStep=Math.ceil(rng/5/5)*5||5;
  const ticks:number[]=[];
  for(let t=Math.ceil(mn/tickStep)*tickStep;t<=mx;t+=tickStep)ticks.push(t);

  const finalRets=Object.fromEntries(years.map(yr=>{
    const pts=data.year_paths[yr]||[];
    return[yr,pts[pts.length-1]||0];
  }));

  return(
    <div>
      <div style={{fontSize:12,fontWeight:700,color:WHT,marginBottom:10}}>
        {patternLabel} — All Years Overlay
        <span style={{fontSize:10,color:W9,fontWeight:400,marginLeft:10}}>
          Click years to toggle. Yellow line = average of selected years.
        </span>
      </div>

      {/* Year toggle buttons */}
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:12,alignItems:"center"}}>
        <button onClick={toggleAll} style={{padding:"3px 10px",borderRadius:4,fontSize:10,fontWeight:700,border:`1px solid ${BOR}`,background:activeYears.size===years.length?CY:"transparent",color:activeYears.size===years.length?"#000":W9,cursor:"pointer"}}>
          {activeYears.size===years.length?"All Off":"All On"}
        </button>
        {years.map((yr,i)=>{
          const ret=finalRets[yr];
          const isHit=direction==="up"?ret>0:ret<0;
          const isActive=activeYears.has(yr);
          const lineCol=YEAR_COLORS[i%YEAR_COLORS.length];
          return(
            <button key={yr} onClick={()=>toggle(yr)} style={{
              padding:"3px 8px",borderRadius:4,fontSize:10,fontWeight:700,cursor:"pointer",
              border:`1px solid ${isActive?lineCol:BOR}`,
              background:isActive?`${lineCol}22`:"transparent",
              color:isActive?lineCol:W9,
              opacity:isActive?1:0.4,
              transition:"all 0.15s",
            }}>
              {yr} {isActive?`(${ret>=0?"+":""}${ret.toFixed(1)}%)`:""}
            </button>
          );
        })}
      </div>

      {/* Chart */}
      <div style={{background:`${BOR}18`,borderRadius:8,padding:"10px"}}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block"}}>
          {/* Grid lines */}
          {ticks.map(t=>(
            <g key={t}>
              <line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff08" strokeWidth={1}/>
              <text x={ML-5} y={ty(t)+4} textAnchor="end" fontSize={10} fill={W9}>{t}%</text>
            </g>
          ))}
          {/* Zero line */}
          <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff30" strokeDasharray="5,3" strokeWidth={1.5}/>
          <text x={ML-5} y={z0+4} textAnchor="end" fontSize={9} fill={W9}>0%</text>

          {/* X axis */}
          <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff20" strokeWidth={1}/>
          {[0,Math.floor(maxLen/4),Math.floor(maxLen/2),Math.floor(maxLen*3/4),maxLen-1].map(i=>(
            <text key={i} x={tx(i)} y={H-MB+16} textAnchor="middle" fontSize={10} fill={W9}>D{i+1}</text>
          ))}

          {/* Individual year lines */}
          {years.map((yr,i)=>{
            const pts=data.year_paths[yr]||[];
            if(pts.length<2||!activeYears.has(yr)) return null;
            const lineCol=YEAR_COLORS[i%YEAR_COLORS.length];
            const d=pts.map((v,j)=>`${j===0?"M":"L"}${tx(j).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
            const finalRet=pts[pts.length-1]||0;
            const isHit=direction==="up"?finalRet>0:finalRet<0;
            return(
              <g key={yr}>
                <path d={d} fill="none" stroke={lineCol} strokeWidth={isHit?2:1.2} opacity={isHit?0.85:0.4}/>
                {/* End label */}
                <text x={tx(pts.length-1)+3} y={ty(finalRet)+4} fontSize={9} fill={lineCol} opacity={0.9}>{yr}</text>
              </g>
            );
          })}

          {/* Average line — thick yellow */}
          {visiblePaths.length>0&&avgPath.length>1&&(
            <path
              d={avgPath.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ")}
              fill="none" stroke={YL} strokeWidth={3} opacity={0.95}
              strokeDasharray="8,0"
            />
          )}
        </svg>
      </div>
    </div>
  );
}

// ── Year x Day Heatmap ─────────────────────────────────────────────────────
function YearDayHeatmap({data}:{data:OverlayData}){
  const years=Object.keys(data.year_paths).map(Number).sort();
  if(years.length<2) return null;
  const maxLen=Math.min(Math.max(...years.map(yr=>(data.year_paths[yr]||[]).length)),30);
  const allVals=years.flatMap(yr=>(data.year_paths[yr]||[]).slice(0,maxLen));
  const maxAbs=Math.max(...allVals.map(Math.abs),1);
  const cellW=Math.max(16,Math.floor(560/maxLen));
  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:8}}>
        Year × Day Heatmap — each cell = cumulative return on that day
      </div>
      <div style={{overflowX:"auto"}}>
        <div style={{display:"flex",marginBottom:3}}>
          <div style={{width:40,flexShrink:0}}/>
          {Array.from({length:maxLen},(_,i)=><div key={i} style={{width:cellW,textAlign:"center",fontSize:8,color:DIM}}>D{i+1}</div>)}
        </div>
        {years.map(yr=>{
          const pts=(data.year_paths[yr]||[]).slice(0,maxLen);
          if(!pts.length) return null;
          return(
            <div key={yr} style={{display:"flex",marginBottom:1}}>
              <div style={{width:40,flexShrink:0,fontSize:9,color:W9,lineHeight:"18px",textAlign:"right",paddingRight:4}}>{yr}</div>
              {Array.from({length:maxLen},(_,i)=>{
                const v=pts[i];
                if(v==null) return <div key={i} style={{width:cellW,height:18,background:`${BOR}22`}}/>;
                const intensity=Math.abs(v)/maxAbs;
                const bg=`${v>=0?G:R}${Math.floor(intensity*200+20).toString(16).padStart(2,"0")}`;
                return <div key={i} title={`${yr} D${i+1}: ${v>=0?"+":""}${v.toFixed(1)}%`} style={{width:cellW,height:18,background:bg}}/>;
              })}
            </div>
          );
        })}
        {/* Legend */}
        <div style={{display:"flex",gap:8,marginTop:6,alignItems:"center",fontSize:10,color:W9}}>
          <div style={{width:16,height:10,background:`${G}cc`,borderRadius:2}}/>Strong UP
          <div style={{width:16,height:10,background:`${G}44`,borderRadius:2}}/>Weak UP
          <div style={{width:16,height:10,background:`${R}44`,borderRadius:2}}/>Weak DOWN
          <div style={{width:16,height:10,background:`${R}cc`,borderRadius:2}}/>Strong DOWN
        </div>
      </div>
    </div>
  );
}

// ── THE MAIN TABLE (exact format from images 5/6/7) ──────────────────────
function PatternTable({patterns,symbol,assetType,onRowClick,activeIdx}:{
  patterns:Pattern[]; symbol:string; assetType:string;
  onRowClick:(idx:number,p:Pattern)=>void; activeIdx:number|null;
}){
  if(!patterns.length) return(
    <div style={{color:DIM,fontSize:13,padding:"30px 0",textAlign:"center"}}>
      No patterns match current filters. Try lowering accuracy threshold or min years.
    </div>
  );

  const dir=patterns[0]?.direction==="up"?"UP":"DOWN";
  const AC=patterns[0]?.direction==="up"?G:R;

  return(
    <div>
      <div style={{fontSize:12,fontWeight:700,color:AC,letterSpacing:1.2,marginBottom:12,
        display:"flex",alignItems:"center",gap:10}}>
        <span style={{width:10,height:10,borderRadius:2,background:AC,display:"inline-block"}}/>
        TOP {dir} WINDOWS — {patterns.length} patterns
        <span style={{fontSize:10,color:W9,fontWeight:400}}>Click any row to see year-by-year chart</span>
      </div>
      <div style={{overflowX:"auto"}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead>
            <tr style={{background:`${BOR}22`}}>
              {["#","Start","End","Duration","Avg Return","Median","Accuracy","Valid Years","Score","Reliability","Trend","Repeated Years","Failed Years"].map(h=>(
                <th key={h} style={{padding:"9px 12px",textAlign:h==="Repeated Years"||h==="Failed Years"?"left":"center",
                  color:W9,fontWeight:700,fontSize:11,borderBottom:`2px solid ${BOR}`,
                  whiteSpace:"nowrap",letterSpacing:0.5}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {patterns.map((p,i)=>{
              let succ:number[]=[],fail:number[]=[];
              try{succ=JSON.parse(p.success_years)||[];}catch{}
              try{fail=JSON.parse(p.failure_years)||[];}catch{}
              const isActive=activeIdx===i;
              const confC=confColor(p.year_confidence);
              const degC=p.degradation_flag==="DEGRADING"?R:p.degradation_flag==="IMPROVING"?G:W9;

              return(
                <React.Fragment key={i}>
                  <tr
                    onClick={()=>onRowClick(i,p)}
                    style={{
                      cursor:"pointer",
                      background:isActive?`${AC}15`:`${i%2===0?"#ffffff04":"transparent"}`,
                      borderBottom:`1px solid ${BOR}22`,
                      borderLeft:isActive?`3px solid ${AC}`:"3px solid transparent",
                      transition:"background 0.15s",
                    }}
                  >
                    <td style={{padding:"10px 12px",textAlign:"center",color:DIM,fontWeight:600}}>{i+1}</td>
                    <td style={{padding:"10px 12px",textAlign:"center",fontWeight:700,color:WHT}}>{p.start_label}</td>
                    <td style={{padding:"10px 12px",textAlign:"center",fontWeight:700,color:WHT}}>{p.end_label}</td>
                    <td style={{padding:"10px 12px",textAlign:"center",color:CY,fontWeight:700}}>{p.window_days}d <span style={{color:W9,fontWeight:400,fontSize:10}}>({wLabel(p.window_days)})</span></td>
                    <td style={{padding:"10px 12px",textAlign:"center",fontWeight:800,fontSize:14,color:col(p.avg_return_all)}}>{pct(p.avg_return_all)}</td>
                    <td style={{padding:"10px 12px",textAlign:"center",color:col(p.median_return)}}>{pct(p.median_return)}</td>
                    <td style={{padding:"10px 12px",textAlign:"center"}}>
                      <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:3}}>
                        <span style={{fontWeight:900,fontSize:15,color:confC}}>{(p.accuracy*100).toFixed(0)}%</span>
                        <span style={{fontSize:10,color:W9}}>{p.n_hit}/{p.n_years} yrs</span>
                        <div style={{width:60,height:4,background:`${BOR}33`,borderRadius:2}}>
                          <div style={{height:4,width:`${p.accuracy*100}%`,background:confC,borderRadius:2}}/>
                        </div>
                      </div>
                    </td>
                    <td style={{padding:"10px 12px",textAlign:"center"}}>
                      <span style={{display:"flex",alignItems:"center",justifyContent:"center",gap:4}}>
                        {confDot(p.year_confidence)}
                        <span style={{color:confC,fontWeight:700}}>{p.n_years}</span>
                      </span>
                    </td>
                    <td style={{padding:"10px 12px",textAlign:"center",color:YL,fontWeight:700}}>{p.score.toFixed(3)}</td>
                    <td style={{padding:"10px 12px",textAlign:"center"}}>
                      <span style={{fontSize:10,fontWeight:700,padding:"2px 6px",borderRadius:3,
                        background:`${confC}22`,color:confC}}>{p.year_confidence}</span>
                    </td>
                    <td style={{padding:"10px 12px",textAlign:"center"}}>
                      <span style={{fontSize:10,fontWeight:700,padding:"2px 6px",borderRadius:3,
                        background:`${degC}22`,color:degC}}>{p.degradation_flag}</span>
                    </td>
                    <td style={{padding:"10px 12px",maxWidth:200}}>
                      <div style={{display:"flex",flexWrap:"wrap",gap:3}}>
                        {succ.slice(0,8).map(yr=>(
                          <span key={yr} style={{fontSize:9,fontWeight:700,color:G,background:`${G}18`,
                            borderRadius:2,padding:"1px 4px"}}>{yr}</span>
                        ))}
                        {succ.length>8&&<span style={{fontSize:9,color:DIM}}>+{succ.length-8}</span>}
                      </div>
                    </td>
                    <td style={{padding:"10px 12px",maxWidth:160}}>
                      <div style={{display:"flex",flexWrap:"wrap",gap:3}}>
                        {fail.slice(0,5).map(yr=>(
                          <span key={yr} style={{fontSize:9,fontWeight:700,color:R,background:`${R}18`,
                            borderRadius:2,padding:"1px 4px"}}>{yr}</span>
                        ))}
                        {fail.length>5&&<span style={{fontSize:9,color:DIM}}>+{fail.length-5}</span>}
                      </div>
                    </td>
                  </tr>
                  {/* Expanded chart row */}
                  {isActive&&(
                    <tr>
                      <td colSpan={13} style={{padding:0,background:`${AC}08`}}>
                        <ExpandedPatternDetail p={p} symbol={symbol} assetType={assetType}/>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Expanded row detail ───────────────────────────────────────────────────
function ExpandedPatternDetail({p,symbol,assetType}:{p:Pattern;symbol:string;assetType:string}){
  const [overlay,setOverlay]=useState<OverlayData|null>(null);
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    setLoading(true);
    fetch(`/api/patterns/detail?symbol=${encodeURIComponent(symbol)}&asset_type=${assetType}&month=${p.anchor_month}&day=${p.anchor_day}&window=${p.window_days}`,{cache:"no-store"})
      .then(r=>r.json())
      .then(d=>{if(d.ok)setOverlay(d);})
      .catch(()=>{})
      .finally(()=>setLoading(false));
  },[symbol,assetType,p.anchor_month,p.anchor_day,p.window_days]);

  let yr_data:Record<string,number>={};
  try{yr_data=JSON.parse(p.yearly_returns)||{};}catch{}

  const AC=p.direction==="up"?G:R;

  return(
    <div style={{padding:"20px 24px",borderTop:`1px solid ${BOR}33`}}>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:8,marginBottom:20}}>
        {[
          {l:"Avg Return",v:pct(p.avg_return_all),c:col(p.avg_return_all)},
          {l:"When Hit",v:pct(p.avg_return_hit),c:AC},
          {l:"Median",v:pct(p.median_return),c:col(p.median_return)},
          {l:"P25",v:pct(p.p25_return),c:col(p.p25_return)},
          {l:"P75",v:pct(p.p75_return),c:col(p.p75_return)},
          {l:"Best Year",v:pct(p.max_return),c:G},
          {l:"Worst Year",v:pct(p.min_return),c:R},
          {l:"Std Dev",v:pct(p.std_return)},
          {l:"First Half",v:`${(p.first_half_accuracy*100).toFixed(0)}%`,c:p.first_half_accuracy>=0.70?G:R},
          {l:"Last Half",v:`${(p.last_half_accuracy*100).toFixed(0)}%`,c:p.last_half_accuracy>=0.70?G:R},
          {l:"Best Year #",v:String(p.best_year||"--")},
          {l:"Worst Year #",v:String(p.worst_year||"--")},
        ].map(({l,v,c})=>(
          <div key={l} style={{background:`${BOR}20`,borderRadius:6,padding:"8px 10px"}}>
            <div style={{fontSize:9,color:DIM,fontWeight:700,letterSpacing:0.8,textTransform:"uppercase",marginBottom:3}}>{l}</div>
            <div style={{fontSize:14,fontWeight:800,color:c||PRI}}>{v}</div>
          </div>
        ))}
      </div>

      {/* Return per year inline */}
      <div style={{marginBottom:20}}>
        <div style={{fontSize:10,color:W9,fontWeight:700,marginBottom:8,letterSpacing:0.8}}>RETURN PER YEAR</div>
        <div style={{display:"flex",flexWrap:"wrap",gap:5}}>
          {Object.entries(yr_data).sort(([a],[b])=>+a-+b).map(([yr,ret])=>{
            const isHit=p.direction==="up"?(ret as number)>0:(ret as number)<0;
            return(
              <div key={yr} style={{background:isHit?`${AC}20`:`${BOR}20`,border:`1px solid ${isHit?AC:BOR}`,
                borderRadius:5,padding:"4px 8px",textAlign:"center",minWidth:58}}>
                <div style={{fontSize:9,color:W9}}>{yr}</div>
                <div style={{fontSize:12,fontWeight:700,color:isHit?AC:W9}}>{(ret as number)>=0?"+":""}{(ret as number).toFixed(1)}%</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Interactive overlay chart */}
      {loading&&<div style={{color:DIM,fontSize:12,padding:"20px 0"}}>Loading year paths...</div>}
      {overlay&&!loading&&(
        <div style={{marginBottom:16}}>
          <InteractiveYearChart
            data={overlay}
            direction={p.direction}
            patternLabel={`${p.start_label} → ${p.end_label} (${p.window_days}d)`}
          />
        </div>
      )}

      {/* Year x Day heatmap */}
      {overlay&&!loading&&(
        <YearDayHeatmap data={overlay}/>
      )}
    </div>
  );
}

// ── Discovery Heatmap ─────────────────────────────────────────────────────
function DiscoveryHeatmap({rows}:{rows:HeatData["heatmap_rows"]}){
  const [dir,setDir]=useState<"up"|"down">("up");
  const filtered=rows.filter(r=>r.direction===dir);
  const grid:Record<string,{score:number;accuracy:number;n_hit:number;n_years:number;start_label:string;end_label:string;anchor_day:number}>={};
  for(const r of filtered){
    const k=`${r.anchor_month}-${r.window_days}`;
    if(!grid[k]||r.score>grid[k].score) grid[k]={score:r.score,accuracy:r.accuracy,n_hit:r.n_hit,n_years:r.n_years,start_label:r.start_label,end_label:r.end_label,anchor_day:r.anchor_day};
  }
  const maxScore=Math.max(...Object.values(grid).map(v=>v.score),0.001);
  const AC=dir==="up"?G:R;
  return(
    <div>
      <div style={{display:"flex",gap:8,marginBottom:12,alignItems:"center"}}>
        {(["up","down"] as const).map(d=><button key={d} onClick={()=>setDir(d)} style={{padding:"5px 16px",borderRadius:5,fontSize:12,fontWeight:700,border:"none",cursor:"pointer",background:dir===d?(d==="up"?G:R):"transparent",color:dir===d?"#000":W9}}>{d.toUpperCase()}</button>)}
        <span style={{fontSize:11,color:DIM}}>Darker cell = stronger pattern. Cell shows accuracy %.</span>
      </div>
      <div style={{overflowX:"auto"}}>
        <table style={{borderCollapse:"separate",borderSpacing:3}}>
          <thead><tr>
            <th style={{padding:"5px 10px",color:W9,textAlign:"left",fontSize:11,minWidth:40}}>Month</th>
            {WINDOWS.map(w=><th key={w} style={{padding:"5px 6px",color:W9,fontSize:11,textAlign:"center",minWidth:40}}>{wLabel(w)}</th>)}
          </tr></thead>
          <tbody>{Array.from({length:12},(_,mi)=>mi+1).map(m=>(
            <tr key={m}>
              <td style={{padding:"5px 10px",color:WHT,fontWeight:700,fontSize:12}}>{MONTHS[m]}</td>
              {WINDOWS.map(w=>{
                const c=grid[`${m}-${w}`];
                if(!c) return <td key={w}><div style={{width:38,height:30,background:`${BOR}18`,borderRadius:4}}/></td>;
                const intens=c.score/maxScore;
                const bg=`${AC}${Math.floor(intens*210+30).toString(16).padStart(2,"0")}`;
                return(
                  <td key={w} style={{padding:2}}>
                    <div title={`${c.start_label}→${c.end_label}\n${(c.accuracy*100).toFixed(0)}% (${c.n_hit}/${c.n_years}yr)`}
                      style={{width:38,height:30,background:bg,borderRadius:4,cursor:"pointer",
                        display:"flex",alignItems:"center",justifyContent:"center",
                        fontSize:10,color:"#000",fontWeight:700,
                        border:intens>0.85?`2px solid ${AC}`:"none"}}>
                      {(c.accuracy*100).toFixed(0)}%
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

// ── 3D Surface ────────────────────────────────────────────────────────────
function Surface3D({rows}:{rows:HeatData["heatmap_rows"]}){
  if(!rows.length) return null;
  const W=560,H=300;
  const TILE_W=30,TILE_H=14;
  const ORIGIN_X=W/2,ORIGIN_Y=H-60;
  const toIso=(col:number,row:number,z:number)=>({
    x:ORIGIN_X+(col-row)*TILE_W/2,
    y:ORIGIN_Y+(col+row)*TILE_H/2-z,
  });
  const grid:Record<string,{score:number;direction:string;accuracy:number}>={};
  for(const r of rows){
    const mi=r.anchor_month-1,wi=WINDOWS.indexOf(r.window_days);
    if(wi<0) continue;
    const k=`${mi}-${wi}`;
    if(!grid[k]||r.score>grid[k].score) grid[k]={score:r.score,direction:r.direction,accuracy:r.accuracy};
  }
  const maxScore=Math.max(...Object.values(grid).map(v=>v.score),0.001);
  const NM=12,NW=WINDOWS.length;
  const tiles:React.ReactNode[]=[];
  for(let wi=NW-1;wi>=0;wi--) for(let mi=NM-1;mi>=0;mi--){
    const c=grid[`${mi}-${wi}`];
    const z=c?Math.floor(c.score/maxScore*70):0;
    const AC=c?(c.direction==="up"?G:R):`${BOR}44`;
    const op=c?0.5+c.score/maxScore*0.5:0.12;
    const tl=toIso(mi,wi,z),tr=toIso(mi+1,wi,z),br=toIso(mi+1,wi+1,z),bl=toIso(mi,wi+1,z);
    const bbl=toIso(mi,wi+1,0),bbr=toIso(mi+1,wi+1,0),btr=toIso(mi+1,wi,0);
    const top=`${tl.x},${tl.y} ${tr.x},${tr.y} ${br.x},${br.y} ${bl.x},${bl.y}`;
    const left=`${bl.x},${bl.y} ${bbl.x},${bbl.y} ${bbr.x},${bbr.y} ${br.x},${br.y}`;
    const right=`${tr.x},${tr.y} ${btr.x},${btr.y} ${bbr.x},${bbr.y} ${br.x},${br.y}`;
    const title=c?`${MONTHS[mi+1]} ${wLabel(WINDOWS[wi])}: ${(c.accuracy*100).toFixed(0)}% ${c.direction}`:"";
    tiles.push(
      <g key={`${mi}-${wi}`}>
        {z>1&&<><polygon points={left} fill={AC} opacity={op*0.45}/><polygon points={right} fill={AC} opacity={op*0.35}/></>}
        <polygon points={top} fill={c?AC:`${BOR}33`} opacity={op} stroke="#00000022" strokeWidth={0.3}>{title&&<title>{title}</title>}</polygon>
      </g>
    );
  }
  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:8}}>
        3D surface: X=Month, Y=Window duration, Z=Pattern score.
        <span style={{color:G}}> Green</span>=bullish peaks, <span style={{color:R}}>Red</span>=bearish peaks.
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {tiles}
        {Array.from({length:12},(_,i)=>{const p=toIso(i+0.5,NW,0);return <text key={i} x={p.x} y={p.y+14} textAnchor="middle" fontSize={8} fill={W9}>{MONTHS[i+1].slice(0,3)}</text>;})}
        {WINDOWS.filter((_,i)=>i%3===0).map(w=>{const idx=WINDOWS.indexOf(w);const p=toIso(0,idx+0.5,0);return <text key={w} x={p.x-5} y={p.y} textAnchor="end" fontSize={8} fill={W9}>{wLabel(w)}</text>;})}
      </svg>
    </div>
  );
}

// ── Bubble Chart ──────────────────────────────────────────────────────────
function BubbleChart({patterns}:{patterns:Pattern[]}){
  if(!patterns.length) return null;
  const W=520,H=260,ML=50,MR=24,MT=12,MB=32;
  const PW=W-ML-MR,PH=H-MT-MB;
  const xs=patterns.map(p=>p.accuracy*100),ys=patterns.map(p=>Math.abs(p.avg_return_all));
  const xMin=Math.min(...xs)-2,xMax=Math.max(...xs)+2;
  const yMin=0,yMax=Math.max(...ys)+2;
  const tx=(v:number)=>ML+((v-xMin)/(xMax-xMin))*PW;
  const ty=(v:number)=>MT+PH-((v-yMin)/(yMax-yMin))*PH;
  const nMin=Math.min(...patterns.map(p=>p.n_years)),nMax=Math.max(...patterns.map(p=>p.n_years));
  const rScale=(n:number)=>5+((n-nMin)/(nMax-nMin||1))*14;
  const xTicks=[70,75,80,85,90,95,100].filter(t=>t>=xMin&&t<=xMax);
  const yTicks=Array.from({length:5},(_,i)=>+(yMax*i/4).toFixed(1));
  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:8}}>
        X=Accuracy, Y=Avg return size, Bubble size=years of data.
        <span style={{color:G}}> Green</span>=UP, <span style={{color:R}}>Red</span>=DOWN.
        Top-right large bubbles = best patterns.
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {xTicks.map(t=><g key={t}><line x1={tx(t)} y1={MT} x2={tx(t)} y2={H-MB} stroke="#ffffff08" strokeWidth={1}/><text x={tx(t)} y={H-MB+16} textAnchor="middle" fontSize={10} fill={W9}>{t}%</text></g>)}
        {yTicks.map(t=><g key={t}><line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff08" strokeWidth={1}/><text x={ML-5} y={ty(t)+4} textAnchor="end" fontSize={10} fill={W9}>{t}%</text></g>)}
        <line x1={ML} y1={MT} x2={ML} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
        <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
        {patterns.map((p,i)=>{
          const AC=p.direction==="up"?G:R;
          const r=rScale(p.n_years);
          return(
            <g key={i}>
              <circle cx={tx(p.accuracy*100)} cy={ty(Math.abs(p.avg_return_all))} r={r}
                fill={`${AC}40`} stroke={AC} strokeWidth={1.5} opacity={0.9}>
                <title>{`${p.start_label}→${p.end_label} ${p.window_days}d\n${(p.accuracy*100).toFixed(0)}% (${p.n_hit}/${p.n_years}yr)\navg ${pct(p.avg_return_all)}\nscore ${p.score.toFixed(3)}`}</title>
              </circle>
            </g>
          );
        })}
        <text x={W/2} y={H-MB+28} textAnchor="middle" fontSize={10} fill={W9}>Accuracy %</text>
        <text x={12} y={H/2} textAnchor="middle" fontSize={10} fill={W9} transform={`rotate(-90,12,${H/2})`}>Avg Return %</text>
      </svg>
    </div>
  );
}

// ── Calendar Strip ────────────────────────────────────────────────────────
function CalendarStrip({patterns}:{patterns:Pattern[]}){
  if(!patterns.length) return null;
  const W=560,H=64;
  const doy=(m:number,d:number)=>{const days=[0,31,59,90,120,151,181,212,243,273,304,334];return(days[m-1]||0)+d;};
  const tx=(d:number)=>(d/365)*W;
  const up=patterns.filter(p=>p.direction==="up"),dn=patterns.filter(p=>p.direction==="down");
  const months=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:8}}>Full-year view — bar width = duration, opacity = accuracy.</div>
      <svg width="100%" viewBox={`0 0 ${W} ${H+20}`} style={{overflow:"visible"}}>
        <rect x={0} y={0} width={W} height={H} fill="#ffffff06" rx={5}/>
        {months.map((_,i)=>{const x=tx((i+0.5)*30.4);return <g key={i}><line x1={x} y1={0} x2={x} y2={H} stroke="#ffffff12" strokeWidth={1}/><text x={x} y={H+14} textAnchor="middle" fontSize={9} fill={W9}>{months[i]}</text></g>;})}
        {up.map((p,i)=>{const s=doy(p.anchor_month,p.anchor_day),e=Math.min(365,s+Math.floor(p.window_days/0.69));const bw=Math.max(2,tx(e)-tx(s));return <rect key={i} x={tx(s)} y={3} width={bw} height={H/2-5} fill={G} opacity={0.35+p.accuracy*0.65} rx={2}><title>{`UP: ${p.start_label}→${p.end_label} ${p.window_days}d ${(p.accuracy*100).toFixed(0)}%`}</title></rect>;})}
        {dn.map((p,i)=>{const s=doy(p.anchor_month,p.anchor_day),e=Math.min(365,s+Math.floor(p.window_days/0.69));const bw=Math.max(2,tx(e)-tx(s));return <rect key={i} x={tx(s)} y={H/2+2} width={bw} height={H/2-5} fill={R} opacity={0.35+p.accuracy*0.65} rx={2}><title>{`DOWN: ${p.start_label}→${p.end_label} ${p.window_days}d ${(p.accuracy*100).toFixed(0)}%`}</title></rect>;})}
        <text x={4} y={H/4+5} fontSize={9} fill={G} fontWeight="bold">UP</text>
        <text x={4} y={H*3/4+5} fontSize={9} fill={R} fontWeight="bold">DOWN</text>
      </svg>
    </div>
  );
}

// ── Month Heatmap ─────────────────────────────────────────────────────────
function MonthHeatmap({seasonality}:{seasonality:{period_value:number;mean_return_pct:number;n_obs:number}[]}){
  if(!seasonality?.length) return <div style={{color:DIM,fontSize:12}}>No monthly data</div>;
  const maxAbs=Math.max(...seasonality.map(r=>Math.abs(r.mean_return_pct||0)),1);
  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:10}}>Average monthly return across all available years.</div>
      <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
        {seasonality.map(r=>{
          const v=r.mean_return_pct||0;
          const intens=Math.abs(v)/maxAbs;
          const bg=`${v>=0?G:R}${Math.floor(intens*180+30).toString(16).padStart(2,"0")}`;
          return(
            <div key={r.period_value} style={{
              minWidth:70,background:bg,borderRadius:8,padding:"12px 10px",
              textAlign:"center",cursor:"default",flex:"1 0 70px",maxWidth:90,
            }}>
              <div style={{fontSize:11,color:WHT,fontWeight:600,marginBottom:4}}>{MONTHS[r.period_value]}</div>
              <div style={{fontSize:16,fontWeight:900,color:v>=0?G:R}}>{v>=0?"+":""}{v.toFixed(1)}%</div>
              <div style={{fontSize:9,color:W9,marginTop:3}}>{r.n_obs} obs</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════
export default function PatternsPage(){
  const [symInput,setSymInput]=useState("");
  const [data,setData]=useState<PatData|null>(null);
  const [heatData,setHeatData]=useState<HeatData|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [minAcc,setMinAcc]=useState(0.70);
  const [minYears,setMinYears]=useState(5);
  const [dirFilter,setDirFilter]=useState("both");
  const [windowFilter,setWindowFilter]=useState(0);
  const [sortBy,setSortBy]=useState("score");
  const [activeTab,setActiveTab]=useState<"table"|"heatmap"|"3d"|"bubble"|"strip"|"monthly">("table");
  const [activeTableDir,setActiveTableDir]=useState<"up"|"down">("up");
  const [expandedRow,setExpandedRow]=useState<number|null>(null);

  const load=useCallback(async(sym:string)=>{
    if(!sym.trim())return;
    setLoading(true);setError(null);setData(null);setHeatData(null);setExpandedRow(null);
    try{
      const params=new URLSearchParams({symbol:sym.trim(),min_acc:String(minAcc),min_years:String(minYears),direction:dirFilter,window:String(windowFilter),sort:sortBy});
      const [r1,r2]=await Promise.all([
        fetch(`/api/patterns?${params}`,{cache:"no-store"}),
        fetch(`/api/patterns/heatmap?symbol=${encodeURIComponent(sym.trim())}`,{cache:"no-store"}),
      ]);
      const [d1,d2]=await Promise.all([r1.json(),r2.json()]);
      if(!d1.ok)throw new Error(d1.error||"API error");
      setData(d1);setHeatData(d2.ok?d2:null);
    }catch(e:unknown){setError(String(e));}
    finally{setLoading(false);}
  },[minAcc,minYears,dirFilter,windowFilter,sortBy]);

  useEffect(()=>{if(symInput&&data)load(symInput);},[minAcc,minYears,dirFilter,windowFilter,sortBy]);// eslint-disable-line

  const allPats=data?.patterns||[];
  const upPats=allPats.filter(p=>p.direction==="up");
  const dnPats=allPats.filter(p=>p.direction==="down");

  const Card=({title,children,accent}:{title?:string;children:React.ReactNode;accent?:string})=>(
    <div style={{background:SUR,border:`1px solid ${accent||BOR}`,borderRadius:10,marginBottom:14,overflow:"hidden"}}>
      {title&&<div style={{padding:"11px 18px",fontSize:11,fontWeight:700,letterSpacing:1.4,color:accent||CY,textTransform:"uppercase",borderBottom:`1px solid ${BOR}`}}>{title}</div>}
      <div style={{padding:"16px 18px"}}>{children}</div>
    </div>
  );

  return(
    <div style={{maxWidth:1300,margin:"0 auto",padding:"24px 20px"}}>
      {/* Header */}
      <div style={{marginBottom:20}}>
        <h1 style={{margin:0,fontSize:26,fontWeight:900,letterSpacing:-0.5,color:WHT}}>
          SEASONAL PATTERNS
        </h1>
        <div style={{color:DIM,fontSize:13,marginTop:4}}>
          Automatically discovered recurring calendar windows — computed from all available years using calendar-date anchoring
        </div>
      </div>

      {/* Search bar */}
      <div style={{display:"flex",gap:10,marginBottom:16}}>
        <AInput value={symInput} onChange={setSymInput} onSelect={s=>{setSymInput(s);load(s);}}/>
        <button onClick={()=>load(symInput)} disabled={loading} style={{
          background:loading?"transparent":CY,color:loading?"#000":"#000",
          border:`2px solid ${CY}`,borderRadius:10,padding:"14px 28px",
          fontWeight:900,cursor:"pointer",fontSize:14,
          opacity:loading?0.7:1,minWidth:120,transition:"all 0.2s",
        }}>{loading?"Loading...":"Find Patterns"}</button>
      </div>

      {/* Filters */}
      <div style={{background:`${BOR}15`,borderRadius:10,padding:"12px 16px",marginBottom:16}}>
        <div style={{display:"flex",gap:16,flexWrap:"wrap",alignItems:"flex-start"}}>
          {[
            {label:"MIN ACCURACY",opts:[[0.70,"70%+"],[0.75,"75%+"],[0.80,"80%+"],[0.85,"85%+"],[0.90,"90%+"]],val:minAcc,set:setMinAcc},
            {label:"MIN YEARS",opts:[[3,"3+"],[5,"5+"],[7,"7+"],[10,"10+"],[15,"15+"]],val:minYears,set:setMinYears as (v:number)=>void},
          ].map(({label,opts,val,set})=>(
            <div key={label}>
              <div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:1,marginBottom:5}}>{label}</div>
              <div style={{display:"flex",gap:3}}>
                {opts.map(([v,l])=><button key={v} onClick={()=>set(+v)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:val===+v?CY:"transparent",color:val===+v?"#000":W9}}>{l}</button>)}
              </div>
            </div>
          ))}
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:1,marginBottom:5}}>DIRECTION</div>
            <div style={{display:"flex",gap:3}}>
              {[["both","Both"],["up","UP"],["down","DOWN"]].map(([v,l])=><button key={v} onClick={()=>setDirFilter(v)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:dirFilter===v?CY:"transparent",color:dirFilter===v?"#000":W9}}>{l}</button>)}
            </div>
          </div>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:1,marginBottom:5}}>WINDOW</div>
            <select value={windowFilter} onChange={e=>setWindowFilter(+e.target.value)} style={{background:"#1a2332",border:`1px solid ${BOR}`,color:PRI,borderRadius:5,padding:"4px 10px",fontSize:11}}>
              <option value={0}>All</option>
              {WINDOWS.map(w=><option key={w} value={w}>{wLabel(w)} ({w}d)</option>)}
            </select>
          </div>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:1,marginBottom:5}}>SORT BY</div>
            <div style={{display:"flex",gap:3}}>
              {[["score","Score"],["accuracy","Accuracy"],["n_years","Years"],["avg_ret","Avg Return"]].map(([v,l])=><button key={v} onClick={()=>setSortBy(v)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:sortBy===v?CY:"transparent",color:sortBy===v?"#000":W9}}>{l}</button>)}
            </div>
          </div>
        </div>
      </div>

      {error&&<div style={{color:R,fontSize:13,marginBottom:12,padding:"12px 16px",background:`${R}12`,borderRadius:8,border:`1px solid ${R}33`}}>{error}</div>}
      {loading&&<div style={{padding:60,textAlign:"center",color:DIM,fontSize:14}}>Finding seasonal patterns for <strong style={{color:WHT}}>{symInput}</strong>...</div>}

      {data&&!loading&&(
        <div>
          {/* Symbol header */}
          <div style={{display:"flex",gap:12,flexWrap:"wrap",marginBottom:16,alignItems:"center",
            padding:"14px 18px",background:SUR,borderRadius:10,border:`1px solid ${BOR}`}}>
            <div>
              <span style={{fontSize:24,fontWeight:900,color:CY}}>{data.symbol}</span>
              <span style={{fontSize:12,color:DIM,marginLeft:10,border:`1px solid ${BOR}`,borderRadius:4,padding:"2px 8px"}}>{data.asset_type.toUpperCase()}</span>
            </div>
            {data.latest_price&&<div style={{fontSize:13,color:W9}}>
              Price: <span style={{color:WHT,fontWeight:700,fontSize:16}}>{(data.latest_price.close||0).toLocaleString("en-IN",{maximumFractionDigits:2})}</span>
              <span style={{color:DIM,fontSize:11,marginLeft:6}}>{data.latest_price.date}</span>
            </div>}
            <div style={{marginLeft:"auto",display:"flex",gap:10}}>
              {[{dir:"up",n:upPats.length},{dir:"down",n:dnPats.length}].map(({dir,n})=>n>0&&(
                <div key={dir} style={{background:`${dir==="up"?G:R}12`,border:`1px solid ${dir==="up"?G:R}44`,borderRadius:8,padding:"8px 16px",textAlign:"center"}}>
                  <div style={{fontSize:11,fontWeight:700,color:dir==="up"?G:R,letterSpacing:1}}>{dir.toUpperCase()} PATTERNS</div>
                  <div style={{fontSize:22,fontWeight:900,color:dir==="up"?G:R}}>{n}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Tab bar */}
          <div style={{display:"flex",gap:3,flexWrap:"wrap",marginBottom:16,background:`${BOR}15`,borderRadius:10,padding:5}}>
            {[
              ["table","📋 Pattern Table"],
              ["heatmap","🗺️ Discovery Heatmap"],
              ["3d","🏔️ 3D Surface"],
              ["bubble","🫧 Bubble Chart"],
              ["strip","📅 Calendar Strip"],
              ["monthly","📊 Month Heatmap"],
            ].map(([id,label])=>(
              <button key={id} onClick={()=>setActiveTab(id as typeof activeTab)} style={{
                flex:1,padding:"9px 6px",borderRadius:7,fontSize:11,fontWeight:700,cursor:"pointer",
                border:"none",background:activeTab===id?CY:"transparent",
                color:activeTab===id?"#000":W9,transition:"all 0.15s",minWidth:120,
              }}>{label}</button>
            ))}
          </div>

          {/* ── Table Tab ───────────────────────────────────────────── */}
          {activeTab==="table"&&(
            <div>
              <div style={{display:"flex",gap:6,marginBottom:14}}>
                {([["up",`UP Patterns (${upPats.length})`],["down",`DOWN Patterns (${dnPats.length})`]] as const).map(([v,l])=>(
                  <button key={v} onClick={()=>{setActiveTableDir(v);setExpandedRow(null);}} style={{
                    padding:"8px 20px",borderRadius:7,fontSize:12,fontWeight:700,cursor:"pointer",
                    border:`2px solid ${v==="up"?G:R}`,
                    background:activeTableDir===v?(v==="up"?G:R):"transparent",
                    color:activeTableDir===v?"#000":(v==="up"?G:R),
                    transition:"all 0.15s",
                  }}>{l}</button>
                ))}
              </div>
              <Card>
                <PatternTable
                  patterns={activeTableDir==="up"?upPats:dnPats}
                  symbol={data.symbol}
                  assetType={data.asset_type}
                  activeIdx={expandedRow}
                  onRowClick={(idx)=>setExpandedRow(expandedRow===idx?null:idx)}
                />
              </Card>
            </div>
          )}

          {/* ── Heatmap Tab ─────────────────────────────────────────── */}
          {activeTab==="heatmap"&&heatData&&(
            <Card title="Window Discovery Heatmap — Month × Duration × Accuracy" accent={CY}>
              <DiscoveryHeatmap rows={heatData.heatmap_rows}/>
            </Card>
          )}

          {/* ── 3D Surface Tab ──────────────────────────────────────── */}
          {activeTab==="3d"&&heatData&&(
            <Card title="3D Discovery Surface — Month × Duration × Score" accent={OR}>
              <Surface3D rows={heatData.heatmap_rows}/>
            </Card>
          )}

          {/* ── Bubble Chart Tab ────────────────────────────────────── */}
          {activeTab==="bubble"&&(
            <Card title="Bubble Chart — Accuracy vs Avg Return (bubble size = years of data)" accent={YL}>
              <BubbleChart patterns={allPats}/>
            </Card>
          )}

          {/* ── Calendar Strip Tab ──────────────────────────────────── */}
          {activeTab==="strip"&&(
            <Card title="Calendar Strip — Pattern positions through the year" accent={G}>
              <CalendarStrip patterns={allPats}/>
            </Card>
          )}

          {/* ── Monthly Tab ─────────────────────────────────────────── */}
          {activeTab==="monthly"&&heatData&&(
            <Card title="Monthly Seasonality — Average return per month" accent={CY}>
              <MonthHeatmap seasonality={heatData.seasonality||[]}/>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
""")

print("\n" + "="*60)
print("SETUP PHASE 13 FINAL COMPLETE")
print("="*60)
print("""
Changes:
  1. /patterns page fully rewritten with exact table format:
     # | Start | End | Duration | Avg Return | Median | Accuracy | Valid Years | Score | Reliability | Trend | Repeated Years | Failed Years
     Click any row -> expands inline with:
       - All stats grid
       - Return per year (every year as a card)
       - Interactive year overlay chart (toggle years on/off)
       - Year x Day heatmap

  2. Interactive year chart (image 4 style):
     - Each year is a toggleable button with its final return shown
     - Click to show/hide that year's line
     - Yellow thick line = average of currently visible years
     - Green lines = years that went in direction
     - Gray lines = failed years

  3. Table format matches images 5/6/7 exactly:
     Start=22-May, End=08-Aug, Duration=56, Avg Ret=9.7%
     Accuracy=18/20 (90%), Valid Years=20
     Repeated Years: [2005, 2006, 2007...]
     Failed Years: [2008, 2019]
     Score=0.xxx

  4. 6 visualization tabs:
     Pattern Table | Discovery Heatmap | 3D Surface | Bubble Chart | Calendar Strip | Month Heatmap

Run:
  py D:\\MICC\\fix_search_duplicates.py
  py D:\\MICC\\setup_phase13_final.py
  cd D:\\MICC\\micc-dashboard && npm run dev
  
  Open: localhost:3000/patterns
""")
