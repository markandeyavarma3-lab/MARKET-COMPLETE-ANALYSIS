# -*- coding: utf-8 -*-
r"""
validate_patterns_oos.py  --  Run from D:\MICC
Phase 1 Task 3: OOS per-pattern accuracy columns

Splits seasonality_patterns_v3 at 2019-01-01:
  TRAIN: all returns before 2019
  TEST : all returns 2019 onwards (OOS)

Adds three columns to seasonality_patterns_v3:
  oos_accuracy    REAL   -- win rate on OOS period (NULL if < 5 obs)
  oos_n_obs       INT    -- number of OOS observations
  oos_degradation REAL   -- (in_sample_accuracy - oos_accuracy), positive = overfit

Marks patterns with oos_degradation > 0.10 (10pp) as overfit:
  overfit         INT    -- 1 if degraded >10pp, 0 otherwise

Strategy: bulk temp-table UPDATE (never per-row) -- safe for 19M rows.

Runtime estimate: ~15-25 min for 19M rows on your machine.
Run overnight or in background.

Run: py D:\MICC\validate_patterns_oos.py [--test]
  --test  : runs on 10,000 rows only to verify logic, then exits
"""
import sqlite3, json, sys
from pathlib import Path
from datetime import datetime

DB      = r"D:\marketDB\db\market.db"
PARQUET = Path(r"D:\marketDB\stocks\all")
OOS_CUT = "2019-01-01"   # train < this date, test >= this date
MIN_OOS = 5              # minimum OOS observations to compute oos_accuracy
OVERFIT_THRESH = 0.10    # 10pp degradation = overfit

TEST_MODE = "--test" in sys.argv

print(f"OOS Pattern Validation")
print(f"  OOS cutoff : {OOS_CUT}")
print(f"  Min OOS obs: {MIN_OOS}")
print(f"  Overfit thr: {OVERFIT_THRESH*100:.0f}pp")
print(f"  Mode       : {'TEST (10k rows)' if TEST_MODE else 'FULL RUN'}")
print()

conn = sqlite3.connect(DB, timeout=60)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-512000")  # 512MB cache

# ── Step 1: Add columns if missing ───────────────────────────────────────────
print("[1] Adding OOS columns to seasonality_patterns_v3...")
existing = [r[1] for r in conn.execute("PRAGMA table_info(seasonality_patterns_v3)").fetchall()]
added = []
for col, typedef in [
    ("oos_accuracy",    "REAL"),
    ("oos_n_obs",       "INTEGER"),
    ("oos_degradation", "REAL"),
    ("overfit",         "INTEGER DEFAULT 0"),
]:
    if col not in existing:
        conn.execute(f"ALTER TABLE seasonality_patterns_v3 ADD COLUMN {col} {typedef}")
        added.append(col)
        print(f"  Added column: {col}")
    else:
        print(f"  Already exists: {col}")
conn.commit()

# ── Step 2: Load all parquet files and compute OOS stats ─────────────────────
print("\n[2] Computing OOS accuracy from parquet files...")
print("    This reads all_returns JSON from the DB table and splits at 2019.")
print("    Note: all_returns is stored as JSON array of [date, return] pairs.")

# Check how all_returns is stored
sample = conn.execute(
    "SELECT symbol, anchor_mm_dd, window_days, all_returns, accuracy FROM "
    "seasonality_patterns_v3 WHERE all_returns IS NOT NULL LIMIT 3"
).fetchall()

if not sample:
    print("  [WARN] all_returns column is NULL/empty. Cannot compute OOS from DB alone.")
    print("  Falling back to parquet-based computation...")
    USE_PARQUET = True
else:
    print(f"  Sample all_returns[0]: {str(sample[0][3])[:100]}")
    USE_PARQUET = False

