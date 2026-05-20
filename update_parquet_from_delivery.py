# -*- coding: utf-8 -*-
"""
update_parquet_from_delivery.py  v3  FINAL
============================================
Uses stock_data (SQLite) for OHLCV + stock_delivery for delivery_pct.
Handles mixed date formats in parquet (" 01-Apr-2026" and "2026-04-15").

Run from D:/MICC/:
  py update_parquet_from_delivery.py
"""

import sqlite3, sys
from datetime import datetime
from pathlib import Path
import pandas as pd

DB_PATH      = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def to_iso(val) -> str:
    """Convert any date string to YYYY-MM-DD."""
    s = str(val).strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%b/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return ""


def to_display(iso: str) -> str:
    """2026-05-12 -> 12-May-2026"""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d-%b-%Y")
    except Exception:
        return iso


def get_pq_max(folder: Path, sym: str, year: int):
    """Return (path, max_iso_date) for the parquet file."""
    for pf in [folder / f"{sym}_{year}.parquet", folder / f"{year}.parquet"]:
        if pf.exists():
            try:
                df = pd.read_parquet(pf, columns=["date"])
                iso_list = [d for d in (to_iso(v) for v in df["date"].tolist()) if d]
                return pf, max(iso_list) if iso_list else "1900-01-01"
            except Exception:
                return pf, "1900-01-01"
    return None, "1900-01-01"


def fetch_new_rows(conn, sym: str, after: str, upto: str) -> pd.DataFrame:
    """Fetch OHLCV from stock_data + delivery_pct from stock_delivery."""
    return pd.read_sql("""
        SELECT sd.symbol, sd.date,
               sd.open, sd.high, sd.low, sd.close, sd.volume,
               del.delivery_pct, del.delivery_qty
        FROM stock_data sd
        LEFT JOIN stock_delivery del
               ON sd.symbol = del.symbol AND sd.date = del.date
        WHERE sd.symbol = ? AND sd.date > ? AND sd.date <= ?
          AND sd.close IS NOT NULL
        ORDER BY sd.date
    """, conn, params=(sym, after, upto))


def build_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Convert to parquet schema."""
    if df.empty:
        return pd.DataFrame()
    o = pd.DataFrame()
    o["symbol"]      = df["symbol"]
    o["series"]      = "EQ"
    o["date1"]       = None
    o["prev_close"]  = None
    o["open"]        = pd.to_numeric(df["open"],  errors="coerce")
    o["high"]        = pd.to_numeric(df["high"],  errors="coerce")
    o["low"]         = pd.to_numeric(df["low"],   errors="coerce")
    o["last_price"]  = pd.to_numeric(df["close"], errors="coerce")
    o["close"]       = pd.to_numeric(df["close"], errors="coerce")
    o["avg_price"]   = None
    o["volume"]      = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    o["turnover"]    = None
    o["trade_count"] = 0
    o["delivery_qty"]= pd.to_numeric(df["delivery_qty"], errors="coerce")
    o["delivery_pct"]= pd.to_numeric(df["delivery_pct"], errors="coerce")
    o["date"]        = df["date"].apply(to_display)
    o["trade_date"]  = o["date"]
    return o.dropna(subset=["close"]).reset_index(drop=True)


def append_pq(pf: Path, new: pd.DataFrame, sym: str) -> int:
    """Append new rows to parquet, skipping duplicates."""
    if new.empty:
        return 0
    if pf.exists():
        try:
            existing = pd.read_parquet(pf)
            ex_iso   = {to_iso(v) for v in existing.get("date", pd.Series()).tolist()} - {""}
            new_iso  = [to_iso(v) for v in new["date"].tolist()]
            new      = new[[d not in ex_iso for d in new_iso]]
            if new.empty:
                return 0
            # Align columns to existing schema
            for col in existing.columns:
                if col not in new.columns:
                    new = new.copy(); new[col] = None
            new      = new[list(existing.columns)]
            combined = pd.concat([existing, new], ignore_index=True)
        except Exception as e:
            log(f"  {sym}: read err: {e}", "WARN")
            combined = new
    else:
        combined = new
    try:
        combined.to_parquet(pf, index=False, compression="snappy")
        return len(new)
    except Exception as e:
        log(f"  {sym}: write err: {e}", "FAIL")
        return 0


def main():
    print()
    print("=" * 65)
    print("  UPDATE PARQUET — stock_data OHLCV + delivery_pct  v3")
    print("=" * 65)
    print()

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL"); sys.exit(1)
    if not PARQUET_ROOT.exists():
        log(f"PARQUET_ROOT not found", "FAIL"); sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")

    stock_max = conn.execute("SELECT MAX(date) FROM stock_data").fetchone()[0] or "1900-01-01"
    log(f"stock_data  latest : {stock_max}")
    log(f"stock_deliv latest : " +
        (conn.execute("SELECT MAX(date) FROM stock_delivery").fetchone()[0] or "N/A"))

    sym_dirs = [d for d in PARQUET_ROOT.iterdir() if d.is_dir()]
    log(f"Symbol dirs        : {len(sym_dirs):,}")
    print()

    if stock_max == "1900-01-01":
        log("stock_data empty — run pipeline first", "FAIL"); conn.close(); sys.exit(1)

    cur_year      = datetime.today().year
    total_updated = total_rows = total_current = 0

    for i, sym_dir in enumerate(sym_dirs):
        sym = sym_dir.name

        for year in [cur_year, cur_year - 1]:
            pf, pq_max = get_pq_max(sym_dir, sym, year)

            if pq_max >= stock_max:
                total_current += 1; break

            if pf is None:
                pf = sym_dir / f"{sym}_{year}.parquet"

            df  = fetch_new_rows(conn, sym, pq_max, stock_max)
            new = build_rows(df)
            n   = append_pq(pf, new, sym)

            if n > 0:
                total_updated += 1
                total_rows    += n
                if total_updated <= 5 or total_updated % 500 == 0:
                    log(f"  {sym}: +{n} rows  ({pq_max} -> {stock_max})", "OK")
            break

        if (i + 1) % 500 == 0:
            log(f"Progress {i+1:,}/{len(sym_dirs):,}  updated:{total_updated:,}  rows:{total_rows:,}")

    conn.close()

    print()
    print("=" * 65)
    print("  RESULT")
    print("=" * 65)
    log(f"Symbols updated   : {total_updated:,}", "OK" if total_updated > 0 else "WARN")
    log(f"Rows appended     : {total_rows:,}",    "OK" if total_rows    > 0 else "WARN")
    log(f"Already current   : {total_current:,}")
    print()

    if total_updated > 0:
        print("  Done. Now verify:")
        print("    py agent_beta.py")
    else:
        print(f"  0 symbols updated. stock_data max: {stock_max}")
        print()
        print("  Check stock_data has May 2026 rows:")
        print(r"  py -c ""import sqlite3; c=sqlite3.connect('D:/marketDB/db/market.db')"
              r"; print(c.execute('SELECT MAX(date),COUNT(*) FROM stock_data').fetchone())""")
    print()


if __name__ == "__main__":
    main()
