"""
build_phase9_fixed.py
=====================
Rewrites Phase 9 files without the syntax error.
Uses Path.write_text() directly, no nested string issues.

Run: py D:\MICC\build_phase9_fixed.py
"""
from pathlib import Path
import sqlite3, json
from datetime import datetime

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
APP  = DASH / "src" / "app"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

print("=" * 55)
print("PHASE 9 FINAL")
print("=" * 55)


# ── [1] Task Scheduler XML ────────────────────────────────────────────────────
log("[1] Writing Task Scheduler XML...")

xml = (
    '<?xml version="1.0" encoding="UTF-16"?>\n'
    '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
    '  <RegistrationInfo>\n'
    '    <Description>MICC Daily ML -- HMM + XGB + Fusion</Description>\n'
    '    <URI>\\MICC_Daily_ML_Update</URI>\n'
    '  </RegistrationInfo>\n'
    '  <Triggers>\n'
    '    <CalendarTrigger>\n'
    '      <StartBoundary>2026-05-26T06:30:00</StartBoundary>\n'
    '      <Enabled>true</Enabled>\n'
    '      <ScheduleByWeek>\n'
    '        <WeeksInterval>1</WeeksInterval>\n'
    '        <DaysOfWeek>\n'
    '          <Monday /><Tuesday /><Wednesday /><Thursday /><Friday />\n'
    '        </DaysOfWeek>\n'
    '      </ScheduleByWeek>\n'
    '    </CalendarTrigger>\n'
    '  </Triggers>\n'
    '  <Actions Context="Author">\n'
    '    <Exec>\n'
    '      <Command>C:\\Users\\marka\\AppData\\Local\\Programs\\Python\\Python314\\python.exe</Command>\n'
    '      <Arguments>D:\\MICC\\daily_ml_update.py</Arguments>\n'
    '      <WorkingDirectory>D:\\MICC</WorkingDirectory>\n'
    '    </Exec>\n'
    '  </Actions>\n'
    '  <Settings>\n'
    '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
    '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
    '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
    '    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>\n'
    '    <Priority>7</Priority>\n'
    '  </Settings>\n'
    '</Task>\n'
)
xml_path = MICC / "micc_ml_scheduler.xml"
xml_path.write_text(xml, encoding="utf-16")
print(f"  [OK] {xml_path}")


# ── [2] fetch_gift_nifty.py ───────────────────────────────────────────────────
log("[2] Writing fetch_gift_nifty.py...")

