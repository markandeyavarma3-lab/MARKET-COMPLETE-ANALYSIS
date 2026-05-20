import sqlite3
c = sqlite3.connect(r"D:\marketDB\db\market.db")
c.execute("UPDATE my_portfolio SET target_1=1550, target_2=1650 WHERE symbol='RELIANCE'")
c.commit()
n = c.execute("SELECT symbol, entry_price, stop_loss, target_1, target_2, status FROM my_portfolio").fetchall()
print("All positions:")
for r in n:
    print(f"  {r}")
c.close()