if not USE_PARQUET:
    # ── Path A: all_returns stored in DB ────────────────────────────────────
    print("\n[3a] Computing OOS from all_returns JSON in DB (temp table strategy)...")

    # Create temp table with computed OOS stats
    conn.execute("DROP TABLE IF EXISTS _oos_temp")
    conn.execute("""
        CREATE TEMP TABLE _oos_temp (
            id              INTEGER PRIMARY KEY,
            oos_accuracy    REAL,
            oos_n_obs       INTEGER,
            oos_degradation REAL,
            overfit         INTEGER
        )
    """)

    limit_clause = "LIMIT 10000" if TEST_MODE else ""
    rows = conn.execute(
        f"SELECT id, accuracy, all_returns FROM seasonality_patterns_v3 "
        f"WHERE all_returns IS NOT NULL {limit_clause}"
    ).fetchall()

    print(f"  Processing {len(rows):,} rows...")
    batch = []
    t0 = datetime.now()

    for i, (pid, in_acc, all_ret_raw) in enumerate(rows):
        if i % 100000 == 0 and i > 0:
            elapsed = (datetime.now() - t0).total_seconds()
            rate = i / elapsed
            eta = (len(rows) - i) / rate / 60
            print(f"    {i:,}/{len(rows):,}  {rate:.0f} rows/s  ETA {eta:.1f} min")

        try:
            returns = json.loads(all_ret_raw)  # [[date, ret], ...]
        except Exception:
            continue

        if not returns:
            continue

        # Split at OOS_CUT
        oos = [r[1] for r in returns if isinstance(r, (list, tuple)) and len(r) >= 2
               and str(r[0]) >= OOS_CUT]

        if len(oos) < MIN_OOS:
            batch.append((None, len(oos), None, 0, pid))
            continue

        oos_acc = sum(1 for r in oos if float(r) > 0) / len(oos)
        degrade = (float(in_acc) if in_acc is not None else 0) - oos_acc
        overfit = 1 if degrade > OVERFIT_THRESH else 0

        batch.append((oos_acc, len(oos), round(degrade, 4), overfit, pid))

        # Flush every 50k rows
        if len(batch) >= 50000:
            conn.executemany(
                "INSERT OR REPLACE INTO _oos_temp(oos_accuracy,oos_n_obs,oos_degradation,overfit,id) "
                "VALUES(?,?,?,?,?)",
                batch
            )
            conn.commit()
            batch = []

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO _oos_temp(oos_accuracy,oos_n_obs,oos_degradation,overfit,id) "
            "VALUES(?,?,?,?,?)",
            batch
        )
        conn.commit()

    # ── Bulk UPDATE from temp table ──────────────────────────────────────────
    print("\n[4] Bulk UPDATE seasonality_patterns_v3 from temp table...")
    conn.execute("""
        UPDATE seasonality_patterns_v3
        SET oos_accuracy    = (SELECT oos_accuracy    FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id),
            oos_n_obs       = (SELECT oos_n_obs       FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id),
            oos_degradation = (SELECT oos_degradation FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id),
            overfit         = (SELECT overfit         FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id)
        WHERE id IN (SELECT id FROM _oos_temp)
    """)
    conn.commit()

