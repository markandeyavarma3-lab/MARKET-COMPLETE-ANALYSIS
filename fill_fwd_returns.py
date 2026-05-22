"""
fill_fwd_returns.py
===================
Fills fwd_1d, fwd_3d, fwd_5d, fwd_10d columns in signals_history
by reading parquet files directly.

oos_backtest.py computes these in-memory but NEVER writes to DB.
This script does the actual DB write.

Run: py D:\MICC\fill_fwd_returns.py
"""
from pathlib import Path
import sqlite3

MICC        = Path(r"D:\MICC")
DB_PATH     = r"D:\marketDB\db\market.db"
PARQUET     = Path(r"D:\marketDB\stocks\all")
HORIZONS    = [1, 3, 5, 10]

def log(msg):
    from datetime import datetime
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

try:
    import pandas as pd
    import numpy as np
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "pandas", "pyarrow", "--break-system-packages", "-q"])
    import pandas as pd
    import numpy as np

print("Fill Forward Returns -> signals_history")
print("=" * 45)

# ── Step 1: ensure columns exist ──────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH, timeout=60)
conn.execute("PRAGMA journal_mode=WAL")
existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(signals_history)").fetchall()}
for col in ["fwd_1d", "fwd_3d", "fwd_5d", "fwd_10d", "hit_1d", "hit_3d", "hit_5d", "hit_10d"]:
    if col not in existing_cols:
        conn.execute(f"ALTER TABLE signals_history ADD COLUMN {col} REAL")
        log(f"Added column: {col}")
conn.commit()

# ── Step 2: load signals that need filling ────────────────────────────────────
rows = conn.execute(
    "SELECT rowid, symbol, run_date FROM signals_history"
    " WHERE fwd_5d IS NULL ORDER BY run_date DESC"
).fetchall()
log(f"Signals needing fwd_5d: {len(rows)}")

if not rows:
    log("All fwd_5d already filled!")
    conn.close()
    exit(0)

# ── Step 3: load parquet per symbol (cached) ──────────────────────────────────
cache = {}

def get_closes(sym):
    if sym in cache:
        return cache[sym]
    folder = PARQUET / sym
    if not folder.exists():
        cache[sym] = {}
        return {}
    frames = []
    for f in sorted(folder.glob(f"{sym}_*.parquet")):
        try:
            df = pd.read_parquet(f, columns=["date", "close"])
            frames.append(df)
        except Exception:
            pass
    if not frames:
        cache[sym] = {}
        return {}
    df = pd.concat(frames).drop_duplicates("date").sort_values("date")
    df["date"]  = df["date"].astype(str).str[:10]
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    closes = dict(zip(df["date"], df["close"].values))
    cache[sym] = closes
    return closes

# ── Step 4: compute forward returns ──────────────────────────────────────────
def compute_fwd(sym, run_date):
    closes = get_closes(sym)
    if not closes:
        return {}
    sorted_dates = sorted(closes.keys())
    # Find index of run_date or nearest prior date
    idx = None
    for i, d in enumerate(sorted_dates):
        if d >= run_date:
            idx = i - 1 if i > 0 else 0
            break
    if idx is None:
        idx = len(sorted_dates) - 1
    base = closes[sorted_dates[idx]]
    if not base or base <= 0:
        return {}
    result = {}
    for h in HORIZONS:
        if idx + h < len(sorted_dates):
            fwd_close = closes[sorted_dates[idx + h]]
            fwd_ret   = (fwd_close / base - 1) * 100
            result[f"fwd_{h}d"] = round(fwd_ret, 4)
            result[f"hit_{h}d"] = 1 if fwd_ret > 0 else 0
    return result

# ── Step 5: fill and batch update ─────────────────────────────────────────────
batch = []
ok = 0; miss = 0

for i, (rowid, sym, run_date) in enumerate(rows):
    if i % 100 == 0 and i > 0:
        log(f"{i}/{len(rows)}  ok={ok}  miss={miss}")

    fwd = compute_fwd(sym, str(run_date)[:10])
    if fwd:
        batch.append((
            fwd.get("fwd_1d"),  fwd.get("fwd_3d"),
            fwd.get("fwd_5d"),  fwd.get("fwd_10d"),
            fwd.get("hit_1d"),  fwd.get("hit_3d"),
            fwd.get("hit_5d"),  fwd.get("hit_10d"),
            rowid
        ))
        ok += 1
    else:
        miss += 1

    if len(batch) >= 100:
        conn.executemany(
            "UPDATE signals_history SET"
            " fwd_1d=?, fwd_3d=?, fwd_5d=?, fwd_10d=?,"
            " hit_1d=?, hit_3d=?, hit_5d=?, hit_10d=?"
            " WHERE rowid=?",
            batch
        )
        conn.commit()
        batch = []

if batch:
    conn.executemany(
        "UPDATE signals_history SET"
        " fwd_1d=?, fwd_3d=?, fwd_5d=?, fwd_10d=?,"
        " hit_1d=?, hit_3d=?, hit_5d=?, hit_10d=?"
        " WHERE rowid=?",
        batch
    )
    conn.commit()

# ── Step 6: verify ────────────────────────────────────────────────────────────
n_filled = conn.execute(
    "SELECT COUNT(*) FROM signals_history WHERE fwd_5d IS NOT NULL"
).fetchone()[0]
n_total  = conn.execute("SELECT COUNT(*) FROM signals_history").fetchone()[0]

# Quick sample
sample = conn.execute(
    "SELECT symbol, run_date, fwd_5d, fwd_10d FROM signals_history"
    " WHERE fwd_5d IS NOT NULL ORDER BY run_date DESC LIMIT 5"
).fetchall()
conn.close()

print()
log(f"DONE.  ok={ok}  miss={miss}")
log(f"signals_history: {n_filled}/{n_total} rows have fwd_5d")
print()
print("  Sample filled rows:")
for sym, dt, f5, f10 in sample:
    print(f"    {sym:<15} {dt}  fwd_5d={f5:+.2f}%  fwd_10d={f10:+.2f}%" if f5 else f"    {sym} {dt} fwd_5d=None")

print()
if n_filled >= 50:
    print("Ready to train XGBoost:")
    print("  py D:\\MICC\\train_conviction_xgb.py")
else:
    print(f"Only {n_filled} rows filled -- signals may be too recent (no future data yet).")
    print("XGBoost needs historical signals. Run after market data accumulates.")
    print()
    print("For now, train on available data anyway:")
    print("  py D:\\MICC\\train_conviction_xgb.py  (will try with available rows)")
