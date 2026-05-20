"use client";
import NavBar from "@/components/NavBar";
import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import MarkdownText from "@/components/MarkdownText";

interface WindowRow { window_days:number; n_windows:number; mean_return:number; std_return:number; p5:number; p25:number; p75:number; p95:number; prob_positive:number; prob_gt10:number; prob_lt_neg10:number; sharpe_ratio:number; ann_return_equiv:number; }
interface SeasonRow { period_value:number; n_obs:number; mean_return_pct:number; median_return_pct:number; }
interface CorrRow   { symbol_b:string; correlation_20d:number; correlation_60d:number; beta_20d:number; }
interface RegRow    { regime:string; n_windows:number; mean_return:number; std_return:number; prob_positive:number; p5:number; p95:number; }
interface Tech      { atr_14_pct:number; adx_14:number; pct_above_sma20:number; vol_surge_20d:number; rsi_14:number; macd_line:number; macd_signal:number; bb_pct:number; as_of_date:string; }
interface Series    { cagr_pct:number; ann_volatility_pct:number; max_drawdown_pct:number; sharpe_ratio:number; sortino_ratio:number; calmar_ratio:number; n_trading_days:number; mdd_start_date:string; mdd_trough_date:string; mdd_recovery_days:number; }
interface Insider   { filing_date:string; name:string; category:string; transaction_type:string; quantity:number; price:number; value:number; }
interface Ann       { announcement_date:string; subject:string; }
interface KappaData {
  ok:boolean; error?:string; symbol:string; has_cached_report:boolean;
  report: { asset_type:string; llm_verdict:string; llm_source:string; timestamp:string; } | null;
  technicals:Tech|null; window_stats:WindowRow[]; seasonality:SeasonRow[];
  correlations:CorrRow[]; regime_stats:RegRow[]; series_stats:Series|null;
  latest_price:{close:number;date:string;volume:number}|null;
  insider_trades:Insider[]; announcements:Ann[];
}

const C = { green:"var(--accent-green)",red:"var(--accent-red)",cyan:"var(--accent-cyan)",yellow:"var(--accent-yellow)",orange:"var(--accent-orange,#f97316)",dim:"var(--text-tertiary)",primary:"var(--text-primary)",border:"var(--border-color)",surface:"var(--surface-card)" };
const pct = (v:unknown,d=2)=>v==null?"--":`${(+v)>=0?"+":""}${(+v).toFixed(d)}%`;
const num = (v:unknown,d=2)=>v==null?"--":(+v).toFixed(d);
const col = (v:unknown)=>(+v??0)>=0?C.green:C.red;
const MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function Card({title,children,accent}:{title:string;children:React.ReactNode;accent?:string}) {
  return <div style={{background:C.surface,border:`1px solid ${accent||C.border}`,borderRadius:8,padding:"16px 20px",marginBottom:18}}><div style={{fontSize:11,fontWeight:700,letterSpacing:1.5,color:accent||C.cyan,textTransform:"uppercase",marginBottom:12,borderBottom:`1px solid ${C.border}`,paddingBottom:8}}>{title}</div>{children}</div>;
}
function Grid({items}:{items:{label:string;value:string;color?:string}[]}) {
  return <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:10}}>{items.map(({label,value,color})=><div key={label} style={{background:`${C.border}22`,borderRadius:6,padding:"10px 12px"}}><div style={{fontSize:10,color:C.dim,fontWeight:700,marginBottom:4}}>{label}</div><div style={{fontSize:16,fontWeight:800,color:color||C.primary}}>{value}</div></div>)}</div>;
}

