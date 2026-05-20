# -*- coding: utf-8 -*-
"""
auto_update_snapshot.py
========================
Automatically downloads NSE daily index snapshot CSVs and inserts
them into market_snapshot. No manual file downloads ever needed.

Fast design:
  - First tries direct requests (no Selenium needed for archive URLs)
  - Only downloads dates that are actually missing from market_snapshot
  - Maximum 10 calendar days lookback (covers any recent missing dates)
  - Falls back to Selenium session if direct requests get blocked
  - All timeouts are generous — never blocks the pipeline

Location: D:/MICC/auto_update_snapshot.py
Run: py auto_update_snapshot.py
"""

import csv
import io
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

# ── SSL fix ───────────────────────────────────────────────────────────────────
try:
    import certifi
    _b = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = _b
    os.environ["SSL_CERT_FILE"]      = _b
    os.environ["CURL_CA_BUNDLE"]     = _b
except ImportError:
    pass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH      = Path(r"D:\marketDB\db\market.db")
SNAPSHOT_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{ddmmyyyy}.csv"

# Only look back this many calendar days — keeps it fast
LOOKBACK_DAYS = 14

# Per-request timeout (seconds)
REQUEST_TIMEOUT = 45

# Delay between consecutive downloads (seconds) — polite to NSE
INTER_DOWNLOAD_DELAY = 2.0

# NSE 2026 holidays
NSE_HOLIDAYS = {
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26",
    "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
    "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02",
    "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
}

# All known column name variants from NSE CSVs
COL_MAP = {
    "index name":              "index_name",
    "open index value":        "open_index_value",
    "open":                    "open_index_value",
    "high index value":        "high_index_value",
    "high":                    "high_index_value",
    "low index value":         "low_index_value",
    "low":                     "low_index_value",
    "closing index value":     "closing_index_value",
    "close":                   "closing_index_value",
    "closing":                 "closing_index_value",
    "points change":           "points_change",
    "points chg":              "points_change",
    "change(%)":               "change",
    "change (%)":              "change",
    "% chg":                   "change",
    "%chg":                    "change",
    "change %":                "change",
    "change":                  "change",
    "chng (%)":                "change",
    "chng(%)":                 "change",
    "% change":                "change",
    "pct change":              "change",
    "pct chg":                 "change",
    "volume":                  "volume",
    "turnover (rs. cr.)":      "turnover_rs_cr",
    "turnover (rs cr)":        "turnover_rs_cr",
    "turnover(rs cr)":         "turnover_rs_cr",
    "turnover":                "turnover_rs_cr",
    "p/e":                     "pe",
    "pe":                      "pe",
    "p/b":                     "pb",
    "pb":                      "pb",
    "div yield":               "div_yield",
    "div. yield":              "div_yield",
    "dividend yield":          "div_yield",
}


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN",
           "SKIP": "SKIP"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_trading_day(d: datetime) -> bool:
    return d.weekday() < 5 and d.strftime("%Y-%m-%d") not in NSE_HOLIDAYS


def get_missing_dates(conn) -> list:
    """Return sorted list of trading ISO dates missing from market_snapshot."""
    existing = {r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM market_snapshot"
    ).fetchall()}

    today  = datetime.today()
    result = []
    for i in range(LOOKBACK_DAYS):
        d = today - timedelta(days=i)
        # Don't include today if market hasn't closed yet (after 3:30 PM IST)
        if i == 0:
            import zoneinfo
            try:
                ist = datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
                if ist.hour < 15 or (ist.hour == 15 and ist.minute < 35):
                    continue  # market not closed yet
            except Exception:
                pass
        iso = d.strftime("%Y-%m-%d")
        if is_trading_day(d) and iso not in existing:
            result.append(iso)

    return sorted(result)


def to_ddmmyyyy(iso: str) -> str:
    return iso[8:10] + iso[5:7] + iso[:4]


# ── Session ───────────────────────────────────────────────────────────────────

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}


