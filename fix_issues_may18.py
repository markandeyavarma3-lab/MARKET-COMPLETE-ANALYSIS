"""
fix_issues_may18.py
====================
Fixes three issues identified May 18 2026:

1. morning_brief.py: Wrong global_indices_daily symbol names
   - SP500VIX -> VIX
   - INDIAVIX -> IndiaVIX
   - Also fixes the LABELS dict to match

2. run_pipeline.py: Add conviction + exit + cross-asset phases after engine

3. micc_data.py: send_telegram_chunks has misplaced docstring (after code,
   not after def) -- Python ignores it. Also adds retry logic on 429.

Run from D:/MICC:
  python fix_issues_may18.py
"""

import re
from pathlib import Path

MICC = Path(r"D:\MICC")
PIPELINE = MICC / "data_pipeline"


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def patch_file(path: Path, old: str, new: str, label: str):
    if not path.exists():
        print(f"  [SKIP] {label}: file not found: {path}")
        return False
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print(f"  [SKIP] {label}: pattern not found (already patched?)")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  [OK]   {label}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — morning_brief.py symbol names
# ─────────────────────────────────────────────────────────────────────────────

def fix_morning_brief():
    print("\n[FIX 1] morning_brief.py — global symbol names")
    path = MICC / "morning_brief.py"

    # Fix WATCH list
    patch_file(
        path,
        'WATCH = ["NIFTY50","SPX","SP500VIX","INDIAVIX","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"]',
        'WATCH = ["NIFTY50","SPX","VIX","IndiaVIX","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"]',
        "WATCH list symbols"
    )

    # Fix LABELS dict — SP500VIX -> VIX, INDIAVIX -> IndiaVIX
    patch_file(
        path,
        '"SP500VIX":"VIX      ",\n            "INDIAVIX":"India VIX"',
        '"VIX":"VIX      ",\n            "IndiaVIX":"India VIX"',
        "LABELS dict keys"
    )

    # Also check for single-line version
    patch_file(
        path,
        '"SP500VIX":"VIX      ","INDIAVIX":"India VIX"',
        '"VIX":"VIX      ","IndiaVIX":"India VIX"',
        "LABELS dict keys (single-line variant)"
    )

    # Fix the for loop — snap.items() iterates in insertion order, but the
    # dict lookup now uses correct keys. Verify LABELS covers all WATCH items.
    # Rewrite the entire get_global_snapshot block to be order-preserving.
    path2 = path
    text = path2.read_text(encoding="utf-8")

    OLD_SNAP = '''def get_global_snapshot():
    WATCH = ["NIFTY50","SPX","VIX","IndiaVIX","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"]
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        rows = conn.execute(
            "SELECT symbol,close,pct_change FROM global_indices_daily"
            " WHERE symbol IN (" + ",".join("?"*len(WATCH)) + ")"
            " AND date=(SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)",
            WATCH
        ).fetchall()
        conn.close()
        return {r[0]: (r[1], r[2]) for r in rows}
    except:
        return {}'''

    NEW_SNAP = '''def get_global_snapshot():
    WATCH = ["NIFTY50","SPX","VIX","IndiaVIX","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"]
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        placeholders = ",".join("?" * len(WATCH))
        rows = conn.execute(
            "SELECT symbol, close, pct_change FROM global_indices_daily"
            f" WHERE symbol IN ({placeholders})"
            " AND date = (SELECT MAX(date) FROM global_indices_daily"
            "             WHERE symbol = global_indices_daily.symbol)",
            WATCH
        ).fetchall()
        conn.close()
        # Preserve WATCH order for consistent brief layout
        data = {r[0]: (r[1], r[2]) for r in rows}
        return {sym: data[sym] for sym in WATCH if sym in data}
    except Exception as e:
        print(f"[brief] global_snapshot error: {e}")
        return {}'''

    if OLD_SNAP in text:
        path2.write_text(text.replace(OLD_SNAP, NEW_SNAP, 1), encoding="utf-8")
        print("  [OK]   get_global_snapshot rewritten (order-preserving + debug)")
    else:
        print("  [INFO] get_global_snapshot block not matched exactly — manual review may be needed")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2 — run_pipeline.py: add conviction + exit + cross-asset phases
# ─────────────────────────────────────────────────────────────────────────────

