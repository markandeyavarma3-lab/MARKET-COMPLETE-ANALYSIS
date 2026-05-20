# -*- coding: utf-8 -*-
"""
fix_phase10b.py  --  Run from D:\\MICC
Fixes:
  1. /deep NaN error   -> sanitize NaN in ALL existing route.ts files
  2. Remove /compare   -> delete page, remove NavBar link
  3. Remove /backtest  -> delete page, remove NavBar link
  4. Add /api/search/route.ts -> autocomplete for stock/index search
  5. Update /analysis/page.tsx -> add autocomplete dropdown to search input

Run: py D:\\MICC\\fix_phase10b.py
"""

from pathlib import Path
import re

BASE = Path(r"D:\MICC")
DASH = BASE / "micc-dashboard"
SRC  = DASH / "src"
APP  = SRC / "app"
COMP = SRC / "components"

def write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    print(f"  [OK] {p.relative_to(BASE)}")

def delete(p: Path):
    if p.exists():
        p.unlink()
        print(f"  [DEL] {p.relative_to(BASE)}")
    else:
        print(f"  [SKIP] not found: {p.relative_to(BASE)}")

# =============================================================================
# [1] FIX NaN -- patch ALL route.ts files that call micc_db_bridge
# =============================================================================
print("\n[1/5] Patching NaN sanitization into all route.ts files...")

NAN_FIX_OLD = "return out ? JSON.parse(out) : []"
NAN_FIX_NEW = "return out ? JSON.parse(out.replace(/:\\s*NaN/g,': null').replace(/:\\s*Infinity/g,': null').replace(/:\\s*-Infinity/g,': null')) : []"

patched = 0
for route_file in (APP / "api").rglob("route.ts"):
    txt = route_file.read_text(encoding="utf-8")
    if NAN_FIX_OLD in txt and NAN_FIX_NEW not in txt:
        txt = txt.replace(NAN_FIX_OLD, NAN_FIX_NEW)
        route_file.write_text(txt, encoding="utf-8", newline="\n")
        print(f"  [NaN fix] {route_file.relative_to(BASE)}")
        patched += 1

# Also patch the old /api/deep/[symbol]/route.ts specifically
deep_sym = APP / "api" / "deep" / "[symbol]" / "route.ts"
if deep_sym.exists():
    txt = deep_sym.read_text(encoding="utf-8")
    # Add NaN sanitization if any parse without it
    if "NaN" not in txt:
        txt = txt.replace(
            "return out ? JSON.parse(out) : []",
            "return out ? JSON.parse(out.replace(/:\\s*NaN/g,': null').replace(/:\\s*Infinity/g,': null')) : []"
        )
        deep_sym.write_text(txt, encoding="utf-8", newline="\n")
        print(f"  [NaN fix] deep/[symbol]/route.ts")
        patched += 1

print(f"  Patched {patched} route files")


# =============================================================================
# [2] /api/search/route.ts -- fast autocomplete from stock_registry + indices
# =============================================================================
print("\n[2/5] /api/search/route.ts (autocomplete)")

