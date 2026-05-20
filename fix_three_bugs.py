"""
fix_three_bugs.py  --  Run from D:\MICC
Fixes 3 bugs found on May 13 2026:

  Bug 1: [options] Bridge error: no such column: volume
          -> options route.ts SQL references bare `volume` but the JOIN with
             option_greeks_raw (which has NO volume col) makes it ambiguous.
             Must be `f.volume` (fo_data alias).

  Bug 2: MarkdownText TypeError: text.trim is not a function
          -> Epsilon report analysis field may be object/array, not string.
             MarkdownText must coerce to string before .trim()

  Bug 3: agent_epsilon.py --send: expected string or bytes-like object, got 'tuple'
          -> send_telegram_chunks() called with a tuple. Patch micc_data.py
             to make send_telegram_chunks() tuple-safe (belt+suspenders fix).
"""

import re, sys
from pathlib import Path

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"

def read(p):  return Path(p).read_text(encoding="utf-8")
def write(p, t): Path(p).write_text(t, encoding="utf-8"); print(f"  [OK] Wrote {p}")


# ─────────────────────────────────────────────────────────────────────────────
# BUG 1: options/route.ts -- no such column: volume
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("BUG 1: options/route.ts -- no such column: volume")
print("="*60)

route = None
for p in DASH.rglob("route.ts"):
    if "options" in str(p).replace("\\", "/").lower():
        route = p
        break

if not route:
    print("[SKIP] options/route.ts not found under", DASH)
else:
    print(f"  File: {route}")
    src = read(route)
    orig = src

    vol_lines = [(i+1, l) for i, l in enumerate(src.splitlines()) if 'volume' in l]
    print(f"  Lines with 'volume' ({len(vol_lines)} found):")
    for ln, l in vol_lines[:15]:
        print(f"    {ln:4d}: {l}")

    if vol_lines:
        # Replace g.volume -> f.volume (wrong table alias)
        src = src.replace('g.volume', 'f.volume')

        # In template-literal SQL blocks, replace bare `volume` with `f.volume`
        def fix_bare(m):
            sql = m.group(0)
            # Only replace `volume` not already prefixed by alias (word char + dot)
            return re.sub(r'(?<![A-Za-z_\d]\.)(?<![A-Za-z_\d])volume(?![A-Za-z_\d])',
                          'f.volume', sql)

        src = re.sub(r'`[^`]*\bvolume\b[^`]*`', fix_bare, src, flags=re.DOTALL)
        src = re.sub(r'"[^"]*\bvolume\b[^"]*"',  fix_bare, src, flags=re.DOTALL)

        if src != orig:
            write(route, src)
            print("  Fixed: bare `volume` -> `f.volume`")
        else:
            print("  [WARN] Regex found but did not change anything.")
            print("  Manual fix: in the SQL query, change `volume` to `f.volume`")
    else:
        print("  No 'volume' refs found — may already be fixed or different column name.")


# ─────────────────────────────────────────────────────────────────────────────
# BUG 2: MarkdownText.tsx -- text.trim is not a function
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("BUG 2: MarkdownText.tsx -- text.trim is not a function")
print("="*60)

md = None
for p in DASH.rglob("MarkdownText.tsx"):
    md = p; break

if not md:
    print("[SKIP] MarkdownText.tsx not found.")
else:
    print(f"  File: {md}")
    src = read(md)
    orig = src

    # Show lines 1-15
    for i, l in enumerate(src.splitlines()[:15], 1):
        print(f"    {i:4d}: {l}")

    OLD_GUARD = "if (!text || !text.trim()) return null;"
    NEW_GUARD_BLOCK = """\
  // Coerce non-string text prop (object/array from LLM JSON -> string)
  const _text: string =
    typeof text === 'string' ? text
    : Array.isArray(text) ? (text as unknown[]).map(String).join('\\n')
    : text == null ? ''
    : String(text);
  if (!_text.trim()) return null;\
"""

    if OLD_GUARD in src:
        src = src.replace(OLD_GUARD, NEW_GUARD_BLOCK)
        # Replace downstream uses of text. with _text. (split, replace, etc.)
        # Find end of the guard block, replace in the rest of function body
        guard_end_idx = src.index("if (!_text.trim()) return null;") + len("if (!_text.trim()) return null;")
        before = src[:guard_end_idx]
        after  = src[guard_end_idx:]
        after  = re.sub(r'\btext\.', '_text.', after)
        src = before + after
        write(md, src)
        print("  Fixed: inserted _text coercion, replaced text.xxx with _text.xxx")
    elif "Coerce non-string" in src:
        print("  Already has coercion guard — skipping.")
    else:
        # Fallback: insert right after function opening brace
        fn_m = re.search(r'(export default function \w+\([^{]+\{)\s*\n', src)
        if fn_m:
            pos = fn_m.end()
            coerce = (
                "  // Coerce non-string text prop\n"
                "  const _text: string = typeof text === 'string' ? text\n"
                "    : Array.isArray(text) ? (text as unknown[]).map(String).join('\\n')\n"
                "    : text == null ? '' : String(text);\n"
            )
            src = src[:pos] + coerce + src[pos:]
            src = re.sub(r'\btext\.(trim|split|replace|includes|length)\b', r'_text.\1', src)
            write(md, src)
            print("  Fixed (fallback path): inserted coercion at top of function")
        else:
            print("  [WARN] Could not parse function signature. Edit manually:")
            print("  Add at line 9:  const _text = typeof text==='string' ? text : String(text??'');")
            print("  Replace:  if (!text || !text.trim())")
            print("  With:     if (!_text.trim())")


