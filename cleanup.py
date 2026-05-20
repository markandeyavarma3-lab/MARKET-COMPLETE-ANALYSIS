"""
MICC Cleanup Script
Run from DATA-ANALYSIS:  py cleanup.py
Deletes all patch/fix/probe/diag/debug/backup files, keeps only core working files.
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))

# ── Files to DELETE (all the fix/patch/probe/diag garbage) ───────────────────
DELETE = [
    # Dashboard fix attempts
    "fix_dashboard.py", "fix_gamma_score.ps1", "fix_utf8.py",
    "fix2_dashboard.ps1", "patch_dashboard.ps1", "fix_dashboard.ps1",
    "fix_task3.ps1", "setup_dashboard.ps1", "deploy_micc_v3.ps1",
    "build_dashboard.py",  # old one - will be replaced

    # Phase 1 patches (already applied)
    "patch_1_1_date_normaliser.py", "patch_1_2_engine_argparse.py",
    "patch_1_5_error_logging.py", "patch_1_6_snapshot_dedup.py",
    "setup_1_4_scheduler.ps1",

    # Phase 2 patches (already applied)
    "patch_2_1_global_data.py", "patch_2_2_earnings_accel.py",
    "patch_2_2b_eps_level_boost.py", "patch_2_3_insider_alerts.py",
    "fix_2_2_earnings_keys.py", "fix_2_2b_beta_eps.py",
    "patch_2_5_signals_history.py", "patch_2_6_regime_conditioning.py",
    "fix_2_5_final.py", "fix_2_5_beta_imports.py",

    # Phase 3 patches (already applied)
    "patch_3_1_telegram_enhancements.py", "patch_3_2_gamma_delta_regime.py",
    "fix_3_1_markdown_and_dates.py", "direct_3_2_apply.py",
    "telegram_custom_patch.py",

    # Fix scripts (already applied)
    "fix_delta_regime_key.py", "fix_delta_sig.py", "fix_delta_final.py",
    "fix_date_keys.py", "fix_escape_warning.py", "fix_beta_imports.py",
    "fix_beta_import_final.py", "fix_eps_direct.py", "fix_eps_closure.py",
    "fix_eps_level_schema.py", "fix_line565.py", "fix_nan_json.py",
    "fix_nan_indent.py", "fix_splice.py", "fix_quotes.py",
    "fix_indices.py", "fix_tailwind_v4.py", "patch_delta_vix.py",
    "fix_delta_sig.py",

    # Probe/diagnostic scripts (one-time use, done)
    "probe_1_6_snapshot_dupes.py", "probe_custom_tables.py",
    "probe_date_keys.py", "probe_delta_ret.py", "probe_eps_coverage.py",
    "probe_fii_dii.py", "probe_final_confirm.py", "probe_market_activity.py",
    "probe_parquet.py", "probe_quarterly_income.py", "probe_quarterly_real.py",
    "probe_imports.py", "probe_beta_live.py",

    # Debug/diag scripts
    "diag_eps.py", "diag_eps2.py", "diag_eps3.py",
    "debug_eps_level.py", "date_probe.py", "check.py", "check_bytes.py",
    "check_live.py",

    # Inline/rewrite one-offs
    "inline_eps_beta.py", "rewrite_eps.py", "read_beta_call.py",
    "trace_eps.py", "find_micc_data.py", "purge_and_test.py",
    "final_test.py", "test_earnings_accel.py", "test_delta_alerts.py",

    # Backup files
    "micc_data.py.bak_phase2_2b", "micc_data.py.bak_phase2_2",
    "micc_data.py.bak_phase2_1", "micc_data.py.bak_phase1_1",
    "micc_engine.py.bak_phase1_2", "micc_engine.py.bak_phase1_5",
    "agent_beta.py.bak_phase2_2", "agent_alpha.py.bak_phase2_1",

    # Old/unused agent variants
    "agent_alpha1.py", "agent_beta1.py", "agent_gamma1.py",
    "agent_delta.py",  # KEEP if this is the real one - see note below
    "agent_epsilon.py", "agent_zeta.py", "agent_eta.py",
    "agent_theta.py", "agent_iota.py",

    # Custom period / deep analysis (unused in main pipeline)
    "custom_period_report.py", "deep_analysis_engine.py",

    # Run wrapper duplicates
    "run_engine_wrapper.ps1",
]

# ── Files to KEEP (never touch these) ────────────────────────────────────────
KEEP = {
    "agent_alpha.py", "agent_beta.py", "agent_gamma.py", "agent_delta.py",
    "micc_engine.py", "micc_data.py", "micc_db_bridge.py",
    "telegram_bot.py", "health_check.py", "run_engine_wrapper.py",
    "backfill_signals_history.py", "backfill_indices.py", "backfill_fo_data.py",
    "setup.py", "requirements.txt", "micc_watchlist.json",
    "cleanup.py",  # this file
}

print("=" * 60)
print("MICC Cleanup - Preview Mode")
print("=" * 60)

to_delete = []
not_found = []
protected = []

for fname in DELETE:
    path = os.path.join(BASE, fname)
    if fname in KEEP:
        protected.append(fname)
    elif os.path.exists(path):
        to_delete.append(path)
    else:
        not_found.append(fname)

print(f"\nFiles to DELETE ({len(to_delete)}):")
for p in to_delete:
    print(f"  DEL  {os.path.basename(p)}")

if not_found:
    print(f"\nNot found (already clean, {len(not_found)}):")
    for f in not_found:
        print(f"  N/A  {f}")

if protected:
    print(f"\nSkipped (in KEEP list, {len(protected)}):")
    for f in protected:
        print(f"  KEEP {f}")

print(f"\n{'=' * 60}")
print(f"Will delete {len(to_delete)} files. KEEP list has {len(KEEP)} protected files.")
print(f"{'=' * 60}")

if len(to_delete) == 0:
    print("Nothing to delete. Already clean!")
    sys.exit(0)

confirm = input("\nType YES to delete, anything else to cancel: ").strip()
if confirm != "YES":
    print("Cancelled.")
    sys.exit(0)

deleted = 0
errors = 0
for p in to_delete:
    try:
        os.remove(p)
        print(f"  deleted: {os.path.basename(p)}")
        deleted += 1
    except Exception as e:
        print(f"  ERROR deleting {os.path.basename(p)}: {e}")
        errors += 1

print(f"\nDone. Deleted {deleted} files. Errors: {errors}")
print("\nCore files kept:")
for f in sorted(KEEP):
    p = os.path.join(BASE, f)
    status = "EXISTS" if os.path.exists(p) else "MISSING"
    print(f"  [{status}] {f}")
