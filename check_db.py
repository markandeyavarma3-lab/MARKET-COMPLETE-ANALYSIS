import sqlite3
conn = sqlite3.connect(r"D:\marketDB\db\market.db")
cur = conn.cursor()
print("window_extremes count:", cur.execute("SELECT COUNT(*) FROM window_extremes").fetchone())
print("window_days:", cur.execute("SELECT DISTINCT window_days FROM window_extremes ORDER BY window_days").fetchall())
print("window_stats count:", cur.execute("SELECT COUNT(*) FROM window_stats").fetchone())
print("window_days in stats:", cur.execute("SELECT DISTINCT window_days FROM window_stats ORDER BY window_days").fetchall())
print("sample extreme:", cur.execute("SELECT * FROM window_extremes LIMIT 3").fetchall())
conn.close()