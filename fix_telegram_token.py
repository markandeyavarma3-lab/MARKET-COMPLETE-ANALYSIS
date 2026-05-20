"""
fix_telegram_token.py
Directly patches the hardcoded fallback token in micc_data.py.
Run: py fix_telegram_token.py
"""
from pathlib import Path

MICC = Path(r"D:\MICC")
f    = MICC / "micc_data.py"

if not f.exists():
    print("ERROR: micc_data.py not found"); exit(1)

src = f.read_text(encoding="utf-8")

OLD_TOKEN = "8420620581:AAGz9ztaCkj8KUJ5etBOaB0vmH69vHpeMRI"
NEW_TOKEN = "8420620581:AAGFtYxNodQ6nAR7kJVS_jAGti2IVPooFMU"
OLD_GROQ  = "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"
NEW_GROQ  = "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"

changed = 0
if OLD_TOKEN in src:
    src = src.replace(OLD_TOKEN, NEW_TOKEN)
    changed += 1
    print(f"[OK] Telegram token replaced in micc_data.py")
else:
    print(f"[INFO] Old Telegram token not found (already patched or different)")

if OLD_GROQ in src:
    src = src.replace(OLD_GROQ, NEW_GROQ)
    changed += 1
    print(f"[OK] Groq key replaced in micc_data.py")
else:
    print(f"[INFO] Old Groq key not found (already patched or different)")

if changed:
    f.write_text(src, encoding="utf-8")
    print(f"\n[OK] micc_data.py saved with new tokens")
else:
    print(f"\n[WARN] Nothing changed — check micc_data.py manually")
    # Show current token lines
    for i, line in enumerate(src.splitlines()):
        if "TELEGRAM_BOT_TOKEN" in line or "GROQ_API_KEY" in line:
            print(f"  Line {i+1}: {line.strip()}")

# Quick test
print("\nTesting Telegram...")
import sys
sys.path.insert(0, str(MICC))
# Force reload
import importlib
try:
    import micc_data
    importlib.reload(micc_data)
    ok = micc_data.send_telegram("MICC: Token rotation confirmed. System operational.")
    print(f"  Telegram: {'SENT OK' if ok else 'STILL FAILING'}")
except Exception as e:
    print(f"  Error: {e}")
