import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { readFileSync } from "fs";
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
  if(r.status!==0){console.error("[fusion]",r.stderr?.slice(0,200));return[];}
  try{return JSON.parse(san(r.stdout.trim()||"[]"));}catch{return[];}
}

export const dynamic = "force-dynamic";

export async function GET() {
  let report: any = null;
  try {
    report = JSON.parse(san(readFileSync(`${DA}/agents/fusion/last_report.json`,"utf-8")));
  } catch {
    return NextResponse.json({
      picks:[],meta:null,regime:"UNKNOWN",nifty:0,n_total:0,
      error:"Run: py D:/MICC/agent_fusion.py",
      generated_at:new Date().toISOString(),
    });
  }

  const picks: any[] = report.picks ?? [];
  const meta          = report.meta  ?? {};

  if (picks.length === 0) {
    return NextResponse.json({
      picks:[],meta,regime:meta.regime??"UNKNOWN",nifty:meta.nifty??0,n_total:0,
      error:"No picks with 2+ layers. Run all agents then agent_fusion.py.",
      generated_at:new Date().toISOString(),
    });
  }

  const syms = picks.map((p:any)=>p.symbol);
  const ph   = syms.map(()=>"?").join(",");

  const techs = qdb(
    `SELECT symbol,rsi_14,adx_14,macd_line,macd_signal,
            ROUND(CAST(atr_14_pct AS REAL),2) AS atr_14_pct,
            ROUND(CAST(pct_from_52w_high AS REAL),1) AS pct_52h
     FROM symbol_technicals WHERE symbol IN (${ph})`,syms);
  const tMap:Record<string,any>={};
  for(const t of techs) tMap[t.symbol]=t;

  const prices = qdb(
    `SELECT symbol,close FROM stock_data
     WHERE date=(SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)
       AND symbol IN (${ph}) AND close IS NOT NULL`,syms);
  const pMap:Record<string,number>={};
  for(const p of prices) pMap[p.symbol]=parseFloat(p.close);

  const pats = qdb(
    `SELECT symbol,direction,
            ROUND(CAST(mean_ret AS REAL),2) AS mean_ret,
            ROUND(CAST(accuracy AS REAL)*100,1) AS win_pct,window_days
     FROM seasonality_patterns_v3
     WHERE anchor_mm_dd=strftime('%m-%d','now','localtime')
       AND fdr_reject=1 AND n_obs>=10 AND symbol IN (${ph})
     ORDER BY CAST(score_v2 AS REAL) DESC`,syms);
  const patMap:Record<string,any>={};
  for(const p of pats){if(!patMap[p.symbol])patMap[p.symbol]=p;}

  const nr=qdb("SELECT closing_index_value AS close FROM market_snapshot WHERE index_name='NIFTY 50' ORDER BY date DESC LIMIT 1");
  const nifty=parseFloat(nr[0]?.close??meta.nifty??"0");
  const regime=nifty>22000?"BULLISH":nifty>18000?"SIDEWAYS":nifty>0?"BEARISH":(meta.regime??"UNKNOWN");

  const enriched=picks.map((p:any)=>{
    const t=tMap[p.symbol]??{};
    return{
      ...p,
      rsi_14:   t.rsi_14??null,
      adx_14:   t.adx_14??null,
      atr_pct:  t.atr_14_pct??null,
      pct_52h:  t.pct_52h??null,
      macd_bull:(t.macd_line??0)>(t.macd_signal??0),
      price:    pMap[p.symbol]??null,
      today_pat:patMap[p.symbol]??null,
    };
  });

  return NextResponse.json({
    picks:enriched,meta,
    report_date:report.date??report.generated_at??null,
    regime,nifty,n_total:enriched.length,
    generated_at:new Date().toISOString(),
  });
}
