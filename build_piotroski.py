#!/usr/bin/env python3
"""
build_piotroski.py - Piotroski F-Score (single-quarter adapted)
Since quarterly_balance only has 1 row per symbol, we score 9 criteria
that work on a single quarter across income/balance/cashflow.
Run: python build_piotroski.py
"""

import json, sqlite3, warnings
from datetime import datetime
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")
DB_PATH = Path("D:/marketDB/db/market.db")
TODAY   = datetime.today().strftime("%Y-%m-%d")


def _get(d, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                f = float(v)
                if not (np.isnan(f) or np.isinf(f)):
                    return f
            except Exception:
                pass
    return None


def _s(v, default=0.0):
    if v is None: return default
    try:
        f = float(v)
        return default if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return default


def load_latest(conn, symbol, table):
    row = conn.execute(
        "SELECT data_json FROM " + table + " WHERE symbol=? ORDER BY report_date DESC LIMIT 1",
        (symbol,)
    ).fetchone()
    if not row: return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}


def compute_fscore(symbol, bal, inc, cf):
    if not bal and not inc:
        return None

    total_assets = _s(_get(bal, "Total Assets", "TotalAssets"), 1.0)
    net_income   = _s(_get(inc,
        "Net Income", "NetIncome",
        "Net Income Common Stockholders",
        "Net Income Continuous Operations"))
    cfo = _s(_get(cf,
        "Operating Cash Flow", "OperatingCashFlow",
        "Cash Flow From Continuing Operating Activities"))
    capex = abs(_s(_get(cf, "Capital Expenditure", "CapitalExpenditure")))
    fcf   = cfo - capex

    revenue = _s(_get(inc, "Total Revenue", "Revenue", "TotalRevenue"), 1.0)
    cogs    = _s(_get(inc,
        "Cost Of Revenue", "Reconciled Cost Of Revenue",
        "CostOfRevenue", "CostOfGoodsAndServicesSold"))
    gross_m = (revenue - cogs) / revenue if revenue > 0 else 0.0

    ca = _s(_get(bal, "Current Assets", "CurrentAssets"))
    cl = _s(_get(bal, "Current Liabilities", "CurrentLiabilities"), 1.0)
    cr = ca / cl if cl > 0 else 0.0

    equity     = _s(_get(bal,
        "Common Stock Equity", "Stockholders Equity",
        "Total Equity Gross Minority Interest"), 1.0)
    total_debt = _s(_get(bal, "Total Debt", "Net Debt"))
    eps        = _s(_get(inc, "Basic EPS", "Diluted EPS", "BasicEPS", "DilutedEPS"))

    roa = net_income / total_assets if total_assets > 0 else 0.0
    at  = revenue / total_assets if total_assets > 0 else 0.0

    F1 = int(roa > 0)
    F2 = int(cfo > 0)
    F3 = int(cfo > net_income)
    F4 = int(gross_m > 0)
    F5 = int(at > 0.1)
    F6 = int(total_debt <= equity)
    F7 = int(cr > 1.0)
    F8 = int(fcf > 0)
    F9 = int(eps > 0)

    f_score = F1 + F2 + F3 + F4 + F5 + F6 + F7 + F8 + F9

    return {
        "symbol":               symbol,
        "f_score":              f_score,
        "roa":                  round(roa, 4),
        "roa_delta":            0.0,
        "cfo":                  round(cfo, 0),
        "accrual":              round((net_income - cfo) / total_assets, 4) if total_assets else 0.0,
        "leverage_delta":       0.0,
        "liquidity_delta":      round(cr - 1.0, 4),
        "dilution":             0,
        "gross_margin_delta":   round(gross_m, 4),
        "asset_turnover_delta": round(at, 4),
        "computed_date":        TODAY,
        "data_quarters":        1,
    }


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS symbol_quality_scores (
            symbol TEXT PRIMARY KEY, f_score INTEGER,
            roa REAL, roa_delta REAL, cfo REAL, accrual REAL,
            leverage_delta REAL, liquidity_delta REAL, dilution INTEGER,
            gross_margin_delta REAL, asset_turnover_delta REAL,
            computed_date TEXT, data_quarters INTEGER
        )
    """)
    conn.commit()


def _flush(conn, batch):
    conn.executemany("""
        INSERT OR REPLACE INTO symbol_quality_scores
        (symbol, f_score, roa, roa_delta, cfo, accrual, leverage_delta,
         liquidity_delta, dilution, gross_margin_delta, asset_turnover_delta,
         computed_date, data_quarters)
        VALUES
        (:symbol, :f_score, :roa, :roa_delta, :cfo, :accrual, :leverage_delta,
         :liquidity_delta, :dilution, :gross_margin_delta, :asset_turnover_delta,
         :computed_date, :data_quarters)
    """, batch)
    conn.commit()


def main():
    print("[" + datetime.now().strftime("%H:%M:%S") + "] Piotroski F-Score (single-quarter mode)...")
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    create_table(conn)

    symbols = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM quarterly_income ORDER BY symbol"
    ).fetchall()]
    print("  Found " + str(len(symbols)) + " symbols with quarterly income data")

    ok = skipped = errors = 0
    batch = []

    for i, sym in enumerate(symbols, 1):
        try:
            bal = load_latest(conn, sym, "quarterly_balance")
            inc = load_latest(conn, sym, "quarterly_income")
            cf  = load_latest(conn, sym, "quarterly_cashflow")
            result = compute_fscore(sym, bal, inc, cf)
            if result:
                batch.append(result)
                ok += 1
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print("  [WARN] " + sym + ": " + str(e))

        if len(batch) >= 200:
            _flush(conn, batch)
            batch = []

        if i % 500 == 0:
            print("  [" + str(i) + "/" + str(len(symbols)) + "] ok=" + str(ok) + " skipped=" + str(skipped) + " errors=" + str(errors))

    if batch:
        _flush(conn, batch)

    conn.close()
    print("\n  DONE - ok=" + str(ok) + " skipped=" + str(skipped) + " errors=" + str(errors))
    print("  symbol_quality_scores: " + str(ok) + " rows written")


if __name__ == "__main__":
    main()
