"""Read-only synthetic case 10 verifier; does not import the runtime."""
import hashlib
import json
import sqlite3
from datetime import datetime
from decimal import Decimal

SOURCE_FIELDS = ("prior_date", "current_date", "prior_close", "current_close",
                 "cash_dividend", "no_other_corporate_action")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha_text(value):
    return hashlib.sha256(value.encode()).hexdigest()


def sha_obj(value):
    return sha_text(canonical(value))


def verify_case10(db_path, run_id, fixture, protocol):
    """Verify source, arithmetic, ledger, approval, and local journal readback."""
    errors = []
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return {"status": "synthetic_rejected", "errors": ["run missing"]}
        run = json.loads(row["data"])
        events = list(db.execute("SELECT payload,prev_hash,event_hash FROM events WHERE run_id=? ORDER BY seq", (run_id,)))
        previous = "0" * 64
        actions = []
        for event in events:
            if event["prev_hash"] != previous or event["event_hash"] != sha_text(previous + event["payload"]):
                errors.append("event chain mismatch")
                break
            previous = event["event_hash"]
            actions.append(json.loads(event["payload"]))
        if not actions or actions[-1].get("revision") != run.get("revision") or actions[-1].get("state") != run.get("state"):
            errors.append("final event differs from run snapshot")
        if run.get("artifact_hash") != sha_obj(run.get("observation")):
            errors.append("observation artifact hash mismatch")
        receipt = run.get("source_receipt") or {}
        fixture_hash = sha_obj({key: fixture.get(key) for key in
                                ("fixture_id", "instrument_id", "observed_at", "entitled", *SOURCE_FIELDS)})
        if (receipt.get("status") != "ok" or receipt.get("entitlement") != "confirmed" or
                receipt.get("fixture_sha256") != fixture_hash or
                receipt.get("observed_at") != fixture.get("observed_at")):
            errors.append("source receipt mismatch")
        observation = run.get("observation") or {}
        if (run.get("account_id") != fixture.get("account_id") or
                run.get("session_id") != fixture.get("session_id") or
                observation.get("instrument_id") != fixture.get("instrument_id") or
                observation.get("source_timestamp") != fixture.get("observed_at") or
                observation.get("entitled") is not True or observation.get("fresh") is not True or
                any(observation.get(key) != fixture.get(key) for key in SOURCE_FIELDS)):
            errors.append("observation differs from source fixture")
        try:
            prior = Decimal(str(observation["prior_close"]))
            current = Decimal(str(observation["current_close"]))
            cash = Decimal(str(observation["cash_dividend"]))
            raw = str((current - prior) / prior)
            adjusted = str((current + cash - prior) / prior)
            expected = protocol["expected"]
            if (raw, adjusted) != (expected["raw_return"], expected["cash_adjusted_return"]):
                errors.append("independent arithmetic differs from frozen expectation")
            decision = "pass" if Decimal(raw) < 0 < Decimal(adjusted) else "pause"
            if decision != expected["decision"] or run.get("draft") != {
                    "raw_return": raw, "cash_adjusted_return": adjusted, "decision": decision}:
                errors.append("draft differs from independent arithmetic")
        except (KeyError, ZeroDivisionError, ArithmeticError, ValueError):
            errors.append("independent arithmetic unavailable")
        if run.get("draft_hash") != sha_obj(run.get("draft")):
            errors.append("draft hash mismatch")
        approval = next((event for event in actions if event.get("action") == "approve"), None)
        action_names = [event.get("action") for event in actions]
        required_order = ("create", "preview", "approve", "begin_submission", "readback_confirmed")
        if (any(action_names.count(action) != 1 for action in required_order) or
                [action_names.index(action) for action in required_order] !=
                sorted(action_names.index(action) for action in required_order)):
            errors.append("required event order or uniqueness mismatch")
        if not approval or run.get("approval_actor") != run.get("owner_id"):
            errors.append("approval missing or wrong actor")
        else:
            expected_operation = sha_obj([run_id, approval["revision"],
                                          "synthetic-paper-journal", run.get("draft_hash")])
            if run.get("operation_id") != expected_operation:
                errors.append("operation ID mismatch")
        if run.get("submissions") != 1 or run.get("state") != "recorded" or run.get("effect_status") != "confirmed":
            errors.append("run has no confirmed synthetic effect")
        journal = db.execute("SELECT * FROM journal WHERE operation_id=?", (run.get("operation_id"),)).fetchone()
        if journal is None or (journal["account_id"], journal["instrument_id"], journal["draft_hash"]) != (
                run.get("account_id"), run.get("instrument_id"), run.get("draft_hash")):
            errors.append("journal readback mismatch")
        receipts = run.get("destination_receipts") or []
        if ([item.get("stage") for item in receipts[:2]] != ["draft", "approval"] or
                not receipts or receipts[-1].get("stage") != "readback" or
                receipts[-1].get("status") != "confirmed" or
                receipts[-1].get("operation_id") != run.get("operation_id") or
                receipts[0].get("draft_hash") != run.get("draft_hash") or
                receipts[1].get("draft_hash") != run.get("draft_hash") or
                receipts[1].get("operation_id") != run.get("operation_id") or
                (journal is not None and receipts[-1].get("journal_ref_sha256") != sha_obj(dict(journal)))):
            errors.append("destination receipt sequence mismatch")
        try:
            observed_at = datetime.fromisoformat(receipt["observed_at"].replace("Z", "+00:00"))
            max_age = receipt["max_age_seconds"]
            for event in actions:
                if event.get("action") in ("preview", "approve", "begin_submission"):
                    age = (datetime.fromisoformat(event["at"]) - observed_at).total_seconds()
                    if not 0 <= age <= max_age:
                        errors.append("source stale at consequential step")
                        break
        except (KeyError, AttributeError, TypeError, ValueError):
            errors.append("source freshness evidence invalid")
        if actions:
            last = actions[-1]
            if (last.get("source_receipt_hash") != sha_obj(run.get("source_receipt")) or
                    last.get("destination_receipts_hash") != sha_obj(receipts)):
                errors.append("receipt hashes differ from final event")
    finally:
        db.close()
    return {"status": "synthetic_verified" if not errors else "synthetic_rejected", "errors": errors}
