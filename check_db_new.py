import sqlite3

c = sqlite3.connect(r"D:\marketDB\db\market.db")

# Check market_snapshot columns
cols = c.execute("PRAGMA table_info(market_snapshot)").fetchall()
for col in cols:
    print(col)

# Check indices_data table
try:
    cols2 = c.execute("PRAGMA table_info(indices_data)").fetchall()
    print("indices_data:", cols2[:5])
except Exception as e:
cd