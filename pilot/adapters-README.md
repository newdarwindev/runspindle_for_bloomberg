# Synthetic adapter contracts (v0.1)

Issue #6 now has a narrow observation and paper destination contract in
[`adapters.py`](adapters.py), integrated with the [synthetic run coordinator](runtime-README.md).
The [sanitized case 10 fixture](fixtures/case-10-observation.v1.json) contains
fictional values only. `python3 scripts/run_synthetic_demo.py --check`
verifies the committed [end-to-end synthetic traces](demo-runs.v1.json).

## Observation contract

`ObservationRequest` binds the synthetic account, session, exact instrument,
and route. `SyntheticObservationAdapter.observe` returns an
`ObservationResult` with `status`, optional values, and a metadata receipt.
The only allowed route is `synthetic:case-10-dividend`. The fixture represents
the two dated closes and one cash dividend from catalog case 10; it does not
assert actual DVD or TRA command behavior.

Statuses are `ok`, `route_blocked`, `identity_mismatch`, `target_mismatch`,
`not_entitled`, `missing`, `invalid_timestamp`, and `stale`. Only `ok` provides
values and can create a run. The receipt identifies the fixture, timestamp,
entitlement result, age limit, and SHA-256 of selected fixture fields. Wrong
identity/route/target responses omit fixture provenance and entitlement
detail. No password, token, account credential, screenshot, or protected
market value is included in a receipt. This is metadata hygiene for a
synthetic fixture, not a ruling on live data rights.

The runtime checks source age again before preview, approval, and submission.
Changing an adapter-backed observation requires a new sourced run; an
operator cannot silently replace its values while retaining the receipt.

## Destination contract

`SyntheticPaperDestination` exposes `draft`, `approve`, `execute`, and
`readback`. Each stage produces a sanitized receipt tied to the exact draft
hash or stable operation ID. `execute` requires the bound synthetic route,
approval, and `submitting` state. The journal table has a unique operation
ID. A lost response leaves the run uncertain; readback by that ID must find
matching account, instrument, and draft hash before the runtime marks the
simulated effect confirmed. An absent readback remains inconclusive; it never
permits an automatic retry. A mismatch pauses the run.

The runtime accepts a readback receipt only for the current adapter version,
readback stage, configured route and original operation. Confirmation and
mismatch require a journal reference hash. An inconclusive absence has no
journal reference. An unrecognized receipt leaves the prior ledger state intact.

The journal and run ledger share one SQLite database. Their distinct methods
exercise the contract but are **not independent external systems**. A
confirmed synthetic journal row is not Bloomberg acceptance, a NOTE write,
or an independently verified real-world effect.

## Live access blocker

Issue #2 has not established a written permitted Terminal/API route,
entitlements, field rights, retention/export rules, or authorized destination
for this workflow. No Bloomberg or other live adapter is present. The
runtime rejects any non-synthetic account or observation route. A live
adapter must wait for those decisions, qualified domain review of the
dividend calculation, and an independently checkable destination readback.
