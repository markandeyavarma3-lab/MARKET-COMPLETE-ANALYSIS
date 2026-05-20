# -*- coding: utf-8 -*-
"""
MICC - watch_folder.py
Polling-based watcher. Scans NSE Data folder every 5 seconds.
HOW TO RUN:  py pipeline/watch_folder.py
HOW TO STOP: Ctrl+C
"""

import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    NSE_DATA_ROOT,
    NSE_INDICES_DIR,
    NSE_OTHER_DIR,
    INDICES_CATEGORY_MAP,
    OTHER_DATA_MAP,
    SUPPORTED_EXTENSIONS,
    FILE_STABLE_WAIT,
)
from agents.shared.logger import get_logger
from pipeline.ingestion.router import route_file

log = get_logger("pipeline.watcher")

POLL_INTERVAL = 5


def file_signature(path: Path) -> str:
    try:
        stat = path.stat()
        return str(stat.st_size) + "_" + str(stat.st_mtime)
    except Exception:
        return ""


def classify_file(path: Path):
    """
    Match file to one of the 13 types using case-insensitive folder matching.
    """
    if path.suffix.upper() not in SUPPORTED_EXTENSIONS:
        return None

    # Walk up from the file to find which NSE sub-folder it lives in
    # We check all parent folders of the file against our maps

    # --- Check if under NSE INDICES ---
    try:
        relative = path.relative_to(NSE_INDICES_DIR)
        parts = relative.parts
        # parts[0] = category (e.g. BROAD MARKET INDICES)
        # parts[1] = index name subfolder OR filename (2 or 3 level deep)
        if len(parts) >= 2:
            folder_actual = parts[0]
            for key, category in INDICES_CATEGORY_MAP.items():
                if folder_actual.upper() == key.upper():
                    return {
                        "path":       path,
                        "type":       "indices",
                        "parser_key": "indices_csv",
                        "table":      "indices_data",
                        "category":   category,
                    }
    except ValueError:
        pass

    # --- Check if under NSE OTHER DATA ---
    try:
        relative = path.relative_to(NSE_OTHER_DIR)
        parts = relative.parts
        if len(parts) >= 2:
            folder_actual = parts[0].lower().strip()
            for key, (parser_key, table) in OTHER_DATA_MAP.items():
                if folder_actual == key.lower().strip():
                    return {
                        "path":       path,
                        "type":       "other",
                        "parser_key": parser_key,
                        "table":      table,
                        "category":   None,
                    }
    except ValueError:
        pass

    return None


def scan_folder(root: Path) -> list:
    if not root.exists():
        return []
    try:
        return [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.upper() in SUPPORTED_EXTENSIONS
        ]
    except Exception as e:
        log.warning("Scan error: " + str(e))
        return []


def _human_size(path: Path) -> str:
    try:
        b = path.stat().st_size
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return str(round(b, 1)) + " " + unit
            b /= 1024
        return str(round(b, 1)) + " TB"
    except Exception:
        return "?"


def _process_file(path: Path):
    log.info("-" * 60)
    log.info("Processing: " + path.name)
    log.info("Size: " + _human_size(path) + " | " + datetime.now().strftime("%H:%M:%S"))

    metadata = classify_file(path)
    if metadata is None:
        log.warning("Could not classify: " + path.name)
        log.warning("Parent folder: " + str(path.parent.name))
        log.warning("Check that the folder name exactly matches settings.py OTHER_DATA_MAP keys")
        return

    log.info("Type: [" + metadata["parser_key"] + "] -> " + metadata["table"])

    try:
        result = route_file(metadata)
        if result["success"]:
            log.info(
                "SUCCESS: " + str(result["rows_written"]) + " rows -> "
                + metadata["table"] + " (" + str(round(result["duration_ms"])) + "ms)"
            )
        else:
            log.error("FAILED: " + str(result.get("error", "unknown")))
    except Exception as exc:
        log.exception("Error: " + str(exc))


def start_watcher():
    log.info("=" * 60)
    log.info("  MICC FILE WATCHER  (polling mode)")
    log.info("=" * 60)
    log.info("  Watching : " + str(NSE_DATA_ROOT))
    log.info("  Indices  : " + str(NSE_INDICES_DIR))
    log.info("  Other    : " + str(NSE_OTHER_DIR))

    # Show whether the folders actually exist
    root_exists    = NSE_DATA_ROOT.exists()
    indices_exists = NSE_INDICES_DIR.exists()
    other_exists   = NSE_OTHER_DIR.exists()

    log.info("  Root exists    : " + str(root_exists))
    log.info("  Indices exists : " + str(indices_exists))
    log.info("  Other exists   : " + str(other_exists))
    log.info("=" * 60)

    if not root_exists:
        log.error("FATAL: Watch folder not found: " + str(NSE_DATA_ROOT))
        log.error("Check NSE_DATA_ROOT in config/settings.py")
        sys.exit(1)

    log.info("  Drop CSV files into sub-folders. Ctrl+C to stop.")
    log.info("=" * 60)

    seen: dict = {}

    try:
        while True:
            current_files = scan_folder(NSE_DATA_ROOT)
            now = time.monotonic()

            for path in current_files:
                sig = file_signature(path)
                key = str(path)

                if key not in seen:
                    seen[key] = {"sig": sig, "first_seen": now, "processed": False}
                    log.info("Detected: " + path.name + " (" + _human_size(path) + ")")
                    log.info("In folder: " + str(path.parent.name))
                    continue

                entry = seen[key]
                if entry["processed"]:
                    continue

                if sig != entry["sig"]:
                    entry["sig"] = sig
                    entry["first_seen"] = now
                    continue

                elapsed = now - entry["first_seen"]
                if elapsed >= FILE_STABLE_WAIT:
                    entry["processed"] = True
                    _process_file(path)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info("Watcher stopped.")


if __name__ == "__main__":
    start_watcher()
