# Native Plan-Commitment and Evidence-Gate Study: Native Continuation Results

This is a **development-only official CostBench native execution audit** using
the 67 real cost-change checkpoints from the earlier sealed 80-task development set.
Actual pre-event DeepSeek assistant text is the only model-plan source.
No old-price planner-synthesized incumbent is labeled an LLM commitment.

## Results

- Model-written paths uniquely parsed and validated: **27/67**.
- Plan-status breakdown: {'NO_VALID_COMMITTED_PATH': 27, 'UNPARSEABLE_OR_AMBIGUOUS': 13, 'VALID_PRE_EVENT_COMMITMENT': 27}.
- Deterministic evidence-gate actions: {'NO_VERIFIABLE_PLAN_FULL_GRAPH_FALLBACK': 40, 'RETAIN_OBSERVED_LLM_PLAN': 22, 'SWITCH_FROM_OBSERVED_LLM_PLAN': 5}. These are symbolic policy outputs, not post-event model choices.
- Official native tool goal: **67/67**, run complete **67/67**, final answer accepted **61/67**.
- Same-checkpoint Full answer accepted: **61/67**, discordant success cases **0**.
- Public tool cost: gate **4082.50** vs exact Full **4081.37**; regret **1.13**.
- Graph expansions: gate **494** vs exact Full **494**.
- Event verification required **0 model calls** because all relevant
public tool prices and type dependencies are supplied in the official event.

## Interpretation

Plan memory coverage is a *high-precision parser feasibility result*, not
an accuracy or completeness guarantee for informal plans. The gate's
complete fallback remains in the denominator. Exact public graph checking
cannot be claimed to improve on Full Replan's optimal tool cost.
Historical prompt-only model continuations are a different inference
configuration and must not be pooled with this symbolic run as if
they were newly randomized independent model trials.

## Per-category plan memory coverage

| Category | Unique verified commitment | Total checkpoints |
|---|---:|---:|
| accommodation | 3 | 11 |
| attraction | 4 | 10 |
| dining | 7 | 11 |
| shopping | 3 | 11 |
| transportation | 10 | 24 |

Full records are in [NATIVE_AUDIT.json](evidence/NATIVE_AUDIT.json).


## Original Agent behavior in the raw official dynamic runs

This is a separate action-level extraction from the original 80-task official CostBench dynamic-run JSON. It is not the deterministic evidence-gate continuation reported above.

- The pre-event executed prefix matches the Agent-authored plan in **27/27** recoverable-plan cases.
- The original model's first post-event tool action follows its own incumbent suffix in **27/27** cases.
- The first post-event action matches the current graph-optimal first action in **15/27** cases; it differs in **12/27**.
- The complete post-event tool sequence exactly matches the incumbent suffix in **23/27** cases and the current optimal suffix in **15/27**.
- In the five cases where the deterministic gate selects SWITCH, the original model still follows the incumbent on its first post-event action in **5/5** cases; **0/5** match the current optimal first action.
- All 27 original trajectories reach the goal; 24/27 official final answers are accepted.

The gate's 22 RETAIN / 5 SWITCH counts remain deterministic policy outputs. The 27/27 first-action result above is extracted independently from the original model's archived conversation history.

Reproduction: [audit script](audit_original_agent_retention.py), [JSON audit](evidence/ORIGINAL_AGENT_RETENTION_AUDIT.json), and [per-task CSV](evidence/ORIGINAL_AGENT_RETENTION_AUDIT.csv).
