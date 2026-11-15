"""Read-only counters for the local synthetic run ledger."""
import json
import sqlite3
from pathlib import Path


def summarize(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        runs = [json.loads(row[0]) for row in db.execute("SELECT data FROM runs")]
        events = [(row[0], json.loads(row[1])) for row in db.execute("SELECT run_id,payload FROM events")]
        journal_rows = db.execute("SELECT count(*) FROM journal").fetchone()[0]
    finally:
        db.close()
    queued = {event["operation_id"] for _, event in events
              if event["action"] == "begin_submission" and event["operation_id"]}
    emitted = {event["operation_id"] for _, event in events
               if event["action"] in ("adapter_response", "adapter_timeout") and event["operation_id"]}
    confirmed = {event["operation_id"] for _, event in events
                 if event["action"] == "readback_confirmed" and event["operation_id"]}
    stopped = {run_id for run_id, event in events
               if event["action"] in ("decline", "pause", "readback_mismatch", "revoke")}
    return {"evidence_level": "synthetic_local_only", "runs": len(runs),
            "queued_operation_count": len(queued), "emitted_operation_count": len(emitted),
            "stopped_run_count": len(stopped), "simulated_journal_row_count": journal_rows,
            "simulated_readback_confirmed_count": len(confirmed),
            "unknown_effect_run_count": sum(run["effect_status"] == "unknown" for run in runs),
            "interrupted_run_count": sum(run["state"] == "submitting" for run in runs),
            "external_observed_count": None, "source_rejection_count": None}
