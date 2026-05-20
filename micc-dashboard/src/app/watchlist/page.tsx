"use client";
import NavBar from "@/components/NavBar";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

//  Types 
interface WatchList { id:string; name:string; symbols:string[]; alerts:Alert[]; }
interface Alert { id:string; symbol:string; type:string; value?:number; low?:number; high?:number; note?:string; }
interface PriceData { symbol:string; close:number; date:string; volume:number; pct_1d:number; }
interface TechData  { symbol:string; rsi_14:number; adx_14:number; pct_above_sma20:number; vol_surge_20d:number; macd_line:number; macd_signal:number; atr_14_pct:number; }
interface Triggered { symbol:string; type:string; reason:string; close:number; listId:string; listName:string; }

const C = {
  green:"#4ade80",red:"#f87171",cyan:"#22d3ee",yellow:"#facc15",orange:"var(--orange)",
  dim:"var(--dim)",primary:"var(--text)",
  border:"var(--border)",surface:"var(--card)",
};

const ALERT_TYPES = [
  {id:"price_above",   label:"Price Above",    fields:["value"],          desc:"Triggers when price >= value"},
  {id:"price_below",   label:"Price Below",    fields:["value"],          desc:"Triggers when price <= value"},
  {id:"price_band",    label:"Price Band",     fields:["low","high"],     desc:"Triggers when price is inside low-high band"},
  {id:"pct_move_up",   label:"% Move Up",      fields:["value"],          desc:"Triggers when 1d gain >= value%"},
  {id:"pct_move_down", label:"% Move Down",    fields:["value"],          desc:"Triggers when 1d drop >= value%"},
  {id:"volume_surge",  label:"Volume Surge",   fields:["value"],          desc:"Triggers when vol surge 20d >= value x"},
  {id:"rsi_above",     label:"RSI Above",      fields:["value"],          desc:"Triggers when RSI 14 >= value"},
  {id:"rsi_below",     label:"RSI Below",      fields:["value"],          desc:"Triggers when RSI 14 <= value"},
  {id:"above_sma20",   label:"Above SMA20",    fields:[],                 desc:"Triggers when price crosses above SMA20"},
  {id:"below_sma20",   label:"Below SMA20",    fields:[],                 desc:"Triggers when price drops below SMA20"},
];

function col(v:number|null|undefined){return(v??0)>=0?C.green:C.red;}
function pct(v:number|null|undefined,d=2){if(v==null)return"--";return`${v>=0?"+":""}${v.toFixed(d)}%`;}
function num(v:number|null|undefined,d=2){if(v==null)return"--";return v.toFixed(d);}

function Card({title,children,accent,action}:{title?:string;children:React.ReactNode;accent?:string;action?:React.ReactNode}){
  return(
    <div style={{background:C.surface,border:`1px solid ${accent||C.border}`,borderRadius:8,marginBottom:14,overflow:"hidden"}}>
      {title&&<div style={{padding:"10px 16px",display:"flex",justifyContent:"space-between",alignItems:"center",borderBottom:`1px solid ${C.border}`}}>
        <span style={{fontSize:11,fontWeight:700,letterSpacing:1.4,color:accent||C.cyan,textTransform:"uppercase"}}>{title}</span>
        {action}
      </div>}
      <div style={{padding:"12px 16px"}}>{children}</div>
    </div>
  );
}

function AlertBadge({type}:{type:string}){
  const colors:Record<string,string> = {
    price_above:C.green,price_below:C.red,price_band:C.yellow,
    pct_move_up:C.green,pct_move_down:C.red,
    volume_surge:C.cyan,rsi_above:C.orange,rsi_below:C.orange,
    above_sma20:C.green,below_sma20:C.red,
  };
  const label = ALERT_TYPES.find(a=>a.id===type)?.label||type;
  const color = colors[type]||C.dim;
  return <span style={{fontSize:10,fontWeight:700,color,background:`${color}22`,border:`1px solid ${color}44`,borderRadius:3,padding:"1px 6px"}}>{label}</span>;
}

