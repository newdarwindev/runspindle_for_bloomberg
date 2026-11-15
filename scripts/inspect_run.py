#!/usr/bin/env python3
"""Read a synthetic run's status and append-only event chain."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot.runtime import Runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Database file does not exist")
    runtime = Runtime(args.database)
    try:
        print(json.dumps({"status": runtime.status(args.run_id),
                          "event_chain_valid": runtime.verify_chain(args.run_id),
                          "events": [json.loads(row["payload"]) for row in runtime.events(args.run_id)]},
                         indent=2))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
