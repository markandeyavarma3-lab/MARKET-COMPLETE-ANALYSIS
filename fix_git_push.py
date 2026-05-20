import subprocess
from pathlib import Path

GIT  = r"C:\Program Files\Git\cmd\git.exe"
MICC = r"D:\MICC"

def git(args, cwd=MICC):
    r = subprocess.run([GIT] + args, capture_output=True, text=True, cwd=cwd)
    out = r.stdout.strip()
    err = r.stderr.strip()
    if out: print(f"  {out[:300]}")
    if err and "warning" not in err.lower(): print(f"  {err[:300]}")
    return r

print("[1] Updating .gitignore to exclude node_modules and large files...")
gi_path = Path(MICC) / ".gitignore"
gi = gi_path.read_text(encoding="utf-8") if gi_path.exists() else ""

additions = [
    "# Node modules (large, never commit)",
    "node_modules/",
    ".next/",
    "out/",
    "",
    "# Large binaries",
    "*.node",
    "*.exe",
    "*.dll",
    "*.dylib",
    "*.so",
    "",
    "# Database files",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.sqlite",
    "",
    "# Python cache",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "",
    "# Parquet files (huge)",
    "*.parquet",
    "",
    "# Secrets",
    ".env",
    "",
    "# Checkpoints",
    "pipeline_state.json",
    "adjusted.json",
    "agents/",
    "seasonality_stocks_checkpoint.json",
    "seasonality_v3_checkpoint.json",
]

for line in additions:
    if line not in gi:
        gi += line + "\n"

gi_path.write_text(gi, encoding="utf-8")
print("  .gitignore updated")

print("\n[2] Removing node_modules from git tracking (not from disk)...")
git(["rm", "-r", "--cached", "micc-dashboard/node_modules/", "--ignore-unmatch"])
git(["rm", "-r", "--cached", "micc-dashboard/.next/", "--ignore-unmatch"])

print("\n[3] Stage everything with new .gitignore applied...")
git(["add", "-A"])

print("\n[4] Commit...")
git(["commit", "-m", "Fix: exclude node_modules and large binaries from git"])

print("\n[5] Set upstream and push...")
git(["push", "--set-upstream", "origin", "main"])

print("""
======================================================================
  DONE
======================================================================

  If push still fails with auth error, run this (replace TOKEN):
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" remote set-url origin https://markandeyavarma3-lab:TOKEN@github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS.git
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push --set-upstream origin main

  IMPORTANT: Never paste tokens in chat.
  Store your token in Windows Credential Manager instead:
    Open: Control Panel > Credential Manager > Windows Credentials
    Add: github.com | username | token
  Then git will use it automatically forever.

  Future pushes (3 commands every time):
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "what changed"
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push
""")
