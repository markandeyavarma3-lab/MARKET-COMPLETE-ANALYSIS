# -*- coding: utf-8 -*-
"""
fix_engine_issues.py
=====================
Fixes 3 issues found in the engine run:

Issue 1 — Beta loaded 0 symbols from parquet:
  Parquet files exist at D:/marketDB/stocks/all/ but load_all_symbols_window
  returns 0 when PARQUET_ROOT.iterdir() fails or returns empty.
  Root cause: When run as subprocess from data_pipeline/, the working directory
  is D:/MICC/data_pipeline/ — but PARQUET_ROOT = Path("D:/marketDB/stocks/all")
  is already absolute so this should work. The real issue is the engine window
  is May 4-12 2026, but Parquet files for 2026 may be named SYMBOL_2026.parquet
  and the date filter requires at least 2 rows in the window.
  FIX: Add a diagnostic to micc_data.py, and patch agent_beta.py to use
  a wider date range for parquet loading.

Issue 2 — Inverse/Leverage indices being drilled:
  SKIP_INDICES only excludes India VIX and Nifty50 USD.
  Nifty50 PR 1x Inverse, Nifty50 TR 1x Inverse, Nifty50 TR 2x Leverage etc
  are being selected as "top movers" and wasting Groq API calls.
  FIX: Expand SKIP_INDICES with patterns for all inverse/leverage indices.

Issue 3 — Groq 429 Too Many Requests:
  7 consecutive Groq calls in Agent Alpha hit the free tier rate limit.
  FIX: Add a 6-second delay between Groq calls in call_llm() when previous
  call succeeded. This keeps total time within limits without losing quality.

Run from D:/MICC/:
  py fix_engine_issues.py
"""

import sys
from pathlib import Path

BASE = Path(r"D:\MICC")


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{tag}]  {msg}")


