"""
daily_ml_update.py
==================
Runs HMM regime detection + XGB conviction scoring.
Add to Windows Task Scheduler to run after daily_update.py.

Run: py D:\MICC\daily_ml_update.py
"""
import subprocess, sys
from pathlib import Path
from datetime import datetime

DA  = Path(r"D:\MICC")
PY  = sys.executable

def run(script, label, timeout=180):
    print(f"  [{datetime.now().strftime("%H:%M:%S")}] {label}...", flush=True)
    try:
        r = subprocess.run(
            [PY, str(DA / script)],
            cwd=str(DA), timeout=timeout, capture_output=True, text=True
        )
        if r.returncode == 0:
            # Extract last meaningful line from stdout
            lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
            last  = lines[-1] if lines else "OK"
            print(f"    OK: {last}")
        else:
            print(f"    FAILED: {r.stderr[:200]}")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT after {timeout}s")
        return False
    except Exception as e:
        print(f"    ERROR: {e}")
        return False

print(f"MICC Daily ML Update -- {datetime.now().strftime("%Y-%m-%d %H:%M")}")
print("=" * 45)

results = {
    "hmm":    run("agent_hmm.py",                  "HMM Regime Detection",    timeout=120),
    "xgb":    run("train_conviction_xgb.py --score","XGB Conviction Scoring",  timeout=300),
    "fusion": run("agent_fusion.py",               "Fusion Agent",            timeout=120),
}

print()
ok = sum(results.values())
print(f"Results: {ok}/{len(results)} OK")
for k, v in results.items():
    print(f"  {k:<10} {'OK' if v else 'FAILED'}")

if ok == len(results):
    print("\nAll ML models updated successfully.")
else:
    print("\nSome tasks failed -- check output above.")