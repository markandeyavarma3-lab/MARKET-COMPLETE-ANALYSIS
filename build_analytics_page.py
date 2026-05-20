# -*- coding: utf-8 -*-
r"""
build_analytics_page.py  --  Run from D:\MICC

Builds /analytics page:
  - Fundamentals screener table (PE, PB, ROE, ROCE, promoter%, D/E, revenue growth)
  - RBI repo rate history chart with NIFTY 50 overlay
  - Quality filter: ROCE>15, ROE>15, D/E<1, Promoter>50
  - Sortable, filterable, searchable
  - Links to /stocks/[symbol] and /deep/[symbol]

Run: py D:\MICC\build_analytics_page.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path, content, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

# =============================================================================
# [1]  /api/analytics/route.ts
# =============================================================================
print("\n[1/3] Writing /api/analytics/route.ts ...")

api = r"""import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DA = "D:/MICC";
const PY = "py";

function san(s: string) {
  return s.replace(/:[ \t]*NaN\b/g,": null").replace(/:[ \t]*-?Infinity\b/g,": null");
}
function qdb(sql: string, params: (string|number)[] = []): any[] {
  const payload = Buffer.from(JSON.stringify({ sql, params })).toString("base64");
  const script = [
    "import sqlite3,json,base64,sys",
    "d=json.loads(base64.b64decode(sys.argv[1]))",
    "conn=sqlite3.connect(r'D:/marketDB/db/market.db',timeout=15)",
    "conn.row_factory=sqlite3.Row",
    "rows=conn.execute(d['sql'],d['params']).fetchall()",
    "print(json.dumps([dict(r) for r in rows],default=str))",
    "conn.close()",
  ].join("\n");
  const r = spawnSync(PY,["-c",script,payload],{cwd:DA,encoding:"utf-8",timeout:20000});
  if(r.status!==0){console.error("[analytics]",r.stderr?.slice(0,200));return[];}
  try{return JSON.parse(san(r.stdout.trim()||"[]"));}catch{return[];}
}

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const limit  = parseInt(url.searchParams.get("limit") || "500");
  const filter = url.searchParams.get("filter") || "all";  // all|quality|value|growth

  // Build WHERE clause based on filter
  let where = "WHERE f.pe_ratio IS NOT NULL";
  if (filter === "quality") {
    where += " AND f.roce >= 15 AND f.roe >= 15 AND f.debt_equity <= 1 AND f.promoter_pct >= 50";
  } else if (filter === "value") {
    where += " AND f.pe_ratio <= 20 AND f.pb_ratio <= 3";
  } else if (filter === "growth") {
    where += " AND f.revenue_growth >= 15 AND f.profit_growth >= 15";
  }

  const stocks = qdb(`
    SELECT
      f.symbol,
      ROUND(CAST(f.pe_ratio      AS REAL),1) AS pe,
      ROUND(CAST(f.pb_ratio      AS REAL),1) AS pb,
      ROUND(CAST(f.ps_ratio      AS REAL),1) AS ps,
      ROUND(CAST(f.roe           AS REAL),1) AS roe,
      ROUND(CAST(f.roce          AS REAL),1) AS roce,
      ROUND(CAST(f.roa           AS REAL),1) AS roa,
      ROUND(CAST(f.debt_equity   AS REAL),1) AS de,
      ROUND(CAST(f.promoter_pct  AS REAL),1) AS promoter,
      ROUND(CAST(f.fii_pct       AS REAL),1) AS fii,
      ROUND(CAST(f.dii_pct       AS REAL),1) AS dii,
      ROUND(CAST(f.market_cap_cr AS REAL),0) AS mcap,
      ROUND(CAST(f.revenue_growth AS REAL),1) AS rev_growth,
      ROUND(CAST(f.profit_growth  AS REAL),1) AS prof_growth,
      ROUND(CAST(f.current_ratio  AS REAL),2) AS curr_ratio,
      ROUND(CAST(f.eps           AS REAL),2)  AS eps,
      ROUND(CAST(f.div_yield     AS REAL),2)  AS div_yield,
      ROUND(CAST(f.beta          AS REAL),2)  AS beta,
      f.current_price,
      f.high_52w,
      f.low_52w,
      f.source,
      ROUND(CAST(c.conviction_score AS REAL),1) AS conviction,
      t.rsi_14,
      t.adx_14,
      ROUND(CAST(t.pct_from_52w_high AS REAL),1) AS pct_52h
    FROM screener_fundamentals_v2 f
    LEFT JOIN symbol_conviction c ON c.symbol = f.symbol
    LEFT JOIN symbol_technicals t ON t.symbol = f.symbol
    ${where}
    ORDER BY CAST(f.market_cap_cr AS REAL) DESC NULLS LAST
    LIMIT ?
  `, [limit]);

  // RBI rate history for chart
  const rbi = qdb(
    "SELECT date, repo_rate, reverse_repo, crr FROM rbi_monetary_data " +
    "WHERE repo_rate IS NOT NULL ORDER BY date ASC"
  );

  // Nifty history for overlay (monthly)
  const nifty = qdb(
    "SELECT date, closing_index_value AS close FROM market_snapshot " +
    "WHERE index_name='NIFTY 50' ORDER BY date ASC"
  );

  // Summary stats
  const stats = qdb(`
    SELECT
      COUNT(*) AS total,
      COALESCE(ROUND(AVG(CASE WHEN pe_ratio BETWEEN 1 AND 200 THEN pe_ratio END),1),0) AS avg_pe,
      COALESCE(ROUND(AVG(CASE WHEN roe IS NOT NULL THEN roe END),1),0) AS avg_roe,
      COALESCE(ROUND(AVG(CASE WHEN roce IS NOT NULL THEN roce END),1),0) AS avg_roce,
      COALESCE(ROUND(AVG(CASE WHEN promoter_pct IS NOT NULL THEN promoter_pct END),1),0) AS avg_promoter,
      SUM(CASE WHEN roce >= 15 AND roe >= 15 AND debt_equity <= 1 THEN 1 END) AS quality_count,
      SUM(CASE WHEN pe_ratio <= 20 AND pb_ratio <= 3 THEN 1 END) AS value_count,
      SUM(CASE WHEN revenue_growth >= 15 AND profit_growth >= 15 THEN 1 END) AS growth_count
    FROM screener_fundamentals_v2
    WHERE pe_ratio IS NOT NULL
  `)[0];

  return NextResponse.json({
    stocks,
    rbi,
    nifty: nifty.slice(-252),  // last 1 year
    stats,
    filter,
    generated_at: new Date().toISOString(),
  });
}
"""

write(SRC / "api" / "analytics" / "route.ts", api, "/api/analytics/route.ts")

# =============================================================================
# [2]  /analytics/page.tsx
# =============================================================================
print("\n[2/3] Writing /analytics/page.tsx ...")

page = r"""
"use client";
import { useEffect, useState, useMemo } from "react";
import NavBar from "@/components/NavBar";

