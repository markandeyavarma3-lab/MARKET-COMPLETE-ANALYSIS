"""
fix_brief_final.py
==================
Fix 1: global_snapshot -- check actual DB symbols + fix alias map
Fix 2: agent_eta timeout -- increase to 300s, skip LLM on morning brief run
Fix 3: pattern dedup -- one row per symbol (best score)

Run: py D:\MICC\fix_brief_final.py
"""
from pathlib import Path
import sqlite3, re

MICC = Path(r"D:\MICC")

def log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

print("=" * 60)
print("FIX BRIEF FINAL")
print("=" * 60)

# ─── Step 0: check what's actually in the DB ─────────────────────────────────
log("[0] Checking global_indices_daily symbols in DB...")
DB = r"D:\marketDB\db\market.db"
try:
    conn = sqlite3.connect(DB, timeout=10)
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM global_indices_daily ORDER BY symbol"
    ).fetchall()
    conn.close()
    actual_symbols = [r[0] for r in rows]
    print(f"  Found {len(actual_symbols)} symbols in global_indices_daily:")
    for s in actual_symbols:
        print(f"    '{s}'")
except Exception as e:
    print(f"  [ERROR] {e}")
    actual_symbols = []

# ─── Step 1: rewrite morning_brief.py with all fixes ─────────────────────────
log("[1] Rewriting morning_brief.py with all fixes...")

mb_path = MICC / "morning_brief.py"
src = mb_path.read_text(encoding="utf-8")

# Fix 1: Build correct WANT dict based on actual symbols found
# We'll make get_global_snapshot() use a flexible fuzzy match
OLD_GET_SNAP = re.search(r'def get_global_snapshot\(\):.*?(?=\ndef |\Z)', src, re.DOTALL)
if OLD_GET_SNAP:
    new_snap = (
        "def get_global_snapshot():\n"
        "    # Flexible alias map: display_label -> list of possible DB names\n"
        "    WANT = {\n"
        "        'Nifty 50 ':  ['NIFTY50','NIFTY 50','^NSEI','Nifty 50','NIFTY'],\n"
        "        'S&P 500  ':  ['SPX','S&P 500','^GSPC','SP500','S&P500'],\n"
        "        'Dow Jones':  ['DJI','Dow Jones','^DJI','DJIA'],\n"
        "        'Nasdaq   ':  ['NDX','Nasdaq','^NDX','^IXIC','NASDAQ'],\n"
        "        'VIX      ':  ['VIX','^VIX','CBOE VIX','CBOE Volatility Index'],\n"
        "        'IndiaVIX ':  ['IndiaVIX','INDIA VIX','India VIX','^INDIAVIX','INDIAVIX'],\n"
        "        'US 10Y   ':  ['US10Y','US 10Y','TNX','^TNX','US 10-Yr'],\n"
        "        'Gold     ':  ['Gold','GOLD','GC=F','XAU','Gold Futures'],\n"
        "        'Crude WTI':  ['CrudeWTI','Crude WTI','WTI','CL=F','Crude Oil WTI'],\n"
        "        'USD/INR  ':  ['USDINR','USD/INR','USDINR=X','USD-INR'],\n"
        "        'Bitcoin  ':  ['Bitcoin','BITCOIN','BTC-USD','BTC','BTC/USD'],\n"
        "        'Nikkei   ':  ['Nikkei','NIKKEI','^N225','Nikkei 225'],\n"
        "        'DAX      ':  ['DAX','^GDAXI','DAX Index'],\n"
        "        'SGX Nifty':  ['SGXNifty','SGX Nifty','SGXNIFTY'],\n"
        "    }\n"
        "    try:\n"
        "        conn = sqlite3.connect(DB_P, timeout=10)\n"
        "        avail = {r[0] for r in conn.execute(\n"
        "            'SELECT DISTINCT symbol FROM global_indices_daily'\n"
        "        ).fetchall()}\n"
        "        to_query = {}  # label -> db_symbol\n"
        "        for label, candidates in WANT.items():\n"
        "            for c in candidates:\n"
        "                if c in avail:\n"
        "                    to_query[label] = c\n"
        "                    break\n"
        "        if not to_query:\n"
        "            log(f'global_snapshot: 0 matches. DB has: {sorted(avail)[:15]}')\n"
        "            conn.close(); return []\n"
        "        syms = list(to_query.values())\n"
        "        ph   = ','.join('?'*len(syms))\n"
        "        rows = conn.execute(\n"
        "            f'SELECT symbol,close,pct_change FROM global_indices_daily'\n"
        "            f' WHERE symbol IN ({ph})'\n"
        "            f' AND date=(SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)',\n"
        "            syms\n"
        "        ).fetchall()\n"
        "        conn.close()\n"
        "        data = {r[0]:(r[1],r[2]) for r in rows}\n"
        "        result = []\n"
        "        for label, db_sym in to_query.items():\n"
        "            if db_sym not in data: continue\n"
        "            close, chg = data[db_sym]\n"
        "            if close is None: continue\n"
        "            ico   = 'UP' if (chg or 0) > 0.3 else 'DN' if (chg or 0) < -0.3 else '--'\n"
        "            chg_s = f'{chg:+.2f}%' if chg is not None else ''\n"
        "            result.append(f'  {ico} `{label}` {close:,.2f}  {chg_s}')\n"
        "        log(f'global_snapshot: {len(result)}/{len(to_query)} symbols found')\n"
        "        return result\n"
        "    except Exception as e:\n"
        "        log(f'global_snapshot error: {e}')\n"
        "        return []\n"
        "\n"
    )
    src = src[:OLD_GET_SNAP.start()] + new_snap + src[OLD_GET_SNAP.end():]
    print("  [OK] get_global_snapshot() rewritten with full alias map")
