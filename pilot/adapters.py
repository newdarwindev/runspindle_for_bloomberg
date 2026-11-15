"""Versioned contracts and local synthetic adapters. No Bloomberg access."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

ADAPTER_VERSION = "0.1.0"
SOURCE_ROUTE = "synthetic:case-10-dividend"
DESTINATION_ROUTE = "synthetic-paper-journal"
FIELDS = ("prior_date", "current_date", "prior_close", "current_close",
          "cash_dividend", "no_other_corporate_action")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("Timestamp must be ISO-8601") from exc
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result


@dataclass(frozen=True)
class ObservationRequest:
    account_id: str
    session_id: str
    instrument_id: str
    route: str = SOURCE_ROUTE


@dataclass(frozen=True)
class ObservationResult:
    status: str
    observation: dict | None
    receipt: dict


class ObservationAdapter(Protocol):
    def observe(self, request: ObservationRequest) -> ObservationResult: ...


class DestinationAdapter(Protocol):
    def draft(self, instrument_id: str, draft: dict) -> dict: ...
    def approve(self, operation_id: str, draft_hash: str, actor_id: str) -> dict: ...
    def execute(self, run: dict) -> dict: ...
    def readback(self, run: dict) -> dict: ...


class SyntheticObservationAdapter:
    def __init__(self, fixture: dict, *, clock=lambda: datetime.now(timezone.utc),
                 max_age=timedelta(hours=2)):
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        self.fixture = fixture
        self.clock = clock
        self.max_age = max_age

    def observe(self, request: ObservationRequest) -> ObservationResult:
        fixture = self.fixture
        status = "ok"
        if request.route != SOURCE_ROUTE or fixture.get("route") != SOURCE_ROUTE:
            status = "route_blocked"
        elif (request.account_id, request.session_id) != (fixture.get("account_id"), fixture.get("session_id")):
            status = "identity_mismatch"
        elif request.instrument_id != fixture.get("instrument_id"):
            status = "target_mismatch"
        elif fixture.get("entitled") is not True:
            status = "not_entitled"
        elif any(fixture.get(field) is None for field in FIELDS) or not fixture.get("observed_at"):
            status = "missing"
        else:
            try:
                observed_at = _time(fixture["observed_at"])
            except ValueError:
                status = "invalid_timestamp"
            else:
                age = self.clock() - observed_at
                if age < timedelta(0) or age > self.max_age:
                    status = "stale"
        identity_ok = status not in ("route_blocked", "identity_mismatch", "target_mismatch")
        receipt = {"adapter_version": ADAPTER_VERSION, "status": status,
                   "route": SOURCE_ROUTE, "requested_instrument": request.instrument_id,
                   "fixture_id": fixture.get("fixture_id") if identity_ok else None,
                   "fixture_sha256": _hash({key: fixture.get(key) for key in
                                            ("fixture_id", "instrument_id", "observed_at", "entitled", *FIELDS)}) if identity_ok else None,
                   "observed_at": fixture.get("observed_at") if identity_ok else None,
                   "max_age_seconds": int(self.max_age.total_seconds()) if identity_ok else None,
                   "entitlement": ("confirmed" if fixture.get("entitled") is True else "denied")
                                  if identity_ok else "unknown"}
        if status != "ok":
            return ObservationResult(status, None, receipt)
        observation = {"instrument_id": request.instrument_id,
                       "source_timestamp": fixture["observed_at"],
                       "entitled": True, "fresh": True,
                       **{field: fixture[field] for field in FIELDS}}
        return ObservationResult(status, observation, receipt)


class SyntheticPaperDestination:
    """Simulated destination using the runtime's local journal table."""
    def __init__(self, db: sqlite3.Connection, *, clock=lambda: datetime.now(timezone.utc)):
        self.db = db
        self.clock = clock

    def draft(self, instrument_id: str, draft: dict) -> dict:
        if not instrument_id or draft.get("decision") != "pass":
            raise ValueError("Only a bounded paper Pass can be drafted")
        return {"adapter_version": ADAPTER_VERSION, "stage": "draft",
                "route": DESTINATION_ROUTE, "instrument_id": instrument_id,
                "draft_hash": _hash(draft)}

    def approve(self, operation_id: str, draft_hash: str, actor_id: str) -> dict:
        if not all((operation_id, draft_hash, actor_id)):
            raise ValueError("Operation, exact draft, and approver required")
        return {"adapter_version": ADAPTER_VERSION, "stage": "approval",
                "route": DESTINATION_ROUTE, "operation_id": operation_id,
                "draft_hash": draft_hash, "actor_id": actor_id}

    def execute(self, run: dict) -> dict:
        if (run.get("destination") != DESTINATION_ROUTE or
                not run.get("account_id", "").startswith("synthetic:") or
                run.get("state") != "submitting" or not run.get("approval_actor") or
                not run.get("operation_id") or not run.get("draft_hash")):
            raise PermissionError("Synthetic destination contract not satisfied")
        committed_at = self.clock().isoformat()
        self.db.execute("INSERT INTO journal VALUES (?,?,?,?,?)",
                        (run["operation_id"], run["account_id"], run["instrument_id"],
                         run["draft_hash"], committed_at))
        return {"adapter_version": ADAPTER_VERSION, "stage": "execute",
                "route": DESTINATION_ROUTE, "operation_id": run["operation_id"],
                "committed_at": committed_at, "status": "submitted"}

    def readback(self, run: dict) -> dict:
        row = self.db.execute("SELECT * FROM journal WHERE operation_id=?",
                              (run["operation_id"],)).fetchone()
        if row is None:
            status = "absent_inconclusive"
        elif (row["account_id"], row["instrument_id"], row["draft_hash"]) != (
                run["account_id"], run["instrument_id"], run["draft_hash"]):
            status = "mismatch"
        else:
            status = "confirmed"
        return {"adapter_version": ADAPTER_VERSION, "stage": "readback",
                "route": DESTINATION_ROUTE, "operation_id": run["operation_id"],
                "status": status,
                "journal_ref_sha256": _hash(dict(row)) if row is not None else None}
