# -*- coding: utf-8 -*-
"""
fetch_global_indices_v2.py  —  MICC Advanced Global Index Fetcher
==================================================================
Fetches 40+ global indices / commodities / FX / rates / crypto
from MULTIPLE FREE SOURCES with automatic fallback:
  Source 1: yfinance  (primary)
  Source 2: investpy  (fallback — pip install investpy)
  Source 3: pandas_datareader / FRED (rates & macro)
  Source 4: manual CSV from stooq.com (last resort)

Features:
  - 40+ symbols: equity indices, commodities, FX, rates, crypto, volatility
  - Full backfill mode (--full) or incremental (--incremental, default)
  - Polite delays between requests (no bans)
  - Never crashes — every error is caught and logged, script continues
  - Live terminal progress with ETA, success/fail counts
  - Saves to global_indices_daily table (same schema as before)
  - After fetch: shows a neat summary table of coverage per symbol

Run:
  py D:\\MICC\\fetch_global_indices_v2.py               # incremental
  py D:\\MICC\\fetch_global_indices_v2.py --full        # full backfill
  py D:\\MICC\\fetch_global_indices_v2.py --verify      # just show coverage
  py D:\\MICC\\fetch_global_indices_v2.py --sym SPX     # single symbol only
"""

import os, sys, time, sqlite3, warnings, traceback
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

# ── SSL fix ───────────────────────────────────────────────────────────────────
try:
    import certifi
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    os.environ["SSL_CERT_FILE"]      = certifi.where()
    os.environ["CURL_CA_BUNDLE"]     = certifi.where()
except ImportError:
    pass

import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")

# ── Delay config (seconds) ────────────────────────────────────────────────────
DELAY_BETWEEN   = 3.5   # between each symbol
DELAY_ON_RETRY  = 8.0   # after a source fails before trying next
DELAY_RATE_LIMIT= 30.0  # if we see 429 / rate limit

