"use client";
import { useEffect, useState, useMemo } from "react";
import NavBar from "@/components/NavBar";

interface ConvRow {
  symbol:           string;
  conviction_score: number;
  momentum_score:   number;
  seasonality_score:number;
  quality_score:    number;
  delivery_score:   number;
  insider_score:    number;
  news_score:       number;
  fundamental_score:number;
  signal_count:     number;
  top_reason:       string;
  active_tags:      string;
  n_layers:         number;
  rsi_14:           number | null;
  adx_14:           number | null;
  macd_bullish:     boolean;
  pct_from_52w_high:number | null;
  latest_close:     number | null;
  today_pattern:    { direction:string; mean_ret:number; win_pct:number; window_days:number } | null;
  today_signals:    string;
}
interface Resp { rows:ConvRow[]; total:number; regime:string; nifty:number; generated_at:string; }

// Layer definitions matching REAL symbol_conviction columns
const LAYERS = [
  { k:"M", label:"Momentum",   color:"#58a6ff", key:"momentum_score"    },
  { k:"S", label:"Seasonal",   color:"#39d353", key:"seasonality_score" },
  { k:"Q", label:"Quality",    color:"#3fb950", key:"quality_score"     },
  { k:"D", label:"Delivery",   color:"#a371f7", key:"delivery_score"    },
  { k:"I", label:"Insider",    color:"#f85149", key:"insider_score"     },
  { k:"N", label:"News",       color:"#e3b341", key:"news_score"        },
  { k:"F", label:"Fundament.", color:"#ffa657", key:"fundamental_score" },
];

const sc = (s:number) => s>=75?"#3fb950":s>=50?"#58a6ff":s>=30?"#e3b341":"#8b949e";
const sg = (s:number) => s>=80?"A+":s>=65?"A":s>=50?"B":s>=35?"C":"D";
const fn = (v:number|null) => v==null?"--":v.toLocaleString("en-IN",{maximumFractionDigits:2});

