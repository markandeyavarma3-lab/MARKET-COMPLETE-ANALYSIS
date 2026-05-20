import re
from pathlib import Path

DASH = Path(r"D:\MICC\micc-dashboard")
APP  = DASH / "src" / "app"

# Pages with their own custom header -- NavBar should NOT be in these
CUSTOM_HEADER_PAGES = [
    "page.tsx",       # root: has PAUSED/RESUME/Market Intelligence Command Center
    "deep/page.tsx",  # has DEEP ANALYSIS ROOM header with its own sticky bar
]

fixed = 0
for page_file in sorted(APP.rglob("page.tsx")):
    rel  = str(page_file.relative_to(APP)).replace("\\", "/")
    text = page_file.read_text(encoding="utf-8")
    nb   = text.count("<NavBar")
    original = text

    # Case 1: double NavBar anywhere -- strip to single
    if nb > 1:
        text = text.replace("<NavBar />", "__NB__", 1)
        text = text.replace("<NavBar />", "")
        text = text.replace("<NavBar/>",  "")
        text = text.replace("__NB__", "<NavBar />")
        print(f"  [FIXED double] {rel}")

    # Case 2: custom-header pages should have NO NavBar
    if rel in CUSTOM_HEADER_PAGES and "<NavBar" in text:
        text = re.sub(r'import NavBar from ["\']@/components/NavBar["\'];\n', '', text)
        text = text.replace("<NavBar />", "")
        text = text.replace("<NavBar/>",  "")
        print(f"  [FIXED custom-header] {rel} -- removed injected NavBar")

    if text != original:
        page_file.write_text(text, encoding="utf-8")
        fixed += 1
    else:
        status = "OK" if nb == 1 else ("OK-custom" if nb == 0 else "WARN-none")
        print(f"  [{status}] {rel}")

print(f"\nFixed {fixed} pages.")
print("Restart: cd D:\\MICC\\micc-dashboard && npm run dev")
