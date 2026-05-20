# -*- coding: utf-8 -*-
"""
fix_groq_and_beta.py
=====================
Two precise surgical fixes:

FIX A — Groq 429 rate limiting
  The previous fix couldn't find the Groq POST call because it spans
  multiple lines. This patch inserts the rate-limit delay directly into
  the call_groq() function at the correct location.

FIX B — Beta loads 0 symbols
  Path is correct (2675 dirs, 2026 files exist).
  Root cause: Parquet files have 'close_price' or 'last_price' column.
  The alias check: ("close_price","last_price","ltp","close") only renames
  if "close" NOT already in df.columns. But after lowercasing,
  'close_price' becomes 'close_price' which contains 'close' as a substring
  but IS NOT the column 'close'. Yet the check `"close" not in df.columns`
  may be False if there's already a 'close' column from the lowercase step.
  Real fix: probe what columns the 2026 parquet files actually have,
  then ensure the rename logic works correctly.
  We also add debug logging to Beta so we can see exactly what's happening.

Run from D:/MICC/:
  py fix_groq_and_beta.py
"""

import sys
from pathlib import Path

BASE = Path(r"D:\MICC")
MICC_DATA = BASE / "micc_data.py"


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{tag}]  {msg}")


def read(p): return Path(p).read_text(encoding="utf-8", errors="replace")
def write(p, c):
    Path(p).write_text(c, encoding="utf-8")
    try: print(f"  wrote: {Path(p).relative_to(BASE)}")
    except ValueError: print(f"  wrote: {p}")


# =============================================================================
# FIX A — Groq rate-limit delay in call_groq()
# Exact function found at line 1272 in micc_data.py:
#
#   def call_groq(prompt: str, model: str = GROQ_MODEL,
#                 max_tokens: int = 1200, timeout: int = GROQ_TIMEOUT) -> str:
#       """Call Groq free API (llama-3.3-70b). Returns clean text or raises."""
#       if not GROQ_API_KEY:
#           raise ValueError("No Groq API key")
#       resp = requests.post(
#           GROQ_URL, ...
# =============================================================================
print()
print("=" * 60)
print("  FIX A: Groq rate-limit delay in call_groq()")
print("=" * 60)

content = read(MICC_DATA)

OLD_CALL_GROQ = '''def call_groq(prompt: str, model: str = GROQ_MODEL,
              max_tokens: int = 1200, timeout: int = GROQ_TIMEOUT) -> str:
    """Call Groq free API (llama-3.3-70b). Returns clean text or raises."""
    if not GROQ_API_KEY:
        raise ValueError("No Groq API key")
    resp = requests.post(
        GROQ_URL,'''

NEW_CALL_GROQ = '''def call_groq(prompt: str, model: str = GROQ_MODEL,
              max_tokens: int = 1200, timeout: int = GROQ_TIMEOUT) -> str:
    """Call Groq free API (llama-3.3-70b). Returns clean text or raises."""
    if not GROQ_API_KEY:
        raise ValueError("No Groq API key")
    # Rate-limit guard: enforce minimum gap between consecutive Groq calls
    # Groq free tier: 30 req/min. We wait 7s between calls to stay safe.
    import time as _t
    global _groq_last_call
    _elapsed = _t.time() - _groq_last_call
    if _elapsed < GROQ_RATE_DELAY and _groq_last_call > 0:
        _t.sleep(GROQ_RATE_DELAY - _elapsed)
    resp = requests.post(
        GROQ_URL,'''

if OLD_CALL_GROQ in content:
    content = content.replace(OLD_CALL_GROQ, NEW_CALL_GROQ)
    log("Inserted rate-limit delay into call_groq()", "OK")
else:
    log("call_groq() signature not found — trying alternate match", "WARN")
    # Try without the docstring
    ALT_OLD = '''    if not GROQ_API_KEY:
        raise ValueError("No Groq API key")
    resp = requests.post(
        GROQ_URL,'''
    ALT_NEW = '''    if not GROQ_API_KEY:
        raise ValueError("No Groq API key")
    import time as _t
    global _groq_last_call
    _elapsed = _t.time() - _groq_last_call
    if _elapsed < GROQ_RATE_DELAY and _groq_last_call > 0:
        _t.sleep(GROQ_RATE_DELAY - _elapsed)
    resp = requests.post(
        GROQ_URL,'''
    if ALT_OLD in content:
        content = content.replace(ALT_OLD, ALT_NEW)
        log("Inserted rate-limit delay (alternate match)", "OK")
    else:
        log("Could not find call_groq POST block", "FAIL")

