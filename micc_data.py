# -*- coding: utf-8 -*-
"""
MICC v2 — Shared Data Layer
============================
Imported by all agents. Provides:
  - DB connection + common queries
  - Parquet loader (bhavcopy format preferred)
  - Index constituent lookup
  - News fetcher (4 free sources, no API key needed except Groq)
  - LLM caller: Ollama → Groq (free) → local rules fallback
  - Common utilities

Usage: from micc_data import *
"""

import sqlite3
import re
import time
import os
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import requests

warnings.filterwarnings("ignore")

# ── SSL FIX — override any broken system cert paths with certifi's bundle ──────
# The env var REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE may point to a deleted folder
# (D:\filesssss\...) left behind by old GDAL/PostGIS installs.
# Force certifi's valid bundle before any network call is made.
try:
    import certifi
    _cert_path = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = _cert_path
    os.environ["SSL_CERT_FILE"]      = _cert_path
    os.environ["CURL_CA_BUNDLE"]     = _cert_path
except ImportError:
    pass  # certifi not installed — requests will use system default

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — edit these if paths change
# ═══════════════════════════════════════════════════════════════════════════════

DB_PATH      = Path("D:/marketDB/db/market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")
# Verify the path exists at import time and warn if not
if not PARQUET_ROOT.exists():
    import warnings as _w
    _w.warn(f"[micc_data] PARQUET_ROOT not found: {PARQUET_ROOT}", RuntimeWarning)

# ── Credentials: loaded from .env, fallback to defaults ──────────────────────
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; use os.environ or hardcoded fallbacks

GROQ_API_KEY   = os.environ.get("GROQ_API_KEY",       "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")
GROQ_MODEL     = os.environ.get("GROQ_MODEL",          "llama-3.3-70b-versatile")
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TIMEOUT   = 90
GROQ_RATE_DELAY= 6
_groq_last_call= 0.0

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8420620581:AAGFtYxNodQ6nAR7kJVS_jAGti2IVPooFMU")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "6505636241")

OLLAMA_URL     = os.environ.get("OLLAMA_URL",    "http://localhost:11434/api/chat")
OLLAMA_MODEL   = os.environ.get("OLLAMA_MODEL",  "gemma3:4b")
OLLAMA_TIMEOUT = 180


# Telegram (hardcoded for convenience — same as existing bot)
TELEGRAM_BOT_TOKEN = "8420620581:AAGFtYxNodQ6nAR7kJVS_jAGti2IVPooFMU"
TELEGRAM_CHAT_ID   = "6505636241"

# Screening constants
MIN_TURNOVER_LACS = 50
MIN_PRICE         = 5.0   # filter sub-penny junk
ETF_PATTERNS = (
    "ETF", "LIQUID", "GOLD", "SILVER", "GILT", "BEES", "MOM30",
    "SETF", "BSLGOLD", "ABSLPAY", "ICICIB22", "NIFTYBEES",
)

# News sources (free, no API key)
NEWS_TIMEOUT = 10

