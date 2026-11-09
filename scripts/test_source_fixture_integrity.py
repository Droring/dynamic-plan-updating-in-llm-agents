"""Verify the merged source archive and five new extension tasks."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "experiments" / "paired_50" / "provenance" / "source_records" / "source_archive"

def pairs(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    return value["pairs"] if isinstance(value, dict) else value

class SourceFixtureIntegrityTests(unittest.TestCase):
    def test_merged_archive_matches_preserved_raw_records(self):
        source = pairs(ARCHIVE / "source_pairs.json")
        raw_a = pairs(ARCHIVE / "raw_source_material_a" / "generated" / "pairs.json")
        raw_b = pairs(ARCHIVE / "raw_source_material_b" / "generated" / "pairs.json")
        self.assertEqual(source, raw_a + raw_b)
        self.assertEqual(len(source), 45)

    def test_merged_source_archive_and_extension_are_disjoint(self):
        source = pairs(ARCHIVE / "source_pairs.json")
        extension = pairs(ROOT / "experiments" / "paired_50" / "generated" / "pairs.json")
        self.assertEqual(len(source), 45)
        self.assertEqual(len(extension), 5)
        source_ids = {x["query_id"] for x in source}
        extension_ids = {x["query_id"] for x in extension}
        self.assertEqual(len(source_ids), 45)
        self.assertEqual(len(extension_ids), 5)
        self.assertTrue(source_ids.isdisjoint(extension_ids))
        self.assertEqual(len(source_ids | extension_ids), 50)

    def test_extension_fixture_is_balanced(self):
        extension = pairs(ROOT / "experiments" / "paired_50" / "generated" / "pairs.json")
        categories = {}
        for row in extension:
            categories[row["task"]] = categories.get(row["task"], 0) + 1
        self.assertEqual(categories, {
            "transportation": 1, "accommodation": 1, "attraction": 1,
            "dining": 1, "shopping": 1
        })

if __name__ == "__main__":
    unittest.main()
