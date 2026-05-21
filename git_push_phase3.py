import subprocess, sys
from pathlib import Path
from datetime import datetime

MICC = Path(r'D:\MICC')
GIT  = r'C:\Program Files\Git\cmd\git.exe'

def git(args, cwd=None):
    r = subprocess.run([GIT] + args, cwd=str(cwd or MICC),
                       capture_output=True, text=True)
    if r.stdout.strip(): print(' ', r.stdout.strip()[:200])
    if r.stderr.strip() and r.returncode != 0: print('  ERR:', r.stderr.strip()[:200])
    return r.returncode == 0

msg = f'Phase 3A/3B: fix all broken pages + OOS validation + scraper resume ({datetime.now().strftime("%Y-%m-%d")})'

print('Adding all changes...')
git(['-C', str(MICC), 'add', '-A'])

print('Committing...')
ok = git(['-C', str(MICC), 'commit', '-m', msg])
if not ok:
    print('  Nothing to commit or commit failed')

print('Pushing...')
ok = git(['-C', str(MICC), 'push', 'origin', 'main', '--force'])
if ok:
    print('  Pushed to GitHub OK')
else:
    print('  Push failed -- check credentials')
    print('  Manual: & "C:\\Program Files\\Git\\cmd\\git.exe" -C D:\\MICC push origin main --force')