#!/usr/bin/env python3
"""Recompute the completed native plan-handoff 2x2 results from its artifact."""
from __future__ import annotations
import argparse, json
from pathlib import Path
TASKS=("Query00178","Query00351","Query00549","Query00689","Query00851")
ENVS=("RETAIN","SWITCH"); ARMS=("A","B","C","D"); REPS=(1,2); TOL=1e-6
def read_jsonl(p):
    with Path(p).open(encoding="utf-8") as f: return [json.loads(x) for x in f if x.strip()]
def close(a,b): return abs(float(a)-float(b))<=TOL
def mean(xs): return sum(xs)/len(xs) if xs else 0.0
def analyze(rows,summary,ledger):
    expected={(t,e,a,r) for t in TASKS for e in ENVS for a in ARMS for r in REPS}; keyed={}
    for x in rows:
        k=(x.get("query_id"),x.get("environment"),x.get("arm"),x.get("repetition"))
        if k in keyed: raise ValueError(f"Duplicate cell {k}")
        keyed[k]=x
    if set(keyed)!=expected or len(rows)!=80: raise ValueError("Frozen 5x2x4x2 matrix mismatch")
    for k,x in keyed.items():
        if not x.get("goal_reached") or x.get("provider_outcome_unknown"): raise ValueError(f"Unknown/incomplete outcome {k}")
        if not close(sum(float(z["bellman_loss"]) for z in x.get("trace",[])),x["continuation_regret"]): raise ValueError(f"Continuation Bellman loss mismatch {k}")
        if not close(float(x["common_prefix_loss"])+float(x["continuation_regret"]),x["full_path_regret"]): raise ValueError(f"Full-path regret mismatch {k}")
    fields=("checkpoint_sha256","common_first_action","common_arguments_sha256","common_tool_result_sha256","post_action_state_sha256","common_prefix_loss")
    for t in TASKS:
        for e in ENVS:
            cell=[keyed[(t,e,a,r)] for a in ARMS for r in REPS]
            for f in fields:
                if len({json.dumps(x.get(f),sort_keys=True) for x in cell})!=1: raise ValueError(f"State mismatch {t}/{e}/{f}")
    metrics={}; tm={}
    for e in ENVS:
        for a in ARMS:
            g=[keyed[(t,e,a,r)] for t in TASKS for r in REPS]; rr=[float(x["continuation_regret"]) for x in g]
            metrics[f"{e}/{a}"]={"n_trajectories":10,"goals_reached":sum(bool(x["goal_reached"]) for x in g),
                "exact_optimal_continuations":sum(abs(v)<=TOL for v in rr),"mean_continuation_regret":round(mean(rr),8),
                "mean_full_path_regret":round(mean([float(x["full_path_regret"]) for x in g]),8),
                "model_calls":sum(int(x["model_calls"]) for x in g),"provider_tokens":sum(int(x["provider_tokens"]) for x in g),
                "mean_elapsed_seconds":round(mean([float(x.get("elapsed_seconds",0)) for x in g]),6)}
            for t in TASKS: tm[(t,e,a)]=mean([float(keyed[(t,e,a,r)]["continuation_regret"]) for r in REPS])
    contrasts={}; matches={}
    for e in ENVS:
        contrasts[e]={}
        for name,l,r in (("A_to_B","A","B"),("C_to_D","C","D"),("B_to_D","B","D"),("A_to_C","A","C")):
            diff={t:round(tm[(t,e,l)]-tm[(t,e,r)],8) for t in TASKS}
            contrasts[e][name]={"task_level_differences_left_minus_right":diff,
                "tasks_improved_by_right":[t for t,v in diff.items() if v>TOL],
                "tasks_worsened_by_right":[t for t,v in diff.items() if v<-TOL],
                "tasks_unchanged":[t for t,v in diff.items() if abs(v)<=TOL]}
        m=[keyed[(t,e,"B",r)]["executed_continuation"]==keyed[(t,e,"D",r)]["executed_continuation"] for t in TASKS for r in REPS]
        matches[e]={"matched_task_repetitions":10,"exact_B_D_continuation_matches":sum(m)}
    if summary.get("status")!="complete" or int(summary.get("completed_trajectories",-1))!=80 or int(summary.get("goal_reached",-1))!=80 or int(summary.get("unknown_provider_outcomes",-1))!=0: raise ValueError("Run summary is incomplete")
    if ledger.get("status")!="complete" or int(ledger.get("completed_trajectories",-1))!=80: raise ValueError("Ledger is incomplete")
    for k,v in metrics.items():
        old=summary.get("by_environment_and_arm",{}).get(k)
        if old is None or int(old["n"])!=10 or int(old["exact_optimal_continuations"])!=v["exact_optimal_continuations"] or not close(old["mean_continuation_regret"],v["mean_continuation_regret"]) or not close(old["mean_full_path_regret"],v["mean_full_path_regret"]): raise ValueError(f"Archived summary mismatch {k}")
    elapsed=[float(x.get("elapsed_seconds",0)) for x in rows]
    return {"status":"verified","independent_base_tasks":5,"completed_trajectories":80,"goals_reached":80,
        "unknown_provider_outcomes":0,"model_calls":int(summary["model_calls"]),"provider_tokens":int(summary["provider_tokens_charged"]),
        "total_trajectory_elapsed_seconds":round(sum(elapsed),6),"mean_trajectory_elapsed_seconds":round(mean(elapsed),6),
        "independent_statistical_unit":"base task (n=5)","by_environment_and_arm":metrics,
        "task_level_paired_contrasts":contrasts,"B_D_exact_continuation_path_match":matches}
def main():
    p=argparse.ArgumentParser(); p.add_argument("--responses",required=True,type=Path); p.add_argument("--summary",required=True,type=Path); p.add_argument("--ledger",required=True,type=Path); p.add_argument("--out",required=True,type=Path); a=p.parse_args()
    result=analyze(read_jsonl(a.responses),json.loads(a.summary.read_text()),json.loads(a.ledger.read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"completed_trajectories":80,"B_D_path_matches":result["B_D_exact_continuation_path_match"]}))
if __name__=="__main__": main()