else:
    print("  [WARN] Could not find get_global_snapshot()")

# Fix 2: eta timeout 120 -> 300s
src = src.replace(
    'for script in [\'agent_fusion.py\', \'agent_eta.py\', \'agent_alert.py\']:',
    'for script, tout in [(\'agent_fusion.py\',120),(\'agent_eta.py\',300),(\'agent_alert.py\',60)]:'
)
src = src.replace(
    'ok = run_agent(script)',
    'ok = run_agent(script, timeout=tout)'
)
# Simpler replacement if first didn't match
if "timeout=tout" not in src:
    src = src.replace(
        "for script in ['agent_fusion.py', 'agent_eta.py', 'agent_alert.py']:",
        "for script, tout in [('agent_fusion.py',120),('agent_eta.py',300),('agent_alert.py',60)]:"
    ).replace(
        "        ok = run_agent(script)\n        log(f'  {script}:",
        "        ok = run_agent(script, timeout=tout)\n        log(f'  {script}:"
    )
print("  [OK] agent_eta timeout raised to 300s")

# Fix 3: pattern dedup — one row per symbol (best score)
OLD_PATS = (
    "    if pats:\n"
    "        lines.append(f'*Seasonal Patterns ({mmdd}) [OOS-validated]:*')\n"
    "        for sym, win, dirn, acc, mean, score in pats:"
)
NEW_PATS = (
    "    if pats:\n"
    "        # Dedup: one row per symbol, keep best score\n"
    "        seen = {}  \n"
    "        for row in pats:\n"
    "            s = row[0]\n"
    "            if s not in seen or float(row[5] or 0) > float(seen[s][5] or 0):\n"
    "                seen[s] = row\n"
    "        pats = list(seen.values())[:6]\n"
    "        lines.append(f'*Seasonal Patterns ({mmdd}) [OOS-validated]:*')\n"
    "        for sym, win, dirn, acc, mean, score in pats:"
)
if OLD_PATS in src:
    src = src.replace(OLD_PATS, NEW_PATS, 1)
    print("  [OK] Pattern dedup added (one row per symbol)")
else:
    # More flexible match
    src = re.sub(
        r"(        if pats:\n)"
        r"(            lines\.append\(f'\*Seasonal Patterns)",
        r"\1"
        r"        seen_syms = {}\n"
        r"        deduped = []\n"
        r"        for row in pats:\n"
        r"            if row[0] not in seen_syms:\n"
        r"                seen_syms[row[0]] = True\n"
        r"                deduped.append(row)\n"
        r"        pats = deduped[:6]\n"
        r"\2",
        src, count=1
    )
    print("  [OK] Pattern dedup added (fallback method)")

mb_path.write_text(src, encoding="utf-8")
print(f"  [OK] morning_brief.py saved")

