import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pilot.adapters import ObservationRequest, SyntheticObservationAdapter
from pilot.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "pilot/fixtures/case-10-observation.v1.json").read_text())
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.request = ObservationRequest(account_id="synthetic:paper-desk",
                                          session_id="synthetic-session",
                                          instrument_id="SYNTH-CASE-10")

    def adapter(self, fixture=FIXTURE, now=NOW):
        return SyntheticObservationAdapter(fixture, clock=lambda: now)

    def test_entitlement_identity_freshness_and_missing_states(self):
        result = self.adapter().observe(self.request)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.observation["cash_dividend"], "1.20")
        self.assertNotIn("account_id", result.observation)
        denied = self.adapter({**FIXTURE, "entitled": False}).observe(self.request)
        self.assertEqual((denied.status, denied.observation), ("not_entitled", None))
        stale = self.adapter(now=NOW + timedelta(hours=3)).observe(self.request)
        self.assertEqual(stale.status, "stale")
        missing = self.adapter({**FIXTURE, "current_close": None}).observe(self.request)
        self.assertEqual(missing.status, "missing")
        invalid = self.adapter({**FIXTURE, "observed_at": "not-a-time"}).observe(self.request)
        self.assertEqual(invalid.status, "invalid_timestamp")
        wrong = self.adapter().observe(ObservationRequest("synthetic:wrong", "synthetic-session", "SYNTH-CASE-10"))
        self.assertEqual(wrong.status, "identity_mismatch")
        self.assertIsNone(wrong.receipt["fixture_sha256"])
        self.assertEqual(wrong.receipt["entitlement"], "unknown")
        target = self.adapter().observe(ObservationRequest("synthetic:paper-desk", "synthetic-session", "WRONG"))
        self.assertEqual(target.status, "target_mismatch")
        blocked = self.adapter().observe(ObservationRequest("synthetic:paper-desk", "synthetic-session",
                                                            "SYNTH-CASE-10", "live:unapproved"))
        self.assertEqual(blocked.status, "route_blocked")
        with_secret = self.adapter({**FIXTURE, "api_token": "never-export"}).observe(self.request)
        self.assertNotIn("never-export", json.dumps(with_secret.receipt) + json.dumps(with_secret.observation))

    def test_adapter_to_runtime_timeout_and_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Runtime(Path(temporary) / "run.sqlite", clock=lambda: NOW)
            adapter = self.adapter()
            run_id, result = runtime.create_from_adapter(
                adapter, self.request, actor_id="operator",
                lease_until=(NOW + timedelta(hours=1)).isoformat(),
                deadline=(NOW + timedelta(minutes=30)).isoformat())
            self.assertEqual(result.status, "ok")
            identity = dict(actor_id="operator", account_id=self.request.account_id,
                            session_id=self.request.session_id)
            self.assertEqual(runtime.status(run_id)["source_receipt"]["status"], "ok")
            with self.assertRaises(ValueError):
                runtime.revise(run_id, result.observation, **identity)
            runtime.preview(run_id, **identity)
            self.assertEqual(runtime.status(run_id)["destination_receipts"][-1]["stage"], "draft")
            runtime.approve(run_id, **identity, accepted=True)
            runtime.submit(run_id, **identity, mode="timeout_after_commit")
            with self.assertRaises(ValueError):
                runtime.submit(run_id, **identity)
            completed = runtime.readback(run_id, **identity)
            self.assertEqual(completed["state"], "recorded")
            self.assertEqual(completed["destination_receipts"][-1]["status"], "confirmed")
            self.assertTrue(runtime.verify_chain(run_id))
            runtime.close()

    def test_observation_expires_before_submit(self):
        with tempfile.TemporaryDirectory() as temporary:
            now = [NOW]
            runtime = Runtime(Path(temporary) / "run.sqlite", clock=lambda: now[0])
            fixture = {**FIXTURE, "observed_at": "2026-11-15T11:55:00Z"}
            adapter = SyntheticObservationAdapter(fixture, clock=lambda: now[0],
                                                  max_age=timedelta(minutes=10))
            run_id, _ = runtime.create_from_adapter(
                adapter, self.request, actor_id="operator",
                lease_until=(NOW + timedelta(hours=1)).isoformat(),
                deadline=(NOW + timedelta(minutes=30)).isoformat())
            identity = dict(actor_id="operator", account_id=self.request.account_id,
                            session_id=self.request.session_id)
            runtime.preview(run_id, **identity)
            runtime.approve(run_id, **identity, accepted=True)
            now[0] += timedelta(minutes=11)
            with self.assertRaisesRegex(PermissionError, "stale"):
                runtime.submit(run_id, **identity)
            self.assertEqual(runtime.status(run_id)["submissions"], 0)
            runtime.close()

    def test_blocked_observation_creates_no_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Runtime(Path(temporary) / "run.sqlite", clock=lambda: NOW)
            run_id, result = runtime.create_from_adapter(
                self.adapter({**FIXTURE, "entitled": False}), self.request,
                actor_id="operator", lease_until=(NOW + timedelta(hours=1)).isoformat(),
                deadline=(NOW + timedelta(minutes=30)).isoformat())
            self.assertIsNone(run_id)
            self.assertEqual(result.status, "not_entitled")
            self.assertEqual(runtime.db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)
            with self.assertRaises(PermissionError):
                runtime.create_from_adapter(
                    object(), self.request, actor_id="operator",
                    lease_until=(NOW + timedelta(hours=1)).isoformat(),
                    deadline=(NOW + timedelta(minutes=30)).isoformat())
            runtime.close()


if __name__ == "__main__":
    unittest.main()
