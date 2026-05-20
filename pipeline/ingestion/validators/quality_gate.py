# -*- coding: utf-8 -*-
"""
MICC - Quality Gate
Runs validation checks on a parsed DataFrame before it's written to DB.
Rejects data that is too sparse, anomalous, or structurally wrong.
"""

import pandas as pd
from agents.shared.logger import get_logger

log = get_logger("pipeline.validators.quality_gate")

# Minimum required columns per parser type
REQUIRED_COLUMNS = {
    "indices_csv":          ["index_name", "close", "date"],
    "nse_all_indices":      ["index_name", "close", "date"],
    "full_bhavcopy":        ["symbol", "open", "high", "low", "close", "volume", "date"],
    "sme_bhavcopy":         ["symbol", "close", "date"],
    "nifty_holdings":       ["company_name", "weight_pct", "date"],
    "daily_snapshot":       ["date"],
    "all_etfs":             ["symbol", "date"],
    "total_stocks_traded":  ["date"],
    "market_activity":      ["date"],
}

# Numeric sanity ranges (min, max) per column
SANITY_RANGES = {
    "close":           (0.01, 1_000_000),
    "open":            (0.01, 1_000_000),
    "high":            (0.01, 1_000_000),
    "low":             (0.01, 1_000_000),
    "delivery_pct":    (0.0,  100.0),
    "weight_pct":      (0.0,  100.0),
    "premium_discount_pct": (-50.0, 50.0),
    "ad_ratio":        (0.0,  1000.0),
}


def run_quality_gate(df: pd.DataFrame, parser_key: str, table: str) -> dict:
    """
    Validates a parsed DataFrame.

    Returns:
        {
            "passed":       bool,
            "reason":       str | None,   # Why it failed (if failed)
            "coverage_pct": float,        # % of rows with non-null critical cols
            "warnings":     list[str],    # Non-blocking issues
            "row_count":    int,
        }
    """
    result = {
        "passed":       True,
        "reason":       None,
        "coverage_pct": 100.0,
        "warnings":     [],
        "row_count":    len(df),
    }

    # -- 1. Empty DataFrame check ---------------------------------------
    if df is None or len(df) == 0:
        result["passed"] = False
        result["reason"] = "DataFrame is empty"
        return result

    # -- 2. Required columns check --------------------------------------
    required = REQUIRED_COLUMNS.get(parser_key, [])
    missing = [col for col in required if col not in df.columns]
    if missing:
        result["passed"] = False
        result["reason"] = f"Missing required columns: {missing}"
        return result

    # -- 3. Coverage check (non-null rate on critical columns) ----------
    if required:
        null_counts = df[required].isnull().sum()
        total_cells = len(df) * len(required)
        null_total  = null_counts.sum()
        coverage    = (1 - null_total / total_cells) * 100 if total_cells > 0 else 100.0
        result["coverage_pct"] = round(coverage, 2)

        try:
            from config.settings import MIN_COVERAGE_PCT
        except ImportError:
            MIN_COVERAGE_PCT = 95.0

        if coverage < MIN_COVERAGE_PCT:
            result["passed"] = False
            result["reason"] = (
                f"Coverage {coverage:.1f}% < threshold {MIN_COVERAGE_PCT}%. "
                f"Null counts: {null_counts.to_dict()}"
            )
            return result

    # -- 4. Numeric sanity ranges ---------------------------------------
    for col, (min_val, max_val) in SANITY_RANGES.items():
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(numeric) == 0:
            continue

        out_of_range = ((numeric < min_val) | (numeric > max_val)).sum()
        pct = out_of_range / len(numeric) * 100

        if pct > 5.0:  # More than 5% of values out of range = warning
            result["warnings"].append(
                f"Column '{col}': {out_of_range:,} values ({pct:.1f}%) "
                f"outside [{min_val}, {max_val}]"
            )

    # -- 5. Date column validation --------------------------------------
    if "date" in df.columns:
        bad_dates = df["date"].isnull().sum()
        if bad_dates > 0:
            result["warnings"].append(f"{bad_dates:,} rows have null date")

        # Check dates aren't in the far future
        try:
            from datetime import datetime, timedelta
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if len(dates) > 0:
                max_date = dates.max()
                if max_date > datetime.now() + timedelta(days=2):
                    result["warnings"].append(f"Future dates detected: max={max_date.date()}")
        except Exception:
            pass

    # -- 6. Duplicate check (warn, don't fail) -------------------------
    if required and "date" in df.columns:
        key_cols = [c for c in required if c != "date"] + ["date"]
        key_cols = [c for c in key_cols if c in df.columns]
        if key_cols:
            dups = df.duplicated(subset=key_cols).sum()
            if dups > 0:
                result["warnings"].append(
                    f"{dups:,} duplicate rows detected (key: {key_cols})"
                )

    # Log warnings
    for w in result["warnings"]:
        log.warning(f"Quality warning [{parser_key}]: {w}")

    log.info(
        f"Quality gate: {'PASS' if result['passed'] else 'FAIL'} | "
        f"rows={result['row_count']:,} | coverage={result['coverage_pct']:.1f}%"
    )
    return result
