import copy
import unittest
from decimal import Decimal

from evaluation.finance_oracle import verify
from evaluation.finance_replay import expression, replay
from scripts.replay_finance import FIXTURES, ORACLE, REPORT, SOURCE_FIXTURES, build_report, load


class FinanceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = load(FIXTURES)
        cls.oracle = load(ORACLE)
        cls.source = load(SOURCE_FIXTURES)
        cls.report = build_report(cls.fixtures, cls.oracle, cls.source)

    def test_committed_all_case_report_reproduces(self):
        self.assertEqual(self.report, load(REPORT))
        self.assertEqual(self.report["baseline_count"], 40)
        self.assertEqual(self.report["adverse_count"], 128)
        self.assertEqual(self.report["failures"], [])
        family_splits = {}
        for row in self.report["cases"]:
            family_splits.setdefault(row["family"], set()).add(row["split"])
            self.assertTrue(row["source_urls"])
        self.assertTrue(all(len(splits) == 1 for splits in family_splits.values()))
        self.assertEqual(self.report["domain_review"], "not_run")
        self.assertTrue(all(value is None for value in self.report["measurement"].values()))

    def test_oracle_catches_changed_formula_even_with_same_decision(self):
        changed = copy.deepcopy(self.fixtures)
        changed["cases"][0]["calculations"]["gross_margin_usd"] = "901"
        report = build_report(changed, self.oracle, self.source)
        first = report["cases"][0]
        self.assertEqual(first["baseline"]["decision"], "stage_draft")
        self.assertEqual(report["failures"], [{
            "id": 1, "scenario": "baseline", "message": "computed metrics differ from frozen expectation",
        }])

    def test_oracle_rejects_computation_after_blocked_evidence(self):
        rows = copy.deepcopy(self.report["cases"])
        rows[0]["adverse"]["exact_delivery_month"]["metrics"]["quote_usd"] = "70800"
        errors = verify(self.fixtures["cases"], self.oracle["cases"], rows)
        self.assertEqual(errors[0]["scenario"], "exact_delivery_month")
        self.assertEqual(len(errors), 1)

    def test_missing_threshold_does_not_become_zero(self):
        oil = self.fixtures["cases"][12]
        self.assertEqual(replay(oil), {
            "decision": "pause",
            "reasons": ["missing:preset_threshold"],
            "metrics": {"entry_spread_usd_bbl": "1.30", "short_spread_pnl_usd_bbl": "0.40"},
        })
        self.assertEqual(replay(oil, input_changes={"preset_threshold": "1.20"})["decision"],
                         "stage_paper")
        self.assertEqual(replay(oil, check_changes={"same_day_settlements": None}), {
            "decision": "pause", "reasons": ["same_day_settlements"], "metrics": {},
        })

    def test_evaluator_rejects_unknown_operations_and_nonfinite_values(self):
        with self.assertRaises(ValueError):
            expression(["arbitrary", "1", "2"], {})
        with self.assertRaises(ValueError):
            expression(["mul", "$price", "2"], {"price": Decimal("NaN")})
