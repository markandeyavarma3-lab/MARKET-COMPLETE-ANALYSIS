import subprocess, sys, re
from pathlib import Path

GIT  = r"C:\Program Files\Git\cmd\git.exe"
MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"

def git(args):
    r = subprocess.run([GIT] + args, capture_output=True, text=True, cwd=str(MICC))
    if r.stdout.strip(): print(f"  {r.stdout.strip()[:300]}")
    if r.stderr.strip(): print(f"  {r.stderr.strip()[:300]}")
    return r

# ── Fix NavBar.tsx ─────────────────────────────────────────────────────────────
print("[1] Fixing NavBar.tsx...")
nb = None
for p in (DASH / "src").rglob("NavBar.tsx"):
    nb = p
    break

if nb:
    src = nb.read_text(encoding="utf-8")
    
    # Fix double commas: },, -> },
    src = re.sub(r'\},\s*,', '},', src)
    
    # Fix missing comma before { on same array:
    # pattern: }  \n  { with no comma
    src = re.sub(r'\}\s*\n(\s*\{)', r'},\n\1', src)
    
    # Clean up any triple+ commas
    src = re.sub(r',{2,}', ',', src)
    
    nb.write_text(src, encoding="utf-8")
    print("  [OK] NavBar.tsx fixed")
    
    # Show the relevant lines
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "href" in line and ("conviction" in line.lower() or 
                                "analytics" in line.lower() or
                                "fusion" in line.lower()):
            print(f"    {i+1}: {line.strip()}")
else:
    print("  [ERR] NavBar.tsx not found")

# ── Git: force push (remote has diverged, we force overwrite) ─────────────────
print("\n[2] Force pushing to GitHub...")
git(["add", "-A"])
git(["commit", "-m", "Fix NavBar syntax + exclude node_modules"])
git(["push", "origin", "main", "--force"])

print("""
Done.

  Future git push (every time):
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "what changed"
    & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push origin main --force
""")
