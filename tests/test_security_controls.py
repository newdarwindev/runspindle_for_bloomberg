import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pilot.runtime import IntegrityError, Runtime, SCHEMA_OBJECTS, verify_schema
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
        self.assertEqual(counts["recorded_readback_confirmation_count"], 1)
        self.assertEqual(counts["simulated_readback_conflict_count"], 0)
        self.assertEqual(counts["simulated_journal_exact_count"], 1)
        self.assertEqual(counts["simulated_journal_unbound_count"], 0)
        self.assertEqual(counts["unknown_effect_run_count"], 1)
        self.assertIsNone(counts["external_observed_count"])

    def test_monitor_reconciles_historical_confirmation_against_exact_current_journal(self):
        run_id = self.approved()
        self.runtime.submit(run_id, **self.identity)
        run = self.runtime.readback(run_id, **self.identity)
        operation = run["operation_id"]
        for change, exact, unbound in (
            ("UPDATE journal SET committed_at='2026-11-15T12:01:00+00:00'", 1, 0),
            ("UPDATE journal SET account_id='synthetic:wrong'", 0, 1),
            ("DELETE FROM journal", 0, 0),
        ):
            with self.subTest(change=change):
                self.runtime.db.execute(change + " WHERE operation_id=?", (operation,))
                before = self.runtime.db.execute("SELECT * FROM journal").fetchall()
                counts = summarize(self.path)
                self.assertEqual(counts["recorded_readback_confirmation_count"], 1)
                self.assertEqual(counts["simulated_readback_confirmed_count"], 0)
                self.assertEqual(counts["simulated_readback_conflict_count"], 1)
                self.assertEqual(counts["simulated_journal_exact_count"], exact)
                self.assertEqual(counts["simulated_journal_unbound_count"], unbound)
                self.assertEqual(self.runtime.db.execute("SELECT * FROM journal").fetchall(), before)

    def test_monitor_reports_local_readback_rejection_and_orphan_journal(self):
        run_id = self.approved()
        run = self.runtime.submit(run_id, **self.identity)
        self.runtime.db.execute("UPDATE journal SET draft_hash=? WHERE operation_id=?",
                                ("0" * 64, run["operation_id"]))
        self.runtime.db.execute("INSERT INTO journal VALUES (?,?,?,?,?)",
                                ("orphan", run["account_id"], run["instrument_id"],
                                 run["draft_hash"], NOW.isoformat()))
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "mismatch")
        counts = summarize(self.path)
        self.assertEqual(counts["simulated_readback_mismatch_count"], 1)
        self.assertEqual(counts["stopped_run_count"], 1)
        self.assertEqual(counts["simulated_readback_confirmed_count"], 0)
        self.assertEqual(counts["simulated_journal_exact_count"], 0)
        self.assertEqual(counts["simulated_journal_unbound_count"], 2)
        self.assertIsNone(counts["external_observed_count"])

    def test_monitor_holds_one_snapshot_during_a_concurrent_valid_write(self):
        run_id = self.approved()

        def submit_after_snapshot_starts(db, objects):
            verify_schema(db, objects)
            self.runtime.submit(run_id, **self.identity)
            self.runtime.readback(run_id, **self.identity)

        with patch("pilot.monitor.verify_schema", side_effect=submit_after_snapshot_starts):
            before = summarize(self.path)
        self.assertEqual((before["queued_operation_count"], before["simulated_journal_row_count"]), (0, 0))
        self.assertEqual(summarize(self.path)["simulated_readback_confirmed_count"], 1)

    def test_monitor_rejects_unbound_snapshot_and_cli_sanitizes_failure(self):
        run_id = self.approved()
        self.runtime.submit(run_id, **self.identity)
        self.runtime.readback(run_id, **self.identity)
        self.runtime.db.execute("UPDATE runs SET data=? WHERE id=?", ("{private-canary", run_id))
        with self.assertRaises(IntegrityError):
            summarize(self.path)
        script = Path(__file__).resolve().parents[1] / "scripts/monitor_synthetic.py"
        result = subprocess.run([sys.executable, "-B", str(script), str(self.path)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "Synthetic ledger unavailable or inconsistent.\n")

    def test_monitor_checks_required_schema_even_when_tables_are_readable(self):
        self.approved()
        self.runtime.db.execute("DROP TRIGGER events_no_delete")
        with self.assertRaisesRegex(IntegrityError, "incompatible synthetic ledger schema"):
            summarize(self.path)

    def test_monitor_checks_event_chain_with_schema_intact(self):
        run_id = self.approved()
        db = self.runtime.db
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET event_hash=? WHERE run_id=? AND seq=1",
                   ("f" * 64, run_id))
        db.execute(SCHEMA_OBJECTS["trigger", "events_no_update"])
        with self.assertRaisesRegex(IntegrityError, "Run integrity verification failed"):
            summarize(self.path)

    def test_monitor_opens_literal_database_filename_read_only(self):
        target = Path(self.temp.name) / "monitor?fixture#1.sqlite"
        other = Runtime(target, clock=lambda: NOW)
        try:
            self.assertEqual(summarize(target)["runs"], 0)
            missing = target.with_suffix(".missing")
            with self.assertRaises(FileNotFoundError):
                summarize(missing)
            self.assertFalse(missing.exists())
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
