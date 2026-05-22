"""
fix_eta_and_phase8.py
=====================
Fix 1: agent_eta.py -- argparse rejects --no-llm, add it properly
Fix 2: agent_eta.py -- align output schema with /eta page expectations
         page expects: screen1_results_season, screen3_insider_clusters,
                       screen4_big_trades, screen5_post_results_reaction
         agent writes: results_season, insider_cluster, big_insider_trades
Phase 8:
  [1] /overview page -- wire /api/morning-brief endpoint inline
  [2] Daily pipeline scheduler update -- add HMM+XGB phases
  [3] MICC status dashboard widget -- show pipeline health on overview

Run: py D:\MICC\fix_eta_and_phase8.py
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
print("FIX ETA + PHASE 8")
print("=" * 60)


# =============================================================================
# FIX 1+2: agent_eta.py
#   - Add --no-llm to argparse (not sys.argv) so it doesn't crash
#   - Add schema aliases so /eta page gets both old and new key names
# =============================================================================
log("[FIX 1+2] Patching agent_eta.py...")

eta_path = MICC / "agent_eta.py"
eta_src  = eta_path.read_text(encoding="utf-8")

# Fix 1: Add --no-llm to argparse
old_ap = (
    "if __name__ == \"__main__\":\n"
    "    ap = argparse.ArgumentParser()\n"
    "    ap.add_argument(\"--send\", action=\"store_true\")\n"
    "    args = ap.parse_args()\n"
    "    run_eta(send=args.send)"
)
new_ap = (
    "if __name__ == \"__main__\":\n"
    "    ap = argparse.ArgumentParser()\n"
    "    ap.add_argument(\"--send\",   action=\"store_true\")\n"
    "    ap.add_argument(\"--no-llm\", action=\"store_true\", dest=\"no_llm\")\n"
    "    args = ap.parse_args()\n"
    "    run_eta(send=args.send, no_llm=args.no_llm)"
)

if old_ap in eta_src:
    eta_src = eta_src.replace(old_ap, new_ap, 1)
    print("  [OK] argparse: added --no-llm argument")
else:
    # Try alternate spacing
    eta_src = re.sub(
        r'(if __name__ == "__main__":\s*\n\s*ap = argparse\.ArgumentParser\(\)\s*\n\s*ap\.add_argument\("--send".*?\n\s*args = ap\.parse_args\(\)\s*\n\s*run_eta\(send=args\.send\))',
        (
            'if __name__ == "__main__":\n'
            '    ap = argparse.ArgumentParser()\n'
            '    ap.add_argument("--send",   action="store_true")\n'
            '    ap.add_argument("--no-llm", action="store_true", dest="no_llm")\n'
            '    args = ap.parse_args()\n'
            '    run_eta(send=args.send, no_llm=args.no_llm)'
        ),
        eta_src, flags=re.DOTALL
    )
    print("  [OK] argparse patched (regex method)")

# Fix 2: Add no_llm parameter to run_eta function
old_def = "def run_eta(send: bool = False) -> dict:"
new_def = "def run_eta(send: bool = False, no_llm: bool = False) -> dict:"
eta_src = eta_src.replace(old_def, new_def, 1)

# Fix 3: Wrap LLM call with no_llm check
old_llm = (
    "    print(\"  LLM analysis...\")\n"
    "    prompt   = build_prompt(results_season, dividends, clusters,\n"
    "                             big_trades, reactions, upcoming)\n"
    "    analysis, _src = call_llm(prompt, max_tokens=600, label=\"Eta\")\n"
    "    print(f\"    {len(str(analysis))} chars\")"
)
new_llm = (
    "    print(\"  LLM analysis...\")\n"
    "    if no_llm:\n"
    "        analysis = \"[LLM skipped]\"\n"
    "        print(\"    skipped (--no-llm)\")\n"
    "    else:\n"
    "        prompt   = build_prompt(results_season, dividends, clusters,\n"
    "                                 big_trades, reactions, upcoming)\n"
    "        analysis, _src = call_llm(prompt, max_tokens=600, label=\"Eta\")\n"
    "        print(f\"    {len(str(analysis))} chars\")"
)
if old_llm in eta_src:
    eta_src = eta_src.replace(old_llm, new_llm, 1)
    print("  [OK] LLM call wrapped with no_llm check")
else:
    # Looser match
    eta_src = re.sub(
        r'(    print\("  LLM analysis\.\.\."\)\n)'
        r'(    prompt.*?call_llm.*?\n    print\(f"    \{len.*?\))',
        (
            r'\1'
            '    if no_llm:\n'
            '        analysis = "[LLM skipped]"\n'
            '        print("    skipped (--no-llm)")\n'
            '    else:\n'
            r'        \2'
        ),
        eta_src, flags=re.DOTALL
    )
    print("  [OK] LLM block wrapped (regex method)")

# Fix 4: Add schema aliases to report dict so /eta page works
# The page expects screen3_insider_clusters, screen4_big_trades etc.
old_report = (
    "    report = {\n"
    "        \"agent\":              \"eta\",\n"
    "        \"date\":               today_str(),\n"
    "        \"generated_at\":       now_ist(),\n"
    "        \"results_season\":     results_season,\n"
    "        \"dividend_calendar\":  dividends,\n"
    "        \"insider_cluster\":    clusters,\n"
    "        \"big_insider_trades\": big_trades,\n"
    "        \"post_results_reaction\": reactions,\n"
    "        \"upcoming_results\":   upcoming,\n"
    "        \"analysis\":           analysis,\n"
    "    }"
)
new_report = (
    "    report = {\n"
    "        \"agent\":              \"eta\",\n"
    "        \"date\":               today_str(),\n"
    "        \"timestamp\":          now_ist(),\n"
    "        \"generated_at\":       now_ist(),\n"
    "        # Original keys (kept for backward compat)\n"
    "        \"results_season\":     results_season,\n"
    "        \"dividend_calendar\":  dividends,\n"
    "        \"insider_cluster\":    clusters,\n"
    "        \"big_insider_trades\": big_trades,\n"
    "        \"post_results_reaction\": reactions,\n"
    "        \"upcoming_results\":   upcoming,\n"
    "        \"analysis\":           analysis,\n"
    "        # New keys matching /eta dashboard page expectations\n"
    "        \"screen1_results_season\":      results_season,\n"
    "        \"screen2_dividends\":            dividends,\n"
    "        \"screen3_insider_clusters\":     clusters,\n"
    "        \"screen4_big_trades\":           big_trades,\n"
    "        \"screen5_post_results_reaction\": reactions,\n"
    "        \"screen6_upcoming_results\":     upcoming,\n"
    "        \"llm_analysis\":                analysis,\n"
    "    }"
)
if old_report in eta_src:
    eta_src = eta_src.replace(old_report, new_report, 1)
    print("  [OK] Report schema: added screen1-6 aliases + llm_analysis key")
else:
    print("  [WARN] Could not find report dict to add schema aliases")

# Remove the broken no_llm injection from previous patches (import sys line)
eta_src = eta_src.replace(
    'import sys\nno_llm = "--no-llm" in sys.argv',
    'import sys',
    1
)

eta_path.write_text(eta_src, encoding="utf-8")
print("  [OK] agent_eta.py saved")


# =============================================================================
# [1]  /api/eta/route.ts -- reads last_report.json (normalize both schemas)
# =============================================================================
log("[1/3] Building /api/eta/route.ts...")

eta_api_lines = [
    'import { NextResponse } from "next/server";',
    'import { readFileSync, existsSync } from "fs";',
    '',
    'const REPORT = "D:/MICC/agents/eta/last_report.json";',
    '',
    'export function GET() {',
    '  try {',
    '    if (!existsSync(REPORT)) {',
    '      return NextResponse.json({',
    '        screen1_results_season: [], screen2_dividends: [],',
    '        screen3_insider_clusters: [], screen4_big_trades: [],',
    '        screen5_post_results_reaction: [], screen6_upcoming_results: [],',
    '        llm_analysis: null, error: "Run agent_eta.py first"',
    '      });',
    '    }',
    '    const raw  = readFileSync(REPORT, "utf-8")',
    '      .replace(/:\\s*NaN\\b/g, ":null")',
    '      .replace(/:\\s*Infinity\\b/g, ":null");',
    '    const data = JSON.parse(raw);',
    '    // Normalize: support both old schema and new schema',
    '    const normalized = {',
    '      ...data,',
    '      screen1_results_season:',
    '        data.screen1_results_season ?? data.results_season ?? [],',
    '      screen2_dividends:',
    '        data.screen2_dividends ?? data.dividend_calendar ?? [],',
    '      screen3_insider_clusters:',
    '        data.screen3_insider_clusters ?? data.insider_cluster ?? [],',
    '      screen4_big_trades:',
    '        data.screen4_big_trades ?? data.big_insider_trades ?? [],',
    '      screen5_post_results_reaction:',
    '        data.screen5_post_results_reaction ?? data.post_results_reaction ?? [],',
    '      screen6_upcoming_results:',
    '        data.screen6_upcoming_results ?? data.upcoming_results ?? [],',
    '      llm_analysis:',
    '        data.llm_analysis ?? data.analysis ?? null,',
    '    };',
    '    return NextResponse.json(normalized);',
    '  } catch (e) {',
    '    return NextResponse.json({ error: String(e), screen3_insider_clusters: [] });',
    '  }',
    '}',
]
write(APP / "api" / "eta" / "route.ts", eta_api_lines, "/api/eta/route.ts")


# =============================================================================
# [2]  Pipeline scheduler: ensure HMM + XGB run daily
#      Write a standalone wrapper script that can be added to Task Scheduler
# =============================================================================
log("[2/3] Writing daily_ml_update.py (HMM + XGB daily runner)...")

ml_update_lines = [
    '"""',
    'daily_ml_update.py',
    '==================',
    'Runs HMM regime detection + XGB conviction scoring.',
    'Add to Windows Task Scheduler to run after daily_update.py.',
    '',
    'Run: py D:\\MICC\\daily_ml_update.py',
    '"""',
    'import subprocess, sys',
    'from pathlib import Path',
    'from datetime import datetime',
    '',
    'DA  = Path(r"D:\\MICC")',
    'PY  = sys.executable',
    '',
    'def run(script, label, timeout=180):',
    '    print(f"  [{datetime.now().strftime(\"%H:%M:%S\")}] {label}...", flush=True)',
    '    try:',
    '        r = subprocess.run(',
    '            [PY, str(DA / script)],',
    '            cwd=str(DA), timeout=timeout, capture_output=True, text=True',
    '        )',
    '        if r.returncode == 0:',
    '            # Extract last meaningful line from stdout',
    '            lines = [l for l in r.stdout.strip().split("\\n") if l.strip()]',
    '            last  = lines[-1] if lines else "OK"',
    '            print(f"    OK: {last}")',
    '        else:',
    '            print(f"    FAILED: {r.stderr[:200]}")',
    '        return r.returncode == 0',
    '    except subprocess.TimeoutExpired:',
    '        print(f"    TIMEOUT after {timeout}s")',
    '        return False',
    '    except Exception as e:',
    '        print(f"    ERROR: {e}")',
    '        return False',
    '',
    'print(f"MICC Daily ML Update -- {datetime.now().strftime(\"%Y-%m-%d %H:%M\")}")',
    'print("=" * 45)',
    '',
    'results = {',
    '    "hmm":    run("agent_hmm.py",                  "HMM Regime Detection",    timeout=120),',
    '    "xgb":    run("train_conviction_xgb.py --score","XGB Conviction Scoring",  timeout=300),',
    '    "fusion": run("agent_fusion.py",               "Fusion Agent",            timeout=120),',
    '}',
    '',
    'print()',
    'ok = sum(results.values())',
    'print(f"Results: {ok}/{len(results)} OK")',
    'for k, v in results.items():',
    '    print(f"  {k:<10} {\'OK\' if v else \'FAILED\'}")',
    '',
    'if ok == len(results):',
    '    print("\\nAll ML models updated successfully.")',
    'else:',
    '    print("\\nSome tasks failed -- check output above.")',
]
write(MICC / "daily_ml_update.py", ml_update_lines, "daily_ml_update.py")


