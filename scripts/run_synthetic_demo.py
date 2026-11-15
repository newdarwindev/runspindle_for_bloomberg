#!/usr/bin/env python3
"""Generate deterministic, synthetic issue #5 run traces. No live effects."""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot.adapters import ObservationRequest, SyntheticObservationAdapter
from pilot.runtime import Runtime

OUTPUT = ROOT / "pilot/demo-runs.v1.json"


def build_demo():
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    ids = iter(("synthetic-success", "synthetic-timeout"))
    identity = dict(actor_id="synthetic-operator", account_id="synthetic:paper-desk",
                    session_id="synthetic-session")
    fixture = json.loads((ROOT / "pilot/fixtures/case-10-observation.v1.json").read_text())
    source = SyntheticObservationAdapter(fixture, clock=lambda: now)
    request = ObservationRequest(account_id=identity["account_id"],
                                 session_id=identity["session_id"],
                                 instrument_id="SYNTH-CASE-10")
    with tempfile.TemporaryDirectory() as temporary:
        runtime = Runtime(Path(temporary) / "demo.sqlite", clock=lambda: now,
                          id_factory=lambda: next(ids))
        traces = []
        for mode in ("success", "timeout_after_commit"):
            run_id, source_result = runtime.create_from_adapter(
                source, request, actor_id=identity["actor_id"],
                lease_until=(now + timedelta(hours=1)).isoformat(),
                deadline=(now + timedelta(minutes=30)).isoformat())
            assert run_id and source_result.status == "ok"
            runtime.preview(run_id, **identity)
            runtime.approve(run_id, **identity, accepted=True)
            before_readback = runtime.submit(run_id, **identity, mode=mode)
            after_readback = runtime.readback(run_id, **identity)
            traces.append({"mode": mode, "run_id": run_id,
                           "source_receipt": source_result.receipt,
                           "before_readback_state": before_readback["state"],
                           "before_readback_effect": before_readback["effect_status"],
                           "after_readback_state": after_readback["state"],
                           "after_readback_effect": after_readback["effect_status"],
                           "operation_id": after_readback["operation_id"],
                           "destination_receipts": after_readback["destination_receipts"],
                           "chain_valid": runtime.verify_chain(run_id),
                           "events": [json.loads(event["payload"]) for event in runtime.events(run_id)]})
        runtime.close()
    return {"schema_version": 1, "evidence_level": "deterministic_synthetic_demo",
            "live_connection": False, "traces": traces}


def main():
    expected = json.dumps(build_demo(), indent=2) + "\n"
    if __import__("sys").argv[1:] == ["--check"]:
        if not OUTPUT.exists() or OUTPUT.read_text() != expected:
            raise SystemExit("Synthetic trace differs; regenerate deliberately")
        print("Synthetic demo traces match")
    else:
        OUTPUT.write_text(expected)
        print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
