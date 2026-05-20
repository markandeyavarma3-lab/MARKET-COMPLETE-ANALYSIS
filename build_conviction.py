#!/usr/bin/env python3
"""
build_conviction.py - Unified Conviction Score (0-100)
7 layers fused with proportional weight redistribution.
Fixed column names: roce_pct/roe_pct, anchor_month, accuracy/avg_return_all/n_years
Run: python build_conviction.py
"""

import sqlite3, warnings
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
DB_PATH = Path("D:/marketDB/db/market.db")
TODAY   = datetime.today().strftime("%Y-%m-%d")
CUTOFF_DAYS = 30

WEIGHTS = {
    "momentum":    0.20,
    "seasonality": 0.20,
    "quality":     0.15,
    "delivery":    0.15,
    "insider":     0.10,
    "news":        0.10,
    "fundamental": 0.10,
}


def log(msg):
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)


def load_momentum(conn):
    log("  Loading momentum (symbol_technicals)...")
    try:
        df = pd.read_sql("""
            SELECT symbol, pct_above_sma20, adx_14, vol_surge_20d
            FROM symbol_technicals
            WHERE as_of_date >= date('now', '-7 days')
        """, conn)
        if df.empty: return pd.DataFrame(columns=["symbol", "momentum_score"])
        df["s_sma"] = df["pct_above_sma20"].clip(0, 100)
        df["s_adx"] = (df["adx_14"].clip(0, 60) / 60 * 100)
        df["s_vol"] = ((df["vol_surge_20d"].clip(0, 3) - 1) / 2 * 100).clip(0, 100)
        df["momentum_score"] = (0.50*df["s_sma"] + 0.30*df["s_adx"] + 0.20*df["s_vol"]).round(2)
        return df[["symbol", "momentum_score"]].dropna()
    except Exception as e:
        log("  [WARN] momentum: " + str(e))
        return pd.DataFrame(columns=["symbol", "momentum_score"])


def load_seasonality(conn):
    log("  Loading seasonality (seasonality_patterns)...")
    try:
        cur_month = datetime.today().month
        df = pd.read_sql("""
            SELECT symbol,
                   AVG(avg_return_all) AS mean_ret,
                   AVG(accuracy)       AS acc,
                   AVG(n_years)        AS n_obs
            FROM seasonality_patterns
            WHERE anchor_month = ?
              AND window_days BETWEEN 15 AND 25
            GROUP BY symbol
        """, conn, params=(cur_month,))
        if df.empty: return pd.DataFrame(columns=["symbol", "seasonality_score"])
        df["ic"] = (df["acc"] - 0.50).clip(-0.5, 0.5)
        df["ic_sqrt_n"] = df["ic"] * np.sqrt(df["n_obs"].clip(5, 100))
        df["seasonality_score"] = ((df["ic_sqrt_n"] + 3.5) / 7.0 * 100).clip(0, 100).round(2)
        return df[["symbol", "seasonality_score"]].dropna()
    except Exception as e:
        log("  [WARN] seasonality: " + str(e))
        return pd.DataFrame(columns=["symbol", "seasonality_score"])


def load_quality(conn):
    log("  Loading quality (symbol_quality_scores)...")
    try:
        df = pd.read_sql("SELECT symbol, f_score FROM symbol_quality_scores", conn)
        if df.empty: return pd.DataFrame(columns=["symbol", "quality_score"])
        df["quality_score"] = (df["f_score"] / 9.0 * 100).round(2)
        return df[["symbol", "quality_score"]].dropna()
    except Exception as e:
        log("  [WARN] quality: " + str(e))
        return pd.DataFrame(columns=["symbol", "quality_score"])


