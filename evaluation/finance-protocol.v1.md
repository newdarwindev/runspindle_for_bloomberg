# Synthetic finance corpus protocol v1

The fixed cohort is source case IDs 1 through 40, in numerical order. The
[source catalog](fixtures.v1.json) provides case names, problem statements,
verification text, and source links. The [replay inputs](finance-fixtures.v1.json)
provide normalized numeric values, calculation trees, decision predicates,
and factual checks. The [expectation sheet](finance-expected.v1.json) fixes
the independently transcribed answers and decisions. It also records the
existing synthetic family assignments, holdout families, and required adverse
checks for each case. The verifier compares the fixture and generated report
against that inventory. Dropped or renamed checks and changed family or split
assignments invalidate the run. Scan the whole cohort one time and keep every
calculation mismatch in the report.

The runner uses Decimal arithmetic with 40 significant digits and rounds
half up only at explicit fixture steps. The separate verifier compares
numeric values as exact fractions against the frozen answer sheet. A check
runs once with its stated synthetic input and once with that particular check
false. A false or unknown check pauses before calculation. If the named
decision threshold is missing, the run pauses without discarding arithmetic
that was already verified. An unavailable rule or value is never zero.

`stage_draft` and `stage_paper` describe hypothetical fixture decisions.
`pass` means pass on the opportunity in the source examples. `review` and
`review_bond_b` describe further investigation. None of these outcomes is
approval, a trade, a claim, a verified external effect, or measured task quality.
Case 10 also has a separately specified [durable replay](protocol.v1.md) for
approval, duplicate delivery, uncertainty, and readback.

## Partitions and measurement

Whole FX, rates, and options families are reserved for later holdout. The
remaining families form the development partition. This partition does not
establish a trained model, an empirical holdout result, or proof against
leakage. The synthetic expected answers are public.

Keep the [matched-baseline plan](protocol.v1.md#measurement-plan-for-a-later-pilot)
for any permissioned pilot. Native, expert-assisted, deterministic, and
Runspindle alternatives must use the same authority, source rights, budget,
eligible episodes and independent acceptance checks. Keep accepted authorized
completion, correct refusal, uncertain effect and produced-only output distinct.
Record human-active seconds, latency, quality, cost, uncertainty, and model/tool
versions separately. The synthetic report uses null for unmeasured values.

## Reproduction and review

Run `python3 scripts/replay_finance.py --check` from the checkout.
It validates provenance, frozen expectations, and the committed
[finance report](finance-report.v1.json). Use only synthetic values.
Columns and calculation conventions still require a qualified domain reviewer
before use in a pilot. Several cases expressly model a conditional branch
and state the assumptions used for that branch. The evaluation never calls a
market data provider or loads any live account.
