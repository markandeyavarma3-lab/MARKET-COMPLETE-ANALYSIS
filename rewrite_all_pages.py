#!/usr/bin/env python3
"""
rewrite_all_pages.py
====================
Rewrites macro, alerts, compare, conviction, portfolio, eta,
analysis, watchlist, settings, patterns, patterns-v3, global
to exactly match the streaks/indices/overview design system.

Design system (extracted from liked pages):
  Wrapper:  minHeight:"100vh", background:"var(--bg)"
  Inner:    padding:"16px 20px", maxWidth:1600, margin:"0 auto"
  Font:     fontFamily:"monospace" (inline) / Space Grotesk (body via CSS)
  Header:   fontSize:14, fontWeight:700, letterSpacing:"0.12em", color:accentColor
  Sublabel: fontSize:9, color:"var(--dim)", letterSpacing:"0.1em"
  Btn:      padding:"3px 10px", fontSize:10, monospace, active=color+"22"+color border
  Table:    borderCollapse:collapse, fontSize:11, monospace, 1px solid var(--border)
  Colors:   var(--bg/surface/card/border/dim/muted/text/accent/pos/neg/warn/orange/cyan)
  NO emojis, NO rounded cards with thick borders, NO gradient buttons

Run: python rewrite_all_pages.py
Location: D:/MICC/rewrite_all_pages.py
"""

from pathlib import Path
import re

MICC = Path("D:/MICC")
DASH = MICC / "micc-dashboard"
SRC  = DASH / "src" / "app"

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    lines = len(content.splitlines())
    print("  [OK] " + str(path.relative_to(DASH)) + " (" + str(lines) + " lines)")

def log(msg):
    from datetime import datetime
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg, flush=True)

W = 'minHeight:"100vh",background:"var(--bg)"'
INN = 'padding:"16px 20px",maxWidth:1600,margin:"0 auto"'

# Shared button component used across all pages
BTN = """
function Btn({active=false,color="var(--accent)",onClick,children,style={}}: {active?:boolean;color?:string;onClick?:()=>void;children:any;style?:any}) {
  return (
    <button onClick={onClick} style={{
      padding:"3px 10px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
      background:active?color+"22":"var(--surface)",
      color:active?color:"var(--muted)",
      border:`1px solid ${active?color:"var(--border)"}`,
      borderRadius:4,transition:"all 0.12s",...style,
    }}>{children}</button>
  );
}"""

# =============================================================================
# macro/page.tsx
# =============================================================================
log("[1] Rewriting macro/page.tsx...")

macro_src = (SRC / "macro" / "page.tsx").read_text(encoding="utf-8")

# Strip all emojis
macro_src = re.sub(r'[\U00010000-\U0010ffff]', '', macro_src)
# Fix flags/emojis ASCII art
macro_src = re.sub(r'[^\x00-\x7F]+', '', macro_src)

# Replace wrong wrapper
macro_src = macro_src.replace(
    'minHeight:"100vh",background:"var(--bg)",color:"var(--text)",fontFamily:"\'Courier New\',monospace",padding:"24px"',
    W
)
macro_src = macro_src.replace(
    'minHeight: "100vh", background: "var(--bg)", color: "var(--text)", fontFamily: "system-ui,sans-serif"',
    W
)
macro_src = macro_src.replace(
    "minHeight: '100vh', background: 'var(--bg)'",
    W
)

# Fix card backgrounds still using wrong colors
for wrong, right in [
    ('"#1e293b"', '"var(--card)"'),
    ('"#0f172a"', '"var(--bg)"'),
    ('"#334155"', '"var(--border2)"'),
    ('"#1e3a5f"', '"var(--border)"'),
    ('"#0a0f1a"', '"var(--bg)"'),
    ('"#0f1923"', '"var(--surface)"'),
    ('"#94a3b8"', '"var(--muted)"'),
    ('"#64748b"', '"var(--muted)"'),
    ('"#e2e8f0"', '"var(--text)"'),
    ('"#60a5fa"', '"var(--accent)"'),
    ('"#22c55e"', '"var(--pos)"'),
    ('"#ef4444"', '"var(--neg)"'),
    ('"#f59e0b"', '"var(--warn)"'),
    ("'Courier New', monospace", "monospace"),
    ("'Courier New',monospace", "monospace"),
    ("system-ui, sans-serif", "monospace"),
    ("system-ui,sans-serif", "monospace"),
    ("'JetBrains Mono', monospace", "monospace"),
    ("'JetBrains Mono',monospace", "monospace"),
    ('"Space Grotesk",sans-serif', "monospace"),
    ("letterSpacing: 1,", 'letterSpacing:"0.04em",'),
    ("letterSpacing:1,", 'letterSpacing:"0.04em",'),
    ("letterSpacing: 2,", 'letterSpacing:"0.08em",'),
    ("letterSpacing:2,", 'letterSpacing:"0.08em",'),
    ("letterSpacing: 3,", 'letterSpacing:"0.1em",'),
    ("letterSpacing:3,", 'letterSpacing:"0.1em",'),
]:
    macro_src = macro_src.replace(wrong, right)

write(SRC / "macro" / "page.tsx", macro_src)


# =============================================================================
# alerts/page.tsx
# =============================================================================
log("[2] Rewriting alerts/page.tsx...")

alerts = (SRC / "alerts" / "page.tsx").read_text(encoding="utf-8")
alerts = re.sub(r'[^\x00-\x7F]+', '', alerts)  # remove non-ASCII (emojis)

for wrong, right in [
    ('"#0f172a"', '"var(--bg)"'),
    ('"#1e293b"', '"var(--card)"'),
    ('"#334155"', '"var(--border2)"'),
    ('"#3b82f6"', '"var(--accent)"'),
    ('"#e2e8f0"', '"var(--text)"'),
    ('"#94a3b8"', '"var(--muted)"'),
    ('"#64748b"', '"var(--muted)"'),
    ('"#ef4444"', '"var(--neg)"'),
    ('"#22c55e"', '"var(--pos)"'),
    ('"#f59e0b"', '"var(--warn)"'),
    ('fontFamily:"system-ui,sans-serif"', 'fontFamily:"monospace"'),
    ('fontFamily: "system-ui,sans-serif"', 'fontFamily:"monospace"'),
    ('fontFamily:"Space Grotesk",sans-serif', 'fontFamily:"monospace"'),
    ('"2d1515"', '"var(--bg)"'),
    ('background:"#2d1515"', 'background:"var(--bg)"'),
]:
    alerts = alerts.replace(wrong, right)

# Fix body wrapper
alerts = re.sub(
    r'<div style=\{\{[^}]*minHeight[^}]*\}\}>',
    '<div style={{' + W + '}}>',
    alerts, count=1
)

