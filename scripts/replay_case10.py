#!/usr/bin/env python3
"""Run frozen synthetic case 10 scenarios and emit a non-live replay report."""
import hashlib
import itertools
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.independent import verify_case10
from evaluation.scenario_evidence import snapshot, verify_delta
from pilot.adapters import ObservationRequest, SyntheticObservationAdapter
from pilot.runtime import Runtime

PROTOCOL_PATH = ROOT / "evaluation/case-10-executable.v2.json"
REPORT_PATH = ROOT / "evaluation/replay-report.v2.json"
PROTOCOL = json.loads(PROTOCOL_PATH.read_text())
FIXTURE = json.loads((ROOT / PROTOCOL["source_fixture"]).read_text())
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
IDENTITY = dict(actor_id="synthetic-operator", account_id=FIXTURE["account_id"],
                session_id=FIXTURE["session_id"])
REQUEST = ObservationRequest(account_id=FIXTURE["account_id"],
                             session_id=FIXTURE["session_id"],
                             instrument_id=FIXTURE["instrument_id"])


def build_report():
    cases = []
    run_ids = (f"replay-{n:02d}" for n in itertools.count(1))
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "replay.sqlite"
        runtime = Runtime(path, clock=lambda: NOW, id_factory=lambda: next(run_ids))

        def begin():
            return snapshot(path)

        def add(name, before, run_id, actual, detail=()):
            spec = PROTOCOL["scenarios"][name]
            errors = verify_delta(path, before, run_id, spec)
            expected = spec["outcome"]
            cases.append({"name": name, "expected": expected, "actual": actual,
                          "passed": actual == expected and not errors and not detail,
                          "detail": [*detail, *errors]})

        def observe(fixture=FIXTURE, request=REQUEST):
            source = SyntheticObservationAdapter(fixture, clock=lambda: NOW)
            return runtime.create_from_adapter(
                source, request, actor_id=IDENTITY["actor_id"],
                lease_until=(NOW + timedelta(hours=1)).isoformat(),
                deadline=(NOW + timedelta(minutes=30)).isoformat())

        def approved(fixture=FIXTURE):
            run_id, source = observe(fixture)
            if run_id is None or source.status != "ok":
                raise AssertionError("Expected synthetic observation")
            runtime.preview(run_id, **IDENTITY)
            runtime.approve(run_id, **IDENTITY, accepted=True)
            return run_id

        ledger = begin()
        baseline = approved()
        runtime.submit(baseline, **IDENTITY)
        runtime.readback(baseline, **IDENTITY)
        baseline_check = verify_case10(path, baseline, FIXTURE, PROTOCOL)
        add("baseline_success", ledger, baseline, baseline_check["status"], baseline_check["errors"])

        for name, changed in (
            ("stale_data", {"observed_at": "2026-11-15T08:00:00Z"}),
            ("missing_data", {"current_close": None}),
            ("entitlement_failure", {"entitled": False}),
        ):
            ledger = begin()
            run_id, result = observe({**FIXTURE, **changed})
            add(name, ledger, run_id, result.status)
        wrong_request = ObservationRequest(FIXTURE["account_id"], FIXTURE["session_id"], "WRONG")
        ledger = begin()
        run_id, result = observe(FIXTURE, wrong_request)
        add("wrong_instrument", ledger, run_id, result.status)

        ledger = begin()
        declined, _ = observe()
        runtime.preview(declined, **IDENTITY)
        runtime.approve(declined, **IDENTITY, accepted=False)
        try:
            runtime.submit(declined, **IDENTITY)
            declined_actual = "submitted"
        except ValueError:
            declined_actual = runtime.status(declined)["state"]
        add("declined_approval", ledger, declined, declined_actual)

        ledger = begin()
        before = approved()
        runtime.submit(before, **IDENTITY, mode="timeout_before_commit")
        runtime.readback(before, **IDENTITY)
        try:
            runtime.submit(before, **IDENTITY)
            before_actual = "resubmitted"
        except ValueError:
            before_actual = "unknown_effect" if runtime.status(before)["effect_status"] == "unknown" else "wrong_state"
        add("lost_response_before_commit", ledger, before, before_actual)

        ledger = begin()
        after = approved()
        transient = runtime.submit(after, **IDENTITY, mode="timeout_after_commit")
        try:
            runtime.submit(after, **IDENTITY)
            duplicate_after = False
        except ValueError:
            duplicate_after = True
        runtime.readback(after, **IDENTITY)
        after_check = verify_case10(path, after, FIXTURE, PROTOCOL)
        after_actual = after_check["status"] if transient["effect_status"] == "unknown" and duplicate_after else "unsafe_retry"
        add("lost_response_after_commit", ledger, after, after_actual, after_check["errors"])

        ledger = begin()
        duplicate = approved()
        runtime.submit(duplicate, **IDENTITY)
        runtime.readback(duplicate, **IDENTITY)
        try:
            runtime.submit(duplicate, **IDENTITY)
            duplicate_actual = "duplicate_allowed"
        except ValueError:
            duplicate_actual = "duplicate_rejected"
        duplicate_check = verify_case10(path, duplicate, FIXTURE, PROTOCOL)
        add("duplicate_delivery", ledger, duplicate, duplicate_actual, duplicate_check["errors"])

        ledger = begin()
        mismatch = approved()
        runtime.submit(mismatch, **IDENTITY)
        runtime.db.execute("UPDATE journal SET instrument_id='WRONG' WHERE operation_id=?",
                           (runtime.status(mismatch)["operation_id"],))
        mismatch_status = runtime.readback(mismatch, **IDENTITY)
        add("destination_mismatch", ledger, mismatch,
            "mismatch_paused" if (mismatch_status["state"], mismatch_status["effect_status"]) ==
            ("paused", "mismatch") else "unsafe_state")

        later_fixture = {**FIXTURE, "fixture_id": "synthetic-case-10-later-mark",
                         "observed_at": "2026-11-15T11:30:00Z", "current_close": "48.70"}
        ledger = begin()
        later, _ = observe(later_fixture)
        later_state = runtime.preview(later, **IDENTITY)
        add("later_mark_revision", ledger, later,
            "revised_to_pause" if later_state["state"] == "paused" and
            runtime.status(baseline)["state"] == "recorded" and
            later_state["artifact_hash"] != runtime.status(baseline)["artifact_hash"]
            else "revision_not_isolated")
        runtime.close()

    if [case["name"] for case in cases] != list(PROTOCOL["scenarios"]):
        raise AssertionError("Replay scenarios differ from frozen protocol")
    return {"schema_version": 2, "evidence_level": "synthetic_replay_only",
            "protocol_sha256": hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest(),
            "source_fixture_sha256": hashlib.sha256((ROOT / PROTOCOL["source_fixture"]).read_bytes()).hexdigest(),
            "case_count": len(cases), "passed": sum(case["passed"] for case in cases),
            "human_active_seconds": None, "latency_seconds": None, "full_cost": None,
            "live_acceptance": None, "cases": cases}


def main():
    report = build_report()
    expected = json.dumps(report, indent=2) + "\n"
    if sys.argv[1:] == ["--check"]:
        if not REPORT_PATH.exists() or REPORT_PATH.read_text() != expected:
            raise SystemExit("Replay report differs; regenerate after reviewing the protocol")
        print("Synthetic case 10 replay report matches")
    else:
        REPORT_PATH.write_text(expected)
        print(f"Wrote {REPORT_PATH}")
    if report["passed"] != report["case_count"]:
        raise SystemExit("One or more replay scenarios failed")


if __name__ == "__main__":
    main()
