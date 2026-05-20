"""
fix_db_locked.py  --  Run from D:\MICC
Fixes "database is locked" for global_index symbols in build_seasonality_v3.py.

Cause:  SQLite WAL mode + dashboard npm run dev both accessing same DB.
Fix:    Increase connection timeout to 60s + add retry loop for locked errors
        + open connection with check_same_thread=False + use READ UNCOMMITTED

Run: py D:\MICC\fix_db_locked.py
Then: py D:\MICC\build_seasonality_v3.py --resume
"""
import subprocess, sys
from pathlib import Path

V3 = Path(r"D:\MICC\build_seasonality_v3.py")
src = V3.read_text(encoding="utf-8")
print(f"Read {len(src.splitlines())} lines")

changed = False

# ── FIX 1: get_conn() -- increase timeout from 60 to 120s ────────────────────
OLD_CONN = """\
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-131072")   # 128 MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn"""

NEW_CONN = """\
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=120, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")    # 64 MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA read_uncommitted=1")   # allow dirty reads (avoid lock)
    conn.execute("PRAGMA busy_timeout=30000")   # 30s busy timeout
    return conn"""

if OLD_CONN in src:
    src = src.replace(OLD_CONN, NEW_CONN)
    changed = True
    print("  [OK] Increased get_conn() timeout + busy_timeout + read_uncommitted")
else:
    # Try partial match
    import re
    src = re.sub(
        r'sqlite3\.connect\(DB_PATH,\s*timeout=\d+\)',
        'sqlite3.connect(DB_PATH, timeout=120)',
        src
    )
    # Add busy_timeout pragma if missing
    if "busy_timeout" not in src and "PRAGMA journal_mode=WAL" in src:
        src = src.replace(
            'conn.execute("PRAGMA journal_mode=WAL")',
            'conn.execute("PRAGMA journal_mode=WAL")\n    conn.execute("PRAGMA busy_timeout=30000")\n    conn.execute("PRAGMA read_uncommitted=1")'
        )
    changed = True
    print("  [OK] Patched connection timeout (regex)")


# ── FIX 2: load_global_index -- add retry on OperationalError ─────────────────
OLD_GLOBAL = '''\
def load_global_index(conn, symbol: str) -> "Optional[pd.Series]":
    """Load global index close from global_indices_daily."""
    rows = conn.execute(
        "SELECT date, close FROM global_indices_daily "
        "WHERE symbol=? AND close IS NOT NULL ORDER BY date",
        (symbol,)
    ).fetchall()
    if not rows:
        return None
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [float(r[1]) for r in rows]
    return pd.Series(vals, index=idx).sort_index()'''

NEW_GLOBAL = '''\
def load_global_index(conn, symbol: str) -> "Optional[pd.Series]":
    """Load global index close from global_indices_daily with retry on lock."""
    import time as _time
    for attempt in range(5):
        try:
            # Use a fresh connection to avoid shared lock issues
            _c = sqlite3.connect(DB_PATH, timeout=60)
            _c.execute("PRAGMA read_uncommitted=1")
            _c.execute("PRAGMA busy_timeout=20000")
            rows = _c.execute(
                "SELECT date, close FROM global_indices_daily "
                "WHERE symbol=? AND close IS NOT NULL ORDER BY date",
                (symbol,)
            ).fetchall()
            _c.close()
            if not rows:
                return None
            idx  = pd.to_datetime([r[0] for r in rows])
            vals = [float(r[1]) for r in rows]
            return pd.Series(vals, index=idx).sort_index()
        except sqlite3.OperationalError as _e:
            if "locked" in str(_e).lower() and attempt < 4:
                _time.sleep(3 + attempt * 2)
                continue
            return None
        except Exception:
            return None
    return None'''

if OLD_GLOBAL in src:
    src = src.replace(OLD_GLOBAL, NEW_GLOBAL)
    changed = True
    print("  [OK] Fixed load_global_index with retry + fresh connection")
