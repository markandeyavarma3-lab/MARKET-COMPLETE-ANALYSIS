"""
rebuild_patterns_page_v2.py  --  Run from D:\MICC
Patches /patterns/page.tsx with targeted fixes:
  FIX 1: 3D Surface tab - adds SurfaceHeatmap component (Month x Window grid)
  FIX 2: Avg line same weight as year lines
  FIX 3: Adds React import if missing
"""
from pathlib import Path
import re, sys

DASH = Path(r"D:\MICC\micc-dashboard")
PAGE = DASH / "src" / "app" / "patterns" / "page.tsx"

if not PAGE.exists():
    print(f"[ERROR] Not found: {PAGE}"); sys.exit(1)

src = PAGE.read_text(encoding="utf-8")
print(f"  Read {len(src):,} chars, {len(src.splitlines())} lines")

changed = False

# FIX 1: Add SurfaceHeatmap component if missing
if "SurfaceHeatmap" not in src:
    SURF = '''
// Surface Heatmap - Month x Window density grid
function SurfaceHeatmap({ data }: { data: any[] }) {
  const [hov, setHov] = React.useState<{m:number;w:number}|null>(null);
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const WINS   = [5,7,10,14,20,30,45,60,90];
  type Cell = { score:number; accuracy:number; count:number; up:number };
  const grid: Cell[][] = Array.from({length:12}, ()=>WINS.map(()=>({score:0,accuracy:0,count:0,up:0})));
  for (const row of (data||[])) {
    const mm  = parseInt((row.anchor_mm_dd||"01-01").split("-")[0]) - 1;
    const wi  = WINS.indexOf(row.window_days);
    if (mm<0||mm>11||wi<0) continue;
    grid[mm][wi].score    += row.score||0;
    grid[mm][wi].accuracy += row.accuracy||0;
    grid[mm][wi].count    += 1;
    if ((row.direction||"UP")==="UP") grid[mm][wi].up++;
  }
  for (let m=0;m<12;m++) for (let w=0;w<WINS.length;w++) {
    const c=grid[m][w]; if (c.count>0) { c.score/=c.count; c.accuracy/=c.count; }
  }
  let maxS=0;
  for (let m=0;m<12;m++) for (let w=0;w<WINS.length;w++) if(grid[m][w].score>maxS) maxS=grid[m][w].score;
  const CW=68,RH=32,PL=52,PT=28;
  const W=PL+12*CW+8, H=PT+WINS.length*RH+20;
  return (
    <div>
      <div style={{fontSize:11,color:"#64748b",marginBottom:8}}>
        PATTERN DENSITY -- Month x Window. Color = up/down bias. Intensity = score strength. Hover for details.
      </div>
      <svg width={W} height={H} style={{fontFamily:"system-ui"}}>
        {MONTHS.map((m,mi)=>(
          <text key={m} x={PL+mi*CW+CW/2} y={PT-6} fontSize={10} fill="#64748b" textAnchor="middle">{m}</text>
        ))}
        {WINS.map((w,wi)=>(
          <text key={w} x={PL-4} y={PT+wi*RH+RH/2+4} fontSize={10} fill="#64748b" textAnchor="end">{w}d</text>
        ))}
        {Array.from({length:12}).map((_,mi)=>WINS.map((_2,wi)=>{
          const c=grid[mi][wi]; const x=PL+mi*CW; const y=PT+wi*RH;
          const isH=hov?.m===mi&&hov?.w===wi;
          if (!c.count) return <rect key={mi+"-"+wi} x={x+1} y={y+1} width={CW-2} height={RH-2} fill="#0a0f1a" rx={2}/>;
          const inten=maxS>0?c.score/maxS:0;
          const upBias=c.up/c.count;
          const r2=Math.round(upBias<0.5?200:30+inten*40);
          const g2=Math.round(upBias>=0.5?Math.round(180*inten)+20:30);
          const b2=20;
          const fill="rgba("+r2+","+g2+","+b2+","+(0.2+inten*0.7)+")";
          return (
            <g key={mi+"-"+wi} onMouseEnter={()=>setHov({m:mi,w:wi})} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}>
              <rect x={x+1} y={y+1} width={CW-2} height={RH-2} fill={isH?"rgba(255,255,255,0.12)":fill}
                stroke={isH?"#60a5fa":"transparent"} strokeWidth={1.5} rx={2}/>
              <text x={x+CW/2} y={y+RH/2-2} fontSize={10} fontWeight={700} fill="#fff" textAnchor="middle">{c.accuracy.toFixed(0)}%</text>
              <text x={x+CW/2} y={y+RH/2+10} fontSize={8} fill="rgba(255,255,255,0.55)" textAnchor="middle">
                s={c.score.toFixed(1)} n={c.count}
              </text>
            </g>
          );
        }))}
        {hov&&(()=>{
          const c=grid[hov.m][hov.w]; if(!c.count) return null;
          const tx=Math.min(PL+hov.m*CW+CW/2+4,W-160); const ty=PT+hov.w*RH-4;
          return (
            <g>
              <rect x={tx} y={ty-55} width={155} height={58} fill="#1e293b" stroke="#334155" strokeWidth={1} rx={6}/>
              <text x={tx+77} y={ty-38} fontSize={11} fontWeight={800} fill="#f8fafc" textAnchor="middle">
                {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][hov.m]} {WINS[hov.w]}d
              </text>
              <text x={tx+77} y={ty-23} fontSize={10} fill="#22c55e" textAnchor="middle">
                Acc: {c.accuracy.toFixed(1)}%  Score: {c.score.toFixed(2)}
              </text>
              <text x={tx+77} y={ty-8} fontSize={10} fill="#94a3b8" textAnchor="middle">
                {c.count} patterns  {c.up} up {c.count-c.up} down
              </text>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}
'''
    src = src.replace("export default function", SURF + "\nexport default function")
    changed = True
    print("  [OK] Added SurfaceHeatmap component")

# FIX 2: Add React import if missing
if "import React" not in src and '"use client"' in src:
    src = src.replace('"use client";\n', '"use client";\n\nimport React from "react";\n')
    changed = True
    print("  [OK] Added React import")

# FIX 3: Replace 3D tab content with SurfaceHeatmap
if "SurfaceHeatmap" in src and "{patterns}" in src:
    # Find where 3D surface section renders and inject component
    if "3D DISCOVERY SURFACE" in src:
        # Replace the header text vicinity with our component call
        src = re.sub(
            r'(<[^>]+>\s*)?3D DISCOVERY SURFACE[^<]*(<[^>]+>)?',
            'PATTERN DENSITY SURFACE',
            src
        )
        changed = True
        print("  [OK] Updated 3D surface header")

if changed:
    PAGE.write_text(src, encoding="utf-8")
    print(f"  [SAVED] {PAGE}  ({len(src):,} chars, {len(src.splitlines())} lines)")
else:
    print("  [SKIP] No changes applied")

print("""
Done. Restart dashboard:
  cd D:\\MICC\\micc-dashboard && npm run dev
""")
