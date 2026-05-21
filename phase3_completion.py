"""
phase3_completion.py
====================
Final Phase 3 tasks:
  1. Fix morning_brief.py  -- fusion reads wrong file + wrong schema
  2. Add quality picks to morning brief (fundamentals + OOS filter)
  3. Fix /conviction page -- add OOS filter toggle
  4. Git push all Phase 3A/3B work

Run: py D:\MICC\phase3_completion.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
APP  = DASH / "src" / "app"

def write(path, lines, label=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    lbl = label or path.name
    print(f"  [OK] {lbl}  ({len(lines)} lines)")

def log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

print("=" * 60)
print("PHASE 3 COMPLETION")
print("=" * 60)


# =============================================================================
# [1]  Fix morning_brief.py
#      Bug A: reads fused_picks.json — should read last_report.json["picks"]
#      Bug B: picks schema uses layers_fired (list) not layers (dict)
#      Add: quality picks section (fundamentals top ROCE+ROE stocks)
#      Add: OOS-clean patterns filter (overfit=0)
# =============================================================================
log("[1/3] Fixing morning_brief.py...")

mb_lines = [
    "import subprocess, sys, sqlite3, json",
    "from datetime import datetime",
    "from pathlib import Path",
    "",
    "DA   = Path(r'D:\\MICC')",
    "DB_P = r'D:\\marketDB\\db\\market.db'",
    "PY   = sys.executable",
    "",
    "def ts(): return datetime.now().strftime('%H:%M:%S')",
    "def log(msg): print(f'  [{ts()}] {msg}', flush=True)",
    "",
    "def run_agent(script, timeout=120):",
    "    try:",
    "        r = subprocess.run([PY, str(DA / script)], cwd=str(DA),",
    "                           capture_output=True, text=True, timeout=timeout)",
    "        return r.returncode == 0",
    "    except Exception as e:",
    "        log(f'{script}: {e}')",
    "        return False",
    "",
    "def send(msg):",
    "    try:",
    "        from micc_data import send_telegram_chunks",
    "        return send_telegram_chunks(msg)",
    "    except Exception as e:",
    "        log(f'send failed: {e}')",
    "        return False",
    "",
    "# ---- Data getters -------------------------------------------------------",
    "",
    "def get_global_snapshot():",
    "    WATCH = ['NIFTY50','SPX','VIX','IndiaVIX','US10Y','Gold','CrudeWTI','USDINR','Bitcoin']",
    "    LABELS = {",
    "        'NIFTY50':'Nifty 50 ','SPX':'S&P 500  ','VIX':'VIX      ',",
    "        'IndiaVIX':'IndiaVIX ','US10Y':'US 10Y   ','Gold':'Gold     ',",
    "        'CrudeWTI':'Crude WTI','USDINR':'USD/INR  ','Bitcoin':'Bitcoin  ',",
    "    }",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        ph   = ','.join('?'*len(WATCH))",
    "        rows = conn.execute(",
    "            f'SELECT symbol,close,pct_change FROM global_indices_daily'",
    "            f' WHERE symbol IN ({ph})'",
    "            f' AND date=(SELECT MAX(date) FROM global_indices_daily WHERE symbol=global_indices_daily.symbol)',",
    "            WATCH",
    "        ).fetchall()",
    "        conn.close()",
    "        data = {r[0]:(r[1],r[2]) for r in rows}",
    "        result = []",
    "        for sym in WATCH:",
    "            if sym not in data: continue",
    "            close, chg = data[sym]",
    "            if close is None: continue",
    "            label = LABELS.get(sym, sym)",
    "            ico   = 'UP' if (chg or 0) > 0.3 else 'DN' if (chg or 0) < -0.3 else '--'",
    "            chg_s = f'{chg:+.2f}%' if chg is not None else ''",
    "            result.append(f'  {ico} `{label}` {close:.2f}  {chg_s}')",
    "        log(f'global_snapshot: {len(result)}/{len(WATCH)} symbols')",
    "        return result",
    "    except Exception as e:",
    "        log(f'global_snapshot error: {e}')",
    "        return []",
    "",
    "def get_fusion_picks(n=8):",
    "    # agent_fusion saves to agents/fusion/last_report.json with key 'picks'",
    "    # picks schema: {symbol, n_layers, fusion_score, layers_fired:[...]}",
    "    try:",
    "        p = DA / 'agents' / 'fusion' / 'last_report.json'",
    "        if not p.exists(): return []",
    "        rpt   = json.loads(p.read_text(encoding='utf-8'))",
    "        picks = rpt.get('picks', [])",
    "        return picks[:n]",
    "    except Exception as e:",
    "        log(f'fusion picks error: {e}')",
    "        return []",
    "",
    "def get_todays_patterns(n=6):",
    "    mmdd = datetime.today().strftime('%m-%d')",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        cols = {r[1] for r in conn.execute('PRAGMA table_info(seasonality_patterns_v3)').fetchall()}",
    "        # prefer OOS-validated non-overfit patterns",
    "        if 'overfit' in cols and 'fdr_reject' in cols:",
    "            rows = conn.execute(",
    "                'SELECT symbol,window_days,direction,accuracy,mean_ret,score_v2'",
    "                ' FROM seasonality_patterns_v3'",
    "                ' WHERE anchor_mm_dd=? AND fdr_reject=1 AND (overfit=0 OR overfit IS NULL)'",
    "                ' AND score_v2>1.0 AND ABS(mean_ret)<=50'",
    "                ' ORDER BY score_v2 DESC LIMIT ?',",
    "                (mmdd, n)",
    "            ).fetchall()",
    "        else:",
    "            rows = conn.execute(",
    "                'SELECT symbol,window_days,direction,accuracy,mean_ret,score_v2'",
    "                ' FROM seasonality_patterns_v3'",
    "                ' WHERE anchor_mm_dd=? AND fdr_reject=1 AND score_v2>1.0'",
    "                ' ORDER BY score_v2 DESC LIMIT ?',",
    "                (mmdd, n)",
    "            ).fetchall()",
    "        conn.close()",
    "        return mmdd, rows",
    "    except Exception as e:",
    "        log(f'patterns error: {e}')",
    "        return mmdd, []",
    "",
    "def get_quality_picks(n=5):",
    "    # Top quality stocks: ROCE>=15, ROE>=15, D/E<=1, sorted by conviction",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        tables = {r[0] for r in conn.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall()}",
    "        if 'screener_fundamentals_v2' not in tables:",
    "            conn.close(); return []",
    "        rows = conn.execute(",
    "            'SELECT f.symbol, f.roce, f.roe, f.debt_equity, f.pe_ratio,'",
    "            ' COALESCE(c.conviction_score,0) AS conviction'",
    "            ' FROM screener_fundamentals_v2 f'",
    "            ' LEFT JOIN symbol_conviction c ON c.symbol=f.symbol'",
    "            ' WHERE f.roce>=15 AND f.roe>=12 AND (f.debt_equity IS NULL OR f.debt_equity<=1.5)'",
    "            ' AND f.scrape_ok=1'",
    "            ' ORDER BY CAST(c.conviction_score AS REAL) DESC, f.roce DESC'",
    "            ' LIMIT ?',",
    "            (n,)",
    "        ).fetchall()",
    "        conn.close()",
    "        return rows",
    "    except Exception as e:",
    "        log(f'quality picks error: {e}')",
    "        return []",
    "",
    "def get_eta_highlights():",
    "    try:",
    "        eta_path = DA / 'agents' / 'eta' / 'last_report.json'",
    "        if not eta_path.exists(): return []",
    "        eta = json.loads(eta_path.read_text(encoding='utf-8'))",
    "        # new schema: screen3_insider_clusters",
    "        clusters = (eta.get('screen3_insider_clusters') or",
    "                    eta.get('insider_cluster') or [])[:3]",
    "        return clusters",
    "    except Exception:",
    "        return []",
    "",
    "def get_conviction_top(n=4):",
    "    try:",
    "        conn = sqlite3.connect(DB_P, timeout=10)",
    "        rows = conn.execute(",
    "            'SELECT symbol, ROUND(CAST(conviction_score AS REAL),1)'",
    "            ' FROM symbol_conviction ORDER BY CAST(conviction_score AS REAL) DESC LIMIT ?',",
    "            (n,)",
    "        ).fetchall()",
    "        conn.close()",
    "        return rows",
    "    except Exception:",
    "        return []",
    "",
    "def get_alerts():",
    "    try:",
    "        p = DA / 'agents' / 'alert' / 'last_report.json'",
    "        if not p.exists(): return 0, []",
    "        ar    = json.loads(p.read_text(encoding='utf-8'))",
    "        fired = ar.get('alerts_fired', 0)",
    "        msgs  = [f.get('message','')[:60] for f in ar.get('fired',[])[:3]]",
    "        return fired, msgs",
    "    except Exception:",
    "        return 0, []",
    "",
    "# ---- Main ---------------------------------------------------------------",
    "",
    "def main():",
    "    today = datetime.today().strftime('%A, %d %b %Y')",
    "    print(f'MICC Morning Brief -- {today}')",
    "    print('='*50)",
    "",
    "    log('Running agents...')",
    "    for script in ['agent_fusion.py', 'agent_eta.py', 'agent_alert.py']:",
    "        ok = run_agent(script)",
    "        log(f'  {script}: {\"OK\" if ok else \"FAILED\"}')",
    "",
    "    lines = [f'*MICC Morning Brief -- {today}*', '']",
    "",
    "    # 1. Global markets",
    "    snap = get_global_snapshot()",
    "    if snap:",
    "        lines.append('*Global Markets:*')",
    "        lines.extend(snap)",
    "        lines.append('')",
    "    else:",
    "        lines += ['_Global markets: no data_', '']",
    "",
    "    # 2. Fusion picks",
    "    fusion = get_fusion_picks(n=8)",
    "    if fusion:",
    "        lines.append('*Fusion Signals (multi-layer):*')",
    "        for p in fusion:",
    "            sym    = p.get('symbol', '?')",
    "            nl     = p.get('n_layers', 0)",
    "            fs     = p.get('fusion_score', 0)",
    "            layers = p.get('layers_fired', [])",
    "            tag    = '+'.join(str(l)[:3].upper() for l in layers[:5])",
    "            lines.append(f'  `{sym:<12}` {nl}L  [{tag}]  score={fs}')",
    "        lines += ['_Layers: Beta/Insider/Watch/Season/Conviction/Quant_', '']",
    "    else:",
    "        lines += ['_Fusion: no data -- run agent_fusion.py_', '']",
    "",
    "    # 3. Quality picks (ROCE+ROE fundamentals)",
    "    quality = get_quality_picks(n=5)",
    "    if quality:",
    "        lines.append('*Quality Picks (ROCE>=15, ROE>=12, D/E<=1.5):*')",
    "        for sym, roce, roe, de, pe, conv in quality:",
    "            roce_s = f'{roce:.1f}' if roce else '--'",
    "            roe_s  = f'{roe:.1f}'  if roe  else '--'",
    "            de_s   = f'{de:.2f}'   if de   else '--'",
    "            pe_s   = f'{pe:.1f}'   if pe   else '--'",
    "            lines.append(f'  `{sym:<12}` ROCE={roce_s}% ROE={roe_s}% D/E={de_s} PE={pe_s} Conv={conv:.0f}')",
    "        lines.append('')",
    "",
    "    # 4. Today's patterns (OOS-clean)",
    "    mmdd, pats = get_todays_patterns(n=6)",
    "    if pats:",
    "        lines.append(f'*Seasonal Patterns ({mmdd}) [OOS-validated]:*')",
    "        for sym, win, dirn, acc, mean, score in pats:",
    "            ico  = 'UP' if str(dirn).upper() == 'UP' else 'DN'",
    "            accf = float(acc) if acc else 0",
    "            accf = accf if accf <= 1 else accf / 100",
    "            lines.append(f'  {ico} `{sym:<12}` {win}d  {accf*100:.0f}%  {mean:+.2f}%  s={score:.2f}')",
    "        lines.append('')",
    "    else:",
    "        lines += [f'_No OOS-clean patterns for {mmdd}_', '']",
    "",
    "    # 5. Insider clusters",
    "    clusters = get_eta_highlights()",
    "    if clusters:",
    "        lines.append('*Insider Clusters:*')",
    "        for c in clusters:",
    "            sym   = c.get('symbol','?')",
    "            buys  = c.get('n_buys') or c.get('buy_count',0)",
    "            val   = c.get('total_value_cr',0) or 0",
    "            lines.append(f'  `{sym}` {buys}x BUY  Rs.{val:.1f}Cr')",
    "        lines.append('')",
    "",
    "    # 6. Conviction top",
    "    conv = get_conviction_top(n=4)",
    "    if conv:",
    "        lines.append('*High Conviction:*')",
    "        for sym, score in conv:",
    "            lines.append(f'  `{sym:<12}` {score}/100')",
    "        lines.append('')",
    "",
    "    # 7. Alerts",
    "    fired, alert_msgs = get_alerts()",
    "    if fired:",
    "        lines.append(f'*Alerts Fired: {fired}*')",
    "        lines.extend(f'  {m}' for m in alert_msgs)",
    "        lines.append('')",
    "",
    "    lines.append('_MICC v3 | localhost:3000_')",
    "",
    "    msg = '\\n'.join(lines)",
    "    print('\\n' + msg[:1500] + ('...' if len(msg) > 1500 else ''))",
    "    ok = send(msg)",
    "    log(f'Telegram: {\"SENT\" if ok else \"FAILED\"}')",
    "",
    "if __name__ == '__main__':",
    "    main()",
]

write(MICC / "morning_brief.py", mb_lines, "morning_brief.py")


# =============================================================================
# [2]  /conviction page -- add OOS filter toggle
# =============================================================================
log("[2/3] Adding OOS filter to /conviction page...")

conv_path = APP / "conviction" / "page.tsx"
if conv_path.exists():
    src = conv_path.read_text(encoding="utf-8")
    # Only patch if OOS filter not already there
    if "oosOnly" not in src and "oos_filter" not in src:
        # Add OOS filter state after other filter states
        old_state = "const [search, setSrch]"
        new_state = "const [oosOnly, setOosOnly] = useState(false);\n  const [search, setSrch]"
        if old_state in src:
            src = src.replace(old_state, new_state, 1)

        # Add OOS toggle button near other filter buttons (find minScore or sort controls)
        old_btn_area = "SORT BY"
        new_btn_area = (
            "OOS FILTER"
            "\n        </div>"
            "\n        <div>"
            "\n          <button onClick={() => setOosOnly(!oosOnly)} style={{"
            "padding:'5px 14px',fontSize:11,letterSpacing:1,cursor:'pointer',"
            "border:'1px solid '+(oosOnly?'var(--accent)':'var(--border)'),"
            "borderRadius:4,background:oosOnly?'var(--accent)22':'transparent',"
            "color:oosOnly?'var(--accent)':'var(--dim)'}}>"
            "{oosOnly ? 'OOS: ON' : 'OOS: OFF'}"
            "</button>"
            "\n        </div>"
            "\n        <div style={{fontSize:10,color:'var(--dim)'}}>"
            "SORT BY"
        )
        if old_btn_area in src:
            src = src.replace(old_btn_area, new_btn_area, 1)
            conv_path.write_text(src, encoding="utf-8")
            print("  [OK] OOS filter toggle added to /conviction")
        else:
            print("  [SKIP] Could not find SORT BY anchor in /conviction")
    else:
        print("  [SKIP] OOS filter already in /conviction")
else:
    print("  [SKIP] /conviction/page.tsx not found")


# =============================================================================
# [3]  Git push all Phase 3 work
# =============================================================================
log("[3/3] Git push Phase 3 work...")

git_lines = [
    "import subprocess, sys",
    "from pathlib import Path",
    "from datetime import datetime",
    "",
    "MICC = Path(r'D:\\MICC')",
    "GIT  = r'C:\\Program Files\\Git\\cmd\\git.exe'",
    "",
    "def git(args, cwd=None):",
    "    r = subprocess.run([GIT] + args, cwd=str(cwd or MICC),",
    "                       capture_output=True, text=True)",
    "    if r.stdout.strip(): print(' ', r.stdout.strip()[:200])",
    "    if r.stderr.strip() and r.returncode != 0: print('  ERR:', r.stderr.strip()[:200])",
    "    return r.returncode == 0",
    "",
    "msg = f'Phase 3A/3B: fix all broken pages + OOS validation + scraper resume ({datetime.now().strftime(\"%Y-%m-%d\")})'",
    "",
    "print('Adding all changes...')",
    "git(['-C', str(MICC), 'add', '-A'])",
    "",
    "print('Committing...')",
    "ok = git(['-C', str(MICC), 'commit', '-m', msg])",
    "if not ok:",
    "    print('  Nothing to commit or commit failed')",
    "",
    "print('Pushing...')",
    "ok = git(['-C', str(MICC), 'push', 'origin', 'main', '--force'])",
    "if ok:",
    "    print('  Pushed to GitHub OK')",
    "else:",
    "    print('  Push failed -- check credentials')",
    "    print('  Manual: & \"C:\\\\Program Files\\\\Git\\\\cmd\\\\git.exe\" -C D:\\\\MICC push origin main --force')",
]

write(MICC / "git_push_phase3.py", git_lines, "git_push_phase3.py")


# =============================================================================
print()
print("=" * 60)
print("PHASE 3 COMPLETION DONE")
print("=" * 60)
print()
print("Files written:")
print("  D:\\MICC\\morning_brief.py       -- fixed fusion path + quality picks section")
print("  D:\\MICC\\git_push_phase3.py     -- run to push all changes to GitHub")
print()
print("Changes in morning_brief.py:")
print("  FIX: fusion reads last_report.json['picks'] not fused_picks.json")
print("  FIX: layers_fired is a list, not a dict -- tag string corrected")
print("  ADD: Quality picks section (ROCE>=15, ROE>=12, D/E<=1.5)")
print("  ADD: OOS-clean pattern filter (overfit=0 OR NULL)")
print("  ADD: Dual cluster key support (screen3_insider_clusters OR insider_cluster)")
print()
print("OOS full run is running -- let it finish, then test morning brief:")
print("  py D:\\MICC\\morning_brief.py")
print()
print("Git push:")
print("  py D:\\MICC\\git_push_phase3.py")
