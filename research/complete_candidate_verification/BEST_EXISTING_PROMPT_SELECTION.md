# Best Existing Prompt Baseline Selection

**Selected arm: A_original from the frozen four-arm plan-cue screen.**

## Selection rule

Method 3 in the seven-arm independent validation is the best previously evaluated non-oracle prompt. It is selected by historical first-action balanced accuracy, with ties resolved by the simpler prompt and fewer added instructions.

The archived four-arm screen reported:

| Prompt arm | RETAIN optimal first action | SWITCH optimal first action | Balanced accuracy |
|---|---:|---:|---:|
| A_original | 16/16 (100%) | 2/16 (12.5%) | **56.25%** |
| B_localized_current_fact | 16/16 (100%) | 2/16 (12.5%) | **56.25%** |
| C_plan_omitted | 8/16 (50%) | 8/16 (50%) | 50.00% |
| D_plan_omitted_localized_fact | 6/16 (37.5%) | 9/16 (56.25%) | 46.875% |

A and B tie on balanced accuracy and both class-conditional results. The B reminder did not improve either class, so A is selected as the less modified prompt. This is a prompt baseline, not a successful replanning algorithm: its historical SWITCH accuracy was only 12.5%.

The oracle-assisted candidate-menu diagnostic is excluded from this selection because its prompt receives an externally supplied menu containing solver-optimal candidate names; it is not a prompt-only baseline with the same information access.

## Frozen prompt definition

- Arm identifier: A_original.
- Incumbent plan: visible.
- Current native tool interfaces and current values: visible.
- Additional localized changed-tool reminder: absent.
- Plan-omission instruction: absent.
- Model: DeepSeek Flash.
- Temperature: 0.
- Thinking: disabled.
- Source builder: run_four_arm_experiment.py, using build_user_messages from four_arm_prompt_audit.py and make_official_system_prompt from run_official_harness.py.
- Source code commit: ae67a858a58e951e9ff9ac6fb49f404ccaf81892.
- Source workflow: [GitHub Actions run 42665117176](https://github.com/Droring/dynamic-plan-updating-in-llm-agents/actions/runs/42665117176).
- Source artifact: four-arm-deepseek-formal, artifact ID 13697210404.
- Archived ZIP SHA-256: 2ae46a0a61cd64db8dea765b79bb8eabef7e3bab9c4872fc4c9ed24d48444cf4.
- Archived requests.jsonl SHA-256: b4805637a362cad06423ac0b714a2c83acb3cf07177bf4e5093dc18221164e8f.

The SHA-256 hashes below identify the exact category-specific system prompt content in the archived A_original requests. The task-specific user messages and tool schemas vary with the frozen checkpoint and will be serialized and hashed per trial in the independent run.

| CostBench category | A_original system-prompt SHA-256 |
|---|---|
| Accommodation | b1c19635d13ee88d71f5666b79e5844cdd9d1c2695f8fbf6a3c33cba143d125f |
| Attraction | 090657e0e9ef44f857a0b5e889e536f83f04dc971ed235e82fc9739293c3e20b |
| Dining | d964f184113c1683ae2fab03ff4b6d0c58baa647f632f822d760d5cbca0a5397 |
| Shopping | 07bfd926a44cf2ef6ab6db7ec5048938d7b030d4206a3714a45f924055d7d4cd |
| Transportation | 8999b365c0a1e63891383ba33f466499179470eff03983b6442fd6fb2894330d |

## Use in the independent study

Method 3 is now frozen as A_original. It is evaluated on the same 20 new base tasks and paired RETAIN/SWITCH conditions as the other six methods. The prompt does not receive condition labels, oracle paths, oracle values, or solver outputs. It receives only the task/checkpoint data and current native tool interfaces defined by the common protocol.

This selection used archived development evidence only. No new provider request was made. The total token ceiling and maximum output-token settings for the 280-trajectory study remain to be set before any paid execution.