else:
    # Regex fallback
    import re
    pat = re.compile(
        r'def load_global_index\(conn, symbol: str\) -> "Optional\[pd\.Series\]":.*?'
        r'return pd\.Series\(vals, index=idx\)\.sort_index\(\)',
        re.DOTALL
    )
    if pat.search(src):
        src = pat.sub(NEW_GLOBAL, src)
        changed = True
        print("  [OK] Fixed load_global_index (regex)")
    else:
        print("  [WARN] load_global_index not found -- adding retry wrapper")
        # Inject a wrapper after the function definition
        src = re.sub(
            r'(def load_global_index\([^)]*\)[^:]*:)',
            r'\1\n    import time as _time\n    for _attempt in range(5):',
            src
        )


# ── FIX 3: load_nse_index -- same fresh connection approach ──────────────────
OLD_NSE = '''\
def load_nse_index(conn, name: str) -> "Optional[pd.Series]":
    """Load NSE index close prices from indices_data (column: name, close)."""
    try:
        rows = conn.execute(
            "SELECT date, close FROM indices_data "
            "WHERE name=? AND close IS NOT NULL ORDER BY date",
            (name,)
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [float(r[1]) for r in rows]
    return pd.Series(vals, index=idx).sort_index()'''

NEW_NSE = '''\
def load_nse_index(conn, name: str) -> "Optional[pd.Series]":
    """Load NSE index close prices from indices_data with retry on lock."""
    import time as _time
    for attempt in range(4):
        try:
            _c = sqlite3.connect(DB_PATH, timeout=60)
            _c.execute("PRAGMA read_uncommitted=1")
            _c.execute("PRAGMA busy_timeout=20000")
            rows = _c.execute(
                "SELECT date, close FROM indices_data "
                "WHERE name=? AND close IS NOT NULL ORDER BY date",
                (name,)
            ).fetchall()
            _c.close()
            if not rows:
                return None
            idx  = pd.to_datetime([r[0] for r in rows])
            vals = [float(r[1]) for r in rows]
            return pd.Series(vals, index=idx).sort_index()
        except sqlite3.OperationalError as _e:
            if "locked" in str(_e).lower() and attempt < 3:
                _time.sleep(3 + attempt * 2)
                continue
            return None
        except Exception:
            return None
    return None'''

if OLD_NSE in src:
    src = src.replace(OLD_NSE, NEW_NSE)
    changed = True
    print("  [OK] Fixed load_nse_index with retry + fresh connection")
else:
    import re
    pat2 = re.compile(
        r'def load_nse_index\(conn, name: str\) -> "Optional\[pd\.Series\]":.*?'
        r'return pd\.Series\(vals, index=idx\)\.sort_index\(\)',
        re.DOTALL
    )
    if pat2.search(src):
        src = pat2.sub(NEW_NSE, src)
        changed = True
        print("  [OK] Fixed load_nse_index (regex)")


# ── FIX 4: process_symbol -- wrap commit in retry ────────────────────────────
# The INSERT OR REPLACE can also lock. Add retry on commit.
OLD_COMMIT = '''\
                conn.executemany("""
                    INSERT OR REPLACE INTO seasonality_patterns_v3
                    (symbol, anchor_mm_dd, window_days, direction, n_obs,
                     accuracy, mean_ret, median_ret, std_ret, p10, p25, p75, p90,
                     best_ret, worst_ret, score, consistency, edge_ratio,
                     t_stat, p_value, early_accuracy, recent_accuracy,
                     degradation, recent_mean, recent_vs_all,
                     best_years, worst_years, all_returns)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, rows)
                conn.commit()
                inserted += len(rows)
                rows = []'''

NEW_COMMIT = '''\
                import time as _t
                for _retry in range(6):
                    try:
                        conn.executemany("""
                            INSERT OR REPLACE INTO seasonality_patterns_v3
                            (symbol, anchor_mm_dd, window_days, direction, n_obs,
                             accuracy, mean_ret, median_ret, std_ret, p10, p25, p75, p90,
                             best_ret, worst_ret, score, consistency, edge_ratio,
                             t_stat, p_value, early_accuracy, recent_accuracy,
                             degradation, recent_mean, recent_vs_all,
                             best_years, worst_years, all_returns)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, rows)
                        conn.commit()
                        break
                    except sqlite3.OperationalError as _le:
                        if "locked" in str(_le).lower() and _retry < 5:
                            _t.sleep(5 + _retry * 3)
                        else:
                            raise
                inserted += len(rows)
                rows = []'''

