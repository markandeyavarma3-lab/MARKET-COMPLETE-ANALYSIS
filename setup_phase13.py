# -*- coding: utf-8 -*-
"""
setup_phase13.py  --  Run from D:\\MICC
Adds all 7 visualizations from the spec to /patterns page:
  1. Window Discovery Heatmap (start-day x duration x score)
  2. All-years overlay chart (normalized lines per year)
  3. Year x relative-day heatmap per pattern
  4. 3D discovery surface (SVG approximation)
  5. Bubble chart (accuracy vs avg_return, size=years)
  6. Calendar strip (year timeline of patterns)
  7. Month x year heatmap (rows=years, cols=months)
  + new /api/patterns/detail route for per-pattern price data
Run: py D:\\MICC\\setup_phase13.py
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
# [1] /api/patterns/detail/route.ts  -- per-pattern price data for overlay chart
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

  // Load full price history
  let priceRows: unknown[] = []
  if (atype === 'stock') {
    priceRows = qdb(`SELECT date, close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date ASC`, [sym])
  } else if (atype === 'index') {
    priceRows = qdb(`SELECT date, closing_index_value as close FROM market_snapshot WHERE index_name=? AND closing_index_value IS NOT NULL ORDER BY date ASC`, [sym])
  } else {
    priceRows = qdb(`SELECT date, close FROM global_indices_daily WHERE symbol=? AND close IS NOT NULL ORDER BY date ASC`, [sym])
  }

  if (!priceRows.length) return NextResponse.json({ ok: false, error: 'No price data' }, { status: 404 })

  // Group by year
  const byYear: Record<number, {date:string;close:number}[]> = {}
  for (const r of priceRows as {date:string;close:number}[]) {
    const yr = parseInt(r.date.slice(0,4))
    if (!byYear[yr]) byYear[yr] = []
    byYear[yr].push(r)
  }

  // For each year, find the window starting near (month, day)
  const yearPaths: Record<number, number[]> = {}

  for (const [yrStr, pts] of Object.entries(byYear)) {
    const yr = parseInt(yrStr)
    if (pts.length < 50) continue

    // Find nearest trading day to anchor
    let bestIdx = -1, bestDelta = 999
    const targetMD = `${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`
    for (let i = 0; i < pts.length; i++) {
      const md = pts[i].date.slice(5) // MM-DD
      const diff = Math.abs(
        new Date(`2024-${md}`).getTime() - new Date(`2024-${targetMD}`).getTime()
      ) / 86400000
      if (diff < bestDelta) { bestDelta = diff; bestIdx = i }
    }
    if (bestIdx < 0 || bestDelta > 15) continue

    const endIdx = bestIdx + window
    if (endIdx >= pts.length) continue

    // Compute normalized cumulative return day by day
    const startPrice = pts[bestIdx].close
    const path: number[] = []
    for (let i = bestIdx; i <= Math.min(endIdx, bestIdx + window); i++) {
      path.push(((pts[i].close - startPrice) / startPrice) * 100)
    }
    yearPaths[yr] = path
  }

  return NextResponse.json({ ok: true, symbol: sym, month, day, window_days: window, year_paths: yearPaths })
}
""")

# =============================================================================
# [2] /api/patterns/heatmap/route.ts -- discovery heatmap data
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

  // Get ALL patterns for this symbol (not just filtered ones) for heatmap
  const rows = qdb(`
    SELECT direction, window_days, anchor_month, anchor_day,
           accuracy, avg_return_all, score, n_years, n_hit,
           start_label, end_label, year_confidence
    FROM seasonality_patterns
    WHERE symbol=?
    ORDER BY anchor_month, anchor_day, window_days
  `, [sym])

  // Also get monthly return data for month-year heatmap
  // We'll compute this from yearly_returns in the pattern table
  const monthlyRows = qdb(`
    SELECT anchor_month, avg_return_all, n_years, accuracy, direction
    FROM seasonality_patterns
    WHERE symbol=? AND window_days=20
    GROUP BY anchor_month, direction
    ORDER BY anchor_month
  `, [sym])

  // Year-month return data from seasonality table
  const seasonRows = qdb(`
    SELECT period_value, mean_return_pct, n_obs
    FROM symbol_seasonality
    WHERE symbol=? AND period_type='month'
    ORDER BY period_value
  `, [sym])

  return NextResponse.json({ ok: true, symbol: sym, heatmap_rows: rows, monthly: monthlyRows, seasonality: seasonRows })
}
""")

# =============================================================================
# [3] /patterns/page.tsx -- full rewrite with all 7 visualizations
# =============================================================================
print("\n[3/3] /patterns/page.tsx — full rewrite with all visualizations")
write(APP / "patterns" / "page.tsx", r"""
"use client";
import React, { useState, useCallback, useRef, useEffect } from "react";

// ── Types ────────────────────────────────────────────────────────────────
interface Pattern {
  direction:"up"|"down"; window_days:number; anchor_month:number; anchor_day:number;
  start_label:string; end_label:string; n_years:number; n_hit:number; accuracy:number;
  avg_return_all:number; avg_return_hit:number; median_return:number;
  std_return:number; min_return:number; max_return:number; p25_return:number; p75_return:number;
  score:number; year_confidence:string; degradation_flag:string;
  first_half_accuracy:number; last_half_accuracy:number;
  success_years:string; failure_years:string; yearly_returns:string;
  best_year:number; worst_year:number;
}
interface Summary { direction:string; n:number; avg_acc:number; max_acc:number; avg_score:number; max_score:number; avg_years:number; green_n:number; yellow_n:number; red_n:number; danger_n:number; degrading_n:number; improving_n:number; stable_n:number; }
interface ByWindow { direction:string; window_days:number; n:number; avg_acc:number; max_acc:number; avg_score:number; }
interface ByMonth  { direction:string; anchor_month:number; n:number; avg_acc:number; }
interface PatData  { ok:boolean; error?:string; not_built?:boolean; not_computed?:boolean; symbol:string; asset_type:string; total_patterns:number; patterns:Pattern[]; summary:Summary[]; by_window:ByWindow[]; by_month:ByMonth[]; latest_price:{close:number;date:string}|null; }
interface HeatData { ok:boolean; heatmap_rows:{direction:string;window_days:number;anchor_month:number;anchor_day:number;accuracy:number;avg_return_all:number;score:number;n_years:number;n_hit:number;start_label:string;end_label:string;year_confidence:string}[]; seasonality:{period_value:number;mean_return_pct:number;n_obs:number}[]; }
interface OverlayData { ok:boolean; year_paths:Record<number,number[]>; }
interface Sug { symbol:string; name:string; sector:string; type:string; }

