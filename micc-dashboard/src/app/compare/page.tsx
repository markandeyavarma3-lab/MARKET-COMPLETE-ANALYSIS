"use client";
import NavBar from "@/components/NavBar";

import { useState, useCallback, useEffect, useRef } from "react";

interface SeriesStats {
  cagr_pct: number|null; ann_volatility_pct: number|null;
  max_drawdown_pct: number|null; sharpe_ratio: number|null;
  sortino_ratio: number|null; calmar_ratio: number|null;
  skewness: number|null; kurtosis: number|null;
  n_trading_days: number|null; hi_52w: number|null;
  lo_52w: number|null; dist_from_52w_hi: number|null;
}
interface WindowRow {
  window_days: number; mean: number|null; std: number|null;
  p5: number|null; p25: number|null; p75: number|null; p95: number|null;
  prob_positive: number|null; prob_gt10: number|null; sharpe: number|null;
}
interface RegimeStat { regime: string; mean: number|null; prob_positive: number|null; n_windows: number|null; }
interface Seasonality {
  best_month: {month:string;avg_return:number}|null;
  worst_month: {month:string;avg_return:number}|null;
  best_weekday: {day:string;avg_return:number}|null;
  worst_weekday: {day:string;avg_return:number}|null;
}
interface Technicals {
  rsi_14: number|null; macd_signal: string|null; adx: number|null;
  dist_sma200: number|null; pct_above_sma20: number|null; atr_14_pct: number|null;
}
interface KappaReport {
  symbol: string; asset_type: string; date: string;
  series_stats: SeriesStats; window_table: WindowRow[];
  regime_stats_20d: RegimeStat[]; seasonality: Seasonality;
  technicals: Technicals; correlations: Record<string,number|null>;
  llm_verdict: string;
}
interface SearchResult { symbol: string; name: string; type: string; }

const COLORS = ["var(--accent)","var(--pos)","#f472b6","var(--warn)","var(--purple)"];
const WINDOWS = [5,10,20,30,60,90];
const CORR_BM = ["SPX","GOLD","DXY","VIX","USDINR","NIFTY50"];

const n   = (v:number|null|undefined,d=2) => v==null?"":Number(v).toFixed(d);
const pct = (v:number|null|undefined,d=2) => v==null?"":"" + (Number(v)>=0?"+":"") + Number(v).toFixed(d)+"%";
const clr = (v:number|null|undefined) => v==null?"var(--muted)":Number(v)>=0?"var(--pos)":"var(--neg)";

