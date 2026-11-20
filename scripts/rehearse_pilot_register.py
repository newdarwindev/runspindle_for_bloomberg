#!/usr/bin/env python3
"""Generate deterministic synthetic issue #9 register evidence."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot.partner_register import BASELINES, METRICS, PilotRegister, preflight

OUTPUT = ROOT / "pilot/register-demo.v2.json"
TEMPLATE = ROOT / "pilot/design-partner-plan.template.json"
PROTOCOL = ROOT / "evaluation/protocol.v1.md"


def synthetic_plan():
    plan = json.loads(TEMPLATE.read_text())
    plan.update(mode="synthetic_rehearsal", status="approved_for_rehearsal",
                partner_code="SYNTHETIC-PARTNER", consent_ref="synthetic:not-applicable",
                operator_id="synthetic-operator", reviewer_id="synthetic-reviewer",
                account_id="synthetic:paper-desk", session_id="synthetic-session",
                allowed_effects=["paper_record"], rights_decision_ref="synthetic:fixtures-only",
                task_boundary_ref="synthetic:case-10", budget_ref="synthetic:one-paper-record",
                holdout_policy_ref="synthetic:no-training",
                withdrawal_procedure_ref="synthetic:revoke", support_owner="synthetic-operator",
                incident_route_ref="synthetic:local-runbook",
                acceptance_criteria_ref="synthetic:case-10-protocol",
                evaluation_protocol_sha256=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                pilot_start_at="2026-11-15T12:00:00Z", pilot_end_at="2026-11-15T13:00:00Z",
                max_eligible_episodes=3,
                gate_refs={key: "synthetic:rehearsal-only" for key in ("2", "4", "5", "6", "7", "8")})
    return plan


def episode(number, timestamp, outcome, **changes):
    record = {"episode_id": f"synthetic-episode-{number}", "eligible_at": timestamp,
              "outcome": outcome, "source_ref": None, "destination_ref": None,
              "reviewer_id": None, "boundary_violation": False,
              "baselines": {name: None for name in BASELINES},
              **{metric: None for metric in METRICS}}
    record.update(changes)
    return record


def build_demo():
    plan = synthetic_plan()
    with tempfile.TemporaryDirectory() as temporary:
        register = PilotRegister(Path(temporary) / "episodes.sqlite", plan)
        times = ("2026-11-15T12:00:00Z", "2026-11-15T12:05:00Z", "2026-11-15T12:10:00Z")
        for number, timestamp in enumerate(times, 1):
            register.record_eligible(f"synthetic-episode-{number}", timestamp)
        register.append(episode(1, times[0], "accepted_authorized_completion",
                                source_ref="synthetic:source-1", destination_ref="synthetic:readback-1",
                                reviewer_id="synthetic-reviewer"))
        register.append(episode(2, times[1], "correct_refusal",
                                source_ref="synthetic:source-2", reviewer_id="synthetic-reviewer"))
        register.append(episode(3, times[2], "setup_failure"))
        summary = register.summary()
        intake = register.intake_rows()
        rows = [{"sequence": row["seq"], "row_hash": row["row_hash"],
                 **json.loads(row["payload"])} for row in register.rows()]
        register.close()
    return {"schema_version": 2, "evidence_level": "synthetic_rehearsal_only",
            "preflight": preflight(plan), "summary": summary, "intake": intake, "episodes": rows}


def main():
    expected = json.dumps(build_demo(), indent=2) + "\n"
    if sys.argv[1:] == ["--check"]:
        if not OUTPUT.exists() or OUTPUT.read_text() != expected:
            raise SystemExit("Synthetic register demo differs; regenerate deliberately")
        print("Synthetic pilot register demo matches")
    else:
        OUTPUT.write_text(expected)
        print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
