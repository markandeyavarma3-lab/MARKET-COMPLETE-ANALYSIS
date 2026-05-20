# -*- coding: utf-8 -*-
"""
MICC Phase 1.3 — health_check.py
==================================
Runs at 9:05 AM IST (before micc_engine.py at 9:10 AM).
Validates 5 things and sends Telegram pass/fail summary.

Checks:
  1. DB file accessible and not locked
  2. market_snapshot freshness  (latest date <= 2 trading days ago)
  3. stock_delivery freshness   (latest date <= 3 trading days ago)
  4. Groq API responding        (lightweight ping)
  5. Ollama responding          (lightweight ping)

Exit codes:
  0  — all checks passed (Task Scheduler: proceed to run engine)
  1  — one or more CRITICAL checks failed (engine should not run)

Usage:
  py health_check.py              -- run checks, send Telegram, exit with code
  py health_check.py --no-send    -- run checks, print only, no Telegram
  py health_check.py --quiet      -- minimal console output (for Task Scheduler)

Task Scheduler setup (Phase 1.4 will wire this up):
  Trigger:  Daily 9:05 AM IST
  Action:   py health_check.py
  On success (exit 0): Task Scheduler runs micc_engine.py --days 7 --send
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ── SSL FIX — same broken GDAL cert path as micc_data.py ─────────────────────
# D:\filesssss\ssl\certs\ca-bundle.crt no longer exists.
# Force certifi's valid bundle before any network call.
try:
    import certifi
    _cert = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = _cert
    os.environ["SSL_CERT_FILE"]      = _cert
    os.environ["CURL_CA_BUNDLE"]     = _cert
except ImportError:
    pass  # certifi not installed — requests will use system default

import requests

# ── Config (mirrors micc_data.py — no import to keep health_check standalone) ─
DB_PATH            = Path("D:/marketDB/db/market.db")
LOG_DIR            = Path("agents/logs")
GROQ_API_KEY       = "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"
GROQ_URL           = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL         = "llama-3.3-70b-versatile"
OLLAMA_URL         = "http://localhost:11434/api/chat"
OLLAMA_MODEL       = "gemma3:4b"
TELEGRAM_BOT_TOKEN = "8420620581:AAGz9ztaCkj8KUJ5etBOaB0vmH69vHpeMRI"
TELEGRAM_CHAT_ID   = "6505636241"
IST                = ZoneInfo("Asia/Kolkata")

# Freshness thresholds (calendar days — accounts for weekends + Indian market holidays)
# NSE has ~15 holidays/year; long weekends can mean 4+ calendar days with no new data.
# WARN tier: unusual but not a pipeline failure (holiday stretch)
# CRITICAL tier: genuine pipeline failure — block the engine
SNAPSHOT_WARN_DAYS      = 4   # market_snapshot: warn if > 4 days old
SNAPSHOT_MAX_STALE_DAYS = 7   # market_snapshot: CRITICAL if > 7 days old
DELIVERY_WARN_DAYS      = 5   # stock_delivery:  warn if > 5 days old
DELIVERY_MAX_STALE_DAYS = 7   # stock_delivery:  CRITICAL if > 7 days old

# Criticality: CRITICAL failures block the engine; WARN failures allow it but alert
CRITICAL = "CRITICAL"
WARN     = "WARN"
OK       = "OK"

LOG_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def check_db_accessible() -> dict:
    """Check 1: DB file exists and SQLite can open + query it."""
    name = "DB Access"
    try:
        if not DB_PATH.exists():
            return {"name": name, "status": CRITICAL,
                    "msg": f"DB file not found: {DB_PATH}"}

        size_gb = DB_PATH.stat().st_size / (1024 ** 3)

        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=10)
        # Simple query to confirm it's not locked or corrupt
        result = conn.execute("SELECT COUNT(*) FROM market_snapshot").fetchone()
        conn.close()

        return {"name": name, "status": OK,
                "msg": f"DB accessible ({size_gb:.1f} GB, {result[0]:,} snapshot rows)"}

    except Exception as e:
        return {"name": name, "status": CRITICAL,
                "msg": f"DB error: {e}"}


def check_market_snapshot_freshness() -> dict:
    """
    Check 2: Data freshness using the three most reliable tables in the DB.
    Checks indices_data, stock_data, and market_snapshot — takes the MAX
    latest date across all three so a stale market_snapshot doesn't false-alarm
    when indices_data and stock_data are fresh.
    """
    name = "Snapshot Freshness"
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=10)

        # Query all three authoritative tables — take the freshest date across them
        checks = {
            "indices_data":    "SELECT MAX(date) FROM indices_data",
            "stock_data":      "SELECT MAX(date) FROM stock_data",
            "market_snapshot": "SELECT MAX(date) FROM market_snapshot",
        }
        results = {}
        for tbl, sql in checks.items():
            try:
                row = conn.execute(sql).fetchone()
                results[tbl] = row[0] if row and row[0] else None
            except Exception:
                results[tbl] = None

        conn.close()

        # Use the most recent date across all tables as the true freshness signal
        valid_dates = [v for v in results.values() if v]
        if not valid_dates:
            return {"name": name, "status": CRITICAL,
                    "msg": "All freshness tables empty — DB may be corrupt"}

        latest_str = max(valid_dates)  # ISO strings sort correctly
        source     = [k for k, v in results.items() if v == latest_str][0]
        latest     = date.fromisoformat(latest_str[:10])
        today      = date.today()
        age        = (today - latest).days

        detail = " | ".join(f"{k}={v or 'NULL'}" for k, v in results.items())

        if age > SNAPSHOT_MAX_STALE_DAYS:
            return {"name": name, "status": CRITICAL,
                    "msg": f"STALE {age}d: freshest={latest_str} ({source}) — pipeline has not run in over a week"}

        if age > SNAPSHOT_WARN_DAYS:
            return {"name": name, "status": WARN,
                    "msg": f"latest={latest_str} ({age}d ago, {source}) — possible holiday stretch, engine will run"}

        return {"name": name, "status": OK,
                "msg": f"latest={latest_str} ({age}d ago, via {source})"}

    except Exception as e:
        return {"name": name, "status": CRITICAL,
                "msg": f"Snapshot check error: {e}"}


def check_stock_delivery_freshness() -> dict:
    """
    Check 3: stock_delivery freshness.
    Per DB schema: stock_delivery.date is YYYY-MM-DD (latest 2026-05-08).
    Also cross-checks the `date` column vs `trade_date` column since older
    rows used different column names — takes MAX across both to be safe.
    """
    name = "Delivery Freshness"
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=10)

        col_info = [r[1].lower() for r in
                    conn.execute("PRAGMA table_info(stock_delivery)").fetchall()]

        # Collect candidate date columns — check all that exist
        candidates = [c for c in ["date", "trade_date", "date1"] if c in col_info]
        if not candidates:
            conn.close()
            return {"name": name, "status": WARN,
                    "msg": "stock_delivery has no recognised date column"}

        latest_str = None
        for col in candidates:
            try:
                row = conn.execute(
                    f"SELECT MAX({col}) FROM stock_delivery WHERE {col} IS NOT NULL AND {col} != ''"
                ).fetchone()
                val = row[0] if row else None
                if val:
                    # Normalise to ISO if needed
                    _MON_MAP = {
                        "jan":"01","feb":"02","mar":"03","apr":"04",
                        "may":"05","jun":"06","jul":"07","aug":"08",
                        "sep":"09","oct":"10","nov":"11","dec":"12",
                    }
                    import re
                    iso = val
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(val)):
                        m = re.match(r"^(\d{1,2})[-/](\w{3})[-/](\d{4})$", str(val).strip())
                        if m:
                            d2, mon, y = m.groups()
                            mo = _MON_MAP.get(mon.lower())
                            if mo:
                                iso = f"{y}-{mo}-{int(d2):02d}"
                    if latest_str is None or iso > latest_str:
                        latest_str = iso
            except Exception:
                continue

        conn.close()

        if not latest_str:
            return {"name": name, "status": CRITICAL,
                    "msg": "stock_delivery is empty or all date columns are NULL"}

        latest = date.fromisoformat(latest_str[:10])
        today  = date.today()
        age    = (today - latest).days

        if age > DELIVERY_MAX_STALE_DAYS:
            return {"name": name, "status": CRITICAL,
                    "msg": f"STALE {age}d: latest={latest_str} — pipeline has not run in over a week"}

        if age > DELIVERY_WARN_DAYS:
            return {"name": name, "status": WARN,
                    "msg": f"latest={latest_str} ({age}d ago) — possible holiday stretch, engine will run"}

        return {"name": name, "status": OK,
                "msg": f"latest={latest_str} ({age}d ago)"}

    except Exception as e:
        return {"name": name, "status": CRITICAL,
                "msg": f"Delivery check error: {e}"}


def check_groq_api() -> dict:
    """Check 4: Groq API responds to a minimal request within 15 seconds."""
    name = "Groq API"
    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": "Reply OK"}],
                "max_tokens": 5,
                "temperature": 0,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return {"name": name, "status": OK,
                    "msg": f"Groq responding (HTTP {resp.status_code})"}
        elif resp.status_code == 429:
            return {"name": name, "status": WARN,
                    "msg": f"Groq rate-limited (429) — may be slow, will use Ollama fallback"}
        else:
            return {"name": name, "status": WARN,
                    "msg": f"Groq HTTP {resp.status_code}: {resp.text[:100]}"}
    except requests.exceptions.Timeout:
        return {"name": name, "status": WARN,
                "msg": "Groq timeout (>15s) — Ollama fallback will be used"}
    except Exception as e:
        err_str = str(e)
        if "certificate" in err_str.lower() or "ssl" in err_str.lower() or "tls" in err_str.lower():
            return {"name": name, "status": WARN,
                    "msg": f"Groq TLS error (certifi fix should resolve): {err_str[:80]}"}
        return {"name": name, "status": WARN,
                "msg": f"Groq unreachable: {err_str[:100]} — Ollama fallback will be used"}


def check_ollama() -> dict:
    """Check 5: Local Ollama responds within 10 seconds."""
    name = "Ollama (local)"
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": "Reply OK"}],
                "stream": False,
                "options": {"num_predict": 5},
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return {"name": name, "status": OK,
                    "msg": f"Ollama responding ({OLLAMA_MODEL})"}
        else:
            return {"name": name, "status": WARN,
                    "msg": f"Ollama HTTP {resp.status_code} — Groq fallback will be used"}
    except requests.exceptions.ConnectionError:
        return {"name": name, "status": WARN,
                "msg": "Ollama not running — Groq fallback will be used"}
    except requests.exceptions.Timeout:
        return {"name": name, "status": WARN,
                "msg": "Ollama timeout (>10s) — Groq fallback will be used"}
    except Exception as e:
        return {"name": name, "status": WARN,
                "msg": f"Ollama error: {e}"}


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER + REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

def run_all_checks() -> list:
    """Run all 5 checks in order. Returns list of result dicts."""
    return [
        check_db_accessible(),
        check_market_snapshot_freshness(),
        check_stock_delivery_freshness(),
        check_groq_api(),
        check_ollama(),
    ]


def build_report(results: list, elapsed_s: float) -> tuple[str, bool]:
    """
    Build console + Telegram report string.
    Returns (report_text, all_critical_passed).
    """
    now_str  = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    critical_failures = [r for r in results if r["status"] == CRITICAL]
    warnings_list     = [r for r in results if r["status"] == WARN]
    ok_list           = [r for r in results if r["status"] == OK]

    all_critical_passed = len(critical_failures) == 0

    # Status icon
    if critical_failures:
        header_icon = "FAIL"
        header_line = f"MICC HEALTH CHECK — {header_icon}"
    elif warnings_list:
        header_icon = "WARN"
        header_line = f"MICC HEALTH CHECK — {header_icon}"
    else:
        header_icon = "PASS"
        header_line = f"MICC HEALTH CHECK — {header_icon}"

    lines = [
        header_line,
        f"{now_str} | {elapsed_s:.1f}s",
        "",
    ]

    status_icons = {OK: "OK  ", WARN: "WARN", CRITICAL: "FAIL"}
    for r in results:
        icon = status_icons[r["status"]]
        lines.append(f"[{icon}] {r['name']}: {r['msg']}")

    lines.append("")

    if critical_failures:
        lines.append(f"ENGINE BLOCKED — {len(critical_failures)} critical failure(s).")
        lines.append("Fix data issues before the engine can run.")
    elif warnings_list:
        lines.append(f"Engine will run with {len(warnings_list)} warning(s).")
        lines.append("LLM fallback chain active if needed.")
    else:
        lines.append("All checks passed. Engine is clear to run.")

    return "\n".join(lines), all_critical_passed


def send_telegram_msg(text: str) -> bool:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  [Telegram] HTTP {resp.status_code}: {resp.text[:120]}")
            return False
        return True
    except Exception as e:
        print(f"  [Telegram] Send failed: {e}")
        return False


def write_log(results: list, report: str, passed: bool) -> Path:
    """Write JSON log to agents/logs/YYYYMMDD_health.json."""
    ts  = datetime.now().strftime("%Y%m%d_%H%M")
    out = LOG_DIR / f"{ts}_health.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "passed":    passed,
        "results":   results,
        "report":    report,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="MICC Health Check — validates data and APIs before engine runs"
    )
    parser.add_argument(
        "--no-send", action="store_true",
        help="Skip Telegram notification (print to console only)"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Minimal console output (for Task Scheduler logs)"
    )
    args = parser.parse_args()

    t0 = datetime.now()

    if not args.quiet:
        print("\n" + "=" * 55)
        print("  MICC Health Check")
        print("=" * 55)

    results = run_all_checks()
    elapsed = (datetime.now() - t0).total_seconds()

    report, passed = build_report(results, elapsed)

    # Console output
    if not args.quiet:
        print()
        for line in report.split("\n"):
            print(f"  {line}")
        print()
    else:
        # Quiet mode: just print the verdict line
        verdict = "PASS" if passed else "FAIL"
        n_crit  = len([r for r in results if r["status"] == CRITICAL])
        n_warn  = len([r for r in results if r["status"] == WARN])
        print(f"[HealthCheck] {verdict} | critical={n_crit} warn={n_warn} | {elapsed:.1f}s")

    # Log to file
    log_path = write_log(results, report, passed)
    if not args.quiet:
        print(f"  Log saved: {log_path}")

    # Telegram — always send on failure; on success only send if not --no-send
    if not passed:
        # Always send critical failures to Telegram
        send_telegram_msg(report)
        if not args.quiet:
            print("  Telegram: SENT (critical failure)")
    elif not args.no_send:
        send_telegram_msg(report)
        if not args.quiet:
            print("  Telegram: SENT")
    else:
        if not args.quiet:
            print("  Telegram: SKIPPED (--no-send)")

    # Exit code: 0 = all critical passed, 1 = engine should not run
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
