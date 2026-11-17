"""SQLite-backed synthetic paper-run coordinator. No live adapters or trading."""
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pilot.adapters import (DESTINATION_ROUTE, SOURCE_ROUTE, ObservationRequest,
                            SyntheticObservationAdapter, SyntheticPaperDestination)

SCHEMA_VERSION = 1
RUNTIME_VERSION = "0.3.0"
MODEL_VERSION = "none"
DESTINATION = DESTINATION_ROUTE
OBSERVATION_FIELDS = {"instrument_id", "prior_date", "current_date", "source_timestamp",
                      "prior_close", "current_close", "cash_dividend", "entitled", "fresh",
                      "no_other_corporate_action"}
SOURCE_RECEIPT_FIELDS = {"adapter_version", "status", "route", "requested_instrument",
                         "fixture_id", "fixture_sha256", "observed_at", "max_age_seconds",
                         "entitlement"}
SYNTHETIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("Expected an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed


def paper_decision(observation):
    if not all(observation.get(key) for key in
               ("instrument_id", "prior_date", "current_date", "source_timestamp")):
        raise ValueError("Exact instrument, dates, and source timestamp required")
    try:
        prior_date = date.fromisoformat(observation["prior_date"])
        current_date = date.fromisoformat(observation["current_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Closing dates must be ISO dates") from exc
    parse_time(observation["source_timestamp"])
    if current_date <= prior_date:
        raise ValueError("Closing dates are not ordered")
    if not all(observation.get(key) is True for key in
               ("entitled", "fresh", "no_other_corporate_action")):
        raise ValueError("Observation rights, freshness, or corporate action unresolved")
    try:
        prior = Decimal(str(observation["prior_close"]))
        current = Decimal(str(observation["current_close"]))
        dividend = Decimal(str(observation["cash_dividend"]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError("Valid close and dividend values required") from exc
    if not all(x.is_finite() for x in (prior, current, dividend)) or prior <= 0 or current < 0 or dividend < 0:
        raise ValueError("Close and dividend values out of range")
    raw = (current - prior) / prior
    adjusted = (current + dividend - prior) / prior
    return {"raw_return": str(raw), "cash_adjusted_return": str(adjusted),
            "decision": "pass" if raw < 0 < adjusted else "pause"}


def validate_observation(observation, instrument_id):
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_FIELDS:
        raise ValueError("Observation must contain only the ten allowed fields")
    if (not isinstance(instrument_id, str) or not SYNTHETIC_ID.fullmatch(instrument_id) or
            observation["instrument_id"] != instrument_id):
        raise ValueError("Observation instrument differs from selected synthetic target")
    paper_decision(observation)


class IntegrityError(RuntimeError):
    """Persisted state cannot be trusted for observation or execution."""


class Runtime:
    def __init__(self, path, clock=utc_now, id_factory=uuid.uuid4):
        self.path = Path(path)
        self.clock = clock
        self.id_factory = id_factory
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self._schema()
        self.destination = SyntheticPaperDestination(self.db, clock=clock)

    def close(self):
        self.db.close()

    def _schema(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                payload TEXT NOT NULL, prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id));
            CREATE TABLE IF NOT EXISTS journal(
                operation_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                instrument_id TEXT NOT NULL, draft_hash TEXT NOT NULL,
                committed_at TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
        """)
        versions = [row[0] for row in self.db.execute("SELECT version FROM schema_meta")]
        if not versions:
            self.db.execute("INSERT INTO schema_meta VALUES (?)", (SCHEMA_VERSION,))
        elif versions != [SCHEMA_VERSION]:
            raise RuntimeError("Unsupported schema version; migrate or restore a compatible backup")

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @contextmanager
    def _consistent_read(self):
        # Reuse an enclosing write transaction; otherwise bind both queries to
        # one SQLite snapshot so a concurrent valid transition is not corruption.
        owned = not self.db.in_transaction
        if owned:
            self.db.execute("BEGIN")
        try:
            yield
        finally:
            if owned:
                self.db.execute("ROLLBACK")

    def _snapshot(self, run_id):
        row = self.db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        try:
            run = json.loads(row["data"])
            if not self._verify_snapshot(run_id, run):
                raise IntegrityError("Run integrity verification failed")
        except (ValueError, TypeError, AttributeError):
            raise IntegrityError("Run integrity verification failed") from None
        return run

    def status(self, run_id):
        with self._consistent_read():
            return self._snapshot(run_id)

    def events(self, run_id):
        return [dict(row) for row in self.db.execute(
            "SELECT seq,payload,prev_hash,event_hash FROM events WHERE run_id=? ORDER BY seq", (run_id,))]

    def verify_chain(self, run_id):
        try:
            with self._consistent_read():
                self._snapshot(run_id)
            return True
        except (IntegrityError, KeyError):
            return False

    def _verify_snapshot(self, run_id, run):
        previous = "0" * 64
        last = None
        for event in self.events(run_id):
            if event["prev_hash"] != previous or digest(previous + event["payload"]) != event["event_hash"]:
                return False
            previous = event["event_hash"]
            last = json.loads(event["payload"])
        # Legacy events without full-snapshot binding cannot authorize new work.
        # Never silently seal a previously unverified snapshot during recovery.
        return (isinstance(run, dict) and run.get("id") == run_id
                and isinstance(last, dict)
                and last.get("snapshot_sha256") == digest(canonical(run)))

    def _write(self, run, action, actor):
        run["revision"] += 1
        self.db.execute("UPDATE runs SET data=? WHERE id=?", (canonical(run), run["id"]))
        previous = self.db.execute(
            "SELECT event_hash FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1", (run["id"],)).fetchone()
        prev_hash = previous[0] if previous else "0" * 64
        payload = canonical({"action": action, "actor_id": actor, "at": self.clock().isoformat(),
                             "snapshot_sha256": digest(canonical(run)),
                             "revision": run["revision"], "state": run["state"],
                             "effect_status": run["effect_status"],
                             "operation_id": run["operation_id"],
                             "artifact_hash": run["artifact_hash"],
                             "draft_hash": run["draft_hash"],
                             "source_receipt_hash": digest(canonical(run["source_receipt"])) if run.get("source_receipt") else None,
                             "destination_receipts_hash": digest(canonical(run.get("destination_receipts", [])))})
        self.db.execute("INSERT INTO events(run_id,payload,prev_hash,event_hash) VALUES (?,?,?,?)",
                        (run["id"], payload, prev_hash, digest(prev_hash + payload)))

    def _identity(self, run, actor_id, account_id, session_id):
        if run["owner_id"] != actor_id:
            raise PermissionError("Wrong operator")
        if run["account_id"] != account_id or run["session_id"] != session_id:
            raise PermissionError("Wrong account or session")

    def _bound(self, run, actor_id, account_id, session_id):
        self._identity(run, actor_id, account_id, session_id)
        if self.clock() >= parse_time(run["lease_until"]):
            raise PermissionError("Session lease expired")
        if self.clock() >= parse_time(run["deadline"]):
            raise PermissionError("Run deadline expired")

    def _source_current(self, run):
        receipt = run.get("source_receipt")
        if receipt:
            age = self.clock() - parse_time(receipt["observed_at"])
            if age.total_seconds() < 0 or age.total_seconds() > receipt["max_age_seconds"]:
                raise PermissionError("Source observation stale")

    def create(self, *, actor_id, account_id, session_id, instrument_id,
               observation, lease_until, deadline, max_submissions=1, source_receipt=None):
        if not all((actor_id, account_id, session_id, instrument_id)):
            raise ValueError("Actor, account, session, and instrument required")
        if not account_id.startswith("synthetic:"):
            raise PermissionError("Only synthetic accounts are permitted")
        validate_observation(observation, instrument_id)
        if source_receipt is not None and (not isinstance(source_receipt, dict) or
                               source_receipt.get("status") != "ok" or
                               source_receipt.get("requested_instrument") != instrument_id or
                               source_receipt.get("route") != SOURCE_ROUTE or
                               source_receipt.get("entitlement") != "confirmed" or
                               set(source_receipt) != SOURCE_RECEIPT_FIELDS):
            raise ValueError("Source receipt does not match accepted observation")
        if parse_time(lease_until) <= self.clock() or parse_time(deadline) <= self.clock():
            raise ValueError("Lease and deadline must be in the future")
        if max_submissions != 1:
            raise ValueError("Synthetic runtime permits one submission per approval")
        run = {"id": str(self.id_factory()), "revision": 0, "state": "setup",
               "owner_id": actor_id, "account_id": account_id, "session_id": session_id,
               "instrument_id": instrument_id, "observation": observation,
               "artifact_hash": digest(canonical(observation)), "draft": None, "draft_hash": None,
               "source_receipt": source_receipt, "destination_receipts": [],
               "approval_actor": None, "operation_id": None, "effect_status": "none",
               "allowed_actions": ["paper_record"], "max_submissions": max_submissions,
               "submissions": 0, "lease_until": lease_until, "deadline": deadline,
               "runtime_version": RUNTIME_VERSION, "model_version": MODEL_VERSION,
               "destination": DESTINATION}
        with self._transaction():
            self.db.execute("INSERT INTO runs(id,data) VALUES (?,?)", (run["id"], canonical(run)))
            self._write(run, "create", actor_id)
        return run["id"]

    def create_from_adapter(self, adapter, request: ObservationRequest, *, actor_id,
                            lease_until, deadline):
        """Observe first; a blocked observation never creates an executable run."""
        if not isinstance(adapter, SyntheticObservationAdapter) or request.route != SOURCE_ROUTE:
            raise PermissionError("No live observation route is approved")
        result = adapter.observe(request)
        if result.status != "ok":
            return None, result
        run_id = self.create(actor_id=actor_id, account_id=request.account_id,
                             session_id=request.session_id, instrument_id=request.instrument_id,
                             observation=result.observation, source_receipt=result.receipt,
                             lease_until=lease_until, deadline=deadline)
        return run_id, result

    def preview(self, run_id, *, actor_id, account_id, session_id):
        with self._transaction():
            run = self.status(run_id); self._bound(run, actor_id, account_id, session_id)
            if run["state"] != "setup": raise ValueError("Preview requires setup")
            self._source_current(run)
            draft = paper_decision(run["observation"])
            run["draft"] = draft; run["draft_hash"] = digest(canonical(draft))
            run["state"] = "preview" if draft["decision"] == "pass" else "paused"
            if run["state"] == "preview":
                run.setdefault("destination_receipts", []).append(
                    self.destination.draft(run["instrument_id"], draft))
            self._write(run, "preview", actor_id)
        return self.status(run_id)

    def revise(self, run_id, observation, *, actor_id, account_id, session_id):
        with self._transaction():
            run = self.status(run_id); self._bound(run, actor_id, account_id, session_id)
            if run["state"] not in ("setup", "preview", "paused") or run["submissions"]:
                raise ValueError("Revision unavailable after submission or takeover")
            if run.get("source_receipt"):
                raise ValueError("Adapter-backed observation requires a new sourced run")
            validate_observation(observation, run["instrument_id"])
            run["observation"] = observation
            run["artifact_hash"] = digest(canonical(observation))
            run["draft"] = None; run["draft_hash"] = None
            run["approval_actor"] = None; run["operation_id"] = None
            run["state"] = "setup"
            self._write(run, "revise_observation", actor_id)
        return self.status(run_id)

    def approve(self, run_id, *, actor_id, account_id, session_id, accepted):
        with self._transaction():
            run = self.status(run_id); self._bound(run, actor_id, account_id, session_id)
            if run["state"] != "preview": raise ValueError("Approval requires preview")
            self._source_current(run)
            run["state"] = "approved" if accepted else "paused"
            run["approval_actor"] = actor_id if accepted else None
            if accepted:
                run["operation_id"] = digest(canonical([run_id, run["revision"] + 1,
                                                        DESTINATION, run["draft_hash"]]))
                run.setdefault("destination_receipts", []).append(
                    self.destination.approve(run["operation_id"], run["draft_hash"], actor_id))
            self._write(run, "approve" if accepted else "decline", actor_id)
        return self.status(run_id)

    def submit(self, run_id, *, actor_id, account_id, session_id, mode="success"):
        if mode not in ("success", "timeout_after_commit", "timeout_before_commit", "interrupted"):
            raise ValueError("Unknown synthetic adapter mode")
        with self._transaction():
            run = self.status(run_id); self._bound(run, actor_id, account_id, session_id)
            if run["state"] != "approved" or run["submissions"] >= run["max_submissions"]:
                raise ValueError("Submission requires unused approval")
            self._source_current(run)
            run["state"] = "submitting"; run["effect_status"] = "pending"
            run["submissions"] += 1
            self._write(run, "begin_submission", actor_id)
        if mode == "interrupted":
            return self.status(run_id)
        # A crash here leaves `submitting`; recovery must read back. The
        # simulated destination insert and fence check share a transaction.
        with self._transaction():
            run = self.status(run_id)
            if run["state"] != "submitting":
                raise ValueError("Submission fenced by takeover, cancellation, or recovery")
            # The first transaction can be followed by a long pause. Its
            # admission is not a grant to execute after lease/source expiry.
            self._bound(run, actor_id, account_id, session_id)
            self._source_current(run)
            if mode != "timeout_before_commit":
                receipt = self.destination.execute(run)
                if mode == "success":
                    run.setdefault("destination_receipts", []).append(receipt)
            run["state"] = "pending_readback" if mode == "success" else "uncertain"
            run["effect_status"] = "unverified" if mode == "success" else "unknown"
            self._write(run, "adapter_response" if mode == "success" else "adapter_timeout", actor_id)
        return self.status(run_id)

    def recover(self, run_id, *, actor_id, account_id, session_id):
        with self._transaction():
            run = self.status(run_id)
            self._identity(run, actor_id, account_id, session_id)
            if run["state"] == "submitting":
                run["state"] = "uncertain"; run["effect_status"] = "unknown"
                self._write(run, "recover_interrupted_submission", actor_id)
        return self.status(run_id)

    def readback(self, run_id, *, actor_id, account_id, session_id):
        with self._transaction():
            run = self.status(run_id); self._identity(run, actor_id, account_id, session_id)
            if run["state"] not in ("uncertain", "pending_readback", "cancelled"):
                raise ValueError("No effect requires readback")
            if run["state"] == "cancelled" and run["submissions"] == 0:
                raise ValueError("Cancelled before submission; no effect to read back")
            receipt = self.destination.readback(run)
            run.setdefault("destination_receipts", []).append(receipt)
            if receipt["status"] == "absent_inconclusive":
                run["state"] = "uncertain" if run["state"] != "cancelled" else "cancelled"
                run["effect_status"] = "unknown"
                action = "readback_absent_inconclusive"
            elif receipt["status"] == "mismatch":
                run["state"] = "paused"; run["effect_status"] = "mismatch"
                action = "readback_mismatch"
            else:
                run["effect_status"] = "confirmed"
                if run["state"] != "cancelled": run["state"] = "recorded"
                action = "readback_confirmed"
            self._write(run, action, actor_id)
        return self.status(run_id)

    def control(self, run_id, action, *, actor_id, account_id, session_id):
        with self._transaction():
            run = self.status(run_id); self._bound(run, actor_id, account_id, session_id)
            if action == "takeover" and run["state"] in ("setup", "preview", "approved", "uncertain", "pending_readback"):
                run["prior_state"] = run["state"]
                run["state"] = "takeover"; run["approval_actor"] = None
            elif action == "handback" and run["state"] == "takeover":
                run["state"] = "uncertain" if run["effect_status"] in ("unknown", "unverified", "pending") else "setup"
                run["draft"] = None; run["draft_hash"] = None; run["approval_actor"] = None
            elif action == "pause" and run["state"] in ("setup", "preview", "approved"):
                run["state"] = "paused"; run["approval_actor"] = None
            elif action == "cancel" and run["state"] not in ("cancelled", "recorded"):
                run["state"] = "cancelled"; run["approval_actor"] = None
            else:
                raise ValueError("Control action unavailable from current state")
            self._write(run, action, actor_id)
        return self.status(run_id)

    def revoke(self, run_id, *, actor_id, account_id, session_id):
        """Fence new work after a lease expires; preserve unknown effects."""
        with self._transaction():
            run = self.status(run_id)
            self._identity(run, actor_id, account_id, session_id)
            if run["state"] != "cancelled":
                run["state"] = "cancelled"
                run["approval_actor"] = None
                self._write(run, "revoke", actor_id)
        return self.status(run_id)

    def quarantine_after_restore(self, run_id, *, actor_id, account_id, session_id):
        """Manual rollback fence: unknown later effects must be reconciled."""
        with self._transaction():
            run = self.status(run_id)
            self._identity(run, actor_id, account_id, session_id)
            if run["state"] not in ("approved", "submitting", "pending_readback", "uncertain"):
                raise ValueError("Only a possibly effected run can be quarantined")
            run["state"] = "uncertain"
            run["effect_status"] = "unknown"
            run["approval_actor"] = None
            self._write(run, "quarantine_after_restore", actor_id)
        return self.status(run_id)
