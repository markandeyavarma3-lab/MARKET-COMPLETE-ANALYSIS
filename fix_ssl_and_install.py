"""
fix_ssl_and_install.py
=======================
Fixes the broken SSL certificate path that blocks pip installs.

Root cause: An old GDAL/PostGIS install left behind an environment variable:
  REQUESTS_CA_BUNDLE = D:\\filesssss\\ssl\\certs\\ca-bundle.crt
  (that path no longer exists)

pip uses REQUESTS_CA_BUNDLE to verify SSL, finds the file missing, and fails
every single network operation — including all pip installs.

Fix:
  1. Delete the broken env vars (REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE, SSL_CERT_FILE)
     from the Windows user environment permanently using reg delete + setx.
  2. Install all missing packages with the broken var temporarily cleared.
  3. Re-run micc_engine.py with the latest available dates.

Run from D:/MICC/:
  py fix_ssl_and_install.py
"""

import os
import subprocess
import sys
from pathlib import Path

PIPE = Path(r"D:\MICC\data_pipeline")
MICC = Path(r"D:\MICC")


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{tag}]  {msg}", flush=True)


def run_clean(cmd, timeout=300, cwd=None):
    """Run a command with the broken SSL env vars removed."""
    env = os.environ.copy()
    # Remove every broken cert path variable
    for key in ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE",
                "GDAL_DATA", "PROJ_LIB"]:
        env.pop(key, None)
    # Set certifi's correct bundle
    try:
        import certifi
        bundle = certifi.where()
        env["REQUESTS_CA_BUNDLE"] = bundle
        env["SSL_CERT_FILE"]      = bundle
    except ImportError:
        pass
    return subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout, env=env, cwd=cwd
    )


# =============================================================================
# Step 1: Delete the broken registry env vars permanently
# =============================================================================
print()
print("=" * 60)
print("  STEP 1: Remove broken SSL certificate env vars")
print("=" * 60)
print()

BROKEN_VARS = ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"]

