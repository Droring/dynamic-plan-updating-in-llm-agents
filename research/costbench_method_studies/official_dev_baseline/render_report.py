#!/usr/bin/env python3
"""Render a frozen, fully evidence-derived official CostBench baseline report."""
from __future__ import annotations
import argparse
import json
import random
from math import comb
from collections import defaultdict
from pathlib import Path

def rate(n,d):
    return f"{n}/{d} ({n/d*100:.1f}%)" if d else "N/A"

def resources(doc,condition):
    groups=[v["official_statistics"] for k,v in doc["group_stats"].items()
            if k.startswith(condition+"/")]
    return {
        "valid":sum(int(s.get("valid_num",0)) for s in groups),
        "tool_calls":sum(int((s.get("tool_usage_metrics") or {}).get("total_tool_calls",0)) for s in groups),
        "tool_cost":sum(float((s.get("cost_metrics") or {}).get("total_agent_cost",0) or 0) for s in groups),
        "reference_cost":sum(float((s.get("cost_metrics") or {}).get("total_gt_cost",0) or 0) for s in groups),
    }

def render(d):
    if d["independent_base_tasks"]!=80 or len(d["rows"])!=160:
        raise AssertionError("Official native results are not a complete 80-task study")
    s=d["per_condition"]["static"]
    t=d["per_condition"]["official_cost_change"]
    p=d["paired_task_outcomes"]
    pairs=defaultdict(dict)
    for x in d["rows"]:
        pairs[x["query_id"]][x["condition"]]=x
    if len(pairs)!=80 or any(len(pair)!=2 for pair in pairs.values()):
        raise AssertionError("missing independent paired tasks")
    b=p["static_only_correct"]; c=p["dynamic_only_correct"]; disc=b+c
    mcnemar=min(1.0,2*sum(comb(disc,k) for k in range(min(b,c)+1))/2**disc) if disc else 1.
    vals=[int(v["official_cost_change"]["official_final_answer_success"])
          -int(v["static"]["official_final_answer_success"]) for v in pairs.values()]
    rng=random.Random(20261106)
    boot=[]
    for _ in range(10000):
        boot.append(sum(rng.choices(vals,k=80))/80)
    boot.sort()
    delta=(t["official_final_answer_success"]-s["official_final_answer_success"])/80
    triggered=[v for v in pairs.values() if v["official_cost_change"]["dynamic_events_triggered"]>0]
    triggered_static=sum(v["static"]["official_final_answer_success"] for v in triggered)
    triggered_dynamic=sum(v["official_cost_change"]["official_final_answer_success"] for v in triggered)
    a_cost=resources(d,"static"); b_cost=resources(d,"official_cost_change")
    lines=[
        "# Official Native Dynamic-Robustness Study: CostBench Agent Baseline (80 Development Tasks)",
        "",
        "## Executive summary",
        "",
        "DeepSeek Flash was evaluated using the pinned, unmodified CostBench Agent loop on **80 independent development tasks**, with one static and one official cost-change run per task. These are **160 correlated trajectories**, not independent task samples. The validation (40) and locked-test (80) tasks were not evaluated.",
        "",
        f"Official final-answer accuracy was **{rate(s['official_final_answer_success'],80)} static** and **{rate(t['official_final_answer_success'],80)} dynamic**. The observed paired difference (dynamic minus static) was **{delta*100:+.1f} percentage points** (task-resampled descriptive 95% bootstrap interval [{boot[249]*100:+.1f}, {boot[9749]*100:+.1f}] points). Exact two-sided McNemar p = **{mcnemar:.5f}**. This is exploratory analysis on a development set; it does not establish method improvement or a causal price-change effect.",
        "",
        f"Crucially, the dynamic event was actually triggered in **{t['dynamic_event_triggered']}/80** tasks. The other **{t['dynamic_event_not_triggered']}/80** ended before the planned event, including early stops that the upstream runner recorded as completed. These cases must **not** be interpreted as unsuccessful recovery after observing a price change.",
        "",
        "## Full-denominator outcome table",
        "",
        "| Metric | Static | Official cost change |",
        "|---|---:|---:|",
    ]
    for name,key in [
        ("Attempted task-condition trajectories","attempted_trajectories"),
        ("At least one native tool called","native_tool_called"),
        ("Goal type reached","goal_state_reached"),
        ("Official final answer accepted","official_final_answer_success"),
        ("Official evaluation present","evaluation_recorded"),
        ("No native tool called","no_native_tool_call")
    ]:
        if key=="attempted_trajectories":
            lines.append(f"| {name} | {s[key]} | {t[key]} |")
        else:
            lines.append(f"| {name} | {rate(s[key],80)} | {rate(t[key],80)} |")
    lines.append(f"| Official cost-change event triggered | N/A | {rate(t['dynamic_event_triggered'],80)} |")
    lines.extend([
        "",
        "## Matched-task outcomes",
        "",
        "| Both correct | Static only | Dynamic only | Neither correct |",
        "|---:|---:|---:|---:|",
        f"| {p['both_answers_correct']} | {p['static_only_correct']} | {p['dynamic_only_correct']} | {p['neither_correct']} |",
        "",
        f"Among the **{len(triggered)}** dynamic trajectories where a cost-change event actually fired, **{triggered_dynamic}/{len(triggered)}** dynamic answers were accepted. Static results on those same task IDs were **{triggered_static}/{len(triggered)}**. This conditional subset is **selected based on dynamic execution**, so it is diagnostic only and cannot replace the full 80-task estimate.",
        "",
        "## Early termination before a dynamic event",
        "",
        "The event was not observed in the following run types:",
        "",
        "| Audited early-stop type | Count |",
        "|---|---:|",
    ])
    for key,n in sorted(t["pre_event_termination_types"].items()):
        lines.append(f"| {key.replace('_',' ')} | {n} |")
    lines.extend([
        "",
        "The upstream runner can label a case completed even when the required goal state was never reached. Some histories contain no assistant message at all; the archived files do not preserve enough provider-side error information to distinguish transient request failure from other causes. Treat them as **incomplete Agent trajectories with an unknown underlying cause**, not proven replanning failures.",
        "",
        "## Category-stratified results",
        "",
        "| Category | Distinct tasks | Static correct | Dynamic correct |",
        "|---|---:|---:|---:|",
    ])
    for k,v in d["counts_by_category"].items():
        lines.append(f"| {k} | {v['tasks']} | {rate(v['static_answer_success'],v['tasks'])} | {rate(v['dynamic_answer_success'],v['tasks'])} |")
    lines.extend([
        "",
        "## Resources and cost accounting",
        "",
        "| Official aggregate | Static | Cost change |",
        "|---|---:|---:|",
        f"| Valid CostBench queries used by official cost aggregation | {a_cost['valid']} | {b_cost['valid']} |",
        f"| Native tool calls in official score aggregates | {a_cost['tool_calls']} | {b_cost['tool_calls']} |",
        f"| Simulated Agent tool-cost sum (official units) | {a_cost['tool_cost']:.2f} | {b_cost['tool_cost']:.2f} |",
        f"| Simulated reference cost sum (official units) | {a_cost['reference_cost']:.2f} | {b_cost['reference_cost']:.2f} |",
        "| Provider tokens, API dollars, per-task latency | not recorded | not recorded |",
        "",
        "The official aggregate-cost denominators **differ** (80 vs 67); totals are therefore not a fair per-task treatment comparison. GT and Agent costs may also be evaluated from different execution states. No aligned-state regret, token savings, API spend or replanning latency improvement is inferred.",
        "",
        "## Failure inventory (all task-condition failures retained)",
        "",
        "Each entry represents a task-condition trajectory, not an independent experiment.",
        "",
        "| Task | Condition | Goal reached | Final accepted | Native calls | Event triggered | Diagnostic |",
        "|---|---|---|---|---:|---:|---|",
    ])
    for x in sorted(d["rows"],key=lambda r:(r["query_id"],r["condition"])):
        if (x["official_final_answer_success"]
            and (x["condition"]=="static" or x["dynamic_events_triggered"]>0)):
            continue
        diag=x["pre_event_termination"] or (
            "goal_not_reached" if not x["goal_state_reached"]
            else "final_answer_not_accepted")
        lines.append(f"| {x['query_id']} | {x['condition']} | {x['goal_state_reached']} | {x['official_final_answer_success']} | {x['native_tool_calls_requested']} | {x['dynamic_events_triggered']} | {diag} |")
    lines.extend([
        "",
        "## Research interpretation and limits",
        "",
        "1. This is a **baseline for the official CostBench reactive Agent**, not a verification/local-repair controller evaluation. A changed execution path alone does not establish that an LLM internally decided to replan.",
        "2. The early-stop concentration in non-triggered dynamic runs requires dedicated instrumentation and technical diagnosis before making claims about robustness to *observed* cost changes.",
        "3. Official dynamic cost changes are not the same as the seven graph-only constructed event families. Ground-truth cost comparisons require explicit aligned-state checks before interpreting regret.",
        "4. The tasks were development candidates that had already passed graph feasibility screening; this is not a blind test of a newly proposed method.",
        "5. A simple task-clustered bootstrap reflects uncertainty from task-level variability but cannot correct bias in how CostBench cases were selected or guarantee generalization to production environments.",
        "",
        "## Provenance and reproduction",
        "",
        "- [Frozen task, model, and version manifest](evidence/inputs/manifest.json)",
        "- [Complete deterministic task and category audit](evidence/SUMMARY.json)",
        "- [Eight original official CostBench output files](evidence/results/)",
        "- [Official native execution protocol](README.md)",
        "",
        "To reproduce the report from the saved audit: python research/costbench_method_studies/official_dev_baseline/render_report.py --summary research/costbench_method_studies/official_dev_baseline/evidence/SUMMARY.json --out /tmp/official_native_results.md",
        "",
    ])
    return "\n".join(lines)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--summary",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    a=parser.parse_args()
    if a.out.exists():
        raise FileExistsError("report path must not be silently overwritten")
    doc=json.loads(a.summary.read_text(encoding="utf-8"))
    content=render(doc)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(content,encoding="utf-8")
    print("OFFICIAL_DEV80_REPORT_RENDERED "+str(a.out))
