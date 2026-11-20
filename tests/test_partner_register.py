import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pilot.partner_register import (
    BASELINES, LEGACY_SCHEMA, PilotRegister, canonical, preflight, sha, validate_episode,
)
from scripts.rehearse_pilot_register import build_demo, episode, synthetic_plan

ROOT = Path(__file__).resolve().parents[1]


class PartnerRegisterTests(unittest.TestCase):
    def test_outcomes_require_retained_intake_and_pending_survives_reopen(self):
        plan = synthetic_plan()
        first = episode(1, "2026-11-15T12:00:00Z", "setup_failure")
        second = episode(2, "2026-11-15T12:05:00Z", "withdrawn")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "episodes.sqlite"
            with closing(PilotRegister(path, plan)) as register:
                with self.assertRaisesRegex(ValueError, "no retained intake"):
                    register.append(first)
                for sequence, record in enumerate((first, second), 1):
                    self.assertEqual(
                        register.record_eligible(record["episode_id"], record["eligible_at"]),
                        sequence,
                    )
                with self.assertRaises(sqlite3.DatabaseError):
                    register.db.execute("DELETE FROM intake")
                third = episode(3, "2026-11-15T12:10:00Z", "setup_failure")
                register.record_eligible(third["episode_id"], third["eligible_at"])
                with self.assertRaisesRegex(ValueError, "Predeclared episode limit"):
                    register.record_eligible("synthetic-episode-4", "2026-11-15T12:11:00Z")
            fresh = subprocess.check_output(
                [sys.executable, "-B", "-c",
                 "import json, sys; from contextlib import closing; "
                 "from pilot.partner_register import PilotRegister; "
                 "from scripts.rehearse_pilot_register import synthetic_plan;\n"
                 "with closing(PilotRegister(sys.argv[1], synthetic_plan())) as register:\n"
                 "    print(json.dumps(register.summary()))",
                 str(path)],
                text=True, timeout=10, cwd=ROOT,
            )
            self.assertEqual(json.loads(fresh)["pending_outcomes"], 3)
            with closing(PilotRegister(path, plan)) as reopened:
                self.assertEqual(reopened.summary()["eligible_episodes"], 3)
                self.assertEqual(reopened.summary()["pending_outcomes"], 3)
                with self.assertRaisesRegex(ValueError, "differs from retained intake"):
                    reopened.append({**second, "eligible_at": first["eligible_at"]})
                reopened.append(second)
                self.assertEqual(reopened.summary()["pending_outcomes"], 2)
                reopened.append(first)
                self.assertEqual(reopened.summary()["pending_outcomes"], 1)
                reopened.append(third)
                self.assertEqual(reopened.summary()["pending_outcomes"], 0)
                self.assertTrue(reopened.verify_chain())

    def test_version_one_history_remains_readable_without_inventing_intake(self):
        plan = synthetic_plan()
        first = episode(1, "2026-11-15T12:00:00Z", "setup_failure")
        payload = canonical(first)
        previous = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.sqlite"
            with closing(sqlite3.connect(path)) as db, db:
                for sql in LEGACY_SCHEMA:
                    db.execute(sql)
                db.execute("INSERT INTO register_meta VALUES (?,1)", (sha(canonical(plan)),))
                db.execute("INSERT INTO episodes VALUES (1,?,?,?,?)",
                           (first["episode_id"], payload, previous, sha(previous + payload)))
            with closing(PilotRegister(path, plan)) as register:
                self.assertEqual(register.summary()["episodes"], 1)
                self.assertIsNone(register.summary()["eligible_episodes"])
                self.assertIsNone(register.summary()["pending_outcomes"])
                self.assertTrue(register.verify_chain())
                with self.assertRaisesRegex(ValueError, "read only"):
                    register.record_eligible(first["episode_id"], first["eligible_at"])
                with self.assertRaisesRegex(ValueError, "read only"):
                    register.append(first)

    def test_missing_intake_schema_cannot_reinitialize_an_existing_register(self):
        plan = synthetic_plan()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "episodes.sqlite"
            with closing(PilotRegister(path, plan)) as register:
                register.record_eligible("synthetic-episode-1", "2026-11-15T12:00:00Z")
                register.db.execute("DROP TABLE intake")
            with self.assertRaisesRegex(ValueError, "different plan or schema"):
                PilotRegister(path, plan)

    def test_template_and_live_mode_are_blocked(self):
        template = json.loads((ROOT / "pilot/design-partner-plan.template.json").read_text())
        result = preflight(template)
        self.assertFalse(result["pilot_ready"])
        self.assertFalse(result["synthetic_rehearsal_ready"])
        self.assertIn("gate_refs.2", result["blockers"])
        live = synthetic_plan()
        live["mode"] = "live"
        self.assertIn("live_runtime_and_independent_permissions_not_available", preflight(live)["blockers"])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(PermissionError):
                PilotRegister(Path(temporary) / "live.sqlite", live)

    def test_rehearsal_register_is_append_only_and_plan_bound(self):
        plan = synthetic_plan()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "episodes.sqlite"
            register = PilotRegister(path, plan)
            first = episode(1, "2026-11-15T12:00:00Z", "setup_failure")
            register.record_eligible(first["episode_id"], first["eligible_at"])
            self.assertEqual(register.append(first), 1)
            with self.assertRaises(sqlite3.DatabaseError):
                register.db.execute("DELETE FROM episodes")
            with self.assertRaises(sqlite3.IntegrityError):
                register.append(first)
            with self.assertRaises(ValueError):
                register.record_eligible("synthetic-episode-2", "2026-11-15T11:59:00Z")
            with self.assertRaises(ValueError):
                register.record_eligible("synthetic-episode-2", "2026-11-15T13:00:00Z")
            register.record_eligible("synthetic-episode-2", "2026-11-15T12:01:00Z")
            with self.assertRaises(ValueError):
                register.append(episode(2, "2026-11-15T12:01:00Z", "correct_refusal",
                                        reviewer_id="synthetic-operator"))
            baseline = {"outcome": "setup_failure", "authority_ref": "wrong-authority",
                        "budget_ref": plan["budget_ref"], "reviewer_id": None,
                        "source_ref": None, "destination_ref": None,
                        "human_active_seconds": None, "elapsed_seconds": None, "full_cost": None}
            slots = {name: None for name in BASELINES}
            slots["native_terminal"] = baseline
            with self.assertRaisesRegex(ValueError, "authority or budget"):
                register.append(episode(2, "2026-11-15T12:01:00Z", "setup_failure",
                                        baselines=slots))
            self.assertTrue(register.verify_chain())
            register.close()
            changed_plan = {**plan, "max_eligible_episodes": 4}
            with self.assertRaises(ValueError):
                PilotRegister(path, changed_plan)

    def test_acceptance_requires_evidence_and_unknowns_remain_null(self):
        accepted = episode(1, "2026-11-15T12:00:00Z", "accepted_authorized_completion")
        with self.assertRaises(ValueError):
            validate_episode(accepted)
        accepted.update(source_ref="synthetic:source", destination_ref="synthetic:readback",
                        reviewer_id="synthetic-reviewer")
        validate_episode(accepted)
        demo = build_demo()
        self.assertEqual(demo["summary"]["episodes"], 3)
        self.assertEqual(demo["summary"]["eligible_episodes"], 3)
        self.assertEqual(demo["summary"]["pending_outcomes"], 0)
        self.assertFalse(demo["summary"]["all_baseline_slots_filled"])
        self.assertIsNone(demo["summary"]["live_acceptance"])
        self.assertTrue(demo["summary"]["chain_valid"])
        self.assertTrue(all(row["full_cost"] is None for row in demo["episodes"]))

    def test_matched_baselines_require_the_planned_reviewer_and_synthetic_evidence(self):
        plan = synthetic_plan()
        baseline = {"outcome": "accepted_authorized_completion",
                    "authority_ref": plan["rights_decision_ref"], "budget_ref": plan["budget_ref"],
                    "reviewer_id": plan["reviewer_id"], "source_ref": "synthetic:source",
                    "destination_ref": "synthetic:readback", "human_active_seconds": None,
                    "elapsed_seconds": None, "full_cost": None}
        record = episode(1, "2026-11-15T12:00:00Z", "setup_failure",
                         baselines={name: baseline.copy() for name in BASELINES})
        invalid = (
            ({"source_ref": None}, "evidence and independent review"),
            ({"destination_ref": None}, "evidence and independent review"),
            ({"reviewer_id": None}, "evidence and independent review"),
            ({"outcome": "correct_refusal", "reviewer_id": None}, "requires reviewer"),
            ({"reviewer_id": plan["operator_id"]}, "Operator cannot review own baseline"),
            ({"reviewer_id": "another-reviewer"}, "reviewer differs from plan"),
            ({"source_ref": "external:source"}, "only synthetic evidence"),
            ({"destination_ref": "synthetic:"}, "only synthetic evidence"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "episodes.sqlite"
            with closing(PilotRegister(path, plan)) as register:
                register.record_eligible(record["episode_id"], record["eligible_at"])
                for changes, message in invalid:
                    with self.subTest(changes=changes):
                        slots = {**record["baselines"], "native_terminal": {**baseline, **changes}}
                        with self.assertRaisesRegex(ValueError, message):
                            register.append({**record, "baselines": slots})
                        self.assertEqual(register.summary()["pending_outcomes"], 1)
                self.assertEqual(register.append(record), 1)
                self.assertTrue(register.summary()["all_baseline_slots_filled"])

    def test_historical_baselines_without_review_remain_readable_but_incomplete(self):
        plan = synthetic_plan()
        baseline = {"outcome": "accepted_authorized_completion",
                    "authority_ref": plan["rights_decision_ref"], "budget_ref": plan["budget_ref"],
                    "reviewer_id": None, "source_ref": None, "destination_ref": None,
                    "human_active_seconds": None, "elapsed_seconds": None, "full_cost": None}
        record = episode(1, "2026-11-15T12:00:00Z", "setup_failure",
                         baselines={name: baseline.copy() for name in BASELINES})
        payload = canonical(record)
        previous = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "episodes.sqlite"
            with closing(PilotRegister(path, plan)) as register:
                register.record_eligible(record["episode_id"], record["eligible_at"])
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("INSERT INTO episodes VALUES (1,?,?,?,?)",
                           (record["episode_id"], payload, previous, sha(previous + payload)))
            with closing(PilotRegister(path, plan)) as register:
                self.assertTrue(register.verify_chain())
                self.assertEqual(register.summary()["pending_outcomes"], 0)
                self.assertFalse(register.summary()["all_baseline_slots_filled"])


if __name__ == "__main__":
    unittest.main()
