"""
apply_fdr_fast.py  v4 — fixes rowid not returned by pandas
Uses: SELECT rowid AS rid  (explicit alias forces pandas to include it)
"""
import sys, time, sqlite3, argparse
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")
TABLE   = "seasonality_patterns_v3"
FDR_Q   = 0.05
MIN_OBS = 10
CHUNK   = 200_000

G="\033[92m"; Y="\033[93m"; RD="\033[91m"; C="\033[96m"; B="\033[1m"; R="\033[0m"
def now(): return datetime.now().strftime("%H:%M:%S")
def log(msg, lvl=""):
    col = {"OK":G,"WARN":Y,"FAIL":RD}.get(lvl,C)
    print(f"  [{now()}] [{col}{lvl or 'INFO'}{R}]  {msg}", flush=True)

def bh_reject_vec(p_values, q=FDR_Q):
    m = len(p_values)
    if m == 0: return np.array([], dtype=bool)
    order  = np.argsort(p_values)
    sp     = p_values[order]
    thresh = q * np.arange(1, m+1) / m
    below  = sp <= thresh
    if not below.any(): return np.zeros(m, dtype=bool)
    last   = int(np.where(below)[0].max())
    rs = np.zeros(m, dtype=bool); rs[:last+1] = True
    result = np.zeros(m, dtype=bool); result[order] = rs
    return result

