# 实验设计

[研究协议](STUDY_PROTOCOL_zh.md)是当前实验操作定义的唯一依据。本页概述正式设计并指向冻结证据。

## 主要配对基准

[统一 RETAIN/SWITCH 决策与原生执行研究](../experiments/paired_50/README.md)包含 50 个独立 CostBench 基础任务。每个任务在同一个 checkpoint 上构造 RETAIN 和 SWITCH 两个匹配条件，共 100 条条件记录，五个 CostBench 类别各 10 个任务。

同一批基础任务采用两种评测协议：
- 结构化决策：模型显式输出 RETAIN/SWITCH 标签。
- 原生工具执行：将第一个实际执行的工具与 incumbent suffix 的首个工具比较。

两种协议测量不同结果，因此分别报告。

## 补充证据

- 官方原生动态鲁棒性审计包含 80 个任务，比较静态与动态条件下的最终答案；其中 1 个任务与 50 任务配对研究重合。
- 计划承诺与证据门控审计包含 80 个候选中的 67 个可回放事件检查点。
- 机制诊断与干预可行性研究复用开发任务，属于探索性证据。

这些证据包具有不同统计单位，不能与 50 任务配对基准相加。

## 证据入口

- [统一 50 任务基准](../experiments/paired_50/README.md)：正式注册表、冻结请求、结构化评分和原生执行。
- [实验索引](../experiments/README.md)：当前研究证据包。
- [结果摘要](RESULTS_SUMMARY.md)：当前主要结果。
- [主张—证据矩阵](CLAIM_EVIDENCE_MATRIX.md)：研究主张与来源映射。
- [复现说明](REPRODUCIBILITY.md)：离线验证和外部依赖。
- [研究局限](LIMITATIONS.md)：结果解释边界。
