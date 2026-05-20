# -*- coding: utf-8 -*-
"""
fix_phase10c.py  --  Run from D:\\MICC
Fixes all issues + builds the core Historical Accuracy feature.
Run: py D:\\MICC\\fix_phase10c.py
"""

from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
SRC  = DASH / "src"
APP  = SRC / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# [1] Fix /api/analysis/route.ts
# =============================================================================
print("\n[1/3] Rewriting /api/analysis/route.ts...")

write(APP / "api" / "analysis" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 30000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[analysis]', r.stderr?.slice(0,400)); return [] }
    const out = r.stdout.trim()
    if (!out) return []
    return JSON.parse(out.replace(/:\s*NaN\b/g,': null').replace(/:\s*Infinity\b/g,': null').replace(/:\s*-Infinity\b/g,': null'))
  } catch(e) { console.error('[analysis]', String(e)); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const sym = (searchParams.get('symbol') || '').toUpperCase().trim()
  if (!sym) return NextResponse.json({ ok: false, error: 'No symbol' }, { status: 400 })

  const chk = qdb(`SELECT asset_type FROM window_stats WHERE symbol=? LIMIT 1`, [sym])
  const detectedType = chk.length > 0 ? (chk[0] as Record<string,unknown>).asset_type as string : 'stock'

  const windowStats = qdb(`
    SELECT window_days, n_windows, first_date, last_date,
           mean_return, median_return, std_return, min_return, max_return,
           p5, p25, p75, p95,
           prob_positive, prob_gt5, prob_gt10, prob_gt20,
           prob_lt_neg5, prob_lt_neg10, prob_lt_neg20,
           ann_return_equiv, sharpe_ratio
    FROM window_stats WHERE symbol=? ORDER BY window_days
  `, [sym])

  if (!windowStats.length) {
    return NextResponse.json({ ok: false, error: `No data for: ${sym}` }, { status: 404 })
  }

  const extremesUp   = qdb(`SELECT window_days,rank_n,start_date,end_date,return_pct FROM window_extremes WHERE symbol=? AND direction='up'   ORDER BY window_days,rank_n`, [sym])
  const extremesDown = qdb(`SELECT window_days,rank_n,start_date,end_date,return_pct FROM window_extremes WHERE symbol=? AND direction='down' ORDER BY window_days,rank_n`, [sym])

  const seriesStats  = qdb(`SELECT cagr_pct,ann_volatility_pct,max_drawdown_pct,sharpe_ratio,sortino_ratio,calmar_ratio,n_trading_days,mdd_start_date,mdd_trough_date,mdd_recovery_days FROM symbol_series_stats WHERE symbol=? LIMIT 1`, [sym])
  const technicals   = qdb(`SELECT atr_14_pct,adx_14,pct_above_sma20,vol_surge_20d,rsi_14,macd_line,macd_signal,bb_pct,as_of_date FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1`, [sym])
  const seasonality  = qdb(`SELECT period_value,n_obs,mean_return_pct,median_return_pct FROM symbol_seasonality WHERE symbol=? AND period_type='month' ORDER BY period_value`, [sym])
  const regimeStats  = qdb(`SELECT window_days,regime,n_windows,mean_return,std_return,prob_positive,p5,p95 FROM window_regime_stats WHERE symbol=? ORDER BY window_days,regime`, [sym])
  const correlations = qdb(`SELECT symbol_b,correlation_20d,correlation_60d,beta_20d FROM symbol_correlations WHERE symbol_a=? ORDER BY ABS(COALESCE(correlation_20d,0)) DESC LIMIT 15`, [sym])

  const priceRow = detectedType === 'stock'
    ? qdb(`SELECT close,date,volume,high,low FROM stock_data WHERE symbol=? ORDER BY date DESC LIMIT 1`, [sym])
    : qdb(`SELECT close,date FROM market_snapshot WHERE index_name=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1`, [sym])

  const priceHistRaw = detectedType === 'stock'
    ? qdb(`SELECT date,close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 252`, [sym])
    : qdb(`SELECT date,close FROM market_snapshot WHERE index_name=? AND close IS NOT NULL ORDER BY date DESC LIMIT 252`, [sym])

  const insider = detectedType === 'stock'
    ? qdb(`SELECT filing_date,name,transaction_type,quantity,price,value FROM insider_trading WHERE symbol=? AND transaction_type IN ('BUY','SELL') ORDER BY filing_date DESC LIMIT 10`, [sym])
    : []

  const announcements = qdb(`SELECT announcement_date,subject FROM corporate_announcements WHERE symbol=? ORDER BY announcement_date DESC LIMIT 10`, [sym])

  const rankRow = qdb(`SELECT COUNT(*) as total, SUM(CASE WHEN prob_positive < (SELECT prob_positive FROM window_stats WHERE symbol=? AND window_days=20) THEN 1 ELSE 0 END) as below_me FROM window_stats WHERE window_days=20 AND asset_type=?`, [sym, detectedType])

  return NextResponse.json({
    ok: true, symbol: sym, asset_type: detectedType,
    window_stats: windowStats, extremes_up: extremesUp, extremes_down: extremesDown,
    series_stats: seriesStats[0] || null, technicals: technicals[0] || null,
    seasonality, regime_stats: regimeStats, correlations,
    latest_price: priceRow[0] || null,
    price_history: (priceHistRaw as Record<string,unknown>[]).reverse(),
    insider_trades: insider, announcements,
    rank: rankRow[0] || null,
  })
}
""")

# =============================================================================
# [2] NaN patch all other route.ts files
# =============================================================================
print("\n[2/3] NaN-patching all API route.ts files...")
patched = 0
for rf in (APP / "api").rglob("route.ts"):
    txt = rf.read_text(encoding="utf-8")
    old = "return out ? JSON.parse(out) : []"
    new_s = "return out ? JSON.parse(out.replace(/:\\s*NaN\\b/g,': null').replace(/:\\s*Infinity\\b/g,': null').replace(/:\\s*-Infinity\\b/g,': null')) : []"
    if old in txt and new_s not in txt:
        rf.write_text(txt.replace(old, new_s), encoding="utf-8", newline="\n")
        print(f"  [NaN] {rf.relative_to(BASE)}")
        patched += 1
print(f"  Patched {patched} files")

# =============================================================================
# [3] Rewrite /analysis/page.tsx
# =============================================================================
print("\n[3/3] Rewriting /analysis/page.tsx...")

write(APP / "analysis" / "page.tsx", r"""
"use client";
import React, { useState, useCallback, useRef, useEffect } from "react";

interface WS { window_days:number;n_windows:number;first_date:string;last_date:string;mean_return:number;median_return:number;std_return:number;min_return:number;max_return:number;p5:number;p25:number;p75:number;p95:number;prob_positive:number;prob_gt5:number;prob_gt10:number;prob_gt20:number;prob_lt_neg5:number;prob_lt_neg10:number;prob_lt_neg20:number;ann_return_equiv:number;sharpe_ratio:number; }
interface Ex { window_days:number;rank_n:number;start_date:string;end_date:string;return_pct:number; }
interface SS { cagr_pct:number;ann_volatility_pct:number;max_drawdown_pct:number;sharpe_ratio:number;sortino_ratio:number;calmar_ratio:number;n_trading_days:number;mdd_start_date:string;mdd_trough_date:string;mdd_recovery_days:number; }
interface Tech { rsi_14:number;adx_14:number;pct_above_sma20:number;vol_surge_20d:number;macd_line:number;macd_signal:number;bb_pct:number;atr_14_pct:number;as_of_date:string; }
interface Sea { period_value:number;n_obs:number;mean_return_pct:number;median_return_pct:number; }
interface Reg { window_days:number;regime:string;n_windows:number;mean_return:number;std_return:number;prob_positive:number;p5:number;p95:number; }
interface Cor { symbol_b:string;correlation_20d:number;correlation_60d:number;beta_20d:number; }
interface PH  { date:string;close:number; }
interface Ins { filing_date:string;name:string;transaction_type:string;quantity:number;price:number;value:number; }
interface Ann { announcement_date:string;subject:string; }
interface AData { ok:boolean;error?:string;symbol:string;asset_type:string;window_stats:WS[];extremes_up:Ex[];extremes_down:Ex[];series_stats:SS|null;technicals:Tech|null;seasonality:Sea[];regime_stats:Reg[];correlations:Cor[];latest_price:{close:number;date:string;volume:number}|null;price_history:PH[];insider_trades:Ins[];announcements:Ann[];rank:{total:number;below_me:number}|null; }
interface CData { ok:boolean;error?:string;symbols:string[];window_stats:{symbol:string;window_days:number;mean_return:number;std_return:number;p5:number;p95:number;prob_positive:number;prob_gt10:number;sharpe_ratio:number}[];series_stats:{symbol:string;cagr_pct:number;ann_volatility_pct:number;max_drawdown_pct:number;sharpe_ratio:number;sortino_ratio:number;calmar_ratio:number}[];technicals:{symbol:string;rsi_14:number;adx_14:number;pct_above_sma20:number;vol_surge_20d:number;macd_line:number;macd_signal:number;bb_pct:number;atr_14_pct:number}[];seasonality:{symbol:string;period_value:number;mean_return_pct:number}[];cross_correlations:{symbol_a:string;symbol_b:string;correlation_20d:number;beta_20d:number}[];prices:{symbol:string;close:number;date:string}[]; }
interface Sug { symbol:string;name:string;sector:string;type:string; }

