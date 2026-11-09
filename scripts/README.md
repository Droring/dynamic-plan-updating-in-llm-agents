# Reproduction and validation scripts

The scripts directory contains only repository-wide checks and validators for evidence packages that remain part of the current study.

| Script | Purpose |
|---|---|
| `build_release_manifest.py` | Rebuild/check the SHA-256 release manifest |
| `check_release.py` | Verify tracked-file integrity |
| `check_markdown_links.py` | Check local Markdown links |
| `check_stale_research_paths.py` | Reject references to retired experiment paths |
| `audit_directory_migration.py` | Verify the canonical 50-task layout |
| `test_unified_paired_dataset.py` | Validate the 50-task registry, matched requests and saved scores |
| `test_source_fixture_integrity.py` | Verify the merged source archive and five-task extension |
| `test_official_native_baseline.py` | Reproduce the official 80-task native audit |
| `test_plan_commitment_memory.py` | Test prospective plan extraction and evidence-gate primitives |
| `test_task_registry_integrity.py`, `test_task_registry_screening.py`, `test_cohort_split_integrity.py` | Verify the frozen candidate source registry and official native run allocation |

Run the full offline suite from the repository root with Python 3.12:

```bash
python -m unittest discover -s scripts -v
```

The suite makes no model API calls. Native CostBench integration tests require the pinned upstream checkout documented in [Reproducibility](../docs/REPRODUCIBILITY.md).
