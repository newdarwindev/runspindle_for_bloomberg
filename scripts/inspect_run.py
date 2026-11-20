#!/usr/bin/env python3
"""Read a synthetic run's status and append-only event chain."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot.runtime import IntegrityError, Runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Database file does not exist")
    try:
        runtime = Runtime(args.database, create=False)
    except (IntegrityError, sqlite3.Error):
        parser.error("Cannot open a compatible synthetic ledger")
    try:
        print(json.dumps({"status": runtime.status(args.run_id),
                          "event_chain_valid": runtime.verify_chain(args.run_id),
                          "events": [json.loads(row["payload"]) for row in runtime.events(args.run_id)]},
                         indent=2))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
