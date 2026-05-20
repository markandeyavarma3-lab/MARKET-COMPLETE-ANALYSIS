"""
fix_alert_dedup.py
==================
Fixes alert deduplication in agent_alert.py.
Currently the same alert fires every day if condition persists.
Fix: add last_fired/cooldown_days logic to alerts.json + agent_alert.py.

Run: py fix_alert_dedup.py
"""
from pathlib import Path
import json, re

MICC       = Path(r"D:\MICC")
ALERTS_JSON = MICC / "alerts.json"
AGENT_FILE  = MICC / "agent_alert.py"

# Step 1: Add last_fired field to all alerts in alerts.json
if ALERTS_JSON.exists():
    alerts = json.loads(ALERTS_JSON.read_text())
    changed = 0
    items = alerts if isinstance(alerts, list) else alerts.get("alerts", [])
    for a in items:
        if "last_fired" not in a:
            a["last_fired"] = None
            changed += 1
        if "cooldown_days" not in a:
            a["cooldown_days"] = 1  # default: don't fire same alert 2 days running
            changed += 1
    if changed:
        ALERTS_JSON.write_text(json.dumps(alerts, indent=2))
        print(f"[OK] alerts.json: added last_fired + cooldown_days to {changed//2} alerts")
    else:
        print("[SKIP] alerts.json already has last_fired field")
else:
    print(f"[WARN] alerts.json not found at {ALERTS_JSON}")

# Step 2: Patch agent_alert.py to check last_fired before firing
if not AGENT_FILE.exists():
    print(f"[SKIP] agent_alert.py not found")
else:
    src = AGENT_FILE.read_text(encoding="utf-8")

    # Check if already patched
    if "last_fired" in src and "cooldown_days" in src:
        print("[SKIP] agent_alert.py already has dedup logic")
    else:
        # Find the fire_alert / send_alert call and wrap it
        # Inject helper function at top of file (after imports)
        DEDUP_HELPER = '''

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

'''
        # Insert after last import line
        import_end = 0
        for i, line in enumerate(src.splitlines()):
            if line.startswith("import ") or line.startswith("from "):
                import_end = i
        lines = src.splitlines()
        lines.insert(import_end + 1, DEDUP_HELPER)
        patched = "\n".join(lines)
        AGENT_FILE.write_text(patched, encoding="utf-8")
        print("[OK] agent_alert.py: injected _should_fire() + _mark_fired() helpers")
        print("[INFO] You still need to call _should_fire(alert) before each send_telegram()")
        print("       and _mark_fired(alert, ALERTS_PATH) after each fire.")
        print("       Or use the wrapper below in your check loop:")
        print()
        print('''  # In your alert check loop:
  for alert in alerts:
      if condition_met and _should_fire(alert):
          send_telegram(message)
          _mark_fired(alert, str(ALERTS_JSON))
''')
