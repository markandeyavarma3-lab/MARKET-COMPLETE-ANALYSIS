# -*- coding: utf-8 -*-
"""
fix_beta_complete.py
=====================
Fixes Agent Beta loading 0 symbols. Does everything in one script.

ROOT CAUSE (confirmed from diagnostics):
  Parquet 'date' column has 3 mixed formats:
    ' 01-Apr-2026'  (leading space + DD-Mon-YYYY)
    '2026-04-15'    (ISO)
    '12-May-2026'   (DD-Mon-YYYY, no space)
  pd.to_datetime(errors='coerce') fails on all non-ISO formats -> NaT
  dropna(subset=['date']) removes those rows
  Result: max date stays 2026-04-29, window May 4-12 returns 0 rows

WHAT THIS SCRIPT DOES:
  Step 1 — Rewrite all parquet files:
    - Parse every date string with explicit format list (handles all 3 variants)
    - Convert to clean ISO YYYY-MM-DD strings
    - Deduplicate on (symbol, date) keeping last row
    - Drop rows with no valid date or no close price
    - Rewrite parquet with snappy compression

  Step 2 — Patch micc_data.py load_parquet_symbol:
    - Replace generic pd.to_datetime() with robust multi-format parser
    - Ensures all date formats work forever, not just current ones

Run from D:/MICC/ ONE TIME:
  py fix_beta_complete.py

After it finishes:
  py agent_beta.py
  -> should show [DataLayer] Loaded 1600+ symbols from parquet
"""

import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
MICC_DATA    = Path(r"D:\MICC\micc_data.py")


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


# ── Date parser: handles ALL formats found in parquet ─────────────────────────

def parse_date_str(val) -> str:
    """
    Convert any date string to YYYY-MM-DD.
    Handles: ' 01-Apr-2026', '2026-04-15', '12-May-2026', '01-Apr-2026'
    Returns '' on failure.
    """
    if val is None:
        return ""
    s = str(val).strip()
    if not s or s in ("nan", "NaT", "None", "NaN"):
        return ""
    # Try each format explicitly — fastest and most reliable
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def parse_date_series(series: pd.Series) -> pd.Series:
    """Apply parse_date_str to a whole Series. Returns ISO string Series."""
    return series.apply(parse_date_str)


# ── Fix one parquet file ───────────────────────────────────────────────────────

def fix_file(pf: Path, sym: str) -> dict:
    """
    Read, fix dates, deduplicate, rewrite one parquet file.
    Returns stats dict.
    """
    stats = {"rows_in": 0, "rows_out": 0, "dupes": 0, "bad_dates": 0, "error": ""}

    try:
        df = pd.read_parquet(pf)
    except Exception as e:
        stats["error"] = str(e)
        return stats

    stats["rows_in"] = len(df)
    if len(df) == 0:
        return stats

    # ── Lowercase all column names ────────────────────────────────────────────
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

    # ── Handle date column ─────────────────────────────────────────────────────
    date_col = None
    if "date" in df.columns:
        date_col = "date"
    elif "date1" in df.columns:
        date_col = "date1"
        df.rename(columns={"date1": "date"}, inplace=True)
        date_col = "date"

    if date_col is None:
        # No date column at all — can't fix, skip
        stats["error"] = "no date column"
        return stats

    # Parse all dates to ISO
    iso_dates = parse_date_series(df["date"])
    stats["bad_dates"] = (iso_dates == "").sum()
    df["date"] = iso_dates

    # Also normalize trade_date if present
    if "trade_date" in df.columns:
        df["trade_date"] = parse_date_series(df["trade_date"])

    # ── Normalize close column ────────────────────────────────────────────────
    if "close" not in df.columns:
        for alias in ("close_price", "last_price", "ltp"):
            if alias in df.columns:
                df["close"] = df[alias]
                break

    # ── Drop bad rows ─────────────────────────────────────────────────────────
    # Keep only rows with valid ISO date
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]

    # Keep only rows with valid close price
    if "close" in df.columns:
        df = df[pd.to_numeric(df["close"], errors="coerce").notna()]

    if len(df) == 0:
        stats["rows_out"] = 0
        return stats

    # ── Deduplicate on date (keep last — most recent data wins) ───────────────
    rows_before_dedup = len(df)
    df = df.sort_values("date")
    df = df.drop_duplicates(subset=["date"], keep="last")
    stats["dupes"] = rows_before_dedup - len(df)

    stats["rows_out"] = len(df)

    # ── Rewrite ───────────────────────────────────────────────────────────────
    try:
        df.to_parquet(pf, index=False, compression="snappy")
    except Exception as e:
        stats["error"] = f"write: {e}"

    return stats


# ── Step 1: Fix all parquet files ─────────────────────────────────────────────

