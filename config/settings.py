# -*- coding: utf-8 -*-
"""
MICC - Master Configuration
Edit ONLY this file when your folder structure changes.
"""

import os
from pathlib import Path

# ─────────────────────────────────────────────
# CORE PATHS
# ─────────────────────────────────────────────

DB_ROOT      = Path("D:/marketDB")
DB_PATH      = DB_ROOT / "db" / "market.db"
PARQUET_ROOT = DB_ROOT / "stocks" / "all"

# Your actual OneDrive Desktop path
NSE_DATA_ROOT   = Path.home() / "OneDrive" / "Desktop" / "NSE Data"

NSE_INDICES_DIR = NSE_DATA_ROOT / "NSE INDICES"
NSE_OTHER_DIR   = NSE_DATA_ROOT / "NSE OTHER DATA"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR     = PROJECT_ROOT / "logs"
AGENT_OUTPUTS = PROJECT_ROOT / "agents"

# ─────────────────────────────────────────────
# INDICES CATEGORY MAP
# Maps your actual folder names -> category tag
# ─────────────────────────────────────────────

INDICES_CATEGORY_MAP = {
    "DERIVATIVES":              "DERIVATIVES",
    "BROAD MARKET INDICES":     "BROAD",
    "SECTORAL MARKET INDICES":  "SECTORAL",
    "STRATEGY MARKET INDICES":  "STRATEGY",
    "THEMATIC MARKET INDICES":  "THEMATIC",
}

# ─────────────────────────────────────────────
# OTHER DATA MAP
# Maps your actual folder names -> (parser_key, table)
# ─────────────────────────────────────────────

OTHER_DATA_MAP = {
    "full bhavcopy and security deliverable data": ("full_bhavcopy",       "stock_delivery"),
    "sme-bhavcopy file":                           ("sme_bhavcopy",        "sme_data"),
    "nifty 50 top 10 holdings":                    ("nifty_holdings",      "index_holdings"),
    "daily snapshot":                              ("daily_snapshot",      "market_snapshot"),
    "all etfs":                                    ("all_etfs",            "etf_data"),
    "nse all indices data":                        ("nse_all_indices",     "indices_data"),
    "total stocks traded":                         ("total_stocks_traded", "market_breadth"),
    "market activity report":                      ("market_activity",     "market_activity"),
}

# ─────────────────────────────────────────────
# DATABASE SETTINGS
# ─────────────────────────────────────────────

SQLITE_PRAGMAS = {
    "journal_mode": "WAL",
    "synchronous":  "NORMAL",
    "busy_timeout": 30000,
    "cache_size":   -20000,
    "temp_store":   "MEMORY",
    "mmap_size":    30000000000,
}

# ─────────────────────────────────────────────
# WATCHER SETTINGS
# ─────────────────────────────────────────────

WATCH_INTERVAL_SECONDS = 2
FILE_STABLE_WAIT       = 3
SUPPORTED_EXTENSIONS   = {".csv", ".CSV"}

# ─────────────────────────────────────────────
# QUALITY GATE
# ─────────────────────────────────────────────

MIN_COVERAGE_PCT = 95.0
MAX_NULL_PCT     = 5.0
ANOMALY_SIGMA    = 3.0

# ─────────────────────────────────────────────
# LLM SETTINGS
# ─────────────────────────────────────────────

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODELS = {
    "fast":      "gemma3:4b",
    "reasoning": "deepseek-r1:7b",
    "tiny":      "qwen3:1.7b",
}

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL   = "deepseek-chat"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

LOG_LEVEL        = "INFO"
LOG_FORMAT       = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT  = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES    = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