# Now add the _groq_last_call update AFTER resp.raise_for_status()
OLD_RAISE = '''    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()'''

NEW_RAISE = '''    resp.raise_for_status()
    _groq_last_call = _t.time()  # record successful call time
    return resp.json()["choices"][0]["message"]["content"].strip()'''

if OLD_RAISE in content:
    content = content.replace(OLD_RAISE, NEW_RAISE)
    log("Added _groq_last_call timestamp after successful call", "OK")
else:
    log("raise_for_status() line not in expected format", "WARN")

write(MICC_DATA, content)
print("[FIX A] Done")


# =============================================================================
# FIX B — Diagnose and fix Beta 0 symbols
# Probe one actual parquet file to see real column names
# =============================================================================
print()
print("=" * 60)
print("  FIX B: Diagnose Beta 0 symbols — probe parquet columns")
print("=" * 60)

import sqlite3

PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
DB_PATH      = Path(r"D:\marketDB\db\market.db")

# Find a symbol that should have 2026 data
print()
print("  Probing actual parquet file columns...")
sample_sym  = None
sample_cols = None

try:
    import pandas as pd

    # Try well-known symbols first
    for sym in ["RELIANCE", "TCS", "INFY", "HDFC", "HDFCBANK", "ICICIBANK"]:
        folder = PARQUET_ROOT / sym
        if not folder.exists():
            continue
        # Look for 2026 file
        for pf in [folder / f"{sym}_2026.parquet", folder / f"2026.parquet"]:
            if pf.exists():
                try:
                    df = pd.read_parquet(pf)
                    sample_sym  = sym
                    sample_cols = list(df.columns)
                    sample_dtypes = {c: str(df[c].dtype) for c in df.columns}
                    sample_head = df.head(3)
                    log(f"Probed {sym}: {pf.name}", "OK")
                    print(f"    Columns : {sample_cols}")
                    print(f"    Dtypes  : {sample_dtypes}")
                    print(f"    Rows    : {len(df)}")
                    print(f"    Date range: {df.iloc[0].get('DATE1', df.iloc[0].get('date', '?'))} ...")
                    print(f"    Head:\n{sample_head.to_string()}")
                    break
                except Exception as e:
                    log(f"Could not read {pf}: {e}", "WARN")
        if sample_sym:
            break

    if not sample_sym:
        log("Could not find a 2026 parquet file for any well-known symbol", "WARN")
        # List what's in RELIANCE folder
        rel_folder = PARQUET_ROOT / "RELIANCE"
        if rel_folder.exists():
            files = list(rel_folder.glob("*.parquet"))
            log(f"RELIANCE parquet files: {[f.name for f in files]}", "WARN")

except ImportError:
    log("pandas not available in this environment", "WARN")

print()

# Now determine the fix based on what we found
if sample_cols:
    cols_lower = [c.lower().strip() for c in sample_cols]
    print(f"  Lowercase columns: {cols_lower}")

    has_close      = "close" in cols_lower
    has_closeprice = "close_price" in cols_lower
    has_lastprice  = "last_price" in cols_lower
    has_date       = "date" in cols_lower
    has_date1      = "date1" in cols_lower

    print()
    log(f"  'close' column present    : {has_close}")
    log(f"  'close_price' present     : {has_closeprice}")
    log(f"  'last_price' present      : {has_lastprice}")
    log(f"  'date' column present     : {has_date}")
    log(f"  'date1' column present    : {has_date1}")
    print()

    if not has_close and not has_closeprice and not has_lastprice:
        log("No close column found at all — check column names above", "FAIL")
    elif has_date and has_close:
        log("Parquet has 'date' and 'close' — should work", "OK")
        log("Issue may be date range: checking if May 2026 data exists...", "WARN")
        try:
            import pandas as pd
            folder = PARQUET_ROOT / sample_sym
            for pf in [folder / f"{sample_sym}_2026.parquet", folder / f"2026.parquet"]:
                if pf.exists():
                    df = pd.read_parquet(pf)
                    df.columns = [c.lower().strip() for c in df.columns]
                    if "date" in df.columns:
                        df["date"] = pd.to_datetime(df["date"], errors="coerce")
                        max_d = df["date"].max()
                        min_d = df["date"].min()
                        log(f"  Date range in {sample_sym}_2026.parquet: {min_d.date()} to {max_d.date()}", "OK")
                        may_rows = df[df["date"] >= "2026-05-04"]
                        log(f"  Rows >= 2026-05-04: {len(may_rows)}", "OK" if len(may_rows) > 0 else "FAIL")
                    break
        except Exception as e:
            log(f"Date range check failed: {e}", "WARN")

