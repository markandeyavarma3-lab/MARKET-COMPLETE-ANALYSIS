"""
MICC Backfill - processes all NSE INDICES MW files.
Run: py backfill_indices.py
"""
import sys
from pathlib import Path

sys.path.insert(0, r'D:\MICC')

from pipeline.ingestion.router import route_file

NSE_INDICES_ROOT = Path(r'C:\Users\marka\OneDrive\Desktop\NSE Data\NSE INDICES')

files = sorted(NSE_INDICES_ROOT.rglob('MW-*.csv'))
print(f"Found {len(files)} MW index files\n")

ok = fail = total_rows = 0

for i, f in enumerate(files, 1):
    metadata = {
        "path":       f,
        "parser_key": "indices_csv",
        "table":      "indices_data",
        "category":   None,
    }
    result = route_file(metadata)
    if result["success"]:
        total_rows += result["rows_written"]
        print(f"[{i}/{len(files)}] OK {result['rows_written']:>6} rows <- {f.name}")
        ok += 1
    else:
        print(f"[{i}/{len(files)}] FAIL {f.name}: {result['error']}")
        fail += 1

print(f"\nDone. Success={ok} Failed={fail} Total rows={total_rows:,}")
