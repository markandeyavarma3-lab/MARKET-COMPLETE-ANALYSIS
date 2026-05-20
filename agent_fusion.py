import json, sys, sqlite3
from pathlib import Path
from datetime import datetime

DA         = Path(r"D:\MICC")
DB_PATH    = r"D:\marketDB\db\market.db"
OUTPUT_DIR = DA / "agents" / "fusion"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
send = "--send" in sys.argv

def now_ist():
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M IST")

def read_report(name):
    p = DA / "agents" / name / "last_report.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def qdb(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  [DB ERR] {e}")
        return []

def extract_symbols(report, label):
    out = []
    if not report:
        return out
    for key, val in report.items():
        if not isinstance(val, list):
            continue
        for item in val:
            if not isinstance(item, dict):
                continue
            raw = item.get("symbol") or item.get("ticker") or ""
            sym = str(raw).strip().upper()
            if not sym:
                continue
            if len(sym) < 2 or len(sym) > 20:
                continue
            clean = sym.replace("-", "").replace("&", "")
            if not clean.isalnum():
                continue
            reason = (
                item.get("reason") or item.get("signal") or
                item.get("note")   or item.get("screen") or label
            )
            out.append((sym, str(reason)))
    return out

AGENTS = [
    ("alpha",   "Macro/Regime"),
    ("beta",    "Momentum"),
    ("gamma",   "Options/GEX"),
    ("delta",   "Sectors"),
    ("epsilon", "FII/DII"),
    ("zeta",    "Watchlist"),
    ("eta",     "Insider/Corp"),
    ("iota",    "Global Intel"),
]

print("Fusion agent starting...")

sym_layers   = {}
sym_reasons  = {}
agent_status = {}

for agent_key, label in AGENTS:
    report = read_report(agent_key)
    pairs  = extract_symbols(report, label)
    seen   = set()
    for sym, reason in pairs:
        if sym in seen:
            continue
        seen.add(sym)
        sym_layers.setdefault(sym, []).append(agent_key)
        sym_reasons.setdefault(sym, []).append("[" + agent_key + "] " + reason)
    agent_status[agent_key] = len(seen)
    print("  " + agent_key.ljust(10) + " -> " + str(len(seen)) + " symbols")

# signals_history
sigs = qdb(
    "SELECT symbol, screen_tags FROM signals_history "
    "WHERE run_date=(SELECT MAX(run_date) FROM signals_history)"
)
for s in sigs:
    sym = (s.get("symbol") or "").strip().upper()
    if sym:
        sym_layers.setdefault(sym, []).append("engine")
        tags = s.get("screen_tags") or "signal"
        sym_reasons.setdefault(sym, []).append("[engine] " + tags)
print("  engine     -> " + str(len(sigs)) + " symbols")

# watchlist
wl_file = DA / "micc_watchlist.json"
if wl_file.exists():
    try:
        wl = json.loads(wl_file.read_text(encoding="utf-8"))
        wl_syms = wl.get("symbols", [])
        for item in wl_syms:
            if isinstance(item, str):
                sym = item.strip().upper()
            elif isinstance(item, dict):
                sym = (item.get("symbol") or "").strip().upper()
            else:
                sym = ""
            if sym:
                sym_layers.setdefault(sym, []).append("watchlist")
                sym_reasons.setdefault(sym, []).append("[watchlist] manually tracked")
        print("  watchlist  -> " + str(len(wl_syms)) + " symbols")
    except Exception:
        pass

# Build picks (2+ layers)
picks = []
for sym, layers in sym_layers.items():
    unique = list(dict.fromkeys(layers))
    n = len(unique)
    if n < 2:
        continue
    picks.append({
        "symbol":           sym,
        "total_score":      float(n),
        "n_layers":         n,
        "layers_fired":     unique,
        "reasons":          sym_reasons.get(sym, []),
        "beta_score":       1.0 if "beta"    in layers else 0.0,
        "regime_score":     1.0 if "alpha"   in layers else 0.0,
        "insider_score":    1.0 if "eta"     in layers else 0.0,
        "watchlist_score":  1.0 if "zeta" in layers or "watchlist" in layers else 0.0,
        "seasonal_score":   1.0 if "engine"  in layers else 0.0,
        "conviction_score": 1.0 if "epsilon" in layers else 0.0,
        "quant_score":      1.0 if "gamma" in layers or "delta" in layers or "iota" in layers else 0.0,
    })

picks.sort(key=lambda x: -x["total_score"])
print("\n  Fusion picks (2+ layers): " + str(len(picks)))
for p in picks[:10]:
    print("    " + p["symbol"].ljust(15) + " n=" + str(p["n_layers"]) + "  " + str(p["layers_fired"]))

# Regime
nr = qdb(
    "SELECT closing_index_value AS close FROM market_snapshot "
    "WHERE index_name='NIFTY 50' ORDER BY date DESC LIMIT 1"
)
nifty  = float(nr[0]["close"]) if nr else 0.0
regime = "BULLISH" if nifty > 22000 else "SIDEWAYS" if nifty > 18000 else "BEARISH" if nifty > 0 else "UNKNOWN"

report = {
    "agent":        "fusion",
    "date":         datetime.now().strftime("%Y-%m-%d"),
    "generated_at": now_ist(),
    "picks":        picks,
    "meta": {
        "total_picks":  len(picks),
        "regime":       regime,
        "nifty":        round(nifty, 2),
        "agents_run":   sum(1 for v in agent_status.values() if v > 0),
        "agent_status": agent_status,
    },
}

out = OUTPUT_DIR / "last_report.json"
out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
print("  Saved: " + str(out))

if send:
    try:
        import re, urllib.request
        env  = (DA / ".env").read_text()
        BOT  = re.search(r"TELEGRAM_TOKEN=([^\n]+)", env).group(1).strip()
        CHAT = re.search(r"TELEGRAM_CHAT_ID=([^\n]+)", env).group(1).strip()
        msg_lines = [
            "FUSION PICKS - " + datetime.now().strftime("%d %b"),
            "",
            "Regime: " + regime + "  Nifty: " + f"{nifty:,.0f}",
            "Picks (2+ layers): " + str(len(picks)),
            "",
        ]
        for p in picks[:15]:
            tag = " ".join("[" + l[:3].upper() + "]" for l in p["layers_fired"])
            msg_lines.append(p["symbol"].ljust(12) + " " + str(p["n_layers"]) + "L  " + tag)
        msg  = "\n".join(msg_lines)
        data = json.dumps({"chat_id": CHAT, "text": msg}).encode()
        req  = urllib.request.Request(
            "https://api.telegram.org/bot" + BOT + "/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
        print("  Telegram: OK")
    except Exception as e:
        print("  Telegram: " + str(e))

print("Done.")