def load_delivery(conn):
    log("  Loading delivery (stock_delivery)...")
    try:
        df = pd.read_sql("""
            WITH ranked AS (
                SELECT symbol, date, delivery_pct,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                FROM stock_delivery
                WHERE delivery_pct IS NOT NULL AND delivery_pct > 0
            )
            SELECT symbol,
                   AVG(CASE WHEN rn <= 10 THEN delivery_pct END)  AS cur_del,
                   AVG(CASE WHEN rn BETWEEN 11 AND 20 THEN delivery_pct END) AS pri_del,
                   COUNT(CASE WHEN rn <= 10 THEN 1 END) AS n_cur
            FROM ranked
            GROUP BY symbol
            HAVING n_cur >= 5
        """, conn)
        if df.empty: return pd.DataFrame(columns=["symbol", "delivery_score"])
        df["delta"] = df["cur_del"] - df["pri_del"].fillna(df["cur_del"])
        df["base"]  = (df["cur_del"].clip(0, 80) / 80 * 70)
        df["bonus"] = (df["delta"].clip(-30, 30) / 30 * 30)
        df["delivery_score"] = (df["base"] + df["bonus"]).clip(0, 100).round(2)
        return df[["symbol", "delivery_score"]].dropna()
    except Exception as e:
        log("  [WARN] delivery: " + str(e))
        return pd.DataFrame(columns=["symbol", "delivery_score"])


def load_insider(conn):
    log("  Loading insider (insider_trading)...")
    try:
        cutoff = (datetime.today() - timedelta(days=CUTOFF_DAYS)).strftime("%Y-%m-%d")
        df = pd.read_sql("""
            SELECT symbol,
                   COUNT(*) AS buy_count,
                   SUM(COALESCE(value, 0)) / 1e7 AS value_cr
            FROM insider_trading
            WHERE transaction_type IN ('BUY','Buy','Purchase','PURCHASE')
              AND filing_date >= ?
            GROUP BY symbol
        """, conn, params=(cutoff,))
        if df.empty: return pd.DataFrame(columns=["symbol", "insider_score"])
        df["insider_score"] = (
            (df["buy_count"] * 15).clip(0, 60) +
            (df["value_cr"]  * 0.5).clip(0, 40)
        ).clip(0, 100).round(2)
        return df[["symbol", "insider_score"]].dropna()
    except Exception as e:
        log("  [WARN] insider: " + str(e))
        return pd.DataFrame(columns=["symbol", "insider_score"])


def load_news(conn):
    log("  Loading news (news_headlines)...")
    try:
        cutoff = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            df = pd.read_sql("""
                SELECT symbol, COUNT(*) AS n_news
                FROM symbol_news_daily
                WHERE date >= ? AND symbol IS NOT NULL
                GROUP BY symbol
            """, conn, params=(cutoff,))
        except Exception:
            df = pd.read_sql("""
                SELECT symbol, COUNT(*) AS n_news
                FROM news_headlines
                WHERE date >= ? AND symbol IS NOT NULL AND symbol != ''
                GROUP BY symbol
            """, conn, params=(cutoff,))
        if df.empty: return pd.DataFrame(columns=["symbol", "news_score"])
        df["news_score"] = ((df["n_news"] / 3.0) * 100).clip(0, 100).round(2)
        return df[["symbol", "news_score"]].dropna()
    except Exception as e:
        log("  [WARN] news: " + str(e))
        return pd.DataFrame(columns=["symbol", "news_score"])


def load_fundamental(conn):
    log("  Loading fundamentals (screener_fundamentals)...")
    try:
        df = pd.read_sql("""
            SELECT symbol, roce_pct, roe_pct, debt_equity
            FROM screener_fundamentals
            WHERE roce_pct IS NOT NULL
        """, conn)
        if df.empty: return pd.DataFrame(columns=["symbol", "fundamental_score"])
        df["roce_rank"] = df["roce_pct"].rank(pct=True) * 100
        df["roe_rank"]  = df["roe_pct"].rank(pct=True) * 100
        df["debt_pen"]  = (df["debt_equity"].clip(0, 3) / 3 * 20).fillna(0)
        df["fundamental_score"] = (
            0.55 * df["roce_rank"] + 0.45 * df["roe_rank"] - df["debt_pen"]
        ).clip(0, 100).round(2)
        return df[["symbol", "fundamental_score"]].dropna()
    except Exception as e:
        log("  [WARN] fundamental: " + str(e))
        return pd.DataFrame(columns=["symbol", "fundamental_score"])


