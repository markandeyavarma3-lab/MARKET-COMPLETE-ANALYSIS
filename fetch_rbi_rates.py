import sqlite3, sys, json
from datetime import datetime
from pathlib import Path

DB = r"D:\marketDB\db\market.db"

try:
    import requests
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "requests", "--break-system-packages", "-q"])
    import requests

HEADERS = {"User-Agent": "Mozilla/5.0 MICC/1.0"}

print("RBI DBIE repo rate fetcher")

conn = sqlite3.connect(DB, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("""
    CREATE TABLE IF NOT EXISTS rbi_monetary_data (
        date        TEXT PRIMARY KEY,
        repo_rate   REAL,
        reverse_repo REAL,
        crr         REAL,
        slr         REAL,
        bank_rate   REAL,
        msf_rate    REAL,
        source      TEXT,
        fetched_at  TEXT
    )
""")
conn.commit()

rows_before = conn.execute("SELECT COUNT(*) FROM rbi_monetary_data").fetchone()[0]
print(f"  Existing rows: {rows_before}")

inserted = 0

# ── Source 1: RBI DBIE API ────────────────────────────────────────────────────
print("\n[1] Trying RBI DBIE API...")
try:
    # RBI DBIE series: FMRPRT = Repo Rate
    urls = [
        "https://rbidbie.rbi.org.in/api/dbie/master/seriesData?series=FMRPRT&startDate=01-01-2000&endDate=31-12-2026&frequency=D",
        "https://api.rbi.org.in/api/CompositeData?seriesName=FMRPRT&startDate=01-01-2000&endDate=31-12-2026",
    ]
    data = None
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                print(f"  Got response from: {url[:60]}")
                break
        except Exception:
            continue

    if data:
        # Handle different response formats
        records = data.get("data", data.get("Data", data.get("records", [])))
        if isinstance(records, list):
            for rec in records:
                date_str = rec.get("TIME_PERIOD") or rec.get("date") or rec.get("Date")
                val      = rec.get("OBS_VALUE") or rec.get("value") or rec.get("Value")
                if date_str and val:
                    try:
                        # Normalize date to YYYY-MM-DD
                        for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]:
                            try:
                                dt = datetime.strptime(str(date_str).strip(), fmt)
                                date_str = dt.strftime("%Y-%m-%d")
                                break
                            except Exception:
                                continue
                        conn.execute(
                            "INSERT OR REPLACE INTO rbi_monetary_data "
                            "(date,repo_rate,source,fetched_at) VALUES (?,?,?,?)",
                            (date_str, float(val), "rbi_dbie",
                             datetime.now().strftime("%Y-%m-%d"))
                        )
                        inserted += 1
                    except Exception:
                        continue
            conn.commit()
            print(f"  Inserted {inserted} rows from RBI DBIE")
        else:
            print(f"  Unexpected data format: {str(data)[:200]}")
    else:
        print("  RBI DBIE API not reachable")
except Exception as e:
    print(f"  Error: {e}")

# ── Source 2: FRED (Federal Reserve) - India policy rate ─────────────────────
if inserted < 10:
    print("\n[2] Trying FRED API (India policy rate)...")
    try:
        # FRED series: INDIRLTLT01STM = India lending rate
        # INTDSRINM193N = India discount rate
        fred_series = [
            ("INTDSRINM193N", "repo_rate"),
            ("INDIRLTLT01STM", "repo_rate"),
        ]
        for series_id, field in fred_series:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200 and "," in r.text:
                lines = r.text.strip().split("\n")
                for line in lines[1:]:  # skip header
                    parts = line.strip().split(",")
                    if len(parts) >= 2 and parts[1].strip() != ".":
                        try:
                            date_str = parts[0].strip()
                            val = float(parts[1].strip())
                            conn.execute(
                                "INSERT OR REPLACE INTO rbi_monetary_data "
                                "(date,repo_rate,source,fetched_at) VALUES (?,?,?,?)",
                                (date_str, val, "fred",
                                 datetime.now().strftime("%Y-%m-%d"))
                            )
                            inserted += 1
                        except Exception:
                            continue
                conn.commit()
                print(f"  Inserted {inserted} rows from FRED ({series_id})")
                if inserted > 100:
                    break
    except Exception as e:
        print(f"  Error: {e}")

# ── Source 3: Manual known rates (hardcoded recent history) ──────────────────
print("\n[3] Adding known RBI rate history (hardcoded 2019-2026)...")
# Official RBI repo rates from public announcements
known_rates = [
    # (effective_date, repo, reverse_repo, crr, slr)
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

for date_str, repo, rev_repo, crr, slr in known_rates:
    conn.execute(
        "INSERT OR REPLACE INTO rbi_monetary_data "
        "(date,repo_rate,reverse_repo,crr,slr,source,fetched_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (date_str, repo, rev_repo, crr, slr, "hardcoded",
         datetime.now().strftime("%Y-%m-%d"))
    )
conn.commit()
inserted_hc = len(known_rates)
print(f"  Inserted {inserted_hc} hardcoded rate change dates")

# ── Report ────────────────────────────────────────────────────────────────────
total = conn.execute("SELECT COUNT(*) FROM rbi_monetary_data").fetchone()[0]
latest = conn.execute(
    "SELECT date, repo_rate, reverse_repo, crr, slr FROM rbi_monetary_data "
    "ORDER BY date DESC LIMIT 10"
).fetchall()

print(f"\n  Total rows in rbi_monetary_data: {total}")
print(f"\n  {'DATE':12} {'REPO':>6} {'REV_REPO':>9} {'CRR':>6} {'SLR':>6}")
for r in latest:
    def f(v): return f"{v:6.2f}" if v else "    --"
    print(f"  {r[0]:12} {f(r[1])} {f(r[2]):>9} {f(r[3])} {f(r[4])}")

conn.close()
print("\nDone. rbi_monetary_data table populated.")
print("Latest repo rate: " + str(latest[0][1] if latest else "N/A") + "%")
