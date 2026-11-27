"""Compare invented pilot records only; do not perform a data transfer."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve()
FIXTURE = SCRIPT.with_name("fixtures") / "synthetic-pilot-scope.json"
CASES = {
    "matched": "fixture_ready",
    "missing-entitlement": "entitlement_missing",
    "wrong-entitlement": "entitlement_scope_mismatch",
    "wrong-destination": "destination_scope_mismatch",
    "wrong-pilot": "pilot_scope_mismatch",
}
KEYS = {
    "entitlement": ("dataset", "use"),
    "destination": ("destination", "dataset", "use"),
    "pilot": ("pilot", "dataset", "use", "destination"),
}


def classify(request, records):
    for role, keys in KEYS.items():
        record = records.get(role)
        if record is None:
            return f"{role}_missing"
        if any(
            not isinstance(request.get(key), str) or not request[key]
            or key not in record or record[key] != request[key]
            for key in keys
        ):
            return f"{role}_scope_mismatch"
    return "fixture_ready"


def rehearse(scenario):
    if scenario not in CASES:
        raise ValueError("unknown scenario")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = {role: data[role] for role in KEYS}
    if scenario == "missing-entitlement":
        del records["entitlement"]
    elif scenario == "wrong-entitlement":
        records["entitlement"]["use"] = "fixture-other-use"
    elif scenario == "wrong-destination":
        records["destination"]["destination"] = "fixture-other-sink"
    elif scenario == "wrong-pilot":
        records["pilot"]["pilot"] = "fixture-other-pilot"
    outcome = classify(data["request"], records)
    return {
        "scenario": scenario,
        "synthetic_only": True,
        "live_rights_verified": False,
        "data_transferred": False,
        "outcome": outcome,
        "fixture_scope_matched": outcome == "fixture_ready",
        "passed": outcome == CASES[scenario],
    }


class PilotScopeRehearsalTests(unittest.TestCase):
    def test_cli_cases_are_repeatable_and_never_claim_real_rights(self):
        for case in CASES:
            with self.subTest(case=case):
                cmd = [sys.executable, str(SCRIPT), case]
                result = subprocess.check_output(cmd, text=True)
                self.assertEqual(result, subprocess.check_output(cmd, text=True))
                receipt = json.loads(result)
                self.assertEqual(receipt["outcome"], CASES[case])
                self.assertTrue(receipt["passed"])
                self.assertTrue(receipt["synthetic_only"])
                self.assertFalse(receipt["live_rights_verified"])
                self.assertFalse(receipt["data_transferred"])
                self.assertEqual(receipt["fixture_scope_matched"], case == "matched")

    def test_same_destination_and_pilot_ids_do_not_cover_wrong_dataset_use(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        records = {role: data[role] for role in KEYS}
        for role in ("destination", "pilot"):
            with self.subTest(role=role):
                self.assertEqual(
                    classify(data["request"], {**records, role: {**records[role], "use": "different"}}),
                    f"{role}_scope_mismatch",
                )

    def test_missing_destination_and_pilot_are_explicit_stops(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for role in ("destination", "pilot"):
            with self.subTest(role=role):
                self.assertEqual(
                    classify(data["request"], {key: data[key] for key in KEYS if key != role}),
                    f"{role}_missing",
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=CASES)
    receipt = rehearse(parser.parse_args().scenario)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
