"""
PHASE 3 PLAN - Run this to see what to do next
py D:\MICC\phase3_plan.py
"""
print("""
=============================================================
  MICC PHASE 3 -- WHAT TO DO NOW
=============================================================

STATUS CHECK:
  Git:           PUSHED to GitHub (markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS)
  NavBar:        23/23 pages OK
  Fundamentals:  500 stocks scraped (screener_fundamentals_v2)
  Conviction:    2181 rows (symbol_conviction)
  RBI rates:     33 rate change dates populated
  Dashboard:     All pages building OK

=============================================================
  IMMEDIATE TASKS (run these now)
=============================================================

1. Start dashboard and verify all pages:
   cd D:\\MICC\\micc-dashboard
   npm run dev

   Then open:
     http://localhost:3000/stocks/TCS          <- stock deep dive
     http://localhost:3000/analytics           <- fundamentals screener
     http://localhost:3000/conviction          <- conviction screener
     http://localhost:3000/fusion              <- fusion picks

2. Run daily pipeline to get fresh data:
   cd D:\\MICC\\data_pipeline
   py run_pipeline.py --with-engine

3. Regenerate fusion picks (agents need fresh data):
   py D:\\MICC\\agent_fusion.py

=============================================================
  PHASE 3 BUILDS (in priority order)
=============================================================

PRIORITY 1 -- Patterns page OOS badge
  File to build: build_patterns_oos_badge.py
  What: Add oos_accuracy column display to /patterns page
        Shows "IN: 68% | OOS: 61%" per pattern
        Marks overfit patterns in red

PRIORITY 2 -- Portfolio page improvements  
  File to build: build_portfolio_v2.py
  What: P&L chart, risk metrics, ATR-based position sizing
        Correlation heatmap of holdings
        Max drawdown per position

PRIORITY 3 -- Screener 2000 stocks (run overnight)
  Command: py D:\\MICC\\data_pipeline\\scrape_fundamentals.py 2000
  Note: RELIANCE not in top 500 conviction -- needs 2000 run
        Takes ~2 hours, safe to run overnight

PRIORITY 4 -- Patch fundamentals (ROIC, interest coverage)
  Command: py D:\\MICC\\data_pipeline\\patch_fundamentals.py
  Note: Runs ~30 min, fills ROIC, interest_coverage, ebitda_growth

PRIORITY 5 -- OOS validation (run overnight)
  Command: py D:\\MICC\\validate_patterns_oos.py --test   first
           py D:\\MICC\\validate_patterns_oos.py           then
  Note: 19.7M patterns, ~30 min

=============================================================
  GIT (every time you change something)
=============================================================

  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "what changed"
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push origin main --force

=============================================================
  TELL ME WHICH TO BUILD NEXT
=============================================================

  Say one of:
    "build patterns oos"     -> I build the patterns OOS badge
    "build portfolio v2"     -> I build portfolio improvements  
    "build screener page"    -> I build a screener with filters
    "build alerts upgrade"   -> I upgrade the alerts page
    "build backtest page"    -> I wire up the backtest page
""")
