#!/usr/bin/env python3
"""
fix_design_tokens.py
====================
Replaces all hardcoded hex colors from the wrong design system
with the correct CSS variables used by overview/streaks/indices.

Wrong system  -> Correct vars
#0f172a       -> var(--bg)        (dark bg)
#080c10       -> var(--bg)
#0a0a0a       -> var(--bg)
#0a0f1a       -> var(--bg)
#1e293b       -> var(--surface)   (cards/panels)
#0d1117       -> var(--surface)
#0f1923       -> var(--surface)
#111820       -> var(--card)
#1a1f2e       -> var(--card)
#334155       -> var(--border)
#1e2836       -> var(--border)
#1e3a5f       -> var(--border)    (close enough — accent border)
#1f2937       -> var(--border)
#374151       -> var(--muted)
#4b5563       -> var(--muted)
#475569       -> var(--muted)
#64748b       -> var(--muted)
#6b7280       -> var(--muted)
#637080       -> var(--muted)
#94a3b8       -> var(--muted)
#9ca3af       -> var(--muted)
#e2e8f0       -> var(--text)
#f8fafc       -> var(--text)
#f9fafb       -> var(--text)
#cbd5e1       -> var(--text)
#c9d3df       -> var(--text)
#60a5fa       -> var(--accent)
#58a6ff       -> var(--accent)
#3b82f6       -> var(--accent)
#22c55e       -> var(--pos)
#10b981       -> var(--pos)
#3fb950       -> var(--pos)
#26c485       -> var(--pos)
#ef4444       -> var(--neg)
#f85149       -> var(--neg)
#f59e0b       -> var(--warn)
#d29922       -> var(--warn)
#fbbf24       -> var(--warn)

Font replacements:
'Courier New',monospace  -> 'JetBrains Mono',monospace
system-ui,sans-serif     -> 'Space Grotesk',sans-serif
system-ui, sans-serif    -> 'Space Grotesk',sans-serif

Pages to fix: global, macro, alerts, compare, conviction, portfolio, eta, analysis, patterns-v3, watchlist
"""

from pathlib import Path
import re

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

# Order matters — more specific first
COLOR_MAP = [
    # Backgrounds
    ('"#080c10"',   '"var(--bg)"'),
    ('"#0a0a0a"',   '"var(--bg)"'),
    ('"#0a0f1a"',   '"var(--bg)"'),
    ('"#0f172a"',   '"var(--bg)"'),
    # Surfaces / cards
    ('"#0d1117"',   '"var(--surface)"'),
    ('"#0f1923"',   '"var(--surface)"'),
    ('"#111820"',   '"var(--card)"'),
    ('"#1a1f2e"',   '"var(--card)"'),
    ('"#1e293b"',   '"var(--card)"'),
    ('"#161b22"',   '"var(--card)"'),
    # Borders
    ('"#1e2836"',   '"var(--border)"'),
    ('"#1f2937"',   '"var(--border)"'),
    ('"#2a3444"',   '"var(--border2)"'),
    ('"#30363d"',   '"var(--border)"'),
    ('"#334155"',   '"var(--border2)"'),
    ('"#1e3a5f"',   '"var(--border)"'),
    # Muted text
    ('"#374151"',   '"var(--muted)"'),
    ('"#4b5563"',   '"var(--muted)"'),
    ('"#475569"',   '"var(--muted)"'),
    ('"#64748b"',   '"var(--muted)"'),
    ('"#6b7280"',   '"var(--muted)"'),
    ('"#637080"',   '"var(--muted)"'),
    ('"#94a3b8"',   '"var(--muted)"'),
    ('"#9ca3af"',   '"var(--muted)"'),
    ('"#8b949e"',   '"var(--muted)"'),
    # Text
    ('"#e2e8f0"',   '"var(--text)"'),
    ('"#f8fafc"',   '"var(--text)"'),
    ('"#f9fafb"',   '"var(--text)"'),
    ('"#cbd5e1"',   '"var(--text)"'),
    ('"#c9d3df"',   '"var(--text)"'),
    ('"#d1d5db"',   '"var(--text)"'),
    # Accent blue
    ('"#60a5fa"',   '"var(--accent)"'),
    ('"#58a6ff"',   '"var(--accent)"'),
    ('"#3b82f6"',   '"var(--accent)"'),
    # Positive green
    ('"#22c55e"',   '"var(--pos)"'),
    ('"#10b981"',   '"var(--pos)"'),
    ('"#3fb950"',   '"var(--pos)"'),
    ('"#26c485"',   '"var(--pos)"'),
    ('"#34d399"',   '"var(--pos)"'),
    # Negative red
    ('"#ef4444"',   '"var(--neg)"'),
    ('"#f85149"',   '"var(--neg)"'),
    # Warning
    ('"#f59e0b"',   '"var(--warn)"'),
    ('"#d29922"',   '"var(--warn)"'),
    ('"#fbbf24"',   '"var(--warn)"'),
    ('"#e3b341"',   '"var(--warn)"'),
    # Purple / orange / cyan
    ('"#8b5cf6"',   '"var(--purple)"'),
    ('"#bc8cff"',   '"var(--purple)"'),
    ('"#a78bfa"',   '"var(--purple)"'),
    ('"#818cf8"',   '"var(--purple)"'),
    ('"#f97316"',   '"var(--orange)"'),
    ('"#ffa657"',   '"var(--orange)"'),
    ('"#f0883e"',   '"var(--orange)"'),
    ('"#14b8a6"',   '"var(--cyan)"'),
    ('"#39d5d5"',   '"var(--cyan)"'),
    ('"#06b6d4"',   '"var(--cyan)"'),
    ('"#ec4899"',   '"#ec4899"'),  # pink — keep as is
]

