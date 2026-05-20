# -*- coding: utf-8 -*-
"""
fix_parquet_update.py
======================
Diagnoses why update_parquet_from_delivery.py updated 0 symbols,
then applies the correct fix.

The problem:
  get_parquet_latest_date() reads the 'date' column from parquet.
  Dates are stored as "01-Apr-2026" (DD-Mon-YYYY string).
  pd.to_datetime("01-Apr-2026", dayfirst=True) should work BUT
  if it fails, returns NaT and max() returns NaT which strftime() fails.
  So parquet_latest becomes "1900-01-01" for every symbol.
  Then "1900-01-01" < "2026-05-12" so it SHOULD fetch new rows.
  But get_delivery_for_symbol() with after_date="1900-01-01" returns
  ALL rows for the symbol. Then build_parquet_rows() runs. Then
  append_to_parquet() checks existing_dates which are "01-Apr-2026" strings.
  The new rows have dates also as "01-Apr-2026" format.
  So existing_dates check removes all "new" rows as duplicates -> 0 appended.

Root fix:
  When reading parquet latest date, convert DD-Mon-YYYY to ISO correctly.
  When building new rows from delivery (which has ISO dates like "2026-05-12"),
  convert them to DD-Mon-YYYY to match. Then deduplicate on ISO date, not display.

Run from D:/MICC/:
  py fix_parquet_update.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH      = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{tag}]  {msg}", flush=True)


# =============================================================================
# STEP 1: Full diagnostic
# =============================================================================
print()
print("=" * 60)
print("  DIAGNOSTIC: Why 0 symbols updated")
print("=" * 60)
print()

# Check RELIANCE parquet
sym  = "RELIANCE"
year = 2026
folder = PARQUET_ROOT / sym

for pf_name in [f"{sym}_{year}.parquet", f"{year}.parquet"]:
    pf = folder / pf_name
    if pf.exists():
        log(f"Reading {pf_name}...")
        df = pd.read_parquet(pf)
        log(f"Columns: {list(df.columns)}")
        log(f"Shape: {df.shape}")
        log(f"'date' dtype: {df['date'].dtype}")
        log(f"First 3 date values: {df['date'].head(3).tolist()}")
        log(f"Last 3 date values: {df['date'].tail(3).tolist()}")

        # Test date conversion
        sample = df['date'].iloc[-1]
        log(f"Sample date value: '{sample}'  type: {type(sample)}")

        # Try to_datetime
        try:
            converted = pd.to_datetime(sample, dayfirst=True)
            log(f"pd.to_datetime('{sample}', dayfirst=True) = {converted}", "OK")
        except Exception as e:
            log(f"to_datetime failed: {e}", "FAIL")

        # Full column conversion
        dates_parsed = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
        nulls = dates_parsed.isna().sum()
        log(f"Null dates after conversion: {nulls}/{len(df)}")
        if nulls < len(df):
            log(f"Max date (ISO): {dates_parsed.max().strftime('%Y-%m-%d')}", "OK")
        else:
            log("ALL dates are NaT after conversion!", "FAIL")
        break

print()

# Check stock_delivery for RELIANCE
conn = sqlite3.connect(str(DB_PATH), timeout=30)
delivery_cols = [r[1] for r in conn.execute("PRAGMA table_info(stock_delivery)").fetchall()]
log(f"stock_delivery columns: {delivery_cols}")

df_del = pd.read_sql(
    "SELECT * FROM stock_delivery WHERE symbol='RELIANCE' ORDER BY date DESC LIMIT 5",
    conn
)
log(f"stock_delivery RELIANCE last 5 rows:")
print(df_del.to_string())
print()

delivery_max = conn.execute("SELECT MAX(date) FROM stock_delivery").fetchone()[0]
log(f"stock_delivery MAX date: {delivery_max}")
conn.close()


# =============================================================================
# STEP 2: Write the corrected update script
# =============================================================================
print()
print("=" * 60)
print("  Writing corrected update_parquet_from_delivery.py")
print("=" * 60)

SCRIPT = Path(r"D:\MICC\update_parquet_from_delivery.py")

CONTENT = r'''# -*- coding: utf-8 -*-
"""
update_parquet_from_delivery.py  v2
=====================================
Appends missing recent rows from stock_delivery into parquet files.
Correctly handles DD-Mon-YYYY date format in parquet.

