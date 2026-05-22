"""
train_conviction_xgb.py  --  XGBoost conviction model

Correct signals_history columns: fwd_1d, fwd_3d, fwd_5d, fwd_10d
If fwd_5d is missing, runs oos_backtest.py first to fill it.

Run: py D:\MICC\train_conviction_xgb.py
     py D:\MICC\train_conviction_xgb.py --score
"""
import sys, sqlite3, json, subprocess
from pathlib import Path
from datetime import datetime

DA      = Path(r"D:\MICC")
DB_PATH = r"D:\marketDB\db\market.db"
SCORE_ONLY = "--score" in sys.argv

def log(msg): print(f"  {msg}", flush=True)

try:
    import xgboost as xgb
    import numpy as np
    import pandas as pd
    from sklearn.metrics import roc_auc_score, accuracy_score
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "xgboost", "scikit-learn", "numpy", "pandas",
                    "--break-system-packages", "-q"])
    import xgboost as xgb
    import numpy as np
    import pandas as pd
    from sklearn.metrics import roc_auc_score, accuracy_score

MODEL_PATH = DA / "conviction_xgb.json"

FEATURES = [
    "rsi_14", "adx_14", "atr_14_pct", "pct_above_sma20",
    "vol_surge_20d", "delivery_pct",
    "roce", "roe", "debt_equity", "pe_ratio",
    "oos_accuracy", "score_v2_best",
    "insider_buy_30d", "n_signals_30d",
]

# ── Ensure fwd_5d column exists in signals_history ───────────────────────
def ensure_fwd_columns():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(signals_history)").fetchall()}
    missing = [c for c in ["fwd_1d","fwd_3d","fwd_5d","fwd_10d"] if c not in cols]
    for c in missing:
        conn.execute(f"ALTER TABLE signals_history ADD COLUMN {c} REAL")
        log(f"Added column: {c}")
    conn.commit()
    # Check how many fwd_5d are filled
    n_filled = conn.execute(
        "SELECT COUNT(*) FROM signals_history WHERE fwd_5d IS NOT NULL"
    ).fetchone()[0]
    n_total  = conn.execute("SELECT COUNT(*) FROM signals_history").fetchone()[0]
    conn.close()
    log(f"signals_history: {n_total} rows, {n_filled} with fwd_5d")
    return n_filled, n_total

# ── Compute fwd_5d from parquet if not filled ─────────────────────────────
def compute_fwd_returns():
    log("Computing forward returns from parquet (running oos_backtest --quick)...")
    result = subprocess.run(
        [sys.executable, str(DA / "oos_backtest.py"), "--quick"],
        cwd=str(DA), capture_output=True, text=True, timeout=300
    )
    if result.returncode == 0:
        log("  oos_backtest --quick: OK")
    else:
        log(f"  oos_backtest failed: {result.stderr[:200]}")
        log("  Computing directly from parquet...")
        _compute_fwd_direct()

def _compute_fwd_direct():
    """Compute fwd_5d directly from parquet files without oos_backtest."""
    PARQUET = Path(r"D:\marketDB\stocks\all")
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute(
        "SELECT rowid, symbol, run_date FROM signals_history"
        " WHERE fwd_5d IS NULL ORDER BY run_date DESC LIMIT 5000"
    ).fetchall()
    log(f"  Computing fwd_5d for {len(rows)} signals...")
    updated = 0
    cache = {}
    for rowid, sym, run_date in rows:
        if sym not in cache:
            # Try multiple parquet year files
            closes = {}
            for yr in range(2020, 2027):
                p = PARQUET / sym / f"{sym}_{yr}.parquet"
                if not p.exists(): continue
                try:
                    df = pd.read_parquet(p, columns=["date","close"])
                    df["date"] = df["date"].astype(str)
                    for _, r in df.iterrows():
                        closes[r["date"]] = float(r["close"])
                except Exception:
                    pass
            cache[sym] = closes
        closes = cache[sym]
        if not closes: continue
        sorted_dates = sorted(closes.keys())
        try:
            idx = sorted_dates.index(run_date)
        except ValueError:
            # Find nearest date
            nearest = min(sorted_dates, key=lambda d: abs(d.replace("-","") - run_date.replace("-","")) if d else 999999, default=None)
            if not nearest: continue
            idx = sorted_dates.index(nearest)
        if idx + 5 >= len(sorted_dates): continue
        p0 = closes[sorted_dates[idx]]
        p5 = closes[sorted_dates[idx + 5]]
        if p0 and p0 > 0:
            fwd = (p5 - p0) / p0 * 100
            conn.execute("UPDATE signals_history SET fwd_5d=? WHERE rowid=?", (round(fwd,4), rowid))
            updated += 1
    conn.commit()
    conn.close()
    log(f"  Updated fwd_5d for {updated} signals")

