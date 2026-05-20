# -*- coding: utf-8 -*-
"""
fix_parquet_dates.py
=====================
Two problems found:
  1. New rows stored as "12-May-2026" -> pd.to_datetime() returns NaT
     FIX: Store all dates as ISO "2026-05-12" going forward
  2. Duplicate rows in parquet (same date appears 4-5 times)
     FIX: Deduplicate on (symbol, date) keeping last

This script:
  Step 1: Rewrites existing parquet files — converts all dates to ISO,
          deduplicates, keeps only clean rows with valid close price.
  Step 2: Also fixes update_parquet_from_delivery.py to store ISO dates.

Run from D:/MICC/ ONCE:
  py fix_parquet_dates.py
"""

import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def parse_any_date(val) -> str:
    """Convert any date format to YYYY-MM-DD. Returns '' on failure."""
    s = str(val).strip()
    if not s or s in ("NaT", "nan", "None"):
        return ""
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y",
                "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # pandas fallback
    try:
        parsed = pd.to_datetime(s, dayfirst=True)
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def fix_parquet_file(pf: Path, sym: str) -> tuple:
    """
    Read parquet, normalize all dates to ISO, deduplicate, rewrite.
    Returns (rows_before, rows_after, dupes_removed, bad_dates_fixed).
    """
    try:
        df = pd.read_parquet(pf)
    except Exception as e:
        return 0, 0, 0, 0

    rows_before = len(df)
    if rows_before == 0:
        return 0, 0, 0, 0

    # Step 1: Normalize date column to ISO string
    if "date" in df.columns:
        iso_dates = [parse_any_date(v) for v in df["date"].tolist()]
        bad_dates = sum(1 for d in iso_dates if not d)
        df["date"] = iso_dates
        # Also fix trade_date if present
        if "trade_date" in df.columns:
            df["trade_date"] = [parse_any_date(v) for v in df["trade_date"].tolist()]
    else:
        bad_dates = 0

    # Step 2: Drop rows with no valid date or no close
    df = df[df["date"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}")]
    if "close" in df.columns:
        df = df[pd.to_numeric(df["close"], errors="coerce").notna()]

    # Step 3: Deduplicate — keep last occurrence per date
    # (last is preferred since it has delivery data merged)
    if "date" in df.columns:
        df = df.sort_values("date")
        dupes = len(df) - len(df.drop_duplicates(subset=["date"], keep="last"))
        df = df.drop_duplicates(subset=["date"], keep="last")
    else:
        dupes = 0

    rows_after = len(df)

    # Step 4: Rewrite
    try:
        df.to_parquet(pf, index=False, compression="snappy")
    except Exception as e:
        log(f"  {sym}: write error: {e}", "WARN")
        return rows_before, rows_before, 0, bad_dates

    return rows_before, rows_after, dupes, bad_dates


def main():
    print()
    print("=" * 65)
    print("  FIX PARQUET FILES — Normalize dates to ISO + deduplicate")
    print("=" * 65)
    print()

    if not PARQUET_ROOT.exists():
        log(f"PARQUET_ROOT not found: {PARQUET_ROOT}", "FAIL")
        sys.exit(1)

    sym_dirs = [d for d in PARQUET_ROOT.iterdir() if d.is_dir()]
    log(f"Symbol dirs: {len(sym_dirs):,}")
    print()

    cur_year = datetime.today().year
    total_files    = 0
    total_dupes    = 0
    total_bad_dates = 0
    total_fixed    = 0

    for i, sym_dir in enumerate(sym_dirs):
        sym = sym_dir.name

        for year in [cur_year, cur_year - 1]:
            for pf in [sym_dir / f"{sym}_{year}.parquet",
                       sym_dir / f"{year}.parquet"]:
                if not pf.exists():
                    continue

                before, after, dupes, bad = fix_parquet_file(pf, sym)
                if before == 0:
                    continue

                total_files     += 1
                total_dupes     += dupes
                total_bad_dates += bad

                if dupes > 0 or bad > 0:
                    total_fixed += 1
                    if total_fixed <= 5 or total_fixed % 500 == 0:
                        log(f"  {sym}: {before} -> {after} rows  "
                            f"(dupes: {dupes}, bad_dates: {bad})", "OK")
                break

        if (i + 1) % 500 == 0:
            log(f"Progress {i+1:,}/{len(sym_dirs):,}  "
                f"fixed: {total_fixed:,}  dupes: {total_dupes:,}  bad_dates: {total_bad_dates:,}")

    print()
    print("=" * 65)
    print("  RESULT")
    print("=" * 65)
    log(f"Files processed   : {total_files:,}")
    log(f"Files fixed       : {total_fixed:,}", "OK" if total_fixed > 0 else "WARN")
    log(f"Duplicate rows rem: {total_dupes:,}", "OK" if total_dupes > 0 else "INFO")
    log(f"Bad dates fixed   : {total_bad_dates:,}", "OK" if total_bad_dates > 0 else "INFO")
    print()

    # Verify RELIANCE
    print("  Verifying RELIANCE post-fix...")
    rel_pf = PARQUET_ROOT / "RELIANCE" / f"RELIANCE_{cur_year}.parquet"
    if rel_pf.exists():
        df = pd.read_parquet(rel_pf)
        df["_date_parsed"] = pd.to_datetime(df["date"], errors="coerce")
        nulls = df["_date_parsed"].isna().sum()
        max_d = df["_date_parsed"].max()
        log(f"RELIANCE: {len(df)} rows, NaT dates: {nulls}, max: {max_d.date() if pd.notna(max_d) else 'NaT'}")

        sd = pd.to_datetime("2026-05-04")
        ed = pd.to_datetime("2026-05-12")
        win = df[(df["_date_parsed"] >= sd) & (df["_date_parsed"] <= ed)]
        log(f"RELIANCE window May 4-12: {len(win)} rows",
            "OK" if len(win) > 0 else "FAIL")
    print()

    # Now fix update_parquet_from_delivery.py to use ISO dates
    print("  Updating update_parquet_from_delivery.py to store ISO dates...")
    script = Path(r"D:\MICC\update_parquet_from_delivery.py")
    if script.exists():
        content = script.read_text(encoding="utf-8")
        # Change to_display() usage to store ISO directly
        old = '    o["date"]        = df["date"].apply(to_display)\n    o["trade_date"]  = o["date"]'
        new = '    o["date"]        = df["date"].astype(str)  # keep ISO YYYY-MM-DD\n    o["trade_date"]  = o["date"]'
        if old in content:
            content = content.replace(old, new)
            script.write_text(content, encoding="utf-8")
            log("update_parquet_from_delivery.py patched to store ISO dates", "OK")
        else:
            log("Could not patch update_parquet_from_delivery.py (already correct or different format)", "WARN")
    else:
        log("update_parquet_from_delivery.py not found", "WARN")

    # Also patch micc_data.py load_parquet_symbol to parse ISO dates directly
    print("  Patching micc_data.py to parse ISO date strings correctly...")
    micc_data = Path(r"D:\MICC\micc_data.py")
    if micc_data.exists():
        content = micc_data.read_text(encoding="utf-8")
        old_date = '''        else:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")'''
        new_date = '''        else:
            # Try ISO first (YYYY-MM-DD), then DD-Mon-YYYY, then generic
            if df["date"].dtype == object:
                sample = str(df["date"].dropna().iloc[0]).strip() if len(df["date"].dropna()) > 0 else ""
                if len(sample) == 10 and sample[4] == "-":
                    # ISO format YYYY-MM-DD — parse directly, no dayfirst confusion
                    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
                else:
                    # Display format DD-Mon-YYYY like "12-May-2026"
                    df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce")
                    # If still many NaT, try generic
                    if df["date"].isna().sum() > len(df) * 0.3:
                        df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
            else:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")'''
        if old_date in content:
            content = content.replace(old_date, new_date)
            micc_data.write_text(content, encoding="utf-8")
            log("micc_data.py patched — ISO-first date parsing", "OK")
        else:
            log("Could not patch micc_data.py date parsing (may already be patched)", "WARN")
    else:
        log("micc_data.py not found", "WARN")

    print()
    print("=" * 65)
    print("  ALL DONE")
    print("=" * 65)
    print()
    print("  Now run:")
    print("    py agent_beta.py")
    print()
    print("  You should see: [DataLayer] Loaded 1600+ symbols from parquet")
    print()


if __name__ == "__main__":
    main()
