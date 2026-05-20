# -*- coding: utf-8 -*-
"""
MICC Agent Alert -- Price + Pattern + Watchlist Alerts
=======================================================
Alert types:
  PRICE_ABOVE    symbol price > target
  PRICE_BELOW    symbol price < target
  PCT_MOVE       price moved > X% in last N days
  VOLUME_SURGE   volume > X * 20d average
  PATTERN_HIT    seasonal pattern active today (accuracy >= target)
  RSI_ABOVE      RSI(14) > threshold (overbought)
  RSI_BELOW      RSI(14) < threshold (oversold)

Alerts stored in: D:/MICC/alerts.json

Run:
  py D:/MICC/agent_alert.py          -- check all + Telegram if fired
  py D:/MICC/agent_alert.py --send   -- always send summary
  py D:/MICC/agent_alert.py --list   -- list all alerts
  py D:/MICC/agent_alert.py --add PRICE_ABOVE RELIANCE 2800 "note"
"""

import argparse, json, sqlite3, sys, uuid
from datetime import datetime
from pathlib import Path

from micc_data import send_telegram_chunks, now_ist


def _should_fire(alert: dict) -> bool:
    """Return True only if alert hasn't fired recently (respects cooldown_days)."""
    from datetime import date, timedelta
    last = alert.get("last_fired")
    cooldown = int(alert.get("cooldown_days", 1))
    if last is None:
        return True
    try:
        last_date = date.fromisoformat(str(last))
        return date.today() >= last_date + timedelta(days=cooldown)
    except Exception:
        return True

def _mark_fired(alert: dict, alerts_path: str):
    """Update last_fired date in alerts.json."""
    import json as _json
    from datetime import date as _date
    alert["last_fired"] = str(_date.today())
    try:
        with open(alerts_path) as f:
            data = _json.load(f)
        items = data if isinstance(data, list) else data.get("alerts", [])
        for item in items:
            if item.get("id") == alert.get("id") or (
                item.get("type") == alert.get("type") and
                item.get("symbol") == alert.get("symbol")
            ):
                item["last_fired"] = alert["last_fired"]
                item["cooldown_days"] = alert.get("cooldown_days", 1)
        with open(alerts_path, "w") as f:
            _json.dump(data, f, indent=2)
    except Exception as e:
        pass



DB          = Path(r"D:\marketDB\db\market.db")
DA          = Path(r"D:\MICC")
ALERTS_FILE = DA / "alerts.json"
OUTPUT_DIR  = DA / "agents" / "alert"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY      = datetime.today().strftime("%Y-%m-%d")
TODAY_MMDD = datetime.today().strftime("%m-%d")


def log(msg, level="INFO"):
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] [{tag}]  {msg}", flush=True)


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #

def _conn():
    return sqlite3.connect(DB, timeout=10)

