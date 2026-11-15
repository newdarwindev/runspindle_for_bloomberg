#!/usr/bin/env python3
"""Build and validate a source-linked, synthetic replay corpus.

This preserves the supplied scenarios; it does not infer finance rules from prose.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/runspindle_bloomberg_workflows.csv"
RANKED = ROOT / "assets/runspindle_bloomberg_ranked.csv"
OUTPUT = ROOT / "evaluation/fixtures.v1.json"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def urls(value):
    return [url.strip() for url in value.split("|") if url.strip()]


def build():
    workflows = rows(SOURCE)
    ranked = rows(RANKED)
    ids = [int(row["example_id"]) for row in workflows]
    ranks = [int(row["priority_rank"]) for row in ranked]
    if sorted(ids) != list(range(1, 41)) or sorted(ranks) != list(range(1, 41)):
        raise ValueError("Expected unique case IDs and ranks 1–40")
    by_id = {int(row["example_id"]): row for row in ranked}
    fixtures = []
    for row in workflows:
        case_id = int(row["example_id"])
        rank = by_id[case_id]
        if row["example"] != rank["example"] or row["slice"] != rank["slice"]:
            raise ValueError(f"Ranked catalog mismatch for case {case_id}")
        fixtures.append({
            "id": case_id,
            "name": row["example"],
            "slice": int(row["slice"]),
            "scope": row["workflow_scope"],
            "editorial_rank": int(rank["priority_rank"]),
            "inputs": {"terminal_observation": row["step_1_terminal_check"],
                       "assumptions": row["assumptions"]},
            "decision_rule_source": row["step_2_action_or_pause"],
            "expected_check_source": row["step_3_verification"],
            "illustrative_outcome": row["business_payoff"],
            "source_urls": urls(row["terminal_and_method_source_urls"]),
            "alternative_urls": urls(row["software_source_urls"]),
            "review_status": "unverified_source_prose",
        })
    return {
        "schema_version": 1,
        "evidence_level": "synthetic_source_transcription",
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "ranked_sha256": hashlib.sha256(RANKED.read_bytes()).hexdigest(),
        "fixtures": fixtures,
    }


def main():
    expected = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if __import__("sys").argv[1:] == ["--check"]:
        if not OUTPUT.exists() or OUTPUT.read_text() != expected:
            raise SystemExit("Fixture corpus differs from the source CSVs; regenerate it")
        print("40 fixtures match the source CSVs")
    else:
        OUTPUT.parent.mkdir(exist_ok=True)
        OUTPUT.write_text(expected)
        print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