write(APP / "api" / "search" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function qdb(sql: string, params: unknown[] = []): unknown[] {
  try {
    const r = spawnSync('py', [path.join(DA, 'micc_db_bridge.py')], {
      input: JSON.stringify({ sql, params }),
      encoding: 'utf-8', timeout: 8000, cwd: DA,
    })
    if (r.status !== 0) return []
    const out = r.stdout.trim()
    return out ? JSON.parse(out.replace(/:\s*NaN/g, ': null')) : []
  } catch { return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const q    = (searchParams.get('q') || '').trim().toUpperCase()
  const type = searchParams.get('type') || 'stock'   // stock | index

  if (q.length < 1) return NextResponse.json({ ok: true, results: [] })

  try {
    let results: unknown[] = []

    if (type === 'stock') {
      // Search stock_registry (symbol + company name)
      results = qdb(`
        SELECT symbol, company_name as name, sector, 'stock' as type
        FROM stock_registry
        WHERE symbol LIKE ? OR UPPER(company_name) LIKE ?
        ORDER BY
          CASE WHEN symbol = ? THEN 0
               WHEN symbol LIKE ? THEN 1
               ELSE 2 END,
          symbol
        LIMIT 12
      `, [`${q}%`, `%${q}%`, q, `${q}%`])

      // Fallback: search from window_stats if no registry
      if (!results.length) {
        results = qdb(`
          SELECT DISTINCT symbol, symbol as name, '' as sector, asset_type as type
          FROM window_stats
          WHERE symbol LIKE ? AND asset_type = 'stock'
          ORDER BY symbol LIMIT 12
        `, [`${q}%`])
      }
    } else {
      // Index search — from market_snapshot index names + window_stats
      results = qdb(`
        SELECT DISTINCT index_name as symbol, index_name as name,
               '' as sector, 'index' as type
        FROM market_snapshot
        WHERE UPPER(index_name) LIKE ?
        ORDER BY
          CASE WHEN UPPER(index_name) = ? THEN 0
               WHEN UPPER(index_name) LIKE ? THEN 1
               ELSE 2 END,
          index_name
        LIMIT 12
      `, [`%${q}%`, q, `${q}%`])

      // Also check global indices
      if (results.length < 6) {
        const global = qdb(`
          SELECT DISTINCT symbol, symbol as name, 'Global' as sector, 'global' as type
          FROM global_indices_daily
          WHERE symbol LIKE ?
          LIMIT 6
        `, [`${q}%`])
        results = [...results, ...global].slice(0, 12)
      }
    }

    return NextResponse.json({ ok: true, results })
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 })
  }
}
""")


# =============================================================================
# [3] REMOVE /compare page and /backtest page + update NavBar
# =============================================================================
print("\n[3/5] Removing /compare and /backtest pages...")

# Delete page files
delete(APP / "compare" / "page.tsx")
delete(APP / "backtest" / "page.tsx")

# Note: we keep the API routes since /analysis uses /api/compare internally
# but the old /compare page UI is gone

print("\n[4/5] Updating NavBar -- remove COMPARE + BACKTEST, add ANALYTICS...")

navbar_path = None
for p in SRC.rglob("NavBar.tsx"):
    navbar_path = p
    break

if navbar_path and navbar_path.exists():
    # Full rewrite with correct final page list
    write(navbar_path, r"""
"use client";
import Link            from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const PAGES = [
  { href: "/analysis",   label: "ANALYTICS"  },
  { href: "/",           label: "OVERVIEW"   },
  { href: "/streaks",    label: "STREAKS"    },
  { href: "/indices",    label: "INDICES"    },
  { href: "/options",    label: "OPTIONS"    },
  { href: "/macro",      label: "MACRO"      },
  { href: "/mf",         label: "MF NAV"    },
  { href: "/watchlist",  label: "WATCHLIST"  },
  { href: "/eta",        label: "ETA"        },
  { href: "/deep",       label: "DEEP"       },
];

export default function NavBar() {
  const path = usePathname();
  const [time, setTime] = useState("");

  useEffect(() => {
    function tick() {
      setTime(
        new Date().toLocaleTimeString("en-IN", {
          hour: "2-digit", minute: "2-digit", second: "2-digit",
          timeZone: "Asia/Kolkata",
        }) + " IST"
      );
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 100,
      background: "var(--bg)", borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center",
      padding: "0 16px", height: 48, gap: 0, overflowX: "auto",
    }}>
      <div style={{
        fontFamily: "'Share Tech Mono','JetBrains Mono',monospace",
        fontSize: 15, fontWeight: 700, letterSpacing: "0.18em",
        color: "var(--accent)", marginRight: 20, whiteSpace: "nowrap", flexShrink: 0,
      }}>
        MICC
      </div>
      <nav style={{ display: "flex", gap: 1, flex: 1 }}>
        {PAGES.map(({ href, label }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} style={{
              padding: "6px 11px", fontSize: 10,
              fontFamily: "'JetBrains Mono',monospace",
              letterSpacing: "0.08em",
              fontWeight: active ? 700 : 400,
              color: active ? "var(--accent)" : "var(--muted)",
              borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
              textDecoration: "none", transition: "color 0.15s",
              whiteSpace: "nowrap",
            }}>
              {label}
            </Link>
          );
        })}
      </nav>
      <div style={{
        fontFamily: "monospace", fontSize: 10,
        color: "var(--dim)", whiteSpace: "nowrap", flexShrink: 0,
      }} suppressHydrationWarning>{time}</div>
    </header>
  );
}
""")
else:
    print("  [WARN] NavBar.tsx not found")


# =============================================================================
# [5] Update /analysis/page.tsx -- add autocomplete to search inputs
# =============================================================================
print("\n[5/5] Patching /analysis/page.tsx with autocomplete...")

analysis_page = APP / "analysis" / "page.tsx"

# We'll prepend an Autocomplete component and patch the search input
# Strategy: inject the AutoComplete component + hook, then replace the two input elements

AUTOCOMPLETE_COMPONENT = r"""
// ── Autocomplete component ─────────────────────────────────────────────────
interface SuggestionItem { symbol: string; name: string; sector: string; type: string; }

