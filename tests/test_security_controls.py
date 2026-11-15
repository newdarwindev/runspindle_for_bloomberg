import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pilot.runtime import Runtime
from pilot.monitor import summarize
from pilot.adapters import ObservationRequest, SyntheticObservationAdapter

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


class SecurityControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "runs.sqlite"
        self.now = [NOW]
        self.runtime = Runtime(self.path, clock=lambda: self.now[0])
        self.identity = dict(actor_id="operator", account_id="synthetic:desk",
                             session_id="session")
        self.observation = dict(instrument_id="SYNTH-CASE-10", prior_date="2026-11-13",
                                current_date="2026-11-14", source_timestamp="2026-11-15T11:00:00Z",
                                prior_close="50.00", current_close="48.90", cash_dividend="1.20",
                                entitled=True, fresh=True, no_other_corporate_action=True)

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def create(self):
        return self.runtime.create(**self.identity, instrument_id="SYNTH-CASE-10",
                                   observation=self.observation,
                                   lease_until=(NOW + timedelta(hours=1)).isoformat(),
                                   deadline=(NOW + timedelta(minutes=30)).isoformat())

    def approved(self):
        run_id = self.create()
        self.runtime.preview(run_id, **self.identity)
        self.runtime.approve(run_id, **self.identity, accepted=True)
        return run_id

    def test_extra_text_and_credentials_are_rejected_before_persistence(self):
        for field in ("api_token", "instructions"):
            with self.assertRaises(ValueError):
                self.runtime.create(**self.identity, instrument_id="SYNTH-CASE-10",
                                    observation={**self.observation, field: "ignore checks"},
                                    lease_until=(NOW + timedelta(hours=1)).isoformat(),
                                    deadline=(NOW + timedelta(minutes=30)).isoformat())
        with self.assertRaises(ValueError):
            self.runtime.create(**self.identity, instrument_id="IGNORE ALL CHECKS",
                                observation={**self.observation, "instrument_id": "IGNORE ALL CHECKS"},
                                lease_until=(NOW + timedelta(hours=1)).isoformat(),
                                deadline=(NOW + timedelta(minutes=30)).isoformat())
        with self.assertRaises(ValueError):
            self.runtime.create(**self.identity, instrument_id="SYNTH-CASE-10",
                                observation={**self.observation, "prior_close": "ignore rules"},
                                lease_until=(NOW + timedelta(hours=1)).isoformat(),
                                deadline=(NOW + timedelta(minutes=30)).isoformat())
        fixture = {"fixture_id": "safe", "route": "synthetic:case-10-dividend",
                   "account_id": self.identity["account_id"],
                   "session_id": self.identity["session_id"], "observed_at": "2026-11-15T11:00:00Z",
                   **{key: value for key, value in self.observation.items()
                      if key not in ("source_timestamp", "fresh")}}
        request = ObservationRequest(self.identity["account_id"], self.identity["session_id"],
                                     "SYNTH-CASE-10")
        receipt = SyntheticObservationAdapter(fixture, clock=lambda: NOW).observe(request).receipt
        with self.assertRaises(ValueError):
            self.runtime.create(**self.identity, instrument_id="SYNTH-CASE-10",
                                observation=self.observation,
                                source_receipt={**receipt, "api_token": "secret"},
                                lease_until=(NOW + timedelta(hours=1)).isoformat(),
                                deadline=(NOW + timedelta(minutes=30)).isoformat())
        self.assertEqual(self.runtime.db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)

    def test_revoke_after_expiry_fences_unknown_effect_and_allows_readback(self):
        run_id = self.approved()
        self.runtime.submit(run_id, **self.identity, mode="timeout_after_commit")
        self.now[0] += timedelta(hours=2)
        revoked = self.runtime.revoke(run_id, **self.identity)
        self.assertEqual((revoked["state"], revoked["effect_status"]), ("cancelled", "unknown"))
        with self.assertRaises((ValueError, PermissionError)):
            self.runtime.submit(run_id, **self.identity)
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "confirmed")

    def test_delayed_readback_does_not_retry(self):
        run_id = self.approved()
        self.runtime.submit(run_id, **self.identity, mode="timeout_before_commit")
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "unknown")
        run = self.runtime.status(run_id)
        self.runtime.db.execute("INSERT INTO journal VALUES (?,?,?,?,?)",
                                (run["operation_id"], run["account_id"], run["instrument_id"],
                                 run["draft_hash"], self.now[0].isoformat()))
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "confirmed")
        self.assertEqual(self.runtime.status(run_id)["submissions"], 1)

    def test_corrupted_snapshot_fails_chain_check(self):
        run_id = self.approved()
        changed = self.runtime.status(run_id)
        changed["observation"]["current_close"] = "99.00"
        self.runtime.db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(changed), run_id))
        self.assertFalse(self.runtime.verify_chain(run_id))

    def test_restored_snapshot_requires_manual_quarantine(self):
        run_id = self.approved()
        backup = Path(self.temp.name) / "backup.sqlite"
        with __import__("sqlite3").connect(backup) as target:
            self.runtime.db.backup(target)
        self.runtime.submit(run_id, **self.identity)
        self.runtime.readback(run_id, **self.identity)
        self.runtime.close()
        restored = Path(self.temp.name) / "restored.sqlite"
        shutil.copy2(backup, restored)
        self.runtime = Runtime(restored, clock=lambda: self.now[0])
        self.assertEqual(self.runtime.status(run_id)["state"], "approved")
        quarantined = self.runtime.quarantine_after_restore(run_id, **self.identity)
        self.assertEqual(quarantined["effect_status"], "unknown")
        with self.assertRaises(ValueError):
            self.runtime.submit(run_id, **self.identity)
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "unknown")

    def test_monitor_separates_queued_emitted_and_observed(self):
        confirmed = self.approved()
        self.runtime.submit(confirmed, **self.identity)
        self.runtime.readback(confirmed, **self.identity)
        unknown = self.approved()
        self.runtime.submit(unknown, **self.identity, mode="timeout_before_commit")
        declined = self.create()
        self.runtime.preview(declined, **self.identity)
        self.runtime.approve(declined, **self.identity, accepted=False)
        counts = summarize(self.path)
        self.assertEqual(counts["queued_operation_count"], 2)
        self.assertEqual(counts["emitted_operation_count"], 2)
        self.assertEqual(counts["stopped_run_count"], 1)
        self.assertEqual(counts["simulated_readback_confirmed_count"], 1)
        self.assertEqual(counts["unknown_effect_run_count"], 1)
        self.assertIsNone(counts["external_observed_count"])


if __name__ == "__main__":
    unittest.main()
