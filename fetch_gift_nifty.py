import sqlite3, sys
from datetime import datetime
from pathlib import Path

DB = r"D:\marketDB\db\market.db"

try:
    import yfinance as yf
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "yfinance", "--break-system-packages", "-q"])
    import yfinance as yf

print("Fetching GIFT Nifty...")

TICKERS = [
    ("GIFTNifty", "NIFTY_FUT.NS"),
    ("SGXNifty",  "^NIFTY_FUT"),
]

CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS global_indices_daily"
    " (symbol TEXT, date TEXT, open REAL, high REAL,"
    "  low REAL, close REAL, volume REAL, pct_change REAL,"
    "  display_name TEXT, category TEXT,"
    "  PRIMARY KEY(symbol, date))"
)

def fetch_gift():
    for sym, ticker in TICKERS:
        try:
            df = yf.download(ticker, period="5d", interval="1d",
                             auto_adjust=True, progress=False)
            if df is None or df.empty:
                continue
            conn = sqlite3.connect(DB, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(CREATE_SQL)
            rows = []
            prev = None
            for dt, row in df.iterrows():
                d   = str(dt)[:10]
                c   = float(row["Close"])
                pct = round((c - prev) / prev * 100, 4) if prev else None
                rows.append((
                    sym, d,
                    float(row["Open"]), float(row["High"]),
                    float(row["Low"]),  c,
                    float(row.get("Volume", 0) or 0),
                    pct, "GIFT Nifty Futures", "futures"
                ))
                prev = c
            conn.executemany(
                "INSERT OR REPLACE INTO global_indices_daily"
                " (symbol,date,open,high,low,close,volume,"
                "  pct_change,display_name,category)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                rows
            )
            conn.commit()
            conn.close()
            print(f"  {sym}: {len(rows)} rows stored")
            if rows:
                last = rows[-1]
                pct_s = f"{last[7]:+.2f}%" if last[7] else ""
                print(f"  Latest: {last[1]}  close={last[5]:.2f}  {pct_s}")
            return True
        except Exception as e:
            print(f"  {sym}: {e}")
    return False

ok = fetch_gift()
print("GIFT Nifty: OK" if ok else "GIFT Nifty: FAILED (not critical)")
