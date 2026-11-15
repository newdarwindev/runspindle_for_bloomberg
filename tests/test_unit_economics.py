import copy
import json
import unittest
from pathlib import Path

from scripts.unit_economics import evaluate, evaluate_option, sensitivity

ROOT = Path(__file__).resolve().parents[1]


class EconomicsTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads((ROOT / "economics/model.template.json").read_text())

    def test_unknowns_do_not_become_zero(self):
        result = evaluate(self.template)
        self.assertFalse(result["comparable"])
        self.assertIn("task_boundary", result["missing_context"])
        for option in result["options"].values():
            self.assertIsNone(option["total_cost"])
            self.assertIsNone(option["unit_cost"])
            self.assertTrue(option["missing_inputs"])
            self.assertEqual(option["sensitivity"], [])

    def test_full_cost_and_denominator(self):
        option = copy.deepcopy(self.template["options"]["runspindle"])
        option["attempts"] = 10
        option["accepted_authorized_completions"] = 5
        option["costs"] = {key: 0 for key in option["costs"]}
        option["costs"].update(setup_amortized=100, model=2, human_operation=3,
                               verification=1, recovery=4)
        result = evaluate_option(option)
        self.assertEqual(result["total_cost"], "200")
        self.assertEqual(result["unit_cost"], "40")
        self.assertEqual(len(sensitivity(option)), 5)
        option["accepted_authorized_completions"] = 0
        self.assertIsNone(evaluate_option(option)["unit_cost"])

    def test_invalid_outcomes_and_costs(self):
        option = self.template["options"]["runspindle"]
        option["attempts"] = 2
        option["accepted_authorized_completions"] = 3
        with self.assertRaisesRegex(ValueError, "exceeds"):
            evaluate_option(option)
        option["accepted_authorized_completions"] = 1
        option["costs"]["model"] = -1
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            evaluate_option(option)


if __name__ == "__main__":
    unittest.main()
