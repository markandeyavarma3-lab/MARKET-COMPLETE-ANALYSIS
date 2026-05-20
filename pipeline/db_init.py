# -*- coding: utf-8 -*-
"""
MICC - Database Schema Initializer
Creates all tables if they don't exist.
Adds missing columns to existing tables (safe migration).

Run once before starting the watcher:
    py pipeline/db_init.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.shared.marketdb import db_session
from agents.shared.logger import get_logger

log = get_logger("pipeline.db_init")

# ─────────────────────────────────────────────────────────────────────
# TABLE SCHEMAS
# ─────────────────────────────────────────────────────────────────────

SCHEMAS = {

    "stock_delivery": """
        CREATE TABLE IF NOT EXISTS stock_delivery (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL,
            series          TEXT,
            date            TEXT    NOT NULL,
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            last_price      REAL,
            prev_close      REAL,
            avg_price       REAL,
            volume          REAL,
            turnover        REAL,
            trade_count     REAL,
            delivery_qty    REAL,
            delivery_pct    REAL,
            ingest_date     TEXT,
            source_file     TEXT,
            trade_date      TEXT,
            UNIQUE(symbol, series, date)
        )
    """,

    "indices_data": """
        CREATE TABLE IF NOT EXISTS indices_data (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name      TEXT    NOT NULL,
            date            TEXT    NOT NULL,
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            prev_close      REAL,
            volume          REAL,
            turnover        REAL,
            pe              REAL,
            pb              REAL,
            div_yield       REAL,
            points_change   REAL,
            change_percent  REAL,
            category        TEXT,
            ingest_date     TEXT,
            source_file     TEXT,
            UNIQUE(index_name, date)
        )
    """,

    "market_snapshot": """
        CREATE TABLE IF NOT EXISTS market_snapshot (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT,
            index_name      TEXT,
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            prev_close      REAL,
            points_change   REAL,
            change_percent  REAL,
            advances        REAL,
            declines        REAL,
            unchanged       REAL,
            new_52w_high    REAL,
            new_52w_low     REAL,
            total_volume    REAL,
            total_turnover  REAL,
            ad_ratio        REAL,
            ingest_date     TEXT,
            source_file     TEXT
        )
    """,

    "sme_data": """
        CREATE TABLE IF NOT EXISTS sme_data (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol              TEXT,
            series              TEXT,
            date                TEXT,
            open                REAL,
            high                REAL,
            low                 REAL,
            close               REAL,
            volume              REAL,
            delivery_pct        REAL,
            exchange_segment    TEXT DEFAULT 'SME',
            ingest_date         TEXT,
            source_file         TEXT,
            UNIQUE(symbol, date)
        )
    """,

    "index_holdings": """
        CREATE TABLE IF NOT EXISTS index_holdings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name      TEXT,
            company_name    TEXT,
            symbol          TEXT,
            weight_pct      REAL,
            shares_held     REAL,
            market_value_cr REAL,
            date            TEXT,
            ingest_date     TEXT,
            source_file     TEXT,
            UNIQUE(index_name, company_name, date)
        )
    """,

    "etf_data": """
        CREATE TABLE IF NOT EXISTS etf_data (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            etf_name                TEXT,
            symbol                  TEXT,
            nav                     REAL,
            market_price            REAL,
            premium_discount_pct    REAL,
            volume                  REAL,
            date                    TEXT,
            ingest_date             TEXT,
            source_file             TEXT,
            UNIQUE(symbol, date)
        )
    """,

    "market_breadth": """
        CREATE TABLE IF NOT EXISTS market_breadth (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            date                TEXT,
            total_securities    REAL,
            pct_above_200dma    REAL,
            pct_above_50dma     REAL,
            pct_above_20dma     REAL,
            new_highs           REAL,
            new_lows            REAL,
            total_market_cap_cr REAL,
            ingest_date         TEXT,
            source_file         TEXT,
            UNIQUE(date)
        )
    """,

    "market_activity": """
        CREATE TABLE IF NOT EXISTS market_activity (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            date                TEXT,
            client_type         TEXT,
            segment             TEXT,
            buy_value_cr        REAL,
            sell_value_cr       REAL,
            net_value_cr        REAL,
            cumulative_net_cr   REAL,
            buy_sell_ratio      REAL,
            ingest_date         TEXT,
            source_file         TEXT,
            UNIQUE(date, client_type, segment)
        )
    """,
}

# ─────────────────────────────────────────────────────────────────────
# MIGRATION: Add missing columns to existing tables
# Safe to run multiple times - skips columns that already exist
# ─────────────────────────────────────────────────────────────────────

MIGRATIONS = {
    "stock_delivery": [
        "ALTER TABLE stock_delivery ADD COLUMN series TEXT",
        "ALTER TABLE stock_delivery ADD COLUMN avg_price REAL",
        "ALTER TABLE stock_delivery ADD COLUMN last_price REAL",
        "ALTER TABLE stock_delivery ADD COLUMN prev_close REAL",
        "ALTER TABLE stock_delivery ADD COLUMN trade_count REAL",
        "ALTER TABLE stock_delivery ADD COLUMN delivery_qty REAL",
        "ALTER TABLE stock_delivery ADD COLUMN delivery_pct REAL",
        "ALTER TABLE stock_delivery ADD COLUMN ingest_date TEXT",
        "ALTER TABLE stock_delivery ADD COLUMN source_file TEXT",
        "ALTER TABLE stock_delivery ADD COLUMN trade_date TEXT",
        "ALTER TABLE stock_delivery ADD COLUMN date1 TEXT",
    ],
}


def run_migrations(conn):
    """Add missing columns to existing tables. Ignores errors for columns that already exist."""
    for table, statements in MIGRATIONS.items():
        # Check table exists first
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            continue

        for sql in statements:
            try:
                conn.execute(sql)
                col = sql.split("ADD COLUMN")[1].strip().split()[0]
                log.info("Migration: added column '" + col + "' to " + table)
            except Exception:
                pass  # Column already exists - normal, skip


def create_indexes(conn):
    """Create performance indexes on key lookup columns."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_stock_delivery_symbol_date ON stock_delivery(symbol, date)",
        "CREATE INDEX IF NOT EXISTS idx_stock_delivery_date ON stock_delivery(date)",
        "CREATE INDEX IF NOT EXISTS idx_indices_data_name_date ON indices_data(index_name, date)",
        "CREATE INDEX IF NOT EXISTS idx_indices_data_category ON indices_data(category)",
        "CREATE INDEX IF NOT EXISTS idx_market_activity_date ON market_activity(date)",
        "CREATE INDEX IF NOT EXISTS idx_market_breadth_date ON market_breadth(date)",
    ]
    for sql in indexes:
        try:
            conn.execute(sql)
        except Exception as e:
            log.debug("Index skip: " + str(e))


def init_database():
    log.info("=" * 50)
    log.info("  MICC Database Initializer")
    log.info("=" * 50)

    with db_session() as conn:
        # Step 1: Run migrations on existing tables
        log.info("Running migrations on existing tables...")
        run_migrations(conn)

        # Step 2: Create tables that don't exist yet
        log.info("Creating missing tables...")
        for table_name, schema in SCHEMAS.items():
            conn.execute(schema)
            count = conn.execute("SELECT COUNT(*) FROM " + table_name).fetchone()[0]
            log.info("  " + table_name + ": " + str(count) + " rows")

        # Step 3: Create indexes
        log.info("Creating indexes...")
        create_indexes(conn)

    log.info("=" * 50)
    log.info("  Database ready.")
    log.info("=" * 50)


if __name__ == "__main__":
    init_database()
