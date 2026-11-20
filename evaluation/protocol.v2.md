# Synthetic case 10 replay protocol v2

The cohort is the same baseline and ten adverse cases defined in
[protocol v1](protocol.v1.md). The earlier [manifest](case-10-executable.v1.json)
and [report](replay-report.v1.json) remain available as historical evidence.
The v2 [executable protocol](case-10-executable.v2.json) fixes the outcome,
event sequence, submission count and journal expectation for each case.

A separate read-only connection takes consistent SQLite snapshots before and
after each scenario. Blocked observations must leave no run, event, or journal
record. Started cases must write only the expected run, chain, and journal
entries. Prior states and effects must stay unchanged. The verifier binds
journal rows to their runs and checks the commit timestamp against source
freshness, the lease, and the deadline. A synthetic referee checks case 10's
arithmetic and receipts independently. A refusal or mismatch label alone
cannot pass.

Run both commands from the checkout:

```sh
python3 scripts/replay_corpus.py --check
python3 scripts/replay_case10.py --check
```

The second command reproduces the [v2 report](replay-report.v2.json).
It fails if any scenario fails or the report differs. The journal is a local
simulation. Domain review of the calculation, executable fixtures for the other
39 cases, permissioned data, measured baselines, and production acceptance
remain separate gates. The v1 matched-baseline measurement plan still applies.
