import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_bounded_verifier_confirmation import score


class BoundedVerifierConfirmationTests(unittest.TestCase):
    def test_scoring_rejects_incomplete_or_duplicated_response_records(self):
        with self.assertRaises(ValueError):
            score([], [])

    def test_scoring_keeps_original_trial_ids_stable(self):
        # A 20-record response set may not be silently treated as valid if it
        # does not match its frozen source query and checkpoint.
        p = {
            "incumbent_suffix": ["incumbent"],
            "checkpoint_sha256": "fixture",
        }
        t = [{
            "query_id": "q", "environment_condition": "RETAIN",
            "source_trial_id": "source", "trial_id": "trial",
            "prepared": p,
        }]
        rows = [
            {
                "trial_id": f"trial{i}", "source_trial_id": "source",
                "checkpoint_sha256": "fixture", "first_action_status": "executed",
                "first_action": "candidate",
            } for i in range(20)
        ]
        with self.assertRaises(ValueError):
            score(t, rows)


if __name__ == "__main__":
    unittest.main()
