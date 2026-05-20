import sqlite3

c = sqlite3.connect(r"D:\marketDB\db\market.db")

result = c.execute("""
SELECT MIN(date), MAX(date), COUNT(*)
FROM stock_data
WHERE symbol='HDFCBANK'
""").fetchone()

print(result)