"""Actual SQLite corruption/restart fences; no external adapters or effects."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pilot.runtime import IntegrityError, Runtime

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
IDENTITY = dict(actor_id="operator", account_id="synthetic:desk", session_id="session")
ROOT = Path(__file__).resolve().parents[1]


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "runs.sqlite"
        self.runtime = Runtime(self.path, clock=lambda: NOW)
        self.run_id = self.runtime.create(
            **IDENTITY, instrument_id="SYNTH-CASE-10",
            observation=dict(instrument_id="SYNTH-CASE-10", prior_date="2026-11-13",
                             current_date="2026-11-14", source_timestamp="2026-11-15T11:00:00Z",
                             prior_close="50", current_close="48.9", cash_dividend="1.2",
                             entitled=True, fresh=True, no_other_corporate_action=True),
            lease_until=(NOW + timedelta(hours=1)).isoformat(),
            deadline=(NOW + timedelta(minutes=30)).isoformat())
        preview = self.runtime.preview(self.run_id, **IDENTITY)
        self.runtime.approve(self.run_id, **IDENTITY, accepted=True,
                             preview_revision=preview["revision"], draft_hash=preview["draft_hash"])

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def alter(self, change):
        with closing(sqlite3.connect(self.path)) as db, db:
            raw = db.execute("SELECT data FROM runs WHERE id=?", (self.run_id,)).fetchone()[0]
            run = json.loads(raw)
            run.update(change)
            db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(run), self.run_id))
        return raw

    def test_all_snapshot_authority_fields_fenced_after_fresh_process_reopen(self):
        changes = dict(owner_id="other", account_id="synthetic:other", session_id="other",
                       instrument_id="OTHER", approval_actor="other", allowed_actions=[],
                       max_submissions=2, submissions=-1, lease_until="2099-01-01T00:00:00Z",
                       deadline="2099-01-01T00:00:00Z", destination="other",
                       runtime_version="other", model_version="other", id="other")
        with closing(sqlite3.connect(self.path)) as db:
            original = db.execute("SELECT data FROM runs").fetchone()[0]
            event_count = db.execute("SELECT count(*) FROM events").fetchone()[0]
        script = '''
import json,sys
from datetime import datetime,timezone
from pilot.runtime import Runtime,IntegrityError
r=Runtime(sys.argv[1],clock=lambda:datetime(2026,11,15,12,tzinfo=timezone.utc))
identity=dict(actor_id="operator",account_id="synthetic:desk",session_id="session")
def forbidden(*a,**k): raise AssertionError("destination invoked")
r.destination.execute=forbidden
r.destination.readback=forbidden
blocked=0
for action in [lambda:r.status(sys.argv[2]),lambda:r.submit(sys.argv[2],**identity),
               lambda:r.recover(sys.argv[2],**identity),lambda:r.readback(sys.argv[2],**identity),
               lambda:r.control(sys.argv[2],"cancel",**identity),lambda:r.revoke(sys.argv[2],**identity)]:
 try: action()
 except IntegrityError: blocked+=1
if blocked != 6: raise AssertionError(f"Blocked {blocked} of 6 operations")
if r.verify_chain(sys.argv[2]): raise AssertionError("Corrupt snapshot passed verification")
if r.db.in_transaction: raise AssertionError("Failed read or action left a transaction open")
r.close()
'''
        for field, value in changes.items():
            with self.subTest(field=field):
                self.alter({field: value})
                result = subprocess.run([sys.executable, "-c", script, str(self.path), self.run_id],
                                        cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                with closing(sqlite3.connect(self.path)) as db, db:
                    self.assertEqual(db.execute("SELECT count(*) FROM journal").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], event_count)
                    db.execute("UPDATE runs SET data=?", (original,))

    def test_malformed_snapshot_fails_closed_and_unmodified_run_remains_usable(self):
        with closing(sqlite3.connect(self.path)) as db:
            original = db.execute("SELECT data FROM runs").fetchone()[0]
        for invalid in ("{", "null", "[]"):
            self.runtime.db.execute("UPDATE runs SET data=?", (invalid,))
            self.assertFalse(self.runtime.verify_chain(self.run_id))
            with self.assertRaises(IntegrityError):
                self.runtime.submit(self.run_id, **IDENTITY)
        self.runtime.db.execute("UPDATE runs SET data=?", (original,))
        self.runtime.submit(self.run_id, **IDENTITY)
        self.assertEqual(self.runtime.readback(self.run_id, **IDENTITY)["state"], "recorded")

    def test_disabling_integrity_guard_exposes_real_journal_effect(self):
        self.alter({"max_submissions": 2})
        with self.assertRaises(IntegrityError):
            self.runtime.submit(self.run_id, **IDENTITY)
        # Deliberate local mutation: the independent effect observation must
        # change when the read-before-act integrity fence is removed.
        self.runtime._verify_snapshot = lambda *_: True
        self.runtime.submit(self.run_id, **IDENTITY)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM journal").fetchone()[0], 1)

    def test_legacy_unsealed_tail_is_not_silently_upgraded(self):
        from pilot.runtime import canonical, digest
        event = self.runtime.events(self.run_id)[-1]
        payload = json.loads(event["payload"])
        del payload["snapshot_sha256"]
        payload = canonical(payload)
        self.runtime.db.execute("DROP TRIGGER events_no_update")
        self.runtime.db.execute("UPDATE events SET payload=?,event_hash=? WHERE seq=?",
                                (payload, digest(event["prev_hash"] + payload), event["seq"]))
        self.assertFalse(self.runtime.verify_chain(self.run_id))
        with self.assertRaises(IntegrityError):
            self.runtime.recover(self.run_id, **IDENTITY)
        self.assertEqual(len(self.runtime.events(self.run_id)), 3)

    def test_concurrent_valid_writer_does_not_create_false_corruption(self):
        other = Runtime(self.path, clock=lambda: NOW)
        original = self.runtime._verify_snapshot
        def concurrent(run_id, run):
            other.control(run_id, "pause", **IDENTITY)
            self.runtime._verify_snapshot = original
            return original(run_id, run)
        self.runtime._verify_snapshot = concurrent
        try:
            self.assertEqual(self.runtime.status(self.run_id)["state"], "approved")
            self.assertEqual(self.runtime.status(self.run_id)["state"], "paused")
        finally:
            other.close()

    def test_baseexception_rolls_back_transition_and_releases_writer(self):
        before = self.runtime.status(self.run_id)
        original = self.runtime._write
        def interrupt(*args):
            original(*args)
            raise KeyboardInterrupt()
        self.runtime._write = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.runtime.submit(self.run_id, **IDENTITY)
        self.assertFalse(self.runtime.db.in_transaction)
        self.assertEqual(self.runtime.status(self.run_id), before)
        with closing(sqlite3.connect(self.path, timeout=0.1)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.assertEqual(db.execute("SELECT count(*) FROM journal").fetchone()[0], 0)