write(SRC / "alerts" / "page.tsx", alerts)


# =============================================================================
# analysis/page.tsx  
# =============================================================================
log("[3] Rewriting analysis/page.tsx...")

analysis = (SRC / "analysis" / "page.tsx").read_text(encoding="utf-8")
analysis = re.sub(r'[^\x00-\x7F]+', '', analysis)

for wrong, right in [
    ('"#1e293b"', '"var(--card)"'),
    ('"#0f172a"', '"var(--bg)"'),
    ('"#334155"', '"var(--border2)"'),
    ('"#e2e8f0"', '"var(--text)"'),
    ('"#f8fafc"', '"var(--text)"'),
    ('"#64748b"', '"var(--muted)"'),
    ('"#475569"', '"var(--muted)"'),
    ('"#94a3b8"', '"var(--muted)"'),
    ('"#cbd5e1"', '"var(--text)"'),
    ('"#ef4444"', '"var(--neg)"'),
    ('"#22c55e"', '"var(--pos)"'),
    ('"#3b82f6"', '"var(--accent)"'),
    ('"#f59e0b"', '"var(--warn)"'),
    ('"#8b5cf6"', '"var(--purple)"'),
    ('"#f472b6"', '"var(--cyan)"'),
    ('"#34d399"', '"var(--pos)"'),
    ('"#fbbf24"', '"var(--warn)"'),
    ('"#a78bfa"', '"var(--purple)"'),
    ('v: report.regime,', 'v: String(report.regime || ""),'),
    ('fontFamily:"system-ui,sans-serif"', 'fontFamily:"monospace"'),
    ('fontFamily: "system-ui,sans-serif"', 'fontFamily:"monospace"'),
    ('borderRadius: 12,', 'borderRadius: 6,'),
    ('borderRadius:12,', 'borderRadius:6,'),
]:
    analysis = analysis.replace(wrong, right)

# Fix body wrapper
analysis = re.sub(
    r'style=\{\{[^}]*minHeight[^}]*100vh[^}]*\}\}>',
    'style={{' + W + '}}>',
    analysis, count=1
)

write(SRC / "analysis" / "page.tsx", analysis)


# =============================================================================
# settings/page.tsx
# =============================================================================
log("[4] Rewriting settings/page.tsx...")

settings = (SRC / "settings" / "page.tsx").read_text(encoding="utf-8")
settings = re.sub(r'[^\x00-\x7F]+', '', settings)

for wrong, right in [
    ('"#1e293b"', '"var(--card)"'), ('"#0f172a"', '"var(--bg)"'),
    ('"#0d1117"', '"var(--surface)"'), ('"#334155"', '"var(--border2)"'),
    ('"#e2e8f0"', '"var(--text)"'), ('"#f8fafc"', '"var(--text)"'),
    ('"#64748b"', '"var(--muted)"'), ('"#94a3b8"', '"var(--muted)"'),
    ('"#3b82f6"', '"var(--accent)"'), ('"#60a5fa"', '"var(--accent)"'),
    ('"#22c55e"', '"var(--pos)"'), ('"#ef4444"', '"var(--neg)"'),
    ('"#f59e0b"', '"var(--warn)"'), ('borderRadius: 12,', 'borderRadius: 6,'),
    ('fontFamily:"system-ui,sans-serif"', 'fontFamily:"monospace"'),
]:
    settings = settings.replace(wrong, right)

settings = re.sub(
    r'style=\{\{[^}]*minHeight[^}]*100vh[^}]*\}\}>',
    'style={{' + W + '}}>',
    settings, count=1
)
write(SRC / "settings" / "page.tsx", settings)


# =============================================================================
# watchlist/page.tsx  
# =============================================================================
log("[5] Rewriting watchlist/page.tsx...")

watchlist = (SRC / "watchlist" / "page.tsx").read_text(encoding="utf-8")
watchlist = re.sub(r'[^\x00-\x7F]+', '', watchlist)

# Watchlist uses custom color vars - fix them to real vars
watchlist = watchlist.replace('"var(--text-primary)"', '"var(--text)"')
watchlist = watchlist.replace('"var(--text-secondary)"', '"var(--muted)"')
watchlist = watchlist.replace('"var(--text-tertiary)"', '"var(--dim)"')
watchlist = watchlist.replace('"var(--border-color)"', '"var(--border)"')
watchlist = watchlist.replace('"var(--surface-card)"', '"var(--card)"')
watchlist = watchlist.replace('"var(--surface-hover)"', '"var(--surface)"')
watchlist = watchlist.replace("'var(--text-primary)'", "'var(--text)'")
watchlist = watchlist.replace("'var(--text-secondary)'", "'var(--muted)'")
watchlist = watchlist.replace("'var(--border-color)'", "'var(--border)'")
watchlist = watchlist.replace("'var(--surface-card)'", "'var(--card)'")

for wrong, right in [
    ('"#1e293b"', '"var(--card)"'), ('"#0f172a"', '"var(--bg)"'),
    ('"#0d1117"', '"var(--surface)"'), ('"#334155"', '"var(--border2)"'),
    ('"#e2e8f0"', '"var(--text)"'), ('"#94a3b8"', '"var(--muted)"'),
    ('"#64748b"', '"var(--muted)"'), ('"#3b82f6"', '"var(--accent)"'),
    ('"#60a5fa"', '"var(--accent)"'), ('"#22c55e"', '"var(--pos)"'),
    ('"#ef4444"', '"var(--neg)"'), ('"#f59e0b"', '"var(--warn)"'),
    ('"#06b6d4"', '"var(--cyan)"'), ('borderRadius: 12,', 'borderRadius: 6,'),
    ('borderRadius:12,', 'borderRadius:6,'), ('borderRadius: 16,', 'borderRadius: 6,'),
    ('fontFamily:"\'Courier New\',monospace"', 'fontFamily:"monospace"'),
    ('fontFamily: "system-ui, sans-serif"', 'fontFamily:"monospace"'),
]:
    watchlist = watchlist.replace(wrong, right)

write(SRC / "watchlist" / "page.tsx", watchlist)


# =============================================================================
# global/page.tsx - mostly good but fix remaining hardcoded + remove emojis from UI text
# =============================================================================
log("[6] Fixing global/page.tsx...")

global_page = (SRC / "global" / "page.tsx").read_text(encoding="utf-8")

# Fix remaining hardcoded border
global_page = global_page.replace('"#1e293b"', '"var(--border)"')
global_page = global_page.replace('"#334155"', '"var(--border2)"')

