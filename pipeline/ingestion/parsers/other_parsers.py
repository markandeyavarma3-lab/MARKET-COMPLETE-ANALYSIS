# -*- coding: utf-8 -*-
"""
MICC - Holdings Parser (file type 8)
Nifty 50 top 10 holdings - tracks weight drift of top constituents.
"""
from pathlib import Path
import pandas as pd
from pipeline.ingestion.parsers.base_parser import BaseParser
from agents.shared.logger import get_logger

log = get_logger("pipeline.parsers.holdings")

NUMERIC_COLS = ["weight_pct", "shares_held", "market_value_cr", "portfolio_pct"]

ALIASES = {
    "company":          "company_name",
    "company_name":     "company_name",
    "stock":            "company_name",
    "symbol":           "symbol",
    "weight":           "weight_pct",
    "weight_pct":       "weight_pct",
    "weightage_pct":    "weight_pct",
    "holding_pct":      "weight_pct",
    "shares":           "shares_held",
    "shares_held":      "shares_held",
    "market_value":     "market_value_cr",
    "market_cap_cr":    "market_value_cr",
    "date":             "date",
    "as_on_date":       "date",
}


class NiftyHoldingsParser(BaseParser):
    """Parses Nifty 50 top 10 holdings file."""

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"NiftyHoldingsParser: {path.name}")
        df = self._read_csv(path)
        df = self._clean_columns(df)

        rename_map = {c: ALIASES[c] for c in df.columns if c in ALIASES}
        df = df.rename(columns=rename_map)

        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            trade_date = self._extract_date_from_filename(path.name)
            df["date"] = trade_date or __import__("datetime").date.today().isoformat()

        df = self._coerce_numeric(df, NUMERIC_COLS)
        df["index_name"] = "NIFTY 50"
        df = self._add_metadata(df, path)
        df = df.dropna(subset=["company_name", "weight_pct"], how="any")
        df = df.reset_index(drop=True)

        log.info(f"NiftyHoldingsParser result: {len(df):,} rows")
        return df


# ---------------------------------------------------------------------

"""
MICC - Daily Snapshot Parser (file type 9)
Market breadth: advance/decline, new highs/lows, etc.
"""

SNAPSHOT_ALIASES = {
    "advances":          "advances",
    "advance":           "advances",
    "declines":          "declines",
    "decline":           "declines",
    "unchanged":         "unchanged",
    "new_52w_high":      "new_52w_high",
    "52wk_high":         "new_52w_high",
    "new_52w_low":       "new_52w_low",
    "52wk_low":          "new_52w_low",
    "total_traded_qty":  "total_volume",
    "total_traded_val":  "total_turnover",
    "date":              "date",
    "market_date":       "date",
}

SNAPSHOT_NUMERIC = [
    "advances", "declines", "unchanged",
    "new_52w_high", "new_52w_low",
    "total_volume", "total_turnover",
]


class DailySnapshotParser(BaseParser):
    """Parses daily market snapshot (advance/decline breadth)."""

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"DailySnapshotParser: {path.name}")
        df = self._read_csv(path)
        df = self._clean_columns(df)

        rename_map = {c: SNAPSHOT_ALIASES[c] for c in df.columns if c in SNAPSHOT_ALIASES}
        df = df.rename(columns=rename_map)

        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            df["date"] = self._extract_date_from_filename(path.name) or \
                         __import__("datetime").date.today().isoformat()

        df = self._coerce_numeric(df, SNAPSHOT_NUMERIC)

        # Derived metric: advance/decline ratio
        if "advances" in df.columns and "declines" in df.columns:
            df["ad_ratio"] = df["advances"] / (df["declines"].replace(0, 1))

        df = self._add_metadata(df, path)
        df = df.reset_index(drop=True)
        log.info(f"DailySnapshotParser result: {len(df):,} rows")
        return df


# ---------------------------------------------------------------------

"""MICC - ETF Parser (file type 10)"""

ETF_ALIASES = {
    "scheme_name":      "etf_name",
    "etf_name":         "etf_name",
    "name":             "etf_name",
    "symbol":           "symbol",
    "nav":              "nav",
    "market_price":     "market_price",
    "ltp":              "market_price",
    "close":            "market_price",
    "premium_discount": "premium_discount_pct",
    "premium":          "premium_discount_pct",
    "volume":           "volume",
    "date":             "date",
}

ETF_NUMERIC = ["nav", "market_price", "premium_discount_pct", "volume"]


