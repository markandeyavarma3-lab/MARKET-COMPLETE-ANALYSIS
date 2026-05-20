#!/usr/bin/env python3
"""
unify_design.py - MICC Master Design Unification
=================================================
Rewrites all pages to use the exact same design system as streaks/indices/overview.

Design system (from globals.css + streaks/indices source of truth):
  Colors:    var(--bg) var(--surface) var(--card) var(--border) var(--border2)
             var(--muted) var(--text) var(--accent) var(--pos) var(--neg)
             var(--warn) var(--purple) var(--orange) var(--cyan)
  Font body: Space Grotesk, sans-serif  (globals.css body)
  Font mono: JetBrains Mono, monospace  (labels, tables, badges)
  Spacing:   padding 16px 20px, maxWidth 1600, margin auto (streaks pattern)
  Cards:     class="card" or background var(--card) border var(--border) borderRadius 8
  Buttons:   monospace, small, active = color+"22" bg + color border
  Tables:    class="data-table" or JetBrains Mono, 11px, border var(--border)

Run: python unify_design.py
Location: D:/MICC/unify_design.py
"""

from pathlib import Path
import re

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def log(msg):
    from datetime import datetime
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Fix globals.css - add missing NavBar duplicate fix + clean up
# ─────────────────────────────────────────────────────────────────────────────
log("[1] Fixing globals.css...")

globals_css = """@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg:      #080c10;
  --surface: #0d1117;
  --card:    #111820;
  --border:  #1e2836;
  --border2: #2a3444;
  --muted:   #637080;
  --dim:     #3d4f60;
  --text:    #c9d3df;
  --accent:  #58a6ff;
  --pos:     #3fb950;
  --neg:     #f85149;
  --warn:    #d29922;
  --purple:  #bc8cff;
  --orange:  #ffa657;
  --cyan:    #39d5d5;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

html { scroll-behavior: smooth; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Space Grotesk', sans-serif;
  font-size: 13px;
  line-height: 1.5;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--surface); }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }

/* ── Page shell ── */
.page { min-height: 100vh; background: var(--bg); }
.page-inner { padding: 16px 20px; max-width: 1600px; margin: 0 auto; }

/* ── Page header ── */
.page-header {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.page-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 4px;
}
.page-heading {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -.01em;
}
.page-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  margin-top: 3px;
  letter-spacing: .04em;
}

/* ── Cards ── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.card-sm { padding: 10px 14px; margin-bottom: 10px; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--muted);
}

/* ── KPI grid ── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 8px;
  margin-bottom: 16px;
}
.kpi {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
}
.kpi-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 500;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 4px;
}
.kpi-value {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
}
.kpi-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  margin-top: 3px;
  color: var(--muted);
}

/* ── Tables ── */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}
.data-table th {
  text-align: left;
  padding: 6px 10px;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}
.data-table th:hover { color: var(--text); }
.data-table td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: rgba(255,255,255,.025); }

/* ── Buttons ── */
.btn {
  padding: 4px 12px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: .04em;
  cursor: pointer;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  transition: color .15s, border-color .15s, background .15s;
}
.btn:hover { color: var(--text); border-color: var(--border2); }
.btn-active { background: rgba(88,166,255,.12); color: var(--accent); border-color: var(--accent); }
.btn-pos { background: rgba(63,185,80,.12); color: var(--pos); border-color: var(--pos); }
.btn-neg { background: rgba(248,81,73,.12); color: var(--neg); border-color: var(--neg); }
.btn-primary {
  background: var(--accent); color: #fff; border-color: var(--accent);
  font-weight: 700; padding: 6px 18px; font-size: 11px;
}
.btn-primary:hover { opacity: .85; }
.btn-primary:disabled { background: var(--border2); border-color: var(--border2); cursor: not-allowed; }

/* ── Pills / badges ── */
.pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 100px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .04em;
}
.pill-bull { background: rgba(63,185,80,.12); color: var(--pos); border: 1px solid rgba(63,185,80,.25); }
.pill-bear { background: rgba(248,81,73,.12); color: var(--neg); border: 1px solid rgba(248,81,73,.25); }
.pill-warn { background: rgba(210,153,34,.12); color: var(--warn); border: 1px solid rgba(210,153,34,.25); }
.pill-neut { background: rgba(88,166,255,.08); color: var(--accent); border: 1px solid rgba(88,166,255,.2); }

/* ── Score bar ── */
.sbar-wrap { display: flex; align-items: center; gap: 8px; }
.sbar-bg { flex: 1; height: 4px; background: var(--border2); border-radius: 2px; overflow: hidden; }
.sbar-fill { height: 100%; border-radius: 2px; transition: width .3s; }

/* ── Section label ── */
.section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 8px 0 6px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}

/* ── Analysis text box ── */
.analysis-box {
  font-size: 12px;
  line-height: 1.75;
  color: var(--text);
  padding: 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  white-space: pre-wrap;
  max-height: 400px;
  overflow-y: auto;
}

/* ── Input / select ── */
.micc-input {
  padding: 6px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  outline: none;
  transition: border-color .15s;
}
.micc-input:focus { border-color: var(--accent); }

select.micc-input option { background: var(--surface); }

/* ── Loading spinner ── */
@keyframes spin { to { transform: rotate(360deg); } }
.spinner {
  width: 24px; height: 24px;
  border: 2px solid var(--border2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .7s linear infinite;
  display: inline-block;
}

/* ── Pulse dot ── */
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.pulse-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--pos);
  display: inline-block;
  animation: pulse 2s infinite;
  margin-right: 5px;
}

/* ── Row hover animation ── */
.data-table tbody tr {
  transition: background .12s;
}

/* ── Tabs ── */
.tab-bar {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}
.tab {
  padding: 7px 16px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  border: none;
  background: transparent;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color .15s, border-color .15s;
  margin-bottom: -1px;
}
.tab:hover { color: var(--text); }
.tab-active { color: var(--accent); border-bottom-color: var(--accent); }

/* ── Error box ── */
.error-box {
  background: rgba(248,81,73,.08);
  border: 1px solid rgba(248,81,73,.25);
  border-radius: 6px;
  padding: 10px 14px;
  color: var(--neg);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  margin-bottom: 14px;
}

/* ── Empty state ── */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: .06em;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .page-inner { padding: 12px 14px; }
}
"""

