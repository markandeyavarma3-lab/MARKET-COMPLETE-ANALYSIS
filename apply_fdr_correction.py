"""
apply_fdr_correction.py  (v3)
Fix: rowid not in dtype map for pandas read_sql_query
"""
import sys, math, time, sqlite3, argparse
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")
TABLE   = "seasonality_patterns_v3"
FDR_Q   = 0.05
MIN_OBS = 10
CHUNK   = 50_000

G="\033[92m"; Y="\033[93m"; RD="\033[91m"; C="\033[96m"; B="\033[1m"; R="\033[0m"
def now(): return datetime.now().strftime("%H:%M:%S")
def log(msg, lvl=""):
    col = {"OK":G,"WARN":Y,"FAIL":RD}.get(lvl,C)
    tag = f"[{col}{lvl or 'INFO'}{R}]"
    print(f"  [{now()}] {tag}  {msg}", flush=True)

def get_table(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if TABLE in tables: return TABLE
    if "seasonality_patterns" in tables: return "seasonality_patterns"
    raise RuntimeError("No seasonality table found!")

def ensure_columns(conn, tbl):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
    if "score_v2" not in cols:
        conn.execute(f"ALTER TABLE {tbl} ADD COLUMN score_v2 REAL DEFAULT NULL")
        log("Added: score_v2", "OK")
    if "fdr_reject" not in cols:
        conn.execute(f"ALTER TABLE {tbl} ADD COLUMN fdr_reject INTEGER DEFAULT NULL")
        log("Added: fdr_reject", "OK")
    conn.commit()

def bh_reject_vec(p_values, q=FDR_Q):
    m = len(p_values)
    if m == 0: return np.array([], dtype=bool)
    order  = np.argsort(p_values)
    sp     = p_values[order]
    thresh = q * np.arange(1, m+1) / m
    below  = sp <= thresh
    if not below.any(): return np.zeros(m, dtype=bool)
    last   = int(np.where(below)[0].max())
    rs     = np.zeros(m, dtype=bool); rs[:last+1] = True
    result = np.zeros(m, dtype=bool); result[order] = rs
    return result

def compute_score_v2_vec(accuracy, n_obs):
    acc = np.clip(accuracy, 0, 100) / 100.0
    ic  = np.abs((acc - 0.5) * 2.0)
    return np.round(ic * np.sqrt(np.maximum(n_obs.astype(float), 1)), 4)

def process_all(conn, tbl):
    log("Counting unprocessed rows...")
    total = conn.execute(
        f"SELECT COUNT(*) FROM {tbl} WHERE score_v2 IS NULL").fetchone()[0]
    log(f"Rows to process: {total:,}")
    if total == 0:
        log("All done!", "OK"); return

    log("Loading into DataFrame (no dtype map — fix for rowid)...")
    t0 = time.time()

    # FIX: don't specify dtype for rowid — let pandas infer, then cast manually
    df = pd.read_sql_query(
        f"SELECT rowid, anchor_mm_dd, accuracy, n_obs, p_value"
        f" FROM {tbl} WHERE score_v2 IS NULL",
        conn
    )
    log(f"Loaded {len(df):,} rows in {time.time()-t0:.1f}s", "OK")

    # Cast manually after load
    df["rowid"]    = df["rowid"].astype("int64")
    df["accuracy"] = pd.to_numeric(df["accuracy"], errors="coerce").fillna(50.0).astype("float32")
    df["n_obs"]    = pd.to_numeric(df["n_obs"],    errors="coerce").fillna(0).astype("int32")
    df["p_value"]  = pd.to_numeric(df["p_value"],  errors="coerce").fillna(1.0).clip(1e-15, 1.0).astype("float64")

    log("Computing score_v2 (vectorized)...")
    df["score_v2"]   = compute_score_v2_vec(df["accuracy"].values, df["n_obs"].values).astype("float32")
    df["fdr_reject"] = np.where(df["n_obs"] < MIN_OBS, 0, -1).astype("int8")

    log("Running BH FDR per anchor_mm_dd group...")
    t1 = time.time()
    eligible = df["n_obs"] >= MIN_OBS
    anchors  = df.loc[eligible, "anchor_mm_dd"].unique()
    for i, anchor in enumerate(anchors):
        mask = (df["anchor_mm_dd"] == anchor) & eligible
        idx  = df.index[mask]
        p    = df.loc[idx, "p_value"].values
        df.loc[idx, "fdr_reject"] = bh_reject_vec(p, q=FDR_Q).astype("int8")
        if (i+1) % 50 == 0 or i == len(anchors)-1:
            print(f"    {i+1}/{len(anchors)} anchors  ({now()})", flush=True)

    kept = int((df["fdr_reject"]==1).sum())
    rej  = int((df["fdr_reject"]==0).sum())
    log(f"BH done in {time.time()-t1:.1f}s  kept={kept:,}  rejected={rej:,}", "OK")

    log(f"Writing to DB in chunks of {CHUNK:,}...")
    t2 = time.time()
    updates = list(zip(df["score_v2"].tolist(), df["fdr_reject"].tolist(), df["rowid"].tolist()))
    n = 0
    for i in range(0, len(updates), CHUNK):
        batch = updates[i:i+CHUNK]
        conn.executemany(f"UPDATE {tbl} SET score_v2=?, fdr_reject=? WHERE rowid=?", batch)
        conn.commit()
        n += len(batch)
        pct = 100*n/max(len(updates),1)
        rate = n / max(time.time()-t2, 1)
        eta  = (len(updates)-n) / max(rate, 1)
        print(f"  Written {n:,}/{len(updates):,} ({pct:.1f}%)  {rate:.0f}r/s  ETA {eta/60:.1f}min",
              end="\r", flush=True)
    print()
    log(f"Done. Total time: {time.time()-t0:.1f}s", "OK")

def ensure_index(conn, tbl):
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_sv2 ON {tbl}(score_v2 DESC)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_fdr ON {tbl}(fdr_reject)")
    conn.commit()
    log("Indices created", "OK")

def verify(conn, tbl):
    print(f"\n{B}  Quality Summary{R}")
    total  = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    has_v2 = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE score_v2 IS NOT NULL").fetchone()[0]
    kept   = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE fdr_reject=1").fetchone()[0]
    rej    = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE fdr_reject=0").fetchone()[0]
    print(f"  Total:          {total:>12,}")
    print(f"  Processed:      {has_v2:>12,}")
    print(f"  FDR kept:       {kept:>12,}  ({100*kept/max(has_v2,1):.1f}%)")
    print(f"  FDR rejected:   {rej:>12,}  ({100*rej/max(has_v2,1):.1f}%)")
    if kept > 0:
        print(f"\n  Top 10 by score_v2:")
        print(f"  {'Symbol':<16} {'Anchor':>7} {'Win':>4} {'Dir':>5} {'Acc':>6} {'N':>5} {'SV2':>7} {'p':>8}")
        rows = conn.execute(
            f"SELECT symbol,anchor_mm_dd,window_days,direction,accuracy,n_obs,score_v2,p_value"
            f" FROM {tbl} WHERE fdr_reject=1 ORDER BY score_v2 DESC LIMIT 10"
        ).fetchall()
        for r in rows:
            print(f"  {r[0]:<16} {r[1]:>7} {r[2]:>4} {r[3]:>5} {r[4]:>5.1f}% {r[5]:>5} {r[6]:>7.3f} {r[7]:>8.5f}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--reset",  action="store_true")
    args = ap.parse_args()

    print(f"\n{B}{'='*60}{R}")
    print(f"{B}  MICC FDR Correction v3{R}")
    print(f"{B}{'='*60}{R}\n")
    log(f"FDR q={FDR_Q}  MIN_OBS={MIN_OBS}")

    conn = sqlite3.connect(str(DB_PATH), timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-500000")
    conn.execute("PRAGMA temp_store=MEMORY")
    tbl = get_table(conn)
    log(f"Table: {tbl}")
    ensure_columns(conn, tbl)

    if args.reset:
        log("Resetting...", "WARN")
        conn.execute(f"UPDATE {tbl} SET score_v2=NULL, fdr_reject=NULL")
        conn.commit()
        log("Reset done", "OK")

    if args.verify:
        verify(conn, tbl); conn.close(); return

    process_all(conn, tbl)
    ensure_index(conn, tbl)
    verify(conn, tbl)
    conn.close()
    print(f"\n{G}  Use: WHERE fdr_reject=1 AND score_v2>1.0 ORDER BY score_v2 DESC{R}\n")

if __name__ == "__main__":
    main()
