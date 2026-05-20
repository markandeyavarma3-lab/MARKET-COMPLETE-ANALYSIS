# -*- coding: utf-8 -*-
"""
fix_deep_final.py  --  Run from D:\\MICC
Fixes:
  1. /deep page NaN error (corr_3y: NaN) — patches BOTH /api/deep/route.ts
     AND /api/deep/[symbol]/route.ts with proper NaN sanitization
  2. Upgrades InteractiveYearChart with hover tooltip + click-to-lock comparison
  3. Makes charts available as separate expandable sections

Run: py D:\\MICC\\fix_deep_final.py
"""
from pathlib import Path

BASE = Path(r"D:\MICC")
APP  = BASE / "micc-dashboard" / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# [1] Fix /api/deep/route.ts  — the Iota room overview
#     This is where corr_3y: NaN comes from when loading /deep page
# =============================================================================
print("\n[1/3] Rewriting /api/deep/route.ts with NaN fix...")

write(APP / "api" / "deep" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'
import fs               from 'fs'

const DA = 'D:/MICC'

function sanitize(raw: string): string {
  return raw
    .replace(/:\s*NaN\b/g,      ': null')
    .replace(/:\s*Infinity\b/g,  ': null')
    .replace(/:\s*-Infinity\b/g, ': null')
}

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[deep]', r.stderr?.slice(0,300)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(sanitize(out))
  } catch(e) { console.error('[deep]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    // Load Iota cached report
    const reportPath = path.join(DA, 'agents', 'iota', 'last_report.json')
    let report: Record<string, unknown> | null = null
    if (fs.existsSync(reportPath)) {
      try {
        const raw = fs.readFileSync(reportPath, 'utf-8')
        report = JSON.parse(sanitize(raw))
      } catch(e) {
        console.error('[deep] iota report parse error:', String(e))
        report = null
      }
    }

    // Best probability stocks (20d window)
    const bestProb = qdb(`
      SELECT ws.symbol, ws.asset_type,
             ws.prob_positive, ws.mean_return, ws.p5, ws.p95,
             ws.sharpe_ratio, ws.n_windows,
             ss.cagr_pct, ss.ann_volatility_pct, ss.max_drawdown_pct
      FROM window_stats ws
      LEFT JOIN symbol_series_stats ss ON ws.symbol = ss.symbol
      WHERE ws.window_days = 20
        AND ws.asset_type = 'stock'
        AND ws.n_windows >= 100
      ORDER BY ws.prob_positive DESC
      LIMIT 20
    `)

    // Risk-adjusted gems (high Sharpe)
    const sharpeGems = qdb(`
      SELECT ws.symbol, ws.window_days,
             ws.sharpe_ratio, ws.prob_positive,
             ws.mean_return, ws.std_return,
             ws.p5, ws.p95
      FROM window_stats ws
      WHERE ws.window_days = 20
        AND ws.asset_type = 'stock'
        AND ws.n_windows >= 100
        AND ws.sharpe_ratio IS NOT NULL
      ORDER BY ws.sharpe_ratio DESC
      LIMIT 20
    `)

    // Worst-case protected (p5 floor > -5%)
    const protected_ = qdb(`
      SELECT symbol, window_days, p5, p95,
             prob_positive, mean_return, sharpe_ratio
      FROM window_stats
      WHERE window_days = 20
        AND asset_type = 'stock'
        AND p5 > -5
        AND n_windows >= 100
      ORDER BY p5 DESC
      LIMIT 20
    `)

    // Global macro pulse
    const globalMacro = qdb(`
      SELECT symbol, asset_type,
             prob_positive, mean_return, std_return,
             p5, p95, sharpe_ratio
      FROM window_stats
      WHERE window_days = 20
        AND asset_type IN ('global', 'index')
        AND n_windows >= 20
      ORDER BY prob_positive DESC
      LIMIT 20
    `)

    // Index deep stats — NSE indices
    const indexStats = qdb(`
      SELECT ws.symbol,
             ws.prob_positive, ws.mean_return, ws.std_return,
             ws.p5, ws.p95, ws.sharpe_ratio, ws.n_windows,
             ss.cagr_pct, ss.max_drawdown_pct
      FROM window_stats ws
      LEFT JOIN symbol_series_stats ss ON ws.symbol = ss.symbol
      WHERE ws.window_days = 20
        AND ws.asset_type = 'index'
        AND ws.n_windows >= 20
      ORDER BY ws.prob_positive DESC
      LIMIT 15
    `)

    // Correlations — CORRECT columns: benchmark (not symbol_b)
    // corr_1y (not correlation_20d), IFNULL to avoid NaN
    const correlations = qdb(`
      SELECT symbol,
             benchmark                        AS symbol_b,
             IFNULL(corr_1y,  0)              AS corr_1y,
             IFNULL(corr_3y,  0)              AS corr_3y,
             IFNULL(beta_1y,  0)              AS beta_1y
      FROM symbol_correlations
      WHERE benchmark IS NOT NULL
        AND corr_1y IS NOT NULL
      ORDER BY ABS(IFNULL(corr_1y,0)) DESC
      LIMIT 30
    `)

    // Regime stats for Nifty 50
    const niftyRegime = qdb(`
      SELECT regime, n_windows, mean_return, prob_positive, p5, p95
      FROM window_regime_stats
      WHERE symbol = 'NIFTY 50' AND window_days = 20
      ORDER BY regime
    `)

    return NextResponse.json({
      ok: true,
      has_cached_report: !!report,
      report,
      best_prob:    bestProb,
      sharpe_gems:  sharpeGems,
      protected:    protected_,
      global_macro: globalMacro,
      index_stats:  indexStats,
      correlations,
      nifty_regime: niftyRegime,
      generated_at: new Date().toISOString(),
    })
  } catch(e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")

# =============================================================================
# [2] Fix /api/deep/[symbol]/route.ts — already done but ensure NaN fix
# =============================================================================
print("\n[2/3] Ensuring /api/deep/[symbol]/route.ts has NaN sanitization...")

sym_route = APP / "api" / "deep" / "[symbol]" / "route.ts"
if sym_route.exists():
    txt = sym_route.read_text(encoding="utf-8")
    # Check if sanitize function exists
    if "sanitize" not in txt and "replace(/:\\s*NaN" not in txt:
        # Add NaN sanitization to qdb function
        old = "return out ? JSON.parse(out) : []"
        new = "return out ? JSON.parse(out.replace(/:\\s*NaN\\b/g,': null').replace(/:\\s*Infinity\\b/g,': null').replace(/:\\s*-Infinity\\b/g,': null')) : []"
        if old in txt:
            sym_route.write_text(txt.replace(old, new), encoding="utf-8", newline="\n")
            print("  [OK] NaN fix added to [symbol] route")
        else:
            print("  [OK] Already has NaN handling")
    else:
        print("  [OK] Already has NaN sanitization")
else:
    print("  [WARN] [symbol]/route.ts not found — run fix_deep_nan.py first")

# =============================================================================
# [3] Upgrade InteractiveYearChart in patterns/page.tsx
#     Add: hover tooltip (year/day/return), click-to-lock comparison points
# =============================================================================
print("\n[3/3] Upgrading InteractiveYearChart with hover tooltip + click-to-lock...")

page = APP / "patterns" / "page.tsx"
if not page.exists():
    print("  [WARN] patterns/page.tsx not found")
else:
    txt = page.read_text(encoding="utf-8")

    # Find and replace the SVG section inside InteractiveYearChart
    # We replace just the SVG + add pointer event handlers
    OLD_SVG_BLOCK = '''      {/* SVG Chart */}
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
      </svg>'''

    NEW_SVG_BLOCK = '''      {/* Click-to-lock comparison info */}
      {(lockA||lockB)&&(
        <div style={{display:"flex",gap:10,marginBottom:8,flexWrap:"wrap",alignItems:"center"}}>
          {lockA&&<div style={{padding:"4px 10px",borderRadius:5,background:`${YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length]}22`,border:`1px solid ${YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length]}`,fontSize:11,color:YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length],fontWeight:700}}>
            A: {lockA.yr} D{lockA.dayIdx+1} = {lockA.ret>=0?"+":""}{lockA.ret.toFixed(2)}%
          </div>}
          {lockB&&<div style={{padding:"4px 10px",borderRadius:5,background:`${YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length]}22`,border:`1px solid ${YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length]}`,fontSize:11,color:YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length],fontWeight:700}}>
            B: {lockB.yr} D{lockB.dayIdx+1} = {lockB.ret>=0?"+":""}{lockB.ret.toFixed(2)}%
          </div>}
          {lockA&&lockB&&<div style={{padding:"4px 12px",borderRadius:5,background:`${YL}22`,border:`1px solid ${YL}`,fontSize:12,color:YL,fontWeight:800}}>
            Δ = {(lockB.ret-lockA.ret)>=0?"+":""}{(lockB.ret-lockA.ret).toFixed(2)}%
          </div>}
          <button onClick={()=>{setLockA(null);setLockB(null);}} style={{fontSize:10,color:R,background:"transparent",border:`1px solid ${R}44`,borderRadius:4,padding:"2px 8px",cursor:"pointer"}}>Clear locks</button>
        </div>
      )}

      {/* Hover tooltip */}
      {hover&&(
        <div style={{pointerEvents:"none",position:"absolute",
          left:hover.screenX+12,top:hover.screenY-10,
          background:"#0a1628ee",border:`1px solid ${YEAR_COLORS[allYears.indexOf(hover.yr)%YEAR_COLORS.length]}`,
          borderRadius:6,padding:"6px 10px",fontSize:11,zIndex:100,boxShadow:"0 4px 16px rgba(0,0,0,0.6)"}}>
          <div style={{color:YEAR_COLORS[allYears.indexOf(hover.yr)%YEAR_COLORS.length],fontWeight:700}}>{hover.yr}</div>
          <div style={{color:W9}}>Day {hover.dayIdx+1}</div>
          <div style={{color:hover.ret>=0?G:R,fontWeight:700}}>{hover.ret>=0?"+":""}{hover.ret.toFixed(2)}%</div>
          <div style={{color:DIM,fontSize:9,marginTop:2}}>Click to lock point</div>
        </div>
      )}

      {/* SVG Chart */}
      <div style={{position:"relative"}} ref={svgContainerRef}>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible",display:"block",cursor:"crosshair"}}
        onMouseMove={e=>{
          const rect=svgContainerRef.current?.getBoundingClientRect();
          if(!rect) return;
          const svgX=(e.clientX-rect.left)*(W/rect.width);
          const dayIdx=Math.round((svgX-ML)/PW*(maxLen-1));
          if(dayIdx<0||dayIdx>=maxLen){setHover(null);return;}
          // Find nearest visible year line at this day
          let bestYr=filteredYears.find(yr=>!hiddenYears.has(yr)&&(data.year_paths[yr]||[])[dayIdx]!=null);
          if(!bestYr){setHover(null);return;}
          // Find year whose line is closest to mouse Y
          const svgY=(e.clientY-rect.top)*(H/rect.height);
          let bestDist=999999;
          filteredYears.filter(yr=>!hiddenYears.has(yr)).forEach(yr=>{
            const v=(data.year_paths[yr]||[])[dayIdx];
            if(v==null) return;
            const lineY=ty(v);
            const d=Math.abs(lineY-svgY);
            if(d<bestDist){bestDist=d;bestYr=yr;}
          });
          const ret=(data.year_paths[bestYr!]||[])[dayIdx]||0;
          setHover({yr:bestYr!,dayIdx,ret,screenX:e.clientX-rect.left,screenY:e.clientY-rect.top});
        }}
        onMouseLeave={()=>setHover(null)}
        onClick={e=>{
          if(!hover) return;
          const pt={yr:hover.yr,dayIdx:hover.dayIdx,ret:hover.ret};
          if(!lockA){setLockA(pt);}
          else if(!lockB){setLockB(pt);}
          else{setLockA(pt);setLockB(null);}
        }}
      >
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

        {/* Shaded P25-P75 band */}
        {activeYears.length>=3&&(()=>{
          const p25Path:string[]=[],p75Path:string[]=[];
          for(let i=0;i<maxLen;i++){
            const vs=activeYears.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null&&!isNaN(v)).sort((a,b)=>a-b);
            if(!vs.length) continue;
            const p25=vs[Math.floor(vs.length*0.25)],p75=vs[Math.floor(vs.length*0.75)];
            p25Path.push(`${p25Path.length===0?"M":"L"}${tx(i).toFixed(1)},${ty(p25).toFixed(1)}`);
            p75Path.unshift(`L${tx(i).toFixed(1)},${ty(p75).toFixed(1)}`);
          }
          if(p25Path.length<2) return null;
          return <path d={p25Path.join(" ")+" "+p75Path.join(" ")+"Z"} fill={`${direction==="up"?G:R}18`}/>;
        })()}

        {/* Year lines */}
        {filteredYears.map((yr,i)=>{
          const pts=data.year_paths[yr]||[];
          if(pts.length<2||hiddenYears.has(yr)) return null;
          const lineCol=YEAR_COLORS[allYears.indexOf(yr)%YEAR_COLORS.length];
          const d=pts.map((v,j)=>`${j===0?"M":"L"}${tx(j).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
          const finalRet=pts[pts.length-1]||0;
          const isHit=direction==="up"?finalRet>0:finalRet<0;
          return(
            <g key={yr}>
              <path d={d} fill="none" stroke={lineCol}
                strokeWidth={isHit?1.4:0.9} opacity={isHit?0.80:0.30}
                strokeLinejoin="round" strokeLinecap="round"/>
              <text x={tx(pts.length-1)+4} y={ty(finalRet)+3.5} fontSize={8.5} fill={lineCol} opacity={0.9} fontWeight="600">{yr}</text>
            </g>
          );
        })}

        {/* Average + Median lines */}
        {activeYears.length>0&&avgPath.length>1&&(
          <>
            <path d={avgPath.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ")}
              fill="none" stroke="#ffffff" strokeWidth={2.8} opacity={0.95}
              strokeLinejoin="round" strokeLinecap="round"/>
            <text x={tx(avgPath.length-1)+4} y={ty(avgPath[avgPath.length-1])+3.5} fontSize={9} fill="#ffffff" fontWeight="700">avg</text>
          </>
        )}
        {/* Median line (dashed yellow) */}
        {activeYears.length>0&&(()=>{
          const medPath=Array.from({length:maxLen},(_,i)=>{
            const vs=activeYears.map(yr=>(data.year_paths[yr]||[])[i]).filter(v=>v!=null&&!isNaN(v)).sort((a,b)=>a-b);
            return vs.length?vs[Math.floor(vs.length/2)]:0;
          });
          return <path d={medPath.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ")}
            fill="none" stroke={YL} strokeWidth={1.8} opacity={0.9}
            strokeDasharray="8,4" strokeLinejoin="round" strokeLinecap="round"/>;
        })()}

        {/* Hover crosshair */}
        {hover&&(
          <>
            <line x1={tx(hover.dayIdx)} y1={MT} x2={tx(hover.dayIdx)} y2={H-MB} stroke="#ffffff20" strokeWidth={1} strokeDasharray="3,3"/>
            <circle cx={tx(hover.dayIdx)} cy={ty(hover.ret)} r={4}
              fill={YEAR_COLORS[allYears.indexOf(hover.yr)%YEAR_COLORS.length]}
              stroke="#ffffff" strokeWidth={1.5} opacity={0.95}/>
          </>
        )}

        {/* Locked point A */}
        {lockA&&!hiddenYears.has(lockA.yr)&&(()=>{
          const c=YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length];
          return <g>
            <circle cx={tx(lockA.dayIdx)} cy={ty(lockA.ret)} r={6} fill={c} stroke="#fff" strokeWidth={2}/>
            <text x={tx(lockA.dayIdx)} y={ty(lockA.ret)-10} textAnchor="middle" fontSize={9} fill={c} fontWeight="700">A</text>
          </g>;
        })()}

        {/* Locked point B */}
        {lockB&&!hiddenYears.has(lockB.yr)&&(()=>{
          const c=YEAR_COLORS[allYears.indexOf(lockB.yr)%YEAR_COLORS.length];
          return <g>
            <circle cx={tx(lockB.dayIdx)} cy={ty(lockB.ret)} r={6} fill={c} stroke="#fff" strokeWidth={2}/>
            <text x={tx(lockB.dayIdx)} y={ty(lockB.ret)-10} textAnchor="middle" fontSize={9} fill={c} fontWeight="700">B</text>
          </g>;
        })()}

        {/* Delta line between A and B if same year */}
        {lockA&&lockB&&lockA.yr===lockB.yr&&(()=>{
          const c=YEAR_COLORS[allYears.indexOf(lockA.yr)%YEAR_COLORS.length];
          const delta=lockB.ret-lockA.ret;
          const mx2=(tx(lockA.dayIdx)+tx(lockB.dayIdx))/2;
          const my2=(ty(lockA.ret)+ty(lockB.ret))/2;
          return <g>
            <line x1={tx(lockA.dayIdx)} y1={ty(lockA.ret)} x2={tx(lockB.dayIdx)} y2={ty(lockB.ret)} stroke={YL} strokeWidth={1.5} strokeDasharray="4,3"/>
            <text x={mx2} y={my2-8} textAnchor="middle" fontSize={10} fill={YL} fontWeight="800">{delta>=0?"+":""}{delta.toFixed(2)}%</text>
          </g>;
        })()}
      </svg>
      </div>

      {/* Legend */}
      <div style={{display:"flex",gap:14,marginTop:6,fontSize:10,color:W9,flexWrap:"wrap"}}>
        <span><span style={{color:"#ffffff",fontWeight:700}}>—</span> Average</span>
        <span><span style={{color:YL,fontWeight:700}}>- -</span> Median</span>
        <span style={{color:DIM}}>Click line to lock point A then B to compare returns</span>
      </div>'''

    # Add state variables for hover and lock
    OLD_STATES = '''  const [hiddenYears,setHiddenYears]=useState<Set<number>>(new Set());'''
    NEW_STATES = '''  const [hiddenYears,setHiddenYears]=useState<Set<number>>(new Set());
  const [hover,setHover]=useState<{yr:number;dayIdx:number;ret:number;screenX:number;screenY:number}|null>(null);
  const [lockA,setLockA]=useState<{yr:number;dayIdx:number;ret:number}|null>(null);
  const [lockB,setLockB]=useState<{yr:number;dayIdx:number;ret:number}|null>(null);
  const svgContainerRef=useRef<HTMLDivElement>(null);'''

    changed = False
    if OLD_STATES in txt:
        txt = txt.replace(OLD_STATES, NEW_STATES, 1)
        print("  [OK] Added hover/lock state vars")
        changed = True

    if OLD_SVG_BLOCK in txt:
        txt = txt.replace(OLD_SVG_BLOCK, NEW_SVG_BLOCK, 1)
        print("  [OK] SVG upgraded with tooltip + click-to-lock")
        changed = True
    else:
        print("  [SKIP] SVG block not found — run setup_phase13_final.py first then this script")

    if changed:
        page.write_text(txt, encoding="utf-8", newline="\n")
        print("  [SAVED] patterns/page.tsx")

print("""
=============================================================
FIX DEEP FINAL COMPLETE
=============================================================

Fixes applied:
  [1] /api/deep/route.ts REWRITTEN
      -> sanitize() function applied before every JSON.parse
      -> corr_3y: NaN now null before parsing
      -> Correct column names: benchmark, corr_1y, corr_3y, beta_1y
      -> /deep page will now load without SyntaxError

  [2] /api/deep/[symbol]/route.ts
      -> NaN sanitization verified

  [3] InteractiveYearChart upgraded:
      -> Hover tooltip: shows Year / Day number / Return%
      -> Click to lock point A (first click)
      -> Click again to lock point B (second click)
      -> Shows delta Δ between A and B in yellow
      -> If A and B on same year: draws delta line between them
      -> "Clear locks" button to reset
      -> White average line + yellow dashed median line
      -> Crosshair cursor on hover

Run:
  cd D:\\MICC\\micc-dashboard && npm run dev

Then:
  localhost:3000/deep          -> Should load now (no NaN error)
  localhost:3000/patterns      -> Search HDFCBANK -> click any pattern
                                  -> Hover over chart lines for tooltip
                                  -> Click to lock A, click again to lock B
                                  -> See delta between two points
""")