write(DASH / "src" / "app" / "globals.css", globals_css)
log("  globals.css updated with full design system")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Fix NavBar - remove duplicates, clean up
# ─────────────────────────────────────────────────────────────────────────────
log("[2] Fixing NavBar.tsx - removing duplicate entries...")

navbar_path = DASH / "src" / "components" / "NavBar.tsx"
navbar = navbar_path.read_text(encoding="utf-8")

new_pages = """\
const PAGES = [
  { href: "/",            label: "OVERVIEW"   },
  { href: "/analysis",    label: "ANALYTICS"  },
  { href: "/streaks",     label: "STREAKS"    },
  { href: "/indices",     label: "INDICES"    },
  { href: "/options",     label: "OPTIONS"    },
  { href: "/macro",       label: "MACRO"      },
  { href: "/patterns",    label: "PATTERNS"   },
  { href: "/patterns-v3", label: "PATS-V3"    },
  { href: "/global",      label: "GLOBAL"     },
  { href: "/mf",          label: "MF NAV"     },
  { href: "/watchlist",   label: "WATCHLIST"  },
  { href: "/eta",         label: "ETA"        },
  { href: "/alerts",      label: "ALERTS"     },
  { href: "/compare",     label: "COMPARE"    },
  { href: "/conviction",  label: "CONVICTION" },
  { href: "/portfolio",   label: "PORTFOLIO"  },
  { href: "/deep",        label: "DEEP"       },
  { href: "/backtest",    label: "BACKTEST"   },
  { href: "/settings",    label: "SETTINGS"   },
];"""