def fuse_scores(dfs):
    log("  Fusing scores...")
    score_cols = list(WEIGHTS.keys())
    base = None
    for layer, df in dfs.items():
        if base is None:
            base = df.set_index("symbol")
        else:
            base = base.join(df.set_index("symbol"), how="outer")
    if base is None or base.empty:
        return pd.DataFrame()

    for layer in score_cols:
        col = layer + "_score"
        if col not in base.columns:
            base[col] = np.nan

    base = base.reset_index()
    results = []
    for _, row in base.iterrows():
        total_w = total_s = 0.0
        signal_count = 0
        layer_scores = {}
        for layer, w in WEIGHTS.items():
            col = layer + "_score"
            v = row.get(col, np.nan)
            if pd.notna(v):
                total_w += w
                total_s += w * v
                signal_count += 1
                layer_scores[layer] = round(float(v), 2)
            else:
                layer_scores[layer] = None

        conviction = round(total_s / total_w, 2) if total_w > 0 else 0.0
        best_layer = max(
            [(l, (layer_scores[l] or 0) * WEIGHTS[l]) for l in score_cols if layer_scores.get(l) is not None],
            key=lambda x: x[1],
            default=("unknown", 0)
        )
        results.append({
            "symbol":            row["symbol"],
            "conviction_score":  conviction,
            "momentum_score":    layer_scores.get("momentum"),
            "seasonality_score": layer_scores.get("seasonality"),
            "quality_score":     layer_scores.get("quality"),
            "delivery_score":    layer_scores.get("delivery"),
            "insider_score":     layer_scores.get("insider"),
            "news_score":        layer_scores.get("news"),
            "fundamental_score": layer_scores.get("fundamental"),
            "signal_count":      signal_count,
            "top_reason":        best_layer[0],
            "computed_date":     TODAY,
        })

    out = pd.DataFrame(results)
    out = out[out["signal_count"] >= 2].copy()
    out = out.sort_values("conviction_score", ascending=False).reset_index(drop=True)
    log("  Fused " + str(len(out)) + " symbols with >=2 signal layers")
    return out


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS symbol_conviction (
            symbol TEXT PRIMARY KEY, conviction_score REAL,
            momentum_score REAL, seasonality_score REAL, quality_score REAL,
            delivery_score REAL, insider_score REAL, news_score REAL,
            fundamental_score REAL, signal_count INTEGER,
            top_reason TEXT, computed_date TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conviction_score ON symbol_conviction(conviction_score DESC)")
    conn.commit()


def main():
    log("Starting conviction score build (Phase 29 fixed)...")
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    create_table(conn)

    dfs = {
        "momentum":    load_momentum(conn),
        "seasonality": load_seasonality(conn),
        "quality":     load_quality(conn),
        "delivery":    load_delivery(conn),
        "insider":     load_insider(conn),
        "news":        load_news(conn),
        "fundamental": load_fundamental(conn),
    }
    for layer, df in dfs.items():
        log("    " + layer + ": " + str(len(df)) + " symbols")

    out = fuse_scores(dfs)
    if out.empty:
        log("ERROR: no conviction scores computed")
        conn.close()
        return

    out.to_sql("symbol_conviction", conn, if_exists="replace", index=False)
    conn.commit()

    log("\n  DONE - " + str(len(out)) + " symbols written to symbol_conviction")
    log("  Score range: " + str(round(out["conviction_score"].min(), 1)) + " - " + str(round(out["conviction_score"].max(), 1)))
    log("  Top 10:")
    for _, r in out.head(10).iterrows():
        log("    " + str(r["symbol"]).ljust(12) + "  " + str(r["conviction_score"]) + "  (" + str(r["signal_count"]) + " layers, top=" + str(r["top_reason"]) + ")")

    conn.close()


if __name__ == "__main__":
    main()
