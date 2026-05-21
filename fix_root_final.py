from pathlib import Path
import re

root = Path(r"D:\MICC\micc-dashboard\src\app\page.tsx")
text = root.read_text(encoding="utf-8")

print(f"File length: {len(text.splitlines())} lines")
print(f"NavBar count: {text.count('<NavBar')}")
print(f"NavBar import: {'import NavBar' in text}")
print()

# Show first 10 lines
lines = text.splitlines()
print("First 10 lines:")
for i, l in enumerate(lines[:10], 1):
    print(f"  {i}: {l}")

# If NavBar import missing, add it
if 'import NavBar' not in text:
    print("\nAdding NavBar import...")
    text = text.replace(
        '"use client";\n',
        '"use client";\nimport NavBar from "@/components/NavBar";\n',
        1
    )

# If <NavBar /> missing in return block, add it
if text.count('<NavBar') == 0:
    print("Adding <NavBar /> to return block...")
    # The root page has:  <div style={{ minHeight: "100vh"
    # NavBar goes as first child
    text = text.replace(
        '<div style={{ minHeight: "100vh"',
        '<div style={{ minHeight: "100vh"',
        1
    )
    # Insert NavBar after the opening div tag
    text = re.sub(
        r'(<div style=\{\{ minHeight: "100vh"[^}]*\}\}>)',
        r'\1\n      <NavBar />',
        text, count=1
    )
    print(f"NavBar count after: {text.count('<NavBar')}")

root.write_text(text, encoding="utf-8")

# Also fix validate_patterns_oos.py NoneType error
print("\nFixing validate_patterns_oos.py NoneType error...")
oos = Path(r"D:\MICC\validate_patterns_oos.py")
if oos.exists():
    oos_text = oos.read_text(encoding="utf-8")
    # Replace the stats printing block that crashes
    old = 'print(f"  With OOS data     : {stats[1]:,}")'
    new = 'print(f"  With OOS data     : {(stats[1] or 0):,}")'
    oos_text = oos_text.replace(old, new)
    # Fix all similar lines
    oos_text = re.sub(
        r'print\(f"(.*?)\{stats\[(\d+)\](:,)?\}(.*?)"\)',
        lambda m: f'print(f"{m.group(1)}{{(stats[{m.group(2)}] or 0){m.group(3) or ""}}}{m.group(4)}")',
        oos_text
    )
    oos.write_text(oos_text, encoding="utf-8")
    print("  Fixed")

print("""
Done.
  cd D:\\MICC\\micc-dashboard && npm run dev
""")