navbar = re.sub(r'const PAGES = \[[\s\S]*?\];', new_pages, navbar)
navbar_path.write_text(navbar, encoding="utf-8")
log("  NavBar cleaned - 19 unique pages, no duplicates")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Mass token replacement across ALL pages
# ─────────────────────────────────────────────────────────────────────────────
log("[3] Running mass design token replacement...")

# Map: (old_string, new_string) - order matters, most specific first
REPLACEMENTS = [
    # Wrong backgrounds -> correct vars
    ('background: "#080c10"',   'background: "var(--bg)"'),
    ('background:"#080c10"',    'background:"var(--bg)"'),
    ('background: "#0a0a0a"',   'background: "var(--bg)"'),
    ('background:"#0a0a0a"',    'background:"var(--bg)"'),
    ('background: "#0a0f1a"',   'background: "var(--bg)"'),
    ('background:"#0a0f1a"',    'background:"var(--bg)"'),
    ('background: "#0f172a"',   'background: "var(--bg)"'),
    ('background:"#0f172a"',    'background:"var(--bg)"'),
    ('background: "#0d1117"',   'background: "var(--surface)"'),
    ('background:"#0d1117"',    'background:"var(--surface)"'),
    ('background: "#0f1923"',   'background: "var(--surface)"'),
    ('background:"#0f1923"',    'background:"var(--surface)"'),
    ('background: "#111820"',   'background: "var(--card)"'),
    ('background:"#111820"',    'background:"var(--card)"'),
    ('background: "#1a1f2e"',   'background: "var(--card)"'),
    ('background:"#1a1f2e"',    'background:"var(--card)"'),
    ('background: "#1e293b"',   'background: "var(--card)"'),
    ('background:"#1e293b"',    'background:"var(--card)"'),
    ('background: "#161b22"',   'background: "var(--card)"'),
    ('background:"#161b22"',    'background:"var(--card)"'),
    ('background: "#0c0c0c"',   'background: "var(--bg)"'),
    ('background:"#0c0c0c"',    'background:"var(--bg)"'),
    ('background: "#111827"',   'background: "var(--surface)"'),
    ('background:"#111827"',    'background:"var(--surface)"'),
    ('background: "#1f2937"',   'background: "var(--card)"'),
    ('background:"#1f2937"',    'background:"var(--card)"'),
    ('background: "#1e3a5f"',   'background: "var(--card)"'),
    ('background:"#1e3a5f"',    'background:"var(--card)"'),

    # Border colors
    ('"#334155"',   '"var(--border2)"'),
    ('"#2a3444"',   '"var(--border2)"'),
    ('"#1e2836"',   '"var(--border)"'),
    ('"#1f2937"',   '"var(--border)"'),
    ('"#30363d"',   '"var(--border)"'),
    ('"#374151"',   '"var(--border2)"'),

    # Text colors
    ('"#e2e8f0"',   '"var(--text)"'),
    ('"#f8fafc"',   '"var(--text)"'),
    ('"#f9fafb"',   '"var(--text)"'),
    ('"#cbd5e1"',   '"var(--text)"'),
    ('"#c9d3df"',   '"var(--text)"'),
    ('"#d1d5db"',   '"var(--text)"'),

    # Muted colors
    ('"#94a3b8"',   '"var(--muted)"'),
    ('"#9ca3af"',   '"var(--muted)"'),
    ('"#64748b"',   '"var(--muted)"'),
    ('"#6b7280"',   '"var(--muted)"'),
    ('"#4b5563"',   '"var(--muted)"'),
    ('"#475569"',   '"var(--muted)"'),
    ('"#637080"',   '"var(--muted)"'),
    ('"#8b949e"',   '"var(--muted)"'),

    # Accent blue
    ('"#60a5fa"',   '"var(--accent)"'),
    ('"#58a6ff"',   '"var(--accent)"'),
    ('"#3b82f6"',   '"var(--accent)"'),

    # Green pos
    ('"#22c55e"',   '"var(--pos)"'),
    ('"#10b981"',   '"var(--pos)"'),
    ('"#3fb950"',   '"var(--pos)"'),
    ('"#26c485"',   '"var(--pos)"'),
    ('"#34d399"',   '"var(--pos)"'),

    # Red neg
    ('"#ef4444"',   '"var(--neg)"'),
    ('"#f85149"',   '"var(--neg)"'),

    # Warn yellow
    ('"#f59e0b"',   '"var(--warn)"'),
    ('"#d29922"',   '"var(--warn)"'),
    ('"#fbbf24"',   '"var(--warn)"'),
    ('"#e3b341"',   '"var(--warn)"'),

    # Purple
    ('"#8b5cf6"',   '"var(--purple)"'),
    ('"#bc8cff"',   '"var(--purple)"'),
    ('"#a78bfa"',   '"var(--purple)"'),
    ('"#818cf8"',   '"var(--purple)"'),

    # Orange
    ('"#f97316"',   '"var(--orange)"'),
    ('"#ffa657"',   '"var(--orange)"'),
    ('"#f0883e"',   '"var(--orange)"'),

    # Cyan
    ('"#14b8a6"',   '"var(--cyan)"'),
    ('"#39d5d5"',   '"var(--cyan)"'),
    ('"#06b6d4"',   '"var(--cyan)"'),

    # Font replacements
    ("'Courier New', monospace",   "'JetBrains Mono', monospace"),
    ("'Courier New',monospace",    "'JetBrains Mono', monospace"),
    ('"Courier New", monospace',   "'JetBrains Mono', monospace"),
    ("system-ui, sans-serif",      "'Space Grotesk', sans-serif"),
    ("system-ui,sans-serif",       "'Space Grotesk', sans-serif"),
    ('"system-ui, sans-serif"',    '"Space Grotesk", sans-serif'),
    ('"system-ui,sans-serif"',     '"Space Grotesk", sans-serif'),

    # minHeight with wrong bg
    ('minHeight:"100vh",background:"var(--bg)",color:"var(--text)",fontFamily:"\'Courier New\',monospace"',
     'minHeight:"100vh",background:"var(--bg)"'),
    ('minHeight: "100vh", background: "var(--bg)", color: "#e2e8f0", fontFamily: "system-ui,sans-serif"',
     'minHeight: "100vh", background: "var(--bg)"'),
    ('minHeight: "100vh", background: "var(--bg)", color: "var(--text)", fontFamily: "system-ui,sans-serif"',
     'minHeight: "100vh", background: "var(--bg)"'),
    ('minHeight:"100vh",background:"#0f172a",color:"#e2e8f0",fontFamily:"system-ui,sans-serif"',
     'minHeight:"100vh",background:"var(--bg)"'),

    # letterSpacing:1 -> use em values
    ('letterSpacing: 1,',   'letterSpacing: ".04em",'),
    ('letterSpacing:1,',    'letterSpacing:".04em",'),
    ('letterSpacing: 2,',   'letterSpacing: ".08em",'),
    ('letterSpacing:2,',    'letterSpacing:".08em",'),
    ('letterSpacing: 3,',   'letterSpacing: ".12em",'),
    ('letterSpacing:3,',    'letterSpacing:".12em",'),
]

