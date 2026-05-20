# -*- coding: utf-8 -*-
"""
MICC - First-Time Setup Script
Run this ONCE to create all required folders.
Usage: py setup.py
"""

import shutil
from pathlib import Path


def create_folder_structure():
    home = Path.home()
    desktop = home / "Desktop"

    folders = [
        desktop / "NSE-DATA" / "NSE-INDICES" / "DERIVATIVES",
        desktop / "NSE-DATA" / "NSE-INDICES" / "SECTORAL",
        desktop / "NSE-DATA" / "NSE-INDICES" / "BROAD",
        desktop / "NSE-DATA" / "NSE-INDICES" / "THEMATIC",
        desktop / "NSE-DATA" / "NSE-INDICES" / "STRATEGY",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "full bhavcopy",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "sme-bhavcopy",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "nifty 50 top 10 holdings",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "daily snapshot",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "all etfs",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "nse all indices data",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "total stocks traded",
        desktop / "NSE-DATA" / "NSE-OTHER-DATA" / "market activity report",
        Path("D:/marketDB/db"),
        Path("D:/marketDB/stocks/all"),
    ]

    print("")
    print("=" * 60)
    print("  MICC FIRST-TIME SETUP")
    print("=" * 60)

    created = 0
    existing = 0

    for folder in folders:
        if folder.exists():
            print("  EXISTS   " + str(folder))
            existing += 1
        else:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                print("  CREATED  " + str(folder))
                created += 1
            except Exception as e:
                print("  FAILED   " + str(folder) + " : " + str(e))

    print("=" * 60)
    print("  Created: " + str(created) + "  |  Existed: " + str(existing))
    print("=" * 60)
    print("")
    print("  Next steps:")
    print("  1. py -m pip install -r requirements.txt")
    print("  2. py pipeline/watch_folder.py")
    print("")


if __name__ == "__main__":
    create_folder_structure()
