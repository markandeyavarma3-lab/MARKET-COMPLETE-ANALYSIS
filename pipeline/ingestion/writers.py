# -*- coding: utf-8 -*-
"""
MICC - Data Writers
SQLiteWriter  → writes DataFrame to SQLite (all file types)
DualWriter    → SQLite + Parquet time-series (full bhavcopy only)
"""

from pathlib import Path

import pandas as pd

from agents.shared.logger import get_logger
from agents.shared.marketdb import db_session

log = get_logger("pipeline.writers")


class SQLiteWriter:
    """
    Writes a DataFrame to SQLite using INSERT OR REPLACE (upsert).
    Never duplicates rows for the same (symbol/index, date) key.
    """

    def write(
        self,
        df: pd.DataFrame,
        table: str,
        source_path: Path,
        category: str | None = None,
    ) -> int:
        """
        Write df to SQLite table. Returns number of rows written.
        Uses pandas to_sql with if_exists='append' - SQLite handles
        deduplication via unique constraints on the table.
        """
        log.info(f"SQLiteWriter → {table}: {len(df):,} rows")

        try:
            with db_session() as conn:
                # Use pandas built-in SQLite writer (fast, handles type mapping)
                df.to_sql(
                    name=table,
                    con=conn,
                    if_exists="append",
                    index=False,
                    method="multi",    # Batch inserts for speed
                    chunksize=1000,
                )
            log.info(f"SQLiteWriter: wrote {len(df):,} rows to {table}")
            return len(df)

        except Exception as exc:
            # If table has unique constraint violations, try upsert mode
            log.warning(f"Append failed ({exc}), trying upsert mode")
            return self._upsert_write(df, table)

    def _upsert_write(self, df: pd.DataFrame, table: str) -> int:
        """
        Fallback: INSERT OR REPLACE row by row.
        Slower but handles unique constraint violations gracefully.
        """
        cols = list(df.columns)
        placeholders = ", ".join(["?"] * len(cols))
        col_names    = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"

        rows_written = 0
        with db_session() as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute(sql, tuple(row))
                    rows_written += 1
                except Exception as e:
                    log.debug(f"Row skip: {e}")

        log.info(f"Upsert wrote {rows_written:,} rows to {table}")
        return rows_written


class DualWriter:
    """
    For full bhavcopy: writes to BOTH SQLite AND Parquet.

    SQLite: stock_delivery table (fast lookup by date/symbol)
    Parquet: D:/marketDB/stocks/all/<SYMBOL>/<SYMBOL>_YYYY.parquet
             (time-series for technical analysis, one file per year per stock)
    """

    def __init__(self):
        self._sqlite_writer = SQLiteWriter()

    def write(
        self,
        df: pd.DataFrame,
        table: str,
        source_path: Path,
        category: str | None = None,
    ) -> int:
        # -- Step 1: SQLite write ---------------------------------------
        rows = self._sqlite_writer.write(df, table, source_path)

        # -- Step 2: Parquet write --------------------------------------
        self._write_parquet(df)

        return rows

    def _write_parquet(self, df: pd.DataFrame) -> None:
        """
        Appends today's rows to per-symbol yearly Parquet files.
        File structure: D:/marketDB/stocks/all/RELIANCE/RELIANCE_2025.parquet
        """
        try:
            from config.settings import PARQUET_ROOT
        except ImportError:
            PARQUET_ROOT = Path("D:/marketDB/stocks/all")

        if "symbol" not in df.columns or "date" not in df.columns:
            log.warning("Parquet write skipped: missing symbol or date column")
            return

        # Extract year from date column
        df = df.copy()
        try:
            df["_year"] = pd.to_datetime(df["date"], errors="coerce").dt.year
        except Exception:
            log.warning("Could not extract year for Parquet partitioning")
            return

        # Define Parquet columns (OHLCV + delivery - exclude audit cols)
        parquet_cols = [c for c in df.columns if c not in (
            "ingest_date", "source_file", "_year"
        )]

        symbols_written = 0
        for symbol, group in df.groupby("symbol"):
            year = group["_year"].iloc[0]
            if pd.isna(year):
                continue

            symbol_dir = PARQUET_ROOT / str(symbol)
            symbol_dir.mkdir(parents=True, exist_ok=True)

            parquet_path = symbol_dir / f"{symbol}_{int(year)}.parquet"
            write_df = group[parquet_cols].reset_index(drop=True)

            try:
                if parquet_path.exists():
                    # Append to existing file
                    existing = pd.read_parquet(parquet_path)
                    combined = pd.concat([existing, write_df], ignore_index=True)
                    # Deduplicate by date
                    combined = combined.drop_duplicates(subset=["date"], keep="last")
                    combined = combined.sort_values("date").reset_index(drop=True)
                    combined.to_parquet(parquet_path, index=False, compression="snappy")
                else:
                    write_df.to_parquet(parquet_path, index=False, compression="snappy")

                symbols_written += 1

            except Exception as e:
                log.warning(f"Parquet write failed for {symbol}: {e}")

        log.info(f"DualWriter: Parquet updated for {symbols_written:,} symbols")
