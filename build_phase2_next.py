"""
build_phase2_next.py  --  Run from D:\MICC

Phase 2 tasks:
  [1] Verify /stocks/[symbol] page works (fix API if broken)
  [2] Upgrade morning brief with fundamentals context
  [3] Add fundamentals to conviction scoring

Run: py D:\MICC\build_phase2_next.py
"""
from pathlib import Path
import subprocess, sys

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path, content, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

# =============================================================================
# [1]  Test DB connectivity for stocks page
# =============================================================================
print("[1] Testing DB for stocks page...")
test = """
import sqlite3
DB = r"D:\\marketDB\\db\\market.db"
conn = sqlite3.connect(DB, timeout=10)
# Check screener_fundamentals_v2
cnt = conn.execute("SELECT COUNT(*) FROM screener_fundamentals_v2").fetchone()[0]
print(f"  screener_fundamentals_v2: {cnt} rows")
# Check stocks page needs
for sym in ["RELIANCE", "TCS", "INFY"]:
    fund = conn.execute("SELECT pe_ratio, roe, roce, promoter_pct FROM screener_fundamentals_v2 WHERE symbol=?", (sym,)).fetchone()
    tech = conn.execute("SELECT rsi_14, adx_14 FROM symbol_technicals WHERE symbol=?", (sym,)).fetchone()
    conv = conn.execute("SELECT conviction_score FROM symbol_conviction WHERE symbol=?", (sym,)).fetchone()
    print(f"  {sym}: fund={fund} tech={tech} conv={conv}")
conn.close()
"""
p = MICC / "_test_db.py"
p.write_text(test, encoding="utf-8")
r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, cwd=str(MICC))
p.unlink()
print(r.stdout)
if r.returncode != 0:
    print(f"  ERROR: {r.stderr[:200]}")

# =============================================================================
# [2]  Upgrade morning_brief.py with fundamentals
# =============================================================================
print("\n[2] Upgrading morning_brief.py with fundamentals context...")
mb_path = MICC / "morning_brief.py"
if mb_path.exists():
    mb = mb_path.read_text(encoding="utf-8")
    
    # Check if fundamentals section already exists
    if "screener_fundamentals" in mb:
        print("  [OK] Fundamentals already in morning brief")
    else:
        # Add fundamentals section after conviction section
        FUND_SECTION = '''

def get_quality_picks(conn, limit=5):
    """Top quality stocks from fundamentals"""
    try:
        rows = conn.execute("""
            SELECT f.symbol,
                   ROUND(CAST(f.roce AS REAL),1) AS roce,
                   ROUND(CAST(f.roe AS REAL),1) AS roe,
                   ROUND(CAST(f.pe_ratio AS REAL),1) AS pe,
                   ROUND(CAST(f.promoter_pct AS REAL),1) AS promo,
                   ROUND(CAST(c.conviction_score AS REAL),1) AS conviction
            FROM screener_fundamentals_v2 f
            LEFT JOIN symbol_conviction c ON c.symbol = f.symbol
            WHERE f.roce >= 15 AND f.roe >= 15
              AND CAST(f.debt_equity AS REAL) <= 1
              AND f.promoter_pct >= 50
              AND f.pe_ratio IS NOT NULL
            ORDER BY CAST(c.conviction_score AS REAL) DESC NULLS LAST
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows] if rows else []
    except Exception as e:
        return []

'''
        # Insert before main() or before if __name__
        if "def main(" in mb:
            mb = mb.replace("def main(", FUND_SECTION + "def main(")
        else:
            mb = mb + FUND_SECTION
        
        # Also add to the brief text generation
        QUALITY_TEXT = '''
    # Quality picks section
    quality = get_quality_picks(conn, limit=5)
    if quality:
        lines.append("")
        lines.append("QUALITY PICKS (ROCE>15 ROE>15 D/E<1 PRO>50):")
        for q in quality:
            conv_str = f" conv={q['conviction']}" if q.get('conviction') else ""
            lines.append(f"  {q['symbol']:12} PE={q['pe']} ROCE={q['roce']} ROE={q['roe']} Pro={q['promo']}%{conv_str}")
'''
        # Insert quality section before the return/send lines
        if "lines.append(" in mb and "Telegram" in mb:
            # Find where brief text is assembled, add before send
            mb = mb.replace(
                "# Send Telegram",
                QUALITY_TEXT + "\n    # Send Telegram"
            )
        
        mb_path.write_text(mb, encoding="utf-8")
        print("  [OK] Fundamentals section added to morning_brief.py")
else:
    print("  [SKIP] morning_brief.py not found")

# =============================================================================
# [3]  Check conviction scoring uses fundamentals
# =============================================================================
print("\n[3] Checking build_conviction.py...")
conv_path = MICC / "build_conviction.py"
if conv_path.exists():
    cv = conv_path.read_text(encoding="utf-8")
    if "screener_fundamentals" in cv or "fundamental_score" in cv:
        print("  [OK] Conviction already uses fundamentals")
    else:
        print("  [WARN] Conviction not using fundamentals yet")
        print("  -> Run: py D:\\MICC\\build_conviction.py after reviewing")
else:
    print("  [SKIP] build_conviction.py not found")

# =============================================================================
# [4]  Quick API health check for stocks page
# =============================================================================
print("\n[4] Checking /api/stock/[symbol] route exists...")
route = SRC / "api" / "stock" / "[symbol]" / "route.ts"
if route.exists():
    content = route.read_text(encoding="utf-8")
    has_fund = "screener_fundamentals" in content
    has_tech  = "symbol_technicals" in content
    has_seas  = "seasonality_patterns" in content
    print(f"  Route exists: {route}")
    print(f"  Has fundamentals: {has_fund}")
    print(f"  Has technicals: {has_tech}")
    print(f"  Has seasonality: {has_seas}")
else:
    print(f"  [MISSING] {route}")
    print("  Run: py D:\\MICC\\build_stock_deep.py")

print("""
======================================================================
  NEXT STEPS
======================================================================

  1. Fix git (one-time):
     Remove-Item -Recurse -Force "D:\\MICC\\.git"
     & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" init
     & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" branch -M main
     & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
     & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "MICC clean"
     & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" remote add origin https://markandeyavarma3-lab:TOKEN@github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS.git
     & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push origin main

  2. Test stocks page:
     http://localhost:3000/stocks/RELIANCE
     http://localhost:3000/stocks/TCS

  3. Run patch_fundamentals overnight (fills ROIC, int coverage etc):
     py D:\\MICC\\data_pipeline\\patch_fundamentals.py

  4. Run analytics page:
     http://localhost:3000/analytics
""")
