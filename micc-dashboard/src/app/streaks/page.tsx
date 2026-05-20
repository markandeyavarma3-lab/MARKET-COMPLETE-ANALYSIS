"use client";
import NavBar from "@/components/NavBar";
import { useState, useEffect, useCallback } from "react";

const DURATIONS = [
  {l:"7D",d:7},{l:"14D",d:14},{l:"20D",d:20},{l:"1M",d:30},{l:"2M",d:60},{l:"3M",d:90},
];
const SORTS = [
  {l:"Streak",v:"streak"},{l:"Conviction",v:"conviction"},{l:"Avg Score",v:"score"},
  {l:"Avg Return",v:"pct"},{l:"Delivery",v:"deliv"},{l:"Consistency",v:"consistency"},
];
const LIMITS = [20,30,50,100];

function grade(c: number):{g:string;color:string} {
  if (c>=20) return {g:"A+",color:"var(--pos)"};
  if (c>=12) return {g:"A", color:"var(--accent)"};
  if (c>=7)  return {g:"B", color:"var(--warn)"};
  if (c>=3)  return {g:"C", color:"var(--orange)"};
  return         {g:"D", color:"var(--neg)"};
}

function TagBadge({tag}:{tag:string}) {
  const s = tag.toLowerCase();
  const c = s.includes("mom")?"var(--accent)":s.includes("del")?"var(--pos)":
            s.includes("brk")||s.includes("break")?"var(--warn)":s.includes("con")?"var(--orange)":"var(--muted)";
  return (
    <span style={{
      fontSize:8, padding:"1px 5px", marginLeft:3,
      background:c+"22", border:`1px solid ${c}66`,
      borderRadius:3, color:c, fontFamily:"monospace", whiteSpace:"nowrap",
    }}>{tag.toUpperCase().slice(0,6)}</span>
  );
}

