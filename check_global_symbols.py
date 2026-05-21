import sqlite3
DB = r'D:\marketDB\db\market.db'
conn = sqlite3.connect(DB, timeout=10)
print('All symbols in global_indices_daily:')
rows = conn.execute('SELECT DISTINCT symbol FROM global_indices_daily ORDER BY symbol').fetchall()
for r in rows: print(' ', r[0])
print(f'Total: {len(rows)}')
conn.close()