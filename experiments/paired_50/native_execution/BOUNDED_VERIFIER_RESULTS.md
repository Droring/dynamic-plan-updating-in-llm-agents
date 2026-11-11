# Bounded Candidate-Path Evidence Gate: Development and Independent Confirmation

## Executive result

**A candidate-limited, bounded symbolic path verification gate improves RETAIN/SWITCH first-action balanced accuracy in two studied cohorts.** The gate preserves the old plan unless a no-plan LLM proposal has a verifiable, strictly better complete continuation within four native tool steps. The gate does **not** use native reference solver outputs or gold labels in its selection, but it does perform classical graph search on **the same fully visible type/dependency and tool-value information that the evaluation reference exploits**.

This is therefore **a strong planning-assisted baseline and a proof of concept for externally checkable evidence**, not yet a novel general-purpose LLM replanning algorithm or a benchmark result free of structural oracle-equivalence concerns.

## Reproducible evidence

### Development cohort: 8 reused tasks

- [GitHub Actions offline verifier run #42961219656](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42961219656)
- Original candidate source: [four-arm DeepSeek archive, run #42665117176](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176)
- 8 base tasks x 2 environments x 2 archived C repetitions = **32 candidate first-action decisions**. No new provider calls in this verifier test.
- Max 4 tool steps; strict certificate comparison, finite graph-expansion guard. Oracle solver called **only after action selection for scoring**.

| Method | RETAIN | SWITCH | Balanced accuracy |
|---|---:|---:|---:|
| Original A (visible incumbent) | 16/16 | 2/16 | **56.25%** |
| Plan-omitted C first action | 8/16 | 8/16 | **50%** |
| **No-plan C candidate + bounded verifier** | **16/16** | **8/16** | **75%** |

The verifier accepted 8 SWITCH proposals, including 2 actions that were not globally optimal despite improving the certified path comparison; it accepted **zero** RETAIN proposals. First-action optimality remains only 8/16 in SWITCH: neither a candidate proposal nor a certificate implies global optimality. Query00403 is SWITCH at the path level but its incumbent first action remains optimal; it is still reported as a first-action-optimal case.

### Independent confirmation relative to method development: 10 tasks

- [Frozen task manifest](BOUNDED_VERIFIER_CONFIRMATION_MANIFEST.json): lexicographically first two previously unused query IDs from each of five CostBench task categories, excluding the original 8 development tasks; frozen **before** new provider execution.
- [Successful GitHub Actions #42961827405](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42961827405)
- [Raw 20 new DeepSeek actions, native execution results, verification certificates and scoring](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42961827405/artifacts/13829102725), `bounded-verifier-confirmation` ID `13829102725`.
- **10 independent base tasks**, each with RETAIN and SWITCH conditions, one C-arm model action per condition: **20/20** valid native DeepSeek calls, **110,779** provider-reported tokens, zero invalid calls or API errors.
- Model: DeepSeek Flash, temperature 0, thinking disabled. Upstream CostBench commit `6424069f3f773ade076bcedbed302ed47cfb1837`.

| Rule on frozen 10-task subset | RETAIN correct | SWITCH correct | Balanced accuracy |
|---|---:|---:|---:|
| Incumbent-only (deterministic reference comparator, not a new LLM run) | 10/10 | 0/10 | **50%** |
| New no-plan C first action | 5/10 | 5/10 | **50%** |
| **No-plan C candidate + bounded verifier** | **10/10** | **5/10** | **75%** |

The verifier **rejected all RETAIN deviations** and accepted 6 SWITCH alternatives. Five accepted alternatives were globally optimal first actions; one was strictly better than the incumbent according to the bounded certificate but *not* the global optimum (Query00851 SWITCH). Thus the gate is **selective but not infallible**.

The remaining four SWITCH tasks stayed on suboptimal incumbent actions, typically because the candidate generator did not produce a suitable better first action or no strictly improved certificate was found. The candidate stage therefore remains a practical ceiling for this architecture.

## Algorithmic boundary and interpretation

The verifier `bounded_candidate_verifier.py` operates on current publicly exposed native tool objects: required input types, output types and tool values. It only searches from the **given proposed next action**, to depth 4, and compares a certified complete candidate continuation against the exact submitted incumbent suffix. It does **not** enumerate all first actions to select a new globally best one, nor consult `GroundtruthSolver` when choosing.

However, this environment is a deterministic, explicit tool-dependency graph, and bounded path search for candidate completions is structurally close to the native benchmark's shortest-path reference solver. The strong result **must not** be interpreted as independent evidence that a text-only Agent has acquired reliable general reasoning, or marketed as a novel LLM replanning advance based solely on these accuracy numbers. A fair paper should include exact graph search, bounded graph search, oracle candidate, no-plan, incumbent, and cheaper heuristic verification baselines, with equivalent information access explicitly identified.

The 10 confirmation tasks belong to the same 50-task benchmark, so although disjoint from method-design tasks, they are **not a new dataset or cross-benchmark generalization**. The sample remains small and task repeats are correlated.

## Next gate

The development and ten-task confirmation satisfy the frozen first-action pilot's improvement criterion. **GO to native full-continuation testing with the gate making actual next-tool selections**; freeze the policy and its depth limit. Test complete trajectories on untouched tasks and compare against simple classical planners and comparable model-call budgets. Do not expand to all remaining tasks or assert publication-level novelty until this test is completed.

The output is an *offline policy selection* over real previously executed C actions (and incumbents), not yet a new end-to-end native Agent trajectory incorporating the gated selection. End-to-end action validity and path quality remain untested for the combined policy.
