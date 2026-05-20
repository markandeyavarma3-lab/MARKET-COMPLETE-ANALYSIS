"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import NavBar from "@/components/NavBar";

// ── Types ─────────────────────────────────────────────────────────────────────
interface Fund {
  pe_ratio:number|null; pb_ratio:number|null; ps_ratio:number|null;
  roce:number|null; roe:number|null; roa:number|null; roic:number|null;
  debt_equity:number|null; current_ratio:number|null; quick_ratio:number|null;
  interest_coverage:number|null; promoter_pct:number|null;
  fii_pct:number|null; dii_pct:number|null;
  market_cap_cr:number|null; enterprise_value_cr:number|null;
  sales_cr:number|null; profit_cr:number|null; ebitda_cr:number|null;
  eps:number|null; book_value:number|null; div_yield:number|null;
  div_payout:number|null; beta:number|null;
  revenue_growth:number|null; profit_growth:number|null;
  ebitda_growth:number|null; peg_ratio:number|null;
  high_52w:number|null; low_52w:number|null; current_price:number|null;
  face_value:number|null; cash_cr:number|null;
}
interface Tech {
  rsi_14:number|null; adx_14:number|null; macd_line:number|null;
  macd_signal:number|null; atr_14_pct:number|null;
  pct_from_52w_high:number|null; pct_above_sma20:number|null;
  pct_above_sma50:number|null; vol_surge_20d:number|null;
  bb_position:number|null;
}
interface Conv {
  conviction_score:number|null; momentum_score:number|null;
  seasonality_score:number|null; quality_score:number|null;
  delivery_score:number|null; insider_score:number|null;
  news_score:number|null; signal_count:number|null; top_reason:string|null;
}
interface Seas { anchor_mm_dd:string; window_days:number; direction:string; mean_ret:number; win_pct:number; score:number; }
interface Insider { filing_date:string; name:string; transaction_type:string; quantity:number; price:number; value:number; }
interface Ann { announcement_date:string; subject:string; }
interface Peer { symbol:string; conviction:number|null; pe_ratio:number|null; roce:number|null; roe:number|null; market_cap_cr:number|null; }
interface Resp {
  symbol:string; price:{date:string;close:number;volume:number}[];
  tech:Tech|null; fund:Fund|null; conv:Conv|null;
  seas:Seas[]; insider:Insider[]; announcements:Ann[];
  rbi:{date:string;repo_rate:number}|null;
  peers:Peer[]; quality:{score:number;max:number;grade:string};
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fn = (v:number|null,d=1) => v==null?"--":v.toLocaleString("en-IN",{maximumFractionDigits:d});
const pct = (v:number|null) => v==null?"--":`${v>0?"+":""}${v.toFixed(1)}%`;

function MetricCard({label,value,color,sub}:{label:string;value:string;color?:string;sub?:string}) {
  return (
    <div style={{padding:"8px 12px",background:"var(--surface)",border:"1px solid var(--border)",borderRadius:4,minWidth:110}}>
      <div style={{fontFamily:"monospace",fontSize:8,color:"var(--dim)",letterSpacing:"0.1em"}}>{label}</div>
      <div style={{fontFamily:"monospace",fontSize:15,fontWeight:700,color:color||"var(--text)",marginTop:2}}>{value}</div>
      {sub && <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",marginTop:1}}>{sub}</div>}
    </div>
  );
}

function Section({title,children}:{title:string;children:React.ReactNode}) {
  return (
    <div style={{marginBottom:20}}>
      <div style={{fontFamily:"monospace",fontSize:10,fontWeight:700,color:"var(--dim)",
                   letterSpacing:"0.15em",marginBottom:10,paddingBottom:4,
                   borderBottom:"1px solid var(--border)"}}>{title}</div>
      {children}
    </div>
  );
}

const gc = (v:number|null,good:number,bad:number,higher=true) => {
  if(v==null) return "var(--dim)";
  if(higher) return v>=good?"var(--bull)":v<=bad?"var(--bear)":"var(--text)";
  return v<=good?"var(--bull)":v>=bad?"var(--bear)":"var(--text)";
};

// ── Page ──────────────────────────────────────────────────────────────────────
export default function StockPage() {
  const { symbol } = useParams() as { symbol: string };
  const [data, setData] = useState<Resp|null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"overview"|"fundamentals"|"seasonality"|"insider"|"peers">("overview");

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    fetch(`/api/stock/${symbol}`)
      .then(r=>r.json()).then(d=>{setData(d);setLoading(false);})
      .catch(()=>setLoading(false));
  }, [symbol]);