class ETFParser(BaseParser):
    """Parses NSE ETF data including NAV vs market price."""

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"ETFParser: {path.name}")
        df = self._read_csv(path)
        df = self._clean_columns(df)

        rename_map = {c: ETF_ALIASES[c] for c in df.columns if c in ETF_ALIASES}
        df = df.rename(columns=rename_map)

        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            df["date"] = self._extract_date_from_filename(path.name) or \
                         __import__("datetime").date.today().isoformat()

        df = self._coerce_numeric(df, ETF_NUMERIC)

        # Compute premium/discount if not already present
        if "premium_discount_pct" not in df.columns:
            if "nav" in df.columns and "market_price" in df.columns:
                df["premium_discount_pct"] = (
                    (df["market_price"] - df["nav"]) / df["nav"] * 100
                ).round(4)

        df = self._add_metadata(df, path)
        df = df.dropna(subset=["etf_name", "nav"], how="any")
        df = df.reset_index(drop=True)
        log.info(f"ETFParser result: {len(df):,} rows")
        return df


# ---------------------------------------------------------------------

"""MICC - Total Stocks Traded Parser (file type 12)"""

BREADTH_ALIASES = {
    "date":                   "date",
    "total_securities":       "total_securities",
    "securities_traded":      "total_securities",
    "above_200dma":           "pct_above_200dma",
    "pct_above_200dma":       "pct_above_200dma",
    "above_50dma":            "pct_above_50dma",
    "pct_above_50dma":        "pct_above_50dma",
    "above_20dma":            "pct_above_20dma",
    "new_highs":              "new_highs",
    "new_lows":               "new_lows",
    "market_cap_cr":          "total_market_cap_cr",
}

BREADTH_NUMERIC = [
    "total_securities", "pct_above_200dma", "pct_above_50dma",
    "pct_above_20dma", "new_highs", "new_lows", "total_market_cap_cr",
]


class TotalStocksTradedParser(BaseParser):
    """Parses total stocks traded data with breadth metrics."""

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"TotalStocksTradedParser: {path.name}")
        df = self._read_csv(path)
        df = self._clean_columns(df)

        rename_map = {c: BREADTH_ALIASES[c] for c in df.columns if c in BREADTH_ALIASES}
        df = df.rename(columns=rename_map)

        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            df["date"] = self._extract_date_from_filename(path.name) or \
                         __import__("datetime").date.today().isoformat()

        df = self._coerce_numeric(df, BREADTH_NUMERIC)
        df = self._add_metadata(df, path)
        df = df.reset_index(drop=True)
        log.info(f"TotalStocksTradedParser result: {len(df):,} rows")
        return df


# ---------------------------------------------------------------------

"""MICC - Market Activity Parser (file type 13)"""

ACTIVITY_ALIASES = {
    "date":                  "date",
    "client_type":           "client_type",
    "participant":           "client_type",
    "buy_value":             "buy_value_cr",
    "buy_value_cr":          "buy_value_cr",
    "sell_value":            "sell_value_cr",
    "sell_value_cr":         "sell_value_cr",
    "net_value":             "net_value_cr",
    "net":                   "net_value_cr",
    "cumulative_net_pos":    "cumulative_net_cr",
    "market_segment":        "segment",
    "segment":               "segment",
}

ACTIVITY_NUMERIC = [
    "buy_value_cr", "sell_value_cr", "net_value_cr", "cumulative_net_cr",
]


class MarketActivityParser(BaseParser):
    """
    Parses market activity report (FII/DII/Prop/Retail breakdown).
    Key for Alpha Agent's flow intelligence module.
    """

    def parse(self, path: Path, category: str | None = None) -> pd.DataFrame:
        log.info(f"MarketActivityParser: {path.name}")
        df = self._read_csv(path)
        df = self._clean_columns(df)

        rename_map = {c: ACTIVITY_ALIASES[c] for c in df.columns if c in ACTIVITY_ALIASES}
        df = df.rename(columns=rename_map)

        if "date" in df.columns:
            df["date"] = self._parse_date_column(df["date"])
        else:
            df["date"] = self._extract_date_from_filename(path.name) or \
                         __import__("datetime").date.today().isoformat()

        df = self._coerce_numeric(df, ACTIVITY_NUMERIC)

        # Derived: buy/sell ratio per participant
        if "buy_value_cr" in df.columns and "sell_value_cr" in df.columns:
            df["buy_sell_ratio"] = (
                df["buy_value_cr"] / df["sell_value_cr"].replace(0, 1)
            ).round(4)

        df = self._add_metadata(df, path)
        df = df.reset_index(drop=True)
        log.info(f"MarketActivityParser result: {len(df):,} rows")
        return df
