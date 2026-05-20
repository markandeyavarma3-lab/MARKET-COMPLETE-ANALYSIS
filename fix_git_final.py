import subprocess
from pathlib import Path

GIT  = r"C:\Program Files\Git\cmd\git.exe"
MICC = r"D:\MICC"

def git(args):
    r = subprocess.run([GIT] + args, capture_output=True, text=True, cwd=MICC)
    if r.stdout.strip(): print(f"  {r.stdout.strip()[:400]}")
    if r.stderr.strip(): print(f"  {r.stderr.strip()[:400]}")
    return r

print("[1] Removing node_modules and .next from git index...")
git(["rm", "-r", "--cached", "micc-dashboard/node_modules/", "--ignore-unmatch"])
git(["rm", "-r", "--cached", "micc-dashboard/.next/", "--ignore-unmatch"])

print("\n[2] Verifying .gitignore has the right entries...")
gi = Path(MICC) / ".gitignore"
content = gi.read_text(encoding="utf-8") if gi.exists() else ""
needed = ["node_modules/", ".next/", "*.node", "*.db", "*.parquet", ".env"]
for n in needed:
    if n not in content:
        content += f"\n{n}"
        print(f"  Added: {n}")
gi.write_text(content, encoding="utf-8")
print("  .gitignore OK")

print("\n[3] Committing the removal...")
git(["add", "-A"])
git(["commit", "-m", "Remove node_modules and .next from git tracking"])

print("\n[4] Pushing...")
r = git(["push", "origin", "main", "--force"])
if r.returncode == 0:
    print("\n  PUSHED: https://github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS")
else:
    print("\n  Auth needed - run this:")
    print(f'  & "{GIT}" -C "{MICC}" remote set-url origin https://markandeyavarma3-lab:YOUR_TOKEN@github.com/markandeyavarma3-lab/MARKET-COMPLETE-ANALYSIS.git')
    print(f'  & "{GIT}" -C "{MICC}" push origin main --force')

print("""
Future pushes (these 3 lines every time):
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "description"
  & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push origin main --force
""")