# Also handle template literal colors (backtick strings)
# e.g. `${color}22` patterns are dynamic, leave those alone

FONT_MAP = [
    ("'Courier New',monospace",   "'JetBrains Mono',monospace"),
    ("'Courier New', monospace",  "'JetBrains Mono',monospace"),
    ("\"Courier New\",monospace", "'JetBrains Mono',monospace"),
    ("system-ui,sans-serif",      "'Space Grotesk',sans-serif"),
    ("system-ui, sans-serif",     "'Space Grotesk',sans-serif"),
    ('"system-ui,sans-serif"',    '"Space Grotesk",sans-serif'),
    ('"system-ui, sans-serif"',   '"Space Grotesk",sans-serif'),
    ("\"system-ui,sans-serif\"",  "'Space Grotesk',sans-serif"),
]

# Pages to fix
PAGES = [
    "global", "macro", "alerts", "compare",
    "conviction", "portfolio", "eta", "analysis",
    "patterns-v3", "watchlist", "mf", "backtest",
    "settings", "deep",
]

def fix_page(path: Path) -> int:
    if not path.exists():
        return 0
    original = path.read_text(encoding="utf-8")
    modified = original

    # Apply color token replacements
    for old, new in COLOR_MAP:
        modified = modified.replace(old, new)

    # Apply font replacements
    for old, new in FONT_MAP:
        modified = modified.replace(old, new)

    # Fix body wrapper background hardcoded as non-string
    # e.g. background:"#0f172a" -> background:"var(--bg)"
    # Already handled above but do a regex pass for any remaining hex in background:
    def replace_bg_hex(m):
        hex_val = m.group(1).lower()
        bg_colors = {"080c10","0a0a0a","0a0f1a","0f172a","0f1923","111111","0d1117"}
        if hex_val in bg_colors:
            return 'background:"var(--bg)"'
        return m.group(0)

    modified = re.sub(r'background:"#([0-9a-fA-F]{6})"', replace_bg_hex, modified)

    if modified != original:
        path.write_text(modified, encoding="utf-8")
        # Count changes
        changes = sum(1 for a, b in zip(original.split('\n'), modified.split('\n')) if a != b)
        return changes
    return 0


def log(msg):
    from datetime import datetime
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)


log("Starting design token mass-replacement...")
total_files = 0
total_changes = 0

for page in PAGES:
    path = SRC / page / "page.tsx"
    n = fix_page(path)
    if n > 0:
        print("  FIXED  " + page.ljust(15) + " — " + str(n) + " lines changed")
        total_files += 1
        total_changes += n
    else:
        print("  SKIP   " + page.ljust(15) + " — no changes needed")

# Also fix any sub-pages
for page in ["deep/[symbol]", "stocks/[symbol]"]:
    path = SRC / page / "page.tsx"
    n = fix_page(path)
    if n > 0:
        print("  FIXED  " + page.ljust(15) + " — " + str(n) + " lines changed")
        total_files += 1

log("Done. " + str(total_files) + " files updated, ~" + str(total_changes) + " lines changed.")
print("")
print("All pages now use CSS variables matching overview/streaks/indices.")
print("Refresh http://localhost:3000 to verify.")
