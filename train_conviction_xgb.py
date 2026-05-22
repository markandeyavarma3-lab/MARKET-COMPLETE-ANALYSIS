"""
train_conviction_xgb.py  --  XGBoost conviction model
Trains on historical signals + forward returns.
Features: 14 technical + fundamental + seasonal features
Label: 5d forward return > 1%

Run: py D:\MICC\train_conviction_xgb.py
     py D:\MICC\train_conviction_xgb.py --score   (just score current universe)
"""
import sys, sqlite3, json
from pathlib import Path
from datetime import datetime

DA      = Path(r"D:\MICC")
DB_PATH = r"D:\marketDB\db\market.db"
SCORE_ONLY = "--score" in sys.argv

def log(msg): print(f"  {msg}", flush=True)

# ── Install deps ──────────────────────────────────────────────────────────
try:
    import xgboost as xgb
    import numpy as np
    import pandas as pd
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "xgboost", "numpy", "pandas",
                    "--break-system-packages", "-q"])
    import xgboost as xgb
    import numpy as np
    import pandas as pd

MODEL_PATH = DA / "conviction_xgb.json"

FEATURES = [
    "rsi_14", "adx_14", "atr_14_pct", "pct_above_sma20",
    "vol_surge_20d", "delivery_pct",
    "roce", "roe", "debt_equity", "pe_ratio",
    "oos_accuracy", "score_v2_best",
    "insider_buy_30d", "n_signals_30d",
]

def load_training_data():
    log("Loading training data...")
    conn = sqlite3.connect(DB_PATH, timeout=30)

    # Base: signals_history with forward returns
    df = pd.read_sql(
        "SELECT sh.symbol, sh.run_date, sh.score,"
        "  COALESCE(sh.forward_return_5d, 0) AS fwd5d"
        " FROM signals_history sh"
        " WHERE sh.forward_return_5d IS NOT NULL"
        " ORDER BY sh.run_date DESC LIMIT 50000",
        conn
    )
    log(f"  signals_history: {len(df)} rows")
    if len(df) < 100:
        conn.close()
        raise ValueError("Need at least 100 signals with forward returns")

    # Technicals
    tech = pd.read_sql(
        "SELECT symbol, rsi_14, adx_14, atr_14_pct, pct_above_sma20, vol_surge_20d"
        " FROM symbol_technicals",
        conn
    )
    # Delivery
    deliv = pd.read_sql(
        "SELECT symbol, AVG(CAST(delivery_pct AS REAL)) AS delivery_pct"
        " FROM stock_delivery"
        " WHERE date >= date('now', '-30 days')"
        " GROUP BY symbol",
        conn
    )
    # Fundamentals
    try:
        fund = pd.read_sql(
            "SELECT symbol, roce, roe, debt_equity, pe_ratio"
            " FROM screener_fundamentals_v2 WHERE scrape_ok=1",
            conn
        )
    except Exception:
        fund = pd.DataFrame(columns=["symbol","roce","roe","debt_equity","pe_ratio"])
    # Best OOS accuracy per symbol
    try:
        oos = pd.read_sql(
            "SELECT symbol,"
            "  MAX(CAST(oos_accuracy AS REAL)) AS oos_accuracy,"
            "  MAX(CAST(score_v2 AS REAL)) AS score_v2_best"
            " FROM seasonality_patterns_v3"
            " WHERE fdr_reject=1 AND (overfit=0 OR overfit IS NULL)"
            "   AND oos_accuracy IS NOT NULL"
            " GROUP BY symbol",
            conn
        )
    except Exception:
        oos = pd.DataFrame(columns=["symbol","oos_accuracy","score_v2_best"])
    # Insider buys last 30d
    try:
        ins = pd.read_sql(
            "SELECT symbol, COUNT(*) AS insider_buy_30d"
            " FROM insider_trading"
            " WHERE transaction_type='BUY'"
            "   AND filing_date >= date('now', '-30 days')"
            " GROUP BY symbol",
            conn
        )
    except Exception:
        ins = pd.DataFrame(columns=["symbol","insider_buy_30d"])
    # Signal count per symbol last 30d
    sig_cnt = pd.read_sql(
        "SELECT symbol, COUNT(*) AS n_signals_30d"
        " FROM signals_history"
        " WHERE run_date >= date('now', '-30 days')"
        " GROUP BY symbol",
        conn
    )
    conn.close()

    # Merge all
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

    # Label: 5d forward return > 1%
    df["label"] = (df["fwd5d"] > 1.0).astype(int)
    log(f"  Positive labels: {df['label'].mean():.1%}")
    return df

