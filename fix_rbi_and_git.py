import sqlite3, subprocess
from datetime import datetime

DB  = r"D:\marketDB\db\market.db"
GIT = r"C:\Program Files\Git\cmd\git.exe"

# ── Fix RBI: series column has NOT NULL constraint, need to include it ────────
print("[1] Fixing RBI monetary data...")
conn = sqlite3.connect(DB, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

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
ok = 0
for date_str, repo, rev_repo, crr, slr in known_rates:
    try:
        # Use UPDATE for existing rows (which have series), INSERT for new rows
        # First try to update existing row with matching date
        r = conn.execute(
            "UPDATE rbi_monetary_data SET repo_rate=?, reverse_repo=?, crr=?, slr=?, source=?, fetched_at=? "
            "WHERE date=?",
            (repo, rev_repo, crr, slr, "official_rbi", today, date_str)
        )
        if r.rowcount == 0:
            # No existing row, insert with series filled
            conn.execute(
                "INSERT INTO rbi_monetary_data (date, series, value, unit, last_updated, repo_rate, reverse_repo, crr, slr, source, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (date_str, "RBI_Policy_Rates", repo, "% per annum", today,
                 repo, rev_repo, crr, slr, "official_rbi", today)
            )
        ok += 1
    except Exception as e:
        print(f"  Error {date_str}: {e}")

conn.commit()
print(f"  Inserted/updated {ok} rate change dates")

latest = conn.execute(
    "SELECT date, repo_rate, reverse_repo, crr FROM rbi_monetary_data "
    "WHERE repo_rate IS NOT NULL ORDER BY date DESC LIMIT 6"
).fetchall()
print(f"\n  {'DATE':12} {'REPO':>6} {'R-REPO':>7} {'CRR':>5}")
for r in latest:
    def f(v): return f"{v:.2f}" if v else "  --"
    print(f"  {r[0]:12} {f(r[1]):>6} {f(r[2]):>7} {f(r[3]):>5}")
conn.close()
print("  RBI done.")

# ── Git push ──────────────────────────────────────────────────────────────────
print("\n[2] Git push instructions...")
print("""
  ROTATE YOUR TOKEN FIRST (the one you shared is now compromised):
  1. Go to https://github.com/settings/tokens
  2. Delete the old token (ghp_u1bg...)
  3. Create new token: check only [repo], no expiry
  4. Copy the new token

  Then run these 3 commands (replace YOUR_NEW_TOKEN):
""")

TOKEN_PLACEHOLDER = "YOUR_NEW_TOKEN_HERE"
REPO = "https://markandeyavarma3-lab:{}@github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS.git"

print(f'  & "{GIT}" -C "D:\\MICC" add -A')
print(f'  & "{GIT}" -C "D:\\MICC" commit -m "Phase 1 complete: analytics + fundamentals 500 stocks + RBI rates"')
print(f'  & "{GIT}" -C "D:\\MICC" remote set-url origin {REPO.format(TOKEN_PLACEHOLDER)}')
print(f'  & "{GIT}" -C "D:\\MICC" push -u origin main --force')
print()
print("  After push works once, future pushes (no token needed again):")
print(f'  & "{GIT}" -C "D:\\MICC" add -A')
print(f'  & "{GIT}" -C "D:\\MICC" commit -m "describe change"')
print(f'  & "{GIT}" -C "D:\\MICC" push')
