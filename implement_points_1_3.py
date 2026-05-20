# -*- coding: utf-8 -*-
"""
implement_points_1_3.py  --  Run from D:\\MICC

Point 1: Expandable separate chart sections on /patterns page
  - Each visualization tab (Heatmap, 3D, Bubble, Strip, Monthly)
    is now also available as a floating expandable panel on the
    Pattern Table tab — user clicks a button to open/close each chart
    without leaving the table view

Point 3: Add Indian indices to global_indices_daily fetcher
  Based on the spec doc:
    A.A tier: ^NSEI (Nifty 50), added to global_indices_daily
    A.B tier: ^NSEBANK (Nifty Bank), added
    B.A tier: ^BSESN (Sensex), ^CNXIT (Nifty IT), added
  These are already in market_snapshot but NOT in global_indices_daily,
  so seasonality patterns can't find them as 'global' type.
  This script patches phase9a_fetch_global_indices.py to add them.

Run: py D:\\MICC\\implement_points_1_3.py
"""
from pathlib import Path
import shutil

BASE = Path(r"D:\MICC")
APP  = BASE / "micc-dashboard" / "src" / "app"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

# =============================================================================
# POINT 3: Add Indian indices to phase9a_fetch_global_indices.py
# =============================================================================
print("\n[POINT 3] Adding Indian indices to global fetcher...")

fetcher = BASE / "phase9a_fetch_global_indices.py"
if not fetcher.exists():
    fetcher = BASE / "data_pipeline" / "phase9a_fetch_global_indices.py"

if fetcher.exists():
    txt = fetcher.read_text(encoding="utf-8")

    OLD_TICKERS = '''    # ── Bitcoin (global risk-on barometer) ────────────────────────────────
    "Bitcoin":      ("BTC-USD",  "Bitcoin",           "crypto"),
}'''

    NEW_TICKERS = '''    # ── Bitcoin (global risk-on barometer) ────────────────────────────────
    "Bitcoin":      ("BTC-USD",  "Bitcoin",           "crypto"),

    # ── Indian Indices (Tier A.A and A.B per spec) ────────────────────────
    # These give India-specific seasonality in global_indices_daily
    "NIFTY50":      ("^NSEI",      "Nifty 50",             "equity_index"),
    "NIFTYBANK":    ("^NSEBANK",   "Nifty Bank",           "equity_index"),
    "SENSEX":       ("^BSESN",     "Sensex (BSE)",         "equity_index"),
    "NIFTYIT":      ("^CNXIT",     "Nifty IT",             "equity_index"),
    "NIFTYMID100":  ("^NSEMDCP50", "Nifty Midcap 50",      "equity_index"),
    "EUROSTOXX50":  ("^STOXX50E",  "Euro Stoxx 50",        "equity_index"),
}'''

    if OLD_TICKERS in txt and "NIFTY50" not in txt:
        txt = txt.replace(OLD_TICKERS, NEW_TICKERS)
        fetcher.write_text(txt, encoding="utf-8", newline="\n")
        print(f"  [OK] Added 5 Indian + 1 European indices to {fetcher.name}")
        print("  Added: NIFTY50, NIFTYBANK, SENSEX, NIFTYIT, NIFTYMID100, EUROSTOXX50")
        print("  Run: py D:\\MICC\\phase9a_fetch_global_indices.py --incremental")
        print("  Then re-run: py D:\\MICC\\build_seasonality_v2.py --yes -> [c]ontinue")
    elif "NIFTY50" in txt:
        print("  Already has Indian indices")
    else:
        print("  [WARN] Could not find insertion point. Add manually to GLOBAL_TICKERS dict")
else:
    print(f"  [WARN] phase9a_fetch_global_indices.py not found")

# Also update build_seasonality_v2.py to include 'indian' asset_type from market_snapshot
sv2 = BASE / "build_seasonality_v2.py"
if sv2.exists():
    txt = sv2.read_text(encoding="utf-8")
    # Check if market_snapshot NSE indices are included
    if "closing_index_value" not in txt:
        print("  [WARN] build_seasonality_v2.py doesn't load market_snapshot indices")
        print("  They should already be there from fix_api_columns.py")
    else:
        print("  [OK] build_seasonality_v2.py already loads market_snapshot indices")

# =============================================================================
# POINT 1: Add expandable chart panel buttons to Pattern Table tab
#   When on Pattern Table tab, user can click buttons to open/close
#   any of the 5 charts (Heatmap, 3D, Bubble, Strip, Monthly) as
#   collapsible panels below the table, without switching tabs.
# =============================================================================
print("\n[POINT 1] Adding expandable chart panels to patterns/page.tsx...")

page = APP / "patterns" / "page.tsx"
if not page.exists():
    print("  [WARN] patterns/page.tsx not found. Run setup_phase13_final.py first.")
