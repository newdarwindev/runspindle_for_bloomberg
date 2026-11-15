import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evaluation.independent import verify_case10
from pilot.adapters import ObservationRequest, SyntheticObservationAdapter
from pilot.runtime import Runtime
from scripts.replay_case10 import build_report

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "pilot/fixtures/case-10-observation.v1.json").read_text())
PROTOCOL = json.loads((ROOT / "evaluation/case-10-executable.v1.json").read_text())
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


class IndependentVerifierTests(unittest.TestCase):
    def test_replay_protocol_covers_all_negative_cases(self):
        report = build_report()
        self.assertEqual(report["case_count"], 11)
        self.assertEqual(report["passed"], 11)
        self.assertIsNone(report["live_acceptance"])
        self.assertEqual({case["name"] for case in report["cases"]},
                         {"baseline_success", *PROTOCOL["negative_case_names"]})

    def test_independent_verifier_rejects_changed_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.sqlite"
            runtime = Runtime(path, clock=lambda: NOW)
            identity = dict(actor_id="operator", account_id=FIXTURE["account_id"],
                            session_id=FIXTURE["session_id"])
            request = ObservationRequest(FIXTURE["account_id"], FIXTURE["session_id"],
                                         FIXTURE["instrument_id"])
            run_id, _ = runtime.create_from_adapter(
                SyntheticObservationAdapter(FIXTURE, clock=lambda: NOW), request,
                actor_id="operator", lease_until=(NOW + timedelta(hours=1)).isoformat(),
                deadline=(NOW + timedelta(minutes=30)).isoformat())
            runtime.preview(run_id, **identity)
            runtime.approve(run_id, **identity, accepted=True)
            runtime.submit(run_id, **identity)
            runtime.readback(run_id, **identity)
            self.assertEqual(verify_case10(path, run_id, FIXTURE, PROTOCOL)["status"], "synthetic_verified")
            changed = runtime.status(run_id)
            changed["draft"]["cash_adjusted_return"] = "0.9"
            runtime.db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(changed), run_id))
            result = verify_case10(path, run_id, FIXTURE, PROTOCOL)
            self.assertEqual(result["status"], "synthetic_rejected")
            self.assertIn("draft differs from independent arithmetic", result["errors"])
            runtime.close()


if __name__ == "__main__":
    unittest.main()
