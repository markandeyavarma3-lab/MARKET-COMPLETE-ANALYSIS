# -*- coding: utf-8 -*-
"""
fix_phase13_v2.py  --  Run from D:\\MICC
Fixes:
  1. Year filter on overlay chart (last 3/5/7/10 years + remove all)
  2. Thinner lines + better looking overlay chart
  3. 3D surface rendered as proper bar chart (not isometric that clips)
  4. Monthly heatmap obs in bright white
  5. Backtest analysis: break years into N-year groups, analyze each group
  6. Smaller windows: add 1,2,3 day windows to the builder
Run: py D:\\MICC\\fix_phase13_v2.py
"""
from pathlib import Path

BASE = Path(r"D:\MICC")
APP  = BASE / "micc-dashboard" / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

def patch(p: Path, old: str, new: str, label: str = ""):
    txt = p.read_text(encoding="utf-8")
    if old not in txt:
        print(f"  [SKIP] {label or p.name} — pattern not found")
        return False
    p.write_text(txt.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"  [OK] patched {label or p.name}")
    return True

# =============================================================================
# [1] Fix build_seasonality_v2.py — add smaller windows (1,2,3,4 days)
# =============================================================================
print("\n[1] Adding smaller windows to build_seasonality_v2.py...")
sv2 = BASE / "build_seasonality_v2.py"
if sv2.exists():
    patch(sv2,
        "WINDOWS          = [5, 7, 10, 12, 15, 18, 20, 25, 30, 35, 40, 45, 50, 60, 75, 90]",
        "WINDOWS          = [1, 2, 3, 4, 5, 7, 10, 12, 15, 18, 20, 25, 30, 35, 40, 45, 50, 60, 75, 90]",
        "smaller windows"
    )
    print("  Note: Re-run: py D:\\MICC\\build_seasonality_v2.py --yes -> choose [r] to reset and rebuild")
else:
    print("  [WARN] build_seasonality_v2.py not found at D:\\MICC\\")

# =============================================================================
# [2] Rewrite InteractiveYearChart component in patterns/page.tsx
#     + Fix 3D surface + Fix monthly obs color + Add backtest analysis
# =============================================================================
print("\n[2] Patching /patterns/page.tsx...")

page_path = APP / "patterns" / "page.tsx"
if not page_path.exists():
    print("  [WARN] patterns/page.tsx not found. Run setup_phase13_final.py first.")