def get_latest_price(symbol: str):
    try:
        c = _conn()
        r = c.execute(
            "SELECT close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        c.close()
        return float(r[0]) if r else None
    except Exception:
        return None

def get_latest_volume(symbol: str):
    try:
        c = _conn()
        rows = c.execute(
            "SELECT volume FROM stock_data WHERE symbol=? AND volume IS NOT NULL ORDER BY date DESC LIMIT 21",
            (symbol.upper(),)
        ).fetchall()
        c.close()
        if not rows:
            return None, None
        vols = [float(r[0]) for r in rows]
        return vols[0], sum(vols[1:]) / max(len(vols) - 1, 1)
    except Exception:
        return None, None

def get_pct_move(symbol: str, days: int):
    try:
        c = _conn()
        rows = c.execute(
            "SELECT close FROM stock_data WHERE symbol=? AND close IS NOT NULL ORDER BY date DESC LIMIT ?",
            (symbol.upper(), days + 1)
        ).fetchall()
        c.close()
        if len(rows) < 2:
            return None
        return (float(rows[0][0]) / float(rows[-1][0]) - 1) * 100
    except Exception:
        return None

def get_rsi(symbol: str):
    try:
        c = _conn()
        r = c.execute(
            "SELECT rsi_14 FROM symbol_technicals WHERE symbol=? ORDER BY as_of_date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        c.close()
        return float(r[0]) if r and r[0] is not None else None
    except Exception:
        return None

def get_todays_patterns(min_accuracy=68.0, min_score=1.5):
    try:
        c = _conn()
        tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        tbl = "seasonality_patterns_v3" if "seasonality_patterns_v3" in tables else "seasonality_patterns"
        rows = c.execute(
            "SELECT symbol, window_days, direction, accuracy, mean_ret, score "
            "FROM " + tbl + " WHERE anchor_mm_dd=? AND accuracy>=? AND score>=? "
            "ORDER BY score DESC LIMIT 20",
            (TODAY_MMDD, min_accuracy, min_score)
        ).fetchall()
        c.close()
        return [{"symbol": r[0], "window": r[1], "direction": r[2],
                 "accuracy": r[3], "mean_ret": r[4], "score": r[5]} for r in rows]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Alert file I/O
# --------------------------------------------------------------------------- #

def load_alerts():
    if not ALERTS_FILE.exists():
        return []
    try:
        return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_alerts(alerts):
    ALERTS_FILE.write_text(json.dumps(alerts, indent=2, default=str), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Check one alert
# --------------------------------------------------------------------------- #

def check_alert(alert: dict):
    sym    = alert.get("symbol", "").upper()
    typ    = alert.get("type", "")
    target = float(alert.get("target", 0))
    note   = alert.get("note", "")
    days   = int(alert.get("days", 5))
    suffix = ("  [" + note + "]") if note else ""

    if typ == "PRICE_ABOVE":
        price = get_latest_price(sym)
        if price and price > target:
            return True, f"PRICE ABOVE: {sym} @ {price:.2f} > {target:.2f}{suffix}"

    elif typ == "PRICE_BELOW":
        price = get_latest_price(sym)
        if price and price < target:
            return True, f"PRICE BELOW: {sym} @ {price:.2f} < {target:.2f}{suffix}"

    elif typ == "PCT_MOVE":
        move = get_pct_move(sym, days)
        if move is not None and abs(move) >= target:
            return True, f"PCT MOVE: {sym} {move:+.1f}% in {days}d (threshold {target:.1f}%){suffix}"

    elif typ == "VOLUME_SURGE":
        vol, avg = get_latest_volume(sym)
        if vol and avg and avg > 0:
            ratio = vol / avg
            if ratio >= target:
                return True, f"VOL SURGE: {sym} {ratio:.1f}x 20d avg (threshold {target:.1f}x){suffix}"

    elif typ == "RSI_ABOVE":
        rsi = get_rsi(sym)
        if rsi is not None and rsi > target:
            return True, f"RSI OVERBOUGHT: {sym} RSI={rsi:.1f} > {target:.0f}{suffix}"

    elif typ == "RSI_BELOW":
        rsi = get_rsi(sym)
        if rsi is not None and rsi < target:
            return True, f"RSI OVERSOLD: {sym} RSI={rsi:.1f} < {target:.0f}{suffix}"

    elif typ == "PATTERN_HIT":
        patterns = get_todays_patterns(min_accuracy=target, min_score=1.0)
        hits = [p for p in patterns if p["symbol"].upper() == sym]
        if hits:
            p = hits[0]
            return True, (f"PATTERN: {sym} {p['direction']} {p['window']}d  "
                          f"acc={p['accuracy']:.0f}%  mean={p['mean_ret']:+.2f}%{suffix}")

    return False, ""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def run_alerts(send: bool = False):
    print("=" * 55)
    print("  AGENT ALERT -- Price + Pattern + Watchlist")
    print("=" * 55)

    alerts = load_alerts()
    log(f"Loaded {len(alerts)} alerts")

    fired = []
    for alert in alerts:
        if not alert.get("active", True):
            continue
        triggered, msg = check_alert(alert)
        if triggered:
            alert["triggered_at"] = now_ist()
            alert["last_message"] = msg
            if alert.get("one_shot", True):
                alert["active"] = False
            fired.append((alert, msg))
            log(f"FIRED: {msg}", "OK")

    save_alerts(alerts)

    patterns = get_todays_patterns(min_accuracy=70.0, min_score=2.0)
    log(f"Patterns today ({TODAY_MMDD}): {len(patterns)}")

    report = {
        "date": TODAY, "generated_at": now_ist(),
        "alerts_checked": len(alerts), "alerts_fired": len(fired),
        "fired": [{"alert": a, "message": m} for a, m in fired],
        "patterns_today": patterns,
    }
    out = OUTPUT_DIR / "last_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log(f"Saved: {out}")

    print(f"\n  Alerts checked: {len(alerts)}")
    print(f"  Alerts fired:   {len(fired)}")
    print(f"  Patterns today: {len(patterns)}")
    print("=" * 55)

    if send and (fired or patterns):
        lines = [f"*MICC Alerts -- {TODAY}*", ""]
        if fired:
            lines.append("*TRIGGERED:*")
            for _, msg in fired:
                lines.append(f"  {msg}")
            lines.append("")
        if patterns:
            lines.append(f"*PATTERNS TODAY ({TODAY_MMDD}):*")
            for p in patterns[:8]:
                ico = "UP" if p["direction"] == "UP" else "DN"
                lines.append(
                    f"  {ico} `{p['symbol']:<14}` {p['window']}d  "
                    f"{p['accuracy']:.0f}%  {p['mean_ret']:+.2f}%  s={p['score']:.1f}"
                )
        ok = send_telegram_chunks("\n".join(lines))
        log(f"Telegram: {'OK' if ok else 'FAILED'}")

    return report


def add_alert(type_: str, symbol: str, target: float,
              note: str = "", days: int = 5, one_shot: bool = True):
    alerts = load_alerts()
    alerts.append({
        "id": str(uuid.uuid4())[:8], "type": type_.upper(),
        "symbol": symbol.upper(), "target": target,
        "note": note, "days": days, "one_shot": one_shot,
        "active": True, "created_at": now_ist(),
        "triggered_at": None, "last_message": None,
    })
    save_alerts(alerts)
    log(f"Added: {type_.upper()} {symbol.upper()} target={target} note={note!r}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--add",  nargs="+", help="TYPE SYMBOL TARGET [NOTE]")
    args = ap.parse_args()

    if args.list:
        for a in load_alerts():
            st = "ACTIVE" if a.get("active") else "FIRED"
            print(f"  [{st}] {a['type']:<15} {a['symbol']:<14} target={a['target']}  {a.get('note','')}")
        sys.exit(0)

    if args.add:
        if len(args.add) < 3:
            print("Usage: --add TYPE SYMBOL TARGET [NOTE]"); sys.exit(1)
        add_alert(args.add[0], args.add[1], float(args.add[2]),
                  note=" ".join(args.add[3:]) if len(args.add) > 3 else "")
        sys.exit(0)

    run_alerts(send=args.send)