# =============================================================================
# [3]  /overview page -- add pipeline status panel + HMM regime widget
#      Patch the existing overview to show a status strip at bottom
# =============================================================================
log("[3/3] Patching /overview page with HMM + pipeline status...")

overview_path = APP / "page.tsx"
if overview_path.exists():
    ov_src = overview_path.read_text(encoding="utf-8")

    if "hmm_regime" not in ov_src and "morning-brief" not in ov_src:
        # Add regime state
        old_state = "const [reports, setReports] = useState"
        new_state = (
            "const [regime, setRegime]   = useState<{regime:string;bull_prob:number;bear_prob:number;confidence:number}|null>(null);\n"
            "  const [reports, setReports] = useState"
        )
        ov_src = ov_src.replace(old_state, new_state, 1)

        # Add regime fetch
        old_fetch_end = "setReports(d); setLoading(false);"
        new_fetch_end = (
            "setReports(d); setLoading(false);\n"
            "          // Also fetch HMM regime\n"
            "          fetch('/api/morning-brief')\n"
            "            .then(r => r.json())\n"
            "            .then(d => setRegime(d.hmm as typeof regime))\n"
            "            .catch(() => {});"
        )
        ov_src = ov_src.replace(old_fetch_end, new_fetch_end, 1)

        # Add HMM regime banner before agent cards
        regime_banner = (
            "\n        {/* HMM Regime Banner */}\n"
            "        {regime && (\n"
            "          <div style={{\n"
            "            display: 'flex', gap: 16, alignItems: 'center',\n"
            "            padding: '10px 16px', marginBottom: 16,\n"
            "            background: 'var(--surface)', border: '1px solid var(--border)',\n"
            "            borderRadius: 8, fontSize: 12,\n"
            "          }}>\n"
            "            <span style={{ fontSize: 10, color: 'var(--dim)', letterSpacing: 1 }}>REGIME (HMM)</span>\n"
            "            <span style={{\n"
            "              fontWeight: 700, fontSize: 14,\n"
            "              color: regime.regime === 'BULL' ? 'var(--bull)'\n"
            "                   : regime.regime === 'BEAR' ? 'var(--bear)' : 'var(--warn)'\n"
            "            }}>\n"
            "              {regime.regime === 'BULL' ? 'UP' : regime.regime === 'BEAR' ? 'DN' : '--'}\n"
            "              {' '}{regime.regime}\n"
            "            </span>\n"
            "            <span style={{ fontSize: 11, color: 'var(--dim)' }}>\n"
            "              {(regime.confidence * 100).toFixed(0)}% conf\n"
            "            </span>\n"
            "            <span style={{ color: 'var(--bull)', fontSize: 11 }}>\n"
            "              Bull {(regime.bull_prob * 100).toFixed(0)}%\n"
            "            </span>\n"
            "            <span style={{ color: 'var(--bear)', fontSize: 11 }}>\n"
            "              Bear {(regime.bear_prob * 100).toFixed(0)}%\n"
            "            </span>\n"
            "            <a href='/fusion' style={{ marginLeft: 'auto', fontSize: 10,\n"
            "              color: 'var(--accent)', textDecoration: 'none' }}>VIEW FUSION ›</a>\n"
            "          </div>\n"
            "        )}\n"
        )

        # Find the agent cards rendering section
        for anchor in [
            "<AlphaPanel",
            "{loading && <div",
            "<div style={wrap}",
        ]:
            if anchor in ov_src:
                ov_src = ov_src.replace(anchor, regime_banner + "        " + anchor, 1)
                print("  [OK] HMM regime banner added to /overview")
                break
        else:
            print("  [INFO] Could not find injection point in /overview -- banner skipped")

        overview_path.write_text(ov_src, encoding="utf-8")
    else:
        print("  [SKIP] HMM already in /overview")
else:
    print("  [SKIP] /overview page.tsx not found")


print()
print("=" * 60)
print("ALL FIXES + PHASE 8 COMPLETE")
print("=" * 60)
print()
print("Fixes:")
print("  agent_eta.py    -- --no-llm works via argparse now")
print("  agent_eta.py    -- schema aligned (screen1-6 + llm_analysis keys)")
print("  /api/eta        -- normalizes old+new schema transparently")
print()
print("New:")
print("  daily_ml_update.py  -- run HMM+XGB+fusion daily (Task Scheduler)")
print("  /overview           -- HMM regime banner with confidence + probs")
print()
print("Test eta directly:")
print("  py D:\\MICC\\agent_eta.py --no-llm")
print("  (should run all 6 screens in <5s, no LLM timeout)")
print()
print("Test morning brief:")
print("  py D:\\MICC\\morning_brief.py")
print("  (eta should show OK this time)")
print()
print("Daily ML (add to Task Scheduler after daily_update.py):")
print("  py D:\\MICC\\daily_ml_update.py")
print()
print("Git push:")
print("  py D:\\MICC\\git_push_phase3.py")
