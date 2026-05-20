"use client";
import NavBar from "@/components/NavBar";
import { useState, useEffect, useCallback } from "react";

const DURATIONS = [
  {l:"1D",d:1},{l:"3D",d:3},{l:"5D",d:5},{l:"7D",d:7},
  {l:"10D",d:10},{l:"14D",d:14},{l:"20D",d:20},
  {l:"1M",d:22},{l:"2M",d:44},{l:"3M",d:66},{l:"6M",d:132},
];

function IRow({rank,row,color}:{rank:number;row:any;color:string}) {
  const pct  = Number(row.pct_change);
  const barW = Math.min((Math.abs(pct)/20)*100,100);
  return (
    <tr style={{borderBottom:"1px solid var(--border)"}}>
      <td style={{padding:"5px 6px",color:"var(--dim)",textAlign:"right",fontFamily:"monospace",fontSize:10}}>{rank}</td>
      <td style={{padding:"5px 8px",color:"var(--text)",fontSize:11}}>{row.name}</td>
      <td style={{padding:"5px 6px",textAlign:"right",color:"var(--dim)",fontFamily:"monospace",fontSize:10}}>
        {row.end_close!=null?Number(row.end_close).toLocaleString("en-IN",{maximumFractionDigits:2}):"--"}
      </td>
      <td style={{padding:"5px 4px",textAlign:"right",color:"var(--dim)",fontFamily:"monospace",fontSize:10}}>
        {row.pe!=null?Number(row.pe).toFixed(1):"--"}
      </td>
      <td style={{padding:"5px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color,fontWeight:600}}>
        {pct>=0?"+":""}{pct.toFixed(2)}%
      </td>
      <td style={{padding:"5px 8px",width:90}}>
        <div style={{width:90,height:5,background:"var(--border)",borderRadius:2,overflow:"hidden"}}>
          <div style={{width:barW+"%",height:"100%",background:color,borderRadius:2}}/>
        </div>
      </td>
    </tr>
  );
}

export default function IndicesPage() {
  const [days,   setDays]   = useState(7);
  const [data,   setData]   = useState<any>(null);
  const [loading,setLoading]= useState(true);
  const [tab,    setTab]    = useState<"split"|"all">("split");

  const load = useCallback(async(d:number)=>{
    setLoading(true);
    try {
      const r = await fetch(`/api/indices?days=${d}`,{cache:"no-store"});
      setData(await r.json());
    } catch(e){console.error(e);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load(days);},[days,load]);

  const gainers = data?.gainers??[];
  const losers  = data?.losers ??[];
  const all     = data?.all    ??[];

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
            <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",
                     marginBottom:14,flexWrap:"wrap",gap:10}}>
          <div>
            <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,
                         letterSpacing:"0.12em",color:"var(--pos)"}}>INDEX PERFORMANCE</div>
            <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginTop:2}}>
              {data?.total??"--"} indices &nbsp;|&nbsp; {data?.days??"--"}D window
            </div>
          </div>
          <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
            {DURATIONS.map(({l,d})=>(
              <button key={d} onClick={()=>setDays(d)} style={{
                padding:"4px 10px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
                background:days===d?"rgba(38,196,133,0.15)":"var(--surface)",
                color:days===d?"var(--pos)":"var(--muted)",
                border:`1px solid ${days===d?"var(--pos)":"var(--border)"}`,
                borderRadius:4,
              }}>{l}</button>
            ))}
          </div>
        </div>

        <div style={{display:"flex",gap:6,marginBottom:14}}>
          {(["split","all"] as const).map(t=>(
            <button key={t} onClick={()=>setTab(t)} style={{
              padding:"4px 14px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
              background:tab===t?"var(--pos)":"var(--surface)",
              color:tab===t?"#000":"var(--muted)",
              border:"1px solid var(--border)",borderRadius:4,
            }}>
              {t==="split"?"TOP 25 GAINERS / BOTTOM 25 DECLINERS":`FULL TABLE (${all.length})`}
            </button>
          ))}
        </div>

        {loading ? (
          <div style={{color:"var(--dim)",fontFamily:"monospace",padding:40,textAlign:"center"}}>Loading...</div>
        ) : tab==="split" ? (
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:20}}>
            {/* Gainers */}
            <div>
              <div style={{fontFamily:"monospace",fontSize:10,color:"var(--pos)",letterSpacing:"0.1em",
                           marginBottom:8,borderBottom:"1px solid var(--border)",paddingBottom:4}}>
                TOP {gainers.length} GAINERS
              </div>
              <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead>
                  <tr style={{fontSize:9,color:"var(--dim)",borderBottom:"1px solid var(--border)"}}>
                    <th style={{padding:"3px 6px",textAlign:"right",width:28}}>#</th>
                    <th style={{padding:"3px 8px",textAlign:"left"}}>INDEX</th>
                    <th style={{padding:"3px 6px",textAlign:"right"}}>CLOSE</th>
                    <th style={{padding:"3px 4px",textAlign:"right"}}>PE</th>
                    <th style={{padding:"3px 8px",textAlign:"right"}}>CHG%</th>
                    <th style={{padding:"3px 8px",width:90}}></th>
                  </tr>
                </thead>
                <tbody>
                  {gainers.map((r:any,i:number)=><IRow key={r.name} rank={i+1} row={r} color="var(--pos)"/>)}
                </tbody>
              </table>
            </div>
            {/* Decliners */}
            <div>
              <div style={{fontFamily:"monospace",fontSize:10,color:"var(--neg)",letterSpacing:"0.1em",
                           marginBottom:8,borderBottom:"1px solid var(--border)",paddingBottom:4}}>
                BOTTOM {losers.length} DECLINERS
              </div>
              <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead>
                  <tr style={{fontSize:9,color:"var(--dim)",borderBottom:"1px solid var(--border)"}}>
                    <th style={{padding:"3px 6px",textAlign:"right",width:28}}>#</th>
                    <th style={{padding:"3px 8px",textAlign:"left"}}>INDEX</th>
                    <th style={{padding:"3px 6px",textAlign:"right"}}>CLOSE</th>
                    <th style={{padding:"3px 4px",textAlign:"right"}}>PE</th>
                    <th style={{padding:"3px 8px",textAlign:"right"}}>CHG%</th>
                    <th style={{padding:"3px 8px",width:90}}></th>
                  </tr>
                </thead>
                <tbody>
                  {losers.map((r:any,i:number)=><IRow key={r.name} rank={i+1} row={r} color="var(--neg)"/>)}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
            <thead>
              <tr style={{fontSize:9,color:"var(--dim)",borderBottom:"2px solid var(--border)",letterSpacing:"0.08em"}}>
                <th style={{padding:"5px 6px",textAlign:"right",width:28}}>#</th>
                <th style={{padding:"5px 8px",textAlign:"left"}}>INDEX NAME</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>CLOSE</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>PE</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>PB</th>
                <th style={{padding:"5px 8px",textAlign:"right"}}>CHG%</th>
                <th style={{padding:"5px 8px",width:120}}></th>
              </tr>
            </thead>
            <tbody>
              {all.map((r:any,i:number)=>{
                const pct=Number(r.pct_change);
                const color=pct>=0?"var(--pos)":"var(--neg)";
                const barW=Math.min((Math.abs(pct)/20)*100,100);
                return (
                  <tr key={r.name} style={{borderBottom:"1px solid var(--border)"}}>
                    <td style={{padding:"4px 6px",color:"var(--dim)",textAlign:"right"}}>{i+1}</td>
                    <td style={{padding:"4px 8px",color:"var(--text)"}}>{r.name}</td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:"var(--dim)"}}>
                      {Number(r.end_close).toLocaleString("en-IN",{maximumFractionDigits:2})}
                    </td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:"var(--dim)"}}>
                      {r.pe!=null?Number(r.pe).toFixed(1):"--"}
                    </td>
                    <td style={{padding:"4px 8px",textAlign:"right",color:"var(--dim)"}}>
                      {r.pb!=null?Number(r.pb).toFixed(2):"--"}
                    </td>
                    <td style={{padding:"4px 8px",textAlign:"right",color,fontWeight:600}}>
                      {pct>=0?"+":""}{pct.toFixed(2)}%
                    </td>
                    <td style={{padding:"4px 8px"}}>
                      <div style={{width:120,height:5,background:"var(--border)",borderRadius:2,overflow:"hidden"}}>
                        <div style={{width:barW+"%",height:"100%",background:color,borderRadius:2}}/>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
