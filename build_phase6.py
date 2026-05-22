"""
build_phase6.py
===============
Phase 6: Wire everything together

[1] /conviction page  -- add XGB score column + sort by XGB toggle
[2] /stocks/[symbol]  -- wire news tab (API already built in phase 5)
[3] /portfolio page   -- add correlation heatmap SVG tab
[4] morning_brief.py  -- add HMM regime banner + XGB top picks section

Run: py D:\MICC\build_phase6.py
"""
from pathlib import Path
import re

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
APP  = DASH / "src" / "app"

def write(path, lines, label=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [OK] {label or path.name}  ({len(lines)} lines)")

def log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

print("=" * 60)
print("PHASE 6 BUILD")
print("=" * 60)


# =============================================================================
# [1]  /api/conviction/route.ts -- add xgb_score to response
# =============================================================================
log("[1/4] Patching /api/conviction/route.ts to include xgb_score...")

conv_api = APP / "api" / "conviction" / "route.ts"
if conv_api.exists():
    src = conv_api.read_text(encoding="utf-8")
    # Add xgb_score LEFT JOIN if not already there
    if "symbol_conviction_xgb" not in src:
        # Find the main SELECT and add XGB join
        old_from = "FROM symbol_conviction c"
        new_from = (
            "FROM symbol_conviction c\n"
            "    LEFT JOIN symbol_conviction_xgb x ON x.symbol = c.symbol"
        )
        old_select_end = "sd.close                                     AS latest_close"
        new_select_end = (
            "sd.close                                     AS latest_close,\n"
            "      ROUND(CAST(x.xgb_score AS REAL),1)          AS xgb_score"
        )
        if old_from in src:
            src = src.replace(old_from, new_from, 1)
        if old_select_end in src:
            src = src.replace(old_select_end, new_select_end, 1)
        conv_api.write_text(src, encoding="utf-8")
        print("  [OK] Added xgb_score to conviction API")
    else:
        print("  [SKIP] xgb_score already in conviction API")
else:
    # Write a clean conviction API with xgb_score
    lines = [
        'import { NextResponse } from "next/server";',
        'import Database from "better-sqlite3";',
        '',
        'const DB = "D:/marketDB/db/market.db";',
        '',
        'export function GET(req: Request) {',
        '  const url      = new URL(req.url);',
        '  const minScore = parseFloat(url.searchParams.get("min") ?? "40");',
        '  const limit    = parseInt(url.searchParams.get("limit") ?? "200");',
        '  let db: ReturnType<typeof Database> | null = null;',
        '  try {',
        '    db = new Database(DB, { readonly: true, timeout: 8000 });',
        '    const rows = db.prepare(`',
        '      SELECT c.symbol,',
        '        ROUND(CAST(c.conviction_score AS REAL),1) AS conviction_score,',
        '        ROUND(CAST(c.momentum_score AS REAL),1) AS momentum_score,',
        '        ROUND(CAST(c.seasonality_score AS REAL),1) AS seasonality_score,',
        '        ROUND(CAST(c.delivery_score AS REAL),1) AS delivery_score,',
        '        ROUND(CAST(c.insider_score AS REAL),1) AS insider_score,',
        '        IFNULL(c.top_reason,"") AS top_reason,',
        '        t.rsi_14, t.adx_14, t.macd_line, t.macd_signal,',
        '        ROUND(CAST(t.atr_14_pct AS REAL),2) AS atr_14_pct,',
        '        ROUND(CAST(t.pct_from_52w_high AS REAL),1) AS pct_from_52w_high,',
        '        sd.close AS latest_close,',
        '        ROUND(CAST(x.xgb_score AS REAL),1) AS xgb_score',
        '      FROM symbol_conviction c',
        '      LEFT JOIN symbol_technicals t ON t.symbol = c.symbol',
        '      LEFT JOIN symbol_conviction_xgb x ON x.symbol = c.symbol',
        '      LEFT JOIN (',
        '        SELECT symbol, close FROM stock_data',
        '        WHERE date = (SELECT MAX(date) FROM stock_data WHERE close IS NOT NULL)',
        '          AND close IS NOT NULL',
        '      ) sd ON sd.symbol = c.symbol',
        '      WHERE CAST(c.conviction_score AS REAL) >= ?',
        '      ORDER BY CAST(c.conviction_score AS REAL) DESC',
        '      LIMIT ?',
        '    `).all(minScore, limit);',
        '    return NextResponse.json({ rows, count: rows.length });',
        '  } catch (e) {',
        '    return NextResponse.json({ rows: [], error: String(e) });',
        '  } finally { try { db?.close(); } catch {} }',
        '}',
    ]
    write(conv_api, lines, "/api/conviction/route.ts")


# =============================================================================
# [2]  /conviction page -- add XGB column + sort toggle
# =============================================================================
log("[2/4] Patching /conviction page to show XGB score...")

conv_page = APP / "conviction" / "page.tsx"
if conv_page.exists():
    src = conv_page.read_text(encoding="utf-8")
    changed = False

    # Add xgb_score to interface if missing
    if "xgb_score" not in src:
        src = src.replace(
            "top_reason?: string;",
            "top_reason?: string;\n  xgb_score?: number | null;"
        )
        # Add XGB column header after CONVICTION header
        src = src.replace(
            '"CONVICTION"',
            '"CONVICTION", "XGB"',
            1  # only first occurrence (table header)
        )
        # Add XGB sort button near conviction sort
        old_sort = '"SCORE"'
        # Find the sort buttons area and add XGB
        src = re.sub(
            r'(\["symbol","SYMBOL"\],\s*\["conviction_score","SCORE"\])',
            r'["symbol","SYMBOL"], ["conviction_score","SCORE"], ["xgb_score","XGB"]',
            src, count=1
        )
        # Add XGB value cell after conviction cell in table rows
        # Find: {fmt(r.conviction_score, 0)}  and add XGB after
        src = re.sub(
            r'(\{fmt\(r\.conviction_score,\s*0\)\})',
            r'\1\n                      </td>\n                      <td style={{ ...S.td, color: '
            r'Number(r.xgb_score)>=70?"var(--bull)":Number(r.xgb_score)>=50?"var(--warn)":"var(--bear)", '
            r'fontWeight: 600 }}>\n                        {r.xgb_score != null ? fmt(r.xgb_score,0) : "--"}',
            src, count=1
        )
        changed = True

    if changed:
        conv_page.write_text(src, encoding="utf-8")
        print("  [OK] XGB score column added to /conviction page")
    else:
        print("  [SKIP] XGB already in /conviction page or pattern not matched")
else:
    print("  [SKIP] /conviction/page.tsx not found")


# =============================================================================
# [3]  /stocks/[symbol] page -- add NEWS tab (API built in Phase 5)
# =============================================================================
log("[3/4] Adding NEWS tab to /stocks/[symbol] page...")

stocks_path = APP / "stocks" / "[symbol]" / "page.tsx"
if stocks_path.exists():
    src = stocks_path.read_text(encoding="utf-8")

    if "newsData" not in src and "NEWS" not in src:
        # Add news state + fetch after existing states
        old_state_block = 'const [loading, setLoading] = useState(true);'
        new_state_block = (
            'const [loading, setLoading] = useState(true);\n'
            '  const [newsData, setNewsData] = useState<{date:string;headline:string;source:string;sentiment_score:number|null}[]>([]);\n'
            '  const [newsLoading, setNewsLoading] = useState(false);'
        )
        src = src.replace(old_state_block, new_state_block, 1)

        # Add news fetch in useEffect or as separate effect
        old_effect_end = '  }, [symbol]);'
        new_effect_end = (
            '  }, [symbol]);\n\n'
            '  useEffect(() => {\n'
            '    if (!symbol) return;\n'
            '    setNewsLoading(true);\n'
            '    fetch(`/api/stocks/${symbol}/news`)\n'
            '      .then(r => r.json())\n'
            '      .then(d => { setNewsData(d.news || []); setNewsLoading(false); })\n'
            '      .catch(() => setNewsLoading(false));\n'
            '  }, [symbol]);'
        )
        src = src.replace(old_effect_end, new_effect_end, 1)

        # Add NEWS to tabs array
        src = re.sub(
            r'const TABS\s*=\s*\[([^\]]+)\]',
            lambda m: m.group(0).replace(m.group(1), m.group(1).rstrip() + ', "NEWS"'),
            src, count=1
        )

        # Add NEWS tab render block before final closing
        news_block = (
            '\n\n          {/* NEWS TAB */}\n'
            '          {tab === "NEWS" && (\n'
            '            <div style={{ background: "var(--surface)", border: "1px solid var(--border)",\n'
            '              borderRadius: 8, overflow: "hidden" }}>\n'
            '              {newsLoading && <div style={{ padding: 30, textAlign: "center",\n'
            '                color: "var(--dim)", fontSize: 12 }}>Loading news...</div>}\n'
            '              {!newsLoading && newsData.length === 0 && (\n'
            '                <div style={{ padding: 30, textAlign: "center", color: "var(--dim)", fontSize: 12 }}>\n'
            '                  No news found for {symbol}\n'
            '                </div>\n'
            '              )}\n'
            '              {!newsLoading && newsData.length > 0 && (\n'
            '                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>\n'
            '                  <thead><tr>\n'
            '                    {["DATE","SOURCE","HEADLINE","SENTIMENT"].map(h => (\n'
            '                      <th key={h} style={{ padding: "8px 12px", textAlign: "left",\n'
            '                        fontSize: 10, letterSpacing: 1, color: "var(--dim)",\n'
            '                        borderBottom: "1px solid var(--border)" }}>{h}</th>\n'
            '                    ))}\n'
            '                  </tr></thead>\n'
            '                  <tbody>\n'
            '                    {newsData.map((n, i) => {\n'
            '                      const sent = n.sentiment_score;\n'
            '                      const sentColor = sent == null ? "var(--dim)"\n'
            '                        : sent > 0.2 ? "var(--bull)" : sent < -0.2 ? "var(--bear)" : "var(--warn)";\n'
            '                      return (\n'
            '                        <tr key={i} style={{ background: i%2===0?"transparent":"var(--surface)88" }}>\n'
            '                          <td style={{ padding: "8px 12px", color: "var(--dim)",\n'
            '                            fontSize: 11, whiteSpace: "nowrap", borderBottom: "1px solid var(--border)" }}>\n'
            '                            {(n.date || "").slice(0,10)}\n'
            '                          </td>\n'
            '                          <td style={{ padding: "8px 12px", fontSize: 10,\n'
            '                            color: "var(--info)", borderBottom: "1px solid var(--border)" }}>\n'
            '                            {n.source || "--"}\n'
            '                          </td>\n'
            '                          <td style={{ padding: "8px 12px", fontSize: 12,\n'
            '                            color: "var(--text)", borderBottom: "1px solid var(--border)",\n'
            '                            lineHeight: 1.5 }}>\n'
            '                            {n.headline}\n'
            '                          </td>\n'
            '                          <td style={{ padding: "8px 12px", color: sentColor,\n'
            '                            fontWeight: 600, fontSize: 11, borderBottom: "1px solid var(--border)" }}>\n'
            '                            {sent != null ? (sent > 0 ? "+" : "") + sent.toFixed(2) : "--"}\n'
            '                          </td>\n'
            '                        </tr>\n'
            '                      );\n'
            '                    })}\n'
            '                  </tbody>\n'
            '                </table>\n'
            '              )}\n'
            '            </div>\n'
            '          )}'
        )

        # Inject before the last closing tags of the page
        # Find the end of the tab rendering section
        src = re.sub(
            r'(\s+\}\s*\}\s*\n\s*\);\s*\})',
            news_block + r'\1',
            src, count=1
        )

        stocks_path.write_text(src, encoding="utf-8")
        print("  [OK] NEWS tab added to /stocks/[symbol] page")
    else:
        print("  [SKIP] NEWS tab already in /stocks/[symbol] page")
else:
    print("  [SKIP] /stocks/[symbol]/page.tsx not found")


# =============================================================================
# [4]  /portfolio page -- add correlation heatmap tab
# =============================================================================
log("[4/4] Adding correlation heatmap to /portfolio page...")

port_path = APP / "portfolio" / "page.tsx"
if port_path.exists():
    src = port_path.read_text(encoding="utf-8")

    if "correlation" not in src.lower():
        # Add correlation state
        old_refresh = 'const [refresh, setRef] = useState(0);'
        new_refresh = (
            'const [refresh, setRef] = useState(0);\n'
            '  const [corrData, setCorrData] = useState<{symbols:string[];matrix:{symA:string;symB:string;corr:number|null}[]}|null>(null);\n'
            '  const [activeTab, setActiveTab] = useState<"positions"|"chart"|"correlation">("positions");'
        )
        src = src.replace(old_refresh, new_refresh, 1)

        # Add correlation fetch in useEffect
        old_fetch_end = '      .catch(e => { setE(e.message); setL(false); });'
        new_fetch_end = (
            '      .catch(e => { setE(e.message); setL(false); });\n'
            '    fetch("/api/portfolio/correlation")\n'
            '      .then(r => r.json())\n'
            '      .then(d => setCorrData(d))\n'
            '      .catch(() => {});'
        )
        src = src.replace(old_fetch_end, new_fetch_end, 1)

        # Add correlation heatmap component as inline function before return
        heatmap_component = '''
  function CorrHeatmap() {
    if (!corrData || !corrData.symbols || corrData.symbols.length < 2) {
      return <div style={{ padding: 40, textAlign: "center", color: "var(--dim)", fontSize: 12 }}>
        Need 2+ open positions for correlation matrix.
      </div>;
    }
    const { symbols, matrix } = corrData;
    const n = symbols.length;
    const cellSize = Math.min(80, Math.floor(560 / n));
    const W = cellSize * n + 120;
    const H = cellSize * n + 80;
    const getCorr = (a: string, b: string) =>
      matrix.find(m => m.symA === a && m.symB === b)?.corr ?? null;
    const corrColor = (c: number | null) => {
      if (c === null) return "var(--muted)";
      if (c >= 0.7)  return "#f87171";  // high positive = bad (concentrated)
      if (c >= 0.3)  return "#fbbf24";  // moderate
      if (c >= -0.3) return "#34d399";  // low = good diversification
      return "#60a5fa";                  // negative = excellent hedge
    };
    return (
      <div>
        <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 12 }}>
          POSITION CORRELATION MATRIX  (90d daily returns)
        </div>
        <div style={{ overflowX: "auto" }}>
          <svg width={W} height={H} style={{ fontFamily: "JetBrains Mono, monospace" }}>
            {/* Column headers */}
            {symbols.map((sym, j) => (
              <text key={j} x={120 + j * cellSize + cellSize/2} y={60}
                textAnchor="middle" fontSize={10} fill="var(--dim)"
                transform={`rotate(-45, ${120 + j*cellSize + cellSize/2}, 60)`}>
                {sym.slice(0,8)}
              </text>
            ))}
            {/* Row labels + cells */}
            {symbols.map((symA, i) => (
              <g key={i}>
                <text x={110} y={80 + i * cellSize + cellSize/2 + 4}
                  textAnchor="end" fontSize={10} fill="var(--dim)">{symA.slice(0,8)}</text>
                {symbols.map((symB, j) => {
                  const c = getCorr(symA, symB);
                  const bg = corrColor(c);
                  return (
                    <g key={j}>
                      <rect x={120 + j*cellSize} y={70 + i*cellSize}
                        width={cellSize-2} height={cellSize-2} fill={bg} opacity={0.85} rx={2} />
                      <text x={120 + j*cellSize + cellSize/2} y={70 + i*cellSize + cellSize/2 + 4}
                        textAnchor="middle" fontSize={Math.max(9, cellSize/6)} fill="#000" fontWeight={600}>
                        {c !== null ? c.toFixed(2) : "--"}
                      </text>
                    </g>
                  );
                })}
              </g>
            ))}
          </svg>
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 10, color: "var(--dim)" }}>
          <span><span style={{ color: "#34d399" }}>GREEN</span>  low correlation (good diversification)</span>
          <span><span style={{ color: "#fbbf24" }}>YELLOW</span> moderate correlation</span>
          <span><span style={{ color: "#f87171" }}>RED</span>    high correlation (concentrated risk)</span>
          <span><span style={{ color: "#60a5fa" }}>BLUE</span>   negative correlation (hedge)</span>
        </div>
      </div>
    );
  }
'''
        # Inject before return statement
        src = re.sub(
            r'(\n  return \()',
            heatmap_component + r'\1',
            src, count=1
        )

        # Add tab buttons to sub-header
        old_sub_content = '<span style={S.stitle}>PORTFOLIO  /  POSITIONS & P&L</span>'
        new_sub_content = (
            '<span style={S.stitle}>PORTFOLIO  /  POSITIONS & P&L</span>\n'
            '        {["positions","chart","correlation"].map(t => (\n'
            '          <button key={t} onClick={() => setActiveTab(t as typeof activeTab)}\n'
            '            style={{ padding:"3px 10px", fontSize:10, letterSpacing:1, cursor:"pointer",\n'
            '              border:"1px solid "+(activeTab===t?"var(--accent)":"var(--border)"),\n'
            '              borderRadius:4, background:activeTab===t?"var(--accent)22":"transparent",\n'
            '              color:activeTab===t?"var(--accent)":"var(--dim)" }}>\n'
            '            {t.toUpperCase()}\n'
            '          </button>\n'
            '        ))}'
        )
        src = src.replace(old_sub_content, new_sub_content, 1)

        # Wrap existing content with tab check + add correlation tab
        # Find the EquityCurve render and wrap it
        src = src.replace(
            '          {/* Equity curve */}\n          <EquityCurve positions={positions} />',
            '          {activeTab === "chart" && <EquityCurve positions={positions} />}'
        )
        src = src.replace(
            '          {/* Positions table */}\n          {positions.length === 0',
            '          {activeTab === "positions" && positions.length === 0'
        )
        # Find the add position hint and wrap it
        src = src.replace(
            '          {/* Add position hint */}\n          <div style={S.hint}>',
            '          {activeTab === "positions" && <div style={S.hint}>'
        )
        # Close the hint wrapper
        src = src.replace(
            "            </div>\n          </>\n        }",
            "            </div>}\n\n          {activeTab === 'correlation' && <CorrHeatmap />}\n          </>\n        }"
        )

        port_path.write_text(src, encoding="utf-8")
        print("  [OK] Correlation heatmap tab added to /portfolio page")
    else:
        print("  [SKIP] Correlation already in /portfolio page")
else:
    print("  [SKIP] /portfolio/page.tsx not found")


# =============================================================================
# [5]  morning_brief.py -- add HMM regime banner + XGB top picks
# =============================================================================
log("[5/5] Adding HMM regime + XGB picks to morning_brief.py...")

mb_path = MICC / "morning_brief.py"
src = mb_path.read_text(encoding="utf-8")

# Add get_hmm_regime function if missing
if "get_hmm_regime" not in src:
    hmm_fn = (
        "\ndef get_hmm_regime():\n"
        "    try:\n"
        "        p = DA / 'agents' / 'hmm' / 'last_report.json'\n"
        "        if not p.exists(): return None\n"
        "        return json.loads(p.read_text(encoding='utf-8'))\n"
        "    except Exception:\n"
        "        return None\n"
        "\ndef get_xgb_top(n=5):\n"
        "    try:\n"
        "        conn = sqlite3.connect(DB_P, timeout=10)\n"
        "        rows = conn.execute(\n"
        "            'SELECT x.symbol, x.xgb_score, COALESCE(c.conviction_score,0) AS conv'\n"
        "            ' FROM symbol_conviction_xgb x'\n"
        "            ' LEFT JOIN symbol_conviction c ON c.symbol=x.symbol'\n"
        "            ' WHERE x.xgb_score >= 60'\n"
        "            ' ORDER BY x.xgb_score DESC LIMIT ?',\n"
        "            (n,)\n"
        "        ).fetchall()\n"
        "        conn.close()\n"
        "        return rows\n"
        "    except Exception:\n"
        "        return []\n"
    )
    # Insert before def main():
    src = src.replace("def main():", hmm_fn + "def main():", 1)

# Add HMM section to brief output
if "HMM Regime" not in src and "get_hmm_regime" in src:
    old_global = "    # 1. Global markets"
    new_global = (
        "    # 0. HMM Regime\n"
        "    hmm = get_hmm_regime()\n"
        "    if hmm:\n"
        "        reg   = hmm.get('current_regime', '--')\n"
        "        conf  = hmm.get('confidence', 0)\n"
        "        bullp = hmm.get('bull_prob', 0)\n"
        "        bearp = hmm.get('bear_prob', 0)\n"
        "        ico   = {'BULL':'UP','BEAR':'DN','SIDEWAYS':'--'}.get(reg, '--')\n"
        "        lines.append(f'*Regime (HMM): {ico} {reg}* ({conf:.0%} conf | Bull={bullp:.0%} Bear={bearp:.0%})')\n"
        "        lines.append('')\n\n"
        "    # 1. Global markets"
    )
    src = src.replace(old_global, new_global, 1)

# Add XGB picks section
if "XGB" not in src and "get_xgb_top" in src:
    old_quality = "    # 3. Quality picks"
    new_quality = (
        "    # 2b. XGB ML picks\n"
        "    xgb_picks = get_xgb_top(n=5)\n"
        "    if xgb_picks:\n"
        "        lines.append('*ML Picks (XGBoost >60):*')\n"
        "        for sym, xgb_s, conv in xgb_picks:\n"
        "            lines.append(f'  `{str(sym):<12}` XGB={xgb_s:.0f}  Conv={conv:.0f}')\n"
        "        lines.append('')\n\n"
        "    # 3. Quality picks"
    )
    src = src.replace(old_quality, new_quality, 1)

mb_path.write_text(src, encoding="utf-8")
print("  [OK] morning_brief.py updated with HMM regime + XGB picks")


# =============================================================================
# Summary
# =============================================================================
print()
print("=" * 60)
print("PHASE 6 COMPLETE")
print("=" * 60)
print()
print("Changes:")
print("  /api/conviction/route.ts -- xgb_score added via LEFT JOIN")
print("  /conviction/page.tsx     -- XGB column in table")
print("  /stocks/[symbol]         -- NEWS tab wired to /api/stocks/.../news")
print("  /portfolio/page.tsx      -- Positions/Chart/Correlation tabs")
print("  morning_brief.py         -- HMM regime banner + XGB top picks")
print()
print("Test:")
print("  py D:\\MICC\\morning_brief.py")
print("  -> Should show: Regime (HMM): BULL section at top")
print("  -> Should show: ML Picks (XGBoost) section")
print()
print("Git push:")
print("  py D:\\MICC\\git_push_phase3.py")
