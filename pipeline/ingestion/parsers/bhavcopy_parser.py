# -*- coding: utf-8 -*-
"""
MICC - BhavCopy Parser
Handles:
  - File type 6: Full bhavcopy (all 2,386 NSE stocks)
  - File type 7: SME bhavcopy (SME exchange stocks only)

NSE Bhavcopy columns (typical):
    SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE,
    TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN,
    DELQ, DELV (delivery quantity / value - not always present)

Full Bhavcopy with delivery typically has:
    SYMBOL, SERIES, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE,
    LAST_PRICE, PREV_CLOSE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES,
    DELIV_QTY, DELIV_PER
"""

from pathlib import Path

import pandas as pd

from pipeline.ingestion.parsers.base_parser import BaseParser
from agents.shared.logger import get_logger

log = get_logger("pipeline.parsers.bhavcopy")

# All possible column name variants across NSE bhavcopy versions
BHAVCOPY_ALIASES = {
    "symbol":           "symbol",
    "series":           "series",
    "open":             "open",
    "open_price":       "open",
    "high":             "high",
    "high_price":       "high",
    "low":              "low",
    "low_price":        "low",
    "close":            "close",
    "close_price":      "close",
    "last":             "last_price",
    "last_price":       "last_price",
    "prevclose":        "prev_close",
    "prev_close":       "prev_close",
    "tottrdqty":        "volume",
    "ttl_trd_qnty":     "volume",
    "total_trade_qty":  "volume",
    "tottrdval":        "turnover",
    "turnover_lacs":    "turnover",
    "totaltrades":      "trade_count",
    "no_of_trades":     "trade_count",
    "isin":             "isin",
    "timestamp":        "date",
    "date":             "date",
    "date1":            "date",
    "deliv_qty":        "delivery_qty",
    "delq":             "delivery_qty",
    "deliv_per":        "delivery_pct",
    "delv":             "delivery_pct",
    "delivery__":       "delivery_pct",   # Some NSE versions use this
}

NUMERIC_COLS = [
    "open", "high", "low", "close", "last_price", "prev_close",
    "volume", "turnover", "trade_count", "delivery_qty", "delivery_pct",
]

# Only keep EQ series by default (filter out BE, BL, GC, IL etc.)
# Set to None to keep all series
SERIES_FILTER = ["EQ", "BE"]


class FullBhavCopyParser(BaseParser):
    """
    Parser for the full bhavcopy (file type 6).
    This is the most important daily file - covers all 2,386 stocks.

    Writes to:
      - SQLite: stock_delivery table
      - Parquet: D:/marketDB/stocks/all/<SYMBOL>/<SYMBOL>_YYYY.parquet
    """

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"FullBhavCopyParser: {path.name}")

        df = self._read_csv(path)
        log.info(f"Raw rows: {len(df):,} | columns: {list(df.columns)}")

        df = self._clean_columns(df)
        df = self._apply_bhavcopy_aliases(df)

        # -- Date ------------------------------------------------------
        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            trade_date = self._extract_date_from_filename(path.name)
            df["date"] = trade_date or __import__("datetime").date.today().isoformat()

        # -- Filter to EQ + BE series only (main board stocks) ---------
        if "series" in df.columns and SERIES_FILTER:
            before = len(df)
            df = df[df["series"].str.strip().isin(SERIES_FILTER)]
            log.info(f"Series filter ({SERIES_FILTER}): {before:,} → {len(df):,} rows")

        # -- Numeric coercion -------------------------------------------
        df = self._coerce_numeric(df, NUMERIC_COLS)

        # -- Delivery % sanity check ------------------------------------
        if "delivery_pct" in df.columns:
            # Delivery % must be 0-100
            df["delivery_pct"] = df["delivery_pct"].clip(0, 100)

        # -- Metadata ---------------------------------------------------
        df = self._add_metadata(df, path, trade_date=df["date"].iloc[0] if len(df) > 0 else None)

        # -- Drop rows missing critical columns -------------------------
        df = df.dropna(subset=["symbol", "close"], how="any")
        df = df.reset_index(drop=True)

        log.info(f"FullBhavCopyParser result: {len(df):,} rows | symbols: {df['symbol'].nunique():,}")
        return df

    def _apply_bhavcopy_aliases(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {}
        for col in df.columns:
            key = col.lower().strip()
            if key in BHAVCOPY_ALIASES:
                rename_map[col] = BHAVCOPY_ALIASES[key]
        if rename_map:
            df = df.rename(columns=rename_map)
            log.debug(f"Renamed {len(rename_map)} columns")
        return df


class SMEBhavCopyParser(BaseParser):
    """
    Parser for SME bhavcopy (file type 7).
    Same format as full bhavcopy but different exchange segment.
    We tag these rows with exchange='SME' for separate analysis.
    """

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"SMEBhavCopyParser: {path.name}")

        # Reuse full bhavcopy logic
        delegate = FullBhavCopyParser()
        df = delegate.parse(path, category)

        # Tag as SME
        df["exchange_segment"] = "SME"

        # SME has different liquidity profile - track separately
        log.info(f"SMEBhavCopyParser result: {len(df):,} rows")
        return df