def make_direct_session() -> requests.Session:
    """Fast session — no Selenium. Works for NSE archive URLs most of the time."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.verify = False
    session.headers.update(NSE_HEADERS)
    return session


def warm_up_session(session: requests.Session):
    """
    Visit NSE home page briefly to pick up cookies.
    NSE archive URLs work better with cookies from the main site.
    Uses a short timeout — won't block.
    """
    try:
        log("Warming up NSE session (visiting nseindia.com)...")
        session.get("https://www.nseindia.com", timeout=20, verify=False)
        time.sleep(2)
        # Also visit archives page
        session.get("https://nsearchives.nseindia.com/", timeout=15, verify=False)
        time.sleep(1)
        log("Session warm-up done", "OK")
    except Exception as e:
        log(f"Warm-up note: {e} — continuing anyway", "WARN")


def make_selenium_session() -> requests.Session:
    """Selenium-based session as fallback if direct requests fail."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,720")
        opts.add_argument("--log-level=3")
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])

        log("Starting Chrome (Selenium fallback)...")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=opts
        )
        try:
            driver.get("https://www.nseindia.com")
            time.sleep(10)
            driver.get("https://nsearchives.nseindia.com/")
            time.sleep(3)

            session = make_direct_session()
            for c in driver.get_cookies():
                session.cookies.set(c["name"], c["value"])

            log("Selenium session ready", "OK")
            return session
        finally:
            driver.quit()

    except Exception as e:
        log(f"Selenium failed: {e} — using plain session", "WARN")
        return make_direct_session()


# ── Download ──────────────────────────────────────────────────────────────────

def download_csv(session: requests.Session, date_iso: str) -> str:
    """Download one snapshot CSV. Returns text or empty string."""
    ddmmyyyy = to_ddmmyyyy(date_iso)
    url = SNAPSHOT_URL.format(ddmmyyyy=ddmmyyyy)

    for attempt in range(1, 4):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 404:
                log(f"  {date_iso}: 404 — not yet available on NSE", "SKIP")
                return ""

            if resp.status_code == 403:
                log(f"  {date_iso}: 403 — blocked, waiting {attempt * 5}s...", "WARN")
                time.sleep(attempt * 5)
                continue

            if resp.status_code != 200:
                log(f"  {date_iso}: HTTP {resp.status_code}", "WARN")
                time.sleep(3)
                continue

            # Decode
            try:
                text = resp.content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = resp.content.decode("latin-1", errors="replace")

            # Validate it's actually a CSV (not HTML or binary)
            first = text.strip()[:200].lower()
            if "<html" in first or "<!doctype" in first:
                log(f"  {date_iso}: Got HTML (NSE blocked) — attempt {attempt}/3", "WARN")
                time.sleep(attempt * 4)
                continue

            if len(text.strip()) < 50:
                log(f"  {date_iso}: Response too short", "WARN")
                return ""

            # Check it has recognizable index data
            if "index" not in first and "nifty" not in first:
                log(f"  {date_iso}: Unrecognized format", "WARN")
                return ""

            log(f"  {date_iso}: {len(resp.content):,} bytes", "OK")
            return text

        except requests.exceptions.Timeout:
            log(f"  {date_iso}: Timeout ({REQUEST_TIMEOUT}s) — attempt {attempt}/3", "WARN")
            time.sleep(attempt * 3)
        except Exception as e:
            log(f"  {date_iso}: Error: {e}", "WARN")
            time.sleep(3)

    log(f"  {date_iso}: All attempts failed", "FAIL")
    return ""


# ── Parse + Insert ────────────────────────────────────────────────────────────

