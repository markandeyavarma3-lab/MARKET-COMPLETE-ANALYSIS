import sqlite3, sys
from datetime import datetime

DB = r"D:\marketDB\db\market.db"
conn = sqlite3.connect(DB, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

# ── Check actual rbi_monetary_data schema ─────────────────────────────────────
print("[1] Checking rbi_monetary_data schema...")
cols = [r[1] for r in conn.execute("PRAGMA table_info(rbi_monetary_data)").fetchall()]
print(f"  Existing columns: {cols}")
count = conn.execute("SELECT COUNT(*) FROM rbi_monetary_data").fetchone()[0]
print(f"  Existing rows: {count}")
sample = conn.execute("SELECT * FROM rbi_monetary_data LIMIT 3").fetchall()
for r in sample:
    print(f"  Sample: {r}")

# ── Add missing columns ────────────────────────────────────────────────────────
print("\n[2] Adding missing columns...")
needed = [
    ("repo_rate",    "REAL"),
    ("reverse_repo", "REAL"),
    ("crr",          "REAL"),
    ("slr",          "REAL"),
    ("bank_rate",    "REAL"),
    ("msf_rate",     "REAL"),
    ("source",       "TEXT"),
    ("fetched_at",   "TEXT"),
]
# Also check what the date column is called
date_col = None
for c in cols:
    if "date" in c.lower():
        date_col = c
        break
print(f"  Date column: {date_col}")

for col, typ in needed:
    if col not in cols:
        try:
            conn.execute(f"ALTER TABLE rbi_monetary_data ADD COLUMN {col} {typ}")
            print(f"  Added: {col}")
        except Exception as e:
            print(f"  Skip {col}: {e}")
conn.commit()
cols = [r[1] for r in conn.execute("PRAGMA table_info(rbi_monetary_data)").fetchall()]
print(f"  Columns now: {cols}")

# ── Insert hardcoded RBI rate history ─────────────────────────────────────────
print("\n[3] Inserting RBI rate history...")

# Map to actual date column name
dc = date_col if date_col else "date"

known_rates = [
    ("2019-02-07", 6.25, 6.00, 4.0, 19.5),
    ("2019-04-04", 6.00, 5.75, 4.0, 19.5),
    ("2019-06-06", 5.75, 5.50, 4.0, 19.0),
    ("2019-08-07", 5.40, 5.15, 4.0, 19.0),
    ("2019-10-04", 5.15, 4.90, 4.0, 18.75),
    ("2019-12-05", 5.15, 4.90, 4.0, 18.75),
    ("2020-02-06", 5.15, 4.90, 4.0, 18.5),
    ("2020-03-27", 4.40, 4.00, 3.0, 18.5),
    ("2020-05-22", 4.00, 3.35, 3.0, 18.0),
    ("2020-10-09", 4.00, 3.35, 3.0, 18.0),
    ("2021-04-07", 4.00, 3.35, 3.0, 18.0),
    ("2021-06-04", 4.00, 3.35, 4.0, 18.0),
    ("2022-04-08", 4.00, 3.35, 4.0, 18.0),
    ("2022-05-04", 4.40, 3.35, 4.0, 18.0),
    ("2022-06-08", 4.90, 3.35, 4.5, 18.0),
    ("2022-08-05", 5.40, 3.35, 4.5, 18.0),
    ("2022-09-30", 5.90, 3.35, 4.5, 18.0),
    ("2022-12-07", 6.25, 3.35, 4.5, 18.0),
    ("2023-02-08", 6.50, 3.35, 4.5, 18.0),
    ("2023-04-06", 6.50, 3.35, 4.5, 18.0),
    ("2023-06-08", 6.50, 3.35, 4.5, 18.0),
    ("2023-08-10", 6.50, 3.35, 4.5, 18.0),
    ("2023-10-06", 6.50, 3.35, 4.5, 18.0),
    ("2023-12-08", 6.50, 3.35, 4.5, 18.0),
    ("2024-02-08", 6.50, 3.35, 4.5, 18.0),
    ("2024-04-05", 6.50, 3.35, 4.5, 18.0),
    ("2024-06-07", 6.50, 3.35, 4.5, 18.0),
    ("2024-08-08", 6.50, 3.35, 4.5, 18.0),
    ("2024-10-09", 6.50, 3.35, 4.5, 18.0),
    ("2024-12-06", 6.50, 3.35, 4.5, 18.0),
    ("2025-02-07", 6.25, 3.35, 4.0, 18.0),
    ("2025-04-09", 6.00, 3.35, 4.0, 18.0),
    ("2025-06-06", 5.75, 3.35, 4.0, 18.0),
]

today = datetime.now().strftime("%Y-%m-%d")
inserted = 0
for date_str, repo, rev_repo, crr, slr in known_rates:
    try:
        conn.execute(
            f"INSERT OR REPLACE INTO rbi_monetary_data "
            f"({dc}, repo_rate, reverse_repo, crr, slr, source, fetched_at) "
            f"VALUES (?,?,?,?,?,?,?)",
            (date_str, repo, rev_repo, crr, slr, "official", today)
        )
        inserted += 1
    except Exception as e:
        print(f"  Error on {date_str}: {e}")

conn.commit()
print(f"  Inserted {inserted} rows")

# ── Verify ────────────────────────────────────────────────────────────────────
print("\n[4] Latest rates:")
latest = conn.execute(
    f"SELECT {dc}, repo_rate, reverse_repo, crr, slr "
    f"FROM rbi_monetary_data WHERE repo_rate IS NOT NULL "
    f"ORDER BY {dc} DESC LIMIT 8"
).fetchall()
print(f"  {'DATE':12} {'REPO':>6} {'R-REPO':>7} {'CRR':>5} {'SLR':>5}")
for r in latest:
    def f(v): return f"{v:.2f}" if v else "  --"
    print(f"  {r[0]:12} {f(r[1]):>6} {f(r[2]):>7} {f(r[3]):>5} {f(r[4]):>5}")

total = conn.execute("SELECT COUNT(*) FROM rbi_monetary_data").fetchone()[0]
print(f"\n  Total rows: {total}")
conn.close()
print("Done.")