interface Stock {
  symbol: string; pe: number|null; pb: number|null; ps: number|null;
  roe: number|null; roce: number|null; roa: number|null; de: number|null;
  promoter: number|null; fii: number|null; dii: number|null;
  mcap: number|null; rev_growth: number|null; prof_growth: number|null;
  curr_ratio: number|null; eps: number|null; div_yield: number|null;
  beta: number|null; current_price: number|null; high_52w: number|null;
  low_52w: number|null; source: string; conviction: number|null;
  rsi_14: number|null; adx_14: number|null; pct_52h: number|null;
}
interface RBI { date: string; repo_rate: number; }
interface Stats {
  total: number; avg_pe: number; avg_roe: number; avg_roce: number;
  avg_promoter: number; quality_count: number; value_count: number; growth_count: number;
}
interface Resp {
  stocks: Stock[]; rbi: RBI[]; stats: Stats; filter: string; generated_at: string;
}

const fn = (v: number|null, d=1) => v==null ? "--" : v.toLocaleString("en-IN",{maximumFractionDigits:d});
const fc = (v: number|null, good: number, bad: number, higher=true) => {
  if (v==null) return "var(--dim)";
  if (higher) return v>=good?"var(--bull)":v<=bad?"var(--bear)":"var(--text)";
  return v<=good?"var(--bull)":v>=bad?"var(--bear)":"var(--text)";
};

type SortKey = keyof Stock;

