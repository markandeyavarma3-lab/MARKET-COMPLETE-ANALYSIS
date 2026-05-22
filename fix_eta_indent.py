"""
fix_eta_indent.py
=================
Rewrites the broken section of agent_eta.py (lines ~481-524).
The previous patch created mixed indentation around the LLM block.
This directly replaces the entire run_eta() tail + __main__ block.

Run: py D:\MICC\fix_eta_indent.py
"""
from pathlib import Path

eta_path = Path(r"D:\MICC\agent_eta.py")
src = eta_path.read_text(encoding="utf-8")

# Find the anchor just before the broken section
ANCHOR = '    print("  Screen 6: Upcoming results calendar...")'
assert ANCHOR in src, "Anchor not found -- agent_eta structure changed"

# Everything up to and including the anchor + upcoming lines
idx = src.index(ANCHOR)
# Keep everything up to end of "upcoming" assignment
end_of_upcoming = src.index(
    '    print(f"    {len(upcoming)} stocks with results due soon")',
    idx
)
end_of_upcoming += len('    print(f"    {len(upcoming)} stocks with results due soon")')

prefix = src[:end_of_upcoming]

# Write the correct tail
tail = '''

    print("  LLM analysis...")
    if no_llm:
        analysis = "[LLM skipped]"
        print("    skipped (--no-llm)")
    else:
        prompt   = build_prompt(results_season, dividends, clusters,
                                 big_trades, reactions, upcoming)
        analysis, _src = call_llm(prompt, max_tokens=600, label="Eta")
        print(f"    {len(str(analysis))} chars")

    report = {
        "agent":              "eta",
        "date":               today_str(),
        "timestamp":          now_ist(),
        "generated_at":       now_ist(),
        # Original keys (backward compat)
        "results_season":     results_season,
        "dividend_calendar":  dividends,
        "insider_cluster":    clusters,
        "big_insider_trades": big_trades,
        "post_results_reaction": reactions,
        "upcoming_results":   upcoming,
        "analysis":           analysis,
        # New keys matching /eta dashboard page
        "screen1_results_season":        results_season,
        "screen2_dividends":             dividends,
        "screen3_insider_clusters":      clusters,
        "screen4_big_trades":            big_trades,
        "screen5_post_results_reaction": reactions,
        "screen6_upcoming_results":      upcoming,
        "llm_analysis":                  analysis,
    }

    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {out}")

    if send:
        msg = format_telegram(report)
        ok  = send_telegram_chunks(msg)
        print(f"  Telegram: {'OK' if ok else 'FAILED'}")

    print(f"\\n  Results reported:      {len(results_season)}")
    print(f"  Corporate actions:     {len(dividends)}")
    print(f"  Insider clusters:      {len(clusters)}")
    print(f"  Big insider trades:    {len(big_trades)}")
    print(f"  Upcoming results:      {len(upcoming)}")
    print("=" * 55)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send",   action="store_true")
    ap.add_argument("--no-llm", action="store_true", dest="no_llm")
    args = ap.parse_args()
    run_eta(send=args.send, no_llm=args.no_llm)
'''

# Also fix the function signature
prefix = prefix.replace(
    "def run_eta(send: bool = False) -> dict:",
    "def run_eta(send: bool = False, no_llm: bool = False) -> dict:",
    1
)

# Remove any stale no_llm injections from previous patches
prefix = prefix.replace(
    'import sys\nno_llm = "--no-llm" in sys.argv\n',
    'import sys\n'
)
prefix = prefix.replace(
    'no_llm = "--no-llm" in sys.argv\n',
    ''
)

final = prefix + tail
eta_path.write_text(final, encoding="utf-8")

# Verify it parses
import ast
try:
    ast.parse(final)
    print("[OK] agent_eta.py syntax valid")
except SyntaxError as e:
    print(f"[ERROR] Still has syntax error: {e}")
    print("  Check around line", e.lineno)

lines = len(final.splitlines())
print(f"[OK] agent_eta.py written ({lines} lines)")
print()
print("Test:")
print("  py D:\\MICC\\agent_eta.py --no-llm")
print("  (should complete in <5s with all 6 screens)")