# ── Universe: (micc_symbol, yf_ticker, display_name, category) ────────────────
# 40+ symbols across all asset classes
UNIVERSE = [
    # ── EQUITY INDICES — USA ──────────────────────────────────────────────────
    ("SPX",         "^GSPC",      "S&P 500",              "equity_us"),
    ("NDX",         "^NDX",       "Nasdaq 100",           "equity_us"),
    ("DJIA",        "^DJI",       "Dow Jones",            "equity_us"),
    ("RUT",         "^RUT",       "Russell 2000",         "equity_us"),
    ("SP500VIX",    "^VIX",       "CBOE VIX",             "volatility"),

    # ── EQUITY INDICES — INDIA ────────────────────────────────────────────────
    ("NIFTY50",     "^NSEI",      "Nifty 50",             "equity_india"),
    ("NIFTYBANK",   "^NSEBANK",   "Nifty Bank",           "equity_india"),
    ("SENSEX",      "^BSESN",     "BSE Sensex",           "equity_india"),
    ("NIFTYIT",     "^CNXIT",     "Nifty IT",             "equity_india"),
    ("NIFTYMID100", "^NSEMDCP50", "Nifty Midcap 50",      "equity_india"),
    ("NIFTYFMCG",   "^CNXFMCG",   "Nifty FMCG",           "equity_india"),
    ("NIFTYAUTO",   "^CNXAUTO",   "Nifty Auto",           "equity_india"),
    ("INDIAVIX",    "^INDIAVIX",  "India VIX",            "volatility"),

    # ── EQUITY INDICES — EUROPE ───────────────────────────────────────────────
    ("DAX",         "^GDAXI",     "DAX (Germany)",        "equity_eu"),
    ("FTSE100",     "^FTSE",      "FTSE 100 (UK)",        "equity_eu"),
    ("CAC40",       "^FCHI",      "CAC 40 (France)",      "equity_eu"),
    ("EUROSTOXX50", "^STOXX50E",  "Euro Stoxx 50",        "equity_eu"),
    ("AEX",         "^AEX",       "AEX (Netherlands)",    "equity_eu"),
    ("SMI",         "^SSMI",      "SMI (Switzerland)",    "equity_eu"),
    ("IBEX35",      "^IBEX",      "IBEX 35 (Spain)",      "equity_eu"),
    ("MIB",         "FTSEMIB.MI", "FTSE MIB (Italy)",     "equity_eu"),

    # ── EQUITY INDICES — ASIA PACIFIC ─────────────────────────────────────────
    ("Nikkei225",   "^N225",      "Nikkei 225 (Japan)",   "equity_apac"),
    ("HangSeng",    "^HSI",       "Hang Seng (HK)",       "equity_apac"),
    ("Shanghai",    "000001.SS",  "Shanghai Comp",        "equity_apac"),
    ("CSI300",      "000300.SS",  "CSI 300 (China)",      "equity_apac"),
    ("Kospi",       "^KS11",      "KOSPI (Korea)",        "equity_apac"),
    ("ASX200",      "^AXJO",      "ASX 200 (Australia)",  "equity_apac"),
    ("Taiwan",      "^TWII",      "Taiwan Weighted",      "equity_apac"),
    ("Straits",     "^STI",       "Straits Times (SG)",   "equity_apac"),
    ("Jakarta",     "^JKSE",      "Jakarta Comp (ID)",    "equity_apac"),
    ("Bovespa",     "^BVSP",      "Bovespa (Brazil)",     "equity_latam"),
    ("IPC",         "^MXX",       "IPC (Mexico)",         "equity_latam"),

    # ── COMMODITIES ───────────────────────────────────────────────────────────
    ("Gold",        "GC=F",       "Gold Futures",         "commodity"),
    ("Silver",      "SI=F",       "Silver Futures",       "commodity"),
    ("CrudeWTI",    "CL=F",       "Crude Oil WTI",        "commodity"),
    ("BrentCrude",  "BZ=F",       "Brent Crude",          "commodity"),
    ("NatGas",      "NG=F",       "Natural Gas",          "commodity"),
    ("Copper",      "HG=F",       "Copper",               "commodity"),
    ("Wheat",       "ZW=F",       "Wheat Futures",        "commodity"),
    ("Palladium",   "PA=F",       "Palladium",            "commodity"),

    # ── CURRENCIES / FX ───────────────────────────────────────────────────────
    ("DXY",         "DX-Y.NYB",   "USD Index (DXY)",      "fx"),
    ("USDINR",      "USDINR=X",   "USD/INR",              "fx"),
    ("EURUSD",      "EURUSD=X",   "EUR/USD",              "fx"),
    ("USDJPY",      "USDJPY=X",   "USD/JPY",              "fx"),
    ("GBPUSD",      "GBPUSD=X",   "GBP/USD",              "fx"),
    ("USDCNY",      "CNY=X",      "USD/CNY",              "fx"),
    ("USDBRL",      "BRL=X",      "USD/BRL",              "fx"),

    # ── US RATES ──────────────────────────────────────────────────────────────
    ("US10Y",       "^TNX",       "US 10Y Yield",         "rates"),
    ("US2Y",        "^IRX",       "US 2Y Yield",          "rates"),
    ("US30Y",       "^TYX",       "US 30Y Yield",         "rates"),

    # ── CRYPTO ────────────────────────────────────────────────────────────────
    ("Bitcoin",     "BTC-USD",    "Bitcoin",              "crypto"),
    ("Ethereum",    "ETH-USD",    "Ethereum",             "crypto"),
]

TOTAL = len(UNIVERSE)

# ─────────────────────────────────────────────────────────────────────────────
# TERMINAL DISPLAY
# ─────────────────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
BLUE   = "\033[94m"
MAGENTA= "\033[95m"

