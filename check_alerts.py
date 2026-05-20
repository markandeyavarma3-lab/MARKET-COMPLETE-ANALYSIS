import json, sqlite3, sys
from pathlib import Path
from datetime import datetime

DA      = Path(r"D:\MICC")
DB      = r"D:\marketDB\db\market.db"
WL_PATH = DA / "micc_watchlists.json"


def qdb(sql, params=()):
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, list(params)).fetchall()]
    conn.close()
    return rows


def load_watchlists():
    if not WL_PATH.exists():
        return {"lists": []}
    return json.loads(WL_PATH.read_text(encoding="utf-8"))


def check_alerts():
    wl = load_watchlists()
    all_syms = list({s for lst in wl["lists"] for s in lst.get("symbols", [])})
    if not all_syms:
        print("No symbols in any watchlist.")
        return

    ph = ",".join(["?"] * len(all_syms))

    sql_p = (
        "SELECT p.symbol, p.close, p.date, p.volume "
        "FROM stock_data p "
        "INNER JOIN (SELECT symbol, MAX(date) md FROM stock_data "
        "WHERE symbol IN (" + ph + ") GROUP BY symbol) lx "
        "ON p.symbol=lx.symbol AND p.date=lx.md"
    )
    prices = {r["symbol"]: r for r in qdb(sql_p, all_syms)}

    sql_t = (
        "SELECT t.symbol, t.rsi_14, t.vol_surge_20d, t.pct_above_sma20, "
        "t.macd_line, t.macd_signal "
        "FROM symbol_technicals t "
        "INNER JOIN (SELECT symbol, MAX(as_of_date) md FROM symbol_technicals "
        "WHERE symbol IN (" + ph + ") GROUP BY symbol) lx "
        "ON t.symbol=lx.symbol AND t.as_of_date=lx.md"
    )
    tech = {r["symbol"]: r for r in qdb(sql_t, all_syms)}

    triggered = []
    for lst in wl["lists"]:
        for alert in lst.get("alerts", []):
            sym   = alert["symbol"]
            atype = alert["type"]
            p     = prices.get(sym, {})
            t     = tech.get(sym, {})
            close = p.get("close", 0) or 0
            vol_s = t.get("vol_surge_20d", 0) or 0
            rsi   = t.get("rsi_14", 50) or 50
            vs20  = t.get("pct_above_sma20", 0) or 0
            v     = alert.get("value") or 0
            lo    = alert.get("low") or 0
            hi    = alert.get("high") or 1e9

            hit = False
            reason = ""
            if   atype == "price_above"  and close >= v:       hit = True; reason = f"Price {close:.2f} above {v}"
            elif atype == "price_below"  and close <= v:       hit = True; reason = f"Price {close:.2f} below {v}"
            elif atype == "price_band"   and lo <= close <= hi: hit = True; reason = f"Price {close:.2f} in band {lo}-{hi}"
            elif atype == "pct_move_up"  and close > 0:
                # pct_1d not in prices here, skip gracefully
                pass
            elif atype == "volume_surge" and vol_s >= v:       hit = True; reason = f"Vol surge {vol_s:.1f}x >= {v}x"
            elif atype == "rsi_above"    and rsi >= v:         hit = True; reason = f"RSI {rsi:.1f} above {v}"
            elif atype == "rsi_below"    and rsi <= v:         hit = True; reason = f"RSI {rsi:.1f} below {v}"
            elif atype == "above_sma20"  and vs20 > 0:         hit = True; reason = f"Price {vs20:+.2f}% above SMA20"
            elif atype == "below_sma20"  and vs20 < 0:         hit = True; reason = f"Price {vs20:+.2f}% below SMA20"

            if hit:
                triggered.append({
                    "list":   lst["name"],
                    "symbol": sym,
                    "type":   atype,
                    "reason": reason,
                    "note":   alert.get("note", ""),
                })

    if not triggered:
        print(f"[{datetime.now():%H:%M}] No alerts triggered.")
        return

    print(f"\n[{datetime.now():%H:%M}] TRIGGERED ALERTS: {len(triggered)}")
    msg_lines = [
        "*MICC Watchlist Alerts*",
        f"{datetime.now():%Y-%m-%d %H:%M} IST",
        "",
    ]
    for t in triggered:
        print(f"  [{t['list']}] {t['symbol']}: {t['reason']}")
        msg_lines.append(f"*{t['symbol']}* [{t['list']}]")
        msg_lines.append(f"  {t['reason']}")
        if t["note"]:
            msg_lines.append(f"  Note: {t['note']}")
        msg_lines.append("")

    try:
        sys.path.insert(0, str(DA))
        from micc_data import send_telegram_chunks
        send_telegram_chunks(["\n".join(msg_lines)])
        print("Sent to Telegram.")
    except Exception as e:
        print(f"Telegram send failed: {e}")
        print("\n".join(msg_lines))


if __name__ == "__main__":
    check_alerts()
