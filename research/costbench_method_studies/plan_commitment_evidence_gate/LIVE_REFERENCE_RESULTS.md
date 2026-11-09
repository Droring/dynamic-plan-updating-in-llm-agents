# Archived Same-Checkpoint Continuation Comparison

This is a retrospective comparison on 15 development checkpoints, not a newly randomized experiment. Both arms use matching public tool-catalogue digests, native type-state hashes, and the same archived pre-event assistant and tool-response content.

| Measure | Plan-evidence gate | Archived native continuation |
|---|---:|---:|
| Official final answer accepted | 13/15 | 13/15 |
| Native goal reached | 15/15 | 15/15 |
| Prospective Agent-authored plan recovered | 6/15 | — |

For the six checkpoints with a recovered plan, the gate retained five and selected a different continuation in one. The other nine used an explicit fallback because no qualifying plan could be recovered.

This is descriptive retrospective evidence from a small development subset. It is not a fresh randomized comparison, a held-out generalization result, or evidence that the gate improves the official Agent. The original per-task matches and archived execution records are in [the audit data](evidence/LIVE_REFERENCE_AUDIT.json).
