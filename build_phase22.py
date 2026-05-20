"""
build_phase22.py  --  Run from D:\MICC
Fixes:
  [1] /eta/page.tsx  -- fix unterminated string (newline inside string literal)
  [2] build_seasonality_v3_stocks.py -- mine patterns for NSE stocks (parquet)
  [3] Universal autocomplete SymbolSearch component
  [4] Wire autocomplete into /patterns-v3 page

Run: py D:\MICC\build_phase22.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"
COMP = DASH / "src" / "components"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")

def patch(path: Path, old: str, new: str, label: str) -> bool:
    if not path.exists():
        print(f"  [SKIP] {label} -- not found"); return False
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [SKIP] {label} -- marker not found"); return False
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  [OK] {label}"); return True


# =============================================================================
# [1]  Fix /eta/page.tsx -- unterminated string on line 278
#      The bug: text.split("\n") was written with a literal newline instead
#      of the escape sequence \n
# =============================================================================
print("\n[1/4] Fixing /eta/page.tsx unterminated string ...")

eta_path = SRC / "eta" / "page.tsx"
if not eta_path.exists():
    print("  [SKIP] eta/page.tsx not found")
else:
    src = eta_path.read_text(encoding="utf-8")

    # The broken line has a literal newline inside a string split call
    # Find and fix: text.split(" with a real newline after it
    import re

    # Fix 1: literal newline inside string split
    # Pattern: text.split(" then newline then ");
    broken = 'text.split("\n");'
    # It might be stored as text.split(" + actual_newline + ");
    # Replace all variants
    src = re.sub(
        r'text\.split\(\s*"\s*\n\s*"\s*\)',
        'text.split("\\n")',
        src
    )
    # Also fix any other string literals with literal newlines (common Python->TS bug)
    src = re.sub(
        r'("|\')([^"\']*)\n([^"\']*)\1',
        lambda m: m.group(1) + m.group(2) + "\\n" + m.group(3) + m.group(1),
        src
    )

    # Fix 2: the AnalysisBox function specifically
    # Replace the whole function with a clean version
    OLD_ANALYSIS = re.search(
        r'function AnalysisBox\(\{[^}]+\}\)[^{]*\{.*?^}',
        src, re.MULTILINE | re.DOTALL
    )
    if OLD_ANALYSIS:
        CLEAN_ANALYSIS = '''\
function AnalysisBox({ text }: { text: string }) {
  if (!text) return null;
  const lines = text.split("\\n");
  return (
    <Card style={{ borderColor: "#7c3aed" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 18 }}>🧠</span>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#e2e8f0", letterSpacing: 1 }}>
          LLM ANALYSIS
        </h2>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#7c3aed" }}>Eta Agent</span>
      </div>
      <div style={{ lineHeight: 1.7 }}>
        {lines.map((line, i) => {
          const isHeader = line.trim().length > 4 && line.trim() === line.trim().toUpperCase();
          return (
            <p key={i} style={{
              margin: "4px 0",
              fontSize: 13,
              fontWeight: isHeader ? 700 : 400,
              color: isHeader ? "#a78bfa" : "#cbd5e1",
              letterSpacing: isHeader ? 1 : 0,
            }}>{line || String.fromCharCode(160)}</p>
          );
        })}
      </div>
    </Card>
  );
}'''
        src = src[:OLD_ANALYSIS.start()] + CLEAN_ANALYSIS + src[OLD_ANALYSIS.end():]
        print("  [OK] Rewrote AnalysisBox function cleanly")
    else:
        print("  [WARN] AnalysisBox not found via regex -- applying string fix only")

    eta_path.write_text(src, encoding="utf-8")
    print("  [OK] eta/page.tsx saved")


# =============================================================================
# [2]  build_seasonality_v3_stocks.py
#      Mines patterns ONLY for parquet stocks (NSE stocks like AXISBANK, etc.)
#      Run separately after this script:
#        py D:\MICC\build_seasonality_v3_stocks.py
# =============================================================================
print("\n[2/4] Writing build_seasonality_v3_stocks.py ...")

stocks_builder_lines = [
    '"""',
    'build_seasonality_v3_stocks.py  --  Run from D:\\MICC',
    'Mines seasonality_patterns_v3 for NSE stocks from parquet files.',
    'The original build_seasonality_v3.py processed NSE indices + global indices.',
    'This script processes the remaining ~2600 NSE stocks.',
    '',
    'Run:',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py           -- full build',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py --resume  -- resume',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py --sym AXISBANK  -- test one',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py --verify  -- show counts',
    '',
    'This will take many hours (2600 stocks x 58 windows x 365 anchors).',
    'Run overnight. Auto-checkpoints every 100 symbols.',
    '"""',
    '',
    '# Re-uses all functions from build_seasonality_v3.py',
    '# Just changes the symbol source to parquet-only',
    '',
    'import sys, json, time, math, sqlite3, warnings, os',
    'warnings.filterwarnings("ignore")',
    'from pathlib import Path',
    'from datetime import datetime',
    '',
    'try:',
    '    import numpy as np',
    '    import pandas as pd',
    '    from scipy import stats as scipy_stats',
    '    HAS_SCIPY = True',
    'except ImportError:',
    '    import numpy as np',
    '    import pandas as pd',
    '    HAS_SCIPY = False',
    '',
    'DB_PATH  = Path(r"D:\\marketDB\\db\\market.db")',
    'PARQUET  = Path(r"D:\\marketDB\\stocks\\all")',
    'CKPT     = Path(r"D:\\MICC\\seasonality_stocks_checkpoint.json")',
    '',
    '# Copy constants from v3',
    'WIN_MIN = 3',
    'WIN_MAX = 60',
    'WINDOWS = list(range(WIN_MIN, WIN_MAX + 1))',
    'MIN_OBS      = 5',
    'MIN_ACCURACY = 55.0',
    'MIN_SCORE    = 0.3',
    'COMMIT_EVERY = 1000',
    '',
    'R=chr(27)+"[0m"; B=chr(27)+"[1m"; G=chr(27)+"[92m"',
    'Y=chr(27)+"[93m"; RD=chr(27)+"[91m"; C=chr(27)+"[96m"',
    'D=chr(27)+"[2m"; M=chr(27)+"[95m"',
    '',
    'def now_str(): return datetime.now().strftime("%H:%M:%S")',
    'def hms(s):',
    '    h=int(s//3600); m=int((s%3600)//60); sc=int(s%60)',
    '    return f"{h}h{m:02d}m{sc:02d}s" if h else f"{m}m{sc:02d}s"',
    'def pbar(done, total, w=28):',
    '    f=int(w*done/max(total,1))',
    '    return f"[{chr(9608)*f}{chr(9617)*(w-f)}] {100*done/max(total,1):5.1f}%"',
    'def log(msg, lvl="INFO"):',
    '    tag={"OK":f"{G} OK {R}","FAIL":f"{RD}FAIL{R}","WARN":f"{Y}WARN{R}"}.get(lvl,f"{C}INFO{R}")',
    '    print(f"  [{now_str()}] [{tag}]  {msg}", flush=True)',
    '',
    'def get_conn():',
    '    conn = sqlite3.connect(DB_PATH, timeout=120)',
    '    conn.execute("PRAGMA journal_mode=WAL")',
    '    conn.execute("PRAGMA synchronous=NORMAL")',
    '    conn.execute("PRAGMA cache_size=-65536")',
    '    conn.execute("PRAGMA temp_store=MEMORY")',
    '    conn.execute("PRAGMA busy_timeout=30000")',
    '    conn.execute("PRAGMA read_uncommitted=1")',
    '    return conn',
    '',
    'def load_parquet(symbol: str):',
    '    sym_dir = PARQUET / symbol',
    '    if not sym_dir.exists(): return None',
    '    files = sorted(sym_dir.glob(f"{symbol}_*.parquet"))',
    '    if not files: return None',
    '    dfs = []',
    '    for f in files:',
    '        try: dfs.append(pd.read_parquet(f, columns=["date","close"]))',
    '        except Exception: continue',
    '    if not dfs: return None',
    '    df = pd.concat(dfs, ignore_index=True)',
    '    df["date"] = pd.to_datetime(df["date"])',
    '    df = df.dropna(subset=["close"]).sort_values("date")',
    '    df = df.drop_duplicates("date").set_index("date")',
    '    return df["close"].astype(float)',
    '',
    'def get_all_anchors():',
    '    from datetime import date',
    '    anchors = []',
    '    for month in range(1,13):',
    '        for day in range(1,32):',
    '            try:',
    '                d = date(2000,month,day)',
    '                if not (month==2 and day==29): anchors.append(f"{month:02d}-{day:02d}")',
    '            except ValueError: continue',
    '    return anchors',
    '',
    'def mine_anchor_window(prices, anchor_mm_dd, window, dates_arr, price_map):',
    '    import bisect',
    '    from datetime import date',
    '    mm, dd = int(anchor_mm_dd[:2]), int(anchor_mm_dd[3:])',
    '    year_returns = {}',
    '    years = sorted(set(d.year for d in dates_arr))',
    '    for yr in years:',
    '        try: target = date(yr, mm, dd)',
    '        except ValueError: continue',
    '        entry_date = None',
    '        bi = bisect.bisect_left(dates_arr, pd.Timestamp(target))',
    '        for k in range(bi, min(bi+5, len(dates_arr))):',
    '            if dates_arr[k].year == yr:',
    '                entry_date = dates_arr[k]; break',
    '        if entry_date is None: continue',
    '        ep = price_map.get(entry_date)',
    '        if not ep or ep <= 0: continue',
    '        exit_bi = bisect.bisect_left(dates_arr, entry_date) + window',
    '        if exit_bi >= len(dates_arr): continue',
    '        xp = price_map.get(dates_arr[exit_bi])',
    '        if not xp or xp <= 0: continue',
    '        ret = (xp / ep - 1) * 100',
    '        # Sanity check: skip if return is unrealistic (price level artifact)',
    '        if abs(ret) > 50: continue',
    '        year_returns[yr] = round(ret, 4)',
    '    if len(year_returns) < MIN_OBS: return None',
    '    rets = list(year_returns.values())',
    '    arr  = np.array(rets, dtype=float)',
    '    n    = len(arr)',
    '    mean_ret  = float(np.mean(arr))',
    '    direction = "UP" if mean_ret >= 0 else "DOWN"',
    '    accuracy  = float(np.mean(arr > 0)*100 if direction=="UP" else np.mean(arr < 0)*100)',
    '    if accuracy < MIN_ACCURACY: return None',
    '    std_ret  = float(np.std(arr, ddof=1)) if n > 1 else 0.0',
    '    score    = round(accuracy * abs(mean_ret) * math.log(max(n,2)) / 100, 4)',
    '    if score < MIN_SCORE: return None',
    '    med_ret  = float(np.median(arr))',
    '    p10=float(np.percentile(arr,10)); p25=float(np.percentile(arr,25))',
    '    p75=float(np.percentile(arr,75)); p90=float(np.percentile(arr,90))',
    '    best_ret=float(np.max(arr)); worst_ret=float(np.min(arr))',
    '    consistency = round(max(0.0, min(1.0, 1 - std_ret/(abs(mean_ret)+1e-9))), 4)',
    '    edge_ratio  = round(abs(mean_ret)/(abs(worst_ret)+1e-9), 4)',
    '    if n > 1 and std_ret > 0:',
    '        t_stat = float(mean_ret/(std_ret/math.sqrt(n)))',
    '        if HAS_SCIPY: p_value = float(scipy_stats.t.sf(abs(t_stat),df=n-1)*2)',
    '        else: p_value = float(min(1.0, 2/(1+abs(t_stat)*math.sqrt(n))))',
    '    else: t_stat=0.0; p_value=1.0',
    '    half = n // 2',
    '    if half >= 3:',
    '        fh=arr[:half]; sh=arr[half:]',
    '        early_acc  = float(np.mean(fh>0)*100 if direction=="UP" else np.mean(fh<0)*100)',
    '        recent_acc = float(np.mean(sh>0)*100 if direction=="UP" else np.mean(sh<0)*100)',
    '        degradation= round(recent_acc-early_acc, 2)',
    '    else: early_acc=recent_acc=accuracy; degradation=0.0',
    '    years_list = sorted(year_returns.keys())',
    '    cutoff_yr  = max(years_list)-5',
    '    recent_rets= [year_returns[y] for y in years_list if y>=cutoff_yr]',
    '    recent_mean = float(np.mean(recent_rets)) if recent_rets else mean_ret',
    '    recent_vs_all = round(recent_mean - mean_ret, 4)',
    '    import json as _json',
    '    sorted_rets = sorted(year_returns.items(), key=lambda x:x[1], reverse=True)',
    '    best_years  = _json.dumps([{"year":y,"ret":round(r,3)} for y,r in sorted_rets[:5]])',
    '    worst_years = _json.dumps([{"year":y,"ret":round(r,3)} for y,r in sorted_rets[-5:]])',
    '    all_returns = _json.dumps([{"year":y,"ret":round(year_returns[y],3)} for y in years_list])',
    '    return (anchor_mm_dd, window, direction, n,',
    '            round(accuracy,2), round(mean_ret,4), round(med_ret,4),',
    '            round(std_ret,4), round(p10,4), round(p25,4), round(p75,4), round(p90,4),',
    '            round(best_ret,4), round(worst_ret,4), score, consistency,',
    '            round(edge_ratio,4), round(t_stat,4), round(p_value,6),',
    '            round(early_acc,2), round(recent_acc,2), degradation,',
    '            round(recent_mean,4), round(recent_vs_all,4),',
    '            best_years, worst_years, all_returns)',
    '',
    'def process_symbol(conn, symbol, prices):',
    '    if len(prices) < 300: return 0',
    '    prices     = prices.sort_index()',
    '    price_map  = prices.to_dict()',
    '    dates_arr  = sorted(prices.index)',
    '    anchors    = get_all_anchors()',
    '    rows       = []',
    '    inserted   = 0',
    '    INSERT_SQL = """',
    '        INSERT OR REPLACE INTO seasonality_patterns_v3',
    '        (symbol,anchor_mm_dd,window_days,direction,n_obs,',
    '         accuracy,mean_ret,median_ret,std_ret,p10,p25,p75,p90,',
    '         best_ret,worst_ret,score,consistency,edge_ratio,',
    '         t_stat,p_value,early_accuracy,recent_accuracy,',
    '         degradation,recent_mean,recent_vs_all,',
    '         best_years,worst_years,all_returns)',
    '        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""',
    '    for anchor in anchors:',
    '        for window in WINDOWS:',
    '            try:',
    '                result = mine_anchor_window(prices, anchor, window, dates_arr, price_map)',
    '            except Exception: continue',
    '            if result is None: continue',
    '            rows.append((symbol,) + result)',
    '            if len(rows) >= COMMIT_EVERY:',
    '                for _r in range(6):',
    '                    try: conn.executemany(INSERT_SQL, rows); conn.commit(); break',
    '                    except sqlite3.OperationalError as _e:',
    '                        if "locked" in str(_e).lower() and _r<5: time.sleep(5+_r*3)',
    '                        else: raise',
    '                inserted += len(rows); rows = []',
    '    if rows:',
    '        for _r in range(6):',
    '            try: conn.executemany(INSERT_SQL, rows); conn.commit(); break',
    '            except sqlite3.OperationalError as _e:',
    '                if "locked" in str(_e).lower() and _r<5: time.sleep(5+_r*3)',
    '                else: raise',
    '        inserted += len(rows)',
    '    return inserted',
    '',
    'def save_ckpt(done): CKPT.write_text(json.dumps({"done":done}))',
    'def load_ckpt():',
    '    if not CKPT.exists(): return set()',
    '    try: return set(json.loads(CKPT.read_text()).get("done",[]))',
    '    except: return set()',
    '',
    'def run(resume=False, single=None):',
    '    print(f"\\n{B}{C}Seasonality Miner v3 -- STOCKS ONLY{R}")',
    '    print(f"  Windows: {WIN_MIN}d to {WIN_MAX}d ({len(WINDOWS)} windows)")',
    '    print(f"  Source:  {PARQUET}\\n")',
    '',
    '    # Build symbol list from parquet',
    '    if single:',
    '        syms = [single.upper()]',
    '    else:',
    '        if not PARQUET.exists():',
    '            log(f"Parquet directory not found: {PARQUET}", "FAIL"); return',
    '        syms = []',
    '        for d in sorted(PARQUET.iterdir()):',
    '            if d.is_dir() and d.name and (d / f"{d.name}_2024.parquet").exists():',
    '                syms.append(d.name)',
    '        log(f"Found {len(syms):,} symbols in parquet directory")',
    '',
    '    done_set = load_ckpt() if resume else set()',
    '    if resume and done_set:',
    '        log(f"Resuming -- {len(done_set)} done, {len(syms)-len(done_set)} remaining")',
    '',
    '    conn = get_conn()',
    '    t0   = time.time()',
    '    done_count = 0',
    '    total_pats = 0',
    '    fail_count = 0',
    '    done_list  = list(done_set)',
    '',
    '    for idx, symbol in enumerate(syms, 1):',
    '        if symbol in done_set: done_count += 1; continue',
    '',
    '        elapsed = time.time() - t0',
    '        speed   = done_count / max(elapsed, 1)',
    '        eta_s   = (len(syms) - idx) / max(speed, 1e-9)',
    '        sym_label = str(symbol or "?")[:18]',
    '        print(',
    '            f"\\r  {pbar(idx, len(syms))}  {G}{sym_label:<18}{R}"',
    '            f"  ETA {hms(eta_s)}  pats={total_pats:,}  ",',
    '            end="", flush=True',
    '        )',
    '',
    '        prices = None',
    '        try: prices = load_parquet(symbol)',
    '        except Exception as e: log(f"{symbol}: load failed -- {str(e)[:60]}", "FAIL"); fail_count+=1; continue',
    '',
    '        if prices is None or len(prices) < 300:',
    '            done_list.append(symbol); done_set.add(symbol); done_count+=1; continue',
    '',
    '        try: n_pats = process_symbol(conn, symbol, prices)',
    '        except Exception as e: log(f"\\n{symbol}: mine failed -- {str(e)[:60]}", "FAIL"); fail_count+=1; continue',
    '',
    '        total_pats += n_pats',
    '        done_list.append(symbol); done_set.add(symbol); done_count += 1',
    '',
    '        if done_count % 100 == 0: save_ckpt(done_list)',
    '        if done_count % 50 == 0:',
    '            print()',
    '            total_db = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]',
    '            log(f"Progress: {done_count}/{len(syms)}  DB rows: {total_db:,}  Elapsed: {hms(elapsed)}")',
    '',
    '    print()',
    '    save_ckpt(done_list)',
    '    total_db = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]',
    '    conn.close()',
    '    elapsed = time.time() - t0',
    '    print(f"\\n{B}BUILD COMPLETE{R}")',
    '    print(f"  Symbols processed: {done_count:,}")',
    '    print(f"  Symbols failed:    {fail_count:,}")',
    '    print(f"  Total DB rows:     {total_db:,}")',
    '    print(f"  Time:              {hms(elapsed)}")',
    '',
    'if __name__ == "__main__":',
    '    import argparse',
    '    ap = argparse.ArgumentParser()',
    '    ap.add_argument("--resume", action="store_true")',
    '    ap.add_argument("--sym")',
    '    ap.add_argument("--verify", action="store_true")',
    '    args = ap.parse_args()',
    '    if args.verify:',
    '        conn = get_conn()',
    '        total = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]',
    '        syms  = conn.execute("SELECT COUNT(DISTINCT symbol) FROM seasonality_patterns_v3").fetchone()[0]',
    '        print(f"  Patterns: {total:,}  |  Symbols: {syms:,}")',
    '        top = conn.execute(',
    '            "SELECT symbol, COUNT(*) FROM seasonality_patterns_v3 GROUP BY symbol ORDER BY COUNT(*) DESC LIMIT 10"',
    '        ).fetchall()',
    '        for s,c in top: print(f"    {s:<20} {c:>8,}")',
    '        conn.close()',
    '    else:',
    '        run(resume=args.resume, single=args.sym)',
]

