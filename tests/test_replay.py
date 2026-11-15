import json
import unittest

from scripts.replay_corpus import build
from scripts.verify_replay import classify, verify


class ReplayTests(unittest.TestCase):
    def test_corpus_preserves_all_cases_and_sources(self):
        corpus = build()
        self.assertEqual(len(corpus["fixtures"]), 40)
        self.assertEqual({f["id"] for f in corpus["fixtures"]}, set(range(1, 41)))
        self.assertEqual({f["editorial_rank"] for f in corpus["fixtures"]}, set(range(1, 41)))
        self.assertTrue(all(f["source_urls"] and f["review_status"] == "unverified_source_prose"
                            for f in corpus["fixtures"]))

    def test_acceptance_requires_every_evidence_gate(self):
        run = dict(decision="execute", effect_status="confirmed", authorized=True,
                   approval_receipt="approval:1", source_receipt="source:1",
                   destination_readback="readback:1", independent_review="accepted")
        self.assertEqual(classify(run), "accepted_authorized_completion")
        for field in ("effect_status", "authorized", "approval_receipt", "source_receipt",
                      "destination_readback", "independent_review"):
            incomplete = dict(run)
            incomplete.pop(field)
            self.assertEqual(classify(incomplete), "produced_only", field)
        self.assertEqual(classify({**run, "effect_status": "unknown"}), "unknown_effect")
        self.assertEqual(classify({**run, "boundary_violation": True}), "boundary_failure")

    def test_refusal_and_duplicate_run(self):
        self.assertEqual(classify({"decision": "pause"}), "unverified_refusal")
        self.assertEqual(classify({"decision": "refuse", "independent_review": "correct_refusal"}),
                         "correct_refusal")
        with self.assertRaisesRegex(ValueError, "unique"):
            verify([{"run_id": "x", "fixture_id": 1, "decision": "pause"}] * 2, build())


if __name__ == "__main__":
    unittest.main()