Run from D:/MICC/:
  py update_parquet_from_delivery.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH      = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN",
           "SKIP": "SKIP"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def parse_parquet_dates(series: pd.Series) -> pd.Series:
    """Parse dates from parquet - handles DD-Mon-YYYY and ISO formats."""
    # Try dayfirst (DD-Mon-YYYY like "01-Apr-2026")
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    # If too many NaT, try other formats
    if parsed.isna().sum() > len(series) * 0.5:
        parsed = pd.to_datetime(series, errors="coerce")
    return parsed


def get_parquet_max_iso(folder: Path, symbol: str, year: int):
    """Return (filepath, max_date_iso) or (None, '1900-01-01')."""
    for pf in [folder / f"{symbol}_{year}.parquet",
               folder / f"{year}.parquet"]:
        if pf.exists():
            try:
                df = pd.read_parquet(pf, columns=["date"])
                if df.empty:
                    return pf, "1900-01-01"
                dates = parse_parquet_dates(df["date"]).dropna()
                if dates.empty:
                    return pf, "1900-01-01"
                return pf, dates.max().strftime("%Y-%m-%d")
            except Exception:
                return pf, "1900-01-01"
    return None, "1900-01-01"


def iso_to_display(iso_date: str) -> str:
    """Convert 2026-05-12 -> 12-May-2026 to match parquet format."""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d-%b-%Y")
    except Exception:
        return iso_date


def build_rows_from_delivery(df_del: pd.DataFrame) -> pd.DataFrame:
    """Build parquet-schema rows from stock_delivery DataFrame."""
    if df_del.empty:
        return pd.DataFrame()

    cols = list(df_del.columns)
    out  = pd.DataFrame()

    out["symbol"]      = df_del["symbol"]
    out["series"]      = "EQ"
    out["date1"]       = None
    out["prev_close"]  = None

    # Price
    for src, dst in [("open","open"),("high","high"),("low","low"),
                     ("close","last_price"),("close","close")]:
        if src in cols:
            out[dst] = pd.to_numeric(df_del[src], errors="coerce")
        else:
            out[dst] = None

    out["avg_price"]   = None
    out["trade_count"] = 0

    # Volume
    vol = df_del.get("volume", df_del.get("total_traded_qty"))
    out["volume"] = pd.to_numeric(vol, errors="coerce").fillna(0).astype("int64") \
                    if vol is not None else 0

    # Turnover
    turn = df_del.get("turnover")
    out["turnover"] = pd.to_numeric(turn, errors="coerce") if turn is not None else None

    # Delivery
    dqty = df_del.get("delivery_qty")
    out["delivery_qty"] = pd.to_numeric(dqty, errors="coerce") if dqty is not None else None

    dpct = df_del.get("delivery_pct", df_del.get("delivery_percent"))
    out["delivery_pct"] = pd.to_numeric(dpct, errors="coerce") if dpct is not None else None

    # Date — convert ISO "2026-05-12" to display "12-May-2026"
    out["date"]       = df_del["date"].apply(iso_to_display)
    out["trade_date"] = out["date"]

    # Drop rows with no close price
    out = out.dropna(subset=["close"])
    return out.reset_index(drop=True)


