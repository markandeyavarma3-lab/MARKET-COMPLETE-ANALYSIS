# MICC Nuclear Fix — Pure CSS, no Tailwind, fix all JSON keys
# py fix_final.py  (run from DATA-ANALYSIS\)

import pathlib, json

DASH   = pathlib.Path(r"D:\MICC\micc-dashboard")
AGENTS = pathlib.Path(r"D:\MICC\agents")

def w(rel, content):
    p = DASH / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"  wrote: {rel}")

# ── globals.css — pure CSS, zero Tailwind ───────────────────
w("app/globals.css", """\
@import url("https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Share+Tech+Mono&display=swap");

:root {
  --bg:      #090b0f;
  --surface: #0d1117;
  --border:  #1e2530;
  --muted:   #3a4455;
  --text:    #c9d1d9;
  --dim:     #768390;
  --accent:  #00d4aa;
  --bull:    #26c485;
  --bear:    #f85149;
  --warn:    #e3b341;
  --info:    #58a6ff;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  min-height: 100vh;
}

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* ── Layout ── */
.dashboard { padding: 12px; max-width: 1600px; margin: 0 auto; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
@media (max-width: 900px) { .grid2 { grid-template-columns: 1fr; } }

/* ── Header ── */
.header {
  position: sticky; top: 0; z-index: 50;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 8px 16px;
  display: flex; align-items: center; gap: 12px;
}
.header-logo { font-family: 'Share Tech Mono', monospace; font-size: 15px; color: var(--accent); letter-spacing: 0.2em; }
.header-sub  { font-size: 11px; color: var(--dim); }
.header-right { margin-left: auto; display: flex; align-items: center; gap: 12px; font-size: 11px; }
.refresh-btn {
  background: none; border: 1px solid var(--border); color: var(--dim);
  padding: 2px 8px; border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 11px;
}
.refresh-btn:hover { color: var(--accent); border-color: var(--accent); }

/* ── Panel ── */
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 14px; }
.panel-title {
  font-family: 'Share Tech Mono', monospace; font-size: 10px; letter-spacing: 0.15em;
  text-transform: uppercase; color: var(--dim);
  padding-bottom: 8px; margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 6px;
}
.panel-title .ml { margin-left: auto; display: flex; align-items: center; gap: 8px; }

/* ── Colors ── */
.c-accent { color: var(--accent); }
.c-bull   { color: var(--bull);   }
.c-bear   { color: var(--bear);   }
.c-warn   { color: var(--warn);   }
.c-info   { color: var(--info);   }
.c-dim    { color: var(--dim);    }
.c-muted  { color: var(--muted);  }
.c-text   { color: var(--text);   }

/* ── Regime pill ── */
.pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px; border-radius: 4px; border: 1px solid;
  font-size: 11px; font-weight: 500;
}
.pill-bull { color: var(--bull); border-color: rgba(38,196,133,.3); background: rgba(38,196,133,.08); }
.pill-bear { color: var(--bear); border-color: rgba(248, 81, 73,.3); background: rgba(248, 81, 73,.08); }
.pill-neut { color: var(--info); border-color: rgba(88,166,255,.3);  background: rgba(88,166,255,.08); }
.pill-unkn { color: var(--warn); border-color: rgba(227,179, 65,.3); background: rgba(227,179, 65,.08); }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
.blink { animation: blink 1.4s step-end infinite; }

/* ── Stat grid ── */
.stat-grid { display: grid; gap: 8px; margin-bottom: 10px; }
.sg2 { grid-template-columns: 1fr 1fr; }
.sg3 { grid-template-columns: 1fr 1fr 1fr; }
.sg4 { grid-template-columns: 1fr 1fr 1fr 1fr; }
.stat-box {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 4px; padding: 8px; text-align: center;
}
.stat-val  { font-size: 16px; font-weight: 600; line-height: 1.2; }
.stat-lbl  { font-size: 9px; color: var(--dim); text-transform: uppercase; letter-spacing: .1em; margin-top: 2px; }

/* ── Score bar ── */
.bar-wrap { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; flex: 1; }
.bar-fill { height: 100%; border-radius: 2px; transition: width .5s ease; }

/* ── Table ── */
.tbl { width: 100%; font-size: 11px; border-collapse: collapse; }
.tbl th { color: var(--dim); text-align: left; padding: 0 6px 6px 0; font-weight: 400; white-space: nowrap; }
.tbl th.r { text-align: right; }
.tbl td { padding: 3px 6px 3px 0; border-bottom: 1px solid rgba(30,37,48,.5); white-space: nowrap; }
.tbl td.r { text-align: right; }
.tbl tr:hover td { background: rgba(255,255,255,.02); }

/* ── Tag ── */
.tag { font-size: 9px; padding: 1px 5px; border-radius: 3px; }
.tag-mom  { background: rgba(38,196,133,.1);  color: var(--bull); }
.tag-del  { background: rgba(88,166,255,.1);  color: var(--info); }
.tag-brk  { background: rgba(227,179,65,.1);  color: var(--warn); }
.tag-con  { background: rgba(0,212,170,.1);   color: var(--accent); }
.tag-def  { background: rgba(58,68,85,.15);   color: var(--dim); }

/* ── Gauge SVG ── */
.gauge-ring { transform-origin: center; transform: rotate(-90deg); transition: stroke-dashoffset .8s; }

/* ── Flow bar row ── */
.flow-row { display: flex; align-items: center; gap: 8px; }

/* ── Section label ── */
.sec-lbl { font-size: 9px; color: var(--dim); text-transform: uppercase; letter-spacing: .12em; margin-bottom: 6px; }

/* ── Analysis box ── */
.analysis {
  background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
  padding: 8px; font-size: 11px; color: var(--dim); line-height: 1.6;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  margin-top: 8px;
}

/* ── Misc ── */
.row   { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.col2  { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.bold  { font-weight: 600; }
.mono  { font-family: 'Share Tech Mono', monospace; }
.small { font-size: 10px; }
.xs    { font-size: 9px; }
.ml-auto { margin-left: auto; }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
.footer { text-align: center; font-size: 9px; color: var(--muted); letter-spacing: .12em; padding: 20px 0 8px; }
""")

