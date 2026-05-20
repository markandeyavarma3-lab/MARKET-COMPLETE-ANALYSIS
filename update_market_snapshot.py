"""
update_market_snapshot.py
==========================
Reads NSE daily snapshot CSV files from disk and inserts them
into the market_snapshot table in market.db.

market_snapshot columns:
  index_name, index_date, open_index_value, high_index_value,
  low_index_value, closing_index_value, points_change, change,
  volume, turnover_rs_cr, pe, pb, div_yield, date, ingest_date, source_file

NSE snapshot CSVs live in:
  C:\\Users\\marka\\OneDrive\\Desktop\\NSE Data\\NSE OTHER DATA\\daily snapshot\\

File format: ind_close_all_DDMMYYYY.csv
  Columns: Index Name, Open Index Value, High Index Value, Low Index Value,
           Closing Index Value, Points Change, Change (%), Volume,
           Turnover (Rs. Cr.), P/E, P/B, Div Yield

Run from D:/MICC/ or anywhere:
  py update_market_snapshot.py

The script:
  1. Scans the daily snapshot folder for all CSV files
  2. Parses dates from filenames (DDMMYYYY format)
  3. Skips dates already in market_snapshot
  4. Inserts all new rows with INSERT OR IGNORE
  5. Prints a summary of what was added
"""

import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH       = Path(r"D:\marketDB\db\market.db")
SNAPSHOT_DIR  = Path(r"C:\Users\marka\OneDrive\Desktop\NSE Data\NSE OTHER DATA\daily snapshot")

# Column name mapping: CSV header -> DB column
COL_MAP = {
    "index name":            "index_name",
    "open index value":      "open_index_value",
    "high index value":      "high_index_value",
    "low index value":       "low_index_value",
    "closing index value":   "closing_index_value",
    "points change":         "points_change",
    "change (%)":            "change",
    "change":                "change",
    "volume":                "volume",
    "turnover (rs. cr.)":    "turnover_rs_cr",
    "turnover (rs cr)":      "turnover_rs_cr",
    "p/e":                   "pe",
    "p/b":                   "pb",
    "div yield":             "div_yield",
}


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}.get(level, "INFO")
    print(f"[{tag}]  {msg}", flush=True)


def parse_date_from_filename(filename: str):
    """
    Parse DDMMYYYY from filename like 'ind_close_all_12052026.csv'
    Returns 'YYYY-MM-DD' string or None.
    """
    m = re.search(r"(\d{8})", filename)
    if not m:
        return None
    digits = m.group(1)
    try:
        dd, mm, yyyy = digits[:2], digits[2:4], digits[4:]
        dt = datetime(int(yyyy), int(mm), int(dd))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def get_existing_dates(conn):
    """Get set of dates already in market_snapshot."""
    rows = conn.execute("SELECT DISTINCT date FROM market_snapshot").fetchall()
    return {r[0] for r in rows}


