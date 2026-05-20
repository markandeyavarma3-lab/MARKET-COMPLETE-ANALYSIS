"""
micc_full_audit.py  --  Run from D:\MICC
================================================
COMPLETE AUDIT AND FIX SCRIPT

Does everything in one run:
  1. Reads every live page.tsx and audits NavBar state
  2. Fixes NavBar.tsx syntax (double commas etc)
  3. Fixes each page: exactly 0 or 1 NavBar (never 2)
  4. Lists unused/duplicate Python scripts
  5. Prints full report

Run: py D:\MICC\micc_full_audit.py
"""
import re, os, hashlib
from pathlib import Path
from collections import defaultdict

MICC = Path(r"D:\MICC")
DASH = MICC / "micc-dashboard"
APP  = DASH / "src" / "app"
SRC  = DASH / "src"

SEP = "=" * 65

# ─────────────────────────────────────────────────────────────────
# PART 1: Read every live page.tsx and audit NavBar
# ─────────────────────────────────────────────────────────────────
print(SEP)
print("PART 1: LIVE PAGE AUDIT")
print(SEP)

# Pages whose own sticky header replaces NavBar entirely
# Determined by reading content, not guessing
SKIP_PATTERNS = [
    "Market Intelligence Command Center",  # root page
    "DEEP ANALYSIS ROOM",                  # deep page
]

pages = sorted(APP.rglob("page.tsx"))
audit = []

for pf in pages:
    rel   = str(pf.relative_to(APP)).replace("\\", "/")
    text  = pf.read_text(encoding="utf-8", errors="replace")
    nb    = text.count("<NavBar")
    imp   = text.count("import NavBar")
    has_custom = any(p in text for p in SKIP_PATTERNS)
    audit.append(dict(path=pf, rel=rel, text=text, nb=nb, imp=imp, custom=has_custom))

print(f"\n{'PAGE':<50} {'<NB>':>5} {'IMPORT':>6}  STATUS")
print("-" * 70)
for a in audit:
    if a["custom"]:
        st = "CUSTOM-HEADER (no NavBar needed)"
    elif a["nb"] > 1:
        st = f"!! DOUBLE NavBar x{a['nb']}"
    elif a["nb"] == 0:
        st = "MISSING NavBar"
    else:
        st = "OK"
    print(f"  {a['rel']:<48} {a['nb']:>5} {a['imp']:>6}  {st}")

# ─────────────────────────────────────────────────────────────────
# PART 2: Fix NavBar.tsx (syntax)
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("PART 2: FIX NavBar.tsx SYNTAX")
print(SEP)

nb_path = None
for p in SRC.rglob("NavBar.tsx"):
    nb_path = p
    break

if not nb_path:
    print("  ERROR: NavBar.tsx not found!")
else:
    src = nb_path.read_text(encoding="utf-8")
    original = src

    # Fix ,,  -> ,
    src = re.sub(r',[ \t]*,', ',', src)
    # Fix },  \n  { missing comma: }  \n  {  -> },  \n  {
    src = re.sub(r'\}(\s*\n\s*)\{', r'},\1{', src)
    # Remove trailing comma before ] or )
    src = re.sub(r',(\s*[\]\)])', r'\1', src)

    if src != original:
        nb_path.write_text(src, encoding="utf-8")
        print(f"  [FIXED] {nb_path}")
    else:
        print(f"  [OK] {nb_path} (no changes needed)")

    # Show current links
    links = re.findall(r'href:\s*["\']([^"\']+)["\']', src)
    print(f"  Current nav links ({len(links)}): {links}")

# ─────────────────────────────────────────────────────────────────
# PART 3: Fix each page
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("PART 3: FIX ALL PAGES")
print(SEP)

IMPORT_LINE = 'import NavBar from "@/components/NavBar";\n'
fixed = []

for a in audit:
    pf   = a["path"]
    text = a["text"]
    orig = text

    if a["custom"]:
        # Remove any injected NavBar
        if a["nb"] > 0 or a["imp"] > 0:
            text = re.sub(r'import NavBar from ["\']@/components/NavBar["\'];\n?', '', text)
            text = text.replace("<NavBar />", "").replace("<NavBar/>", "")
            action = "REMOVED (custom header page)"
        else:
            action = "SKIP (custom header, already clean)"

    elif a["nb"] > 1:
        # Remove all, then add one back
        text = re.sub(r'import NavBar from ["\']@/components/NavBar["\'];\n?', '', text)
        text = text.replace("<NavBar />", "").replace("<NavBar/>", "")
        # Re-add import
        text = text.replace('"use client";\n', '"use client";\n' + IMPORT_LINE, 1)
        # Re-add usage after first opening div
        text = re.sub(
            r'(return\s*\(\s*\n\s*<div[^>]*>)',
            r'\1\n      <NavBar />',
            text, count=1
        )
        action = f"FIXED (was {a['nb']}x, now 1x)"

    elif a["nb"] == 0:
        # Add NavBar
        if IMPORT_LINE.strip() not in text:
            text = text.replace('"use client";\n', '"use client";\n' + IMPORT_LINE, 1)

        inserted = False
        new = re.sub(
            r'(return\s*\(\s*\n\s*<div[^>]*>)',
            r'\1\n      <NavBar />',
            text, count=1
        )
        if new != text:
            text = new
            inserted = True
        if not inserted:
            new = re.sub(
                r'(<div style=\{\{[^}]*minHeight[^}]*\}[^>]*>)',
                r'\1\n      <NavBar />',
                text, count=1
            )
            if new != text:
                text = new
                inserted = True
        action = "ADDED NavBar" if inserted else "WARN: could not insert NavBar"

    else:
        action = "OK (already 1x)"

    if text != orig:
        pf.write_text(text, encoding="utf-8")
        fixed.append((a["rel"], action))
        print(f"  >> {a['rel']:<50} {action}")
    else:
        print(f"  OK {a['rel']:<50} {action}")