def step1_fix_parquets():
    print()
    print("=" * 65)
    print("  STEP 1: Rewriting parquet files with clean ISO dates")
    print("=" * 65)
    print()

    if not PARQUET_ROOT.exists():
        log(f"PARQUET_ROOT not found: {PARQUET_ROOT}", "FAIL")
        sys.exit(1)

    sym_dirs = sorted(d for d in PARQUET_ROOT.iterdir() if d.is_dir())
    log(f"Symbol dirs: {len(sym_dirs):,}")
    print()

    cur_year    = datetime.today().year
    total_files = total_fixed = total_dupes = total_bad = 0
    errors      = []

    for i, sym_dir in enumerate(sym_dirs):
        sym = sym_dir.name

        for year in [cur_year, cur_year - 1]:
            for pf_name in [f"{sym}_{year}.parquet", f"{year}.parquet"]:
                pf = sym_dir / pf_name
                if not pf.exists():
                    continue

                total_files += 1
                s = fix_file(pf, sym)

                if s["error"]:
                    errors.append(f"{sym}: {s['error']}")
                    continue

                if s["dupes"] > 0 or s["bad_dates"] > 0:
                    total_fixed += 1
                    total_dupes += s["dupes"]
                    total_bad   += s["bad_dates"]

                    if total_fixed <= 5 or total_fixed % 500 == 0:
                        log(f"  {sym}: {s['rows_in']} -> {s['rows_out']} rows  "
                            f"(dupes:{s['dupes']} bad_dates:{s['bad_dates']})", "OK")
                break  # only process one file per year

        if (i + 1) % 500 == 0:
            log(f"Progress {i+1:,}/{len(sym_dirs):,}  "
                f"fixed:{total_fixed:,}  dupes:{total_dupes:,}  bad_dates:{total_bad:,}")

    print()
    log(f"Files processed : {total_files:,}")
    log(f"Files changed   : {total_fixed:,}", "OK")
    log(f"Duplicate rows  : {total_dupes:,}", "OK")
    log(f"Bad dates fixed : {total_bad:,}",  "OK")
    if errors:
        log(f"Errors          : {len(errors)}", "WARN")
        for e in errors[:5]:
            log(f"  {e}", "WARN")


# ── Step 2: Patch micc_data.py date parsing ───────────────────────────────────

def step2_patch_micc_data():
    print()
    print("=" * 65)
    print("  STEP 2: Patch micc_data.py — robust date parsing")
    print("=" * 65)
    print()

    if not MICC_DATA.exists():
        log(f"micc_data.py not found: {MICC_DATA}", "FAIL")
        return

    content = MICC_DATA.read_text(encoding="utf-8")

    # The exact block we need to replace in load_parquet_symbol
    # Original:
    #     df["date"] = pd.to_datetime(df["date"], errors="coerce")
    # But there are two branches — the date1 branch and the else branch.
    # We replace the else branch's to_datetime call with robust parsing.

    OLD = '''        else:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")'''

    NEW = '''        else:
            # Robust multi-format date parser
            # Handles: '2026-05-12' (ISO), ' 01-Apr-2026' (display+space),
            #          '12-May-2026' (display), mixed formats in same file
            def _parse_dates(series):
                import datetime as _dt
                fmts = ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y")
                def _one(v):
                    s = str(v).strip() if v is not None else ""
                    if not s or s in ("nan", "NaT", "None"):
                        return pd.NaT
                    for fmt in fmts:
                        try:
                            return _dt.datetime.strptime(s, fmt)
                        except ValueError:
                            pass
                    return pd.NaT
                return series.apply(_one)
            df["date"] = _parse_dates(df["date"])'''

    if OLD in content:
        content = content.replace(OLD, NEW)
        MICC_DATA.write_text(content, encoding="utf-8")
        log("Patched load_parquet_symbol date parsing", "OK")
    else:
        log("Target block not found — checking current state", "WARN")
        # Show what's there
        for i, line in enumerate(content.splitlines()):
            if "pd.to_datetime(df[\"date\"]" in line or "pd.to_datetime(df['date']" in line:
                log(f"  Line {i+1}: {line.strip()}", "WARN")


# ── Step 3: Verify ────────────────────────────────────────────────────────────

def step3_verify():
    print()
    print("=" * 65)
    print("  STEP 3: Verification")
    print("=" * 65)
    print()

    cur_year = datetime.today().year
    all_ok   = True

    for sym in ["RELIANCE", "TCS", "INFY", "HDFCBANK", "WIPRO"]:
        folder = PARQUET_ROOT / sym
        pf = folder / f"{sym}_{cur_year}.parquet"
        if not pf.exists():
            pf = folder / f"{cur_year}.parquet"
        if not pf.exists():
            log(f"{sym}: no parquet file", "WARN")
            continue

        try:
            df = pd.read_parquet(pf)
            df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

            # Parse dates with the same logic as the patch
            import datetime as _dt
            fmts = ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y")
            def parse_one(v):
                s = str(v).strip() if v is not None else ""
                for fmt in fmts:
                    try:
                        return _dt.datetime.strptime(s, fmt)
                    except ValueError:
                        pass
                return pd.NaT
            df["_date"] = df["date"].apply(parse_one)

            nat_count = df["_date"].isna().sum()
            max_d     = df["_date"].max()

            sd = pd.to_datetime("2026-05-04")
            ed = pd.to_datetime("2026-05-12")
            win = df[(df["_date"] >= sd) & (df["_date"] <= ed)]

            status = "OK" if len(win) >= 5 and nat_count == 0 else "FAIL"
            if status == "FAIL":
                all_ok = False
            log(f"{sym:15} rows:{len(df):3}  NaT:{nat_count}  "
                f"max:{max_d.strftime('%Y-%m-%d') if pd.notna(max_d) else 'NaT'}  "
                f"window:{len(win)}", status)
        except Exception as e:
            log(f"{sym}: {e}", "FAIL")
            all_ok = False

    print()
    if all_ok:
        log("All symbols verified — run: py agent_beta.py", "OK")
    else:
        log("Some symbols still have issues — check output above", "WARN")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 65)
    print("  FIX BETA COMPLETE — parquet dates + micc_data patch")
    print("=" * 65)

    step1_fix_parquets()
    step2_patch_micc_data()
    step3_verify()

    print()
    print("=" * 65)
    print("  DONE")
    print("=" * 65)
    print()
    print("  Run:  py agent_beta.py")
    print("  Expected:  [DataLayer] Loaded 1600+ symbols from parquet")
    print()


if __name__ == "__main__":
    main()
