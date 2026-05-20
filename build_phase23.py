"""
build_phase23.py  --  Run from D:\MICC
Fixes:
  [1] build_seasonality_v3_stocks.py  -- reads stock_data from SQLite (not parquet)
                                         parquet only has current-year delivery data
  [2] /api/patterns-v3/detail/route.ts -- fix for stock symbols
  [3] /stocks/[symbol]/page.tsx patch  -- add seasonal patterns section

Run: py D:\MICC\build_phase23.py
Then start overnight build:
  py D:\MICC\build_seasonality_v3_stocks.py --sym AXISBANK   (test first)
  py D:\MICC\build_seasonality_v3_stocks.py                   (overnight)
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path: Path, content: str, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {label}  ({len(content.splitlines())} lines)")


# =============================================================================
# [1]  build_seasonality_v3_stocks.py  -- FIXED to use stock_data SQLite
# =============================================================================
print("\n[1/3] Writing build_seasonality_v3_stocks.py (fixed) ...")

lines = []
lines += [
    '# -*- coding: utf-8 -*-',
    '"""',
    'build_seasonality_v3_stocks.py  --  Run from D:\\MICC',
    'Mines seasonality_patterns_v3 for NSE stocks.',
    'FIXED: reads from stock_data SQLite table (has full history back to ~2000)',
    '       parquet files only have current-year delivery data -- wrong source.',
    '',
    'Run:',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py --sym AXISBANK  (test)',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py                  (overnight full)',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py --resume         (resume if crashed)',
    '  py D:\\MICC\\build_seasonality_v3_stocks.py --verify         (show counts)',
    '"""',
    '',
    'import sys, json, time, math, sqlite3, warnings, bisect',
    'from pathlib import Path',
    'from datetime import datetime, date',
    '',
    'warnings.filterwarnings("ignore")',
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
    'DB_PATH = Path(r"D:\\marketDB\\db\\market.db")',
    'CKPT    = Path(r"D:\\MICC\\seasonality_stocks_checkpoint.json")',
    '',
    'WIN_MIN      = 3',
    'WIN_MAX      = 60',
    'WINDOWS      = list(range(WIN_MIN, WIN_MAX + 1))',
    'MIN_OBS      = 5',
    'MIN_ACCURACY = 55.0',
    'MIN_SCORE    = 0.3',
    'COMMIT_EVERY = 2000',
    'PROGRESS_EVERY = 20',
    '',
    '# Terminal colors',
    'R  = chr(27) + "[0m"',
    'B  = chr(27) + "[1m"',
    'G  = chr(27) + "[92m"',
    'Y  = chr(27) + "[93m"',
    'RD = chr(27) + "[91m"',
    'C  = chr(27) + "[96m"',
    'D  = chr(27) + "[2m"',
    '',
    'def now_str(): return datetime.now().strftime("%H:%M:%S")',
    '',
    'def hms(s):',
    '    h = int(s // 3600); m = int((s % 3600) // 60); sc = int(s % 60)',
    '    return f"{h}h{m:02d}m{sc:02d}s" if h else f"{m}m{sc:02d}s"',
    '',
    'def pbar(done, total, w=28):',
    '    f = int(w * done / max(total, 1))',
    '    return "[" + chr(9608)*f + chr(9617)*(w-f) + f"] {100*done/max(total,1):5.1f}%"',
    '',
    'def log(msg, lvl="INFO"):',
    '    tag = {"OK": G+" OK "+R, "FAIL": RD+"FAIL"+R, "WARN": Y+"WARN"+R}.get(lvl, C+"INFO"+R)',
    '    print(f"  [{now_str()}] [{tag}]  {msg}", flush=True)',
    '',
    '',
    '# ── DB connection ────────────────────────────────────────────────────────',
    'def get_conn():',
    '    conn = sqlite3.connect(DB_PATH, timeout=120)',
    '    conn.execute("PRAGMA journal_mode=WAL")',
    '    conn.execute("PRAGMA synchronous=NORMAL")',
    '    conn.execute("PRAGMA cache_size=-131072")',
    '    conn.execute("PRAGMA temp_store=MEMORY")',
    '    conn.execute("PRAGMA busy_timeout=30000")',
    '    conn.execute("PRAGMA read_uncommitted=1")',
    '    return conn',
    '',
    '',
    '# ── Load stock prices from stock_data table ───────────────────────────────',
    'def load_stock_prices(conn, symbol: str):',
    '    """Load close prices from stock_data table. Returns pd.Series indexed by Timestamp."""',
    '    try:',
    '        rows = conn.execute(',
    '            "SELECT date, close FROM stock_data "',
    '            "WHERE symbol=? AND close IS NOT NULL AND close > 0 "',
    '            "ORDER BY date",',
    '            (symbol.upper(),)',
    '        ).fetchall()',
    '        if len(rows) < MIN_OBS * 10:',
    '            return None',
    '        idx  = pd.to_datetime([r[0] for r in rows])',
    '        vals = [float(r[1]) for r in rows]',
    '        series = pd.Series(vals, index=idx).sort_index()',
    '        series = series[series > 0]',
    '        return series if len(series) >= 300 else None',
    '    except Exception as e:',
    '        return None',
    '',
    '',
    '# ── Get all tradable symbols from stock_data ──────────────────────────────',
    'def get_all_symbols(conn):',
    '    """Get symbols with enough history (min 5 years = ~1250 trading days)."""',
    '    rows = conn.execute(',
    '        "SELECT symbol, COUNT(*) as n "',
    '        "FROM stock_data "',
    '        "WHERE close IS NOT NULL AND close > 0 "',
    '        "GROUP BY symbol "',
    '        "HAVING n >= 1250 "',
    '        "ORDER BY symbol"',
    '    ).fetchall()',
    '    return [r[0] for r in rows]',
    '',
    '',
    '# ── Anchor dates ─────────────────────────────────────────────────────────',
    'def get_all_anchors():',
    '    anchors = []',
    '    for month in range(1, 13):',
    '        for day in range(1, 32):',
    '            try:',
    '                date(2000, month, day)',
    '                if not (month == 2 and day == 29):',
    '                    anchors.append(f"{month:02d}-{day:02d}")',
    '            except ValueError:',
    '                continue',
    '    return anchors',
    '',
    '',
    '# ── Mine one anchor × window ──────────────────────────────────────────────',
    'def mine_anchor_window(prices, anchor_mm_dd, window, dates_arr, price_map):',
    '    mm  = int(anchor_mm_dd[:2])',
    '    dd  = int(anchor_mm_dd[3:])',
    '    year_returns = {}',
    '    years = sorted(set(d.year for d in dates_arr))',
    '',
    '    for yr in years:',
    '        try:',
    '            target = date(yr, mm, dd)',
    '        except ValueError:',
    '            continue',
    '',
    '        target_ts = pd.Timestamp(target)',
    '        bi = bisect.bisect_left(dates_arr, target_ts)',
    '',
    '        # Find first trading day >= target in this year',
    '        entry_date = None',
    '        for k in range(bi, min(bi + 5, len(dates_arr))):',
    '            if dates_arr[k].year == yr:',
    '                entry_date = dates_arr[k]',
    '                break',
    '        if entry_date is None:',
    '            continue',
    '',
    '        ep = price_map.get(entry_date)',
    '        if not ep or ep <= 0:',
    '            continue',
    '',
    '        # Exit: window trading days later',
    '        entry_bi = bisect.bisect_left(dates_arr, entry_date)',
    '        exit_bi  = entry_bi + window',
    '        if exit_bi >= len(dates_arr):',
    '            continue',
    '',
    '        xp = price_map.get(dates_arr[exit_bi])',
    '        if not xp or xp <= 0:',
    '            continue',
    '',
    '        ret = (xp / ep - 1) * 100',
    '        year_returns[yr] = round(ret, 4)',
    '',
    '    if len(year_returns) < MIN_OBS:',
    '        return None',
    '',
    '    rets = list(year_returns.values())',
    '    arr  = np.array(rets, dtype=float)',
    '    n    = len(arr)',
    '',
    '    mean_ret  = float(np.mean(arr))',
    '    direction = "UP" if mean_ret >= 0 else "DOWN"',
    '    accuracy  = float((np.mean(arr > 0) if direction == "UP" else np.mean(arr < 0)) * 100)',
    '',
    '    if accuracy < MIN_ACCURACY:',
    '        return None',
    '',
    '    std_ret  = float(np.std(arr, ddof=1)) if n > 1 else 0.0',
    '    score    = round(accuracy * abs(mean_ret) * math.log(max(n, 2)) / 100, 4)',
    '',
    '    if score < MIN_SCORE:',
    '        return None',
    '',
    '    med_ret   = float(np.median(arr))',
    '    p10 = float(np.percentile(arr, 10))',
    '    p25 = float(np.percentile(arr, 25))',
    '    p75 = float(np.percentile(arr, 75))',
    '    p90 = float(np.percentile(arr, 90))',
    '    best_ret  = float(np.max(arr))',
    '    worst_ret = float(np.min(arr))',
    '    consistency  = round(max(0.0, min(1.0, 1 - std_ret / (abs(mean_ret) + 1e-9))), 4)',
    '    edge_ratio   = round(abs(mean_ret) / (abs(worst_ret) + 1e-9), 4)',
    '',
    '    if n > 1 and std_ret > 0:',
    '        t_stat = float(mean_ret / (std_ret / math.sqrt(n)))',
    '        if HAS_SCIPY:',
    '            p_value = float(scipy_stats.t.sf(abs(t_stat), df=n-1) * 2)',
    '        else:',
    '            p_value = float(min(1.0, 2 / (1 + abs(t_stat) * math.sqrt(n))))',
    '    else:',
    '        t_stat = 0.0',
    '        p_value = 1.0',
    '',
    '    half = n // 2',
    '    if half >= 3:',
    '        fh = arr[:half]; sh = arr[half:]',
    '        early_acc  = float((np.mean(fh > 0) if direction=="UP" else np.mean(fh < 0)) * 100)',
    '        recent_acc = float((np.mean(sh > 0) if direction=="UP" else np.mean(sh < 0)) * 100)',
    '        degradation = round(recent_acc - early_acc, 2)',
    '    else:',
    '        early_acc = recent_acc = accuracy',
    '        degradation = 0.0',
    '',
    '    years_list  = sorted(year_returns.keys())',
    '    cutoff_yr   = max(years_list) - 5',
    '    recent_rets = [year_returns[y] for y in years_list if y >= cutoff_yr]',
    '    recent_mean = float(np.mean(recent_rets)) if recent_rets else mean_ret',
    '    recent_vs_all = round(recent_mean - mean_ret, 4)',
    '',
    '    sorted_rets = sorted(year_returns.items(), key=lambda x: x[1], reverse=True)',
    '    best_years  = json.dumps([{"year": y, "ret": round(r, 3)} for y, r in sorted_rets[:5]])',
    '    worst_years = json.dumps([{"year": y, "ret": round(r, 3)} for y, r in sorted_rets[-5:]])',
    '    all_returns = json.dumps([{"year": y, "ret": round(year_returns[y], 3)} for y in years_list])',
    '',
    '    return (',
    '        anchor_mm_dd, window, direction, n,',
    '        round(accuracy, 2), round(mean_ret, 4), round(med_ret, 4),',
    '        round(std_ret, 4), round(p10, 4), round(p25, 4), round(p75, 4), round(p90, 4),',
    '        round(best_ret, 4), round(worst_ret, 4), score, consistency,',
    '        round(edge_ratio, 4), round(t_stat, 4), round(p_value, 6),',
    '        round(early_acc, 2), round(recent_acc, 2), degradation,',
    '        round(recent_mean, 4), round(recent_vs_all, 4),',
    '        best_years, worst_years, all_returns',
    '    )',
    '',
    '',
    '# ── Process one symbol ───────────────────────────────────────────────────',
    'INSERT_SQL = """INSERT OR REPLACE INTO seasonality_patterns_v3',
    '    (symbol,anchor_mm_dd,window_days,direction,n_obs,',
    '     accuracy,mean_ret,median_ret,std_ret,p10,p25,p75,p90,',
    '     best_ret,worst_ret,score,consistency,edge_ratio,',
    '     t_stat,p_value,early_accuracy,recent_accuracy,',
    '     degradation,recent_mean,recent_vs_all,',
    '     best_years,worst_years,all_returns)',
    '    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""',
    '',
    'def process_symbol(conn, symbol, prices):',
    '    if len(prices) < 300:',
    '        return 0',
    '    prices    = prices.sort_index()',
    '    price_map = prices.to_dict()',
    '    dates_arr = sorted(prices.index)',
    '    anchors   = get_all_anchors()',
    '    rows      = []',
    '    inserted  = 0',
    '',
    '    for anchor in anchors:',
    '        for window in WINDOWS:',
    '            try:',
    '                result = mine_anchor_window(prices, anchor, window, dates_arr, price_map)',
    '            except Exception:',
    '                continue',
    '            if result is None:',
    '                continue',
    '            rows.append((symbol,) + result)',
    '',
    '            if len(rows) >= COMMIT_EVERY:',
    '                for attempt in range(6):',
    '                    try:',
    '                        conn.executemany(INSERT_SQL, rows)',
    '                        conn.commit()',
    '                        break',
    '                    except sqlite3.OperationalError as e:',
    '                        if "locked" in str(e).lower() and attempt < 5:',
    '                            time.sleep(5 + attempt * 3)',
    '                        else:',
    '                            raise',
    '                inserted += len(rows)',
    '                rows = []',
    '',
    '    if rows:',
    '        for attempt in range(6):',
    '            try:',
    '                conn.executemany(INSERT_SQL, rows)',
    '                conn.commit()',
    '                break',
    '            except sqlite3.OperationalError as e:',
    '                if "locked" in str(e).lower() and attempt < 5:',
    '                    time.sleep(5 + attempt * 3)',
    '                else:',
    '                    raise',
    '        inserted += len(rows)',
    '',
    '    return inserted',
    '',
    '',
    '# ── Checkpoint ───────────────────────────────────────────────────────────',
    'def save_ckpt(done_list):',
    '    CKPT.write_text(json.dumps({"done": done_list}))',
    '',
    'def load_ckpt():',
    '    if not CKPT.exists():',
    '        return set()',
    '    try:',
    '        return set(json.loads(CKPT.read_text()).get("done", []))',
    '    except Exception:',
    '        return set()',
    '',
    '',
    '# ── Main ─────────────────────────────────────────────────────────────────',
    'def run(resume=False, single=None):',
    '    print(f"\\n{B}{C}Seasonality Miner v3 -- NSE Stocks (stock_data){R}")',
    '    print(f"  Windows : {WIN_MIN}d to {WIN_MAX}d ({len(WINDOWS)} windows)")',
    '    print(f"  Source  : stock_data table in SQLite DB")',
    '    print(f"  DB      : {DB_PATH}\\n")',
    '',
    '    conn = get_conn()',
    '',
    '    if single:',
    '        syms = [single.upper()]',
    '        log(f"Single symbol mode: {single.upper()}")',
    '    else:',
    '        log("Loading symbol list from stock_data (min 1250 rows = ~5yr history)...")',
    '        syms = get_all_symbols(conn)',
    '        log(f"Found {len(syms):,} symbols with sufficient history", "OK")',
    '',
    '    done_set  = load_ckpt() if resume else set()',
    '    remaining = [s for s in syms if s not in done_set]',
    '',
    '    if resume and done_set:',
    '        log(f"Resuming: {len(done_set)} done, {len(remaining)} remaining")',
    '',
    '    t0         = time.time()',
    '    done_count = 0',
    '    total_pats = 0',
    '    fail_count = 0',
    '    done_list  = list(done_set)',
    '',
    '    for idx, symbol in enumerate(remaining, 1):',
    '        elapsed = time.time() - t0',
    '        speed   = done_count / max(elapsed, 1)',
    '        eta_s   = (len(remaining) - idx) / max(speed, 1e-9)',
    '        sym_lbl = str(symbol)[:16]',
    '',
    '        print(',
    '            f"\\r  {pbar(idx, len(remaining))} {G}{sym_lbl:<16}{R}"',
    '            f"  ETA {hms(eta_s)}  pats={total_pats:,}  db_total={done_count+len(done_set):,}  ",',
    '            end="", flush=True',
    '        )',
    '',
    '        # Load prices',
    '        try:',
    '            prices = load_stock_prices(conn, symbol)',
    '        except Exception as e:',
    '            print()',
    '            log(f"{symbol}: load failed -- {str(e)[:60]}", "FAIL")',
    '            fail_count += 1',
    '            continue',
    '',
    '        if prices is None:',
    '            # Not enough history -- mark done and skip',
    '            done_list.append(symbol)',
    '            done_set.add(symbol)',
    '            done_count += 1',
    '            continue',
    '',
    '        # Mine patterns',
    '        try:',
    '            n_pats = process_symbol(conn, symbol, prices)',
    '        except Exception as e:',
    '            print()',
    '            log(f"{symbol}: mine failed -- {str(e)[:80]}", "FAIL")',
    '            fail_count += 1',
    '            continue',
    '',
    '        total_pats += n_pats',
    '        done_list.append(symbol)',
    '        done_set.add(symbol)',
    '        done_count += 1',
    '',
    '        # Checkpoint every 100 symbols',
    '        if done_count % 100 == 0:',
    '            save_ckpt(done_list)',
    '',
    '        # Progress log every N symbols',
    '        if done_count % PROGRESS_EVERY == 0:',
    '            print()',
    '            total_db = conn.execute(',
    '                "SELECT COUNT(*) FROM seasonality_patterns_v3"',
    '            ).fetchone()[0]',
    '            log(',
    '                f"Progress: {done_count}/{len(remaining)} syms"',
    '                f"  DB rows: {total_db:,}"',
    '                f"  Elapsed: {hms(elapsed)}"',
    '                f"  ETA: {hms(eta_s)}"',
    '            )',
    '',
    '    print()',
    '    save_ckpt(done_list)',
    '',
    '    total_db = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]',
    '    conn.close()',
    '',
    '    elapsed = time.time() - t0',
    '    print(f"\\n{B}{"="*55}{R}")',
    '    print(f"{B}  BUILD COMPLETE{R}")',
    '    print(f"{"="*55}")',
    '    print(f"  Symbols processed : {done_count:,}")',
    '    print(f"  Symbols failed    : {fail_count:,}")',
    '    print(f"  Total DB rows     : {total_db:,}")',
    '    print(f"  Time              : {hms(elapsed)}")',
    '',
    '    # Show top 15 patterns',
    '    conn2 = get_conn()',
    '    print(f"\\n  Top patterns by score:")',
    '    top = conn2.execute(',
    '        "SELECT symbol, anchor_mm_dd, window_days, direction, accuracy, mean_ret, score "',
    '        "FROM seasonality_patterns_v3 "',
    '        "WHERE symbol NOT IN (\'US2Y\',\'US10Y\',\'US30Y\') "',
    '        "ORDER BY score DESC LIMIT 15"',
    '    ).fetchall()',
    '    for r in top:',
    '        sym, anc, win, dirn, acc, mean, score = r',
    '        d = G if dirn=="UP" else RD',
    '        print(f"  {C}{sym:<16}{R} {anc} {win:>3}d {d}{dirn:<5}{R} {acc:.1f}% {mean:+.2f}% s={score:.2f}")',
    '    conn2.close()',
    '',
    '',
    'if __name__ == "__main__":',
    '    import argparse',
    '    ap = argparse.ArgumentParser()',
    '    ap.add_argument("--resume", action="store_true")',
    '    ap.add_argument("--sym",    help="Single symbol to test")',
    '    ap.add_argument("--verify", action="store_true")',
    '    args = ap.parse_args()',
    '',
    '    if args.verify:',
    '        conn = get_conn()',
    '        total = conn.execute("SELECT COUNT(*) FROM seasonality_patterns_v3").fetchone()[0]',
    '        syms  = conn.execute("SELECT COUNT(DISTINCT symbol) FROM seasonality_patterns_v3").fetchone()[0]',
    '        wins  = conn.execute("SELECT COUNT(DISTINCT window_days) FROM seasonality_patterns_v3").fetchone()[0]',
    '        print(f"\\n  Total patterns : {total:,}")',
    '        print(f"  Unique symbols : {syms:,}")',
    '        print(f"  Window sizes   : {wins}")',
    '        print(f"\\n  Top 20 symbols by pattern count:")',
    '        top = conn.execute(',
    '            "SELECT symbol, COUNT(*), AVG(accuracy), AVG(score) "',
    '            "FROM seasonality_patterns_v3 GROUP BY symbol "',
    '            "ORDER BY COUNT(*) DESC LIMIT 20"',
    '        ).fetchall()',
    '        for s, c, acc, sc in top:',
    '            print(f"    {s:<20} {c:>7,} patterns  acc={acc:.1f}%  score={sc:.2f}")',
    '        conn.close()',
    '    else:',
    '        run(resume=args.resume, single=args.sym)',
]