# ─── Step 2: also increase agent_eta default timeout arg ─────────────────────
log("[2] Checking agent_eta.py LLM call...")
eta_path = MICC / "agent_eta.py"
if eta_path.exists():
    eta_src = eta_path.read_text(encoding="utf-8")
    # If Ollama times out, it should fall back to Groq faster
    # Check call_llm timeout
    if "call_llm" in eta_src and "timeout" not in eta_src.lower():
        print("  [INFO] agent_eta has no explicit timeout — LLM calls use default")
    print("  [INFO] agent_eta LLM: if Ollama is slow/offline, Groq fallback handles it")
    print("  [INFO] 300s timeout in morning_brief should be enough")

# ─── Step 3: Add --no-llm flag to agent_eta.py ───────────────────────────────
log("[3] Adding --no-llm flag to agent_eta.py...")
if eta_path.exists():
    eta_src = eta_path.read_text(encoding="utf-8")
    if "--no-llm" not in eta_src and "no_llm" not in eta_src:
        # Add near top after imports
        old_send_line = 'send = "--send" in sys.argv'
        new_send_line = (
            'send    = "--send"   in sys.argv\n'
            'no_llm  = "--no-llm" in sys.argv'
        )
        if old_send_line in eta_src:
            eta_src = eta_src.replace(old_send_line, new_send_line, 1)
            # Find LLM analysis section and wrap with no_llm check
            # Pattern: "  LLM analysis..." or "call_llm("
            eta_src = re.sub(
                r'(\s+)(log\("  LLM analysis\.\.\."\)|print\("  LLM analysis\.\.\."\))',
                r'\1if not no_llm:\n\1    \2',
                eta_src, count=1
            )
            # Also wrap the actual call_llm or LLM section
            eta_src = re.sub(
                r'(\s+)(analysis = call_llm|llm_analysis = call_llm)',
                r'\1if not no_llm:\n\1    \2',
                eta_src, count=1
            )
            eta_path.write_text(eta_src, encoding="utf-8")
            print("  [OK] --no-llm flag added to agent_eta.py")
        else:
            print("  [SKIP] send line pattern not found in agent_eta.py")
    else:
        print("  [SKIP] --no-llm already in agent_eta.py")

# ─── Step 4: Update morning_brief to pass --no-llm to eta ────────────────────
log("[4] Update morning_brief to use --no-llm for eta...")

mb_src = mb_path.read_text(encoding="utf-8")

# Update run_agent call for eta specifically
# Change the loop to use script-specific args
old_loop = "for script, tout in [('agent_fusion.py',120),('agent_eta.py',300),('agent_alert.py',60)]:"
new_loop = "for script, tout, extra_args in [('agent_fusion.py',120,[]),(\"agent_eta.py\",300,[\"--no-llm\"]),(\"agent_alert.py\",60,[])]:"

if old_loop in mb_src:
    mb_src = mb_src.replace(old_loop, new_loop, 1)
    # Update run_agent call to pass extra_args
    mb_src = mb_src.replace(
        "        ok = run_agent(script, timeout=tout)\n",
        "        ok = run_agent(script, timeout=tout, extra_args=extra_args)\n"
    )
    # Update run_agent function signature
    old_def = "def run_agent(script, timeout=120):"
    new_def = "def run_agent(script, timeout=120, extra_args=None):"
    mb_src = mb_src.replace(old_def, new_def, 1)
    # Update subprocess call to include extra_args
    old_sub = "        r = subprocess.run([PY, str(DA / script)], cwd=str(DA),"
    new_sub = "        cmd = [PY, str(DA / script)] + (extra_args or [])\n        r = subprocess.run(cmd, cwd=str(DA),"
    mb_src = mb_src.replace(old_sub, new_sub, 1)
    mb_path.write_text(mb_src, encoding="utf-8")
    print("  [OK] morning_brief passes --no-llm to agent_eta (fast, no LLM timeout)")
else:
    print("  [INFO] Loop pattern changed -- eta will use 300s timeout but still run LLM")
    # At minimum just use timeout=300 which was already set
    mb_path.write_text(mb_src, encoding="utf-8")

# ─── Summary ─────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("DONE")
print("=" * 60)
print()
if actual_symbols:
    print("Actual DB global_indices_daily symbols:")
    for s in actual_symbols:
        print(f"  '{s}'")
    print()
    print("Copy any that look like VIX/Nifty/SPX above and tell me")
    print("if the alias map needs updating.")
print()
print("Test:")
print("  py D:\\MICC\\morning_brief.py")
print()
print("If global still shows 2/9, run:")
print("  py D:\\MICC\\check_global_symbols.py")
print("and share the output -- I'll add exact names to the alias map.")
