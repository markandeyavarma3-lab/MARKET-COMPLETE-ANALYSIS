"""
rotate_tokens.py — prints exact steps to rotate Groq + Telegram tokens.
Run: py rotate_tokens.py
"""
print("""
=== ROTATE TOKENS NOW (10 minutes) ===

STEP 1 — Groq API key:
  1. Go to: https://console.groq.com/keys
  2. Delete the old key (starts with gsk_dLS...)
  3. Create new key, copy it
  4. Open D:\MICC\.env
  5. Replace GROQ_API_KEY=gsk_dLS... with the new value

STEP 2 — Telegram bot token:
  1. Open Telegram, search @BotFather
  2. Send: /mybots
  3. Select your bot
  4. Choose: API Token → Revoke current token → Yes
  5. Copy the new token
  6. Open D:\MICC\.env
  7. Replace TELEGRAM_BOT_TOKEN=8420620581:... with the new value

STEP 3 — Test:
  py D:\MICC\morning_brief.py

Done. Old tokens are now dead. New tokens are in .env only.
""")
