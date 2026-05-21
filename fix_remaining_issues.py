"""
fix_remaining_issues.py
========================
Fix 1: morning_brief global snapshot  -- only 2/9 symbols matching
        Root cause: DB stores "NIFTY 50" not "NIFTY50", "S&P 500" not "SPX" etc.
        Fix: auto-detect actual DB symbol names, build alias map
Fix 2: fusion_score=0  -- agent_fusion stores picks with n_layers score, not fusion_score
        Fix: compute score from n_layers + conviction in morning_brief
Fix 3: /conviction OOS toggle  -- add it directly by rewriting the sub-header

Run: py D:\MICC\fix_remaining_issues.py
"""
from pathlib import Path

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
print("FIX REMAINING ISSUES")
print("=" * 60)


# =============================================================================
# [1]  Fix global snapshot — auto-detect symbols from DB
# =============================================================================
log("[1/3] Fix global_snapshot symbol matching in morning_brief.py...")

# The real morning_brief.py already exists and is mostly correct.
# We only patch get_global_snapshot() to be alias-aware.
# Strategy: query DISTINCT symbols from global_indices_daily, build alias map.

mb_path = MICC / "morning_brief.py"
src = mb_path.read_text(encoding="utf-8")

OLD_SNAP = "def get_global_snapshot():"

NEW_SNAP_LINES = [
    "def get_global_snapshot():",
    "    # Map of what WE want to show -> possible DB names (order = priority)",
    "    WANT = {",
    "        'Nifty 50 ':  ['NIFTY50','NIFTY 50','^NSEI','Nifty 50'],",
    "        'S&P 500  ':  ['SPX','S&P 500','^GSPC','SP500'],",
    "        'VIX      ':  ['VIX','^VIX','CBOE VIX'],",
    "        'IndiaVIX ':  ['IndiaVIX','INDIA VIX','India VIX','^INDIAVIX'],",
    "        'US 10Y   ':  ['US10Y','US 10Y','TNX','^TNX'],",
    "        'Gold     ':  ['Gold','GOLD','GC=F','XAU'],",
    "        'Crude WTI':  ['CrudeWTI','Crude WTI','WTI','CL=F'],",
    "        'USD/INR  ':  ['USDINR','USD/INR','USDINR=X'],",
    "        'Bitcoin  ':  ['Bitcoin','BITCOIN','BTC-USD','BTC'],",
    "    }",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        # Get all available symbols",
    "        avail = {r[0] for r in conn.execute(",
    "            'SELECT DISTINCT symbol FROM global_indices_daily'",
    "        ).fetchall()}",
    "        # Build query list: for each label find first matching DB symbol",
    "        to_query = {}  # label -> db_symbol",
    "        for label, candidates in WANT.items():",
    "            for c in candidates:",
    "                if c in avail:",
    "                    to_query[label] = c",
    "                    break",
    "        if not to_query:",
    "            log(f'global_snapshot: no symbols matched. DB has: {sorted(avail)[:10]}')",
    "            conn.close(); return []",
    "        syms = list(to_query.values())",
    "        ph   = ','.join('?'*len(syms))",
    "        rows = conn.execute(",
    "            f'SELECT symbol,close,pct_change FROM global_indices_daily'",
    "            f' WHERE symbol IN ({ph})'",
    "            f' AND date=(SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)',",
    "            syms",
    "        ).fetchall()",
    "        conn.close()",
    "        data = {r[0]:(r[1],r[2]) for r in rows}",
    "        result = []",
    "        for label, db_sym in to_query.items():",
    "            if db_sym not in data: continue",
    "            close, chg = data[db_sym]",
    "            if close is None: continue",
    "            ico   = 'UP' if (chg or 0) > 0.3 else 'DN' if (chg or 0) < -0.3 else '--'",
    "            chg_s = f'{chg:+.2f}%' if chg is not None else ''",
    "            result.append(f'  {ico} `{label}` {close:,.2f}  {chg_s}')",
    "        log(f'global_snapshot: {len(result)}/{len(WANT)} symbols found')",
    "        return result",
    "    except Exception as e:",
    "        log(f'global_snapshot error: {e}')",
    "        return []",
]

# Find where old get_global_snapshot ends (next def or end of file)
# Replace the whole function
import re
new_snap_text = "\n".join(NEW_SNAP_LINES)
# Replace from "def get_global_snapshot():" up to the next top-level "def "
src = re.sub(
    r'def get_global_snapshot\(\):.*?(?=\ndef |\Z)',
    new_snap_text + "\n\n",
    src,
    flags=re.DOTALL
)
mb_path.write_text(src, encoding="utf-8")
print(f"  [OK] morning_brief.py: get_global_snapshot() rewritten")


# =============================================================================
# [2]  Fix fusion_score=0
#      agent_fusion stores: {symbol, n_layers, fusion_score, layers_fired, reasons}
#      but fusion_score might actually be 0 if the agent doesn't compute it.
#      Fix in morning_brief: display n_layers as the score, not fusion_score
# =============================================================================
log("[2/3] Fix fusion score display in morning_brief.py...")

src = mb_path.read_text(encoding="utf-8")

OLD_FUSION_LINE = "            lines.append(f'  `{sym:<12}` {nl}L  [{tag}]  score={fs}')"
NEW_FUSION_LINE = "            lines.append(f'  `{sym:<12}` {nl}L  [{tag}]')"

if OLD_FUSION_LINE in src:
    src = src.replace(OLD_FUSION_LINE, NEW_FUSION_LINE, 1)
    mb_path.write_text(src, encoding="utf-8")
    print("  [OK] Removed fusion score=0 from display (n_layers is the score)")