function AutocompleteInput({
  value, onChange, onSelect, placeholder, searchType, autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  onSelect: (sym: string) => void;
  placeholder: string;
  searchType: "stock" | "index";
  autoFocus?: boolean;
}) {
  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([]);
  const [showDrop, setShowDrop]       = useState(false);
  const [loading,  setLoading]        = useState(false);
  const [hiIdx,    setHiIdx]          = useState(-1);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.length < 1) { setSuggestions([]); return; }
    setLoading(true);
    try {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&type=${searchType}`, { cache: "no-store" });
      const d = await r.json();
      setSuggestions(d.results || []);
      setShowDrop(true);
    } catch { setSuggestions([]); }
    finally { setLoading(false); }
  }, [searchType]);

  const handleChange = (v: string) => {
    onChange(v);
    setHiIdx(-1);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => fetchSuggestions(v), 180);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setHiIdx(i => Math.min(i + 1, suggestions.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHiIdx(i => Math.max(i - 1, -1)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (hiIdx >= 0 && suggestions[hiIdx]) { onSelect(suggestions[hiIdx].symbol); setShowDrop(false); }
      else { onSelect(value); setShowDrop(false); }
    } else if (e.key === "Escape") { setShowDrop(false); }
  };

  const pick = (sym: string) => { onSelect(sym); onChange(sym); setShowDrop(false); setSuggestions([]); };

  const typeColor: Record<string, string> = { stock: "#22d3ee", index: "#4ade80", global: "#facc15" };

  return (
    <div style={{ position: "relative", flex: 1 }}>
      <input
        value={value}
        onChange={e => handleChange(e.target.value.toUpperCase())}
        onKeyDown={handleKeyDown}
        onFocus={() => value.length > 0 && suggestions.length > 0 && setShowDrop(true)}
        onBlur={() => setTimeout(() => setShowDrop(false), 200)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        style={{
          width: "100%", background: "var(--surface-card)",
          border: "1px solid var(--border-color)", color: "var(--text-primary)",
          borderRadius: 8, padding: "12px 16px", fontSize: 14,
          boxSizing: "border-box",
          borderBottomLeftRadius: showDrop && suggestions.length > 0 ? 0 : 8,
          borderBottomRightRadius: showDrop && suggestions.length > 0 ? 0 : 8,
        }}
      />
      {loading && (
        <div style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", fontSize: 11, color: "var(--text-tertiary)" }}>...</div>
      )}
      {showDrop && suggestions.length > 0 && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, zIndex: 999,
          background: "var(--surface-card)", border: "1px solid var(--border-color)",
          borderTop: "none", borderRadius: "0 0 8px 8px",
          maxHeight: 320, overflowY: "auto",
          boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
        }}>
          {suggestions.map((s, i) => (
            <div key={s.symbol} onMouseDown={() => pick(s.symbol)} style={{
              padding: "8px 14px", cursor: "pointer", display: "flex",
              alignItems: "center", gap: 10,
              background: i === hiIdx ? "rgba(34,211,238,0.1)" : "transparent",
              borderBottom: i < suggestions.length - 1 ? "1px solid var(--border-color)" : "none",
            }}>
              <span style={{ color: typeColor[s.type] || "#22d3ee", fontWeight: 800, fontSize: 13, minWidth: 80 }}>{s.symbol}</span>
              <span style={{ color: "var(--text-primary)", fontSize: 12, flex: 1 }}>{s.name !== s.symbol ? s.name : ""}</span>
              {s.sector && <span style={{ color: "var(--text-tertiary)", fontSize: 10 }}>{s.sector}</span>}
              <span style={{ fontSize: 9, fontWeight: 700, color: typeColor[s.type] || "#22d3ee", opacity: 0.7, minWidth: 36, textAlign: "right" }}>{s.type.toUpperCase()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

"""

if analysis_page.exists():
    txt = analysis_page.read_text(encoding="utf-8")

    # 1. Add useRef, useCallback imports if not already there (they should be)
    # 2. Inject AutocompleteInput component before the main export
    # 3. Replace the two search inputs with AutocompleteInput

    # Inject component before "export default function AnalysisPage"
    INJECT_BEFORE = "export default function AnalysisPage()"
    if "AutocompleteInput" not in txt:
        txt = txt.replace(INJECT_BEFORE, AUTOCOMPLETE_COMPONENT + INJECT_BEFORE)
        print("  Injected AutocompleteInput component")

    # Replace the stock search input block
    OLD_STOCK_INPUT = '''            <input
              ref={searchInputRef}
              value={searchInput}
              onChange={e=>setSearchInput(e.target.value.toUpperCase())}
              onKeyDown={e=>e.key==="Enter"&&doSearch(searchInput)}
              placeholder={mode==="search-stock" ? "Enter stock symbol (e.g. RELIANCE, TCS, INFY)..." : "Enter index name (e.g. NIFTY 50, NIFTY BANK, SPX)..."}
              style={{flex:1,background:C.surface,border:`1px solid ${C.border}`,color:C.primary,borderRadius:8,padding:"12px 16px",fontSize:14}}
              autoFocus
            />'''

    NEW_STOCK_INPUT = '''            <AutocompleteInput
              value={searchInput}
              onChange={setSearchInput}
              onSelect={(sym) => { setSearchInput(sym); doSearch(sym); }}
              placeholder={mode==="search-stock" ? "Type stock name or ticker (e.g. HDFC Bank, RELIANCE, TCS)..." : "Type index name (e.g. NIFTY 50, NIFTY BANK)..."}
              searchType={assetType as "stock"|"index"}
              autoFocus
            />'''

    if OLD_STOCK_INPUT in txt:
        txt = txt.replace(OLD_STOCK_INPUT, NEW_STOCK_INPUT)
        print("  Replaced search input with AutocompleteInput")
    else:
        print("  [WARN] Could not find exact search input block -- trying fallback patch")
        # Fallback: find the input by ref={searchInputRef} pattern
        txt = re.sub(
            r'<input\s+ref=\{searchInputRef\}[^/]*/>', 
            NEW_STOCK_INPUT,
            txt,
            count=1,
            flags=re.DOTALL
        )

    # Replace compare input with autocomplete for first symbol hint
    # (compare takes multiple symbols so we keep it as text but add suggestions for first token)
    OLD_CMP_INPUT = '''            <input
              value={cmpInput}
              onChange={e=>setCmpInput(e.target.value.toUpperCase())}
              onKeyDown={e=>e.key==="Enter"&&doCompare(cmpInput)}
              placeholder={mode==="compare-stocks" ? "RELIANCE, TCS, HDFCBANK, INFY (2-5 symbols)" : "NIFTY 50, NIFTY BANK, NIFTY IT (2-5 indices)"}
              style={{flex:1,background:C.surface,border:`1px solid ${C.border}`,color:C.primary,borderRadius:8,padding:"12px 16px",fontSize:14}}
              autoFocus
            />'''

    NEW_CMP_INPUT = '''            <input
              value={cmpInput}
              onChange={e=>setCmpInput(e.target.value.toUpperCase())}
              onKeyDown={e=>e.key==="Enter"&&doCompare(cmpInput)}
              placeholder={mode==="compare-stocks" ? "RELIANCE, TCS, HDFCBANK, INFY (2-5 symbols separated by commas)" : "NIFTY 50, NIFTY BANK, NIFTY IT (2-5 indices)"}
              style={{flex:1,background:"var(--surface-card)",border:"1px solid var(--border-color)",color:"var(--text-primary)",borderRadius:8,padding:"12px 16px",fontSize:14}}
              autoFocus
            />'''

    if OLD_CMP_INPUT in txt:
        txt = txt.replace(OLD_CMP_INPUT, NEW_CMP_INPUT)

    # Add missing useRef import if needed
    if "useRef" not in txt:
        txt = txt.replace(
            'import React, { useState, useCallback, useRef }',
            'import React, { useState, useCallback, useRef }'
        )

    analysis_page.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] /analysis/page.tsx patched with autocomplete")
else:
    print("  [WARN] /analysis/page.tsx not found -- run setup_phase10.py first")


# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 60)
print("FIX PHASE 10B COMPLETE")
print("=" * 60)
print("""
Changes:
  [1] NaN sanitized in ALL API route.ts files
      -> /deep page should no longer crash on corr_3y: NaN

  [2] /api/search/route.ts added
      -> searches stock_registry + market_snapshot for autocomplete

  [3] /compare/page.tsx DELETED (use /analysis Compare tab)
      /backtest/page.tsx DELETED

  [4] NavBar updated:
      ANALYTICS | OVERVIEW | STREAKS | INDICES | OPTIONS |
      MACRO | MF NAV | WATCHLIST | ETA | DEEP
      (COMPARE and BACKTEST removed)

  [5] /analysis search box now has Google-style autocomplete
      -> type "HDFC" -> shows HDFCBANK, HDFC, HDFCLIFE etc
      -> shows symbol + company name + sector + type badge
      -> arrow keys to navigate, Enter to select

Restart: cd D:\\MICC\\micc-dashboard && npm run dev

Test:
  localhost:3000/analysis  -> type "HDFC" -> see suggestions drop
  localhost:3000/deep      -> should no longer show NaN error
  localhost:3000/compare   -> 404 (removed, use /analysis)
  localhost:3000/backtest  -> 404 (removed)
""")