# ── Load training data ────────────────────────────────────────────────────
def load_training_data():
    log("Loading training data...")
    conn = sqlite3.connect(DB_PATH, timeout=30)
    # Use correct column name fwd_5d
    df = pd.read_sql(
        "SELECT symbol, run_date, score, fwd_5d"
        " FROM signals_history"
        " WHERE fwd_5d IS NOT NULL"
        " ORDER BY run_date DESC LIMIT 50000",
        conn
    )
    log(f"  Training rows: {len(df)}")
    if len(df) < 50:
        conn.close()
        raise ValueError(f"Only {len(df)} labeled signals -- run oos_backtest.py first")
    # Technicals
    tech = pd.read_sql(
        "SELECT symbol, rsi_14, adx_14, atr_14_pct, pct_above_sma20, vol_surge_20d"
        " FROM symbol_technicals", conn)
    # Delivery
    try:
        deliv = pd.read_sql(
            "SELECT symbol, AVG(CAST(delivery_pct AS REAL)) AS delivery_pct"
            " FROM stock_delivery WHERE date >= date('now','-30 days')"
            " GROUP BY symbol", conn)
    except Exception:
        deliv = pd.DataFrame(columns=["symbol","delivery_pct"])
    # Fundamentals
    try:
        fund = pd.read_sql(
            "SELECT symbol, roce, roe, debt_equity, pe_ratio"
            " FROM screener_fundamentals_v2 WHERE scrape_ok=1", conn)
    except Exception:
        fund = pd.DataFrame(columns=["symbol","roce","roe","debt_equity","pe_ratio"])
    # OOS accuracy
    try:
        oos = pd.read_sql(
            "SELECT symbol,"
            "  MAX(CAST(oos_accuracy AS REAL)) AS oos_accuracy,"
            "  MAX(CAST(score_v2 AS REAL)) AS score_v2_best"
            " FROM seasonality_patterns_v3"
            " WHERE fdr_reject=1 AND (overfit=0 OR overfit IS NULL)"
            "   AND oos_accuracy IS NOT NULL GROUP BY symbol", conn)
    except Exception:
        oos = pd.DataFrame(columns=["symbol","oos_accuracy","score_v2_best"])
    # Insider buys
    try:
        ins = pd.read_sql(
            "SELECT symbol, COUNT(*) AS insider_buy_30d"
            " FROM insider_trading"
            " WHERE transaction_type='BUY'"
            "   AND filing_date >= date('now','-30 days')"
            " GROUP BY symbol", conn)
    except Exception:
        ins = pd.DataFrame(columns=["symbol","insider_buy_30d"])
    # Signal count
    sig_cnt = pd.read_sql(
        "SELECT symbol, COUNT(*) AS n_signals_30d"
        " FROM signals_history WHERE run_date >= date('now','-30 days')"
        " GROUP BY symbol", conn)
    conn.close()
    # Merge
    df = df.merge(tech,    on="symbol", how="left")
    df = df.merge(deliv,   on="symbol", how="left")
    df = df.merge(fund,    on="symbol", how="left")
    df = df.merge(oos,     on="symbol", how="left")
    df = df.merge(ins,     on="symbol", how="left")
    df = df.merge(sig_cnt, on="symbol", how="left")
    df["insider_buy_30d"] = df["insider_buy_30d"].fillna(0)
    df["n_signals_30d"]   = df["n_signals_30d"].fillna(0)
    df["oos_accuracy"]    = df["oos_accuracy"].fillna(0.5)
    df["score_v2_best"]   = df["score_v2_best"].fillna(0)
    df["label"] = (df["fwd_5d"] > 1.0).astype(int)
    log(f"  Positive labels: {df['label'].mean():.1%}  ({df['label'].sum()} of {len(df)})")
    return df

# ── Train ─────────────────────────────────────────────────────────────────
def train(df):
    log("Training XGBoost...")
    X = df[FEATURES].fillna(df[FEATURES].median())
    y = df["label"]
    split = int(len(df) * 0.8)
    X_tr, X_te = X.iloc[:split], X.iloc[split:]
    y_tr, y_te = y.iloc[:split], y.iloc[split:]
    pos_weight = max(1.0, float((y_tr==0).sum()) / max(float((y_tr==1).sum()), 1))
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=pos_weight,
        eval_metric="logloss", random_state=42, verbosity=0
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
    preds = model.predict_proba(X_te)[:,1]
    auc   = roc_auc_score(y_te, preds)
    acc   = accuracy_score(y_te, model.predict(X_te))
    log(f"  AUC={auc:.3f}  Acc={acc:.1%}  Train={len(X_tr)}  Test={len(X_te)}")
    imp = sorted(zip(FEATURES, model.feature_importances_), key=lambda x:-x[1])
    log("  Top 5 features:")
    for feat, score in imp[:5]:
        log(f"    {feat:<22} {score:.3f}")
    model.save_model(str(MODEL_PATH))
    log(f"  Saved: {MODEL_PATH}")
    return model, auc