function Bar({score}:{score:number}) {
  const c = sc(score);
  return (
    <div style={{display:"flex",alignItems:"center",gap:6}}>
      <div style={{width:66,height:5,background:"var(--border)",borderRadius:3,overflow:"hidden"}}>
        <div style={{width:`${Math.min(100,score)}%`,height:"100%",background:c,borderRadius:3}}/>
      </div>
      <span style={{fontFamily:"monospace",fontSize:12,color:c,fontWeight:700,minWidth:26}}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

function Dots({tags}:{tags:string}) {
  const t = tags ? tags.split(",").filter(Boolean) : [];
  return (
    <div style={{display:"flex",gap:3}}>
      {LAYERS.map(({k,label,color})=>{
        const on = t.includes(k);
        return (
          <div key={k} title={label} style={{
            width:15,height:15,borderRadius:"50%",fontSize:8,
            fontFamily:"monospace",fontWeight:700,
            background:on?color:"var(--border)",
            color:on?"#000":"var(--dim)",
            display:"flex",alignItems:"center",justifyContent:"center",
          }}>{k}</div>
        );
      })}
    </div>
  );
}

export default function ConvictionPage() {
  const [data,    setData]    = useState<Resp|null>(null);
  const [loading, setLoading] = useState(true);
  const [search,  setSearch]  = useState("");
  const [minS,    setMinS]    = useState(0);
  const [sortBy,  setSortBy]  = useState<keyof ConvRow>("conviction_score");
  const [asc,     setAsc]     = useState(false);
  const [expLayers,setExpL]   = useState(false);
  const [filter,  setFilter]  = useState("ALL");

  useEffect(()=>{
    setLoading(true);
    fetch(`/api/conviction?min=${minS}&limit=300`)
      .then(r=>r.json()).then(d=>{setData(d);setLoading(false);})
      .catch(()=>setLoading(false));
  },[minS]);

  const rows = useMemo(()=>{
    if (!data?.rows) return [];
    let r=[...data.rows];
    if (search) { const q=search.toUpperCase(); r=r.filter(x=>x.symbol.includes(q)); }
    if (filter!=="ALL") {
      r=r.filter(x=>{
        if (filter==="PATTERN") return x.today_pattern!=null;
        if (filter==="SIGNAL")  return x.today_signals.length>0;
        return (x.active_tags||"").split(",").includes(filter);
      });
    }
    const m=asc?1:-1;
    return r.sort((a,b)=>{
      const av=(a as any)[sortBy], bv=(b as any)[sortBy];
      return typeof av==="string"?m*av.localeCompare(bv):m*((+av||0)-(+bv||0));
    });
  },[data,search,filter,sortBy,asc]);

  function Th({col,label,right}:{col:keyof ConvRow;label:string;right?:boolean}) {
    const active=sortBy===col;
    return (
      <th onClick={()=>{if(sortBy===col)setAsc(a=>!a);else{setSortBy(col);setAsc(false);}}}
        style={{padding:"8px 10px",cursor:"pointer",userSelect:"none",
          textAlign:right?"right":"left",
          color:active?"var(--accent)":"var(--dim)",
          fontFamily:"monospace",fontSize:10,fontWeight:700,letterSpacing:"0.08em",
          background:"var(--surface)",
          borderBottom:`2px solid ${active?"var(--accent)":"var(--border)"}`,
          whiteSpace:"nowrap"}}>
        {label}{active?(asc?" ^":" v"):""}
      </th>
    );
  }

  const rc=data?.regime==="BULLISH"?"#3fb950":data?.regime==="BEARISH"?"#f85149":"#e3b341";

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)",color:"var(--text)"}}>
      <NavBar />
      <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"center",gap:14,flexWrap:"wrap",marginBottom:14}}>
          <div>
            <div style={{fontFamily:"monospace",fontSize:17,fontWeight:700,
                         letterSpacing:"0.12em",color:"var(--accent)"}}>CONVICTION SCREENER</div>
            <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginTop:1}}>
              7-layer scoring &mdash; {rows.length} shown{data?` of ${data.total}`:""}
            </div>
          </div>
          <div style={{padding:"5px 12px",background:"var(--surface)",
                       border:`1px solid ${rc}`,borderRadius:6}}>
            <div style={{fontFamily:"monospace",fontSize:8,color:"var(--dim)"}}>REGIME</div>
            <div style={{fontFamily:"monospace",fontSize:12,fontWeight:700,color:rc}}>
              {data?.regime??"--"}
            </div>
          </div>
          <div style={{padding:"5px 12px",background:"var(--surface)",
                       border:"1px solid var(--border)",borderRadius:6}}>
            <div style={{fontFamily:"monospace",fontSize:8,color:"var(--dim)"}}>NIFTY 50</div>
            <div style={{fontFamily:"monospace",fontSize:12,fontWeight:700,color:"var(--text)"}}>
              {fn(data?.nifty??null)}
            </div>
          </div>
          {data&&<div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",marginLeft:"auto"}}>
            {new Date(data.generated_at).toLocaleTimeString("en-IN")}
          </div>}
        </div>

        {/* Controls */}
        <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10,alignItems:"center"}}>
          <input value={search} onChange={e=>setSearch(e.target.value)}
            placeholder="Symbol..." style={{
              background:"var(--surface)",border:"1px solid var(--border)",
              borderRadius:6,color:"var(--text)",fontFamily:"monospace",
              fontSize:12,padding:"5px 10px",width:140,outline:"none"}} />
          <span style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)"}}>MIN</span>
          {[0,25,40,60,75].map(v=>(
            <button key={v} onClick={()=>setMinS(v)} style={{
              padding:"4px 9px",fontFamily:"monospace",fontSize:10,cursor:"pointer",borderRadius:4,
              background:minS===v?"var(--accent)":"var(--surface)",
              color:minS===v?"#000":"var(--dim)",
              border:`1px solid ${minS===v?"var(--accent)":"var(--border)"}`}}>{v}+</button>
          ))}
          <span style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginLeft:6}}>FILTER</span>
          {["ALL","M","S","Q","D","I","N","F","PATTERN","SIGNAL"].map(tag=>{
            const lm=LAYERS.find(l=>l.k===tag);
            return (
              <button key={tag} onClick={()=>setFilter(tag)} style={{
                padding:"4px 7px",fontFamily:"monospace",fontSize:10,cursor:"pointer",borderRadius:4,
                background:filter===tag?(lm?.color??"var(--accent)"):"var(--surface)",
                color:filter===tag?"#000":"var(--dim)",
                border:`1px solid ${filter===tag?(lm?.color??"var(--accent)"):"var(--border)"}`}}>
                {tag}
              </button>
            );
          })}
          <button onClick={()=>setExpL(v=>!v)} style={{
            marginLeft:"auto",padding:"4px 10px",fontFamily:"monospace",fontSize:10,
            cursor:"pointer",borderRadius:4,
            background:expLayers?"var(--accent)":"var(--surface)",
            color:expLayers?"#000":"var(--dim)",
            border:`1px solid ${expLayers?"var(--accent)":"var(--border)"}`}}>
            {expLayers?"HIDE LAYERS":"SHOW LAYERS"}
          </button>
        </div>

        {/* Legend */}
        <div style={{display:"flex",gap:12,marginBottom:12,flexWrap:"wrap"}}>
          {LAYERS.map(({k,label,color})=>(
            <div key={k} style={{display:"flex",alignItems:"center",gap:4}}>
              <div style={{width:9,height:9,borderRadius:"50%",background:color}}/>
              <span style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)"}}>{k}={label}</span>
            </div>
          ))}
        </div>

        {/* Table */}
        {loading?(
          <div style={{padding:60,textAlign:"center",fontFamily:"monospace",
                       fontSize:13,color:"var(--dim)"}}>Loading...</div>
        ):(
          <div style={{overflowX:"auto",borderRadius:8,border:"1px solid var(--border)"}}>
            <table style={{width:"100%",borderCollapse:"collapse"}}>
              <thead>
                <tr>
                  <th style={{padding:"8px 10px",background:"var(--surface)",width:32,
                               borderBottom:"2px solid var(--border)",
                               fontFamily:"monospace",fontSize:10,color:"var(--dim)",textAlign:"left"}}>#</th>
                  <Th col="symbol"           label="SYMBOL"/>
                  <Th col="conviction_score" label="CONVICTION", "XGB"/>
                  <th style={{padding:"8px 10px",background:"var(--surface)",
                               borderBottom:"2px solid var(--border)",
                               fontFamily:"monospace",fontSize:10,color:"var(--dim)"}}>LAYERS</th>
                  {expLayers&&<>
                    <Th col="momentum_score"    label="MOM"   right/>
                    <Th col="seasonality_score" label="SEAS"  right/>
                    <Th col="quality_score"     label="QUAL"  right/>
                    <Th col="delivery_score"    label="DELIV" right/>
                    <Th col="insider_score"     label="INS"   right/>
                    <Th col="news_score"        label="NEWS"  right/>
                    <Th col="fundamental_score" label="FUND"  right/>
                  </>}
                  <Th col="n_layers"    label="N"    right/>
                  <Th col="signal_count" label="SIG" right/>
                  <Th col="rsi_14"      label="RSI"  right/>
                  <Th col="adx_14"      label="ADX"  right/>
                  <th style={{padding:"8px 10px",background:"var(--surface)",
                               borderBottom:"2px solid var(--border)",
                               fontFamily:"monospace",fontSize:10,color:"var(--dim)",
                               textAlign:"center"}}>MACD</th>
                  <th style={{padding:"8px 10px",background:"var(--surface)",
                               borderBottom:"2px solid var(--border)",
                               fontFamily:"monospace",fontSize:10,color:"var(--dim)"}}>TODAY PAT</th>
                  <Th col="latest_close" label="PRICE" right/>
                </tr>
              </thead>
              <tbody>
                {rows.map((row,i)=>{
                  const grade=sg(row.conviction_score);
                  const gc=sc(row.conviction_score);
                  const rsiC=row.rsi_14==null?"var(--dim)":row.rsi_14>70?"#f85149":row.rsi_14<30?"#3fb950":"var(--text)";
                  const stags=row.today_signals?row.today_signals.split(/[,|]/).filter(Boolean):[];
                  return (
                    <tr key={row.symbol}
                      style={{borderBottom:"1px solid var(--border)"}}
                      onMouseEnter={e=>(e.currentTarget.style.background="rgba(255,255,255,0.025)")}
                      onMouseLeave={e=>(e.currentTarget.style.background="transparent")}>
                      <td style={{padding:"7px 10px",fontFamily:"monospace",fontSize:11,color:"var(--dim)"}}>{i+1}</td>
                      <td style={{padding:"7px 10px"}}>
                        <div style={{display:"flex",alignItems:"center",gap:7}}>
                          <a href={`/stocks/${row.symbol}`} style={{
                            fontFamily:"monospace",fontSize:13,fontWeight:700,
                            color:"var(--text)",textDecoration:"none"}}>{row.symbol}</a>
                          <span style={{fontFamily:"monospace",fontSize:10,fontWeight:700,
                                        color:gc,padding:"1px 5px",
                                        background:gc+"22",borderRadius:3}}>{grade}</span>
                        </div>
                      </td>
                      <td style={{padding:"7px 10px"}}><Bar score={row.conviction_score}/></td>
                      <td style={{padding:"7px 10px"}}><Dots tags={row.active_tags}/></td>
                      {expLayers&&<>
                        {(["momentum_score","seasonality_score","quality_score",
                           "delivery_score","insider_score","news_score",
                           "fundamental_score"] as (keyof ConvRow)[]).map(k=>{
                          const v=row[k] as number;
                          return (
                            <td key={k} style={{padding:"7px 10px",textAlign:"right",
                                                fontFamily:"monospace",fontSize:11}}>
                              {v>0?<span style={{color:sc(v*10)}}>{v.toFixed(1)}</span>
                                  :<span style={{color:"var(--border)"}}>--</span>}
                            </td>
                          );
                        })}
                      </>}
                      <td style={{padding:"7px 10px",textAlign:"right",fontFamily:"monospace",
                                  fontSize:12,color:row.n_layers>=5?"#3fb950":row.n_layers>=3?"#e3b341":"var(--dim)"}}>
                        {row.n_layers}
                      </td>
                      <td style={{padding:"7px 10px",textAlign:"right",fontFamily:"monospace",
                                  fontSize:12,color:"var(--accent)"}}>{row.signal_count||"--"}</td>
                      <td style={{padding:"7px 10px",textAlign:"right",fontFamily:"monospace",fontSize:12,color:rsiC}}>
                        {row.rsi_14!=null?row.rsi_14.toFixed(0):"--"}
                      </td>
                      <td style={{padding:"7px 10px",textAlign:"right",fontFamily:"monospace",fontSize:12,
                                  color:(row.adx_14??0)>25?"#3fb950":"var(--dim)"}}>
                        {row.adx_14!=null?row.adx_14.toFixed(0):"--"}
                      </td>
                      <td style={{padding:"7px 10px",textAlign:"center"}}>
                        <span style={{fontFamily:"monospace",fontSize:10,padding:"2px 6px",borderRadius:3,
                                      background:row.macd_bullish?"rgba(63,185,80,0.15)":"rgba(248,81,73,0.15)",
                                      color:row.macd_bullish?"#3fb950":"#f85149"}}>
                          {row.macd_bullish?"BULL":"BEAR"}
                        </span>
                      </td>
                      <td style={{padding:"7px 10px",minWidth:130}}>
                        {row.today_pattern?(
                          <span style={{fontFamily:"monospace",fontSize:10}}>
                            <span style={{color:row.today_pattern.direction==="UP"?"#3fb950":"#f85149",
                                          fontWeight:700,marginRight:3}}>{row.today_pattern.direction}</span>
                            <span style={{color:row.today_pattern.mean_ret>0?"#3fb950":"#f85149"}}>
                              {row.today_pattern.mean_ret>0?"+":""}{row.today_pattern.mean_ret}%
                            </span>
                            <span style={{color:"var(--dim)"}}> {row.today_pattern.win_pct}%w</span>
                            <span style={{color:"var(--dim)",fontSize:9}}> {row.today_pattern.window_days}d</span>
                          </span>
                        ):<span style={{color:"var(--border)",fontFamily:"monospace",fontSize:10}}>--</span>}
                      </td>
                      <td style={{padding:"7px 10px",textAlign:"right",fontFamily:"monospace",
                                  fontSize:12,color:"var(--text)"}}>{fn(row.latest_close)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {rows.length===0&&(
              <div style={{padding:40,textAlign:"center",fontFamily:"monospace",
                           fontSize:12,color:"var(--dim)"}}>No symbols match filters.</div>
            )}
          </div>
        )}

        {/* Stats */}
        {data&&(
          <div style={{display:"flex",gap:10,marginTop:12,flexWrap:"wrap"}}>
            {([["TOTAL",data.total],["SHOWING",rows.length],
               ["75+",data.rows.filter(r=>r.conviction_score>=75).length],
               ["50+",data.rows.filter(r=>r.conviction_score>=50).length],
               ["PATTERN",data.rows.filter(r=>r.today_pattern!=null).length],
               ["SIGNAL",data.rows.filter(r=>r.today_signals.length>0).length],
            ] as [string,number][]).map(([l,v])=>(
              <div key={l} style={{padding:"5px 12px",background:"var(--surface)",
                                   border:"1px solid var(--border)",borderRadius:6}}>
                <div style={{fontFamily:"monospace",fontSize:8,color:"var(--dim)",letterSpacing:"0.1em"}}>{l}</div>
                <div style={{fontFamily:"monospace",fontSize:15,fontWeight:700,color:"var(--accent)"}}>{v}</div>
              </div>
            ))}
            {data.rows[0]?.top_reason&&(
              <div style={{padding:"5px 12px",background:"var(--surface)",
                           border:"1px solid var(--border)",borderRadius:6,flex:1}}>
                <div style={{fontFamily:"monospace",fontSize:8,color:"var(--dim)"}}>TOP #1 REASON</div>
                <div style={{fontFamily:"monospace",fontSize:11,color:"var(--accent)"}}>
                  {data.rows[0]?.top_reason}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
