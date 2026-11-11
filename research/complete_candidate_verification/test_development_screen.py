from __future__ import annotations

import json
import unittest

from .prepare_development_screen import MANIFEST_PATH
from .run_development_screen import build_schedule


class DevelopmentScreenScheduleTests(unittest.TestCase):
    def test_all_frozen_cells_are_unique_and_balanced(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        schedule = build_schedule(manifest)
        self.assertEqual(len(schedule), 32)
        self.assertEqual(len({(x["query_id"], x["condition"], x["method"]) for x in schedule}), 32)
        self.assertEqual(sum(x["condition"] == "RETAIN" for x in schedule), 16)
        self.assertEqual(sum(x["condition"] == "SWITCH" for x in schedule), 16)
        for method in ("repair_plus_fresh", "fresh_plus_fresh"):
            self.assertEqual(sum(x["method"] == method for x in schedule), 16)
        for task in manifest["selection"]["tasks"]:
            rows = [x for x in schedule if x["query_id"] == task["query_id"]]
            self.assertEqual(len(rows), 4)
            self.assertEqual({x["condition"] for x in rows}, {"RETAIN", "SWITCH"})
            self.assertEqual({x["method"] for x in rows}, {"repair_plus_fresh", "fresh_plus_fresh"})

    def test_first_condition_method_order_is_counterbalanced(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        rows = [x for x in build_schedule(manifest) if x["condition_order_index"] == 0]
        self.assertEqual(len(rows), 16)
        self.assertEqual(sum(x["method_order_index"] == 0 for x in rows), 8)
        self.assertEqual(sum(x["method_order_index"] == 1 for x in rows), 8)


if __name__ == "__main__":
    unittest.main()
