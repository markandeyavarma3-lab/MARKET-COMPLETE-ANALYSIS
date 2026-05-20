"""
update_env_tokens.py
Updates .env with new Groq key and Telegram token.
Run: py update_env_tokens.py
"""
from pathlib import Path

ENV = Path(r"D:\MICC\.env")
if not ENV.exists():
    print("ERROR: .env not found at D:\\MICC\\.env")
    exit(1)

content = ENV.read_text(encoding="utf-8")

# Replace Groq key
old_groq = None
new_groq  = "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"
for line in content.splitlines():
    if line.startswith("GROQ_API_KEY="):
        old_groq = line.split("=",1)[1].strip()

# Replace Telegram token
old_tele = None
new_tele  = "8420620581:AAGFtYxNodQ6nAR7kJVS_jAGti2IVPooFMU"
for line in content.splitlines():
    if line.startswith("TELEGRAM_BOT_TOKEN="):
        old_tele = line.split("=",1)[1].strip()

if old_groq:
    content = content.replace(f"GROQ_API_KEY={old_groq}", f"GROQ_API_KEY={new_groq}")
    print(f"[OK] Groq key: {old_groq[:12]}... -> {new_groq[:12]}...")
else:
    # Append if missing
    content += f"\nGROQ_API_KEY={new_groq}"
    print(f"[OK] Groq key added")

if old_tele:
    content = content.replace(f"TELEGRAM_BOT_TOKEN={old_tele}", f"TELEGRAM_BOT_TOKEN={new_tele}")
    print(f"[OK] Telegram token: {old_tele[:15]}... -> {new_tele[:15]}...")
else:
    content += f"\nTELEGRAM_BOT_TOKEN={new_tele}"
    print(f"[OK] Telegram token added")

ENV.write_text(content, encoding="utf-8")
print(f"\n[OK] .env saved. Verifying...")

# Verify
final = ENV.read_text()
ok1 = new_groq in final
ok2 = new_tele in final
print(f"  Groq key present:     {'YES' if ok1 else 'NO - CHECK!'}")
print(f"  Telegram token present: {'YES' if ok2 else 'NO - CHECK!'}")

if ok1 and ok2:
    print("\n  Tokens rotated. Test with: py D:\\MICC\\morning_brief.py")