export default function AnalyticsPage() {
  const [data,    setData]    = useState<Resp|null>(null);
  const [loading, setLoading] = useState(true);
  const [filter,  setFilter]  = useState("all");
  const [search,  setSearch]  = useState("");
  const [sortBy,  setSortBy]  = useState<SortKey>("mcap");
  const [sortAsc, setSortAsc] = useState(false);
  const [tab,     setTab]     = useState<"table"|"rbi">("table");

  useEffect(() => {
    setLoading(true);
    fetch(`/api/analytics?filter=${filter}&limit=500`)
      .then(r=>r.json()).then(d=>{setData(d);setLoading(false);})
      .catch(()=>setLoading(false));
  }, [filter]);

  const rows = useMemo(() => {
    if (!data?.stocks) return [];
    let r = [...data.stocks];
    if (search) { const q=search.toUpperCase(); r=r.filter(x=>x.symbol.includes(q)); }
    const m = sortAsc ? 1 : -1;
    return r.sort((a,b) => {
      const av=(a as any)[sortBy], bv=(b as any)[sortBy];
      return typeof av==="string" ? m*av.localeCompare(bv) : m*((+av||0)-(+bv||0));
    });
  }, [data, search, sortBy, sortAsc]);

  function Th({col,label,right}:{col:SortKey;label:string;right?:boolean}) {
    const active = sortBy===col;
    return (
      <th onClick={()=>{if(sortBy===col)setSortAsc(a=>!a);else{setSortBy(col);setSortAsc(false);}}}
        style={{padding:"7px 8px",cursor:"pointer",userSelect:"none",
          textAlign:right?"right":"left",whiteSpace:"nowrap",
          color:active?"var(--accent)":"var(--dim)",
          fontFamily:"monospace",fontSize:9,fontWeight:700,letterSpacing:"0.08em",
          background:"var(--surface)",
          borderBottom:`2px solid ${active?"var(--accent)":"var(--border)"}`}}>
        {label}{active?(sortAsc?" ^":" v"):""}
      </th>
    );
  }

  const FILTERS = ["all","quality","value","growth"] as const;
  const FILTER_LABELS: Record<string,string> = {
    all:"All Stocks", quality:"Quality (ROCE>15 ROE>15 D/E<1)", value:"Value (PE<20 PB<3)", growth:"Growth (Rev>15% Prof>15%)"
  };

  const s = data?.stats;

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)",color:"var(--text)"}}>
      <NavBar />
      <div style={{padding:"14px 20px",maxWidth:1600,margin:"0 auto"}}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"center",gap:14,flexWrap:"wrap",marginBottom:14}}>
          <div>
            <div style={{fontFamily:"monospace",fontSize:16,fontWeight:700,
                         letterSpacing:"0.12em",color:"var(--accent)"}}>ANALYTICS</div>
            <div style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginTop:1}}>
              Fundamentals screener + RBI macro
            </div>
          </div>
          {s && (
            <>
              {[
                ["STOCKS",   s.total],
                ["AVG PE",   s.avg_pe],
                ["AVG ROE",  s.avg_roe + "%"],
                ["AVG ROCE", s.avg_roce + "%"],
                ["QUALITY",  s.quality_count],
                ["VALUE",    s.value_count],
                ["GROWTH",   s.growth_count],
              ].map(([l,v]) => (
                <div key={l as string} style={{padding:"5px 10px",background:"var(--surface)",
                                               border:"1px solid var(--border)",borderRadius:4}}>
                  <div style={{fontFamily:"monospace",fontSize:8,color:"var(--dim)"}}>{l}</div>
                  <div style={{fontFamily:"monospace",fontSize:13,fontWeight:700,color:"var(--accent)"}}>{v}</div>
                </div>
              ))}
            </>
          )}
        </div>

        {/* Tabs */}
        <div style={{display:"flex",gap:6,marginBottom:10}}>
          {(["table","rbi"] as const).map(t => (
            <button key={t} onClick={()=>setTab(t)} style={{
              padding:"5px 14px",fontFamily:"monospace",fontSize:10,cursor:"pointer",borderRadius:4,
              background:tab===t?"var(--accent)":"var(--surface)",
              color:tab===t?"#000":"var(--dim)",
              border:`1px solid ${tab===t?"var(--accent)":"var(--border)"}`}}>
              {t==="table"?"FUNDAMENTALS":"RBI RATES"}
            </button>
          ))}
        </div>

        {tab === "table" && (
          <>
            {/* Controls */}
            <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10,alignItems:"center"}}>
              <input value={search} onChange={e=>setSearch(e.target.value)}
                placeholder="Symbol..." style={{
                  background:"var(--surface)",border:"1px solid var(--border)",
                  borderRadius:4,color:"var(--text)",fontFamily:"monospace",
                  fontSize:12,padding:"5px 10px",width:130,outline:"none"}} />
              {FILTERS.map(f => (
                <button key={f} onClick={()=>setFilter(f)} style={{
                  padding:"4px 10px",fontFamily:"monospace",fontSize:10,cursor:"pointer",borderRadius:4,
                  background:filter===f?"var(--accent)":"var(--surface)",
                  color:filter===f?"#000":"var(--dim)",
                  border:`1px solid ${filter===f?"var(--accent)":"var(--border)"}`}}>
                  {f.toUpperCase()}
                </button>
              ))}
              <span style={{fontFamily:"monospace",fontSize:10,color:"var(--dim)",marginLeft:"auto"}}>
                {rows.length} stocks
              </span>
            </div>

            {loading ? (
              <div style={{padding:60,textAlign:"center",fontFamily:"monospace",fontSize:12,color:"var(--dim)"}}>
                Loading fundamentals...
              </div>
            ) : (
              <div style={{overflowX:"auto",borderRadius:6,border:"1px solid var(--border)"}}>
                <table style={{width:"100%",borderCollapse:"collapse"}}>
                  <thead>
                    <tr>
                      <th style={{padding:"7px 8px",background:"var(--surface)",width:28,
                                   borderBottom:"2px solid var(--border)",
                                   fontFamily:"monospace",fontSize:9,color:"var(--dim)",textAlign:"left"}}>#</th>
                      <Th col="symbol"     label="SYMBOL" />
                      <Th col="mcap"       label="MCAP_CR" right />
                      <Th col="pe"         label="P/E"    right />
                      <Th col="pb"         label="P/B"    right />
                      <Th col="roce"       label="ROCE%"  right />
                      <Th col="roe"        label="ROE%"   right />
                      <Th col="roa"        label="ROA%"   right />
                      <Th col="de"         label="D/E"    right />
                      <Th col="promoter"   label="PRO%"   right />
                      <Th col="fii"        label="FII%"   right />
                      <Th col="rev_growth" label="REVGR%" right />
                      <Th col="prof_growth"label="PROFGR%"right />
                      <Th col="curr_ratio" label="CR"     right />
                      <Th col="div_yield"  label="DIV%"   right />
                      <Th col="eps"        label="EPS"    right />
                      <Th col="conviction" label="CONV"   right />
                      <Th col="pct_52h"    label="52H%"   right />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => (
                      <tr key={row.symbol}
                        style={{borderBottom:"1px solid var(--border)"}}
                        onMouseEnter={e=>(e.currentTarget.style.background="rgba(255,255,255,0.02)")}
                        onMouseLeave={e=>(e.currentTarget.style.background="transparent")}>
                        <td style={{padding:"6px 8px",fontFamily:"monospace",fontSize:10,color:"var(--dim)"}}>{i+1}</td>
                        <td style={{padding:"6px 8px"}}>
                          <div style={{display:"flex",gap:6,alignItems:"center"}}>
                            <a href={`/stocks/${row.symbol}`} style={{
                              fontFamily:"monospace",fontSize:12,fontWeight:700,
                              color:"var(--text)",textDecoration:"none"}}>{row.symbol}</a>
                            <a href={`/deep/${row.symbol}`} style={{
                              fontFamily:"monospace",fontSize:9,color:"var(--dim)",textDecoration:"none"}}>DEEP</a>
                          </div>
                        </td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:"var(--dim)"}}>{fn(row.mcap,0)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.pe,15,30,false)}}>{fn(row.pe)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.pb,1,4,false)}}>{fn(row.pb)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.roce,15,8)}}>{fn(row.roce)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.roe,15,8)}}>{fn(row.roe)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.roa,10,5)}}>{fn(row.roa)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.de,0.5,2,false)}}>{fn(row.de)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.promoter,60,40)}}>{fn(row.promoter)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:"var(--info)"}}>{fn(row.fii)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.rev_growth,15,0)}}>{fn(row.rev_growth)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.prof_growth,15,0)}}>{fn(row.prof_growth)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:fc(row.curr_ratio,2,1)}}>{fn(row.curr_ratio,2)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:"var(--warn)"}}>{fn(row.div_yield,2)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11}}>{fn(row.eps,2)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:"var(--accent)"}}>{fn(row.conviction)}</td>
                        <td style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:row.pct_52h!=null&&row.pct_52h>-5?"var(--bull)":"var(--dim)"}}>{fn(row.pct_52h)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {rows.length===0&&<div style={{padding:40,textAlign:"center",fontFamily:"monospace",fontSize:12,color:"var(--dim)"}}>No stocks match filters.</div>}
              </div>
            )}
          </>
        )}

        {tab === "rbi" && data?.rbi && (
          <div style={{padding:"10px 0"}}>
            <div style={{fontFamily:"monospace",fontSize:11,color:"var(--dim)",marginBottom:10}}>
              RBI Repo Rate History
            </div>

            {/* Simple rate timeline */}
            <div style={{overflowX:"auto",borderRadius:6,border:"1px solid var(--border)"}}>
              <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead>
                  <tr>
                    {["DATE","REPO RATE","CHANGE","REVERSE REPO","CRR"].map(h => (
                      <th key={h} style={{padding:"7px 12px",background:"var(--surface)",
                                          fontFamily:"monospace",fontSize:10,color:"var(--dim)",
                                          textAlign:h==="DATE"?"left":"right",
                                          borderBottom:"2px solid var(--border)"}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...data.rbi].reverse().map((row, i, arr) => {
                    const prev = arr[i+1];
                    const change = prev ? row.repo_rate - prev.repo_rate : 0;
                    const cc = change > 0 ? "var(--bear)" : change < 0 ? "var(--bull)" : "var(--dim)";
                    return (
                      <tr key={row.date} style={{borderBottom:"1px solid var(--border)"}}>
                        <td style={{padding:"6px 12px",fontFamily:"monospace",fontSize:11}}>{row.date}</td>
                        <td style={{padding:"6px 12px",textAlign:"right",fontFamily:"monospace",fontSize:13,fontWeight:700,color:"var(--accent)"}}>
                          {row.repo_rate}%
                        </td>
                        <td style={{padding:"6px 12px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:cc}}>
                          {change !== 0 ? (change > 0 ? "+" : "") + change.toFixed(2) + "%" : "--"}
                        </td>
                        <td style={{padding:"6px 12px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:"var(--dim)"}}>
                          {(row as any).reverse_repo ? (row as any).reverse_repo + "%" : "--"}
                        </td>
                        <td style={{padding:"6px 12px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:"var(--dim)"}}>
                          {(row as any).crr ? (row as any).crr + "%" : "--"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
""".lstrip()

write(SRC / "analytics" / "page.tsx", page, "/analytics/page.tsx")

# =============================================================================
# [3]  Add ANALYTICS to NavBar if missing
# =============================================================================
print("\n[3/3] Checking NavBar...")
import re
for nb in (DASH / "src").rglob("NavBar.tsx"):
    src = nb.read_text(encoding="utf-8")
    if "/analytics" not in src:
        src = re.sub(
            r'(\{[^}]*href:\s*["\']\/conviction["\'][^}]*\})',
            r'\1\n  { href: "/analytics", label: "ANALYTICS" },',
            src, count=1
        )
        nb.write_text(src, encoding="utf-8")
        print("  [OK] ANALYTICS added to NavBar")
    else:
        print("  [OK] ANALYTICS already in NavBar")

print("""
======================================================================
  DONE
======================================================================

  Run in order:

  1. Fetch RBI rates:
       py D:\\MICC\\fetch_rbi_rates.py

  2. Run fundamentals scraper (if not done):
       py D:\\MICC\\data_pipeline\\scrape_fundamentals.py 500

  3. Restart dashboard:
       cd D:\\MICC\\micc-dashboard
       npm run dev

  4. Open:
       http://localhost:3000/analytics

  5. Push to git:
       & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
       & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "analytics page + fundamentals"
       & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push
""")