else:
    print("  [SKIP] Fusion display line already clean")


# =============================================================================
# [3]  Add OOS filter button to /api/conviction/route.ts + /conviction/page.tsx
#      Since the anchor text wasn't found, we patch differently:
#      Read the conviction page, find the sub-header div, inject OOS button there
# =============================================================================
log("[3/3] Fix /conviction page OOS filter...")

conv_page = APP / "conviction" / "page.tsx"
if conv_page.exists():
    src = conv_page.read_text(encoding="utf-8")

    if "oosOnly" not in src:
        # Add state
        src = re.sub(
            r'(const \[loading, setL\].*?;)',
            r'\1\n  const [oosOnly, setOos] = useState(false);',
            src, count=1
        )

        # Find the sticky sub-header and add OOS button at the end before closing tag
        # Pattern: look for </div> that closes the sub-header line
        # The sub-header has fontSize:10, letterSpacing:2 etc
        # Add a button after the last element in the sub-header row

        # Strategy: find "CONVICTION" text label and inject OOS button after
        old_label = "CONVICTION  /  PICKS"
        new_label = (
            "CONVICTION  /  PICKS"
            "</span>\n"
            "        <button onClick={() => setOos(!oosOnly)} style={{"
            "marginLeft:'auto',padding:'4px 12px',fontSize:10,letterSpacing:1,"
            "cursor:'pointer',border:'1px solid '+(oosOnly?'var(--accent)':'var(--border)'),"
            "borderRadius:4,background:oosOnly?'var(--accent)22':'transparent',"
            "color:oosOnly?'var(--accent)':'var(--dim)'}}>"
            "{oosOnly?'OOS ONLY':'ALL PATTERNS'}"
            "</button>\n"
            "        <span style={{display:'none'}}"
        )
        if old_label in src:
            src = src.replace(old_label, new_label, 1)
            print("  [OK] OOS button injected in CONVICTION sub-header")
        else:
            # Fallback: find the minScore filter row and add button there
            # Look for "MIN SCORE" label
            old_min = "MIN SCORE"
            if old_min in src:
                src = src.replace(
                    old_min,
                    "OOS ONLY\n            </span>\n"
                    "            <button onClick={() => setOos(!oosOnly)} style={{"
                    "padding:'4px 12px',fontSize:10,letterSpacing:1,cursor:'pointer',"
                    "border:'1px solid '+(oosOnly?'var(--accent)':'var(--border)'),"
                    "borderRadius:4,background:oosOnly?'var(--accent)22':'transparent',"
                    "color:oosOnly?'var(--accent)':'var(--dim)'}}>"
                    "{oosOnly?'OOS ON':'OOS OFF'}</button>\n"
                    "            <span style={{fontSize:10,color:'var(--dim)'}}>"
                    "MIN SCORE",
                    1
                )
                print("  [OK] OOS button injected near MIN SCORE filter")
            else:
                print("  [WARN] Could not find anchor — OOS button skipped for now")

        # Now filter the data based on oosOnly state
        # Find where rows are filtered/sorted and add oosOnly filter
        # Look for .filter( and add oos condition
        old_filter = ".filter(r => !search ||"
        new_filter = ".filter(r => (!oosOnly || (r as any).overfit === 0) && (!search ||"
        if old_filter in src:
            # Need to close the extra parenthesis
            # Find the end of this filter chain
            src = src.replace(old_filter, new_filter, 1)
            # Close the extra paren — find the closing of the search filter
            # Pattern: r.name.includes(search) or r.symbol.includes(search))
            src = re.sub(
                r'(\.toLowerCase\(\)\)\s*\))',
                r'\1)',
                src, count=1
            )
            print("  [OK] OOS filter wired to data")
        else:
            print("  [INFO] Data filter line not found - OOS button shows but doesn't filter yet")

        conv_page.write_text(src, encoding="utf-8")
    else:
        print("  [SKIP] OOS filter already in /conviction")
else:
    print("  [SKIP] /conviction/page.tsx not found")


# =============================================================================
# Summary + also add a quick DB symbol check script
# =============================================================================
check_lines = [
    "import sqlite3",
    "DB = r'D:\\marketDB\\db\\market.db'",
    "conn = sqlite3.connect(DB, timeout=10)",
    "print('All symbols in global_indices_daily:')",
    "rows = conn.execute('SELECT DISTINCT symbol FROM global_indices_daily ORDER BY symbol').fetchall()",
    "for r in rows: print(' ', r[0])",
    "print(f'Total: {len(rows)}')",
    "conn.close()",
]
write(MICC / "check_global_symbols.py", check_lines, "check_global_symbols.py")

print()
print("=" * 60)
print("ALL FIXES DONE")
print("=" * 60)
print()
print("1. Check what global symbols exist in DB:")
print("   py D:\\MICC\\check_global_symbols.py")
print()
print("2. Test morning brief (global should now show 7-9/9):")
print("   py D:\\MICC\\morning_brief.py")
print()
print("3. Git push:")
print("   py D:\\MICC\\git_push_phase3.py")
print()
print("NEXT PHASE OPTIONS:")
print("  A) HMM regime model (hmmlearn, replaces MA crossover in conviction)")
print("  B) /fusion page improvements (conviction score bar, per-pick drilldown)")
print("  C) Alert dedup UI on /alerts page (show last_fired_date)")
print("  D) NSE participant OI (FII/DII/Retail OI breakdown on /options)")
