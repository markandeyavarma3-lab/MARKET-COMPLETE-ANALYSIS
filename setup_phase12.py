# -*- coding: utf-8 -*-
"""
setup_phase12.py  --  Run from D:\\MICC
Builds the full Seasonality Patterns dashboard.
Run AFTER build_seasonality_v2.py completes.
Run: py D:\\MICC\\setup_phase12.py
"""

from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
APP  = DASH / "src" / "app"
SRC  = DASH / "src"

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
      encoding: 'utf-8', timeout: 25000, cwd: DA,
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
  const sym        = (searchParams.get('symbol') || '').trim()
  const direction  = searchParams.get('direction') || 'both'
  const minAcc     = parseFloat(searchParams.get('min_acc')   || '0.70')
  const minYears   = parseInt(searchParams.get('min_years')   || '5')
  const minReturn  = parseFloat(searchParams.get('min_ret')   || '0')
  const windowF    = parseInt(searchParams.get('window')      || '0')
  const confF      = searchParams.get('confidence') || ''
  const degF       = searchParams.get('degradation') || ''
  const sortBy     = searchParams.get('sort') || 'score'

  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  // Check table exists
  const tblCheck = qdb(
    `SELECT COUNT(*) as n FROM sqlite_master WHERE type='table' AND name='seasonality_patterns'`
  )
  const tblExists = (tblCheck[0] as Record<string,unknown>)?.n as number > 0
  if (!tblExists) {
    return NextResponse.json({
      ok: false, not_built: true,
      error: 'seasonality_patterns table not found. Run build_seasonality_v2.py first.',
    }, { status: 404 })
  }

  // Check patterns exist for this symbol
  const chk = qdb(`SELECT COUNT(*) as n FROM seasonality_patterns WHERE symbol=?`, [sym])
  const total_n = (chk[0] as Record<string,unknown>)?.n as number || 0
  if (total_n === 0) {
    return NextResponse.json({
      ok: false, not_computed: true,
      error: `No seasonality patterns for "${sym}". Run build_seasonality_v2.py to compute.`,
    }, { status: 404 })
  }

  // Build dynamic filters
  const filters: string[] = [
    `symbol=?`, `accuracy >= ?`, `n_years >= ?`,
    `ABS(avg_return_all) >= ?`,
  ]
  const params: unknown[] = [sym, minAcc, minYears, minReturn]

  if (direction !== 'both') { filters.push(`direction=?`); params.push(direction); }
  if (windowF > 0)           { filters.push(`window_days=?`); params.push(windowF); }
  if (confF)                 { filters.push(`year_confidence=?`); params.push(confF); }
  if (degF)                  { filters.push(`degradation_flag=?`); params.push(degF); }

  const whereClause = filters.join(' AND ')

  const sortMap: Record<string, string> = {
    score:    'score DESC',
    accuracy: 'accuracy DESC, n_years DESC',
    n_years:  'n_years DESC, accuracy DESC',
    avg_ret:  'ABS(avg_return_all) DESC',
    window:   'window_days ASC, accuracy DESC',
  }
  const orderClause = sortMap[sortBy] || 'score DESC'

  const patterns = qdb(`
    SELECT direction, window_days, anchor_month, anchor_day,
           start_label, end_label, n_years, n_hit, accuracy,
           avg_return_all, avg_return_hit, median_return,
           std_return, min_return, max_return, p25_return, p75_return,
           score, year_confidence, degradation_flag,
           first_half_accuracy, last_half_accuracy,
           success_years, failure_years, yearly_returns,
           best_year, worst_year
    FROM seasonality_patterns
    WHERE ${whereClause}
    ORDER BY ${orderClause}
    LIMIT 300
  `, params)

  // Summary stats
  const summary = qdb(`
    SELECT direction,
           COUNT(*) as n,
           AVG(accuracy) as avg_acc,
           MAX(accuracy) as max_acc,
           AVG(score) as avg_score,
           MAX(score) as max_score,
           AVG(n_years) as avg_years,
           SUM(CASE WHEN year_confidence='GREEN'  THEN 1 ELSE 0 END) as green_n,
           SUM(CASE WHEN year_confidence='YELLOW' THEN 1 ELSE 0 END) as yellow_n,
           SUM(CASE WHEN year_confidence='RED'    THEN 1 ELSE 0 END) as red_n,
           SUM(CASE WHEN year_confidence='DANGER' THEN 1 ELSE 0 END) as danger_n,
           SUM(CASE WHEN degradation_flag='DEGRADING'  THEN 1 ELSE 0 END) as degrading_n,
           SUM(CASE WHEN degradation_flag='IMPROVING'  THEN 1 ELSE 0 END) as improving_n,
           SUM(CASE WHEN degradation_flag='STABLE'     THEN 1 ELSE 0 END) as stable_n
    FROM seasonality_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction
  `, [sym, minAcc, minYears])

  // By window distribution
  const byWindow = qdb(`
    SELECT direction, window_days,
           COUNT(*) as n, AVG(accuracy) as avg_acc,
           MAX(accuracy) as max_acc, AVG(score) as avg_score
    FROM seasonality_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction, window_days
    ORDER BY direction, window_days
  `, [sym, minAcc, minYears])

  // By month distribution (which months have most patterns)
  const byMonth = qdb(`
    SELECT direction, anchor_month,
           COUNT(*) as n, AVG(accuracy) as avg_acc
    FROM seasonality_patterns
    WHERE symbol=? AND accuracy >= ? AND n_years >= ?
    GROUP BY direction, anchor_month
    ORDER BY direction, anchor_month
  `, [sym, minAcc, minYears])

  // Asset info
  const assetInfo = qdb(`
    SELECT asset_type FROM seasonality_patterns WHERE symbol=? LIMIT 1
  `, [sym])

  // Latest price
  const assetType = (assetInfo[0] as Record<string,unknown>)?.asset_type as string || 'stock'
  let price: unknown[] = []
  if (assetType === 'stock') {
    price = qdb(`SELECT close, date FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`, [sym])
  } else if (assetType === 'index') {
    price = qdb(`SELECT close, date FROM indices_data WHERE index_name=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1`, [sym])
  } else {
    price = qdb(`SELECT close, date FROM global_indices_daily WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1`, [sym])
  }

  return NextResponse.json({
    ok: true, symbol: sym,
    asset_type: assetType,
    total_patterns: total_n,
    patterns,
    summary,
    by_window: byWindow,
    by_month: byMonth,
    latest_price: price[0] || null,
    active_filters: { min_acc: minAcc, min_years: minYears, direction, window: windowF },
  })
}
""")


# =============================================================================
# [2] /patterns/page.tsx — full dashboard
# =============================================================================
print("\n[2/3] /patterns/page.tsx")

write(APP / "patterns" / "page.tsx", r"""
"use client";
import React, { useState, useCallback, useRef, useEffect } from "react";

