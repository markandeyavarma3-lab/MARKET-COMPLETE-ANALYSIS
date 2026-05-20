"use client";
import NavBar from "@/components/NavBar";

import { useState, useEffect, useCallback } from "react";

interface Alert {
  id: string; type: string; symbol: string; target: number;
  note: string; days: number; one_shot: boolean; active: boolean;
  created_at: string; triggered_at: string|null; last_message: string|null;
}
interface SR { symbol: string; name: string; type: string; }

const ALERT_TYPES = [
  { v:"PRICE_ABOVE",   l:"Price Above",    d:"Price crosses above target" },
  { v:"PRICE_BELOW",   l:"Price Below",    d:"Price drops below target" },
  { v:"PCT_MOVE",      l:"% Move (N days)",d:"Price moves > target% in N days" },
  { v:"VOLUME_SURGE",  l:"Volume Surge",   d:"Volume > target x 20d average" },
  { v:"RSI_ABOVE",     l:"RSI Overbought", d:"RSI(14) > target" },
  { v:"RSI_BELOW",     l:"RSI Oversold",   d:"RSI(14) < target" },
  { v:"PATTERN_HIT",   l:"Pattern Hit",    d:"Seasonal pattern active today (acc >= target%)" },
];
const TYPE_CLR: Record<string,string> = {
  PRICE_ABOVE:"var(--pos)", PRICE_BELOW:"var(--neg)", PCT_MOVE:"var(--warn)",
  VOLUME_SURGE:"var(--purple)", RSI_ABOVE:"var(--orange)", RSI_BELOW:"var(--accent)", PATTERN_HIT:"var(--pos)",
};

const inp = (extra?: object) => ({
  padding:"8px 12px", background:"var(--bg)", border:"1px solid #334155",
  borderRadius:7, color:"var(--text)", fontSize:13, outline:"none",
  width:"100%", boxSizing:"border-box" as const, ...extra,
});

