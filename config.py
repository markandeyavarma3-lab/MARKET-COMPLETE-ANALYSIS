# -*- coding: utf-8 -*-
"""
config.py — MICC Data Pipeline Configuration
=============================================
All paths are ABSOLUTE. This works regardless of CWD.
Place in: D:\\MICC\\data_pipeline\\config.py

The database lives in D:\\marketDB (the original extraction project location).
It is NOT moved — it's 53GB+ and already indexed and optimised there.
"""

from pathlib import Path

# ── Database (never moved — stays at D:\\marketDB) ────────────────────────────
DB_PATH       = Path(r"D:\marketDB\db\market.db")
STOCKS_DIR    = Path(r"D:\marketDB\stocks\all")
INDICES_DIR   = Path(r"D:\marketDB\indices\all")
BHAVCOPY_DIR  = Path(r"D:\marketDB\bhavcopy\raw")
LOGS_DIR      = Path(r"D:\MICC\data_pipeline\logs")
REGISTRY_PATH = Path(r"D:\marketDB\stocks\registry.parquet")

# ── Delays / Retries ──────────────────────────────────────────────────────────
BASE_DELAY  = 2.5
MAX_RETRIES = 3

# ── NSE Indices Master ────────────────────────────────────────────────────────
# Format: "Display Name": ("Yahoo Symbol", "Start Date", "Category")
NSE_INDEX_MASTER = {
    "NIFTY 50":                ("^NSEI",        "1999-11-03", "Broad Market"),
    "NIFTY BANK":              ("^NSEBANK",     "2000-01-01", "Sectoral"),
    "NIFTY IT":                ("^CNXIT",       "1999-01-01", "Sectoral"),
    "NIFTY MIDCAP 100":        ("^CNX100",      "2001-01-01", "Broad Market"),
    "NIFTY SMALLCAP 100":      ("NIFTY_SMALLCAP_100.NS", "2004-01-01", "Broad Market"),
    "NIFTY NEXT 50":           ("^NSMIDCP",     "1997-01-01", "Broad Market"),
    "NIFTY 100":               ("^CNX100",      "2003-01-01", "Broad Market"),
    "NIFTY 200":               ("^CNX200",      "2004-01-01", "Broad Market"),
    "NIFTY 500":               ("^CNX500",      "1999-01-01", "Broad Market"),
    "NIFTY AUTO":              ("^CNXAUTO",     "2004-01-01", "Sectoral"),
    "NIFTY FMCG":              ("^CNXFMCG",     "1996-01-01", "Sectoral"),
    "NIFTY PHARMA":            ("^CNXPHARMA",   "2001-01-01", "Sectoral"),
    "NIFTY METAL":             ("^CNXMETAL",    "2004-01-01", "Sectoral"),
    "NIFTY REALTY":            ("^CNXREALTY",   "2007-01-01", "Sectoral"),
    "NIFTY ENERGY":            ("^CNXENERGY",   "2001-01-01", "Sectoral"),
    "NIFTY INFRA":             ("^CNXINFRA",    "2004-01-01", "Sectoral"),
    "NIFTY MEDIA":             ("^CNXMEDIA",    "2005-01-01", "Sectoral"),
    "NIFTY PSU BANK":          ("^CNXPSUBANK",  "2004-01-01", "Sectoral"),
    "NIFTY PRIVATE BANK":      ("^NSPVTBNK",    "2004-01-01", "Sectoral"),
    "INDIA VIX":               ("^INDIAVIX",    "2008-01-01", "Volatility"),
    "NIFTY MIDCAP 50":         ("^NSEMDCP50",   "2005-01-01", "Broad Market"),
    "NIFTY CONSUMER DURABLES": ("^CNXCONSDUR",  "2015-01-01", "Sectoral"),
    "NIFTY OIL GAS":           ("^CNXOILGAS",   "2021-01-01", "Sectoral"),
    "NIFTY FINANCIAL SERVICES":("^CNXFINANCE",  "2004-01-01", "Sectoral"),
    "NIFTY HEALTHCARE":        ("^CNXHEALTH",   "2021-01-01", "Sectoral"),
    "SENSEX":                  ("^BSESN",       "1997-01-01", "BSE"),
    "BSE 500":                 ("BSE-500.BO",   "1999-01-01", "BSE"),
}

# ── URLs ──────────────────────────────────────────────────────────────────────
NIFTY500_URL        = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
NIFTY50_URL         = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
NSE_ALL_SYMBOLS_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
BHAVCOPY_BASE_URL   = ("https://nsearchives.nseindia.com/products/content/"
                        "sec_bhavdata_full_{date}.csv")

NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

# ── API Keys ──────────────────────────────────────────────────────────────────
FRED_API_KEY = "97dcf9c665ec4d3d4aeab55cbc113361"