# ── layout.tsx ───────────────────────────────────────────────
w("app/layout.tsx", """\
import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "MICC", description: "Market Intelligence Command Center" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
""")

# ── components/RegimePill.tsx ────────────────────────────────
w("components/RegimePill.tsx", '''\
"use client";
export default function RegimePill({ regime }: { regime: string }) {
  const r = (regime || "").toLowerCase();
  const cls = r.includes("bull") ? "pill pill-bull"
            : r.includes("bear") ? "pill pill-bear"
            : (r.includes("neutral")||r.includes("sideways")) ? "pill pill-neut"
            : "pill pill-unkn";
  const dcls = r.includes("bull") ? "dot blink" + " " + "c-bull"
             : r.includes("bear") ? "dot blink c-bear"
             : "dot blink c-warn";
  return (
    <span className={cls} style={{display:"inline-flex",alignItems:"center",gap:5}}>
      <span style={{width:6,height:6,borderRadius:"50%",display:"inline-block",
        background: r.includes("bull")?"#26c485":r.includes("bear")?"#f85149":"#e3b341",
        animation:"blink 1.4s step-end infinite"}} />
      {regime || "UNKNOWN"}
    </span>
  );
}
''')

# ── components/AlphaPanel.tsx ────────────────────────────────
# Alpha key fixes: breadth uses "advancing"/"declining", regime_analysis is a STRING
w("components/AlphaPanel.tsx", '''\
"use client";
import RegimePill from "./RegimePill";

export default function AlphaPanel({ data }: { data: any }) {
  if (!data) return <div className="panel"><div className="c-dim small">Alpha report unavailable</div></div>;

  const rm   = data.regime_metrics    || {};
  const ba   = data.breadth_analytics || {};
  const cr   = data.cap_rotation      || {};
  const gc   = data.global_context    || {};
  // regime_analysis is a STRING in this agent version
  const regimeText = typeof data.regime_analysis === "string" ? data.regime_analysis : "";
  // Extract regime word from the analysis string
  const regimeWord = regimeText.match(/BULLISH|BEARISH|NEUTRAL|SIDEWAYS|CAUTIOUS/i)?.[0] || "UNKNOWN";

  const top3 = (ba.top3_performers    || []).slice(0,3);
  const bot3 = (ba.bottom3_performers || []).slice(0,3);

  const caps = [
    { k: "large_cap", label: "LARGE" },
    { k: "mid_cap",   label: "MID"   },
    { k: "small_cap", label: "SMALL" },
  ];

  return (
    <div className="panel">
      <div className="panel-title">
        <span className="c-accent">&#9672;</span> ALPHA &mdash; MACRO &amp; REGIME
        <span className="ml">{data.latest_market_date}</span>
      </div>

      <div className="row">
        <RegimePill regime={regimeWord} />
        {rm.nifty_close && (
          <span className="c-dim small">NIFTY&nbsp;
            <span className="c-text bold">{Number(rm.nifty_close).toLocaleString("en-IN")}</span>
          </span>
        )}
        {rm.nifty_change_pct !== undefined && (
          <span className={rm.nifty_change_pct >= 0 ? "c-bull bold small" : "c-bear bold small"}>
            {rm.nifty_change_pct >= 0 ? "▲" : "▼"} {Math.abs(rm.nifty_change_pct).toFixed(2)}%
          </span>
        )}
      </div>

      <div className="stat-grid sg3" style={{marginBottom:10}}>
        {[
          { l:"Advances",  v: ba.advancing,  c:"c-bull" },
          { l:"Declines",  v: ba.declining,  c:"c-bear" },
          { l:"Unchanged", v: ba.unchanged,  c:"c-warn" },
        ].map(({l,v,c}) => (
          <div key={l} className="stat-box">
            <div className={`stat-val ${c}`}>{v ?? "—"}</div>
            <div className="stat-lbl">{l}</div>
          </div>
        ))}
      </div>

      <div className="stat-grid sg3" style={{marginBottom:10}}>
        {caps.map(({k,label}) => {
          const v = cr[k] || {}; const pct = Number(v.avg_change_pct ?? v.change_pct ?? 0);
          return (
            <div key={k} className="stat-box">
              <div className={`stat-val ${pct>=0?"c-bull":"c-bear"}`}>{pct>=0?"+":""}{pct.toFixed(2)}%</div>
              <div className="stat-lbl">{label}</div>
            </div>
          );
        })}
      </div>

      <div className="col2" style={{marginBottom:10}}>
        <div>
          <div className="sec-lbl">Top Indices</div>
          {top3.map((idx:any) => (
            <div key={idx.index||idx.name} style={{display:"flex",justifyContent:"space-between",padding:"2px 0",fontSize:11}}>
              <span className="c-dim truncate">{idx.index||idx.name}</span>
              <span className="c-bull">+{Number(idx.change_pct||idx.pct_chg||0).toFixed(2)}%</span>
            </div>
          ))}
        </div>
        <div>
          <div className="sec-lbl">Bottom Indices</div>
          {bot3.map((idx:any) => (
            <div key={idx.index||idx.name} style={{display:"flex",justifyContent:"space-between",padding:"2px 0",fontSize:11}}>
              <span className="c-dim truncate">{idx.index||idx.name}</span>
              <span className="c-bear">{Number(idx.change_pct||idx.pct_chg||0).toFixed(2)}%</span>
            </div>
          ))}
        </div>
      </div>

      {Object.keys(gc).length > 0 && (
        <div>
          <div className="sec-lbl">Global Context</div>
          <div className="stat-grid" style={{gridTemplateColumns:"repeat(auto-fill,minmax(90px,1fr))"}}>
            {Object.entries(gc).map(([key, val]: [string, any]) => {
              const v = val?.value ?? val?.close ?? val;
              const chg = val?.change_pct ?? val?.chg_pct;
              return (
                <div key={key} className="stat-box">
                  <div className="stat-lbl">{key.replace("_"," ").toUpperCase()}</div>
                  <div className="stat-val c-text" style={{fontSize:12}}>{typeof v==="number"?v.toFixed(2):v}</div>
                  {chg !== undefined && (
                    <div className={`xs ${Number(chg)>=0?"c-bull":"c-bear"}`}>
                      {Number(chg)>=0?"+":""}{Number(chg).toFixed(2)}%
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {regimeText && (
        <div className="analysis">{regimeText.slice(0, 400)}{regimeText.length > 400 ? "..." : ""}</div>
      )}
    </div>
  );
}
''')