def append_to_parquet(pf: Path, new_rows: pd.DataFrame, symbol: str) -> int:
    """Append new_rows to parquet file, deduplicating on ISO date."""
    if new_rows.empty:
        return 0

    if pf.exists():
        try:
            existing = pd.read_parquet(pf)
            # Convert existing dates to ISO for dedup
            ex_dates_iso = parse_parquet_dates(
                existing["date"] if "date" in existing.columns
                else pd.Series([], dtype=str)
            ).dt.strftime("%Y-%m-%d").dropna().tolist()

            # Convert new rows dates to ISO for dedup
            new_dates_iso = parse_parquet_dates(new_rows["date"]).dt.strftime("%Y-%m-%d").tolist()
            new_rows = new_rows[[d not in ex_dates_iso for d in new_dates_iso]]

            if new_rows.empty:
                return 0

            # Align columns
            for col in existing.columns:
                if col not in new_rows.columns:
                    new_rows[col] = None
            new_rows = new_rows[existing.columns]

            combined = pd.concat([existing, new_rows], ignore_index=True)
        except Exception as e:
            log(f"  {symbol}: read error: {e} — replacing", "WARN")
            combined = new_rows
    else:
        combined = new_rows

    try:
        combined.to_parquet(pf, index=False, compression="snappy")
        return len(new_rows)
    except Exception as e:
        log(f"  {symbol}: write error: {e}", "FAIL")
        return 0


def main():
    print()
    print("=" * 65)
    print("  UPDATE PARQUET FROM STOCK_DELIVERY  v2")
    print("=" * 65)
    print()

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL"); sys.exit(1)
    if not PARQUET_ROOT.exists():
        log(f"PARQUET_ROOT not found: {PARQUET_ROOT}", "FAIL"); sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")

    delivery_max = conn.execute("SELECT MAX(date) FROM stock_delivery").fetchone()[0]
    log(f"stock_delivery latest : {delivery_max}")

    sym_dirs = [d for d in PARQUET_ROOT.iterdir() if d.is_dir()]
    log(f"Symbol dirs           : {len(sym_dirs):,}")
    print()

    current_year = datetime.today().year
    years = [current_year, current_year - 1]

    total_updated = 0
    total_rows    = 0
    total_current = 0

    for i, sym_dir in enumerate(sym_dirs):
        sym = sym_dir.name

        for year in years:
            pf, pq_max = get_parquet_max_iso(sym_dir, sym, year)

            if pq_max >= delivery_max:
                total_current += 1
                break

            if pf is None:
                # No parquet file for this year — use year file
                pf = sym_dir / f"{sym}_{year}.parquet"

            # Fetch new delivery rows
            df_del = pd.read_sql(
                "SELECT * FROM stock_delivery WHERE symbol=? AND date>? ORDER BY date",
                conn, params=(sym, pq_max)
            )
            if df_del.empty:
                break

            new_rows = build_rows_from_delivery(df_del)
            if new_rows.empty:
                break

            n = append_to_parquet(pf, new_rows, sym)
            if n > 0:
                total_updated += 1
                total_rows    += n
                if total_updated <= 5 or total_updated % 500 == 0:
                    log(f"  {sym}: +{n} rows ({pq_max} -> {delivery_max})", "OK")
            break

        if (i + 1) % 500 == 0:
            log(f"Progress {i+1}/{len(sym_dirs)} | updated: {total_updated} | rows: {total_rows:,}")

    conn.close()

    print()
    print("=" * 65)
    print("  DONE")
    print("=" * 65)
    log(f"Symbols updated       : {total_updated:,}", "OK" if total_updated > 0 else "WARN")
    log(f"Rows appended         : {total_rows:,}", "OK" if total_rows > 0 else "WARN")
    log(f"Already current       : {total_current:,}")
    print()

    if total_updated > 0:
        print("  Parquet files updated. Run: py agent_beta.py")
    else:
        print("  No updates. Check stock_delivery has May 2026 data.")
    print()


if __name__ == "__main__":
    main()
'''

SCRIPT.write_text(CONTENT, encoding="utf-8")
log(f"Written: {SCRIPT}", "OK")

print()
print("=" * 60)
print("  DONE — now run:")
print("=" * 60)
print()
print("  py update_parquet_from_delivery.py")
print("  py agent_beta.py")
print()
