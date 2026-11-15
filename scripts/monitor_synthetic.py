#!/usr/bin/env python3
"""Print local synthetic run counters; never labels them external acceptance."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot.monitor import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.database), indent=2))


if __name__ == "__main__":
    main()
