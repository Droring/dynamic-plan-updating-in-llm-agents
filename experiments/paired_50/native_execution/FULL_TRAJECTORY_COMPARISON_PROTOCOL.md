# Full native continuation and information-matched baseline comparison

## Research question

Does the observed first-action balanced-accuracy gain of the bounded candidate verifier translate into actual goal-reaching native CostBench trajectories, and is there any benefit beyond classical graph planning when both receive the exact same tool dependencies and current values?

Prior independent confirmation used 10 tasks and 20 first-action model requests; the bounded gate scored RETAIN 10/10, SWITCH 5/10 (75% balanced accuracy). An unrestricted information-matched Dijkstra-style graph planner on all 20 checkpoints found a suitable incumbent continuation in RETAIN 10/10 and an improving continuation in SWITCH 10/10. Those graph paths had not yet been executed by the native tool APIs.

## Fixed full-trajectory cohort

Take **one task in each CostBench category**, in the lexicographically earliest order from the prior 10-task confirmation manifest: `Query00178` (transportation), `Query00351` (accommodation), `Query00549` (attraction), `Query00689` (dining), `Query00851` (shopping). These five tasks are disjoint from the original 8-task mechanism development cohort. They were, however, previously used in first-action independent confirmation, so this is a **follow-up trajectory pilot, not a fresh held-out study**.

Each of 5 tasks has paired RETAIN and SWITCH checkpoints, and three evaluation policies:

- **Incumbent:** pick the old first tool and allow the LLM to continue natively.
- **Candidate gate:** reuse the previously frozen, genuinely executed plan-omitted DeepSeek first-action proposal; apply exactly the same four-step evidence verifier to choose the incumbent or proposal, then allow the LLM to continue.
- **Unrestricted graph planner:** choose the first action of a non-oracle-API Dijkstra search over all currently visible type-feasible tools, then allow the same LLM to continue.

Total: **5 x 2 x 3 = 30 complete-trajectory attempts**. All methods have identical initial checkpoint, original plan-visible task text and current native tools. To make first-action selection a controlled policy comparison, all three methods restrict their *first* function-tool interface to their policy's chosen tool; DeepSeek supplies its valid arguments. For **all subsequent calls**, DeepSeek sees the full native tool set, without any further action restriction. This does not reuse an archived first action's arguments or tool result; each path is freshly executed.

## Primary outcome

Report goal reach, actual first and complete tool paths, native tool errors, number of model calls and tokens, and full-path regret against independently computed minimum path value. A policy with an optimal first action but a poor later trajectory has **not** solved adaptive replanning. All three policy branches must be reported on each checkpoint. Model inputs never receive oracle labels, reference values or recommended *future* actions.

## Important limits

The path-verification method and the Dijkstra comparator share the same complete visible tool dependency graph and values; this is an **information-matched classical baseline**. Any gains over simple old-plan following must be interpreted in that context. The unrestricted planner is structurally close to CostBench's own shortest-path ground truth, making claims of novelty from this graph representation especially weak.

The first tool is forced identically for all methods. The comparison therefore tests **conditional execution after policy selection**, rather than natural unprompted first-action choice. All paths are complete native executions but this is not evidence of deployment-level generalization.

Live execution requires explicit approval, a secret API key and the GitHub Actions token cap. Offline preflight performs no provider calls.