# ── components/BetaPanel.tsx ────────────────────────────────
w("components/BetaPanel.tsx", '''\
"use client";

function tagClass(t: string) {
  const s = t.toLowerCase();
  if (s.includes("mom"))  return "tag tag-mom";
  if (s.includes("del"))  return "tag tag-del";
  if (s.includes("brk") || s.includes("break")) return "tag tag-brk";
  if (s.includes("con"))  return "tag tag-con";
  return "tag tag-def";
}

export default function BetaPanel({ data }: { data: any }) {
  if (!data) return <div className="panel"><div className="c-dim small">Beta report unavailable</div></div>;

  const screens   = data.screens   || {};
  const synth     = data.synthesis || {};
  const composite = (screens.composite || []).slice(0, 12);
  const regime    = data.regime_used || data.regime || "";

  return (
    <div className="panel">
      <div className="panel-title">
        <span className="c-bull">&#9672;</span> BETA &mdash; SCREENER
        <span className="ml">
          {regime && <span className="tag tag-del" style={{marginRight:6}}>{regime}</span>}
          <span style={{fontSize:10,color:"var(--dim)"}}>{data.start_date} &rarr; {data.end_date}</span>
        </span>
      </div>

      <div className="stat-grid sg4" style={{marginBottom:10}}>
        {[
          {l:"Universe",  v:data.total_symbols,                                   c:"c-text"},
          {l:"Composite", v:composite.length,                                     c:"c-accent"},
          {l:"Profitable",v:synth.profitable_count ?? "—",                        c:"c-bull"},
          {l:"Streak>2",  v:synth.streak_count ?? composite.filter((s:any)=>s.streak>1).length, c:"c-warn"},
        ].map(({l,v,c})=>(
          <div key={l} className="stat-box">
            <div className={`stat-val ${c}`}>{v ?? "—"}</div>
            <div className="stat-lbl">{l}</div>
          </div>
        ))}
      </div>

      <div className="sec-lbl">Composite Picks</div>
      <table className="tbl">
        <thead><tr>
          <th>Symbol</th><th>Score</th><th className="r">Chg%</th><th className="r">Del%</th><th>Tags</th>
        </tr></thead>
        <tbody>
          {composite.map((s:any) => {
            const pct = Number(s.pct_chg ?? 0);
            const scr = Number(s.score ?? 0);
            const barW = Math.min(100, (scr/10)*100);
            const barC = barW>70?"#26c485":barW>40?"#e3b341":"#58a6ff";
            const tags = (s.screens || "").toString().split(",").filter(Boolean).slice(0,2);
            return (
              <tr key={s.symbol}>
                <td className="c-text bold">
                  {s.symbol}
                  {(s.streak ?? 0) > 1 && <span className="c-warn" style={{marginLeft:4}}>&#9733;{s.streak}d</span>}
                  {s.earnings_flag && <span className="c-accent" style={{marginLeft:4,fontSize:9}}>EPS</span>}
                </td>
                <td>
                  <div style={{display:"flex",alignItems:"center",gap:4}}>
                    <span className="c-accent" style={{minWidth:24,textAlign:"right"}}>{scr.toFixed(1)}</span>
                    <div className="bar-wrap" style={{width:48}}><div className="bar-fill" style={{width:`${barW}%`,background:barC}} /></div>
                  </div>
                </td>
                <td className={`r ${pct>=0?"c-bull":"c-bear"}`}>{pct>=0?"+":""}{pct.toFixed(2)}%</td>
                <td className="r c-dim">{Number(s.avg_deliv_pct??0).toFixed(1)}%</td>
                <td><div style={{display:"flex",gap:3,flexWrap:"wrap"}}>{tags.map((t:string)=><span key={t} className={tagClass(t)}>{t.trim()}</span>)}</div></td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="col2" style={{marginTop:10}}>
        <div>
          <div className="sec-lbl">52W Breakouts</div>
          {(data.w52||[]).slice(0,5).map((s:any)=>(
            <div key={s.symbol} style={{display:"flex",justifyContent:"space-between",padding:"2px 0",fontSize:11}}>
              <span className="c-warn">{s.symbol}</span>
              <span className="c-dim">{Number(s.pct_chg||0).toFixed(2)}%</span>
            </div>
          ))}
        </div>
        <div>
          <div className="sec-lbl">Sector Rotation</div>
          {Object.entries(data.sector_rotation||{}).slice(0,5).map(([sec,cnt])=>(
            <div key={sec} style={{display:"flex",justifyContent:"space-between",padding:"2px 0",fontSize:11}}>
              <span className="c-text truncate">{sec}</span>
              <span className="c-accent">{cnt as number}</span>
            </div>
          ))}
        </div>
      </div>

      {synth.summary && <div className="analysis">{synth.summary}</div>}
    </div>
  );
}
''')