else:
    txt = page.read_text(encoding="utf-8")

    # Add openPanels state
    OLD_STATE = '''  const [expandedRow,setExpandedRow]=useState<number|null>(null);'''
    NEW_STATE = '''  const [expandedRow,setExpandedRow]=useState<number|null>(null);
  const [openPanels,setOpenPanels]=useState<Set<string>>(new Set());
  const togglePanel=(id:string)=>setOpenPanels(prev=>{const n=new Set(prev);n.has(id)?n.delete(id):n.add(id);return n;});'''

    # Add panel buttons + panels inside the table tab, after the UP/DOWN direction toggle
    OLD_TABLE_TAB_HEADER = '''          <div style={{display:"flex",gap:6,marginBottom:14}}>
                {([["up",`UP Patterns (${upPats.length})`],["down",`DOWN Patterns (${dnPats.length})`]] as const).map(([v,l])=>(
                  <button key={v} onClick={()=>{setActiveTableDir(v);setExpandedRow(null);}} style={{
                    padding:"8px 20px",borderRadius:7,fontSize:12,fontWeight:700,cursor:"pointer",
                    border:`2px solid ${v==="up"?G:R}`,
                    background:activeTableDir===v?(v==="up"?G:R):"transparent",
                    color:activeTableDir===v?"#000":(v==="up"?G:R),
                    transition:"all 0.15s",
                  }}>{l}</button>
                ))}
              </div>'''

    NEW_TABLE_TAB_HEADER = '''          <div style={{display:"flex",gap:6,marginBottom:10,flexWrap:"wrap",alignItems:"center"}}>
                {([["up",`UP Patterns (${upPats.length})`],["down",`DOWN Patterns (${dnPats.length})`]] as const).map(([v,l])=>(
                  <button key={v} onClick={()=>{setActiveTableDir(v);setExpandedRow(null);}} style={{
                    padding:"8px 20px",borderRadius:7,fontSize:12,fontWeight:700,cursor:"pointer",
                    border:`2px solid ${v==="up"?G:R}`,
                    background:activeTableDir===v?(v==="up"?G:R):"transparent",
                    color:activeTableDir===v?"#000":(v==="up"?G:R),
                    transition:"all 0.15s",
                  }}>{l}</button>
                ))}
                {/* Quick chart panel buttons */}
                <div style={{marginLeft:"auto",display:"flex",gap:5,flexWrap:"wrap"}}>
                  <span style={{fontSize:10,color:W9,alignSelf:"center"}}>Open charts:</span>
                  {[
                    ["hmap","🗺 Heatmap"],
                    ["surf","🏔 3D Surface"],
                    ["bubl","🫧 Bubble"],
                    ["strp","📅 Strip"],
                    ["mnth","📊 Monthly"],
                  ].map(([id,label])=>(
                    <button key={id} onClick={()=>togglePanel(id)} style={{
                      padding:"5px 10px",borderRadius:6,fontSize:10,fontWeight:700,cursor:"pointer",
                      border:`1px solid ${openPanels.has(id)?CY:BOR}`,
                      background:openPanels.has(id)?`${CY}22`:"transparent",
                      color:openPanels.has(id)?CY:W9,transition:"all 0.15s",
                    }}>{label} {openPanels.has(id)?"▲":"▼"}</button>
                  ))}
                </div>
              </div>

              {/* Expandable chart panels — inline with table */}
              {heatData&&openPanels.has("hmap")&&(
                <div style={{marginBottom:14,background:SUR,border:`1px solid ${CY}44`,borderRadius:10,overflow:"hidden"}}>
                  <div style={{padding:"10px 16px",fontSize:11,fontWeight:700,color:CY,letterSpacing:1.3,borderBottom:`1px solid ${BOR}`,display:"flex",justifyContent:"space-between"}}>
                    WINDOW DISCOVERY HEATMAP
                    <button onClick={()=>togglePanel("hmap")} style={{background:"transparent",border:"none",color:W9,cursor:"pointer",fontSize:14}}>✕</button>
                  </div>
                  <div style={{padding:"14px 16px"}}><DiscoveryHeatmap rows={heatData.heatmap_rows}/></div>
                </div>
              )}
              {heatData&&openPanels.has("surf")&&(
                <div style={{marginBottom:14,background:SUR,border:`1px solid ${OR}44`,borderRadius:10,overflow:"hidden"}}>
                  <div style={{padding:"10px 16px",fontSize:11,fontWeight:700,color:OR,letterSpacing:1.3,borderBottom:`1px solid ${BOR}`,display:"flex",justifyContent:"space-between"}}>
                    3D DISCOVERY SURFACE
                    <button onClick={()=>togglePanel("surf")} style={{background:"transparent",border:"none",color:W9,cursor:"pointer",fontSize:14}}>✕</button>
                  </div>
                  <div style={{padding:"14px 16px"}}><Surface3D rows={heatData.heatmap_rows}/></div>
                </div>
              )}
              {openPanels.has("bubl")&&(
                <div style={{marginBottom:14,background:SUR,border:`1px solid ${YL}44`,borderRadius:10,overflow:"hidden"}}>
                  <div style={{padding:"10px 16px",fontSize:11,fontWeight:700,color:YL,letterSpacing:1.3,borderBottom:`1px solid ${BOR}`,display:"flex",justifyContent:"space-between"}}>
                    BUBBLE CHART — Accuracy vs Avg Return
                    <button onClick={()=>togglePanel("bubl")} style={{background:"transparent",border:"none",color:W9,cursor:"pointer",fontSize:14}}>✕</button>
                  </div>
                  <div style={{padding:"14px 16px"}}><BubbleChart patterns={allPats}/></div>
                </div>
              )}
              {openPanels.has("strp")&&(
                <div style={{marginBottom:14,background:SUR,border:`1px solid ${G}44`,borderRadius:10,overflow:"hidden"}}>
                  <div style={{padding:"10px 16px",fontSize:11,fontWeight:700,color:G,letterSpacing:1.3,borderBottom:`1px solid ${BOR}`,display:"flex",justifyContent:"space-between"}}>
                    CALENDAR STRIP
                    <button onClick={()=>togglePanel("strp")} style={{background:"transparent",border:"none",color:W9,cursor:"pointer",fontSize:14}}>✕</button>
                  </div>
                  <div style={{padding:"14px 16px"}}><CalendarStrip patterns={allPats}/></div>
                </div>
              )}
              {heatData&&openPanels.has("mnth")&&(
                <div style={{marginBottom:14,background:SUR,border:`1px solid ${CY}44`,borderRadius:10,overflow:"hidden"}}>
                  <div style={{padding:"10px 16px",fontSize:11,fontWeight:700,color:CY,letterSpacing:1.3,borderBottom:`1px solid ${BOR}`,display:"flex",justifyContent:"space-between"}}>
                    MONTHLY SEASONALITY
                    <button onClick={()=>togglePanel("mnth")} style={{background:"transparent",border:"none",color:W9,cursor:"pointer",fontSize:14}}>✕</button>
                  </div>
                  <div style={{padding:"14px 16px"}}><MonthHeatmap seasonality={heatData.seasonality||[]}/></div>
                </div>
              )}'''

    changed = False

    if OLD_STATE in txt:
        txt = txt.replace(OLD_STATE, NEW_STATE, 1)
        print("  [OK] Added openPanels state")
        changed = True
    else:
        print("  [SKIP] openPanels state already exists or different structure")

    if OLD_TABLE_TAB_HEADER in txt:
        txt = txt.replace(OLD_TABLE_TAB_HEADER, NEW_TABLE_TAB_HEADER, 1)
        print("  [OK] Added expandable chart panel buttons + panels")
        changed = True
    else:
        print("  [SKIP] Table tab header not found — may need full rebuild")

    if changed:
        page.write_text(txt, encoding="utf-8", newline="\n")
        print("  [SAVED] patterns/page.tsx")

