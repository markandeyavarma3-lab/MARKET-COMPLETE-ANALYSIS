"use client";
import NavBar from "@/components/NavBar";
import React, { useState, useCallback, useRef, useEffect } from "react";

//  Types 
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
interface Summary { direction:string;n:number;avg_acc:number;max_acc:number;avg_score:number;max_score:number;avg_years:number;green_n:number;yellow_n:number;red_n:number;danger_n:number;degrading_n:number;improving_n:number;stable_n:number; }
interface ByWindow { direction:string;window_days:number;n:number;avg_acc:number;max_acc:number;avg_score:number; }
interface ByMonth  { direction:string;anchor_month:number;n:number;avg_acc:number; }
interface PatData  { ok:boolean;error?:string;not_built?:boolean;not_computed?:boolean;symbol:string;asset_type:string;total_patterns:number;patterns:Pattern[];summary:Summary[];by_window:ByWindow[];by_month:ByMonth[];latest_price:{close:number;date:string}|null;active_filters:Record<string,unknown>; }
interface HeatRow  { direction:string;window_days:number;anchor_month:number;anchor_day:number;accuracy:number;avg_return_all:number;score:number;n_years:number;n_hit:number;start_label:string;end_label:string;year_confidence:string; }
interface HeatData { ok:boolean;heatmap_rows:HeatRow[];seasonality:{period_value:number;mean_return_pct:number;n_obs:number}[]; }
interface OverlayData { ok:boolean;year_paths:Record<number,number[]>; }
interface Sug { symbol:string;name:string;sector:string;type:string; }