// Loading skeleton with animation
function LoadingSkeleton({ elapsed }: { elapsed: number }) {
  const steps = [
    "Fetching series stats...",
    "Computing window behavior...",
    "Analysing regime slices...",
    "Correlations + seasonality...",
    "LLM verdict (Kappa agent)...",
  ];
  const step = Math.min(Math.floor(elapsed / 6), steps.length - 1);
  return (
    <div style={{
      display:"flex", flexDirection:"column", alignItems:"center",
      justifyContent:"center", padding:"60px 28px", gap:28,
    }}>
      <div style={{ position:"relative", width:72, height:72 }}>
        {[0,1,2].map(i => (
          <div key={i} style={{
            position:"absolute",
            inset: i * 10,
            borderRadius:"50%",
            border:`2px solid ${COLORS[i]}`,
            animation:`micc-spin ${1.1+i*0.35}s linear infinite`,
            opacity: 0.8 - i*0.2,
          }} />
        ))}
      </div>
      <div style={{ textAlign:"center", maxWidth:380 }}>
        <p style={{ margin:"0 0 6px", fontSize:16, fontWeight:700, color:"var(--text)" }}>
          Running deep analysis
        </p>
        <p style={{ margin:"0 0 14px", fontSize:12, color:"var(--muted)" }}>
          {steps[step]}  ({elapsed}s elapsed)
        </p>
        <div style={{ display:"flex", flexDirection:"column", gap:6, textAlign:"left" }}>
          {steps.map((s,i) => (
            <div key={i} style={{ display:"flex", alignItems:"center", gap:10 }}>
              <span style={{ fontSize:11, minWidth:16, textAlign:"center" }}>
                {i < step ? "" : i === step ? ">" : " "}
              </span>
              <span style={{ fontSize:11, color: i < step ? "var(--pos)" : i===step ? "var(--accent)" : "var(--border2)" }}>
                {s}
              </span>
              {i === step && (
                <div style={{
                  flex:1, height:3, background:"var(--card)", borderRadius:3, overflow:"hidden",
                }}>
                  <div style={{
                    height:"100%", borderRadius:3,
                    background:`linear-gradient(90deg,${COLORS[i%COLORS.length]},transparent)`,
                    animation:"micc-shimmer 1.4s ease-in-out infinite alternate",
                  }} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <style>{`
        @keyframes micc-spin { to { transform: rotate(360deg); } }
        @keyframes micc-shimmer { from{width:15%;opacity:.4} to{width:95%;opacity:1} }
      `}</style>
    </div>
  );
}

// Autocomplete search input
function SymbolSearch({ onAdd, disabled }: { onAdd:(s:string)=>void; disabled:boolean }) {
  const [val,  setVal]  = useState("");
  const [sug,  setSug]  = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [idx,  setIdx]  = useState(-1);
  const ref = useRef<HTMLDivElement>(null);
  const TYPE_CLR: Record<string,string> = { stock:"var(--accent)", index:"var(--pos)", global:"var(--warn)" };

  useEffect(() => {
    if (!val.trim()) { setSug([]); setOpen(false); return; }
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(val)}&limit=12`);
        const d = await r.json();
        setSug(d.results || []);
        setOpen((d.results||[]).length > 0);
        setIdx(-1);
      } catch {}
    }, 200);
    return () => clearTimeout(t);
  }, [val]);

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const pick = (sym: string) => { onAdd(sym); setVal(""); setSug([]); setOpen(false); setIdx(-1); };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx(i => Math.min(i+1, sug.length-1)); }
    else if (e.key === "ArrowUp")  { e.preventDefault(); setIdx(i => Math.max(i-1, -1)); }
    else if (e.key === "Enter")    { e.preventDefault(); idx>=0&&sug[idx] ? pick(sug[idx].symbol) : val.trim()&&pick(val.trim().toUpperCase()); }
    else if (e.key === "Escape")   setOpen(false);
  };

  return (
    <div ref={ref} style={{ position:"relative", flex:1, maxWidth:340 }}>
      <input value={val}
        onChange={e => setVal(e.target.value)}
        onKeyDown={onKey}
        onFocus={() => sug.length && setOpen(true)}
        placeholder={disabled ? "Max 5 symbols reached" : "Type symbol or company name..."}
        disabled={disabled}
        autoComplete="off"
        style={{
          width:"100%", padding:"10px 14px", boxSizing:"border-box",
          background:"var(--card)", border:"1px solid #334155",
          borderRadius:8, color:"var(--text)", fontSize:13, outline:"none",
          opacity: disabled ? 0.45 : 1,
        }}
      />
      {open && sug.length > 0 && (
        <div style={{
          position:"absolute", top:"calc(100% + 4px)", left:0, right:0, zIndex:200,
          background:"var(--card)", border:"1px solid #334155", borderRadius:8,
          boxShadow:"0 12px 40px rgba(0,0,0,0.6)", overflow:"hidden",
        }}>
          {sug.map((s,i) => (
            <div key={s.symbol} onMouseDown={() => pick(s.symbol)}
              style={{
                padding:"9px 14px", cursor:"pointer",
                background: i===idx ? "var(--border2)" : "transparent",
                display:"flex", alignItems:"center", gap:10,
                borderBottom: i<sug.length-1 ? "1px solid #0f172a" : "none",
              }}>
              <span style={{
                fontFamily:"monospace", fontWeight:700, fontSize:13,
                color: TYPE_CLR[s.type]||"var(--text)", minWidth:110,
              }}>{s.symbol}</span>
              {s.name !== s.symbol && (
                <span style={{
                  fontSize:11, color:"var(--muted)", flex:1,
                  overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                }}>{s.name}</span>
              )}
              <span style={{
                fontSize:9, padding:"1px 6px", borderRadius:4,
                color: TYPE_CLR[s.type]||"var(--muted)",
                background: (TYPE_CLR[s.type]||"var(--muted)")+"22",
              }}>{s.type}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Symbol pill with remove button
function Pill({ symbol, color, onRemove }: { symbol:string; color:string; onRemove:()=>void }) {
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:6,
      background:`${color}18`, border:`1.5px solid ${color}55`,
      borderRadius:999, padding:"5px 14px",
      fontFamily:"monospace", fontWeight:800, fontSize:13, color,
    }}>
      {symbol}
      <button onClick={onRemove} style={{
        background:"none", border:"none", cursor:"pointer",
        color:`${color}88`, fontSize:16, lineHeight:1, padding:0,
      }}>x</button>
    </span>
  );
}

// Metric bar chart
function MetricBar({ label, values, colors, fmt, higherBetter=true }: {
  label:string; values:(number|null)[]; colors:string[];
  fmt:(v:number|null)=>string; higherBetter?:boolean;
}) {
  const valid = values.filter(v => v != null) as number[];
  if (!valid.length) return null;
  const mn = Math.min(...valid), mx = Math.max(...valid), rng = mx-mn||1;
  return (
    <div style={{ marginBottom:14 }}>
      <div style={{ fontSize:10, color:"var(--muted)", marginBottom:4, letterSpacing:0.5, textTransform:"uppercase" }}>{label}</div>
      {values.map((v,i) => {
        if (v==null) return <div key={i} style={{ height:24, marginBottom:3 }} />;
        const frac = (v - mn) / rng;
        const w    = Math.max((higherBetter ? frac : 1-frac) * 100, 2);
        return (
          <div key={i} style={{ display:"flex", alignItems:"center", gap:10, marginBottom:3 }}>
            <div style={{ width:3, height:18, borderRadius:2, background:colors[i], flexShrink:0 }} />
            <div style={{ width:200, background:"var(--bg)", borderRadius:3, height:7, overflow:"hidden" }}>
              <div style={{
                width:`${w}%`, height:"100%", borderRadius:3,
                background:`linear-gradient(90deg,${colors[i]}88,${colors[i]})`,
                transition:"width 0.5s ease",
              }} />
            </div>
            <span style={{ fontSize:13, color:colors[i], fontWeight:700, minWidth:72, textAlign:"right" }}>
              {fmt(v)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// Window stats breakdown table + year groups
function WindowBreakdown({ reports, loaded, colors, win }: {
  reports:Record<string,KappaReport>; loaded:string[]; colors:string[]; win:number;
}) {
  const rows = loaded.map(s => reports[s]?.window_table?.find(w => w.window_days===win));
  const metrics = [
    { label:"Mean Return",    key:"mean",          fmt:pct },
    { label:"Prob Positive",  key:"prob_positive", fmt:(v:number|null)=>v==null?"":""+v+"%" },
    { label:"Prob > 10%",     key:"prob_gt10",     fmt:(v:number|null)=>v==null?"":""+v+"%" },
    { label:"Std Dev",        key:"std",           fmt:pct },
    { label:"P5  (worst-case)",key:"p5",           fmt:pct },
    { label:"P25",            key:"p25",           fmt:pct },
    { label:"P75",            key:"p75",           fmt:pct },
    { label:"P95  (best-case)",key:"p95",          fmt:pct },
    { label:"Sharpe Ratio",   key:"sharpe",        fmt:(v:number|null)=>n(v) },
  ];
  return (
    <div style={{ marginTop:12, background:"var(--bg)", borderRadius:8, overflow:"hidden" }}>
      <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
        <thead>
          <tr style={{ background:"var(--bg)" }}>
            <th style={{ textAlign:"left", padding:"7px 10px", color:"var(--border2)", fontSize:10, fontWeight:600 }}>METRIC</th>
            {loaded.map((s,i) => (
              <th key={s} style={{ textAlign:"right", padding:"7px 10px", color:colors[i], fontSize:11, fontWeight:700 }}>{s}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map(m => (
            <tr key={m.key} style={{ borderTop:"1px solid #1e293b" }}>
              <td style={{ padding:"6px 10px", color:"var(--muted)", fontSize:11 }}>{m.label}</td>
              {rows.map((r,i) => {
                const v = r ? (r as any)[m.key] as number|null : null;
                const c = (m.key==="mean"||m.key==="p5"||m.key==="p95") ? clr(v) : colors[i];
                return (
                  <td key={i} style={{ padding:"6px 10px", textAlign:"right", color:c, fontWeight:700 }}>
                    {m.fmt(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Panel card
function Card({ title, icon, children }: { title:string; icon:string; children:React.ReactNode }) {
  return (
    <div style={{
      background:"var(--card)", border:"1px solid #334155", borderRadius:6, padding:"18px 20px",
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16 }}>
        <span style={{ fontSize:15 }}>{icon}</span>
        <h3 style={{ margin:0, fontSize:12, fontWeight:700, color:"var(--muted)", letterSpacing:".04em", textTransform:"uppercase" }}>{title}</h3>
      </div>
      {children}
    </div>
  );
}

// LLM verdict collapsible
function Verdict({ symbol, text, color }: { symbol:string; text:string; color:string }) {
  const [open, setOpen] = useState(false);
  return (
    <div onClick={() => setOpen(o=>!o)} style={{
      background:"var(--bg)", border:`1px solid ${open?color+"55":"var(--card)"}`,
      borderRadius:9, padding:"11px 14px", marginBottom:7, cursor:"pointer",
      transition:"border-color 0.2s",
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:10 }}>
        <span style={{ fontFamily:"monospace", fontWeight:800, color, fontSize:13 }}>{symbol}</span>
        {!open && (
          <span style={{ fontSize:11, color:"var(--muted)", flex:1, overflow:"hidden",
            textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
            {text.slice(0,100)}{text.length>100?"...":""}
          </span>
        )}
        <span style={{ color:"var(--border2)", fontSize:11, marginLeft:"auto" }}>{open?"v":">"}</span>
      </div>
      {open && <p style={{ margin:"10px 0 0", fontSize:12, color:"var(--text)", lineHeight:1.75 }}>{text}</p>}
    </div>
  );
}

// =============================================================================
// MAIN PAGE
// =============================================================================
export default function ComparePage() {
  const [symbols,  setSymbols]  = useState<string[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [reports,  setReports]  = useState<Record<string,KappaReport>>({});
  const [errors,   setErrors]   = useState<Record<string,string>>({});
  const [activeWin,setActiveWin]= useState(20);
  const [status,   setStatus]   = useState("");
  const [elapsed,  setElapsed]  = useState(0);
  const QUICK = ["RELIANCE","HDFCBANK","ICICIBANK","INFY","TCS","NIFTY50","AXISBANK","SBIN"];

  const addSym = useCallback((s:string) => {
    const sym = s.trim().toUpperCase();
    if (!sym || symbols.includes(sym) || symbols.length>=5) return;
    setSymbols(p=>[...p,sym]);
  },[symbols]);

  const rmSym = useCallback((s:string) => {
    setSymbols(p=>p.filter(x=>x!==s));
    setReports(p=>{ const r={...p}; delete r[s]; return r; });
  },[]);

  useEffect(() => {
    if (!loading) { setElapsed(0); return; }
    const t = setInterval(()=>setElapsed(e=>e+1), 1000);
    return ()=>clearInterval(t);
  },[loading]);

  const runCompare = useCallback(async (force=false) => {
    if (!symbols.length) return;
    setLoading(true); setStatus(""); setErrors({});
    try {
      const r = await fetch(`/api/compare?symbols=${symbols.join(",")}&force=${force?1:0}`);
      const d = await r.json();
      setReports(d.results||{});
      setErrors(d.errors||{});
      const ct = Object.keys(d.results||{}).length;
      setStatus("Loaded "+ct+"/"+symbols.length+" symbol"+(ct!==1?"s":"")+"."
        +(Object.keys(d.errors||{}).length?" Some failed.":""));
    } catch(e:any) { setStatus("Error: "+e.message); }
    finally { setLoading(false); }
  },[symbols]);

  const loaded  = symbols.filter(s=>reports[s]);
  const colors  = symbols.map((_,i)=>COLORS[i%COLORS.length]);
  const lColors = loaded.map(s=>colors[symbols.indexOf(s)]);

  return (
    <div style={{ minHeight:"100vh", background:"var(--bg)", color:"var(--text)", fontFamily:"'Space Grotesk',sans-serif" }}>
      <NavBar />

      {/* Header */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b" }}>
        <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"var(--text)" }}>
          Compare Stocks
        </h1>
        <p style={{ margin:"4px 0 0", fontSize:12, color:"var(--muted)" }}>
          Side-by-side deep analysis up to 5 symbols
        </p>
      </div>

      {/* Input bar */}
      <div style={{ padding:"16px 28px", borderBottom:"1px solid #1e293b", background:"#080d14" }}>
        {symbols.length>0 && (
          <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:12 }}>
            {symbols.map((s,i)=><Pill key={s} symbol={s} color={COLORS[i%COLORS.length]} onRemove={()=>rmSym(s)} />)}
          </div>
        )}
        <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
          <SymbolSearch onAdd={addSym} disabled={symbols.length>=5} />
          <button onClick={()=>runCompare(false)} disabled={loading||!symbols.length}
            style={{
              padding:"10px 22px",
              background:loading||!symbols.length?"var(--card)":"var(--pos)",
              color:loading||!symbols.length?"var(--border2)":"#fff",
              border:"none", borderRadius:8,
              cursor:loading||!symbols.length?"not-allowed":"pointer",
              fontSize:13, fontWeight:800,
            }}>
            {loading ? elapsed+"s..." : "Compare"}
          </button>
          <button onClick={()=>runCompare(true)} disabled={loading||!symbols.length}
            title="Force refresh (ignore cache)"
            style={{ padding:"10px 14px", background:"var(--card)", color:"var(--muted)",
              border:"1px solid #334155", borderRadius:8, cursor:"pointer", fontSize:12 }}>
            Refresh
          </button>
          {symbols.length>0 && (
            <button onClick={()=>{setSymbols([]);setReports({});setStatus("");}}
              style={{ padding:"10px 14px", background:"var(--card)", color:"var(--muted)",
                border:"1px solid #334155", borderRadius:8, cursor:"pointer", fontSize:12 }}>
              Clear all
            </button>
          )}
        </div>
        <div style={{ marginTop:10, display:"flex", gap:6, flexWrap:"wrap", alignItems:"center" }}>
          <span style={{ fontSize:11, color:"var(--border2)" }}>Quick add:</span>
          {QUICK.map(s=>(
            <button key={s} onClick={()=>addSym(s)} style={{
              fontSize:11, fontFamily:"monospace",
              background:symbols.includes(s)?"var(--card)":"var(--bg)",
              color:symbols.includes(s)?"var(--border2)":"var(--accent)",
              border:"1px solid "+(symbols.includes(s)?"var(--card)":"var(--border)"),
              borderRadius:6, padding:"3px 10px", cursor:"pointer",
            }}>{s}</button>
          ))}
        </div>
        {status && <p style={{ margin:"8px 0 0", fontSize:12, color:status.startsWith("Loaded")?"var(--pos)":"var(--muted)" }}>{status}</p>}
        {Object.entries(errors).map(([sym,err])=>(
          <div key={sym} style={{ marginTop:5, padding:"4px 12px", background:"#2d1515", borderRadius:6, fontSize:11, color:"var(--neg)" }}>
            {sym}: {err}
          </div>
        ))}
      </div>

      {/* Loading */}
      {loading && <LoadingSkeleton elapsed={elapsed} />}

      {/* Empty states */}
      {!loading && loaded.length===0 && symbols.length===0 && (
        <div style={{ padding:"80px 28px", textAlign:"center" }}>
          <div style={{ fontSize:52, marginBottom:16 }}>Compare</div>
          <h2 style={{ color:"var(--text)", marginBottom:8, fontSize:20 }}>Compare up to 5 stocks</h2>
          <p style={{ color:"var(--muted)", fontSize:13, maxWidth:460, margin:"0 auto 8px" }}>
            Type a symbol or company name above  autocomplete will find it.
            Cached Kappa reports load instantly. Fresh analysis: ~30s per symbol.
          </p>
          <p style={{ color:"var(--border2)", fontSize:11 }}>
            CAGR, Sharpe, Drawdown, Window stats, Regime returns, Seasonality, Correlations, LLM verdict
          </p>
        </div>
      )}
      {!loading && loaded.length===0 && symbols.length>0 && (
        <div style={{ padding:"60px 28px", textAlign:"center" }}>
          <p style={{ color:"var(--muted)", fontSize:14 }}>
            Press Compare to run analysis
          </p>
        </div>
      )}

      {/* Results */}
      {!loading && loaded.length>0 && (
        <div style={{ padding:"20px 28px" }}>

          {/* Legend */}
          <div style={{ display:"flex", gap:20, marginBottom:20, flexWrap:"wrap" }}>
            {loaded.map((s,i)=>(
              <div key={s} style={{ display:"flex", alignItems:"center", gap:8 }}>
                <div style={{ width:12, height:12, borderRadius:3, background:lColors[i] }} />
                <span style={{ fontFamily:"monospace", fontWeight:800, fontSize:14, color:lColors[i] }}>{s}</span>
                <span style={{ fontSize:11, color:"var(--muted)" }}>{reports[s]?.asset_type} {reports[s]?.date}</span>
              </div>
            ))}
          </div>

          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:18 }}>

            {/* Key Stats */}
            <Card icon="p" title="Key Stats">
              {([
                {label:"CAGR",           key:"cagr_pct",          hb:true},
                {label:"Ann Volatility", key:"ann_volatility_pct",hb:false},
                {label:"Max Drawdown",   key:"max_drawdown_pct",  hb:false},
                {label:"Sharpe Ratio",   key:"sharpe_ratio",      hb:true},
                {label:"Sortino Ratio",  key:"sortino_ratio",     hb:true},
                {label:"Calmar Ratio",   key:"calmar_ratio",      hb:true},
                {label:"Skewness",       key:"skewness",          hb:true},
                {label:"Kurtosis",       key:"kurtosis",          hb:false},
              ] as any[]).map((m:any)=>(
                <MetricBar key={m.key} label={m.label}
                  values={loaded.map(s=>reports[s]?.series_stats?.[m.key as keyof SeriesStats]??null)}
                  colors={lColors} fmt={pct} higherBetter={m.hb} />
              ))}
            </Card>

            {/* Technicals */}
            <Card icon="T" title="Technicals">
              {([
                {label:"RSI 14",      key:"rsi_14",      fmt:(v:any)=>v==null?"":Number(v).toFixed(1)},
                {label:"MACD Signal", key:"macd_signal", fmt:(v:any)=>v??""},
                {label:"ADX 14",      key:"adx",         fmt:(v:any)=>v==null?"":Number(v).toFixed(1)},
                {label:"Dist SMA200", key:"dist_sma200", fmt:pct},
                {label:"ATR 14%",     key:"atr_14_pct",  fmt:pct},
              ] as any[]).map((m:any)=>(
                <div key={m.key} style={{ marginBottom:10 }}>
                  <div style={{ fontSize:10, color:"var(--muted)", marginBottom:4, textTransform:"uppercase", letterSpacing:0.5 }}>{m.label}</div>
                  <div style={{ display:"flex", gap:16, flexWrap:"wrap" }}>
                    {loaded.map((s,i)=>(
                      <span key={s} style={{ fontWeight:800, fontSize:14, color:lColors[i] }}>
                        {m.fmt(reports[s]?.technicals?.[m.key as keyof Technicals]??null)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              <div style={{ borderTop:"1px solid #334155", marginTop:12, paddingTop:12 }}>
                <div style={{ fontSize:10, color:"var(--muted)", marginBottom:8, textTransform:"uppercase", letterSpacing:0.5 }}>52W Range</div>
                {loaded.map((s,i)=>{
                  const st=reports[s]?.series_stats;
                  return (
                    <div key={s} style={{
                      display:"flex", gap:8, alignItems:"center",
                      padding:"5px 10px", background:"var(--bg)", borderRadius:6, marginBottom:4,
                      borderLeft:`3px solid ${lColors[i]}`,
                    }}>
                      <span style={{ fontFamily:"monospace", fontWeight:700, fontSize:11, color:lColors[i], minWidth:90 }}>{s}</span>
                      <span style={{ fontSize:11, color:"var(--muted)" }}>
                        {st?.lo_52w?.toFixed(0)??"?"} - {st?.hi_52w?.toFixed(0)??"?"}
                      </span>
                      {st?.dist_from_52w_hi!=null && (
                        <span style={{ marginLeft:"auto", fontSize:11, color:"var(--neg)" }}>
                          {st.dist_from_52w_hi.toFixed(1)}% from high
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>

            {/* Window Behavior */}
            <Card icon="W" title="Window Behavior">
              <div style={{ display:"flex", gap:6, marginBottom:14, flexWrap:"wrap" }}>
                {WINDOWS.map(w=>(
                  <button key={w} onClick={()=>setActiveWin(w)} style={{
                    padding:"4px 14px", borderRadius:999, fontSize:12, fontWeight:700,
                    background:activeWin===w?"var(--accent)":"var(--border2)",
                    color:activeWin===w?"#fff":"var(--muted)",
                    border:"none", cursor:"pointer",
                  }}>{w}d</button>
                ))}
              </div>
              {([
                {label:"Mean Return",   key:"mean",          fmt:pct,  hb:true},
                {label:"Prob Positive", key:"prob_positive", fmt:(v:number|null)=>v==null?"":""+v+"%", hb:true},
                {label:"Std Dev",       key:"std",           fmt:pct,  hb:false},
                {label:"P5 (downside)", key:"p5",            fmt:pct,  hb:false},
                {label:"P95 (upside)",  key:"p95",           fmt:pct,  hb:true},
                {label:"Sharpe",        key:"sharpe",        fmt:(v:number|null)=>n(v), hb:true},
              ] as any[]).map((m:any)=>(
                <MetricBar key={m.key} label={m.label}
                  values={loaded.map(s=>reports[s]?.window_table?.find(w=>w.window_days===activeWin)?.[m.key as keyof WindowRow]??null)}
                  colors={lColors} fmt={m.fmt} higherBetter={m.hb} />
              ))}
              <WindowBreakdown reports={reports} loaded={loaded} colors={lColors} win={activeWin} />
            </Card>

            {/* Regime Stats */}
            <Card icon="R" title="Regime Stats (20d mean return)">
              <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign:"left", padding:"5px 8px", color:"var(--muted)", fontSize:10 }}>Regime</th>
                    {loaded.map((s,i)=>(
                      <th key={s} style={{ textAlign:"right", padding:"5px 8px", color:lColors[i], fontSize:12, fontWeight:700 }}>{s}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {["bull","bear","sideways","all"].map(regime=>(
                    <tr key={regime} style={{ borderTop:"1px solid #1e293b" }}>
                      <td style={{ padding:"7px 8px", color:"var(--muted)", fontWeight:600, textTransform:"capitalize" }}>{regime}</td>
                      {loaded.map((s,i)=>{
                        const row=reports[s]?.regime_stats_20d?.find(x=>x.regime===regime);
                        return (
                          <td key={s} style={{ padding:"7px 8px", textAlign:"right", color:clr(row?.mean), fontWeight:800, fontSize:13 }}>
                            {pct(row?.mean)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ marginTop:14, borderTop:"1px solid #334155", paddingTop:14 }}>
                <div style={{ fontSize:10, color:"var(--muted)", marginBottom:8, textTransform:"uppercase", letterSpacing:0.5 }}>
                  Prob Positive per Regime
                </div>
                {["bull","bear","sideways"].map(regime=>(
                  <div key={regime} style={{ display:"flex", gap:10, alignItems:"center", marginBottom:6 }}>
                    <span style={{ fontSize:11, color:"var(--muted)", minWidth:70, textTransform:"capitalize" }}>{regime}</span>
                    {loaded.map((s,i)=>{
                      const row=reports[s]?.regime_stats_20d?.find(x=>x.regime===regime);
                      const v=row?.prob_positive;
                      return (
                        <span key={s} style={{ fontSize:12, fontWeight:700, color:lColors[i] }}>
                          {v!=null?v+"%":""}
                        </span>
                      );
                    })}
                  </div>
                ))}
              </div>
            </Card>

            {/* Seasonality */}
            <Card icon="S" title="Seasonality">
              {([
                {label:"Best Month",    key:"best_month",    sub:"month",  sub2:"avg_return"},
                {label:"Worst Month",   key:"worst_month",   sub:"month",  sub2:"avg_return"},
                {label:"Best Weekday",  key:"best_weekday",  sub:"day",    sub2:"avg_return"},
                {label:"Worst Weekday", key:"worst_weekday", sub:"day",    sub2:"avg_return"},
              ] as any[]).map((m:any)=>(
                <div key={m.key} style={{ marginBottom:12 }}>
                  <div style={{ fontSize:10, color:"var(--muted)", marginBottom:5, textTransform:"uppercase", letterSpacing:0.5 }}>{m.label}</div>
                  <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                    {loaded.map((s,i)=>{
                      const seas=(reports[s]?.seasonality as any)?.[m.key];
                      return (
                        <div key={s} style={{
                          padding:"4px 12px", background:"var(--bg)",
                          borderRadius:7, border:`1px solid ${lColors[i]}33`,
                        }}>
                          <span style={{ fontFamily:"monospace", fontWeight:700, color:lColors[i], fontSize:11 }}>{s}: </span>
                          <span style={{ fontSize:12, color:"var(--text)", fontWeight:700 }}>
                            {seas ? seas[m.sub]+" ("+seas[m.sub2]?.toFixed(1)+"%)" : ""}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </Card>

            {/* Correlations */}
            <Card icon="C" title="Correlations (1Y vs benchmarks)">
              <div style={{ display:"flex", gap:8, marginBottom:8 }}>
                <span style={{ minWidth:80 }} />
                {loaded.map((s,i)=>(
                  <span key={s} style={{ minWidth:58, textAlign:"center", fontSize:11, fontWeight:700, color:lColors[i], fontFamily:"monospace" }}>{s}</span>
                ))}
              </div>
              {CORR_BM.map(bm=>{
                const vals=loaded.map(s=>{
                  const c=reports[s]?.correlations||{};
                  return (c[bm]??c[bm.toLowerCase()]??null) as number|null;
                });
                if (vals.every(v=>v==null)) return null;
                return (
                  <div key={bm} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:5 }}>
                    <span style={{ fontSize:11, color:"var(--muted)", minWidth:80 }}>{bm}</span>
                    {vals.map((v,i)=>{
                      const abs=v==null?0:Math.abs(v);
                      const bg=v==null?"var(--card)":v>0?`rgba(34,197,94,${abs*0.7})`:`rgba(239,68,68,${abs*0.7})`;
                      return (
                        <div key={i} style={{
                          minWidth:58, textAlign:"center",
                          padding:"4px 6px", borderRadius:6,
                          background:bg, fontSize:12,
                          color:abs>0.3?"var(--text)":"var(--muted)", fontWeight:700,
                        }}>{v==null?"":v.toFixed(2)}</div>
                      );
                    })}
                  </div>
                );
              })}
            </Card>

          </div>

          {/* LLM Verdicts */}
          <div style={{ marginTop:18, background:"var(--card)", border:"1px solid #334155", borderRadius:6, padding:"18px 20px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:14 }}>
              <span style={{ fontSize:15 }}>L</span>
              <h3 style={{ margin:0, fontSize:12, fontWeight:700, color:"var(--muted)", letterSpacing:".04em", textTransform:"uppercase" }}>LLM Verdicts</h3>
            </div>
            {loaded.map((s,i)=>(
              <Verdict key={s} symbol={s} text={String(reports[s]?.llm_verdict||"")} color={lColors[i]} />
            ))}
          </div>

        </div>
      )}
    </div>
  );
}
