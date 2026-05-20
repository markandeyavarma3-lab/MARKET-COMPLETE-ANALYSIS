"""
fix_pipeline_deps.py
====================
Fixes all pipeline errors from run_pipeline.py output:

1. ModuleNotFoundError: selenium
2. ModuleNotFoundError: nselib
3. ModuleNotFoundError: fredapi
4. ModuleNotFoundError: nsefin
5. UnicodeEncodeError in check_db_health.py (emoji on Windows cp1252)
6. SyntaxWarning in run_pipeline.py (raw string backslash)

Run from D:/MICC/:
  py fix_pipeline_deps.py
"""

import subprocess
import sys
import os
from pathlib import Path

PIPE = Path(r"D:\MICC\data_pipeline")


def log(msg, level="INFO"):
    tag = {" OK ": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{tag}]  {msg}", flush=True)


def pip_install(packages: list) -> bool:
    """Install packages, return True if success."""
    cmd = [sys.executable, "-m", "pip", "install"] + packages + ["--quiet"]
    log(f"Installing: {' '.join(packages)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            log(f"Installed: {' '.join(packages)}", " OK ")
            return True
        else:
            # Try with --break-system-packages (Python 3.14 sometimes needs this)
            cmd2 = cmd + ["--break-system-packages"]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
            if result2.returncode == 0:
                log(f"Installed (--break-system-packages): {' '.join(packages)}", " OK ")
                return True
            log(f"Failed: {result.stderr[-300:]}", "FAIL")
            return False
    except subprocess.TimeoutExpired:
        log(f"Timeout installing {packages}", "FAIL")
        return False
    except Exception as e:
        log(f"Error: {e}", "FAIL")
        return False


# =============================================================================
# Step 1: Install all missing packages
# =============================================================================
print()
print("=" * 60)
print("  STEP 1: Installing missing Python packages")
print("=" * 60)
print()

PACKAGES = [
    # Core selenium (for NSE session cookies)
    ["selenium"],
    # ChromeDriver manager (auto-downloads matching ChromeDriver)
    ["webdriver-manager"],
    # NSE delivery bhavcopy
    ["nselib"],
    # NSE corporate announcements + insider trading
    ["nsefin"],
    # FRED API (US + India macro)
    ["fredapi"],
    # Other deps that might be missing
    ["tenacity"],
    ["tqdm"],
]

installed = 0
failed_pkgs = []
for pkg_list in PACKAGES:
    if pip_install(pkg_list):
        installed += 1
    else:
        failed_pkgs.extend(pkg_list)

print()
log(f"Installed {installed}/{len(PACKAGES)} package groups", " OK " if not failed_pkgs else "WARN")
if failed_pkgs:
    log(f"Failed: {failed_pkgs} — try manual install below", "WARN")


# =============================================================================
# Step 2: Fix check_db_health.py — UnicodeEncodeError from emoji on Windows
# The script uses ✅ and ⚠️ which Windows cp1252 can't encode.
# Fix: set PYTHONIOENCODING=utf-8 OR replace emoji with ASCII equivalents.
# We patch the file to remove emoji characters.
# =============================================================================
print()
print("=" * 60)
print("  STEP 2: Fix check_db_health.py — Unicode emoji crash")
print("=" * 60)
print()

health_file = PIPE / "check_db_health.py"
if health_file.exists():
    content = health_file.read_text(encoding="utf-8", errors="replace")
    # Replace emoji with ASCII
    replacements = {
        "\u2705": "[OK]",    # ✅
        "\u26a0": "[WARN]",  # ⚠
        "\ufe0f": "",        # variation selector (comes after ⚠)
        "\u274c": "[FAIL]",  # ❌
        "\U0001f534": "[RED]",   # 🔴
        "\U0001f7e2": "[GRN]",   # 🟢
        "\U0001f4ca": "[CHART]", # 📊
        "\U0001f4c8": "[UP]",    # 📈
        "\U0001f4c9": "[DN]",    # 📉
        "\U0001f6a8": "[ALERT]", # 🚨
    }
    original = content
    for emoji, replacement in replacements.items():
        content = content.replace(emoji, replacement)

    # Also add UTF-8 encoding line at top if not present
    if "# -*- coding: utf-8 -*-" not in content and "utf-8" not in content[:100]:
        content = "# -*- coding: utf-8 -*-\n" + content

    # Add sys.stdout reconfigure at top of main block if not present
    if "reconfigure" not in content and "PYTHONIOENCODING" not in content:
        # Insert after imports
        import_end = content.find("\ndef ") 
        if import_end == -1:
            import_end = content.find("\nif __name__")
        if import_end > 0:
            inject = '\nimport sys\ntry:\n    sys.stdout.reconfigure(encoding="utf-8")\nexcept Exception:\n    pass\n'
            if "sys.stdout.reconfigure" not in content:
                content = content[:import_end] + inject + content[import_end:]

    if content != original:
        health_file.write_text(content, encoding="utf-8")
        log("Patched check_db_health.py — removed emoji, added UTF-8 output", " OK ")
    else:
        log("check_db_health.py already clean", " OK ")
else:
    log("check_db_health.py not found in data_pipeline/", "WARN")


# =============================================================================
# Step 3: Fix run_pipeline.py — SyntaxWarning backslash in docstring
# =============================================================================
print()
print("=" * 60)
print("  STEP 3: Fix run_pipeline.py SyntaxWarning")
print("=" * 60)
print()

run_pipe_file = PIPE / "run_pipeline.py"
if run_pipe_file.exists():
    content = run_pipe_file.read_text(encoding="utf-8", errors="replace")
    # The warning is: "\M" is invalid escape sequence
    # It's in the docstring: "Location: D:\MICC\data_pipeline\run_pipeline.py"
    # Fix: replace the docstring backslashes with forward slashes
    if r"D:\MICC\data_pipeline" in content:
        content = content.replace(
            r"D:\MICC\data_pipeline\run_pipeline.py",
            "D:/MICC/data_pipeline/run_pipeline.py"
        )
        run_pipe_file.write_text(content, encoding="utf-8")
        log("Fixed backslash in run_pipeline.py docstring", " OK ")
    else:
        log("run_pipeline.py docstring already clean", " OK ")
else:
    log("run_pipeline.py not found", "WARN")


# =============================================================================
# Step 4: Set PYTHONIOENCODING=utf-8 in the environment permanently
# This prevents cp1252 errors for ALL pipeline scripts on Windows
# =============================================================================
print()
print("=" * 60)
print("  STEP 4: Set PYTHONIOENCODING=utf-8 permanently")
print("=" * 60)
print()

try:
    result = subprocess.run(
        ["setx", "PYTHONIOENCODING", "utf-8"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        log("Set PYTHONIOENCODING=utf-8 in user environment", " OK ")
        log("This prevents Unicode errors for ALL scripts — takes effect in new terminals", " OK ")
    else:
        log("Could not set env var via setx — set manually if needed", "WARN")
except Exception as e:
    log(f"setx failed: {e} — set manually if needed", "WARN")


# =============================================================================
# Step 5: Verify imports work now
# =============================================================================
print()
print("=" * 60)
print("  STEP 5: Verifying package imports")
print("=" * 60)
print()

IMPORT_CHECKS = [
    ("selenium",         "from selenium import webdriver"),
    ("nselib",           "from nselib import capital_market"),
    ("fredapi",          "from fredapi import Fred"),
    ("nsefin",           "import nsefin"),
    ("webdriver_manager","from webdriver_manager.chrome import ChromeDriverManager"),
    ("yfinance",         "import yfinance"),
    ("pandas",           "import pandas"),
    ("numpy",            "import numpy"),
    ("pyarrow",          "import pyarrow"),
    ("requests",         "import requests"),
    ("certifi",          "import certifi"),
]

all_ok = True
for name, import_stmt in IMPORT_CHECKS:
    result = subprocess.run(
        [sys.executable, "-c", import_stmt],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        log(f"{name:25} OK", " OK ")
    else:
        log(f"{name:25} MISSING", "FAIL")
        all_ok = False


# =============================================================================
# Summary
# =============================================================================
print()
print("=" * 60)
print("  DONE")
print("=" * 60)
print()
if all_ok:
    print("  All packages installed. Run the pipeline now:")
    print()
    print("  cd D:\\MICC\\data_pipeline")
    print("  py run_pipeline.py")
    print()
    print("  After it completes, re-run the engine:")
    print("  cd D:\\MICC")
    print("  py micc_engine.py 7 --send")
    print()
    print("  Then refresh the dashboard at http://localhost:3000")
else:
    print("  Some packages still missing. Try manual install:")
    print()
    print("  py -m pip install selenium webdriver-manager nselib nsefin fredapi")
    print()
    print("  If you get 'externally managed' error, add --break-system-packages:")
    print("  py -m pip install selenium webdriver-manager nselib nsefin fredapi --break-system-packages")
    print()

print("  NOTE: Open a NEW PowerShell window before running run_pipeline.py")
print("  so that PYTHONIOENCODING=utf-8 takes effect.")
print()