# ═══════════════════════════════════════════════════════════════════════════════
# DB HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def get_trading_dates(n: int, table: str = "market_snapshot") -> list:
    """Return last N distinct trading dates from market_snapshot (ISO strings, ascending)."""
    conn = get_conn()
    rows = conn.execute(
        f"SELECT DISTINCT date FROM {table} ORDER BY date DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return sorted([r[0] for r in rows])


def get_all_trading_dates_since(start_date: str) -> list:
    """Return all trading dates from start_date to latest (ascending)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT date FROM market_snapshot WHERE date >= ? ORDER BY date",
        (start_date,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]



# ═══════════════════════════════════════════════════════════════════════════════
# DATE NORMALISER  (Phase 1.1)
# ═══════════════════════════════════════════════════════════════════════════════

_MON_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

def _parse_dd_mon_yyyy(s: str):
    """
    Parse '30-Mar-2026' → datetime.date(2026, 3, 30).
    Returns None on failure.
    """
    if not s or not isinstance(s, str):
        return None
    m = re.match(r"^(\d{1,2})[-/](\w{3})[-/](\d{4})$", s.strip())
    if m:
        day, mon, year = m.groups()
        mo = _MON_MAP.get(mon.lower())
        if mo:
            try:
                from datetime import date as _date
                return _date(int(year), int(mo), int(day))
            except ValueError:
                return None
    return None


def normalise_date(s) -> str:
    """
    Convert any date string MICC touches into YYYY-MM-DD.

    Handles:
      '30-Mar-2026'   → '2026-03-30'   (stock_delivery DD-Mon-YYYY)
      '2026-03-30'    → '2026-03-30'   (market_snapshot, indices_data — already ISO)
      '30/03/2026'    → '2026-03-30'   (DD/MM/YYYY)
      '30-03-2026'    → '2026-03-30'   (DD-MM-YYYY)
      datetime / date   → '2026-03-30'   (pandas Timestamp, datetime.date)

    Returns original string unchanged if format not recognised (safe fallback).
    """
    if s is None:
        return ""

    # pandas Timestamp / datetime / date
    try:
        import pandas as _pd
        if isinstance(s, (_pd.Timestamp,)):
            return s.strftime("%Y-%m-%d")
    except ImportError:
        pass

    from datetime import datetime as _dt, date as _date
    if isinstance(s, _date):
        return s.strftime("%Y-%m-%d")
    if isinstance(s, _dt):
        return s.strftime("%Y-%m-%d")

    s = str(s).strip()

    # Already ISO — fastest path
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # DD-Mon-YYYY  e.g. 30-Mar-2026
    parsed = _parse_dd_mon_yyyy(s)
    if parsed:
        return parsed.strftime("%Y-%m-%d")

    # DD/MM/YYYY or DD-MM-YYYY (numeric month)
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        try:
            from datetime import date as _date2
            return _date2(int(y), int(mo), int(d)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # YYYY/MM/DD
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        try:
            from datetime import date as _date3
            return _date3(int(y), int(mo), int(d)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Unknown format — return as-is so nothing breaks
    return s


def get_trading_dates_from_delivery(n: int) -> list:
    """
    Return last N distinct trading dates from stock_delivery as ISO strings
    (YYYY-MM-DD), most-recent first.

    stock_delivery stores dates as '30-Mar-2026' so this converts before sorting.
    """
    conn = get_conn()
    # Try both column names (DATE and DATE1 seen in different imports)
    col_info = [r[1].upper() for r in conn.execute("PRAGMA table_info(stock_delivery)").fetchall()]
    date_col = "DATE1" if "DATE1" in col_info else "DATE"

    rows = conn.execute(
        f"SELECT DISTINCT {date_col} FROM stock_delivery"
    ).fetchall()
    conn.close()

    raw = [r[0] for r in rows if r[0]]

    parsed = []
    for s in raw:
        iso = normalise_date(s)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", iso):
            parsed.append(iso)

    parsed.sort(reverse=True)
    return parsed[:n]


def get_delivery_for_dates(iso_dates: list) -> pd.DataFrame:
    """
    Fetch stock_delivery rows for a list of ISO dates (YYYY-MM-DD).
    Works regardless of whether the DB stores dates as DD-Mon-YYYY or YYYY-MM-DD.

    Returns DataFrame with normalised 'date' column in ISO format.
    Columns: SYMBOL, SERIES, date, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE,
             LOW_PRICE, CLOSE_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, DELIV_QTY,
             DELIV_PER  (names lowercased)
    """
    if not iso_dates:
        return pd.DataFrame()

    conn = get_conn()
    col_info = [r[1].upper() for r in conn.execute("PRAGMA table_info(stock_delivery)").fetchall()]
    date_col = "DATE1" if "DATE1" in col_info else "DATE"

    # Fetch a broad window — then filter in Python after normalising dates
    # (Cannot do BETWEEN on mixed-format date strings in SQLite)
    iso_sorted = sorted(iso_dates)
    # Convert ISO dates back to the DB's native format for a rough filter
    # We over-fetch by month and trim — safe and fast enough for ~2500 rows/day
    start_iso = iso_sorted[0]
    end_iso   = iso_sorted[-1]

    df = pd.read_sql(
        f"SELECT * FROM stock_delivery WHERE {date_col} IS NOT NULL",
        conn
    )
    conn.close()

    if df.empty:
        return df

    df.columns = [c.lower() for c in df.columns]
    actual_date_col = "date1" if "date1" in df.columns else "date"

    # Normalise all dates to ISO
    df["date"] = df[actual_date_col].apply(normalise_date)

    # Now filter cleanly
    iso_set = set(iso_dates)
    df = df[df["date"].isin(iso_set)].copy()
    df = df.reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL MACRO CONTEXT  (Phase 2.1)
# ═══════════════════════════════════════════════════════════════════════════════

# Tickers in global_data that matter for NSE macro context
_GLOBAL_TICKERS = {
    "DXY":        ("DXY",         "USD Index",    "inverse"),   # DXY up = FII headwind
    "Crude Oil":  ("Crude Oil",   "Crude Oil",    "mixed"),     # high = inflation risk
    "Gold":       ("Gold",        "Gold",         "risk-off"),  # gold up = risk-off
    "S&P 500":    ("S&P 500",     "S&P 500",      "leading"),   # US leads India
    "Dow Jones":  ("Dow Jones",   "Dow",          "leading"),
    "Nasdaq":     ("Nasdaq",      "Nasdaq",       "leading"),
    "USD/INR":    ("USD/INR",     "USD/INR",      "inverse"),   # rupee weak = FII sell
    "India VIX":  ("India VIX",   "India VIX",    "fear"),      # VIX > 20 = caution
}



# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# EPS LEVEL (Patch 2.2b — single-quarter signal)
# ─────────────────────────────────────────────────────────────────────────────

def get_eps_level(symbols: list) -> dict:
    """
    Return latest EPS per symbol from quarterly_income.
    Schema: quarterly_income(symbol, report_date, data_json)
    Returns: {symbol: {"eps": float|None, "profitable": bool}}
    """
    if not symbols:
        return {}
    conn = get_conn()
    try:
        placeholders = ",".join("?" * len(symbols))
        rows = conn.execute(
            "SELECT symbol, report_date, data_json "
            "FROM quarterly_income "
            "WHERE symbol IN ({}) "
            "ORDER BY symbol, report_date DESC".format(placeholders),
            [s.upper() for s in symbols],
        ).fetchall()
    except Exception as e:
        print("[Data] get_eps_level query failed: {}".format(e))
        return {}
    finally:
        conn.close()

    if not rows:
        return {}

    seen = set()
    result = {}

    for sym, rdate, djson in rows:
        sym = str(sym).upper()
        if sym in seen:
            continue
        seen.add(sym)

        # Parse data_json — handle NaN literals from yfinance
        data = {}
        if isinstance(djson, str):
            try:
                data = json.loads(djson)
            except Exception:
                safe = djson.replace(": NaN", ": null").replace(":NaN", ":null")
                safe = safe.replace(": Infinity", ": null").replace(":-Infinity", ":null")
                safe = safe.replace(": -Infinity", ":null")
                try:
                    data = json.loads(safe)
                except Exception:
                    data = {}
        elif isinstance(djson, dict):
            data = djson

        # Extract EPS — try Diluted first, then Basic
        eps = None
        for key in ("Diluted EPS", "Basic EPS"):
            val = data.get(key)
            if val is None:
                continue
            try:
                fval = float(val)
                if fval == fval:   # not NaN
                    eps = fval
                    break
            except (ValueError, TypeError):
                pass

        # Fallback: net income
        if eps is None:
            for key in (
                "Net Income From Continuing Operation Net Minority Interest",
                "Normalized Income",
                "Net Income From Continuing And Discontinued Operation",
            ):
                val = data.get(key)
                if val is None:
                    continue
                try:
                    fval = float(val)
                    if fval == fval:
                        eps = fval
                        break
                except (ValueError, TypeError):
                    pass

        profitable = bool(eps is not None and eps > 0)
        result[sym] = {
            "eps": round(eps, 2) if eps is not None else None,
            "profitable": profitable,
        }

    return result

def get_global_context(n_days: int = 7) -> dict:
    """
    Fetch global macro context from global_data table.
    Returns dict with per-ticker change% + interpretation string.

    Used by Agent Alpha to open every brief with global context:
    "DXY +0.8% (FII headwind) | Crude -2.1% (inflation easing) | Gold +1.2% (risk-off)"
    """
    conn = get_conn()

    # Get all tickers present in the table
    available = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM global_data"
    ).fetchall()]

    if not available:
        conn.close()
        return {"available": False, "summary": "global_data empty", "tickers": {}}

    # For each ticker: get latest N+5 days to compute window change
    results = {}
    for ticker in available:
        try:
            df = pd.read_sql(
                "SELECT date, close FROM global_data WHERE ticker = ? ORDER BY date DESC LIMIT ?",
                conn, params=(ticker, n_days + 5)
            )
            if df.empty or len(df) < 2:
                continue
            df = df.sort_values("date")
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.dropna(subset=["close"])
            if len(df) < 2:
                continue

            latest_close  = float(df["close"].iloc[-1])
            start_close   = float(df["close"].iloc[0])
            latest_date   = df["date"].iloc[-1]
            pct_chg       = ((latest_close / start_close) - 1) * 100 if start_close > 0 else 0.0

            # 1-day change
            pct_1d = ((df["close"].iloc[-1] / df["close"].iloc[-2]) - 1) * 100 if len(df) >= 2 else 0.0

            results[ticker] = {
                "latest_close": round(latest_close, 2),
                "latest_date":  latest_date,
                "pct_chg":      round(pct_chg, 2),
                "pct_1d":       round(pct_1d, 2),
            }
        except Exception:
            continue

    conn.close()

    if not results:
        return {"available": False, "summary": "No data parsed", "tickers": {}}

    # Build interpretation for key tickers
    interp = []

    dxy = results.get("DXY", {})
    if dxy:
        sign = "+" if dxy["pct_chg"] >= 0 else ""
        note = "FII headwind" if dxy["pct_chg"] > 0.5 else ("FII tailwind" if dxy["pct_chg"] < -0.5 else "neutral")
        interp.append(f"DXY {sign}{dxy['pct_chg']:.1f}% ({note})")

    crude = results.get("Crude Oil", {})
    if crude:
        sign = "+" if crude["pct_chg"] >= 0 else ""
        note = "inflation risk" if crude["pct_chg"] > 3 else ("relief" if crude["pct_chg"] < -3 else "stable")
        interp.append(f"Crude {sign}{crude['pct_chg']:.1f}% ({note})")

    gold = results.get("Gold", {})
    if gold:
        sign = "+" if gold["pct_chg"] >= 0 else ""
        note = "risk-off" if gold["pct_chg"] > 1 else ("risk-on" if gold["pct_chg"] < -1 else "neutral")
        interp.append(f"Gold {sign}{gold['pct_chg']:.1f}% ({note})")

    sp500 = results.get("S&P 500", {})
    if sp500:
        sign = "+" if sp500["pct_chg"] >= 0 else ""
        interp.append(f"S&P {sign}{sp500['pct_chg']:.1f}%")

    usdinr = results.get("USD/INR", {})
    if usdinr:
        sign = "+" if usdinr["pct_chg"] >= 0 else ""
        note = "rupee weak" if usdinr["pct_chg"] > 0.5 else ("rupee strong" if usdinr["pct_chg"] < -0.5 else "stable")
        interp.append(f"USD/INR {sign}{usdinr['pct_chg']:.1f}% ({note})")

    vix = results.get("India VIX", {})
    if vix:
        vix_val = vix["latest_close"]
        vix_note = "elevated fear" if vix_val > 20 else ("complacency" if vix_val < 12 else "normal")
        interp.append(f"VIX {vix_val:.1f} ({vix_note})")

    summary = " | ".join(interp) if interp else "Global data unavailable"

    return {
        "available": True,
        "summary":   summary,
        "tickers":   results,
        "n_days":    n_days,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EARNINGS ACCELERATION  (Phase 2.2)
# ═══════════════════════════════════════════════════════════════════════════════

def get_earnings_acceleration(symbols: list) -> dict:
    """
    Parse quarterly_income JSON and compute earnings acceleration.

    Uses yfinance income statement format (confirmed from DB probe):
      Primary:  'Diluted EPS'  — most populated field across all symbols
      Fallback: 'Net Income From Continuing Operation Net Minority Interest'
      Also:     'EBITDA' as secondary signal

    For each symbol, checks last 4 quarters. A stock is ACCELERATING if
    the latest Q-o-Q EPS growth > previous Q-o-Q growth by >2pp.

    Returns:
      {
        "TCS": {
          "accel":          True,
          "eps_q":          [34.1, 36.2, 37.8, 39.1],   # ascending
          "eps_growth_pct": [6.2, 4.4, 3.4],             # Q-o-Q %
          "pat_q":          [1.2e11, 1.3e11, ...],        # raw values
          "ebitda_q":       [...],
          "trend":          "ACCELERATING",
          "latest_eps":     39.1,
          "signal":         "EPS",                        # what we used
        },
        ...
      }
    """
    if not symbols:
        return {}

    conn = get_conn()
    placeholders = ",".join("?" * len(symbols))
    rows = conn.execute(
        f"""SELECT symbol, report_date, data_json
            FROM quarterly_income
            WHERE symbol IN ({placeholders})
            ORDER BY symbol, report_date ASC""",
        symbols
    ).fetchall()
    conn.close()

    if not rows:
        return {}

    from collections import defaultdict
    sym_rows = defaultdict(list)
    for sym, rdate, djson in rows:
        sym_rows[sym].append((rdate, djson))

    results = {}
    for sym, quarters in sym_rows.items():
        quarters = sorted(quarters, key=lambda x: x[0])[-4:]
        if len(quarters) < 3:
            results[sym] = {"trend": "INSUFFICIENT_DATA", "accel": False}
            continue

        eps_series    = []
        pat_series    = []
        ebitda_series = []

        for _, djson in quarters:
            try:
                if isinstance(djson, str):
                    try:
                        data = json.loads(djson)
                    except (ValueError, TypeError):
                        safe = (djson
                                .replace(": NaN",       ": null")
                                .replace(":NaN",        ":null")
                                .replace(": Infinity",  ": null")
                                .replace(":-Infinity",  ":null")
                                .replace(": -Infinity", ":null"))
                        try:
                            data = json.loads(safe)
                        except Exception:
                            data = {}
                else:
                    data = djson or {}
            except Exception:
                data = {}
        def _compute_accel(series, label):
            """Compute acceleration from a series of quarterly values."""
            valid = [(i, v) for i, v in enumerate(series) if v is not None]
            if len(valid) < 3:
                return None, None, None

            # Q-o-Q growth %
            growth = []
            for i in range(1, len(series)):
                a, b = series[i-1], series[i]
                if a is not None and b is not None and a != 0:
                    growth.append(round(((b / a) - 1) * 100, 1))
                else:
                    growth.append(None)

            valid_g = [g for g in growth if g is not None]
            if len(valid_g) < 2:
                return growth, "INSUFFICIENT_DATA", False

            latest_g = valid_g[-1]
            prev_g   = valid_g[-2]

            if latest_g > prev_g + 2:
                return growth, "ACCELERATING", True
            elif latest_g < prev_g - 2:
                return growth, "DECELERATING", False
            else:
                return growth, "STABLE", False

        # Try EPS first (most reliable), fallback to PAT, then EBITDA
        signal = None
        trend  = "INSUFFICIENT_DATA"
        accel  = False
        growth = []

        for series, label in [(eps_series, "EPS"), (pat_series, "PAT"), (ebitda_series, "EBITDA")]:
            g, t, a = _compute_accel(series, label)
            if t and t != "INSUFFICIENT_DATA":
                growth = g
                trend  = t
                accel  = a
                signal = label
                break

        results[sym] = {
            "accel":          accel,
            "trend":          trend,
            "signal":         signal or "NONE",
            "eps_q":          [round(v, 2) if v is not None else None for v in eps_series],
            "pat_q":          [round(v, 0) if v is not None else None for v in pat_series],
            "ebitda_q":       [round(v, 0) if v is not None else None for v in ebitda_series],
            "growth_pct":     growth,
            "latest_eps":     eps_series[-1] if eps_series else None,
        }

    return results


def clean_index_name(name: str) -> str:
    """Remove dated suffixes: 'NIFTY BANK 21 Apr 2026 (1)' → 'NIFTY BANK'"""
    if not isinstance(name, str):
        return str(name)
    name = re.sub(r'\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}(\s*\(\d+\))?\s*$', '', name)
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)
    return name.strip()


def is_etf(symbol: str) -> bool:
    s = symbol.upper()
    return any(p in s for p in ETF_PATTERNS)


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET SNAPSHOT QUERIES
# ═══════════════════════════════════════════════════════════════════════════════

def get_index_history(index_name: str, n_days: int = 60) -> pd.DataFrame:
    """Get N days of close/PE/PB for one index from market_snapshot."""
    conn = get_conn()
    df = pd.read_sql("""
        SELECT date, closing_index_value as close, change, pe, pb,
               points_change, volume, turnover_rs_cr
        FROM market_snapshot
        WHERE index_name = ?
        ORDER BY date DESC LIMIT ?
    """, conn, params=(index_name, n_days))
    conn.close()
    for col in ["close", "change", "pe", "pb", "points_change", "volume", "turnover_rs_cr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def get_all_indices_for_dates(dates: list) -> pd.DataFrame:
    """Get all index closes for given date list."""
    conn = get_conn()
    placeholders = ",".join(f"'{d}'" for d in dates)
    df = pd.read_sql(f"""
        SELECT index_name, date,
               AVG(CAST(closing_index_value AS REAL)) as close,
               AVG(CAST(pe AS REAL)) as pe,
               AVG(CAST(pb AS REAL)) as pb,
               AVG(CAST(change AS REAL)) as daily_change
        FROM market_snapshot
        WHERE date IN ({placeholders})
        GROUP BY index_name, date
        ORDER BY index_name, date
    """, conn)
    conn.close()
    df["index_name"] = df["index_name"].apply(clean_index_name)
    return df


def get_nifty50_history(n_days: int = 60) -> pd.DataFrame:
    return get_index_history("Nifty 50", n_days)


# ═══════════════════════════════════════════════════════════════════════════════
# INDEX CONSTITUENTS
# ═══════════════════════════════════════════════════════════════════════════════

def get_index_constituents(index_name: str, date_str: str = None) -> list:
    """
    Get list of symbols in an index from indices_data.
    Falls back to closest available date if exact date not found.
    Returns list of symbol strings.
    """
    conn = get_conn()

    # Try exact date first, else latest available
    if date_str:
        rows = conn.execute("""
            SELECT DISTINCT symbol FROM indices_data
            WHERE symbol IS NOT NULL
              AND (index_name = ? OR index_name LIKE ?)
              AND date = ?
        """, (index_name, f"{index_name}%", date_str)).fetchall()

        if not rows:
            # Fallback: latest date
            rows = conn.execute("""
                SELECT DISTINCT symbol FROM indices_data
                WHERE symbol IS NOT NULL
                  AND (index_name = ? OR index_name LIKE ?)
                  AND date = (SELECT MAX(date) FROM indices_data WHERE index_name LIKE ?)
            """, (index_name, f"{index_name}%", f"{index_name}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT DISTINCT symbol FROM indices_data
            WHERE symbol IS NOT NULL
              AND (index_name = ? OR index_name LIKE ?)
              AND date = (SELECT MAX(date) FROM indices_data WHERE index_name LIKE ?)
        """, (index_name, f"{index_name}%", f"{index_name}%")).fetchall()

    conn.close()
    return [r[0] for r in rows if r[0]]


