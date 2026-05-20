# -*- coding: utf-8 -*-
"""
marketdb.py  —  MICC Data Pipeline Query API
=============================================
Clean, composable access to D:\\marketDB (SQLite + Parquet).
Import this from any script in D:\\MICC\\ or D:\\MICC\\data_pipeline\\

Usage:
    from marketdb import MarketDB
    db = MarketDB()

    # Stock prices (Parquet — fast)
    df  = db.get_stock("RELIANCE", last_n=252)
    wide = db.get_close_prices(["RELIANCE", "TCS", "INFY"], start="2026-01-01")
    px   = db.get_latest_price("HDFC")

    # Indices (SQLite)
    nifty = db.get_index("NIFTY 50", start="2026-01-01")
    names = db.list_indices()

    # FII/DII (SQLite)
    fii   = db.get_fiidii_net("FII", segment="EQ", last_n=30)
    pivot = db.get_fiidii_summary(start="2026-04-01")

    # F&O (SQLite — always filter by date, 144M rows)
    chain = db.get_fo("NIFTY", instrument="IDO", start="2026-05-09",
                      end="2026-05-09", option_typ="CE")
    oi    = db.get_fo_oi("NIFTY", instrument="IDO", start="2026-04-01")

    # Greeks + GEX (SQLite)
    gex   = db.get_gex("NIFTY", date="2026-05-09")
    greeks = db.get_greeks("NIFTY", date="2026-05-09")

    # Fundamentals (SQLite)
    fund  = db.get_fundamentals(["RELIANCE", "TCS"])

    # Delivery % (SQLite)
    deliv = db.get_delivery("RELIANCE", last_n=30)

    # US / India Macro (SQLite)
    gdp   = db.get_us_macro("GDP", last_n=20)
    cpi   = db.get_india_macro_fred("CPALTT01INM657N", last_n=24)

    # Health check
    db.summary()
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

# ── Paths (absolute — works from any CWD) ─────────────────────────────────────
DB_PATH    = Path(r"D:\marketDB\db\market.db")
STOCKS_DIR = Path(r"D:\marketDB\stocks\all")


class MarketDB:
    """
    Single entry point for all market database queries.
    Abstracts over SQLite tables and Parquet files.
    Thread-safe for reads (new connection per call).
    """

    def __init__(self, db_path: Path = None, stocks_dir: Path = None):
        self.db_path    = db_path    or DB_PATH
        self.stocks_dir = stocks_dir or STOCKS_DIR

    # ══════════════════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _conn(self) -> sqlite3.Connection:
        """Open a fresh read connection. Caller is responsible for closing."""
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA query_only=1")   # safety: read-only mode
        return conn

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        r = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return r is not None

    @staticmethod
    def _parse_dates(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
        """Coerce date column to datetime, drop nulls, sort."""
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df = df.dropna(subset=[col]).sort_values(col).reset_index(drop=True)
        return df

    def _read_parquets(self, folder: Path, years: list = None) -> pd.DataFrame:
        """Read one or more yearly Parquet files for a symbol."""
        if not folder.exists():
            return pd.DataFrame()
        files = sorted(folder.glob("*.parquet"))
        if not files:
            return pd.DataFrame()
        if years:
            files = [f for f in files
                     if f.stem.isdigit() and int(f.stem) in years]
        if not files:
            return pd.DataFrame()
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_parquet(f))
            except Exception:
                pass
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    @staticmethod
    def _year_range(start, end) -> list:
        s = (pd.to_datetime(start) if start else datetime(2000, 1, 1)).year
        e = (pd.to_datetime(end)   if end   else datetime.today()).year
        return list(range(s, e + 1))

    # ══════════════════════════════════════════════════════════════════════════
    # STOCKS  (Parquet — 5-10x faster than SQLite for OHLCV)
    # ══════════════════════════════════════════════════════════════════════════

    def get_stock(
        self,
        symbol: str,
        start:  str = None,
        end:    str = None,
        last_n: int = None,
    ) -> pd.DataFrame:
        """
        Daily OHLCV for one NSE stock from Parquet files.
        Args:
            symbol : NSE symbol, e.g. 'RELIANCE'
            start  : 'YYYY-MM-DD'  (inclusive)
            end    : 'YYYY-MM-DD'  (inclusive)
            last_n : last N rows (overrides start/end; smart year selection)
        Returns: DataFrame with columns date, open, high, low, close, volume
        """
        symbol = symbol.upper()
        folder = self.stocks_dir / symbol
        if not folder.exists():
            return pd.DataFrame()

        if last_n:
            # Need roughly last_n // 250 + 2 years
            years = [datetime.today().year - i for i in range(max(1, last_n // 200 + 2))]
        else:
            years = self._year_range(start, end)

        df = self._read_parquets(folder, years)
        if df.empty:
            return df

        # Normalise columns
        df.columns = [c.lower().strip() for c in df.columns]
        # date column aliases
        for alias in ("timestamp", "date1"):
            if alias in df.columns and "date" not in df.columns:
                df.rename(columns={alias: "date"}, inplace=True)
                break
        # close column aliases
        for alias in ("close_price", "last_price", "ltp"):
            if alias in df.columns and "close" not in df.columns:
                df.rename(columns={alias: "close"}, inplace=True)
                break

        df = self._parse_dates(df)

        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        if start:
            df = df[df["date"] >= pd.to_datetime(start)]
        if end:
            df = df[df["date"] <= pd.to_datetime(end)]
        return df.reset_index(drop=True)

    def get_close_prices(
        self,
        symbols: list,
        start:   str = None,
        end:     str = None,
        last_n:  int = None,
    ) -> pd.DataFrame:
        """
        Wide close-price matrix: index=date, columns=symbols.
        Useful for correlation, beta, portfolio calculations.
        """
        frames = {}
        for sym in symbols:
            df = self.get_stock(sym, start=start, end=end, last_n=last_n)
            if not df.empty and "close" in df.columns:
                frames[sym] = df.set_index("date")["close"]
        return pd.DataFrame(frames).sort_index() if frames else pd.DataFrame()

    def get_latest_price(self, symbol: str) -> dict:
        """Return most recent OHLCV row as dict."""
        df = self.get_stock(symbol, last_n=5)
        return df.iloc[-1].to_dict() if not df.empty else {}

    # ══════════════════════════════════════════════════════════════════════════
    # INDICES  (SQLite — indices_data)
    # ══════════════════════════════════════════════════════════════════════════

    def list_indices(self) -> list:
        """All distinct index names in indices_data."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT DISTINCT name FROM indices_data ORDER BY name"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_index(
        self,
        name:   str,
        start:  str = None,
        end:    str = None,
        last_n: int = None,
    ) -> pd.DataFrame:
        """
        OHLCV for a Nifty/BSE index by name.
        Tries exact match first, then case-insensitive fallback.
        """
        conn = self._conn()
        df = pd.read_sql(
            "SELECT * FROM indices_data WHERE name=? ORDER BY date",
            conn, params=(name,)
        )
        if df.empty:
            # Case-insensitive fallback
            all_names = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT name FROM indices_data"
                ).fetchall()
            ]
            match = next((n for n in all_names if n.lower() == name.lower()), None)
            if match:
                df = pd.read_sql(
                    "SELECT * FROM indices_data WHERE name=? ORDER BY date",
                    conn, params=(match,)
                )
        conn.close()

        if df.empty:
            return df

        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        if start:
            df = df[df["date"] >= pd.to_datetime(start)]
        if end:
            df = df[df["date"] <= pd.to_datetime(end)]
        return df.reset_index(drop=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FII / DII  (SQLite — fii_dii_data)
    # ══════════════════════════════════════════════════════════════════════════

    def get_fiidii(
        self,
        start:       str = None,
        end:         str = None,
        participant: str = None,
        segment:     str = None,
    ) -> pd.DataFrame:
        """
        Raw FII/DII data.
        participant : 'FII' | 'DII' | 'Pro' | 'Client'
        segment     : 'EQ' | 'FUT_IDX' | 'FUT_STK' | 'OPT_IDX' | 'OPT_STK'
        """
        q, params = "SELECT * FROM fii_dii_data WHERE 1=1", []
        if start:
            q += " AND date >= ?"; params.append(start)
        if end:
            q += " AND date <= ?"; params.append(end)
        if participant:
            q += " AND participant = ?"; params.append(participant)
        if segment:
            q += " AND segment = ?"; params.append(segment)
        q += " ORDER BY date"

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return self._parse_dates(df)

    def get_fiidii_net(
        self,
        participant: str = "FII",
        segment:     str = "EQ",
        start:       str = None,
        end:         str = None,
        last_n:      int = None,
    ) -> pd.DataFrame:
        """Simplified net flow: date, net_contracts, net_value."""
        df = self.get_fiidii(start=start, end=end,
                              participant=participant, segment=segment)
        if df.empty:
            return df
        df = df[["date", "net_contracts", "net_value"]].reset_index(drop=True)
        if last_n:
            df = df.tail(last_n).reset_index(drop=True)
        return df

    def get_fiidii_summary(self, start: str = None, end: str = None) -> pd.DataFrame:
        """Pivot: date vs FII/DII net_value — one row per date."""
        df = self.get_fiidii(start=start, end=end, segment="EQ")
        if df.empty:
            return df
        pivot = df.pivot_table(
            index="date", columns="participant",
            values="net_value", aggfunc="sum"
        ).reset_index()
        pivot.columns.name = None
        return pivot

    # ══════════════════════════════════════════════════════════════════════════
    # F&O  (SQLite — fo_data, 144M rows — ALWAYS filter by date)
    # ══════════════════════════════════════════════════════════════════════════

    def get_fo(
        self,
        symbol:     str,
        instrument: str = None,
        start:      str = None,
        end:        str = None,
        expiry:     str = None,
        option_typ: str = None,
        last_n:     int = None,
    ) -> pd.DataFrame:
        """
        F&O bhavcopy data.
        ALWAYS provide start (and ideally end) to avoid full table scan.
        instrument : 'IDO'/'OPTIDX' (index options) | 'STO'/'OPTSTK' (stock)
                     | 'FUTIDX' (index futures) | 'FUTSTK' (stock futures)
        option_typ : 'CE' | 'PE' | 'XX' (futures)
        """
        q, params = "SELECT * FROM fo_data WHERE symbol=?", [symbol.upper()]
        if instrument:
            q += " AND instrument=?";  params.append(instrument.upper())
        if start:
            q += " AND date>=?";       params.append(start)
        if end:
            q += " AND date<=?";       params.append(end)
        if expiry:
            q += " AND expiry=?";      params.append(expiry)
        if option_typ:
            q += " AND option_typ=?";  params.append(option_typ.upper())
        q += " ORDER BY date, expiry, strike"
        if last_n:
            q += f" LIMIT {int(last_n)}"

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        df = self._parse_dates(df)
        if "expiry" in df.columns:
            df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce")
        return df

    def get_fo_oi(
        self,
        symbol:     str,
        instrument: str = None,
        start:      str = None,
        end:        str = None,
    ) -> pd.DataFrame:
        """Aggregated open interest + contracts by date."""
        df = self.get_fo(symbol=symbol, instrument=instrument,
                         start=start, end=end)
        if df.empty:
            return df
        return (
            df.groupby("date")
              .agg(total_oi=("open_int", "sum"), total_contracts=("contracts", "sum"))
              .reset_index()
              .sort_values("date")
              .reset_index(drop=True)
        )

    def get_options_chain(self, symbol: str, date: str, expiry: str = None) -> pd.DataFrame:
        """
        Full options chain for one symbol on one date.
        Returns CE and PE rows with strike, OI, volume, close.
        """
        q = ("SELECT strike, option_typ, expiry, open_int, contracts, close, settle_pr "
             "FROM fo_data "
             "WHERE symbol=? AND instrument IN ('IDO','OPTIDX','OPTSTK','STO') "
             "AND date=? AND option_typ IN ('CE','PE')")
        params = [symbol.upper(), date]
        if expiry:
            q += " AND expiry=?"; params.append(expiry)
        q += " ORDER BY expiry, strike"

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    def get_fo_expiries(self, symbol: str) -> list:
        """All distinct expiry dates for a symbol."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT DISTINCT expiry FROM fo_data WHERE symbol=? ORDER BY expiry",
            (symbol.upper(),)
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    # ══════════════════════════════════════════════════════════════════════════
    # GREEKS + GAMMA EXPOSURE  (SQLite — option_greeks_raw, gamma_exposure_daily)
    # ══════════════════════════════════════════════════════════════════════════

    def get_greeks(
        self,
        symbol: str,
        date:   str,
        expiry: str = None,
    ) -> pd.DataFrame:
        """Option Greeks for one symbol on one date."""
        q = ("SELECT * FROM option_greeks_raw "
             "WHERE symbol=? AND date=?")
        params = [symbol.upper(), date]
        if expiry:
            q += " AND expiry=?"; params.append(expiry)
        q += " ORDER BY expiry, strike, option_type"

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    def get_gex(
        self,
        symbol: str,
        date:   str,
    ) -> pd.DataFrame:
        """
        Gamma Exposure (GEX) by strike for one symbol on one date.
        Returns strike, option_type, gamma_exposure, open_interest.
        """
        conn = self._conn()
        df = pd.read_sql(
            "SELECT strike, option_type, gamma_exposure, open_interest "
            "FROM gamma_exposure_daily "
            "WHERE symbol=? AND date=? "
            "ORDER BY strike",
            conn, params=(symbol.upper(), date)
        )
        conn.close()
        return df

    def get_gex_net(self, symbol: str, date: str) -> pd.DataFrame:
        """
        Net GEX per strike: CE GEX - PE GEX.
        Positive = dealers long gamma (stabilising).
        Negative = dealers short gamma (amplifying).
        """
        df = self.get_gex(symbol, date)
        if df.empty:
            return df
        ce = df[df["option_type"] == "CE"].set_index("strike")["gamma_exposure"]
        pe = df[df["option_type"] == "PE"].set_index("strike")["gamma_exposure"]
        net = (ce.subtract(pe, fill_value=0)).reset_index()
        net.columns = ["strike", "net_gex"]
        return net.sort_values("strike")

    # ══════════════════════════════════════════════════════════════════════════
    # FUNDAMENTALS  (SQLite — stock_fundamentals)
    # ══════════════════════════════════════════════════════════════════════════

    def get_fundamentals(self, symbols: list = None) -> pd.DataFrame:
        """
        TTM fundamentals for one or many symbols.
        Returns: symbol, sector, industry, marketCap, trailingPE, priceToBook,
                 dividendYield, beta, last_updated
        """
        if symbols:
            placeholders = ",".join("?" * len(symbols))
            q = (f"SELECT * FROM stock_fundamentals "
                 f"WHERE symbol IN ({placeholders})")
            params = [s.upper() for s in symbols]
        else:
            q, params = "SELECT * FROM stock_fundamentals", []

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    # ══════════════════════════════════════════════════════════════════════════
    # DELIVERY PERCENTAGE  (SQLite — stock_delivery)
    # ══════════════════════════════════════════════════════════════════════════

    def get_delivery(
        self,
        symbol: str = None,
        start:  str = None,
        end:    str = None,
        last_n: int = None,
    ) -> pd.DataFrame:
        """
        Delivery percentage data.
        If symbol is None, returns ALL symbols for the date range.
        """
        q, params = "SELECT * FROM stock_delivery WHERE 1=1", []
        if symbol:
            q += " AND symbol=?"; params.append(symbol.upper())
        if start:
            q += " AND date>=?";  params.append(start)
        if end:
            q += " AND date<=?";  params.append(end)
        q += " ORDER BY date"
        if last_n and symbol:
            q += f" LIMIT {int(last_n)}"

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return self._parse_dates(df)

    # ══════════════════════════════════════════════════════════════════════════
    # GLOBAL MACRO  (SQLite — global_data)
    # ══════════════════════════════════════════════════════════════════════════

    def get_global(
        self,
        ticker: str,
        start:  str = None,
        end:    str = None,
        last_n: int = None,
    ) -> pd.DataFrame:
        """
        Global market data (indices, commodities, forex, VIX).
        Known tickers: 'S&P 500', 'Dow Jones', 'Nasdaq', 'Gold',
                       'Crude Oil', 'USD/INR', 'DXY', 'India VIX'
        """
        q = "SELECT * FROM global_data WHERE ticker=? ORDER BY date"
        params = [ticker]
        if start:
            q = ("SELECT * FROM global_data WHERE ticker=? AND date>=? "
                 + ("AND date<=? " if end else "") + "ORDER BY date")
            params = [ticker, start] + ([end] if end else [])

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        return df

    def list_global_tickers(self) -> list:
        """All tickers in global_data."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM global_data ORDER BY ticker"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    # ══════════════════════════════════════════════════════════════════════════
    # US MACRO  (SQLite — us_macro_data)
    # ══════════════════════════════════════════════════════════════════════════

    def get_us_macro(self, series_id: str, last_n: int = None) -> pd.DataFrame:
        """
        US FRED macro series.
        series_id examples: 'GDP', 'CPIAUCSL', 'UNRATE', 'FEDFUNDS',
                            'DGS10', 'DGS2', 'VIXCLS', 'Term_Spread'
        """
        conn = self._conn()
        df = pd.read_sql(
            "SELECT date, value, frequency FROM us_macro_data "
            "WHERE series_id=? ORDER BY date",
            conn, params=(series_id,)
        )
        conn.close()
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        return df

    def list_us_macro_series(self) -> list:
        conn = self._conn()
        rows = conn.execute(
            "SELECT DISTINCT series_id FROM us_macro_data ORDER BY series_id"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    # ══════════════════════════════════════════════════════════════════════════
    # INDIA MACRO  (SQLite — india_macro_fred + world_bank_macro)
    # ══════════════════════════════════════════════════════════════════════════

    def get_india_macro_fred(self, series_id: str, last_n: int = None) -> pd.DataFrame:
        """India FRED macro series (CPI, forex reserves, exports, imports, 10Y)."""
        conn = self._conn()
        df = pd.read_sql(
            "SELECT date, value, frequency FROM india_macro_fred "
            "WHERE series_id=? ORDER BY date",
            conn, params=(series_id,)
        )
        conn.close()
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        return df

    def get_world_bank(self, indicator_code: str) -> pd.DataFrame:
        """Annual World Bank India indicators (GDP growth, CPI, trade, etc.)."""
        conn = self._conn()
        df = pd.read_sql(
            "SELECT date, value, indicator_name FROM world_bank_macro "
            "WHERE indicator_code=? ORDER BY date",
            conn, params=(indicator_code,)
        )
        conn.close()
        return self._parse_dates(df)

    # ══════════════════════════════════════════════════════════════════════════
    # MUTUAL FUNDS  (SQLite — mf_nav_history)
    # ══════════════════════════════════════════════════════════════════════════

    def get_mf_nav(self, scheme_code: int = None, last_n: int = None) -> pd.DataFrame:
        """Mutual fund NAV history. scheme_code=None returns latest NAV for all funds."""
        if scheme_code:
            q = ("SELECT scheme_code, scheme_name, date, nav "
                 "FROM mf_nav_history WHERE scheme_code=? ORDER BY date")
            params = (scheme_code,)
        else:
            # Latest NAV for every fund
            q = ("SELECT scheme_code, scheme_name, date, nav "
                 "FROM mf_nav_history "
                 "WHERE date = (SELECT MAX(date) FROM mf_nav_history) "
                 "ORDER BY scheme_name")
            params = ()

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        df = self._parse_dates(df)
        if last_n and scheme_code:
            return df.tail(last_n).reset_index(drop=True)
        return df

    # ══════════════════════════════════════════════════════════════════════════
    # CORPORATE EVENTS  (SQLite)
    # ══════════════════════════════════════════════════════════════════════════

    def get_corporate_actions(
        self,
        symbols:     list = None,
        start:       str  = None,
        end:         str  = None,
        action_type: str  = None,  # 'SPLIT' | 'DIVIDEND'
    ) -> pd.DataFrame:
        """Splits and dividends."""
        q, params = "SELECT * FROM corporate_actions WHERE 1=1", []
        if symbols:
            ph = ",".join("?" * len(symbols))
            q += f" AND symbol IN ({ph})"; params.extend([s.upper() for s in symbols])
        if start:
            q += " AND date>=?"; params.append(start)
        if end:
            q += " AND date<=?"; params.append(end)
        if action_type:
            q += " AND action_type=?"; params.append(action_type.upper())
        q += " ORDER BY date DESC"

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return self._parse_dates(df)

    def get_insider_trading(
        self,
        symbols: list = None,
        start:   str  = None,
        end:     str  = None,
    ) -> pd.DataFrame:
        """Insider trading (SEBI filings)."""
        q, params = "SELECT * FROM insider_trading WHERE 1=1", []
        if symbols:
            ph = ",".join("?" * len(symbols))
            q += f" AND symbol IN ({ph})"; params.extend([s.upper() for s in symbols])
        if start:
            q += " AND filing_date>=?"; params.append(start)
        if end:
            q += " AND filing_date<=?"; params.append(end)
        q += " ORDER BY filing_date DESC"

        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTRY & SEARCH
    # ══════════════════════════════════════════════════════════════════════════

    def list_symbols(self, active_only: bool = True) -> list:
        """All NSE symbols from stock_registry."""
        conn = self._conn()
        if active_only:
            rows = conn.execute(
                "SELECT symbol FROM stock_registry WHERE is_active=1 ORDER BY symbol"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT symbol FROM stock_registry ORDER BY symbol"
            ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def list_tradable(self) -> list:
        """The clean 2388-symbol EQ universe (no ETFs/MFs)."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT symbol FROM tradable_eq_stocks ORDER BY symbol"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def search_symbol(self, query: str) -> pd.DataFrame:
        """Search registry by symbol or company name (case-insensitive)."""
        q = query.upper()
        conn = self._conn()
        df = pd.read_sql(
            "SELECT symbol, company_name, is_active FROM stock_registry "
            "WHERE UPPER(symbol) LIKE ? OR UPPER(company_name) LIKE ? "
            "ORDER BY is_active DESC, symbol",
            conn, params=(f"%{q}%", f"%{q}%")
        )
        conn.close()
        return df

    # ══════════════════════════════════════════════════════════════════════════
    # HEALTH SUMMARY
    # ══════════════════════════════════════════════════════════════════════════

    def summary(self):
        """Print a quick health report for all major tables."""
        conn = self._conn()

        def row_count(table: str) -> str:
            if not self._table_exists(conn, table):
                return "TABLE MISSING"
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            return f"{n:,}"

        def max_date(table: str, col: str = "date") -> str:
            if not self._table_exists(conn, table):
                return "N/A"
            r = conn.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
            return r or "N/A"

        print("=" * 65)
        print("  MarketDB — Summary")
        print("=" * 65)
        stock_dirs = sum(
            1 for d in self.stocks_dir.iterdir()
            if d.is_dir() and any(d.glob("*.parquet"))
        ) if self.stocks_dir.exists() else 0
        print(f"  Parquet symbols     : {stock_dirs:,}")
        print(f"  indices_data        : {row_count('indices_data'):>12}  latest: {max_date('indices_data')}")
        print(f"  fo_data             : {row_count('fo_data'):>12}  latest: {max_date('fo_data')}")
        print(f"  fii_dii_data        : {row_count('fii_dii_data'):>12}  latest: {max_date('fii_dii_data')}")
        print(f"  stock_delivery      : {row_count('stock_delivery'):>12}  latest: {max_date('stock_delivery')}")
        print(f"  global_data         : {row_count('global_data'):>12}  latest: {max_date('global_data')}")
        print(f"  option_greeks_raw   : {row_count('option_greeks_raw'):>12}  latest: {max_date('option_greeks_raw')}")
        print(f"  gamma_exposure_daily: {row_count('gamma_exposure_daily'):>12}  latest: {max_date('gamma_exposure_daily')}")
        print(f"  us_macro_data       : {row_count('us_macro_data'):>12}  latest: {max_date('us_macro_data')}")
        print(f"  stock_fundamentals  : {row_count('stock_fundamentals'):>12}  latest: {max_date('stock_fundamentals', 'last_updated')}")
        print(f"  mf_nav_history      : {row_count('mf_nav_history'):>12}  latest: {max_date('mf_nav_history')}")
        print(f"  insider_trading     : {row_count('insider_trading'):>12}  latest: {max_date('insider_trading', 'filing_date')}")
        print(f"  tradable_eq_stocks  : {row_count('tradable_eq_stocks'):>12}")
        print("=" * 65)
        conn.close()


# ── Quick test when run directly ──────────────────────────────────────────────
if __name__ == "__main__":
    db = MarketDB()
    db.summary()
    print()
    print("Testing get_stock('RELIANCE', last_n=3):")
    print(db.get_stock("RELIANCE", last_n=3))
    print()
    print("Testing get_index('NIFTY 50', last_n=3):")
    print(db.get_index("NIFTY 50", last_n=3))
    print()
    print("Testing get_fiidii_net('FII', segment='EQ', last_n=5):")
    print(db.get_fiidii_net("FII", segment="EQ", last_n=5))
