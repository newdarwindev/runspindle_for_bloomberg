# Synthetic replay corpus, version 1

Issue #7's first reproducible artifact transcribes all 40 supplied cases into
`fixtures.v1.json`. Run `python3 scripts/replay_corpus.py --check` to confirm
that the committed corpus still matches both source CSVs. Regenerate it with
`python3 scripts/replay_corpus.py` after an intentional source change.

Each fixture separates source observation, decision text, verification text,
and source URLs. The `review_status` is deliberately
`unverified_source_prose`: the CSV does not supply machine-readable market
observations, independently validated calculations, or permissioned effects.
Editorial rank is not measured demand or performance. A qualified reviewer
must turn a selected case into a finance-specific executable fixture before a
passing run can be described as domain-correct.

## Executable arithmetic for all 40 cases

The [synthetic finance protocol](finance-protocol.v1.md) adds normalized inputs,
decision rules, a separately authored answer sheet, and a reproducible report
for all 40 cases. Run `python3 scripts/replay_finance.py --check` to verify the
calculations and case-specific pauses against the frozen expectations. The
report also checks both decision branches for the ten cases whose baseline
rules are missing. The source catalog remains the provenance record. Case 10
has a durable operational replay covering authority and journal readback.

## Run classification

`python3 scripts/verify_replay.py runs.json` reads an array of run records and
prints one classification per run. A record has a unique `run_id`, an integer
`fixture_id`, and `decision` (`execute`, `refuse`, or `pause`). Optional fields
are `boundary_violation` (boolean), `effect_status` (`confirmed` or `unknown`),
`authorized` (boolean), `approval_receipt`, `source_receipt`,
`destination_readback` (nonempty evidence references), and
`independent_review` (`accepted` or `correct_refusal`).

The classifier gives precedence to a boundary failure and an unknown effect.
An executed run is an accepted authorized completion only when it has
confirmed effect status, authority, approval, source and readback references,
and independent review. Everything else is produced-only. A pause or refusal
needs independent review to be labeled correct. Evidence references and review
labels are supplied by the evaluator, so this script checks their presence; it
does not authenticate them or independently verify finance calculations.

The [case 10 replay protocol](protocol.v1.md) now adds one executable
synthetic fixture, ten negative cases, a separate read-only verifier, and a
deterministic report. The other 39 cases do not yet have a durable operational replay.
Do not publish a completion rate from these fixtures alone. Issue #7 still
needs domain-reviewed calculations across the selected corpus, real matched
baselines, holdout families, human time, latency, full cost, and uncertainty.
Live acceptance depends on separate access and pilot gates.

The [case 10 protocol v2](protocol.v2.md) independently verifies ledger and
simulated journal evidence for every case 10 scenario, including refusals and
unresolved outcomes. The v1 protocol and report are retained as historical
evidence.
