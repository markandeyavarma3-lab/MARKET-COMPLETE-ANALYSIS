import sqlite3

DB = r"D:\marketDB\db\market.db"
c = sqlite3.connect(DB)

print("=" * 50)
print("market_snapshot columns:")
for col in c.execute("PRAGMA table_info(market_snapshot)").fetchall():
    print(f"  {col[0]:3d}  {col[1]:<25} {col[2]}")

print()
print("market_snapshot sample row:")
row = c.execute("SELECT * FROM market_snapshot LIMIT 1").fetchone()
print(" ", row)

print()
print("=" * 50)
print("Checking for indices-related tables:")
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
for t in tables:
    name = t[0]
    if any(x in name.lower() for x in ["ind", "nifty", "global", "index"]):
        print(f"\n  TABLE: {name}")
        cols = c.execute(f"PRAGMA table_info({name})").fetchall()
        for col in cols:
            print(f"    {col[0]:3d}  {col[1]:<25} {col[2]}")
        cnt = c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"    Rows: {cnt:,}")
        sample = c.execute(f"SELECT * FROM {name} LIMIT 1").fetchone()
        print(f"    Sample: {sample}")

print()
print("=" * 50)
print("All tables in DB:")
for t in tables:
    cnt = c.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
    print(f"  {t[0]:<40} {cnt:>10,} rows")

c.close()