export default function StreaksPage() {
  const [days,   setDays]   = useState(30);
  const [sortBy, setSortBy] = useState("streak");
  const [screen, setScreen] = useState("");
  const [regime, setRegime] = useState("");
  const [limit,  setLimit]  = useState(30);
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [expand, setExpand] = useState<string|null>(null);

  const load = useCallback(async()=>{
    setLoading(true);
    try {
      const qs = new URLSearchParams({
        days:String(days),sort:sortBy,screen,regime,limit:String(limit),
      });
      const r = await fetch(`/api/streak-extended?${qs}`,{cache:"no-store"});
      setData(await r.json());
    } catch(e){ console.error(e); }
    finally { setLoading(false); }
  },[days,sortBy,screen,regime,limit]);

  useEffect(()=>{load();},[load]);

  const rows    = data?.rows    ??[];
  const tags    = data?.tags    ??[];
  const regimes = data?.regimes ??[];
  const stats   = data?.stats   ??{};
  const hot     = data?.hot     ??[];
  const maxConv = Math.max(...rows.map((r:any)=>Number(r.conviction??0)),1);

  function Btn({active,color,onClick,children}:{active:boolean;color:string;onClick:()=>void;children:any}) {
    return (
      <button onClick={onClick} style={{
        padding:"3px 10px", fontSize:10, cursor:"pointer", fontFamily:"monospace",
        background: active?color+"22":"var(--surface)",
        color:      active?color:"var(--muted)",
        border:`1px solid ${active?color:"var(--border)"}`,
        borderRadius:4,
      }}>{children}</button>
    );
  }

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
            <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"baseline",gap:16,marginBottom:12}}>
          <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,letterSpacing:"0.12em",color:"var(--accent)"}}>
            STREAK LEADERBOARD
          </div>
          <div style={{fontSize:10,fontFamily:"monospace",color:"var(--dim)"}}>
            {stats.total_rows} rows &nbsp;|&nbsp;
            {stats.unique_symbols} symbols &nbsp;|&nbsp;
            {stats.unique_dates} dates &nbsp;|&nbsp;
            latest: {stats.latest_date??"--"}
          </div>
        </div>

        {/* HOT strip */}
        {hot.length>0 && (
          <div style={{display:"flex",gap:8,marginBottom:12,flexWrap:"wrap",alignItems:"center"}}>
            <span style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em"}}>HOT 7D:</span>
            {hot.map((h:any)=>(
              <div key={h.symbol} style={{
                padding:"3px 10px",
                background:"rgba(88,166,255,0.08)",border:"1px solid rgba(88,166,255,0.3)",
                borderRadius:4,fontFamily:"monospace",fontSize:11,
              }}>
                <span style={{color:"var(--accent)",fontWeight:700}}>{h.symbol}</span>
                <span style={{color:"var(--dim)",fontSize:10,marginLeft:8}}>{h.days}d  score {h.avg_score}</span>
              </div>
            ))}
          </div>
        )}

        {/* Filters row */}
        <div style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:14,alignItems:"flex-start"}}>

          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>LOOKBACK</div>
            <div style={{display:"flex",gap:4}}>
              {DURATIONS.map(({l,d})=>(
                <Btn key={d} active={days===d} color="var(--accent)" onClick={()=>setDays(d)}>{l}</Btn>
              ))}
            </div>
          </div>

          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>SORT BY</div>
            <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
              {SORTS.map(({l,v})=>(
                <Btn key={v} active={sortBy===v} color="var(--info)" onClick={()=>setSortBy(v)}>{l}</Btn>
              ))}
            </div>
          </div>

          {tags.length>0 && (
            <div>
              <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>SCREEN</div>
              <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
                <Btn active={screen===""} color="var(--pos)" onClick={()=>setScreen("")}>All</Btn>
                {tags.slice(0,8).map((t:any)=>(
                  <Btn key={t.screen_tags} active={screen===t.screen_tags} color="var(--pos)"
                       onClick={()=>setScreen(t.screen_tags)}>
                    {(t.screen_tags??"").slice(0,10)}
                  </Btn>
                ))}
              </div>
            </div>
          )}

          {regimes.length>1 && (
            <div>
              <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>REGIME</div>
              <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
                <Btn active={regime===""} color="var(--warn)" onClick={()=>setRegime("")}>All</Btn>
                {regimes.map((rg:any)=>(
                  <Btn key={rg.regime} active={regime===rg.regime} color="var(--warn)"
                       onClick={()=>setRegime(rg.regime)}>
                    {(rg.regime??"").slice(0,12)}
                  </Btn>
                ))}
              </div>
            </div>
          )}

          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>SHOW</div>
            <div style={{display:"flex",gap:4}}>
              {LIMITS.map(n=>(
                <Btn key={n} active={limit===n} color="var(--orange)" onClick={()=>setLimit(n)}>{n}</Btn>
              ))}
            </div>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div style={{color:"var(--dim)",fontFamily:"monospace",fontSize:12,padding:40,textAlign:"center"}}>Loading...</div>
        ) : rows.length===0 ? (
          <div style={{color:"var(--muted)",fontFamily:"monospace",fontSize:12,padding:40,textAlign:"center"}}>
            No results. Try wider lookback or fewer filters.
          </div>
        ) : (
          <div style={{overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
              <thead>
                <tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)",letterSpacing:"0.08em"}}>
                  <th style={{textAlign:"left",  padding:"6px 8px",width:28}}>#</th>
                  <th style={{textAlign:"left",  padding:"6px 8px",minWidth:110}}>SYMBOL</th>
                  <th style={{textAlign:"center",padding:"6px 8px"}}>STREAK</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>CONVICTION</th>
                  <th style={{textAlign:"center",padding:"6px 8px",minWidth:100}}>CONSISTENCY</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>AVG SCORE</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>MAX SCORE</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>AVG RET%</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>MAX RET%</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>DELIV%</th>
                  <th style={{textAlign:"left",  padding:"6px 8px"}}>SCREENS</th>
                  <th style={{textAlign:"left",  padding:"6px 8px"}}>REGIME</th>
                  <th style={{textAlign:"right", padding:"6px 8px"}}>LAST SEEN</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row:any,i:number)=>{
                  const cvG  = grade(Number(row.conviction??0));
                  const tags = (row.all_tags??"").split(",").filter(Boolean);
                  const isExp= expand===row.symbol;
                  const cnsty= Number(row.consistency??0);
                  const cBar = Math.round((Number(row.conviction??0)/maxConv)*100);
                  return (
                    <>
                      <tr key={row.symbol} onClick={()=>setExpand(isExp?null:row.symbol)}
                          style={{borderBottom:"1px solid var(--border)",cursor:"pointer",
                                  background:isExp?"rgba(88,166,255,0.05)":undefined}}>
                        <td style={{padding:"7px 8px",color:"var(--dim)"}}>{i+1}</td>
                        <td style={{padding:"7px 8px"}}>
                          <span style={{color:"var(--text)",fontWeight:700,fontSize:12}}>{row.symbol}</span>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"center"}}>
                          <span style={{color:"var(--accent)",fontWeight:700}}>{row.streak_days}d</span>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right"}}>
                          <span style={{color:cvG.color,fontWeight:700,marginRight:5}}>{cvG.g}</span>
                          <span style={{color:"var(--dim)",fontSize:10}}>{Number(row.conviction??0).toFixed(1)}</span>
                          <div style={{height:3,marginTop:3,background:"var(--border)",borderRadius:2}}>
                            <div style={{width:cBar+"%",height:"100%",background:cvG.color,borderRadius:2}}/>
                          </div>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"center"}}>
                          <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:5}}>
                            <div style={{width:50,height:5,background:"var(--border)",borderRadius:2,overflow:"hidden"}}>
                              <div style={{
                                width:Math.min(cnsty,100)+"%",height:"100%",borderRadius:2,
                                background:cnsty>=60?"var(--pos)":cnsty>=40?"var(--warn)":"var(--orange)",
                              }}/>
                            </div>
                            <span style={{color:"var(--dim)",fontSize:10}}>{cnsty.toFixed(0)}%</span>
                          </div>
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right"}}>{Number(row.avg_score??0).toFixed(1)}</td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--accent)"}}>{Number(row.max_score??0).toFixed(1)}</td>
                        <td style={{padding:"7px 8px",textAlign:"right",
                            color:Number(row.avg_pct)>=0?"var(--pos)":"var(--neg)"}}>
                          {Number(row.avg_pct??0)>=0?"+":""}{Number(row.avg_pct??0).toFixed(2)}%
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--pos)"}}>
                          +{Number(row.max_pct??0).toFixed(2)}%
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--info)"}}>
                          {row.avg_deliv!=null?Number(row.avg_deliv).toFixed(1)+"%":"--"}
                        </td>
                        <td style={{padding:"7px 8px"}}>
                          {tags.slice(0,3).map((t:string)=><TagBadge key={t} tag={t}/>)}
                        </td>
                        <td style={{padding:"7px 8px",color:"var(--dim)",fontSize:10}}>
                          {(row.latest_regime??"--").slice(0,12)}
                        </td>
                        <td style={{padding:"7px 8px",textAlign:"right",color:"var(--dim)"}}>{row.last_seen}</td>
                      </tr>
                      {isExp && (
                        <tr key={row.symbol+"_exp"} style={{background:"rgba(88,166,255,0.04)"}}>
                          <td colSpan={13} style={{padding:"10px 16px 12px"}}>
                            <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:12,fontSize:10,marginBottom:8}}>
                              {[
                                {l:"WINDOW",       v:`${row.first_seen} - ${row.last_seen}`,        c:"var(--text)" },
                                {l:"MIN RETURN",   v:`${Number(row.min_pct??0).toFixed(2)}%`,        c:"var(--neg)"  },
                                {l:"MAX DELIVERY", v:`${row.max_deliv!=null?Number(row.max_deliv).toFixed(1)+"%" :"--"}`, c:"var(--info)" },
                                {l:"EPS DAYS",     v:String(row.eps_days??0),                         c:Number(row.eps_days)>0?"var(--warn)":"var(--dim)"},
                                {l:"REGIMES SEEN", v:String(row.regime_count??1),                      c:"var(--text)" },
                              ].map(({l,v,c})=>(
                                <div key={l}>
                                  <div style={{color:"var(--dim)",marginBottom:3}}>{l}</div>
                                  <div style={{color:c,fontWeight:600}}>{v}</div>
                                </div>
                              ))}
                            </div>
                            <div>{tags.map((t:string)=><TagBadge key={t} tag={t}/>)}</div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