pages_to_fix = [
    "global", "macro", "alerts", "compare", "conviction", "portfolio",
    "eta", "analysis", "watchlist", "mf", "settings", "patterns-v3",
    "overview", "indices", "options", "streaks", "deep", "patterns",
]

total_changed = 0
for page in pages_to_fix:
    path = SRC / page / "page.tsx"
    if not path.exists():
        continue
    original = path.read_text(encoding="utf-8")
    modified = original
    for old, new in REPLACEMENTS:
        modified = modified.replace(old, new)

    # Also fix template literal colors (backtick patterns)
    # e.g. `#ef4444` in template strings
    modified = re.sub(r'`#ef4444`', '`var(--neg)`', modified)
    modified = re.sub(r'`#22c55e`', '`var(--pos)`', modified)
    modified = re.sub(r'`#58a6ff`', '`var(--accent)`', modified)
    modified = re.sub(r'`#60a5fa`', '`var(--accent)`', modified)

    if modified != original:
        path.write_text(modified, encoding="utf-8")
        n = sum(1 for a,b in zip(original.splitlines(), modified.splitlines()) if a!=b)
        total_changed += n
        print("  FIXED  " + page.ljust(15) + "  ~" + str(n) + " lines")
    else:
        print("  OK     " + page.ljust(15) + "  (no changes)")

