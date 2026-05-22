import sqlite3, json, sys
from pathlib import Path
from datetime import datetime

DA = Path(r"D:\MICC")
DB = r"D:\marketDB\db\market.db"

def q1(sql, params=()):
    try:
        c = sqlite3.connect(DB, timeout=10)
        r = c.execute(sql, params).fetchone()
        c.close()
        return r[0] if r else None
    except Exception as e:
        return f"ERR: {e}"

def rj(p):
    try: return json.loads(Path(p).read_text())
    except: return {}

def fmt(v):
    if isinstance(v, int): return f"{v:,}"
    return str(v) if v is not None else "N/A"

print("=" * 55)
print(f"MICC STATUS -- {datetime.now().strftime("%Y-%m-%d %H:%M")}")
print("=" * 55)

print("\nDATABASE:")
checks = [
    ("Stock rows",          "SELECT COUNT(*) FROM stock_data"),
    ("Symbols",             "SELECT COUNT(DISTINCT symbol) FROM stock_data"),
    ("Latest price date",   "SELECT MAX(date) FROM stock_data"),
    ("Patterns (v3)",       "SELECT COUNT(*) FROM seasonality_patterns_v3"),
    ("OOS validated",       "SELECT COUNT(*) FROM seasonality_patterns_v3 WHERE oos_accuracy IS NOT NULL"),
    ("Fundamentals",        "SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE scrape_ok=1"),
    ("Conviction scores",   "SELECT COUNT(*) FROM symbol_conviction"),
    ("XGB scores",          "SELECT COUNT(*) FROM symbol_conviction_xgb"),
    ("HMM regime rows",     "SELECT COUNT(*) FROM hmm_regime_daily"),
    ("Signals history",     "SELECT COUNT(*) FROM signals_history"),
    ("Insider trades",      "SELECT COUNT(*) FROM insider_trading"),
    ("News headlines",      "SELECT COUNT(*) FROM news_headlines"),
    ("Global indices rows", "SELECT COUNT(*) FROM global_indices_daily"),
]
for label, sql in checks:
    val = fmt(q1(sql))
    print(f"  {label:<25} {val}")

print("\nAGENTS:")
for name in ["alpha","beta","gamma","delta","epsilon","zeta","eta","iota","fusion","hmm"]:
    p = DA / "agents" / name / "last_report.json"
    if p.exists():
        d  = rj(p)
        ts = d.get("generated_at") or d.get("date") or d.get("timestamp") or "?"
        print(f"  {name:<12} OK   {ts}")
    else:
        print(f"  {name:<12} MISSING")

print("\nHMM REGIME:")
hmm = rj(DA / "agents" / "hmm" / "last_report.json")
if hmm:
    reg  = hmm.get("current_regime", "?")
    conf = hmm.get("confidence", 0)
    bull = hmm.get("bull_prob", 0)
    bear = hmm.get("bear_prob", 0)
    print(f"  {reg}  conf={conf:.0%}  bull={bull:.0%}  bear={bear:.0%}")
else:
    print("  No data -- run: py agent_hmm.py")

print("\nPIPELINE STATE:")
ps_path = Path(r"D:\MICC\data_pipeline\pipeline_state.json")
if ps_path.exists():
    ps = json.loads(ps_path.read_text())
    print(f"  Last run : {ps.get("last_run", "?")}")
    phases = ps.get("phases", {})
    ok  = sum(1 for v in phases.values() if v)
    tot = len(phases)
    print(f"  Phases   : {ok}/{tot} green")
    for ph, status in phases.items():
        icon = "OK" if status else "FAIL"
        print(f"    {ph:<25} {icon}")
else:
    print("  pipeline_state.json not found")

print()
print("Dashboard  : http://localhost:3000")
print("Brief      : py D:\\MICC\\morning_brief.py")
print("ML update  : py D:\\MICC\\daily_ml_update.py")
print("Scheduler  : schtasks /Create /XML D:\\MICC\\micc_ml_scheduler.xml /TN MICC_Daily_ML_Update")
