"""Recheck time-sensitive authority at the actual synthetic effect boundary."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pilot.adapters import ObservationRequest, SyntheticObservationAdapter
from pilot.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
FIXTURE = json.loads((ROOT / "pilot/fixtures/case-10-observation.v1.json").read_text())
IDENTITY = dict(actor_id="operator", account_id=FIXTURE["account_id"],
                session_id=FIXTURE["session_id"])


class FinalAuthorityTests(unittest.TestCase):
    def test_expiry_after_intent_has_no_effect_and_restart_never_resubmits(self):
        for boundary in ("lease", "deadline", "source"):
            for mode in ("success", "timeout_after_commit"):
                with self.subTest(boundary=boundary, mode=mode), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "runs.sqlite"
                    now = [NOW]
                    runtime = Runtime(path, clock=lambda: now[0])
                    lease = NOW + timedelta(minutes=30 if boundary == "lease" else 180)
                    deadline = NOW + timedelta(minutes=30 if boundary == "deadline" else 180)
                    run_id, _ = runtime.create_from_adapter(
                        SyntheticObservationAdapter(FIXTURE, clock=lambda: now[0]),
                        ObservationRequest(IDENTITY["account_id"], IDENTITY["session_id"], FIXTURE["instrument_id"]),
                        actor_id=IDENTITY["actor_id"], lease_until=lease.isoformat(), deadline=deadline.isoformat())
                    preview = runtime.preview(run_id, **IDENTITY)
                    runtime.approve(run_id, **IDENTITY, accepted=True,
                                    preview_revision=preview["revision"], draft_hash=preview["draft_hash"])
                    original = runtime._write
                    def delayed(*args):
                        original(*args)
                        if args[1] == "begin_submission":
                            now[0] = NOW + timedelta(minutes=61 if boundary == "source" else 30)
                    runtime._write = delayed
                    calls = []
                    execute = runtime.destination.execute
                    def counted(run):
                        calls.append(run["operation_id"])
                        return execute(run)
                    runtime.destination.execute = counted
                    with self.assertRaises(PermissionError):
                        runtime.submit(run_id, **IDENTITY, mode=mode)
                    self.assertEqual(calls, [])
                    self.assertEqual(runtime.status(run_id)["state"], "submitting")
                    self.assertEqual(runtime.status(run_id)["submissions"], 1)
                    runtime.close()
                    script = '''
import json,sys
from datetime import datetime
from pilot.runtime import Runtime
identity=json.loads(sys.argv[3])
r=Runtime(sys.argv[1],clock=lambda:datetime.fromisoformat(sys.argv[4]))
if r.recover(sys.argv[2],**identity)["state"]!="uncertain": raise AssertionError("not uncertain")
try: r.submit(sys.argv[2],**identity)
except (ValueError,PermissionError): pass
else: raise AssertionError("resubmission allowed")
result=r.readback(sys.argv[2],**identity)
if result["effect_status"]!="unknown" or result["submissions"]!=1: raise AssertionError("lost uncertainty")
if not r.verify_chain(sys.argv[2]): raise AssertionError("invalid chain")
r.close()
'''
                    result = subprocess.run([sys.executable, "-c", script, str(path), run_id,
                                             json.dumps(IDENTITY), now[0].isoformat()],
                                            cwd=ROOT, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    with closing(sqlite3.connect(path)) as independent:
                        self.assertEqual(independent.execute("SELECT count(*) FROM journal").fetchone()[0], 0)
                        actions = [json.loads(row[0])["action"] for row in
                                   independent.execute("SELECT payload FROM events ORDER BY seq")]
                        self.assertEqual(actions.count("begin_submission"), 1)
                        self.assertNotIn("adapter_response", actions)
                        self.assertNotIn("adapter_timeout", actions)