# ── components/GammaPanel.tsx ────────────────────────────────
w("components/GammaPanel.tsx", '''\
"use client";

export default function GammaPanel({ data }: { data: any }) {
  if (!data) return <div className="panel"><div className="c-dim small">Gamma report unavailable</div></div>;

  const eq       = data.eq_flow || {};
  const metrics  = eq.metrics   || {};
  const flowTable= (eq.flow_table||[]).slice(0,8);
  const score    = Number(data.flow_score ?? 0);
  const scorePct = Math.min(100, Math.abs(score));
  const fno      = data.fno_positioning || {};
  const maxCr    = Math.max(...flowTable.map((r:any)=>Math.abs(r.net_fii||r.fii_net||0)),1);
  const scoreColor = score>=0?"#00d4aa":"#f85149";

  return (
    <div className="panel">
      <div className="panel-title">
        <span style={{color:"#00d4aa"}}>&#9672;</span> GAMMA &mdash; FII/DII FLOWS
        <span className="ml" style={{fontSize:10,color:"var(--dim)"}}>{data.start_date} &rarr; {data.end_date}</span>
      </div>

      <div style={{display:"flex",gap:14,marginBottom:10,alignItems:"center"}}>
        <div style={{position:"relative",width:64,height:64,flexShrink:0}}>
          <svg viewBox="0 0 64 64" style={{width:"100%",height:"100%"}}>
            <circle cx="32" cy="32" r="26" fill="none" stroke="var(--border)" strokeWidth="6"/>
            <circle cx="32" cy="32" r="26" fill="none" stroke={scoreColor} strokeWidth="6"
              strokeDasharray={`${scorePct*1.634} 163.4`}
              style={{transformOrigin:"center",transform:"rotate(-90deg)"}}/>
          </svg>
          <div style={{position:"absolute",inset:0,display:"flex",alignItems:"center",justifyContent:"center"}}>
            <span style={{fontSize:13,fontWeight:700,color:scoreColor}}>{score.toFixed(0)}</span>
          </div>
        </div>
        <div style={{flex:1,fontSize:11}}>
          {[
            ["FII Cumulative", `\u20B9${Number(metrics.fii_cumulative_cr||0).toFixed(0)} Cr`, Number(metrics.fii_cumulative_cr||0)>=0?"#00d4aa":"#f85149"],
            ["DII Cumulative", `\u20B9${Number(metrics.dii_cumulative_cr||0).toFixed(0)} Cr`, Number(metrics.dii_cumulative_cr||0)>=0?"#58a6ff":"#f85149"],
            ["FII Trend",      metrics.fii_trend||"—", "var(--text)"],
          ].map(([l,v,c])=>(
            <div key={String(l)} style={{display:"flex",justifyContent:"space-between",padding:"2px 0"}}>
              <span style={{color:"var(--dim)"}}>{l}</span>
              <span style={{color:String(c)}}>{v}</span>
            </div>
          ))}
          <div style={{display:"flex",gap:10,marginTop:3,fontSize:10}}>
            <span className="c-bull">&#9650; {metrics.fii_buy_days||0}d buy</span>
            <span className="c-bear">&#9660; {metrics.fii_sell_days||0}d sell</span>
            {Number(metrics.fii_consec_buy_days)>0 &&
              <span className="c-accent">&#9733;{metrics.fii_consec_buy_days}d consec</span>}
          </div>
        </div>
      </div>

      <div className="sec-lbl">Recent Flows (&#8377; Cr)</div>
      <table className="tbl">
        <thead><tr>
          <th>Date</th><th className="r">FII Net</th><th className="r">DII Net</th><th style={{paddingLeft:8}}>Flow</th>
        </tr></thead>
        <tbody>
          {flowTable.map((r:any,i:number)=>{
            const fNet = Number(r.fii_net_value ?? r.net_fii ?? r.fii_net ?? 0);
            const dNet = Number(r.dii_net_value ?? r.dii_net ?? 0);
            const barW = Math.min(100, Math.abs(fNet/maxCr)*100);
            const barC = fNet>=0?"#00d4aa":"#f85149";
            return (
              <tr key={i}>
                <td className="c-dim">{r.date||r.DATE1}</td>
                <td className={`r ${fNet>=0?"c-accent":"c-bear"}`}>{(fNet/100).toFixed(0)}</td>
                <td className={`r ${dNet>=0?"c-info":"c-bear"}`}>{(dNet/100).toFixed(0)}</td>
                <td style={{paddingLeft:8}}>
                  <div className="bar-wrap" style={{width:60}}><div className="bar-fill" style={{width:`${barW}%`,background:barC}}/></div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {Object.keys(fno).length>0 && (
        <div style={{marginTop:8}}>
          <div className="sec-lbl">F&amp;O Positioning</div>
          {Object.entries(fno).slice(0,4).map(([k,v])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",fontSize:11,padding:"2px 0"}}>
              <span className="c-dim">{k.replace(/_/g," ")}</span>
              <span className="c-text">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
      {data.analysis && <div className="analysis">{data.analysis}</div>}
    </div>
  );
}
''')

