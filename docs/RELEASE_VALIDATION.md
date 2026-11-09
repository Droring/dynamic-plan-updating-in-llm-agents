# Release Validation

The release branch is validated against the canonical unified 50-task benchmark.

## Required offline checks

```bash
python scripts/build_release_manifest.py --check
python scripts/check_release.py
python scripts/check_markdown_links.py
python experiments/paired_50/build_unified_dataset.py --check
python -m unittest discover -s scripts -v
python -m unittest discover -s experiments/paired_50/native_execution -p 'test_*.py' -v
```

The release workflow also checks the pinned CostBench integration suite when the upstream checkout is available.

## Data integrity

The canonical dataset has 50 unique base tasks, 100 matched conditions, ten tasks per category, frozen request hashes and one shared checkpoint per matched pair. Structured model results and native first-action results are separate evidence products.

## Release status rules

- A successful dataset-validation workflow establishes frozen dataset and offline protocol integrity.
- A successful Markdown check establishes local documentation links resolve.
- A successful release workflow establishes the checks actually executed by that workflow.
- A workflow that skips integration tests must not be described as having passed those integration tests.
- Live model/API execution is separate from offline release validation.

See the [unified benchmark](../experiments/paired_50/README.md), [reproducibility guide](REPRODUCIBILITY.md) and [claim-evidence matrix](CLAIM_EVIDENCE_MATRIX.md).