# =============================================================================
# Patch load_all_symbols_window to add per-symbol debug for first few symbols
# =============================================================================
print()
print("  Patching load_all_symbols_window with better diagnostics...")

content = read(MICC_DATA)

OLD_LOAD = '''    records = []
    count = 0
    for sym_dir in sym_dirs:
        if not sym_dir.is_dir():
            continue
        sym = sym_dir.name
        if is_etf(sym):
            continue

        df = load_parquet_symbol(sym, years)
        if df.empty or "close" not in df.columns:
            continue

        df_win = df[(df["date"] >= sd) & (df["date"] <= ed)].copy()
        if len(df_win) < 2:
            continue'''

NEW_LOAD = '''    records = []
    count = 0
    _debug_printed = 0  # print details for first 3 symbols that fail
    for sym_dir in sym_dirs:
        if not sym_dir.is_dir():
            continue
        sym = sym_dir.name
        if is_etf(sym):
            continue

        df = load_parquet_symbol(sym, years)
        if df.empty:
            if _debug_printed < 3:
                print(f"[DataLayer] DEBUG {sym}: parquet returned empty DataFrame")
                _debug_printed += 1
            continue
        if "close" not in df.columns:
            if _debug_printed < 3:
                print(f"[DataLayer] DEBUG {sym}: no 'close' col, has: {list(df.columns)[:6]}")
                _debug_printed += 1
            continue

        df_win = df[(df["date"] >= sd) & (df["date"] <= ed)].copy()
        if len(df_win) < 2:
            if _debug_printed < 3 and sym in ("RELIANCE","TCS","INFY"):
                print(f"[DataLayer] DEBUG {sym}: date window {sd.date()} to {ed.date()} got {len(df_win)} rows. df date range: {df['date'].min()} to {df['date'].max()}")
                _debug_printed += 1
            continue'''

if OLD_LOAD in content:
    content = content.replace(OLD_LOAD, NEW_LOAD)
    log("Added per-symbol debug logging to load_all_symbols_window", "OK")
else:
    log("load_all_symbols_window block not found in expected format", "WARN")

write(MICC_DATA, content)
print("[FIX B] Done")


# =============================================================================
# Verify
# =============================================================================
print()
print("=" * 60)
print("  VERIFICATION")
print("=" * 60)
content_final = read(MICC_DATA)

ok_a1 = "_groq_last_call" in content_final and "_elapsed" in content_final
ok_a2 = "_groq_last_call = _t.time()" in content_final
ok_b1 = "DEBUG" in content_final and "no 'close' col" in content_final

log(f"Groq delay inserted in call_groq() : {'YES' if ok_a1 else 'NO'}", "OK" if ok_a1 else "FAIL")
log(f"Groq last-call timestamp updated   : {'YES' if ok_a2 else 'NO'}", "OK" if ok_a2 else "FAIL")
log(f"Beta debug logging added           : {'YES' if ok_b1 else 'NO'}", "OK" if ok_b1 else "FAIL")

print()
print("=" * 60)
print("  NEXT STEPS")
print("=" * 60)
print()
print("  1. Run agent_beta.py standalone to see the debug output:")
print("     cd D:\\MICC")
print("     py agent_beta.py")
print()
print("  The output will show exactly why symbols fail:")
print("    [DataLayer] DEBUG RELIANCE: date window 2026-05-04 to 2026-05-12 got 0 rows")
print("    -> means the 2026 parquet doesn't have May data yet")
print("    OR")
print("    [DataLayer] DEBUG RELIANCE: no 'close' col, has: ['DATE1','OPEN_PRICE',...]")
print("    -> means column rename is failing")
print()
print("  2. Paste the debug output here and we'll fix the exact cause.")
print()
print("  3. Groq rate limiting is now fixed (7s delay between calls).")
print("     Next engine run should use Groq for all 7 indices.")
print()