write(MICC / "build_seasonality_v3_stocks.py", "\n".join(lines),
      "build_seasonality_v3_stocks.py")


# =============================================================================
# [2]  /api/patterns-v3/detail/route.ts  -- fix for any symbol type
# =============================================================================
print("\n[2/3] Writing /api/patterns-v3/detail/route.ts ...")

detail_ts = """import { NextResponse } from "next/server";
import { spawnSync }    from "child_process";
import { Buffer }       from "buffer";

const DB = "D:/marketDB/db/market.db";
const PY = "py";
const DA = "D:/MICC";

function sanitize(s: string) {
  return s.replace(/:\\s*NaN\\b/g, ": null").replace(/:\\s*Infinity\\b/g, ": null");
}

function qone(sql: string, params: any[]): any | null {
  const sqlB64  = Buffer.from(sql).toString("base64");
  const pyLines = [
    "import sqlite3, json, sys, base64",
    "conn = sqlite3.connect(r'" + DB + "', timeout=15)",
    "conn.row_factory = sqlite3.Row",
    "sql = base64.b64decode(sys.argv[1]).decode()",
    "params = json.loads(sys.argv[2])",
    "row = conn.execute(sql, params).fetchone()",
    "print(json.dumps(dict(row) if row else None, default=str))",
    "conn.close()",
  ];
  const r = spawnSync(PY, ["-c", pyLines.join("\\n"), sqlB64, JSON.stringify(params)],
    { cwd: DA, encoding: "utf-8", timeout: 15000 });
  if (r.status !== 0) throw new Error(r.stderr?.slice(0, 200));
  const txt = r.stdout.trim();
  if (!txt || txt === "null") return null;
  return JSON.parse(sanitize(txt));
}

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "").toUpperCase();
  const anchor = url.searchParams.get("anchor") || "";
  const window_ = parseInt(url.searchParams.get("window") || "0");
  const dir    = (url.searchParams.get("direction") || "").toUpperCase();

  if (!symbol || !anchor || !window_ || !dir)
    return NextResponse.json({ error: "Need symbol, anchor, window, direction" }, { status: 400 });

  try {
    const row = qone(
      "SELECT * FROM seasonality_patterns_v3 WHERE symbol=? AND anchor_mm_dd=? AND window_days=? AND direction=?",
      [symbol, anchor, window_, dir]
    );
    if (!row) return NextResponse.json({ error: "Pattern not found" }, { status: 404 });

    try { row.best_years  = JSON.parse(row.best_years  || "[]"); } catch {}
    try { row.worst_years = JSON.parse(row.worst_years || "[]"); } catch {}
    try { row.all_returns = JSON.parse(row.all_returns || "[]"); } catch {}

    return NextResponse.json(row);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
"""
write(SRC / "api" / "patterns-v3" / "detail" / "route.ts", detail_ts,
      "/api/patterns-v3/detail/route.ts")


