# -*- coding: utf-8 -*-
"""
MICC Engine Wrapper (Phase 1.4)
Replaces run_engine_wrapper.ps1 — avoids PowerShell encoding issues.

What it does:
  1. Runs health_check.py — aborts if critical failure
  2. Starts Ollama if not running
  3. Runs micc_engine.py --days 7 --send

Usage:
  py run_engine_wrapper.py
"""

import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

PYTHON      = sys.executable
PROJ        = Path(r"D:\MICC")
LOG_DIR     = PROJ / "agents" / "logs"
LOG_FILE    = LOG_DIR / "engine_run.log"
OLLAMA_EXE  = Path(r"C:\Users\marka\AppData\Local\Programs\Ollama\ollama.exe")

LOG_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    log("=== MICC Engine Wrapper START ===")

    # Step 1: Health check
    log("Running health_check.py...")
    hc = subprocess.run(
        [PYTHON, str(PROJ / "health_check.py"), "--quiet"],
        cwd=str(PROJ)
    )
    log(f"Health check exit code: {hc.returncode}")

    if hc.returncode != 0:
        log("HEALTH CHECK FAILED - engine will not run.")
        sys.exit(1)

    log("Health check passed.")

    # Step 2: Start Ollama if not running
    if OLLAMA_EXE.exists():
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq ollama.exe"],
            capture_output=True, text=True
        )
        if "ollama.exe" not in result.stdout:
            log("Starting Ollama...")
            subprocess.Popen(
                [str(OLLAMA_EXE), "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            import time; time.sleep(8)
            log("Ollama started.")
        else:
            log("Ollama already running.")
    else:
        log("Ollama not found - Groq fallback will be used.")

    # Step 3: Run engine
    log("Starting micc_engine.py --days 7 --send ...")
    engine = subprocess.run(
        [PYTHON, str(PROJ / "micc_engine.py"), "--days", "7", "--send"],
        cwd=str(PROJ)
    )
    log(f"Engine finished with exit code: {engine.returncode}")
    log("=== MICC Engine Wrapper END ===")
    sys.exit(engine.returncode)

if __name__ == "__main__":
    main()