const DW=[3,5,7,10,15,20,30,45,60,90,120,180,252,504,756];
const MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const SC=["#22d3ee","#4ade80","#facc15","#f97316","#a855f7"];
const G="#4ade80",R="#f87171",CY="#22d3ee",YL="#facc15",OR="#f97316";
const DIM="var(--text-tertiary)",PRI="var(--text-primary)",BOR="var(--border-color)",SUR="var(--surface-card)";
const W9="#94a3b8",WHT="#e2e8f0";

const pct=(v:unknown,d=1)=>v==null?"--":`${(+(v as number))>=0?"+":""}${(+(v as number)).toFixed(d)}%`;
const num=(v:unknown,d=2)=>v==null?"--":(+(v as number)).toFixed(d);
const col=(v:unknown)=>(+(v as number)??0)>=0?G:R;
const fd=(s:string)=>s?.slice(0,10)||"--";
function wL(d:number){const m:Record<number,string>={1:"1D",2:"2D",3:"3D",5:"5D",7:"7D",10:"2W",15:"3W",20:"1M",30:"6W",45:"2M",60:"3M",90:"4M",120:"6M",180:"9M",252:"1Y",504:"2Y",756:"3Y"};return m[d]||`${d}D`;}

// ── Autocomplete Input (works for all 4 modes) ─────────────────────────────
function AInput({value,onChange,onSelect,placeholder,stype,autoFocus,multi}:{
  value:string;onChange:(v:string)=>void;onSelect:(s:string)=>void;
  placeholder:string;stype:"stock"|"index";autoFocus?:boolean;multi?:boolean;
}){
  const [sugg,setSugg]=useState<Sug[]>([]);
  const [show,setShow]=useState(false);
  const [hi,setHi]=useState(-1);
  const tmr=useRef<ReturnType<typeof setTimeout>|null>(null);

  const getQ=(v:string)=>multi?v.split(",").pop()?.trim()||"":v.trim();

  const fetch_=useCallback(async(q:string)=>{
    if(q.length<1){setSugg([]);return;}
    try{
      const r=await fetch(`/api/search?q=${encodeURIComponent(q.toUpperCase())}&type=${stype}`,{cache:"no-store"});
      const d=await r.json();
      setSugg(d.results||[]);setShow(true);
    }catch{setSugg([]);}
  },[stype]);

  const change=(v:string)=>{
    onChange(v);setHi(-1);
    const q=getQ(v);
    if(tmr.current)clearTimeout(tmr.current);
    tmr.current=setTimeout(()=>fetch_(q),180);
  };

  const pick=(sym:string)=>{
    if(multi){
      const parts=value.split(",").map(s=>s.trim()).filter(Boolean);
      parts[Math.max(0,parts.length-1)]=sym;
      onChange(parts.join(", ")+", ");
    }else{onChange(sym);onSelect(sym);}
    setShow(false);setSugg([]);setHi(-1);
  };

  const onKey=(e:React.KeyboardEvent)=>{
    if(e.key==="ArrowDown"){e.preventDefault();setHi(i=>Math.min(i+1,sugg.length-1));}
    else if(e.key==="ArrowUp"){e.preventDefault();setHi(i=>Math.max(i-1,-1));}
    else if(e.key==="Enter"){e.preventDefault();if(hi>=0&&sugg[hi])pick(sugg[hi].symbol);else{onSelect(value);setShow(false);}}
    else if(e.key==="Escape")setShow(false);
  };

  const tc:Record<string,string>={stock:CY,index:G,global:YL};

  return(
    <div style={{position:"relative",flex:1}}>
      <input value={value} onChange={e=>change(e.target.value.toUpperCase())}
        onKeyDown={onKey} onBlur={()=>setTimeout(()=>setShow(false),200)}
        placeholder={placeholder} autoFocus={autoFocus}
        style={{width:"100%",background:SUR,border:`1px solid ${BOR}`,color:PRI,
          borderRadius:show&&sugg.length>0?"8px 8px 0 0":"8px",
          padding:"12px 16px",fontSize:14,boxSizing:"border-box"}}
      />
      {show&&sugg.length>0&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,
          background:"#0d1520",border:`1px solid ${BOR}`,borderTop:"none",
          borderRadius:"0 0 8px 8px",maxHeight:300,overflowY:"auto",
          boxShadow:"0 8px 32px rgba(0,0,0,0.7)"}}>
          {sugg.map((s,i)=>(
            <div key={s.symbol} onMouseDown={()=>pick(s.symbol)} style={{
              padding:"9px 14px",cursor:"pointer",display:"flex",alignItems:"center",gap:10,
              background:i===hi?`${CY}18`:"transparent",
              borderBottom:i<sugg.length-1?`1px solid ${BOR}22`:"none"}}>
              <span style={{color:tc[s.type]||CY,fontWeight:800,fontSize:13,minWidth:90,fontFamily:"monospace"}}>{s.symbol}</span>
              <span style={{color:WHT,fontSize:12,flex:1}}>{s.name!==s.symbol?s.name:""}</span>
              {s.sector&&<span style={{color:W9,fontSize:10}}>{s.sector}</span>}
              <span style={{fontSize:9,fontWeight:700,color:tc[s.type]||CY,opacity:0.7}}>{s.type.toUpperCase()}</span>
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

function SBox({label,value,color,sub}:{label:string;value:string;color?:string;sub?:string}){
  return(
    <div style={{background:`${BOR}22`,borderRadius:6,padding:"10px 12px",minWidth:88}}>
      <div style={{fontSize:9,color:DIM,fontWeight:700,letterSpacing:1,textTransform:"uppercase",marginBottom:3}}>{label}</div>
      <div style={{fontSize:16,fontWeight:800,color:color||PRI}}>{value}</div>
      {sub&&<div style={{fontSize:10,color:DIM,marginTop:2}}>{sub}</div>}
    </div>
  );
}

// ── Sparkline ─────────────────────────────────────────────────────────────
function Spark({data}:{data:PH[]}){
  if(!data||data.length<2)return null;
  const pr=data.map(d=>d.close),mn=Math.min(...pr),mx=Math.max(...pr),rng=mx-mn||1;
  const W=600,H=56;
  const pts=pr.map((p,i)=>`${(i/(pr.length-1))*W},${H-((p-mn)/rng)*H}`).join(" ");
  const lc=pr[pr.length-1]>=pr[0]?G:R;
  return(
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{borderRadius:4}}>
      <polyline points={pts} fill="none" stroke={lc} strokeWidth={1.8} vectorEffect="non-scaling-stroke"/>
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// THE CORE FEATURE: HISTORICAL ACCURACY
// "20D window: 85% accurate -- 17 out of 20 years went UP"
// ═══════════════════════════════════════════════════════════════════════════
function HistAcc({stats,eu,ed}:{stats:WS[];eu:Ex[];ed:Ex[]}){
  const [dn,setDn]=useState(false);
  const filtered=stats.filter(s=>DW.includes(s.window_days)&&s.n_windows>=8);

  const rows=(goDown:boolean)=>filtered.map(s=>{
    const pp=goDown?(1-(s.prob_positive||0)):(s.prob_positive||0);
    const hits=Math.round(pp*s.n_windows);
    const best=(goDown?ed:eu).filter(e=>e.window_days===s.window_days)[0]||null;
    return{window_days:s.window_days,hits,n:s.n_windows,pct_v:pp*100,mean:s.mean_return,p5:s.p5,p95:s.p95,std:s.std_return,best};
  }).filter(r=>r.pct_v>=70).sort((a,b)=>b.pct_v-a.pct_v);

  const R_=rows(dn),dir=dn?"DOWN":"UP",AC=dn?R:G;

  return(
    <div>
      <div style={{display:"flex",gap:10,marginBottom:14,alignItems:"center",flexWrap:"wrap"}}>
        <span style={{fontSize:12,color:DIM}}>Show windows where stock historically goes:</span>
        <button onClick={()=>setDn(false)} style={{padding:"5px 14px",borderRadius:4,fontSize:12,fontWeight:700,border:"none",cursor:"pointer",background:!dn?G:"transparent",color:!dn?"#000":DIM}}>UP (Bull)</button>
        <button onClick={()=>setDn(true)}  style={{padding:"5px 14px",borderRadius:4,fontSize:12,fontWeight:700,border:"none",cursor:"pointer",background:dn?R:"transparent",color:dn?"#fff":DIM}}>DOWN (Bear)</button>
        <span style={{fontSize:11,color:DIM}}>Accuracy threshold: 70%</span>
      </div>

      {R_.length===0?(
        <div style={{color:DIM,fontSize:13,padding:"20px 0",textAlign:"center"}}>
          No windows with {">"}70% {dir} accuracy found. This asset has mixed directional behavior across all windows.
        </div>
      ):(
        <>
          <div style={{marginBottom:12,fontSize:13}}>
            Found <span style={{color:AC,fontWeight:700}}>{R_.length} windows</span> with {">"}70% historical {dir} accuracy:
          </div>
          {R_.map(row=>{
            const cLabel=row.pct_v>=90?"VERY HIGH":row.pct_v>=80?"HIGH":"GOOD";
            const cColor=row.pct_v>=90?G:row.pct_v>=80?"#4ade80bb":YL;
            return(
              <div key={row.window_days} style={{marginBottom:10,padding:"14px 16px",background:`${AC}0c`,border:`1px solid ${AC}2a`,borderRadius:8,borderLeft:`4px solid ${AC}`}}>
                <div style={{display:"flex",alignItems:"center",gap:14,marginBottom:8,flexWrap:"wrap"}}>
                  <span style={{fontWeight:900,fontSize:20,color:WHT,minWidth:48}}>{wL(row.window_days)}</span>
                  <div style={{flex:1}}>
                    <div style={{display:"flex",alignItems:"baseline",gap:8}}>
                      <span style={{fontWeight:900,fontSize:22,color:cColor}}>{row.pct_v.toFixed(0)}%</span>
                      <span style={{fontSize:12,color:DIM}}>accurate</span>
                      <span style={{fontSize:13,color:WHT,fontWeight:600}}>({row.hits}/{row.n} periods went {dir})</span>
                    </div>
                    <div style={{height:6,background:`${BOR}33`,borderRadius:3,marginTop:5,maxWidth:360}}>
                      <div style={{height:6,width:`${Math.min(100,row.pct_v)}%`,background:AC,borderRadius:3,transition:"width 0.5s"}}/>
                    </div>
                  </div>
                  <span style={{fontSize:10,fontWeight:700,padding:"2px 8px",borderRadius:3,background:`${cColor}22`,color:cColor,letterSpacing:1}}>{cLabel}</span>
                </div>
                <div style={{display:"flex",gap:16,flexWrap:"wrap",fontSize:12}}>
                  <span><span style={{color:DIM}}>Avg move: </span><span style={{color:col(row.mean),fontWeight:700}}>{pct(row.mean)}</span></span>
                  <span><span style={{color:DIM}}>Range: </span><span style={{color:R}}>{pct(row.p5)}</span><span style={{color:DIM}}> to </span><span style={{color:G}}>{pct(row.p95)}</span></span>
                  <span><span style={{color:DIM}}>Std: </span><span style={{color:WHT}}>{pct(row.std)}</span></span>
                  {row.best&&<span><span style={{color:DIM}}>{dn?"Worst":"Best"} episode: </span><span style={{color:dn?R:G,fontWeight:700}}>{pct(row.best.return_pct)}</span><span style={{color:DIM,fontSize:11}}> ({fd(row.best.start_date)} to {fd(row.best.end_date)})</span></span>}
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}

// ── Prob Heatmap ──────────────────────────────────────────────────────────
function PHmap({stats}:{stats:WS[]}){
  const f=stats.filter(s=>DW.includes(s.window_days));
  const M=[{k:"prob_positive",l:"Prob UP"},{k:"prob_gt5",l:">+5%"},{k:"prob_gt10",l:">+10%"},{k:"prob_gt20",l:">+20%"},{k:"prob_lt_neg5",l:"<-5%"},{k:"prob_lt_neg10",l:"<-10%"}] as const;
  const bg=(k:string,v:number)=>{const p=(v||0)*100;if(k.startsWith("prob_lt"))return p>30?"#f87171cc":p>20?"#f97316aa":p>10?"#facc1544":"#4ade8033";return p>65?"#4ade80cc":p>55?"#4ade8055":p>45?"#facc1533":"#f8717133";};
  return(
    <div style={{overflowX:"auto"}}>
      <table style={{borderCollapse:"collapse",fontSize:11,width:"100%"}}>
        <thead><tr>
          <th style={{padding:"5px 10px",textAlign:"left",color:W9,fontWeight:600,fontSize:10}}>Window</th>
          {M.map(m=><th key={m.k} style={{padding:"5px 8px",textAlign:"center",color:W9,fontWeight:600,fontSize:10,whiteSpace:"nowrap"}}>{m.l}</th>)}
        </tr></thead>
        <tbody>{f.map(s=>(
          <tr key={s.window_days}>
            <td style={{padding:"4px 10px",fontWeight:700,color:WHT}}>{wL(s.window_days)}</td>
            {M.map(m=>{const v=(s[m.k as keyof WS] as number)||0;return(
              <td key={m.k} style={{padding:"3px 5px",textAlign:"center"}}>
                <div style={{background:bg(m.k,v),borderRadius:4,padding:"3px 6px",fontWeight:700,color:"#fff",fontSize:11}}>{((v||0)*100).toFixed(0)}%</div>
              </td>
            );})}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

// ── Percentile Fan (FIXED: visible axis labels) ───────────────────────────
function PFan({stats}:{stats:WS[]}){
  const f=stats.filter(s=>DW.includes(s.window_days)).sort((a,b)=>a.window_days-b.window_days);
  if(f.length<2)return null;
  const av=f.flatMap(s=>[s.p5,s.p95,s.mean_return]).filter(v=>v!=null&&!isNaN(v));
  const gMn=Math.min(...av,-5),gMx=Math.max(...av,5),rng=gMx-gMn;
  const W=560,H=160,ML=44,MR=20,MT=10,MB=28;
  const PW=W-ML-MR,PH=H-MT-MB;
  const tx=(i:number)=>ML+(i/(f.length-1))*PW;
  const ty=(v:number)=>MT+PH-((v-gMn)/rng)*PH;
  const mk=(vals:number[])=>vals.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
  const area=(top:number[],bot:number[])=>{
    const a=top.map((v,i)=>`${i===0?"M":"L"}${tx(i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
    const b=[...bot].reverse().map((v,i)=>`L${tx(bot.length-1-i).toFixed(1)},${ty(v).toFixed(1)}`).join(" ");
    return`${a} ${b} Z`;
  };
  const p95v=f.map(s=>s.p95),p75v=f.map(s=>s.p75),mv=f.map(s=>s.mean_return),p25v=f.map(s=>s.p25),p5v=f.map(s=>s.p5);
  const z0=ty(0);
  const step=Math.ceil((gMx-gMn)/5/5)*5||5;
  const ticks:number[]=[];
  for(let t=Math.ceil(gMn/step)*step;t<=gMx;t+=step)ticks.push(t);
  return(
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        {ticks.map(t=>(
          <g key={t}>
            <line x1={ML} y1={ty(t)} x2={W-MR} y2={ty(t)} stroke="#ffffff18" strokeWidth={1}/>
            <text x={ML-4} y={ty(t)+4} textAnchor="end" fontSize={9} fill={W9}>{t}%</text>
          </g>
        ))}
        <line x1={ML} y1={z0} x2={W-MR} y2={z0} stroke="#ffffff40" strokeDasharray="4,3" strokeWidth={1}/>
        <path d={area(p95v,p5v)} fill={`${CY}12`}/>
        <path d={area(p75v,p25v)} fill={`${CY}28`}/>
        <path d={mk(p95v)} fill="none" stroke={`${CY}66`} strokeWidth={1} strokeDasharray="4,3"/>
        <path d={mk(p5v)}  fill="none" stroke={`${R}66`}  strokeWidth={1} strokeDasharray="4,3"/>
        <path d={mk(p75v)} fill="none" stroke={`${G}aa`}  strokeWidth={1.2}/>
        <path d={mk(p25v)} fill="none" stroke={`${OR}aa`} strokeWidth={1.2}/>
        <path d={mk(mv)}   fill="none" stroke={CY}         strokeWidth={2.2}/>
        {f.map((s,i)=><text key={s.window_days} x={tx(i)} y={H-2} textAnchor="middle" fontSize={9} fill={W9}>{wL(s.window_days)}</text>)}
        <line x1={ML} y1={H-MB} x2={W-MR} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
      </svg>
      <div style={{display:"flex",gap:14,fontSize:10,color:W9,marginTop:4,flexWrap:"wrap"}}>
        {[[CY,"Mean"],[G,"P75"],[OR,"P25"],[`${CY}66`,"P95"],[`${R}66`,"P5"]].map(([c,l])=>(
          <span key={l}><span style={{color:c as string,fontWeight:700}}>--</span> {l}</span>
        ))}
      </div>
    </div>
  );
}

// ── Episodes ──────────────────────────────────────────────────────────────
function Eps({eu,ed,sw,setSw}:{eu:Ex[];ed:Ex[];sw:number;setSw:(d:number)=>void}){
  const uw=eu.filter(e=>e.window_days===sw),dw=ed.filter(e=>e.window_days===sw);
  const bm=Math.max(...uw.map(e=>Math.abs(e.return_pct)),...dw.map(e=>Math.abs(e.return_pct)),1);
  const avail=DW.filter(d=>eu.some(e=>e.window_days===d)||ed.some(e=>e.window_days===d));
  return(
    <div>
      <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:12}}>
        {avail.map(d=><button key={d} onClick={()=>setSw(d)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"1px solid",background:sw===d?CY:"transparent",color:sw===d?"#000":DIM,borderColor:sw===d?CY:BOR}}>{wL(d)}</button>)}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
        <div>
          <div style={{fontSize:11,fontWeight:700,color:G,letterSpacing:1.2,textTransform:"uppercase",marginBottom:8}}>Top Rallies ({wL(sw)})</div>
          {uw.length===0&&<div style={{color:DIM,fontSize:12}}>No data</div>}
          {uw.map((e,i)=>{const b=(Math.abs(e.return_pct)/bm)*100;return(
            <div key={i} style={{marginBottom:8,padding:"10px 12px",background:`${G}11`,borderRadius:6,borderLeft:`3px solid ${G}`}}>
              <div style={{display:"flex",justifyContent:"space-between",marginBottom:3}}><span style={{fontSize:10,color:DIM}}>#{i+1}</span><span style={{fontWeight:800,fontSize:15,color:G}}>{pct(e.return_pct)}</span></div>
              <div style={{height:4,background:`${BOR}33`,borderRadius:2,marginBottom:4}}><div style={{height:4,width:`${b}%`,background:G,borderRadius:2}}/></div>
              <div style={{fontSize:11,color:DIM}}>{fd(e.start_date)} to {fd(e.end_date)}</div>
            </div>
          );})}
        </div>
        <div>
          <div style={{fontSize:11,fontWeight:700,color:R,letterSpacing:1.2,textTransform:"uppercase",marginBottom:8}}>Worst Crashes ({wL(sw)})</div>
          {dw.length===0&&<div style={{color:DIM,fontSize:12}}>No data</div>}
          {dw.map((e,i)=>{const b=(Math.abs(e.return_pct)/bm)*100;return(
            <div key={i} style={{marginBottom:8,padding:"10px 12px",background:`${R}11`,borderRadius:6,borderLeft:`3px solid ${R}`}}>
              <div style={{display:"flex",justifyContent:"space-between",marginBottom:3}}><span style={{fontSize:10,color:DIM}}>#{i+1}</span><span style={{fontWeight:800,fontSize:15,color:R}}>{pct(e.return_pct)}</span></div>
              <div style={{height:4,background:`${BOR}33`,borderRadius:2,marginBottom:4}}><div style={{height:4,width:`${b}%`,background:R,borderRadius:2}}/></div>
              <div style={{fontSize:11,color:DIM}}>{fd(e.start_date)} to {fd(e.end_date)}</div>
            </div>
          );})}
        </div>
      </div>
    </div>
  );
}

// ── Seasonality chart ─────────────────────────────────────────────────────
function SeaChart({data}:{data:Sea[]}){
  if(!data.length)return <div style={{color:DIM,fontSize:12}}>No data</div>;
  const mx=Math.max(...data.map(r=>Math.abs(r.mean_return_pct||0)),1);
  const W=560,H=120,PAD=22;
  return(
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H+PAD}`} style={{overflow:"visible"}}>
        <line x1={0} y1={H/2} x2={W} y2={H/2} stroke="#ffffff25" strokeWidth={1}/>
        {data.map((r,i)=>{
          const h=Math.max(2,(Math.abs(r.mean_return_pct||0)/mx)*(H/2-6));
          const pos=(r.mean_return_pct||0)>=0;
          const bw=Math.floor(W/data.length)-3;
          const x=i*(W/data.length)+(W/data.length-bw)/2;
          const y=pos?(H/2-h):(H/2);
          return(
            <g key={r.period_value}>
              <rect x={x} y={y} width={bw} height={h} fill={pos?G:R} opacity={0.8} rx={2}/>
              <text x={x+bw/2} y={H+PAD-2} textAnchor="middle" fontSize={9} fill={W9}>{MON[r.period_value-1].slice(0,3)}</text>
              <text x={x+bw/2} y={pos?y-3:y+h+9} textAnchor="middle" fontSize={8} fill={pos?G:R} fontWeight="bold">{pct(r.mean_return_pct,1)}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── Window table ──────────────────────────────────────────────────────────
function WTable({stats}:{stats:WS[]}){
  const sorted=[...stats].filter(s=>DW.includes(s.window_days)).sort((a,b)=>b.prob_positive-a.prob_positive);
  return(
    <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
        <thead><tr style={{background:`${BOR}22`}}>{["Window","N","Prob UP","Avg","P5","P95","Std","Best","Worst","Sharpe","Signal"].map(h=><th key={h} style={{padding:"6px 10px",textAlign:h==="Window"?"left":"right",color:W9,fontWeight:600,fontSize:10,borderBottom:`1px solid ${BOR}`,whiteSpace:"nowrap"}}>{h}</th>)}</tr></thead>
        <tbody>{sorted.map(s=>{const pp=(s.prob_positive||0)*100;return(
          <tr key={s.window_days} style={{borderBottom:`1px solid ${BOR}22`}}>
            <td style={{padding:"7px 10px",fontWeight:700,color:WHT}}>{wL(s.window_days)}</td>
            <td style={{padding:"7px 10px",textAlign:"right",color:DIM}}>{s.n_windows}</td>
            <td style={{padding:"7px 10px",textAlign:"right"}}><span style={{color:pp>=60?G:pp>=50?YL:R,fontWeight:700}}>{pp.toFixed(0)}%</span></td>
            <td style={{padding:"7px 10px",textAlign:"right",color:col(s.mean_return),fontWeight:600}}>{pct(s.mean_return)}</td>
            <td style={{padding:"7px 10px",textAlign:"right",color:col(s.p5)}}>{pct(s.p5)}</td>
            <td style={{padding:"7px 10px",textAlign:"right",color:CY}}>{pct(s.p95)}</td>
            <td style={{padding:"7px 10px",textAlign:"right",color:DIM}}>{pct(s.std_return)}</td>
            <td style={{padding:"7px 10px",textAlign:"right",color:G,fontWeight:600}}>{pct(s.max_return)}</td>
            <td style={{padding:"7px 10px",textAlign:"right",color:R,fontWeight:600}}>{pct(s.min_return)}</td>
            <td style={{padding:"7px 10px",textAlign:"right",color:CY}}>{num(s.sharpe_ratio)}</td>
            <td style={{padding:"7px 10px",textAlign:"right"}}>
              <span style={{fontSize:10,padding:"2px 6px",borderRadius:3,background:pp>=65?`${G}22`:pp>=55?`${YL}22`:`${R}22`,color:pp>=65?G:pp>=55?YL:R,fontWeight:700}}>{pp>=65?"STRONG":pp>=55?"GOOD":pp>=45?"NEUTRAL":"WEAK"}</span>
            </td>
          </tr>
        );})}</tbody>
      </table>
    </div>
  );
}

// ── Compare helpers ───────────────────────────────────────────────────────
function PFanCmp({data,syms}:{data:CData;syms:string[]}){
  return(
    <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
        <thead>
          <tr style={{background:`${BOR}22`}}>
            <th style={{padding:"5px 10px",textAlign:"left",color:W9,fontWeight:600,fontSize:10}}>Window</th>
            {syms.map((s,i)=><th key={s} colSpan={4} style={{padding:"5px 10px",textAlign:"center",color:SC[i],fontWeight:700,fontSize:10,borderLeft:`1px solid ${BOR}`}}>{s}</th>)}
          </tr>
          <tr>
            <th style={{padding:"3px 10px"}}></th>
            {syms.map(s=>["Mean","P5","P95","Prob+"].map(h=><th key={`${s}${h}`} style={{padding:"3px 6px",textAlign:"right",color:W9,fontSize:9,fontWeight:600}}>{h}</th>))}
          </tr>
        </thead>
        <tbody>{DW.map(wd=>(
          <tr key={wd} style={{borderBottom:`1px solid ${BOR}22`}}>
            <td style={{padding:"5px 10px",fontWeight:700,color:WHT}}>{wL(wd)}</td>
            {syms.map((s,si)=>{
              const w=data.window_stats.find(x=>x.symbol===s&&x.window_days===wd);
              const pp=(w?.prob_positive||0)*100;
              return(<React.Fragment key={s}>
                <td style={{padding:"5px 6px",textAlign:"right",color:col(w?.mean_return),fontWeight:600,borderLeft:`1px solid ${BOR}22`}}>{pct(w?.mean_return)}</td>
                <td style={{padding:"5px 6px",textAlign:"right",color:R}}>{pct(w?.p5)}</td>
                <td style={{padding:"5px 6px",textAlign:"right",color:CY}}>{pct(w?.p95)}</td>
                <td style={{padding:"5px 6px",textAlign:"right",color:pp>=55?G:pp>=45?YL:R,fontWeight:700}}>{pp.toFixed(0)}%</td>
              </React.Fragment>);
            })}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Scatter({data,syms}:{data:CData;syms:string[]}){
  const pts=syms.map((s,i)=>{const w=data.window_stats.find(x=>x.symbol===s&&x.window_days===20);return w?{sym:s,x:w.std_return,y:w.mean_return,c:SC[i]}:null;}).filter(Boolean) as {sym:string;x:number;y:number;c:string}[];
  if(!pts.length)return null;
  const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);
  const xMn=Math.min(...xs)*0.8,xMx=Math.max(...xs)*1.2,yMn=Math.min(...ys,0)*1.2,yMx=Math.max(...ys)*1.2;
  const W=420,H=220,ML=44,MR=20,MT=10,MB=30,PW=W-ML-MR,PH=H-MT-MB;
  const tx=(v:number)=>ML+((v-xMn)/(xMx-xMn))*PW;
  const ty=(v:number)=>MT+PH-((v-yMn)/(yMx-yMn))*PH;
  return(
    <div>
      <div style={{fontSize:11,color:W9,marginBottom:6}}>Risk-Return Scatter (20-day window) -- X: Std Dev, Y: Mean Return</div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{overflow:"visible"}}>
        <line x1={ML} y1={ty(0)} x2={W-MR} y2={ty(0)} stroke="#ffffff30" strokeDasharray="4,3" strokeWidth={1}/>
        <line x1={ML} y1={MT} x2={ML} y2={H-MB} stroke="#ffffff25" strokeWidth={1}/>
        {pts.map(p=>(
          <g key={p.sym}>
            <circle cx={tx(p.x)} cy={ty(p.y)} r={10} fill={`${p.c}33`} stroke={p.c} strokeWidth={2}/>
            <text x={tx(p.x)} y={ty(p.y)-14} textAnchor="middle" fontSize={11} fill={p.c} fontWeight="bold">{p.sym}</text>
          </g>
        ))}
        <text x={W/2} y={H-2} textAnchor="middle" fontSize={9} fill={W9}>Std Dev (Risk)</text>
        <text x={10} y={H/2} textAnchor="middle" fontSize={9} fill={W9} transform={`rotate(-90,10,${H/2})`}>Mean Return</text>
      </svg>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// SEARCH RESULT PANEL
// ═══════════════════════════════════════════════════════════════════════════
function SResult({data,onClose}:{data:AData;onClose:()=>void}){
  const [tab,setTab]=useState<"accuracy"|"overview"|"windows"|"episodes"|"technicals"|"seasonality"|"regime"|"correlations">("accuracy");
  const [sw,setSw]=useState(20);
  const ss=data.series_stats,tech=data.technicals,lp=data.latest_price,rank=data.rank;
  const rp=rank?Math.round((rank.below_me/rank.total)*100):null;
  const TABS=[
    {id:"accuracy",label:"Historical Accuracy",core:true},
    {id:"overview",label:"Overview"},
    {id:"windows",label:"All Windows"},
    {id:"episodes",label:"Episodes"},
    {id:"technicals",label:"Technicals"},
    {id:"seasonality",label:"Seasonality"},
    {id:"regime",label:"Regimes"},
    {id:"correlations",label:"Correlations"},
  ] as const;

  return(
    <div style={{marginTop:14}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:10}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}}>
            <h2 style={{margin:0,fontSize:24,fontWeight:900,color:CY,letterSpacing:-1}}>{data.symbol}</h2>
            <span style={{fontSize:11,fontWeight:600,color:DIM,border:`1px solid ${BOR}`,borderRadius:4,padding:"2px 8px"}}>{data.asset_type.toUpperCase()}</span>
            {rp!==null&&<span style={{fontSize:11,fontWeight:700,color:YL,border:`1px solid ${YL}44`,borderRadius:4,padding:"2px 8px"}}>Top {100-rp}% by 20d Prob</span>}
          </div>
          {lp&&<div style={{color:DIM,fontSize:12,marginTop:3}}>
            Price: <span style={{color:WHT,fontWeight:700,fontSize:14}}>{(lp.close||0).toLocaleString("en-IN",{maximumFractionDigits:2})}</span>
            {" "}&bull; {lp.date}
            {lp.volume?` \u2022 Vol: ${(lp.volume||0).toLocaleString("en-IN")}`:""}
          </div>}
        </div>
        <button onClick={onClose} style={{background:"transparent",border:`1px solid ${BOR}`,color:DIM,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Clear</button>
      </div>

      {data.price_history.length>1&&<div style={{marginBottom:10}}><Spark data={data.price_history}/></div>}

      {ss&&<div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:12}}>
        <SBox label="CAGR"    value={pct(ss.cagr_pct,1)}           color={col(ss.cagr_pct)}/>
        <SBox label="Ann Vol" value={pct(ss.ann_volatility_pct,1)}/>
        <SBox label="Max DD"  value={pct(ss.max_drawdown_pct,1)}   color={R}/>
        <SBox label="Sharpe"  value={num(ss.sharpe_ratio)}         color={CY}/>
        <SBox label="Sortino" value={num(ss.sortino_ratio)}        color={CY}/>
        <SBox label="Calmar"  value={num(ss.calmar_ratio)}         color={CY}/>
        <SBox label="N Days"  value={(ss.n_trading_days||0).toLocaleString()}/>
        {ss.mdd_recovery_days!=null&&<SBox label="DD Recovery" value={`${ss.mdd_recovery_days}d`}/>}
      </div>}

      <div style={{display:"flex",gap:3,flexWrap:"wrap",marginBottom:12,borderBottom:`1px solid ${BOR}`,paddingBottom:8}}>
        {TABS.map(t=>(
          <button key={t.id} onClick={()=>setTab(t.id)} style={{padding:"5px 11px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:tab===t.id?CY:"transparent",color:tab===t.id?"#000":DIM}}>
            {t.label}{"core" in t&&t.core&&<span style={{marginLeft:4,fontSize:8,background:G,color:"#000",borderRadius:2,padding:"1px 3px",fontWeight:700}}>CORE</span>}
          </button>
        ))}
      </div>

      {tab==="accuracy"&&<Card title="Historical Accuracy -- Windows Where This Stock Consistently Goes UP or DOWN" accent={G}><HistAcc stats={data.window_stats} eu={data.extremes_up} ed={data.extremes_down}/></Card>}
      {tab==="overview"&&<><Card title="Probability Heatmap" accent={YL}><PHmap stats={data.window_stats}/></Card><Card title="Return Distribution by Window (Percentile Fan)" accent={G}><PFan stats={data.window_stats}/></Card></>}
      {tab==="windows"&&<Card title="Full Window Stats (17 windows)" accent={CY}><WTable stats={data.window_stats}/></Card>}
      {tab==="episodes"&&<Card title="Historical Best and Worst Episodes" accent={G}><Eps eu={data.extremes_up} ed={data.extremes_down} sw={sw} setSw={setSw}/></Card>}
      {tab==="technicals"&&(
        <div>
          {!tech?<Card title="Technicals" accent={YL}><div style={{color:DIM,fontSize:12}}>No technical data for {data.symbol}. Run the daily pipeline to populate symbol_technicals.</div></Card>:(
            <Card title="Current Technical Indicators" accent={YL}>
              <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10}}>
                <SBox label="RSI 14"    value={num(tech.rsi_14,1)}         color={tech.rsi_14>70?R:tech.rsi_14<30?G:WHT} sub={tech.rsi_14>70?"Overbought":tech.rsi_14<30?"Oversold":"Neutral"}/>
                <SBox label="ATR 14%"   value={pct(tech.atr_14_pct,2)}/>
                <SBox label="ADX 14"    value={num(tech.adx_14,1)}         color={tech.adx_14>25?G:DIM} sub={tech.adx_14>25?"Trending":"Ranging"}/>
                <SBox label="Vs SMA20"  value={pct(tech.pct_above_sma20,2)} color={col(tech.pct_above_sma20)}/>
                <SBox label="Vol Surge" value={`${num(tech.vol_surge_20d,1)}x`} color={tech.vol_surge_20d>2?G:DIM}/>
                <SBox label="MACD"      value={tech.macd_line>tech.macd_signal?"BULL":"BEAR"} color={tech.macd_line>tech.macd_signal?G:R}/>
                <SBox label="BB%"       value={num(tech.bb_pct,2)}/>
              </div>
              <div style={{fontSize:10,color:DIM}}>As of: {tech.as_of_date?.slice(0,10)||"--"}</div>
            </Card>
          )}
          {data.insider_trades.length>0&&<Card title="Recent Insider Trades" accent={YL}>
            <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
              <thead><tr>{["Date","Name","Type","Qty","Price","Value Cr"].map(h=><th key={h} style={{padding:"4px 8px",color:W9,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${BOR}`}}>{h}</th>)}</tr></thead>
              <tbody>{data.insider_trades.map((t,i)=>(
                <tr key={i} style={{borderBottom:`1px solid ${BOR}22`}}>
                  <td style={{padding:"4px 8px",color:DIM,textAlign:"right"}}>{t.filing_date}</td>
                  <td style={{padding:"4px 8px",textAlign:"right",color:WHT}}>{t.name}</td>
                  <td style={{padding:"4px 8px",fontWeight:700,textAlign:"right",color:t.transaction_type==="BUY"?G:R}}>{t.transaction_type}</td>
                  <td style={{padding:"4px 8px",textAlign:"right"}}>{(t.quantity||0).toLocaleString("en-IN")}</td>
                  <td style={{padding:"4px 8px",textAlign:"right"}}>{num(t.price,1)}</td>
                  <td style={{padding:"4px 8px",textAlign:"right",color:CY}}>{t.value?(t.value/1e7).toFixed(2):"--"}</td>
                </tr>
              ))}</tbody>
            </table></div>
          </Card>}
          {data.announcements.length>0&&<Card title="Recent Announcements" accent={DIM}>
            {data.announcements.map((a,i)=><div key={i} style={{display:"flex",gap:12,padding:"5px 0",borderBottom:`1px solid ${BOR}22`,fontSize:12}}><span style={{color:DIM,minWidth:90}}>{a.announcement_date}</span><span style={{color:WHT}}>{a.subject}</span></div>)}
          </Card>}
        </div>
      )}
      {tab==="seasonality"&&<Card title="Monthly Seasonality" accent={CY}>
        <SeaChart data={data.seasonality}/>
        {data.seasonality.length>0&&<div style={{marginTop:14,overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead><tr>{["Month","Avg Return","Median","N Obs"].map(h=><th key={h} style={{padding:"4px 8px",color:W9,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${BOR}`}}>{h}</th>)}</tr></thead>
          <tbody>{data.seasonality.map(r=><tr key={r.period_value} style={{borderBottom:`1px solid ${BOR}22`}}>
            <td style={{padding:"4px 8px",fontWeight:700,color:WHT,textAlign:"right"}}>{MON[r.period_value-1]}</td>
            <td style={{padding:"4px 8px",textAlign:"right",color:col(r.mean_return_pct),fontWeight:600}}>{pct(r.mean_return_pct)}</td>
            <td style={{padding:"4px 8px",textAlign:"right",color:col(r.median_return_pct)}}>{pct(r.median_return_pct)}</td>
            <td style={{padding:"4px 8px",textAlign:"right",color:DIM}}>{r.n_obs}</td>
          </tr>)}</tbody>
        </table></div>}
      </Card>}
      {tab==="regime"&&<Card title="Performance by Market Regime (20d)" accent={OR}>
        {(()=>{
          const r20=data.regime_stats.filter(r=>r.window_days===20);
          if(!r20.length) return <div style={{color:DIM,fontSize:12}}>No regime data available</div>;
          return <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(185px,1fr))",gap:10}}>
            {r20.map(r=><div key={r.regime} style={{background:`${BOR}22`,borderRadius:6,padding:"12px 14px",borderLeft:`3px solid ${col(r.mean_return)}`}}>
              <div style={{fontSize:11,fontWeight:700,color:W9,marginBottom:5}}>{r.regime}</div>
              <div style={{fontSize:16,fontWeight:800,color:col(r.mean_return)}}>{pct(r.mean_return)}</div>
              <div style={{fontSize:11,color:G}}>Prob+: {r.prob_positive!=null?((r.prob_positive)*100).toFixed(0)+"%":"--"}</div>
              <div style={{fontSize:11,color:DIM}}>N={r.n_windows} &bull; P5:{pct(r.p5)} P95:{pct(r.p95)}</div>
            </div>)}
          </div>;
        })()}
      </Card>}
      {tab==="correlations"&&<Card title="Top Correlated Assets" accent={DIM}>
        {data.correlations.length===0?(
          <div style={{color:DIM,fontSize:12}}>No correlation data for {data.symbol}. Requires symbol_correlations table to have rows with symbol_a=&apos;{data.symbol}&apos;.</div>
        ):(
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(175px,1fr))",gap:8}}>
            {data.correlations.map(c=><div key={c.symbol_b} style={{background:`${BOR}22`,borderRadius:6,padding:"10px 12px"}}>
              <div style={{color:CY,fontWeight:800,fontSize:14,marginBottom:3}}>{c.symbol_b}</div>
              <div style={{fontSize:11,color:DIM}}>20d: <span style={{color:col(c.correlation_20d),fontWeight:700}}>{num(c.correlation_20d)}</span></div>
              <div style={{fontSize:11,color:DIM}}>60d: <span style={{color:col(c.correlation_60d)}}>{num(c.correlation_60d)}</span></div>
              <div style={{fontSize:11,color:DIM}}>Beta: <span style={{color:YL}}>{num(c.beta_20d,2)}</span></div>
            </div>)}
          </div>
        )}
      </Card>}
    </div>
  );
}

// ── Compare Result ────────────────────────────────────────────────────────
function CResult({data,onClose}:{data:CData;onClose:()=>void}){
  const [tab,setTab]=useState<"summary"|"windows"|"probability"|"seasonality"|"correlation">("summary");
  const [cw,setCw]=useState(20);
  const syms=data.symbols;
  const sM=Object.fromEntries(data.series_stats.map(s=>[s.symbol,s]));
  const tM=Object.fromEntries(data.technicals.map(s=>[s.symbol,s]));
  const pM=Object.fromEntries(data.prices.map(s=>[s.symbol,s]));
  const best=(vals:(number|null|undefined)[],hi=true)=>{
    const ns=vals.map(v=>v??NaN);const vld=ns.filter(n=>!isNaN(n));
    if(!vld.length)return ns.map(()=>false);
    const t=hi?Math.max(...vld):Math.min(...vld);return ns.map(n=>!isNaN(n)&&n===t);
  };
  return(
    <div style={{marginTop:14}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
          <h2 style={{margin:0,fontSize:18,fontWeight:900}}>COMPARING</h2>
          {syms.map((s,i)=><span key={s} style={{color:SC[i],fontWeight:700,fontSize:13,padding:"3px 8px",border:`1px solid ${SC[i]}44`,borderRadius:4}}>{s}</span>)}
        </div>
        <button onClick={onClose} style={{background:"transparent",border:`1px solid ${BOR}`,color:DIM,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Clear</button>
      </div>
      <div style={{display:"flex",gap:3,flexWrap:"wrap",marginBottom:12,borderBottom:`1px solid ${BOR}`,paddingBottom:8}}>
        {(["summary","windows","probability","seasonality","correlation"] as const).map(t=><button key={t} onClick={()=>setTab(t)} style={{padding:"5px 11px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"none",background:tab===t?CY:"transparent",color:tab===t?"#000":DIM}}>{t.charAt(0).toUpperCase()+t.slice(1)}</button>)}
      </div>
      {tab==="summary"&&(
        <div>
          <Card title="Series Statistics" accent={CY}>
            <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
              <thead><tr>
                <th style={{padding:"5px 10px",textAlign:"left",color:W9,fontWeight:600,borderBottom:`1px solid ${BOR}`}}>Metric</th>
                {syms.map((s,i)=><th key={s} style={{padding:"5px 10px",textAlign:"right",color:SC[i],fontWeight:700,borderBottom:`1px solid ${BOR}`}}>{s}</th>)}
              </tr></thead>
              <tbody>{[
                {l:"Price",  v:syms.map(s=>pM[s]?.close?.toLocaleString("en-IN",{maximumFractionDigits:2})||"--"),hi:undefined},
                {l:"CAGR%",  v:syms.map(s=>sM[s]?.cagr_pct),hi:true},
                {l:"Vol%",   v:syms.map(s=>sM[s]?.ann_volatility_pct),hi:false},
                {l:"MaxDD%", v:syms.map(s=>sM[s]?.max_drawdown_pct),hi:false},
                {l:"Sharpe", v:syms.map(s=>sM[s]?.sharpe_ratio),hi:true},
                {l:"Sortino",v:syms.map(s=>sM[s]?.sortino_ratio),hi:true},
                {l:"RSI",    v:syms.map(s=>tM[s]?.rsi_14),hi:undefined},
                {l:"Vs SMA20%",v:syms.map(s=>tM[s]?.pct_above_sma20),hi:true},
                {l:"MACD",   v:syms.map(s=>{const t=tM[s];return t?(t.macd_line>t.macd_signal?"BULL":"BEAR"):null;}),hi:undefined},
              ].map(row=>{
                const ib=row.hi!==undefined?best(row.v as number[],row.hi):null;
                return(<tr key={row.l} style={{borderBottom:`1px solid ${BOR}22`}}>
                  <td style={{padding:"5px 10px",color:W9}}>{row.l}</td>
                  {(row.v as unknown[]).map((v,i)=>{
                    const isN=typeof v==="number";
                    const txt=isN?(row.l.includes("%")||row.l.includes("CAGR")||row.l.includes("Vol")||row.l.includes("DD")||row.l.includes("SMA")?pct(v):num(v)):String(v??"--");
                    return <td key={i} style={{padding:"5px 10px",textAlign:"right",color:ib?.[i]?SC[i]:WHT,fontWeight:ib?.[i]?800:400,background:ib?.[i]?`${SC[i]}15`:"transparent"}}>{txt}</td>;
                  })}
                </tr>);
              })}</tbody>
            </table></div>
          </Card>
          <Card title="Risk-Return Scatter" accent={CY}><Scatter data={data} syms={syms}/></Card>
        </div>
      )}
      {tab==="windows"&&(
        <div>
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:10}}>
            {DW.map(d=><button key={d} onClick={()=>setCw(d)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"1px solid",background:cw===d?CY:"transparent",color:cw===d?"#000":DIM,borderColor:cw===d?CY:BOR}}>{wL(d)}</button>)}
          </div>
          <Card title="Full Window Comparison" accent={G}><PFanCmp data={data} syms={syms}/></Card>
        </div>
      )}
      {tab==="probability"&&(
        <div>
          <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:10}}>
            {DW.map(d=><button key={d} onClick={()=>setCw(d)} style={{padding:"4px 10px",borderRadius:4,fontSize:11,fontWeight:600,cursor:"pointer",border:"1px solid",background:cw===d?CY:"transparent",color:cw===d?"#000":DIM,borderColor:cw===d?CY:BOR}}>{wL(d)}</button>)}
          </div>
          <Card title="Probability Comparison" accent={YL}>
            {[{k:"prob_positive",l:"Prob UP",c:CY},{k:"prob_gt10",l:">+10%",c:G},{k:"prob_lt_neg10",l:"<-10%",c:R}].map(m=>(
              <div key={m.k} style={{marginBottom:14}}>
                <div style={{fontSize:10,color:W9,fontWeight:600,marginBottom:6}}>{m.l} ({wL(cw)} window)</div>
                {syms.map((s,i)=>{
                  const w=data.window_stats.find(x=>x.symbol===s&&x.window_days===cw);
                  const v=w?((w as Record<string,unknown>)[m.k] as number||0)*100:0;
                  return(<div key={s} style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
                    <span style={{minWidth:90,fontSize:11,fontWeight:700,color:SC[i]}}>{s}</span>
                    <div style={{flex:1,height:10,background:`${BOR}33`,borderRadius:5}}>
                      <div style={{height:10,width:`${Math.min(100,v)}%`,background:SC[i],borderRadius:5,opacity:0.85}}/>
                    </div>
                    <span style={{fontSize:12,color:SC[i],fontWeight:700,minWidth:36}}>{v.toFixed(0)}%</span>
                  </div>);
                })}
              </div>
            ))}
          </Card>
        </div>
      )}
      {tab==="seasonality"&&<Card title="Seasonality Comparison" accent={CY}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:14}}>
          {syms.map((s,i)=>{
            const sd=data.seasonality.filter(r=>r.symbol===s);
            const mx=Math.max(...sd.map(r=>Math.abs(r.mean_return_pct||0)),1);
            return(<div key={s}>
              <div style={{color:SC[i],fontWeight:700,fontSize:12,marginBottom:6}}>{s}</div>
              <div style={{display:"flex",gap:3,alignItems:"flex-end",height:60}}>
                {sd.map(r=>{const h=Math.max(2,(Math.abs(r.mean_return_pct||0)/mx)*55);const pos=(r.mean_return_pct||0)>=0;return <div key={r.period_value} style={{flex:1,height:h,background:pos?SC[i]:R,opacity:0.75,borderRadius:"1px 1px 0 0",minHeight:2}}/>;  })}
              </div>
              <div style={{display:"flex",gap:3}}>{sd.map(r=><div key={r.period_value} style={{flex:1,textAlign:"center",fontSize:7,color:DIM}}>{MON[r.period_value-1].slice(0,1)}</div>)}</div>
            </div>);
          })}
        </div>
      </Card>}
      {tab==="correlation"&&<Card title="Cross Correlations" accent={DIM}>
        {data.cross_correlations.length===0?<div style={{color:DIM,fontSize:12}}>No cross-correlation data</div>:(
          <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
            {data.cross_correlations.map(c=><div key={`${c.symbol_a}-${c.symbol_b}`} style={{background:`${BOR}22`,borderRadius:6,padding:"8px 12px",fontSize:12}}>
              <span style={{color:SC[syms.indexOf(c.symbol_a)]||CY,fontWeight:700}}>{c.symbol_a}</span><span style={{color:DIM}}> x </span><span style={{color:SC[syms.indexOf(c.symbol_b)]||G,fontWeight:700}}>{c.symbol_b}</span>
              <div style={{fontSize:11,marginTop:3}}><span style={{color:DIM}}>20d: </span><span style={{color:col(c.correlation_20d),fontWeight:700}}>{num(c.correlation_20d)}</span><span style={{color:DIM}}> beta: </span><span style={{color:YL}}>{num(c.beta_20d,2)}</span></div>
            </div>)}
          </div>
        )}
      </Card>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════
const PS=[["Top Banks","HDFCBANK,ICICIBANK,SBIN,AXISBANK,KOTAKBANK"],["IT Giants","TCS,INFY,WIPRO,HCLTECH,TECHM"],["Nifty Top5","RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK"],["FMCG","HINDUNILVR,ITC,NESTLEIND,BRITANNIA,DABUR"],["Auto","MARUTI,TATAMOTORS,M&M,BAJAJ-AUTO,EICHERMOT"]];
const PI=[["Broad Mkt","NIFTY 50,NIFTY MIDCAP 100,NIFTY SMALLCAP 100"],["Sectoral","NIFTY BANK,NIFTY IT,NIFTY PHARMA,NIFTY AUTO"],["Global","SPX,NDX,NIKKEI225,DAX,FTSE100"]];

export default function AnalysisPage(){
  const [mode,setMode]=useState<"search-stock"|"compare-stocks"|"search-index"|"compare-index">("search-stock");
  const [sIn,setSIn]=useState("");const [sData,setSData]=useState<AData|null>(null);const [sLoad,setSLoad]=useState(false);const [sErr,setSErr]=useState<string|null>(null);
  const [cIn,setCIn]=useState("");const [cData,setCData]=useState<CData|null>(null);const [cLoad,setCLoad]=useState(false);const [cErr,setCErr]=useState<string|null>(null);
  const isCmp=mode==="compare-stocks"||mode==="compare-index";
  const atype=(mode==="search-index"||mode==="compare-index")?"index":"stock";

  const doSearch=useCallback(async(sym:string)=>{
    if(!sym.trim())return;
    setSLoad(true);setSErr(null);setSData(null);
    try{const r=await fetch(`/api/analysis?symbol=${encodeURIComponent(sym.trim().toUpperCase())}`,{cache:"no-store"});const d=await r.json();if(!d.ok)throw new Error(d.error||"Not found");setSData(d);}
    catch(e:unknown){setSErr(String(e));}finally{setSLoad(false);}
  },[]);

  const doCompare=useCallback(async(raw:string)=>{
    const syms=raw.split(/[,\s]+/).map(s=>s.trim().toUpperCase()).filter(Boolean).slice(0,5);
    if(syms.length<2){setCErr("Enter 2-5 symbols");return;}
    setCLoad(true);setCErr(null);setCData(null);
    try{const r=await fetch(`/api/analysis/compare?symbols=${syms.join(",")}`,{cache:"no-store"});const d=await r.json();if(!d.ok)throw new Error(d.error||"API error");setCData(d);}
    catch(e:unknown){setCErr(String(e));}finally{setCLoad(false);}
  },[]);

  useEffect(()=>{setSData(null);setCData(null);setSErr(null);setCErr(null);},[mode]);

  const MODES=[{id:"search-stock",l:"Search Stock"},{id:"compare-stocks",l:"Compare Stocks"},{id:"search-index",l:"Search Index"},{id:"compare-index",l:"Compare Indices"}] as const;

  return(
    <div style={{maxWidth:1200,margin:"0 auto",padding:"20px 16px"}}>
      <div style={{marginBottom:16}}>
        <h1 style={{margin:0,fontSize:24,fontWeight:900,letterSpacing:-0.5}}>ANALYTICS HUB</h1>
        <div style={{color:DIM,fontSize:12,marginTop:3}}>Deep analysis -- 649k historical episodes, 17 windows, full probability + historical accuracy</div>
      </div>

      <div style={{display:"flex",gap:5,marginBottom:16,background:`${BOR}22`,borderRadius:8,padding:5}}>
        {MODES.map(b=><button key={b.id} onClick={()=>setMode(b.id)} style={{flex:1,padding:"10px 8px",borderRadius:6,fontSize:12,fontWeight:700,cursor:"pointer",border:"none",background:mode===b.id?CY:"transparent",color:mode===b.id?"#000":DIM}}>{b.l}</button>)}
      </div>

      {!isCmp?(
        <div style={{marginBottom:12}}>
          <div style={{display:"flex",gap:8}}>
            <AInput value={sIn} onChange={setSIn} onSelect={s=>{setSIn(s);doSearch(s);}}
              placeholder={mode==="search-stock"?"Type stock name or symbol (e.g. HDFC Bank, Reliance, TCS)...":"Type index name (e.g. NIFTY 50, NIFTY BANK, India VIX)..."}
              stype={atype as "stock"|"index"} autoFocus/>
            <button onClick={()=>doSearch(sIn)} disabled={sLoad} style={{background:CY,color:"#000",border:"none",borderRadius:8,padding:"12px 22px",fontWeight:800,cursor:"pointer",fontSize:14,opacity:sLoad?0.6:1,minWidth:110}}>{sLoad?"Loading...":"Analyze"}</button>
          </div>
          {sErr&&<div style={{color:R,fontSize:13,marginTop:8}}>{sErr}</div>}
        </div>
      ):(
        <div style={{marginBottom:12}}>
          <div style={{display:"flex",gap:8,marginBottom:8}}>
            <AInput value={cIn} onChange={setCIn} onSelect={()=>{}}
              placeholder={mode==="compare-stocks"?"Type symbols (RELIANCE, TCS, HDFCBANK) -- separate by comma":"Type indices (NIFTY 50, NIFTY BANK, NIFTY IT)"}
              stype={atype as "stock"|"index"} multi autoFocus/>
            <button onClick={()=>doCompare(cIn)} disabled={cLoad} style={{background:CY,color:"#000",border:"none",borderRadius:8,padding:"12px 22px",fontWeight:800,cursor:"pointer",fontSize:14,opacity:cLoad?0.6:1,minWidth:110}}>{cLoad?"Loading...":"Compare"}</button>
          </div>
          <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
            {(mode==="compare-stocks"?PS:PI).map(([l,v])=><button key={l} onClick={()=>{setCIn(v.replace(/,/g,", "));doCompare(v);}} style={{background:"transparent",border:`1px solid ${BOR}`,color:DIM,borderRadius:4,padding:"4px 10px",cursor:"pointer",fontSize:11,fontWeight:600}}>{l}</button>)}
          </div>
          {cErr&&<div style={{color:R,fontSize:13,marginTop:8}}>{cErr}</div>}
          {cLoad&&<div style={{color:DIM,padding:"20px 0",textAlign:"center"}}>Comparing...</div>}
        </div>
      )}

      {sLoad&&<div style={{padding:40,textAlign:"center",color:DIM}}>Analyzing {sIn}... querying 649k historical episodes...</div>}
      {sData&&<SResult data={sData} onClose={()=>{setSData(null);setSIn("");}}/>}
      {cData&&<CResult data={cData} onClose={()=>{setCData(null);setCIn("");}}/>}
    </div>
  );
}
""")

print("\n" + "="*60)
print("FIX PHASE 10C COMPLETE")
print("="*60)
print("""
Changes:
  [1] /api/analysis/route.ts rewritten
      -> Correlations: ORDER BY ABS(COALESCE(correlation_20d,0))
      -> Technicals: ORDER BY as_of_date DESC LIMIT 1
      -> Full NaN sanitization

  [2] /analysis/page.tsx fully rewritten
      -> HISTORICAL ACCURACY is the first tab (marked CORE)
         Shows every window >70% accurate UP or DOWN
         "20D: 85% accurate (17/20 periods went UP)"
         With accuracy bar, hits/total, avg move, range, best episode
      -> Autocomplete on ALL 4 modes including Compare (multi-input)
      -> SVG labels: #94a3b8 (visible on dark bg)
      -> Technicals: clear "no data" message
      -> Correlations: clear "no data" message
      -> All text colors use WHT/W9 variables instead of CSS vars

  [3] All API route.ts files NaN-patched

Restart: cd D:\\MICC\\micc-dashboard && npm run dev

Test: localhost:3000/analysis
  Type "HDFC Bank" -> select HDFCBANK from dropdown
  Click Analyze -> Historical Accuracy tab loads first
  See all windows where HDFCBANK historically goes UP >70%
""")
