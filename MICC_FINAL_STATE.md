# MICC Final State -- Phase 28

## Architecture
- **DB**: D:/marketDB/db/market.db (~56GB SQLite WAL)
- **Dashboard**: D:/MICC/micc-dashboard (Next.js 14)
- **Agents**: D:/MICC/agent_*.py (10 agents)
- **Pipeline**: D:/MICC/data_pipeline/run_pipeline.py

## Pages (17)
/ overview, /analysis, /streaks, /indices, /options,
/macro, /mf, /watchlist, /backtest, /patterns, /patterns-v3,
/eta, /compare, /global, /alerts, /deep, /settings

## Agents (10)
Alpha (market pulse), Beta (momentum), Gamma (options/GEX),
Delta (sectors), Epsilon (FII/DII), Zeta (watchlist),
Eta (corporate/insider), Iota (global intel), Kappa (deep profile),
Alert (price/RSI/volume/pattern triggers)

## Data Sources
- 2,188 NSE stocks in stock_data (OHLCV back to ~2000)
- 52 global indices (SPX/DAX/Nikkei/Gold/BTC/DXY etc, back to 2000)
- NSE indices via indices_data table
- MF NAVs, Options Greeks, FII/DII, Insider trading, Corp events

## Seasonality Patterns
- **seasonality_patterns_v3**: 3d-60d (58 windows), all anchors
- NSE indices + global indices: ~1M patterns (done)
- NSE stocks: ~21M patterns (build_seasonality_v3_stocks.py, overnight)
- Key metrics: accuracy, mean_ret, score, t_stat, p_value,
  consistency, edge_ratio, degradation, recent_mean

## Daily Pipeline (one command)
```
py D:/MICC/data_pipeline/run_pipeline.py --with-engine
```
Phases: core -> delivery -> global_idx -> us_macro -> mf_nav ->
announcements -> insider -> greeks -> macro -> snapshot ->
parquet_sync -> fundamentals -> corp_actions -> epsilon ->
engine (7 agents) -> morning_brief

## Telegram Commands
/start /report /today /patterns /global /eta /alerts
/deep /kappa /stock /hot /watch /status

## Key Scripts
- py D:/MICC/morning_brief.py                    (9AM daily)
- py D:/MICC/agent_alert.py --send               (alert checks)
- py D:/MICC/fetch_global_indices_v2.py          (52 global symbols)
- py D:/MICC/build_seasonality_v3_stocks.py      (stock patterns)
- py D:/MICC/build_seasonality_v3_stocks.py --verify (check counts)
- py D:/MICC/micc_engine.py 7 --send             (all agents)