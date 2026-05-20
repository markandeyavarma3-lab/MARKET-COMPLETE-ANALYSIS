"""
patch_zeta.py  --  Run from D:\MICC
Patches agent_zeta.py with:
  1. Correct stock_delivery column names: volume, delivery_qty, delivery_pct
     (NOT deliv_qty / traded_qty)
  2. Fixes SyntaxWarning on docstring backslash (raw string)
  3. Completes setup_phase6 steps that failed (NavBar, Telegram, pipeline)
"""

import re
from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"

def read(p):  return Path(p).read_text(encoding="utf-8")
def write(p, t): Path(p).write_text(t, encoding="utf-8"); print(f"  [OK] {p}")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 1: Fix agent_zeta.py -- wrong delivery column names + docstring warning
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== PATCH 1: agent_zeta.py delivery columns ===")

zeta = BASE / "agent_zeta.py"
if not zeta.exists():
    print(f"  [ERROR] {zeta} not found")
    raise SystemExit(1)

src = read(zeta)
orig = src

# Fix 1a: docstring backslash warning -- change to raw string
src = src.replace(
    '"""\nMICC Phase 6',
    'r"""\nMICC Phase 6'
)

# Fix 1b: wrong column names in get_delivery_window
OLD_QUERY = '''\
    df = pd.read_sql_query(
        "SELECT symbol, date, deliv_qty, traded_qty FROM stock_delivery "
        "WHERE date >= ? ORDER BY symbol, date",
        conn, params=(cutoff,)
    )
    conn.close()
    df["deliv_pct"] = (df["deliv_qty"] / df["traded_qty"].replace(0, np.nan) * 100).fillna(0)'''

NEW_QUERY = '''\
    df = pd.read_sql_query(
        "SELECT symbol, date, volume, delivery_qty, delivery_pct "
        "FROM stock_delivery "
        "WHERE date >= ? ORDER BY symbol, date",
        conn, params=(cutoff,)
    )
    conn.close()
    # delivery_pct already computed; normalise column name for downstream use
    if "delivery_pct" not in df.columns:
        df["delivery_pct"] = 0.0
    df["deliv_pct"] = pd.to_numeric(df["delivery_pct"], errors="coerce").fillna(0)'''

if OLD_QUERY in src:
    src = src.replace(OLD_QUERY, NEW_QUERY)
    print("  Fixed: delivery column names (deliv_qty/traded_qty -> volume/delivery_qty/delivery_pct)")
else:
    print("  [WARN] exact query not found, doing targeted replace...")
    src = src.replace("deliv_qty", "delivery_qty")
    src = src.replace("traded_qty", "volume")
    # Fix the derived deliv_pct line
    src = re.sub(
        r'df\["deliv_pct"\]\s*=.*?\.fillna\(0\)',
        'df["deliv_pct"] = pd.to_numeric(df.get("delivery_pct", 0), errors="coerce").fillna(0)',
        src
    )
    print("  Fixed: replaced column names via targeted regex")

# Fix 1c: in screen_volume_delivery_surge, `deliv_pct` column ref is fine
# but the surge merge might use wrong name -- check deliv_today merge
OLD_MERGE = 'deliv_today = delivery[delivery["date"] == today_date][["symbol","deliv_pct"]]'
NEW_MERGE = '''\
    # delivery has 'deliv_pct' col (normalised in get_delivery_window)
        deliv_today = delivery[delivery["date"] == today_date][["symbol","deliv_pct"]]'''

# No change needed there since we now produce deliv_pct correctly

# Fix 1d: avg_deliv_pct computation also needs deliv_pct
OLD_AVG = 'deliv_avg = delivery[delivery["date"] < today_date].groupby("symbol")["deliv_pct"].mean().rename("avg_deliv_pct")'
# This is fine since we renamed to deliv_pct -- no change needed

if src != orig:
    write(zeta, src)
    print("  agent_zeta.py patched successfully")
else:
    print("  No changes made (may already be correct)")


