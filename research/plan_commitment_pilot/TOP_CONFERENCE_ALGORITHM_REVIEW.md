# Top-Conference Review: LLM-Agent Planning, Feedback, and Replanning

Status: literature and code audit; no new paid model calls; no algorithm result is claimed by this document.

Repository target: research/complete-candidate-verification  
Audited base commit: a81ec6b  
Scope: 30 peer-reviewed papers from NeurIPS, ICLR, ICML, ACL, EMNLP, AAAI, ICCV, and ICRA. One paper (LLM-A*) is an EMNLP Findings paper and is explicitly marked as such. Benchmark papers are included only where they directly expose planning, tool-dependency, execution-feedback, or replanning failure modes.

## 1. Executive decision

The three strongest implementation candidates for this CostBench question are:

1. **LLMFP (ICLR 2025)** — best overall fit for a low-resource, solver-backed checkpoint planner. The proposed single-module change is an incumbent-aware, checkpoint-conditioned Formulator.
2. **LATS (ICML 2024)** — strongest open-source general agent-search candidate. Its LM value function is a clear leverage point, but the method is expensive and relies on accurate state discrimination.
3. **AdaPlanner (NeurIPS 2023)** — closest feedback-triggered refinement architecture and has official code, but its original assertion/feedback trigger does not fire on the CostBench failure mode observed so far.

**Provisional mainline: LLMFP with an incumbent-aware checkpoint Formulator.** This is a literature-based candidate selection, not a GO decision. It must first beat the existing strongest simple baseline in a small native end-to-end test. If it does not, stop this line.

ToolChain* is highly relevant conceptually, but it is not shortlisted as an implementation candidate: the ICLR paper presents an A* search over tool-call trees, while the current CostBench environment already exposes a structured tool graph and has a strong native graph-planning reference. The paper does not provide a public official implementation in the paper materials inspected. Reimplementing it would risk duplicating the existing graph planner rather than testing a new LLM-agent contribution.

## 2. Thirty-paper comparative review

The compact entries below cover: problem; novelty and pipeline; module/data/model basis; strength; observed limitation; ablations/parameters; future direction; and relevance to CostBench. “Future direction” is described as author-stated where the paper explicitly discusses it; otherwise it is a limitation-derived research direction, not a quotation from the authors.

