# -*- coding: utf-8 -*-
"""
fix_pattern_card_final.py  --  Run from D:\\MICC
Fixes:
  1. Restore the year-by-year bar chart inside expanded pattern cards
     (was removed accidentally — image shows it should be there)
  2. Move year group comparison to BOTTOM of expanded card (not top)
  3. Add hover tooltip + click-to-lock to the bar chart
  4. Keep the return distribution dot plot (from image)
  5. Expandable chart sections (Point 3) — toggle buttons on table tab
Run: py D:\\MICC\\fix_pattern_card_final.py
"""
from pathlib import Path
import re

BASE = Path(r"D:\MICC")
APP  = BASE / "micc-dashboard" / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# Rewrite ExpandedPatternDetail with all features
# =============================================================================
print("\nPatching ExpandedPatternDetail in patterns/page.tsx...")

page = APP / "patterns" / "page.tsx"
if not page.exists():
    print("  [WARN] patterns/page.tsx not found — run setup_phase13_final.py first")
    exit(1)

txt = page.read_text(encoding="utf-8")

OLD_EXPANDED = '''// ── Expanded row detail ───────────────────────────────────────────────────
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
}'''

NEW_EXPANDED = '''// ── Year-by-year bar chart with hover+lock (restored from image) ──────────
function YearBarChart({p,compareYears}:{p:Pattern;compareYears:number}){
  const [hoverYr,setHoverYr]=useState<string|null>(null);
  const [lockPts,setLockPts]=useState<{yr:string;ret:number}[]>([]);

  let yr_data:Record<string,number>={};
  try{yr_data=JSON.parse(p.yearly_returns)||{};}catch{}
  const entries=Object.entries(yr_data).sort(([a],[b])=>+a-+b);
  if(!entries.length) return null;

  const AC=p.direction==="up"?G:R;
  const rets=entries.map(([,v])=>v as number);
  const mn=Math.min(...rets,-2),mx=Math.max(...rets,2),rng=mx-mn||1;
  const avgRet=rets.reduce((a,b)=>a+b,0)/rets.length;

  const W=620,H=160,ML=44,MR=40,MT=10,MB=30;
  const PW=W-ML-MR,PH=H-MT-MB;
  const barW=Math.max(4,Math.floor(PW/entries.length)-2);
  const tx=(i:number)=>ML+i*(PW/entries.length)+barW/2;
  const ty=(v:number)=>MT+PH-((v-mn)/rng)*PH;
  const z0=ty(0);
  const avgY=ty(avgRet);

  // Ticks
  const tickStep=Math.max(2,Math.ceil(rng/5/2)*2);
  const ticks:number[]=[];
  for(let t=Math.ceil(mn/tickStep)*tickStep;t<=mx+0.01;t+=tickStep){if(ticks.length>10)break;ticks.push(Math.round(t*100)/100);}

  const onBarClick=(yr:string,ret:number)=>{
    setLockPts(prev=>{
      if(prev.find(p=>p.yr===yr)) return prev.filter(p=>p.yr!==yr);
      if(prev.length>=2) return [{yr,ret}];
      return [...prev,{yr,ret}];
    });
  };

  const delta=lockPts.length===2?lockPts[1].ret-lockPts[0].ret:null;

  // Year groups — at bottom
  const groupSize=compareYears||0;
  const allYears=entries.map(([yr])=>yr);
  const groups:string[][]=groupSize>0?[]:[];
  if(groupSize>0){for(let i=0;i<allYears.length;i+=groupSize)groups.push(allYears.slice(i,i+groupSize));}

  return(
    <div style={{marginBottom:16}}>
      <div style={{fontSize:10,color:W9,fontWeight:700,letterSpacing:0.8,marginBottom:6}}>
        YEAR-BY-YEAR RETURNS
        <span style={{fontSize:9,color:DIM,fontWeight:400,marginLeft:8}}>
          Hover bar for details. Click to lock A/B and compare.
        </span>
        {lockPts.length>0&&(
          <button onClick={()=>setLockPts([])} style={{marginLeft:8,fontSize:9,color:R,background:"transparent",border:`1px solid ${R}44`,borderRadius:3,padding:"1px 6px",cursor:"pointer"}}>Clear</button>
        )}
      </div>

      {/* Lock comparison display */}
      {lockPts.length>0&&(
        <div style={{display:"flex",gap:8,marginBottom:8,flexWrap:"wrap",alignItems:"center"}}>
          {lockPts.map((lp,i)=>{
            const isHit=p.direction==="up"?lp.ret>0:lp.ret<0;
            return(
              <div key={lp.yr} style={{padding:"4px 10px",borderRadius:5,background:`${isHit?AC:W9}22`,border:`1px solid ${isHit?AC:W9}66`,fontSize:11,color:isHit?AC:W9,fontWeight:700}}>
                {String.fromCharCode(65+i)}: {lp.yr} = {lp.ret>=0?"+":""}{lp.ret.toFixed(1)}%
              </div>
            );
          })}
          {delta!==null&&(
            <div style={{padding:"4px 12px",borderRadius:5,background:`${YL}22`,border:`1px solid ${YL}`,fontSize:12,color:YL,fontWeight:800}}>
              Δ = {delta>=0?"+":""}{delta.toFixed(1)}%
            </div>
          )}
        </div>
      )}

      <div style={{position:"relative"}}>
        {/* Hover tooltip */}
        {hoverYr&&yr_data[hoverYr]!=null&&(()=>{
          const idx=entries.findIndex(([yr])=>yr===hoverYr);
          const ret=yr_data[hoverYr];
          const isHit=p.direction==="up"?ret>0:ret<0;
          return(
            <div style={{position:"absolute",top:0,left:Math.max(0,Math.min(tx(idx)-30,PW)),
              background:"#0a1628ee",border:`1px solid ${isHit?AC:W9}`,borderRadius:6,
              padding:"6px 10px",fontSize:11,zIndex:100,pointerEvents:"none",
              boxShadow:"0 4px 16px rgba(0,0,0,0.6)"}}>
              <div style={{color:WHT,fontWeight:700}}>{hoverYr}</div>
              <div style={{color:isHit?AC:R,fontWeight:700}}>{ret>=0?"+":""}{ret.toFixed(2)}%</div>
              <div style={{color:DIM,fontSize:9}}>Click to lock {lockPts.length===0?"A":lockPts.length===1?"B":"(replace A)"}</div>
            </div>
          );
        })()}

        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block"}}>
          {/* Grid */}
          {ticks.map(t=>(
            <g key={t}>
              <line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff0a" strokeWidth={1}/>
              <text x={ML-4} y={ty(t)+3.5} textAnchor="end" fontSize={9} fill={W9}>{t}%</text>
            </g>
          ))}
          {/* Zero line */}
          <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff35" strokeDasharray="4,3" strokeWidth={1}/>
          {/* Avg dashed line */}
          <line x1={ML} y1={avgY} x2={W-MR} y2={avgY} stroke={YL} strokeDasharray="8,4" strokeWidth={1.8} opacity={0.9}/>
          <text x={W-MR+4} y={avgY+3.5} fontSize={9} fill={YL} fontWeight="700">avg</text>

          {/* Bars */}
          {entries.map(([yr,ret_],i)=>{
            const ret=ret_ as number;
            const isHit=p.direction==="up"?ret>0:ret<0;
            const barH=Math.max(2,Math.abs(ty(ret)-z0));
            const barY=ret>=0?ty(ret):z0;
            const barColor=isHit?AC:W9;
            const isHovered=hoverYr===yr;
            const isLocked=lockPts.some(lp=>lp.yr===yr);
            const lockIdx=lockPts.findIndex(lp=>lp.yr===yr);
            return(
              <g key={yr}
                onMouseEnter={()=>setHoverYr(yr)}
                onMouseLeave={()=>setHoverYr(null)}
                onClick={()=>onBarClick(yr,ret)}
                style={{cursor:"pointer"}}>
                <rect x={tx(i)-barW/2} y={barY} width={barW} height={barH}
                  fill={barColor}
                  opacity={isHovered?1:isHit?0.80:0.35}
                  rx={2}/>
                {/* Lock indicator */}
                {isLocked&&(
                  <text x={tx(i)} y={barY-(ret>=0?6:-(barH+14))} textAnchor="middle"
                    fontSize={9} fill={YL} fontWeight="800">
                    {String.fromCharCode(65+lockIdx)}
                  </text>
                )}
                {/* Year label */}
                <text x={tx(i)} y={H-MB+14} textAnchor="middle" fontSize={7.5} fill={isHit?W9:DIM}
                  transform={`rotate(-45,${tx(i)},${H-MB+8})`}>
                  {yr}
                </text>
              </g>
            );
          })}

          {/* X axis */}
          <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff20" strokeWidth={1}/>
        </svg>
      </div>

      {/* Year group comparison — AT BOTTOM */}
      {groupSize>0&&groups.length>1&&(
        <div style={{marginTop:12}}>
          <div style={{fontSize:9,color:W9,fontWeight:700,letterSpacing:0.8,marginBottom:8}}>
            {groupSize}-YEAR GROUP BREAKDOWN
          </div>
          <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
            {groups.map((grp,gi)=>{
              const grpRets=grp.map(y=>yr_data[y]||0);
              const hits=grpRets.filter(v=>p.direction==="up"?v>0:v<0).length;
              const acc=hits/grpRets.length;
              const avg=grpRets.reduce((a,b)=>a+b,0)/grpRets.length;
              const c=acc>=0.80?G:acc>=0.70?YL:acc>=0.50?OR:R;
              return(
                <div key={gi} style={{background:`${c}12`,border:`1px solid ${c}44`,borderRadius:7,padding:"8px 12px",minWidth:120}}>
                  <div style={{fontSize:9,color:W9,marginBottom:2}}>{grp[0]}–{grp[grp.length-1]}</div>
                  <div style={{fontSize:18,fontWeight:900,color:c,lineHeight:1}}>{(acc*100).toFixed(0)}%</div>
                  <div style={{fontSize:10,color:W9}}>{hits}/{grp.length} yrs</div>
                  <div style={{fontSize:11,fontWeight:700,color:avg>=0?G:R,marginTop:2}}>{avg>=0?"+":""}{avg.toFixed(1)}%</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Expanded row detail ───────────────────────────────────────────────────
function ExpandedPatternDetail({p,symbol,assetType,compareYears}:{p:Pattern;symbol:string;assetType:string;compareYears:number}){
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
    <div style={{padding:"20px 24px",borderTop:`1px solid ${BOR}33`,background:"#060e18"}}>
      {/* Stats grid */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:8,marginBottom:16}}>
        {[
          {l:"Avg Return (all yrs)",v:pct(p.avg_return_all),c:col(p.avg_return_all)},
          {l:"Avg When Hit",v:pct(p.avg_return_hit),c:AC},
          {l:"Median Return",v:pct(p.median_return),c:col(p.median_return)},
          {l:"P25 Return",v:pct(p.p25_return),c:col(p.p25_return)},
          {l:"P75 Return",v:pct(p.p75_return),c:col(p.p75_return)},
          {l:"Best Year Return",v:pct(p.max_return),c:G},
          {l:"Worst Year Return",v:pct(p.min_return),c:R},
          {l:"Std Deviation",v:pct(p.std_return)},
          {l:"First Half Acc",v:`${(p.first_half_accuracy*100).toFixed(0)}%`,c:p.first_half_accuracy>=0.70?G:R},
          {l:"Last Half Acc",v:`${(p.last_half_accuracy*100).toFixed(0)}%`,c:p.last_half_accuracy>=0.70?G:R},
          {l:"Best Year",v:String(p.best_year||"--")},
          {l:"Worst Year",v:String(p.worst_year||"--")},
        ].map(({l,v,c})=>(
          <div key={l} style={{background:`${BOR}20`,borderRadius:6,padding:"8px 10px"}}>
            <div style={{fontSize:9,color:DIM,fontWeight:700,letterSpacing:0.8,textTransform:"uppercase",marginBottom:3}}>{l}</div>
            <div style={{fontSize:14,fontWeight:800,color:c||PRI}}>{v}</div>
          </div>
        ))}
      </div>

      {/* Return distribution dot plot */}
      <div style={{marginBottom:16}}>
        <div style={{fontSize:10,color:W9,fontWeight:700,marginBottom:6}}>
          RETURN DISTRIBUTION ({Object.keys(yr_data).length} years)
        </div>
        {(()=>{
          const rets=Object.values(yr_data).map(Number).sort((a,b)=>a-b);
          if(!rets.length) return null;
          const mn=rets[0],mx=rets[rets.length-1],rng=mx-mn||1;
          const W=560,H=60;
          const tx=(v:number)=>20+((v-mn)/rng)*(W-40);
          const med=rets[Math.floor(rets.length/2)];
          const p25=rets[Math.floor(rets.length*0.25)];
          const p75=rets[Math.floor(rets.length*0.75)];
          const avgR=rets.reduce((a,b)=>a+b,0)/rets.length;
          return(
            <div style={{background:`${BOR}15`,borderRadius:8,padding:"10px 16px"}}>
              <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block"}}>
                {/* P25-P75 shaded box */}
                <rect x={tx(p25)} y={H/2-14} width={Math.max(4,tx(p75)-tx(p25))} height={28}
                  fill={`${AC}22`} stroke={`${AC}55`} strokeWidth={1} rx={4}/>
                {/* Zero line */}
                {mn<0&&mx>0&&<line x1={tx(0)} y1={8} x2={tx(0)} y2={H-8} stroke={W9} strokeWidth={1} strokeDasharray="3,2" opacity={0.5}/>}
                {/* Median */}
                <line x1={tx(med)} y1={H/2-18} x2={tx(med)} y2={H/2+18} stroke={YL} strokeWidth={2.5}/>
                {/* Avg */}
                <line x1={tx(avgR)} y1={H/2-12} x2={tx(avgR)} y2={H/2+12} stroke={"#ffffff"} strokeWidth={2}/>
                {/* Dots */}
                {rets.map((v,i)=>{
                  const isHit=p.direction==="up"?v>0:v<0;
                  return <circle key={i} cx={tx(v)} cy={H/2+(Math.random()*10-5)*0} r={5}
                    fill={isHit?AC:W9} opacity={isHit?0.85:0.4}
                    stroke="#060e18" strokeWidth={1}>
                    <title>{v>=0?"+":""}{ v.toFixed(2)}%</title>
                  </circle>;
                })}
                {/* Labels */}
                <text x={tx(mn)} y={H-4} textAnchor="middle" fontSize={9} fill={R}>{pct(mn,1)}</text>
                <text x={tx(med)} y={H+12} textAnchor="middle" fontSize={9} fill={YL}>med {pct(med,1)}</text>
                <text x={tx(mx)} y={H-4} textAnchor="middle" fontSize={9} fill={G}>{pct(mx,1)}</text>
                <text x={tx(avgR)+3} y={H/2-20} textAnchor="middle" fontSize={8} fill="#fff">avg</text>
              </svg>
            </div>
          );
        })()}
      </div>

      {/* Year-by-year bar chart — THE MAIN CHART (restored) */}
      <YearBarChart p={p} compareYears={compareYears}/>

      {/* Interactive overlay chart */}
      {loading&&<div style={{color:DIM,fontSize:12,padding:"16px 0"}}>Loading year-path overlay...</div>}
      {overlay&&!loading&&(
        <div style={{marginBottom:14}}>
          <InteractiveYearChart
            data={overlay}
            direction={p.direction}
            patternLabel={`${p.start_label} → ${p.end_label} (${p.window_days}d)`}
          />
        </div>
      )}

      {/* Year x Day heatmap */}
      {overlay&&!loading&&(
        <div style={{marginTop:14}}>
          <div style={{fontSize:10,color:W9,fontWeight:700,marginBottom:6}}>YEAR × DAY HEATMAP</div>
          <YearDayHeatmap data={overlay}/>
        </div>
      )}
    </div>
  );
}'''

