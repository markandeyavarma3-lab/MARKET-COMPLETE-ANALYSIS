# -*- coding: utf-8 -*-
"""
MICC - Ingestion Router
Dispatches classified files to the correct parser and writer.
"""

import time
from pathlib import Path
from agents.shared.logger import get_logger

log = get_logger("pipeline.router")


def route_file(metadata: dict) -> dict:
    path       = metadata["path"]
    parser_key = metadata["parser_key"]
    table      = metadata["table"]
    category   = metadata.get("category")

    start = time.monotonic()
    result = {
        "success":      False,
        "rows_written": 0,
        "table":        table,
        "duration_ms":  0.0,
        "error":        None,
        "quality":      {},
    }

    try:
        parser = _get_parser(parser_key, path)
        if parser is None:
            raise ValueError("No parser for key: " + parser_key)

        log.info("Parsing [" + parser_key + "]: " + path.name)
        df = parser.parse(path, category=category)

        if df is None or df.empty:
            raise ValueError("Parser returned empty DataFrame for " + path.name)

        log.info("Parsed " + str(len(df)) + " rows x " + str(len(df.columns)) + " columns")

        from pipeline.ingestion.validators.quality_gate import run_quality_gate
        quality = run_quality_gate(df, parser_key, table)
        result["quality"] = quality

        if not quality["passed"]:
            raise ValueError("Quality gate failed: " + quality["reason"])

        log.info("Quality gate: PASSED (coverage=" + str(quality["coverage_pct"]) + "%)")

        writer = _get_writer(parser_key)
        rows_written = writer.write(df, table, path, category=category)
        result["rows_written"] = rows_written
        result["success"] = True

    except Exception as exc:
        result["error"] = str(exc)
        log.error("Route failed for " + path.name + ": " + str(exc))

    finally:
        result["duration_ms"] = (time.monotonic() - start) * 1000
        log.info(
            "Route complete | success=" + str(result["success"]) +
            " | rows=" + str(result["rows_written"]) +
            " | " + str(round(result["duration_ms"])) + "ms"
        )

    return result


def _get_parser(parser_key: str, path: Path = None):
    """
    Auto-detect MW files by filename prefix regardless of parser_key.
    MW-*.csv files go to MarketWatchParser always.
    """
    # Auto-detect Market Watch files by filename
    if path and path.name.startswith("MW-"):
        from pipeline.ingestion.parsers.mw_parser import MarketWatchParser
        return MarketWatchParser()

    try:
        if parser_key == "indices_csv":
            from pipeline.ingestion.parsers.indices_parser import IndicesParser
            return IndicesParser()

        elif parser_key == "nse_all_indices":
            from pipeline.ingestion.parsers.indices_parser import NSEAllIndicesParser
            return NSEAllIndicesParser()

        elif parser_key == "full_bhavcopy":
            from pipeline.ingestion.parsers.bhavcopy_parser import FullBhavCopyParser
            return FullBhavCopyParser()

        elif parser_key == "sme_bhavcopy":
            from pipeline.ingestion.parsers.bhavcopy_parser import SMEBhavCopyParser
            return SMEBhavCopyParser()

        elif parser_key == "nifty_holdings":
            from pipeline.ingestion.parsers.holdings_parser import NiftyHoldingsParser
            return NiftyHoldingsParser()

        elif parser_key == "daily_snapshot":
            from pipeline.ingestion.parsers.snapshot_parser import DailySnapshotParser
            return DailySnapshotParser()

        elif parser_key == "all_etfs":
            from pipeline.ingestion.parsers.etf_parser import ETFParser
            return ETFParser()

        elif parser_key == "total_stocks_traded":
            from pipeline.ingestion.parsers.breadth_parser import TotalStocksTradedParser
            return TotalStocksTradedParser()

        elif parser_key == "market_activity":
            from pipeline.ingestion.parsers.activity_parser import MarketActivityParser
            return MarketActivityParser()

        else:
            log.error("Unknown parser_key: " + parser_key)
            return None

    except ImportError as e:
        log.error("Failed to import parser '" + parser_key + "': " + str(e))
        return None


def _get_writer(parser_key: str):
    if parser_key == "full_bhavcopy":
        from pipeline.ingestion.writers import DualWriter
        return DualWriter()
    else:
        from pipeline.ingestion.writers import SQLiteWriter
        return SQLiteWriter()