| # | Paper / venue | Problem, innovation, and pipeline | Evidence, limitations, ablations, parameters, future direction, and CostBench value |
|---|---|---|---|
| 1 | [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629), ICLR 2023 | Interleaves a reasoning trace with an external action and observation: Thought → Action → Observation → Thought. The central mechanism is the alternating control loop, not a separate planner. | The action observation grounds later reasoning and reduces purely internal hallucination. The paper compares reasoning-only, acting-only, and combined prompting. It does not maintain an explicit incumbent-plan value or a formal retain/switch decision. Future work naturally includes stronger long-horizon planning and more reliable action selection. CostBench value: the basic environment-feedback baseline, but insufficient for valid-yet-inferior plan detection. |
| 2 | [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366), NeurIPS 2023 | Runs a trajectory, evaluates the result, generates a verbal reflection, stores it in episodic memory, and retries with the reflection in context. It improves behavior without updating model weights. | Memory and reflection are the key modules; ablations compare memory/reflection variants and task settings. Its main dependency is informative feedback: if a plan completes successfully but is strategically inferior, the feedback may not identify the problem. Future work includes better reflection quality and transfer. CostBench value: useful for learning from explicit failures, but not a sufficient trigger for silent plan-quality drift. |
| 3 | [AdaPlanner: Adaptive Planning from Feedback with Language Models](https://arxiv.org/abs/2305.16653), NeurIPS 2023 | Generates a plan with assertions, executes it, compares predicted and observed feedback, performs in-plan or out-of-plan refinement, then resumes from a checkpoint. The pipeline is plan → assertions → execution feedback → refinement → resume. | Assertions and refinement are the leverage points. The method is strongest when execution feedback contradicts an expected assertion. It does not naturally detect an action sequence that remains executable but becomes inferior. We inspected the official [AdaPlanner repository](https://github.com/haotiansun14/AdaPlanner), including its ALFWorld execution loop: refinement is tied to assertion/feedback errors. CostBench transfer audit: 27/27 plans remained executable and no tool error occurred, so the original trigger was not activated. Future direction for this project: replace only the trigger with a decision-quality-aware trigger, but only if it beats the stronger prompt baseline. |
| 4 | [Describe, Explain, Plan and Select (DEPS)](https://arxiv.org/abs/2305.XXXX), NeurIPS 2023 | Uses environment description, explanation of failure/feedback, subgoal planning, and a selector that chooses among subgoals. It targets long-horizon open-world embodied tasks such as Minecraft. | The goal selector and feedback loop are important; experiments compare with prior embodied-agent planners and ablate planning/selection elements. The selector is domain- and capability-dependent, and its subgoal estimates are not a generic tool-path value function. Future work includes more capable open-world task planning. CostBench value: illustrates that subgoal ordering matters, but the domain-specific selector is not directly reusable. |
| 5 | [Reasoning with Language Model is Planning with World Model (RAP)](https://arxiv.org/abs/2305.14992), EMNLP 2023 | Uses the LLM both as a policy/agent and as a learned world model; MCTS performs selection, expansion, simulation, and backpropagation using predicted states and task rewards. | The world model and reward guide exploration; the paper reports gains over CoT and least-to-most baselines, including a 33% relative improvement in a plan-generation setting. Its weakness is that imagined state transitions and rewards can be wrong; search magnifies model errors and adds inference cost. Key parameters include search depth, rollout count, and exploration balance. Future work includes more reliable world models and search. CostBench value: conceptually relevant, but real CostBench observations are more reliable than imagined transitions. |
| 6 | [Tree of Thoughts: Deliberate Problem Solving with Large Language Models](https://arxiv.org/abs/2305.10601), NeurIPS 2023 | Generates multiple intermediate “thought” states, evaluates them, and explores them with BFS/DFS-style search. | The key modules are thought generation, state evaluation, and search. Ablations vary search strategy, branching, and evaluator. The central limitation is evaluator reliability: a poor self-evaluator can prune the correct branch. It is not an environment-grounded tool-execution algorithm. Future work is stronger evaluation and broader tasks. CostBench value: a useful search template, not a standalone replanning solution. |
| 7 | [LLM-Planner: Few-Shot Grounded Planning for Embodied Agents](https://openaccess.thecvf.com/content/ICCV2023/html/Song_LLM-Planner_Few-Shot_Grounded_Planning_for_Embodied_Agents_with_Large_Language_ICCV_2023_paper.html), ICCV 2023 | Retrieves relevant demonstrations, generates high-level plans, grounds them against current visual observations, and updates plans when the observed environment does not support the planned subgoal. | The grounding and retrieval components contribute to few-shot performance on ALFRED. Ablations examine retrieval/grounding and few-shot data. The setting depends on visual perception and embodied affordances, and the plan-update mechanism is not an explicit value comparison between incumbent and alternative tool paths. Future work includes broader grounding and fewer demonstrations. CostBench value: supports state-conditioned plan updates, but the perception stack is not transferable. |
| 8 | [ProgPrompt: Generating Situated Robot Task Plans Using Large Language Models](https://progprompt.github.io/), ICRA 2023 | Represents available objects and robot actions using program-like specifications; prompts the LLM to generate executable program-shaped plans. | Structured action/object declarations and generation constraints reduce impossible actions. The paper reports prompt-structure and generation-constraint ablations, including VirtualHome and a physical robot demonstration. Its assumption is that the action schema is known and mostly stable; it does not solve mid-execution retain/switch decisions. Future work includes broader situated planning. CostBench value: supports typed tool/action schemas and executable plan representations. |
| 9 | [SayCanPay: Heuristic Planning with Large Language Models Using Learnable Domain Knowledge](https://ojs.aaai.org/index.php/AAAI/article/view/29991), AAAI 2024 | Combines LLM action generation (“Say”), learned feasibility (“Can”), learned long-term payoff (“Pay”), and heuristic search over action sequences. | Feasibility and payoff models are central; the paper compares against other LLM planners and studies search/domain-knowledge components. It requires learned domain-specific models and training, which conflicts with the no-GPU/no-training constraint. Its payoff model may also be stale under dynamic changes. Future work includes better domain knowledge and planning generalization. CostBench value: strong conceptual decomposition, but not a practical implementation route here. |
| 10 | [ExpeL: LLM Agents Are Experiential Learners](https://ojs.aaai.org/index.php/AAAI/article/view/29936), AAAI 2024 | Collects successful and failed experiences, extracts natural-language insights, retrieves relevant experiences at inference, and conditions the agent on them. | The memory/insight retrieval is the key module; experiments show performance can improve as experience accumulates. It relies on relevant retrieval and useful experience summaries; it is not a per-checkpoint plan-value evaluator. Future work includes stronger transfer and experience selection. CostBench value: useful for cross-task memory, but not the primary plan-commitment mechanism. |
| 11 | [CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing](https://proceedings.iclr.cc/paper_files/paper/2024/hash/fef126561bbf9d4467dbb8d27334b8fe-Abstract-Conference.html), ICLR 2024 | Produces an answer, selects external tools to critique specific aspects, receives tool feedback, and revises the answer. | External feedback is the key component; tasks include factual QA, code/math, and toxicity. The limitation is that tool critique is not necessarily a plan-level comparison or a complete-path decision. Tool selection and feedback quality are important. Future work includes richer tools and feedback. CostBench value: supports external verification, but a verifier must assess plan quality rather than only factual correctness. |
| 12 | [Language Agent Tree Search (LATS)](https://proceedings.mlr.press/v235/zhou24r.html), ICML 2024 | Selects a node with UCT, expands multiple LLM actions, executes in the environment, evaluates states with an LM value function plus self-consistency, simulates, backpropagates, and reflects after failures. | Official code was inspected at [LanguageAgentTreeSearch](https://github.com/lapisrocks/LanguageAgentTreeSearch) (the repository resolves to andyz245). On HotPotQA, removing the LM heuristic reduces EM from 0.63 to 0.37; removing reflection reduces it to 0.58. The reported configuration uses n=5 children and k=50 trajectories, with 173,290 tokens in one reported comparison. Limitations explicitly include high compute cost and the need to revert to earlier environment states. Future work includes efficiency and larger environments. CostBench value: strong search architecture, but its LM value function is exactly the component most likely to mis-rank a valid incumbent against an alternative. |
| 13 | [ToolChain*: Efficient Action Space Navigation in Large Language Models with A* Search](https://proceedings.iclr.cc/paper_files/paper/2024/hash/13250eb13871b3c2c0a0667b54bad165-Abstract-Conference.html), ICLR 2024 | Represents tool-call sequences as a decision tree and applies A* search. The g and h scores combine memory-derived action-position information, self-consistency, and LLM-imagined future scores. | The method reports better planning/reasoning performance and reduced time against baselines. The heuristic depends on memory coverage and LLM imagination; the paper studies components and search settings such as candidate count and horizon. A public official implementation was not available in the paper materials inspected. CostBench already has a structured tool graph and a native graph-search reference, so this risks duplicating a solver rather than advancing LLM-agent decision quality. |
| 14 | [ToolPlanner: A Tool Augmented LLM for Multi Granularity Instructions with Path Planning and Feedback](https://aclanthology.org/2024.emnlp-main.1018/), EMNLP 2024 | Builds MGToolBench, then uses a two-stage reinforcement-learning framework with path planning and two feedback mechanisms to improve task completion and instruction following. | Reports gains in match/pass/win rates; the method is trained on multi-granularity instructions. It depends on task-specific training data and RL, so it is not aligned with the current no-GPU, low-budget constraint. Future work includes broader tool/instruction generalization. CostBench value: supports explicit planning feedback but is not a drop-in algorithm. |
| 15 | [LLMFP: Planning Anything with Rigor](https://proceedings.iclr.cc/paper_files/paper/2025/file/a1c8a68e52499c9396854e3f967e37c0-Paper-Conference.pdf), ICLR 2025 | Pipeline: Definer extracts variables/constraints; Formulator organizes objects, predicates, actions, state updates, and goals; Code Generator creates Z3/SMT code; solver produces a plan; Self-Assessment & Modification checks and repairs the formulation/code. | On multi-step tasks, LLMFP reports 87.5% optimal rate with GPT-4o and 91.8% with Claude 3.5 Sonnet. Removing Formulator reduces the GPT-4o multi-step average to 0.1%; removing Self-Assessment & Modification reduces it to 75.1%. The paper explicitly notes dependence on clear, detailed task descriptions and solver scalability. We inspected the official [LLMFP repository](https://github.com/yih301/LLMFP), including its time-indexed predicates, action preconditions/effects, state-update API, and self-assessment loop. CostBench gap: the original formulation starts from a task-described initial state and does not explicitly compare a committed incumbent suffix against a newly optimized suffix at a live execution checkpoint. |
| 16 | [Interactive and Expressive Code-Augmented Planning with Large Language Models (REPL-Plan)](https://aclanthology.org/2025.acl-long.994/), ACL 2025 | Generates code in a persistent REPL, executes partial code, observes results, and interactively revises code; combines hard program control flow with soft LLM reasoning. | Evaluated on ALFWorld, WebShop, and real-world web tasks. The REPL allows recovery from coding errors and unstructured observations. Its main dynamic mechanism is error/observation-driven code correction; it does not explicitly compare an executable incumbent plan with an alternative plan's value. No official public code repository was found in the paper materials inspected. Future work includes stronger handling of ambiguous observations and more robust code execution. |
| 17 | [CodePlan: Unlocking Reasoning Potential in LLMs by Scaling Code-Form Planning](https://proceedings.iclr.cc/paper_files/paper/2025/hash/c362b360765ed90ae4bd9c6764837e0e-Abstract-Conference.html), ICLR 2025 | Trains LLMs to produce and follow code-form plans, using a 2M-example dataset that pairs code-form plans with prompt-response data. | Reports a 25.1% relative improvement averaged over 13 multi-step reasoning benchmarks. Data scale and code-form representation are the key levers. It requires model training and is not an online checkpoint-replanning mechanism. Future work includes broader code-form planning and data efficiency. CostBench value: structured plans may help execution, but training is outside the current resource envelope. |
| 18 | [LLM-A*: Large Language Model Enhanced Incremental Heuristic Search on Path Planning]((EMNLP Findings 2024; bibliographic link pending verification)), EMNLP Findings 2024 | Uses an LLM to suggest waypoints/heuristic guidance while an incremental A* planner searches a path. | The method targets search efficiency in path planning, not tool-agent plan commitment. Its performance depends on waypoint quality and heuristic guidance; it is not a main-track EMNLP paper. Future work includes broader path-planning domains. CostBench value: adjacent to dynamic graph search, but not a primary candidate. |
| 19 | [Generalized Planning in PDDL Domains with Pretrained Large Language Models](https://ojs.aaai.org/index.php/AAAI/article/view/30006), AAAI 2024 | Prompts an LLM with a PDDL domain and a few tasks to synthesize a reusable Python planning program; validates it on training tasks and reprompts with debugging feedback. | Evaluates seven PDDL domains and ablates CoT summarization, automated debugging, names, and model choice. Automated debugging is important; two training tasks can often support generalization. The generated policy/program is domain-specific and not inherently an online plan-commitment controller. Future work includes more robust generalized planning and better failure handling. CostBench value: a useful alternative formalization baseline, but LLMFP is more directly solver-backed for this pilot. |
| 20 | [PlanBench: An Extensible Benchmark for Evaluating LLMs on Planning and Reasoning about Change](https://openreview.net/forum?id=X6dEqXIsEW), NeurIPS 2023 Datasets & Benchmarks | Provides diverse planning domains, including action/change reasoning, to distinguish actual planning from world-knowledge recall. | It is a benchmark, not a new planner. Results show LLM planning is weak on several core capabilities. Its contribution is task coverage and evaluation protocol; future work is broader planning capability assessment. CostBench value: supports evaluation beyond final success and motivates precise state-transition tests. |
| 21 | [On the Planning Abilities of Large Language Models: A Critical Investigation](https://openreview.net/forum?id=X6dEqXIsEW), NeurIPS 2023 Datasets & Benchmarks | Evaluates LLMs on formal planning tasks and separates autonomous planning from heuristic-guided settings. | Shows that apparent planning ability can be overstated when formal constraints and action effects are not checked. External planners/verifiers provide useful controls. It is diagnostic rather than a new online replanning algorithm. Future work includes stronger formal planning benchmarks and grounded evaluation. CostBench value: supports including a symbolic planner as a reference ceiling. |
| 22 | [When is Tree Search Useful for LLM Planning? It Depends on the Discriminator](https://aclanthology.org/2024.acl-long.738/), ACL 2024 | Separates a language agent into generator, discriminator, and planner; compares reranking, iterative correction, and tree search as discriminator accuracy varies. | Finds advanced planning needs a discriminator around 90% accurate to reliably beat reranking; tree search can be 10–20× slower with negligible gains when the discriminator is weak. This is a key negative result for LATS-like methods. Future work is better discriminators and more efficient search. CostBench value: directly informs the GO gate: do not adopt tree search until the state/plan evaluator is demonstrably reliable. |
| 23 | [WebArena: A Realistic Web Environment for Building Autonomous Agents](https://proceedings.iclr.cc/paper_files/paper/2024/hash/4410c0711e9154a7a2d26f9b3816d1ef-Abstract-Conference.html), ICLR 2024 | Provides functional websites, long-horizon user tasks, and programmatic task-completion checks. | GPT-4-based agents achieve 14.41% end-to-end success versus 78.24% human performance in the reported setup. It is an environment/benchmark, not a planner. It shows execution and website state are major sources of failure. Future work includes more capable web agents and robust evaluation. CostBench value: reference for a harder follow-up environment after a CostBench GO. |
| 24 | [TravelPlanner: A Benchmark for Real-World Planning with Language Agents](https://proceedings.mlr.press/v235/xie24j.html), ICML 2024 | Provides 1,225 travel-planning intents, a sandbox, tools, and nearly four million data records; evaluates multi-constraint plan construction. | GPT-4 achieves only 0.6% success in the reported benchmark. Failures include staying on task, using the right tools, and maintaining constraints. It is a benchmark rather than an adaptive planner. Future work is more reliable real-world planning. CostBench value: supports multi-constraint evaluation, but is not the first pilot target. |
| 25 | [AgentBench: Evaluating LLMs as Agents](https://proceedings.iclr.cc/paper_files/paper/2024/hash/e9df36b21ff4ee211a8b71ee8b7e9f57-Abstract-Conference.html), ICLR 2024 | Unifies eight interactive environments to evaluate reasoning and decision-making across 29 API-based and open models. | Reveals long-term reasoning, decision-making, and instruction following as major failure sources. It is an evaluation suite, not an algorithm. Future work includes better multi-round alignment and agent training. CostBench value: supports evaluating interaction quality rather than only one-shot answers. |
| 26 | [AgentBoard: An Analytical Evaluation Board of Multi-turn LLM Agents](https://proceedings.neurips.cc/paper_files/paper/2024/hash/877b40688e330a0e2a3fc24084208dfa-Abstract-Datasets_and_Benchmarks_Track.html), NeurIPS 2024 Datasets & Benchmarks | Adds fine-grained progress-rate and process-level evaluation across diverse multi-turn environments. | Its main contribution is diagnosing progress within a trajectory rather than reporting only final success. It is a benchmark/evaluation tool, not a planner. Future work is more interpretable and granular agent evaluation. CostBench value: supports reporting where a trajectory first diverges, not only final task success. |
| 27 | [AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents](https://aclanthology.org/2024.acl-long.850/), ACL 2024 | Provides nine apps, 457 APIs, 750 tasks, realistic user state, and state-based tests including collateral-damage checks. | GPT-4o solves about 49% of normal and 30% of challenge tasks in the reported setup. It evaluates rich code execution and cross-app dependencies. It is a benchmark, not an algorithm. Future work includes stronger interactive coding agents. CostBench value: a possible external validation environment for tool-dependency and side-effect robustness. |
| 28 | [T1: A Tool-Oriented Conversational Dataset for Multi-Turn Agentic Planning](https://proceedings.neurips.cc/paper_files/paper/2025/hash/965605e3b223f3a157d6d6bb64bc9592-Abstract-Datasets_and_Benchmarks_Track.html), NeurIPS 2025 Datasets & Benchmarks | Provides multi-turn, multi-domain tool dependencies and an integrated cache for deciding whether to reuse or recompute results; includes T1-Agent. | Its distinctive issue is multi-turn tool dependency and dynamic reuse/replanning. It is primarily a dataset and evaluation resource. Future work includes better multi-turn tool planning and memory/caching policies. CostBench value: relevant to preserving valid completed work while updating only the remaining plan. |
| 29 | [PlanBench-XL: Evaluating Long-Horizon Planning of LLM Tool-Use Agents in Large-Scale Tool Ecosystems](https://aclanthology.org/2026.emnlp-main.385/), EMNLP 2026 | Evaluates 327 retail tasks over 1,665 tools with retrieval-limited visibility and optional blockers; agents must retrieve tools, build intermediate evidence, and adapt at runtime. | GPT-5.4 reaches 51.90% in block-free settings but 11.36% under the most severe blocking condition. Failures are worse when disruption has no explicit error signal or recovery requires longer alternative paths. It is a benchmark, not a solution. Future work is robust long-horizon replanning in large imperfect tool ecosystems. CostBench value: strong external validation target after the first pilot, especially for silent path degradation. |
| 30 | [Why Do LLM-based Web Agents Fail? A Hierarchical Planning Perspective](https://aclanthology.org/2026.acl-long.1483/), ACL 2026 | Analyzes agents at high-level planning, low-level execution, and replanning layers, separating plan quality from grounding and recovery. | Finds structured PDDL plans can be more concise and goal-directed than natural-language plans, while low-level execution remains a dominant bottleneck. It is a diagnostic study rather than a new planner. Future work emphasizes grounding and adaptive control. CostBench value: reinforces that a correct first action is not enough; full-trajectory execution and replanning must be measured. |

### Notes on the paper set

- Benchmark/diagnostic papers are not presented as algorithms. Their role is to define failure modes and evaluation standards.
- LLM-A* is a Findings paper, not a main-track conference paper; it is included as adjacent incremental-search work, not as a top-three candidate.
- The paper title “Reasoning via Planning (RAP)” is the EMNLP 2023 paper “Reasoning with Language Model is Planning with World Model”.
- The official source-code audit was focused on the top candidates, not all 30 repositories. AdaPlanner, LATS, and LLMFP code were inspected. ToolChain* and REPL-Plan did not have a public official code path in the materials searched.

## 3. Three algorithm candidates

### Candidate A — LLMFP (ICLR 2025)

**Why it fits**

- It is a general LLM planning framework with an explicit formal optimization stage.
- It supports multi-step state transitions and what-if changes.
- It does not require training a new model or GPU fine-tuning.
- It has official code and a modular pipeline.
- The Formulator is empirically important: removing it reduces multi-step optimal rate from 87.5% to 0.1% in the reported GPT-4o ablation.
- Its solver-backed output can be handed to the existing CostBench native executor as a complete remaining plan, addressing the observed gap between choosing a correct first action and maintaining a correct continuation.

**Weakness to target**

The original formulation is task/query-centred. It represents initial predicates, actions, updates, and goals, but does not explicitly encode the incumbent plan suffix as a competing candidate at a live execution checkpoint. It therefore does not directly solve the project’s central decision: should the agent retain the unexecuted suffix it has already committed to, or replace it?

**Single-module change**

Modify only the **Formulator** to produce a checkpoint-conditioned, incumbent-aware optimization representation. Do not alter Definer, Code Generator, solver choice, or Self-Assessment & Modification in the first implementation.

### Candidate B — LATS (ICML 2024)

**Why it is attractive**

- It has an official, inspectable implementation.
- It integrates planning, acting, environment feedback, and reflection.
- It explicitly supports search over alternative continuations.

**Why it is not the mainline**

- Its LM value function is essential: removing it drops HotPotQA EM from 0.63 to 0.37.
- The ACL 2024 discriminator study finds that tree search needs roughly 90% discriminator accuracy to reliably outperform reranking.
- CostBench’s own plan-identity and candidate-comparison audits show that LLM judgements can be inconsistent.
- The paper’s standard setting uses n=5 and k=50 and reports substantial token consumption; the user’s current budget constraint makes this a risky first implementation.
- The environment must support rollback to previous states.

A graph-grounded value function is a plausible future modification, but the existing bounded verifier did not yet establish a full-trajectory advantage. LATS should not be implemented until the evaluator passes an independent accuracy gate.

### Candidate C — AdaPlanner (NeurIPS 2023)

**Why it is attractive**

- Its plan/assertion/refinement/resume pipeline directly concerns adaptive planning.
- Official code is available.
- It is simple to port and has explicit in-plan and out-of-plan refinement.

**Why it is not the mainline**

The original trigger is feedback/assertion mismatch. The CostBench audit found 27/27 plans still executable and no subsequent tool-error output, so the original trigger did not activate on the observed valid-but-inferior plan cases. Replacing the trigger could be useful, but the replacement would be a new decision-quality mechanism and still needs to prove that AdaPlanner’s refiner actually switches when invoked. The existing explicit fact-update baseline is already strong.

## 4. Mainline proposal: Checkpoint-Aware Incumbent Formulator

Working description: **Checkpoint-Aware LLMFP**. This is a provisional research label, not a final paper title.

### Original pipeline

Task/query + action descriptions  
→ Definer  
→ Formulator (objects, predicates, actions, transition/update constraints, goal)  
→ Code Generator  
→ Z3/SMT solver  
→ Self-Assessment & Modification  
→ plan

### Modified pipeline

Task/query + actual checkpoint state + executed prefix + incumbent suffix + current tool descriptions  
→ Definer (unchanged)  
→ **Checkpoint-Aware Incumbent Formulator (the only modified core module)**  
→ Code Generator (unchanged)  
→ Z3/SMT solver  
→ Self-Assessment & Modification (unchanged)  
→ RETAIN/SWITCH decision + complete selected suffix  
→ existing native executor

### Online inputs

The online method may use only:

- the user goal and task description;
- the actual state reconstructed from successful tool outputs;
- the already executed action prefix;
- the unexecuted incumbent suffix;
- current tool names, schemas, preconditions/effects, availability, and current attributes exposed by the environment;
- the current environment update.

It must not use:

- test-set labels;
- a hidden optimal plan;
- future observations;
- post-hoc shortest-path labels unavailable at decision time;
- any oracle output from the evaluation script.

The graph-search reference may be used offline for evaluation, but it must not be passed into the online Formulator unless that exact graph information is available to the agent at runtime.

### Mathematical definition

Let \(s_t\) be the actual checkpoint state after the executed prefix \(P_{<t}\). Let \(\pi_{\mathrm{old}}^{t:}\) be the incumbent unexecuted suffix. Let \(\mathcal{A}_t\) be the actions described by the current tool interface, with current transition relation \(T_t\) and objective \(J_t\).

The Formulator builds a feasible suffix set:

\[
\Pi(s_t,G,T_t)=\{\pi:\ T_t(s_t,\pi)\models G\}.
\]

It evaluates the incumbent suffix under the current state and current environment:

\[
F_{\mathrm{old}} =
\mathbf{1}\left[\pi_{\mathrm{old}}^{t:}\in\Pi(s_t,G,T_t)\right],
\qquad
J_{\mathrm{old}}=J_t(\pi_{\mathrm{old}}^{t:}).
\]

It then solves for a current feasible candidate:

\[
\pi^*=\arg\min_{\pi\in\Pi(s_t,G,T_t)}J_t(\pi),
\qquad
J^*=J_t(\pi^*).
\]

Decision rule:

\[
\text{decision}=
\begin{cases}
\text{SWITCH}, & F_{\mathrm{old}}=0,\\
\text{SWITCH}, & J_{\mathrm{old}}>J^*+\epsilon,\\
\text{RETAIN}, & \text{otherwise}.
\end{cases}
\]

For the first pilot, set \(\epsilon=0\): ties retain the incumbent, avoiding unnecessary revisions. Do not tune \(\epsilon\) on the test set. If a non-zero tolerance is later justified, choose it only on development data.

The executed prefix is immutable. The solver starts from \(s_t\), not the original initial state, and must never replay completed actions.

### Pseudocode

1. Recover the actual checkpoint state from successful native tool outputs.
2. Extract the incumbent unexecuted suffix from the original agent trajectory.
3. Read the current tool schema and current environment facts.
4. Ask the modified Formulator to encode the checkpoint as time zero, the executed prefix as fixed history, the incumbent suffix as a fixed candidate, and a new suffix as decision variables.
5. Generate the Z3 model using the unchanged Code Generator.
6. Check incumbent feasibility and evaluate its current objective.
7. Solve for a feasible current candidate suffix.
8. If the incumbent is infeasible or strictly worse, return SWITCH and the full candidate suffix; otherwise return RETAIN and the incumbent suffix.
9. Execute the selected full suffix through the native executor. Validate each real tool result against the expected next state. If a new environment update occurs, start a new checkpoint cycle.

### Expected wins

- The old plan remains executable but is no longer the best current continuation.
- The model is biased toward retaining the old plan when asked for a free-form judgement.
- A first action is selected correctly but the model later drifts away from the selected continuation.
- Completed actions must be preserved and not repeated after replanning.

### Expected failure cases

- The tool schema omits a precondition, effect, or relevant environment attribute.
- The LLM Formulator generates an incorrect transition model; the solver can then return a formally valid but semantically wrong plan.
- The environment is partially observed and the current state is incomplete.
- The action space is too large for the solver budget.
- The incumbent suffix is not recoverable from the agent trace.
- The objective does not represent the actual task preference.

This method must be rejected if its advantage depends on hidden optimal labels or a post-hoc oracle.

## 5. First end-to-end screening protocol

No paid API call has been made for this candidate. The existing CostBench outputs are retained as evidence; they are not misrepresented as a run of LLMFP.

### Methods

| Arm | Method | Purpose |
|---|---|---|
| A | Original LLMFP, adapted to the same CostBench checkpoint input | Mature algorithm baseline |
| B | Strongest existing explicit-fact-update Prompt/symbolic-repair baseline | Strong simple baseline |
| C | Checkpoint-Aware LLMFP (only Formulator changed) | Proposed method |
| Reference | Native graph planner / complete-plan handoff | Upper-bound/reference, not a competing LLM method |

All arms receive the same task, model, initial state, checkpoint, current tool descriptions, and action budget. Gold RETAIN/SWITCH labels and offline optimal paths are hidden from all online arms.

### Task selection

Select 8–12 development tasks from existing CostBench materials. Prefer 10 tasks arranged as five matched pairs, with both RETAIN and SWITCH cases represented. The set must cover:

- RETAIN: the incumbent suffix remains feasible and best;
- SWITCH: the incumbent suffix remains feasible but is no longer best;
- SWITCH: the incumbent suffix becomes infeasible;
- RETAIN: an environment update is irrelevant to the incumbent suffix;
- cases where the first action is correct but later continuation is at risk.

Task selection must be frozen before running the model. Do not select tasks after looking at the new method’s responses.

### Metrics

- RETAIN Accuracy
- SWITCH Accuracy
- Balanced Accuracy
- Pair Accuracy
- Task Success Rate
- False RETAIN
- False SWITCH
- Unnecessary plan revisions
- Full-suffix execution validity
- First-action correctness
- Number of model calls and wall-clock time

### GO / NO-GO

GO only if all of the following hold:

1. C improves Balanced Accuracy over the strongest simple baseline by at least two additional correct decisions on a 10-task screen, or shows an equivalently clear paired improvement.
2. The gain is not obtained by collapsing into always RETAIN or always SWITCH.
3. Task success and full-suffix execution validity do not regress.
4. The improvement appears in more than one matched pair and is not caused by one exceptional task.
5. All online inputs are available at runtime; no gold label or test-set optimum leaks into the method.
6. The result can be reproduced from the recorded prompts, solver models, native traces, and evaluation script.

NO-GO if C only matches the simple baseline, if the Formulator frequently mis-specifies transitions, if the solver output cannot execute in the native harness, or if the advantage disappears when the complete plan is executed rather than only forcing its first action.

The 8–12-task screen is a low-cost rejection test, not publication-level statistical evidence. Only after GO should the project run parameter analysis, full comparisons, ablations, and frozen independent testing.

## 6. Resource and repository constraints

- Continue only on research/complete-candidate-verification.
- Do not create a new branch.
- Do not modify main.
- Preserve all existing CostBench data and the AdaPlanner audit.
- Do not revive ToolMaze, ReCAP, or EALR as experimental routes.
- Do not run paid API calls without explicit approval.
- First port the official LLMFP pipeline to the existing DeepSeek-compatible client and run static/schema tests without model calls.
- Before any paid run, estimate tokens from the exact frozen prompts and report the maximum budget for approval.
- A passing unit test, valid Z3 model, or successful directory check is not evidence of algorithmic improvement.

## 7. Current acceptance status

| Item | Status |
|---|---|
| Current branch and commit verified | Complete |
| Existing CostBench and AdaPlanner audit reviewed | Complete |
| Thirty-paper shortlist and comparative analysis | Literature review drafted in this document |
| Official code inspection for AdaPlanner, LATS, LLMFP | Complete |
| Three candidates compared | Complete |
| Main candidate selected provisionally | Complete: LLMFP Formulator |
| Single-module change specified | Complete: checkpoint-aware incumbent Formulator |
| Minimal end-to-end protocol specified | Complete |
| LLMFP port to CostBench | Not started |
| Static solver/schema tests | Not started |
| Paid native model pilot | Not run; requires explicit budget approval |
| GO/NO-GO | Not yet determined |

The next implementation action is a zero-API port of the LLMFP Formulator interface and a static replay against existing task/state records. No performance claim should be made until the matched native end-to-end screen is run.
