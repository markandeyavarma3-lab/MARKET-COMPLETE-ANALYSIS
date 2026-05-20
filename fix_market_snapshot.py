"""
fix_market_snapshot.py
=======================
AGENT ROOM DIAGNOSIS:
  Agent 1 (Data Analyst): The CSV column for "Change (%)" is different in newer files.
                           The INSERT fails because :change is NULL but the DB column
                           may have a NOT NULL constraint, OR SQLite named binding
                           requires ALL params to be present.
  Agent 2 (DBA):          Use executemany with only the columns we HAVE data for,
                           not a fixed INSERT with all columns including :change.
  Agent 3 (Debug):        Probe the actual CSV headers from the failing files.
  Agent 4 (Fix):          Write a robust insert that uses only available columns,
                           with change defaulting to NULL if missing.

ROOT CAUSES FOUND:
  1. Newer NSE CSVs use "% Chg" instead of "Change (%)" for the change column.
  2. The INSERT statement requires :change (named parameter) but if it's missing
     from the dict, sqlite3 raises "did not supply a value for binding parameter".
  3. Fix: probe actual headers, map all variants, default missing cols to None.

Run from D:/MICC/:
  py fix_market_snapshot.py
"""

import csv
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH      = Path(r"D:\marketDB\db\market.db")
SNAPSHOT_DIR = Path(r"C:\Users\marka\OneDrive\Desktop\NSE Data\NSE OTHER DATA\daily snapshot")


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN", "INFO": "INFO"}.get(level, "INFO")
    print(f"[{tag}]  {msg}", flush=True)


def probe_csv_headers():
    """Print actual headers from all CSV files to understand column variance."""
    print()
    print("=" * 60)
    print("  PROBING CSV HEADERS")
    print("=" * 60)
    all_headers = {}
    for f in sorted(SNAPSHOT_DIR.glob("ind_close_all_*.csv")):
        try:
            with open(f, encoding="utf-8-sig", errors="replace") as fh:
                reader = csv.DictReader(fh)
                headers = tuple(h.strip() for h in (reader.fieldnames or []))
                key = headers
                if key not in all_headers:
                    all_headers[key] = []
                all_headers[key].append(f.name)
        except Exception as e:
            log(f"Could not read {f.name}: {e}", "WARN")

    print(f"\n  Found {len(all_headers)} distinct header format(s):\n")
    for i, (headers, files) in enumerate(all_headers.items(), 1):
        print(f"  Format {i} (used by {len(files)} files):")
        print(f"    Headers: {list(headers)}")
        print(f"    Example files: {files[:3]}")
        print()
    return all_headers


