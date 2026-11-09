# Study Scope and Limitations

This page distinguishes the independent units and claims of the project's active evidence packages.

## Unified paired RETAIN/SWITCH study

The canonical paired benchmark contains **50 independent CostBench base tasks**, with 100 matched condition records (50 RETAIN and 50 SWITCH). Each task contributes one matched pair from a shared frozen checkpoint. The five CostBench categories contain ten tasks each.

The structured decision protocol achieved 48/50 RETAIN accuracy, 3/50 SWITCH accuracy and 1/50 paired accuracy. The separate native execution protocol achieved 48/50 incumbent-following first actions in each condition; these are descriptive behavior counts; all 100 trajectories reached the goal.

These are distinct outcome measures. The native incumbent suffix is solver-derived and supplied at a controlled checkpoint. This benchmark therefore measures checkpoint decisions and observable execution relative to that incumbent, not autonomous plan authorship or a causal effect of self-commitment.

## Complementary studies and statistical units

- The official native dynamic-robustness audit contains 80 tasks and paired static/dynamic trajectories: 70/80 static accepted answers, 60/80 dynamic accepted answers, 13 correct-to-incorrect transitions and 3 incorrect-to-correct transitions. One task (`Query00499`) also appears in the 50-task paired benchmark, so these two evidence packages are not fully task-disjoint.
- The plan-commitment/evidence-gate audit contains 67 replay-matched event checkpoints from 80 candidates; 27 authentic prospective plans were parsed. Its unit and eligibility criteria differ from the paired benchmark.
- The four-task native fact-revision pilot contains repeated, correlated intervention arms and is exploratory development evidence.
- Mechanism diagnostics reuse development tasks and native traces; they are not an independent held-out prevalence estimate.
- EDR and Action Guard did not demonstrate an end-to-end advantage over the explicit fact-update baseline in the current four-task pilot.

Conditions, trajectories, policy arms, API calls, tool calls and workflow runs are not additional independent base tasks. Do not add sample counts across studies that reuse or select from the same underlying task pool. In particular, the 50-task paired study and 80-task native audit share `Query00499`.

## Objective and measurement

The paired benchmark labels are based on a simulated finite CostBench type-graph objective. The benchmark excludes business-level semantic validity, model planning time, verification effort and any general claim about real-world tool environments.

The archived native execution result does not yet establish path-level optimality. Incumbent first-action deviation is descriptive and may not be treated as a correct SWITCH without comparing the executed continuation value with the current-condition native optimum. It does not reveal hidden model reasoning. Reaching the final goal is reported separately and must not be used as a substitute for correct first-action adaptation.

## Reproducibility

The canonical dataset, frozen model requests, scoring output and native execution evidence are under [the unified 50-task study](../experiments/paired_50/README.md). The merged source archive and its raw provenance records remain under that package's provenance directory; they are not separate current studies.

Offline checks can verify committed inputs, hashes and deterministic outputs. Re-running the paid model evaluation requires provider access and incurs charges; it is not part of the offline test suite.

See the [experiment index](../experiments/README.md), [claim-evidence matrix](CLAIM_EVIDENCE_MATRIX.md), [reproducibility guide](REPRODUCIBILITY.md) and [research mainline](../research/plan_commitment_pilot/RESEARCH_MAINLINE.md).