# ── Score universe ────────────────────────────────────────────────────────
def score_universe(model):
    log("Scoring current universe...")
    conn = sqlite3.connect(DB_PATH, timeout=30)
    tech = pd.read_sql(
        "SELECT symbol, rsi_14, adx_14, atr_14_pct, pct_above_sma20, vol_surge_20d"
        " FROM symbol_technicals", conn)
    dfs  = [tech]
    for sql, cols in [
        ("SELECT symbol, AVG(CAST(delivery_pct AS REAL)) AS delivery_pct"
         " FROM stock_delivery WHERE date>=date('now','-30 days') GROUP BY symbol",
         ["symbol","delivery_pct"]),
        ("SELECT symbol, roce, roe, debt_equity, pe_ratio"
         " FROM screener_fundamentals_v2 WHERE scrape_ok=1",
         ["symbol","roce","roe","debt_equity","pe_ratio"]),
    ]:
        try:
            dfs.append(pd.read_sql(sql, conn))
        except Exception:
            dfs.append(pd.DataFrame(columns=cols))
    try:
        dfs.append(pd.read_sql(
            "SELECT symbol, MAX(CAST(oos_accuracy AS REAL)) AS oos_accuracy,"
            " MAX(CAST(score_v2 AS REAL)) AS score_v2_best"
            " FROM seasonality_patterns_v3"
            " WHERE fdr_reject=1 AND (overfit=0 OR overfit IS NULL)"
            "   AND oos_accuracy IS NOT NULL GROUP BY symbol", conn))
    except Exception:
        dfs.append(pd.DataFrame(columns=["symbol","oos_accuracy","score_v2_best"]))
    try:
        dfs.append(pd.read_sql(
            "SELECT symbol, COUNT(*) AS insider_buy_30d FROM insider_trading"
            " WHERE transaction_type='BUY' AND filing_date>=date('now','-30 days')"
            " GROUP BY symbol", conn))
    except Exception:
        dfs.append(pd.DataFrame(columns=["symbol","insider_buy_30d"]))
    dfs.append(pd.read_sql(
        "SELECT symbol, COUNT(*) AS n_signals_30d FROM signals_history"
        " WHERE run_date>=date('now','-30 days') GROUP BY symbol", conn))
    conn.close()
    df = dfs[0]
    for other in dfs[1:]:
        df = df.merge(other, on="symbol", how="left")
    df["insider_buy_30d"] = df.get("insider_buy_30d", pd.Series(0, index=df.index)).fillna(0)
    df["n_signals_30d"]   = df.get("n_signals_30d",   pd.Series(0, index=df.index)).fillna(0)
    df["oos_accuracy"]    = df.get("oos_accuracy",    pd.Series(0.5, index=df.index)).fillna(0.5)
    df["score_v2_best"]   = df.get("score_v2_best",   pd.Series(0, index=df.index)).fillna(0)
    X    = df[FEATURES].fillna(df[FEATURES].median())
    prob = model.predict_proba(X)[:,1]
    df["xgb_score"] = (prob * 100).round(1)
    conn2 = sqlite3.connect(DB_PATH, timeout=30)
    conn2.execute("PRAGMA journal_mode=WAL")
    conn2.execute(
        "CREATE TABLE IF NOT EXISTS symbol_conviction_xgb"
        " (symbol TEXT PRIMARY KEY, xgb_score REAL, updated_at TEXT)")
    now_ts = datetime.now().isoformat()
    batch = [(r.symbol, r.xgb_score, now_ts) for _, r in df.iterrows()]
    conn2.executemany(
        "INSERT OR REPLACE INTO symbol_conviction_xgb (symbol,xgb_score,updated_at)"
        " VALUES (?,?,?)", batch)
    conn2.commit()
    conn2.close()
    top = df.nlargest(10, "xgb_score")[["symbol","xgb_score"]]
    log(f"Saved {len(batch)} XGB scores.  Top 10:")
    for _, r in top.iterrows():
        log(f"  {r.symbol:<15} {r.xgb_score:.1f}")
    return df

# ── Main ──────────────────────────────────────────────────────────────────
print("XGBoost Conviction Model")
print("=" * 40)

# Step 0: ensure fwd columns exist + are populated
n_filled, n_total = ensure_fwd_columns()
if n_filled < 50 and not SCORE_ONLY:
    log(f"Only {n_filled} labeled signals -- running oos_backtest to fill...")
    compute_fwd_returns()
    n_filled, _ = ensure_fwd_columns()
    log(f"After fill: {n_filled} labeled signals")

if SCORE_ONLY and MODEL_PATH.exists():
    log("Loading existing model...")
    model = xgb.XGBClassifier()
    model.load_model(str(MODEL_PATH))
    score_universe(model)
else:
    try:
        df = load_training_data()
        model, auc = train(df)
        score_universe(model)
        print(f"\nDone. AUC={auc:.3f}. Scores in symbol_conviction_xgb.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()