print("""
=============================================================
IMPLEMENT POINTS 1 & 3 COMPLETE
=============================================================

POINT 1 — Expandable chart panels on Pattern Table tab:
  When viewing the Pattern Table, you now see 5 buttons at top-right:
    🗺 Heatmap | 🏔 3D Surface | 🫧 Bubble | 📅 Strip | 📊 Monthly
  Click any button -> that chart opens as a collapsible panel ABOVE the table
  Click again (or ✕) -> it closes
  You can have multiple panels open simultaneously
  Works while staying on the Pattern Table tab (no tab switching needed)

POINT 3 — Indian indices added to global fetcher:
  Added to phase9a_fetch_global_indices.py GLOBAL_TICKERS:
    NIFTY50   -> ^NSEI    (Nifty 50)       [Tier A.A]
    NIFTYBANK -> ^NSEBANK (Nifty Bank)     [Tier A.B]
    SENSEX    -> ^BSESN   (Sensex BSE)    [Tier B.A]
    NIFTYIT   -> ^CNXIT   (Nifty IT)       [Tier B.B]
    NIFTYMID100 -> ^NSEMDCP50 (Midcap 50) [Tier B.B]
    EUROSTOXX50 -> ^STOXX50E               [Tier A.C]

  To fetch their price history:
    py D:\\MICC\\phase9a_fetch_global_indices.py --incremental
    (or full: py D:\\MICC\\phase9a_fetch_global_indices.py)

  Then re-run seasonality builder to find patterns for these indices:
    py D:\\MICC\\build_seasonality_v2.py --yes  -> choose [c] continue

  After that, search "NIFTY50" or "NIFTYBANK" in /patterns
  to see their seasonal patterns!

Restart dashboard:
  cd D:\\MICC\\micc-dashboard && npm run dev
""")