def parse_csv(filepath: Path, date_str: str):
    """
    Parse one NSE snapshot CSV. Returns list of row dicts for DB insert.
    """
    rows = []
    try:
        import csv
        with open(filepath, encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                # Normalise column names
                row = {k.strip().lower(): v.strip() for k, v in raw.items() if k}

                index_name = row.get("index name", "").strip()
                if not index_name or index_name.lower() in ("", "index name"):
                    continue

                # Map columns
                mapped = {"index_name": index_name, "date": date_str}
                for csv_col, db_col in COL_MAP.items():
                    if csv_col in row and db_col != "index_name":
                        val = row[csv_col].strip()
                        mapped[db_col] = val if val not in ("", "-", "NA", "N/A") else None

                # index_date = same as date
                mapped["index_date"] = date_str
                mapped["ingest_date"] = datetime.now().strftime("%Y-%m-%d")
                mapped["source_file"] = filepath.name

                rows.append(mapped)
    except Exception as e:
        log(f"Error parsing {filepath.name}: {e}", "FAIL")
    return rows


def insert_rows(conn, rows: list):
    """Insert rows into market_snapshot with INSERT OR IGNORE."""
    if not rows:
        return 0

    inserted = 0
    for row in rows:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_snapshot
                  (index_name, index_date, open_index_value, high_index_value,
                   low_index_value, closing_index_value, points_change, change,
                   volume, turnover_rs_cr, pe, pb, div_yield,
                   date, ingest_date, source_file)
                VALUES
                  (:index_name, :index_date, :open_index_value, :high_index_value,
                   :low_index_value, :closing_index_value, :points_change, :change,
                   :volume, :turnover_rs_cr, :pe, :pb, :div_yield,
                   :date, :ingest_date, :source_file)
            """, row)
            inserted += conn.execute("SELECT changes()").fetchone()[0]
        except Exception as e:
            log(f"Insert error for {row.get('index_name','?')} {row.get('date','?')}: {e}", "WARN")
    return inserted


def main():
    print()
    print("=" * 60)
    print("  UPDATE MARKET SNAPSHOT FROM NSE DAILY SNAPSHOT FILES")
    print("=" * 60)
    print()

    # -- Check paths
    if not DB_PATH.exists():
        log(f"Database not found: {DB_PATH}", "FAIL")
        sys.exit(1)

    if not SNAPSHOT_DIR.exists():
        log(f"Snapshot folder not found: {SNAPSHOT_DIR}", "FAIL")
        log("Looking for alternative locations...", "WARN")
        # Try alternative paths
        alternatives = [
            Path(r"C:\Users\marka\OneDrive\Desktop\NSE Data\NSE OTHER DATA\daily snapshot"),
            Path(r"D:\NSE Data\NSE OTHER DATA\daily snapshot"),
            Path(r"C:\Users\marka\Desktop\NSE Data\NSE OTHER DATA\daily snapshot"),
        ]
        found = None
        for alt in alternatives:
            if alt.exists():
                found = alt
                break
        if found:
            log(f"Found at: {found}", "OK")
            snapshot_dir = found
        else:
            log("Could not find NSE snapshot folder.", "FAIL")
            log("Please check the path and update SNAPSHOT_DIR in this script.", "WARN")
            log(f"Expected: {SNAPSHOT_DIR}", "WARN")
            sys.exit(1)
    else:
        snapshot_dir = SNAPSHOT_DIR

    log(f"Database  : {DB_PATH}")
    log(f"Snapshots : {snapshot_dir}")

    # -- Find all CSV files
    csv_files = sorted(snapshot_dir.glob("ind_close_all_*.csv"))
    if not csv_files:
        # Also try other patterns
        csv_files = sorted(snapshot_dir.glob("*.csv"))

    log(f"Found {len(csv_files)} CSV files in snapshot folder")
    if not csv_files:
        log("No CSV files found.", "FAIL")
        sys.exit(1)

    # -- Connect DB
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # -- Get existing dates
    existing = get_existing_dates(conn)
    log(f"Existing dates in market_snapshot: {len(existing)} (latest: {max(existing) if existing else 'none'})")

    # -- Process each file
    total_inserted = 0
    total_skipped  = 0
    total_new      = 0
    failed_files   = []

    for csv_path in csv_files:
        date_str = parse_date_from_filename(csv_path.name)
        if not date_str:
            log(f"Cannot parse date from: {csv_path.name}", "WARN")
            continue

        if date_str in existing:
            total_skipped += 1
            continue

        rows = parse_csv(csv_path, date_str)
        if not rows:
            log(f"No rows parsed from {csv_path.name}", "WARN")
            failed_files.append(csv_path.name)
            continue

        n = insert_rows(conn, rows)
        conn.commit()
        total_inserted += n
        total_new += 1
        log(f"Inserted {n:3d} rows for {date_str} ({csv_path.name})", "OK")
        existing.add(date_str)

    conn.close()

    # -- Summary
    print()
    print("=" * 60)
    print("  DONE")
    print("=" * 60)
    print()
    log(f"New dates processed : {total_new}")
    log(f"Rows inserted       : {total_inserted}")
    log(f"Dates already in DB : {total_skipped} (skipped)")
    if failed_files:
        log(f"Failed files        : {len(failed_files)}", "WARN")
        for f in failed_files[:5]:
            log(f"  {f}", "WARN")
    print()

    if total_inserted > 0:
        print("  market_snapshot is now updated.")
        print()
        print("  Now run the engine to get fresh analysis:")
        print("    cd D:\\MICC")
        print("    py micc_engine.py 7 --send")
    elif total_new == 0 and total_skipped > 0:
        print("  All available dates already in DB — market_snapshot is up to date.")
        print()

        # Check what the latest date is vs today
        conn2 = sqlite3.connect(str(DB_PATH), timeout=10)
        latest = conn2.execute("SELECT MAX(date) FROM market_snapshot").fetchone()[0]
        conn2.close()
        print(f"  Latest date in market_snapshot: {latest}")
        print()
        if latest and latest < "2026-05-12":
            print("  NOTE: The NSE snapshot folder may not have files for recent dates.")
            print(f"  Check: {snapshot_dir}")
            print()
            print("  List of CSV files found:")
            for f in sorted(csv_files)[-5:]:
                print(f"    {f.name}")
    print()


if __name__ == "__main__":
    main()
