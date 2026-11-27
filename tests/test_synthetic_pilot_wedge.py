"""Select a hypothetical pilot wedge using invented evidence only."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve()
FIXTURE = SCRIPT.with_name("fixtures") / "synthetic-pilot-wedge.json"
CASES = {
    "choose-one": ("fixture_go", "fixture-a"),
    "missing-rights": ("no_eligible_candidate", None),
    "missing-pilot-evidence": ("no_eligible_candidate", None),
    "insufficient-demand": ("no_eligible_candidate", None),
    "tie": ("tied_top_candidates", None),
}


def assessment(row, limits):
    if row.get("scope_confirmed") is not True:
        return None, "rights_missing"
    if any(
        type(row.get(key)) is not int or row[key] < limits[minimum]
        for key, minimum in (
            ("interviews", "minimum_interviews"),
            ("weekly_frequency", "minimum_weekly_frequency"),
        )
    ):
        return None, "demand_insufficient"
    pairs, baseline, pilot = (
        row.get("comparable_pairs"), row.get("baseline_minutes"), row.get("pilot_minutes")
    )
    if (
        not all(type(value) is int for value in (pairs, baseline, pilot))
        or pairs < limits["minimum_paired_examples"]
        or not 0 <= pilot < baseline
    ):
        return None, "comparable_pilot_missing"
    return (baseline - pilot) * row["weekly_frequency"], None


def choose(rows, limits):
    scores = {}
    blockers = {}
    seen = set()
    for row in rows:
        key = row["id"]
        if key in seen:
            return "duplicate_candidate", None, {}, {}
        seen.add(key)
        score, reason = assessment(row, limits)
        if reason is None:
            scores[key] = score
        else:
            blockers[key] = reason
    if not scores:
        return "no_eligible_candidate", None, scores, blockers
    best = [key for key, score in scores.items() if score == max(scores.values())]
    if len(best) != 1:
        return "tied_top_candidates", None, scores, blockers
    return "fixture_go", best[0], scores, blockers


def replay(case):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = data["candidate_rows"]
    if case == "missing-rights":
        for row in rows:
            row.pop("scope_confirmed")
    elif case == "missing-pilot-evidence":
        for row in rows:
            row["comparable_pairs"] = 0
    elif case == "insufficient-demand":
        for row in rows:
            row["weekly_frequency"] = 1
    elif case == "tie":
        rows[1]["pilot_minutes"] = 2

    outcome, candidate, scores, blockers = choose(rows, data)
    return {
        "synthetic_only": True,
        "real_buyers_or_rights_verified": False,
        "scenario": case,
        "outcome": outcome,
        "selected_fixture": candidate,
        "fixture_minutes_saved_per_week": scores,
        "blocks": blockers,
        "pricing_decision": None,
        "launch_decision": None,
        "passed": (outcome, candidate) == CASES[case],
    }


class SyntheticPilotWedgeTests(unittest.TestCase):
    def test_cli_cases_deterministic_and_never_set_pricing_or_launch(self):
        for case, expected in CASES.items():
            with self.subTest(case=case):
                cmd = [sys.executable, str(SCRIPT), case]
                first = subprocess.check_output(cmd, text=True)
                self.assertEqual(first, subprocess.check_output(cmd, text=True))
                receipt = json.loads(first)
                self.assertEqual((receipt["outcome"], receipt["selected_fixture"]), expected)
                self.assertTrue(receipt["passed"])
                self.assertTrue(receipt["synthetic_only"])
                self.assertFalse(receipt["real_buyers_or_rights_verified"])
                self.assertIsNone(receipt["pricing_decision"])
                self.assertIsNone(receipt["launch_decision"])

    def test_ineligible_high_score_cannot_hide_the_supported_candidate(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        a, b = fixture["candidate_rows"]
        a["scope_confirmed"] = False
        result = choose([b, a], fixture)
        self.assertEqual(result, ("fixture_go", "fixture-b", {"fixture-b": 12}, {"fixture-a": "rights_missing"}))

    def test_duplicate_candidate_cannot_be_counted_as_another_buying_signal(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        first = fixture["candidate_rows"][0]
        self.assertEqual(choose([first, first], fixture)[:2], ("duplicate_candidate", None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=CASES)
    receipt = replay(parser.parse_args().scenario)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
