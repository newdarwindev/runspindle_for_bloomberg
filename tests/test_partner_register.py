import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pilot.partner_register import BASELINES, PilotRegister, preflight, validate_episode
from scripts.rehearse_pilot_register import build_demo, episode, synthetic_plan

ROOT = Path(__file__).resolve().parents[1]


class PartnerRegisterTests(unittest.TestCase):
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
            self.assertEqual(register.append(first), 1)
            with self.assertRaises(sqlite3.DatabaseError):
                register.db.execute("DELETE FROM episodes")
            with self.assertRaises(sqlite3.IntegrityError):
                register.append(first)
            with self.assertRaises(ValueError):
                register.append(episode(2, "2026-11-15T11:59:00Z", "setup_failure"))
            with self.assertRaises(ValueError):
                register.append(episode(2, "2026-11-15T13:00:00Z", "setup_failure"))
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
        self.assertFalse(demo["summary"]["all_baseline_slots_filled"])
        self.assertIsNone(demo["summary"]["live_acceptance"])
        self.assertTrue(demo["summary"]["chain_valid"])
        self.assertTrue(all(row["full_cost"] is None for row in demo["episodes"]))


if __name__ == "__main__":
    unittest.main()