gift = (
    'import sqlite3, sys\n'
    'from datetime import datetime\n'
    'from pathlib import Path\n'
    '\n'
    'DB = r"D:\\marketDB\\db\\market.db"\n'
    '\n'
    'try:\n'
    '    import yfinance as yf\n'
    'except ImportError:\n'
    '    import subprocess\n'
    '    subprocess.run([sys.executable, "-m", "pip", "install",\n'
    '                    "yfinance", "--break-system-packages", "-q"])\n'
    '    import yfinance as yf\n'
    '\n'
    'print("Fetching GIFT Nifty...")\n'
    '\n'
    'TICKERS = [\n'
    '    ("GIFTNifty", "NIFTY_FUT.NS"),\n'
    '    ("SGXNifty",  "^NIFTY_FUT"),\n'
    ']\n'
    '\n'
    'CREATE_SQL = (\n'
    '    "CREATE TABLE IF NOT EXISTS global_indices_daily"\n'
    '    " (symbol TEXT, date TEXT, open REAL, high REAL,"\n'
    '    "  low REAL, close REAL, volume REAL, pct_change REAL,"\n'
    '    "  display_name TEXT, category TEXT,"\n'
    '    "  PRIMARY KEY(symbol, date))"\n'
    ')\n'
    '\n'
    'def fetch_gift():\n'
    '    for sym, ticker in TICKERS:\n'
    '        try:\n'
    '            df = yf.download(ticker, period="5d", interval="1d",\n'
    '                             auto_adjust=True, progress=False)\n'
    '            if df is None or df.empty:\n'
    '                continue\n'
    '            conn = sqlite3.connect(DB, timeout=30)\n'
    '            conn.execute("PRAGMA journal_mode=WAL")\n'
    '            conn.execute(CREATE_SQL)\n'
    '            rows = []\n'
    '            prev = None\n'
    '            for dt, row in df.iterrows():\n'
    '                d   = str(dt)[:10]\n'
    '                c   = float(row["Close"])\n'
    '                pct = round((c - prev) / prev * 100, 4) if prev else None\n'
    '                rows.append((\n'
    '                    sym, d,\n'
    '                    float(row["Open"]), float(row["High"]),\n'
    '                    float(row["Low"]),  c,\n'
    '                    float(row.get("Volume", 0) or 0),\n'
    '                    pct, "GIFT Nifty Futures", "futures"\n'
    '                ))\n'
    '                prev = c\n'
    '            conn.executemany(\n'
    '                "INSERT OR REPLACE INTO global_indices_daily"\n'
    '                " (symbol,date,open,high,low,close,volume,"\n'
    '                "  pct_change,display_name,category)"\n'
    '                " VALUES (?,?,?,?,?,?,?,?,?,?)",\n'
    '                rows\n'
    '            )\n'
    '            conn.commit()\n'
    '            conn.close()\n'
    '            print(f"  {sym}: {len(rows)} rows stored")\n'
    '            if rows:\n'
    '                last = rows[-1]\n'
    '                pct_s = f"{last[7]:+.2f}%" if last[7] else ""\n'
    '                print(f"  Latest: {last[1]}  close={last[5]:.2f}  {pct_s}")\n'
    '            return True\n'
    '        except Exception as e:\n'
    '            print(f"  {sym}: {e}")\n'
    '    return False\n'
    '\n'
    'ok = fetch_gift()\n'
    'print("GIFT Nifty: OK" if ok else "GIFT Nifty: FAILED (not critical)")\n'
)
(MICC / "fetch_gift_nifty.py").write_text(gift, encoding="utf-8")
print("  [OK] fetch_gift_nifty.py")


# ── [3] micc_status.py ───────────────────────────────────────────────────────
log("[3] Writing micc_status.py...")

