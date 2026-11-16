#!/usr/bin/env python3
"""Show structural pilot blockers; never grants permission for a live pilot."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot.partner_register import preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    print(json.dumps(preflight(json.loads(args.plan.read_text())), indent=2))


if __name__ == "__main__":
    main()