export default function DeepSymbolPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const router = useRouter();
  const [data, setData] = useState<KappaData|null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string|null>(null);

  const load = useCallback(async () => {
    if (!symbol) return;
    setLoading(true); setError(null);
    try {
      const r = await fetch(`/api/deep/${symbol}`, { cache: "no-store" });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error||"API error");
      setData(d);
    } catch(e:unknown) { setError(String(e)); }
    finally { setLoading(false); }
  }, [symbol]);

  useEffect(()=>{ load(); },[load]);

  if (loading) return <div style={{padding:40,color:C.dim,textAlign:"center"}}>Loading {symbol}...</div>;
  if (error)   return <div style={{padding:40,color:C.red}}>Error: {error}</div>;
  if (!data)   return <div style={{padding:40,color:C.yellow}}>No data for {symbol}</div>;

  const ss=data.series_stats, tech=data.technicals, lp=data.latest_price, kv=data.report;
  const seriesItems = ss ? [
    {label:"CAGR",    value:pct(ss.cagr_pct,1),         color:col(ss.cagr_pct)},
    {label:"Ann Vol", value:pct(ss.ann_volatility_pct,1)},
    {label:"Max DD",  value:pct(ss.max_drawdown_pct,1),  color:C.red},
    {label:"Sharpe",  value:num(ss.sharpe_ratio),        color:C.cyan},
    {label:"Sortino", value:num(ss.sortino_ratio),       color:C.cyan},
    {label:"Calmar",  value:num(ss.calmar_ratio),        color:C.cyan},
    {label:"N Days",  value:String(ss.n_trading_days)},
    {label:"DD Days", value:ss.mdd_recovery_days!=null?String(ss.mdd_recovery_days):"--"},
  ] : [];
  const techItems = tech ? [
    {label:"RSI 14",   value:num(tech.rsi_14,1),       color:tech.rsi_14>70?C.red:tech.rsi_14<30?C.green:C.primary},
    {label:"ATR 14%",  value:pct(tech.atr_14_pct,2)},
    {label:"ADX 14",   value:num(tech.adx_14,1),       color:tech.adx_14>25?C.green:C.dim},
    {label:"Vs SMA20", value:pct(tech.pct_above_sma20,2), color:col(tech.pct_above_sma20)},
    {label:"Vol Surge",value:num(tech.vol_surge_20d,1)+"x"},
    {label:"MACD",     value:tech.macd_line>tech.macd_signal?"BULL":"BEAR", color:tech.macd_line>tech.macd_signal?C.green:C.red},
    {label:"BB%",      value:num(tech.bb_pct,2)},
  ] : [];
  const DISPLAY=[5,10,20,60,120];
  const wRows=data.window_stats.filter(r=>DISPLAY.includes(r.window_days));
  const maxAbs=Math.max(...data.seasonality.map(r=>Math.abs(r.mean_return_pct||0)),1);

  return (
    <div style={{maxWidth:1050,margin:"0 auto",padding:"24px 16px"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:12}}>
            <button onClick={()=>router.push("/deep")} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:4,padding:"4px 10px",cursor:"pointer",fontSize:11}}>Back to Room</button>
            <h1 style={{margin:0,fontSize:24,fontWeight:900,color:C.cyan}}>{data.symbol}</h1>
            {kv?.asset_type && <span style={{fontSize:11,fontWeight:700,color:C.dim,border:`1px solid ${C.border}`,borderRadius:4,padding:"2px 8px"}}>{kv.asset_type.toUpperCase()}</span>}
          </div>
          {lp && <div style={{color:C.dim,fontSize:12,marginTop:6}}>Last: <span style={{color:C.primary,fontWeight:700}}>{lp.close?.toLocaleString("en-IN",{maximumFractionDigits:2})}</span> &bull; {lp.date} &bull; Vol: {lp.volume?.toLocaleString("en-IN")}</div>}
        </div>
        <div style={{display:"flex",gap:8}}>
          {!data.has_cached_report && <span style={{fontSize:11,color:C.yellow,border:`1px solid ${C.yellow}44`,borderRadius:4,padding:"3px 8px"}}>Live DB - run: py agent_kappa.py {data.symbol}</span>}
          <button onClick={()=>router.push(`/compare?symbols=${data.symbol}`)} style={{background:"transparent",color:C.yellow,border:`1px solid ${C.yellow}`,borderRadius:6,padding:"6px 12px",fontWeight:700,cursor:"pointer",fontSize:12}}>Compare</button>
          <button onClick={load} style={{background:"transparent",color:C.dim,border:`1px solid ${C.border}`,borderRadius:6,padding:"6px 10px",cursor:"pointer",fontSize:11}}>Refresh</button>
        </div>
      </div>

      {seriesItems.length>0 && <Card title="Full-History Series Stats" accent={C.cyan}><Grid items={seriesItems} />{ss?.mdd_start_date && <div style={{marginTop:12,fontSize:12,color:C.dim}}>Max Drawdown: {ss.mdd_start_date} to {ss.mdd_trough_date}{ss.mdd_recovery_days!=null?` (${ss.mdd_recovery_days}d to recover)`:""}</div>}</Card>}
      {techItems.length>0 && <Card title="Current Technicals" accent={C.yellow}><Grid items={techItems} /></Card>}

      <Card title="Rolling Window Behavior" accent={C.green}>
        {wRows.length===0 ? <div style={{color:C.dim,fontSize:12}}>No window data (run phase9b_build_window_stats.py)</div> :
        <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead><tr>{["Win","N","Mean%","Std%","P5%","P95%","Prob+",">10%","<-10%","Sharpe","Ann%"].map(h=><th key={h} style={{padding:"4px 8px",textAlign:"right",color:C.dim,fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
          <tbody>{wRows.map(r=><tr key={r.window_days} style={{borderBottom:`1px solid ${C.border}22`}}>
            <td style={{padding:"5px 8px",color:C.cyan,fontWeight:700,textAlign:"right"}}>{r.window_days}d</td>
            <td style={{padding:"5px 8px",color:C.dim,textAlign:"right"}}>{r.n_windows}</td>
            <td style={{padding:"5px 8px",color:col(r.mean_return),textAlign:"right"}}>{pct(r.mean_return)}</td>
            <td style={{padding:"5px 8px",color:C.dim,textAlign:"right"}}>{pct(r.std_return)}</td>
            <td style={{padding:"5px 8px",color:col(r.p5),textAlign:"right"}}>{pct(r.p5)}</td>
            <td style={{padding:"5px 8px",color:col(r.p95),textAlign:"right"}}>{pct(r.p95)}</td>
            <td style={{padding:"5px 8px",color:C.green,textAlign:"right"}}>{r.prob_positive}%</td>
            <td style={{padding:"5px 8px",color:C.cyan,textAlign:"right"}}>{r.prob_gt10}%</td>
            <td style={{padding:"5px 8px",color:C.red,textAlign:"right"}}>{r.prob_lt_neg10}%</td>
            <td style={{padding:"5px 8px",color:C.cyan,textAlign:"right"}}>{num(r.sharpe_ratio)}</td>
            <td style={{padding:"5px 8px",color:col(r.ann_return_equiv),textAlign:"right"}}>{pct(r.ann_return_equiv,1)}</td>
          </tr>)}</tbody>
        </table></div>}
      </Card>

      <Card title="Regime Breakdown (20d Window)" accent={C.orange}>
        {data.regime_stats.length===0 ? <div style={{color:C.dim,fontSize:12}}>No regime data</div> :
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(190px,1fr))",gap:10}}>
          {data.regime_stats.map(r=><div key={r.regime} style={{background:`${C.border}22`,borderRadius:6,padding:"10px 12px"}}>
            <div style={{fontSize:11,fontWeight:700,color:C.dim,marginBottom:6}}>{r.regime}</div>
            <div style={{fontSize:12,color:col(r.mean_return)}}>Mean: {pct(r.mean_return)}</div>
            <div style={{fontSize:12,color:C.green}}>Prob+: {r.prob_positive!=null?(r.prob_positive*100).toFixed(0)+"%":"--"}</div>
            <div style={{fontSize:12,color:C.dim}}>N: {r.n_windows} &bull; P5:{pct(r.p5)} P95:{pct(r.p95)}</div>
          </div>)}
        </div>}
      </Card>

      <Card title="Monthly Seasonality" accent={C.cyan}>
        {data.seasonality.length===0 ? <div style={{color:C.dim,fontSize:12}}>No seasonality data</div> :
        <div style={{display:"flex",gap:6,alignItems:"flex-end",height:110}}>
          {data.seasonality.map(r=>{const h=Math.abs((r.mean_return_pct||0)/maxAbs)*80;const pos=(r.mean_return_pct||0)>=0;return(
            <div key={r.period_value} style={{flex:1,textAlign:"center"}}>
              <div style={{fontSize:9,color:col(r.mean_return_pct),fontWeight:700,marginBottom:2}}>{pct(r.mean_return_pct,1)}</div>
              <div style={{height:h,background:pos?C.green:C.red,opacity:0.7,borderRadius:"2px 2px 0 0",minHeight:2}} />
      <NavBar />
              <div style={{fontSize:9,color:C.dim,marginTop:2}}>{MONTHS[(r.period_value-1)%12]}</div>
            </div>
          );})}
        </div>}
      </Card>

      {data.correlations.length>0 && <Card title="Top Correlations" accent={C.dim}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(170px,1fr))",gap:8}}>
          {data.correlations.slice(0,12).map(c=><div key={c.symbol_b} style={{background:`${C.border}22`,borderRadius:6,padding:"8px 12px",cursor:"pointer"}} onClick={()=>router.push(`/deep/${c.symbol_b}`)}>
            <div style={{color:C.cyan,fontWeight:700,fontSize:13}}>{c.symbol_b}</div>
            <div style={{fontSize:11,color:C.dim}}>20d: <span style={{color:col(c.correlation_20d)}}>{num(c.correlation_20d)}</span> &bull; beta {num(c.beta_20d,2)}</div>
          </div>)}
        </div>
      </Card>}

      {data.insider_trades.length>0 && <Card title="Insider Trades (Recent)" accent={C.yellow}>
        <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
          <thead><tr>{["Date","Name","Category","Type","Qty","Price","Value Cr"].map(h=><th key={h} style={{padding:"4px 8px",color:C.dim,textAlign:"right",fontWeight:600,borderBottom:`1px solid ${C.border}`}}>{h}</th>)}</tr></thead>
          <tbody>{data.insider_trades.map((t,i)=><tr key={i} style={{borderBottom:`1px solid ${C.border}22`}}>
            <td style={{padding:"4px 8px",color:C.dim,textAlign:"right"}}>{t.filing_date}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{t.name}</td>
            <td style={{padding:"4px 8px",color:C.dim,textAlign:"right"}}>{t.category}</td>
            <td style={{padding:"4px 8px",fontWeight:700,textAlign:"right",color:t.transaction_type==="BUY"?C.green:C.red}}>{t.transaction_type}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{t.quantity?.toLocaleString("en-IN")}</td>
            <td style={{padding:"4px 8px",textAlign:"right"}}>{num(t.price,1)}</td>
            <td style={{padding:"4px 8px",textAlign:"right",color:C.cyan}}>{t.value?(t.value/1e7).toFixed(2):"--"}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>}

      {data.announcements.length>0 && <Card title="Corporate Announcements" accent={C.dim}>
        {data.announcements.map((a,i)=><div key={i} style={{display:"flex",gap:12,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
          <span style={{color:C.dim,minWidth:90}}>{a.announcement_date}</span>
          <span style={{color:C.primary}}>{a.subject}</span>
        </div>)}
      </Card>}

      {kv?.llm_verdict && <Card title={`Kappa AI Verdict (${kv.llm_source||"LLM"})`} accent={C.cyan}><MarkdownText text={kv.llm_verdict} /></Card>}
    </div>
  );
}
