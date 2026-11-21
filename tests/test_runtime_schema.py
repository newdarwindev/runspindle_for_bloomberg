"""Synthetic ledger initialization and reopening over actual SQLite files."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pilot.runtime import IntegrityError, Runtime

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
IDENTITY = dict(actor_id="operator", account_id="synthetic:desk", session_id="session")
# Exact v1 SQL from the prior format, independently of the new schema inventory.
LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
    payload TEXT NOT NULL, prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TABLE IF NOT EXISTS journal(
    operation_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL, draft_hash TEXT NOT NULL,
    committed_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
"""


def child(code, *args):
    return subprocess.run(
        [sys.executable, "-B", "-c", code, *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )


class RuntimeSchemaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "ledger #1?.sqlite"

    def legacy(self, version=1):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(LEGACY_SCHEMA)
            db.execute("INSERT INTO schema_meta VALUES (?)", (version,))

    def inventory(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute(
                "SELECT type,name,sql FROM sqlite_schema ORDER BY name"
            ).fetchall()

    def approved(self, runtime):
        run = runtime.create(
            **IDENTITY,
            instrument_id="SYNTH-CASE-10",
            observation=dict(
                instrument_id="SYNTH-CASE-10",
                prior_date="2026-11-13",
                current_date="2026-11-14",
                source_timestamp="2026-11-15T11:00:00Z",
                prior_close="50",
                current_close="48.9",
                cash_dividend="1.2",
                entitled=True,
                fresh=True,
                no_other_corporate_action=True,
            ),
            lease_until=(NOW + timedelta(hours=1)).isoformat(),
            deadline=(NOW + timedelta(minutes=30)).isoformat(),
        )
        preview = runtime.preview(run, **IDENTITY)
        runtime.approve(run, **IDENTITY, accepted=True,
                        preview_revision=preview["revision"], draft_hash=preview["draft_hash"])
        return run

    def submitted(self):
        with closing(Runtime(self.path, clock=lambda: NOW)) as runtime:
            run = self.approved(runtime)
            runtime.submit(run, **IDENTITY, mode="timeout_after_commit")
            return run

    def test_prior_v1_store_and_its_effect_reopen_without_schema_rewrite(self):
        self.legacy()
        initial = self.inventory()
        run = self.submitted()
        with closing(Runtime(self.path, create=False)) as runtime:
            self.assertTrue(runtime.verify_chain(run))
            self.assertEqual(runtime.readback(run, **IDENTITY)["state"], "recorded")
        self.assertEqual(self.inventory(), initial)

    def test_lost_journal_blocks_fresh_process_before_destination(self):
        run = self.submitted()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM journal").fetchone(), (1,)
            )
            db.execute("DROP TABLE journal")
            previous = db.execute("SELECT data FROM runs").fetchall()
            count = db.execute("SELECT count(*) FROM events").fetchone()
        marker = self.path.with_suffix(".marker")
        result = child(
            """
import sys
from pathlib import Path
import pilot.runtime as runtime
original = runtime.SyntheticPaperDestination
class Destination(original):
    def readback(self, run):
        Path(sys.argv[3]).write_text("readback boundary reached")
        return super().readback(run)
runtime.SyntheticPaperDestination = Destination
try:
    r = runtime.Runtime(sys.argv[1])
except runtime.IntegrityError:
    sys.exit(0)
try:
    r.readback(sys.argv[2], actor_id="operator", account_id="synthetic:desk", session_id="session")
finally:
    r.close()
sys.exit("corrupt ledger opened")
""",
            self.path,
            run,
            marker,
        )
        self.assertFalse(
            marker.exists(), "lost journal must never invoke destination readback"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("journal", {name for _, name, _ in self.inventory()})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT data FROM runs").fetchall(), previous)
            self.assertEqual(
                db.execute("SELECT count(*) FROM events").fetchone(), count
            )

    def test_corrupt_and_future_schemas_are_not_modified(self):
        for change in [
            "DROP TABLE schema_meta",
            "DELETE FROM schema_meta",
            "INSERT INTO schema_meta VALUES (1)",
            "UPDATE schema_meta SET version=99",
            "ALTER TABLE journal ADD COLUMN unexpected TEXT",
            "DROP TRIGGER events_no_delete",
            "DROP TRIGGER events_no_update; CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT 1; END",
        ]:
            with self.subTest(change=change):
                self.legacy()
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.executescript(change)
                prior = self.path.read_bytes()
                with self.assertRaises(IntegrityError):
                    Runtime(self.path)
                self.assertEqual(self.path.read_bytes(), prior)
                self.path.unlink()

    def test_schema_drift_after_intent_prevents_destination_execution(self):
        with closing(Runtime(self.path, clock=lambda: NOW)) as runtime:
            run = self.approved(runtime)
            begins = 0

            def drop_guard_before_effect(statement):
                nonlocal begins
                if statement == "BEGIN IMMEDIATE":
                    begins += 1
                    if begins == 2:
                        with closing(sqlite3.connect(self.path)) as db, db:
                            db.execute("DROP TRIGGER events_no_delete")

            runtime.db.set_trace_callback(drop_guard_before_effect)
            try:
                with patch.object(runtime.destination, "execute", wraps=runtime.destination.execute) as execute:
                    with self.assertRaises(IntegrityError):
                        runtime.submit(run, **IDENTITY)
                    execute.assert_not_called()
            finally:
                runtime.db.set_trace_callback(None)
        self.assertEqual(begins, 2)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM journal").fetchone(), (0,))
            stored = json.loads(db.execute("SELECT data FROM runs").fetchone()[0])
            self.assertEqual((stored["state"], stored["submissions"]), ("submitting", 1))
            actions = [
                json.loads(payload)["action"]
                for (payload,) in db.execute("SELECT payload FROM events ORDER BY seq")
            ]
            self.assertEqual(actions[-1], "begin_submission")
            self.assertNotIn("events_no_delete", {name for _, name, _ in self.inventory()})

    def test_open_connection_rejects_readback_and_observation_after_schema_drift(self):
        run = self.submitted()
        with closing(Runtime(self.path, clock=lambda: NOW, create=False)) as runtime:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("UPDATE schema_meta SET version=99")
                history = db.execute("SELECT * FROM events ORDER BY seq").fetchall()
            with patch.object(runtime.destination, "readback", wraps=runtime.destination.readback) as read:
                with self.assertRaises(IntegrityError):
                    runtime.readback(run, **IDENTITY)
                read.assert_not_called()
            for observe in (runtime.status, runtime.events):
                with self.assertRaises(IntegrityError):
                    observe(run)
            self.assertFalse(runtime.verify_chain(run))
            self.assertFalse(runtime.db.in_transaction)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT * FROM events ORDER BY seq").fetchall(), history)
            self.assertEqual(db.execute("SELECT version FROM schema_meta").fetchall(), [(99,)])

    def test_reopen_and_inspection_cannot_bootstrap_a_missing_or_empty_store(self):
        with self.assertRaises(sqlite3.OperationalError):
            Runtime(self.path, create=False)
        self.assertFalse(self.path.exists())
        self.path.touch()
        with self.assertRaises(IntegrityError):
            Runtime(self.path, create=False)
        failed = subprocess.run(
            [sys.executable, "-B", "scripts/inspect_run.py", str(self.path), "run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertIn("Cannot open a compatible synthetic ledger", failed.stderr)
        self.assertEqual(self.path.read_bytes(), b"")

    def test_interrupted_bootstrap_leaves_no_partial_schema(self):
        result = child(
            """
import os, sqlite3, sys
from pilot.runtime import Runtime
connect = sqlite3.connect
def interrupt(action, table, *_):
    if action == sqlite3.SQLITE_CREATE_TABLE and table == "journal":
        os._exit(73)
    return sqlite3.SQLITE_OK
def intercepted(*args, **kwargs):
    db = connect(*args, **kwargs)
    db.set_authorizer(interrupt)
    return db
sqlite3.connect = intercepted
Runtime(sys.argv[1])
""",
            self.path,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual(self.inventory(), [])
        with self.assertRaises(IntegrityError):
            Runtime(self.path, create=False)
        with closing(Runtime(self.path)) as runtime:
            self.assertEqual(
                runtime.db.execute("SELECT version FROM schema_meta").fetchone()[0], 1
            )

    def test_concurrent_initializers_keep_one_marker_and_journal(self):
        script = "import sys; from pilot.runtime import Runtime; Runtime(sys.argv[1]).close()"
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: child(script, self.path), range(4)))
        self.assertEqual([result.stderr for result in results], [""] * 4)
        self.assertEqual([result.returncode for result in results], [0] * 4)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT version FROM schema_meta").fetchall(), [(1,)]
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM journal").fetchone(), (0,)
            )
