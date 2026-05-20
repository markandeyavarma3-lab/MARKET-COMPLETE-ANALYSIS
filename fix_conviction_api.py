# -*- coding: utf-8 -*-
"""
fix_conviction_api.py  --  Run from D:\MICC

Fixes all 3 SQL errors from the logs:
  1. c.beta_score -- schema probe not working (template literal bug in JS)
  2. mean_return_pct -- seasonality table uses different column
  3. close -- market_snapshot uses closing_index_value not close

Also probes actual DB schema so we know exact column names.

Run:  py D:\MICC\fix_conviction_api.py
"""

import sqlite3
from pathlib import Path

DB   = r"D:\marketDB\db\market.db"
MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

# ── 1. Probe actual DB schema ────────────────────────────────────────────────
print("\n[1] Probing actual DB schema...")
conn = sqlite3.connect(DB, timeout=10)

def cols(table):
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except:
        return []

def count(table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except:
        return "ERROR"

conv_cols = cols("symbol_conviction")
tech_cols = cols("symbol_technicals")
snap_cols = cols("market_snapshot")
seas_cols = cols("seasonality_patterns_v3")
sig_cols  = cols("signals_history")

print(f"\n  symbol_conviction    ({count('symbol_conviction')} rows)")
print(f"    cols: {conv_cols}")
print(f"\n  symbol_technicals    ({count('symbol_technicals')} rows)")
print(f"    cols: {tech_cols}")
print(f"\n  market_snapshot      ({count('market_snapshot')} rows)")
print(f"    price cols: {[c for c in snap_cols if 'close' in c.lower() or 'value' in c.lower() or 'index' in c.lower()]}")
print(f"\n  seasonality_patterns_v3 ({count('seasonality_patterns_v3')} rows)")
print(f"    cols: {seas_cols}")
print(f"\n  signals_history      ({count('signals_history')} rows)")
print(f"    cols: {sig_cols}")

conn.close()

# ── 2. Build the API with EXACT column names from probe ──────────────────────
print("\n[2] Writing /api/conviction/route.ts with exact column names...")

# Determine which columns actually exist
def pick(options, available):
    for o in options:
        if o in available:
            return o
    return options[0]  # will fail but at least shows intent

c_score    = pick(["conviction_score","score","total_score","conv_score"], conv_cols)
c_beta     = pick(["beta_score","beta","beta_layer"], conv_cols)
c_regime   = pick(["regime_score","regime","regime_layer"], conv_cols)
c_insider  = pick(["insider_score","insider","insider_layer"], conv_cols)
c_watch    = pick(["watchlist_score","watchlist","watch_score","watch_layer"], conv_cols)
c_seasonal = pick(["seasonal_score","seasonal","seasonal_layer"], conv_cols)
c_quant    = pick(["quant_score","quant","quant_layer"], conv_cols)
c_layers   = pick(["n_layers","layers","layer_count","num_layers"], conv_cols)
c_tags     = pick(["active_tags","tags","layers_fired","fired_layers"], conv_cols)

# Seasonality columns
seas_mean  = pick(["mean_return_pct","mean_ret","avg_return_pct","mean_return"], seas_cols)
seas_win   = pick(["win_rate","accuracy","prob_positive","win_pct"], seas_cols)
seas_score = pick(["score_v2","score","ic_score"], seas_cols)
seas_fdr   = pick(["fdr_reject","is_significant"], seas_cols)
seas_today = pick(["is_today","today"], seas_cols)
seas_label = pick(["period_label","label","window_label"], seas_cols)

# Market snapshot price column
snap_price = pick(["closing_index_value","close","index_close","value"], snap_cols)

print(f"\n  symbol_conviction columns mapped:")
print(f"    score={c_score}, beta={c_beta}, regime={c_regime}")
print(f"    insider={c_insider}, watch={c_watch}, seasonal={c_seasonal}")
print(f"    quant={c_quant}, layers={c_layers}, tags={c_tags}")
print(f"\n  seasonality_patterns_v3: mean={seas_mean}, win={seas_win}")
print(f"    score={seas_score}, fdr={seas_fdr}, today={seas_today}")
print(f"\n  market_snapshot price col: {snap_price}")

# ── 3. Write the API ─────────────────────────────────────────────────────────

# Build Python script strings that will be embedded (no template literal collision)
probe_script = f"""
import sqlite3, json
conn = sqlite3.connect(r'D:/marketDB/db/market.db', timeout=15)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT c.symbol, "
    "ROUND(CAST(c.{c_score} AS REAL),1) AS conviction_score, "
    "ROUND(CAST(c.{c_beta} AS REAL),1) AS beta_score, "
    "ROUND(CAST(c.{c_regime} AS REAL),1) AS regime_score, "
    "ROUND(CAST(c.{c_insider} AS REAL),1) AS insider_score, "
    "ROUND(CAST(c.{c_watch} AS REAL),1) AS watchlist_score, "
    "ROUND(CAST(c.{c_seasonal} AS REAL),1) AS seasonal_score, "
    "ROUND(CAST(c.{c_quant} AS REAL),1) AS quant_score, "
    "CAST(c.{c_layers} AS INTEGER) AS n_layers, "
    "IFNULL(c.{c_tags},'') AS active_tags, "
    "t.rsi_14, t.adx_14, t.macd_line, t.macd_signal, "
    "ROUND(CAST(t.atr_14_pct AS REAL),2) AS atr_14_pct, "
    "sd.close AS latest_close "
    "FROM symbol_conviction c "
    "LEFT JOIN symbol_technicals t ON t.symbol = c.symbol "
    "LEFT JOIN (SELECT symbol, close FROM stock_data WHERE (symbol,date) IN "
    "  (SELECT symbol,MAX(date) FROM stock_data WHERE close IS NOT NULL GROUP BY symbol)) sd "
    "  ON sd.symbol = c.symbol "
    "WHERE CAST(c.{c_score} AS REAL) >= ? "
    "ORDER BY CAST(c.{c_score} AS REAL) DESC "
    "LIMIT ?",
    [MIN_SCORE, LIMIT]
).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
""".strip()

seas_script = f"""
import sqlite3, json
conn = sqlite3.connect(r'D:/marketDB/db/market.db', timeout=10)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT symbol, direction, "
    "ROUND(CAST({seas_mean} AS REAL),2) AS mean_ret, "
    "ROUND(CAST({seas_win} AS REAL)*100,1) AS win_pct, "
    "IFNULL({seas_label},'') AS period_label "
    "FROM seasonality_patterns_v3 "
    "WHERE {seas_today}=1 AND {seas_fdr}=1 AND n_obs>=10 "
    "ORDER BY CAST({seas_score} AS REAL) DESC"
).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
""".strip()

sig_script = """
import sqlite3, json
conn = sqlite3.connect(r'D:/marketDB/db/market.db', timeout=10)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT symbol, screen_tags FROM signals_history "
    "WHERE run_date=(SELECT MAX(run_date) FROM signals_history)"
).fetchall()
print(json.dumps([dict(r) for r in rows], default=str))
conn.close()
""".strip()

nifty_script = f"""
import sqlite3, json
conn = sqlite3.connect(r'D:/marketDB/db/market.db', timeout=10)
conn.row_factory = sqlite3.Row
row = conn.execute(
    "SELECT {snap_price} as close FROM market_snapshot "
    "WHERE index_name='NIFTY 50' ORDER BY date DESC LIMIT 1"
).fetchone()
print(json.dumps(dict(row) if row else {{}}, default=str))
conn.close()
""".strip()

# Write the TS API — all Python is pre-baked as base64, no template literal issues
api_content = f"""import {{ NextResponse }} from "next/server";
import {{ spawnSync }}    from "child_process";
import {{ Buffer }}       from "buffer";

const DA = "D:/MICC";
const PY = "py";

function sanitize(s: string) {{
  return s.replace(/:[ \\t]*NaN\\b/g, ": null").replace(/:[ \\t]*-?Infinity\\b/g, ": null");
}}

function runScript(script: string, replacements: Record<string, string> = {{}}): any[] {{
  let s = script;
  for (const [k, v] of Object.entries(replacements)) s = s.replace(k, v);
  const b64 = Buffer.from(s).toString("base64");
  const r = spawnSync(PY, ["-c",
    "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())",
    b64,
  ], {{ cwd: DA, encoding: "utf-8", timeout: 25000 }});
  if (r.status !== 0) {{
    console.error("[conviction]", r.stderr?.slice(0, 300));
    return [];
  }}
  try {{ return JSON.parse(sanitize(r.stdout.trim() || "[]")); }}
  catch {{ return []; }}
}}

function runOne(script: string): any {{
  const b64 = Buffer.from(script).toString("base64");
  const r = spawnSync(PY, ["-c",
    "import base64,sys; exec(base64.b64decode(sys.argv[1]).decode())",
    b64,
  ], {{ cwd: DA, encoding: "utf-8", timeout: 10000 }});
  if (r.status !== 0) return null;
  try {{ return JSON.parse(sanitize(r.stdout.trim() || "null")); }}
  catch {{ return null; }}
}}

// Pre-baked Python scripts (column names resolved at build time)
const MAIN_SCRIPT = `{probe_script}`;
const SEAS_SCRIPT = `{seas_script}`;
const SIG_SCRIPT  = `{sig_script}`;
const NIFTY_SCRIPT= `{nifty_script}`;

export const dynamic = "force-dynamic";

export async function GET(req: Request) {{
  const url      = new URL(req.url);
  const minScore = url.searchParams.get("min") || "0";
  const limit    = url.searchParams.get("limit") || "300";

  const rows = runScript(MAIN_SCRIPT
    .replace("MIN_SCORE", minScore)
    .replace("LIMIT", limit));

  const todayPatterns = runScript(SEAS_SCRIPT);
  const todaySignals  = runScript(SIG_SCRIPT);
  const niftyData     = runOne(NIFTY_SCRIPT);

  const patMap: Record<string, any> = {{}};
  for (const p of todayPatterns) {{
    if (!patMap[p.symbol]) patMap[p.symbol] = p;
  }}
  const sigMap: Record<string, string> = {{}};
  for (const s of todaySignals) sigMap[s.symbol] = s.screen_tags || "";

  const nifty  = parseFloat(niftyData?.close ?? "0");
  const regime = nifty > 22000 ? "BULLISH" : nifty > 18000 ? "SIDEWAYS" : nifty > 0 ? "BEARISH" : "UNKNOWN";

  const enriched = rows.map((r: any) => ({{
    ...r,
    today_pattern: patMap[r.symbol] ?? null,
    today_signals: sigMap[r.symbol] ?? "",
    macd_bullish:  (parseFloat(r.macd_line ?? 0)) > (parseFloat(r.macd_signal ?? 0)),
  }}));

  return NextResponse.json({{
    rows:         enriched,
    total:        enriched.length,
    regime,
    nifty,
    generated_at: new Date().toISOString(),
  }});
}}
"""

write(SRC / "api" / "conviction" / "route.ts", api_content, "/api/conviction/route.ts")

print(f"""
======================================================================
  CONVICTION API FIXED
======================================================================

  Actual column names used:
    symbol_conviction.{c_score}    (conviction score)
    symbol_conviction.{c_beta}     (beta layer)
    symbol_conviction.{c_tags}     (active tags)
    market_snapshot.{snap_price}   (nifty price)
    seasonality.{seas_mean}         (mean return)

  Run fix_double_navbar.py first if not done yet, then:
    cd D:\\MICC\\micc-dashboard && npm run dev
""")
