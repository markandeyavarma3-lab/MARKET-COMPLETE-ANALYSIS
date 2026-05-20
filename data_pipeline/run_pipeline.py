"""
run_pipeline.py
================
MICC Data Pipeline - Daily Orchestrator
Location: D:/MICC/data_pipeline/run_pipeline.py

Usage:
  cd D:/MICC/data_pipeline
  py run_pipeline.py              -> full update + engine + Telegram
  py run_pipeline.py --with-engine -> same
  py run_pipeline.py --check      -> health check only
  py run_pipeline.py --weekly     -> include fundamentals + corporate actions
  py run_pipeline.py --no-engine  -> skip engine at the end
"""

import subprocess
import sys
import time
import os
import json
from datetime import datetime
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.resolve()
MICC_DIR     = PIPELINE_DIR.parent
STATE_FILE   = MICC_DIR / "pipeline_state.json"


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def clean_env():
    env = os.environ.copy()
    try:
        import certifi
        b = certifi.where()
        env["REQUESTS_CA_BUNDLE"] = b
        env["SSL_CERT_FILE"]      = b
        env["CURL_CA_BUNDLE"]     = b
    except ImportError:
        pass
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(script_path, desc, args=None, timeout=1800, cwd=None):
    cmd = [sys.executable, str(script_path)] + (args or [])
    log(f"-> {desc}")
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout,
            cwd=str(cwd or Path(script_path).parent),
            env=clean_env(),
        )
        elapsed = time.time() - t0
        if result.returncode == 0:
            log(f"{desc} ({elapsed:.0f}s)", "OK")
            return True
        else:
            log(f"{desc}  exit {result.returncode}  ({elapsed:.0f}s)", "FAIL")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-5:]:
                    log(f"   {line}", "FAIL")
            return False
    except subprocess.TimeoutExpired:
        log(f"{desc} timed out after {timeout}s", "FAIL")
        return False
    except Exception as e:
        log(f"{desc} exception: {e}", "FAIL")
        return False


def load_state():
    today = datetime.now().strftime("%Y-%m-%d")
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            if state.get("date") == today:
                return state
        except Exception:
            pass
    return {"date": today, "completed": [], "failed": []}


def save_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def run_phase(name, script_path, desc, state, args=None, timeout=1800, cwd=None):
    if name in state["completed"]:
        log(f"SKIP (already done today): {desc}", "WARN")
        return True
    ok = run(script_path, desc, args=args, timeout=timeout, cwd=cwd)
    if ok:
        state["completed"].append(name)
        if name in state["failed"]:
            state["failed"].remove(name)
    else:
        if name not in state["failed"]:
            state["failed"].append(name)
    save_state(state)
    return ok


def send_fallback_telegram(msg):
    try:
        sys.path.insert(0, str(MICC_DIR))
        from micc_data import send_telegram
        send_telegram(msg)
    except Exception:
        pass


