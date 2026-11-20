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


def verify(cases, oracle, results):
    ids = [case["id"] for case in cases]
    if ids != list(range(1, 41)) or [item["id"] for item in oracle] != ids:
        raise ValueError("finance fixture and expectation sheets must each cover IDs 1–40 once")
    if [row["id"] for row in results] != ids:
        raise ValueError("replay output must cover each case in frozen order")
    failures = []
    for case, expected, row in zip(cases, oracle, results, strict=True):
        for message in _compare(row["baseline"], expected):
            failures.append({"id": case["id"], "scenario": "baseline", "message": message})
        adverse = row["adverse"]
        if list(adverse) != list(case["checks"]):
            raise ValueError(f"adverse checks differ from fixture for case {case['id']}")
        for check, result in adverse.items():
            target = {"decision": "pause", "reasons": [check], "metrics": {}}
            for message in _compare(result, target):
                failures.append({"id": case["id"], "scenario": check, "message": message})
    return failures