def train(df):
    log("Training XGBoost model...")
    X = df[FEATURES].fillna(df[FEATURES].median())
    y = df["label"]

    # Train/test split by date
    split = int(len(df) * 0.8)
    X_tr, X_te = X.iloc[:split], X.iloc[split:]
    y_tr, y_te = y.iloc[:split], y.iloc[split:]

    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=(y_tr==0).sum()/(y_tr==1).sum(),
        use_label_encoder=False, eval_metric="logloss",
        random_state=42, verbosity=0
    )
    model.fit(X_tr, y_tr,
              eval_set=[(X_te, y_te)],
              verbose=False)

    from sklearn.metrics import roc_auc_score, accuracy_score
    preds = model.predict_proba(X_te)[:,1]
    auc   = roc_auc_score(y_te, preds)
    acc   = accuracy_score(y_te, model.predict(X_te))
    log(f"  Test AUC={auc:.3f}  Acc={acc:.1%}")

    # Feature importance
    imp = sorted(zip(FEATURES, model.feature_importances_),
                 key=lambda x: -x[1])
    log("  Top features:")
    for feat, score in imp[:5]:
        log(f"    {feat:<20} {score:.3f}")

    model.save_model(str(MODEL_PATH))
    log(f"  Model saved: {MODEL_PATH}")
    return model, auc

def score_universe(model):
    log("Scoring current universe...")
    conn = sqlite3.connect(DB_PATH, timeout=30)

    # Load current features for all symbols
    tech = pd.read_sql(
        "SELECT symbol, rsi_14, adx_14, atr_14_pct, pct_above_sma20, vol_surge_20d"
        " FROM symbol_technicals", conn)
    try:
        deliv = pd.read_sql(
            "SELECT symbol, AVG(CAST(delivery_pct AS REAL)) AS delivery_pct"
            " FROM stock_delivery WHERE date >= date('now', '-30 days')"
            " GROUP BY symbol", conn)
    except Exception:
        deliv = pd.DataFrame(columns=["symbol","delivery_pct"])
    try:
        fund = pd.read_sql(
            "SELECT symbol, roce, roe, debt_equity, pe_ratio"
            " FROM screener_fundamentals_v2 WHERE scrape_ok=1", conn)
    except Exception:
        fund = pd.DataFrame(columns=["symbol","roce","roe","debt_equity","pe_ratio"])
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
    try:
        ins = pd.read_sql(
            "SELECT symbol, COUNT(*) AS insider_buy_30d"
            " FROM insider_trading"
            " WHERE transaction_type='BUY'"
            "   AND filing_date >= date('now', '-30 days')"
            " GROUP BY symbol", conn)
    except Exception:
        ins = pd.DataFrame(columns=["symbol","insider_buy_30d"])
    sig_cnt = pd.read_sql(
        "SELECT symbol, COUNT(*) AS n_signals_30d"
        " FROM signals_history WHERE run_date >= date('now', '-30 days')"
        " GROUP BY symbol", conn)

    conn.close()

    df = tech
    for other in [deliv, fund, oos, ins, sig_cnt]:
        df = df.merge(other, on="symbol", how="left")
    df["insider_buy_30d"] = df["insider_buy_30d"].fillna(0)
    df["n_signals_30d"]   = df["n_signals_30d"].fillna(0)
    df["oos_accuracy"]    = df["oos_accuracy"].fillna(0.5)
    df["score_v2_best"]   = df["score_v2_best"].fillna(0)

    X    = df[FEATURES].fillna(df[FEATURES].median())
    prob = model.predict_proba(X)[:,1]
    df["xgb_score"] = (prob * 100).round(1)

    # Save to DB
    conn2 = sqlite3.connect(DB_PATH, timeout=30)
    conn2.execute("PRAGMA journal_mode=WAL")
    conn2.execute(
        "CREATE TABLE IF NOT EXISTS symbol_conviction_xgb"
        " (symbol TEXT PRIMARY KEY, xgb_score REAL, updated_at TEXT)"
    )
    now = datetime.now().isoformat()
    batch = [(row.symbol, row.xgb_score, now) for _, row in df.iterrows()]
    conn2.executemany(
        "INSERT OR REPLACE INTO symbol_conviction_xgb (symbol,xgb_score,updated_at)"
        " VALUES (?,?,?)", batch)
    conn2.commit()
    conn2.close()
    log(f"  Saved {len(batch)} XGB scores to symbol_conviction_xgb")

    top = df.nlargest(10, "xgb_score")[["symbol","xgb_score"]]
    log("  Top 10 by XGB score:")
    for _, r in top.iterrows():
        log(f"    {r.symbol:<15} {r.xgb_score:.1f}")
    return df

print("XGBoost Conviction Model")
print("=" * 40)

if SCORE_ONLY and MODEL_PATH.exists():
    log("Loading existing model...")
    model = xgb.XGBClassifier()
    model.load_model(str(MODEL_PATH))
    score_universe(model)
else:
    try:
        df   = load_training_data()
        model, auc = train(df)
        score_universe(model)
        print(f"Done. AUC={auc:.3f}  Scores saved to symbol_conviction_xgb")
    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()