# ── components/DeltaPanel.tsx ────────────────────────────────
w("components/DeltaPanel.tsx", '''\
"use client";

export default function DeltaPanel({ data }: { data: any }) {
  if (!data) return <div className="panel"><div className="c-dim small">Delta report unavailable</div></div>;

  const score      = Number(data.risk_score ?? 50);
  const level      = (data.risk_level||"").toLowerCase();
  const levelColor = level.includes("low")?"var(--bull)":level.includes("high")?"var(--bear)":"var(--warn)";
  const gaugeColor = score<35?"#26c485":score<65?"#e3b341":"#f85149";
  const dash       = Math.min(100,score)*1.634;
  const riskFlags  = data.risk_flags  || [];
  const greenFlags = data.green_flags || [];
  const insiders   = (data.insider_activity||[]).slice(0,6);
  const corps      = (data.corporate_actions||[]).slice(0,4);

  return (
    <div className="panel">
      <div className="panel-title">
        <span className="c-bear">&#9672;</span> DELTA &mdash; RISK ENGINE
        <span className="ml" style={{fontSize:10,color:"var(--dim)"}}>{data.start_date} &rarr; {data.end_date}</span>
      </div>

      <div style={{display:"flex",gap:14,marginBottom:10,alignItems:"center"}}>
        <div style={{position:"relative",width:72,height:72,flexShrink:0}}>
          <svg viewBox="0 0 64 64" style={{width:"100%",height:"100%"}}>
            <circle cx="32" cy="32" r="26" fill="none" stroke="var(--border)" strokeWidth="6"/>
            <circle cx="32" cy="32" r="26" fill="none" stroke={gaugeColor} strokeWidth="6"
              strokeDasharray={`${dash} 163.4`}
              style={{transformOrigin:"center",transform:"rotate(-90deg)"}}/>
          </svg>
          <div style={{position:"absolute",inset:0,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center"}}>
            <span style={{fontSize:15,fontWeight:700,color:gaugeColor}}>{score.toFixed(0)}</span>
            <span style={{fontSize:8,color:"var(--dim)"}}>RISK</span>
          </div>
        </div>
        <div style={{flex:1,fontSize:11}}>
          {[
            ["Risk Level",      data.risk_level||"—",  levelColor],
            ["VIX",             data.vix?Number(data.vix).toFixed(2):"—", "var(--text)"],
            ["High PE Stocks",  String(data.high_pe_count??  "—"), "var(--warn)"],
            ["Quality Universe",String(data.quality_count ?? "—"), "var(--bull)"],
          ].map(([l,v,c])=>(
            <div key={String(l)} style={{display:"flex",justifyContent:"space-between",padding:"2px 0"}}>
              <span style={{color:"var(--dim)"}}>{l}</span>
              <span style={{color:String(c),fontWeight:600}}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="col2" style={{marginBottom:10}}>
        <div>
          <div className="sec-lbl">Risk Flags</div>
          {riskFlags.length===0&&<div className="c-dim xs">None</div>}
          {riskFlags.slice(0,5).map((f:string,i:number)=>(
            <div key={i} style={{fontSize:10,color:"var(--bear)",padding:"1px 0",lineHeight:1.4}}>&#8226; {f}</div>
          ))}
        </div>
        <div>
          <div className="sec-lbl">Green Flags</div>
          {greenFlags.length===0&&<div className="c-dim xs">None</div>}
          {greenFlags.slice(0,5).map((f:string,i:number)=>(
            <div key={i} style={{fontSize:10,color:"var(--bull)",padding:"1px 0",lineHeight:1.4}}>&#8226; {f}</div>
          ))}
        </div>
      </div>

      {insiders.length>0 && (
        <>
          <div className="sec-lbl">Insider Activity</div>
          <table className="tbl">
            <thead><tr><th>Symbol</th><th>Name</th><th>Type</th><th className="r">Val (Cr)</th></tr></thead>
            <tbody>
              {insiders.map((ins:any,i:number)=>{
                const buy=(ins.transaction_type||"").toLowerCase().includes("buy")||(ins.transaction_type||"").toLowerCase().includes("acqui");
                return (
                  <tr key={i}>
                    <td className="c-accent bold">{ins.symbol}</td>
                    <td className="c-dim truncate">{ins.name}</td>
                    <td style={{color:buy?"var(--bull)":"var(--bear)"}}>{buy?"BUY":"SELL"}</td>
                    <td className="r c-text">{ins.value?(ins.value/10000000).toFixed(2):"—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      {corps.length>0 && (
        <div style={{marginTop:8}}>
          <div className="sec-lbl">Corporate Actions</div>
          {corps.map((ca:any,i:number)=>(
            <div key={i} style={{display:"flex",justifyContent:"space-between",fontSize:11,padding:"2px 0"}}>
              <span className="c-warn">{ca.symbol||ca.SYMBOL}</span>
              <span className="c-dim">{ca.ex_date||ca.EX_DATE}</span>
              <span className="c-text">{(ca.purpose||ca.PURPOSE||"").slice(0,30)}</span>
            </div>
          ))}
        </div>
      )}
      {data.analysis && <div className="analysis">{data.analysis}</div>}
    </div>
  );
}
''')