print(f"\n  Total pages fixed: {len(fixed)}")

# ─────────────────────────────────────────────────────────────────
# PART 4: Find duplicate/unused Python files in D:\MICC
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("PART 4: DUPLICATE AND UNUSED PYTHON FILES")
print(SEP)

py_files = sorted(MICC.glob("*.py"))
print(f"  Total .py files in D:\\MICC: {len(py_files)}")

# Group by content hash to find true duplicates
hash_map = defaultdict(list)
for pf in py_files:
    try:
        h = hashlib.md5(pf.read_bytes()).hexdigest()
        hash_map[h].append(pf.name)
    except:
        pass

print("\n  EXACT DUPLICATES (same content):")
has_dups = False
for h, names in hash_map.items():
    if len(names) > 1:
        print(f"    {names}")
        has_dups = True
if not has_dups:
    print("    None found")

# Find fix_ and build_ scripts that are clearly old (by pattern)
print("\n  LIKELY OBSOLETE fix_* scripts (superseded by later versions):")
fix_scripts = [f for f in py_files if f.name.startswith("fix_") or f.name.startswith("build_")]

# Group by prefix pattern to find series
from collections import Counter
prefixes = Counter()
for f in fix_scripts:
    name = f.name.replace(".py","")
    # strip trailing version number
    base = re.sub(r'[_v]\d+[a-z]?$', '', name)
    prefixes[base] += 1

print("\n  Scripts with multiple versions (keep latest, delete rest):")
obsolete = []
for base, count in sorted(prefixes.items()):
    if count > 1:
        versions = sorted([f for f in fix_scripts
                           if f.name.startswith(base.replace("fix_","fix_").replace("build_","build_"))],
                          key=lambda x: x.stat().st_mtime)
        keep = versions[-1]
        delete = versions[:-1]
        print(f"    Base: {base} ({count} versions)")
        for d in delete:
            print(f"      DELETE: {d.name}")
            obsolete.append(d)
        print(f"      KEEP:   {keep.name}")

# Write cleanup script
cleanup_path = MICC / "cleanup_obsolete.py"
lines = [
    "# Auto-generated by micc_full_audit.py",
    "# Review before running!",
    "import os",
    "from pathlib import Path",
    "",
    "MICC = Path(r'D:\\MICC')",
    "to_delete = [",
]
for f in obsolete:
    lines.append(f"    '{f.name}',")
lines += [
    "]",
    "",
    "for name in to_delete:",
    "    p = MICC / name",
    "    if p.exists():",
    "        p.unlink()",
    "        print(f'Deleted: {name}')",
    "    else:",
    "        print(f'Not found: {name}')",
    "print(f'Done. Deleted {len(to_delete)} files.')",
]
cleanup_path.write_text("\n".join(lines), encoding="utf-8")
print(f"\n  Cleanup script written: {cleanup_path}")
print(f"  Review it, then run: py D:\\MICC\\cleanup_obsolete.py")

# ─────────────────────────────────────────────────────────────────
# PART 5: Final verification
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("PART 5: FINAL VERIFICATION")
print(SEP)

ok = warn = 0
for pf in sorted(APP.rglob("page.tsx")):
    rel  = str(pf.relative_to(APP)).replace("\\", "/")
    text = pf.read_text(encoding="utf-8", errors="replace")
    nb   = text.count("<NavBar")
    has_custom = any(p in text for p in SKIP_PATTERNS)

    if has_custom and nb == 0:
        print(f"  OK CUSTOM {rel}")
        ok += 1
    elif not has_custom and nb == 1:
        print(f"  OK        {rel}")
        ok += 1
    else:
        print(f"  WARN      {rel}  nb={nb}  custom={has_custom}")
        warn += 1

print(f"\n  OK: {ok}  WARNINGS: {warn}")

print(f"""
{SEP}
DONE
{SEP}

COMMANDS TO RUN NOW:

1. Restart dashboard:
   cd D:\\MICC\\micc-dashboard
   npm run dev

2. Review and run cleanup (removes old fix_ scripts):
   py D:\\MICC\\cleanup_obsolete.py

3. Push to git:
   & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" add -A
   & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" commit -m "audit: fix all navbars + cleanup"
   & "C:\\Program Files\\Git\\cmd\\git.exe" -C "D:\\MICC" push origin main --force
""")