// ── Types ──────────────────────────────────────────────────────────────────
interface Pattern {
  direction:           "up"|"down";
  window_days:         number;
  anchor_month:        number;
  anchor_day:          number;
  start_label:         string;
  end_label:           string;
  n_years:             number;
  n_hit:               number;
  accuracy:            number;
  avg_return_all:      number;
  avg_return_hit:      number;
  median_return:       number;
  std_return:          number;
  min_return:          number;
  max_return:          number;
  p25_return:          number;
  p75_return:          number;
  score:               number;
  year_confidence:     string;
  degradation_flag:    string;
  first_half_accuracy: number;
  last_half_accuracy:  number;
  success_years:       string;
  failure_years:       string;
  yearly_returns:      string;
  best_year:           number;
  worst_year:          number;
}
interface Summary {
  direction:string; n:number; avg_acc:number; max_acc:number;
  avg_score:number; max_score:number; avg_years:number;
  green_n:number; yellow_n:number; red_n:number; danger_n:number;
  degrading_n:number; improving_n:number; stable_n:number;
}
interface ByWindow { direction:string; window_days:number; n:number; avg_acc:number; max_acc:number; avg_score:number; }
interface ByMonth  { direction:string; anchor_month:number; n:number; avg_acc:number; }
interface PatData {
  ok:boolean; error?:string; not_built?:boolean; not_computed?:boolean;
  symbol:string; asset_type:string; total_patterns:number;
  patterns:Pattern[]; summary:Summary[];
  by_window:ByWindow[]; by_month:ByMonth[];
  latest_price:{close:number;date:string}|null;
  active_filters:Record<string,unknown>;
}
interface Sug { symbol:string; name:string; sector:string; type:string; }

