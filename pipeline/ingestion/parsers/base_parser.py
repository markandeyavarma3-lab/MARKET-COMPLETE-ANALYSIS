# -*- coding: utf-8 -*-
"""
MICC - Base Parser
All parsers inherit from BaseParser and implement parse().
This ensures consistent interface, date handling, and column cleaning.
"""

import re
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from agents.shared.logger import get_logger

log = get_logger("pipeline.parsers.base")


class BaseParser(ABC):
    """
    Abstract base parser. Every file-type parser extends this.

    Subclasses must implement:
        parse(path, category=None) → pd.DataFrame

    Subclasses get for free:
        _read_csv()         - safe CSV reading with encoding fallback
        _clean_columns()    - strip whitespace, normalize column names
        _parse_date()       - handle NSE date formats robustly
        _add_metadata()     - ingest_date, source_file columns
    """

    # NSE uses multiple date formats - we try them all
    NSE_DATE_FORMATS = [
        "%d-%b-%Y",   # 01-Jan-2025  ← most common in bhavcopy
        "%d-%m-%Y",   # 01-01-2025
        "%Y-%m-%d",   # 2025-01-01   ← ISO
        "%d/%m/%Y",   # 01/01/2025
        "%b %d, %Y",  # Jan 01, 2025
    ]

    @abstractmethod
    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        """Parse CSV at path and return a clean DataFrame."""
        ...

    # -----------------------------------------------------------------
    # PROTECTED HELPERS - available to all subclasses
    # -----------------------------------------------------------------

    def _read_csv(
        self,
        path: Path,
        skip_rows: int = 0,
        encoding: str = "utf-8",
    ) -> pd.DataFrame:
        """
        Read a CSV with automatic encoding fallback.
        NSE files are sometimes latin-1, sometimes utf-8.
        """
        encodings = [encoding, "utf-8", "latin-1", "cp1252"]
        last_error = None

        for enc in encodings:
            try:
                df = pd.read_csv(
                    path,
                    skiprows=skip_rows,
                    encoding=enc,
                    low_memory=False,
                    on_bad_lines="warn",
                )
                log.debug(f"Read {path.name} with encoding={enc}: {len(df):,} rows")
                return df
            except (UnicodeDecodeError, pd.errors.ParserError) as e:
                last_error = e
                continue

        raise ValueError(f"Could not read {path.name} with any encoding. Last error: {last_error}")

    def _clean_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names:
          - Strip whitespace
          - Lowercase
          - Replace spaces/hyphens with underscores
          - Remove special characters
        """
        df.columns = [
            re.sub(r"[^a-z0-9_]", "", col.strip().lower().replace(" ", "_").replace("-", "_"))
            for col in df.columns
        ]
        return df

    def _parse_date_column(self, series: pd.Series) -> pd.Series:
        """
        Try multiple date formats on a Series until one works.
        Returns ISO format strings (YYYY-MM-DD) for SQLite compatibility.
        """
        for fmt in self.NSE_DATE_FORMATS:
            try:
                parsed = pd.to_datetime(series, format=fmt, errors="raise")
                return parsed.dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue

        # Last resort: let pandas infer
        try:
            parsed = pd.to_datetime(series, infer_datetime_format=True, errors="coerce")
            return parsed.dt.strftime("%Y-%m-%d")
        except Exception:
            log.warning(f"Could not parse date column: {series.name} - keeping raw values")
            return series

    def _add_metadata(
        self,
        df: pd.DataFrame,
        source_path: Path,
        trade_date: str | None = None,
    ) -> pd.DataFrame:
        """
        Add audit columns to every row:
          - ingest_date  : when MICC ingested this file (today)
          - source_file  : original filename for traceability
          - trade_date   : the market date this data represents
        """
        from datetime import date
        df["ingest_date"]  = date.today().isoformat()
        df["source_file"]  = source_path.name
        if trade_date:
            df["trade_date"] = trade_date
        return df

    def _extract_date_from_filename(self, filename: str) -> str | None:
        """
        Try to extract a date from NSE filenames.
        e.g. "BhavCopy_BSE_CM_01012025.csv" → "2025-01-01"
             "ind_close_all_01012025.csv"   → "2025-01-01"
        """
        # Pattern: 8 consecutive digits
        matches = re.findall(r"\d{8}", filename)
        for m in matches:
            for fmt in ["%d%m%Y", "%Y%m%d"]:
                try:
                    from datetime import datetime
                    dt = datetime.strptime(m, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    def _coerce_numeric(self, df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        """
        Force listed columns to numeric, setting unparseable values to NaN.
        Removes commas and currency symbols first.
        """
        for col in columns:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(",", "", regex=False)
                    .str.replace("₹", "", regex=False)
                    .str.replace("$", "", regex=False)
                    .str.strip()
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