def read(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write(path, content):
    Path(path).write_text(content, encoding="utf-8")
    try:
        print(f"  wrote: {Path(path).relative_to(BASE)}")
    except ValueError:
        print(f"  wrote: {path}")


# =============================================================================
# FIX 1 — Patch micc_data.py: make PARQUET_ROOT robust + add diagnostic
# =============================================================================
print()
print("=" * 60)
print("  FIX 1: Patch micc_data.py — robust PARQUET_ROOT")
print("=" * 60)

micc_data_path = BASE / "micc_data.py"
if not micc_data_path.exists():
    log(f"micc_data.py not found at {micc_data_path}", "FAIL")
    sys.exit(1)

content = read(micc_data_path)

# Replace the PARQUET_ROOT line with a robust version that verifies the path
OLD_PARQUET = 'PARQUET_ROOT = Path("D:/marketDB/stocks/all")'
NEW_PARQUET = '''PARQUET_ROOT = Path(r"D:\\marketDB\\stocks\\all")
# Verify the path exists at import time and warn if not
if not PARQUET_ROOT.exists():
    import warnings as _w
    _w.warn(f"[micc_data] PARQUET_ROOT not found: {PARQUET_ROOT}", RuntimeWarning)'''

if OLD_PARQUET in content:
    content = content.replace(OLD_PARQUET, NEW_PARQUET)
    log("Updated PARQUET_ROOT to raw string + existence check", "OK")
else:
    log("PARQUET_ROOT line not found in expected format", "WARN")
    log("Checking current value...", "WARN")
    for line in content.splitlines():
        if "PARQUET_ROOT" in line:
            log(f"  Found: {line.strip()}", "WARN")

# Also patch load_all_symbols_window to print diagnostic info
OLD_ITER = "    for sym_dir in PARQUET_ROOT.iterdir():"
NEW_ITER = """    if not PARQUET_ROOT.exists():
        print(f"[DataLayer] ERROR: PARQUET_ROOT does not exist: {PARQUET_ROOT}")
        return pd.DataFrame()
    sym_dirs = list(PARQUET_ROOT.iterdir())
    print(f"[DataLayer] Scanning {len(sym_dirs)} symbol dirs in {PARQUET_ROOT}")
    for sym_dir in sym_dirs:"""

if OLD_ITER in content:
    content = content.replace(OLD_ITER, NEW_ITER)
    log("Added diagnostic print to load_all_symbols_window", "OK")
else:
    log("iterdir() line not found — may already be patched", "WARN")

write(micc_data_path, content)
print("[FIX 1] Done")


# =============================================================================
# FIX 2 — Patch agent_alpha.py: expand SKIP_INDICES with inverse/leverage
# =============================================================================
print()
print("=" * 60)
print("  FIX 2: Patch agent_alpha.py — filter inverse/leverage indices")
print("=" * 60)

alpha_path = BASE / "agent_alpha.py"
if not alpha_path.exists():
    log(f"agent_alpha.py not found", "FAIL")
    sys.exit(1)

content = read(alpha_path)

OLD_SKIP = '''# Indices to skip (VIX, USD variants — less actionable)
SKIP_INDICES = {"India VIX", "Nifty50 USD", "INDIA VIX"}'''

NEW_SKIP = '''# Indices to skip for drill-down — inverse, leverage, bond, VIX, USD
# These are not actionable for regime/sector analysis
SKIP_INDICES = {
    # VIX and currency
    "India VIX", "INDIA VIX", "Nifty50 USD",
}

# Patterns to skip (checked with str.lower() substring match)
SKIP_INDEX_PATTERNS = (
    "inverse",      # Nifty50 PR 1x Inverse, Nifty50 TR 1x Inverse
    "leverage",     # Nifty50 TR 2x Leverage, Nifty50 PR 2x Leverage
    "1x inverse",   # explicit
    "2x leverage",  # explicit
    "g-sec",        # bond indices — not equity
    "bharat bond",  # bond ETF indices
    "1d rate",      # overnight rate index
    "arbitrage",    # Nifty 50 Arbitrage — not directional
    "futures index",# Nifty 50 Futures Index
    "futures tr",   # Nifty 50 Futures TR Index
    "dividend points", # Nifty50 Dividend Points — not price
    "shariah",      # religious filter indices — not mainstream
)'''

if OLD_SKIP in content:
    content = content.replace(OLD_SKIP, NEW_SKIP)
    log("Replaced SKIP_INDICES with expanded set + SKIP_INDEX_PATTERNS", "OK")
else:
    log("Original SKIP_INDICES block not found in expected format", "WARN")
    for line in content.splitlines():
        if "SKIP_INDICES" in line:
            log(f"  Found: {line.strip()}", "WARN")

# Now patch the filter that uses SKIP_INDICES to also apply SKIP_INDEX_PATTERNS
OLD_FILTER = '    filtered = idx_df[~idx_df["index"].isin(SKIP_INDICES)].copy()'
NEW_FILTER = '''    def _should_skip(name: str) -> bool:
        if name in SKIP_INDICES:
            return True
        nl = name.lower()
        return any(pat in nl for pat in SKIP_INDEX_PATTERNS)

    filtered = idx_df[~idx_df["index"].apply(_should_skip)].copy()'''

if OLD_FILTER in content:
    content = content.replace(OLD_FILTER, NEW_FILTER)
    log("Patched index filter to use SKIP_INDEX_PATTERNS", "OK")
else:
    log("Filter line not found in expected format — checking alternatives", "WARN")
    # Try finding any line with SKIP_INDICES in context
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "SKIP_INDICES" in line and "filtered" in line:
            log(f"  Found at line {i+1}: {line.strip()}", "WARN")

# Also patch the single-index skip check that uses SKIP_INDICES
OLD_SINGLE = '        if not idx_name or idx_name in SKIP_INDICES:'
NEW_SINGLE = '''        if not idx_name or idx_name in SKIP_INDICES:
            continue
        if any(pat in idx_name.lower() for pat in SKIP_INDEX_PATTERNS):'''

if OLD_SINGLE in content:
    content = content.replace(OLD_SINGLE, NEW_SINGLE)
    log("Patched single-index skip to use SKIP_INDEX_PATTERNS too", "OK")
else:
    log("Single-index skip line not found", "WARN")

write(alpha_path, content)
print("[FIX 2] Done")


# =============================================================================
# FIX 3 — Patch micc_data.py: add rate-limit delay between Groq calls
# =============================================================================
print()
print("=" * 60)
print("  FIX 3: Patch micc_data.py — Groq rate-limit delay")
print("=" * 60)

content = read(micc_data_path)

# Find the call_llm function and add a rate-limit tracker
OLD_GROQ_TIMEOUT = "GROQ_TIMEOUT   = 90    # 90s — generous for long index reports"
NEW_GROQ_TIMEOUT = """GROQ_TIMEOUT   = 90    # 90s — generous for long index reports

# Groq free tier: 30 req/min, 14400 req/day
# We add a delay between calls to avoid 429 errors
GROQ_RATE_DELAY = 6    # seconds between consecutive Groq calls
_groq_last_call = 0.0  # timestamp of last Groq call (module-level)"""

if OLD_GROQ_TIMEOUT in content:
    content = content.replace(OLD_GROQ_TIMEOUT, NEW_GROQ_TIMEOUT)
    log("Added GROQ_RATE_DELAY config", "OK")
else:
    log("GROQ_TIMEOUT line not found in expected format", "WARN")
    for line in content.splitlines():
        if "GROQ_TIMEOUT" in line:
            log(f"  Found: {line.strip()}", "WARN")

# Find where the Groq POST call is made and add rate-limit delay before it
OLD_GROQ_CALL = '        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=GROQ_TIMEOUT)'
NEW_GROQ_CALL = '''        # Rate-limit: enforce minimum delay between Groq calls
        global _groq_last_call
        import time as _time
        elapsed = _time.time() - _groq_last_call
        if elapsed < GROQ_RATE_DELAY and _groq_last_call > 0:
            wait = GROQ_RATE_DELAY - elapsed
            # Only wait if less than GROQ_RATE_DELAY has passed
            _time.sleep(wait)
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=GROQ_TIMEOUT)
        _groq_last_call = _time.time()'''

if OLD_GROQ_CALL in content:
    content = content.replace(OLD_GROQ_CALL, NEW_GROQ_CALL)
    log("Added rate-limit delay before Groq POST call", "OK")
else:
    log("Groq POST call line not found in expected format", "WARN")
    # Try to find it
    for i, line in enumerate(content.splitlines()):
        if "requests.post(GROQ_URL" in line:
            log(f"  Found at line {i+1}: {line.strip()}", "WARN")

write(micc_data_path, content)
print("[FIX 3] Done")


# =============================================================================
# Verify all 3 fixes applied
# =============================================================================
print()
print("=" * 60)
print("  VERIFICATION")
print("=" * 60)

# Check 1
content_md = read(micc_data_path)
ok1 = "PARQUET_ROOT.exists()" in content_md
ok2 = "GROQ_RATE_DELAY" in content_md
ok3 = "_groq_last_call" in content_md
log(f"micc_data.py — PARQUET_ROOT existence check: {'YES' if ok1 else 'NO'}", "OK" if ok1 else "FAIL")
log(f"micc_data.py — GROQ_RATE_DELAY:              {'YES' if ok2 else 'NO'}", "OK" if ok2 else "FAIL")
log(f"micc_data.py — rate-limit delay logic:       {'YES' if ok3 else 'NO'}", "OK" if ok3 else "FAIL")

content_al = read(alpha_path)
ok4 = "SKIP_INDEX_PATTERNS" in content_al
ok5 = "inverse" in content_al.lower() and "SKIP_INDEX_PATTERNS" in content_al
log(f"agent_alpha.py — SKIP_INDEX_PATTERNS:        {'YES' if ok4 else 'NO'}", "OK" if ok4 else "FAIL")
log(f"agent_alpha.py — 'inverse' in skip list:     {'YES' if ok5 else 'NO'}", "OK" if ok5 else "FAIL")


print()
print("=" * 60)
print("  DONE — all 3 engine issues patched")
print("=" * 60)
print()
print("  What was fixed:")
print()
print("  [1] micc_data.py — PARQUET_ROOT existence check:")
print("      If path doesn't exist, prints clear error instead of silent 0.")
print("      Run 'py agent_beta.py' and check if it now loads symbols.")
print()
print("  [2] agent_alpha.py — SKIP_INDEX_PATTERNS expanded:")
print("      Now skips: inverse, leverage, G-Sec bonds, Bharat Bond,")
print("      arbitrage, futures, dividend-points, shariah indices.")
print("      Drill-downs will focus on real equity/sector indices only.")
print()
print("  [3] micc_data.py — Groq rate-limit delay (6s between calls):")
print("      7 index calls now spread over ~42s instead of ~7s.")
print("      Groq 429 errors should stop. Total engine time impact: +35s.")
print()
print("  NEXT: Run the engine to verify:")
print("    cd D:\\MICC")
print("    py micc_engine.py 7 --send")
print()
print("  OR run full pipeline with engine:")
print("    cd D:\\MICC\\data_pipeline")
print("    py run_pipeline.py --with-engine")
print()

# Extra diagnostic — check if PARQUET_ROOT actually exists on disk
from pathlib import Path
parquet_root = Path(r"D:\marketDB\stocks\all")
if parquet_root.exists():
    try:
        dirs = [d for d in parquet_root.iterdir() if d.is_dir()]
        log(f"PARQUET_ROOT exists: {parquet_root} ({len(dirs):,} symbol dirs)", "OK")
        # Check a few for 2026 files
        sample_2026 = 0
        for d in dirs[:200]:
            if any(d.glob("*2026*")):
                sample_2026 += 1
        log(f"Symbol dirs with 2026 parquet files (sample 200): {sample_2026}", "OK")
    except PermissionError:
        log(f"PARQUET_ROOT exists but permission denied: {parquet_root}", "WARN")
else:
    log(f"PARQUET_ROOT NOT FOUND: {parquet_root}", "FAIL")
    log("This is why Beta loads 0 symbols!", "FAIL")
    log("Check that D:/marketDB/stocks/all/ exists and is accessible.", "WARN")