def main():
    weekly    = "--weekly"    in sys.argv
    no_engine = "--no-engine" in sys.argv

    if "--check" in sys.argv:
        run(PIPELINE_DIR / "check_db_health.py", "DB Health Check", timeout=60)
        return

    state = load_state()

    print()
    print("=" * 65)
    print("  MICC DATA PIPELINE - FULL DAILY UPDATE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if state["completed"]:
        print(f"  Resuming: already done: {', '.join(state['completed'])}")
    print("=" * 65)
    print()

    r = {}

    r["core"]     = run_phase("core", PIPELINE_DIR / "daily_update.py",
                              "Core: Stocks + Indices + FII/DII + F&O + Global",
                              state, timeout=1200)
    r["delivery"] = run_phase("delivery", PIPELINE_DIR / "update_delivery.py",
                              "Delivery % (nselib)", state, timeout=300)
    r["us_macro"] = run_phase("us_macro", PIPELINE_DIR / "update_macro_us.py",
                              "US Macro (FRED)", state, args=["--daily"], timeout=600)
    r["mf_nav"]   = run_phase("mf_nav", PIPELINE_DIR / "update_mf_nav.py",
                              "MF NAVs", state, timeout=300)
    r["announce"] = run_phase("announce", PIPELINE_DIR / "phase4_corporate_announcements.py",
                              "Corporate Announcements", state, timeout=180)
    r["insider"]  = run_phase("insider", PIPELINE_DIR / "insider_trading_fetch.py",
                              "Insider Trading (SEBI)", state, timeout=180)
    r["news"] = run_phase("news",
                          PIPELINE_DIR / "fetch_news_final.py",
                          "News + NSE announcements",
                          state, timeout=300)

    r["yf_news"] = run_phase("yf_news",
                             PIPELINE_DIR / "fetch_yfinance_news.py",
                             "Per-stock news (yfinance top 500)",
                             state, args=["--top", "500"], timeout=600)

    r["rbi"] = run_phase("rbi",
                         PIPELINE_DIR / "fetch_phase1_data.py",
                         "RBI + G-Sec yield",
                         state, args=["--rbi", "--gsec"], timeout=300)
    # Phase 3.5 — Extended data (add after r["insider"])
    r["news"] = run_phase("news",
                          PIPELINE_DIR / "fetch_news_final.py",
                          "News headlines + NSE announcements",
                          state, timeout=300)

    r["yf_news"] = run_phase("yf_news",
                             PIPELINE_DIR / "fetch_yfinance_news.py",
                             "Per-stock news via yfinance (top 500)",
                             state, args=["--top", "500"], timeout=600)

    r["phase1"] = run_phase("phase1",
                            PIPELINE_DIR / "fetch_phase1_data.py",
                            "RBI + G-Sec + India macro",
                            state, args=["--rbi", "--gsec"], timeout=300)
    r["greeks"]   = run_phase("greeks", PIPELINE_DIR / "phase2_greeks_calculator.py",
                              "Greeks + GEX (incremental)", state,
                              args=["--daily"], timeout=600)
    r["world_bank"]  = run_phase("world_bank", PIPELINE_DIR / "update_world_bank_india.py",
                                 "World Bank India Macro", state, timeout=180)
    r["india_macro"] = run_phase("india_macro", PIPELINE_DIR / "update_macro_india_fred.py",
                                 "FRED India Macro", state, args=["--daily"], timeout=300)

    snap = MICC_DIR / "auto_update_snapshot.py"
    if snap.exists():
        r["snapshot"] = run_phase("snapshot", snap,
                                  "NSE Snapshot auto-download -> market_snapshot",
                                  state, timeout=600, cwd=MICC_DIR)
    else:
        log("auto_update_snapshot.py not in D:/MICC/", "WARN")
        r["snapshot"] = False

    if weekly:
        r["fundamentals"] = run_phase("fundamentals", PIPELINE_DIR / "update_fundamentals.py",
                                      "Fundamentals TTM", state, timeout=7200)
        r["corp_actions"] = run_phase("corp_actions", PIPELINE_DIR / "update_corporate_actions.py",
                                      "Corporate Actions", state, timeout=1800)

    run(PIPELINE_DIR / "check_db_health.py", "Health Check", timeout=60)

    if not no_engine:
        eng = MICC_DIR / "micc_engine.py"
        if eng.exists():
            ok = run_phase("engine", eng,
                           "MICC Engine (all agents + Telegram)",
                           state, args=["7", "--send"],
                           timeout=900, cwd=MICC_DIR)
            r["engine"] = ok
            if not ok:
                today_str = datetime.now().strftime("%d %b %Y")
                send_fallback_telegram(
                    f"MICC Pipeline Alert {today_str}: "
                    f"Engine failed. Failed phases: {str(state['failed'])}"
                )
        else:
            log("micc_engine.py not found", "WARN")
            r["engine"] = False

    passed = sum(1 for v in r.values() if v)
    failed = sum(1 for v in r.values() if not v)
    print()
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    for name, ok in r.items():
        print(f"  [{'OK  ' if ok else 'FAIL'}]  {name}")
    print()
    log(f"Passed: {passed}  |  Failed: {failed}")
    print("=" * 65)
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
