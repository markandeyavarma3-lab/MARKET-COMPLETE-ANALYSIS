import subprocess, sys, os
from pathlib import Path

# ── Fix git PATH ──────────────────────────────────────────────────────────────
GIT_PATHS = [
    r"C:\Program Files\Git\cmd",
    r"C:\Program Files\Git\bin",
    r"C:\Program Files (x86)\Git\cmd",
]

print("[1] Finding git installation...")
git_exe = None
for p in GIT_PATHS:
    candidate = Path(p) / "git.exe"
    if candidate.exists():
        git_exe = str(candidate)
        print(f"  Found: {git_exe}")
        break

if not git_exe:
    print("  Git not found in standard paths. Searching...")
    r = subprocess.run("where git", shell=True, capture_output=True, text=True)
    if r.returncode == 0:
        git_exe = r.stdout.strip().split("\n")[0]
        print(f"  Found: {git_exe}")
    else:
        print("  Git not found. Download from https://git-scm.com/download/win and install.")
        sys.exit(1)

GIT = git_exe

def git(cmd, cwd=r"D:\MICC"):
    full = GIT + " " + cmd
    r = subprocess.run(full, shell=True, capture_output=True, text=True, cwd=cwd)
    out = r.stdout.strip()
    err = r.stderr.strip()
    if out: print(f"  {out[:300]}")
    if err: print(f"  {err[:300]}")
    return r

print("\n[2] Setting up git repo...")
MICC = r"D:\MICC"

git("init")
git("branch -M main")
git('config user.name "markandeyavarma3-lab"')
git('config user.email "markandeyavarma3@users.noreply.github.com"')
git("add -A")
git('commit -m "MICC Phase 1: conviction + fusion + fundamentals scraper"')
git("remote remove origin")
git("remote add origin https://github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS.git")

print("\n[3] Pushing to GitHub...")
r = git("push -u origin main")
if r.returncode != 0:
    print("""
  Push failed. This usually means GitHub needs a token.
  Steps:
  1. Go to https://github.com/settings/tokens/new
  2. Note: "MICC"  |  Expiration: No expiration
  3. Check: [x] repo  (full access)
  4. Click Generate token
  5. Copy the token (starts with ghp_...)
  6. Run this in PowerShell:
       & "C:\\Program Files\\Git\\cmd\\git.exe" push -u origin main
     When asked for password, paste the token
""")
else:
    print("\n  PUSHED: https://github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS")

print(f"""
======================================================================
  FOR FUTURE PUSHES -- run these 3 lines every time:
  (copy-paste this block)

  & "C:\\Program Files\\Git\\cmd\\git.exe" -C D:\\MICC add -A
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C D:\\MICC commit -m "update"
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C D:\\MICC push

  OR add git to PATH permanently (do once):
  [System.Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\\Program Files\\Git\\cmd", "User")
  Then restart terminal and just use: git add -A / git commit / git push
======================================================================
""")
