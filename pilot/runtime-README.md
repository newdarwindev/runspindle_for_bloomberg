# Synthetic run coordinator (v0.3.0)

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
snapshot. Every new event binds the entire canonical run snapshot, including
owner/account/session, approval, allowed actions, leases, budgets and versions.
Status and all transitions verify the chain and that binding before returning a
run or invoking a destination. Reads use one SQLite snapshot, including while a
concurrent valid writer commits. Precommit cancellation-style exceptions roll
back the transition; interruption during commit may still have an uncertain
outcome and requires reopening and reconciliation. This detects ordinary corruption; it is not tamper-proof against a
database administrator and has no external integrity anchor.

The only destination is a local simulated journal table. A submission first
persists `submitting`. Its simulated effect and response then commit under a
state fence. The `success` response still waits for readback. A timeout after
commit leaves `uncertain`; readback by operation ID can confirm it. A missing
readback stays `uncertain` because absence may be inconclusive. Before recording
a readback, the runtime independently derives the receipt from the bound journal
row inside the same transaction. The adapter gets a detached snapshot. A receipt
that differs from the journal or an adapter write through the observation
transaction aborts the transition. A duplicate
submit is rejected. Cancellation fences new submissions but preserves an
unknown or confirmed effect for reconciliation. Takeover clears approval. If
it commits after submission intent and before execution, the destination call
is fenced. Handback before any possible effect discards the previous draft and
requires a fresh preview and approval. Handback after a possible effect retains
the exact draft hash, operation ID and budget and returns to uncertain for
readback. A mismatch after restore stays fenced from revision and submission,
even if the restored snapshot reports zero submissions.
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

On restart, open the same database with `Runtime(path, create=False)`. If a run is `submitting`, call `recover`
with the bound identity; it becomes `uncertain`, never auto-submits. Read back
before any further decision. The schema version is 1. Unknown versions fail
closed. Opening checks the v1 tables and both append-only triggers under one
SQLite transaction. A missing journal, changed trigger, or missing or duplicated
version marker blocks opening before the destination adapter is constructed.
The runtime creates a schema and its version marker in one transaction when
opening an empty store with creation enabled. The inspection CLI always opens
an existing store. Supported existing v1 stores preserve their schema and data.

Pre-v0.3.0 runs lack the full-snapshot binding: status and transitions
reject them instead of silently sealing potentially changed state. Do not edit
old events or replay a possibly submitted operation. Retain such stores for
inspection and independent reconciliation; migration tooling is still required.
New synthetic runs can be created in a fresh store. The SQL schema remains 1;
the event contract change is identified by runtime version 0.3.0. Before changing schema, take a consistent SQLite backup (for example,
Python `sqlite3.Connection.backup`), migrate a copy, and validate event chains.
Rollback restores the backup; do not merge later journal effects into an old
snapshot without reconciliation. A production migration and rollback tool
remain outstanding.

This slice does not authenticate operator identity, source data, or journal
receipts beyond the supplied IDs and local store. It has no live credentials,
secrets, network calls, external effects, measured savings, or pilot acceptance.
Issue #2's permission gate remains in force.

## Integrity verification scope

The handback regression verifies the local journal from a separate SQLite
connection, then reads back after handback in a fresh process. A second
connection also takes over between the committed intent and the effect call.
The synthetic prototype requires an explicit readback before a simulated
record can enter review and retains uncertainty after an inconclusive result.

`python3 -m unittest discover -s tests -p test_runtime_integrity.py -v` tests
14 corrupted authority/state fields across six read/action paths in fresh
processes, with independent zero-effect SQLite observations. A deliberate guard
mutation produces an actual local journal row, showing the effect fence matters.
Malformed state, legacy unsealed events, concurrent valid writes and precommit
interruption are covered separately. The independent case-10 verifier also
checks the full snapshot using its own hashing implementation and read snapshot.
Raw `events()` and `monitor.py` counters remain diagnostic data, not verified
execution authority or external acceptance. Unkeyed hashes do not resist a
database writer recomputing valid seals. Whole-store rollback/replay also remains
outside this local integrity check; no external trust anchor, authenticated
identity or live rights have been added. Issues #5 and #8 remain open for the
integrated pilot gates.

`python3 -m unittest discover -s tests -p test_runtime_schema.py -v` checks v1
compatibility, incomplete and future schemas, inspection of a missing or empty
store, concurrent bootstrap and process exit before the schema transaction
commits. Dropping the journal from a run after simulated submission blocks the
fresh process with zero destination readback calls. Running that test against
the prior runtime reaches the independent readback marker and fails. These
checks exercise SQLite files on a local filesystem. Power loss and recovery
from a wholly lost or rolled-back store still require separate evidence.

### Final submission fence

The second submission transaction rechecks the bound operator/account/session,
lease, deadline and source freshness immediately before the simulated destination
call. A pause after the committed `begin_submission` event is not continuing
authority. If these checks fail, no destination call occurs: the retained
`submitting` intent and consumed submission budget remain for recovery. Reopening
and `recover` changes it to `uncertain`; readback may report absence as
inconclusive, never reset the budget or automatically resubmit.

`tests/test_runtime_final_authority.py` crosses each time boundary between the
two transactions in both success and timeout-after-commit modes. It counts zero
destination calls, reopens in a fresh process, and independently checks zero
journal rows and exactly one submission intent. This is a local transaction
boundary check, not remote revocation or proof against expiry during an already
running external action. A future real adapter needs its own effect-time fence.
