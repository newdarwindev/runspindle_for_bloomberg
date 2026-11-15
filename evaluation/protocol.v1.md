# Synthetic replay protocol v1

This protocol defines the issue #7 repository replay before any permissioned
pilot measurement. The [40-case corpus](fixtures.v1.json) remains source prose.
Only [case 10](case-10-executable.v1.json) has an executable synthetic fixture.
Its arithmetic and corporate-action convention still need a qualified domain
reviewer. The committed [report](replay-report.v1.json) is deterministic
software evidence, not market acceptance or an ROI result.

## Cohort and outcomes

The fixed cohort is one synthetic baseline and the ten named negative cases
in the case 10 protocol: stale or missing data, wrong instrument, entitlement
failure, declined approval, lost responses before and after commit, duplicate
delivery, destination mismatch, and later mark revision. Run all cases in
the listed order. Do not drop failures or replay a consequential effect to
improve a rate. The only simulated external effect is a local paper journal
row with a unique operation ID.

`synthetic_verified` means the separate read-only verifier recomputed the
arithmetic and checked the source fixture, hashes, event order, approval,
operation ID, and local journal readback. `synthetic_rejected` means at least
one of those checks failed. `unknown_effect` remains unresolved after an
inconclusive readback. A correct pause/refusal is recorded separately from
an executed run. `produced_only` is an output without the required approval
and readback evidence. `boundary_failure` is any unauthorized source or
effect. None of these labels is a live accepted completion.

## Measurement plan for a later pilot

Use consecutive eligible episodes. Predeclare the task boundary, instrument,
account, access rights, operator, budget, deadline, and acceptance check for
each episode. Record run and reviewer IDs, source and destination receipts,
human-active seconds, elapsed seconds, quality errors, recovery effort, model
and tool versions, and full cost. Report accepted authorized completions,
correct refusals, unknown effects, produced-only outputs, and boundary
failures with denominators and uncertainty. A zero accepted denominator has
no unit cost. The current synthetic report leaves human time, latency,
full cost, and live acceptance unknown.

Match native Terminal, expert-assisted, deterministic integration, and
Runspindle alternatives on the same eligible episodes, authority, source
rights, budget, and acceptance criteria. Hold out whole task families before
model or rule tuning. Record each alternative's version and setup/support
cost. The [full-cost model](../economics/README.md) can consume measured
inputs; the ranking CSV cannot substitute for them. No baseline comparison
or holdout result is claimed by this replay.

## Reproduction and limits

Run `python3 scripts/replay_corpus.py --check`, then
`python3 scripts/replay_case10.py --check`. The latter builds a fresh temporary
SQLite database and compares its report with the committed JSON. The
independent verifier reads that database directly and does not import the
runtime's decision or ledger methods. It still observes the same local
simulated journal, so it cannot establish an external effect or legal data
rights. A live test waits on issue #2 and a signed pilot contract.