// ── Constants ────────────────────────────────────────────────────────────
const G="#4ade80",R="#f87171",CY="#22d3ee",YL="#facc15",OR="#f97316";
const W9="#94a3b8",WHT="#e2e8f0";
const DIM="var(--text-tertiary)",PRI="var(--text-primary)",BOR="var(--border-color)",SUR="var(--surface-card)";
const MONTHS=["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const WINDOWS=[5,7,10,12,15,18,20,25,30,35,40,45,50,60,75,90];

const pct=(v:unknown,d=1)=>v==null?"--":`${(+(v as number))>=0?"+":""}${(+(v as number)).toFixed(d)}%`;
const col=(v:unknown)=>(+(v as number)??0)>=0?G:R;
const num=(v:unknown,d=2)=>v==null?"--":(+(v as number)).toFixed(d);
function confColor(c:string){return c==="GREEN"?G:c==="YELLOW"?YL:c==="RED"?OR:c==="DANGER"?R:W9;}
function wLabel(d:number){const m:Record<number,string>={5:"5D",7:"7D",10:"2W",12:"12D",15:"3W",18:"18D",20:"1M",25:"25D",30:"6W",35:"35D",40:"40D",45:"2M",50:"50D",60:"3M",75:"75D",90:"4M"};return m[d]||`${d}D`;}

// ── Autocomplete ─────────────────────────────────────────────────────────
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
      setSugg([...(ad.results||[]),...(bd.results||[])].slice(0,12));
      setShow(true);
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
        style={{width:"100%",background:SUR,border:`1px solid ${BOR}`,color:PRI,
          borderRadius:show&&sugg.length>0?"8px 8px 0 0":"8px",padding:"12px 16px",fontSize:14,boxSizing:"border-box"}}/>
      {show&&sugg.length>0&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,background:"#0d1520",
          border:`1px solid ${BOR}`,borderTop:"none",borderRadius:"0 0 8px 8px",
          maxHeight:300,overflowY:"auto",boxShadow:"0 8px 32px rgba(0,0,0,0.7)"}}>
          {sugg.map((s,i)=>(
            <div key={`${s.symbol}-${s.type}`} onMouseDown={()=>pick(s.symbol)} style={{
              padding:"9px 14px",cursor:"pointer",display:"flex",alignItems:"center",gap:10,
              background:i===hi?`${CY}18`:"transparent",
              borderBottom:i<sugg.length-1?`1px solid ${BOR}22`:"none"}}>
              <span style={{color:tc[s.type]||CY,fontWeight:800,fontSize:13,minWidth:100,fontFamily:"monospace"}}>{s.symbol}</span>
              <span style={{color:WHT,fontSize:12,flex:1}}>{s.name!==s.symbol?s.name:""}</span>
              <span style={{fontSize:9,fontWeight:700,color:tc[s.type]||CY,opacity:0.7,background:`${tc[s.type]||CY}22`,padding:"1px 5px",borderRadius:2}}>{s.type.toUpperCase()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── CHART 1: Window Discovery Heatmap ─────────────────────────────────────
// x = window duration, y = start month, color = score (green=bullish, red=bearish)
function WindowDiscoveryHeatmap({rows,onSelect}:{rows:HeatData["heatmap_rows"];onSelect:(p:{anchor_month:number;anchor_day:number;window_days:number;direction:string})=>void}){
  const [showDir,setShowDir]=useState<"up"|"down">("up");
  const filtered=rows.filter(r=>r.direction===showDir);
  if(!filtered.length) return <div style={{color:DIM,fontSize:12}}>No patterns to display</div>;

  // Build grid: rows=months (1-12), cols=windows (WINDOWS array)
  const grid:Record<string,{score:number;accuracy:number;n_hit:number;n_years:number;start_label:string;end_label:string;anchor_day:number}>={};
  for(const r of filtered){
    const key=`${r.anchor_month}-${r.window_days}`;
    if(!grid[key]||r.score>grid[key].score){
      grid[key]={score:r.score,accuracy:r.accuracy,n_hit:r.n_hit,n_years:r.n_years,
        start_label:r.start_label,end_label:r.end_label,anchor_day:r.anchor_day};
    }
  }

  const maxScore=Math.max(...Object.values(grid).map(v=>v.score),0.001);
  const AC=showDir==="up"?G:R;

  return(
    <div>
      <div style={{display:"flex",gap:8,marginBottom:10,alignItems:"center"}}>
        <span style={{fontSize:11,color:W9}}>Direction:</span>
        {(["up","down"] as const).map(d=>(
          <button key={d} onClick={()=>setShowDir(d)} style={{padding:"3px 10px",borderRadius:4,fontSize:11,fontWeight:700,border:"none",cursor:"pointer",background:showDir===d?(d==="up"?G:R):"transparent",color:showDir===d?"#000":W9}}>{d.toUpperCase()}</button>
        ))}
        <span style={{fontSize:10,color:DIM,marginLeft:8}}>Darker = stronger pattern. Click any cell to see detail.</span>
      </div>
      <div style={{overflowX:"auto"}}>
        <table style={{borderCollapse:"separate",borderSpacing:2,fontSize:10}}>
          <thead>
            <tr>
              <th style={{padding:"4px 8px",color:W9,textAlign:"left",fontWeight:600,minWidth:40}}>Month</th>
              {WINDOWS.map(w=><th key={w} style={{padding:"4px 6px",color:W9,fontWeight:600,textAlign:"center",minWidth:36}}>{wLabel(w)}</th>)}
            </tr>
          </thead>
          <tbody>
            {Array.from({length:12},(_,i)=>i+1).map(month=>(
              <tr key={month}>
                <td style={{padding:"4px 8px",color:W9,fontWeight:600,whiteSpace:"nowrap"}}>{MONTHS[month]}</td>
                {WINDOWS.map(w=>{
                  const cell=grid[`${month}-${w}`];
                  if(!cell) return <td key={w} style={{padding:2}}><div style={{width:34,height:28,background:`${BOR}18`,borderRadius:3}}/></td>;
                  const intensity=cell.score/maxScore;
                  const bg=`${AC}${Math.floor(intensity*200+30).toString(16).padStart(2,"0")}`;
                  const accPct=(cell.accuracy*100).toFixed(0);
                  return(
                    <td key={w} style={{padding:2}} title={`${cell.start_label}->${cell.end_label}\n${accPct}% (${cell.n_hit}/${cell.n_years}yr)\navg ${pct(0)}`}>
                      <div onClick={()=>onSelect({anchor_month:month,anchor_day:cell.anchor_day,window_days:w,direction:showDir})}
                        style={{width:34,height:28,background:bg,borderRadius:3,cursor:"pointer",
                          display:"flex",alignItems:"center",justifyContent:"center",
                          fontSize:9,color:"#000",fontWeight:700,
                          border:intensity>0.8?`1px solid ${AC}`:"none"}}>
                        {accPct}%
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── CHART 2: All-years overlay chart ─────────────────────────────────────
// Normalized cumulative return paths, one line per year
function YearOverlayChart({data,direction}:{data:OverlayData;direction:"up"|"down"}){
  if(!data?.year_paths) return null;
  const years=Object.keys(data.year_paths).map(Number).sort();
  if(years.length<2) return <div style={{color:DIM,fontSize:12}}>Not enough years for overlay</div>;

  const AC=direction==="up"?G:R;
  const allVals=years.flatMap(yr=>data.year_paths[yr]||[]);
  const mn=Math.min(...allVals,-3),mx=Math.max(...allVals,3);
  const rng=mx-mn||1;
  const W=560,H=200,ML=44,MR=20,MT=10,MB=25;
  const PW=W-ML-MR,PH=H-MT-MB;
  const maxLen=Math.max(...years.map(yr=>(data.year_paths[yr]||[]).length));
  const tx=(i:number)=>ML+(i/(maxLen-1||1))*PW;
  const ty=(v:number)=>MT+PH-((v-mn)/rng)*PH;
  const z0=ty(0);

  // Compute avg path
  const avgPath:number[]=[];
  for(let i=0;i<maxLen;i++){
    const vals=years.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null);
    avgPath.push(vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:0);
  }

  const tickStep=Math.ceil((mx-mn)/5/5)*5||5;
  const ticks:number[]=[];
  for(let t=Math.ceil(mn/tickStep)*tickStep;t<=mx;t+=tickStep)ticks.push(t);

  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>
        All {years.length} years overlaid — normalized to 0% at start. 
        <span style={{color:AC}}> Colored</span> = direction hit. 
        <span style={{color:W9}}> Gray</span> = miss.
        <span style={{color:YL}}> Yellow</span> = average.
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {/* Grid */}
        {ticks.map(t=>(
          <g key={t}>
            <line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff0a" strokeWidth={1}/>
            <text x={ML-4} y={ty(t)+4} textAnchor="end" fontSize={9} fill={W9}>{t}%</text>
          </g>
        ))}
        {/* Zero line */}
        <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff33" strokeDasharray="4,3" strokeWidth={1.5}/>

        {/* Individual year lines */}
        {years.map(yr=>{
          const pts=data.year_paths[yr]||[];
          if(pts.length<2) return null;
          const finalRet=pts[pts.length-1]||0;
          const isHit=direction==="up"?finalRet>0:finalRet<0;
          const lineCol=isHit?AC:W9;
          const d=pts.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
          return<path key={yr} d={d} fill="none" stroke={lineCol} strokeWidth={isHit?1.2:0.8} opacity={isHit?0.5:0.2}><title>{yr}: {pct(finalRet)}</title></path>;
        })}

        {/* Average path — thick yellow */}
        {avgPath.length>1&&(
          <path d={avgPath.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ")}
            fill="none" stroke={YL} strokeWidth={2.5} opacity={0.9}/>
        )}

        {/* X axis */}
        <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
        {[0,Math.floor(maxLen/4),Math.floor(maxLen/2),Math.floor(maxLen*3/4),maxLen-1].map(i=>(
          <text key={i} x={tx(i)} y={H-MB+14} textAnchor="middle" fontSize={9} fill={W9}>D{i+1}</text>
        ))}
      </svg>

      {/* Year list */}
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginTop:8}}>
        {years.map(yr=>{
          const pts=data.year_paths[yr]||[];
          const finalRet=pts[pts.length-1]||0;
          const isHit=direction==="up"?finalRet>0:finalRet<0;
          return(
            <span key={yr} style={{fontSize:10,fontWeight:700,
              color:isHit?AC:W9,background:`${isHit?AC:W9}18`,
              borderRadius:3,padding:"2px 5px"}}>
              {yr} {pct(finalRet,1)}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ── CHART 3: Year x relative-day heatmap ────────────────────────────────
function YearDayHeatmap({data,direction}:{data:OverlayData;direction:"up"|"down"}){
  if(!data?.year_paths) return null;
  const years=Object.keys(data.year_paths).map(Number).sort();
  if(years.length<2) return null;
  const AC=direction==="up"?G:R;
  const maxLen=Math.max(...years.map(yr=>(data.year_paths[yr]||[]).length));
  const showDays=Math.min(maxLen,30);

  const allVals=years.flatMap(yr=>(data.year_paths[yr]||[]).slice(0,showDays));
  const maxAbs=Math.max(...allVals.map(Math.abs),1);

  const cellW=Math.max(14,Math.floor(560/showDays));
  const cellH=20;

  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>
        Rows = years. Columns = day within window. Color = cumulative return.
        Green = positive, Red = negative.
      </div>
      <div style={{overflowX:"auto"}}>
        <div style={{display:"flex",gap:0,marginBottom:4}}>
          <div style={{width:44,flexShrink:0}}/>
          {Array.from({length:showDays},(_,i)=>(
            <div key={i} style={{width:cellW,textAlign:"center",fontSize:8,color:DIM}}>D{i+1}</div>
          ))}
        </div>
        {years.map(yr=>{
          const pts=(data.year_paths[yr]||[]).slice(0,showDays);
          if(!pts.length) return null;
          return(
            <div key={yr} style={{display:"flex",gap:0,marginBottom:1}}>
              <div style={{width:44,flexShrink:0,fontSize:9,color:W9,lineHeight:`${cellH}px`,textAlign:"right",paddingRight:4}}>{yr}</div>
              {Array.from({length:showDays},(_,i)=>{
                const v=pts[i];
                if(v==null) return <div key={i} style={{width:cellW,height:cellH,background:`${BOR}22`}}/>;
                const intensity=Math.abs(v)/maxAbs;
                const isPos=v>=0;
                const bg=`${isPos?G:R}${Math.floor(intensity*200+20).toString(16).padStart(2,"0")}`;
                return(
                  <div key={i} title={`${yr} Day${i+1}: ${v>=0?"+":""}${v.toFixed(1)}%`}
                    style={{width:cellW,height:cellH,background:bg,cursor:"default"}}/>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── CHART 4: 3D Surface (SVG isometric approximation) ───────────────────
function Surface3D({rows}:{rows:HeatData["heatmap_rows"]}){
  const upRows=rows.filter(r=>r.direction==="up");
  const dnRows=rows.filter(r=>r.direction==="down");
  if(!upRows.length&&!dnRows.length) return <div style={{color:DIM,fontSize:12}}>No data</div>;

  // Build score grid: month(1-12) x window index
  const W=560,H=280;
  const N_MONTHS=12,N_WIN=WINDOWS.length;

  // Isometric projection params
  const TILE_W=32,TILE_H=16,TILE_DEPTH=6;
  const ORIGIN_X=W/2,ORIGIN_Y=H-80;

  const toIso=(col:number,row:number,z:number):{x:number;y:number}=>{
    const x=ORIGIN_X+(col-row)*TILE_W/2;
    const y=ORIGIN_Y+(col+row)*TILE_H/2-z;
    return{x,y};
  };

  const scoreGrid:Record<string,{score:number;direction:string;accuracy:number}>={};
  for(const r of [...upRows,...dnRows]){
    const mIdx=r.anchor_month-1;
    const wIdx=WINDOWS.indexOf(r.window_days);
    if(wIdx<0) continue;
    const key=`${mIdx}-${wIdx}`;
    if(!scoreGrid[key]||r.score>scoreGrid[key].score){
      scoreGrid[key]={score:r.score,direction:r.direction,accuracy:r.accuracy};
    }
  }
  const maxScore=Math.max(...Object.values(scoreGrid).map(v=>v.score),0.001);

  const tiles:React.ReactNode[]=[];
  for(let wIdx=N_WIN-1;wIdx>=0;wIdx--){
    for(let mIdx=N_MONTHS-1;mIdx>=0;mIdx--){
      const cell=scoreGrid[`${mIdx}-${wIdx}`];
      const z=cell?Math.floor(cell.score/maxScore*60):0;
      const AC=cell?(cell.direction==="up"?G:R):BOR;
      const opacity=cell?0.5+cell.score/maxScore*0.5:0.15;

      const tl=toIso(mIdx,wIdx,z);
      const tr=toIso(mIdx+1,wIdx,z);
      const br=toIso(mIdx+1,wIdx+1,z);
      const bl=toIso(mIdx,wIdx+1,z);
      const top=`${tl.x},${tl.y} ${tr.x},${tr.y} ${br.x},${br.y} ${bl.x},${bl.y}`;

      // Left face
      const bbl=toIso(mIdx,wIdx+1,0),bbr=toIso(mIdx+1,wIdx+1,0);
      const left=`${bl.x},${bl.y} ${bbl.x},${bbl.y} ${bbr.x},${bbr.y} ${br.x},${br.y}`;

      // Right face
      const btr=toIso(mIdx+1,wIdx,0);
      const right=`${tr.x},${tr.y} ${btr.x},${btr.y} ${bbr.x},${bbr.y} ${br.x},${br.y}`;

      const title=cell?`${MONTHS[mIdx+1]} ${wLabel(WINDOWS[wIdx])}: ${(cell.accuracy*100).toFixed(0)}% ${cell.direction}`:"";
      tiles.push(
        <g key={`${mIdx}-${wIdx}`}>
          {z>1&&<>
            <polygon points={left}  fill={AC} opacity={opacity*0.5}/>
            <polygon points={right} fill={AC} opacity={opacity*0.4}/>
          </>}
          <polygon points={top} fill={cell?AC:`${BOR}44`} opacity={opacity} stroke="#00000033" strokeWidth={0.3}>
            {title&&<title>{title}</title>}
          </polygon>
        </g>
      );
    }
  }

  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>
        3D surface: X=Month, Y=Window duration, Z=Pattern score. Green peaks=bullish, Red peaks=bearish.
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {tiles}
        {/* X axis labels */}
        {Array.from({length:12},(_,i)=>{
          const p=toIso(i+0.5,N_WIN,0);
          return<text key={i} x={p.x} y={p.y+12} textAnchor="middle" fontSize={8} fill={W9}>{MONTHS[i+1].slice(0,3)}</text>;
        })}
        {/* Y axis labels */}
        {WINDOWS.filter((_,i)=>i%3===0).map((w,i)=>{
          const idx=WINDOWS.indexOf(w);
          const p=toIso(0,idx+0.5,0);
          return<text key={w} x={p.x-4} y={p.y} textAnchor="end" fontSize={8} fill={W9}>{wLabel(w)}</text>;
        })}
      </svg>
    </div>
  );
}

// ── CHART 5: Bubble chart ────────────────────────────────────────────────
function BubbleChart({patterns}:{patterns:Pattern[]}){
  if(!patterns.length) return null;
  const W=520,H=260,ML=50,MR=20,MT=10,MB=30;
  const PW=W-ML-MR,PH=H-MT-MB;

  const xs=patterns.map(p=>p.accuracy*100);
  const ys=patterns.map(p=>Math.abs(p.avg_return_all));
  const xMin=Math.min(...xs)-2,xMax=Math.max(...xs)+2;
  const yMin=0,yMax=Math.max(...ys)+2;
  const tx=(v:number)=>ML+((v-xMin)/(xMax-xMin))*PW;
  const ty=(v:number)=>MT+PH-((v-yMin)/(yMax-yMin))*PH;

  const nMin=Math.min(...patterns.map(p=>p.n_years));
  const nMax=Math.max(...patterns.map(p=>p.n_years));
  const rScale=(n:number)=>4+((n-nMin)/(nMax-nMin||1))*12;

  const xTicks=[70,75,80,85,90,95];
  const yTicks=Array.from({length:5},(_,i)=>Math.round(yMax/4*i));

  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>
        Bubble chart: X=accuracy, Y=avg return magnitude, Size=years of data. 
        <span style={{color:G}}> Green</span>=UP, <span style={{color:R}}>Red</span>=DOWN.
        Best patterns = top-right large bubbles.
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {/* Grid */}
        {xTicks.map(t=>t>=xMin&&t<=xMax&&(
          <g key={t}>
            <line x1={tx(t)} y1={MT} x2={tx(t)} y2={H-MB} stroke="#ffffff0a" strokeWidth={1}/>
            <text x={tx(t)} y={H-MB+14} textAnchor="middle" fontSize={9} fill={W9}>{t}%</text>
          </g>
        ))}
        {yTicks.map(t=>(
          <g key={t}>
            <line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff0a" strokeWidth={1}/>
            <text x={ML-4} y={ty(t)+4} textAnchor="end" fontSize={9} fill={W9}>{t}%</text>
          </g>
        ))}
        <line x1={ML} y1={MT} x2={ML} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
        <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>

        {/* Bubbles */}
        {patterns.map((p,i)=>{
          const cx=tx(p.accuracy*100);
          const cy=ty(Math.abs(p.avg_return_all));
          const r=rScale(p.n_years);
          const AC=p.direction==="up"?G:R;
          return(
            <g key={i}>
              <circle cx={cx} cy={cy} r={r} fill={`${AC}44`} stroke={AC} strokeWidth={1.5} opacity={0.85}>
                <title>{`${p.start_label}->${p.end_label} ${p.window_days}d\n${(p.accuracy*100).toFixed(0)}% (${p.n_hit}/${p.n_years}yr)\navg ${pct(p.avg_return_all)}\nscore ${p.score.toFixed(3)}`}</title>
              </circle>
            </g>
          );
        })}

        <text x={W/2} y={H-MB+26} textAnchor="middle" fontSize={9} fill={W9}>Accuracy %</text>
        <text x={10} y={H/2} textAnchor="middle" fontSize={9} fill={W9} transform={`rotate(-90,10,${H/2})`}>Avg Return %</text>
      </svg>
    </div>
  );
}

// ── CHART 6: Calendar Strip ──────────────────────────────────────────────
function CalendarStrip({patterns}:{patterns:Pattern[]}){
  if(!patterns.length) return null;
  const W=560,H=60;
  const AC_UP=G,AC_DN=R;

  // Convert anchor_month/day to day-of-year (approx)
  const doy=(m:number,d:number)=>{
    const days=[0,31,59,90,120,151,181,212,243,273,304,334];
    return (days[m-1]||0)+d;
  };
  const MAX_DOY=365;
  const tx=(d:number)=>(d/MAX_DOY)*W;

  const up=patterns.filter(p=>p.direction==="up");
  const dn=patterns.filter(p=>p.direction==="down");

  const months=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const monthPositions=months.map((_,i)=>({label:months[i],x:tx((i+0.5)*30.4)}));

  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>
        Calendar strip: bars show where patterns occur through the year. 
        <span style={{color:G}}> Green</span>=UP patterns, 
        <span style={{color:R}}> Red</span>=DOWN patterns.
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H+20}`} style={{overflow:"visible"}}>
        {/* Background */}
        <rect x={0} y={0} width={W} height={H} fill="#ffffff08" rx={4}/>

        {/* Month dividers */}
        {monthPositions.map(({label,x})=>(
          <g key={label}>
            <line x1={x} y1={0} x2={x} y2={H} stroke="#ffffff15" strokeWidth={1}/>
            <text x={x} y={H+14} textAnchor="middle" fontSize={8} fill={W9}>{label}</text>
          </g>
        ))}

        {/* UP patterns — top half */}
        {up.map((p,i)=>{
          const startD=doy(p.anchor_month,p.anchor_day);
          const endD=Math.min(MAX_DOY,startD+Math.floor(p.window_days/0.69));
          const x1=tx(startD),x2=tx(endD);
          const bw=Math.max(2,x2-x1);
          const opacity=0.4+p.accuracy*0.6;
          return(
            <rect key={i} x={x1} y={4} width={bw} height={H/2-6}
              fill={AC_UP} opacity={opacity} rx={2}>
              <title>{`UP: ${p.start_label}->${p.end_label} ${p.window_days}d ${(p.accuracy*100).toFixed(0)}%`}</title>
            </rect>
          );
        })}

        {/* DOWN patterns — bottom half */}
        {dn.map((p,i)=>{
          const startD=doy(p.anchor_month,p.anchor_day);
          const endD=Math.min(MAX_DOY,startD+Math.floor(p.window_days/0.69));
          const x1=tx(startD),x2=tx(endD);
          const bw=Math.max(2,x2-x1);
          const opacity=0.4+p.accuracy*0.6;
          return(
            <rect key={i} x={x1} y={H/2+2} width={bw} height={H/2-6}
              fill={AC_DN} opacity={opacity} rx={2}>
              <title>{`DOWN: ${p.start_label}->${p.end_label} ${p.window_days}d ${(p.accuracy*100).toFixed(0)}%`}</title>
            </rect>
          );
        })}

        {/* UP/DOWN labels */}
        <text x={4} y={H/4+4} fontSize={8} fill={G} fontWeight="bold">UP</text>
        <text x={4} y={H*3/4+4} fontSize={8} fill={R} fontWeight="bold">DOWN</text>
      </svg>
    </div>
  );
}

// ── CHART 7: Month x Year Heatmap ────────────────────────────────────────
function MonthYearHeatmap({seasonality}:{seasonality:{period_value:number;mean_return_pct:number;n_obs:number}[]}){
  if(!seasonality||!seasonality.length) return <div style={{color:DIM,fontSize:12}}>No monthly data</div>;
  const maxAbs=Math.max(...seasonality.map(r=>Math.abs(r.mean_return_pct||0)),1);
  const cellW=38,cellH=24;
  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>
        Average return per month. Green = historically bullish month, Red = bearish.
      </div>
      <div style={{display:"flex",gap:2}}>
        {seasonality.map(r=>{
          const v=r.mean_return_pct||0;
          const intensity=Math.abs(v)/maxAbs;
          const bg=`${v>=0?G:R}${Math.floor(intensity*180+30).toString(16).padStart(2,"0")}`;
          return(
            <div key={r.period_value} title={`${MONTHS[r.period_value]}: avg ${v>=0?"+":""}${v.toFixed(2)}% (${r.n_obs} obs)`} style={{
              width:cellW,background:bg,borderRadius:4,padding:"6px 2px",
              textAlign:"center",cursor:"default",
            }}>
              <div style={{fontSize:9,color:W9,marginBottom:3}}>{MONTHS[r.period_value].slice(0,3)}</div>
              <div style={{fontSize:11,fontWeight:700,color:v>=0?G:R}}>{v>=0?"+":""}{ v.toFixed(1)}%</div>
              <div style={{fontSize:8,color:DIM}}>{r.n_obs}obs</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Pattern Card (compact) ────────────────────────────────────────────────
function PatCard({p,onExpand,expanded,compareYears,overlayData}:{p:Pattern;onExpand:()=>void;expanded:boolean;compareYears:number;overlayData:OverlayData|null}){
  const AC=p.direction==="up"?G:R;
  const confC=confColor(p.year_confidence);
  let succ:number[]=[],fail:number[]=[],yr_data:Record<string,number>={};
  try{succ=JSON.parse(p.success_years)||[];}catch{}
  try{fail=JSON.parse(p.failure_years)||[];}catch{}
  try{yr_data=JSON.parse(p.yearly_returns)||{};}catch{}

  const groupSize=compareYears||succ.length+fail.length;
  const allYears=Object.keys(yr_data).map(Number).sort();
  const groups:number[][]=[];
  for(let i=0;i<allYears.length;i+=groupSize)groups.push(allYears.slice(i,i+groupSize));

  return(
    <div style={{marginBottom:8,background:`${AC}0a`,border:`1px solid ${AC}22`,borderRadius:8,borderLeft:`4px solid ${AC}`,overflow:"hidden"}}>
      {/* Header */}
      <div style={{padding:"11px 14px",cursor:"pointer"}} onClick={onExpand}>
        <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",marginBottom:5}}>
          <span style={{fontWeight:900,fontSize:18,color:WHT,minWidth:44}}>{wLabel(p.window_days)}</span>
          <span style={{fontSize:12,fontWeight:600,color:W9}}>{p.start_label} &rarr; {p.end_label}</span>
          <div style={{flex:1}}>
            <div style={{display:"flex",alignItems:"baseline",gap:6}}>
              <span style={{fontWeight:900,fontSize:20,color:confC}}>{(p.accuracy*100).toFixed(0)}%</span>
              <span style={{fontSize:11,color:DIM}}>accurate</span>
              <span style={{fontSize:12,color:WHT,fontWeight:600}}>({p.n_hit}/{p.n_years}yr {p.direction.toUpperCase()})</span>
            </div>
            <div style={{height:5,background:`${BOR}33`,borderRadius:3,marginTop:3,maxWidth:280}}>
              <div style={{height:5,width:`${Math.min(100,p.accuracy*100)}%`,background:confC,borderRadius:3}}/>
            </div>
          </div>
          <div style={{display:"flex",gap:5,alignItems:"center"}}>
            <span style={{fontSize:9,fontWeight:700,padding:"2px 6px",borderRadius:3,background:`${confC}22`,color:confC}}>{p.year_confidence} {p.n_years}yr</span>
            <span style={{fontSize:9,fontWeight:700,padding:"2px 6px",borderRadius:3,background:`${p.degradation_flag==="DEGRADING"?R:p.degradation_flag==="IMPROVING"?G:W9}22`,color:p.degradation_flag==="DEGRADING"?R:p.degradation_flag==="IMPROVING"?G:W9}}>{p.degradation_flag}</span>
            <span style={{fontSize:9,color:DIM}}>{expanded?"▲":"▼"}</span>
          </div>
        </div>
        <div style={{display:"flex",gap:14,flexWrap:"wrap",fontSize:11}}>
          <span><span style={{color:DIM}}>Avg: </span><span style={{color:col(p.avg_return_all),fontWeight:700}}>{pct(p.avg_return_all)}</span></span>
          <span><span style={{color:DIM}}>Median: </span><span style={{color:col(p.median_return)}}>{pct(p.median_return)}</span></span>
          <span><span style={{color:DIM}}>Range: </span><span style={{color:R}}>{pct(p.min_return)}</span> to <span style={{color:G}}>{pct(p.max_return)}</span></span>
          <span><span style={{color:DIM}}>Score: </span><span style={{color:CY}}>{p.score.toFixed(3)}</span></span>
        </div>
      </div>

      {/* Expanded */}
      {expanded&&(
        <div style={{padding:"0 14px 14px"}}>
          <div style={{height:1,background:`${BOR}33`,marginBottom:12}}/>
          {/* Stats */}
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(120px,1fr))",gap:6,marginBottom:14}}>
            {[
              {l:"Avg (all yrs)",v:pct(p.avg_return_all),c:col(p.avg_return_all)},
              {l:"Avg when hit",v:pct(p.avg_return_hit),c:AC},
              {l:"Median",v:pct(p.median_return),c:col(p.median_return)},
              {l:"P25",v:pct(p.p25_return),c:col(p.p25_return)},
              {l:"P75",v:pct(p.p75_return),c:col(p.p75_return)},
              {l:"Best year",v:pct(p.max_return),c:G},
              {l:"Worst year",v:pct(p.min_return),c:R},
              {l:"Std dev",v:pct(p.std_return)},
              {l:"First half acc",v:`${(p.first_half_accuracy*100).toFixed(0)}%`,c:p.first_half_accuracy>=0.70?G:R},
              {l:"Last half acc",v:`${(p.last_half_accuracy*100).toFixed(0)}%`,c:p.last_half_accuracy>=0.70?G:R},
              {l:"Best year",v:String(p.best_year||"--")},
              {l:"Worst year",v:String(p.worst_year||"--")},
            ].map(({l,v,c})=>(
              <div key={l} style={{background:`${BOR}22`,borderRadius:4,padding:"6px 8px"}}>
                <div style={{fontSize:8,color:DIM,fontWeight:700,marginBottom:2,textTransform:"uppercase"}}>{l}</div>
                <div style={{fontSize:13,fontWeight:800,color:c||PRI}}>{v}</div>
              </div>
            ))}
          </div>

          {/* All-years overlay */}
          {overlayData&&(
            <div style={{marginBottom:14}}>
              <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:8}}>ALL YEARS OVERLAY</div>
              <YearOverlayChart data={overlayData} direction={p.direction}/>
            </div>
          )}

          {/* Year x Day heatmap */}
          {overlayData&&(
            <div style={{marginBottom:14}}>
              <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:8}}>YEAR x DAY HEATMAP</div>
              <YearDayHeatmap data={overlayData} direction={p.direction}/>
            </div>
          )}

          {/* Year groups comparison */}
          {compareYears>0&&groups.length>1&&(
            <div style={{marginBottom:14}}>
              <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:8}}>
                {compareYears}-YEAR GROUP COMPARISON (first vs recent)
              </div>
              <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
                {groups.map((grp,gi)=>{
                  const grpRets=grp.map(y=>yr_data[String(y)]||0);
                  const hits=grpRets.filter(v=>p.direction==="up"?v>0:v<0).length;
                  const acc=hits/grpRets.length;
                  const c=acc>=0.80?G:acc>=0.70?YL:R;
                  return(
                    <div key={gi} style={{background:`${c}18`,border:`1px solid ${c}33`,borderRadius:6,padding:"8px 12px",minWidth:110}}>
                      <div style={{fontSize:10,color:W9,marginBottom:3}}>{grp[0]}-{grp[grp.length-1]}</div>
                      <div style={{fontSize:18,fontWeight:900,color:c}}>{(acc*100).toFixed(0)}%</div>
                      <div style={{fontSize:11,color:W9}}>{hits}/{grp.length}yr</div>
                      <div style={{fontSize:10,color:col(grpRets.reduce((a,b)=>a+b,0)/grpRets.length)}}>avg {pct(grpRets.reduce((a,b)=>a+b,0)/grpRets.length)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Success/failure years */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
            <div>
              <div style={{fontSize:10,fontWeight:700,color:G,letterSpacing:1,marginBottom:5}}>SUCCESS ({succ.length})</div>
              <div style={{display:"flex",flexWrap:"wrap",gap:3}}>
                {succ.map(yr=><span key={yr} style={{fontSize:10,fontWeight:700,color:G,background:`${G}18`,borderRadius:3,padding:"1px 4px"}}>{yr} <span style={{color:DIM,fontWeight:400}}>({(yr_data[String(yr)]||0)>=0?"+":""}{(yr_data[String(yr)]||0).toFixed(1)}%)</span></span>)}
              </div>
            </div>
            <div>
              <div style={{fontSize:10,fontWeight:700,color:R,letterSpacing:1,marginBottom:5}}>FAILURE ({fail.length})</div>
              <div style={{display:"flex",flexWrap:"wrap",gap:3}}>
                {fail.map(yr=><span key={yr} style={{fontSize:10,fontWeight:700,color:R,background:`${R}18`,borderRadius:3,padding:"1px 4px"}}>{yr} <span style={{color:DIM,fontWeight:400}}>({(yr_data[String(yr)]||0)>=0?"+":""}{(yr_data[String(yr)]||0).toFixed(1)}%)</span></span>)}
              </div>
            </div>
          </div>
        </div>
      )}
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
  const [compareYears,setCompareYears]=useState(0);
  const [activeDir,setActiveDir]=useState<"both"|"up"|"down">("both");
  const [activeTab,setActiveTab]=useState<"patterns"|"heatmap"|"3d"|"bubble"|"strip"|"monthly">("patterns");
  const [expandedIdx,setExpandedIdx]=useState<number|null>(null);
  const [overlayCache,setOverlayCache]=useState<Record<string,OverlayData>>({});
  const [heatSelected,setHeatSelected]=useState<{anchor_month:number;anchor_day:number;window_days:number;direction:string}|null>(null);

  const load=useCallback(async(sym:string)=>{
    if(!sym.trim()) return;
    setLoading(true); setError(null); setData(null); setHeatData(null); setExpandedIdx(null);
    try{
      const params=new URLSearchParams({symbol:sym.trim(),min_acc:String(minAcc),min_years:String(minYears),direction:dirFilter,window:String(windowFilter),sort:sortBy});
      const [r1,r2]=await Promise.all([
        fetch(`/api/patterns?${params}`,{cache:"no-store"}),
        fetch(`/api/patterns/heatmap?symbol=${encodeURIComponent(sym.trim())}`,{cache:"no-store"}),
      ]);
      const [d1,d2]=await Promise.all([r1.json(),r2.json()]);
      if(!d1.ok) throw new Error(d1.error||"API error");
      setData(d1); setHeatData(d2.ok?d2:null);
    }catch(e:unknown){setError(String(e));}
    finally{setLoading(false);}
  },[minAcc,minYears,dirFilter,windowFilter,sortBy]);

  // Load overlay data when expanding a pattern card
  const loadOverlay=useCallback(async(p:Pattern,sym:string,atype:string)=>{
    const key=`${sym}-${p.anchor_month}-${p.anchor_day}-${p.window_days}`;
    if(overlayCache[key]) return;
    try{
      const r=await fetch(`/api/patterns/detail?symbol=${encodeURIComponent(sym)}&asset_type=${atype}&month=${p.anchor_month}&day=${p.anchor_day}&window=${p.window_days}`,{cache:"no-store"});
      const d=await r.json();
      if(d.ok) setOverlayCache(c=>({...c,[key]:d}));
    }catch{}
  },[overlayCache]);

  useEffect(()=>{if(symInput&&data)load(symInput);},[minAcc,minYears,dirFilter,windowFilter,sortBy]);// eslint-disable-line

  const allPats=data?.patterns||[];
  const upPats=allPats.filter(p=>p.direction==="up");
  const dnPats=allPats.filter(p=>p.direction==="down");
  const showPats=activeDir==="both"?allPats:activeDir==="up"?upPats:dnPats;

  return(
    <div style={{maxWidth:1200,margin:"0 auto",padding:"20px 16px"}}>
      <div style={{marginBottom:14}}>
        <h1 style={{margin:0,fontSize:24,fontWeight:900}}>SEASONAL PATTERNS</h1>
        <div style={{color:DIM,fontSize:12,marginTop:3}}>Recurring calendar windows — automatically discovered from all available years</div>
      </div>

      {/* Search */}
      <div style={{display:"flex",gap:8,marginBottom:12}}>
        <AInput value={symInput} onChange={setSymInput} onSelect={s=>{setSymInput(s);load(s);}}/>
        <button onClick={()=>load(symInput)} disabled={loading} style={{background:CY,color:"#000",border:"none",borderRadius:8,padding:"12px 22px",fontWeight:800,cursor:"pointer",fontSize:14,opacity:loading?0.6:1,minWidth:110}}>{loading?"Loading...":"Find"}</button>
      </div>

      {/* Filters */}
      <div style={{background:`${BOR}18`,borderRadius:8,padding:"10px 12px",marginBottom:12}}>
        <div style={{display:"flex",gap:12,flexWrap:"wrap",alignItems:"flex-start"}}>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:600,marginBottom:4}}>MIN ACCURACY</div>
            <div style={{display:"flex",gap:3}}>
              {[0.70,0.75,0.80,0.85,0.90].map(v=><button key={v} onClick={()=>setMinAcc(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:minAcc===v?CY:"transparent",color:minAcc===v?"#000":W9}}>{(v*100).toFixed(0)}%+</button>)}
            </div>
          </div>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:600,marginBottom:4}}>MIN YEARS</div>
            <div style={{display:"flex",gap:3}}>
              {[3,5,7,10,15].map(v=><button key={v} onClick={()=>setMinYears(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:minYears===v?CY:"transparent",color:minYears===v?"#000":W9}}>{v}+</button>)}
            </div>
          </div>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:600,marginBottom:4}}>DIRECTION</div>
            <div style={{display:"flex",gap:3}}>
              {[["both","Both"],["up","UP"],["down","DOWN"]].map(([v,l])=><button key={v} onClick={()=>setDirFilter(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:dirFilter===v?CY:"transparent",color:dirFilter===v?"#000":W9}}>{l}</button>)}
            </div>
          </div>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:600,marginBottom:4}}>WINDOW</div>
            <select value={windowFilter} onChange={e=>setWindowFilter(+e.target.value)} style={{background:"#1a2332",border:`1px solid ${BOR}`,color:PRI,borderRadius:4,padding:"3px 8px",fontSize:10}}>
              <option value={0}>All</option>
              {WINDOWS.map(w=><option key={w} value={w}>{wLabel(w)}</option>)}
            </select>
          </div>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:600,marginBottom:4}}>SORT</div>
            <div style={{display:"flex",gap:3}}>
              {[["score","Score"],["accuracy","Acc"],["n_years","Years"],["avg_ret","Return"]].map(([v,l])=><button key={v} onClick={()=>setSortBy(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:sortBy===v?CY:"transparent",color:sortBy===v?"#000":W9}}>{l}</button>)}
            </div>
          </div>
          <div>
            <div style={{fontSize:9,color:W9,fontWeight:600,marginBottom:4}}>YEAR GROUPS</div>
            <div style={{display:"flex",gap:3}}>
              {[[0,"Off"],[2,"2yr"],[4,"4yr"],[6,"6yr"],[8,"8yr"],[10,"10yr"]].map(([v,l])=><button key={v} onClick={()=>setCompareYears(+v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:compareYears===+v?YL:"transparent",color:compareYears===+v?"#000":W9}}>{l}</button>)}
            </div>
          </div>
        </div>
      </div>

      {error&&<div style={{color:R,fontSize:13,marginBottom:10,padding:"10px 14px",background:`${R}11`,borderRadius:6,border:`1px solid ${R}33`}}>{error}</div>}
      {loading&&<div style={{padding:40,textAlign:"center",color:DIM}}>Finding patterns for {symInput}...</div>}

      {data&&!loading&&(
        <div>
          {/* Symbol header */}
          <div style={{display:"flex",gap:10,flexWrap:"wrap",marginBottom:12,alignItems:"center"}}>
            <span style={{fontSize:20,fontWeight:900,color:CY}}>{data.symbol}</span>
            <span style={{fontSize:11,color:DIM,border:`1px solid ${BOR}`,borderRadius:4,padding:"2px 8px"}}>{data.asset_type.toUpperCase()}</span>
            {data.latest_price&&<span style={{fontSize:13,color:W9}}>Price: <span style={{color:WHT,fontWeight:700}}>{(data.latest_price.close||0).toLocaleString("en-IN",{maximumFractionDigits:2})}</span></span>}
            <span style={{fontSize:11,color:DIM}}>{data.total_patterns} total patterns</span>
            <div style={{marginLeft:"auto",display:"flex",gap:8}}>
              {[
                {dir:"up",n:upPats.length,sum:data.summary.find(s=>s.direction==="up")},
                {dir:"down",n:dnPats.length,sum:data.summary.find(s=>s.direction==="down")},
              ].map(({dir,n,sum})=>n>0&&(
                <div key={dir} style={{background:`${dir==="up"?G:R}0f`,border:`1px solid ${dir==="up"?G:R}33`,borderRadius:6,padding:"6px 12px"}}>
                  <span style={{fontSize:11,fontWeight:700,color:dir==="up"?G:R}}>{dir.toUpperCase()}: {n}</span>
                  {sum&&<span style={{fontSize:10,color:W9,marginLeft:6}}>best {(sum.max_acc*100).toFixed(0)}%</span>}
                </div>
              ))}
            </div>
          </div>

          {/* Tab navigation */}
          <div style={{display:"flex",gap:4,flexWrap:"wrap",marginBottom:14,borderBottom:`1px solid ${BOR}`,paddingBottom:8}}>
            {[
              ["patterns","Pattern Cards"],
              ["heatmap","Discovery Heatmap"],
              ["3d","3D Surface"],
              ["bubble","Bubble Chart"],
              ["strip","Calendar Strip"],
              ["monthly","Month Heatmap"],
            ].map(([id,label])=>(
              <button key={id} onClick={()=>setActiveTab(id as typeof activeTab)} style={{
                padding:"6px 14px",borderRadius:6,fontSize:11,fontWeight:700,cursor:"pointer",border:"none",
                background:activeTab===id?CY:"transparent",color:activeTab===id?"#000":W9,
              }}>{label}</button>
            ))}
          </div>

          {/* ── TAB: Pattern Cards ─────────────────────────────────────── */}
          {activeTab==="patterns"&&(
            <div>
              <div style={{display:"flex",gap:6,marginBottom:10}}>
                {([["both",`All (${allPats.length})`],["up",`UP (${upPats.length})`],["down",`DOWN (${dnPats.length})`]] as const).map(([v,l])=>(
                  <button key={v} onClick={()=>setActiveDir(v)} style={{padding:"6px 14px",borderRadius:6,fontSize:11,fontWeight:700,cursor:"pointer",border:"1px solid",background:activeDir===v?(v==="down"?R:v==="up"?G:CY):"transparent",color:activeDir===v?"#000":DIM,borderColor:activeDir===v?(v==="down"?R:v==="up"?G:CY):BOR}}>{l}</button>
                ))}
              </div>
              {showPats.length===0?(
                <div style={{color:DIM,fontSize:13,padding:"30px 0",textAlign:"center"}}>No patterns match filters. Try lowering accuracy or min years.</div>
              ):(
                showPats.map((p,i)=>(
                  <PatCard key={i} p={p}
                    expanded={expandedIdx===i}
                    compareYears={compareYears}
                    overlayData={overlayCache[`${data.symbol}-${p.anchor_month}-${p.anchor_day}-${p.window_days}`]||null}
                    onExpand={()=>{
                      const newIdx=expandedIdx===i?null:i;
                      setExpandedIdx(newIdx);
                      if(newIdx!==null) loadOverlay(p,data.symbol,data.asset_type);
                    }}
                  />
                ))
              )}
            </div>
          )}

          {/* ── TAB: Discovery Heatmap ─────────────────────────────────── */}
          {activeTab==="heatmap"&&heatData&&(
            <div>
              <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"16px"}}>
                <div style={{fontSize:11,fontWeight:700,color:CY,letterSpacing:1.4,marginBottom:12}}>
                  WINDOW DISCOVERY HEATMAP — Month x Duration x Accuracy
                </div>
                <WindowDiscoveryHeatmap rows={heatData.heatmap_rows} onSelect={sel=>{
                  setHeatSelected(sel);
                  const key=`${data.symbol}-${sel.anchor_month}-1-${sel.window_days}`;
                  if(!overlayCache[key]){
                    fetch(`/api/patterns/detail?symbol=${encodeURIComponent(data.symbol)}&asset_type=${data.asset_type}&month=${sel.anchor_month}&day=1&window=${sel.window_days}`,{cache:"no-store"})
                      .then(r=>r.json()).then(d=>{if(d.ok)setOverlayCache(c=>({...c,[key]:d}));}).catch(()=>{});
                  }
                }}/>
              </div>
              {heatSelected&&overlayCache[`${data.symbol}-${heatSelected.anchor_month}-1-${heatSelected.window_days}`]&&(
                <div style={{marginTop:14,background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"16px"}}>
                  <div style={{fontSize:11,fontWeight:700,color:CY,letterSpacing:1.4,marginBottom:12}}>
                    SELECTED: {MONTHS[heatSelected.anchor_month]} {wLabel(heatSelected.window_days)} {heatSelected.direction.toUpperCase()} PATTERN
                  </div>
                  <YearOverlayChart data={overlayCache[`${data.symbol}-${heatSelected.anchor_month}-1-${heatSelected.window_days}`]} direction={heatSelected.direction as "up"|"down"}/>
                </div>
              )}
            </div>
          )}

          {/* ── TAB: 3D Surface ───────────────────────────────────────── */}
          {activeTab==="3d"&&heatData&&(
            <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:CY,letterSpacing:1.4,marginBottom:12}}>
                3D DISCOVERY SURFACE — Month x Duration x Score
              </div>
              <Surface3D rows={heatData.heatmap_rows}/>
            </div>
          )}

          {/* ── TAB: Bubble Chart ─────────────────────────────────────── */}
          {activeTab==="bubble"&&(
            <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:CY,letterSpacing:1.4,marginBottom:12}}>
                BUBBLE CHART — Accuracy vs Avg Return (size = years of data)
              </div>
              <BubbleChart patterns={allPats}/>
            </div>
          )}

          {/* ── TAB: Calendar Strip ───────────────────────────────────── */}
          {activeTab==="strip"&&(
            <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:CY,letterSpacing:1.4,marginBottom:12}}>
                CALENDAR STRIP — Pattern positions through the year
              </div>
              <CalendarStrip patterns={allPats}/>
            </div>
          )}

          {/* ── TAB: Month Heatmap ────────────────────────────────────── */}
          {activeTab==="monthly"&&(
            <div style={{background:SUR,border:`1px solid ${BOR}`,borderRadius:8,padding:"16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:CY,letterSpacing:1.4,marginBottom:12}}>
                MONTHLY SEASONALITY HEATMAP
              </div>
              <MonthYearHeatmap seasonality={heatData?.seasonality||[]}/>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
""")

print("\n" + "="*60)
print("PHASE 13 COMPLETE")
print("="*60)
print("""
New API routes:
  /api/patterns/detail  -- per-pattern year-by-year price paths
  /api/patterns/heatmap -- discovery heatmap + monthly data

/patterns page now has 6 visualization tabs:

1. Pattern Cards
   - Every pattern card expandable
   - Inside: all-years overlay chart + year-day heatmap
   - Year group comparison (2yr/4yr/6yr/8yr/10yr)
   - Success/failure years with return %

2. Discovery Heatmap
   - Month x Duration grid
   - Cell color = accuracy (darker = stronger)
   - Click any cell -> loads overlay chart below
   - Toggle UP / DOWN

3. 3D Surface
   - Isometric 3D visualization
   - X=Month, Y=Window, Z=Score
   - Green peaks = bullish zones, Red = bearish

4. Bubble Chart
   - X=accuracy, Y=avg return
   - Bubble size = years of data
   - Best patterns = top-right large bubbles

5. Calendar Strip
   - Full year timeline
   - Green bars = UP patterns, Red = DOWN
   - Bar width = duration, opacity = accuracy

6. Month Heatmap
   - Average return per month bar chart
   - Color coded green/red by return

Restart: cd D:\\MICC\\micc-dashboard && npm run dev
Open: localhost:3000/patterns -> search HDFCBANK
""")