def parse_date_from_filename(filename: str):
    m = re.search(r"(\d{8})", filename)
    if not m:
        return None
    digits = m.group(1)
    try:
        dd, mm, yyyy = digits[:2], digits[2:4], digits[4:]
        return datetime(int(yyyy), int(mm), int(dd)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalise_header(h: str) -> str:
    """Normalise a CSV header to lowercase stripped."""
    return h.strip().lower()


# Complete column mapping — ALL known NSE header variants
COL_MAP = {
    # Index name
    "index name":                "index_name",
    # Open
    "open index value":          "open_index_value",
    "open":                      "open_index_value",
    # High
    "high index value":          "high_index_value",
    "high":                      "high_index_value",
    # Low
    "low index value":           "low_index_value",
    "low":                       "low_index_value",
    # Close
    "closing index value":       "closing_index_value",
    "close":                     "closing_index_value",
    "closing":                   "closing_index_value",
    # Points change
    "points change":             "points_change",
    "points chg":                "points_change",
    "pointschange":              "points_change",
    # Percentage change — ALL KNOWN VARIANTS
    "change (%)":                "change",
    "change(%)":                 "change",
    "% chg":                     "change",
    "%chg":                      "change",
    "change %":                  "change",
    "pct change":                "change",
    "pct chg":                   "change",
    "change":                    "change",
    "chng (%)":                  "change",
    "chng(%)":                   "change",
    "% change":                  "change",
    # Volume
    "volume":                    "volume",
    # Turnover
    "turnover (rs. cr.)":        "turnover_rs_cr",
    "turnover (rs cr)":          "turnover_rs_cr",
    "turnover(rs cr)":           "turnover_rs_cr",
    "turnover":                  "turnover_rs_cr",
    # PE
    "p/e":                       "pe",
    "pe":                        "pe",
    # PB
    "p/b":                       "pb",
    "pb":                        "pb",
    # Div yield
    "div yield":                 "div_yield",
    "div. yield":                "div_yield",
    "dividend yield":            "div_yield",
}


def parse_csv_robust(filepath: Path, date_str: str) -> list:
    """Parse CSV with flexible column mapping. Never fails on missing columns."""
    rows = []
    try:
        with open(filepath, encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                # Normalise all keys
                row = {normalise_header(k): (v.strip() if v else "") for k, v in raw.items() if k}

                index_name = row.get("index name", "").strip()
                if not index_name or index_name.lower() == "index name":
                    continue

                # Build mapped row — only include columns we can find
                mapped = {
                    "index_name":   index_name,
                    "date":         date_str,
                    "index_date":   date_str,
                    "ingest_date":  datetime.now().strftime("%Y-%m-%d"),
                    "source_file":  filepath.name,
                    # Default all optional cols to None
                    "open_index_value":    None,
                    "high_index_value":    None,
                    "low_index_value":     None,
                    "closing_index_value": None,
                    "points_change":       None,
                    "change":              None,
                    "volume":              None,
                    "turnover_rs_cr":      None,
                    "pe":                  None,
                    "pb":                  None,
                    "div_yield":           None,
                }

                # Fill from CSV using all column name variants
                for csv_col, val in row.items():
                    db_col = COL_MAP.get(csv_col)
                    if db_col and db_col != "index_name":
                        v = val.strip() if val else None
                        if v in ("", "-", "NA", "N/A", "nan", "NaN"):
                            v = None
                        mapped[db_col] = v

                rows.append(mapped)

    except Exception as e:
        log(f"Error parsing {filepath.name}: {e}", "FAIL")
    return rows


def insert_rows_robust(conn, rows: list) -> int:
    """Insert rows using only the columns we have. change defaults to None."""
    if not rows:
        return 0
    inserted = 0
    for row in rows:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_snapshot
                  (index_name, index_date,
                   open_index_value, high_index_value, low_index_value, closing_index_value,
                   points_change, change,
                   volume, turnover_rs_cr, pe, pb, div_yield,
                   date, ingest_date, source_file)
                VALUES
                  (:index_name, :index_date,
                   :open_index_value, :high_index_value, :low_index_value, :closing_index_value,
                   :points_change, :change,
                   :volume, :turnover_rs_cr, :pe, :pb, :div_yield,
                   :date, :ingest_date, :source_file)
            """, row)
            inserted += conn.execute("SELECT changes()").fetchone()[0]
        except Exception as e:
            log(f"Insert error {row.get('index_name','?')} {row.get('date','?')}: {e}", "WARN")
    return inserted


def main():
    print()
    print("=" * 60)
    print("  FIX MARKET SNAPSHOT — ROBUST CSV INGESTION")
    print("=" * 60)

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL"); sys.exit(1)
    if not SNAPSHOT_DIR.exists():
        log(f"Snapshot dir not found: {SNAPSHOT_DIR}", "FAIL"); sys.exit(1)

    # Step 1: probe headers so we see exactly what columns are in the CSVs
    probe_csv_headers()

    # Step 2: connect DB
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Step 3: get existing dates
    existing = {r[0] for r in conn.execute("SELECT DISTINCT date FROM market_snapshot").fetchall()}
    latest_before = max(existing) if existing else "none"
    log(f"Existing dates: {len(existing)}  |  latest before: {latest_before}")

    # Step 4: process all CSV files
    csv_files = sorted(SNAPSHOT_DIR.glob("ind_close_all_*.csv"))
    log(f"CSV files found: {len(csv_files)}")
    print()

    total_new = 0
    total_inserted = 0
    total_skipped = 0
    errors = []

    for csv_path in csv_files:
        date_str = parse_date_from_filename(csv_path.name)
        if not date_str:
            log(f"Cannot parse date: {csv_path.name}", "WARN"); continue

        if date_str in existing:
            total_skipped += 1
            continue

        rows = parse_csv_robust(csv_path, date_str)
        if not rows:
            log(f"No rows from {csv_path.name}", "WARN")
            errors.append(csv_path.name)
            continue

        n = insert_rows_robust(conn, rows)
        conn.commit()
        total_inserted += n
        total_new += 1
        existing.add(date_str)

        if n > 0:
            log(f"Inserted {n:3d} rows for {date_str}  ({csv_path.name})", "OK")
        else:
            log(f"0 rows inserted for {date_str} — may already exist (INSERT OR IGNORE)", "WARN")

    conn.close()

    # Step 5: verify new latest date
    conn2 = sqlite3.connect(str(DB_PATH), timeout=10)
    new_latest = conn2.execute("SELECT MAX(date) FROM market_snapshot").fetchone()[0]
    all_dates = sorted([r[0] for r in conn2.execute(
        "SELECT DISTINCT date FROM market_snapshot ORDER BY date DESC LIMIT 10"
    ).fetchall()])
    conn2.close()

    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print()
    log(f"New dates added     : {total_new}")
    log(f"Total rows inserted : {total_inserted}")
    log(f"Dates skipped       : {total_skipped}")
    log(f"Latest date before  : {latest_before}")
    log(f"Latest date NOW     : {new_latest}", "OK")
    print()
    print(f"  Most recent dates in market_snapshot:")
    for d in sorted(all_dates)[-8:]:
        print(f"    {d}")
    print()

    if new_latest and new_latest > latest_before:
        print("  SUCCESS — market_snapshot updated with new dates!")
        print()
        print("  Now run the engine with fresh data:")
        print("    cd D:\\MICC")
        print("    py micc_engine.py 7 --send")
        print()
        print("  The engine will now use dates up to:", new_latest)
    else:
        print("  No new dates were added.")
        print()
        if errors:
            print(f"  {len(errors)} files had issues:")
            for e in errors:
                print(f"    {e}")
        print()
        print("  Check the PROBING section above for actual CSV column names.")
        print("  If headers differ from expected, update COL_MAP in this script.")
    print()


if __name__ == "__main__":
    main()