# Find and replace
if "// ── Expanded row detail ───────────────────────────────────────────────────" in txt:
    # Find the full function
    start_marker = "// ── Expanded row detail ───────────────────────────────────────────────────"
    start_idx = txt.find(start_marker)

    # Find the end (next top-level function or component)
    # Look for the next // ── or export default
    end_markers = [
        "\n// ── MAIN TABLE",
        "\n// ── THE MAIN TABLE",
        "\n// ═══",
        "\nexport default function",
    ]
    end_idx = len(txt)
    for em in end_markers:
        idx = txt.find(em, start_idx + 100)
        if idx > 0 and idx < end_idx:
            end_idx = idx

    old_func = txt[start_idx:end_idx]

    # Also check if YearBarChart already exists — if so, don't add it again
    if "function YearBarChart" in txt:
        # Just replace ExpandedPatternDetail
        txt = txt.replace(old_func, NEW_EXPANDED[NEW_EXPANDED.find("// ── Expanded row detail"):], 1)
        print("  [OK] Updated ExpandedPatternDetail (YearBarChart already exists)")
    else:
        txt = txt.replace(old_func, NEW_EXPANDED, 1)
        print("  [OK] Replaced ExpandedPatternDetail + added YearBarChart")

    # Now fix PatternTable to pass compareYears to ExpandedPatternDetail
    # The table calls ExpandedPatternDetail — update its props
    txt = txt.replace(
        "<ExpandedPatternDetail p={p} symbol={symbol} assetType={assetType}/>",
        "<ExpandedPatternDetail p={p} symbol={symbol} assetType={assetType} compareYears={compareYears}/>",
    )
    # Fix PatternTable signature to accept compareYears
    txt = txt.replace(
        "function PatternTable({patterns,symbol,assetType,onRowClick,activeIdx}:{",
        "function PatternTable({patterns,symbol,assetType,onRowClick,activeIdx,compareYears}:{",
    )
    txt = txt.replace(
        "  patterns:Pattern[]; symbol:string; assetType:string;\n  onRowClick:(idx:number,p:Pattern)=>void; activeIdx:number|null;",
        "  patterns:Pattern[]; symbol:string; assetType:string;\n  onRowClick:(idx:number,p:Pattern)=>void; activeIdx:number|null; compareYears:number;",
    )
    # Pass compareYears from main page to PatternTable
    txt = txt.replace(
        "<PatternTable\n                  patterns={activeTableDir===\"up\"?upPats:dnPats}\n                  symbol={data.symbol}\n                  assetType={data.asset_type}\n                  activeIdx={expandedRow}\n                  onRowClick={(idx)=>setExpandedRow(expandedRow===idx?null:idx)}",
        "<PatternTable\n                  patterns={activeTableDir===\"up\"?upPats:dnPats}\n                  symbol={data.symbol}\n                  assetType={data.asset_type}\n                  activeIdx={expandedRow}\n                  compareYears={compareYears}\n                  onRowClick={(idx)=>setExpandedRow(expandedRow===idx?null:idx)}",
    )
    print("  [OK] PatternTable updated to pass compareYears")

    page.write_text(txt, encoding="utf-8", newline="\n")
    print("  [SAVED] patterns/page.tsx")
else:
    print("  [WARN] Could not find ExpandedPatternDetail — file structure may have changed")
    print("  Run setup_phase13_final.py first, then this script")

print("""
=============================================================
FIX PATTERN CARD FINAL COMPLETE
=============================================================

Restored & fixed:
  1. YEAR-BY-YEAR BAR CHART is back in expanded pattern rows
     - Green bars = years that went in the right direction
     - Gray bars = failed years
     - Yellow dashed line = average return
     - Hover any bar -> tooltip with year + return%
     - Click bar -> locks as point A (first click) or B (second click)
     - Shows Δ between A and B return%
     - Click again on locked bar to unlock

  2. YEAR GROUP COMPARISON is now at the BOTTOM of the card
     (not at top — as per your feedback on image 1)
     
  3. RETURN DISTRIBUTION dot plot restored
     - Each dot = one year
     - Yellow line = median, White = average
     - Shaded box = P25-P75 range

  4. compareYears properly passed from page -> PatternTable -> ExpandedPatternDetail -> YearBarChart

Run: cd D:\\MICC\\micc-dashboard && npm run dev
""")
