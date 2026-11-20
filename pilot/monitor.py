"""Read-only evidence for the local synthetic run ledger."""
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from pilot.adapters import paper_readback_receipt
from pilot.runtime import IntegrityError, run_events, schema_objects, verified_events, verify_schema


def _readback_matches(run, observed):
    recorded = next((receipt for receipt in reversed(run["destination_receipts"])
                     if receipt["stage"] == "readback"), None)
    return recorded == observed and run["destination"] == observed["route"]


def _summarize(db):
    verify_schema(db, schema_objects(db))
    if db.execute("SELECT 1 FROM events LEFT JOIN runs ON runs.id=events.run_id "
                  "WHERE runs.id IS NULL LIMIT 1").fetchone() is not None:
        raise IntegrityError("Synthetic ledger contains orphaned events")

    journal = {row["operation_id"]: row for row in db.execute("SELECT * FROM journal")}
    actions = defaultdict(set)
    owned, exact_journal = set(), set()
    runs = stopped = unknown = interrupted = confirmed = conflicts = 0
    for row in db.execute("SELECT id,data FROM runs"):
        run_id, raw = row
        run = json.loads(raw)
        history = verified_events(run_id, run, run_events(db, run_id))
        for event in history:
            if event["operation_id"]:
                actions[event["action"]].add(event["operation_id"])
        names = {event["action"] for event in history}
        runs += 1
        stopped += bool(names & {"decline", "pause", "cancel", "readback_mismatch", "revoke"})
        unknown += run["effect_status"] == "unknown"
        interrupted += run["state"] == "submitting"

        operation = run["operation_id"]
        if operation is None:
            if run["effect_status"] == "confirmed":
                raise IntegrityError("Confirmed effect lacks an operation identity")
            continue
        if operation in owned:
            raise IntegrityError("Synthetic ledger has ambiguous operation ownership")
        owned.add(operation)
        bound_actions = {"begin_submission", "readback_confirmed", "readback_mismatch"}
        bound = {event["action"] for event in history
                 if event["operation_id"] == operation and event["action"] in bound_actions}
        observed = paper_readback_receipt(run, journal.get(operation))
        exact = observed["status"] == "confirmed" and run["destination"] == observed["route"]
        if bound and exact:
            exact_journal.add(operation)
        if run["effect_status"] == "confirmed":
            supported = ("readback_confirmed" in bound and exact and _readback_matches(run, observed))
            confirmed += supported
            conflicts += not supported

    return {"evidence_level": "synthetic_local_only", "runs": runs,
            "queued_operation_count": len(actions["begin_submission"]),
            "emitted_operation_count": len(actions["adapter_response"] | actions["adapter_timeout"]),
            "stopped_run_count": stopped, "simulated_journal_row_count": len(journal),
            "simulated_journal_exact_count": len(exact_journal),
            "simulated_journal_unbound_count": len(journal) - len(exact_journal),
            "recorded_readback_confirmation_count": len(actions["readback_confirmed"]),
            "simulated_readback_confirmed_count": confirmed,
            "simulated_readback_conflict_count": conflicts,
            "simulated_readback_mismatch_count": len(actions["readback_mismatch"]),
            "unknown_effect_run_count": unknown, "interrupted_run_count": interrupted,
            "external_observed_count": None, "source_rejection_count": None}


def summarize(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        try:
            return _summarize(db)
        except (KeyError, TypeError, ValueError):
            raise IntegrityError("Malformed synthetic ledger evidence") from None