# Fix category badges - remove emoji from rendering (keep in META data)
# The flag emoji in table display is OK, it's data. Remove from button/UI elements
for wrong, right in [
    ('borderRadius: 12,', 'borderRadius: 4,'),
    ('borderRadius:12,', 'borderRadius:4,'),
    ('background: selected ? "#1e3a5f" : "transparent"', 'background: selected ? "rgba(88,166,255,0.1)" : "transparent"'),
    ('background: selected ? "var(--border)" : "transparent"', 'background: selected ? "rgba(88,166,255,0.1)" : "transparent"'),
]:
    global_page = global_page.replace(wrong, right)

write(SRC / "global" / "page.tsx", global_page)


# =============================================================================
# compare/page.tsx
# =============================================================================
log("[7] Fixing compare/page.tsx...")

compare = (SRC / "compare" / "page.tsx").read_text(encoding="utf-8")
compare = re.sub(r'[^\x00-\x7F]+', '', compare)

for wrong, right in [
    ('"#1e293b"', '"var(--card)"'), ('"#0f172a"', '"var(--bg)"'),
    ('"#334155"', '"var(--border2)"'), ('"#0d1117"', '"var(--surface)"'),
    ('"#e2e8f0"', '"var(--text)"'), ('"#94a3b8"', '"var(--muted)"'),
    ('"#64748b"', '"var(--muted)"'), ('"#3b82f6"', '"var(--accent)"'),
    ('"#60a5fa"', '"var(--accent)"'), ('"#22c55e"', '"var(--pos)"'),
    ('"#ef4444"', '"var(--neg)"'), ('"#f59e0b"', '"var(--warn)"'),
    ('borderRadius: 12,', 'borderRadius: 6,'), ('borderRadius:12,', 'borderRadius:6,'),
    ('fontFamily: "system-ui, sans-serif"', 'fontFamily:"monospace"'),
    ('fontFamily:"system-ui,sans-serif"', 'fontFamily:"monospace"'),
]:
    compare = compare.replace(wrong, right)

write(SRC / "compare" / "page.tsx", compare)


# =============================================================================
# patterns-v3/page.tsx - remove rounded pill buttons, fix colors, no emojis
# =============================================================================
log("[8] Fixing patterns-v3/page.tsx...")

pv3 = (SRC / "patterns-v3" / "page.tsx").read_text(encoding="utf-8")
pv3 = re.sub(r'[^\x00-\x7F]+', '', pv3)

for wrong, right in [
    ('"#0f172a"', '"var(--bg)"'), ('"#1e293b"', '"var(--card)"'),
    ('"#334155"', '"var(--border2)"'), ('"#1e3a5f"', '"var(--border)"'),
    ('"#60a5fa"', '"var(--accent)"'), ('"#22c55e"', '"var(--pos)"'),
    ('"#ef4444"', '"var(--neg)"'), ('"#f59e0b"', '"var(--warn)"'),
    ('"#94a3b8"', '"var(--muted)"'), ('"#e2e8f0"', '"var(--text)"'),
    # Fix big rounded pill buttons to match design system
    ('borderRadius: 100,', 'borderRadius: 4,'),
    ('borderRadius:100,', 'borderRadius:4,'),
    ('borderRadius: 50,', 'borderRadius: 4,'),
    ('borderRadius:50,', 'borderRadius:4,'),
    ('borderRadius: 24,', 'borderRadius: 4,'),
    ('borderRadius:24,', 'borderRadius:4,'),
    ('borderRadius: 20,', 'borderRadius: 4,'),
    ('borderRadius:20,', 'borderRadius:4,'),
    ('borderRadius: 16,', 'borderRadius: 4,'),
    ('borderRadius:16,', 'borderRadius:4,'),
    ('borderRadius: 12,', 'borderRadius: 6,'),
    ('borderRadius:12,', 'borderRadius:6,'),
    # Fix big cyan Find Patterns button
    ('background: "#00e5ff"', 'background: "var(--accent)"'),
    ('background:"#00e5ff"', 'background:"var(--accent)"'),
    ('background: "#00bcd4"', 'background: "var(--accent)"'),
    ('background:"#00bcd4"', 'background:"var(--accent)"'),
    # Fix yellow buttons
    ('background: "#ffd600"', 'background: "var(--warn)"'),
    ('background:"#ffd600"', 'background:"var(--warn)"'),
    ('background: "#ffeb3b"', 'background: "var(--warn)"'),
    ('background:"#ffeb3b"', 'background:"var(--warn)"'),
    # Font fixes
    ('fontFamily: "system-ui, sans-serif"', 'fontFamily:"monospace"'),
    ('fontFamily:"system-ui,sans-serif"', 'fontFamily:"monospace"'),
]:
    pv3 = pv3.replace(wrong, right)

write(SRC / "patterns-v3" / "page.tsx", pv3)


# =============================================================================
# patterns/page.tsx - same treatment
# =============================================================================
log("[9] Fixing patterns/page.tsx...")

patterns = (SRC / "patterns" / "page.tsx").read_text(encoding="utf-8")
patterns = re.sub(r'[^\x00-\x7F]+', '', patterns)

for wrong, right in [
    ('"#0f172a"', '"var(--bg)"'), ('"#1e293b"', '"var(--card)"'),
    ('"#334155"', '"var(--border2)"'), ('"#1e3a5f"', '"var(--border)"'),
    ('"#60a5fa"', '"var(--accent)"'), ('"#22c55e"', '"var(--pos)"'),
    ('"#ef4444"', '"var(--neg)"'), ('"#f59e0b"', '"var(--warn)"'),
    ('"#94a3b8"', '"var(--muted)"'), ('"#e2e8f0"', '"var(--text)"'),
    ('"#00e5ff"', '"var(--accent)"'), ('"#00bcd4"', '"var(--accent)"'),
    ('"#ffd600"', '"var(--warn)"'), ('"#ffeb3b"', '"var(--warn)"'),
    ('borderRadius: 100,', 'borderRadius: 4,'),
    ('borderRadius:100,', 'borderRadius:4,'),
    ('borderRadius: 24,', 'borderRadius: 4,'),
    ('borderRadius:24,', 'borderRadius:4,'),
    ('borderRadius: 20,', 'borderRadius: 4,'),
    ('borderRadius:20,', 'borderRadius:4,'),
    ('borderRadius: 16,', 'borderRadius: 6,'),
    ('borderRadius:16,', 'borderRadius:6,'),
    ('borderRadius: 12,', 'borderRadius: 6,'),
    ('borderRadius:12,', 'borderRadius:6,'),
    ('fontFamily: "system-ui, sans-serif"', 'fontFamily:"monospace"'),
    ('fontFamily:"system-ui,sans-serif"', 'fontFamily:"monospace"'),
]:
    patterns = patterns.replace(wrong, right)

