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
synthetic fixture, ten negative cases, and a deterministic report. The independent
verifier checks ledger and simulated journal evidence for every scenario,
including refusals and unresolved outcomes. The other 39 cases remain unreviewed source prose.
Do not publish a completion rate from these fixtures alone. Issue #7 still
needs domain-reviewed calculations across the selected corpus, real matched
baselines, holdout families, human time, latency, full cost, and uncertainty.
Live acceptance depends on separate access and pilot gates.