export default function AlertsPage() {
  const [alerts,  setAlerts]  = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [saving,  setSaving]  = useState(false);
  const [form, setForm] = useState({ type:"PRICE_ABOVE", symbol:"", target:"", note:"", days:5, one_shot:true });
  const [searchQ, setSearchQ] = useState("");
  const [searchR, setSearchR] = useState<SR[]>([]);

  const reload = useCallback(async () => {
    setLoading(true);
    try { const r = await fetch("/api/alerts"); const d = await r.json(); setAlerts(d.alerts||[]); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { reload(); }, []);

  useEffect(() => {
    if (!searchQ.trim()) { setSearchR([]); return; }
    const t = setTimeout(async () => {
      try { const r = await fetch("/api/search?q="+encodeURIComponent(searchQ)+"&limit=8"); const d = await r.json(); setSearchR(d.results||[]); } catch {}
    }, 200);
    return () => clearTimeout(t);
  }, [searchQ]);

  const addAlert = async () => {
    if (!form.symbol || !form.target) return;
    setSaving(true);
    try {
      await fetch("/api/alerts", { method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ type:form.type, symbol:form.symbol.toUpperCase(),
          target:parseFloat(form.target), note:form.note, days:form.days, one_shot:form.one_shot }) });
      setShowAdd(false);
      setForm({ type:"PRICE_ABOVE", symbol:"", target:"", note:"", days:5, one_shot:true });
      setSearchQ(""); setSearchR([]); reload();
    } catch {} finally { setSaving(false); }
  };

  const del = async (id: string) => {
    await fetch("/api/alerts", { method:"DELETE", headers:{"Content-Type":"application/json"}, body:JSON.stringify({id}) });
    reload();
  };

  const toggle = async (id: string, active: boolean) => {
    await fetch("/api/alerts", { method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({id,active}) });
    reload();
  };

  const active  = alerts.filter(a => a.active);
  const fired   = alerts.filter(a => !a.active && a.triggered_at);
  const paused  = alerts.filter(a => !a.active && !a.triggered_at);

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />

      {/* Header */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b",
        display:"flex", alignItems:"center", flexWrap:"wrap", gap:16 }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:800, color:"var(--text)" }}>Alerts</h1>
          <p style={{ margin:"4px 0 0", fontSize:12, color:"var(--muted)" }}>
            Price, RSI, volume, pattern triggers sent to Telegram
          </p>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:10, alignItems:"center" }}>
          {[{l:"Active",v:active.length,c:"var(--pos)"},{l:"Fired",v:fired.length,c:"var(--warn)"},{l:"Paused",v:paused.length,c:"var(--muted)"}].map(s=>(
            <div key={s.l} style={{ textAlign:"center", padding:"7px 14px",
              background:"var(--card)", borderRadius:8, border:`1px solid ${s.c}33` }}>
              <div style={{ fontSize:18, fontWeight:800, color:s.c }}>{s.v}</div>
              <div style={{ fontSize:10, color:"var(--muted)" }}>{s.l}</div>
            </div>
          ))}
          <button onClick={()=>setShowAdd(o=>!o)} style={{
            padding:"9px 18px", background:"var(--accent)", color:"#fff",
            border:"none", borderRadius:8, cursor:"pointer", fontSize:13, fontWeight:700,
          }}>+ Add Alert</button>
        </div>
      </div>

      <div style={{ padding:"20px 28px" }}>

        {/* Add form */}
        {showAdd && (
          <div style={{ background:"var(--card)", border:"1px solid #3b82f6", borderRadius:6, padding:"20px", marginBottom:20 }}>
            <h3 style={{ margin:"0 0 16px", fontSize:14, fontWeight:700, color:"var(--accent)" }}>New Alert</h3>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12 }}>

              <div>
                <div style={{ fontSize:10, color:"var(--muted)", marginBottom:4 }}>TYPE</div>
                <select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))} style={inp()}>
                  {ALERT_TYPES.map(t=><option key={t.v} value={t.v}>{t.l}</option>)}
                </select>
                <div style={{ fontSize:10, color:"var(--muted)", marginTop:4 }}>
                  {ALERT_TYPES.find(t=>t.v===form.type)?.d}
                </div>
              </div>

              <div style={{ position:"relative" }}>
                <div style={{ fontSize:10, color:"var(--muted)", marginBottom:4 }}>SYMBOL</div>
                <input value={searchQ||form.symbol}
                  onChange={e=>{setSearchQ(e.target.value);setForm(f=>({...f,symbol:e.target.value.toUpperCase()}));}}
                  placeholder="e.g. RELIANCE or HDFC Bank" style={inp()} />
                {searchR.length>0 && searchQ && (
                  <div style={{ position:"absolute", top:"100%", left:0, right:0, zIndex:100,
                    background:"var(--card)", border:"1px solid #334155", borderRadius:7,
                    boxShadow:"0 8px 24px rgba(0,0,0,0.5)", overflow:"hidden" }}>
                    {searchR.map(r=>(
                      <div key={r.symbol} onMouseDown={()=>{setForm(f=>({...f,symbol:r.symbol}));setSearchQ("");setSearchR([]);}}
                        style={{ padding:"8px 12px", cursor:"pointer", fontSize:12,
                          borderBottom:"1px solid #0f172a", display:"flex", gap:10 }}>
                        <span style={{ fontFamily:"monospace", fontWeight:700, color:"var(--accent)" }}>{r.symbol}</span>
                        <span style={{ color:"var(--muted)" }}>{r.name!==r.symbol?r.name:""}</span>
                        <span style={{ marginLeft:"auto", fontSize:10, color:"var(--border2)" }}>{r.type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div style={{ fontSize:10, color:"var(--muted)", marginBottom:4 }}>
                  TARGET ({form.type==="VOLUME_SURGE"?"x avg":form.type==="PCT_MOVE"?"%":form.type.startsWith("RSI")?"RSI value":"price"})
                </div>
                <input type="number" value={form.target} onChange={e=>setForm(f=>({...f,target:e.target.value}))}
                  placeholder={form.type==="VOLUME_SURGE"?"e.g. 3":form.type==="PCT_MOVE"?"e.g. 5":"e.g. 2800"} style={inp()} />
              </div>

              {form.type==="PCT_MOVE" && (
                <div>
                  <div style={{ fontSize:10, color:"var(--muted)", marginBottom:4 }}>LOOKBACK DAYS</div>
                  <input type="number" value={form.days} onChange={e=>setForm(f=>({...f,days:parseInt(e.target.value)||5}))} style={inp()} />
                </div>
              )}

              <div style={{ gridColumn:"1/-1" }}>
                <div style={{ fontSize:10, color:"var(--muted)", marginBottom:4 }}>NOTE (optional)</div>
                <input value={form.note} onChange={e=>setForm(f=>({...f,note:e.target.value}))}
                  placeholder="e.g. Resistance level, earnings play" style={inp()} />
              </div>

              <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                <input type="checkbox" id="os" checked={form.one_shot} onChange={e=>setForm(f=>({...f,one_shot:e.target.checked}))} />
                <label htmlFor="os" style={{ fontSize:12, color:"var(--muted)", cursor:"pointer" }}>
                  One-shot (deactivate after firing)
                </label>
              </div>
            </div>

            <div style={{ display:"flex", gap:8, marginTop:14 }}>
              <button onClick={addAlert} disabled={saving||!form.symbol||!form.target}
                style={{ padding:"8px 20px", background:"var(--pos)", color:"#fff",
                  border:"none", borderRadius:7, cursor:"pointer", fontSize:13, fontWeight:700 }}>
                {saving?"Saving...":"Add Alert"}
              </button>
              <button onClick={()=>setShowAdd(false)}
                style={{ padding:"8px 16px", background:"var(--border2)", color:"var(--muted)",
                  border:"none", borderRadius:7, cursor:"pointer", fontSize:13 }}>Cancel</button>
            </div>
          </div>
        )}

        {/* Quick-add examples */}
        <div style={{ marginBottom:20, padding:"12px 16px", background:"var(--card)", borderRadius:10 }}>
          <div style={{ fontSize:10, color:"var(--muted)", marginBottom:8, textTransform:"uppercase", letterSpacing:0.5 }}>
            Quick-add examples
          </div>
          <div style={{ display:"flex", gap:7, flexWrap:"wrap" }}>
            {[
              {type:"RSI_BELOW",   symbol:"NIFTY50",  target:35,  note:"Oversold"},
              {type:"PRICE_ABOVE", symbol:"RELIANCE",  target:1400,note:"Breakout"},
              {type:"VOLUME_SURGE",symbol:"HDFCBANK",  target:3,   note:"Big vol"},
              {type:"PCT_MOVE",    symbol:"SBIN",      target:5,   note:"5% move",days:3},
              {type:"PATTERN_HIT", symbol:"INFY",      target:70,  note:"Pattern 70%+"},
              {type:"RSI_ABOVE",   symbol:"Bitcoin",   target:80,  note:"BTC overbought"},
            ].map((ex,i)=>(
              <button key={i} onClick={async ()=>{
                await fetch("/api/alerts",{method:"POST",headers:{"Content-Type":"application/json"},
                  body:JSON.stringify({...ex,active:true,one_shot:true,days:ex.days||5})});
                reload();
              }} style={{ fontSize:11, padding:"4px 12px", background:"var(--bg)",
                border:"1px solid #334155", borderRadius:6, cursor:"pointer", color:"var(--muted)" }}>
                {ex.type.replace(/_/g," ")} {ex.symbol} {ex.target}{ex.note?" ("+ex.note+")":""}
              </button>
            ))}
          </div>
        </div>

        {/* Alert groups */}
        {loading ? (
          <div style={{ color:"var(--muted)", fontSize:13 }}>Loading...</div>
        ) : alerts.length===0 ? (
          <div style={{ textAlign:"center", padding:"60px 0", color:"var(--muted)" }}>
            <div style={{ fontSize:40, marginBottom:12 }}>No alerts yet</div>
            <p style={{ fontSize:13 }}>Click Add Alert or use quick-add examples above.</p>
            <code style={{ fontSize:11, color:"var(--muted)" }}>
              py D:\MICC\agent_alert.py --send
            </code>
          </div>
        ) : (
          [{label:"Active Alerts",  items:active,  accent:"var(--pos)"},
           {label:"Fired Alerts",   items:fired,   accent:"var(--warn)"},
           {label:"Paused Alerts",  items:paused,  accent:"var(--muted)"},
          ].filter(g=>g.items.length>0).map(g=>(
            <div key={g.label} style={{ marginBottom:22 }}>
              <h3 style={{ fontSize:11, fontWeight:700, color:g.accent,
                letterSpacing:".04em", marginBottom:10, textTransform:"uppercase" }}>
                {g.label} ({g.items.length})
              </h3>
              {g.items.map(a=>(
                <div key={a.id} style={{
                  background:"var(--card)",
                  border:`1px solid ${a.active?(TYPE_CLR[a.type]||"var(--border2)")+"55":"var(--border2)"}`,
                  borderRadius:10, padding:"11px 16px", marginBottom:7,
                  display:"flex", alignItems:"center", gap:12, flexWrap:"wrap",
                }}>
                  <span style={{
                    fontSize:10, fontWeight:700, padding:"2px 8px", borderRadius:4,
                    background:(TYPE_CLR[a.type]||"var(--muted)")+"22",
                    color:TYPE_CLR[a.type]||"var(--muted)",
                  }}>{a.type.replace(/_/g," ")}</span>
                  <span style={{ fontFamily:"monospace", fontWeight:800, color:"var(--accent)", fontSize:13 }}>{a.symbol}</span>
                  <span style={{ fontSize:13, color:"var(--text)", fontWeight:700 }}>target: {a.target}</span>
                  {a.note && <span style={{ fontSize:11, color:"var(--muted)" }}>{a.note}</span>}
                  {a.triggered_at && <span style={{ fontSize:10, color:"var(--warn)" }}>Fired: {a.triggered_at}</span>}
                  {a.last_message && <span style={{ fontSize:11, color:"var(--muted)", flex:1 }}>{a.last_message}</span>}
                  <div style={{ display:"flex", gap:6, marginLeft:"auto" }}>
                    <button onClick={()=>toggle(a.id,!a.active)} style={{
                      padding:"4px 10px", fontSize:11,
                      background:a.active?"var(--border2)":"var(--border)",
                      color:a.active?"var(--muted)":"var(--accent)",
                      border:"1px solid #334155", borderRadius:5, cursor:"pointer",
                    }}>{a.active?"Pause":"Resume"}</button>
                    <button onClick={()=>del(a.id)} style={{
                      padding:"4px 10px", fontSize:11,
                      background:"var(--bg)", color:"var(--neg)",
                      border:"1px solid #ef444433", borderRadius:5, cursor:"pointer",
                    }}>Delete</button>
                  </div>
                </div>
              ))}
            </div>
          ))
        )}

        <div style={{ marginTop:20, padding:"13px 16px", background:"var(--card)", borderRadius:10 }}>
          <div style={{ fontSize:11, color:"var(--muted)", marginBottom:6, fontWeight:700 }}>Run alerts manually</div>
          <code style={{ fontSize:12, color:"var(--accent)", display:"block", marginBottom:4 }}>
            py D:\MICC\agent_alert.py --send
          </code>
          <code style={{ fontSize:12, color:"var(--accent)", display:"block", marginBottom:4 }}>
            py D:\MICC\agent_alert.py --add PRICE_ABOVE RELIANCE 2800 "note"
          </code>
          <div style={{ fontSize:11, color:"var(--muted)", marginTop:6 }}>
            Runs automatically in daily pipeline (already patched in run_pipeline.py)
          </div>
        </div>
      </div>
    </div>
  );
}