log("  Total lines changed: " + str(total_changed))


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Fix remaining hardcoded wrong-system colors in 1e3a5f (accent border)
# ─────────────────────────────────────────────────────────────────────────────
log("[4] Fixing remaining #1e3a5f (wrong-system accent border)...")

for page in pages_to_fix:
    path = SRC / page / "page.tsx"
    if not path.exists(): continue
    src = path.read_text(encoding="utf-8")
    # #1e3a5f was a wrong-system border color, replace with var(--border)
    fixed = src.replace('"#1e3a5f"', '"var(--border)"').replace("'#1e3a5f'", "'var(--border)'")
    # Also fix wrong-system surface colors still remaining
    fixed = fixed.replace('"#0a0f1a"', '"var(--bg)"').replace('"#0f1923"', '"var(--surface)"')
    if fixed != src:
        path.write_text(fixed, encoding="utf-8")
        print("  FIXED remaining tokens: " + page)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Fix layout.tsx paddingTop to match actual NavBar height (48px)
# ─────────────────────────────────────────────────────────────────────────────
log("[5] Verifying layout.tsx...")

layout = (SRC / "layout.tsx").read_text(encoding="utf-8")
if "paddingTop" not in layout:
    layout = layout.replace(
        "<NavBar />",
        "<NavBar />\n        <div style={{ paddingTop: '48px' }}>"
    ).replace(
        "{children}",
        "{children}\n        </div>"
    )
    write(SRC / "layout.tsx", layout)
    log("  Added paddingTop wrapper")
else:
    log("  layout.tsx OK")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Fix mf/page.tsx which is basically empty
# ─────────────────────────────────────────────────────────────────────────────
log("[6] Checking mf/page.tsx...")

