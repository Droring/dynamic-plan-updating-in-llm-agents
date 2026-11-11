# Plan Handoff and State Tracking: Offline Prompt Preflight

## Status

**Passed offline; no model/provider calls.** The final common-prefix correction and prompt builder passed the pinned CostBench GitHub Actions run.

- [Validation run](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42981872586)
- Artifact: `common-action-restoration-preflight` (40 isolated native replays)
- Artifact: `plan-handoff-prompt-preflight` (80 frozen request payloads and summary)
- [Prompt builder](prepare_plan_handoff_experiment.py)
- [Four-arm restoration implementation](preflight_common_action_restoration.py)
- [Live full-trajectory runner](run_plan_handoff_experiment.py)

## Final task and request matrix

The first graph-planner-action design was reproducible, but four of its ten cells completed the goal in one composite action. Those cells could not support a post-action continuation comparison. The final design therefore chooses one **shared, feasible, nonterminal action per base task**, taken from a previously successful multi-step archived trajectory. The exact tool and argument string are reused in both RETAIN and SWITCH; each environment has its own native result, which is replayed identically across A/B/C/D.

| Base task | Shared nonterminal action | Source trajectory | RETAIN prefix loss | SWITCH prefix loss | Updated plan differs from remaining incumbent |
|---|---|---|---:|---:|---|
| Query00178 | `Search_Transportation_Candidates` | SWITCH / graph planner | 0.20 | 0.00 | Yes / Yes |
| Query00351 | `Accommodation_Refinement_Step1` | SWITCH / candidate gate | 0.00 | 1.30 | No / No |
| Query00549 | `Attraction_Search_to_Step1` | SWITCH / graph planner | 0.08 | 0.00 | Yes / Yes |
| Query00689 | `Search_Dining_Candidates` | SWITCH / graph planner | 0.19 | 0.00 | Yes / Yes |
| Query00851 | `Shopping_Search_to_Step1` | SWITCH / graph planner | 0.23 | 0.00 | Yes / Yes |

The fixed common action is not guaranteed to be optimal in both environment conditions. Its loss is a **controlled prefix effect**, held constant within A/B/C/D for each task/environment cell and reported separately. The total observed common-prefix loss across the ten cells is 2.00. The primary continuation regret starts **after** this common action; end-to-end regret, when the goal is reached, is common-prefix loss plus continuation regret.

The unrestricted graph planner's post-action continuation differs from the remaining incumbent suffix in 8/10 cells and is unchanged in 2/10. This gives the plan-handoff factor a real contrast while retaining two no-change cells where a handoff should not be mistaken for an instruction to switch.

## Restoration and prompt equivalence checks

| Check | Result |
|---|---:|
| Base tasks | 5 |
| Paired environment checkpoints | 10 |
| Independent A/B/C/D process restorations | 40 |
| Exact common arguments replayed | 40/40 |
| Exact source-environment archived result matches | 20/20 |
| Environment-specific native result matches across four arms | 40/40 |
| Post-action state hashes match within each four-arm cell | 10/10 |
| Identical common-history hash within each four-arm cell | 10/10 |
| Identical native tool-schema hash within each four-arm cell | 10/10 |
| Four distinct factorial prompt hashes per cell | 10/10 |

The full-trajectory archive did not retain the assistant's free-form text accompanying the first tool call. The continuation context therefore uses a normalized assistant tool-call message with `content: null` in every arm. The exact first-action arguments and native tool observation are retained. This is a documented normalization, not a byte-for-byte reconstruction of the historical assistant turn.

## Frozen 2×2 development screen

- **A:** original plan context; no separate state ledger.
- **B:** complete graph-planner continuation handed off as current; old plan explicitly superseded; no separate ledger.
- **C:** original plan context; explicit observed-state ledger.
- **D:** complete graph-planner handoff; explicit observed-state ledger.

The state ledger contains only checkpoint-visible types and exact native observations. The typed CostBench state is monotonic; the renderer does not infer invalidation from new type additions. Unobserved semantic facts remain unknown.

The prompt builder generated:

[
5\text{ tasks}\times2\text{ environments}\times4\text{ arms}\times2\text{ repetitions}=80\text{ trajectories}.
]

Frozen model configuration: `deepseek-flash`, temperature 0, thinking disabled, 2,048 maximum output tokens per call. The harness's summed request reservation is **2,317,696 reservation units** (mean 28,971.2 per trajectory start). These units are a conservative serialized-request reservation measure, **not actual tokenizer token counts**. Each trajectory may require multiple model calls after the common action.

## Interpretation boundary

These five base tasks have already been explored and are a development screen, not an unseen confirmation set. Repeated runs remain nested within the same five independent tasks. B/D use an externally computed graph-planner path and are privileged diagnostic interventions, not deployable LLM-only method results.

No DeepSeek call has been made in this stage. The live runner [`run_plan_handoff_experiment.py`](run_plan_handoff_experiment.py) replays the common action in each fresh branch, measures post-action Bellman loss and full continuation regret, and updates the ledger only in C/D. The manual workflow gate has a 3,443,584-token hard cap; it is separate from offline prompt preparation.


## Live-run isolation and dispatch gate

The offline runner validation also passed a second, in-process isolation check: each A/B/C/D branch receives a deep copy of the native tool registry and typed checkpoint state. **40/40 deep-copied native action replays** reproduced the frozen environment-specific observation and post-action state. The live runner creates a fresh copy for every one of the 80 trajectories, preventing mutable tool state from leaking between arms or repetitions.

The manual GitHub Actions input is `run_paid_plan_handoff`. The paid job repeats the independent-process restoration, prompt construction and deep-copy dry run before the first API call. It then runs the 80-trajectory continuation screen with a hard cap of **3,443,584 actual provider tokens** and uploads the raw per-trajectory records even if the run stops early. The 80 prompt starts may each require multiple continuation calls.

**No paid model call has been made.** The paid job is intentionally manual; offline validation and prompt generation do not start it automatically.
