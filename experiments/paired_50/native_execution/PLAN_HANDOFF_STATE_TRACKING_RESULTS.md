# Plan Handoff × Observed-State 2×2: Native Continuation Results

## Result status

**Completed: 80/80 native continuation trajectories.** The five-task development screen ran in [GitHub Actions run 42997923650](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42997923650); its [archived artifact](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42997923650/artifacts/13844657416) contains requests, responses, call journal, ledger and preflight evidence.

- Independent base tasks: **5** — Query00178, Query00351, Query00549, Query00689, Query00851.
- Conditions: RETAIN and SWITCH; arms A/B/C/D; two repetitions.
- Total: **80 trajectories**, 120 model calls, 80/80 goals reached, zero unknown provider outcomes.
- Model: DeepSeek Flash, temperature 0, thinking disabled, 2,048 maximum output tokens.
- CostBench revision: `6424069f3f773ade076bcedbed302ed47cfb1837`.

The successful retry recorded 725,465 provider tokens. The earlier interrupted attempt has an unrecorded provider outcome and remains separately reserved in the recovery record; its usage is not added to the measured retry total.

## Design

The experiment starts after a shared, feasible, nonterminal native first action. Its exact arguments, environment-specific observation and resulting typed state are held constant across A/B/C/D within each task/environment cell. Each continuation starts from an independent restored native environment.

| Arm | Continuation plan | Separate observed-state ledger |
|---|---|---|
| A | Original incumbent remains in history; no replacement path | No |
| B | Complete updated graph-planner continuation is supplied as current; former plan superseded | No |
| C | Original incumbent remains in history; no replacement path | Yes |
| D | Complete updated graph-planner continuation is supplied as current; former plan superseded | Yes |

B/D are **planner-assisted diagnostic interventions**: an external graph planner supplies the full continuation. They do not measure an LLM-only planning method. The C/D ledger contains only checkpoint-visible types and exact native observations.

The shared prefix is not guaranteed to be optimal in both environments. Its loss is fixed within each A/B/C/D comparison. The primary endpoint is therefore post-prefix continuation quality, not end-to-end replanning from the original checkpoint.

## Results

Each arm/environment cell contains ten trajectories (five tasks × two repetitions).

| Environment | Arm | Optimal continuations | Goals reached | Mean continuation regret | Mean full-path regret |
|---|---|---:|---:|---:|---:|
| RETAIN | A | 5/10 | 10/10 | 0.080 | 0.220 |
| RETAIN | B | **10/10** | 10/10 | **0.000** | 0.140 |
| RETAIN | C | 6/10 | 10/10 | 0.064 | 0.204 |
| RETAIN | D | **10/10** | 10/10 | **0.000** | 0.140 |
| SWITCH | A | 6/10 | 10/10 | 0.660 | 0.920 |
| SWITCH | B | **10/10** | 10/10 | **0.000** | 0.260 |
| SWITCH | C | 6/10 | 10/10 | 0.660 | 0.920 |
| SWITCH | D | **10/10** | 10/10 | **0.000** | 0.260 |

The non-zero full-path regret in B/D is entirely the controlled common-prefix contribution. B/D have zero regret after the shared prefix in all 20 task/environment/repetition cells.

### Task-level paired comparisons

The two repetitions are averaged within each base task before classifying improvement.

| Environment | Contrast | Improved by right-hand arm | Worsened | Unchanged |
|---|---|---:|---:|---:|
| RETAIN | A → B | 3/5 | 0/5 | 2/5 |
| RETAIN | C → D | 2/5 | 0/5 | 3/5 |
| RETAIN | B → D | 0/5 | 0/5 | 5/5 |
| SWITCH | A → B | 2/5 | 0/5 | 3/5 |
| SWITCH | C → D | 2/5 | 0/5 | 3/5 |
| SWITCH | B → D | 0/5 | 0/5 | 5/5 |

B and D executed **identical continuation action sequences in all 20 matched task/repetition comparisons** (10 RETAIN and 10 SWITCH). The ledger-only contrast (A versus C) was inconsistent in RETAIN and unchanged in SWITCH.

## Execution checks and interpretation

- All 80 frozen request IDs completed exactly once; all 80 trajectories reached the goal.
- No provider outcome remained unknown.
- Step-level Bellman losses matched continuation regret; full-path regret equalled fixed-prefix loss plus continuation regret.
- Recorded trajectory elapsed time: **148.729 seconds total**, **1.859 seconds mean per trajectory**.
- The 40-branch common-action restoration and 80-request prompt preflight passed; see [offline preflight](PLAN_HANDOFF_PROMPT_PREFLIGHT_REPORT.md).

The result supports a narrow conclusion: **complete graph-planner handoff resolved the measured post-prefix continuation errors on these five development tasks; the extra state ledger did not improve the handed-off plan.** It does not show that DeepSeek independently generated the updated plan. The independent sample is five base tasks, not 80 trajectories; repetitions and conditions are nested and paired. The fixed-plan executor and per-step graph-replanner controls in the broader protocol were not run.

## Next diagnostic

The separate [checkpoint-level plan-status annotation protocol](PLAN_STATUS_CONFIRMATION_PROTOCOL.md) holds the complete planner continuation fixed and varies only whether the prior plan is UNSET or annotated VALID/STALE. Its ten-task cohort and 80-request matrix passed offline preflight in [run 43006621052](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/43006621052); the manifest is committed. The paid confirmation job was skipped, so this follow-up has not made provider calls.