# ── components/StreakBoard.tsx ────────────────────────────────
w("components/StreakBoard.tsx", '''\
"use client";
import { useEffect, useState } from "react";
interface Row { symbol:string; streak:number; total_appearances:number; avg_score:number; bull_days:number; last_seen:string; }

export default function StreakBoard() {
  const [rows,    setRows]    = useState<Row[]>([]);
  const [error,   setError]   = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(()=>{
    fetch("/api/streak").then(r=>r.json())
      .then(d=>{setRows(d.streak||[]); if(d.error) setError(d.error);})
      .catch(e=>setError(e.message))
      .finally(()=>setLoading(false));
  },[]);

  const maxApp = Math.max(...rows.map(r=>r.total_appearances),1);

  return (
    <div className="panel">
      <div className="panel-title">
        <span className="c-warn">&#9672;</span> STREAK LEADERBOARD
        <span className="ml" style={{fontSize:10,color:"var(--dim)"}}>signals_history &middot; live</span>
      </div>
      {loading && <div className="c-dim small">Querying signals_history...</div>}
      {error   && <div className="c-bear small">DB error: {error}</div>}
      {!loading&&rows.length===0&&!error&&<div className="c-dim small">No data yet.</div>}
      {rows.length>0&&(
        <table className="tbl">
          <thead><tr>
            <th>#</th><th>Symbol</th><th>Streak</th><th>Appearances</th>
            <th className="r">Avg Score</th><th className="r">Last Seen</th>
          </tr></thead>
          <tbody>
            {rows.map((r,i)=>{
              const pct=(r.total_appearances/maxApp)*100;
              const win=r.total_appearances>0?((r.bull_days/r.total_appearances)*100).toFixed(0):"0";
              return (
                <tr key={r.symbol}>
                  <td className="c-muted">{i+1}</td>
                  <td className="c-accent bold">{r.symbol}</td>
                  <td>{r.streak>0
                    ?<span className="c-warn bold">{r.streak}d</span>
                    :<span className="c-muted">-</span>}
                  </td>
                  <td>
                    <div style={{display:"flex",alignItems:"center",gap:6}}>
                      <span className="c-text" style={{minWidth:18,textAlign:"right"}}>{r.total_appearances}</span>
                      <div className="bar-wrap" style={{width:60}}><div className="bar-fill" style={{width:`${pct}%`,background:"#00d4aa"}}/></div>
                      <span className="c-dim xs">{win}% bull</span>
                    </div>
                  </td>
                  <td className="r c-info">{Number(r.avg_score).toFixed(1)}</td>
                  <td className="r c-dim">{r.last_seen}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
''')

