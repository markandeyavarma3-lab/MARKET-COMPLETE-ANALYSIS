"""
diagnose_adjusted.py
Figures out WHY all symbols are failing in jugaad-data.
Run: py diagnose_adjusted.py
"""
import warnings
warnings.filterwarnings("ignore")
from datetime import date
from jugaad_data.nse import stock_df

# Test a few known large-caps
test_syms = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "WIPRO"]

for sym in test_syms:
    try:
        df = stock_df(symbol=sym, from_date=date(2020,1,1), to_date=date(2026,1,1), series="EQ")
        if df is None or df.empty:
            print(f"  {sym}: EMPTY (None or empty df)")
        else:
            print(f"  {sym}: OK  {len(df)} rows  cols={list(df.columns)[:5]}")
    except Exception as e:
        print(f"  {sym}: ERROR — {e}")