def compute_score_v2(accuracy, n_obs):
    acc = np.clip(accuracy, 0, 100) / 100.0
    ic  = np.abs((acc - 0.5) * 2.0)
    return np.round(ic * np.sqrt(np.maximum(n_obs.astype(float), 1)), 4)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    print(f"\n{B}{'='*60}{R}")
    print(f"{B}  MICC FDR Fast v4{R}")
    print(f"{B}{'='*60}{R}\n")

    conn = sqlite3.connect(str(DB_PATH), timeout=300)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-1000000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=2147483648")

    if args.verify:
        total  = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        done   = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE score_v2 IS NOT NULL").fetchone()[0]
        kept   = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE fdr_reject=1").fetchone()[0]
        print(f"  Total:     {total:>12,}")
        print(f"  Processed: {done:>12,}  ({100*done/max(total,1):.1f}%)")
        print(f"  FDR kept:  {kept:>12,}  ({100*kept/max(done,1):.1f}% of processed)")
        if kept:
            rows = conn.execute(
                f"SELECT symbol,anchor_mm_dd,window_days,direction,accuracy,n_obs,score_v2,p_value"
                f" FROM {TABLE} WHERE fdr_reject=1 ORDER BY score_v2 DESC LIMIT 10"
            ).fetchall()
            print(f"\n  Top 10 by score_v2:")
            for r in rows:
                print(f"    {r[0]:<16} {r[1]} {r[2]:>3}d {r[3]:>5} "
                      f"acc={r[4]:.0f}% n={r[5]} sv2={r[6]:.3f} p={r[7]:.5f}")
        conn.close()
        return

    # ── Ensure columns ───────────────────────────────────────────────────────
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})").fetchall()}
    if "score_v2" not in cols:
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN score_v2 REAL DEFAULT NULL")
        log("Added: score_v2", "OK")
    if "fdr_reject" not in cols:
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN fdr_reject INTEGER DEFAULT NULL")
        log("Added: fdr_reject", "OK")
    conn.commit()

    # ── Load — KEY FIX: alias rowid AS rid ──────────────────────────────────
    log("Loading all rows (rowid AS rid to force pandas inclusion)...")
    t0 = time.time()
    df = pd.read_sql_query(
        f"SELECT rowid AS rid, anchor_mm_dd, accuracy, n_obs, p_value FROM {TABLE}",
        conn
    )
    log(f"Loaded {len(df):,} rows in {time.time()-t0:.1f}s", "OK")
    log(f"Columns: {list(df.columns)}")

    df["rid"]      = df["rid"].astype("int64")
    df["accuracy"] = pd.to_numeric(df["accuracy"], errors="coerce").fillna(50.0).astype("float32")
    df["n_obs"]    = pd.to_numeric(df["n_obs"],    errors="coerce").fillna(0).astype("int32")
    df["p_value"]  = pd.to_numeric(df["p_value"],  errors="coerce").fillna(1.0).clip(1e-15,1.0).astype("float64")

    # ── score_v2 ─────────────────────────────────────────────────────────────
    log("Computing score_v2...")
    df["score_v2"]   = compute_score_v2(df["accuracy"].values, df["n_obs"].values)
    df["fdr_reject"] = np.where(df["n_obs"] < MIN_OBS, 0, -1).astype("int8")

    # ── BH per anchor ────────────────────────────────────────────────────────
    log("BH FDR per anchor_mm_dd group...")
    t1 = time.time()
    eligible = df["n_obs"] >= MIN_OBS
    anchors  = df.loc[eligible, "anchor_mm_dd"].unique()
    for i, anchor in enumerate(anchors):
        mask = (df["anchor_mm_dd"] == anchor) & eligible
        idx  = df.index[mask]
        df.loc[idx, "fdr_reject"] = bh_reject_vec(
            df.loc[idx, "p_value"].values).astype("int8")
        if (i+1) % 100 == 0 or i == len(anchors)-1:
            print(f"    {i+1}/{len(anchors)} anchors  [{now()}]", flush=True)
    kept = int((df["fdr_reject"]==1).sum())
    log(f"BH done {time.time()-t1:.1f}s  kept={kept:,}  ({100*kept/len(df):.1f}%)", "OK")

    # ── Bulk insert into temp table ──────────────────────────────────────────
    log("Creating temp table fdr_results...")
    conn.execute("DROP TABLE IF EXISTS fdr_results")
    conn.execute("""
        CREATE TABLE fdr_results (
            rid        INTEGER PRIMARY KEY,
            score_v2   REAL,
            fdr_reject INTEGER
        )
    """)

    log(f"Inserting {len(df):,} rows into fdr_results...")
    t2 = time.time()
    data = list(zip(
        df["rid"].tolist(),
        df["score_v2"].tolist(),
        df["fdr_reject"].tolist()
    ))
    for i in range(0, len(data), CHUNK):
        batch = data[i:i+CHUNK]
        conn.executemany(
            "INSERT INTO fdr_results (rid, score_v2, fdr_reject) VALUES (?,?,?)", batch)
        n = i + len(batch)
        pct  = 100*n/len(data)
        rate = n / max(time.time()-t2, 0.1)
        eta  = (len(data)-n) / max(rate, 1)
        print(f"  {n:>12,}/{len(data):,} ({pct:5.1f}%)  "
              f"{rate:>8,.0f} r/s  ETA {eta/60:.1f}min",
              end="\r", flush=True)
    conn.commit()
    print()
    log(f"Temp table filled in {time.time()-t2:.1f}s", "OK")

    # ── Single UPDATE via correlated subquery ────────────────────────────────
    log("Updating main table from temp (single statement — may take 5-15 min)...")
    t3 = time.time()
    conn.execute(f"""
        UPDATE {TABLE}
        SET score_v2   = (SELECT score_v2   FROM fdr_results r WHERE r.rid = {TABLE}.rowid),
            fdr_reject = (SELECT fdr_reject FROM fdr_results r WHERE r.rid = {TABLE}.rowid)
        WHERE {TABLE}.rowid IN (SELECT rid FROM fdr_results)
    """)
    conn.commit()
    log(f"Main table updated in {(time.time()-t3)/60:.1f} min", "OK")

    # ── Cleanup + Index ──────────────────────────────────────────────────────
    conn.execute("DROP TABLE IF EXISTS fdr_results")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_sv2 ON {TABLE}(score_v2 DESC)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_fdr ON {TABLE}(fdr_reject)")
    conn.commit()
    log("Cleanup + indices done", "OK")

    total = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    done  = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE score_v2 IS NOT NULL").fetchone()[0]
    kept2 = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE fdr_reject=1").fetchone()[0]
    conn.close()

    print(f"\n{B}  Final Results:{R}")
    print(f"  Total:          {total:>12,}")
    print(f"  Processed:      {done:>12,}  ({100*done/max(total,1):.1f}%)")
    print(f"  FDR kept:       {kept2:>12,}  ({100*kept2/max(done,1):.1f}%)")
    print(f"  Total time:     {(time.time()-t0)/60:.1f} min")
    print(f"\n{G}  Done. Use: WHERE fdr_reject=1 AND score_v2>1.0 ORDER BY score_v2 DESC{R}\n")

if __name__ == "__main__":
    main()
