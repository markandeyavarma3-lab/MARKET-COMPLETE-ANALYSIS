# -*- coding: utf-8 -*-
r"""
fix_and_git_setup.py  --  Run from D:\MICC
"""
from pathlib import Path
import subprocess, sys

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"

def write(path, content, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

def run(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=str(cwd or MICC))
    if r.stdout.strip(): print(f"    {r.stdout.strip()[:200]}")
    if r.stderr.strip() and r.returncode != 0: print(f"    ERR: {r.stderr.strip()[:200]}")
    return r

def syntax_check(path):
    r = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                       capture_output=True, text=True)
    print(f"  Syntax: {'OK' if r.returncode==0 else r.stderr[:200]}")
    return r.returncode == 0

# =============================================================================
# [1]  Fix agent_fusion.py  (triple-quote bug on watchlist line)
# =============================================================================
print("\n[1/5] Fixing agent_fusion.py ...")
af = MICC / "agent_fusion.py"
if af.exists():
    src = af.read_text(encoding="utf-8")
    # The bad pattern:  item.get("symbol","  <-- three quotes
    src = src.replace('item.get("symbol","\"").strip()', 'item.get("symbol","").strip()')
    src = src.replace("item.get(\"symbol\",\"\"\").strip()", 'item.get("symbol","").strip()')
    # Catch it with a simple find
    if '""").strip()' in src:
        src = src.replace('""").strip()', '").strip()')
    write(af, src, "agent_fusion.py")
    syntax_check(af)
else:
    print("  [SKIP] not found")

# =============================================================================
# [2]  Rewrite validate_patterns_oos.py  (all SQL as string concat, no indent issues)
# =============================================================================
print("\n[2/5] Writing validate_patterns_oos.py ...")

# Build content as a plain list of lines -- zero triple-quote or indent risk
L = []
A = L.append