def get_all_index_names() -> list:
    """Get all unique cleaned index names from indices_data."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT index_name FROM indices_data WHERE index_name IS NOT NULL"
    ).fetchall()
    conn.close()
    seen = set()
    result = []
    for (name,) in rows:
        cleaned = clean_index_name(name)
        if cleaned and cleaned not in seen and len(cleaned) > 3:
            seen.add(cleaned)
            result.append(cleaned)
    return sorted(result)


def get_index_stock_performance(index_name: str, dates: list) -> pd.DataFrame:
    """
    Get per-stock performance for all constituents of an index over given dates.
    Uses parquet files (fast) with fallback to stock_delivery.
    Returns DataFrame with columns: symbol, start_close, end_close, pct_chg,
                                     avg_deliv_pct, avg_volume, adv_days, total_days
    """
    symbols = get_index_constituents(index_name, dates[-1] if dates else None)
    if not symbols:
        return pd.DataFrame()

    start_d = dates[0]
    end_d   = dates[-1]
    sd = pd.to_datetime(start_d)
    ed = pd.to_datetime(end_d)
    years = list(range(sd.year, ed.year + 1))

    records = []
    for sym in symbols:
        if is_etf(sym):
            continue
        df = load_parquet_symbol(sym, years)
        if df.empty:
            continue
        df_win = df[(df["date"] >= sd) & (df["date"] <= ed)].copy()
        if len(df_win) < 2:
            continue

        close_col = next((c for c in df_win.columns if c.lower() in ("close",)), None)
        if not close_col:
            continue
        closes = pd.to_numeric(df_win[close_col], errors="coerce").dropna()
        if len(closes) < 2 or closes.iloc[0] <= 0:
            continue

        pct_chg = ((closes.iloc[-1] / closes.iloc[0]) - 1) * 100

        # Delivery
        deliv_col = next((c for c in df_win.columns
                          if "delivery_pct" in c.lower() or "deliv_per" in c.lower()), None)
        avg_deliv = float(pd.to_numeric(df_win[deliv_col], errors="coerce").mean()) \
            if deliv_col else None

        # Volume
        vol_col = next((c for c in df_win.columns if c.lower() == "volume"), None)
        avg_vol = float(pd.to_numeric(df_win[vol_col], errors="coerce").mean()) \
            if vol_col else 0

        # Turnover
        turn_col = next((c for c in df_win.columns if "turnover" in c.lower()), None)
        avg_turn = float(pd.to_numeric(df_win[turn_col], errors="coerce").mean()) \
            if turn_col else None

        adv_days = int((closes.diff() > 0).sum())

        records.append({
            "symbol":           sym,
            "start_close":      round(float(closes.iloc[0]), 2),
            "end_close":        round(float(closes.iloc[-1]), 2),
            "pct_chg":          round(pct_chg, 2),
            "avg_deliv_pct":    round(avg_deliv, 1) if avg_deliv is not None else None,
            "avg_volume":       int(avg_vol),
            "avg_turnover_lacs": round(avg_turn, 1) if avg_turn else None,
            "adv_days":         adv_days,
            "total_days":       len(closes),
        })

    if not records:
        return pd.DataFrame()

    df_out = pd.DataFrame(records).sort_values("pct_chg", ascending=False)
    return df_out.reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PARQUET LOADER
# ═══════════════════════════════════════════════════════════════════════════════

def load_parquet_symbol(symbol: str, years: list) -> pd.DataFrame:
    """
    Load parquet data for a symbol across given years.
    Prefers SYMBOL_YYYY.parquet (bhavcopy) over YYYY.parquet (yfinance).
    Returns normalised DataFrame with: date, open, high, low, close, volume,
                                        [delivery_pct / deliv_per], [turnover]
    """
    folder = PARQUET_ROOT / symbol
    if not folder.exists():
        return pd.DataFrame()

    frames = []
    for year in years:
        df = pd.DataFrame()
        for pf in [folder / f"{symbol}_{year}.parquet", folder / f"{year}.parquet"]:
            if pf.exists():
                try:
                    df = pd.read_parquet(pf)
                    break
                except Exception:
                    continue
        if df.empty:
            continue

        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

        # Ensure date column
        if "date" not in df.columns:
            if "date1" in df.columns:
                df["date"] = pd.to_datetime(df["date1"], errors="coerce")
            else:
                continue
        else:
            # Robust multi-format date parser
            # Handles: '2026-05-12' (ISO), ' 01-Apr-2026' (display+space),
            #          '12-May-2026' (display), mixed formats in same file
            def _parse_dates(series):
                import datetime as _dt
                fmts = ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y")
                def _one(v):
                    s = str(v).strip() if v is not None else ""
                    if not s or s in ("nan", "NaT", "None"):
                        return pd.NaT
                    for fmt in fmts:
                        try:
                            return _dt.datetime.strptime(s, fmt)
                        except ValueError:
                            pass
                    return pd.NaT
                return series.apply(_one)
            df["date"] = _parse_dates(df["date"])

        df = df.dropna(subset=["date"]).sort_values("date")

        # Normalise close column name
        for alias in ("close_price", "last_price", "ltp", "close"):
            if alias in df.columns and "close" not in df.columns:
                df.rename(columns={alias: "close"}, inplace=True)
                break

        # Normalise delivery pct
        for alias in ("delivery_pct", "deliv_per", "deliv_percent", "delivery_per"):
            if alias in df.columns and "delivery_pct" not in df.columns:
                df.rename(columns={alias: "delivery_pct"}, inplace=True)
                break

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return combined


def load_all_symbols_window(dates: list) -> pd.DataFrame:
    """
    Load ALL symbols from parquet for a given date window.
    Returns one row per symbol with aggregated stats.
    Used by Agent Beta for bulk screening.
    """
    start_d = dates[0]
    end_d   = dates[-1]
    sd = pd.to_datetime(start_d)
    ed = pd.to_datetime(end_d)
    years = list(range(sd.year, ed.year + 1))

    records = []
    count = 0
    if not PARQUET_ROOT.exists():
        print(f"[DataLayer] ERROR: PARQUET_ROOT does not exist: {PARQUET_ROOT}")
        return pd.DataFrame()
    sym_dirs = list(PARQUET_ROOT.iterdir())
    print(f"[DataLayer] Scanning {len(sym_dirs)} symbol dirs in {PARQUET_ROOT}")
    for sym_dir in sym_dirs:
        if not sym_dir.is_dir():
            continue
        sym = sym_dir.name
        if is_etf(sym):
            continue

        df = load_parquet_symbol(sym, years)
        if df.empty or "close" not in df.columns:
            continue

        df_win = df[(df["date"] >= sd) & (df["date"] <= ed)].copy()
        if len(df_win) < 2:
            continue

        closes = pd.to_numeric(df_win["close"], errors="coerce").dropna()
        if len(closes) < 2 or closes.iloc[0] <= MIN_PRICE:
            continue

        start_close = float(closes.iloc[0])
        end_close   = float(closes.iloc[-1])
        pct_chg     = ((end_close / start_close) - 1) * 100

        # Turnover filter
        if "turnover" in df_win.columns:
            avg_turn = float(pd.to_numeric(df_win["turnover"], errors="coerce").mean())
            if avg_turn < MIN_TURNOVER_LACS:
                continue
        else:
            avg_turn = None

        # Volume
        avg_vol = 0
        last_vol = 0
        if "volume" in df_win.columns:
            vols = pd.to_numeric(df_win["volume"], errors="coerce").dropna()
            avg_vol  = float(vols.mean()) if len(vols) > 0 else 0
            last_vol = float(vols.iloc[-1]) if len(vols) > 0 else 0

        vol_surge = (last_vol / avg_vol) if avg_vol > 0 else 0

        # Delivery
        avg_deliv = None
        if "delivery_pct" in df_win.columns:
            avg_deliv = float(pd.to_numeric(df_win["delivery_pct"], errors="coerce").mean())

        adv_days = int((closes.diff() > 0).sum())

        records.append({
            "symbol":           sym,
            "start_close":      round(start_close, 2),
            "end_close":        round(end_close, 2),
            "pct_chg":          round(pct_chg, 2),
            "avg_volume":       int(avg_vol),
            "avg_turnover_lacs": round(avg_turn, 1) if avg_turn else None,
            "avg_deliv_pct":    round(avg_deliv, 1) if avg_deliv is not None else None,
            "vol_surge_lastday": round(vol_surge, 2),
            "adv_days":         adv_days,
            "total_days":       len(closes),
        })
        count += 1

    print(f"[DataLayer] Loaded {count} symbols from parquet")
    return pd.DataFrame(records) if records else pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# FUNDAMENTALS
# ═══════════════════════════════════════════════════════════════════════════════

def get_fundamentals(symbols: list) -> pd.DataFrame:
    """Fetch PE, ROE, sector, beta, D/E for a list of symbols."""
    if not symbols:
        return pd.DataFrame()
    conn = get_conn()
    quoted = ",".join(f"'{s}'" for s in symbols)
    df = pd.read_sql(f"""
        SELECT symbol, sector, trailingPE as pe, returnOnEquity as roe,
               priceToBook as pb, debtToEquity as de, beta, marketCap,
               currentRatio, industry
        FROM stock_fundamentals
        WHERE symbol IN ({quoted})
    """, conn)
    conn.close()
    for col in ["pe", "roe", "pb", "de", "beta", "marketCap", "currentRatio"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_52w_extremes(symbols: list) -> pd.DataFrame:
    """
    Compute 52-week high and low for symbols from parquet.
    Returns DataFrame: symbol, high_52w, low_52w, current_price, pct_from_high, pct_from_low
    """
    if not symbols:
        return pd.DataFrame()

    cutoff = datetime.now() - timedelta(days=365)
    cur_year = datetime.now().year
    years = [cur_year - 1, cur_year]
    records = []

    for sym in symbols:
        df = load_parquet_symbol(sym, years)
        if df.empty or "close" not in df.columns:
            continue
        df_1y = df[df["date"] >= pd.Timestamp(cutoff)]
        if df_1y.empty:
            continue
        closes = pd.to_numeric(df_1y["close"], errors="coerce").dropna()
        if closes.empty:
            continue
        high = float(closes.max())
        low  = float(closes.min())
        cur  = float(closes.iloc[-1])
        records.append({
            "symbol":        sym,
            "high_52w":      round(high, 2),
            "low_52w":       round(low, 2),
            "current_price": round(cur, 2),
            "pct_from_high": round((cur / high - 1) * 100, 1),
            "pct_from_low":  round((cur / low  - 1) * 100, 1),
        })

    return pd.DataFrame(records) if records else pd.DataFrame()


def get_corporate_actions(start_date: str, end_date: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("""
        SELECT symbol, date, action_type, ratio, amount
        FROM corporate_actions
        WHERE date BETWEEN ? AND ?
        ORDER BY date, action_type
    """, conn, params=(start_date, end_date))
    conn.close()
    return df


def get_fii_dii_flow(dates: list) -> pd.DataFrame:
    """Get FII/DII EQ cash flow for given dates. Deduplicates pipeline re-inserts."""
    conn = get_conn()
    start_d = dates[0]
    end_d   = dates[-1]
    df = pd.read_sql("""
        SELECT date, participant,
               MAX(buy_value)  AS buy_value,
               MAX(sell_value) AS sell_value,
               MAX(net_value)  AS net_value
        FROM fii_dii_data
        WHERE segment = 'EQ'
          AND participant IN ('FII', 'DII')
          AND buy_value IS NOT NULL
          AND date BETWEEN ? AND ?
        GROUP BY date, participant
        ORDER BY date, participant
    """, conn, params=(start_d, end_d))
    conn.close()
    for col in ["buy_value", "sell_value", "net_value"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_fno_positioning() -> dict:
    """Get latest F&O positioning (stale after Jul 2024 — used as directional context)."""
    conn = get_conn()
    df = pd.read_sql("""
        SELECT date, participant, segment,
               SUM(net_contracts) AS net_contracts,
               SUM(net_value)     AS net_lot_value
        FROM fii_dii_data
        WHERE segment IN ('FUT_IDX', 'FUT_STK')
          AND participant IN ('FII', 'DII', 'Pro', 'Client')
          AND date = (SELECT MAX(date) FROM fii_dii_data WHERE segment='FUT_IDX')
        GROUP BY date, participant, segment
        ORDER BY participant, segment
    """, conn)
    conn.close()

    if df.empty:
        return {}

    fno_date = df["date"].iloc[0] if not df.empty else "N/A"
    positions = {}
    for _, row in df.iterrows():
        p = row["participant"]
        if p not in positions:
            positions[p] = {"net_contracts": 0}
        nc = int(row["net_contracts"] or 0)
        positions[p]["net_contracts"] += nc

    for p in positions:
        nc = positions[p]["net_contracts"]
        positions[p]["bias"] = "LONG" if nc > 0 else "SHORT" if nc < 0 else "NEUTRAL"

    return {"date": fno_date, "positions": positions, "note": "F&O stale post Jul 2024"}


# ═══════════════════════════════════════════════════════════════════════════════
# NEWS FETCHER — 4 FREE SOURCES
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_rss(url: str, max_items: int = 8, label: str = "") -> list:
    """Parse an RSS feed. Returns list of {title, link, published} dicts."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (MICC/2.0 NSE Research Bot)"}
        resp = requests.get(url, timeout=NEWS_TIMEOUT, headers=headers)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        results = []
        for item in items[:max_items]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            if title:
                results.append({"title": title, "link": link, "published": pub, "source": label})
        return results
    except Exception as e:
        print(f"[News] RSS fetch failed ({label}): {e}")
        return []