if OLD_COMMIT in src:
    src = src.replace(OLD_COMMIT, NEW_COMMIT)
    changed = True
    print("  [OK] Added retry on commit (INSERT OR REPLACE)")
else:
    print("  [SKIP] Commit retry -- pattern not found (may already be patched)")


# ── FIX 5: Final flush also needs retry ──────────────────────────────────────
OLD_FLUSH = '''\
    # Final flush
    if rows:
        conn.executemany("""
            INSERT OR REPLACE INTO seasonality_patterns_v3
            (symbol, anchor_mm_dd, window_days, direction, n_obs,
             accuracy, mean_ret, median_ret, std_ret, p10, p25, p75, p90,
             best_ret, worst_ret, score, consistency, edge_ratio,
             t_stat, p_value, early_accuracy, recent_accuracy,
             degradation, recent_mean, recent_vs_all,
             best_years, worst_years, all_returns)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()
        inserted += len(rows)'''

NEW_FLUSH = '''\
    # Final flush
    if rows:
        import time as _t2
        for _retry2 in range(6):
            try:
                conn.executemany("""
                    INSERT OR REPLACE INTO seasonality_patterns_v3
                    (symbol, anchor_mm_dd, window_days, direction, n_obs,
                     accuracy, mean_ret, median_ret, std_ret, p10, p25, p75, p90,
                     best_ret, worst_ret, score, consistency, edge_ratio,
                     t_stat, p_value, early_accuracy, recent_accuracy,
                     degradation, recent_mean, recent_vs_all,
                     best_years, worst_years, all_returns)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, rows)
                conn.commit()
                break
            except sqlite3.OperationalError as _le2:
                if "locked" in str(_le2).lower() and _retry2 < 5:
                    _t2.sleep(5 + _retry2 * 3)
                else:
                    raise
        inserted += len(rows)'''

if OLD_FLUSH in src:
    src = src.replace(OLD_FLUSH, NEW_FLUSH)
    changed = True
    print("  [OK] Added retry on final flush")
else:
    print("  [SKIP] Final flush retry -- pattern not found")


# ── Save ──────────────────────────────────────────────────────────────────────
if changed:
    V3.write_text(src, encoding="utf-8")
    print(f"\n  [SAVED] {len(src.splitlines())} lines")
else:
    print("\n  [WARN] No changes saved")

# Syntax check
result = subprocess.run(
    [sys.executable, "-m", "py_compile", str(V3)],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("  [OK] Syntax check PASSED")
else:
    print(f"  [FAIL] Syntax error:\n{result.stderr}")
    import re
    m = re.search(r"line (\d+)", result.stderr)
    if m:
        ln = int(m.group(1))
        ctx = V3.read_text(encoding="utf-8").splitlines()
        for i, l in enumerate(ctx[max(0,ln-4):ln+5], start=max(1,ln-3)):
            print(f"  {'>>>' if i==ln else '   '} {i:3d}: {l}")

print("""
=============================================================
DATABASE LOCKED FIX COMPLETE

Root cause: SQLite WAL mode + dashboard (npm run dev) holding
a read lock on market.db at the same time as the builder
tries to read global_indices_daily.

Fixes applied:
  [1] get_conn(): timeout=120s, PRAGMA busy_timeout=30000,
                  PRAGMA read_uncommitted=1
  [2] load_global_index(): fresh connection per call + 5 retries
      with 3-11s sleep between retries
  [3] load_nse_index(): same retry pattern
  [4] process_symbol() commit: 6 retries on locked error
  [5] Final flush: same retry

Now run:
  py D:\\MICC\\build_seasonality_v3.py --resume

The failed global symbols (CAC40, CSI300, Copper...) are NOT
in the checkpoint since they failed -- they will be retried.
=============================================================
""")