export default function WatchlistPage() {
  const router = useRouter();
  const [lists,     setLists]     = useState<WatchList[]>([]);
  const [prices,    setPrices]    = useState<Record<string,PriceData>>({});
  const [technicals,setTechnicals]= useState<Record<string,TechData>>({});
  const [triggered, setTriggered] = useState<Triggered[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [saving,    setSaving]    = useState(false);
  const [activeList,setActiveList]= useState<string>("");
  const [addSym,    setAddSym]    = useState("");
  const [newListName,setNewListName]=useState("");
  const [showNewList,setShowNewList]=useState(false);
  const [showAddAlert,setShowAddAlert]=useState<{listId:string;symbol:string}|null>(null);
  const [alertForm, setAlertForm] = useState({type:"price_above",value:"",low:"",high:"",note:""});

  const load = useCallback(async()=>{
    setLoading(true);
    try {
      const r = await fetch("/api/watchlist-alerts",{cache:"no-store"});
      const d = await r.json();
      if (d.ok){
        setLists(d.watchlists||[]);
        setPrices(d.prices||{});
        setTechnicals(d.technicals||{});
        setTriggered(d.triggered||[]);
        if (!activeList && d.watchlists?.length>0) setActiveList(d.watchlists[0].id);
      }
    } finally { setLoading(false); }
  },[activeList]);

  useEffect(()=>{load();},[load]);

  const api = async(body:Record<string,unknown>)=>{
    setSaving(true);
    try {
      const r = await fetch("/api/watchlist-alerts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const d = await r.json();
      if (d.ok) setLists(d.watchlists||[]);
    } finally { setSaving(false); }
  };

  const currentList = lists.find(l=>l.id===activeList)||lists[0];

  const createList = async()=>{
    if (!newListName.trim()) return;
    await api({action:"create_list",name:newListName.trim()});
    setNewListName(""); setShowNewList(false);
    await load();
  };

  const addSymbol = async()=>{
    if (!addSym.trim()||!currentList) return;
    await api({action:"add_symbol",listId:currentList.id,symbol:addSym.trim().toUpperCase()});
    setAddSym(""); await load();
  };

  const removeSymbol = async(sym:string)=>{
    if (!currentList) return;
    await api({action:"remove_symbol",listId:currentList.id,symbol:sym});
    await load();
  };

  const addAlert = async()=>{
    if (!showAddAlert) return;
    const alert = {
      symbol: showAddAlert.symbol,
      type: alertForm.type,
      ...(alertForm.value ? {value:parseFloat(alertForm.value)} : {}),
      ...(alertForm.low   ? {low:parseFloat(alertForm.low)}     : {}),
      ...(alertForm.high  ? {high:parseFloat(alertForm.high)}   : {}),
      ...(alertForm.note  ? {note:alertForm.note}               : {}),
    };
    await api({action:"add_alert",listId:showAddAlert.listId,alert});
    setShowAddAlert(null); setAlertForm({type:"price_above",value:"",low:"",high:"",note:""});
    await load();
  };

  const removeAlert = async(listId:string,alertId:string)=>{
    await api({action:"remove_alert",listId,alertId});
    await load();
  };

  if (loading) return <div style={{padding:40,color:C.dim,textAlign:"center"}}>Loading watchlists...</div>;

  return (
    <div style={{maxWidth:1100,margin:"0 auto",padding:"20px 16px"}}>
      <NavBar />

      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}>
        <div>
          <h1 style={{margin:0,fontSize:22,fontWeight:900}}>WATCHLIST</h1>
          <div style={{color:C.dim,fontSize:12,marginTop:4}}>Multiple lists, per-stock alerts, live DB data  no agent needed</div>
        </div>
        <button onClick={load} style={{background:"transparent",border:`1px solid ${C.border}`,color:C.dim,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:12}}>Refresh</button>
      </div>

      {/* Triggered alerts banner */}
      {triggered.length>0 && (
        <div style={{background:`${C.yellow}18`,border:`1px solid ${C.yellow}`,borderRadius:8,padding:"10px 16px",marginBottom:16}}>
          <div style={{fontSize:11,fontWeight:700,color:C.yellow,letterSpacing:1.2,marginBottom:8}}>ALERTS TRIGGERED ({triggered.length})</div>
          {triggered.map((t,i)=>(
            <div key={i} style={{display:"flex",gap:12,padding:"4px 0",fontSize:12}}>
              <span style={{color:C.cyan,fontWeight:700,minWidth:100,cursor:"pointer"}} onClick={()=>router.push(`/analysis?sym=${t.symbol}`)}>{t.symbol}</span>
              <AlertBadge type={t.type} />
              <span style={{color:C.primary}}>{t.reason}</span>
              <span style={{color:C.dim,fontSize:11}}>[{t.listName}]</span>
            </div>
          ))}
        </div>
      )}

      <div style={{display:"grid",gridTemplateColumns:"200px 1fr",gap:16}}>

        {/* LEFT: List selector */}
        <div>
          <div style={{fontSize:10,fontWeight:700,color:C.dim,letterSpacing:1.2,marginBottom:8}}>YOUR LISTS</div>
          {lists.map(l=>(
            <div key={l.id} onClick={()=>setActiveList(l.id)} style={{
              padding:"8px 12px",borderRadius:6,cursor:"pointer",marginBottom:4,
              background:activeList===l.id?`${C.cyan}22`:`${C.border}22`,
              border:`1px solid ${activeList===l.id?C.cyan:C.border}`,
              color:activeList===l.id?C.cyan:C.primary,fontWeight:activeList===l.id?700:400,fontSize:13,
            }}>
              <div>{l.name}</div>
              <div style={{fontSize:10,color:C.dim}}>{l.symbols.length} stocks &bull; {l.alerts.length} alerts</div>
            </div>
          ))}

          {showNewList ? (
            <div style={{marginTop:8}}>
              <input value={newListName} onChange={e=>setNewListName(e.target.value)}
                onKeyDown={e=>e.key==="Enter"&&createList()}
                placeholder="List name..."
                style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"6px 8px",fontSize:12,boxSizing:"border-box"}} />
              <div style={{display:"flex",gap:4,marginTop:4}}>
                <button onClick={createList} style={{flex:1,background:C.cyan,color:"#000",border:"none",borderRadius:4,padding:"5px",fontWeight:700,cursor:"pointer",fontSize:11}}>Create</button>
                <button onClick={()=>setShowNewList(false)} style={{flex:1,background:"transparent",color:C.dim,border:`1px solid ${C.border}`,borderRadius:4,padding:"5px",cursor:"pointer",fontSize:11}}>Cancel</button>
              </div>
            </div>
          ) : (
            <button onClick={()=>setShowNewList(true)} style={{width:"100%",marginTop:8,background:"transparent",border:`1px dashed ${C.border}`,color:C.dim,borderRadius:6,padding:"8px",cursor:"pointer",fontSize:12,fontWeight:600}}>+ New List</button>
          )}
        </div>

        {/* RIGHT: List content */}
        <div>
          {!currentList ? (
            <div style={{color:C.dim,padding:40,textAlign:"center"}}>Create a list to get started</div>
          ) : (
            <>
              {/* Add symbol */}
              <div style={{display:"flex",gap:8,marginBottom:14}}>
                <input value={addSym} onChange={e=>setAddSym(e.target.value.toUpperCase())}
                  onKeyDown={e=>e.key==="Enter"&&addSymbol()}
                  placeholder={`Add symbol to "${currentList.name}"...`}
                  style={{flex:1,background:C.surface,border:`1px solid ${C.border}`,color:C.primary,borderRadius:6,padding:"9px 14px",fontSize:13}}
                />
                <button onClick={addSymbol} disabled={saving} style={{background:C.cyan,color:"#000",border:"none",borderRadius:6,padding:"9px 18px",fontWeight:700,cursor:"pointer",fontSize:13,opacity:saving?0.6:1}}>Add</button>
              </div>

              {/* Stocks table */}
              {currentList.symbols.length===0 ? (
                <div style={{color:C.dim,fontSize:12,padding:"20px 0",textAlign:"center"}}>No stocks yet. Add symbols above.</div>
              ) : (
                <div style={{overflowX:"auto",marginBottom:14}}>
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                    <thead>
                      <tr style={{background:`${C.border}22`}}>
                        {["Symbol","Price","Date","1D %","Vol Surge","RSI","Vs SMA20","MACD","Alerts","Actions"].map(h=>(
                          <th key={h} style={{padding:"6px 10px",textAlign:h==="Symbol"?"left":"right",color:C.dim,fontWeight:600,fontSize:10,borderBottom:`1px solid ${C.border}`,whiteSpace:"nowrap"}}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {currentList.symbols.map(sym=>{
                        const p=prices[sym]; const t=technicals[sym];
                        const myAlerts=currentList.alerts.filter(a=>a.symbol===sym);
                        return (
                          <tr key={sym} style={{borderBottom:`1px solid ${C.border}22`}}>
                            <td style={{padding:"7px 10px",color:C.cyan,fontWeight:700,cursor:"pointer"}} onClick={()=>router.push(`/analysis`)}>{sym}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",fontWeight:600}}>{p?.close?.toLocaleString("en-IN",{maximumFractionDigits:2})||"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:C.dim,fontSize:11}}>{p?.date||"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",fontWeight:700,color:col(p?.pct_1d)}}>{p?.pct_1d!=null?pct(p.pct_1d):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:t?.vol_surge_20d>2?C.green:C.dim}}>{t?.vol_surge_20d!=null?`${num(t.vol_surge_20d,1)}x`:"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:t?.rsi_14>70?C.red:t?.rsi_14<30?C.green:C.primary}}>{t?.rsi_14!=null?num(t.rsi_14,1):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:col(t?.pct_above_sma20)}}>{t?.pct_above_sma20!=null?pct(t.pct_above_sma20):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right",color:t?(t.macd_line>t.macd_signal?C.green:C.red):C.dim}}>{t?(t.macd_line>t.macd_signal?"BULL":"BEAR"):"--"}</td>
                            <td style={{padding:"7px 10px",textAlign:"right"}}>
                              <div style={{display:"flex",gap:3,justifyContent:"flex-end",flexWrap:"wrap"}}>
                                {myAlerts.slice(0,2).map(a=><AlertBadge key={a.id} type={a.type} />)}
                                {myAlerts.length>2&&<span style={{fontSize:10,color:C.dim}}>+{myAlerts.length-2}</span>}
                              </div>
                            </td>
                            <td style={{padding:"7px 10px",textAlign:"right"}}>
                              <div style={{display:"flex",gap:4,justifyContent:"flex-end"}}>
                                <button onClick={()=>setShowAddAlert({listId:currentList.id,symbol:sym})} style={{background:`${C.yellow}22`,color:C.yellow,border:`1px solid ${C.yellow}44`,borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10,fontWeight:600}}>+ Alert</button>
                                <button onClick={()=>router.push(`/analysis`)} style={{background:`${C.cyan}22`,color:C.cyan,border:`1px solid ${C.cyan}44`,borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10,fontWeight:600}}>Dive</button>
                                <button onClick={()=>removeSymbol(sym)} style={{background:`${C.red}22`,color:C.red,border:`1px solid ${C.red}44`,borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10}}>x</button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Alerts for this list */}
              {currentList.alerts.length>0 && (
                <Card title={`Alerts on "${currentList.name}" (${currentList.alerts.length})`} accent={C.yellow}>
                  {currentList.alerts.map(a=>(
                    <div key={a.id} style={{display:"flex",alignItems:"center",gap:10,padding:"5px 0",borderBottom:`1px solid ${C.border}22`,fontSize:12}}>
                      <span style={{color:C.cyan,fontWeight:700,minWidth:90}}>{a.symbol}</span>
                      <AlertBadge type={a.type} />
                      <span style={{color:C.dim,flex:1}}>
                        {a.type==="price_band"?`${a.low} - ${a.high}`:a.value!=null?String(a.value):""}
                        {a.note?` (${a.note})`:""}
                      </span>
                      <button onClick={()=>removeAlert(currentList.id,a.id)} style={{background:`${C.red}22`,color:C.red,border:"none",borderRadius:3,padding:"2px 6px",cursor:"pointer",fontSize:10}}>Remove</button>
                    </div>
                  ))}
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      {/* Add Alert Modal */}
      {showAddAlert && (
        <div style={{position:"fixed",inset:0,background:"#000c",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}>
          <div style={{background:"var(--bg)",border:`1px solid ${C.border}`,borderRadius:10,padding:24,width:420,maxWidth:"95vw"}}>
            <div style={{fontSize:14,fontWeight:700,marginBottom:16}}>Add Alert for <span style={{color:C.cyan}}>{showAddAlert.symbol}</span></div>

            <div style={{marginBottom:12}}>
              <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Alert Type</div>
              <select value={alertForm.type} onChange={e=>setAlertForm(f=>({...f,type:e.target.value}))}
                style={{width:"100%",background:"var(--bg)",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13}}>
                {ALERT_TYPES.map(a=><option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
              <div style={{fontSize:10,color:C.dim,marginTop:3}}>{ALERT_TYPES.find(a=>a.id===alertForm.type)?.desc}</div>
            </div>

            {ALERT_TYPES.find(a=>a.id===alertForm.type)?.fields.includes("value") && (
              <div style={{marginBottom:12}}>
                <div style={{fontSize:11,color:C.dim,marginBottom:4}}>
                  {alertForm.type==="volume_surge"?"Surge Multiplier (e.g. 2.5)":alertForm.type.includes("rsi")?"RSI Value (0-100)":alertForm.type.includes("pct")?"% Move (e.g. 3 = 3%)":"Price Value"}
                </div>
                <input type="number" value={alertForm.value} onChange={e=>setAlertForm(f=>({...f,value:e.target.value}))}
                  placeholder="Enter value..."
                  style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}}
                />
              </div>
            )}
            {ALERT_TYPES.find(a=>a.id===alertForm.type)?.fields.includes("low") && (
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:12}}>
                <div>
                  <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Lower Bound</div>
                  <input type="number" value={alertForm.low} onChange={e=>setAlertForm(f=>({...f,low:e.target.value}))}
                    style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}} />
                </div>
                <div>
                  <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Upper Bound</div>
                  <input type="number" value={alertForm.high} onChange={e=>setAlertForm(f=>({...f,high:e.target.value}))}
                    style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}} />
                </div>
              </div>
            )}

            <div style={{marginBottom:16}}>
              <div style={{fontSize:11,color:C.dim,marginBottom:4}}>Note (optional)</div>
              <input value={alertForm.note} onChange={e=>setAlertForm(f=>({...f,note:e.target.value}))}
                placeholder="e.g. support level, target price..."
                style={{width:"100%",background:"transparent",border:`1px solid ${C.border}`,color:C.primary,borderRadius:4,padding:"7px 10px",fontSize:13,boxSizing:"border-box"}} />
            </div>

            <div style={{display:"flex",gap:8}}>
              <button onClick={addAlert} style={{flex:1,background:C.cyan,color:"#000",border:"none",borderRadius:6,padding:"10px",fontWeight:700,cursor:"pointer",fontSize:13}}>Add Alert</button>
              <button onClick={()=>setShowAddAlert(null)} style={{flex:1,background:"transparent",color:C.dim,border:`1px solid ${C.border}`,borderRadius:6,padding:"10px",cursor:"pointer",fontSize:13}}>Cancel</button>
            </div>

            <div style={{marginTop:12,fontSize:11,color:C.dim}}>
              To send triggered alerts to Telegram, run: <code>py D:\MICC\check_alerts.py</code>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