def _fetch_nse_announcements(max_items: int = 10) -> list:
    """
    Fetch NSE corporate announcements from their API.
    Free, no key needed. Returns recent company announcements.
    """
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        })
        # Hit NSE homepage first for cookies
        session.get("https://www.nseindia.com", timeout=NEWS_TIMEOUT)
        time.sleep(0.5)

        resp = session.get(
            "https://www.nseindia.com/api/corporate-announcements?index=equities",
            timeout=NEWS_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data[:max_items] if isinstance(data, list) else []:
            symbol = item.get("symbol", "")
            subject = item.get("subject", item.get("desc", ""))
            bcast = item.get("bcastDt", "")
            if subject:
                results.append({
                    "title":     f"[{symbol}] {subject}",
                    "link":      "",
                    "published": bcast,
                    "source":    "NSE Announcements",
                })
        return results
    except Exception as e:
        print(f"[News] NSE announcements failed: {e}")
        return []


def fetch_market_news(query: str = "", max_per_source: int = 6) -> list:
    """
    Fetch market news from 4 free sources:
    1. NSE Corporate Announcements (official)
    2. Moneycontrol RSS
    3. Economic Times Markets RSS
    4. Business Standard Markets RSS

    query: optional keyword to filter headlines (e.g. index/sector name)
    Returns list of {title, link, published, source} dicts, max ~24 items total.
    """
    all_news = []

    # Source 1: NSE Announcements
    nse = _fetch_nse_announcements(max_items=max_per_source + 4)
    all_news.extend(nse)

    # Source 2: Economic Times Markets RSS
    et_rss = _fetch_rss(
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        max_items=max_per_source,
        label="ET Markets"
    )
    all_news.extend(et_rss)

    # Source 3: Economic Times Stocks RSS
    et_stk = _fetch_rss(
        "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        max_items=max_per_source,
        label="ET Stocks"
    )
    all_news.extend(et_stk)

    # Source 4: Livemint Markets RSS
    mint_rss = _fetch_rss(
        "https://www.livemint.com/rss/markets",
        max_items=max_per_source,
        label="Livemint"
    )
    all_news.extend(mint_rss)

    # Source 5: The Hindu Business Line Markets RSS (clean XML, no bot block)
    hindu_rss = _fetch_rss(
        "https://www.thehindubusinessline.com/markets/feeder/default.rss",
        max_items=max_per_source,
        label="BusinessLine"
    )
    all_news.extend(hindu_rss)

    # Optional keyword filter
    if query:
        q_lower = query.lower()
        keywords = q_lower.replace("nifty ", "").replace(" index", "").split()
        filtered = [
            n for n in all_news
            if any(kw in n["title"].lower() for kw in keywords)
        ]
        # If filter yields too few, include general market news too
        if len(filtered) < 4:
            filtered = filtered + [n for n in all_news if n not in filtered][:6]
        return filtered[:max_per_source * 2]

    return all_news[:max_per_source * 4]


def fetch_sector_news(sector_or_index: str, max_items: int = 8) -> list:
    """Fetch news specifically about a sector or index."""
    return fetch_market_news(query=sector_or_index, max_per_source=max_items)


# ═══════════════════════════════════════════════════════════════════════════════
# LLM CALLER — Ollama → Groq (free) → local fallback
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_think(text: str) -> str:
    """Strip <think>...</think> blocks from LLM output (qwen3 / deepseek emit these)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def call_ollama(prompt: str, model: str = OLLAMA_MODEL,
                max_tokens: int = 800, timeout: int = OLLAMA_TIMEOUT) -> str:
    """Call local Ollama. Returns clean text or raises."""
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens, "think": False},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"]
    clean = _strip_think(raw)
    if not clean:
        raise ValueError("Empty response after think-strip")
    return clean



def call_groq(
    prompt: str,
    system: str = "You are a senior equity analyst at an institutional hedge fund.",
    max_tokens: int = 600,
    temperature: float = 0.25,
    retries: int = 3,
) -> str:
    """
    Call Groq llama-3.3-70b with exponential backoff.

    Improvements over original:
      - Retry up to `retries` times (default 3) with 2^n * 7s backoff
      - On HTTP 429 waits longer (quota reset window ~60s) before retrying
      - Hard timeout enforced per attempt (GROQ_TIMEOUT)
      - Falls through to Ollama on persistent 429 rather than raising
    """
    global _groq_last_call
    import time as _time
    # Enforce minimum spacing between consecutive calls
    gap = _time.time() - _groq_last_call
    if gap < GROQ_RATE_DELAY:
        _time.sleep(GROQ_RATE_DELAY - gap)

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    [
            {"role": "system",  "content": system},
            {"role": "user",    "content": prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }

    for attempt in range(retries):
        try:
            _groq_last_call = _time.time()
            resp = requests.post(
                GROQ_URL,
                headers=headers,
                json=payload,
                timeout=GROQ_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()

            if resp.status_code == 429:
                # Quota hit — wait longer on each attempt
                wait = (2 ** attempt) * 7 + 30   # 37s, 44s, 58s
                print(f"  [Groq] 429 rate-limit on attempt {attempt+1}, "
                      f"waiting {wait}s before retry...", flush=True)
                _time.sleep(wait)
                continue

            # Other HTTP error — raise so caller can fall back
            resp.raise_for_status()

        except requests.exceptions.Timeout:
            wait = (2 ** attempt) * 5
            print(f"  [Groq] timeout on attempt {attempt+1}, "
                  f"waiting {wait}s...", flush=True)
            _time.sleep(wait)
        except requests.exceptions.RequestException as e:
            print(f"  [Groq] request error: {e}", flush=True)
            break

    # All retries exhausted — fall back to Ollama
    print("  [Groq] all retries exhausted, falling back to Ollama", flush=True)
    return call_ollama(prompt, system=system, max_tokens=max_tokens)

def call_llm(prompt: str, max_tokens: int = 800, label: str = "",
             prefer_groq: bool = False) -> tuple[str, str]:
    """
    Smart LLM caller with fallback chain.
    Order:
      - If prefer_groq=True: Groq → Ollama → "LOCAL"
      - If prefer_groq=False: Ollama → Groq → "LOCAL"

    Returns: (response_text, source_used)
    source_used is one of: "Ollama", "Groq", "LOCAL"
    """
    tag = f"[LLM{' '+label if label else ''}]"

    if prefer_groq:
        # Groq first (faster for long detailed analysis)
        try:
            print(f"{tag} Calling Groq ({GROQ_MODEL})...")
            text = call_groq(prompt, max_tokens=max_tokens)
            print(f"{tag} Groq OK ({len(text)} chars)")
            return text, "Groq"
        except Exception as e:
            print(f"{tag} Groq failed: {e} → trying Ollama")

        try:
            print(f"{tag} Calling Ollama ({OLLAMA_MODEL})...")
            text = call_ollama(prompt, max_tokens=max_tokens)
            print(f"{tag} Ollama OK ({len(text)} chars)")
            return text, "Ollama"
        except Exception as e:
            print(f"{tag} Ollama failed: {e} → using local rules")

    else:
        # Ollama first (local, private)
        try:
            print(f"{tag} Calling Ollama ({OLLAMA_MODEL})...")
            text = call_ollama(prompt, max_tokens=max_tokens)
            print(f"{tag} Ollama OK ({len(text)} chars)")
            return text, "Ollama"
        except Exception as e:
            print(f"{tag} Ollama failed: {e} → trying Groq")

        try:
            print(f"{tag} Calling Groq ({GROQ_MODEL})...")
            text = call_groq(prompt, max_tokens=max_tokens)
            print(f"{tag} Groq OK ({len(text)} chars)")
            return text, "Groq"
        except Exception as e:
            print(f"{tag} Groq failed: {e} → using local rules")

    return "LOCAL_FALLBACK", "LOCAL"


def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to configured Telegram chat. Returns True on success.
    Retries once on HTTP 429 (rate limit) with a 3s back-off.
    Falls back to plain text if Markdown parse fails (400 error).
    """
    for attempt in range(2):
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
            }
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                return True
            if resp.status_code == 429:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 3))
                print(f"[Telegram] Rate limited — waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            if resp.status_code == 400 and parse_mode != "":
                # Markdown parse error — retry as plain text
                payload["parse_mode"] = ""
                resp2 = requests.post(url, json=payload, timeout=15)
                return resp2.status_code == 200
            print(f"[Telegram] HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            print(f"[Telegram] Send failed (attempt {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(2)
    return False


def send_telegram_chunks(text, max_len: int = 4000) -> bool:
    """Split long text into Telegram chunks and send all.
    Accepts str, list, or tuple. Chunks on newline boundaries.
    """
    # Defensive coerce: accept tuple/list/any -> str
    if isinstance(text, (list, tuple)):
        text = '\n'.join(str(x) for x in text)
    elif not isinstance(text, str):
        text = str(text) if text is not None else ''
    chunks = []
    while len(text) > max_len:
        sp = text.rfind("\n", 0, max_len)
        if sp == -1:
            sp = max_len
        chunks.append(text[:sp])
        text = text[sp:].lstrip()
    chunks.append(text)
    success = True
    for chunk in chunks:
        if not chunk.strip():
            continue
        if not send_telegram(chunk):
            success = False
        time.sleep(0.3)
    return success


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FORMATTERS
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_pct(val, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
        return f"{v:+.{decimals}f}%"
    except Exception:
        return "N/A"


def fmt_cr(val, decimals: int = 0) -> str:
    if val is None:
        return "N/A"
    try:
        v = float(val)
        return f"₹{v:+,.{decimals}f} Cr"
    except Exception:
        return "N/A"


def fmt_price(val, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    try:
        return f"₹{float(val):,.{decimals}f}"
    except Exception:
        return "N/A"


def now_ist() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y %H:%M IST")


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNALS HISTORY  (Phase 2.5)
# ═══════════════════════════════════════════════════════════════════════════════

def log_beta_signals(composite_df, run_date: str, regime: str = "") -> int:
    """
    Log Beta composite picks to signals_history table.

    Parameters
    ----------
    composite_df : pd.DataFrame
        The composite DataFrame from agent_beta (after all boosts applied).
        Expected columns: symbol, score, screens, pct_chg, avg_deliv_pct,
                          earnings_flag (optional).
    run_date : str
        ISO date string YYYY-MM-DD for today's run.
    regime : str
        Market regime string from Alpha (e.g. "bull", "bear", "sideways").

    Returns
    -------
    int
        Number of rows inserted (0 on failure or empty df).
    """
    if composite_df is None or composite_df.empty:
        return 0

    rows = []
    for _, r in composite_df.iterrows():
        rows.append((
            str(run_date),
            str(r.get("symbol", "")),
            int(r.get("score", 0)) if not _is_nan(r.get("score")) else None,
            str(r.get("screens", "")),
            float(r["pct_chg"])       if not _is_nan(r.get("pct_chg"))       else None,
            float(r["avg_deliv_pct"]) if not _is_nan(r.get("avg_deliv_pct")) else None,
            str(r.get("earnings_flag", "")) or None,
            str(regime) or None,
        ))

    if not rows:
        return 0

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.executemany(
            """INSERT OR IGNORE INTO signals_history
               (run_date, symbol, score, screen_tags, pct_chg, avg_deliv_pct,
                earnings_flag, regime)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows,
        )
        inserted = conn.execute(
            "SELECT changes()"
        ).fetchone()[0]
        conn.commit()
        conn.close()
        print(f"[signals_history] Logged {inserted} new rows for {run_date}")
        return inserted
    except Exception as e:
        print(f"[signals_history] log_beta_signals failed: {e}")
        return 0


def _is_nan(val) -> bool:
    """Safe NaN check that handles None, np.nan, and 'nan' strings."""
    if val is None:
        return True
    try:
        import math
        return math.isnan(float(val))
    except (TypeError, ValueError):
        return False


def get_signal_streak(symbols: list) -> dict:
    """
    For each symbol, count consecutive trading days it appeared in
    signals_history (streak = unbroken run ending on the most recent date).

    Returns
    -------
    dict  {symbol: streak_count}
        Only symbols with streak >= 1 are included.

    Notes
    -----
    Uses raw sqlite3 directly (Python 3.14 finally/conn safe).
    """
    if not symbols:
        return {}

    try:
        conn = sqlite3.connect(str(DB_PATH))

        # All distinct run_dates in table, sorted descending
        all_dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT run_date FROM signals_history ORDER BY run_date DESC"
        ).fetchall()]

        if not all_dates:
            conn.close()
            return {}

        # For each symbol: fetch which dates it appeared on
        placeholders = ",".join("?" * len(symbols))
        rows = conn.execute(
            f"SELECT symbol, run_date FROM signals_history WHERE symbol IN ({placeholders})",
            symbols,
        ).fetchall()
        conn.close()

    except Exception as e:
        print(f"[signals_history] get_signal_streak failed: {e}")
        return {}

    # Build symbol -> set of dates
    sym_dates: dict = {}
    for sym, dt in rows:
        sym_dates.setdefault(sym, set()).add(dt)

    # For each symbol: count consecutive tail ending at most recent date
    streaks = {}
    for sym in symbols:
        present = sym_dates.get(sym, set())
        streak = 0
        for dt in all_dates:          # descending order
            if dt in present:
                streak += 1
            else:
                break                 # streak broken
        if streak >= 1:
            streaks[sym] = streak

    return streaks


# ═══════════════════════════════════════════════════════════════════════════════
# REGIME-CONDITIONED THRESHOLDS  (Phase 2.6)
# ═══════════════════════════════════════════════════════════════════════════════

def get_regime_thresholds(regime: str = "") -> dict:
    """
    Return Beta screen thresholds conditioned on Alpha's market regime.

    Regimes (from compute_nifty_regime):
      TRENDING_UP     — bull run: relax filters, capture more momentum
      TRENDING_DOWN   — bear run: tighten hard, high-conviction only
      HIGH_VOLATILITY — spike: delivery focus, cut speculative noise
      CONSOLIDATION   — range-bound: delivery + consistency only
      MEAN_REVERTING  — mixed: default thresholds
      ""           — unknown/standalone: default thresholds

    Returns dict with keys:
      min_deliv_pct   float   delivery % threshold for accumulation screen
      min_vol_surge   float   volume surge multiple for breakout screen
      min_pct_chg     float   minimum % change required (momentum filter)
      min_adv_offset  int     added to (n_days-1) for consistency screen
      composite_weights dict  per-screen score weights
      regime_tag      str     short label for logging
    """
    r = (regime or "").upper().strip()

    if r == "TRENDING_UP":
        return {
            "min_deliv_pct":   45.0,   # relax — more stocks qualify
            "min_vol_surge":    1.5,   # lower bar — capture early breakouts
            "min_pct_chg":      0.5,   # allow modest gains too
            "min_adv_offset":  -1,     # n_days-2 advancing days OK
            "composite_weights": {"Momentum": 3, "Delivery": 3, "Breakout": 2, "Consistency": 2},
            "regime_tag": "BULL",
        }
    elif r == "TRENDING_DOWN":
        return {
            "min_deliv_pct":   65.0,   # must have strong institutional backing
            "min_vol_surge":    2.5,   # only very convincing breakouts
            "min_pct_chg":      1.5,   # ignore tiny bounces in downtrend
            "min_adv_offset":   0,     # need (n_days-1) advancing days = very consistent
            "composite_weights": {"Momentum": 2, "Delivery": 4, "Breakout": 2, "Consistency": 3},
            "regime_tag": "BEAR",
        }
    elif r == "HIGH_VOLATILITY":
        return {
            "min_deliv_pct":   70.0,   # only genuine buying survives vol spikes
            "min_vol_surge":    2.0,   # standard breakout bar
            "min_pct_chg":      1.0,   # filter noise
            "min_adv_offset":   0,     # standard consistency
            "composite_weights": {"Momentum": 2, "Delivery": 5, "Breakout": 1, "Consistency": 3},
            "regime_tag": "HVOL",
        }
    elif r == "CONSOLIDATION":
        return {
            "min_deliv_pct":   60.0,   # elevated — range-bound needs real buying
            "min_vol_surge":    2.0,   # standard
            "min_pct_chg":      0.3,   # small moves matter in consolidation
            "min_adv_offset":   0,     # consistency matters most
            "composite_weights": {"Momentum": 2, "Delivery": 3, "Breakout": 2, "Consistency": 4},
            "regime_tag": "CONS",
        }
    else:
        # MEAN_REVERTING, unknown, or standalone run
        return {
            "min_deliv_pct":   55.0,
            "min_vol_surge":    2.0,
            "min_pct_chg":      0.0,
            "min_adv_offset":   0,
            "composite_weights": {"Momentum": 3, "Delivery": 3, "Breakout": 2, "Consistency": 2},
            "regime_tag": "DEFAULT",
        }