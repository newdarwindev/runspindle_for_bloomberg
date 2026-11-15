#!/usr/bin/env python3
"""Calculate full cost per accepted authorized completion from supplied inputs."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

FIXED = ("setup_amortized", "licensing", "maintenance", "allocated_fixed")
PER_ATTEMPT = ("model", "tools", "human_operation", "verification", "recovery", "support")
OPTIONS = ("native_terminal", "expert_assisted", "deterministic_integration", "runspindle")
CONTEXT = ("period", "currency", "task_boundary", "permission_rule", "acceptance_criteria", "cost_owner")


def number(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{label} must be a nonnegative number or null")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return result


def quantity(value, label):
    result = number(value, label)
    if result is not None and result != result.to_integral_value():
        raise ValueError(f"{label} must be a whole number")
    return result


def decimal_text(value):
    return None if value is None else format(value.normalize(), "f")


def evaluate_option(option):
    attempts = quantity(option.get("attempts"), "attempts")
    accepted = quantity(option.get("accepted_authorized_completions"), "accepted_authorized_completions")
    if attempts is not None and accepted is not None and accepted > attempts:
        raise ValueError("accepted_authorized_completions exceeds attempts")
    costs = option.get("costs", {})
    fixed = {key: number(costs.get(key), key) for key in FIXED}
    variable = {key: number(costs.get(key), key) for key in PER_ATTEMPT}
    missing = []
    if attempts is None:
        missing.append("attempts")
    if accepted is None:
        missing.append("accepted_authorized_completions")
    missing.extend(f"costs.{key}" for key, value in {**fixed, **variable}.items() if value is None)
    total = None
    unit = None
    if not missing:
        total = sum(fixed.values()) + attempts * sum(variable.values())
        if accepted > 0:
            unit = total / accepted
    return {
        "attempts": decimal_text(attempts),
        "accepted_authorized_completions": decimal_text(accepted),
        "missing_inputs": missing,
        "total_cost": decimal_text(total),
        "unit_cost": decimal_text(unit),
        "unit_cost_reason": ("zero accepted completions" if total is not None and accepted == 0 else
                             "missing inputs" if missing else None),
    }


def sensitivity(option):
    """Hypothetical volume and acceptance changes; no market prediction."""
    result = evaluate_option(option)
    if result["missing_inputs"] or Decimal(result["attempts"]) == 0:
        return []
    attempts = Decimal(result["attempts"])
    accepted = Decimal(result["accepted_authorized_completions"])
    costs = option["costs"]
    fixed = sum(number(costs[key], key) for key in FIXED)
    variable = sum(number(costs[key], key) for key in PER_ATTEMPT)
    rate = accepted / attempts
    scenarios = []
    for volume_factor, rate_shift in ((Decimal("0.5"), Decimal(0)),
                                      (Decimal(1), Decimal("-0.1")),
                                      (Decimal(1), Decimal(0)),
                                      (Decimal(1), Decimal("0.1")),
                                      (Decimal(2), Decimal(0))):
        changed_attempts = attempts * volume_factor
        changed_rate = min(Decimal(1), max(Decimal(0), rate + rate_shift))
        denominator = changed_attempts * changed_rate
        cost = fixed + changed_attempts * variable
        scenarios.append({
            "volume_factor": decimal_text(volume_factor),
            "acceptance_rate": decimal_text(changed_rate),
            "hypothetical_unit_cost": decimal_text(cost / denominator) if denominator else None,
        })
    return scenarios


def evaluate(model):
    if model.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    options = model.get("options", {})
    if set(options) != set(OPTIONS):
        raise ValueError("options must include exactly the four named alternatives")
    missing_context = [key for key in CONTEXT if not model.get(key)]
    results = {name: {**evaluate_option(options[name]), "sensitivity": sensitivity(options[name])}
               for name in OPTIONS}
    workloads = [result["attempts"] for result in results.values()]
    return {
        "context": {key: model.get(key) for key in CONTEXT},
        "missing_context": missing_context,
        "matched_attempts": len(set(workloads)) == 1 and workloads[0] is not None,
        "comparable": not missing_context and len(set(workloads)) == 1 and workloads[0] is not None
                      and all(not result["missing_inputs"] for result in results.values()),
        "note": "Unknown costs remain unknown; sensitivity rows are hypothetical, not ROI estimates.",
        "options": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    args = parser.parse_args()
    data = json.loads(args.model.read_text(), parse_float=Decimal)
    print(json.dumps(evaluate(data), indent=2))


if __name__ == "__main__":
    main()
