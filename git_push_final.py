import subprocess, sys, os
from pathlib import Path

GIT  = r"C:\Program Files\Git\cmd\git.exe"
MICC = r"D:\MICC"

def git(args, cwd=MICC):
    cmd = [GIT] + args
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.stdout.strip(): print(f"  {r.stdout.strip()[:400]}")
    if r.stderr.strip(): print(f"  {r.stderr.strip()[:400]}")
    return r

print("[1] Adding git to PATH permanently...")
ps_cmd = (
    '[System.Environment]::SetEnvironmentVariable('
    '"Path", '
    '[System.Environment]::GetEnvironmentVariable("Path","User") + ";C:\\Program Files\\Git\\cmd", '
    '"User")'
)
subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
print("  Done. Restart terminal after this script to use 'git' directly.")

print("\n[2] Git setup...")
git(["init"])
git(["branch", "-M", "main"])
git(["config", "user.name",  "markandeyavarma3-lab"])
git(["config", "user.email", "markandeyavarma3@users.noreply.github.com"])
git(["remote", "remove", "origin"])
git(["remote", "add", "origin",
     "https://github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS.git"])

print("\n[3] Staging all files...")
git(["add", "-A"])

print("\n[4] Committing...")
git(["commit", "-m", "MICC: full codebase - agents, dashboard, pipeline, scrapers"])

print("\n[5] Pushing...")
r = git(["push", "-u", "origin", "main", "--force"])

if r.returncode == 0:
    print("\n  LIVE: https://github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS")
else:
    print("""
  Authentication needed. Do this ONCE:

  Step 1: Create token
    Open: https://github.com/settings/tokens/new
    Note: MICC
    Expiration: No expiration
    Scope: check [x] repo
    Click Generate token
    Copy the token (ghp_xxxxxxxxxxxx)

  Step 2: Run in PowerShell (paste your token when asked for password):
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push -u origin main --force

  Username: markandeyavarma3-lab
  Password: <paste token here>

  Step 3: After token works once, future pushes are just:
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "update"
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push
""")
