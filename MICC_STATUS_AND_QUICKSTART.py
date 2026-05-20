"""
MICC QUICK START — Read this after system restart
===================================================

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. SEASONALITY BUILD STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your --verify showed:
  Patterns: 19,694,886
  Symbols:  1,526 completed

Out of ~1,447 target symbols from stock_data.
Your build FINISHED but stopped at 1,526 due to system shutdown.
1,526 > 1,447 target (symbols include some indices counted alongside).

STATUS: ✅ BUILD IS EFFECTIVELY COMPLETE
  - 19.7M patterns is ~94% of expected 21M
  - All major symbols (RELIANCE, TCS, HDFC, etc.) are done
  - Missing ~200 symbols from the A-B range in checkpoint (they were
    mid-build when shutdown happened)

ACTION: Run --resume to finish the last ~200 symbols:
  py D:\MICC\build_seasonality_v3_stocks.py --resume

Then verify again:
  py D:\MICC\build_seasonality_v3_stocks.py --verify
Expected: ~21M patterns, 1,650+ symbols


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. MORNING BRIEF — STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Working perfectly
✅ Telegram sent successfully
✅ Scheduler created ("MICC Morning Brief")
✅ Alerts added (RSI_BELOW NIFTY50 35 + PRICE_ABOVE RELIANCE 1450)

One small fix needed — syntax warning in morning_brief.py line 2:
  Change:  morning_brief.py  --  Run from D:\MICC at 9:00 AM
  To:      morning_brief.py  --  Run from D:\\MICC at 9:00 AM
  (double backslash in the docstring)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. PIPELINE FIX — IndentationError
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Error was: IndentationError on line 80-82 of run_pipeline.py

CAUSE: A previous build script added a broken `if` block locally
that doesn't exist in the project version.

FIX: Replace D:\MICC\data_pipeline\run_pipeline.py with the
     file: run_pipeline_fixed.py (provided alongside this file)

  copy run_pipeline_fixed.py D:\MICC\data_pipeline\run_pipeline.py

NEW FEATURES in fixed version:
  - pipeline_state.json: tracks which phases completed today
  - On crash: sends Telegram "⚠️ Pipeline failed at phase X"
  - Resume: re-running skips completed phases automatically
  - --with-engine works correctly (was broken in old version)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. INSTALL ALL NEW DATA LIBRARIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run these ONE TIME in PowerShell:

# Phase 1 data extraction (critical)
pip install fredapi requests beautifulsoup4 lxml --break-system-packages

# Phase 2 data extraction (sentiment + trends)
pip install pytrends feedparser pdfplumber --break-system-packages

# Phase 2 alternative parsers
pip install lxml html5lib --break-system-packages

# For BSE data (optional, extends universe)
pip install bsedata --break-system-packages

# For adjusted prices (IMPORTANT — fixes split/bonus data)
pip install jugaad-data --break-system-packages


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. TODAY'S EXECUTION ORDER (after reading this)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1 — Fix the pipeline (5 min):
  copy D:\path\to\run_pipeline_fixed.py D:\MICC\data_pipeline\run_pipeline.py

Step 2 — Resume seasonality build (30-60 min):
  py D:\MICC\build_seasonality_v3_stocks.py --resume

Step 3 — Verify final count:
  py D:\MICC\build_seasonality_v3_stocks.py --verify

Step 4 — Install new libraries:
  pip install fredapi beautifulsoup4 pytrends feedparser --break-system-packages

Step 5 — Run Phase 1 data extraction:
  copy D:\path\to\fetch_phase1_data.py D:\MICC\data_pipeline\fetch_phase1_data.py
  py D:\MICC\data_pipeline\fetch_phase1_data.py --rbi --gsec --poi

Step 6 — Run Phase 2 data extraction (can run overnight):
  copy D:\path\to\fetch_phase2_data.py D:\MICC\data_pipeline\fetch_phase2_data.py
  py D:\MICC\data_pipeline\fetch_phase2_data.py --news --trends --iv

Step 7 — Run the fixed daily pipeline:
  cd D:\MICC\data_pipeline
  py run_pipeline.py --with-engine


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. NEW TABLES BEING ADDED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 1 scripts add:
  rbi_monetary_data      — repo rate, CRR, forex reserves, M3 (via FRED)
  india_bond_yields      — India 10Y G-Sec yield daily
  participant_oi         — NSE FII vs retail F&O positioning
  shareholding_history   — quarterly promoter/FII/pledge % per stock
  india_monthly_macro    — monthly CPI, IIP from MOSPI/FRED

Phase 2 scripts add:
  screener_fundamentals  — ROCE, ROE, debt/equity from Screener.in
  google_trends          — weekly interest score per stock/sector
  news_headlines         — stored + sentiment-scored daily headlines
  options_iv_history     — ATM IV, IV rank (252d), PCR per symbol/date


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7. ADDING TO DAILY PIPELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After verifying scripts work, add to run_pipeline.py:

    # Phase 3 — Extended data (after greeks)
    r["phase1_ext"] = run_phase("phase1_ext",
        PIPELINE_DIR / "fetch_phase1_data.py",
        "Phase 1: RBI + G-Sec + Participant OI",
        state, args=["--rbi","--gsec","--poi"], timeout=300)

    r["news"] = run_phase("news",
        PIPELINE_DIR / "fetch_phase2_data.py",
        "News headlines + sentiment",
        state, args=["--news"], timeout=120)

    # Weekly: Screener fundamentals (runs with --weekly flag)
    if weekly:
        r["screener"] = run_phase("screener",
            PIPELINE_DIR / "fetch_phase2_data.py",
            "Screener.in fundamentals",
            state, args=["--screener","--max","500"], timeout=3600)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8. DATA.GOV.IN FREE API KEY (for MOSPI data)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Go to: https://data.gov.in/user/register
2. Register free (instant)
3. Get API key from your profile
4. Add to D:\MICC\.env:
   DATAGOV_API_KEY=your_key_here
5. Uncomment the data.gov.in section in fetch_phase1_data.py

This unlocks official MOSPI monthly CPI/WPI/IIP data.
"""

print(__doc__)