# =============================================================================
# [3]  Add seasonal patterns section to /stocks/[symbol] page
#      We add a small API call and display at bottom of existing stock page
# =============================================================================
print("\n[3/3] Patching /stocks/[symbol]/page.tsx ...")

stocks_page = SRC / "stocks" / "[symbol]" / "page.tsx"
if not stocks_page.exists():
    print("  [SKIP] /stocks/[symbol]/page.tsx not found")
else:
    src = stocks_page.read_text(encoding="utf-8")

    if "stock-patterns" not in src and "seasonality" not in src.lower():
        # Add import
        if '"use client"' in src and "import" in src:
            # Add seasonal patterns section component before export default
            SEASONAL_COMPONENT = '''
// ── Seasonal Patterns Section ─────────────────────────────────────────────────
function SeasonalPatterns({ symbol }: { symbol: string }) {
  const [pats, setPats] = React.useState<any[]>([]);
  const [upcoming, setUpcoming] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    if (!symbol) return;
    fetch("/api/stock-patterns/" + symbol + "?min_accuracy=60&limit=15")
      .then(r => r.json())
      .then(d => {
        setPats(d.patterns || []);
        setUpcoming(d.upcoming || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return (
    <div style={{ padding: "20px", color: "#64748b", fontSize: 13 }}>
      Loading seasonal patterns...
    </div>
  );

  if (!pats.length && !upcoming.length) return (
    <div style={{ padding: "20px", color: "#475569", fontSize: 12 }}>
      No patterns found yet. Run: py D:\\\\MICC\\\\build_seasonality_v3_stocks.py
    </div>
  );

  return (
    <div style={{ padding: "20px 28px" }}>
      {upcoming.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: "#fbbf24",
            margin: "0 0 10px", letterSpacing: 0.8 }}>
            UPCOMING PATTERNS (next 30 days)
          </h3>
          {upcoming.map((p: any, i: number) => {
            const up = p.direction === "UP";
            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "7px 12px", background: "#1e293b",
                borderRadius: 8, marginBottom: 5,
                borderLeft: "3px solid " + (up ? "#22c55e" : "#ef4444"),
              }}>
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 3,
                  background: up ? "#0f2d1f" : "#2d1515", color: up ? "#22c55e" : "#ef4444",
                }}>{p.direction}</span>
                <span style={{ fontSize: 11, color: "#64748b" }}>
                  {p.anchor_mm_dd} + {p.window_days}d
                </span>
                <span style={{ marginLeft: "auto", fontSize: 13, fontWeight: 700,
                  color: up ? "#22c55e" : "#ef4444" }}>
                  {p.accuracy?.toFixed(0)}%
                </span>
                <span style={{ fontSize: 11, color: "#94a3b8" }}>
                  {p.mean_ret >= 0 ? "+" : ""}{p.mean_ret?.toFixed(2)}%
                </span>
                <span style={{ fontSize: 10, color: "#475569" }}>s={p.score?.toFixed(1)}</span>
              </div>
            );
          })}
        </div>
      )}

      {pats.length > 0 && (
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: "#94a3b8",
            margin: "0 0 10px", letterSpacing: 0.8 }}>
            TOP SEASONAL PATTERNS (all time)
          </h3>
          {pats.slice(0, 10).map((p: any, i: number) => {
            const up = p.direction === "UP";
            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "6px 12px", background: "#1e293b",
                borderRadius: 7, marginBottom: 4,
                borderLeft: "3px solid " + (up ? "#22c55e44" : "#ef444444"),
              }}>
                <span style={{ fontSize: 10, fontWeight: 700,
                  color: up ? "#22c55e" : "#ef4444" }}>{p.direction}</span>
                <span style={{ fontSize: 11, color: "#64748b" }}>
                  {p.anchor_mm_dd} + {p.window_days}d
                </span>
                <span style={{ fontSize: 11, color: "#94a3b8" }}>
                  acc={p.accuracy?.toFixed(0)}%
                </span>
                <span style={{ fontSize: 11, color: up ? "#22c55e" : "#ef4444" }}>
                  {p.mean_ret >= 0 ? "+" : ""}{p.mean_ret?.toFixed(2)}%
                </span>
                <span style={{ fontSize: 10, color: "#475569",
                  marginLeft: "auto" }}>★{p.score?.toFixed(1)}</span>
              </div>
            );
          })}
          <a href={"/patterns-v3?symbol=" + symbol}
            style={{ fontSize: 11, color: "#3b82f6", marginTop: 8, display: "block" }}>
            View all patterns for {symbol} →
          </a>
        </div>
      )}
    </div>
  );
}
'''
            # Add React import if missing
            if "import React" not in src:
                src = src.replace('"use client";',
                                  '"use client";\n\nimport React from "react";')

            # Insert component before export default
            src = src.replace("export default function",
                              SEASONAL_COMPONENT + "\nexport default function")

            # Inject <SeasonalPatterns symbol={symbol} /> near bottom of return
            # Find a good insertion point - near the end of the main content
            if "SeasonalPatterns" not in src:
                # Try to add before the closing div of the page
                import re
                # Find last </div> before export and add before it
                src = re.sub(
                    r'(\s+</div>\s*\)\s*;\s*\}\s*$)',
                    '\n        <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 12, margin: "0 28px 20px" }}>\n'
                    '          <div style={{ padding: "12px 16px", borderBottom: "1px solid #334155" }}>\n'
                    '            <h2 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "#94a3b8", letterSpacing: 0.8 }}>🔬 SEASONAL PATTERNS</h2>\n'
                    '          </div>\n'
                    '          <SeasonalPatterns symbol={symbol} />\n'
                    '        </div>\n'
                    r'\1',
                    src
                )

            stocks_page.write_text(src, encoding="utf-8")
            print("  [OK] Added SeasonalPatterns section to stocks page")
    else:
        print("  [SKIP] Stocks page already has patterns section")