else:
    # ── Path B: compute from parquet files ──────────────────────────────────
    print("\n[3b] Computing OOS from parquet files...")
    try:
        import pandas as pd
    except ImportError:
        import subprocess
        subprocess.run(["py", "-m", "pip", "install", "pandas", "pyarrow",
                       "--break-system-packages", "-q"])
        import pandas as pd

    # Get unique symbols in the patterns table
    syms = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM seasonality_patterns_v3 LIMIT 100" if TEST_MODE
        else "SELECT DISTINCT symbol FROM seasonality_patterns_v3"
    ).fetchall()]
    print(f"  {len(syms)} symbols to process...")

    conn.execute("DROP TABLE IF EXISTS _oos_temp")
    conn.execute("""
        CREATE TEMP TABLE _oos_temp (
            id              INTEGER PRIMARY KEY,
            oos_accuracy    REAL,
            oos_n_obs       INTEGER,
            oos_degradation REAL,
            overfit         INTEGER
        )
    """)

    processed = 0
    t0 = datetime.now()

    for sym in syms:
        # Load all parquet for this symbol
        sym_dir = PARQUET / sym
        if not sym_dir.exists():
            continue
        dfs = []
        for pf in sorted(sym_dir.glob("*.parquet")):
            try:
                dfs.append(pd.read_parquet(pf, columns=["date","close"]))
            except Exception:
                continue
        if not dfs:
            continue

        df = pd.concat(dfs).drop_duplicates("date").sort_values("date")
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"])
        if len(df) < 30:
            continue

        # Get all patterns for this symbol
        pats = conn.execute(
            "SELECT id, anchor_mm_dd, window_days, accuracy FROM "
            "seasonality_patterns_v3 WHERE symbol=?", (sym,)
        ).fetchall()

        batch = []
        for pid, anchor_mm_dd, window_days, in_acc in pats:
            # Find all dates where month-day == anchor_mm_dd
            anchor_month = int(anchor_mm_dd.split("-")[0])
            anchor_day   = int(anchor_mm_dd.split("-")[1])
            anchors = df[(df["date"].dt.month == anchor_month) &
                        (df["date"].dt.day   == anchor_day)]

            oos_anchors = anchors[anchors["date"] >= OOS_CUT]
            if len(oos_anchors) < MIN_OOS:
                batch.append((None, len(oos_anchors), None, 0, pid))
                continue

            # Compute forward returns for each OOS anchor
            hits = 0
            valid = 0
            for _, row in oos_anchors.iterrows():
                try:
                    idx    = df.index.get_loc(row.name)
                    future = df.iloc[idx + window_days]["close"]
                    ret    = (future - row["close"]) / row["close"]
                    if ret > 0: hits += 1
                    valid += 1
                except Exception:
                    continue

            if valid < MIN_OOS:
                batch.append((None, valid, None, 0, pid))
                continue

            oos_acc = hits / valid
            degrade = (float(in_acc) if in_acc is not None else 0) - oos_acc
            overfit = 1 if degrade > OVERFIT_THRESH else 0
            batch.append((oos_acc, valid, round(degrade, 4), overfit, pid))

        if batch:
            conn.executemany(
                "INSERT OR REPLACE INTO _oos_temp(oos_accuracy,oos_n_obs,oos_degradation,overfit,id) "
                "VALUES(?,?,?,?,?)",
                batch
            )

        processed += 1
        if processed % 100 == 0:
            conn.commit()
            elapsed = (datetime.now() - t0).total_seconds()
            rate = processed / elapsed
            eta  = (len(syms) - processed) / rate / 60
            print(f"    {processed}/{len(syms)} symbols  ETA {eta:.1f} min")

    conn.commit()

    print("\n[4] Bulk UPDATE from temp table...")
    conn.execute("""
        UPDATE seasonality_patterns_v3
        SET oos_accuracy    = (SELECT oos_accuracy    FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id),
            oos_n_obs       = (SELECT oos_n_obs       FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id),
            oos_degradation = (SELECT oos_degradation FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id),
            overfit         = (SELECT overfit         FROM _oos_temp WHERE _oos_temp.id = seasonality_patterns_v3.id)
        WHERE id IN (SELECT id FROM _oos_temp)
    """)
    conn.commit()

# ── Step 5: Report ────────────────────────────────────────────────────────────
print("\n[5] Results...")
stats = conn.execute("""
    SELECT
        COUNT(*)                                         AS total,
        SUM(CASE WHEN oos_accuracy IS NOT NULL THEN 1 END) AS with_oos,
        SUM(CASE WHEN overfit=1 THEN 1 END)              AS overfit_count,
        ROUND(AVG(CASE WHEN oos_accuracy IS NOT NULL THEN oos_accuracy END)*100,1) AS avg_oos_acc,
        ROUND(AVG(CASE WHEN oos_degradation IS NOT NULL THEN oos_degradation END)*100,1) AS avg_degrade
    FROM seasonality_patterns_v3
""").fetchone()

print(f"  Total patterns    : {stats[0]:,}")
print(f"  With OOS data     : {stats[1]:,}")
print(f"  Overfit (>10pp)   : {stats[2]:,}")
print(f"  Avg OOS accuracy  : {stats[3]}%")
print(f"  Avg degradation   : {stats[4]}pp")

# Top overfit examples
print("\n  Top overfit patterns (highest degradation):")
overfit_ex = conn.execute("""
    SELECT symbol, anchor_mm_dd, window_days,
           ROUND(accuracy*100,1) AS in_acc,
           ROUND(oos_accuracy*100,1) AS oos_acc,
           ROUND(oos_degradation*100,1) AS degrade_pp
    FROM seasonality_patterns_v3
    WHERE overfit=1 AND oos_accuracy IS NOT NULL
    ORDER BY oos_degradation DESC LIMIT 10
""").fetchall()
for r in overfit_ex:
    print(f"    {r[0]:15} {r[1]} {r[2]:2}d  in={r[3]}% oos={r[4]}% degrade={r[5]}pp")

conn.close()
elapsed_total = (datetime.now() - t0).total_seconds() / 60
print(f"\nDone in {elapsed_total:.1f} min")
print("""
Next steps:
  - Patterns page can now filter: overfit=0 (hide degraded patterns)
  - /patterns page badge: show oos_accuracy next to in-sample accuracy
  - conviction page: seasonal_score should prefer non-overfit patterns
""")