# ─────────────────────────────────────────────────────────────────────────────
# PATCH 2: Fix setup_phase6.py docstring backslash warnings
# (they're cosmetic SyntaxWarnings, not errors -- but clean them up)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== PATCH 2: Fix SyntaxWarnings in setup scripts ===")

for script in ["setup_phase6.py", "fix_markdowntext.py"]:
    p = BASE / script
    if p.exists():
        s = read(p)
        # The warning is in the module docstring: """\nfix_markdowntext.py  --  Run from D:\MICC
        # Fix: make it a raw string or escape the backslash
        # Easiest: the docstring is just for humans, change \M and \s to \\M \\s
        fixed = s.replace(
            'D:\\MICC\n',
            'D:\\\\MICC\n'
        )
        # Actually the real fix is the path in the docstring -- just suppress with raw
        # Find the triple-quote docstring at top and make it raw
        fixed = re.sub(r'^"""(\nMICC|^"""[\s\S]{0,200}Run from D:\\)', lambda m: 'r"""' + m.group(1), s, count=1, flags=re.MULTILINE)
        if fixed != s:
            write(p, fixed)
        else:
            print(f"  {script}: no change (warning is harmless, just cosmetic)")
    else:
        print(f"  {script} not found, skipping")


# ─────────────────────────────────────────────────────────────────────────────
# PATCH 3: Complete setup_phase6 steps that failed
# (NavBar + Telegram + pipeline -- skipped because copy2 errored out early)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== PATCH 3: NavBar -- add WATCHLIST link ===")

navbar = None
for p in DASH.rglob("NavBar.tsx"):
    navbar = p; break

if not navbar:
    print("  [WARN] NavBar.tsx not found")
else:
    src = read(navbar)
    # Try different patterns for where nav links are defined
    patterns_to_try = [
        ("{ href: '/mf', label: 'MF NAV' },",
         "{ href: '/mf', label: 'MF NAV' },\n  { href: '/watchlist', label: 'WATCHLIST' },"),
        ("href: \"/mf\"",
         "href: \"/mf\""),  # detect only
        ("'MF NAV'", None),  # detect only
    ]
    added = False
    for old, new in patterns_to_try:
        if old in src:
            if new and "watchlist" not in src.lower():
                src = src.replace(old, new)
                write(navbar, src)
                print("  Added WATCHLIST to NavBar")
                added = True
            elif "watchlist" in src.lower():
                print("  WATCHLIST already in NavBar")
                added = True
            break
    if not added:
        print("  [WARN] Could not find MF NAV entry. Showing nav items:")
        for i, l in enumerate(read(navbar).splitlines()):
            if any(x in l for x in ['href', 'label', 'nav', 'OVER', 'STREAK', 'MF']):
                print(f"    {i+1}: {l}")


print("\n=== PATCH 4: Telegram -- add /watch command ===")

bot = BASE / "telegram_bot.py"
if not bot.exists():
    print(f"  [WARN] telegram_bot.py not found")