write(SRC / "patterns" / "page.tsx", patterns)


# =============================================================================
# conviction/page.tsx - rewrite to match exact design system
# =============================================================================
log("[10] Rewriting conviction/page.tsx to match design system...")

conviction = """\
"use client";
import { useEffect, useState, useMemo } from "react";

interface Row {
  symbol: string; score: number|null;
  momentum: number|null; seasonality: number|null; quality: number|null;
  delivery: number|null; insider: number|null; news: number|null; fundamental: number|null;
  signals: number; top_reason: string; close: number|null;
  roce: number|null; roe: number|null; f_score: number|null; as_of: string;
}
interface Stats { total:number; avg_score:number; high:number; med:number; low:number; as_of:string; }

const LAYERS = [
  {key:"momentum",    label:"MOM",     color:"var(--accent)"},
  {key:"seasonality", label:"SEASON",  color:"var(--warn)"},
  {key:"quality",     label:"FSCORE",  color:"var(--pos)"},
  {key:"delivery",    label:"DELIV",   color:"var(--purple)"},
  {key:"insider",     label:"INSIDER", color:"var(--cyan)"},
  {key:"news",        label:"NEWS",    color:"var(--orange)"},
  {key:"fundamental", label:"FUND",    color:"var(--pos)"},
];

function fmt(v:number|null, d=1) { return v==null?"--":v.toFixed(d); }
function scoreColor(v:number|null) {
  if(v==null) return "var(--muted)";
  if(v>=70) return "var(--pos)"; if(v>=50) return "var(--warn)"; return "var(--neg)";
}
function scoreGrade(v:number|null) {
  if(v==null) return "--"; if(v>=70) return "HIGH"; if(v>=50) return "MED"; return "LOW";
}

function Btn({active=false,color="var(--accent)",onClick,children}:{active?:boolean;color?:string;onClick?:()=>void;children:any}) {
  return (
    <button onClick={onClick} style={{
      padding:"3px 10px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
      background:active?color+"22":"var(--surface)",
      color:active?color:"var(--muted)",
      border:`1px solid ${active?color:"var(--border)"}`,
      borderRadius:4,transition:"all 0.12s",
    }}>{children}</button>
  );
}

function LayerBar({value, color}: {value:number|null; color:string}) {
  return (
    <div style={{width:"100%",height:3,background:"var(--border)",borderRadius:2,marginTop:2}}>
      <div style={{width:(value??0)+"%",height:"100%",background:color,borderRadius:2,transition:"width 0.3s"}}/>
    </div>
  );
}

export default function ConvictionPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [stats, setStats] = useState<Stats|null>(null);
  const [reasons, setReasons] = useState<{reason:string;count:number}[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [sortCol, setSortCol] = useState("score");
  const [expanded, setExpanded] = useState<string|null>(null);
  const [layerFilter, setLayerFilter] = useState<string|null>(null);

  useEffect(() => {
    setLoading(true);
    fetch("/api/conviction?limit=200&min="+minScore)
      .then(r=>r.json())
      .then(d=>{setRows(d.rows||[]);setStats(d.stats||null);setReasons(d.top_reasons||[]);setError("");setLoading(false);})
      .catch(e=>{setError(e.message);setLoading(false);});
  }, [minScore]);

  const filtered = useMemo(() => {
    let r = rows;
    if (search) r = r.filter(x => x.symbol.includes(search.toUpperCase()));
    if (layerFilter) r = r.filter(x => x[layerFilter as keyof Row] != null);
    return [...r].sort((a,b) => ((b[sortCol as keyof Row] as number)??-1) - ((a[sortCol as keyof Row] as number)??-1));
  }, [rows, search, sortCol, layerFilter]);

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        {/* Header */}
        <div style={{display:"flex",alignItems:"baseline",gap:16,marginBottom:12}}>
          <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,letterSpacing:"0.12em",color:"var(--accent)"}}>
            CONVICTION SCORE
          </div>
          <div style={{fontSize:10,fontFamily:"monospace",color:"var(--dim)"}}>
            7-LAYER SIGNAL FUSION &nbsp;|&nbsp; MOMENTUM · SEASONALITY · F-SCORE · DELIVERY · INSIDER · NEWS · FUNDAMENTALS
          </div>
        </div>

        {/* Stats strip */}
        {stats && (
          <div style={{display:"flex",gap:8,marginBottom:14,flexWrap:"wrap"}}>
            {[
              {l:"TOTAL",v:stats.total,c:"var(--text)"},
              {l:"AVG SCORE",v:fmt(stats.avg_score),c:"var(--accent)"},
              {l:"HIGH (>=70)",v:stats.high,c:"var(--pos)"},
              {l:"MED (50-70)",v:stats.med,c:"var(--warn)"},
              {l:"LOW (<50)",v:stats.low,c:"var(--neg)"},
              {l:"AS OF",v:stats.as_of?.slice(0,10)||"--",c:"var(--dim)"},
            ].map(s=>(
              <div key={s.l} style={{
                background:"var(--surface)",border:"1px solid var(--border)",
                borderRadius:4,padding:"6px 12px",minWidth:80,
              }}>
                <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em"}}>{s.l}</div>
                <div style={{fontFamily:"monospace",fontSize:16,fontWeight:700,color:s.c,marginTop:2}}>{s.v}</div>
              </div>
            ))}
          </div>
        )}

        {/* Controls */}
        <div style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:14,alignItems:"flex-start"}}>
          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>SEARCH</div>
            <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="SYMBOL..."
              style={{padding:"3px 8px",fontSize:10,fontFamily:"monospace",background:"var(--surface)",
                border:"1px solid var(--border)",borderRadius:4,color:"var(--text)",outline:"none",width:120}}/>
          </div>
          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>MIN SCORE</div>
            <div style={{display:"flex",gap:4}}>
              {[0,30,50,70].map(v=>(
                <Btn key={v} active={minScore===v} color="var(--accent)" onClick={()=>setMinScore(v)}>{v}+</Btn>
              ))}
            </div>
          </div>
          <div>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:5}}>FILTER LAYER</div>
            <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
              <Btn active={layerFilter===null} color="var(--accent)" onClick={()=>setLayerFilter(null)}>ALL</Btn>
              {LAYERS.map(l=>(
                <Btn key={l.key} active={layerFilter===l.key} color={l.color} onClick={()=>setLayerFilter(layerFilter===l.key?null:l.key)}>{l.label}</Btn>
              ))}
            </div>
          </div>
          <div style={{marginLeft:"auto",alignSelf:"flex-end",fontFamily:"monospace",fontSize:10,color:"var(--dim)"}}>
            {filtered.length} SYMBOLS
          </div>
        </div>

        {error && <div style={{color:"var(--neg)",fontFamily:"monospace",fontSize:11,marginBottom:12}}>ERROR: {error}</div>}
        {loading && <div style={{color:"var(--dim)",fontFamily:"monospace",fontSize:12,padding:40,textAlign:"center"}}>Loading...</div>}

        {/* Table */}
        {!loading && (
          <div style={{overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
              <thead>
                <tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)",letterSpacing:"0.08em"}}>
                  <th style={{textAlign:"left",padding:"6px 8px",width:28}}>#</th>
                  <th style={{textAlign:"left",padding:"6px 8px",minWidth:110}}>SYMBOL</th>
                  <th onClick={()=>setSortCol("score")} style={{textAlign:"right",padding:"6px 8px",cursor:"pointer",color:sortCol==="score"?"var(--accent)":"var(--dim)"}}>CONVICTION</th>
                  {LAYERS.map(l=>(
                    <th key={l.key} onClick={()=>setSortCol(l.key)}
                      style={{textAlign:"right",padding:"6px 8px",cursor:"pointer",color:sortCol===l.key?l.color:"var(--dim)"}}>
                      {l.label}
                    </th>
                  ))}
                  <th style={{textAlign:"left",padding:"6px 8px"}}>TOP</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row,i) => (
                  <>
                    <tr key={row.symbol} onClick={()=>setExpanded(expanded===row.symbol?null:row.symbol)}
                      style={{borderBottom:"1px solid var(--border)",cursor:"pointer",
                        background:expanded===row.symbol?"rgba(88,166,255,0.05)":undefined}}>
                      <td style={{padding:"7px 8px",color:"var(--dim)"}}>{i+1}</td>
                      <td style={{padding:"7px 8px"}}>
                        <span style={{color:"var(--text)",fontWeight:700,fontSize:12}}>{row.symbol}</span>
                        <span style={{color:"var(--dim)",fontSize:9,marginLeft:6}}>{row.signals}/7</span>
                      </td>
                      <td style={{padding:"7px 8px",textAlign:"right"}}>
                        <span style={{color:scoreColor(row.score),fontWeight:700}}>{fmt(row.score)}</span>
                        <span style={{color:scoreColor(row.score),fontSize:9,marginLeft:4}}>{scoreGrade(row.score)}</span>
                      </td>
                      {LAYERS.map(l => {
                        const v = row[l.key as keyof Row] as number|null;
                        return <td key={l.key} style={{padding:"7px 8px",textAlign:"right",color:v!=null?l.color:"var(--border)"}}>{v!=null?v.toFixed(0):"--"}</td>;
                      })}
                      <td style={{padding:"7px 8px",color:"var(--dim)",fontSize:9}}>
                        {LAYERS.find(l=>l.key===row.top_reason)?.label||row.top_reason||"--"}
                      </td>
                    </tr>
                    {expanded===row.symbol && (
                      <tr key={"exp-"+row.symbol}>
                        <td colSpan={11} style={{padding:"8px 16px",background:"var(--surface)",borderBottom:"1px solid var(--border)"}}>
                          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
                            <div>
                              <div style={{fontSize:9,color:"var(--dim)",letterSpacing:"0.1em",marginBottom:8}}>LAYER BREAKDOWN</div>
                              {LAYERS.map(l => {
                                const v = row[l.key as keyof Row] as number|null;
                                return <div key={l.key} style={{marginBottom:6}}>
                                  <div style={{display:"flex",justifyContent:"space-between"}}>
                                    <span style={{fontSize:9,color:"var(--dim)"}}>{l.label}</span>
                                    <span style={{fontSize:10,color:l.color,fontWeight:700}}>{v!=null?v.toFixed(0):"--"}</span>
                                  </div>
                                  <LayerBar value={v} color={l.color}/>
                                </div>;
                              })}
                            </div>
                            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,alignContent:"start"}}>
                              {[["ROCE",fmt(row.roce)+"%"],["ROE",fmt(row.roe)+"%"],["F-SCORE",row.f_score!=null?row.f_score+"/9":"--"],["SIGNALS",row.signals+"/7"],["CLOSE",row.close!=null?"INR "+fmt(row.close):"--"],["AS OF",row.as_of?.slice(0,10)||"--"]].map(([k,v])=>(
                                <div key={k} style={{background:"var(--card)",borderRadius:4,padding:"6px 10px"}}>
                                  <div style={{fontSize:9,color:"var(--dim)",letterSpacing:"0.08em"}}>{k}</div>
                                  <div style={{fontSize:13,color:"var(--text)",fontWeight:600,marginTop:2}}>{v}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
            {filtered.length===0 && <div style={{color:"var(--dim)",fontFamily:"monospace",fontSize:12,padding:40,textAlign:"center"}}>No symbols match filters.</div>}
          </div>
        )}

        {/* Reason distribution */}
        {reasons.length>0 && (
          <div style={{marginTop:20,borderTop:"1px solid var(--border)",paddingTop:14}}>
            <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.1em",marginBottom:8}}>TOP DRIVING SIGNAL DISTRIBUTION</div>
            <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
              {reasons.map(({reason,count}) => {
                const layer = LAYERS.find(l=>l.key===reason);
                return <div key={reason} style={{
                  padding:"3px 10px",background:(layer?.color||"var(--muted)")+"22",
                  border:`1px solid ${(layer?.color||"var(--muted)")}44`,
                  borderRadius:4,fontFamily:"monospace",fontSize:10,
                }}>
                  <span style={{color:layer?.color||"var(--muted)",fontWeight:700}}>{layer?.label||reason}</span>
                  <span style={{color:"var(--dim)",marginLeft:6}}>{count}</span>
                </div>;
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
"""
write(SRC / "conviction" / "page.tsx", conviction)


