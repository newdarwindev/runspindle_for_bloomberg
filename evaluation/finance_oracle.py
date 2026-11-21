"""Validate finance replay output against the separately authored expectation sheet."""
from fractions import Fraction


def _same_metrics(actual, expected):
    if type(actual) is not dict or actual.keys() != expected.keys():
        return False
    try:
        return all(
            type(actual[name]) is str and Fraction(actual[name]) == Fraction(value)
            for name, value in expected.items()
        )
    except (ValueError, ZeroDivisionError):
        return False


def _compare(result, target):
    errors = []
    if result["decision"] != target["decision"] or result["reasons"] != target["reasons"]:
        errors.append("decision or pause reason differs from frozen expectation")
    if not _same_metrics(result["metrics"], target["metrics"]):
        errors.append("computed metrics differ from frozen expectation")
    return errors


def verify(fixtures, oracle, results):
    cases = fixtures["cases"]
    expected_cases = oracle["cases"]
    frozen_holdout = oracle["holdout_families"]
    if fixtures["holdout_families"] != frozen_holdout:
        raise ValueError("holdout families differ from frozen expectation")
    ids = [case["id"] for case in cases]
    if ids != list(range(1, 41)) or [item["id"] for item in expected_cases] != ids:
        raise ValueError("finance fixture and expectation sheets must each cover IDs 1–40 once")
    if [row["id"] for row in results] != ids:
        raise ValueError("replay output must cover each case in frozen order")
    failures = []
    for case, expected, row in zip(cases, expected_cases, results, strict=True):
        case_id = case["id"]
        family = expected["family"]
        if case["family"] != family or row["family"] != family:
            raise ValueError(f"family differs from frozen expectation for case {case_id}")
        split = "holdout" if family in frozen_holdout else "development"
        if row["split"] != split:
            raise ValueError(f"split differs from frozen expectation for case {case_id}")
        required_checks = expected["required_checks"]
        if list(case["checks"]) != required_checks:
            raise ValueError(f"required checks differ from frozen expectation for case {case_id}")
        for message in _compare(row["baseline"], expected):
            failures.append({"id": case_id, "scenario": "baseline", "message": message})
        adverse = row["adverse"]
        if list(adverse) != required_checks:
            raise ValueError(f"adverse checks differ from frozen expectation for case {case_id}")
        for check, result in adverse.items():
            target = {"decision": "pause", "reasons": [check], "metrics": {}}
            for message in _compare(result, target):
                failures.append({"id": case_id, "scenario": check, "message": message})
    return failures
