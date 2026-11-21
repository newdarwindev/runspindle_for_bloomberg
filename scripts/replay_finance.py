#!/usr/bin/env python3
"""Run the 40 synthetic finance calculations and refusal checks."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.finance_oracle import verify
from evaluation.finance_replay import replay
from scripts.replay_corpus import OUTPUT as SOURCE_FIXTURES, build as build_source_catalog

FIXTURES = ROOT / "evaluation/finance-fixtures.v1.json"
ORACLE = ROOT / "evaluation/finance-expected.v1.json"
REPORT = ROOT / "evaluation/finance-report.v1.json"
PROTOCOL = ROOT / "evaluation/finance-protocol.v1.md"


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(fixtures, oracle, source):
    cases = fixtures["cases"]
    holdout = set(fixtures["holdout_families"])
    families = {case["family"] for case in cases}
    if not holdout < families or not holdout:
        raise ValueError("holdout must name a proper subset of the case families")
    source_by_id = {case["id"]: case for case in source["fixtures"]}
    results = []
    for case in cases:
        origin = source_by_id[case["id"]]
        baseline = replay(case)
        adverse = {check: replay(case, check_changes={check: False}) for check in case["checks"]}
        results.append(dict(
            id=case["id"], name=origin["name"], family=case["family"],
            split="holdout" if case["family"] in holdout else "development",
            source_urls=origin["source_urls"], baseline=baseline, adverse=adverse,
        ))
    failures = verify(fixtures, oracle, results)
    return {
        "schema_version": 1,
        "evidence_level": "synthetic_finance_only",
        "source_csv_sha256": source["source_sha256"],
        "fixture_sha256": sha_file(FIXTURES),
        "expected_sha256": sha_file(ORACLE),
        "protocol_sha256": sha_file(PROTOCOL),
        "software": {
            "model": None,
            "runner_sha256": sha_file(Path(__file__)),
            "evaluator_sha256": sha_file(ROOT / "evaluation/finance_replay.py"),
            "verifier_sha256": sha_file(ROOT / "evaluation/finance_oracle.py"),
        },
        "holdout_families": fixtures["holdout_families"],
        "baseline_count": len(results),
        "adverse_count": sum(len(row["adverse"]) for row in results),
        "domain_review": "not_run",
        "measurement": {
            "accepted_authorized_completion": None, "correct_refusal": None,
            "unknown_effect": None, "produced_only": None,
            "human_active_seconds": None, "latency_seconds": None,
            "quality": None, "full_cost": None, "matched_baselines": None, "uncertainty": None,
        },
        "failures": failures,
        "cases": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="require the committed report to reproduce")
    options = parser.parse_args()
    catalog = load(SOURCE_FIXTURES)
    if catalog != build_source_catalog():
        raise SystemExit("Source corpus differs from source CSVs")
    report = build_report(load(FIXTURES), load(ORACLE), catalog)
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if not options.check:
        REPORT.write_text(encoded, encoding="utf-8")
    if report["failures"]:
        print(json.dumps(report["failures"], indent=2), file=sys.stderr)
        raise SystemExit("Synthetic replay differs from expected results")
    if options.check and (not REPORT.exists() or REPORT.read_text(encoding="utf-8") != encoded):
        raise SystemExit("Synthetic finance report differs from committed result")
    print(f"Verified {report['baseline_count']} baseline calculations and {report['adverse_count']} adverse checks")


if __name__ == "__main__":
    main()