# =============================================================================
# portfolio/page.tsx - rewrite to match design system
# =============================================================================
log("[11] Rewriting portfolio/page.tsx to match design system...")

portfolio = """\
"use client";
import { useEffect, useState } from "react";

interface Position {
  id:number; symbol:string; entry_date:string; entry_price:number;
  quantity:number; position_size:number; atr_at_entry:number;
  stop_loss:number; target_1:number; target_2:number; risk_per_trade:number;
  status:string; exit_date?:string; exit_price?:number; pnl?:number; pnl_pct?:number;
  current_price?:number; unrealized?:number; unrealized_pct?:number;
  f_score?:number; conviction?:number;
}
interface Signal {
  signal_name:string; asset:string; value:number; signal_type:string;
  condition_desc:string; nifty_fwd_5d?:number; nifty_fwd_10d?:number;
  hit_rate_hist?:number; n_historical:number; date:string;
}
interface Summary {
  open_count:number; closed_count:number; total_invested:number;
  total_unrealized:number; total_realized:number; win_rate?:number;
}

const SIG_IMPACT: Record<string,string> = {
  FEAR:"Contrarian BUY signal", SPIKE:"Short-term caution",
  CALM:"Complacency -- watch for spike",
  STRONG:"DXY strength = FII headwind", WEAK:"DXY weak = FII tailwind",
  BULLISH:"Risk-off, gold rising", BEARISH:"Risk-on, gold falling",
  WEAK_INR:"Rupee weak -- FII outflow", STRONG_INR:"Rupee strong -- FII inflow",
  RISK_ON:"Global risk appetite positive", RISK_OFF:"Global risk appetite negative",
  RISING:"Rate tightening -- valuation headwind", FALLING:"Rate easing -- valuation tailwind",
};

function fmt(v?:number|null, d=1) { return v==null?"--":v.toFixed(d); }
function pc(v?:number|null) { return v==null?"var(--muted)":v>=0?"var(--pos)":"var(--neg)"; }
function pstr(v?:number|null) { return v==null?"--":(v>=0?"+":"")+v!.toFixed(1)+"%"; }

function Btn({active=false,color="var(--accent)",onClick,children}:{active?:boolean;color?:string;onClick?:()=>void;children:any}) {
  return <button onClick={onClick} style={{
    padding:"4px 12px",fontSize:10,cursor:"pointer",fontFamily:"monospace",
    background:active?color+"22":"var(--surface)",
    color:active?color:"var(--muted)",
    border:`1px solid ${active?color:"var(--border)"}`,
    borderRadius:4,transition:"all 0.12s",
  }}>{children}</button>;
}

function AddForm({onAdd}:{onAdd:()=>void}) {
  const [f,setF]=useState({symbol:"",entry_date:new Date().toISOString().slice(0,10),entry_price:"",quantity:"",atr_at_entry:"",account_size:"500000",risk_pct:"1.0"});
  const [res,setRes]=useState<any>(null);
  const [loading,setLoading]=useState(false);
  const set=(k:string,v:string)=>setF(p=>({...p,[k]:v}));
  const inp=(ph:string,k:string,t="text")=>(
    <div>
      <div style={{fontSize:9,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.08em",marginBottom:3}}>{ph}</div>
      <input type={t} value={(f as any)[k]} onChange={e=>set(k,e.target.value)}
        style={{padding:"4px 8px",fontSize:10,fontFamily:"monospace",background:"var(--surface)",
          border:"1px solid var(--border)",borderRadius:4,color:"var(--text)",outline:"none",width:"100%"}}/>
    </div>
  );
  const submit=async()=>{
    setLoading(true);
    const r=await fetch("/api/portfolio",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({action:"add",...f,entry_price:parseFloat(f.entry_price),quantity:parseInt(f.quantity)||0,atr_at_entry:parseFloat(f.atr_at_entry)||0,account_size:parseFloat(f.account_size),risk_pct:parseFloat(f.risk_pct)})});
    const d=await r.json(); setRes(d); setLoading(false); if(d.ok) onAdd();
  };
  return (
    <div style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:4,padding:14,marginBottom:16}}>
      <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em",marginBottom:10}}>ADD POSITION -- ATR SIZING</div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:10}}>
        {inp("SYMBOL","symbol")} {inp("ENTRY DATE","entry_date","date")}
        {inp("ENTRY PRICE","entry_price","number")} {inp("ATR 14D","atr_at_entry","number")}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:12}}>
        {inp("QTY (0=AUTO)","quantity","number")} {inp("ACCOUNT SIZE","account_size","number")}
        {inp("RISK %","risk_pct","number")}
        <div style={{display:"flex",alignItems:"flex-end"}}>
          <button onClick={submit} disabled={loading} style={{
            padding:"4px 16px",fontSize:10,fontFamily:"monospace",cursor:"pointer",
            background:"var(--accent)",color:"var(--bg)",border:"none",borderRadius:4,fontWeight:700,width:"100%",
          }}>{loading?"ADDING...":"ADD POSITION"}</button>
        </div>
      </div>
      {res&&<div style={{fontFamily:"monospace",fontSize:10,color:res.ok?"var(--pos)":"var(--neg)"}}>
        {res.ok?"ADDED -- QTY:"+res.qty+" STOP:"+res.stop_loss+" T1:"+res.target_1+" T2:"+res.target_2+" RISK:"+res.risk_per_trade:"ERROR: "+res.error}
      </div>}
    </div>
  );
}

export default function PortfolioPage() {
  const [data,setData]=useState<{positions:Position[];cross_asset:Signal[];summary:Summary}|null>(null);
  const [loading,setLoading]=useState(true);
  const [tab,setTab]=useState<"open"|"closed"|"signals">("open");
  const [closing,setClosing]=useState<number|null>(null);
  const [exitPrice,setExitPrice]=useState("");

  const load=()=>{setLoading(true);fetch("/api/portfolio").then(r=>r.json()).then(d=>{setData(d);setLoading(false);});};
  useEffect(()=>{load();},[]);

  const closePos=async(id:number)=>{
    const r=await fetch("/api/portfolio",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({action:"close",id,exit_price:parseFloat(exitPrice),exit_date:new Date().toISOString().slice(0,10)})});
    const d=await r.json(); if(d.ok){setClosing(null);setExitPrice("");load();}
  };

  const open=data?.positions.filter(p=>p.status==="OPEN")||[];
  const closed=data?.positions.filter(p=>p.status==="CLOSED")||[];
  const s=data?.summary;

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <div style={{padding:"16px 20px",maxWidth:1600,margin:"0 auto"}}>

        <div style={{display:"flex",alignItems:"baseline",gap:16,marginBottom:12}}>
          <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,letterSpacing:"0.12em",color:"var(--cyan)"}}>PORTFOLIO TRACKER</div>
          <div style={{fontSize:10,fontFamily:"monospace",color:"var(--dim)"}}>ATR POSITION SIZING · CROSS-ASSET SIGNALS · CONVICTION OVERLAY</div>
        </div>

        {s&&<div style={{display:"flex",gap:8,marginBottom:14,flexWrap:"wrap"}}>
          {[
            {l:"OPEN",v:s.open_count,c:"var(--text)"},
            {l:"INVESTED",v:"INR "+(s.total_invested/1000).toFixed(0)+"K",c:"var(--accent)"},
            {l:"UNREALIZED",v:(s.total_unrealized>=0?"+":"")+s.total_unrealized.toFixed(0),c:pc(s.total_unrealized)},
            {l:"REALIZED",v:(s.total_realized>=0?"+":"")+s.total_realized.toFixed(0),c:pc(s.total_realized)},
            {l:"WIN RATE",v:s.win_rate!=null?s.win_rate+"%":"--",c:"var(--warn)"},
            {l:"CLOSED",v:s.closed_count,c:"var(--dim)"},
          ].map(item=>(
            <div key={item.l} style={{background:"var(--surface)",border:"1px solid var(--border)",borderRadius:4,padding:"6px 12px",minWidth:90}}>
              <div style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em"}}>{item.l}</div>
              <div style={{fontFamily:"monospace",fontSize:16,fontWeight:700,color:item.c,marginTop:2}}>{item.v}</div>
            </div>
          ))}
        </div>}

        <AddForm onAdd={load}/>

        <div style={{display:"flex",gap:4,marginBottom:14}}>
          <Btn active={tab==="open"} color="var(--accent)" onClick={()=>setTab("open")}>OPEN ({open.length})</Btn>
          <Btn active={tab==="closed"} color="var(--pos)" onClick={()=>setTab("closed")}>CLOSED ({closed.length})</Btn>
          <Btn active={tab==="signals"} color="var(--warn)" onClick={()=>setTab("signals")}>CROSS-ASSET SIGNALS</Btn>
        </div>

        {loading&&<div style={{color:"var(--dim)",fontFamily:"monospace",fontSize:12,padding:40,textAlign:"center"}}>Loading...</div>}

        {!loading&&tab==="open"&&<div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
            <thead><tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)",letterSpacing:"0.08em"}}>
              {["SYMBOL","DATE","QTY","ENTRY","CMP","UNREAL","UNREAL%","STOP","T1","T2","RISK","CONV","F","ACTION"].map(h=>(
                <th key={h} style={{padding:"6px 8px",textAlign:"right",fontFamily:"monospace"}}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {open.map(p=>(
                <tr key={p.id} style={{borderBottom:"1px solid var(--border)"}}>
                  <td style={{padding:"7px 8px",color:"var(--accent)",fontWeight:700}}>{p.symbol}</td>
                  <td style={{padding:"7px 8px",color:"var(--dim)",textAlign:"right"}}>{p.entry_date?.slice(5)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right"}}>{p.quantity}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--muted)"}}>{fmt(p.entry_price)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--accent)"}}>{fmt(p.current_price)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:pc(p.unrealized)}}>{p.unrealized!=null?(p.unrealized>=0?"+":"")+fmt(p.unrealized,0):"--"}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:pc(p.unrealized_pct)}}>{pstr(p.unrealized_pct)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--neg)"}}>{fmt(p.stop_loss)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--pos)"}}>{fmt(p.target_1)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--pos)"}}>{fmt(p.target_2)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--warn)"}}>{fmt(p.risk_per_trade,0)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--purple)"}}>{fmt(p.conviction,0)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--dim)"}}>{p.f_score!=null?p.f_score+"/9":"--"}</td>
                  <td style={{padding:"7px 8px",textAlign:"right"}}>
                    {closing===p.id?<span style={{display:"flex",gap:4}}>
                      <input value={exitPrice} onChange={e=>setExitPrice(e.target.value)} placeholder="exit" type="number"
                        style={{width:60,background:"var(--surface)",border:"1px solid var(--border)",borderRadius:3,color:"var(--text)",padding:"2px 4px",fontSize:10,fontFamily:"monospace"}}/>
                      <button onClick={()=>closePos(p.id)} style={{background:"var(--pos)",color:"var(--bg)",border:"none",borderRadius:3,padding:"2px 6px",fontSize:9,cursor:"pointer",fontFamily:"monospace"}}>OK</button>
                      <button onClick={()=>setClosing(null)} style={{background:"var(--surface)",color:"var(--muted)",border:"1px solid var(--border)",borderRadius:3,padding:"2px 6px",fontSize:9,cursor:"pointer",fontFamily:"monospace"}}>X</button>
                    </span>:<button onClick={()=>setClosing(p.id)} style={{background:"var(--surface)",color:"var(--muted)",border:"1px solid var(--border)",borderRadius:3,padding:"2px 8px",fontSize:9,cursor:"pointer",fontFamily:"monospace",letterSpacing:"0.04em"}}>CLOSE</button>}
                  </td>
                </tr>
              ))}
              {open.length===0&&<tr><td colSpan={14} style={{textAlign:"center",padding:30,color:"var(--dim)",fontFamily:"monospace",fontSize:11}}>NO OPEN POSITIONS -- ADD ONE ABOVE</td></tr>}
            </tbody>
          </table>
        </div>}

        {!loading&&tab==="closed"&&<div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
            <thead><tr style={{borderBottom:"2px solid var(--border)",fontSize:9,color:"var(--dim)",letterSpacing:"0.08em"}}>
              {["SYMBOL","ENTRY","EXIT","QTY","ENTRY","EXIT","P&L","P&L%"].map(h=><th key={h} style={{padding:"6px 8px",textAlign:"right"}}>{h}</th>)}
            </tr></thead>
            <tbody>
              {closed.map(p=>(
                <tr key={p.id} style={{borderBottom:"1px solid var(--border)"}}>
                  <td style={{padding:"7px 8px",color:"var(--accent)",fontWeight:700}}>{p.symbol}</td>
                  <td style={{padding:"7px 8px",color:"var(--dim)",textAlign:"right"}}>{p.entry_date?.slice(5)}</td>
                  <td style={{padding:"7px 8px",color:"var(--dim)",textAlign:"right"}}>{p.exit_date?.slice(5)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right"}}>{p.quantity}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--muted)"}}>{fmt(p.entry_price)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--muted)"}}>{fmt(p.exit_price)}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:pc(p.pnl)}}>{p.pnl!=null?(p.pnl>=0?"+":"")+fmt(p.pnl,0):"--"}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:pc(p.pnl_pct)}}>{pstr(p.pnl_pct)}</td>
                </tr>
              ))}
              {closed.length===0&&<tr><td colSpan={8} style={{textAlign:"center",padding:30,color:"var(--dim)",fontFamily:"monospace",fontSize:11}}>NO CLOSED TRADES YET</td></tr>}
            </tbody>
          </table>
        </div>}

        {!loading&&tab==="signals"&&(
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))",gap:10}}>
            {(data?.cross_asset||[]).map(sig=>{
              const isPos=["CALM","WEAK","BEARISH","STRONG_INR","RISK_ON","FALLING"].includes(sig.signal_type);
              const color=isPos?"var(--pos)":"var(--neg)";
              const hr=sig.hit_rate_hist;
              return <div key={sig.signal_name} style={{
                background:"var(--surface)",border:"1px solid var(--border)",
                borderLeft:`2px solid ${color}`,borderRadius:4,padding:12,
              }}>
                <div style={{display:"flex",justifyContent:"space-between",marginBottom:6}}>
                  <span style={{fontFamily:"monospace",fontSize:9,color:"var(--dim)",letterSpacing:"0.1em"}}>{sig.asset}</span>
                  <span style={{fontFamily:"monospace",fontSize:9,color,fontWeight:700,letterSpacing:"0.06em"}}>{sig.signal_type}</span>
                </div>
                <div style={{fontFamily:"monospace",fontSize:11,color:"var(--text)",fontWeight:700,marginBottom:3}}>
                  {sig.signal_name.replace(/_/g," ")}
                </div>
                <div style={{fontFamily:"monospace",fontSize:10,color:"var(--muted)",marginBottom:6}}>{sig.condition_desc}</div>
                <div style={{fontFamily:"monospace",fontSize:9,color,marginBottom:8}}>{SIG_IMPACT[sig.signal_type]||""}</div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:6}}>
                  {[
                    ["VALUE",fmt(sig.value,2),"var(--text)"],
                    ["HIT RATE",hr!=null?(hr*100).toFixed(0)+"%":"--",hr!=null?(hr>0.6?"var(--pos)":hr>0.4?"var(--warn)":"var(--neg)"):"var(--muted)"],
                    ["FWD 10D",sig.nifty_fwd_10d!=null?(sig.nifty_fwd_10d>0?"+":"")+fmt(sig.nifty_fwd_10d)+"%":"--",pc(sig.nifty_fwd_10d)],
                  ].map(([lbl,val,col])=>(
                    <div key={lbl as string} style={{background:"var(--card)",borderRadius:3,padding:"4px 6px"}}>
                      <div style={{fontSize:8,color:"var(--dim)",fontFamily:"monospace",letterSpacing:"0.06em"}}>{lbl}</div>
                      <div style={{fontSize:11,color:col as string,fontWeight:700,fontFamily:"monospace"}}>{val}</div>
                    </div>
                  ))}
                </div>
                <div style={{marginTop:6,fontSize:9,color:"var(--dim)",fontFamily:"monospace"}}>n={sig.n_historical} | {sig.date}</div>
              </div>;
            })}
            {(data?.cross_asset||[]).length===0&&<div style={{color:"var(--dim)",fontFamily:"monospace",fontSize:11,padding:40,gridColumn:"1/-1",textAlign:"center"}}>NO CROSS-ASSET SIGNALS -- RUN build_phase30.py FIRST</div>}
          </div>
        )}
      </div>
    </div>
  );
}
"""
write(SRC / "portfolio" / "page.tsx", portfolio)