def parse_and_insert(conn, text: str, date_iso: str) -> int:
    """Parse CSV text and insert rows. Returns count inserted."""
    rows = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        for raw in reader:
            norm = {k.strip().lower(): (v.strip() if v else "") for k, v in raw.items() if k}
            name = norm.get("index name", "").strip()
            if not name or name.lower() == "index name":
                continue

            mapped = {
                "index_name": name, "date": date_iso, "index_date": date_iso,
                "ingest_date": datetime.now().strftime("%Y-%m-%d"),
                "source_file": f"auto_{to_ddmmyyyy(date_iso)}.csv",
                "open_index_value": None, "high_index_value": None,
                "low_index_value": None, "closing_index_value": None,
                "points_change": None, "change": None,
                "volume": None, "turnover_rs_cr": None,
                "pe": None, "pb": None, "div_yield": None,
            }
            for csv_col, val in norm.items():
                db_col = COL_MAP.get(csv_col)
                if db_col and db_col != "index_name":
                    v = val.strip() if val else None
                    if v in ("", "-", "NA", "N/A", "nan", "NaN"):
                        v = None
                    mapped[db_col] = v

            rows.append(mapped)
    except Exception as e:
        log(f"Parse error {date_iso}: {e}", "WARN")
        return 0

    inserted = 0
    for row in rows:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_snapshot
                  (index_name, index_date,
                   open_index_value, high_index_value, low_index_value, closing_index_value,
                   points_change, change, volume, turnover_rs_cr, pe, pb, div_yield,
                   date, ingest_date, source_file)
                VALUES
                  (:index_name, :index_date,
                   :open_index_value, :high_index_value, :low_index_value, :closing_index_value,
                   :points_change, :change, :volume, :turnover_rs_cr, :pe, :pb, :div_yield,
                   :date, :ingest_date, :source_file)
            """, row)
            inserted += conn.execute("SELECT changes()").fetchone()[0]
        except Exception as e:
            log(f"Insert error [{row.get('index_name','?')}]: {e}", "WARN")
    return inserted


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import sqlite3

    print()
    print("=" * 60)
    print("  AUTO UPDATE — NSE INDEX SNAPSHOT")
    print("=" * 60)
    print()

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL"); sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Find missing dates
    missing = get_missing_dates(conn)
    latest_before = conn.execute(
        "SELECT MAX(date) FROM market_snapshot"
    ).fetchone()[0] or "none"

    log(f"Latest in DB : {latest_before}")
    log(f"Missing dates: {len(missing)}  {missing if missing else '(none)'}")

    if not missing:
        log("market_snapshot is up to date", "OK")
        conn.close()
        print()
        return

    # Try direct session first (fast, no Chrome needed)
    log("Creating session (direct requests — no Chrome needed)...")
    session = make_direct_session()
    warm_up_session(session)
    print()

    total_inserted = 0
    success = []
    failed  = []
    needs_selenium = False

    for date_iso in missing:
        log(f"Fetching {date_iso}...")
        text = download_csv(session, date_iso)

        if not text:
            # If first failure, switch to Selenium and retry once
            if not needs_selenium and date_iso == missing[0]:
                log("Direct session failed — upgrading to Selenium session...", "WARN")
                session = make_selenium_session()
                needs_selenium = True
                text = download_csv(session, date_iso)

            if not text:
                failed.append(date_iso)
                time.sleep(INTER_DOWNLOAD_DELAY)
                continue

        n = parse_and_insert(conn, text, date_iso)
        conn.commit()
        total_inserted += n

        if n > 0:
            log(f"  Inserted {n} rows for {date_iso}", "OK")
            success.append(date_iso)
        else:
            log(f"  0 rows inserted for {date_iso} (already in DB?)", "WARN")
            success.append(date_iso)

        time.sleep(INTER_DOWNLOAD_DELAY)

    new_latest = conn.execute("SELECT MAX(date) FROM market_snapshot").fetchone()[0]
    conn.close()

    print()
    print("=" * 60)
    print("  RESULT")
    print("=" * 60)
    log(f"Was    : {latest_before}")
    log(f"Now    : {new_latest}", "OK")
    log(f"Added  : {len(success)} dates  |  {total_inserted} rows")
    if failed:
        log(f"Failed : {failed} — data may not be on NSE yet", "WARN")
    print()

    if new_latest and new_latest > latest_before:
        log("market_snapshot updated successfully", "OK")
    else:
        log("No new dates added", "WARN")
    print()


if __name__ == "__main__":
    main()