A("# -*- coding: utf-8 -*-")
A("import sqlite3, json, sys")
A("from datetime import datetime")
A("")
A("DB             = r'D:\\marketDB\\db\\market.db'")
A("OOS_YEAR       = 2019")
A("MIN_OOS        = 5")
A("OVERFIT_THRESH = 0.10")
A("TEST_MODE      = '--test' in sys.argv")
A("")
A("print(f'OOS Validation  OOS year>={OOS_YEAR}  overfit>{OVERFIT_THRESH*100:.0f}pp')")
A("print(f'Mode: {\"TEST 10k rows\" if TEST_MODE else \"FULL RUN\"}')")
A("")
A("conn = sqlite3.connect(DB, timeout=60)")
A("conn.execute('PRAGMA journal_mode=WAL')")
A("conn.execute('PRAGMA synchronous=NORMAL')")
A("conn.execute('PRAGMA cache_size=-512000')")
A("")
A("# --- Step 1: Add columns ---")
A("print('\\n[1] Columns...')")
A("existing = [r[1] for r in conn.execute('PRAGMA table_info(seasonality_patterns_v3)').fetchall()]")
A("for col, typedef in [")
A("    ('oos_accuracy',    'REAL'),")
A("    ('oos_n_obs',       'INTEGER'),")
A("    ('oos_degradation', 'REAL'),")
A("    ('overfit',         'INTEGER DEFAULT 0'),")
A("]:")
A("    if col not in existing:")
A("        conn.execute(f'ALTER TABLE seasonality_patterns_v3 ADD COLUMN {col} {typedef}')")
A("        print(f'  Added: {col}')")
A("    else:")
A("        print(f'  OK:    {col}')")
A("conn.commit()")
A("")
A("# --- Step 2: Temp table ---")
A("conn.execute('DROP TABLE IF EXISTS _oos_temp')")
A("conn.execute('CREATE TEMP TABLE _oos_temp (id INTEGER PRIMARY KEY, oos_accuracy REAL, oos_n_obs INTEGER, oos_degradation REAL, overfit INTEGER)')")
A("")
A("# --- Step 3: Process rows ---")
A("lim = 'LIMIT 10000' if TEST_MODE else ''")
A("rows = conn.execute(f'SELECT id, accuracy, all_returns FROM seasonality_patterns_v3 WHERE all_returns IS NOT NULL {lim}').fetchall()")
A("print(f'\\n[2] Processing {len(rows):,} rows...')")
A("batch = []")
A("t0 = datetime.now()")
A("")
A("def parse_yr_ret(item):")
A("    if isinstance(item, dict):")
A("        return item.get('year', 0), item.get('ret', 0)")
A("    if isinstance(item, (list, tuple)) and len(item) >= 2:")
A("        try: return int(str(item[0])[:4]), float(item[1])")
A("        except: return 0, 0")
A("    return 0, 0")
A("")
A("SQL_INS = ('INSERT OR REPLACE INTO _oos_temp'")
A("           '(oos_accuracy,oos_n_obs,oos_degradation,overfit,id) VALUES(?,?,?,?,?)')")
A("")
A("for i, (pid, in_acc, raw) in enumerate(rows):")
A("    if i % 200000 == 0 and i > 0:")
A("        elapsed = (datetime.now()-t0).total_seconds()")
A("        eta = (len(rows)-i)/(i/elapsed)/60")
A("        print(f'  {i:,}/{len(rows):,}  {i/elapsed:.0f} rows/s  ETA {eta:.1f} min')")
A("    try:")
A("        returns = json.loads(raw)")
A("    except Exception:")
A("        continue")
A("    if not isinstance(returns, list) or not returns:")
A("        continue")
A("    oos = [parse_yr_ret(r)[1] for r in returns if parse_yr_ret(r)[0] >= OOS_YEAR]")
A("    n   = len(oos)")
A("    if n < MIN_OOS:")
A("        batch.append((None, n, None, 0, pid))")
A("        continue")
A("    oos_acc = sum(1 for v in oos if v > 0) / n")
A("    in_a    = float(in_acc) if in_acc is not None else 0.5")
A("    degrade = in_a - oos_acc")
A("    overfit = 1 if degrade > OVERFIT_THRESH else 0")
A("    batch.append((round(oos_acc,4), n, round(degrade,4), overfit, pid))")
A("    if len(batch) >= 50000:")
A("        conn.executemany(SQL_INS, batch)")
A("        conn.commit()")
A("        batch = []")
A("if batch:")
A("    conn.executemany(SQL_INS, batch)")
A("    conn.commit()")
A("")
A("# --- Step 4: Bulk UPDATE ---")
A("print('\\n[3] Bulk UPDATE...')")
A("sql_upd = ('UPDATE seasonality_patterns_v3 SET'")
A("           ' oos_accuracy=(SELECT oos_accuracy FROM _oos_temp t WHERE t.id=seasonality_patterns_v3.id),'")
A("           ' oos_n_obs=(SELECT oos_n_obs FROM _oos_temp t WHERE t.id=seasonality_patterns_v3.id),'")
A("           ' oos_degradation=(SELECT oos_degradation FROM _oos_temp t WHERE t.id=seasonality_patterns_v3.id),'")
A("           ' overfit=(SELECT overfit FROM _oos_temp t WHERE t.id=seasonality_patterns_v3.id)'")
A("           ' WHERE id IN (SELECT id FROM _oos_temp)')")
A("conn.execute(sql_upd)")
A("conn.commit()")
A("")
A("# --- Step 5: Stats ---")
A("print('\\n[4] Results...')")
A("sql_stat = ('SELECT COUNT(*) AS total,'")
A("            ' COALESCE(SUM(CASE WHEN oos_accuracy IS NOT NULL THEN 1 END),0) AS with_oos,'")
A("            ' COALESCE(SUM(CASE WHEN overfit=1 THEN 1 END),0) AS overfit_count,'")
A("            ' COALESCE(ROUND(AVG(CASE WHEN oos_accuracy IS NOT NULL THEN oos_accuracy END)*100,1),0) AS avg_oos,'")
A("            ' COALESCE(ROUND(AVG(CASE WHEN oos_degradation IS NOT NULL THEN oos_degradation END)*100,1),0) AS avg_deg'")
A("            ' FROM seasonality_patterns_v3')")
A("s = conn.execute(sql_stat).fetchone()")
A("print(f'  Total    : {s[0]:,}')")
A("print(f'  With OOS : {s[1]:,}')")
A("print(f'  Overfit  : {s[2]:,}')")
A("print(f'  Avg OOS  : {s[3]}%')")
A("print(f'  Avg deg  : {s[4]}pp')")
A("print(f'\\nDone in {(datetime.now()-t0).total_seconds()/60:.1f} min')")
A("conn.close()")

write(MICC / "validate_patterns_oos.py", "\n".join(L), "validate_patterns_oos.py")
syntax_check(MICC / "validate_patterns_oos.py")

# =============================================================================
# [3]  .gitignore
# =============================================================================
print("\n[3/5] Writing .gitignore ...")
gi = "\n".join([
    "# Python",
    "__pycache__/",
    "*.py[cod]",
    ".env",
    "",
    "# Node",
    "node_modules/",
    ".next/",
    "out/",
    "",
    "# Database (too large for git)",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.sqlite",
    "",
    "# Parquet",
    "*.parquet",
    "",
    "# Large outputs / checkpoints",
    "seasonality_stocks_checkpoint.json",
    "seasonality_v3_checkpoint.json",
    "pipeline_state.json",
    "adjusted.json",
    "agents/",
    "",
    "# OS",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "*.log",
])
write(MICC / ".gitignore", gi, ".gitignore")