# ── app/page.tsx ─────────────────────────────────────────────
w("app/page.tsx", '''\
"use client";
import { useEffect, useState, useCallback } from "react";
import AlphaPanel  from "@/components/AlphaPanel";
import BetaPanel   from "@/components/BetaPanel";
import GammaPanel  from "@/components/GammaPanel";
import DeltaPanel  from "@/components/DeltaPanel";
import StreakBoard from "@/components/StreakBoard";
import RegimePill  from "@/components/RegimePill";

interface Reports { alpha:any; beta:any; gamma:any; delta:any; fetched_at:string; }

export default function MICCDashboard() {
  const [data,      setData]      = useState<Reports|null>(null);
  const [lastFetch, setLastFetch] = useState("");
  const [err,       setErr]       = useState("");
  const [countdown, setCountdown] = useState(60);
  const [loading,   setLoading]   = useState(true);

  const fetchData = useCallback(async()=>{
    try {
      const d = await fetch("/api/reports",{cache:"no-store"}).then(r=>r.json());
      setData(d); setLastFetch(new Date().toLocaleTimeString("en-IN",{hour12:false})); setErr("");
    } catch(e:any){ setErr(e.message); }
    finally{ setLoading(false); setCountdown(60); }
  },[]);

  useEffect(()=>{ fetchData(); const t=setInterval(fetchData,60000); return()=>clearInterval(t); },[fetchData]);
  useEffect(()=>{ const t=setInterval(()=>setCountdown(c=>c<=1?60:c-1),1000); return()=>clearInterval(t); },[]);

  const regimeText = typeof data?.alpha?.regime_analysis === "string" ? data.alpha.regime_analysis : "";
  const regimeWord = regimeText.match(/BULLISH|BEARISH|NEUTRAL|SIDEWAYS|CAUTIOUS/i)?.[0] || data?.beta?.regime || "";
  const marketDate = data?.alpha?.latest_market_date ?? "";

  return (
    <>
      <header className="header">
        <span className="header-logo">MICC</span>
        <span className="header-sub">Market Intelligence Command Center</span>
        <div className="header-right">
          {err && <span className="c-bear">{err}</span>}
          {loading && <span className="c-dim">Loading...</span>}
          {marketDate && <span className="c-dim"><span style={{color:"var(--muted)"}}>Market:</span> {marketDate}</span>}
          {regimeWord && <RegimePill regime={regimeWord} />}
          <span className="c-dim">
            {lastFetch||"—"}
            <span style={{color:"var(--muted)",marginLeft:4}}>+{countdown}s</span>
          </span>
          <button className="refresh-btn" onClick={fetchData}>&#8635;</button>
        </div>
      </header>
      <div className="dashboard">
        <div className="grid2">
          <AlphaPanel data={data?.alpha} />
          <BetaPanel  data={data?.beta}  />
        </div>
        <div className="grid2">
          <GammaPanel data={data?.gamma} />
          <DeltaPanel data={data?.delta} />
        </div>
        <StreakBoard />
        <div className="footer">MICC &middot; LOCAL &middot; NOT FOR DISTRIBUTION &middot; {new Date().getFullYear()}</div>
      </div>
    </>
  );
}
''')

# ── postcss.config.js — minimal, no Tailwind ────────────────
w("postcss.config.js", """\
module.exports = { plugins: {} };
""")

print("\n✅ Done. Pure CSS — no Tailwind dependency.")
print("\nRun:")
print("  cd micc-dashboard")
print("  Remove-Item .next -Recurse -Force")
print("  npm run dev")