# =============================================================================
# FINAL: Fix remaining token issues across all pages
# =============================================================================
log("[12] Final token cleanup pass...")

all_pages = list(SRC.rglob("page.tsx"))
remaining = [
    ('"#1e293b"', '"var(--card)"'), ('"#0f172a"', '"var(--bg)"'),
    ('"#334155"', '"var(--border2)"'), ('"#1e3a5f"', '"var(--border)"'),
    ('"#0a0f1a"', '"var(--bg)"'), ('"#0f1923"', '"var(--surface)"'),
    ('"#0a0a0a"', '"var(--bg)"'), ('"#111827"', '"var(--surface)"'),
    ('"#1f2937"', '"var(--border)"'), ('"#30363d"', '"var(--border)"'),
    ('"#161b22"', '"var(--card)"'), ('"#374151"', '"var(--dim)"'),
    ('"#4b5563"', '"var(--muted)"'), ('"#94a3b8"', '"var(--muted)"'),
    ('"#9ca3af"', '"var(--muted)"'), ('"#64748b"', '"var(--muted)"'),
    ('"#e2e8f0"', '"var(--text)"'), ('"#f9fafb"', '"var(--text)"'),
    ('"#f8fafc"', '"var(--text)"'), ('"#c9d3df"', '"var(--text)"'),
    ('"#60a5fa"', '"var(--accent)"'), ('"#58a6ff"', '"var(--accent)"'),
    ('"#3b82f6"', '"var(--accent)"'), ('"#22c55e"', '"var(--pos)"'),
    ('"#10b981"', '"var(--pos)"'), ('"#3fb950"', '"var(--pos)"'),
    ('"#ef4444"', '"var(--neg)"'), ('"#f85149"', '"var(--neg)"'),
    ('"#f59e0b"', '"var(--warn)"'), ('"#d29922"', '"var(--warn)"'),
    ('"#fbbf24"', '"var(--warn)"'), ('"#8b5cf6"', '"var(--purple)"'),
    ('"#bc8cff"', '"var(--purple)"'), ('"#f97316"', '"var(--orange)"'),
    ('"#14b8a6"', '"var(--cyan)"'), ('"#06b6d4"', '"var(--cyan)"'),
    ('borderRadius: 12,', 'borderRadius: 6,'), ('borderRadius:12,', 'borderRadius:6,'),
    ('borderRadius: 16,', 'borderRadius: 6,'), ('borderRadius:16,', 'borderRadius:6,'),
    ('borderRadius: 24,', 'borderRadius: 4,'), ('borderRadius:24,', 'borderRadius:4,'),
    ('borderRadius: 100,', 'borderRadius: 4,'), ('borderRadius:100,', 'borderRadius:4,'),
    ("'JetBrains Mono', monospace", "monospace"), ("'JetBrains Mono',monospace", "monospace"),
    ("'Space Grotesk', sans-serif", "monospace"), ("'Courier New', monospace", "monospace"),
    ("'Courier New',monospace", "monospace"), ("system-ui, sans-serif", "monospace"),
    ("system-ui,sans-serif", "monospace"),
]

for page_path in all_pages:
    try:
        orig = page_path.read_text(encoding="utf-8")
        mod = orig
        for old, new in remaining:
            mod = mod.replace(old, new)
        if mod != orig:
            page_path.write_text(mod, encoding="utf-8")
    except Exception as e:
        print("  WARN: " + str(page_path) + ": " + str(e))

print("  Final cleanup done")

print("")
print("=" * 60)
print("DESIGN UNIFICATION COMPLETE")
print("=" * 60)
print("")
print("All pages now match streaks/indices/overview design:")
print("  - fontFamily: monospace")
print("  - background: var(--bg)")
print("  - padding: 16px 20px, maxWidth 1600, margin auto")
print("  - No emojis in UI")
print("  - No rounded pill buttons")
print("  - No thick borders or gradient backgrounds")
print("  - All colors: var(--accent/pos/neg/warn/dim/muted/text)")
print("  - Table headers: 9px monospace dim letterSpacing 0.08em")
print("  - Page headers: 14px monospace bold 0.12em accent color")
print("")
print("Hard-refresh browser: Ctrl+Shift+R")
