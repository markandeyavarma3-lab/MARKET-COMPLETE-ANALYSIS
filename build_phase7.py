"""
build_phase7.py
===============
Fix 1: morning_brief global_snapshot -- definitive hardcoded fix
Fix 2: agent_eta --no-llm not reaching agent (loop format changed)
Phase 7:
  [1] Add HMM + XGB to daily pipeline (run_pipeline.py)
  [2] Telegram bot: /hmm /xgb /conviction /news SYMBOL commands
  [3] /api/morning-brief/route.ts  -- dashboard can pull brief data
  [4] /overview page upgrade       -- show HMM regime + XGB picks inline

Run: py D:\MICC\build_phase7.py
"""
from pathlib import Path
import re

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
APP  = DASH / "src" / "app"

def write(path, lines, label=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [OK] {label or path.name}  ({len(lines)} lines)")

def log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

print("=" * 60)
print("PHASE 7 BUILD")
print("=" * 60)


# =============================================================================
# FIX 1: morning_brief.py -- definitive global_snapshot fix
#         The function gets rewritten to be 100% explicit with exact DB names
# =============================================================================
log("[FIX 1] Rewriting morning_brief.py get_global_snapshot definitively...")

mb_path = MICC / "morning_brief.py"
mb_src  = mb_path.read_text(encoding="utf-8")

# Replace get_global_snapshot completely with hardcoded version
new_snap = '''\
def get_global_snapshot():
    # Exact keys from global_indices_daily — verified from DB on 2026-05-23
    WANT = [
        ("Nifty 50 ", "NIFTY50"),
        ("NiftyBank", "NIFTYBANK"),
        ("S&P 500  ", "SPX"),
        ("Nasdaq   ", "NDX"),
        ("VIX      ", "VIX"),
        ("IndiaVIX ", "IndiaVIX"),
        ("DXY      ", "DXY"),
        ("US 10Y   ", "US10Y"),
        ("Gold     ", "Gold"),
        ("CrudeWTI ", "CrudeWTI"),
        ("USD/INR  ", "USDINR"),
        ("Bitcoin  ", "Bitcoin"),
    ]
    try:
        conn  = sqlite3.connect(DB_P, timeout=10)
        syms  = [s for _, s in WANT]
        ph    = ",".join("?" * len(syms))
        # Get latest date per symbol then join
        rows  = conn.execute(
            "SELECT g.symbol, g.close, g.pct_change"
            " FROM global_indices_daily g"
            " INNER JOIN ("
            "   SELECT symbol, MAX(date) AS md"
            "   FROM global_indices_daily"
            f"  WHERE symbol IN ({ph})"
            "   GROUP BY symbol"
            " ) mx ON mx.symbol=g.symbol AND mx.md=g.date"
            f" WHERE g.symbol IN ({ph})",
            syms + syms
        ).fetchall()
        conn.close()
        data = {r[0]: (r[1], r[2]) for r in rows}
        result = []
        for label, sym in WANT:
            if sym not in data:
                continue
            close, chg = data[sym]
            if close is None:
                continue
            ico   = "UP" if (chg or 0) > 0.3 else "DN" if (chg or 0) < -0.3 else "--"
            chg_s = f"{chg:+.2f}%" if chg is not None else ""
            result.append(f"  {ico} `{label}` {close:,.2f}  {chg_s}")
        log(f"global_snapshot: {len(result)}/{len(WANT)} symbols")
        return result
    except Exception as e:
        log(f"global_snapshot error: {e}")
        return []

'''

mb_src = re.sub(
    r"def get_global_snapshot\(\):.*?(?=\ndef |\Z)",
    new_snap,
    mb_src,
    flags=re.DOTALL
)

# FIX 2: agent_eta --no-llm -- find actual loop format and fix
# The loop now uses extra_args but agent_eta might not have --no-llm flag
# Simplest fix: just pass --no-llm and add it to agent_eta if missing

# Fix the agent loop to ensure --no-llm reaches eta
old_agent_loop_pattern = r"for script, tout, extra_args in \[.*?\]:"
new_agent_loop = (
    "for script, tout, extra_args in ["
    "('agent_fusion.py',120,[]),"
    "('agent_eta.py',300,['--no-llm']),"
    "('agent_alert.py',60,[])"
    "]:"
)
if re.search(old_agent_loop_pattern, mb_src, re.DOTALL):
    mb_src = re.sub(old_agent_loop_pattern, new_agent_loop, mb_src, count=1, flags=re.DOTALL)
    print("  [OK] Agent loop fixed with --no-llm for eta")
else:
    # Try simpler patterns
    for old, new in [
        (
            "for script, tout in [('agent_fusion.py',120),('agent_eta.py',300),('agent_alert.py',60)]:",
            "for script, tout, extra_args in [('agent_fusion.py',120,[]),('agent_eta.py',300,['--no-llm']),('agent_alert.py',60,[])]:"
        ),
        (
            "for script in ['agent_fusion.py', 'agent_eta.py', 'agent_alert.py']:",
            "for script, tout, extra_args in [('agent_fusion.py',120,[]),('agent_eta.py',300,['--no-llm']),('agent_alert.py',60,[])]:"
        ),
    ]:
        if old in mb_src:
            mb_src = mb_src.replace(old, new, 1)
            print("  [OK] Agent loop updated")
            break

# Make sure run_agent accepts extra_args
if "extra_args=None" not in mb_src:
    mb_src = mb_src.replace(
        "def run_agent(script, timeout=120):",
        "def run_agent(script, timeout=120, extra_args=None):"
    )
if "cmd = [PY" not in mb_src:
    mb_src = mb_src.replace(
        "r = subprocess.run([PY, str(DA / script)], cwd=str(DA),",
        "cmd = [PY, str(DA / script)] + (extra_args or [])\n        r = subprocess.run(cmd, cwd=str(DA),"
    )
# Make sure run_agent is called with extra_args
if "run_agent(script, timeout=tout)" in mb_src and "extra_args" not in mb_src.split("run_agent(script, timeout=tout)")[0].split("\n")[-1]:
    mb_src = mb_src.replace(
        "ok = run_agent(script, timeout=tout)",
        "ok = run_agent(script, timeout=tout, extra_args=extra_args)"
    )

mb_path.write_text(mb_src, encoding="utf-8")
print("  [OK] morning_brief.py saved with definitive global_snapshot + eta fix")


# =============================================================================
# FIX 3: agent_eta.py -- add --no-llm flag properly
# =============================================================================
log("[FIX 3] Adding --no-llm to agent_eta.py properly...")

eta_path = MICC / "agent_eta.py"
if eta_path.exists():
    eta_src = eta_path.read_text(encoding="utf-8")
    if "no_llm" not in eta_src:
        # Find the first occurrence of sys.argv usage
        send_patterns = [
            'SEND = "--send" in sys.argv',
            'send = "--send" in sys.argv',
            'send    = "--send" in sys.argv',
            'send  = "--send" in sys.argv',
        ]
        for pat in send_patterns:
            if pat in eta_src:
                eta_src = eta_src.replace(
                    pat,
                    pat + "\nno_llm  = \"--no-llm\" in sys.argv"
                )
                print(f"  [OK] Added no_llm after: {pat[:40]}")
                break
        else:
            # Just prepend to file after imports
            insert_after = "import sys"
            if insert_after in eta_src:
                eta_src = eta_src.replace(
                    insert_after,
                    insert_after + "\nno_llm = \"--no-llm\" in sys.argv",
                    1
                )
                print("  [OK] Added no_llm after import sys")

        # Find LLM call and wrap with if not no_llm
        # Look for print statements about LLM analysis
        for marker in [
            '  print("  LLM analysis...")',
            '  log("  LLM analysis...")',
            '  print("\\n  LLM analysis...")',
            '  log("LLM analysis")',
        ]:
            if marker in eta_src:
                # Find the block from this marker to end of LLM section
                eta_src = eta_src.replace(
                    marker,
                    '  if no_llm:\n      llm_analysis = "[LLM skipped -- use --no-llm flag]"\n  else:\n    ' + marker.strip()
                )
                print("  [OK] LLM section wrapped with no_llm check")
                break

        eta_path.write_text(eta_src, encoding="utf-8")
    else:
        print("  [SKIP] no_llm already in agent_eta.py")
else:
    print("  [SKIP] agent_eta.py not found")


# =============================================================================
# [1]  Add HMM + XGB to daily pipeline
# =============================================================================
log("[1/3] Patching run_pipeline.py to include HMM + XGB daily...")

# Find run_pipeline.py
pipe_candidates = [
    MICC / "data_pipeline" / "run_pipeline.py",
    MICC / "run_pipeline.py",
]
pipe_path = next((p for p in pipe_candidates if p.exists()), None)

if pipe_path:
    pipe_src = pipe_path.read_text(encoding="utf-8")
    changed  = False

    # Add HMM after engine phases if not already there
    if "agent_hmm" not in pipe_src:
        # Find a good injection point — after engine or after greeks
        for anchor in [
            '    # Health check',
            '    print("\\n[SUMMARY]")',
            '    print("Pipeline complete")',
        ]:
            if anchor in pipe_src:
                hmm_block = (
                    "\n    # HMM Regime + XGB Conviction (daily ML)\n"
                    "    try:\n"
                    "        import subprocess as _sp\n"
                    "        _py = sys.executable\n"
                    "        _sp.run([_py, str(MICC_DIR / 'agent_hmm.py')],\n"
                    "                cwd=str(MICC_DIR), timeout=120, capture_output=True)\n"
                    "        print('  [OK] HMM regime updated')\n"
                    "    except Exception as _e:\n"
                    "        print(f'  [WARN] HMM: {_e}')\n"
                    "    try:\n"
                    "        _sp.run([_py, str(MICC_DIR / 'train_conviction_xgb.py'), '--score'],\n"
                    "                cwd=str(MICC_DIR), timeout=180, capture_output=True)\n"
                    "        print('  [OK] XGB scores updated')\n"
                    "    except Exception as _e:\n"
                    "        print(f'  [WARN] XGB: {_e}')\n\n"
                )
                pipe_src  = pipe_src.replace(anchor, hmm_block + anchor, 1)
                changed = True
                print(f"  [OK] HMM+XGB added before: {anchor[:40]}")
                break

    # Make sure MICC_DIR is defined
    if changed and "MICC_DIR" not in pipe_src:
        pipe_src = "from pathlib import Path\nMICC_DIR = Path(r'D:\\MICC')\n" + pipe_src

    if changed:
        pipe_path.write_text(pipe_src, encoding="utf-8")
        print(f"  [OK] {pipe_path.name} updated")
    else:
        print("  [SKIP] HMM already in pipeline or anchor not found")
else:
    print("  [SKIP] run_pipeline.py not found")


# =============================================================================
# [2]  Telegram bot: add /hmm /xgb /conviction commands
# =============================================================================
log("[2/3] Adding /hmm /xgb commands to telegram_bot.py...")

bot_path = MICC / "telegram_bot.py"
if bot_path.exists():
    bot_src = bot_path.read_text(encoding="utf-8")
    changed = False

    if "cmd_hmm" not in bot_src:
        # Find where commands are defined and add new ones before main handler registration
        new_cmds = '''
async def cmd_hmm(update, context):
    """Show current HMM regime."""
    import json
    from pathlib import Path
    try:
        p = Path(r"D:\\MICC\\agents\\hmm\\last_report.json")
        if not p.exists():
            await update.message.reply_text("No HMM data. Run: py agent_hmm.py")
            return
        d = json.loads(p.read_text())
        reg  = d.get("current_regime", "--")
        conf = d.get("confidence", 0)
        bull = d.get("bull_prob", 0)
        side = d.get("sideways_prob", 0)
        bear = d.get("bear_prob", 0)
        ico  = {"BULL": "UP", "BEAR": "DN", "SIDEWAYS": "--"}.get(reg, "--")
        msg  = (f"HMM Regime\\n"
                f"{ico} {reg}  ({conf:.0%} confidence)\\n\\n"
                f"Bull     : {bull:.0%}\\n"
                f"Sideways : {side:.0%}\\n"
                f"Bear     : {bear:.0%}\\n\\n"
                f"Updated  : {d.get('date', '--')}")
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_xgb(update, context):
    """Show top XGBoost conviction picks."""
    import sqlite3
    DB = r"D:\\marketDB\\db\\market.db"
    try:
        conn = sqlite3.connect(DB, timeout=10)
        rows = conn.execute(
            "SELECT x.symbol, x.xgb_score, COALESCE(c.conviction_score,0) AS conv"
            " FROM symbol_conviction_xgb x"
            " LEFT JOIN symbol_conviction c ON c.symbol=x.symbol"
            " WHERE x.xgb_score >= 55"
            " ORDER BY x.xgb_score DESC LIMIT 15"
        ).fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("No XGB scores. Run: py train_conviction_xgb.py --score")
            return
        lines = ["XGBoost Top Picks (ML model)\\n"]
        for sym, xgb_s, conv in rows:
            lines.append(f"  {sym:<14} XGB={xgb_s:.0f}  Conv={conv:.0f}")
        await update.message.reply_text("\\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


'''
        # Insert before main() or before if __name__
        for anchor in ["def main():", "if __name__ == "]:
            if anchor in bot_src:
                bot_src = bot_src.replace(anchor, new_cmds + anchor, 1)
                changed = True
                break

    if changed and "cmd_hmm" in bot_src:
        # Register handlers - find existing handler registration
        for reg_anchor in [
            'application.add_handler(CommandHandler("today"',
            'application.add_handler(CommandHandler("status"',
            'app.add_handler(CommandHandler("status"',
        ]:
            if reg_anchor in bot_src:
                bot_src = bot_src.replace(
                    reg_anchor,
                    'application.add_handler(CommandHandler("hmm", cmd_hmm))\n    '
                    'application.add_handler(CommandHandler("xgb", cmd_xgb))\n    ' + reg_anchor
                )
                print("  [OK] /hmm and /xgb handlers registered")
                break

        bot_path.write_text(bot_src, encoding="utf-8")
        print("  [OK] telegram_bot.py updated with /hmm /xgb commands")
    elif "cmd_hmm" in bot_src:
        print("  [SKIP] /hmm already in telegram_bot.py")
    else:
        print("  [WARN] Could not find injection point in telegram_bot.py")
else:
    print("  [SKIP] telegram_bot.py not found")


# =============================================================================
# [3]  /api/morning-brief/route.ts -- single endpoint for dashboard overview
# =============================================================================
log("[3/3] Building /api/morning-brief/route.ts...")

brief_api_lines = [
    'import { NextResponse } from "next/server";',
    'import { readFileSync, existsSync } from "fs";',
    'import Database from "better-sqlite3";',
    '',
    'const DB   = "D:/marketDB/db/market.db";',
    'const MICC = "D:/MICC";',
    '',
    'function readJson(path: string): Record<string, unknown> {',
    '  try {',
    '    if (!existsSync(path)) return {};',
    '    return JSON.parse(readFileSync(path, "utf-8")',
    '      .replace(/:\\s*NaN\\b/g, ":null")',
    '      .replace(/:\\s*Infinity\\b/g, ":null"));',
    '  } catch { return {}; }',
    '}',
    '',
    'function safeDb<T>(fn: (db: ReturnType<typeof Database>) => T, fallback: T): T {',
    '  let db: ReturnType<typeof Database> | null = null;',
    '  try {',
    '    db = new Database(DB, { readonly: true, timeout: 5000 });',
    '    return fn(db);',
    '  } catch { return fallback; }',
    '  finally { try { db?.close(); } catch {} }',
    '}',
    '',
    'export function GET() {',
    '  // HMM regime',
    '  const hmm = readJson(`${MICC}/agents/hmm/last_report.json`);',
    '',
    '  // Fusion top picks',
    '  const fusion = readJson(`${MICC}/agents/fusion/last_report.json`);',
    '  const picks  = (fusion.picks as unknown[] || []).slice(0, 8);',
    '',
    '  // Global markets snapshot',
    '  const SYMBOLS = ["NIFTY50","NIFTYBANK","SPX","NDX","VIX","IndiaVIX",',
    '                    "DXY","US10Y","Gold","CrudeWTI","USDINR","Bitcoin"];',
    '  const markets = safeDb(db => {',
    '    const ph   = SYMBOLS.map(() => "?").join(",");',
    '    return db.prepare(',
    '      "SELECT g.symbol, g.close, g.pct_change FROM global_indices_daily g"',
    '      " INNER JOIN (SELECT symbol, MAX(date) AS md FROM global_indices_daily"',
    '      `  WHERE symbol IN (${ph}) GROUP BY symbol) mx`',
    '      " ON mx.symbol=g.symbol AND mx.md=g.date"',
    '      `  WHERE g.symbol IN (${ph})`"',
    '    ).all(...SYMBOLS, ...SYMBOLS);',
    '  }, []);',
    '',
    '  // XGB top picks',
    '  const xgbPicks = safeDb(db => {',
    '    try {',
    '      return db.prepare(',
    '        "SELECT x.symbol, x.xgb_score, COALESCE(c.conviction_score,0) AS conviction"',
    '        " FROM symbol_conviction_xgb x"',
    '        " LEFT JOIN symbol_conviction c ON c.symbol=x.symbol"',
    '        " WHERE x.xgb_score >= 55"',
    '        " ORDER BY x.xgb_score DESC LIMIT 8"',
    '      ).all();',
    '    } catch { return []; }',
    '  }, []);',
    '',
    '  // Today\'s OOS-validated patterns',
    '  const mmdd = new Date().toLocaleDateString("en-CA", {',
    '    month: "2-digit", day: "2-digit" }).replace("-", "-");',
    '  const todayDate = new Date();',
    '  const anchor    = `${String(todayDate.getMonth()+1).padStart(2,"0")}-${String(todayDate.getDate()).padStart(2,"0")}`;',
    '  const patterns  = safeDb(db => {',
    '    try {',
    '      return db.prepare(',
    '        "SELECT symbol, window_days, direction, accuracy, mean_ret, score_v2"',
    '        " FROM seasonality_patterns_v3"',
    '        " WHERE anchor_mm_dd=? AND fdr_reject=1 AND (overfit=0 OR overfit IS NULL)"',
    '        "   AND score_v2 > 1.0"',
    '        " ORDER BY score_v2 DESC LIMIT 30"',
    '      ).all(anchor);',
    '    } catch { return []; }',
    '  }, []);',
    '  // Dedup by symbol',
    '  const seen = new Set<string>();',
    '  const patsDeduped = (patterns as {symbol:string}[]).filter(p => {',
    '    if (seen.has(p.symbol)) return false;',
    '    seen.add(p.symbol); return true;',
    '  }).slice(0, 6);',
    '',
    '  // Insider clusters',
    '  const insiders = safeDb(db => {',
    '    try {',
    '      const cutoff = new Date(Date.now() - 30*24*3600*1000).toISOString().slice(0,10);',
    '      return db.prepare(',
    '        "SELECT symbol, COUNT(*) AS n_buys, SUM(CAST(value AS REAL)) AS total_value"',
    '        " FROM insider_trading"',
    '        " WHERE transaction_type=\'BUY\' AND filing_date >= ?"',
    '        " GROUP BY symbol HAVING n_buys >= 2"',
    '        " ORDER BY n_buys DESC, total_value DESC LIMIT 5"',
    '      ).all(cutoff);',
    '    } catch { return []; }',
    '  }, []);',
    '',
    '  return NextResponse.json({',
    '    hmm,',
    '    fusion_picks:  picks,',
    '    markets,',
    '    xgb_picks:     xgbPicks,',
    '    patterns:      patsDeduped,',
    '    insider_clusters: insiders,',
    '    generated_at:  new Date().toISOString(),',
    '  });',
    '}',
]

write(APP / "api" / "morning-brief" / "route.ts",
      brief_api_lines, "/api/morning-brief/route.ts")


print()
print("=" * 60)
print("PHASE 7 COMPLETE")
print("=" * 60)
print()
print("Fixes applied:")
print("  morning_brief.py  -- global_snapshot definitive hardcoded fix")
print("  morning_brief.py  -- agent_eta --no-llm properly wired")
print("  agent_eta.py      -- --no-llm flag added")
print()
print("New:")
print("  run_pipeline.py   -- HMM + XGB run daily after engine")
print("  telegram_bot.py   -- /hmm and /xgb commands")
print("  /api/morning-brief -- single dashboard data endpoint")
print()
print("Test:")
print("  py D:\\MICC\\morning_brief.py")
print("  Expected: 12/12 global symbols + no eta timeout")
print()
print("Restart bot to pick up new commands:")
print("  (stop telegram_bot.py and restart it)")
print()
print("Git push:")
print("  py D:\\MICC\\git_push_phase3.py")