CAT_COLOR = {
    "equity_us":    BLUE,
    "equity_india": GREEN,
    "equity_eu":    CYAN,
    "equity_apac":  MAGENTA,
    "equity_latam": YELLOW,
    "commodity":    YELLOW,
    "fx":           CYAN,
    "rates":        DIM,
    "volatility":   RED,
    "crypto":       MAGENTA,
}

def now():
    return datetime.now().strftime("%H:%M:%S")

def log(msg, level="INFO", end="\n"):
    tag = {
        "OK":   f"{GREEN} OK {RESET}",
        "FAIL": f"{RED}FAIL{RESET}",
        "WARN": f"{YELLOW}WARN{RESET}",
        "SKIP": f"{DIM}SKIP{RESET}",
        "INFO": f"{CYAN}INFO{RESET}",
        "HEAD": f"{BOLD}{BLUE}===={RESET}",
    }.get(level, f"{CYAN}INFO{RESET}")
    print(f"  [{now()}] [{tag}]  {msg}", flush=True, end=end)

def progress_bar(done, total, width=30):
    filled = int(width * done / max(total, 1))
    bar    = "█" * filled + "░" * (width - filled)
    pct    = 100 * done / max(total, 1)
    return f"[{bar}] {pct:5.1f}%  {done}/{total}"

def print_header(title):
    print(f"\n{BOLD}{BLUE}{'='*65}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'='*65}{RESET}\n")

