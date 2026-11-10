# LLM Agent 动态计划更新失误研究

**关于计划保留、环境事实更新与动态重规划失误的实证研究。**

[English](README.md) · [唯一研究主线](research/plan_commitment_pilot/RESEARCH_MAINLINE.md) · [最新四条件机制研究](experiments/paired_50/native_execution/MECHANISM_STUDY_FINAL_REPORT.md) · [实验索引](experiments/README.md) · [论文工作区](paper/README.md) · [相关论文](docs/RELATED_WORK.md) · [复现说明](docs/REPRODUCIBILITY.md) · [算法来源](docs/ALGORITHM_PROVENANCE_AND_CLEANUP.md)

> **核心问题：** LLM Agent 已经形成计划并开始执行后，为什么面对新的环境事实，有时仍然不能正确更新计划？如何使它根据当前证据正确决定 RETAIN、REPAIR 或 SWITCH？

## 项目概况

本项目研究 LLM Agent 面对环境事实变化时，能否更新原计划，并将决策落实到后续工具行动。

| 证据包 | 结果 | 测量内容 |
|---|---:|---|
| [四条件计划提示机制研究](experiments/paired_50/native_execution/MECHANISM_STUDY_FINAL_REPORT.md) | **复用 8 个基础任务，128 次首动作实验；2 个任务 16 条完整续跑** | 控制计划呈现和当前事实提示，分析 RETAIN/SWITCH 权衡 |
| [统一 RETAIN/SWITCH 配对研究](experiments/paired_50/README.md) | **50 个独立基础任务、100 个配对条件** | 结构化决策与真实工具首步行动 |
| [官方 CostBench 原生执行审计](experiments/native_80/README.md) | 80 个任务；静态 70/80，动态 60/80，其中 1 个任务与 50 任务研究重合 | 静态与动态环境下的最终答案鲁棒性 |
| [原生计划承诺与证据门控研究](research/costbench_method_studies/plan_commitment_evidence_gate/README.md) | 80 个候选中的 67 个事件检查点；解析出 27 份真实前瞻计划 | Agent 自主计划提取与证据门控续执行 |
| [机制诊断](experiments/mechanism_diagnosis/README.md) | 重用开发任务与真实执行轨迹 | 新事实观察、旧证据失效、决策和动作之间的失配 |
| [干预可行性](experiments/interventions/README.md) | EDR 与 Action Guard 原型 | 探索性方法比较；尚未证明优于简单事实更新提示 |

当前配对研究的正式数据集统一为 **50 个不同的 CostBench 基础任务和 100 个匹配条件**，其中 RETAIN 和 SWITCH 各 50 个。五个 CostBench 类别各有 10 个任务。历史构造材料统一保存在数据集的 provenance 目录中；当前研究通过一个统一注册表和构建脚本访问，不再要求读者分别理解历史批次。

结构化决策实验中，DeepSeek Flash 的 RETAIN 准确率为 48/50，SWITCH 准确率为 3/50，配对准确率为 1/50。原生工具执行实验中，首个动作的 RETAIN 准确率为 48/50，SWITCH 准确率为 2/50；100 条轨迹均到达目标状态。两种实验测量的结果不同，因此分别报告。

官方 80 任务原生审计中，13 个任务从静态正确变为动态错误，另有 3 个反向变化。这反映最终答案鲁棒性，不代表已经确定每个失败的具体原因。

## 研究问题

环境更新后，Agent 可能 RETAIN（原计划仍有效）、REPAIR（修改受影响的步骤或依赖）或 SWITCH（原计划不再适用）。我们重点分析五类可观察失误：未观察到新事实、未使依赖旧事实的证据失效、未正确评估替代方案、决策与现有证据不一致，以及后续工具执行或恢复失败。

**研究重点是环境变化后的正确计划更新、状态对齐和动作恢复。** CostBench 提供了可复现的受控工具环境。

## 建议阅读顺序

1. 阅读[最新四条件机制研究](experiments/paired_50/native_execution/MECHANISM_STUDY_FINAL_REPORT.md)。
2. 阅读[研究主线](research/plan_commitment_pilot/RESEARCH_MAINLINE.md)。
3. 阅读[实验索引](experiments/README.md)，首先查看[统一 50 任务配对研究](experiments/paired_50/README.md)。
4. 查看[相关论文](docs/RELATED_WORK.md)和[论文结构](paper/README.md)。
5. 检查[复现说明](docs/REPRODUCIBILITY.md)、[局限](docs/LIMITATIONS.md)和[主张—证据矩阵](docs/CLAIM_EVIDENCE_MATRIX.md)。

## 仓库组织

当前仓库围绕少量 CostBench 证据包组织：

- `experiments/paired_50/`：主要的 50 个独立任务配对基准。
- `experiments/native_80/`：官方 80 任务原生鲁棒性审计。
- `experiments/mechanism_diagnosis/` 与 `experiments/interventions/`：机制诊断和干预可行性证据。
- `research/`：计划承诺审计、补充原生证据和研究分析。
- `docs/` 与 `paper/`：实验协议、研究主张、局限和论文结构。
- `scripts/` 与 `.github/workflows/`：当前验证和复现工具。

重建 50 任务基准所需的原始任务输入与模型响应保存在 provenance 目录。当前仓库以统一基准及其补充 CostBench 证据包为主要阅读入口。