// ── Constants ─────────────────────────────────────────────────────────────
const G="#4ade80",R="#f87171",CY="#22d3ee",YL="#facc15",OR="#f97316",PU="#a855f7";
const W9="#94a3b8",WHT="#e2e8f0";
const DIM="var(--text-tertiary)",PRI="var(--text-primary)",BOR="var(--border-color)",SUR="var(--surface-card)";
const MONTHS=["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const pct=(v:unknown,d=1)=>v==null?"--":`${(+(v as number))>=0?"+":""}${(+(v as number)).toFixed(d)}%`;
const num=(v:unknown,d=2)=>v==null?"--":(+(v as number)).toFixed(d);
const col=(v:unknown)=>(+(v as number)??0)>=0?G:R;

function confColor(c:string){
  return c==="GREEN"?"#4ade80":c==="YELLOW"?"#facc15":c==="RED"?"#f97316":c==="DANGER"?"#f87171":W9;
}
function confLabel(c:string){
  return c==="GREEN"?">=15yr":c==="YELLOW"?"10-14yr":c==="RED"?"7-9yr":c==="DANGER"?"<7yr":c;
}
function degColor(d:string){
  return d==="IMPROVING"?G:d==="DEGRADING"?R:W9;
}
function degIcon(d:string){
  return d==="IMPROVING"?"[+]":d==="DEGRADING"?"[-]":"[=]";
}

// ── Autocomplete ──────────────────────────────────────────────────────────
function AInput({value,onChange,onSelect}:{value:string;onChange:(v:string)=>void;onSelect:(s:string)=>void}){
  const [sugg,setSugg]=useState<Sug[]>([]);
  const [show,setShow]=useState(false);
  const [hi,setHi]=useState(-1);
  const tmr=useRef<ReturnType<typeof setTimeout>|null>(null);

  const fetch_=useCallback(async(q:string)=>{
    if(q.length<1){setSugg([]);return;}
    // Try stock first, then index
    try{
      const [sr,ir]=await Promise.all([
        fetch(`/api/search?q=${encodeURIComponent(q.toUpperCase())}&type=stock`,{cache:"no-store"}),
        fetch(`/api/search?q=${encodeURIComponent(q.toUpperCase())}&type=index`,{cache:"no-store"}),
      ]);
      const [sd,id]=await Promise.all([sr.json(),ir.json()]);
      const combined=[...(sd.results||[]),...(id.results||[])].slice(0,12);
      setSugg(combined);setShow(true);
    }catch{setSugg([]);}
  },[]);

  const change=(v:string)=>{
    onChange(v);setHi(-1);
    if(tmr.current)clearTimeout(tmr.current);
    tmr.current=setTimeout(()=>fetch_(v),180);
  };
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
      <input value={value} onChange={e=>change(e.target.value)}
        onKeyDown={onKey} onBlur={()=>setTimeout(()=>setShow(false),200)}
        placeholder="Search any stock or index (e.g. HDFCBANK, NIFTY 50, SPX, RELIANCE)..."
        autoFocus
        style={{width:"100%",background:SUR,border:`1px solid ${BOR}`,color:PRI,
          borderRadius:show&&sugg.length>0?"8px 8px 0 0":"8px",
          padding:"12px 16px",fontSize:14,boxSizing:"border-box"}}/>
      {show&&sugg.length>0&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,
          background:"#0d1520",border:`1px solid ${BOR}`,borderTop:"none",
          borderRadius:"0 0 8px 8px",maxHeight:300,overflowY:"auto",
          boxShadow:"0 8px 32px rgba(0,0,0,0.7)"}}>
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

// ── Year Confidence Badge ─────────────────────────────────────────────────
function ConfBadge({conf,n_years}:{conf:string;n_years:number}){
  const c=confColor(conf);
  return(
    <span title={`${n_years} years of data — ${conf} reliability`} style={{
      display:"inline-flex",alignItems:"center",gap:4,
      fontSize:10,fontWeight:700,padding:"2px 7px",borderRadius:3,
      background:`${c}22`,color:c,border:`1px solid ${c}44`,
      whiteSpace:"nowrap",cursor:"help",
    }}>
      <span style={{width:7,height:7,borderRadius:"50%",background:c,display:"inline-block"}}/>
      {n_years}yr
    </span>
  );
}

// ── Degradation Badge ─────────────────────────────────────────────────────
function DegBadge({flag,fh,lh}:{flag:string;fh:number;lh:number}){
  const c=degColor(flag);
  return(
    <span title={`First half: ${(fh*100).toFixed(0)}% | Last half: ${(lh*100).toFixed(0)}%`} style={{
      fontSize:10,fontWeight:700,padding:"2px 6px",borderRadius:3,
      background:`${c}18`,color:c,cursor:"help",
    }}>{degIcon(flag)} {flag}</span>
  );
}

// ── Year-by-Year Chart ────────────────────────────────────────────────────
function YearChart({pattern,compareYears}:{pattern:Pattern;compareYears:number}){
  let yr_data: Record<string,number> = {};
  try { yr_data = JSON.parse(pattern.yearly_returns); } catch{ return null; }

  const years = Object.keys(yr_data).map(Number).sort();
  if(years.length < 2) return null;

  const AC = pattern.direction==="up"?G:R;

  // Split into groups for comparison
  const groupSize = compareYears || years.length;
  const groups: number[][] = [];
  for(let i=0;i<years.length;i+=groupSize) groups.push(years.slice(i,i+groupSize));

  // Chart dimensions
  const W=560,H=160,ML=44,MR=16,MT=10,MB=30;
  const PW=W-ML-MR,PH=H-MT-MB;
  const rets=years.map(y=>yr_data[String(y)]||0);
  const mn=Math.min(...rets,-5),mx=Math.max(...rets,5),rng=mx-mn||1;
  const tx=(i:number)=>ML+(i/(years.length-1))*PW;
  const ty=(v:number)=>MT+PH-((v-mn)/rng)*PH;
  const z0=ty(0);

  const avgRet=rets.reduce((a,b)=>a+b,0)/rets.length;

  // Tick values for Y axis
  const tickStep=Math.ceil((mx-mn)/5/5)*5||5;
  const ticks:number[]=[];
  for(let t=Math.ceil(mn/tickStep)*tickStep;t<=mx;t+=tickStep)ticks.push(t);

  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>Year-by-year returns — each dot is one year. Hover for details.</div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {/* Grid */}
        {ticks.map(t=>(
          <g key={t}>
            <line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff10" strokeWidth={1}/>
            <text x={ML-4} y={ty(t)+4} textAnchor="end" fontSize={9} fill={W9}>{t}%</text>
          </g>
        ))}
        {/* Zero line */}
        <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff40" strokeDasharray="4,3" strokeWidth={1}/>
        {/* Average line */}
        <line x1={ML} y1={ty(avgRet)} x2={W-MR} y2={ty(avgRet)} stroke={YL} strokeDasharray="6,3" strokeWidth={1.5}/>
        <text x={W-MR+3} y={ty(avgRet)+4} fontSize={9} fill={YL}>avg</text>

        {/* Bars */}
        {years.map((yr,i)=>{
          const v=yr_data[String(yr)]||0;
          const barW=Math.max(1,PW/years.length*0.7);
          const barX=tx(i)-barW/2;
          const barH=Math.abs(ty(v)-z0);
          const barY=v>=0?ty(v):z0;
          const isSuccess=(pattern.direction==="up"&&v>0)||(pattern.direction==="down"&&v<0);
          return(
            <rect key={yr} x={barX} y={barY} width={barW} height={Math.max(1,barH)}
              fill={isSuccess?AC:W9} opacity={isSuccess?0.85:0.3} rx={1}>
              <title>{yr}: {v>=0?"+":""}{ v.toFixed(2)}%</title>
            </rect>
          );
        })}

        {/* X axis */}
        <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
        {years.filter((_,i)=>i%Math.max(1,Math.floor(years.length/10))===0).map((yr,_)=>{
          const i=years.indexOf(yr);
          return <text key={yr} x={tx(i)} y={H-MB+14} textAnchor="middle" fontSize={9} fill={W9}>{yr}</text>;
        })}
      </svg>

      {/* Group comparison if selected */}
      {compareYears > 0 && compareYears < years.length && (
        <div style={{marginTop:12}}>
          <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:8}}>
            Accuracy by {compareYears}-year groups (compare early vs recent):
          </div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            {groups.map((grp,gi)=>{
              const grpRets=grp.map(y=>yr_data[String(y)]||0);
              const hits=grpRets.filter(v=>pattern.direction==="up"?v>0:v<0).length;
              const acc=hits/grpRets.length;
              const c=acc>=0.80?G:acc>=0.70?YL:R;
              return(
                <div key={gi} style={{background:`${c}18`,border:`1px solid ${c}33`,
                  borderRadius:6,padding:"8px 12px",minWidth:120}}>
                  <div style={{fontSize:10,color:W9,marginBottom:4}}>
                    {grp[0]}-{grp[grp.length-1]}
                  </div>
                  <div style={{fontSize:16,fontWeight:800,color:c}}>{(acc*100).toFixed(0)}%</div>
                  <div style={{fontSize:11,color:W9}}>{hits}/{grp.length} years</div>
                  <div style={{fontSize:10,color:col(grpRets.reduce((a,b)=>a+b,0)/grpRets.length)}}>
                    avg {pct(grpRets.reduce((a,b)=>a+b,0)/grpRets.length)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Return Distribution Mini Chart ────────────────────────────────────────
function RetDistChart({p}:{p:Pattern}){
  let yr_data: Record<string,number> = {};
  try { yr_data = JSON.parse(p.yearly_returns); } catch{ return null; }
  const rets=Object.values(yr_data).map(Number).sort((a,b)=>a-b);
  if(rets.length<2) return null;
  const mn=Math.min(...rets),mx=Math.max(...rets),rng=mx-mn||1;
  const W=280,H=40;
  const AC=p.direction==="up"?G:R;
  return(
    <div>
      <div style={{fontSize:9,color:W9,marginBottom:3}}>Return distribution ({rets.length} years)</div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {/* Percentile boxes */}
        {[{lo:p.min_return,hi:p.max_return,op:0.15},{lo:p.p25_return,hi:p.p75_return,op:0.35}].map((box,i)=>{
          const x1=((box.lo-mn)/rng)*W;
          const x2=((box.hi-mn)/rng)*W;
          return <rect key={i} x={x1} y={5} width={Math.max(1,x2-x1)} height={H-15} fill={AC} opacity={box.op} rx={2}/>;
        })}
        {/* Zero line */}
        {mn<0&&mx>0&&<line x1={(-mn/rng)*W} y1={0} x2={(-mn/rng)*W} y2={H-15} stroke={W9} strokeDasharray="3,2" strokeWidth={1}/>}
        {/* Median */}
        {(()=>{const mx2=((p.median_return-mn)/rng)*W;return <line x1={mx2} y1={5} x2={mx2} y2={H-15} stroke={YL} strokeWidth={2}/>;})()}
        {/* Individual year dots */}
        {rets.map((v,i)=>{
          const x=((v-mn)/rng)*W;
          const isHit=p.direction==="up"?v>0:v<0;
          return <circle key={i} cx={x} cy={H/2-5} r={2.5} fill={isHit?AC:W9} opacity={0.7}><title>{v>=0?"+":""}{ v.toFixed(1)}%</title></circle>;
        })}
        {/* Labels */}
        <text x={0} y={H} fontSize={8} fill={W9} textAnchor="start">{pct(mn,1)}</text>
        <text x={W/2} y={H} fontSize={8} fill={YL} textAnchor="middle">med {pct(p.median_return,1)}</text>
        <text x={W} y={H} fontSize={8} fill={W9} textAnchor="end">{pct(mx,1)}</text>
      </svg>
    </div>
  );
}

// ── Pattern Card ──────────────────────────────────────────────────────────
function PatCard({p,compareYears}:{p:Pattern;compareYears:number}){
  const [expanded,setExpanded]=useState(false);
  const AC=p.direction==="up"?G:R;
  const confC=confColor(p.year_confidence);

  let succ:number[]=[],fail:number[]=[],yr_data:Record<string,number>={};
  try{succ=JSON.parse(p.success_years)||[];}catch{}
  try{fail=JSON.parse(p.failure_years)||[];}catch{}
  try{yr_data=JSON.parse(p.yearly_returns)||{};}catch{}

  return(
    <div style={{marginBottom:10,background:`${AC}0a`,border:`1px solid ${AC}22`,
      borderRadius:8,borderLeft:`4px solid ${AC}`,overflow:"hidden"}}>
      {/* Main row - always visible */}
      <div style={{padding:"12px 16px",cursor:"pointer"}} onClick={()=>setExpanded(e=>!e)}>
        <div style={{display:"flex",alignItems:"center",gap:12,flexWrap:"wrap",marginBottom:6}}>
          {/* Window */}
          <span style={{fontWeight:900,fontSize:20,color:WHT,minWidth:48}}>{
            p.window_days>=252?"1Y":p.window_days>=180?"9M":p.window_days>=120?"6M":
            p.window_days>=90?"4M":p.window_days>=60?"3M":p.window_days>=45?"2M":
            p.window_days>=30?"6W":p.window_days>=20?"1M":p.window_days>=15?"3W":
            p.window_days>=10?"2W":`${p.window_days}D`
          }</span>
          {/* Calendar period */}
          <span style={{fontSize:13,fontWeight:600,color:W9}}>
            {p.start_label} &rarr; {p.end_label}
          </span>
          {/* Accuracy + hits */}
          <div style={{flex:1}}>
            <div style={{display:"flex",alignItems:"baseline",gap:8}}>
              <span style={{fontWeight:900,fontSize:22,color:confC}}>{(p.accuracy*100).toFixed(0)}%</span>
              <span style={{fontSize:12,color:DIM}}>accurate</span>
              <span style={{fontSize:13,color:WHT,fontWeight:600}}>
                ({p.n_hit}/{p.n_years} years went {p.direction.toUpperCase()})
              </span>
            </div>
            <div style={{height:5,background:`${BOR}33`,borderRadius:3,marginTop:4,maxWidth:300}}>
              <div style={{height:5,width:`${Math.min(100,p.accuracy*100)}%`,background:confC,borderRadius:3}}/>
            </div>
          </div>
          {/* Badges */}
          <div style={{display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
            <ConfBadge conf={p.year_confidence} n_years={p.n_years}/>
            <DegBadge flag={p.degradation_flag} fh={p.first_half_accuracy} lh={p.last_half_accuracy}/>
            <span style={{fontSize:10,color:W9}}>score {p.score.toFixed(3)}</span>
            <span style={{fontSize:11,color:DIM}}>{expanded?"▲":"▼"}</span>
          </div>
        </div>

        {/* Quick stats */}
        <div style={{display:"flex",gap:16,flexWrap:"wrap",fontSize:12}}>
          <span><span style={{color:DIM}}>Avg: </span><span style={{color:col(p.avg_return_all),fontWeight:700}}>{pct(p.avg_return_all)}</span></span>
          <span><span style={{color:DIM}}>Median: </span><span style={{color:col(p.median_return)}}>{pct(p.median_return)}</span></span>
          <span><span style={{color:DIM}}>Range: </span><span style={{color:R}}>{pct(p.min_return)}</span><span style={{color:DIM}}> to </span><span style={{color:G}}>{pct(p.max_return)}</span></span>
          <span><span style={{color:DIM}}>Std: </span><span style={{color:W9}}>{pct(p.std_return)}</span></span>
          <span><span style={{color:DIM}}>When {p.direction}: </span><span style={{color:AC,fontWeight:600}}>{pct(p.avg_return_hit)}</span></span>
        </div>
      </div>

      {/* Expanded content */}
      {expanded&&(
        <div style={{padding:"0 16px 16px"}}>
          <div style={{height:1,background:`${BOR}33`,marginBottom:14}}/>

          {/* Stats grid */}
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:8,marginBottom:16}}>
            {[
              {l:"Avg Return (all yrs)",  v:pct(p.avg_return_all),  c:col(p.avg_return_all)},
              {l:`Avg When ${p.direction.toUpperCase()}`, v:pct(p.avg_return_hit), c:AC},
              {l:"Median Return",          v:pct(p.median_return),  c:col(p.median_return)},
              {l:"P25 Return",             v:pct(p.p25_return),     c:col(p.p25_return)},
              {l:"P75 Return",             v:pct(p.p75_return),     c:col(p.p75_return)},
              {l:"Best Year Return",       v:pct(p.max_return),     c:G},
              {l:"Worst Year Return",      v:pct(p.min_return),     c:R},
              {l:"Std Deviation",          v:pct(p.std_return)},
              {l:"Best Year",              v:String(p.best_year||"--")},
              {l:"Worst Year",             v:String(p.worst_year||"--")},
              {l:"First Half Acc",         v:`${(p.first_half_accuracy*100).toFixed(0)}%`,c:p.first_half_accuracy>=0.70?G:R},
              {l:"Last Half Acc",          v:`${(p.last_half_accuracy*100).toFixed(0)}%`, c:p.last_half_accuracy>=0.70?G:R},
            ].map(({l,v,c})=>(
              <div key={l} style={{background:`${BOR}22`,borderRadius:5,padding:"7px 10px"}}>
                <div style={{fontSize:9,color:DIM,fontWeight:700,marginBottom:2,textTransform:"uppercase",letterSpacing:0.8}}>{l}</div>
                <div style={{fontSize:14,fontWeight:800,color:c||PRI}}>{v}</div>
              </div>
            ))}
          </div>

          {/* Return distribution mini chart */}
          <div style={{marginBottom:14}}>
            <RetDistChart p={p}/>
          </div>

          {/* Year-by-year bar chart */}
          <div style={{marginBottom:14}}>
            <YearChart pattern={p} compareYears={compareYears}/>
          </div>

          {/* Success / failure years */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:10}}>
            <div>
              <div style={{fontSize:10,fontWeight:700,color:G,letterSpacing:1,marginBottom:6}}>
                SUCCESS YEARS ({succ.length})
              </div>
              <div style={{display:"flex",flexWrap:"wrap",gap:4}}>
                {succ.map(yr=>(
                  <span key={yr} style={{fontSize:10,fontWeight:700,color:G,
                    background:`${G}18`,borderRadius:3,padding:"2px 5px"}}>
                    {yr} <span style={{color:DIM,fontWeight:400}}>({yr_data[String(yr)]>=0?"+":""}{(yr_data[String(yr)]||0).toFixed(1)}%)</span>
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div style={{fontSize:10,fontWeight:700,color:R,letterSpacing:1,marginBottom:6}}>
                FAILURE YEARS ({fail.length})
              </div>
              <div style={{display:"flex",flexWrap:"wrap",gap:4}}>
                {fail.map(yr=>(
                  <span key={yr} style={{fontSize:10,fontWeight:700,color:R,
                    background:`${R}18`,borderRadius:3,padding:"2px 5px"}}>
                    {yr} <span style={{color:DIM,fontWeight:400}}>({yr_data[String(yr)]>=0?"+":""}{(yr_data[String(yr)]||0).toFixed(1)}%)</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Month Heatmap ─────────────────────────────────────────────────────────
function MonthHeatmap({byMonth,dir}:{byMonth:ByMonth[];dir:"up"|"down"}){
  const f=byMonth.filter(b=>b.direction===dir);
  if(!f.length) return null;
  const maxN=Math.max(...f.map(b=>b.n));
  const AC=dir==="up"?G:R;
  const monthMap=Object.fromEntries(f.map(b=>[b.anchor_month,b]));
  return(
    <div>
      <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:8}}>
        {dir==="up"?"UP":"DOWN"} pattern count by calendar month
      </div>
      <div style={{display:"flex",gap:4}}>
        {Array.from({length:12},(_,i)=>i+1).map(m=>{
          const b=monthMap[m];
          const intensity=b?b.n/maxN:0;
          return(
            <div key={m} style={{flex:1,textAlign:"center"}}>
              <div style={{
                height:40,background:b?`${AC}${Math.floor(intensity*80+15).toString(16).padStart(2,"0")}`:`${BOR}22`,
                borderRadius:3,marginBottom:3,display:"flex",alignItems:"center",
                justifyContent:"center",fontSize:9,color:b?AC:DIM,fontWeight:700,
              }}>{b?b.n:""}</div>
              <div style={{fontSize:8,color:W9}}>{MONTHS[m].slice(0,3)}</div>
              {b&&<div style={{fontSize:7,color:W9}}>{(b.avg_acc*100).toFixed(0)}%</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Window Distribution ───────────────────────────────────────────────────
function WinDist({byWindow,dir}:{byWindow:ByWindow[];dir:"up"|"down"}){
  const f=byWindow.filter(b=>b.direction===dir);
  if(!f.length) return <div style={{color:DIM,fontSize:12}}>No patterns</div>;
  const maxN=Math.max(...f.map(b=>b.n));
  const AC=dir==="up"?G:R;
  return(
    <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
      {f.map(b=>(
        <div key={b.window_days} style={{
          background:`${AC}${Math.floor(b.n/maxN*55+15).toString(16).padStart(2,"0")}`,
          border:`1px solid ${AC}44`,borderRadius:6,padding:"7px 10px",
          minWidth:72,textAlign:"center",
        }}>
          <div style={{fontSize:13,fontWeight:700,color:WHT}}>{
            b.window_days>=252?"1Y":b.window_days>=180?"9M":b.window_days>=120?"6M":
            b.window_days>=90?"4M":b.window_days>=60?"3M":b.window_days>=45?"2M":
            b.window_days>=30?"6W":b.window_days>=20?"1M":b.window_days>=15?"3W":
            b.window_days>=10?"2W":`${b.window_days}D`
          }</div>
          <div style={{fontSize:10,color:AC,fontWeight:700}}>{b.n}</div>
          <div style={{fontSize:9,color:W9}}>{(b.avg_acc*100).toFixed(0)}% avg</div>
        </div>
      ))}
    </div>
  );
}

// ── Summary Cards ─────────────────────────────────────────────────────────
function SummaryCards({summary,dir}:{summary:Summary|undefined;dir:"up"|"down"}){
  if(!summary) return null;
  const AC=dir==="up"?G:R;
  const confs=[
    {c:"GREEN",  n:summary.green_n,  label:">=15yr"},
    {c:"YELLOW", n:summary.yellow_n, label:"10-14yr"},
    {c:"RED",    n:summary.red_n,    label:"7-9yr"},
    {c:"DANGER", n:summary.danger_n, label:"<7yr"},
  ];
  const degs=[
    {flag:"STABLE",    n:summary.stable_n,    c:W9},
    {flag:"IMPROVING", n:summary.improving_n, c:G},
    {flag:"DEGRADING", n:summary.degrading_n, c:R},
  ];
  return(
    <div style={{background:SUR,border:`1px solid ${AC}33`,borderRadius:8,padding:"14px 16px"}}>
      <div style={{fontSize:11,fontWeight:700,color:AC,letterSpacing:1.2,marginBottom:10}}>
        {dir.toUpperCase()} PATTERNS — {summary.n} total
      </div>
      <div style={{display:"flex",gap:20,flexWrap:"wrap",marginBottom:10}}>
        <div>
          <div style={{fontSize:10,color:W9,marginBottom:2}}>Best Accuracy</div>
          <div style={{fontSize:20,fontWeight:900,color:AC}}>{(summary.max_acc*100).toFixed(0)}%</div>
        </div>
        <div>
          <div style={{fontSize:10,color:W9,marginBottom:2}}>Avg Accuracy</div>
          <div style={{fontSize:20,fontWeight:900,color:AC}}>{(summary.avg_acc*100).toFixed(0)}%</div>
        </div>
        <div>
          <div style={{fontSize:10,color:W9,marginBottom:2}}>Best Score</div>
          <div style={{fontSize:20,fontWeight:900,color:CY}}>{summary.max_score.toFixed(3)}</div>
        </div>
        <div>
          <div style={{fontSize:10,color:W9,marginBottom:2}}>Avg Years</div>
          <div style={{fontSize:20,fontWeight:900,color:WHT}}>{summary.avg_years.toFixed(0)}</div>
        </div>
      </div>
      {/* Year confidence breakdown */}
      <div style={{marginBottom:8}}>
        <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Data Reliability:</div>
        <div style={{display:"flex",gap:8}}>
          {confs.map(({c,n,label})=>{
            const cc=confColor(c);
            return n>0&&(
              <div key={c} style={{fontSize:10,fontWeight:700,color:cc,
                background:`${cc}18`,borderRadius:3,padding:"2px 6px"}}>
                <span style={{width:6,height:6,borderRadius:"50%",background:cc,display:"inline-block",marginRight:3}}/>
                {n} {label}
              </div>
            );
          })}
        </div>
      </div>
      {/* Degradation breakdown */}
      <div style={{display:"flex",gap:8}}>
        {degs.map(({flag,n,c})=>n>0&&(
          <span key={flag} style={{fontSize:10,color:c,background:`${c}18`,
            borderRadius:3,padding:"2px 6px",fontWeight:600}}>
            {degIcon(flag)} {n} {flag}
          </span>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════
export default function PatternsPage(){
  const [symInput, setSymInput]   = useState("");
  const [data,     setData]       = useState<PatData|null>(null);
  const [loading,  setLoading]    = useState(false);
  const [error,    setError]      = useState<string|null>(null);

  // Filters
  const [minAcc,       setMinAcc]       = useState(0.70);
  const [minYears,     setMinYears]     = useState(5);
  const [dirFilter,    setDirFilter]    = useState("both");
  const [windowFilter, setWindowFilter] = useState(0);
  const [confFilter,   setConfFilter]   = useState("");
  const [degFilter,    setDegFilter]    = useState("");
  const [sortBy,       setSortBy]       = useState("score");
  const [compareYears, setCompareYears] = useState(0);
  const [activeDir,    setActiveDir]    = useState<"both"|"up"|"down">("both");

  const load = useCallback(async(sym:string)=>{
    if(!sym.trim()) return;
    setLoading(true); setError(null); setData(null);
    try{
      const params=new URLSearchParams({
        symbol: sym.trim(),
        min_acc: String(minAcc),
        min_years: String(minYears),
        direction: dirFilter,
        window: String(windowFilter),
        confidence: confFilter,
        degradation: degFilter,
        sort: sortBy,
      });
      const r=await fetch(`/api/patterns?${params}`,{cache:"no-store"});
      const d=await r.json();
      if(!d.ok) throw new Error(d.error||"API error");
      setData(d);
    }catch(e:unknown){setError(String(e));}
    finally{setLoading(false);}
  },[minAcc,minYears,dirFilter,windowFilter,confFilter,degFilter,sortBy]);

  // Re-run search when filters change (if already have data)
  useEffect(()=>{
    if(symInput&&data) load(symInput);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[minAcc,minYears,dirFilter,windowFilter,confFilter,degFilter,sortBy]);

  const upSum  = data?.summary.find(s=>s.direction==="up");
  const dnSum  = data?.summary.find(s=>s.direction==="down");
  const allPats= data?.patterns||[];
  const upPats = allPats.filter(p=>p.direction==="up");
  const dnPats = allPats.filter(p=>p.direction==="down");
  const showPats= activeDir==="both"?allPats:activeDir==="up"?upPats:dnPats;

  const WINDOWS_OPTS=[0,5,7,10,12,15,18,20,25,30,35,40,45,50,60,75,90];

  return(
    <div style={{maxWidth:1200,margin:"0 auto",padding:"20px 16px"}}>

      {/* Page header */}
      <div style={{marginBottom:16}}>
        <h1 style={{margin:0,fontSize:24,fontWeight:900,letterSpacing:-0.5}}>
          SEASONAL PATTERNS
        </h1>
        <div style={{color:DIM,fontSize:12,marginTop:3}}>
          Recurring calendar windows where stocks and indices historically go UP or DOWN --
          computed from all available years using calendar-date anchoring
        </div>
      </div>

      {/* Search */}
      <div style={{display:"flex",gap:8,marginBottom:14}}>
        <AInput value={symInput} onChange={setSymInput}
          onSelect={s=>{setSymInput(s);load(s);}}/>
        <button onClick={()=>load(symInput)} disabled={loading} style={{
          background:CY,color:"#000",border:"none",borderRadius:8,
          padding:"12px 22px",fontWeight:800,cursor:"pointer",fontSize:14,
          opacity:loading?0.6:1,minWidth:120,
        }}>{loading?"Loading...":"Find Patterns"}</button>
      </div>

      {/* Filters */}
      <div style={{background:`${BOR}18`,borderRadius:8,padding:"12px 14px",marginBottom:14}}>
        <div style={{display:"flex",gap:16,flexWrap:"wrap",alignItems:"flex-start"}}>

          {/* Min Accuracy */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Min Accuracy</div>
            <div style={{display:"flex",gap:3}}>
              {[0.70,0.75,0.80,0.85,0.90].map(v=>(
                <button key={v} onClick={()=>setMinAcc(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:minAcc===v?CY:"transparent",color:minAcc===v?"#000":W9}}>{(v*100).toFixed(0)}%+</button>
              ))}
            </div>
          </div>

          {/* Min Years */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Min Years</div>
            <div style={{display:"flex",gap:3}}>
              {[3,5,7,10,15].map(v=>(
                <button key={v} onClick={()=>setMinYears(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:minYears===v?CY:"transparent",color:minYears===v?"#000":W9}}>{v}+</button>
              ))}
            </div>
          </div>

          {/* Direction */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Direction</div>
            <div style={{display:"flex",gap:3}}>
              {[["both","Both"],[" up","UP"],["down","DOWN"]].map(([v,l])=>(
                <button key={v} onClick={()=>setDirFilter(v.trim())} style={{padding:"3px 8px",borderRadius:3,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:dirFilter===v.trim()?CY:"transparent",color:dirFilter===v.trim()?"#000":W9}}>{l}</button>
              ))}
            </div>
          </div>

          {/* Window filter */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Window</div>
            <select value={windowFilter} onChange={e=>setWindowFilter(+e.target.value)}
              style={{background:"#1a2332",border:`1px solid ${BOR}`,color:PRI,borderRadius:4,padding:"3px 8px",fontSize:11}}>
              <option value={0}>All</option>
              {WINDOWS_OPTS.slice(1).map(w=><option key={w} value={w}>{w}d</option>)}
            </select>
          </div>

          {/* Confidence */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Reliability</div>
            <div style={{display:"flex",gap:3}}>
              {[["","All"],["GREEN",">=15yr"],["YELLOW","10-14yr"],["RED","7-9yr"],["DANGER","<7yr"]].map(([v,l])=>(
                <button key={v} onClick={()=>setConfFilter(v)} style={{
                  padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",
                  background:confFilter===v?confColor(v||"ALL"):"transparent",
                  color:confFilter===v?(v?"#000":W9):confColor(v||"W9")||W9,
                }}>{l}</button>
              ))}
            </div>
          </div>

          {/* Degradation */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Trend</div>
            <div style={{display:"flex",gap:3}}>
              {[["","All"],["STABLE","Stable"],["IMPROVING","Improving"],["DEGRADING","Degrading"]].map(([v,l])=>(
                <button key={v} onClick={()=>setDegFilter(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:degFilter===v?CY:"transparent",color:degFilter===v?"#000":W9}}>{l}</button>
              ))}
            </div>
          </div>

          {/* Sort */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Sort By</div>
            <div style={{display:"flex",gap:3}}>
              {[["score","Score"],["accuracy","Accuracy"],["n_years","Years"],["avg_ret","Avg Ret"],["window","Window"]].map(([v,l])=>(
                <button key={v} onClick={()=>setSortBy(v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:sortBy===v?CY:"transparent",color:sortBy===v?"#000":W9}}>{l}</button>
              ))}
            </div>
          </div>

          {/* Compare years */}
          <div>
            <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:5}}>Year Groups</div>
            <div style={{display:"flex",gap:3}}>
              {[[0,"Off"],[2,"2yr"],[4,"4yr"],[6,"6yr"],[8,"8yr"],[10,"10yr"]].map(([v,l])=>(
                <button key={v} onClick={()=>setCompareYears(+v)} style={{padding:"3px 8px",borderRadius:3,fontSize:10,fontWeight:600,cursor:"pointer",border:"none",background:compareYears===+v?YL:"transparent",color:compareYears===+v?"#000":W9}}>{l}</button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Error */}
      {error&&(
        <div style={{color:R,fontSize:13,marginBottom:12,padding:"10px 14px",background:`${R}11`,borderRadius:6,border:`1px solid ${R}33`}}>
          {error}
          {data&&(data as unknown as {not_built?:boolean}).not_built&&(
            <div style={{marginTop:6,fontSize:12,color:W9}}>
              Run first: <code style={{color:CY}}>py D:\MICC\build_seasonality_v2.py --test</code>
              {" "}then: <code style={{color:CY}}>py D:\MICC\build_seasonality_v2.py --yes</code>
            </div>
          )}
        </div>
      )}

      {loading&&<div style={{padding:40,textAlign:"center",color:DIM}}>Loading patterns for {symInput}...</div>}

      {data&&!loading&&(
        <div>
          {/* Symbol header */}
          <div style={{display:"flex",gap:12,flexWrap:"wrap",marginBottom:14,alignItems:"center"}}>
            <div>
              <span style={{fontSize:22,fontWeight:900,color:CY}}>{data.symbol}</span>
              <span style={{fontSize:12,fontWeight:600,color:DIM,marginLeft:10,
                border:`1px solid ${BOR}`,borderRadius:4,padding:"2px 8px"}}>
                {data.asset_type.toUpperCase()}
              </span>
            </div>
            {data.latest_price&&<div style={{fontSize:13,color:W9}}>
              Price: <span style={{color:WHT,fontWeight:700}}>
                {(data.latest_price.close||0).toLocaleString("en-IN",{maximumFractionDigits:2})}
              </span> &bull; {data.latest_price.date}
            </div>}
            <div style={{fontSize:12,color:DIM}}>{data.total_patterns} patterns in DB</div>
          </div>

          {/* Summary cards */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            <SummaryCards summary={upSum} dir="up"/>
            <SummaryCards summary={dnSum} dir="down"/>
          </div>

          {/* Charts row */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            {/* Month heatmaps */}
            <div style={{background:SUR,border:`1px solid ${G}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:G,letterSpacing:1.2,marginBottom:10}}>UP PATTERNS BY MONTH</div>
              <MonthHeatmap byMonth={data.by_month} dir="up"/>
            </div>
            <div style={{background:SUR,border:`1px solid ${R}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:R,letterSpacing:1.2,marginBottom:10}}>DOWN PATTERNS BY MONTH</div>
              <MonthHeatmap byMonth={data.by_month} dir="down"/>
            </div>
          </div>

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
            <div style={{background:SUR,border:`1px solid ${G}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:G,letterSpacing:1.2,marginBottom:10}}>UP PATTERNS BY WINDOW</div>
              <WinDist byWindow={data.by_window} dir="up"/>
            </div>
            <div style={{background:SUR,border:`1px solid ${R}33`,borderRadius:8,padding:"14px 16px"}}>
              <div style={{fontSize:11,fontWeight:700,color:R,letterSpacing:1.2,marginBottom:10}}>DOWN PATTERNS BY WINDOW</div>
              <WinDist byWindow={data.by_window} dir="down"/>
            </div>
          </div>

          {/* Direction toggle */}
          <div style={{display:"flex",gap:6,marginBottom:12}}>
            {([["both",`All (${allPats.length})`],["up",`UP (${upPats.length})`],["down",`DOWN (${dnPats.length})`]] as const).map(([v,l])=>(
              <button key={v} onClick={()=>setActiveDir(v)} style={{
                padding:"7px 16px",borderRadius:6,fontSize:12,fontWeight:700,cursor:"pointer",border:"1px solid",
                background:activeDir===v?(v==="down"?R:v==="up"?G:CY):"transparent",
                color:activeDir===v?"#000":DIM,
                borderColor:activeDir===v?(v==="down"?R:v==="up"?G:CY):BOR,
              }}>{l}</button>
            ))}
            <span style={{marginLeft:"auto",fontSize:11,color:DIM,alignSelf:"center"}}>
              Click any pattern to expand — year chart, success/failure years, degradation analysis
            </span>
          </div>

          {/* Patterns */}
          {showPats.length===0?(
            <div style={{color:DIM,fontSize:13,padding:"30px 0",textAlign:"center"}}>
              No patterns match current filters. Try lowering accuracy threshold or min years.
            </div>
          ):(
            <div>
              {activeDir==="both"&&upPats.length>0&&(
                <div style={{marginBottom:20}}>
                  <div style={{fontSize:13,fontWeight:700,color:G,letterSpacing:1,marginBottom:8}}>
                    UP PATTERNS ({upPats.length}) — Calendar windows where this stock historically RISES
                  </div>
                  {upPats.map((p,i)=><PatCard key={`up-${i}`} p={p} compareYears={compareYears}/>)}
                </div>
              )}
              {activeDir==="both"&&dnPats.length>0&&(
                <div>
                  <div style={{fontSize:13,fontWeight:700,color:R,letterSpacing:1,marginBottom:8}}>
                    DOWN PATTERNS ({dnPats.length}) — Calendar windows where this stock historically FALLS
                  </div>
                  {dnPats.map((p,i)=><PatCard key={`dn-${i}`} p={p} compareYears={compareYears}/>)}
                </div>
              )}
              {activeDir==="up"&&upPats.map((p,i)=><PatCard key={i} p={p} compareYears={compareYears}/>)}
              {activeDir==="down"&&dnPats.map((p,i)=><PatCard key={i} p={p} compareYears={compareYears}/>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
""")


# =============================================================================
# [3] Fix /api/analysis/route.ts — bb_pct column fix + correlations
# =============================================================================
print("\n[3/3] Fixing analysis API (bb_pct + correlations)...")

analysis_route = APP / "api" / "analysis" / "route.ts"
if analysis_route.exists():
    txt = analysis_route.read_text(encoding="utf-8")

    # Fix technicals query — bb_pct might not exist, use IFNULL
    old_tech = "SELECT atr_14_pct,adx_14,pct_above_sma20,vol_surge_20d,rsi_14,macd_line,macd_signal,bb_pct,as_of_date FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1"
    new_tech  = "SELECT atr_14_pct,adx_14,pct_above_sma20,vol_surge_20d,rsi_14,macd_line,macd_signal,IFNULL(bb_pct,0) as bb_pct,as_of_date FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1"

    # Fix correlations query — symbol_b might not exist as column name
    old_corr = "SELECT symbol_b,correlation_20d,correlation_60d,beta_20d FROM symbol_correlations WHERE symbol_a=? ORDER BY ABS(COALESCE(correlation_20d,0)) DESC LIMIT 15"
    new_corr  = "SELECT COALESCE(symbol_b,'') as symbol_b,IFNULL(correlation_20d,0) as correlation_20d,IFNULL(correlation_60d,0) as correlation_60d,IFNULL(beta_20d,0) as beta_20d FROM symbol_correlations WHERE symbol_a=? AND symbol_b IS NOT NULL ORDER BY ABS(IFNULL(correlation_20d,0)) DESC LIMIT 15"

    changed = False
    if old_tech in txt:
        txt = txt.replace(old_tech, new_tech)
        print("  Fixed bb_pct in technicals query")
        changed = True
    if old_corr in txt:
        txt = txt.replace(old_corr, new_corr)
        print("  Fixed correlations query")
        changed = True
    if changed:
        analysis_route.write_text(txt, encoding="utf-8", newline="\n")
    else:
        print("  Already patched or different query format")

# Patch NavBar
nb_path = None
for p in (SRC).rglob("NavBar.tsx"):
    nb_path = p; break

if nb_path and nb_path.exists():
    nb = nb_path.read_text(encoding="utf-8")
    if "/patterns" not in nb:
        nb = nb.replace(
            '{ href: "/analysis",',
            '{ href: "/patterns",   label: "PATTERNS"   },\n  { href: "/analysis",'
        )
        nb_path.write_text(nb, encoding="utf-8", newline="\n")
        print("  Added PATTERNS to NavBar")
    else:
        print("  PATTERNS already in NavBar")


print("\n" + "="*65)
print("PHASE 12 COMPLETE")
print("="*65)
print("""
STEP 1 — Test (30-60 seconds, 6 symbols):
  py D:\\MICC\\build_seasonality_v2.py --test

  You should see output like:
    HDFCBANK: 5272 pts | 21 years (2005-2026) | 23 patterns in 0.8s
    Top UP: 90d Mar 22->Jul 04 | 18/21=86% | avg=+12.5% | score=0.512 | GREEN | STABLE

STEP 2 — Full build (6-10 hours, all stocks + indices):
  py D:\\MICC\\build_seasonality_v2.py --yes

  Safe to Ctrl+C and resume. Progress saved every 30 symbols.
  Asks [r]eset / [c]ontinue on subsequent runs.

STEP 3 — Restart dashboard:
  cd D:\\MICC\\micc-dashboard && npm run dev

STEP 4 — Open localhost:3000/patterns
  Search HDFCBANK, NIFTY 50, SPX, RELIANCE etc.

FEATURES:
  Each pattern shows:
    - Duration (e.g. 30 days) + Calendar period (e.g. Mar 22 -> Apr 28)
    - Accuracy: 86% (18/21 years went UP)
    - Year confidence badge: GREEN/YELLOW/RED/DANGER
    - Degradation badge: STABLE/IMPROVING/DEGRADING
    - First-half vs last-half accuracy comparison
    - Avg, median, std, P25, P75, min, max returns
    - Year-by-year bar chart with success/failure highlighted
    - Return distribution mini chart
    - Success years list + Failure years list (each with return%)
  
  Year-group comparison (select 2yr/4yr/6yr/8yr/10yr in filters):
    Shows accuracy in each period — e.g. 2005-2010: 80%, 2011-2016: 75%, 2017-2021: 90%
    Instantly reveals if patterns are getting stronger or weaker over time

  Filters: accuracy %, min years, direction, window size, reliability, trend, sort
  Charts: month heatmap (which months have most patterns), window distribution
""")