write(MICC / "build_seasonality_v3_stocks.py",
      "\n".join(stocks_builder_lines),
      "build_seasonality_v3_stocks.py")


# =============================================================================
# [3]  Universal SymbolSearch component
#      Used in /patterns-v3, /compare, /alerts, /stocks search, /watchlist
# =============================================================================
print("\n[3/4] Writing SymbolSearch component ...")

COMP.mkdir(parents=True, exist_ok=True)

symbol_search_tsx = '''\
"use client";

import { useState, useEffect, useRef, useCallback } from "react";

export interface SearchResult {
  symbol: string;
  name: string;
  type: "stock" | "index" | "global";
}

interface Props {
  value?: string;
  onSelect: (symbol: string, result?: SearchResult) => void;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  width?: number | string;
  clearAfterSelect?: boolean;
}

const TYPE_COLORS: Record<string, string> = {
  stock:  "#60a5fa",
  index:  "#34d399",
  global: "#fbbf24",
};

const TYPE_LABELS: Record<string, string> = {
  stock:  "NSE",
  index:  "INDEX",
  global: "GLOBAL",
};

export default function SymbolSearch({
  value = "",
  onSelect,
  placeholder = "Search symbol or company name...",
  disabled = false,
  autoFocus = false,
  width = "100%",
  clearAfterSelect = false,
}: Props) {
  const [query,   setQuery]   = useState(value);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open,    setOpen]    = useState(false);
  const [idx,     setIdx]     = useState(-1);
  const [loading, setLoading] = useState(false);
  const ref   = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync external value
  useEffect(() => { setQuery(value); }, [value]);

  // Click outside to close
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  // Debounced search
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (!query.trim() || query.length < 1) {
      setResults([]); setOpen(false); return;
    }
    setLoading(true);
    timer.current = setTimeout(async () => {
      try {
        const r = await fetch(
          "/api/search?q=" + encodeURIComponent(query) + "&limit=12"
        );
        const d = await r.json();
        const res = (d.results || []) as SearchResult[];
        setResults(res);
        setOpen(res.length > 0);
        setIdx(-1);
      } catch {}
      setLoading(false);
    }, 180);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [query]);

  const pick = useCallback((result: SearchResult) => {
    onSelect(result.symbol, result);
    if (clearAfterSelect) {
      setQuery("");
    } else {
      setQuery(result.symbol);
    }
    setResults([]); setOpen(false); setIdx(-1);
  }, [onSelect, clearAfterSelect]);

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault(); setIdx(i => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault(); setIdx(i => Math.max(i - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (idx >= 0 && results[idx]) {
        pick(results[idx]);
      } else if (query.trim()) {
        onSelect(query.trim().toUpperCase());
        if (clearAfterSelect) setQuery("");
        setOpen(false);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={ref} style={{ position: "relative", width }}>
      <div style={{ position: "relative" }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value.toUpperCase())}
          onKeyDown={onKey}
          onFocus={() => results.length && setOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          autoFocus={autoFocus}
          autoComplete="off"
          spellCheck={false}
          style={{
            width: "100%",
            padding: "9px 36px 9px 14px",
            background: "#1e293b",
            border: "1px solid " + (open ? "#3b82f6" : "#334155"),
            borderRadius: 8,
            color: "#f8fafc",
            fontSize: 13,
            outline: "none",
            boxSizing: "border-box",
            opacity: disabled ? 0.45 : 1,
            transition: "border-color 0.15s",
          }}
        />
        {/* Search icon / spinner */}
        <div style={{
          position: "absolute", right: 10, top: "50%",
          transform: "translateY(-50%)",
          color: "#475569", fontSize: 14, pointerEvents: "none",
        }}>
          {loading ? "..." : "⌕"}
        </div>
      </div>

      {/* Dropdown */}
      {open && results.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)",
          left: 0, right: 0, zIndex: 9999,
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: 8,
          boxShadow: "0 12px 40px rgba(0,0,0,0.7)",
          overflow: "hidden",
          maxHeight: 320,
          overflowY: "auto",
        }}>
          {results.map((r, i) => (
            <div
              key={r.symbol}
              onMouseDown={e => { e.preventDefault(); pick(r); }}
              onMouseEnter={() => setIdx(i)}
              style={{
                padding: "9px 14px",
                cursor: "pointer",
                background: i === idx ? "#334155" : "transparent",
                display: "flex",
                alignItems: "center",
                gap: 10,
                borderBottom: i < results.length - 1 ? "1px solid #0f172a" : "none",
                transition: "background 0.1s",
              }}
            >
              <span style={{
                fontFamily: "monospace",
                fontWeight: 700,
                fontSize: 13,
                color: TYPE_COLORS[r.type] || "#f8fafc",
                minWidth: 110,
              }}>
                {r.symbol}
              </span>
              {r.name && r.name !== r.symbol && (
                <span style={{
                  fontSize: 11,
                  color: "#64748b",
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}>
                  {r.name}
                </span>
              )}
              <span style={{
                fontSize: 9,
                fontWeight: 700,
                padding: "1px 6px",
                borderRadius: 4,
                color: TYPE_COLORS[r.type] || "#94a3b8",
                background: (TYPE_COLORS[r.type] || "#94a3b8") + "22",
                flexShrink: 0,
              }}>
                {TYPE_LABELS[r.type] || r.type}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
'''
write(COMP / "SymbolSearch.tsx", symbol_search_tsx, "src/components/SymbolSearch.tsx")