def print_section(title):
    print(f"\n{BOLD}{CYAN}  ── {title} {'─'*(55-len(title))}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS global_indices_daily (
            symbol     TEXT NOT NULL,
            date       TEXT NOT NULL,
            open       REAL,
            high       REAL,
            low        REAL,
            close      REAL,
            volume     REAL,
            pct_change REAL,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gid_sym  ON global_indices_daily(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gid_date ON global_indices_daily(date)")
    conn.commit()

def get_latest_date(conn, symbol):
    row = conn.execute(
        "SELECT MAX(date) FROM global_indices_daily WHERE symbol=?", (symbol,)
    ).fetchone()
    return row[0] if row and row[0] else None

def get_row_count(conn, symbol):
    row = conn.execute(
        "SELECT COUNT(*) FROM global_indices_daily WHERE symbol=?", (symbol,)
    ).fetchone()
    return row[0] if row else 0

def upsert(conn, df):
    if df is None or df.empty:
        return 0
    rows = []
    for _, r in df.iterrows():
        cl = r.get("close")
        if cl != cl or cl is None:  # skip NaN
            continue
        rows.append((
            str(r["symbol"]), str(r["date"]),
            float(r["open"])       if r.get("open")   == r.get("open")   else None,
            float(r["high"])       if r.get("high")   == r.get("high")   else None,
            float(r["low"])        if r.get("low")    == r.get("low")    else None,
            float(cl),
            float(r["volume"])     if r.get("volume") == r.get("volume") else 0.0,
            float(r["pct_change"]) if r.get("pct_change") == r.get("pct_change") else None,
        ))
    if not rows:
        return 0
    conn.executemany("""
        INSERT OR REPLACE INTO global_indices_daily
            (symbol, date, open, high, low, close, volume, pct_change)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1: yfinance
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yfinance(micc_sym, yf_ticker, start, end):
    try:
        import yfinance as yf
        t  = yf.Ticker(yf_ticker)
        df = t.history(start=start, end=end, auto_adjust=True, timeout=20)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        date_col = "date" if "date" in df.columns else "datetime"
        df["date"]   = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
        df["symbol"] = micc_sym
        for c in ["open","high","low","close"]:
            if c not in df.columns: df[c] = None
        if "volume" not in df.columns: df["volume"] = 0
        df = df.sort_values("date").reset_index(drop=True)
        df["pct_change"] = (df["close"].pct_change() * 100).round(4)
        return df[["symbol","date","open","high","low","close","volume","pct_change"]]
    except Exception as e:
        raise RuntimeError(f"yfinance: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2: stooq (free CSV download, no API key)
# ─────────────────────────────────────────────────────────────────────────────

# stooq ticker map (only symbols that differ from yfinance)
STOOQ_MAP = {
    "SPX":       "^spx",
    "NDX":       "^ndx",
    "DJIA":      "^dji",
    "RUT":       "^rut",
    "SP500VIX":  "^vix",
    "DAX":       "^dax",
    "FTSE100":   "^ftse",
    "CAC40":     "^cac",
    "Nikkei225": "^nkx",
    "HangSeng":  "^hsi",
    "Kospi":     "^kospi",
    "ASX200":    "^asx",
    "Gold":      "xauusd",
    "Silver":    "xagusd",
    "CrudeWTI":  "cl.f",
    "DXY":       "dxy",
    "EURUSD":    "eurusd",
    "USDJPY":    "usdjpy",
    "GBPUSD":    "gbpusd",
    "US10Y":     "10ustb.b",
    "Bitcoin":   "btc.v",
}

def fetch_stooq(micc_sym, start, end):
    try:
        import pandas_datareader.data as web
        stooq_sym = STOOQ_MAP.get(micc_sym)
        if not stooq_sym:
            raise RuntimeError("no stooq mapping")
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt   = datetime.strptime(end,   "%Y-%m-%d")
        df = web.DataReader(stooq_sym, "stooq", start_dt, end_dt)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df["date"]       = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["symbol"]     = micc_sym
        df               = df.sort_values("date").reset_index(drop=True)
        df["pct_change"] = (df["close"].pct_change() * 100).round(4)
        if "volume" not in df.columns: df["volume"] = 0
        return df[["symbol","date","open","high","low","close","volume","pct_change"]]
    except Exception as e:
        raise RuntimeError(f"stooq: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 3: FRED (for US rates via pandas_datareader)
# ─────────────────────────────────────────────────────────────────────────────

FRED_MAP = {
    "US10Y": "DGS10",
    "US2Y":  "DGS2",
    "US30Y": "DGS30",
}

def fetch_fred(micc_sym, start, end):
    try:
        import pandas_datareader.data as web
        fred_sym = FRED_MAP.get(micc_sym)
        if not fred_sym:
            raise RuntimeError("no FRED mapping")
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt   = datetime.strptime(end,   "%Y-%m-%d")
        df = web.DataReader(fred_sym, "fred", start_dt, end_dt)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        date_col = [c for c in df.columns if "date" in c][0]
        df["date"]       = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
        df["close"]      = df[fred_sym.lower()]
        df["symbol"]     = micc_sym
        df["open"] = df["high"] = df["low"] = df["close"]
        df["volume"]     = 0
        df               = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        df["pct_change"] = (df["close"].pct_change() * 100).round(4)
        return df[["symbol","date","open","high","low","close","volume","pct_change"]]
    except Exception as e:
        raise RuntimeError(f"FRED: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 4: yfinance download (bulk, different API path)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yfinance_download(micc_sym, yf_ticker, start, end):
    try:
        import yfinance as yf
        df = yf.download(yf_ticker, start=start, end=end,
                         auto_adjust=True, progress=False, timeout=20)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        df.columns = [str(c[0]).lower() if isinstance(c, tuple) else str(c).lower()
                      for c in df.columns]
        date_col = "date" if "date" in df.columns else "datetime"
        df["date"]       = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
        df["symbol"]     = micc_sym
        for c in ["open","high","low","close"]:
            if c not in df.columns: df[c] = None
        if "volume" not in df.columns: df["volume"] = 0
        df               = df.sort_values("date").reset_index(drop=True)
        df["pct_change"] = (df["close"].pct_change() * 100).round(4)
        return df[["symbol","date","open","high","low","close","volume","pct_change"]]
    except Exception as e:
        raise RuntimeError(f"yf.download: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SOURCE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def fetch_with_fallback(micc_sym, yf_ticker, start, end, verbose=True):
    """
    Try each source in order. Return (df, source_name) or (None, None).
    Never raises — all errors are caught and logged.
    """
    sources = [
        ("yfinance.Ticker",   lambda: fetch_yfinance(micc_sym, yf_ticker, start, end)),
        ("yfinance.download", lambda: fetch_yfinance_download(micc_sym, yf_ticker, start, end)),
        ("stooq",             lambda: fetch_stooq(micc_sym, start, end)),
        ("FRED",              lambda: fetch_fred(micc_sym, start, end)),
    ]

    for src_name, fn in sources:
        try:
            df = fn()
            if df is not None and not df.empty and len(df) > 0:
                return df, src_name
            # empty result — try next
            if verbose:
                log(f"  {src_name}: empty result, trying next…", "WARN")
        except Exception as e:
            msg = str(e)[:80]
            if "429" in msg or "rate limit" in msg.lower() or "Too Many" in msg:
                if verbose:
                    log(f"  {src_name}: RATE LIMIT — waiting {DELAY_RATE_LIMIT}s…", "WARN")
                time.sleep(DELAY_RATE_LIMIT)
            else:
                if verbose:
                    log(f"  {src_name}: {msg}", "WARN")
            time.sleep(DELAY_ON_RETRY)

    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FETCH LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run(mode="incremental", single_sym=None):
    print_header("MICC — Advanced Global Index Fetcher v2")

    conn = get_conn()
    ensure_table(conn)

    # Filter universe
    universe = [u for u in UNIVERSE if single_sym is None or u[0].upper() == single_sym.upper()]
    if not universe:
        log(f"Symbol '{single_sym}' not found in universe.", "WARN")
        conn.close(); return

    total   = len(universe)
    ok_syms = []
    fail_syms = []
    skip_syms = []

    full_start = "2000-01-01"
    today_str  = datetime.today().strftime("%Y-%m-%d")
    tomorrow   = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    print_section(f"Mode: {mode.upper()} | Symbols: {total} | DB: {DB_PATH.name}")
    print(f"  {DIM}Delays: {DELAY_BETWEEN}s between symbols, {DELAY_ON_RETRY}s after source fail{RESET}\n")

    t_start = time.time()

    for idx, (micc_sym, yf_ticker, display_name, category) in enumerate(universe, 1):
        cat_clr = CAT_COLOR.get(category, RESET)

        # Print progress line
        prog = progress_bar(idx - 1, total)
        print(f"  {BOLD}{prog}{RESET}  {cat_clr}{micc_sym:<14}{RESET} {DIM}{display_name[:30]}{RESET}",
              flush=True)

        # Determine date range
        if mode == "incremental":
            latest = get_latest_date(conn, micc_sym)
            if latest:
                start = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                start = full_start
        else:
            start = full_start

        end = tomorrow

        # Already up to date?
        if start > today_str:
            existing = get_row_count(conn, micc_sym)
            log(f"    Already up to date ({existing:,} rows)", "SKIP")
            skip_syms.append(micc_sym)
            time.sleep(0.3)
            continue

        # Fetch
        df, source = fetch_with_fallback(micc_sym, yf_ticker, start, end)

        if df is not None and not df.empty:
            inserted = upsert(conn, df)
            total_rows = get_row_count(conn, micc_sym)
            elapsed = time.time() - t_start
            eta_s   = elapsed / idx * (total - idx) if idx > 0 else 0
            eta_str = f"{int(eta_s//60)}m{int(eta_s%60):02d}s"
            log(
                f"    {GREEN}+{inserted:>5} rows{RESET}  total={total_rows:>7,}"
                f"  src={source:<20}  ETA={eta_str}",
                "OK"
            )
            ok_syms.append((micc_sym, inserted, source))
        else:
            log(f"    ALL SOURCES FAILED — skipping {micc_sym}", "FAIL")
            fail_syms.append(micc_sym)

        time.sleep(DELAY_BETWEEN)

    conn.close()

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed_total = time.time() - t_start
    print_header("FETCH COMPLETE — SUMMARY")

    print(f"  {GREEN}✅ Success  : {len(ok_syms):3d} symbols{RESET}")
    print(f"  {DIM}⏭ Skipped  : {len(skip_syms):3d} (already current){RESET}")
    print(f"  {RED}❌ Failed   : {len(fail_syms):3d} symbols{RESET}")
    print(f"  ⏱  Total time : {int(elapsed_total//60)}m {int(elapsed_total%60):02d}s\n")

    if ok_syms:
        print_section("Rows fetched per symbol")
        for sym, n_rows, src in sorted(ok_syms, key=lambda x: -x[1]):
            bar_w = min(int(n_rows / 20), 40)
            bar   = "▓" * bar_w
            print(f"    {GREEN}{sym:<16}{RESET} {bar:<40} {n_rows:>7,}  {DIM}[{src}]{RESET}")

    if fail_syms:
        print_section("Failed symbols")
        for sym in fail_syms:
            print(f"    {RED}{sym}{RESET}")

    # ── Full coverage table ───────────────────────────────────────────────────
    print_section("Full coverage table")
    conn2 = get_conn()
    print(f"  {'Symbol':<16} {'Category':<14} {'From':<12} {'To':<12} {'Rows':>7}")
    print(f"  {DIM}{'─'*16} {'─'*14} {'─'*12} {'─'*12} {'─'*7}{RESET}")
    for micc_sym, _, _, category in UNIVERSE:
        row = conn2.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM global_indices_daily WHERE symbol=?",
            (micc_sym,)
        ).fetchone()
        if row and row[2]:
            cat_clr = CAT_COLOR.get(category, RESET)
            status_clr = GREEN if row[2] > 100 else YELLOW
            print(f"  {cat_clr}{micc_sym:<16}{RESET} {DIM}{category:<14}{RESET} "
                  f"{row[0] or '?':<12} {row[1] or '?':<12} "
                  f"{status_clr}{row[2]:>7,}{RESET}")
        else:
            print(f"  {RED}{micc_sym:<16}{RESET} {DIM}{category:<14}{RESET} "
                  f"{'—':^12} {'—':^12} {RED}{'0':>7}{RESET}")
    conn2.close()
    print()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--verify" in args:
        conn = get_conn()
        ensure_table(conn)
        print_header("COVERAGE VERIFICATION")
        print(f"  {'Symbol':<16} {'Category':<14} {'From':<12} {'To':<12} {'Rows':>7}")
        print(f"  {DIM}{'─'*16} {'─'*14} {'─'*12} {'─'*12} {'─'*7}{RESET}")
        for micc_sym, _, _, category in UNIVERSE:
            row = conn.execute(
                "SELECT MIN(date), MAX(date), COUNT(*) FROM global_indices_daily WHERE symbol=?",
                (micc_sym,)
            ).fetchone()
            cat_clr = CAT_COLOR.get(category, RESET)
            if row and row[2]:
                clr = GREEN if row[2] > 100 else YELLOW
                print(f"  {cat_clr}{micc_sym:<16}{RESET} {DIM}{category:<14}{RESET} "
                      f"{row[0]:<12} {row[1]:<12} {clr}{row[2]:>7,}{RESET}")
            else:
                print(f"  {RED}{micc_sym:<16}{RESET} {DIM}{category:<14}{RESET} "
                      f"{'—':^12} {'—':^12} {RED}{'0':>7}{RESET}")
        conn.close()
        sys.exit(0)

    mode = "full" if "--full" in args else "incremental"
    single = None
    for a in args:
        if not a.startswith("--"):
            single = a.upper()
            break
    if "--sym" in args:
        idx    = args.index("--sym")
        single = args[idx + 1].upper() if idx + 1 < len(args) else None

    run(mode=mode, single_sym=single)
