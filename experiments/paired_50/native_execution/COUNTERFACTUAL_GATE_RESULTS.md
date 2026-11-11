# Counterfactual Candidate Verification Gate — Results

## Decision: NO-GO for the LLM-only KEEP/ACCEPT verifier

The two-stage plan-preserving gate did **not** improve balanced first-action accuracy. The verifier kept the incumbent in **all 16** cases where a previously generated no-plan C-arm candidate differed from it, including all six cases where that alternative was solver-optimal.

This is a **controlled negative result** about a specific LLM-only verification design. It strengthens the observed failure mode: *independently generated better proposals are sometimes recognized as candidates yet rejected once the incumbent plan is reintroduced*, even in a dedicated text-only review step. It does not establish a unique private cognitive mechanism.

## Provenance

- [Completed GitHub Actions run #42960591870](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42960591870)
- [Archived gate messages, responses, summary and preflight](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42960591870/artifacts/13828474833) — `counterfactual-gate-results`, artifact ID `13828474833`
- Code: [`run_counterfactual_gate.py`](run_counterfactual_gate.py), protocol: [`COUNTERFACTUAL_GATE_PROTOCOL.md`](COUNTERFACTUAL_GATE_PROTOCOL.md)
- Original plan-omitted proposal source: [formal four-arm archived run #42665117176](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176).
- DeepSeek Flash, temperature 0, thinking disabled, native CostBench revision `6424069f3f773ade076bcedbed302ed47cfb1837`.
- 8 reused base tasks, 2 conditions, 2 repetitions each = 32 decisions. 16 archived C proposals differed from incumbent and required **16 new model calls**; 16 identical proposals were automatically kept without calls.
- 16/16 new verification requests succeeded, provider-reported usage **77,139 tokens**, cap 250,000.
- No oracle optimality labels or reference path values were passed into review prompts. The native solver scored selections after the LLM review.

## Results

| Condition | Different archived C proposals | Verifier ACCEPT | Verifier KEEP | Selected first action optimal |
|---|---:|---:|---:|---:|
| RETAIN | 8/16 | 0 | 16/16 | **16/16 (100%)** |
| SWITCH | 8/16 | 0 | 16/16 | **2/16 (12.5%)** |
| Overall | 16/32 | 0 | 32/32 | 18/32 (56.25%) |

Balanced accuracy = **(100% + 12.5%)/2 = 56.25%**, identical to the original A baseline.

**Important breakdown of the eight SWITCH proposals that differed from the incumbent:**
- **6/8** were actually oracle-optimal first-action proposals: Query00550, Query00685, Query00858, each with two archived C repeats. The review rejected **all 6/6**.
- **2/8** were not optimal: Query00706 with two repeats. The review also rejected both.
- The verifier therefore made **zero** true-positive SWITCH decisions and **zero** false-positive SWITCH decisions. Its high RETAIN accuracy is simply unconditional retention, not successful calibration.

The 2/16 SWITCH first-action correct scores are from **Query00403**, whose incumbent *first action* stays optimal despite the condition's path-level SWITCH label. They do **not** demonstrate successful plan replacement.

## Mechanism evidence in raw explanations

In the Query00550, Query00685 and Query00858 SWITCH reviews, the model often described the incumbent as an efficient or lower-cost route despite the separate native solver showing that the supplied alternative was the better first action. This is a **wrong comparative conclusion under current task evidence**, not merely an inability to name alternatives or to call executable tools. These are model-generated explanations; they are not reliable access to private model calculations.

Compared with the prior results:
1. The plan-omitted C arm could sometimes **generate** the optimal different first action.
2. When that action was paired with the incumbent and verified by a separate text-only DeepSeek session, the verifier consistently preferred the incumbent.
3. The single-pass plan-preserving comparison prompts and the separate plan-restoring verification prompt both failed to correct SWITCH.

## Research implication

Stop optimizing these incumbent-visible prompt instructions on the same eight cases. A next mechanism must include **independently checkable current-state evidence** for comparing feasible continuations; more generic comparison prompting, longer explanations and duplicated tool descriptions do not reliably produce such evidence. A symbolic tool-dependency/path verifier can be evaluated as a **strong classical planning baseline**, but using the *exact same minimum-path solver as the evaluation oracle* would be circular and must not be marketed as a novel LLM replanning advance.

The next design needs a transparent distinction between: (a) model generation of candidate paths, (b) independent verification of concrete claims under available facts, and (c) selectively authorizing a changed action. On untouched tasks, it must preserve high RETAIN accuracy while improving genuinely suboptimal SWITCH decisions and subsequently complete actual native execution.

**No validated balanced-accuracy improvement has been established by these experiments.**
