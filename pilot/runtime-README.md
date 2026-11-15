# Synthetic run coordinator (v0.2.0)

`pilot/runtime.py` is a local SQLite composition for the [case 10 draft](case-10-contract-v0.1.md).
It is a test runtime, not a Bloomberg integration or an authorized pilot.
Only account IDs beginning `synthetic:` can create runs. The model version is
explicitly `none`; no model is invoked. `paper_decision` applies the synthetic
arithmetic and pauses when required source conditions are not confirmed.
The [adapter contracts](adapters-README.md) now supply source receipts and
paper destination stage receipts for adapter-backed runs.

Run `python3 scripts/run_synthetic_demo.py --check` to verify the committed
[demo traces](demo-runs.v1.json), or omit `--check` to regenerate them. Run
`python3 -m unittest tests.test_runtime -v` for integration tests. To inspect
a database made through the Python `Runtime` API, run
`python3 scripts/inspect_run.py path/to/runs.sqlite RUN_ID`.

## Persisted contract

Each run snapshot stores revision, owner, exact instrument, synthetic account
and session, observation artifact hash, draft hash, stable operation ID,
approval actor, allowed action, one-submission budget, lease, deadline, state,
effect status, and runtime/model versions. Every transition appends an actor
and timestamp event with a hash of the prior event. SQLite triggers reject
event updates and deletes. `verify_chain` checks the chain and its final
snapshot. This detects ordinary corruption; it is not tamper-proof against a
database administrator and has no external integrity anchor.

The only destination is a local simulated journal table. A submission first
persists `submitting`. Its simulated effect and response then commit under a
state fence. The `success` response still waits for readback. A timeout after
commit leaves `uncertain`; readback by operation ID can confirm it. A missing
readback stays `uncertain` because absence may be inconclusive. A duplicate
submit is rejected. Cancellation fences new submissions but preserves an
unknown or confirmed effect for reconciliation. Takeover clears approval;
handback requires a new preview and approval.
Revising the synthetic observation before submission creates a new revision
and invalidates the previous draft and approval.
An adapter-backed observation requires a new sourced run instead of an
in-place revision, so its source receipt remains bound to the exact values.

Status and readback remain available after a lease or deadline expires for
the same bound owner/account/session. State-changing work requires an active
lease and deadline. There is no session rebinding or multi-operator role
model in this slice, so an expired session may require manual repair outside
this prototype. The local journal is a separate logical readback path in one
database, not an independent external acceptance source.
The [security review pack](../operations/security-review-v0.1.md) documents
synthetic failure injection, monitoring, revocation, and rollback quarantine.

## Recovery and schema

On restart, open the same database. If a run is `submitting`, call `recover`
with the bound identity; it becomes `uncertain`, never auto-submits. Read back
before any further decision. The schema version is 1. Unknown versions fail
closed. Before changing schema, take a consistent SQLite backup (for example,
Python `sqlite3.Connection.backup`), migrate a copy, and validate event chains.
Rollback restores the backup; do not merge later journal effects into an old
snapshot without reconciliation. A production migration and rollback tool
remain outstanding.

This slice does not authenticate operator identity, source data, or journal
receipts beyond the supplied IDs and local store. It has no live credentials,
secrets, network calls, external effects, measured savings, or pilot acceptance.
Issue #2's permission gate remains in force.
