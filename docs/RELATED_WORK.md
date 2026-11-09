# Related Work: Empirical Diagnosis of LLM Agent Planning and Recovery

This reading list is selected for **research methodology and problem proximity**, not to imply that the present pilot has the same scale or contribution strength. Conference labels below identify the venue; formal CCF classifications can vary by discipline and edition, so venue prestige should not be substituted for a verified CCF-list entry.

## Closest conceptual neighbors

### 1. Hell or High Water: Evaluating Agentic Recovery from External Failures
- Andrew Wang, Sophia Hager, Adi Asija, Daniel Khashabi, Nicholas Andrews.
- COLM 2025.
- [Paper](https://proceedings.colm.cc/paper_files/paper/2025/hash/80e77d9ed2f74dcaf1a42cb1a2593559-Abstract-Conference.html)
- **Question:** When external failures invalidate part of a tool workflow, can an agent find and execute a backup plan?
- **Finding:** Agents can identify appropriate functions but often fail to adapt to environmental feedback and pursue alternatives.
- **Why it matters here:** This is the closest neighbor to our question about failure to revise an ongoing plan after an environment update.
- **Difference:** Their central intervention is external function unavailability and backup-plan recovery. Our focus is the distinction between justified RETAIN, partial REPAIR and necessary SWITCH after new facts, especially when the Agent has already authored and partly executed a plan. COLM is a relevant specialist venue; do not describe it as CCF-A without checking the applicable list.

### 2. Why Do Multi-Agent LLM Systems Fail?
- Mert Cemri et al.
- NeurIPS 2025, Datasets and Benchmarks Track.
- [Paper](https://proceedings.neurips.cc/paper_files/paper/2025/hash/b1041e52d3be19f0a9bc491657488e4a-Abstract-Datasets_and_Benchmarks_Track.html)
- **Question:** What recurring failure modes explain why multi-agent systems do not deliver expected performance?
- **Method:** Annotates 1,600+ traces from seven frameworks; develops a taxonomy of 14 failure modes from expert trace analysis.
- **Why it matters here:** Strong precedent for making systematic failure discovery and a grounded taxonomy a central research contribution, rather than assuming an algorithm must be the paper's first contribution.
- **Difference:** Their unit is multi-agent system failure; ours is single-agent temporal plan revision and fact-to-action consistency.

### 3. Which Agent Causes Task Failures and When? On Automated Failure Attribution of LLM Multi-Agent Systems
- Shaokun Zhang et al.
- ICML 2025, PMLR 267.
- [Paper](https://proceedings.mlr.press/v267/zhang25cq.html)
- **Question:** Which component/agent and which decisive step caused a system failure?
- **Method:** Who&When contains failure logs from 127 multi-agent systems with fine-grained decisive-step annotations.
- **Why it matters here:** Supports step-level attribution and separating an observed end failure from its root cause.
- **Difference:** Our attribution target is within one agent trajectory: observation, stale dependent evidence, candidate evaluation, decision, and tool execution.

### 4. Why Do LLM-based Web Agents Fail? A Hierarchical Planning Perspective
- Mohamed Aghzal, Gregory J. Stein, Ziyu Yao.
- ACL 2026, Long Papers.
- [Paper](https://aclanthology.org/2026.acl-long.1483/)
- **Question:** At which level do web agents fail: high-level planning, low-level execution, or replanning?
- **Method:** Hierarchical process analysis; compares structured PDDL plans with natural-language plans.
- **Why it matters here:** Directly motivates evaluating the planning, execution and replanning stages separately rather than relying only on end-to-end success.
- **Difference:** Their analysis is hierarchical web-agent performance; ours isolates temporal fact changes and whether a previously selected plan should remain valid.

## Strong empirical evaluation precedents

### 5. AgentBench: Evaluating LLMs as Agents
- Xiao Liu et al.
- ICLR 2024.
- [Paper](https://proceedings.iclr.cc/paper_files/paper/2024/hash/e9df36b21ff4ee211a8b71ee8b7e9f57-Abstract-Conference.html) · [Code](https://github.com/THUDM/AgentBench)
- **Contribution:** Multi-environment agent benchmark and analysis of long-horizon reasoning, decision-making and instruction-following failures.
- **Lesson:** Use diverse executable environments and diagnose why agents fail, not just rank models.

### 6. AgentBoard: An Analytical Evaluation Board of Multi-turn LLM Agents
- Chang Ma et al.
- NeurIPS 2024, Datasets and Benchmarks Track.
- [Paper](https://proceedings.neurips.cc/paper_files/paper/2024/hash/877b40688e330a0e2a3fc24084208dfa-Abstract-Datasets_and_Benchmarks_Track.html)
- **Contribution:** Fine-grained progress metrics and analytical evaluation beyond final success.
- **Lesson:** Our reporting should expose where the plan-update process breaks, not only whether the final task succeeded.

### 7. WebArena: A Realistic Web Environment for Building Autonomous Agents
- Shuyan Zhou et al.
- ICLR 2024.
- [Paper](https://arxiv.org/abs/2307.13854) · [Canonical code](https://github.com/web-arena-x/webarena)
- **Contribution:** Reproducible, self-hostable long-horizon web tasks across functional websites.
- **Lesson:** A credible live-agent study needs an executable environment, stateful tasks and verifiable outcomes.
- **Potential use:** A future external-validity environment if CostBench cannot support semantic updates to user goals and same-state matched continuations.

### 8. TravelPlanner: A Benchmark for Real-World Planning with Language Agents
- Jian Xie et al.
- ICML 2024, PMLR 235.
- [Paper](https://proceedings.mlr.press/v235/xie24j.html)
- **Contribution:** Large, curated real-world planning benchmark and analysis of tool use, constraint tracking and task adherence.
- **Lesson:** Task-level ground truth and multi-constraint verification matter. This is useful context for retaining CostBench as a planning benchmark while not overclaiming its original evaluator as a new-preference verifier.

## The foundational benchmark we build on

### 9. CostBench: Evaluating Multi-Turn Cost-Optimal Planning and Adaptation in Dynamic Environments for LLM Tool-Use Agents
- Jiayu Liu et al.
- ACL 2026, Long Papers.
- [Paper](https://aclanthology.org/2026.acl-long.584/)
- **Contribution:** Travel-domain tool-use benchmark with atomic/composite tools and dynamic events.
- **Our relationship:** We reuse the official native Agent environment and historical task traces as an experimental substrate. Our research question is narrower and different: plan retention/update behavior and the propagation of new facts into subsequent decisions and actions, rather than cost-optimality as the outcome objective.
- **Important limitation:** A cost-change event does not automatically constitute a semantic change to the user's goal. A new evaluator or explicit task-state semantics are needed for a valid RETAIN/SWITCH counterfactual.

## Further diagnostic-method references

### 10. ProbeLLM: Automating Principled Diagnosis of LLM Failures
- Yue Huang et al.
- ICML 2026, PMLR 306.
- [Paper](https://proceedings.mlr.press/v306/huang26r.html)
- **Contribution:** Budgeted probing that discovers structured failure modes rather than isolated examples.
- **Lesson:** Separate exploration of new failure regions from controlled refinement and require verifiable test cases.

### 11. Causal Decomposition of LLM Agent Failure via Oracle-State Intervention
- Leqi Jia et al.
- REALM 2026.
- [Paper](https://aclanthology.org/2026.realm-1.6/)
- **Contribution:** Intervenes on agent state to test whether context replacement recovers failed trajectories.
- **Lesson:** Mechanism claims need interventions that isolate a proposed cause; correlations in traces alone are not causal proof.

### 12. TraceProbe: An Execution-Based Benchmark for Diagnosing Safety Failures in LLM Agents
- Yuxiang He et al.
- EMNLP 2026.
- [Paper](https://aclanthology.org/2026.emnlp-main.1233/)
- **Contribution:** Executable scenarios, normalized traces and step-level failure localization.
- **Lesson:** Use execution evidence and replay to localize failures, rather than rely solely on retrospective natural-language explanations.

## What is the gap we can responsibly claim?

These papers show that **empirical diagnosis of agent failure is a legitimate and established research pattern**. Several already study adaptation to external failures, process-level planning/replanning, and trace-based root-cause attribution. Therefore, we must not claim that "LLM agents fail to adapt to environment changes" is itself novel.

A narrower, potentially meaningful question remains:

> **After an LLM Agent has authored and begun executing a plan, how do newly observed facts propagate through the plan's dependent assumptions and intermediate evidence, and under what conditions does the Agent incorrectly retain, repair, or replace that plan?**

The project must demonstrate what is distinct through controlled same-state semantic update pairs, genuine Agent-authored plans, step-level action labels, and independent verification. The distinction from backup-plan benchmarks is the explicit protection of both correct RETAIN and necessary SWITCH, plus the focus on stale plan dependencies and fact-to-action propagation.

## Recommended paper-reading order

1. Hell or High Water — closest environment-feedback and backup-plan failure.
2. MAST / Why Do Multi-Agent LLM Systems Fail? — empirical taxonomy and trace analysis methodology.
3. Who&When — root-cause attribution at decisive steps.
4. Why Do LLM-based Web Agents Fail? — separates planning, execution and replanning.
5. AgentBoard — process-level evaluation beyond end success.
6. CostBench — exact benchmark assumptions and limits.
7. ProbeLLM and Oracle-State Intervention — principled probing and causal diagnosis.