for var in BROKEN_VARS:
    current = os.environ.get(var, "")
    if current and "filesssss" in current:
        log(f"Found broken: {var} = {current}", "WARN")
        # Delete from user registry
        try:
            result = subprocess.run(
                ["reg", "delete",
                 r"HKCU\Environment",
                 "/v", var, "/f"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                log(f"Deleted from registry: {var}", "OK")
            else:
                log(f"reg delete failed for {var}: {result.stderr[:100]}", "WARN")
        except Exception as e:
            log(f"Could not delete {var}: {e}", "WARN")
        # Also clear in current process
        os.environ.pop(var, None)
        log(f"Cleared in current process: {var}", "OK")
    elif current:
        log(f"{var} = {current[:60]} (keeping — looks valid)")
    else:
        log(f"{var} not set — skipping")

# Set correct certifi bundle in current process
try:
    import certifi
    bundle = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = bundle
    os.environ["SSL_CERT_FILE"]      = bundle
    os.environ["CURL_CA_BUNDLE"]     = bundle
    log(f"Set certifi bundle: {bundle}", "OK")
except ImportError:
    log("certifi not found — SSL may still fail", "WARN")


# =============================================================================
# Step 2: Install all missing packages with clean environment
# =============================================================================
print()
print("=" * 60)
print("  STEP 2: Install missing packages (with clean SSL env)")
print("=" * 60)
print()

ALL_PACKAGES = [
    "selenium",
    "webdriver-manager",
    "nselib",
    "nsefin",
    "fredapi",
    "tenacity",
]

failed = []
for pkg in ALL_PACKAGES:
    log(f"Installing {pkg}...")
    result = run_clean(
        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
        timeout=180
    )
    if result.returncode == 0:
        log(f"{pkg}", "OK")
    else:
        # Try --break-system-packages
        result2 = run_clean(
            [sys.executable, "-m", "pip", "install", pkg,
             "--quiet", "--break-system-packages"],
            timeout=180
        )
        if result2.returncode == 0:
            log(f"{pkg} (--break-system-packages)", "OK")
        else:
            err = (result.stderr or result2.stderr or "")[-200:]
            log(f"{pkg} FAILED: {err}", "FAIL")
            failed.append(pkg)


# =============================================================================
# Step 3: Set env vars permanently so pip always works in future
# =============================================================================
print()
print("=" * 60)
print("  STEP 3: Permanently fix env vars in Windows registry")
print("=" * 60)
print()

try:
    import certifi
    bundle = certifi.where()
    for var in ["REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"]:
        r = subprocess.run(
            ["setx", var, bundle],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            log(f"Permanently set {var} = {bundle}", "OK")
        else:
            log(f"Could not set {var}: {r.stderr[:80]}", "WARN")
except ImportError:
    log("certifi not available for permanent fix", "WARN")


# =============================================================================
# Step 4: Verify all imports
# =============================================================================
print()
print("=" * 60)
print("  STEP 4: Verifying imports")
print("=" * 60)
print()

CHECKS = [
    ("selenium",           "from selenium import webdriver"),
    ("webdriver_manager",  "from webdriver_manager.chrome import ChromeDriverManager"),
    ("nselib",             "from nselib import capital_market"),
    ("nsefin",             "import nsefin"),
    ("fredapi",            "from fredapi import Fred"),
    ("yfinance",           "import yfinance"),
    ("pandas",             "import pandas"),
    ("numpy",              "import numpy"),
    ("pyarrow",            "import pyarrow"),
    ("certifi",            "import certifi"),
    ("requests",           "import requests"),
]

all_ok = True
for name, stmt in CHECKS:
    result = run_clean([sys.executable, "-c", stmt], timeout=15)
    if result.returncode == 0:
        log(f"{name:25} OK", "OK")
    else:
        log(f"{name:25} MISSING", "FAIL")
        all_ok = False


# =============================================================================
# Step 5: Run daily_update.py to refresh market_snapshot with latest NSE data
# =============================================================================
print()
print("=" * 60)
print("  STEP 5: Running daily_update.py to get latest market dates")
print("=" * 60)
print()

if all_ok or "selenium" not in [p for p in failed]:
    log("Running daily_update.py (this takes 2-5 minutes)...")
    result = run_clean(
        [sys.executable, str(PIPE / "daily_update.py")],
        timeout=600,
        cwd=str(PIPE)
    )
    if result.returncode == 0:
        log("daily_update.py completed", "OK")
        print(result.stdout[-800:] if result.stdout else "")
    else:
        log("daily_update.py failed:", "FAIL")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-8:]:
                log(f"  {line}", "FAIL")
        log("Run manually: cd D:\\MICC\\data_pipeline && py daily_update.py", "WARN")
else:
    log("selenium still missing — cannot run daily_update.py", "WARN")
    log("After fixing, run: cd D:\\MICC\\data_pipeline && py daily_update.py", "WARN")


# =============================================================================
print()
print("=" * 60)
print("  SUMMARY")
print("=" * 60)
print()

if failed:
    print("  Packages still missing:")
    for p in failed:
        print(f"    - {p}")
    print()
    print("  Manual install (run in a NEW terminal):")
    print(f"  py -m pip install {' '.join(failed)}")
    print()
else:
    print("  All packages installed.")
    print()

print("  NEXT STEPS (in a NEW PowerShell window):")
print()
print("  1. Update data:")
print("     cd D:\\MICC\\data_pipeline")
print("     py run_pipeline.py")
print()
print("  2. Re-run intelligence engine:")
print("     cd D:\\MICC")
print("     py micc_engine.py 7 --send")
print()
print("  3. Refresh dashboard at http://localhost:3000")
print()
print("  NOTE: Open a NEW PowerShell window — the deleted env vars")
print("  only take effect in new terminals, not the current one.")
print()