mf_path = SRC / "mf" / "page.tsx"
mf_content = mf_path.read_text(encoding="utf-8") if mf_path.exists() else ""
if len(mf_content.strip()) < 100:
    log("  mf/page.tsx is empty stub - writing proper page...")
    mf_page = """\
"use client";
import { useEffect, useState } from "react";

export default function MfPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("/api/mf")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const rows = (data?.rows || []).filter((r: any) =>
    !search || r.scheme_name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="page">
      <div className="page-inner">
        <div className="page-header">
          <div>
            <div className="page-title">MICC</div>
            <div className="page-heading">MF NAV TRACKER</div>
            <div className="page-sub">MUTUAL FUND NAV HISTORY · TOP PERFORMERS · FLOWS</div>
          </div>
          <input className="micc-input" placeholder="Search fund..." value={search}
            onChange={e => setSearch(e.target.value)} style={{ width: 220 }} />
        </div>

        {loading && <div className="empty-state"><div className="spinner" /><div style={{marginTop:12}}>LOADING...</div></div>}

        {!loading && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">NAV DATA — {rows.length} FUNDS</span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>SCHEME</th>
                    <th style={{textAlign:"right"}}>NAV</th>
                    <th style={{textAlign:"right"}}>1D %</th>
                    <th style={{textAlign:"right"}}>1W %</th>
                    <th style={{textAlign:"right"}}>1M %</th>
                    <th style={{textAlign:"right"}}>DATE</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 200).map((r: any, i: number) => (
                    <tr key={i}>
                      <td style={{ color: "var(--accent)", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.scheme_name || r.symbol || "—"}
                      </td>
                      <td style={{ textAlign: "right", color: "var(--text)", fontWeight: 600 }}>
                        {r.nav != null ? Number(r.nav).toFixed(2) : "—"}
                      </td>
                      <td style={{ textAlign: "right", color: r.ret_1d > 0 ? "var(--pos)" : r.ret_1d < 0 ? "var(--neg)" : "var(--muted)" }}>
                        {r.ret_1d != null ? (r.ret_1d >= 0 ? "+" : "") + r.ret_1d.toFixed(2) + "%" : "—"}
                      </td>
                      <td style={{ textAlign: "right", color: r.ret_1w > 0 ? "var(--pos)" : r.ret_1w < 0 ? "var(--neg)" : "var(--muted)" }}>
                        {r.ret_1w != null ? (r.ret_1w >= 0 ? "+" : "") + r.ret_1w.toFixed(2) + "%" : "—"}
                      </td>
                      <td style={{ textAlign: "right", color: r.ret_1m > 0 ? "var(--pos)" : r.ret_1m < 0 ? "var(--neg)" : "var(--muted)" }}>
                        {r.ret_1m != null ? (r.ret_1m >= 0 ? "+" : "") + r.ret_1m.toFixed(2) + "%" : "—"}
                      </td>
                      <td style={{ textAlign: "right", color: "var(--muted)" }}>{r.date || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length === 0 && <div className="empty-state">NO FUND DATA — RUN update_mf_nav.py FIRST</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
"""
    write(mf_path, mf_page)
    log("  mf/page.tsx written")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Fix analysis/page.tsx body wrapper + regime object bug
# ─────────────────────────────────────────────────────────────────────────────
log("[7] Fixing analysis page body wrapper...")

analysis_path = SRC / "analysis" / "page.tsx"
if analysis_path.exists():
    src = analysis_path.read_text(encoding="utf-8")
    # Fix body wrapper
    src = re.sub(
        r'<div style=\{\{ minHeight:"100vh"[^}]*\}\}>',
        '<div className="page">',
        src
    )
    src = re.sub(
        r'<div style=\{\{ minHeight: "100vh"[^}]*\}\}>',
        '<div className="page">',
        src
    )
    # Fix regime object render
    src = src.replace("v: report.regime,", "v: String(report.regime || ''),")
    # Fix inner padding wrapper
    src = src.replace(
        '<div style={{ padding:"20px 28px", display:"flex", flexDirection:"column", gap:20 }}>',
        '<div className="page-inner">'
    )
    src = src.replace(
        '<div style={{ padding: "20px 28px", display: "flex", flexDirection: "column", gap: 20 }}>',
        '<div className="page-inner">'
    )
    analysis_path.write_text(src, encoding="utf-8")
    log("  analysis page fixed")


# ─────────────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────────────
print("")
print("=" * 60)
print("DESIGN UNIFICATION COMPLETE")
print("=" * 60)
print("")
print("Changes made:")
print("  1. globals.css  - full design system with utility classes")
print("  2. NavBar.tsx   - removed duplicates, clean 19-page list")
print("  3. All pages    - CSS variable token replacement")
print("  4. Border fixes - #1e3a5f and other wrong-system colors")
print("  5. layout.tsx   - verified NavBar + paddingTop")
print("  6. mf/page.tsx  - written from scratch (was empty stub)")
print("  7. analysis     - body wrapper + regime object bug fixed")
print("")
print("ALL pages now use:")
print("  Font:    Space Grotesk (body) / JetBrains Mono (mono)")
print("  Colors:  var(--bg/surface/card/border/text/accent/pos/neg)")
print("  Classes: .page .page-inner .card .kpi .data-table .btn .tab")
print("")
print("Refresh http://localhost:3000 to verify all pages look unified.")