# =============================================================================
# [4]  README.md
# =============================================================================
print("\n[4/5] Writing README.md ...")
rm = "\n".join([
    "# MICC - Market Intelligence Command Center",
    "",
    "Personal algorithmic market intelligence system for NSE/BSE.",
    "",
    "## Stack",
    "- Python 3.14, SQLite 55.8GB WAL database",
    "- Next.js 14 + TypeScript dashboard (localhost:3000)",
    "- Telegram bot for morning brief and alerts",
    "- Ollama gemma3:4b local + Groq llama-3.3-70b",
    "",
    "## Agents",
    "Alpha (Macro) / Beta (Momentum) / Gamma (Options) / Delta (Sectors)",
    "Epsilon (FII/DII) / Zeta (Watchlist) / Eta (Insider) / Iota (Global) / Fusion (Cross-agent)",
    "",
    "## Dashboard Pages",
    "/overview /conviction /fusion /patterns /watchlist /eta /portfolio",
    "/alerts /deep /streaks /indices /options /macro /mf /global /backtest /settings",
    "",
    "## Daily Pipeline",
    "```",
    "cd D:\\MICC\\data_pipeline",
    "py run_pipeline.py --with-engine",
    "```",
    "",
    "## Setup",
    "```",
    "py -m pip install -r requirements.txt --break-system-packages",
    "cd micc-dashboard",
    "npm install",
    "npm run dev",
    "```",
])
write(MICC / "README.md", rm, "README.md")

# =============================================================================
# [5]  Git setup + push
# =============================================================================
print("\n[5/5] Git setup...")

GITHUB_USER = "markandeyavarma3-lab"
REPO_NAME   = "micc"
REMOTE      = f"https://github.com/{GITHUB_USER}/{REPO_NAME}.git"

r = run("git --version")
if r.returncode != 0:
    print("  [ERR] git not installed: https://git-scm.com/download/win")
    sys.exit(1)

if not (MICC / ".git").exists():
    run("git init", cwd=MICC)
    run("git branch -M main", cwd=MICC)
    print("  Repo initialised")
else:
    print("  Repo already exists")

run('git config user.name "markandeyavarma3-lab"', cwd=MICC)
run('git config user.email "markandeyavarma3@users.noreply.github.com"', cwd=MICC)

run("git add -A", cwd=MICC)
r = run('git commit -m "MICC Phase 1: conviction + fusion + OOS validation + git setup"', cwd=MICC)

run("git remote remove origin", cwd=MICC)
run(f"git remote add origin {REMOTE}", cwd=MICC)
print(f"  Remote: {REMOTE}")

# Try gh CLI
r_gh = run("gh --version")
if r_gh.returncode == 0:
    print("  gh CLI found -- creating repo and pushing...")
    r = run(f"gh repo create {GITHUB_USER}/{REPO_NAME} --public --description \"MICC - Market Intelligence Command Center\" --source . --remote origin --push", cwd=MICC)
    if r.returncode != 0:
        run("git push -u origin main", cwd=MICC)
    print(f"\n  LIVE: https://github.com/{GITHUB_USER}/{REPO_NAME}")
else:
    print(f"""
  gh CLI not found.  Do this ONCE manually:

  Step 1 - Install gh CLI (optional, makes it automatic next time):
    winget install --id GitHub.cli

  Step 2 - Create repo on GitHub:
    Open https://github.com/new
    Owner : markandeyavarma3-lab
    Name  : micc
    Public, no README, no .gitignore
    Click "Create repository"

  Step 3 - Push:
    cd D:\\MICC
    git push -u origin main

  After that, every future push is just:
    cd D:\\MICC
    git add -A
    git commit -m "message"
    git push
""")

print("""
======================================================================
  ALL DONE
======================================================================

  ORDER TO RUN NOW:
    1.  py D:\\MICC\\agent_fusion.py
        (check output: "Fusion picks (2+ layers): X")
    2.  cd D:\\MICC\\micc-dashboard
        npm run dev
    3.  Open http://localhost:3000/fusion

  OOS VALIDATION (run overnight, safe to close terminal after):
    py D:\\MICC\\validate_patterns_oos.py --test   <- quick test first
    py D:\\MICC\\validate_patterns_oos.py           <- full 30min run

  GIT AFTER ANY CHANGE:
    cd D:\\MICC
    git add -A
    git commit -m "what changed"
    git push
""")