print("""
=============================================================
BUILD PHASE 23 COMPLETE
=============================================================

ROOT CAUSE FOUND & FIXED:
  AXISBANK parquet = AXISBANK_2026.parquet (35 rows, 2026 only!)
  Parquet files = delivery data for current year ONLY
  Historical OHLCV = stock_data SQLite table (back to ~2000)

  Fixed: build_seasonality_v3_stocks.py now reads from stock_data
  with query: WHERE symbol=? AND close IS NOT NULL AND close > 0
  Min 1250 rows (5yr history) required per symbol

[1] build_seasonality_v3_stocks.py -- REWRITTEN
    Source: stock_data SQLite (full history)
    Features: same as v3 (58 windows, all anchors, all metrics)
    Checkpoint: every 100 symbols -> resume if crashed

[2] /api/patterns-v3/detail/route.ts  -- NaN-safe

[3] /stocks/[symbol]/page.tsx
    Added SeasonalPatterns section at bottom:
    - Upcoming patterns (next 30 days) in yellow
    - Top all-time patterns sorted by score
    - Link to /patterns-v3?symbol=SYMBOL

TEST NOW:
  py D:\\MICC\\build_seasonality_v3_stocks.py --sym AXISBANK

  Should show patterns! If it does, START THE OVERNIGHT BUILD:
  py D:\\MICC\\build_seasonality_v3_stocks.py

  Expected: ~2600 symbols, 20-30 min per 100 symbols
  Total time estimate: 8-15 hours
  Auto-checkpoints every 100 symbols
  Resume anytime: py D:\\MICC\\build_seasonality_v3_stocks.py --resume

PARALLEL (while build runs):
  cd D:\\MICC\\micc-dashboard && npm run dev
  localhost:3000/patterns-v3  -- search NIFTY50, SPX, Gold etc. (working)
  localhost:3000/macro        -- yield curve + global rates
  localhost:3000/global       -- 52 global indices
=============================================================
""")
