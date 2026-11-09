# 研究协议：统一 50 任务 RETAIN/SWITCH 基准

## 研究问题

在 CostBench 的受控检查点上，环境事实发生变化后，Agent 能否保留仍然有效的后续计划，或切换到当前更合适的可行方案？

## 数据集与统计单位

当前正式基准包含 **50 个独立 CostBench 基础任务**。每个任务从同一个冻结 checkpoint 构造一组 RETAIN 和 SWITCH 匹配条件，共 100 条条件记录。五个任务类别各包含 10 个任务。

独立统计单位是基础任务，而不是单条条件、模型请求、工具调用或执行轨迹。

## 配对条件构造

- RETAIN：环境更新后，原后续计划仍然最优。
- SWITCH：环境更新后，存在严格更优且可行的后续计划。
- 两个条件共享同一个 checkpoint，只改变受控的环境更新。
- 标签由固定版本的 CostBench 求解器和独立图搜索计算交叉检查。
- 冻结输入及哈希保存在 `experiments/paired_50/generated/`。

## 两种评测协议

### 结构化决策评测

DeepSeek Flash 接收冻结的结构化请求并输出 RETAIN 或 SWITCH。结果为：RETAIN 正确 48/50，SWITCH 正确 3/50，完整配对正确 1/50。

### 原生工具执行评测

同一批 50 个基础任务通过固定版本的 CostBench 原生 harness 执行。将第一个实际执行的工具与 incumbent suffix 的首个工具比较。结果为：RETAIN 首步正确 48/50，SWITCH 首步正确 2/50，完整配对正确 1/50；100 条轨迹均到达目标状态。

两种协议测量不同结果，必须分别报告。

## 环境与复现

固定 CostBench 版本：`6424069f3f773ade076bcedbed302ed47cfb1837`。

离线验证命令：

```bash
python experiments/paired_50/build_unified_dataset.py --check
python -m unittest scripts.test_unified_paired_dataset scripts.test_source_fixture_integrity -v
```

原生执行协议和结果位于 `experiments/paired_50/native_execution/`。离线验证不调用付费模型 API。

## 结论边界

incumbent suffix 由求解器构造，并在受控 checkpoint 提供给模型。因此，本研究测量的是受控检查点下的决策和可观察行动，不等于验证 Agent 自主形成旧计划后的承诺效应。目标完成情况与首步行动是否正确适应环境变化应分别报告。

参见[统一 50 任务基准](../experiments/paired_50/README.md)、[复现说明](REPRODUCIBILITY.md)和[研究局限](LIMITATIONS.md)。