//  Theme 
const G="#4ade80",R="#f87171",CY="#22d3ee",YL="#facc15",OR="var(--orange)";
const W9="var(--muted)",WHT="var(--text)";
const DIM="var(--text-tertiary)",PRI="var(--text-primary)",BOR="var(--border-color)",SUR="var(--surface-card)";
const MONTHS=["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const WINDOWS=[1,2,3,4,5,7,10,12,15,18,20,25,30,35,40,45,50,60,75,90];
const YEAR_COLORS=["#22d3ee","#4ade80","#facc15","var(--orange)","#a855f7","#ec4899","var(--cyan)","#84cc16","var(--warn)","var(--purple)","var(--cyan)","#fb923c","var(--accent)","var(--pos)","#e879f9","var(--warn)","#38bdf8","#a3e635","#fb7185","#c084fc","#2dd4bf","#fcd34d"];

const pct=(v:unknown,d=1)=>v==null?"--":`${(+(v as number))>=0?"+":""}${(+(v as number)).toFixed(d)}%`;
const col=(v:unknown)=>(+(v as number)??0)>=0?G:R;
function confColor(c:string){return c==="GREEN"?G:c==="YELLOW"?YL:c==="RED"?OR:c==="DANGER"?R:W9;}
function degColor(d:string){return d==="IMPROVING"?G:d==="DEGRADING"?R:W9;}
function degIcon(d:string){return d==="IMPROVING"?"[+]":d==="DEGRADING"?"[-]":"[=]";}
function wLabel(d:number){
  if(d>=252)return"1Y";if(d>=180)return"9M";if(d>=120)return"6M";if(d>=90)return"4M";
  if(d>=60)return"3M";if(d>=45)return"2M";if(d>=30)return"6W";if(d>=20)return"1M";
  if(d>=15)return"3W";if(d>=10)return"2W";return`${d}D`;
}

//  Autocomplete 
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
      <NavBar />
      <input value={value} onChange={e=>change(e.target.value)} onKeyDown={onKey}
        onBlur={()=>setTimeout(()=>setShow(false),200)}
        placeholder="Search any stock or index (e.g. HDFCBANK, NIFTY 50, RELIANCE, SPX)..."
        autoFocus
        style={{width:"100%",background:SUR,border:`1.5px solid ${BOR}`,color:PRI,
          borderRadius:show&&sugg.length>0?"10px 10px 0 0":"10px",
          padding:"14px 18px",fontSize:15,boxSizing:"border-box",outline:"none"}}/>
      {show&&sugg.length>0&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,background:"#0a1628",
          border:`1.5px solid ${BOR}`,borderTop:"none",borderRadius:"0 0 10px 10px",
          maxHeight:320,overflowY:"auto",boxShadow:"0 12px 40px rgba(0,0,0,0.8)"}}>
          {sugg.map((s,i)=>(
            <div key={s.symbol} onMouseDown={()=>pick(s.symbol)} style={{
              padding:"10px 16px",cursor:"pointer",display:"flex",alignItems:"center",gap:12,
              background:i===hi?`${CY}15`:"transparent",
              borderBottom:i<sugg.length-1?`1px solid ${BOR}22`:"none"}}>
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

//  CHART: Year-by-year bar chart with hover tooltip + click-to-lock 
function YearChart({pattern,compareYears}:{pattern:Pattern;compareYears:number}){
  const [hoverYr,setHoverYr]=useState<string|null>(null);
  const [locks,setLocks]=useState<{yr:string;ret:number}[]>([]);
  let yr_data:Record<string,number>={};
  try{yr_data=JSON.parse(pattern.yearly_returns);}catch{return null;}
  const entries=Object.entries(yr_data).sort(([a],[b])=>+a-+b);
  if(!entries.length) return null;
  const AC=pattern.direction==="up"?G:R;
  const rets=entries.map(([,v])=>v as number);
  const mn=Math.min(...rets,-2),mx=Math.max(...rets,2),rng=mx-mn||1;
  const avg=rets.reduce((a,b)=>a+b,0)/rets.length;
  const W=600,H=160,ML=44,MR=44,MT=10,MB=28;
  const PW=W-ML-MR,PH=H-MT-MB;
  const bw=Math.max(4,Math.floor(PW/entries.length)-2);
  const tx=(i:number)=>ML+i*(PW/entries.length)+bw/2;
  const ty=(v:number)=>MT+PH-((v-mn)/rng)*PH;
  const z0=ty(0);avgY=ty(avg);
  const step=Math.max(2,Math.ceil(rng/5/2)*2);
  const ticks:number[]=[];for(let t=Math.ceil(mn/step)*step;t<=mx;t+=step)ticks.push(t);
  const onBar=(yr:string,ret:number)=>setLocks(p=>{
    if(p.find(x=>x.yr===yr))return p.filter(x=>x.yr!==yr);
    if(p.length>=2)return[{yr,ret}];
    return[...p,{yr,ret}];
  });
  const delta=locks.length===2?locks[1].ret-locks[0].ret:null;
  // Group comparison
  const years=entries.map(([yr])=>yr);
  const gs=compareYears>0?[]:[];
  if(compareYears>0)for(let i=0;i<years.length;i+=compareYears)gs.push(years.slice(i,i+compareYears));
  return(
    <div style={{marginBottom:14}}>
      <div style={{fontSize:10,color:W9,fontWeight:700,marginBottom:6,display:"flex",alignItems:"center",gap:8}}>
        YEAR-BY-YEAR RETURNS
        <span style={{fontSize:9,color:DIM,fontWeight:400}}>Hover for details. Click to lock A/B and compare.</span>
        {locks.length>0&&<button onClick={()=>setLocks([])} style={{fontSize:9,color:R,background:"transparent",border:`1px solid ${R}44`,borderRadius:3,padding:"1px 6px",cursor:"pointer"}}>Clear</button>}
      </div>
      {locks.length>0&&(
        <div style={{display:"flex",gap:8,marginBottom:8,flexWrap:"wrap",alignItems:"center"}}>
          {locks.map((lk,i)=>{const isHit=pattern.direction==="up"?lk.ret>0:lk.ret<0;return(
            <div key={lk.yr} style={{padding:"4px 10px",borderRadius:5,background:`${isHit?AC:W9}22`,border:`1px solid ${isHit?AC:W9}66`,fontSize:11,color:isHit?AC:W9,fontWeight:700}}>
              {String.fromCharCode(65+i)}: {lk.yr} = {lk.ret>=0?"+":""}{lk.ret.toFixed(1)}%
            </div>
          );})}
          {delta!==null&&<div style={{padding:"4px 12px",borderRadius:5,background:`${YL}22`,border:`1px solid ${YL}`,fontSize:12,color:YL,fontWeight:800}}> = {delta>=0?"+":""}{delta.toFixed(1)}%</div>}
        </div>
      )}
      <div style={{position:"relative"}}>
        {hoverYr&&yr_data[hoverYr]!=null&&(()=>{
          const idx=entries.findIndex(([yr])=>yr===hoverYr);
          const ret=yr_data[hoverYr];const isHit=pattern.direction==="up"?ret>0:ret<0;
          return(<div style={{position:"absolute",top:0,left:Math.max(0,Math.min(tx(idx)-40,PW)),
            background:"#0a1628ee",border:`1px solid ${isHit?AC:W9}`,borderRadius:6,
            padding:"6px 10px",fontSize:11,zIndex:100,pointerEvents:"none",boxShadow:"0 4px 16px rgba(0,0,0,0.6)"}}>
            <div style={{color:WHT,fontWeight:700}}>{hoverYr}</div>
            <div style={{color:isHit?AC:R,fontWeight:700}}>{ret>=0?"+":""}{ret.toFixed(2)}%</div>
            <div style={{color:DIM,fontSize:9}}>Click to lock {locks.length===0?"A":locks.length===1?"B":"(replace)"}</div>
          </div>);
        })()}
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block"}}>
          {ticks.map(t=><g key={t}><line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff0a" strokeWidth={1}/><text x={ML-4} y={ty(t)+3.5} textAnchor="end" fontSize={9} fill={W9}>{t}%</text></g>)}
          <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff35" strokeDasharray="4,3" strokeWidth={1}/>
          <line x1={ML} y1={avgY} x2={W-MR} y2={avgY} stroke={YL} strokeDasharray="8,4" strokeWidth={1.8}/>
          <text x={W-MR+4} y={avgY+3.5} fontSize={9} fill={YL} fontWeight="700">avg</text>
          {entries.map(([yr,ret_],i)=>{
            const ret=ret_ as number;const isHit=pattern.direction==="up"?ret>0:ret<0;
            const barH=Math.max(2,Math.abs(ty(ret)-z0));const barY=ret>=0?ty(ret):z0;
            const isHov=hoverYr===yr;const lkIdx=locks.findIndex(lk=>lk.yr===yr);
            return(<g key={yr} onMouseEnter={()=>setHoverYr(yr)} onMouseLeave={()=>setHoverYr(null)} onClick={()=>onBar(yr,ret)} style={{cursor:"pointer"}}>
              <rect x={tx(i)-bw/2} y={barY} width={bw} height={barH} fill={isHit?AC:W9} opacity={isHov?1:isHit?0.82:0.30} rx={2}/>
              {lkIdx>=0&&<text x={tx(i)} y={barY-(ret>=0?8:-barH-12)} textAnchor="middle" fontSize={10} fill={YL} fontWeight="800">{String.fromCharCode(65+lkIdx)}</text>}
              {i%Math.max(1,Math.floor(entries.length/10))===0&&<text x={tx(i)} y={H-MB+14} textAnchor="middle" fontSize={8} fill={W9}>{yr}</text>}
            </g>);
          })}
          <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff20" strokeWidth={1}/>
        </svg>
      </div>
      {compareYears>0&&gs.length>1&&(
        <div style={{marginTop:10}}>
          <div style={{fontSize:9,color:W9,fontWeight:700,marginBottom:6}}>{compareYears}-YEAR GROUP BREAKDOWN</div>
          <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
            {gs.map((grp,gi)=>{
              const grets=grp.map(y=>yr_data[y]||0);
              const hits=grets.filter(v=>pattern.direction==="up"?v>0:v<0).length;
              const acc=hits/grets.length;const gavg=grets.reduce((a,b)=>a+b,0)/grets.length;
              const c=acc>=0.80?G:acc>=0.70?YL:acc>=0.50?OR:R;
              return(<div key={gi} style={{background:`${c}12`,border:`1px solid ${c}44`,borderRadius:7,padding:"8px 12px",minWidth:110}}>
                <div style={{fontSize:9,color:W9,marginBottom:2}}>{grp[0]}{grp[grp.length-1]}</div>
                <div style={{fontSize:18,fontWeight:900,color:c,lineHeight:1}}>{(acc*100).toFixed(0)}%</div>
                <div style={{fontSize:10,color:W9}}>{hits}/{grp.length} yrs</div>
                <div style={{fontSize:11,fontWeight:700,color:gavg>=0?G:R,marginTop:2}}>{gavg>=0?"+":""}{gavg.toFixed(1)}%</div>
              </div>);
            })}
          </div>
        </div>
      )}
    </div>
  );
}
let avgY=0; // module-level for SVG text ref (hoisted)

//  CHART: Overlay  all years as colored lines with hover+lock 
function OverlayChart({data,direction,label}:{data:OverlayData;direction:"up"|"down";label:string}){
  const allYears=Object.keys(data.year_paths).map(Number).sort();
  const [yearFilter,setYearFilter]=useState(0);
  const [hidden,setHidden]=useState<Set<number>>(new Set());
  const [hover,setHover]=useState<{yr:number;dayIdx:number;ret:number;sx:number;sy:number}|null>(null);
  const [lockA,setLockA]=useState<{yr:number;dayIdx:number;ret:number}|null>(null);
  const [lockB,setLockB]=useState<{yr:number;dayIdx:number;ret:number}|null>(null);
  const ref=useRef<HTMLDivElement>(null);
  if(!allYears.length) return null;
  const filtered=yearFilter>0?allYears.slice(-yearFilter):allYears;
  const active=filtered.filter(yr=>!hidden.has(yr));
  const finalRets=Object.fromEntries(allYears.map(yr=>{const pts=data.year_paths[yr]||[];return[yr,pts[pts.length-1]||0];}));
  const maxLen=Math.max(...filtered.map(yr=>(data.year_paths[yr]||[]).length),1);
  const visVals=active.flatMap(yr=>data.year_paths[yr]||[]);
  const mn=visVals.length?Math.min(...visVals,-2):-5;
  const mx=visVals.length?Math.max(...visVals,2):5;
  const rng=mx-mn||1;
  const W=640,H=240,ML=46,MR=56,MT=14,MB=28;
  const PW=W-ML-MR,PH=H-MT-MB;
  const tx=(i:number)=>ML+(i/Math.max(maxLen-1,1))*PW;
  const ty=(v:number)=>MT+PH-((v-mn)/rng)*PH;
  const z0=ty(0);
  const avgPath=Array.from({length:maxLen},(_,i)=>{const vs=active.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null&&!isNaN(v));return vs.length?vs.reduce((a,b)=>a+b,0)/vs.length:0;});
  const medPath=Array.from({length:maxLen},(_,i)=>{const vs=active.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null&&!isNaN(v)).sort((a,b)=>a-b);return vs.length?vs[Math.floor(vs.length/2)]:0;});
  const step=Math.max(1,Math.ceil(rng/6/5)*5)||2;
  const ticks:number[]=[];for(let t=Math.ceil(mn/step)*step;t<=mx+0.01;t+=step){if(ticks.length>12)break;ticks.push(Math.round(t*100)/100);}
  const onSvgClick=()=>{
    if(!hover) return;
    const pt={yr:hover.yr,dayIdx:hover.dayIdx,ret:hover.ret};
    if(!lockA){setLockA(pt);}else if(!lockB){setLockB(pt);}else{setLockA(pt);setLockB(null);}
  };
  const delta=lockA&&lockB?lockB.ret-lockA.ret:null;
  return(
    <div style={{background:"#060e18",borderRadius:10,padding:"14px 16px",border:`1px solid ${BOR}22`,marginBottom:14}}>
      <div style={{fontSize:12,fontWeight:700,color:WHT,marginBottom:8}}>{label}</div>
      {/* Year filter */}
      <div style={{display:"flex",gap:5,marginBottom:8,flexWrap:"wrap",alignItems:"center"}}>
        <span style={{fontSize:10,color:W9}}>Show:</span>
        {[[0,"All"],[3,"Last 3yr"],[5,"Last 5yr"],[7,"Last 7yr"],[10,"Last 10yr"],[15,"Last 15yr"]].map(([v,l])=>(
          <button key={v} onClick={()=>{setYearFilter(+v);setHidden(new Set());}} style={{padding:"3px 9px",borderRadius:4,fontSize:10,fontWeight:700,border:`1px solid ${yearFilter===+v?CY:BOR}`,background:yearFilter===+v?`${CY}22`:"transparent",color:yearFilter===+v?CY:W9,cursor:"pointer"}}>{l}</button>
        ))}
        <div style={{marginLeft:"auto",display:"flex",gap:4}}>
          <button onClick={()=>setHidden(new Set())} style={{padding:"3px 8px",borderRadius:4,fontSize:10,border:`1px solid ${BOR}`,background:"transparent",color:G,cursor:"pointer"}}>All On</button>
          <button onClick={()=>setHidden(new Set(filtered))} style={{padding:"3px 8px",borderRadius:4,fontSize:10,border:`1px solid ${BOR}`,background:"transparent",color:R,cursor:"pointer"}}>All Off</button>
          {(lockA||lockB)&&<button onClick={()=>{setLockA(null);setLockB(null);}} style={{padding:"3px 8px",borderRadius:4,fontSize:10,border:`1px solid ${R}44`,background:"transparent",color:R,cursor:"pointer"}}>Clear locks</button>}
        </div>
      </div>
      {/* Year toggle buttons */}
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:10}}>
        {filtered.map((yr,i)=>{
          const ret=finalRets[yr];const isHit=direction==="up"?ret>0:ret<0;
          const isActive=!hidden.has(yr);const lineCol=YEAR_COLORS[allYears.indexOf(yr)%YEAR_COLORS.length];
          return(<button key={yr} onClick={()=>setHidden(p=>{const n=new Set(p);n.has(yr)?n.delete(yr):n.add(yr);return n;})} style={{padding:"4px 9px",borderRadius:5,fontSize:10,fontWeight:700,cursor:"pointer",border:`1.5px solid ${isActive?lineCol:BOR}`,background:isActive?`${lineCol}28`:"transparent",color:isActive?lineCol:`${W9}60`,transition:"all 0.12s"}}>
            {yr} {isActive&&<span style={{fontSize:9}}>({ret>=0?"+":""}{ret.toFixed(1)}%)</span>}
          </button>);
        })}
      </div>
      {/* Lock display */}
      {(lockA||lockB)&&(
        <div style={{display:"flex",gap:8,marginBottom:8,flexWrap:"wrap",alignItems:"center"}}>
          {lockA&&<div style={{padding:"4px 10px",borderRadius:5,background:`${YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length]}22`,border:`1px solid ${YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length]}`,fontSize:11,color:YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length],fontWeight:700}}>A: {lockA.yr} D{lockA.dayIdx+1} = {lockA.ret>=0?"+":""}{lockA.ret.toFixed(2)}%</div>}
          {lockB&&<div style={{padding:"4px 10px",borderRadius:5,background:`${YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length]}22`,border:`1px solid ${YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length]}`,fontSize:11,color:YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length],fontWeight:700}}>B: {lockB.yr} D{lockB.dayIdx+1} = {lockB.ret>=0?"+":""}{lockB.ret.toFixed(2)}%</div>}
          {delta!==null&&<div style={{padding:"4px 12px",borderRadius:5,background:`${YL}22`,border:`1px solid ${YL}`,fontSize:12,color:YL,fontWeight:800}}> = {delta>=0?"+":""}{delta.toFixed(2)}%</div>}
        </div>
      )}
      {/* SVG */}
      <div style={{position:"relative"}} ref={ref}>
        {hover&&(
          <div style={{position:"absolute",left:Math.min(hover.sx+10,W-120),top:Math.max(0,hover.sy-40),
            background:"#0a1628ee",border:`1px solid ${YEAR_COLORS[allYears.indexOf(hover.yr)%YEAR_COLORS.length]}`,
            borderRadius:6,padding:"6px 10px",fontSize:11,zIndex:100,pointerEvents:"none",boxShadow:"0 4px 16px rgba(0,0,0,0.6)"}}>
            <div style={{color:YEAR_COLORS[allYears.indexOf(hover.yr)%YEAR_COLORS.length],fontWeight:700}}>{hover.yr}</div>
            <div style={{color:W9,fontSize:10}}>Day {hover.dayIdx+1}</div>
            <div style={{color:hover.ret>=0?G:R,fontWeight:700}}>{hover.ret>=0?"+":""}{hover.ret.toFixed(2)}%</div>
            <div style={{color:DIM,fontSize:9}}>Click to lock</div>
          </div>
        )}
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block",cursor:"crosshair"}}
          onMouseMove={e=>{
            const rect=ref.current?.getBoundingClientRect();if(!rect)return;
            const svgX=(e.clientX-rect.left)*(W/rect.width);
            const dayIdx=Math.round((svgX-ML)/PW*(maxLen-1));
            if(dayIdx<0||dayIdx>=maxLen){setHover(null);return;}
            const svgY=(e.clientY-rect.top)*(H/rect.height);
            let bestYr=filtered.find(yr=>!hidden.has(yr));let bestDist=999999;
            filtered.filter(yr=>!hidden.has(yr)).forEach(yr=>{
              const v=(data.year_paths[yr]||[])[dayIdx];if(v==null)return;
              const d=Math.abs(ty(v)-svgY);if(d<bestDist){bestDist=d;bestYr=yr;}
            });
            if(!bestYr){setHover(null);return;}
            const ret=(data.year_paths[bestYr]||[])[dayIdx]||0;
            setHover({yr:bestYr,dayIdx,ret,sx:e.clientX-rect.left,sy:e.clientY-rect.top});
          }}
          onMouseLeave={()=>setHover(null)}
          onClick={onSvgClick}
        >
          {/* Grid */}
          {ticks.map(t=><g key={t}><line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff0d" strokeWidth={1}/><text x={ML-5} y={ty(t)+3.5} textAnchor="end" fontSize={10} fill={W9}>{t}%</text></g>)}
          <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff40" strokeDasharray="6,4" strokeWidth={1.5}/>
          <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff20" strokeWidth={1}/>
          {[0,Math.floor(maxLen/4),Math.floor(maxLen/2),Math.floor(maxLen*3/4),maxLen-1].filter(i=>i<maxLen).map(i=><text key={i} x={tx(i)} y={H-MB+14} textAnchor="middle" fontSize={9} fill={W9}>D{i+1}</text>)}
          {/* P25-P75 band */}
          {active.length>=3&&(()=>{
            const p25s:string[]=[],p75s:string[]=[];
            for(let i=0;i<maxLen;i++){const vs=active.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null&&!isNaN(v)).sort((a,b)=>a-b);if(!vs.length)continue;p25s.push(`${p25s.length===0?"M":"L"}${tx(i).toFixed(1)},${ty(vs[Math.floor(vs.length*0.25)]).toFixed(1)}`);p75s.unshift(`L${tx(i).toFixed(1)},${ty(vs[Math.floor(vs.length*0.75)]).toFixed(1)}`);}
            if(p25s.length<2)return null;
            return <path d={p25s.join(" ")+" "+p75s.join(" ")+"Z"} fill={`${direction==="up"?G:R}18`}/>;
          })()}
          {/* Year lines */}
          {filtered.map((yr,i)=>{
            const pts=data.year_paths[yr]||[];if(pts.length<2||hidden.has(yr))return null;
            const lineCol=YEAR_COLORS[allYears.indexOf(yr)%YEAR_COLORS.length];
            const d=pts.map((v,j)=>`${j===0?"M":"L"}${tx(j).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
            const finalRet=pts[pts.length-1]||0;const isHit=direction==="up"?finalRet>0:finalRet<0;
            return(<g key={yr}>
              <path d={d} fill="none" stroke={lineCol} strokeWidth={isHit?1.4:0.8} opacity={isHit?0.80:0.28} strokeLinejoin="round" strokeLinecap="round"/>
              <text x={tx(pts.length-1)+4} y={ty(finalRet)+3.5} fontSize={8.5} fill={lineCol} opacity={0.9} fontWeight="600">{yr}</text>
            </g>);
          })}
          {/* Avg (white) + Median (yellow dashed) */}
          {active.length>0&&avgPath.length>1&&<path d={avgPath.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ")} fill="none" stroke="#ffffff" strokeWidth={2.8} opacity={0.95} strokeLinejoin="round"/>}
          {active.length>0&&medPath.length>1&&<path d={medPath.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ")} fill="none" stroke={YL} strokeWidth={1.8} opacity={0.9} strokeDasharray="8,4" strokeLinejoin="round"/>}
          {active.length>0&&avgPath.length>1&&<text x={tx(avgPath.length-1)+4} y={ty(avgPath[avgPath.length-1])+3.5} fontSize={9} fill="#ffffff" fontWeight="700">avg</text>}
          {/* Hover crosshair */}
          {hover&&<><line x1={tx(hover.dayIdx)} y1={MT} x2={tx(hover.dayIdx)} y2={H-MB} stroke="#ffffff20" strokeWidth={1} strokeDasharray="3,3"/><circle cx={tx(hover.dayIdx)} cy={ty(hover.ret)} r={4} fill={YEAR_COLORS[allYears.indexOf(hover.yr)%YEAR_COLORS.length]} stroke="#ffffff" strokeWidth={1.5}/></>}
          {/* Lock A */}
          {lockA&&!hidden.has(lockA.yr)&&(()=>{const c=YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length];return <g><circle cx={tx(lockA.dayIdx)} cy={ty(lockA.ret)} r={6} fill={c} stroke="#fff" strokeWidth={2}/><text x={tx(lockA.dayIdx)} y={ty(lockA.ret)-10} textAnchor="middle" fontSize={9} fill={c} fontWeight="800">A</text></g>;})()}
          {/* Lock B */}
          {lockB&&!hidden.has(lockB.yr)&&(()=>{const c=YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length];return <g><circle cx={tx(lockB.dayIdx)} cy={ty(lockB.ret)} r={6} fill={c} stroke="#fff" strokeWidth={2}/><text x={tx(lockB.dayIdx)} y={ty(lockB.ret)-10} textAnchor="middle" fontSize={9} fill={c} fontWeight="800">B</text></g>;})()}
          {/* Delta line A-B same year */}
          {lockA&&lockB&&lockA.yr===lockB.yr&&!hidden.has(lockA.yr)&&(()=>{const del=lockB.ret-lockA.ret;const mx2=(tx(lockA.dayIdx)+tx(lockB.dayIdx))/2,my2=(ty(lockA.ret)+ty(lockB.ret))/2;return <g><line x1={tx(lockA.dayIdx)} y1={ty(lockA.ret)} x2={tx(lockB.dayIdx)} y2={ty(lockB.ret)} stroke={YL} strokeWidth={1.5} strokeDasharray="4,3"/><text x={mx2} y={my2-8} textAnchor="middle" fontSize={10} fill={YL} fontWeight="800">{del>=0?"+":""}{del.toFixed(2)}%</text></g>;})()}
        </svg>
      </div>
      <div style={{display:"flex",gap:14,marginTop:4,fontSize:10,color:W9}}>
        <span><span style={{color:"#ffffff",fontWeight:700}}></span> Average</span>
        <span><span style={{color:YL,fontWeight:700}}>- -</span> Median</span>
        <span style={{color:DIM}}>Click line to lock A then B to compare</span>
      </div>
    </div>
  );
}

//  CHART: Year x Day heatmap 
function YearDayHeat({data}:{data:OverlayData}){
  const years=Object.keys(data.year_paths).map(Number).sort();
  if(years.length<2)return null;
  const maxLen=Math.min(Math.max(...years.map(yr=>(data.year_paths[yr]||[]).length)),30);
  const allVals=years.flatMap(yr=>(data.year_paths[yr]||[]).slice(0,maxLen));
  const maxAbs=Math.max(...allVals.map(Math.abs),1);
  const cellW=Math.max(14,Math.floor(560/maxLen));
  return(
    <div style={{marginBottom:14}}>
      <div style={{fontSize:10,color:W9,fontWeight:700,marginBottom:6}}>YEAR  DAY HEATMAP  each cell = cumulative return on that day</div>
      <div style={{overflowX:"auto"}}>
        <div style={{display:"flex",marginBottom:3}}><div style={{width:40,flexShrink:0}}/>{Array.from({length:maxLen},(_,i)=><div key={i} style={{width:cellW,textAlign:"center",fontSize:8,color:DIM}}>D{i+1}</div>)}</div>
        {years.map(yr=>{const pts=(data.year_paths[yr]||[]).slice(0,maxLen);if(!pts.length)return null;return(<div key={yr} style={{display:"flex",marginBottom:1}}>
          <div style={{width:40,flexShrink:0,fontSize:9,color:W9,lineHeight:"18px",textAlign:"right",paddingRight:4}}>{yr}</div>
          {Array.from({length:maxLen},(_,i)=>{const v=pts[i];if(v==null)return <div key={i} style={{width:cellW,height:18,background:`${BOR}22`}}/>;const bg=`${v>=0?G:R}${Math.floor(Math.abs(v)/maxAbs*200+20).toString(16).padStart(2,"0")}`;return <div key={i} title={`${yr} D${i+1}: ${v>=0?"+":""}${v.toFixed(1)}%`} style={{width:cellW,height:18,background:bg}}/>;})}</div>);
        })}
      </div>
    </div>
  );
}

//  CHART: Return distribution 
function RetDistChart({p}:{p:Pattern}){
  let yr_data:Record<string,number>={};try{yr_data=JSON.parse(p.yearly_returns);}catch{return null;}
  const rets=Object.values(yr_data).map(Number).sort((a,b)=>a-b);if(rets.length<2)return null;
  const mn=rets[0],mx=rets[rets.length-1],rng=mx-mn||1;
  const W=500,H=50;const AC=p.direction==="up"?G:R;
  const tx=(v:number)=>20+((v-mn)/rng)*(W-40);
  const med=rets[Math.floor(rets.length/2)];
  const avgR=rets.reduce((a,b)=>a+b,0)/rets.length;
  return(
    <div style={{marginBottom:14}}>
      <div style={{fontSize:10,color:W9,fontWeight:700,marginBottom:6}}>RETURN DISTRIBUTION ({rets.length} years)</div>
      <div style={{background:`${BOR}15`,borderRadius:8,padding:"10px 16px"}}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block"}}>
          <rect x={tx(p.p25_return)} y={H/2-12} width={Math.max(4,tx(p.p75_return)-tx(p.p25_return))} height={24} fill={`${AC}22`} stroke={`${AC}55`} strokeWidth={1} rx={4}/>
          {mn<0&&mx>0&&<line x1={tx(0)} y1={6} x2={tx(0)} y2={H-6} stroke={W9} strokeWidth={1} strokeDasharray="3,2" opacity={0.5}/>}
          <line x1={tx(med)} y1={H/2-16} x2={tx(med)} y2={H/2+16} stroke={YL} strokeWidth={2.5}/>
          <line x1={tx(avgR)} y1={H/2-10} x2={tx(avgR)} y2={H/2+10} stroke="#ffffff" strokeWidth={2}/>
          {rets.map((v,i)=>{const isHit=p.direction==="up"?v>0:v<0;return <circle key={i} cx={tx(v)} cy={H/2} r={5} fill={isHit?AC:W9} opacity={isHit?0.85:0.4} stroke="#060e18" strokeWidth={1}><title>{v>=0?"+":""}{v.toFixed(2)}%</title></circle>;})}
          <text x={tx(mn)} y={H+14} textAnchor="middle" fontSize={9} fill={R}>{pct(mn,1)}</text>
          <text x={tx(med)} y={H+14} textAnchor="middle" fontSize={9} fill={YL}>med {pct(med,1)}</text>
          <text x={tx(mx)} y={H+14} textAnchor="middle" fontSize={9} fill={G}>{pct(mx,1)}</text>
          <text x={tx(avgR)} y={H/2-18} textAnchor="middle" fontSize={8} fill="#fff">avg</text>
        </svg>
      </div>
    </div>
  );
}

//  PatCard with expand + overlay chart 
function PatCard({p,compareYears,symbol,assetType}:{p:Pattern;compareYears:number;symbol:string;assetType:string}){
  const [expanded,setExpanded]=useState(false);
  const [overlay,setOverlay]=useState<OverlayData|null>(null);
  const [loadingOv,setLoadingOv]=useState(false);
  const AC=p.direction==="up"?G:R;
  const confC=confColor(p.year_confidence);
  let succ:number[]=[],fail:number[]=[],yr_data:Record<string,number>={};
  try{succ=JSON.parse(p.success_years)||[];}catch{}
  try{fail=JSON.parse(p.failure_years)||[];}catch{}
  try{yr_data=JSON.parse(p.yearly_returns)||{};}catch{}

  const expand=()=>{
    setExpanded(e=>{
      if(!e&&!overlay){
        setLoadingOv(true);
        fetch(`/api/patterns/detail?symbol=${encodeURIComponent(symbol)}&asset_type=${assetType}&month=${p.anchor_month}&day=${p.anchor_day}&window=${p.window_days}`,{cache:"no-store"})
          .then(r=>r.json()).then(d=>{if(d.ok)setOverlay(d);}).catch(()=>{}).finally(()=>setLoadingOv(false));
      }
      return !e;
    });
  };

  return(
    <div style={{marginBottom:10,background:`${AC}0a`,border:`1px solid ${AC}22`,borderRadius:8,borderLeft:`4px solid ${AC}`,overflow:"hidden"}}>
      <div style={{padding:"12px 16px",cursor:"pointer"}} onClick={expand}>
        <div style={{display:"flex",alignItems:"center",gap:12,flexWrap:"wrap",marginBottom:6}}>
          <span style={{fontWeight:900,fontSize:20,color:WHT,minWidth:48}}>{wLabel(p.window_days)}</span>
          <span style={{fontSize:13,fontWeight:600,color:W9}}>{p.start_label}  {p.end_label}</span>
          <div style={{flex:1}}>
            <div style={{display:"flex",alignItems:"baseline",gap:8}}>
              <span style={{fontWeight:900,fontSize:22,color:confC}}>{(p.accuracy*100).toFixed(0)}%</span>
              <span style={{fontSize:12,color:DIM}}>accurate</span>
              <span style={{fontSize:13,color:WHT,fontWeight:600}}>({p.n_hit}/{p.n_years} yrs went {p.direction.toUpperCase()})</span>
            </div>
            <div style={{height:5,background:`${BOR}33`,borderRadius:3,marginTop:4,maxWidth:300}}>
              <div style={{height:5,width:`${Math.min(100,p.accuracy*100)}%`,background:confC,borderRadius:3}}/>
            </div>
          </div>
          <div style={{display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
            <span style={{fontSize:9,fontWeight:700,padding:"2px 6px",borderRadius:3,background:`${confC}22`,color:confC}}>
              <span style={{width:7,height:7,borderRadius:"50%",background:confC,display:"inline-block",marginRight:3}}/>
              {p.n_years}yr {p.year_confidence}
            </span>
            <span style={{fontSize:9,fontWeight:700,padding:"2px 6px",borderRadius:3,background:`${degColor(p.degradation_flag)}18`,color:degColor(p.degradation_flag)}}>{degIcon(p.degradation_flag)} {p.degradation_flag}</span>
            <span style={{fontSize:10,color:W9}}>score {p.score.toFixed(3)}</span>{(p as any).oos_accuracy!=null&&<span style={{fontSize:9,padding:"2px 6px",borderRadius:3,background:(+(p as any).oos_accuracy>=0.70?"#4ade8022":"#f8717122"),color:(+(p as any).oos_accuracy>=0.70?"#4ade80":"#f87171"),marginLeft:4,fontWeight:700}}>OOS {((p as any).oos_accuracy*100).toFixed(0)}%</span>}
            <span style={{fontSize:11,color:DIM}}>{expanded?"":""}</span>
          </div>
        </div>
        <div style={{display:"flex",gap:16,flexWrap:"wrap",fontSize:12}}>
          <span><span style={{color:DIM}}>Avg: </span><span style={{color:col(p.avg_return_all),fontWeight:700}}>{pct(p.avg_return_all)}</span></span>
          <span><span style={{color:DIM}}>Median: </span><span style={{color:col(p.median_return)}}>{pct(p.median_return)}</span></span>
          <span><span style={{color:DIM}}>Range: </span><span style={{color:R}}>{pct(p.min_return)}</span><span style={{color:DIM}}> to </span><span style={{color:G}}>{pct(p.max_return)}</span></span>
          <span><span style={{color:DIM}}>When {p.direction}: </span><span style={{color:AC,fontWeight:600}}>{pct(p.avg_return_hit)}</span></span>
        </div>
      </div>
      {expanded&&(
        <div style={{padding:"0 16px 16px"}}>
          <div style={{height:1,background:`${BOR}33`,marginBottom:14}}/>
          {/* Stats grid */}
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:8,marginBottom:16}}>
            {[
              {l:"Avg (all yrs)",v:pct(p.avg_return_all),c:col(p.avg_return_all)},
              {l:`Avg When ${p.direction.toUpperCase()}`,v:pct(p.avg_return_hit),c:AC},
              {l:"Median",v:pct(p.median_return),c:col(p.median_return)},
              {l:"P25",v:pct(p.p25_return),c:col(p.p25_return)},
              {l:"P75",v:pct(p.p75_return),c:col(p.p75_return)},
              {l:"Best Year Ret",v:pct(p.max_return),c:G},
              {l:"Worst Year Ret",v:pct(p.min_return),c:R},
              {l:"Std Dev",v:pct(p.std_return)},
              {l:"First Half Acc",v:`${(p.first_half_accuracy*100).toFixed(0)}%`,c:p.first_half_accuracy>=0.70?G:R},
              {l:"Last Half Acc",v:`${(p.last_half_accuracy*100).toFixed(0)}%`,c:p.last_half_accuracy>=0.70?G:R},
              {l:"Best Year",v:String(p.best_year||"--")},
              {l:"Worst Year",v:String(p.worst_year||"--")},
            ].map(({l,v,c})=>(
              <div key={l} style={{background:`${BOR}22`,borderRadius:5,padding:"7px 10px"}}>
                <div style={{fontSize:9,color:DIM,fontWeight:700,marginBottom:2,textTransform:"uppercase",letterSpacing:0.8}}>{l}</div>
                <div style={{fontSize:14,fontWeight:800,color:c||PRI}}>{v}</div>
              </div>
            ))}
          </div>
          {/* Return distribution */}
          <RetDistChart p={p}/>
          {/* Year bar chart */}
          <YearChart pattern={p} compareYears={compareYears}/>
          {/* Success/failure years */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            <div>
              <div style={{fontSize:10,fontWeight:700,color:G,letterSpacing:".04em",marginBottom:6}}>SUCCESS ({succ.length})</div>
              <div style={{display:"flex",flexWrap:"wrap",gap:4}}>
                {succ.map(yr=><span key={yr} style={{fontSize:10,fontWeight:700,color:G,background:`${G}18`,borderRadius:3,padding:"2px 5px"}}>{yr} <span style={{color:DIM,fontWeight:400}}>({yr_data[String(yr)]>=0?"+":""}{(yr_data[String(yr)]||0).toFixed(1)}%)</span></span>)}
              </div>
            </div>
            <div>
              <div style={{fontSize:10,fontWeight:700,color:R,letterSpacing:".04em",marginBottom:6}}>FAILURE ({fail.length})</div>
              <div style={{display:"flex",flexWrap:"wrap",gap:4}}>
                {fail.map(yr=><span key={yr} style={{fontSize:10,fontWeight:700,color:R,background:`${R}18`,borderRadius:3,padding:"2px 5px"}}>{yr} <span style={{color:DIM,fontWeight:400}}>({yr_data[String(yr)]>=0?"+":""}{(yr_data[String(yr)]||0).toFixed(1)}%)</span></span>)}
              </div>
            </div>
          </div>
          {/* Overlay chart  all years as lines */}
          {loadingOv&&<div style={{color:DIM,fontSize:12,padding:"12px 0"}}>Loading year overlay...</div>}
          {overlay&&!loadingOv&&<OverlayChart data={overlay} direction={p.direction} label={`${p.start_label}  ${p.end_label} (${p.window_days}d)  All Years Overlay`}/>}
          {/* Year x Day heatmap */}
          {overlay&&!loadingOv&&<YearDayHeat data={overlay}/>}
        </div>
      )}
    </div>
  );
}

//  Summary + Month/Window charts 
function SummaryCards({summary,dir}:{summary:Summary|undefined;dir:"up"|"down"}){
  if(!summary)return null;
  const AC=dir==="up"?G:R;
  return(
    <div style={{background:SUR,border:`1px solid ${AC}33`,borderRadius:8,padding:"14px 16px"}}>
      <div style={{fontSize:11,fontWeight:700,color:AC,letterSpacing:1.2,marginBottom:10}}>{dir.toUpperCase()} PATTERNS  {summary.n} total</div>
      <div style={{display:"flex",gap:20,flexWrap:"wrap",marginBottom:10}}>
        {[{l:"Best Acc",v:`${(summary.max_acc*100).toFixed(0)}%`,c:AC},{l:"Avg Acc",v:`${(summary.avg_acc*100).toFixed(0)}%`,c:AC},{l:"Best Score",v:summary.max_score.toFixed(3),c:CY},{l:"Avg Years",v:summary.avg_years.toFixed(0),c:WHT}].map(({l,v,c})=>(
          <div key={l}><div style={{fontSize:10,color:W9,marginBottom:2}}>{l}</div><div style={{fontSize:20,fontWeight:900,color:c}}>{v}</div></div>
        ))}
      </div>
      <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
        {[{c:"GREEN",n:summary.green_n,l:">=15yr"},{c:"YELLOW",n:summary.yellow_n,l:"10-14yr"},{c:"RED",n:summary.red_n,l:"7-9yr"},{c:"DANGER",n:summary.danger_n,l:"<7yr"}].map(({c,n,l})=>n>0&&(
          <div key={c} style={{fontSize:10,fontWeight:700,color:confColor(c),background:`${confColor(c)}18`,borderRadius:3,padding:"2px 6px"}}><span style={{width:6,height:6,borderRadius:"50%",background:confColor(c),display:"inline-block",marginRight:3}}/>{n} {l}</div>
        ))}
        {[{f:"STABLE",n:summary.stable_n},{f:"IMPROVING",n:summary.improving_n},{f:"DEGRADING",n:summary.degrading_n}].map(({f,n})=>n>0&&(
          <span key={f} style={{fontSize:10,color:degColor(f),background:`${degColor(f)}18`,borderRadius:3,padding:"2px 6px",fontWeight:600}}>{degIcon(f)} {n} {f}</span>
        ))}
      </div>
    </div>
  );
}
function MonthHeatmap({byMonth,dir}:{byMonth:ByMonth[];dir:"up"|"down"}){
  const f=byMonth.filter(b=>b.direction===dir);if(!f.length)return null;
  const maxN=Math.max(...f.map(b=>b.n));const AC=dir==="up"?G:R;
  const mm=Object.fromEntries(f.map(b=>[b.anchor_month,b]));
  return(<div><div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:8}}>{dir==="up"?"UP":"DOWN"} pattern count by month</div>
    <div style={{display:"flex",gap:4}}>{Array.from({length:12},(_,i)=>i+1).map(m=>{const b=mm[m];const int=b?b.n/maxN:0;return(<div key={m} style={{flex:1,textAlign:"center"}}>
      <div style={{height:40,background:b?`${AC}${Math.floor(int*80+15).toString(16).padStart(2,"0")}`:`${BOR}22`,borderRadius:3,marginBottom:3,display:"flex",alignItems:"center",justifyContent:"center",fontSize:9,color:b?AC:DIM,fontWeight:700}}>{b?b.n:""}</div>
      <div style={{fontSize:8,color:W9}}>{MONTHS[m].slice(0,3)}</div>
      {b&&<div style={{fontSize:7,color:W9}}>{(b.avg_acc*100).toFixed(0)}%</div>}
    </div>);})}
  </div></div>);
}
function WinDist({byWindow,dir}:{byWindow:ByWindow[];dir:"up"|"down"}){
  const f=byWindow.filter(b=>b.direction===dir);if(!f.length)return <div style={{color:DIM,fontSize:12}}>No patterns</div>;
  const maxN=Math.max(...f.map(b=>b.n));const AC=dir==="up"?G:R;
  return(<div style={{display:"flex",gap:6,flexWrap:"wrap"}}>{f.map(b=>(
    <div key={b.window_days} style={{background:`${AC}${Math.floor(b.n/maxN*55+15).toString(16).padStart(2,"0")}`,border:`1px solid ${AC}44`,borderRadius:6,padding:"7px 10px",minWidth:72,textAlign:"center"}}>
      <div style={{fontSize:13,fontWeight:700,color:WHT}}>{wLabel(b.window_days)}</div>
      <div style={{fontSize:10,color:AC,fontWeight:700}}>{b.n}</div>
      <div style={{fontSize:9,color:W9}}>{(b.avg_acc*100).toFixed(0)}% avg</div>
    </div>
  ))}</div>);
}

//  Heatmap / 3D / Bubble / Strip / Monthly (for heatData) 
function DiscoveryHeatmap({rows}:{rows:HeatRow[]}){
  const [dir,setDir]=useState<"up"|"down">("up");
  const filtered=rows.filter(r=>r.direction===dir);
  const grid:Record<string,{score:number;accuracy:number;n_hit:number;n_years:number;anchor_day:number}>={};
  for(const r of filtered){const k=`${r.anchor_month}-${r.window_days}`;if(!grid[k]||r.score>grid[k].score)grid[k]={score:r.score,accuracy:r.accuracy,n_hit:r.n_hit,n_years:r.n_years,anchor_day:r.anchor_day};}
  const maxScore=Math.max(...Object.values(grid).map(v=>v.score),0.001);
  const AC=dir==="up"?G:R;
  return(<div>
    <div style={{display:"flex",gap:8,marginBottom:10,alignItems:"center"}}>
      {(["up","down"] as const).map(d=><button key={d} onClick={()=>setDir(d)} style={{padding:"4px 12px",borderRadius:5,fontSize:11,fontWeight:700,border:"none",cursor:"pointer",background:dir===d?(d==="up"?G:R):"transparent",color:dir===d?"#000":W9}}>{d.toUpperCase()}</button>)}
      <span style={{fontSize:10,color:DIM}}>Darker = stronger. Hover for details.</span>
    </div>
    <div style={{overflowX:"auto"}}><table style={{borderCollapse:"separate",borderSpacing:3}}>
      <thead><tr><th style={{padding:"5px 10px",color:W9,textAlign:"left",fontSize:11,minWidth:40}}>Month</th>{WINDOWS.map(w=><th key={w} style={{padding:"5px 6px",color:W9,fontSize:10,textAlign:"center",minWidth:38}}>{wLabel(w)}</th>)}</tr></thead>
      <tbody>{Array.from({length:12},(_,mi)=>mi+1).map(m=>(
        <tr key={m}>
          <td style={{padding:"5px 10px",color:WHT,fontWeight:700,fontSize:12}}>{MONTHS[m]}</td>
          {WINDOWS.map(w=>{const c=grid[`${m}-${w}`];if(!c)return <td key={w}><div style={{width:36,height:28,background:`${BOR}18`,borderRadius:4}}/></td>;
            const int=c.score/maxScore;const bg=`${AC}${Math.floor(int*210+30).toString(16).padStart(2,"0")}`;
            return <td key={w} style={{padding:2}}><div title={`${MONTHS[m]} ${wLabel(w)}: ${(c.accuracy*100).toFixed(0)}% (${c.n_hit}/${c.n_years}yr)`} style={{width:36,height:28,background:bg,borderRadius:4,cursor:"default",display:"flex",alignItems:"center",justifyContent:"center",fontSize:9,color:"#000a",fontWeight:700,border:int>0.85?`1px solid ${AC}88`:"none"}}>{(c.accuracy*100).toFixed(0)}%</div></td>;
          })}
        </tr>
      ))}</tbody>
    </table></div>
  </div>);
}
function BubbleChart({patterns}:{patterns:Pattern[]}){
  if(!patterns.length)return null;
  const W=520,H=260,ML=50,MR=24,MT=12,MB=32,PW=W-ML-MR,PH=H-MT-MB;
  const xs=patterns.map(p=>p.accuracy*100),ys=patterns.map(p=>Math.abs(p.avg_return_all));
  const xMin=Math.min(...xs)-2,xMax=Math.max(...xs)+2,yMin=0,yMax=Math.max(...ys)+2;
  const tx=(v:number)=>ML+((v-xMin)/(xMax-xMin))*PW;
  const ty=(v:number)=>MT+PH-((v-yMin)/(yMax-yMin))*PH;
  const nMin=Math.min(...patterns.map(p=>p.n_years)),nMax=Math.max(...patterns.map(p=>p.n_years));
  const rScale=(n:number)=>5+((n-nMin)/(nMax-nMin||1))*14;
  const xTicks=[70,75,80,85,90,95,100].filter(t=>t>=xMin&&t<=xMax);
  const yTicks=Array.from({length:5},(_,i)=>+(yMax*i/4).toFixed(1));
  return(<div>
    <div style={{fontSize:11,color:W9,marginBottom:6}}>X=Accuracy, Y=Avg return, Size=years. Top-right = best patterns.</div>
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
      {xTicks.map(t=><g key={t}><line x1={tx(t)} y1={MT} x2={tx(t)} y2={H-MB} stroke="#ffffff08" strokeWidth={1}/><text x={tx(t)} y={H-MB+16} textAnchor="middle" fontSize={10} fill={W9}>{t}%</text></g>)}
      {yTicks.map(t=><g key={t}><line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff08" strokeWidth={1}/><text x={ML-5} y={ty(t)+4} textAnchor="end" fontSize={10} fill={W9}>{t}%</text></g>)}
      <line x1={ML} y1={MT} x2={ML} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
      <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
      {patterns.map((p,i)=>{const AC=p.direction==="up"?G:R;const r=rScale(p.n_years);return(<g key={i}><circle cx={tx(p.accuracy*100)} cy={ty(Math.abs(p.avg_return_all))} r={r} fill={`${AC}40`} stroke={AC} strokeWidth={1.5} opacity={0.9}><title>{`${p.start_label}${p.end_label} ${p.window_days}d\n${(p.accuracy*100).toFixed(0)}% (${p.n_hit}/${p.n_years}yr)\navg ${pct(p.avg_return_all)}`}</title></circle></g>);})}
      <text x={W/2} y={H-MB+28} textAnchor="middle" fontSize={10} fill={W9}>Accuracy %</text>
      <text x={12} y={H/2} textAnchor="middle" fontSize={10} fill={W9} transform={`rotate(-90,12,${H/2})`}>Avg Return %</text>
    </svg>
  </div>);
}
function CalendarStrip({patterns}:{patterns:Pattern[]}){
  if(!patterns.length)return null;
  const W=560,H=64;
  const doy=(m:number,d:number)=>{const days=[0,31,59,90,120,151,181,212,243,273,304,334];return(days[m-1]||0)+d;};
  const tx=(d:number)=>(d/365)*W;
  const up=patterns.filter(p=>p.direction==="up"),dn=patterns.filter(p=>p.direction==="down");
  const mns=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return(<div>
    <div style={{fontSize:11,color:W9,marginBottom:6}}>Bar width=duration, opacity=accuracy.</div>
    <svg width="100%" viewBox={`0 0 ${W} ${H+20}`} style={{overflow:"visible"}}>
      <rect x={0} y={0} width={W} height={H} fill="#ffffff06" rx={5}/>
      {mns.map((_,i)=>{const x=tx((i+0.5)*30.4);return <g key={i}><line x1={x} y1={0} x2={x} y2={H} stroke="#ffffff12" strokeWidth={1}/><text x={x} y={H+14} textAnchor="middle" fontSize={9} fill={W9}>{mns[i]}</text></g>;})}
      {up.map((p,i)=>{const s=doy(p.anchor_month,p.anchor_day),e=Math.min(365,s+Math.floor(p.window_days/0.69));const bw=Math.max(2,tx(e)-tx(s));return <rect key={i} x={tx(s)} y={3} width={bw} height={H/2-5} fill={G} opacity={0.35+p.accuracy*0.65} rx={2}><title>{`UP: ${p.start_label}${p.end_label} ${p.window_days}d ${(p.accuracy*100).toFixed(0)}%`}</title></rect>;})}
      {dn.map((p,i)=>{const s=doy(p.anchor_month,p.anchor_day),e=Math.min(365,s+Math.floor(p.window_days/0.69));const bw=Math.max(2,tx(e)-tx(s));return <rect key={i} x={tx(s)} y={H/2+2} width={bw} height={H/2-5} fill={R} opacity={0.35+p.accuracy*0.65} rx={2}><title>{`DOWN: ${p.start_label}${p.end_label} ${p.window_days}d ${(p.accuracy*100).toFixed(0)}%`}</title></rect>;})}
      <text x={4} y={H/4+5} fontSize={9} fill={G} fontWeight="bold">UP</text>
      <text x={4} y={H*3/4+5} fontSize={9} fill={R} fontWeight="bold">DOWN</text>
    </svg>
  </div>);
}
function MonthlySeasonality({seasonality}:{seasonality:{period_value:number;mean_return_pct:number;n_obs:number}[]}){
  if(!seasonality?.length)return <div style={{color:DIM,fontSize:12}}>No monthly data</div>;
  const maxAbs=Math.max(...seasonality.map(r=>Math.abs(r.mean_return_pct||0)),1);
  return(<div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
    {seasonality.map(r=>{const v=r.mean_return_pct||0;const int=Math.abs(v)/maxAbs;const bg=`${v>=0?G:R}${Math.floor(int*180+30).toString(16).padStart(2,"0")}`;return(
      <div key={r.period_value} style={{minWidth:72,background:bg,borderRadius:8,padding:"12px 8px",textAlign:"center",flex:"1 0 72px",maxWidth:90}}>
        <div style={{fontSize:11,color:WHT,fontWeight:600,marginBottom:4}}>{MONTHS[r.period_value]}</div>
        <div style={{fontSize:16,fontWeight:900,color:v>=0?G:R}}>{v>=0?"+":""}{v.toFixed(1)}%</div>
        <div style={{fontSize:9,color:"#ffffff",fontWeight:600,marginTop:3}}>{r.n_obs} obs</div>
      </div>
    );})}
  </div>);
}

// 
// MAIN PAGE
// 
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
  const [openPanels,setOpenPanels]=useState<Set<string>>(new Set());
  const togglePanel=(id:string)=>setOpenPanels(p=>{const n=new Set(p);n.has(id)?n.delete(id):n.add(id);return n;});

  const load=useCallback(async(sym:string)=>{
    if(!sym.trim())return;
    setLoading(true);setError(null);setData(null);setHeatData(null);
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
  const showPats=activeDir==="both"?allPats:activeDir==="up"?upPats:dnPats;
  const upSum=data?.summary.find(s=>s.direction==="up");
  const dnSum=data?.summary.find(s=>s.direction==="down");

  const Card=({title,children,accent}:{title?:string;children:React.ReactNode;accent?:string})=>(
    <div style={{background:SUR,border:`1px solid ${accent||BOR}`,borderRadius:10,marginBottom:14,overflow:"hidden"}}>
      {title&&<div style={{padding:"10px 16px",fontSize:11,fontWeight:700,letterSpacing:1.4,color:accent||CY,textTransform:"uppercase",borderBottom:`1px solid ${BOR}`}}>{title}</div>}
      <div style={{padding:"14px 16px"}}>{children}</div>
    </div>
  );

  return(
    <div style={{minHeight:"100vh",background:"var(--bg)",fontFamily:"JetBrains Mono,monospace"}}>
      <NavBar />
      <div style={{position:"sticky",top:48,zIndex:90,background:"var(--surface)",borderBottom:"1px solid var(--border)",padding:"6px 20px",fontSize:10,color:"var(--dim)",letterSpacing:2}}>PATTERNS  /  SEASONALITY DISCOVERY</div>
      <div style={{maxWidth:1300,margin:"0 auto",padding:"16px 20px"}}>
      <div style={{marginBottom:18}}>
        <h1 style={{margin:0,fontSize:26,fontWeight:900,letterSpacing:-0.5,color:WHT}}>SEASONAL PATTERNS</h1>
        <div style={{color:DIM,fontSize:13,marginTop:4}}>Recurring calendar windows automatically discovered from all available years</div>
      </div>

      {/* Search */}
      <div style={{display:"flex",gap:10,marginBottom:14}}>
        <AInput value={symInput} onChange={setSymInput} onSelect={s=>{setSymInput(s);load(s);}}/>
        <button onClick={()=>load(symInput)} disabled={loading} style={{background:loading?"transparent":CY,color:"#000",border:`2px solid ${CY}`,borderRadius:10,padding:"14px 28px",fontWeight:900,cursor:"pointer",fontSize:14,opacity:loading?0.7:1,minWidth:120}}>
          {loading?"Loading...":"Find Patterns"}
        </button>
      </div>

      {/* Filters */}
      <div style={{background:`${BOR}15`,borderRadius:10,padding:"12px 16px",marginBottom:14}}>
        <div style={{display:"flex",gap:14,flexWrap:"wrap",alignItems:"flex-start"}}>
          {[{l:"MIN ACCURACY",opts:[[0.70,"70%+"],[0.75,"75%+"],[0.80,"80%+"],[0.85,"85%+"],[0.90,"90%+"]],val:minAcc,set:setMinAcc},
            {l:"MIN YEARS",opts:[[3,"3+"],[5,"5+"],[7,"7+"],[10,"10+"],[15,"15+"]],val:minYears,set:setMinYears as (v:number)=>void}
          ].map(({l,opts,val,set})=>(
            <div key={l}><div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:".04em",marginBottom:5}}>{l}</div>
              <div style={{display:"flex",gap:3}}>{opts.map(([v,lbl])=><button key={v} onClick={()=>set(+v)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:val===+v?CY:"transparent",color:val===+v?"#000":W9}}>{lbl}</button>)}</div>
            </div>
          ))}
          <div><div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:".04em",marginBottom:5}}>DIRECTION</div>
            <div style={{display:"flex",gap:3}}>{[["both","Both"],["up","UP"],["down","DOWN"]].map(([v,l])=><button key={v} onClick={()=>setDirFilter(v)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:dirFilter===v?CY:"transparent",color:dirFilter===v?"#000":W9}}>{l}</button>)}</div>
          </div>
          <div><div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:".04em",marginBottom:5}}>WINDOW</div>
            <select value={windowFilter} onChange={e=>setWindowFilter(+e.target.value)} style={{background:"#1a2332",border:`1px solid ${BOR}`,color:PRI,borderRadius:5,padding:"4px 10px",fontSize:11}}>
              <option value={0}>All</option>{WINDOWS.map(w=><option key={w} value={w}>{wLabel(w)} ({w}d)</option>)}
            </select>
          </div>
          <div><div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:".04em",marginBottom:5}}>SORT BY</div>
            <div style={{display:"flex",gap:3}}>{[["score","Score"],["accuracy","Acc"],["n_years","Years"],["avg_ret","Return"]].map(([v,l])=><button key={v} onClick={()=>setSortBy(v)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:sortBy===v?CY:"transparent",color:sortBy===v?"#000":W9}}>{l}</button>)}</div>
          </div>
          <div><div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:".04em",marginBottom:5}}>YEAR GROUPS</div>
            <div style={{display:"flex",gap:3}}>{[[0,"Off"],[2,"2yr"],[3,"3yr"],[4,"4yr"],[5,"5yr"],[6,"6yr"],[8,"8yr"],[10,"10yr"]].map(([v,l])=><button key={v} onClick={()=>setCompareYears(+v)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:compareYears===+v?YL:"transparent",color:compareYears===+v?"#000":W9}}>{l}</button>)}</div>
          </div>
        </div>
      </div>

      {error&&<div style={{color:R,fontSize:13,marginBottom:12,padding:"12px 16px",background:`${R}12`,borderRadius:8,border:`1px solid ${R}33`}}>{error}</div>}
      {loading&&<div style={{padding:60,textAlign:"center",color:DIM,fontSize:14}}>Finding patterns for <strong style={{color:WHT}}>{symInput}</strong>...</div>}

      {data&&!loading&&(
        <div>
          {/* Header */}
          <div style={{display:"flex",gap:12,flexWrap:"wrap",marginBottom:14,alignItems:"center",padding:"14px 18px",background:SUR,borderRadius:10,border:`1px solid ${BOR}`}}>
            <div><span style={{fontSize:24,fontWeight:900,color:CY}}>{data.symbol}</span><span style={{fontSize:12,color:DIM,marginLeft:10,border:`1px solid ${BOR}`,borderRadius:4,padding:"2px 8px"}}>{data.asset_type.toUpperCase()}</span></div>
            {data.latest_price&&<div style={{fontSize:13,color:W9}}>Price: <span style={{color:WHT,fontWeight:700,fontSize:16}}>{(data.latest_price.close||0).toLocaleString("en-IN",{maximumFractionDigits:2})}</span><span style={{color:DIM,fontSize:11,marginLeft:6}}>{data.latest_price.date}</span></div>}
            <div style={{fontSize:11,color:DIM}}>{data.total_patterns} total patterns</div>
            <div style={{marginLeft:"auto",display:"flex",gap:10}}>
              {[{dir:"up",n:upPats.length},{dir:"down",n:dnPats.length}].map(({dir,n})=>n>0&&(<div key={dir} style={{background:`${dir==="up"?G:R}12`,border:`1px solid ${dir==="up"?G:R}44`,borderRadius:8,padding:"8px 16px",textAlign:"center"}}><div style={{fontSize:11,fontWeight:700,color:dir==="up"?G:R,letterSpacing:1}}>{dir.toUpperCase()}</div><div style={{fontSize:22,fontWeight:900,color:dir==="up"?G:R}}>{n}</div></div>))}
            </div>
          </div>

          {/* Summary cards */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            <SummaryCards summary={upSum} dir="up"/>
            <SummaryCards summary={dnSum} dir="down"/>
          </div>

          {/* Month + Window charts */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
            <div style={{background:SUR,border:`1px solid ${G}33`,borderRadius:8,padding:"14px 16px"}}><div style={{fontSize:11,fontWeight:700,color:G,letterSpacing:1.2,marginBottom:10}}>UP BY MONTH</div><MonthHeatmap byMonth={data.by_month} dir="up"/></div>
            <div style={{background:SUR,border:`1px solid ${R}33`,borderRadius:8,padding:"14px 16px"}}><div style={{fontSize:11,fontWeight:700,color:R,letterSpacing:1.2,marginBottom:10}}>DOWN BY MONTH</div><MonthHeatmap byMonth={data.by_month} dir="down"/></div>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
            <div style={{background:SUR,border:`1px solid ${G}33`,borderRadius:8,padding:"14px 16px"}}><div style={{fontSize:11,fontWeight:700,color:G,letterSpacing:1.2,marginBottom:10}}>UP BY WINDOW</div><WinDist byWindow={data.by_window} dir="up"/></div>
            <div style={{background:SUR,border:`1px solid ${R}33`,borderRadius:8,padding:"14px 16px"}}><div style={{fontSize:11,fontWeight:700,color:R,letterSpacing:1.2,marginBottom:10}}>DOWN BY WINDOW</div><WinDist byWindow={data.by_window} dir="down"/></div>
          </div>

          {/* Tab bar */}
          <div style={{display:"flex",gap:3,flexWrap:"wrap",marginBottom:14,background:`${BOR}15`,borderRadius:10,padding:5}}>
            {[["patterns"," Pattern Cards"],["heatmap"," Discovery Heatmap"],["3d"," 3D Surface"],["bubble"," Bubble Chart"],["strip"," Calendar Strip"],["monthly"," Monthly Heatmap"]].map(([id,label])=>(
              <button key={id} onClick={()=>setActiveTab(id as typeof activeTab)} style={{flex:1,padding:"9px 6px",borderRadius:7,fontSize:11,fontWeight:700,cursor:"pointer",border:"none",background:activeTab===id?CY:"transparent",color:activeTab===id?"#000":W9,transition:"all 0.15s",minWidth:110}}>{label}</button>
            ))}
          </div>

          {/*  PATTERNS TAB  */}
          {activeTab==="patterns"&&(
            <div>
              {/* Direction + quick-open chart buttons */}
              <div style={{display:"flex",gap:6,marginBottom:10,flexWrap:"wrap",alignItems:"center"}}>
                {([["both",`All (${allPats.length})`],["up",`UP (${upPats.length})`],["down",`DOWN (${dnPats.length})`]] as const).map(([v,l])=>(
                  <button key={v} onClick={()=>setActiveDir(v)} style={{padding:"7px 16px",borderRadius:6,fontSize:12,fontWeight:700,cursor:"pointer",border:`1px solid ${v==="down"?R:v==="up"?G:CY}`,background:activeDir===v?(v==="down"?R:v==="up"?G:CY):"transparent",color:activeDir===v?"#000":DIM}}>{l}</button>
                ))}
                {/* Expandable chart panel buttons  Point 3 */}
                <div style={{marginLeft:"auto",display:"flex",gap:4,flexWrap:"wrap"}}>
                  <span style={{fontSize:10,color:W9,alignSelf:"center"}}>Open charts:</span>
                  {[["hmap"," Heatmap"],["bubl"," Bubble"],["strp"," Strip"],["mnth"," Monthly"]].map(([id,lbl])=>(
                    <button key={id} onClick={()=>togglePanel(id)} style={{padding:"5px 10px",borderRadius:6,fontSize:10,fontWeight:700,cursor:"pointer",border:`1px solid ${openPanels.has(id)?CY:BOR}`,background:openPanels.has(id)?`${CY}22`:"transparent",color:openPanels.has(id)?CY:W9}}>
                      {lbl} {openPanels.has(id)?"":""}
                    </button>
                  ))}
                </div>
              </div>

              {/* Expandable panels */}
              {heatData&&openPanels.has("hmap")&&<Card title="Window Discovery Heatmap" accent={CY}><DiscoveryHeatmap rows={heatData.heatmap_rows}/></Card>}
              {openPanels.has("bubl")&&<Card title="Bubble Chart  Accuracy vs Return" accent={YL}><BubbleChart patterns={allPats}/></Card>}
              {openPanels.has("strp")&&<Card title="Calendar Strip" accent={G}><CalendarStrip patterns={allPats}/></Card>}
              {heatData&&openPanels.has("mnth")&&<Card title="Monthly Seasonality" accent={CY}><MonthlySeasonality seasonality={heatData.seasonality||[]}/></Card>}

              {/* Pattern list */}
              {showPats.length===0?(
                <div style={{color:DIM,fontSize:13,padding:"30px 0",textAlign:"center"}}>No patterns match filters.</div>
              ):(
                <div>
                  {activeDir==="both"&&upPats.length>0&&<div style={{marginBottom:20}}><div style={{fontSize:13,fontWeight:700,color:G,letterSpacing:".04em",marginBottom:8}}>UP PATTERNS ({upPats.length})</div>{upPats.map((p,i)=><PatCard key={`up-${i}`} p={p} compareYears={compareYears} symbol={data.symbol} assetType={data.asset_type}/>)}</div>}
                  {activeDir==="both"&&dnPats.length>0&&<div><div style={{fontSize:13,fontWeight:700,color:R,letterSpacing:".04em",marginBottom:8}}>DOWN PATTERNS ({dnPats.length})</div>{dnPats.map((p,i)=><PatCard key={`dn-${i}`} p={p} compareYears={compareYears} symbol={data.symbol} assetType={data.asset_type}/>)}</div>}
                  {activeDir==="up"&&upPats.map((p,i)=><PatCard key={i} p={p} compareYears={compareYears} symbol={data.symbol} assetType={data.asset_type}/>)}
                  {activeDir==="down"&&dnPats.map((p,i)=><PatCard key={i} p={p} compareYears={compareYears} symbol={data.symbol} assetType={data.asset_type}/>)}
                </div>
              )}
            </div>
          )}

          {/*  OTHER TABS  */}
          {activeTab==="heatmap"&&heatData&&<Card title="Window Discovery Heatmap  Month  Duration  Accuracy" accent={CY}><DiscoveryHeatmap rows={heatData.heatmap_rows}/></Card>}
          {activeTab==="bubble"&&<Card title="Bubble Chart  Accuracy vs Avg Return" accent={YL}><BubbleChart patterns={allPats}/></Card>}
          {activeTab==="strip"&&<Card title="Calendar Strip  Pattern positions through the year" accent={G}><CalendarStrip patterns={allPats}/></Card>}
          {activeTab==="monthly"&&heatData&&<Card title="Monthly Seasonality" accent={CY}><MonthlySeasonality seasonality={heatData.seasonality||[]}/></Card>}
          {activeTab==="3d"&&heatData&&(
            <Card title="3D Discovery Surface  Month  Duration  Score" accent={OR}>
              <div style={{overflowX:"auto"}}>
                <div style={{display:"flex",marginBottom:4,paddingLeft:52}}>{MONTHS.slice(1).map(m=><div key={m} style={{width:38,textAlign:"center",fontSize:9,color:W9,fontWeight:600}}>{m}</div>)}</div>
                {WINDOWS.slice().reverse().map(w=>(
                  <div key={w} style={{display:"flex",marginBottom:2,alignItems:"center"}}>
                    <div style={{width:48,flexShrink:0,textAlign:"right",paddingRight:6,fontSize:9,color:W9,fontWeight:600}}>{wLabel(w)}</div>
                    {Array.from({length:12},(_,mi)=>{
                      const wi=WINDOWS.indexOf(w);
                      const uk=`${mi}-${wi}`,dk=`${mi}-${wi}`;
                      const hRows=heatData.heatmap_rows;
                      const best=hRows.filter(r=>r.anchor_month-1===mi&&r.window_days===w).sort((a,b)=>b.score-a.score)[0];
                      if(!best)return <div key={mi} style={{width:38,height:28,background:`${BOR}15`,borderRadius:3,margin:1}}/>;
                      const AC=best.direction==="up"?G:R;const int=Math.min(1,best.score/0.6);
                      const bg=`${AC}${Math.floor(int*210+30).toString(16).padStart(2,"0")}`;
                      return <div key={mi} title={`${MONTHS[mi+1]} ${wLabel(w)}: ${(best.accuracy*100).toFixed(0)}% ${best.direction}`} style={{width:38,height:28,background:bg,borderRadius:3,margin:1,display:"flex",alignItems:"center",justifyContent:"center",fontSize:8.5,color:"#000a",fontWeight:700,border:int>0.85?`1px solid ${AC}88`:"none"}}>{(best.accuracy*100).toFixed(0)}%</div>;
                    })}
                  </div>
                ))}
                <div style={{display:"flex",marginTop:4,paddingLeft:52}}>{MONTHS.slice(1).map(m=><div key={m} style={{width:38,textAlign:"center",fontSize:9,color:W9}}>{m}</div>)}</div>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
      </div>
    </div>
  );
}