else:
    txt = page_path.read_text(encoding="utf-8")

    # ── FIX 1: Replace InteractiveYearChart with year-filter version ──────
    OLD_CHART = '''// ── INTERACTIVE YEAR OVERLAY CHART (image 4 style) ───────────────────────
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
}'''

    NEW_CHART = '''// ── INTERACTIVE YEAR OVERLAY CHART — with year filter + thin lines ────────
function InteractiveYearChart({data,direction,patternLabel}:{data:OverlayData;direction:"up"|"down";patternLabel:string}){
  const allYears=Object.keys(data.year_paths).map(Number).sort();
  const [yearFilter,setYearFilter]=useState<number>(0); // 0=all, 3/5/7/10=last N years
  const [hiddenYears,setHiddenYears]=useState<Set<number>>(new Set());

  if(!allYears.length) return null;

  // Apply year filter
  const filteredYears=yearFilter>0
    ? allYears.slice(-yearFilter)
    : allYears;

  // Apply individual toggles (only within filtered set)
  const activeYears=filteredYears.filter(yr=>!hiddenYears.has(yr));

  const toggleYr=(yr:number)=>setHiddenYears(prev=>{
    const n=new Set(prev);
    if(n.has(yr))n.delete(yr); else n.add(yr);
    return n;
  });
  const removeAll=()=>setHiddenYears(new Set(filteredYears));
  const addAll=()=>setHiddenYears(prev=>{const n=new Set(prev);filteredYears.forEach(y=>n.delete(y));return n;});

  const finalRets=Object.fromEntries(allYears.map(yr=>{
    const pts=data.year_paths[yr]||[];
    return[yr,pts[pts.length-1]||0];
  }));

  const maxLen=Math.max(...filteredYears.map(yr=>(data.year_paths[yr]||[]).length),1);
  const visVals=activeYears.flatMap(yr=>data.year_paths[yr]||[]);
  const mn=visVals.length?Math.min(...visVals,-2):-5;
  const mx=visVals.length?Math.max(...visVals,2):5;
  const rng=mx-mn||1;
  const W=640,H=240,ML=46,MR=56,MT=14,MB=28;
  const PW=W-ML-MR,PH=H-MT-MB;
  const tx=(i:number)=>ML+(i/Math.max(maxLen-1,1))*PW;
  const ty=(v:number)=>MT+PH-((v-mn)/rng)*PH;
  const z0=ty(0);

  const avgPath:number[]=Array.from({length:maxLen},(_,i)=>{
    const vs=activeYears.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null&&!isNaN(v));
    return vs.length?vs.reduce((a,b)=>a+b,0)/vs.length:0;
  });

  const tickStep=Math.max(1,Math.ceil(rng/6/5)*5)||2;
  const ticks:number[]=[];
  for(let t=Math.ceil(mn/tickStep)*tickStep;t<=mx+0.01;t+=tickStep){
    if(ticks.length>12)break;
    ticks.push(Math.round(t*100)/100);
  }

  return(
    <div style={{background:"#060e18",borderRadius:10,padding:"14px 16px",border:`1px solid ${BOR}22`}}>
      {/* Header */}
      <div style={{fontSize:12,fontWeight:700,color:WHT,marginBottom:10,display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}}>
        <span>{patternLabel}</span>
        <span style={{fontSize:10,color:W9,fontWeight:400}}>Click years below to toggle lines</span>
      </div>

      {/* Year filter row */}
      <div style={{display:"flex",gap:6,marginBottom:10,alignItems:"center",flexWrap:"wrap"}}>
        <span style={{fontSize:10,color:W9,fontWeight:600}}>Show:</span>
        {[[0,"All"],[3,"Last 3yr"],[5,"Last 5yr"],[7,"Last 7yr"],[10,"Last 10yr"],[15,"Last 15yr"]].map(([v,l])=>(
          <button key={v} onClick={()=>{setYearFilter(+v);setHiddenYears(new Set());}} style={{
            padding:"3px 10px",borderRadius:4,fontSize:10,fontWeight:700,border:`1px solid ${yearFilter===+v?CY:BOR}`,
            background:yearFilter===+v?`${CY}22`:"transparent",color:yearFilter===+v?CY:W9,cursor:"pointer",
          }}>{l}</button>
        ))}
        <div style={{marginLeft:"auto",display:"flex",gap:4}}>
          <button onClick={addAll} style={{padding:"3px 8px",borderRadius:4,fontSize:10,fontWeight:600,border:`1px solid ${BOR}`,background:"transparent",color:G,cursor:"pointer"}}>All On</button>
          <button onClick={removeAll} style={{padding:"3px 8px",borderRadius:4,fontSize:10,fontWeight:600,border:`1px solid ${BOR}`,background:"transparent",color:R,cursor:"pointer"}}>All Off</button>
        </div>
      </div>

      {/* Individual year toggles */}
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:12}}>
        {filteredYears.map((yr,i)=>{
          const ret=finalRets[yr];
          const isHit=direction==="up"?ret>0:ret<0;
          const isActive=!hiddenYears.has(yr);
          const lineCol=YEAR_COLORS[allYears.indexOf(yr)%YEAR_COLORS.length];
          return(
            <button key={yr} onClick={()=>toggleYr(yr)} style={{
              padding:"4px 9px",borderRadius:5,fontSize:10,fontWeight:700,cursor:"pointer",
              border:`1.5px solid ${isActive?lineCol:BOR}`,
              background:isActive?`${lineCol}28`:"transparent",
              color:isActive?lineCol:`${W9}80`,
              transition:"all 0.12s",
            }}>
              {yr} <span style={{opacity:isActive?1:0,fontSize:9}}>({ret>=0?"+":""}{ ret.toFixed(1)}%)</span>
            </button>
          );
        })}
      </div>

      {/* SVG Chart */}
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block"}}>
        {/* Background bands */}
        {ticks.filter((_,i)=>i%2===0).map(t=>{
          const y1=ty(t),y2=ty(Math.min(mx,t+tickStep));
          return <rect key={t} x={ML} y={Math.min(y1,y2)} width={PW} height={Math.abs(y1-y2)} fill="#ffffff03" rx={0}/>;
        })}

        {/* Grid + Y labels */}
        {ticks.map(t=>(
          <g key={t}>
            <line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff0d" strokeWidth={1}/>
            <text x={ML-5} y={ty(t)+3.5} textAnchor="end" fontSize={10} fill={W9}>{t}%</text>
          </g>
        ))}

        {/* Zero line */}
        <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff40" strokeDasharray="6,4" strokeWidth={1.5}/>
        <text x={ML-5} y={z0+3.5} textAnchor="end" fontSize={9} fill="#ffffff80">0%</text>

        {/* X axis */}
        <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff20" strokeWidth={1}/>
        {[0,Math.floor(maxLen/4),Math.floor(maxLen/2),Math.floor(maxLen*3/4),maxLen-1].filter(i=>i<maxLen).map(i=>(
          <text key={i} x={tx(i)} y={H-MB+14} textAnchor="middle" fontSize={9} fill={W9}>D{i+1}</text>
        ))}

        {/* Shaded area between P25-P75 of active years */}
        {activeYears.length>=3&&(()=>{
          const p25Path:string[]=[];
          const p75Path:string[]=[];
          for(let i=0;i<maxLen;i++){
            const vs=activeYears.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null&&!isNaN(v)).sort((a,b)=>a-b);
            if(!vs.length) continue;
            const p25=vs[Math.floor(vs.length*0.25)];
            const p75=vs[Math.floor(vs.length*0.75)];
            p25Path.push(`${p25Path.length===0?"M":"L"}${tx(i).toFixed(1)},${ty(p25).toFixed(1)}`);
            p75Path.unshift(`L${tx(i).toFixed(1)},${ty(p75).toFixed(1)}`);
          }
          if(p25Path.length<2) return null;
          const area=p25Path.join(" ")+" "+p75Path.join(" ")+"Z";
          const AC=direction==="up"?G:R;
          return <path d={area} fill={`${AC}18`}/>;
        })()}

        {/* Individual year lines — thin */}
        {filteredYears.map((yr,i)=>{
          const pts=data.year_paths[yr]||[];
          if(pts.length<2||hiddenYears.has(yr)) return null;
          const lineCol=YEAR_COLORS[allYears.indexOf(yr)%YEAR_COLORS.length];
          const d=pts.map((v,j)=>`${j===0?"M":"L"}${tx(j).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
          const finalRet=pts[pts.length-1]||0;
          const isHit=direction==="up"?finalRet>0:finalRet<0;
          const endY=ty(finalRet);
          const endX=tx(pts.length-1);
          return(
            <g key={yr}>
              <path d={d} fill="none" stroke={lineCol}
                strokeWidth={isHit?1.4:0.9}
                opacity={isHit?0.80:0.30}
                strokeLinejoin="round" strokeLinecap="round"/>
              {/* End-of-line label */}
              <text x={endX+4} y={endY+3.5} fontSize={8.5} fill={lineCol} opacity={0.95} fontWeight="600">{yr}</text>
            </g>
          );
        })}

        {/* Average line */}
        {activeYears.length>0&&avgPath.length>1&&(
          <path
            d={avgPath.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ")}
            fill="none" stroke={YL} strokeWidth={2.5} opacity={0.98}
            strokeLinejoin="round" strokeLinecap="round"
          />
        )}
        {/* Avg end label */}
        {activeYears.length>0&&avgPath.length>1&&(()=>{
          const last=avgPath[avgPath.length-1];
          return <text x={tx(avgPath.length-1)+4} y={ty(last)+3.5} fontSize={9} fill={YL} fontWeight="700">avg</text>;
        })()}
      </svg>
    </div>
  );
}'''

    # ── FIX 2: 3D Surface — replace isometric with proper bar chart ───────
    OLD_3D = '''// ── 3D Surface ────────────────────────────────────────────────────────────
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
}'''

    NEW_3D = '''// ── 3D Surface — proper grouped bar chart (isometric style, visible) ────
function Surface3D({rows}:{rows:HeatData["heatmap_rows"]}){
  const [view3d,setView3d]=useState<"up"|"down"|"both">("both");
  if(!rows.length) return null;

  // Build best pattern per (month, window) for each direction
  const upGrid:Record<string,{score:number;accuracy:number;avg:number}>={};
  const dnGrid:Record<string,{score:number;accuracy:number;avg:number}>={};
  for(const r of rows){
    const k=`${r.anchor_month-1}-${WINDOWS.indexOf(r.window_days)}`;
    if(WINDOWS.indexOf(r.window_days)<0) continue;
    if(r.direction==="up"){if(!upGrid[k]||r.score>upGrid[k].score)upGrid[k]={score:r.score,accuracy:r.accuracy,avg:r.avg_return_all};}
    else {if(!dnGrid[k]||r.score>dnGrid[k].score)dnGrid[k]={score:r.score,accuracy:r.accuracy,avg:r.avg_return_all};}
  }

  const allScores=[...Object.values(upGrid),...Object.values(dnGrid)].map(v=>v.score);
  const maxScore=Math.max(...allScores,0.001);

  // Use a 2D stacked-bar heatmap as the "3D" view — much cleaner and readable
  // Row = window duration, Column = month, color = direction+intensity
  return(
    <div>
      <div style={{display:"flex",gap:8,marginBottom:12,alignItems:"center"}}>
        {(["up","down","both"] as const).map(v=>(
          <button key={v} onClick={()=>setView3d(v)} style={{padding:"4px 12px",borderRadius:5,fontSize:11,fontWeight:700,border:"none",cursor:"pointer",
            background:view3d===v?(v==="up"?G:v==="down"?R:CY):"transparent",
            color:view3d===v?"#000":W9}}>
            {v==="both"?"Both":v.toUpperCase()}
          </button>
        ))}
        <span style={{fontSize:10,color:DIM}}>Intensity = pattern score. Hover cells for details.</span>
      </div>
      <div style={{overflowX:"auto"}}>
        <div style={{display:"flex",gap:2,marginBottom:3,paddingLeft:52}}>
          {MONTHS.slice(1).map(m=><div key={m} style={{width:36,textAlign:"center",fontSize:9,color:W9,fontWeight:600}}>{m}</div>)}
        </div>
        {WINDOWS.slice().reverse().map(w=>{
          const wi=WINDOWS.indexOf(w);
          return(
            <div key={w} style={{display:"flex",gap:2,marginBottom:2,alignItems:"center"}}>
              <div style={{width:48,flexShrink:0,textAlign:"right",paddingRight:6,fontSize:9,color:W9,fontWeight:600}}>{wLabel(w)}</div>
              {Array.from({length:12},(_,mi)=>{
                const uk=`${mi}-${wi}`,dk=`${mi}-${wi}`;
                const up=upGrid[uk],dn=dnGrid[dk];
                const showUp=(view3d==="up"||view3d==="both")&&up;
                const showDn=(view3d==="down"||view3d==="both")&&dn;
                const best=showUp&&showDn?(up.score>=dn.score?{c:G,cell:up,dir:"up"}:{c:R,cell:dn,dir:"down"}):showUp?{c:G,cell:up,dir:"up"}:showDn?{c:R,cell:dn,dir:"down"}:null;
                if(!best) return <div key={mi} style={{width:36,height:26,background:`${BOR}15`,borderRadius:3}}/>;
                const intens=best.cell.score/maxScore;
                const bg=`${best.c}${Math.floor(intens*210+30).toString(16).padStart(2,"0")}`;
                const tip=`${MONTHS[mi+1]} ${wLabel(w)}: ${(best.cell.accuracy*100).toFixed(0)}% ${best.dir}\navg ${best.cell.avg>=0?"+":""}${best.cell.avg.toFixed(1)}%`;
                return(
                  <div key={mi} title={tip} style={{
                    width:36,height:26,background:bg,borderRadius:3,cursor:"default",
                    display:"flex",alignItems:"center",justifyContent:"center",
                    fontSize:8.5,color:"#000a",fontWeight:700,
                    boxShadow:intens>0.8?`0 0 4px ${best.c}66`:"none",
                    border:intens>0.85?`1px solid ${best.c}88`:"none",
                  }}>
                    {(best.cell.accuracy*100).toFixed(0)}%
                  </div>
                );
              })}
            </div>
          );
        })}
        <div style={{display:"flex",gap:2,marginTop:6,paddingLeft:52}}>
          {MONTHS.slice(1).map(m=><div key={m} style={{width:36,textAlign:"center",fontSize:9,color:W9}}>{m}</div>)}
        </div>
      </div>
      {/* Score legend */}
      <div style={{display:"flex",gap:6,marginTop:10,alignItems:"center",fontSize:10,color:W9}}>
        <span>Score legend:</span>
        {[[G,"Bullish"],[R,"Bearish"]].map(([c,l])=>(
          <span key={l} style={{display:"flex",alignItems:"center",gap:3}}>
            <span style={{display:"flex",gap:1}}>
              {[0.3,0.5,0.7,0.9].map(op=><div key={op} style={{width:12,height:12,background:`${c}${Math.floor(op*255).toString(16).padStart(2,"0")}`,borderRadius:2}}/>)}
            </span>
            {l} (low→high)
          </span>
        ))}
      </div>
    </div>
  );
}'''

    # ── FIX 3: Monthly heatmap obs text color — white ─────────────────────
    OLD_OBS = '''<div style={{fontSize:9,color:W9,marginTop:3}}>{r.n_obs} obs</div>'''
    NEW_OBS = '''<div style={{fontSize:9,color:"#ffffff",fontWeight:600,marginTop:3}}>{r.n_obs} obs</div>'''

    # ── FIX 4: Add BacktestAnalysis component before PatternTable ─────────
    OLD_TABLE_FUNC = '''// ── THE MAIN TABLE (exact format from images 5/6/7) ──────────────────────
function PatternTable('''

    NEW_BACKTEST_AND_TABLE = '''// ── BACKTEST ANALYSIS — Break years into N-year groups ──────────────────
function BacktestAnalysis({p,overlayData}:{p:Pattern|null;overlayData:OverlayData|null}){
  const [groupSize,setGroupSize]=useState(3);
  if(!p||!overlayData) return null;

  let yr_data:Record<string,number>={};
  try{yr_data=JSON.parse(p.yearly_returns)||{};}catch{}
  const years=Object.keys(yr_data).map(Number).sort();
  if(years.length<groupSize) return null;

  // Build groups
  const groups:number[][]=[];
  for(let i=0;i<years.length;i+=groupSize)groups.push(years.slice(i,i+groupSize));

  const AC=p.direction==="up"?G:R;

  // Per-group stats
  const groupStats=groups.map(grp=>{
    const rets=grp.map(y=>yr_data[String(y)]||0);
    const hits=rets.filter(v=>p.direction==="up"?v>0:v<0).length;
    const acc=hits/rets.length;
    const avg=rets.reduce((a,b)=>a+b,0)/rets.length;
    const med=[...rets].sort((a,b)=>a-b)[Math.floor(rets.length/2)]||0;
    return{grp,rets,hits,acc,avg,med,start:grp[0],end:grp[grp.length-1]};
  });

  // Overall stats
  const allRets=years.map(y=>yr_data[String(y)]||0);
  const overallHits=allRets.filter(v=>p.direction==="up"?v>0:v<0).length;
  const overallAcc=overallHits/allRets.length;
  const overallAvg=allRets.reduce((a,b)=>a+b,0)/allRets.length;

  const maxAbs=Math.max(...groupStats.map(g=>Math.abs(g.avg)),1);

  return(
    <div style={{padding:"16px",background:"#060e18",borderRadius:10,border:`1px solid ${BOR}22`,marginBottom:16}}>
      <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:14,flexWrap:"wrap"}}>
        <div style={{fontSize:12,fontWeight:700,color:WHT}}>PERIOD BACKTEST ANALYSIS</div>
        <div style={{display:"flex",gap:4,alignItems:"center"}}>
          <span style={{fontSize:10,color:W9}}>Group size:</span>
          {[2,3,4,5,6,7,8,10].map(n=>(
            <button key={n} onClick={()=>setGroupSize(n)} style={{
              padding:"3px 8px",borderRadius:4,fontSize:10,fontWeight:700,cursor:"pointer",
              border:`1px solid ${groupSize===n?CY:BOR}`,
              background:groupSize===n?`${CY}22`:"transparent",
              color:groupSize===n?CY:W9,
            }}>{n}yr</button>
          ))}
        </div>
        <span style={{fontSize:10,color:DIM}}>{groups.length} periods × {groupSize} years each</span>
      </div>

      {/* Overall summary */}
      <div style={{display:"flex",gap:10,flexWrap:"wrap",marginBottom:14,padding:"10px 14px",background:`${AC}10`,borderRadius:8,border:`1px solid ${AC}33`}}>
        <div><div style={{fontSize:9,color:DIM,fontWeight:700}}>OVERALL ACCURACY</div><div style={{fontSize:18,fontWeight:900,color:AC}}>{(overallAcc*100).toFixed(0)}%</div></div>
        <div><div style={{fontSize:9,color:DIM,fontWeight:700}}>TOTAL YEARS</div><div style={{fontSize:18,fontWeight:900,color:WHT}}>{years.length}</div></div>
        <div><div style={{fontSize:9,color:DIM,fontWeight:700}}>OVERALL AVG</div><div style={{fontSize:18,fontWeight:900,color:overallAvg>=0?G:R}}>{overallAvg>=0?"+":""}{overallAvg.toFixed(1)}%</div></div>
        <div><div style={{fontSize:9,color:DIM,fontWeight:700}}>HITS</div><div style={{fontSize:18,fontWeight:900,color:AC}}>{overallHits}/{years.length}</div></div>
      </div>

      {/* Group cards */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(155px,1fr))",gap:8,marginBottom:14}}>
        {groupStats.map((gs,i)=>{
          const c=gs.acc>=0.80?G:gs.acc>=0.70?YL:gs.acc>=0.50?OR:R;
          const barW=(Math.abs(gs.avg)/maxAbs)*100;
          return(
            <div key={i} style={{background:`${c}12`,border:`1px solid ${c}44`,borderRadius:8,padding:"10px 12px"}}>
              <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:4}}>{gs.start}–{gs.end}</div>
              <div style={{fontSize:22,fontWeight:900,color:c,lineHeight:1}}>{(gs.acc*100).toFixed(0)}%</div>
              <div style={{fontSize:10,color:W9,marginTop:2}}>{gs.hits}/{gs.grp.length} years</div>
              <div style={{height:4,background:`${BOR}33`,borderRadius:2,margin:"6px 0"}}>
                <div style={{height:4,width:`${barW}%`,background:gs.avg>=0?G:R,borderRadius:2}}/>
              </div>
              <div style={{fontSize:11,fontWeight:700,color:gs.avg>=0?G:R}}>avg {gs.avg>=0?"+":""}{gs.avg.toFixed(1)}%</div>
              <div style={{fontSize:9,color:DIM}}>med {gs.med>=0?"+":""}{gs.med.toFixed(1)}%</div>
            </div>
          );
        })}
      </div>

      {/* Accuracy trend chart */}
      <div style={{fontSize:10,color:W9,marginBottom:6}}>Accuracy over time (each bar = one period):</div>
      <div style={{display:"flex",gap:4,alignItems:"flex-end",height:60}}>
        {groupStats.map((gs,i)=>{
          const h=Math.max(4,gs.acc*56);
          const c=gs.acc>=0.80?G:gs.acc>=0.70?YL:gs.acc>=0.50?OR:R;
          return(
            <div key={i} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",gap:2}}>
              <div style={{fontSize:8,color:c,fontWeight:700}}>{(gs.acc*100).toFixed(0)}%</div>
              <div style={{width:"100%",height:h,background:c,borderRadius:"3px 3px 0 0",opacity:0.85,
                transition:"height 0.3s"}}/>
              <div style={{fontSize:7,color:DIM,whiteSpace:"nowrap"}}>{gs.start}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── THE MAIN TABLE (exact format from images 5/6/7) ──────────────────────
function PatternTable('''

    # Apply all patches
    changed = False
    if OLD_CHART in txt:
        txt = txt.replace(OLD_CHART, NEW_CHART, 1)
        print("  [OK] Year overlay chart fixed (filter + thin lines)")
        changed = True
    else:
        print("  [SKIP] Chart not found — may already be patched")

    if OLD_3D in txt:
        txt = txt.replace(OLD_3D, NEW_3D, 1)
        print("  [OK] 3D surface replaced with heatmap bar chart")
        changed = True
    else:
        print("  [SKIP] 3D surface not found")

    if OLD_OBS in txt:
        txt = txt.replace(OLD_OBS, NEW_OBS, 1)
        print("  [OK] Monthly obs text color = white")
        changed = True
    else:
        print("  [SKIP] Monthly obs not found")

    if OLD_TABLE_FUNC in txt:
        txt = txt.replace(OLD_TABLE_FUNC, NEW_BACKTEST_AND_TABLE, 1)
        print("  [OK] Backtest analysis component added")
        changed = True
    else:
        print("  [SKIP] PatternTable function not found")

    # Now add BacktestAnalysis to ExpandedPatternDetail
    OLD_DETAIL = '''  {/* Interactive overlay chart */}
      {loading&&<div style={{color:DIM,fontSize:12,padding:"20px 0"}}>Loading year paths...</div>}
      {overlay&&!loading&&(
        <div style={{marginBottom:16}}>
          <InteractiveYearChart
            data={overlay}
            direction={p.direction}
            patternLabel={`${p.start_label} → ${p.end_label} (${p.window_days}d)`}
          />
        </div>
      )}'''

    NEW_DETAIL = '''  {/* Backtest analysis */}
      <BacktestAnalysis p={p} overlayData={overlay}/>

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
      )}'''

    if OLD_DETAIL in txt:
        txt = txt.replace(OLD_DETAIL, NEW_DETAIL, 1)
        print("  [OK] BacktestAnalysis injected into expanded row")
        changed = True

    if changed:
        page_path.write_text(txt, encoding="utf-8", newline="\n")
        print("  [SAVED] patterns/page.tsx")
    else:
        print("  [WARN] No changes applied — patterns/page.tsx may need full rebuild via setup_phase13_final.py")

print("""
=============================================================
PHASE 13 v2 FIXES COMPLETE
=============================================================

Changes applied:
  1. Overlay chart: year filter (Last 3/5/7/10/15yr + All On/Off)
     + Lines are now thin (1.4px hit / 0.9px miss)
     + Shaded P25-P75 band behind lines
     + End-of-line year labels
     + Prettier dark background

  2. 3D Surface: replaced broken isometric with clean 2D heatmap
     Rows = window duration, Cols = month, Color = score intensity
     Toggle UP / DOWN / Both
     Much more readable and actually shows the data

  3. Monthly heatmap obs: now bright white (#ffffff)

  4. Backtest analysis: NEW component in expanded row
     - Choose group size: 2/3/4/5/6/7/8/10 years
     - Each group shows: accuracy %, hits/total, avg return, median
     - Accuracy trend bar chart over time
     - Overall summary at top

  5. Smaller windows: 1,2,3,4 day windows added to builder
     Re-run: py D:\\MICC\\build_seasonality_v2.py --yes -> [r]eset

Restart:
  cd D:\\MICC\\micc-dashboard && npm run dev
""")