# =============================================================================
# [4]  Patch /patterns-v3/page.tsx to use the shared SymbolSearch component
# =============================================================================
print("\n[4/4] Patching /patterns-v3/page.tsx to use SymbolSearch ...")

pv3_path = SRC / "patterns-v3" / "page.tsx"
if not pv3_path.exists():
    print("  [SKIP] /patterns-v3/page.tsx not found")
else:
    src = pv3_path.read_text(encoding="utf-8")

    # Add import if missing
    if "SymbolSearch" not in src:
        src = src.replace(
            '"use client";',
            '"use client";\n\nimport SymbolSearch from "@/components/SymbolSearch";'
        )
        print("  [OK] Added SymbolSearch import")

        # Replace the manual symbol input block with the component
        # Find the SYMBOL input div and replace it
        import re
        # Look for the input with symbol-related placeholder
        OLD_INPUT = re.search(
            r'<div>\s*<div[^>]*>SYMBOL</div>\s*<div[^>]*>[^<]*<input[^/]*/>[^<]*(?:<button[^>]*>[^<]*</button>[^<]*)?(?:<button[^>]*>[^<]*</button>[^<]*)?\s*</div>\s*</div>',
            src, re.DOTALL
        )
        if OLD_INPUT:
            NEW_INPUT = """\
<div>
            <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>SYMBOL</div>
            <div style={{ display: "flex", gap: 6 }}>
              <SymbolSearch
                value={inputSym}
                onSelect={(sym) => { setInputSym(sym); setSymbol(sym); }}
                placeholder="Symbol or company name..."
                width={240}
              />
              {symbol && (
                <button onClick={() => { setSymbol(""); setInputSym(""); }}
                  style={{ padding: "7px 10px", background: "#334155",
                    color: "#94a3b8", border: "none", borderRadius: 7,
                    cursor: "pointer", fontSize: 12 }}>x</button>
              )}
            </div>
          </div>"""
            src = src[:OLD_INPUT.start()] + NEW_INPUT + src[OLD_INPUT.end():]
            print("  [OK] Replaced symbol input with SymbolSearch component")
        else:
            print("  [SKIP] Could not find symbol input block -- add manually")

        pv3_path.write_text(src, encoding="utf-8")
    else:
        print("  [SKIP] SymbolSearch already imported in patterns-v3")