# ─────────────────────────────────────────────────────────────────────────────
# BUG 3: agent_epsilon.py + micc_data.py -- tuple sent to Telegram
# Two-pronged fix:
#   A) Patch epsilon directly where it builds/sends the message
#   B) Make send_telegram_chunks() in micc_data.py tuple-safe (defensive)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("BUG 3: Telegram send receives tuple instead of string")
print("="*60)

# --- 3A: patch agent_epsilon.py ---
eps = BASE / "agent_epsilon.py"
if eps.exists():
    src = read(eps)
    orig = src
    lines = src.splitlines()

    send_lines = [(i+1, l) for i, l in enumerate(lines) if 'send_telegram' in l]
    print(f"  agent_epsilon.py -- {len(send_lines)} send_telegram call(s):")
    for ln, l in send_lines:
        print(f"    {ln:4d}: {l}")

    new_lines = []
    changed = False
    for i, line in enumerate(lines):
        m = re.match(r'^(\s*)(send_telegram(?:_chunks)?)\((.+)\)\s*$', line.rstrip())
        if m:
            indent, func, arg = m.group(1), m.group(2), m.group(3).strip()
            if 'isinstance' not in arg and not arg.startswith('str('):
                safe = (
                    f"{indent}_tg_msg = ('\\n'.join(str(x) for x in {arg})"
                    f" if isinstance({arg}, (list, tuple)) else str({arg}))\n"
                    f"{indent}{func}(_tg_msg)"
                )
                new_lines.append(safe)
                changed = True
                print(f"  Patched line {i+1}: {line.strip()[:70]}")
                continue
        new_lines.append(line)

    if changed:
        write(eps, "\n".join(new_lines) + "\n")
        print("  [OK] agent_epsilon.py send calls are now tuple-safe")
    else:
        print("  No simple send calls found (may be inside helper). Applying micc_data.py fallback.")
else:
    print(f"  agent_epsilon.py not found at {eps}")

# --- 3B: patch micc_data.py send_telegram_chunks (defensive) ---
data_py = BASE / "micc_data.py"
if data_py.exists():
    src = read(data_py)
    OLD_CHUNKS = "def send_telegram_chunks(text: str, max_len: int = 4000) -> bool:"
    NEW_CHUNKS = (
        "def send_telegram_chunks(text, max_len: int = 4000) -> bool:\n"
        "    # Defensive coerce: accept tuple/list/any -> str\n"
        "    if isinstance(text, (list, tuple)):\n"
        "        text = '\\n'.join(str(x) for x in text)\n"
        "    elif not isinstance(text, str):\n"
        "        text = str(text) if text is not None else ''"
    )
    if OLD_CHUNKS in src and "Defensive coerce" not in src:
        src = src.replace(OLD_CHUNKS, NEW_CHUNKS)
        write(data_py, src)
        print("  [OK] micc_data.py send_telegram_chunks() is now tuple-safe")
    elif "Defensive coerce" in src:
        print("  micc_data.py already patched.")
    else:
        print(f"  [WARN] Signature not found in {data_py}. Check manually.")
else:
    print(f"  [WARN] micc_data.py not found at {data_py}")


print("\n" + "="*60)
print("DONE")
print("="*60)
print()
print("Steps to verify:")
print("  1. Kill + restart Next.js:  cd D:\\MICC\\micc-dashboard && npm run dev")
print("  2. Open /options -> Options Chain tab -> should show chain data")
print("  3. Open /options -> Epsilon Signals tab -> should render without crash")
print("  4. py D:\\MICC\\agent_epsilon.py --send   -> no tuple error in Telegram")
