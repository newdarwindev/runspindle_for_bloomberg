"""Independent read-only replay checks for a small, frozen synthetic cohort."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .independent import sha_obj, sha_text


def snapshot(path):
    """Read observation, event, and simulated effect records in one SQLite snapshot."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        return {
            "runs": {row["id"]: json.loads(row["data"]) for row in db.execute("SELECT * FROM runs")},
            "events": {row["seq"]: dict(row) for row in db.execute("SELECT * FROM events")},
            "journal": {row["operation_id"]: dict(row) for row in db.execute("SELECT * FROM journal")},
        }


def _new_rows(before, after, label, errors):
    if any(after.get(key) != value for key, value in before.items()):
        errors.append(f"existing {label} changed during scenario")
    return [value for key, value in after.items() if key not in before]


def _check_chain(rows, run, expected, errors):
    previous = "0" * 64
    names = []
    if any(row["run_id"] != run["id"] for row in rows):
        errors.append("events for an unexpected run")
    for revision, row in enumerate(sorted(rows, key=lambda row: row["seq"]), 1):
        payload = json.loads(row["payload"])
        names.append(payload["action"])
        if (
            row["prev_hash"] != previous
            or row["event_hash"] != sha_text(previous + row["payload"])
            or payload["revision"] != revision
        ):
            errors.append("invalid replay event chain")
            break
        previous = row["event_hash"]
    if names != expected:
        errors.append("replay event actions differ from frozen expectation")
    if not rows or json.loads(max(rows, key=lambda row: row["seq"])["payload"]).get("snapshot_sha256") != sha_obj(run):
        errors.append("replay snapshot integrity mismatch")


def _effect_within_authority(run, row):
    receipt = run["source_receipt"]
    try:
        committed = datetime.fromisoformat(row["committed_at"])
        observed = datetime.fromisoformat(receipt["observed_at"].replace("Z", "+00:00"))
        lease = datetime.fromisoformat(run["lease_until"])
        deadline = datetime.fromisoformat(run["deadline"])
        age = (committed - observed).total_seconds()
        return committed < min(lease, deadline) and 0 <= age <= receipt["max_age_seconds"]
    except (KeyError, AttributeError, TypeError, ValueError):
        return False


def _check_effect(run, rows, expected, errors):
    operation = run.get("operation_id")
    binding = (run["account_id"], run["instrument_id"], run.get("draft_hash"))
    if expected == "none":
        if rows:
            errors.append("unexpected simulated journal effect")
    else:
        if len(rows) != 1 or rows[0]["operation_id"] != operation:
            errors.append("missing, duplicate, or unrelated journal effect")
            return
        row = rows[0]
        observed = row["account_id"], row["instrument_id"], row["draft_hash"]
        target = binding if expected == "exact" else (binding[0], "WRONG", binding[2])
        if observed != target:
            errors.append("unexpected journal effect binding")
        if not _effect_within_authority(run, row):
            errors.append("journal effect outside source freshness, lease, or deadline")
    readbacks = [r for r in run["destination_receipts"] if r["stage"] == "readback"]
    status = {"unknown": "absent_inconclusive", "mismatch": "mismatch", "confirmed": "confirmed"}
    expected_status = status.get(run["effect_status"])
    if expected_status is None and readbacks:
        errors.append("unexpected readback receipt")
    if expected_status is not None and (
        len(readbacks) != 1 or readbacks[0]["status"] != expected_status
        or readbacks[0]["operation_id"] != operation
        or readbacks[0]["journal_ref_sha256"] != (sha_obj(rows[0]) if rows else None)
    ):
        errors.append("readback receipt differs from independent ledger")


def _check_revision(run, spec, errors):
    if "draft" not in spec:
        return
    observation = run["observation"]
    prior = Decimal(observation["prior_close"])
    current = Decimal(observation["current_close"])
    cash = Decimal(observation["cash_dividend"])
    raw, adjusted = str((current - prior) / prior), str((current + cash - prior) / prior)
    draft = {"raw_return": raw, "cash_adjusted_return": adjusted,
             "decision": "pass" if Decimal(raw) < 0 < Decimal(adjusted) else "pause"}
    if draft != spec["draft"] or run["draft"] != draft or run["draft_hash"] != sha_obj(draft):
        errors.append("revised draft differs from independent arithmetic")


def verify_delta(path, before, run_id, spec):
    """Verify both required effects and the absence of unplanned side effects."""
    after = snapshot(path)
    errors = []
    runs, events, journal = (_new_rows(before[key], after[key], key, errors)
                             for key in ("runs", "events", "journal"))
    if "state" not in spec:
        if run_id is not None or runs or events or journal:
            errors.append("blocked observation created durable state or a journal effect")
        return errors
    if len(runs) != 1 or runs[0]["id"] != run_id:
        return errors + ["scenario did not create exactly its own run"]
    run = runs[0]
    if (run["state"], run["effect_status"], run["submissions"]) != (
        spec["state"], spec["effect_status"], spec["submissions"]
    ):
        errors.append("durable run conclusion differs from frozen expectation")
    _check_chain(events, run, spec["events"], errors)
    _check_effect(run, journal, spec["journal"], errors)
    _check_revision(run, spec, errors)
    return errors