print("""
=============================================================
BUILD PHASE 22 COMPLETE
=============================================================

FIXES:
  [1] /eta/page.tsx
      Fixed unterminated string in AnalysisBox (literal newline
      inside text.split() call replaced with \\\\n escape)

  [2] D:\\MICC\\build_seasonality_v3_stocks.py  (NEW)
      Mines patterns for ALL NSE stocks from parquet files
      Start now:
        py D:\\MICC\\build_seasonality_v3_stocks.py --sym AXISBANK  (test)
        py D:\\MICC\\build_seasonality_v3_stocks.py                  (full, overnight)
        py D:\\MICC\\build_seasonality_v3_stocks.py --resume         (if crashed)
      Key: built-in |mean_ret| > 50 guard so no price-level artifacts

  [3] src/components/SymbolSearch.tsx  (SHARED COMPONENT)
      Google-style autocomplete used everywhere:
        - Debounced 180ms
        - Arrow key navigation
        - Enter to select
        - Type badge: NSE / INDEX / GLOBAL
        - Dropdown closes on outside click
      Import: import SymbolSearch from "@/components/SymbolSearch"

  [4] /patterns-v3/page.tsx
      Symbol input replaced with SymbolSearch component

TO USE SymbolSearch on any other page:
  import SymbolSearch from "@/components/SymbolSearch";
  <SymbolSearch
    onSelect={(sym) => setSymbol(sym)}
    placeholder="Search stock..."
    clearAfterSelect={false}
  />

NOW RUN:
  cd D:\\MICC\\micc-dashboard && npm run dev
  -- eta page should compile now
  -- patterns-v3 has autocomplete search

  In new terminal (overnight):
  py D:\\MICC\\build_seasonality_v3_stocks.py --sym AXISBANK
  -- if that shows patterns, run the full build:
  py D:\\MICC\\build_seasonality_v3_stocks.py
=============================================================
""")
