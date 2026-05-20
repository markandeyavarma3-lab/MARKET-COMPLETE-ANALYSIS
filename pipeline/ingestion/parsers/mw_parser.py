# -*- coding: utf-8 -*-
"""
MICC - Market Watch (MW) Parser
Handles NSE Market Watch files: MW-NIFTY-200, MW-NIFTY-50, etc.
These have columns: SYMBOL, OPEN, HIGH, LOW, LTP, %CHNG, VOLUME, 52W H/L
"""

from pathlib import Path
import pandas as pd
from pipeline.ingestion.parsers.base_parser import BaseParser
from agents.shared.logger import get_logger

log = get_logger("pipeline.parsers.mw")

MW_ALIASES = {
    "symbol":           "symbol",
    "open":             "open",
    "high":             "high",
    "low":              "low",
    "prev. close":      "prev_close",
    "prev_close":       "prev_close",
    "ltp":              "close",
    "close":            "close",
    "chng":             "points_change",
    "%chng":            "change_percent",
    "volume":           "volume",
    "volume(shares)":   "volume",
    "value(crores)":    "turnover",
    "value":            "turnover",
    "52w h":            "high_52w",
    "52w l":            "low_52w",
    "30 d%chng":        "chng_30d",
    "365 d%chng":       "chng_365d",
}

NUMERIC_COLS = [
    "open", "high", "low", "close", "prev_close",
    "points_change", "change_percent", "volume", "turnover",
    "high_52w", "low_52w", "chng_30d", "chng_365d",
]


class MarketWatchParser(BaseParser):
    """
    Parses MW-*.csv files from NSE.
    Extracts the index name from the filename (e.g. MW-NIFTY-200 -> NIFTY 200).
    Row 0 is the index itself, rows 1+ are constituent stocks.
    """

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info("MarketWatchParser: " + path.name)

        # Extract index name from filename
        # e.g. MW-NIFTY-200-05-May-2026.csv -> NIFTY 200
        index_name = self._extract_index_name(path.name)
        log.info("Index name: " + index_name)

        df = self._read_csv(path, encoding="utf-8-sig")
        df = self._clean_mw_columns(df)

        # Remove commas from numbers (NSE uses 1,23,456 format)
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(",", "", regex=False).str.strip()

        df = self._coerce_numeric(df, NUMERIC_COLS)

        # Extract date from filename
        trade_date = self._extract_date_from_filename(path.name)
        df["date"] = trade_date or __import__("datetime").date.today().isoformat()
        df["index_name"] = index_name
        if category:
            df["category"] = category

        # Drop the index summary row (first row, symbol = index name)
        # Keep only constituent stocks
        if len(df) > 1:
            df = df.iloc[1:].reset_index(drop=True)

        df = self._add_metadata(df, path)
        df = df.dropna(subset=["symbol"], how="any")
        df = df[df["symbol"].str.strip() != ""].reset_index(drop=True)

        log.info("MarketWatchParser result: " + str(len(df)) + " constituents")
        return df

    def _clean_mw_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean MW column names which have newlines and special chars."""
        import re
        new_cols = []
        for col in df.columns:
            # Remove newlines, extra spaces, special chars
            clean = col.replace("\n", " ").strip()
            clean = re.sub(r"\s+", " ", clean)
            clean = clean.lower()
            # Match against aliases
            matched = False
            for alias_key, alias_val in MW_ALIASES.items():
                if alias_key in clean:
                    new_cols.append(alias_val)
                    matched = True
                    break
            if not matched:
                # Generic clean
                clean = re.sub(r"[^a-z0-9_]", "_", clean).strip("_")
                new_cols.append(clean)

        df.columns = new_cols
        # Drop duplicate columns (MW files sometimes have repeated cols)
        df = df.loc[:, ~df.columns.duplicated()]
        return df

    def _extract_index_name(self, filename: str) -> str:
        """
        MW-NIFTY-200-05-May-2026.csv  -> NIFTY 200
        MW-NIFTY-50-05-May-2026.csv   -> NIFTY 50
        MW-BANKNIFTY-05-May-2026.csv  -> BANKNIFTY
        """
        import re
        name = filename.replace("MW-", "").replace(".csv", "")
        # Remove date portion (DD-Mon-YYYY at end)
        name = re.sub(r"-\d{2}-[A-Za-z]{3}-\d{4}$", "", name)
        return name.replace("-", " ").strip()
