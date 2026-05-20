"""
morning_brief.py  --  Run from D:\MICC at 9:00 AM
Generates and sends the full MICC morning brief to Telegram.

Fixes applied (May 18 2026):
  - Global snapshot symbols corrected (VIX, IndiaVIX, not SP500VIX/INDIAVIX)
  - Added fusion agent section
  - Added conviction top picks
  - Telegram retry on failure

Run: python D:\MICC\morning_brief.py
Schedule: Windows Task Scheduler at 09:00 on weekdays
"""

import subprocess, sys, sqlite3, json
from datetime import datetime
from pathlib import Path

DA   = Path(r"D:\MICC")
DB_P = r"D:\marketDB\db\market.db"
PY   = sys.executable

def ts(): return datetime.now().strftime("%H:%M:%S")
def log(msg): print(f"  [{ts()}] {msg}", flush=True)


def run_agent(script, timeout=120):
    try:
        r = subprocess.run([PY, str(DA / script)], cwd=str(DA),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except Exception as e:
        log(f"  {script}: {e}")
        return False


def send(msg):
    try:
        from micc_data import send_telegram_chunks
        return send_telegram_chunks(msg)
    except Exception as e:
        log(f"send failed: {e}")
        return False


def get_todays_patterns(n=10, min_score=5):
    mmdd = datetime.today().strftime("%m-%d")
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        tbl = "seasonality_patterns_v3" if "seasonality_patterns_v3" in tables else "seasonality_patterns"

        # Use FDR-corrected score_v2 if available
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
        if "score_v2" in cols and "fdr_reject" in cols:
            rows = conn.execute(
                f"SELECT symbol, window_days, direction, accuracy, mean_ret, score_v2"
                f" FROM {tbl}"
                f" WHERE anchor_mm_dd=? AND fdr_reject=1 AND score_v2>1.0"
                f" AND ABS(mean_ret)<=50"
                f" ORDER BY score_v2 DESC LIMIT ?",
                (mmdd, n)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT symbol, window_days, direction, accuracy, mean_ret, score"
                f" FROM {tbl}"
                f" WHERE anchor_mm_dd=? AND accuracy>=65"
                f" AND score>=? AND ABS(mean_ret)<=50"
                f" ORDER BY score DESC LIMIT ?",
                (mmdd, min_score, n)
            ).fetchall()
        conn.close()
        return mmdd, rows
    except Exception as e:
        log(f"patterns error: {e}")
        return mmdd, []


def get_global_snapshot():
    # These are the EXACT symbol names stored in global_indices_daily
    # (from phase9a_fetch_global_indices.py GLOBAL_TICKERS dict keys)
    WATCH = ["NIFTY50", "SPX", "VIX", "IndiaVIX", "US10Y", "Gold", "CrudeWTI", "USDINR", "Bitcoin"]
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        placeholders = ",".join("?" * len(WATCH))
        rows = conn.execute(
            f"SELECT symbol, close, pct_change FROM global_indices_daily"
            f" WHERE symbol IN ({placeholders})"
            f" AND date = (SELECT MAX(date) FROM global_indices_daily"
            f"             WHERE symbol = global_indices_daily.symbol)",
            WATCH
        ).fetchall()
        conn.close()
        # Preserve WATCH order for consistent brief layout
        data = {r[0]: (r[1], r[2]) for r in rows}
        result = {sym: data[sym] for sym in WATCH if sym in data}
        if not result:
            log(f"global_snapshot: got 0 rows. DB symbols may differ from WATCH list.")
        else:
            log(f"global_snapshot: {len(result)}/{len(WATCH)} symbols found")
        return result
    except Exception as e:
        log(f"global_snapshot error: {e}")
        return {}


def get_fusion_picks(n=5):
    """Load fusion agent top picks."""
    try:
        fused_path = DA / "agents" / "fusion" / "fused_picks.json"
        if not fused_path.exists():
            return []
        picks = json.loads(fused_path.read_text())
        return picks[:n]
    except Exception:
        return []


def get_conviction_top(n=5):
    """Top conviction symbols from DB."""
    try:
        conn = sqlite3.connect(DB_P, timeout=10)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "symbol_conviction" not in tables:
            conn.close()
            return []
        rows = conn.execute(
            "SELECT symbol, conviction_score FROM symbol_conviction"
            " ORDER BY conviction_score DESC LIMIT ?",
            (n,)
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def main():
    today = datetime.today().strftime("%A, %d %b %Y")
    print(f"\nMICC Morning Brief -- {today}")
    print("="*50)

    # 1. Run key agents (fusion first — reads all other agents' last_report.json)
    log("Running agents...")
    for script in ["agent_fusion.py", "agent_eta.py", "agent_alert.py"]:
        ok = run_agent(script)
        log(f"  {script}: {'OK' if ok else 'FAILED'}")

    # 2. Build message
    lines = [
        f"*MICC Morning Brief -- {today}*",
        "",
    ]

    # Global snapshot
    snap = get_global_snapshot()
    if snap:
        lines.append("*Global Markets:*")
        LABELS = {
            "NIFTY50":  "Nifty 50 ",
            "SPX":      "S&P 500  ",
            "VIX":      "VIX      ",
            "IndiaVIX": "India VIX",
            "US10Y":    "US 10Y   ",
            "Gold":     "Gold     ",
            "CrudeWTI": "Crude WTI",
            "USDINR":   "USD/INR  ",
            "Bitcoin":  "Bitcoin  ",
        }
        for sym, (close, chg) in snap.items():
            if close is None:
                continue
            label = LABELS.get(sym, sym)
            ico   = "UP" if (chg or 0) > 0.3 else "DN" if (chg or 0) < -0.3 else "--"
            chg_s = f"{chg:+.2f}%" if chg is not None else ""
            lines.append(f"  {ico} `{label}` {close:.2f}  {chg_s}")
        lines.append("")
    else:
        lines.append("_Global markets: no data_")
        lines.append("")

    # Fusion top picks (cross-agent signals)
    fusion = get_fusion_picks(n=5)
    if fusion:
        lines.append("*Fusion Signals (multi-agent overlap):*")
        for p in fusion:
            sym = p["symbol"]
            fs  = p["fusion_score"]
            nl  = p["n_layers"]
            # Build tag string
            tags = []
            lyr  = p.get("layers", {})
            if lyr.get("beta_pick"):   tags.append("B")
            if lyr.get("insider"):     tags.append("I")
            if lyr.get("watchlist"):   tags.append("W")
            if lyr.get("seasonal"):    tags.append("S")
            if lyr.get("conviction"):  tags.append("C")
            if lyr.get("iota"):        tags.append("Q")
            tag_str = "+".join(tags)
            lines.append(f"  `{sym:<14}` {fs:>3}pts  [{tag_str}]")
        lines.append("_B=Beta I=Insider W=Watch S=Season C=Conv Q=Quant_")
        lines.append("")

    # Today's patterns
    mmdd, pats = get_todays_patterns(n=6, min_score=5)
    if pats:
        lines.append(f"*Seasonal Patterns ({mmdd}):*")
        for sym, win, dirn, acc, mean, score in pats:
            ico = "UP" if dirn == "UP" else "DN"
            lines.append(
                f"  {ico} `{sym:<14}` {win}d  {acc:.0f}%  {mean:+.2f}%  s={score:.2f}"
            )
        lines.append("")
    else:
        lines.append(f"_No high-score patterns for {mmdd}_")
        lines.append("")

    # Eta highlights
    try:
        eta_path = DA / "agents" / "eta" / "last_report.json"
        if eta_path.exists():
            eta = json.loads(eta_path.read_text())
            clusters = eta.get("insider_cluster", [])[:3]
            if clusters:
                lines.append("*Insider Clusters:*")
                for c in clusters:
                    lines.append(
                        f"  `{c['symbol']}` {c['buy_count']} insiders"
                        f" Rs.{c.get('total_value_cr', 0):.1f}Cr"
                    )
                lines.append("")
    except Exception:
        pass

    # Conviction top picks
    conv = get_conviction_top(n=4)
    if conv:
        lines.append("*High Conviction:*")
        for sym, score in conv:
            lines.append(f"  `{sym:<14}` {score:.0f}/100")
        lines.append("")

    # Alert summary
    try:
        alert_path = DA / "agents" / "alert" / "last_report.json"
        if alert_path.exists():
            ar = json.loads(alert_path.read_text())
            fired = ar.get("alerts_fired", 0)
            if fired:
                lines.append(f"*Alerts Fired: {fired}*")
                for f in ar.get("fired", [])[:3]:
                    lines.append(f"  {f.get('message', '')[:60]}")
                lines.append("")
    except Exception:
        pass

    lines.append("_MICC v3 | localhost:3000_")

    msg = "\n".join(lines)
    print("\n" + msg[:1200] + ("..." if len(msg) > 1200 else ""))
    ok = send(msg)
    log(f"Telegram: {'SENT' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