status = (
    'import sqlite3, json, sys\n'
    'from pathlib import Path\n'
    'from datetime import datetime\n'
    '\n'
    'DA = Path(r"D:\\MICC")\n'
    'DB = r"D:\\marketDB\\db\\market.db"\n'
    '\n'
    'def q1(sql, params=()):\n'
    '    try:\n'
    '        c = sqlite3.connect(DB, timeout=10)\n'
    '        r = c.execute(sql, params).fetchone()\n'
    '        c.close()\n'
    '        return r[0] if r else None\n'
    '    except Exception as e:\n'
    '        return f"ERR: {e}"\n'
    '\n'
    'def rj(p):\n'
    '    try: return json.loads(Path(p).read_text())\n'
    '    except: return {}\n'
    '\n'
    'def fmt(v):\n'
    '    if isinstance(v, int): return f"{v:,}"\n'
    '    return str(v) if v is not None else "N/A"\n'
    '\n'
    'print("=" * 55)\n'
    'print(f"MICC STATUS -- {datetime.now().strftime(\"%Y-%m-%d %H:%M\")}")\n'
    'print("=" * 55)\n'
    '\n'
    'print("\\nDATABASE:")\n'
    'checks = [\n'
    '    ("Stock rows",          "SELECT COUNT(*) FROM stock_data"),\n'
    '    ("Symbols",             "SELECT COUNT(DISTINCT symbol) FROM stock_data"),\n'
    '    ("Latest price date",   "SELECT MAX(date) FROM stock_data"),\n'
    '    ("Patterns (v3)",       "SELECT COUNT(*) FROM seasonality_patterns_v3"),\n'
    '    ("OOS validated",       "SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE oos_accuracy IS NOT NULL"),\n'
    '    ("Fundamentals",        "SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE scrape_ok=1"),\n'
    '    ("Conviction scores",   "SELECT COUNT(*) FROM symbol_conviction"),\n'
    '    ("XGB scores",          "SELECT COUNT(*) FROM symbol_conviction_xgb"),\n'
    '    ("HMM regime rows",     "SELECT COUNT(*) FROM hmm_regime_daily"),\n'
    '    ("Signals history",     "SELECT COUNT(*) FROM signals_history"),\n'
    '    ("Insider trades",      "SELECT COUNT(*) FROM insider_trading"),\n'
    '    ("News headlines",      "SELECT COUNT(*) FROM news_headlines"),\n'
    '    ("Global indices rows", "SELECT COUNT(*) FROM global_indices_daily"),\n'
    ']\n'
    'for label, sql in checks:\n'
    '    val = fmt(q1(sql))\n'
    '    print(f"  {label:<25} {val}")\n'
    '\n'
    'print("\\nAGENTS:")\n'
    'for name in ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","fusion","hmm"]:\n'
    '    p = DA / "agents" / name / "last_report.json"\n'
    '    if p.exists():\n'
    '        d  = rj(p)\n'
    '        ts = d.get("generated_at") or d.get("date") or d.get("timestamp") or "?"\n'
    '        print(f"  {name:<12} OK   {ts}")\n'
    '    else:\n'
    '        print(f"  {name:<12} MISSING")\n'
    '\n'
    'print("\\nHMM REGIME:")\n'
    'hmm = rj(DA / "agents" / "hmm" / "last_report.json")\n'
    'if hmm:\n'
    '    reg  = hmm.get("current_regime", "?")\n'
    '    conf = hmm.get("confidence", 0)\n'
    '    bull = hmm.get("bull_prob", 0)\n'
    '    bear = hmm.get("bear_prob", 0)\n'
    '    print(f"  {reg}  conf={conf:.0%}  bull={bull:.0%}  bear={bear:.0%}")\n'
    'else:\n'
    '    print("  No data -- run: py agent_hmm.py")\n'
    '\n'
    'print("\\nPIPELINE STATE:")\n'
    'ps_path = Path(r"D:\\MICC\\data_pipeline\\pipeline_state.json")\n'
    'if ps_path.exists():\n'
    '    ps = json.loads(ps_path.read_text())\n'
    '    print(f"  Last run : {ps.get(\"last_run\", \"?\")}")\n'
    '    phases = ps.get("phases", {})\n'
    '    ok  = sum(1 for v in phases.values() if v)\n'
    '    tot = len(phases)\n'
    '    print(f"  Phases   : {ok}/{tot} green")\n'
    '    for ph, status in phases.items():\n'
    '        icon = "OK" if status else "FAIL"\n'
    '        print(f"    {ph:<25} {icon}")\n'
    'else:\n'
    '    print("  pipeline_state.json not found")\n'
    '\n'
    'print()\n'
    'print("Dashboard  : http://localhost:3000")\n'
    'print("Brief      : py D:\\\\MICC\\\\morning_brief.py")\n'
    'print("ML update  : py D:\\\\MICC\\\\daily_ml_update.py")\n'
    'print("Scheduler  : schtasks /Create /XML D:\\\\MICC\\\\micc_ml_scheduler.xml /TN MICC_Daily_ML_Update")\n'
)
(MICC / "micc_status.py").write_text(status, encoding="utf-8")
print("  [OK] micc_status.py")


# ── [4] Verify XML is readable for schtasks ───────────────────────────────────
log("[4] Verifying XML file...")
try:
    content = xml_path.read_text(encoding="utf-16")
    if "<Task" in content and "Python" in content:
        print("  [OK] XML valid and readable")
    else:
        print("  [WARN] XML may be malformed")
except Exception as e:
    print(f"  [ERROR] {e}")


print()
print("=" * 55)
print("PHASE 9 DONE")
print("=" * 55)
print()
print("Run status check:")
print("  py D:\\MICC\\micc_status.py")
print()
print("Install Task Scheduler (PowerShell as admin):")
print('  schtasks /Create /XML "D:\\MICC\\micc_ml_scheduler.xml" /TN "MICC_Daily_ML_Update"')
print()
print("Git push:")
print("  py D:\\MICC\\git_push_phase3.py")