  if (loading) return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
      <div style={{padding:60,textAlign:"center",fontFamily:"monospace",fontSize:12,color:"var(--dim)"}}>
        Loading {symbol}...
      </div>
    </div>
  );

  if (!data) return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      
      <div style={{padding:60,textAlign:"center",fontFamily:"monospace",fontSize:12,color:"var(--bear)"}}>
        Symbol not found: {symbol}
      </div>
    </div>
  );

  const { fund, tech, conv, seas, insider, announcements, peers, quality, rbi } = data;
  const latest = data.price[data.price.length-1];
  const prev    = data.price[data.price.length-2];
  const chg     = latest && prev ? ((latest.close - prev.close)/prev.close*100) : null;
  const chgC    = chg==null?"var(--dim)":chg>=0?"var(--bull)":"var(--bear)";

  const gradeColor = (g:string) =>
    g==="A"?"var(--bull)":g==="B"?"var(--accent)":g==="C"?"var(--warn)":"var(--bear)";

  const TABS = ["overview","fundamentals","seasonality","insider","peers"] as const;

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)",color:"var(--text)"}}>
      

      {/* Symbol header */}
      <div style={{background:"var(--surface)",borderBottom:"1px solid var(--border)",padding:"12px 20px"}}>
        <div style={{maxWidth:1400,margin:"0 auto",display:"flex",alignItems:"center",gap:20,flexWrap:"wrap"}}>
          <div>
            <div style={{fontFamily:"monospace",fontSize:22,fontWeight:700,color:"var(--accent)",letterSpacing:"0.1em"}}>
              {data.symbol}
            </div>
            <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginTop:2}}>
              {fund?.market_cap_cr ? `MCap: ${fn(fund.market_cap_cr,0)} Cr` : ""}
              {fund?.face_value ? `  |  FV: ${fund.face_value}` : ""}
              {rbi ? `  |  Repo: ${rbi.repo_rate}%` : ""}
            </div>
          </div>

          {latest && (
            <>
              <div style={{textAlign:"right"}}>
                <div style={{fontFamily:"monospace",fontSize:24,fontWeight:700,color:"var(--text)"}}>
                  {fn(latest.close,2)}
                </div>
                <div style={{fontFamily:"monospace",fontSize:12,color:chgC}}>
                  {pct(chg)} today
                </div>
              </div>

              <MetricCard label="52W HIGH" value={fn(fund?.high_52w,2)}
                color={latest.close>=(fund?.high_52w||999)?"var(--bull)":"var(--text)"} />
              <MetricCard label="52W LOW"  value={fn(fund?.low_52w,2)}
                color={latest.close<=(fund?.low_52w||0)?"var(--bear)":"var(--text)"} />
              <MetricCard label="FROM 52W HIGH" value={pct(tech?.pct_from_52w_high)}
                color={gc(tech?.pct_from_52w_high,-5,-25)} />
            </>
          )}

          {/* Quality grade */}
          {quality.max > 0 && (
            <div style={{padding:"8px 16px",background:"var(--surface)",
                         border:`2px solid ${gradeColor(quality.grade)}`,borderRadius:6,
                         textAlign:"center"}}>
              <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)"}}>QUALITY</div>
              <div style={{fontFamily:"monospace",fontSize:28,fontWeight:700,color:gradeColor(quality.grade)}}>
                {quality.grade}
              </div>
              <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)"}}>
                {quality.score}/{quality.max} checks
              </div>
            </div>
          )}

          {/* Conviction */}
          {conv?.conviction_score != null && (
            <div style={{padding:"8px 16px",background:"var(--surface)",
                         border:"1px solid var(--border)",borderRadius:6,textAlign:"center"}}>
              <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)"}}>CONVICTION</div>
              <div style={{fontFamily:"monospace",fontSize:24,fontWeight:700,color:"var(--accent)"}}>
                {fn(conv.conviction_score,0)}
              </div>
              <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)"}}>/ 100</div>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div style={{background:"var(--surface)",borderBottom:"1px solid var(--border)",padding:"0 20px"}}>
        <div style={{maxWidth:1400,margin:"0 auto",display:"flex",gap:0}}>
          {TABS.map(t => (
            <button key={t} onClick={()=>setTab(t)} style={{
              padding:"10px 16px",fontFamily:"monospace",fontSize:10,cursor:"pointer",
              background:"transparent",border:"none",
              borderBottom:`2px solid ${tab===t?"var(--accent)":"transparent"}`,
              color:tab===t?"var(--accent)":"var(--dim)",
              letterSpacing:"0.08em",fontWeight:tab===t?700:400,
            }}>{t.toUpperCase()}</button>
          ))}
        </div>
      </div>

      <div style={{padding:"16px 20px",maxWidth:1400,margin:"0 auto"}}>

        {/* ── OVERVIEW TAB ── */}
        {tab==="overview" && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:16}}>

            {/* Technicals */}
            <div>
              <Section title="TECHNICALS">
                <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
                  <MetricCard label="RSI 14" value={fn(tech?.rsi_14,0)}
                    color={tech?.rsi_14==null?"var(--dim)":tech.rsi_14>70?"var(--bear)":tech.rsi_14<30?"var(--bull)":"var(--text)"} />
                  <MetricCard label="ADX 14" value={fn(tech?.adx_14,0)}
                    color={(tech?.adx_14||0)>25?"var(--bull)":"var(--dim)"} />
                  <MetricCard label="MACD" value={(tech?.macd_line||0)>(tech?.macd_signal||0)?"BULL":"BEAR"}
                    color={(tech?.macd_line||0)>(tech?.macd_signal||0)?"var(--bull)":"var(--bear)"} />
                  <MetricCard label="ATR%" value={fn(tech?.atr_14_pct,2)} />
                  <MetricCard label="BB POS" value={fn(tech?.bb_position,2)} />
                  <MetricCard label="VOL SURGE" value={fn(tech?.vol_surge_20d,1)}
                    color={(tech?.vol_surge_20d||0)>1.5?"var(--bull)":"var(--dim)"} />
                  <MetricCard label="SMA20" value={pct(tech?.pct_above_sma20)}
                    color={gc(tech?.pct_above_sma20,0,-10)} />
                  <MetricCard label="SMA50" value={pct(tech?.pct_above_sma50)}
                    color={gc(tech?.pct_above_sma50,0,-10)} />
                </div>
              </Section>
            </div>

            {/* Key fundamentals */}
            <div>
              <Section title="KEY FUNDAMENTALS">
                <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
                  <MetricCard label="P/E" value={fn(fund?.pe_ratio)} color={gc(fund?.pe_ratio,15,40,false)} />
                  <MetricCard label="P/B" value={fn(fund?.pb_ratio)} color={gc(fund?.pb_ratio,1,5,false)} />
                  <MetricCard label="ROCE%" value={fn(fund?.roce)} color={gc(fund?.roce,15,8)} />
                  <MetricCard label="ROE%"  value={fn(fund?.roe)}  color={gc(fund?.roe,15,8)} />
                  <MetricCard label="D/E"   value={fn(fund?.debt_equity)} color={gc(fund?.debt_equity,0.5,2,false)} />
                  <MetricCard label="PROMO%" value={fn(fund?.promoter_pct)} color={gc(fund?.promoter_pct,60,40)} />
                  <MetricCard label="REV GR%" value={pct(fund?.revenue_growth)} color={gc(fund?.revenue_growth,15,0)} />
                  <MetricCard label="PAT GR%" value={pct(fund?.profit_growth)} color={gc(fund?.profit_growth,15,0)} />
                </div>
              </Section>
            </div>

            {/* Conviction breakdown */}
            <div>
              <Section title="CONVICTION LAYERS">
                {conv ? (
                  <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
                    {[
                      ["MOMENTUM",   conv.momentum_score],
                      ["SEASONAL",   conv.seasonality_score],
                      ["QUALITY",    conv.quality_score],
                      ["DELIVERY",   conv.delivery_score],
                      ["INSIDER",    conv.insider_score],
                      ["NEWS",       conv.news_score],
                    ].map(([l,v]) => (
                      <MetricCard key={l as string} label={l as string} value={fn(v as number|null)}
                        color={(v as number||0)>5?"var(--bull)":(v as number||0)>2?"var(--warn)":"var(--dim)"} />
                    ))}
                    {conv.top_reason && (
                      <div style={{width:"100%",padding:"6px 10px",background:"rgba(0,212,170,0.06)",
                                   border:"1px solid var(--accent)",borderRadius:4,
                                   fontFamily:"monospace",fontSize:10,color:"var(--accent)"}}>
                        {conv.top_reason}
                      </div>
                    )}
                  </div>
                ) : <div style={{fontFamily:"monospace",fontSize:11,color:"var(--dim)"}}>No conviction data</div>}
              </Section>

              {/* Recent announcements */}
              {announcements.length > 0 && (
                <Section title="RECENT ANNOUNCEMENTS">
                  {announcements.slice(0,4).map((a,i) => (
                    <div key={i} style={{marginBottom:6,padding:"5px 8px",
                                          background:"var(--surface)",border:"1px solid var(--border)",borderRadius:4}}>
                      <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)"}}>{a.announcement_date}</div>
                      <div style={{fontFamily:"monospace",fontSize:11,color:"var(--text)",marginTop:1}}>{a.subject}</div>
                    </div>
                  ))}
                </Section>
              )}
            </div>
          </div>
        )}

        {/* ── FUNDAMENTALS TAB ── */}
        {tab==="fundamentals" && fund && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>

            <Section title="VALUATION">
              <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
                <MetricCard label="P/E"          value={fn(fund.pe_ratio)}      color={gc(fund.pe_ratio,15,40,false)} />
                <MetricCard label="P/B"          value={fn(fund.pb_ratio)}      color={gc(fund.pb_ratio,1,5,false)} />
                <MetricCard label="P/S"          value={fn(fund.ps_ratio)}      color={gc(fund.ps_ratio,1,5,false)} />
                <MetricCard label="PEG"          value={fn(fund.peg_ratio)}     color={gc(fund.peg_ratio,1,2,false)} />
                <MetricCard label="EPS"          value={fn(fund.eps,2)} />
                <MetricCard label="BOOK VALUE"   value={fn(fund.book_value,2)} />
                <MetricCard label="FACE VALUE"   value={fn(fund.face_value,2)} />
                <MetricCard label="DIV YIELD%"   value={fn(fund.div_yield,2)}   color="var(--warn)" />
                <MetricCard label="DIV PAYOUT%"  value={fn(fund.div_payout,1)} />
              </div>
            </Section>

            <Section title="PROFITABILITY">
              <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
                <MetricCard label="ROCE%"   value={fn(fund.roce)}    color={gc(fund.roce,15,8)} />
                <MetricCard label="ROE%"    value={fn(fund.roe)}     color={gc(fund.roe,15,8)} />
                <MetricCard label="ROA%"    value={fn(fund.roa)}     color={gc(fund.roa,10,5)} />
                <MetricCard label="ROIC%"   value={fn(fund.roic)}    color={gc(fund.roic,15,8)} />
                <MetricCard label="EBITDA%GR" value={pct(fund.ebitda_growth)} color={gc(fund.ebitda_growth,15,0)} />
                <MetricCard label="REV GR%"  value={pct(fund.revenue_growth)} color={gc(fund.revenue_growth,15,0)} />
                <MetricCard label="PAT GR%"  value={pct(fund.profit_growth)}  color={gc(fund.profit_growth,15,0)} />
              </div>
            </Section>

            <Section title="SIZE AND SCALE">
              <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
                <MetricCard label="MCAP CR"    value={fn(fund.market_cap_cr,0)} />
                <MetricCard label="EV CR"      value={fn(fund.enterprise_value_cr,0)} />
                <MetricCard label="SALES CR"   value={fn(fund.sales_cr,0)} />
                <MetricCard label="PROFIT CR"  value={fn(fund.profit_cr,0)} />
                <MetricCard label="EBITDA CR"  value={fn(fund.ebitda_cr,0)} />
                <MetricCard label="CASH CR"    value={fn(fund.cash_cr,0)} />
                <MetricCard label="BETA"       value={fn(fund.beta,2)} />
              </div>
            </Section>

            <Section title="FINANCIAL HEALTH">
              <div style={{display:"flex",flexWrap:"wrap",gap:8}}>
                <MetricCard label="D/E"          value={fn(fund.debt_equity,2)} color={gc(fund.debt_equity,0.5,2,false)} />
                <MetricCard label="CURR RATIO"   value={fn(fund.current_ratio,2)} color={gc(fund.current_ratio,2,1)} />
                <MetricCard label="QUICK RATIO"  value={fn(fund.quick_ratio,2)}   color={gc(fund.quick_ratio,1,0.5)} />
                <MetricCard label="INT COV"      value={fn(fund.interest_coverage,1)} color={gc(fund.interest_coverage,3,1.5)} />
                <MetricCard label="PROMOTER%"    value={fn(fund.promoter_pct,1)} color={gc(fund.promoter_pct,60,40)} />
                <MetricCard label="FII%"         value={fn(fund.fii_pct,1)}      color="var(--info)" />
                <MetricCard label="DII%"         value={fn(fund.dii_pct,1)} />
              </div>
            </Section>
          </div>
        )}

        {/* ── SEASONALITY TAB ── */}
        {tab==="seasonality" && (
          <div>
            {seas.length === 0 ? (
              <div style={{padding:40,textAlign:"center",fontFamily:"monospace",fontSize:12,color:"var(--dim)"}}>
                No significant seasonal patterns (need 10+ years data + FDR correction)
              </div>
            ) : (
              <div style={{borderRadius:6,border:"1px solid var(--border)",overflowX:"auto"}}>
                <table style={{width:"100%",borderCollapse:"collapse"}}>
                  <thead>
                    <tr>
                      {["DATE","DAYS","DIR","MEAN RET","WIN%","SCORE"].map(h => (
                        <th key={h} style={{padding:"8px 12px",background:"var(--surface)",
                                             fontFamily:"monospace",fontSize:10,color:"var(--dim)",
                                             textAlign:h==="DATE"||h==="DIR"?"left":"right",
                                             borderBottom:"2px solid var(--border)"}}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {seas.map((s,i) => (
                      <tr key={i} style={{borderBottom:"1px solid var(--border)"}}
                        onMouseEnter={e=>(e.currentTarget.style.background="rgba(255,255,255,0.02)")}
                        onMouseLeave={e=>(e.currentTarget.style.background="transparent")}>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11}}>{s.anchor_mm_dd}</td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,textAlign:"right"}}>{s.window_days}d</td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,
                                     color:s.direction==="UP"?"var(--bull)":"var(--bear)",fontWeight:700}}>{s.direction}</td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,textAlign:"right",
                                     color:s.mean_ret>0?"var(--bull)":"var(--bear)"}}>
                          {s.mean_ret>0?"+":""}{s.mean_ret}%
                        </td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,textAlign:"right",
                                     color:s.win_pct>=60?"var(--bull)":s.win_pct<=40?"var(--bear)":"var(--text)"}}>
                          {s.win_pct}%
                        </td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,textAlign:"right",
                                     color:"var(--accent)"}}>{s.score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── INSIDER TAB ── */}
        {tab==="insider" && (
          <div>
            {insider.length === 0 ? (
              <div style={{padding:40,textAlign:"center",fontFamily:"monospace",fontSize:12,color:"var(--dim)"}}>
                No recent insider transactions
              </div>
            ) : (
              <div style={{borderRadius:6,border:"1px solid var(--border)",overflowX:"auto"}}>
                <table style={{width:"100%",borderCollapse:"collapse"}}>
                  <thead>
                    <tr>
                      {["DATE","NAME","TYPE","QTY","PRICE","VALUE CR"].map(h => (
                        <th key={h} style={{padding:"8px 12px",background:"var(--surface)",
                                             fontFamily:"monospace",fontSize:10,color:"var(--dim)",
                                             textAlign:"left",borderBottom:"2px solid var(--border)"}}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {insider.map((ins,i) => (
                      <tr key={i} style={{borderBottom:"1px solid var(--border)"}}
                        onMouseEnter={e=>(e.currentTarget.style.background="rgba(255,255,255,0.02)")}
                        onMouseLeave={e=>(e.currentTarget.style.background="transparent")}>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11}}>{ins.filing_date}</td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11}}>{ins.name}</td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,fontWeight:700,
                                     color:ins.transaction_type==="BUY"?"var(--bull)":"var(--bear)"}}>
                          {ins.transaction_type}
                        </td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,textAlign:"right"}}>{fn(ins.quantity,0)}</td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,textAlign:"right"}}>{fn(ins.price,2)}</td>
                        <td style={{padding:"7px 12px",fontFamily:"monospace",fontSize:11,textAlign:"right"}}>{fn(ins.value/1e7,2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── PEERS TAB ── */}
        {tab==="peers" && (
          <div style={{borderRadius:6,border:"1px solid var(--border)",overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse"}}>
              <thead>
                <tr>
                  {["SYMBOL","CONVICTION","P/E","ROCE%","ROE%","MCAP CR"].map(h => (
                    <th key={h} style={{padding:"8px 12px",background:"var(--surface)",
                                         fontFamily:"monospace",fontSize:10,color:"var(--dim)",
                                         textAlign:h==="SYMBOL"?"left":"right",
                                         borderBottom:"2px solid var(--border)"}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {peers.map((p,i) => (
                  <tr key={i} style={{borderBottom:"1px solid var(--border)"}}
                    onMouseEnter={e=>(e.currentTarget.style.background="rgba(255,255,255,0.02)")}
                    onMouseLeave={e=>(e.currentTarget.style.background="transparent")}>
                    <td style={{padding:"7px 12px"}}>
                      <a href={`/stocks/${p.symbol}`} style={{
                        fontFamily:"monospace",fontSize:12,fontWeight:700,
                        color:"var(--text)",textDecoration:"none"}}>{p.symbol}</a>
                    </td>
                    <td style={{padding:"7px 12px",textAlign:"right",fontFamily:"monospace",
                                 fontSize:11,color:"var(--accent)"}}>{fn(p.conviction)}</td>
                    <td style={{padding:"7px 12px",textAlign:"right",fontFamily:"monospace",fontSize:11}}>{fn(p.pe_ratio)}</td>
                    <td style={{padding:"7px 12px",textAlign:"right",fontFamily:"monospace",fontSize:11,
                                 color:gc(p.roce,15,8)}}>{fn(p.roce)}</td>
                    <td style={{padding:"7px 12px",textAlign:"right",fontFamily:"monospace",fontSize:11,
                                 color:gc(p.roe,15,8)}}>{fn(p.roe)}</td>
                    <td style={{padding:"7px 12px",textAlign:"right",fontFamily:"monospace",fontSize:11}}>{fn(p.market_cap_cr,0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
