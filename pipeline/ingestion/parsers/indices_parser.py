# -*- coding: utf-8 -*-
"""
MICC - Indices Parser
Handles file types 1-5 (DERIVATIVES, SECTORAL, BROAD, THEMATIC, STRATEGY)
and file type 11 (NSE all indices bulk file).

NSE indices CSVs typically look like:
    Index Name,Open,High,Low,Close,Volume,Turnover,P/E,P/B,Div Yield,Date
"""

from pathlib import Path

import pandas as pd

from pipeline.ingestion.parsers.base_parser import BaseParser
from agents.shared.logger import get_logger

log = get_logger("pipeline.parsers.indices")


# Columns that must be numeric in indices data
NUMERIC_COLS = [
    "open", "high", "low", "close",
    "volume", "turnover", "pe", "pb", "div_yield",
    "points_change", "change_percent",
]

# Possible column name variants NSE uses (we normalize all to standard names)
COLUMN_ALIASES = {
    "index name":      "index_name",
    "index_name":      "index_name",
    "name":            "index_name",
    "open":            "open",
    "high":            "high",
    "low":             "low",
    "close":           "close",
    "closing index value": "close",
    "previous close":  "prev_close",
    "prev_close":      "prev_close",
    "volume":          "volume",
    "vol":             "volume",
    "turnover_rs_cr":  "turnover",
    "turnover":        "turnover",
    "p/e":             "pe",
    "pe_ratio":        "pe",
    "p/b":             "pb",
    "pb_ratio":        "pb",
    "div_yield":       "div_yield",
    "dividend_yield":  "div_yield",
    "points_change":   "points_change",
    "change":          "points_change",
    "change_%":        "change_percent",
    "change_percent":  "change_percent",
    "date":            "date",
    "index_date":      "date",
}


class IndicesParser(BaseParser):
    """
    Parser for individual index category CSVs (types 1-5).
    Each file has data for one or more indices in one category.
    """

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"IndicesParser: {path.name} (category={category})")

        df = self._read_csv(path)
        df = self._clean_columns(df)
        df = self._apply_aliases(df)

        # -- Date handling ----------------------------------------------
        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            # Try to extract date from filename
            trade_date = self._extract_date_from_filename(path.name)
            if trade_date:
                df["date"] = trade_date
            else:
                log.warning(f"No date found in {path.name} - using today")
                from datetime import date
                df["date"] = date.today().isoformat()

        # -- Numeric coercion -------------------------------------------
        df = self._coerce_numeric(df, NUMERIC_COLS)

        # -- Tag with category ------------------------------------------
        if category:
            df["category"] = category

        # -- Add audit metadata -----------------------------------------
        df = self._add_metadata(df, path)

        # -- Drop fully empty rows --------------------------------------
        df = df.dropna(subset=["index_name", "close"], how="any")
        df = df.reset_index(drop=True)

        log.info(f"IndicesParser result: {len(df):,} rows | cols: {list(df.columns)}")
        return df

    def _apply_aliases(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename columns using COLUMN_ALIASES map."""
        rename_map = {}
        for col in df.columns:
            normalized = col.strip().lower().replace(" ", "_").replace("/", "_")
            if col in COLUMN_ALIASES:
                rename_map[col] = COLUMN_ALIASES[col]
            elif normalized in COLUMN_ALIASES:
                rename_map[col] = COLUMN_ALIASES[normalized]
        if rename_map:
            df = df.rename(columns=rename_map)
            log.debug(f"Renamed columns: {rename_map}")
        return df


class NSEAllIndicesParser(BaseParser):
    """
    Parser for file type 11: 'NSE all indices data'
    This is a bulk file containing ALL 147 indices in one CSV.
    Format is typically identical to individual index CSVs
    but with many more rows.
    """

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"NSEAllIndicesParser: {path.name}")

        df = self._read_csv(path)
        df = self._clean_columns(df)

        # Reuse IndicesParser logic - same format, just bigger
        delegate = IndicesParser()
        df = delegate._apply_aliases(df)

        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            trade_date = self._extract_date_from_filename(path.name)
            df["date"] = trade_date or __import__("datetime").date.today().isoformat()

        df = self._coerce_numeric(df, NUMERIC_COLS)

        # For the bulk file, category comes from the index name itself
        # We set it as "ALL" - agents will sub-classify by index name
        df["category"] = "ALL"

        df = self._add_metadata(df, path)
        df = df.dropna(subset=["index_name", "close"], how="any")
        df = df.reset_index(drop=True)

        log.info(f"NSEAllIndicesParser result: {len(df):,} rows")
        return df