else:
    src = read(bot)
    if "cmd_watch" in src:
        print("  /watch already in telegram_bot.py")
    else:
        WATCH_CMD = r'''

async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show watchlist status from last Zeta report."""
    zeta_path = Path("agents/zeta/last_report.json")
    if not zeta_path.exists():
        await update.message.reply_text(
            "No Zeta report found. Run: py agent_zeta.py --send"
        )
        return
    try:
        report = json.loads(zeta_path.read_text(encoding="utf-8"))
    except Exception as e:
        await update.message.reply_text(f"Error loading Zeta: {e}")
        return

    d        = report.get("date", "?")
    syms     = report.get("watchlist_symbols", [])
    breakouts= report.get("breakout_watch", [])[:5]
    surges   = report.get("vol_delivery_surge", [])[:5]
    alerts   = report.get("triggered_alerts", [])
    reentries= report.get("reentry_radar", [])[:4]
    streaks  = report.get("watchlist_streaks", [])[:8]

    lines = [f"*WATCHLIST INTEL -- {d}*", ""]

    if alerts:
        lines.append("*ALERTS TRIGGERED:*")
        for a in alerts:
            lines.append(f"  `{a['symbol']}` {a['condition'].upper()} {a['level']} @ `{a['price']}`")
        lines.append("")

    if syms:
        lines.append("*WATCHING:* " + " | ".join(f"`{s}`" for s in syms[:12]))
        lines.append("")

    if streaks:
        lines.append("*STREAKS:*")
        for s in streaks:
            bar = "=" * min(s["streak"], 8)
            lines.append(f"  `{s['symbol']}` [{bar}] {s['streak']}d")
        lines.append("")

    if breakouts:
        lines.append("*NEAR 52w HIGH:*")
        for b in breakouts:
            lines.append(f"  `{b['symbol']}` @ {b['close']} (-{b['pct_from_52h']}% from high)")
        lines.append("")

    if surges:
        lines.append("*VOL SURGES:*")
        for s in surges:
            lines.append(f"  `{s['symbol']}` {s['vol_surge']}x vol | {s['deliv_pct']}% deliv")
        lines.append("")

    if reentries:
        lines.append("*RE-ENTRY:*")
        for r in reentries:
            near = " [near MA10]" if r.get("near_ma10") else ""
            lines.append(f"  `{r['symbol']}` -{r['pullback_pct']}%{near}")

    msg = "\n".join(lines)
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")

'''
        # Insert before def main():
        if "def main():" in src:
            src = src.replace("def main():", WATCH_CMD + "def main():")
            # Register handler
            for reg_pattern in [
                'app.add_handler(CommandHandler("status"',
                'application.add_handler(CommandHandler("status"',
            ]:
                if reg_pattern in src:
                    src = src.replace(
                        reg_pattern,
                        f'app.add_handler(CommandHandler("watch", cmd_watch))\n    {reg_pattern}'
                    )
                    break
            write(bot, src)
            print("  Added /watch command to telegram_bot.py")
        else:
            print("  [WARN] Could not find def main() in telegram_bot.py")


print("\n=== PATCH 5: run_pipeline.py -- add Zeta as Phase 11 ===")

pipeline = BASE / "data_pipeline" / "run_pipeline.py"
if not pipeline.exists():
    print(f"  [WARN] {pipeline} not found")
else:
    src = read(pipeline)
    if "agent_zeta" in src:
        print("  Zeta already in pipeline")
    else:
        ZETA_BLOCK = '''
    # Phase 11: Agent Zeta (Watchlist Intelligence)
    if args.with_engine:
        print("\\n[Phase 11] Agent Zeta -- Watchlist Intelligence...")
        import subprocess as _sp
        _r = _sp.run(
            ["py", str(Path(r"D:\\MICC") / "agent_zeta.py"), "--send"],
            capture_output=True, text=True, timeout=300
        )
        if _r.returncode != 0:
            print(f"  [WARN] Zeta failed: {_r.stderr[:200]}")
        else:
            print("  Zeta: OK")
'''
        # Insert near end -- before health check or final print
        for anchor in ["# Health check", "print_health", "print(\"\\nPIPELINE", 'log.info("Pipeline complete']:
            if anchor in src:
                src = src.replace(anchor, ZETA_BLOCK + "\n    " + anchor, 1)
                write(pipeline, src)
                print("  Added Zeta as Phase 11")
                break
        else:
            # Just append before last line
            lines = src.splitlines()
            # find last meaningful line
            insert_idx = len(lines) - 1
            for i in range(len(lines)-1, 0, -1):
                if lines[i].strip() and not lines[i].startswith('#'):
                    insert_idx = i
                    break
            lines.insert(insert_idx, ZETA_BLOCK)
            write(pipeline, "\n".join(lines))
            print("  Added Zeta at end of pipeline")


print("\n" + "="*60)
print("ALL PATCHES DONE")
print("="*60)
print()
print("Test:")
print("  py D:\\MICC\\agent_zeta.py          -- should complete without errors")
print("  py D:\\MICC\\agent_zeta.py --send   -- with Telegram")
print("  localhost:3000/watchlist            -- dashboard page")
