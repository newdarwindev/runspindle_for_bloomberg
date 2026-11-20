"""Exact-decimal, side-effect-free evaluator for the synthetic finance fixtures."""
import operator
from decimal import Decimal, ROUND_HALF_UP, localcontext

ARITHMETIC = {
    "add": operator.add, "sub": operator.sub, "mul": operator.mul, "div": operator.truediv,
    "min": min, "max": max, "gt": operator.gt, "ge": operator.ge,
    "lt": operator.lt, "eq": operator.eq,
}


class MissingInput(Exception):
    """A fixture cannot support the modeled decision with its current inputs."""


def expression(node, values):
    if type(node) is str:
        if node.startswith("$"):
            value = values.get(node[1:])
            if value is None:
                raise MissingInput(node[1:])
            return value
        return Decimal(node)
    if type(node) is bool:
        return node
    operation, *operands = node
    args = [expression(item, values) for item in operands]
    if operation == "and" and args and all(type(arg) is bool for arg in args):
        return all(args)
    if any(type(arg) is not Decimal or not arg.is_finite() for arg in args):
        raise ValueError("finite decimal operands required")
    if operation == "round" and len(args) == 2:
        value, digits = args
        if digits != int(digits) or not 0 <= digits <= 8:
            raise ValueError("invalid decimal rounding precision")
        return value.quantize(Decimal(1).scaleb(-int(digits)), rounding=ROUND_HALF_UP)
    if operation in ARITHMETIC and len(args) == 2:
        return ARITHMETIC[operation](*args)
    raise ValueError(f"unsupported replay expression {operation!r}")


def replay(case, *, input_changes=None, check_changes=None):
    """Only evaluate a paper decision or draft. Nothing is sent or recorded externally."""
    inputs = dict(case["inputs"], **(input_changes or {}))
    checks = dict(case["checks"], **(check_changes or {}))
    failures = [name for name, ok in checks.items() if ok is not True]
    if failures:
        return {"decision": "pause", "reasons": failures, "metrics": {}}
    if set(inputs) & set(case["calculations"]):
        raise ValueError("calculation names cannot shadow input fields")
    values = {key: None if value is None else Decimal(value) for key, value in inputs.items()}
    metrics = {}
    try:
        with localcontext() as context:
            context.prec = 40
            for name, formula in case["calculations"].items():
                number = expression(formula, values)
                if type(number) is not Decimal or not number.is_finite():
                    raise ValueError("calculation must return a finite decimal")
                values[name] = number
                metrics[name] = format(number, "f")
            clear = expression(case["when"], values)
    except MissingInput as missing:
        return {"decision": "pause", "reasons": [f"missing:{missing.args[0]}"], "metrics": metrics}
    if type(clear) is not bool:
        raise ValueError("decision predicate must return a boolean")
    decision = case["if_true"] if clear else case["if_false"]
    return {"decision": decision, "reasons": [], "metrics": metrics}