def fix_pipeline():
    print("\n[FIX 2] run_pipeline.py — conviction + exit + cross-asset phases")
    path = PIPELINE / "run_pipeline.py"

    OLD_PHASE9 = '''    # Phase 9 — Intelligence engine (unless --no-engine)
    if not no_engine:
        eng = MICC_DIR / "micc_engine.py"
        if eng.exists():
            r["engine"] = run(eng, "MICC Engine (all agents + Telegram)",
                              args=["7", "--send"],
                              timeout=900, cwd=MICC_DIR)
        else:
            log("micc_engine.py not found", "WARN")
            r["engine"] = False'''

    NEW_PHASE9 = '''    # Phase 9 — Intelligence engine (unless --no-engine)
    if not no_engine:
        eng = MICC_DIR / "micc_engine.py"
        if eng.exists():
            r["engine"] = run(eng, "MICC Engine (all agents + Telegram)",
                              args=["7", "--send"],
                              timeout=900, cwd=MICC_DIR)
        else:
            log("micc_engine.py not found", "WARN")
            r["engine"] = False

    # Phase 10 — Conviction + Exit signals (Phase 29-31 agents)
    if not no_engine:
        # Cross-asset signals (VIX/DXY/Gold/USDINR/SPX/US10Y)
        cross = MICC_DIR / "agent_cross_asset.py"
        if cross.exists():
            r["cross_asset"] = run(cross, "Cross-Asset Signals", timeout=120, cwd=MICC_DIR)
        else:
            log("agent_cross_asset.py not found — skipping", "WARN")

        # Exit signals (stop/target/trail alerts for portfolio)
        exit_ag = MICC_DIR / "agent_exit.py"
        if exit_ag.exists():
            r["exit_signals"] = run(exit_ag, "Exit Signals (stop/target/trail)",
                                    timeout=180, cwd=MICC_DIR)
        else:
            log("agent_exit.py not found — skipping", "WARN")

        # Conviction scores update (symbol_conviction table)
        # Conviction is rebuilt by build_phase29.py or equivalent;
        # here we just run a lightweight refresh if available.
        conv = MICC_DIR / "refresh_conviction.py"
        if conv.exists():
            r["conviction"] = run(conv, "Conviction Score Refresh", timeout=300, cwd=MICC_DIR)
        else:
            log("refresh_conviction.py not found — conviction not refreshed today", "WARN")'''

    patched = patch_file(path, OLD_PHASE9, NEW_PHASE9, "Phase 10 block")

    if not patched:
        # Try fallback — maybe the file was already partially patched
        print("  [INFO] Trying summary section as anchor...")
        text = path.read_text(encoding="utf-8")
        if "Phase 10" in text:
            print("  [SKIP] Phase 10 already present in pipeline")
        else:
            print("  [WARN] Could not auto-patch run_pipeline.py — check manually")


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 — micc_data.py: send_telegram_chunks docstring + retry on 429
# ─────────────────────────────────────────────────────────────────────────────

def fix_telegram():
    print("\n[FIX 3] micc_data.py — send_telegram_chunks + retry logic")
    path = MICC / "micc_data.py"

    # The docstring is AFTER code — Python sees it as an orphan string expression,
    # not a docstring. The function itself works fine — the bug is cosmetic.
    # Real fix: add retry on HTTP 429 (rate limited) in send_telegram().

    OLD_SEND = '''def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to configured Telegram chat. Returns True on success."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": parse_mode,
        }, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram] Send failed: {e}")
        return False'''

    NEW_SEND = '''def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to configured Telegram chat. Returns True on success.
    Retries once on HTTP 429 (rate limit) with a 3s back-off.
    Falls back to plain text if Markdown parse fails (400 error).
    """
    for attempt in range(2):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
            }
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                return True
            if resp.status_code == 429:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 3))
                print(f"[Telegram] Rate limited — waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            if resp.status_code == 400 and parse_mode != "":
                # Markdown parse error — retry as plain text
                payload["parse_mode"] = ""
                resp2 = requests.post(url, json=payload, timeout=15)
                return resp2.status_code == 200
            print(f"[Telegram] HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            print(f"[Telegram] Send failed (attempt {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(2)
    return False'''

    OLD_CHUNKS = '''def send_telegram_chunks(text, max_len: int = 4000) -> bool:
    # Defensive coerce: accept tuple/list/any -> str
    if isinstance(text, (list, tuple)):
        text = '\\n'.join(str(x) for x in text)
    elif not isinstance(text, str):
        text = str(text) if text is not None else ''
    """Split long text into Telegram chunks and send all."""
    chunks = []'''

    NEW_CHUNKS = '''def send_telegram_chunks(text, max_len: int = 4000) -> bool:
    """Split long text into Telegram chunks and send all.
    Accepts str, list, or tuple. Chunks on newline boundaries.
    """
    # Defensive coerce: accept tuple/list/any -> str
    if isinstance(text, (list, tuple)):
        text = '\\n'.join(str(x) for x in text)
    elif not isinstance(text, str):
        text = str(text) if text is not None else ''
    chunks = []'''

    patch_file(path, OLD_SEND, NEW_SEND, "send_telegram retry logic")
    patch_file(path, OLD_CHUNKS, NEW_CHUNKS, "send_telegram_chunks docstring fix")


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY — print actual symbols in global_indices_daily for cross-check
# ─────────────────────────────────────────────────────────────────────────────

def verify_symbols():
    print("\n[VERIFY] Checking global_indices_daily symbols in DB...")
    import sqlite3
    db = Path(r"D:\marketDB\db\market.db")
    if not db.exists():
        print("  [SKIP] DB not accessible from this machine")
        return
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        rows = conn.execute(
            "SELECT symbol, COUNT(*) as n, MAX(date) as latest"
            " FROM global_indices_daily GROUP BY symbol ORDER BY symbol"
        ).fetchall()
        conn.close()
        print(f"  {'Symbol':<20} {'Rows':>6}  {'Latest'}")
        print(f"  {'-'*20} {'-'*6}  {'-'*10}")
        for sym, n, lat in rows:
            # Flag symbols that morning_brief requests
            watch = ["NIFTY50","SPX","VIX","IndiaVIX","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"]
            mark = " <-- WATCH" if sym in watch else ""
            print(f"  {sym:<20} {n:>6}  {lat}{mark}")
    except Exception as e:
        print(f"  [ERROR] {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  MICC Issue Fixes — May 18 2026")
    print("=" * 60)

    fix_morning_brief()
    fix_pipeline()
    fix_telegram()
    verify_symbols()

    print("\n" + "=" * 60)
    print("  DONE")
    print("  Next steps:")
    print("  1. Run: python morning_brief.py  (test global snapshot)")
    print("  2. Check: D:/MICC/data_pipeline/run_pipeline.py Phase 10 block")
    print("  3. If Telegram still fails: check token with curl:")
    print("     curl https://api.telegram.org/bot<TOKEN>/getMe")
    print("=" * 60)
