import re
from pathlib import Path

APP = Path(r"D:\MICC\micc-dashboard\src\app")
root = APP / "page.tsx"

text = root.read_text(encoding="utf-8")

# Check current state
nb_count = text.count("<NavBar")
print(f"Current NavBar count in page.tsx: {nb_count}")
print(f"Has RefreshController: {'RefreshController' in text}")
print(f"Has Market Intelligence: {'Market Intelligence' in text}")

if nb_count >= 1:
    print("NavBar already present -- checking if it renders before custom bar...")
    # Find position of NavBar vs RefreshController
    nb_pos = text.find("<NavBar")
    rc_pos = text.find("RefreshController") 
    if nb_pos < rc_pos:
        print("NavBar is ABOVE custom bar -- correct!")
    else:
        print("NavBar is BELOW custom bar -- fixing...")
else:
    print("No NavBar -- adding it...")

# Strategy: the root page has a top-level return div
# We need NavBar as the VERY FIRST child before anything else
# Remove any existing NavBar first
text = re.sub(r'import NavBar from ["\']@/components/NavBar["\'];\n?', '', text)
text = text.replace("<NavBar />", "").replace("<NavBar/>", "")

# Add import at top
text = text.replace(
    '"use client";\n',
    '"use client";\nimport NavBar from "@/components/NavBar";\n',
    1
)

# Find the outermost return div and insert NavBar as absolute first child
# The root page wraps everything in a top-level div
new_text = re.sub(
    r'(return\s*\(\s*\n\s*<div[^>]*>)',
    r'\1\n      <NavBar />',
    text, count=1
)

if new_text == text:
    # Try alternative pattern
    new_text = re.sub(
        r'(<div style=\{\{[^}]*minHeight[^}]*\}[^>]*>)',
        r'\1\n      <NavBar />',
        text, count=1
    )

if new_text != text:
    root.write_text(new_text, encoding="utf-8")
    count_after = new_text.count("<NavBar")
    print(f"Done. NavBar count after fix: {count_after}")
    print("NavBar is now the first element rendered in the root page.")
else:
    print("Could not auto-insert. Printing first 40 lines of return block:")
    in_return = False
    count = 0
    for i, line in enumerate(text.splitlines(), 1):
        if "return (" in line:
            in_return = True
        if in_return:
            print(f"  {i}: {line}")
            count += 1
            if count > 40:
                break

print("\nRestart: cd D:\\MICC\\micc-dashboard && npm run dev")
