import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pilot.runtime import IntegrityError, Runtime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "runs.sqlite"
        self.now = [datetime(2026, 11, 15, 12, tzinfo=timezone.utc)]
        self.runtime = Runtime(self.path, clock=lambda: self.now[0])
        self.identity = dict(actor_id="operator-1", account_id="synthetic:desk-1", session_id="session-1")
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
                                   lease_until=(self.now[0] + timedelta(hours=1)).isoformat(),
                                   deadline=(self.now[0] + timedelta(minutes=30)).isoformat())

    def approved(self):
        run_id = self.create()
        preview = self.runtime.preview(run_id, **self.identity)
        self.runtime.approve(run_id, **self.identity, accepted=True,
                             preview_revision=preview["revision"], draft_hash=preview["draft_hash"])
        return run_id

    def test_success_requires_readback_and_chain_is_append_only(self):
        run_id = self.approved()
        self.assertEqual(self.runtime.status(run_id)["draft"]["decision"], "pass")
        self.assertEqual(self.runtime.submit(run_id, **self.identity)["state"], "pending_readback")
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["state"], "recorded")
        self.assertEqual(self.runtime.status(run_id)["effect_status"], "confirmed")
        self.assertTrue(self.runtime.verify_chain(run_id))
        with self.assertRaisesRegex(sqlite3.DatabaseError, "append only"):
            self.runtime.db.execute("DELETE FROM events WHERE run_id=?", (run_id,))

    def test_account_session_and_lease_fence(self):
        run_id = self.create()
        with self.assertRaises(PermissionError):
            self.runtime.preview(run_id, **{**self.identity, "account_id": "synthetic:other"})
        with self.assertRaises(PermissionError):
            self.runtime.preview(run_id, **{**self.identity, "session_id": "stale-session"})
        with self.assertRaises(PermissionError):
            self.runtime.preview(run_id, **{**self.identity, "actor_id": "other-operator"})
        self.now[0] += timedelta(hours=2)
        with self.assertRaisesRegex(PermissionError, "lease expired"):
            self.runtime.preview(run_id, **self.identity)

    def test_timeout_duplicate_and_readback(self):
        run_id = self.approved()
        result = self.runtime.submit(run_id, **self.identity, mode="timeout_after_commit")
        self.assertEqual(result["state"], "uncertain")
        self.assertEqual(result["effect_status"], "unknown")
        with self.assertRaises(ValueError):
            self.runtime.submit(run_id, **self.identity)
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["state"], "recorded")
        self.assertEqual(self.runtime.db.execute("SELECT count(*) FROM journal").fetchone()[0], 1)

    def test_missing_readback_and_cancel_preserve_unknown_effect(self):
        run_id = self.approved()
        self.runtime.submit(run_id, **self.identity, mode="timeout_before_commit")
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["state"], "uncertain")
        self.runtime.control(run_id, "cancel", **self.identity)
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "unknown")
        with self.assertRaises(ValueError):
            self.runtime.submit(run_id, **self.identity)

    def test_readback_mismatch_pauses(self):
        run_id = self.approved()
        self.runtime.submit(run_id, **self.identity)
        self.runtime.db.execute("UPDATE journal SET instrument_id='WRONG' WHERE operation_id=?",
                                (self.runtime.status(run_id)["operation_id"],))
        result = self.runtime.readback(run_id, **self.identity)
        self.assertEqual((result["state"], result["effect_status"]), ("paused", "mismatch"))

    def test_decline_cancel_and_takeover(self):
        run_id = self.create()
        preview = self.runtime.preview(run_id, **self.identity)
        declined = self.runtime.approve(run_id, **self.identity, accepted=False,
                                        preview_revision=preview["revision"], draft_hash=preview["draft_hash"])
        self.assertEqual(declined["state"], "paused")
        with self.assertRaises(ValueError):
            self.runtime.submit(run_id, **self.identity)
        other = self.approved()
        self.runtime.control(other, "takeover", **self.identity)
        self.assertEqual(self.runtime.control(other, "handback", **self.identity)["state"], "setup")
        with self.assertRaises(ValueError):
            self.runtime.submit(other, **self.identity)
        self.runtime.control(other, "cancel", **self.identity)
        with self.assertRaises(ValueError):
            self.runtime.preview(other, **self.identity)
        with self.assertRaises(ValueError):
            self.runtime.readback(other, **self.identity)

    def test_revision_invalidates_draft_and_is_fenced_after_submission(self):
        run_id = self.create()
        first = self.runtime.preview(run_id, **self.identity)
        changed = {**self.observation, "current_close": "48.95"}
        revised = self.runtime.revise(run_id, changed, **self.identity)
        self.assertEqual(revised["state"], "setup")
        self.assertIsNone(revised["draft_hash"])
        self.assertNotEqual(revised["artifact_hash"], first["artifact_hash"])
        preview = self.runtime.preview(run_id, **self.identity)
        self.runtime.approve(run_id, **self.identity, accepted=True,
                             preview_revision=preview["revision"], draft_hash=preview["draft_hash"])
        self.runtime.submit(run_id, **self.identity)
        with self.assertRaises(ValueError):
            self.runtime.revise(run_id, changed, **self.identity)

    def test_approval_and_decline_require_the_reviewed_preview(self):
        for current_close in ("48.90", "48.95"):
            with self.subTest(current_close=current_close):
                run_id = self.create()
                first = self.runtime.preview(run_id, **self.identity)
                with closing(Runtime(self.path, clock=lambda: self.now[0], create=False)) as other:
                    other.revise(run_id, {**self.observation, "current_close": current_close},
                                 **self.identity)
                    replacement = other.preview(run_id, **self.identity)
                events = self.runtime.events(run_id)
                self.assertNotEqual(first["revision"], replacement["revision"])
                self.assertEqual(first["draft_hash"] == replacement["draft_hash"],
                                 current_close == self.observation["current_close"])
                destination = self.runtime.destination
                with patch.object(destination, "approve", wraps=destination.approve) as destination_approve:
                    for decision, revision, draft_hash in (
                        (True, first["revision"], first["draft_hash"]),
                        (False, first["revision"], first["draft_hash"]),
                        (True, replacement["revision"], "0" * 64),
                    ):
                        with self.assertRaisesRegex(ValueError, "preview no longer matches"):
                            self.runtime.approve(run_id, **self.identity, accepted=decision,
                                                 preview_revision=revision, draft_hash=draft_hash)
                    destination_approve.assert_not_called()
                with self.assertRaises(ValueError):
                    self.runtime.submit(run_id, **self.identity)
                self.assertEqual(self.runtime.status(run_id), replacement)
                self.assertEqual(self.runtime.events(run_id), events)

                approved = self.runtime.approve(run_id, **self.identity, accepted=True,
                                                preview_revision=replacement["revision"],
                                                draft_hash=replacement["draft_hash"])
                self.assertEqual(approved["draft_hash"], replacement["draft_hash"])
                with closing(sqlite3.connect(self.path)) as observer:
                    self.assertEqual(observer.execute("SELECT count(*) FROM journal").fetchone(), (0,))

    def test_non_boolean_decision_cannot_approve_a_matching_preview(self):
        run_id = self.create()
        preview = self.runtime.preview(run_id, **self.identity)
        for decision in ("decline", 1, None):
            with self.subTest(decision=decision), self.assertRaisesRegex(ValueError, "boolean decision"):
                self.runtime.approve(run_id, **self.identity, accepted=decision,
                                     preview_revision=preview["revision"], draft_hash=preview["draft_hash"])
        self.assertEqual(self.runtime.status(run_id), preview)

    def test_restart_recovers_interrupted_submission_without_retry(self):
        run_id = self.approved()
        self.assertEqual(self.runtime.submit(run_id, **self.identity, mode="interrupted")["state"], "submitting")
        self.runtime.close()
        self.runtime = Runtime(self.path, clock=lambda: self.now[0])
        self.assertEqual(self.runtime.recover(run_id, **self.identity)["state"], "uncertain")
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "unknown")
        with self.assertRaises(ValueError):
            self.runtime.submit(run_id, **self.identity)
        self.assertTrue(self.runtime.verify_chain(run_id))

    def test_handback_preserves_operation_and_draft_for_fresh_process_readback(self):
        for mode in ("success", "timeout_after_commit", "interrupted"):
            with self.subTest(mode=mode):
                run_id = self.approved()
                submitted = self.runtime.submit(run_id, **self.identity, mode=mode)
                with closing(sqlite3.connect(self.path)) as observer:
                    effects = observer.execute("SELECT * FROM journal WHERE operation_id=?",
                                               (submitted["operation_id"],)).fetchall()
                self.assertEqual(len(effects), 0 if mode == "interrupted" else 1)
                self.runtime.control(run_id, "takeover", **self.identity)
                returned = self.runtime.control(run_id, "handback", **self.identity)
                self.assertEqual((returned["state"], returned["effect_status"]), ("uncertain", "unknown"))
                self.assertIsNone(returned["approval_actor"])
                for field in ("operation_id", "draft", "draft_hash", "submissions"):
                    self.assertEqual(returned[field], submitted[field])
                with self.assertRaises(ValueError):
                    self.runtime.submit(run_id, **self.identity)
                worker = subprocess.run([sys.executable, "-B", "-c", '''
import json, sys
from contextlib import closing
from pilot.runtime import Runtime
with closing(Runtime(sys.argv[1])) as r:
    print(json.dumps(r.readback(sys.argv[2], **json.loads(sys.argv[3]))))
''', str(self.path), run_id, json.dumps(self.identity)],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
                self.assertEqual(worker.returncode, 0, worker.stderr)
                result = json.loads(worker.stdout)
                self.assertEqual(result["effect_status"], "unknown" if not effects else "confirmed")
                with closing(sqlite3.connect(self.path)) as observer:
                    self.assertEqual(observer.execute("SELECT * FROM journal WHERE operation_id=?",
                                                      (submitted["operation_id"],)).fetchall(), effects)

    def test_takeover_between_intent_and_effect_blocks_destination(self):
        run_id = self.approved()
        original = self.runtime._transaction
        calls = []

        @contextmanager
        def handoff_after_commit():
            with original():
                yield
            if self.runtime.status(run_id)["state"] == "submitting":
                with closing(Runtime(self.path, clock=lambda: self.now[0])) as other:
                    other.control(run_id, "takeover", **self.identity)

        self.runtime._transaction = handoff_after_commit
        self.runtime.destination.execute = lambda run: calls.append(run["operation_id"])
        with self.assertRaisesRegex(ValueError, "Submission fenced"):
            self.runtime.submit(run_id, **self.identity)
        self.runtime._transaction = original
        self.assertEqual(calls, [])
        self.assertEqual(self.runtime.control(run_id, "handback", **self.identity)["state"], "uncertain")
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "unknown")
        with closing(sqlite3.connect(self.path)) as observer:
            self.assertEqual(observer.execute("SELECT count(*) FROM journal").fetchone(), (0,))

    def test_receipt_requires_exact_operation_and_explicit_confirmation(self):
        readback = self.runtime.destination.readback
        for field, value in (("status", "queued"), ("stage", "execute"), ("route", "other"),
                             ("operation_id", "other-op"), ("adapter_version", "future"),
                             ("journal_ref_sha256", None), ("journal_ref_sha256", "0" * 64),
                             ("status", "mismatch"), ("status", "absent_inconclusive"),
                             ("unreviewed_payload", "synthetic extra field")):
            with self.subTest(field=field, value=value):
                run_id = self.approved()
                run = self.runtime.submit(run_id, **self.identity)
                original = readback(run)
                history = self.runtime.events(run_id)
                self.runtime.destination.readback = lambda _, f=field, v=value: {**original, f: v}
                rejected = False
                try:
                    self.runtime.readback(run_id, **self.identity)
                except IntegrityError:
                    rejected = True
                self.assertEqual(self.runtime.status(run_id), run, "Invalid readback changed durable state")
                self.assertTrue(rejected)
                self.assertEqual(self.runtime.events(run_id), history)
        self.runtime.destination.readback = readback
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["state"], "recorded")

    def test_fresh_process_refuses_confirmation_without_independent_journal_row(self):
        run_id = self.approved()
        run = self.runtime.submit(run_id, **self.identity, mode="timeout_before_commit")
        receipt = dict(self.runtime.destination.readback(run), status="confirmed",
                       journal_ref_sha256="a" * 64)
        history = self.runtime.events(run_id)
        script = '''
import json, sys
from contextlib import closing
from pilot.runtime import IntegrityError, Runtime
with closing(Runtime(sys.argv[1], create=False)) as runtime:
    runtime.destination.readback = lambda _: json.loads(sys.argv[4])
    try:
        runtime.readback(sys.argv[2], **json.loads(sys.argv[3]))
    except IntegrityError:
        raise SystemExit(3)
'''
        child = subprocess.run(
            [sys.executable, "-B", "-c", script, str(self.path), run_id,
             json.dumps(self.identity), json.dumps(receipt)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(child.returncode, 3, child.stderr)
        self.assertEqual(self.runtime.status(run_id), run)
        self.assertEqual(self.runtime.events(run_id), history)
        with closing(sqlite3.connect(self.path)) as observer:
            self.assertEqual(observer.execute("SELECT count(*) FROM journal").fetchone(), (0,))

    def test_receipt_reader_cannot_manufacture_matching_journal_evidence(self):
        run_id = self.approved()
        run = self.runtime.submit(run_id, **self.identity, mode="timeout_before_commit")
        readback = self.runtime.destination.readback

        def manufacture(snapshot):
            self.runtime.db.execute("INSERT INTO journal VALUES (?,?,?,?,?)", (
                snapshot["operation_id"], snapshot["account_id"], snapshot["instrument_id"],
                snapshot["draft_hash"], self.now[0].isoformat(),
            ))
            return readback(snapshot)

        self.runtime.destination.readback = manufacture
        with self.assertRaises(IntegrityError):
            self.runtime.readback(run_id, **self.identity)
        self.assertEqual(self.runtime.status(run_id), run)
        with closing(sqlite3.connect(self.path)) as observer:
            self.assertEqual(observer.execute("SELECT count(*) FROM journal").fetchone(), (0,))

    def test_readback_input_is_detached_from_the_retained_run(self):
        run_id = self.approved()
        run = self.runtime.submit(run_id, **self.identity)
        readback = self.runtime.destination.readback

        def mutate(snapshot):
            receipt = readback(snapshot)
            snapshot["account_id"] = "synthetic:other"
            snapshot["draft"]["decision"] = "pause"
            return receipt

        self.runtime.destination.readback = mutate
        result = self.runtime.readback(run_id, **self.identity)
        self.assertEqual(result["state"], "recorded")
        self.assertEqual(result["account_id"], run["account_id"])
        self.assertEqual(result["draft"], run["draft"])
        self.assertEqual(result["draft_hash"], run["draft_hash"])

    def test_quarantined_restore_and_cancel_keep_reconciliation_fenced(self):
        run_id = self.approved()
        run = self.runtime.quarantine_after_restore(run_id, **self.identity)
        self.assertEqual(run["submissions"], 0)
        self.runtime.db.execute("INSERT INTO journal VALUES (?,?,?,?,?)", (
            run["operation_id"], run["account_id"], "WRONG", run["draft_hash"], self.now[0].isoformat(),
        ))
        self.assertEqual(self.runtime.readback(run_id, **self.identity)["effect_status"], "mismatch")
        with self.assertRaises(ValueError):
            self.runtime.revise(run_id, self.observation, **self.identity)
        self.runtime.control(run_id, "cancel", **self.identity)
        mismatched = self.runtime.readback(run_id, **self.identity)
        self.assertEqual((mismatched["state"], mismatched["effect_status"]), ("cancelled", "mismatch"))
        self.runtime.db.execute("UPDATE journal SET instrument_id=?", (run["instrument_id"],))
        reconciled = self.runtime.readback(run_id, **self.identity)
        self.assertEqual((reconciled["state"], reconciled["effect_status"]), ("cancelled", "confirmed"))
        with self.assertRaises(ValueError):
            self.runtime.submit(run_id, **self.identity)


if __name__ == "__main__":
    unittest.main()
