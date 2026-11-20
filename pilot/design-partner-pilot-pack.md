# Design-partner pilot pack (draft v0.1)

**Decision:** no live pilot is authorized. Issue #2 has no permitted access and
data-rights decision. Issues #4–#8 still have pilot gates requiring real owners,
external readback, domain review, and security review. No design partner,
signed plan, consent, or live run record is present in this repository.

This pack prepares the evidence format for issue #9. The
[plan template](design-partner-plan.template.json) leaves all real approvals
and identities blank. `python3 scripts/pilot_preflight.py
pilot/design-partner-plan.template.json` lists the blockers. The validator is
structural: even a filled live plan returns `pilot_ready: false`, because this
repository has no way to authenticate signatures, permissions, or a live
adapter. A qualified owner must review those externally before any first run.

## Agreement to complete before a pilot

| Decision | Required recorded evidence |
| --- | --- |
| Partner, buyer, operator, reviewer | Pseudonymous codes in the register; privately held identity and consent records; reviewer separate from operator. |
| Task and cohort | Frozen trigger, exact instrument/record rules, consecutive eligible episodes, start/end window, and maximum episodes. Include ordinary work, stops, and setup failures. |
| Access and permitted effects | Issue #2 written rights matrix; bound account/session; approved source route and destination; precise allowed effects and approvals. |
| Withdrawal and support | Withdrawal/fence procedure, incident route, on-call owner, support hours, and escalation contacts. |
| Acceptance | Signed case contract, independent source and destination checks, outcome taxonomy, quality limits, and duplicate-effect rule. |
| Comparison | Frozen protocol hash, matched native/expert/deterministic alternatives, authority and budget parity, and predeclared holdout families. |
| Public claims | Separate issue #2 claims approval; no pilot result is automatically publishable. |

The plan needs signatures and versioned references outside this template. A
plan hash binds each register to one exact version. If scope, rights, or
acceptance criteria change, stop collection and start a new versioned plan.

## Episode register

`pilot/partner_register.py` has a local append-only SQLite register for
**synthetic rehearsal only**. It rejects live mode. Call
`record_eligible(episode_id, eligible_at)` when a qualifying trigger occurs.
The append-only intake sequence enforces the frozen period and episode limit,
including episodes whose outcomes are pending. Append the outcome separately
using the exact retained episode ID and timestamp. Outcomes can arrive out of
intake order. Each outcome records source and destination
references, reviewer ID, boundary flag, human-active time, elapsed time,
quality errors, full cost, support time, and three baseline slots. Unknown
metrics remain `null`; they are never treated as zero. Accepted completions
need source, destination, and reviewer references. Summary reports show
registered, reported and pending counts. Version 1 registers open read-only
and report eligibility and pending counts as unknown. Reconcile the local
intake against an independent trigger log during a real pilot to check for
omitted episodes.

The [synthetic demo](register-demo.v2.json) includes a completion, a correct
refusal, and a setup failure to exercise the schema. Its `evidence_level` is
`synthetic_rehearsal_only`; `live_acceptance` and the product decision are
`null`. The references beginning `synthetic:` are placeholders, not verified
receipts. Run `python3 scripts/rehearse_pilot_register.py --check` to reproduce
it. Keep any future consent-safe partner records in the ignored
`local-pilot/` directory or an approved private system, never in this public
repository.

## Pilot execution and debrief

For every eligible episode, record the trigger before seeing its outcome.
Record ordinary success, correct refusal, unknown effect, boundary failure,
produced-only output, setup failure, and withdrawal without cherry-picking.
Do not repeat a consequential action after a lost response; reconcile its
stable operation ID. Match alternatives on the same task boundary, rights,
budget, and reviewer acceptance rule. The [evaluation protocol](../evaluation/protocol.v1.md)
and [cost model](../economics/README.md) define the planned metrics and cost
denominator.

The synthetic register requires the reviewer named in the plan and both
synthetic evidence references for an accepted baseline completion. A correct
baseline refusal requires the reviewer. Existing records stay readable, and
a comparison with missing baseline evidence is incomplete in the summary.

Interview the operator and economic buyer after the register is locked. Ask
for recent episodes where the tool saved active work, shifted review/support
work, failed, correctly stopped, or lost to native software or a conventional
integration. Record specific evidence and contrary views with consent-safe
notes; stated interest is not an accepted completion.

## Decision record template

| Item | Status |
| --- | --- |
| Signed pilot plan and rights | Missing |
| Consecutive run register | Missing; synthetic demo only |
| Independently verified live outcomes | Missing |
| Matched baseline and uncertainty | Missing |
| Full-cost economics and support burden | Missing |
| Operator/buyer debrief | Missing |
| Go / iterate / stop recommendation | **Stop before pilot** until gates pass |

A later decision memo must show denominators, failures, unknown effects,
quality, cost, support burden, and disconfirming evidence. A go decision
requires the signed gates and independently verified live effects; an iterate
or stop decision is valid when the evidence warrants it.
