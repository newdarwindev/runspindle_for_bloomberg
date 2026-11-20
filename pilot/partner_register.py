"""Synthetic pilot preflight and append-only episode register, not live approval."""
import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "evaluation/protocol.v1.md"
GATES = ("2", "4", "5", "6", "7", "8")
OUTCOMES = ("accepted_authorized_completion", "correct_refusal", "unknown_effect",
            "produced_only", "boundary_failure", "setup_failure", "withdrawn")
BASELINES = ("native_terminal", "expert_assisted", "deterministic_integration")
BASELINE_FIELDS = {"outcome", "authority_ref", "budget_ref", "reviewer_id",
                   "source_ref", "destination_ref", "human_active_seconds",
                   "elapsed_seconds", "full_cost"}
METRICS = ("human_active_seconds", "elapsed_seconds", "quality_errors",
           "full_cost", "support_minutes")
LEGACY_SCHEMA = (
    "CREATE TABLE register_meta(plan_hash TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)",
    """CREATE TABLE episodes(
        seq INTEGER PRIMARY KEY AUTOINCREMENT, episode_id TEXT NOT NULL UNIQUE,
        payload TEXT NOT NULL, prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL)""",
    """CREATE TRIGGER episode_no_update BEFORE UPDATE ON episodes
        BEGIN SELECT RAISE(ABORT, 'episodes are append only'); END""",
    """CREATE TRIGGER episode_no_delete BEFORE DELETE ON episodes
        BEGIN SELECT RAISE(ABORT, 'episodes are append only'); END""",
)
INTAKE_SCHEMA = (
    """CREATE TABLE intake(
        seq INTEGER PRIMARY KEY, episode_id TEXT NOT NULL UNIQUE, eligible_at TEXT NOT NULL,
        row_hash TEXT NOT NULL)""",
    """CREATE TRIGGER intake_no_update BEFORE UPDATE ON intake
        BEGIN SELECT RAISE(ABORT, 'intake is append only'); END""",
    """CREATE TRIGGER intake_no_delete BEFORE DELETE ON intake
        BEGIN SELECT RAISE(ABORT, 'intake is append only'); END""",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("Timestamp must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return parsed


def preflight(plan):
    blockers = []
    if plan.get("schema_version") != 1:
        blockers.append("schema_version")
    mode = plan.get("mode")
    if mode not in ("synthetic_rehearsal", "live"):
        blockers.append("mode")
    if mode == "live":
        blockers.append("live_runtime_and_independent_permissions_not_available")
    if plan.get("status") != "approved_for_rehearsal":
        blockers.append("status")
    for field in ("partner_code", "consent_ref", "operator_id", "reviewer_id", "account_id",
                  "session_id", "task_boundary_ref", "budget_ref", "holdout_policy_ref",
                  "rights_decision_ref", "withdrawal_procedure_ref", "support_owner",
                  "incident_route_ref", "acceptance_criteria_ref"):
        if not plan.get(field):
            blockers.append(field)
    if plan.get("operator_id") and plan.get("operator_id") == plan.get("reviewer_id"):
        blockers.append("separate_reviewer")
    if mode == "synthetic_rehearsal" and not str(plan.get("account_id", "")).startswith("synthetic:"):
        blockers.append("synthetic_account_only")
    if plan.get("allowed_effects") != ["paper_record"]:
        blockers.append("allowed_effects")
    expected_protocol = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    if plan.get("evaluation_protocol_sha256") != expected_protocol:
        blockers.append("evaluation_protocol_sha256")
    gates = plan.get("gate_refs") or {}
    blockers.extend(f"gate_refs.{gate}" for gate in GATES if not gates.get(gate))
    try:
        if timestamp(plan.get("pilot_start_at")) >= timestamp(plan.get("pilot_end_at")):
            blockers.append("pilot_period")
    except ValueError:
        blockers.append("pilot_period")
    count = plan.get("max_eligible_episodes")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        blockers.append("max_eligible_episodes")
    return {"evidence_level": "structural_check_only", "pilot_ready": False,
            "synthetic_rehearsal_ready": mode == "synthetic_rehearsal" and not blockers,
            "blockers": blockers}


def _validate_outcome_evidence(result):
    if result["outcome"] == "accepted_authorized_completion" and (
            not result["source_ref"] or not result["destination_ref"] or not result["reviewer_id"]):
        raise ValueError("Accepted completion requires evidence and independent review")
    if result["outcome"] == "correct_refusal" and not result["reviewer_id"]:
        raise ValueError("Correct refusal requires reviewer")


def _validate_baseline(name, baseline):
    if not isinstance(baseline, dict) or set(baseline) != BASELINE_FIELDS:
        raise ValueError(f"{name} baseline fields differ from schema")
    if baseline["outcome"] not in OUTCOMES or not baseline["authority_ref"] or not baseline["budget_ref"]:
        raise ValueError(f"{name} baseline needs outcome, authority, and budget")
    _validate_outcome_evidence(baseline)
    for field in ("human_active_seconds", "elapsed_seconds", "full_cost"):
        value = baseline[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                  not math.isfinite(value) or value < 0):
            raise ValueError(f"{name}.{field} must be nonnegative or null")


def validate_episode(record):
    required = {"episode_id", "eligible_at", "outcome", "source_ref", "destination_ref",
                "reviewer_id", "boundary_violation", "baselines", *METRICS}
    if set(record) != required:
        raise ValueError("Episode fields differ from register schema")
    if not isinstance(record["episode_id"], str) or not record["episode_id"]:
        raise ValueError("episode_id required")
    timestamp(record["eligible_at"])
    if record["outcome"] not in OUTCOMES:
        raise ValueError("Unknown outcome")
    if not isinstance(record["boundary_violation"], bool):
        raise ValueError("boundary_violation must be boolean")
    if not isinstance(record["baselines"], dict) or set(record["baselines"]) != set(BASELINES):
        raise ValueError("All baseline slots must be present, even if unknown")
    for name, baseline in record["baselines"].items():
        if baseline is not None:
            _validate_baseline(name, baseline)
    for field in METRICS:
        value = record[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                  not math.isfinite(value) or value < 0):
            raise ValueError(f"{field} must be nonnegative or null")
    _validate_outcome_evidence(record)
    if record["boundary_violation"] and record["outcome"] != "boundary_failure":
        raise ValueError("Boundary violation must be a boundary failure")


class PilotRegister:
    def __init__(self, path, plan):
        gate = preflight(plan)
        if not gate["synthetic_rehearsal_ready"]:
            raise PermissionError("Synthetic rehearsal preflight blocked: " + ", ".join(gate["blockers"]))
        self.path = Path(path)
        self.plan_hash = sha(canonical(plan))
        self.max_episodes = plan["max_eligible_episodes"]
        self.start = timestamp(plan["pilot_start_at"])
        self.end = timestamp(plan["pilot_end_at"])
        self.operator_id = plan["operator_id"]
        self.reviewer_id = plan["reviewer_id"]
        self.authority_ref = plan["rights_decision_ref"]
        self.budget_ref = plan["budget_ref"]
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.version = self._open()
            if self.version == 1:
                self.db.execute("PRAGMA query_only=ON")
        except BaseException:
            self.close()
            raise

    @contextmanager
    def _write(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _open(self):
        with self._write():
            actual = {" ".join(row[0].split()) for row in self.db.execute(
                "SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL AND name NOT GLOB 'sqlite_*'"
            )}
            schemas = {version: {" ".join(sql.split()) for sql in statements}
                       for version, statements in ((1, LEGACY_SCHEMA), (2, LEGACY_SCHEMA + INTAKE_SCHEMA))}
            if not actual:
                for sql in LEGACY_SCHEMA + INTAKE_SCHEMA:
                    self.db.execute(sql)
                self.db.execute("INSERT INTO register_meta VALUES (?,2)", (self.plan_hash,))
                return 2
            for version, expected in schemas.items():
                if actual == expected:
                    meta = list(map(tuple, self.db.execute("SELECT plan_hash,schema_version FROM register_meta")))
                    if meta == [(self.plan_hash, version)]:
                        return version
            raise ValueError("Register is bound to a different plan or schema")

    def close(self):
        self.db.close()

    def _require_intake(self):
        if self.version != 2:
            raise ValueError("Historical register has no intake history and is read only")

    def _intake_hash(self, sequence, episode_id, eligible_at):
        return sha(canonical([self.plan_hash, sequence, episode_id, eligible_at]))

    def record_eligible(self, episode_id, eligible_at):
        self._require_intake()
        if type(episode_id) is not str or not episode_id:
            raise ValueError("episode_id required")
        observed = timestamp(eligible_at)
        if not self.start <= observed < self.end:
            raise ValueError("Episode outside predeclared period")
        with self._write():
            last = self.db.execute("SELECT seq,eligible_at FROM intake ORDER BY seq DESC LIMIT 1").fetchone()
            if last and observed < timestamp(last["eligible_at"]):
                raise ValueError("Eligible episode timestamps must be nondecreasing")
            sequence = 1 if last is None else last["seq"] + 1
            if sequence > self.max_episodes:
                raise ValueError("Predeclared episode limit reached")
            self.db.execute("INSERT INTO intake VALUES (?,?,?,?)",
                            (sequence, episode_id, eligible_at, self._intake_hash(sequence, episode_id, eligible_at)))
            return sequence

    def _validate_review_scope(self, result, label):
        if result["reviewer_id"] == self.operator_id:
            raise ValueError(f"Operator cannot review own {label.lower()}")
        if result["reviewer_id"] not in (None, self.reviewer_id):
            raise ValueError(f"{label} reviewer differs from plan")
        for field in ("source_ref", "destination_ref"):
            ref = result[field]
            if ref is not None and (not isinstance(ref, str) or not ref.startswith("synthetic:")
                                    or not ref.removeprefix("synthetic:").strip()):
                raise ValueError("Synthetic register accepts only synthetic evidence references")

    def _validate_baseline_scope(self, baseline):
        if baseline["authority_ref"] != self.authority_ref or baseline["budget_ref"] != self.budget_ref:
            raise ValueError("Baseline authority or budget differs from plan")
        self._validate_review_scope(baseline, "Baseline")

    def _has_matched_baselines(self, record):
        try:
            for name in BASELINES:
                baseline = record["baselines"].get(name)
                _validate_baseline(name, baseline)
                self._validate_baseline_scope(baseline)
        except ValueError:
            return False
        return True

    def append(self, record):
        self._require_intake()
        validate_episode(record)
        self._validate_review_scope(record, "Episode")
        for baseline in record["baselines"].values():
            if baseline is not None:
                self._validate_baseline_scope(baseline)
        with self._write():
            intake = self.db.execute("SELECT * FROM intake WHERE episode_id=?", (record["episode_id"],)).fetchone()
            if intake is None:
                raise ValueError("Episode has no retained intake")
            if (intake["eligible_at"] != record["eligible_at"] or intake["row_hash"] != self._intake_hash(
                    intake["seq"], intake["episode_id"], intake["eligible_at"])):
                raise ValueError("Episode differs from retained intake")
            last = self.db.execute("SELECT seq,row_hash FROM episodes ORDER BY seq DESC LIMIT 1").fetchone()
            sequence = 1 if last is None else last["seq"] + 1
            previous = "0" * 64 if last is None else last["row_hash"]
            payload = canonical(record)
            self.db.execute("INSERT INTO episodes(seq,episode_id,payload,prev_hash,row_hash) VALUES (?,?,?,?,?)",
                            (sequence, record["episode_id"], payload, previous, sha(previous + payload)))
            return sequence

    def rows(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM episodes ORDER BY seq")]

    def intake_rows(self):
        if self.version == 1:
            return None
        return [dict(row) for row in self.db.execute("SELECT * FROM intake ORDER BY seq")]

    def _snapshot(self):
        self.db.execute("BEGIN")
        try:
            return self.rows(), self.intake_rows()
        finally:
            self.db.rollback()

    def _verify_chain(self, rows, intake):
        registered = None
        if intake is not None:
            registered = {}
            for position, row in enumerate(intake, 1):
                if (row["seq"] != position or row["row_hash"] != self._intake_hash(
                        position, row["episode_id"], row["eligible_at"])):
                    return False
                registered[row["episode_id"]] = row["eligible_at"]
        previous = "0" * 64
        for position, row in enumerate(rows, 1):
            if (row["seq"] != position or row["prev_hash"] != previous
                    or row["row_hash"] != sha(previous + row["payload"])):
                return False
            record = json.loads(row["payload"])
            if (record["episode_id"] != row["episode_id"] or
                    (registered is not None and registered.get(row["episode_id"]) != record["eligible_at"])):
                return False
            previous = row["row_hash"]
        return True

    def verify_chain(self):
        return self._verify_chain(*self._snapshot())

    def summary(self):
        rows, intake = self._snapshot()
        chain_valid = self._verify_chain(rows, intake)
        records = [json.loads(row["payload"]) for row in rows]
        eligible = None if intake is None or not chain_valid else len(intake)
        pending = None if eligible is None else eligible - len(records)
        return {"evidence_level": "synthetic_rehearsal_only", "episodes": len(records),
                "eligible_episodes": eligible, "pending_outcomes": pending,
                "outcomes": {name: sum(record["outcome"] == name for record in records) for name in OUTCOMES},
                "all_baseline_slots_filled": chain_valid and pending in (None, 0) and bool(records) and all(
                    self._has_matched_baselines(record) for record in records),
                "live_acceptance": None, "go_iterate_stop_decision": None,
                "chain_valid": chain_valid}
