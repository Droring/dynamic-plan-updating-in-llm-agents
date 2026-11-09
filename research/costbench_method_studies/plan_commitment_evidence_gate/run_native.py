#!/usr/bin/env python3
"""Run formal state-certified policies in the original CostBench native environment.

Every task starts from its same verified archived dynamic model prefix. Only
the decision callback changes; CostBench owns the live data state, tools,
blocker, execution, and native outcomes. No post-event LLM provider calls.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(HERE))
from replay_gate import BASE,OfflineClient,canonical,load_dev80,load_dynamic,native_args
from native_agent import POLICIES,PENALTY,SymbolicContinuation,calls,ERROR
from core import price

def write_new(path,value):
    if path.exists():raise FileExistsError("immutable result path: "+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,
                               allow_nan=False,default=str)+"\n",encoding="utf-8")

async def one(official,query,archived,mode,gate):
    from env.utils.blocker import DynamicBlocker
    from env.core.data_types import get_final_type
    from env.utils.eval import get_agent_final_answer,check_answer_accuracy
    native_state=[frozenset()]
    original_hook=DynamicBlocker.set_current_state
    def state_hook(self,data_types):
        native_state[0]=frozenset(data_types)
        return original_hook(self,data_types)
    DynamicBlocker.set_current_state=state_hook
    q=copy.deepcopy(query)
    controller=SymbolicContinuation(archived,mode,get_final_type(q["task"]),
                                    lambda:native_state[0],PENALTY)
    try:
        result=await official.run_single_query(OfflineClient(controller),q,
            native_args(official,BASE/"inputs/manifest.json"),0,
            official._stable_int("42:"+q["query_id"]))
    finally:
        DynamicBlocker.set_current_state=original_hook
    hist=result.get("conversation_history") or []
    expected=(result.get("groundtruth") or {}).get("scenarios") or []
    event_count=int((result.get("block_stats") or {}).get("block_count_agent",0) or 0)
    final=get_agent_final_answer(hist)
    accepted=bool(check_answer_accuracy(final,expected,event_count))
    if controller.started and controller.checkpoint_tools_digest!=gate["tool_state_digest"]:
        raise AssertionError("checkpoint public tool snapshot mismatch")
    S=controller.state
    types_sha=hashlib.sha256(canonical(sorted(S)).encode()).hexdigest() if S is not None else None
    attempted=list(controller.generated)
    cost=price([x["name"] for x in attempted],controller.new) if controller.new else None
    issues=[]
    if not controller.started:issues.append("OFFICIAL_EVENT_CHECKPOINT_NOT_REACHED")
    if not controller.finished:issues+=controller.errors or ["OFFICIAL_RUN_TERMINATED_BEFORE_FINAL_ANSWER"]
    if not result.get("is_goal_state"):issues.append("FINAL_NATIVE_GOAL_TYPE_MISSING")
    if len(attempted)!=len(controller.plan or ()):issues.append("PLANNED_NATIVE_CALLS_INCOMPLETE")
    native_tool_messages=[m for m in hist if m.get("role")=="tool"]
    prefix_tool_failures=sum((m.get("content") or "").startswith(ERROR)
        for m in native_tool_messages[:controller.trigger_step])
    if any((m.get("content") or "").startswith(ERROR)
           for m in native_tool_messages[controller.trigger_step:]):
        issues.append("POST_EVENT_NATIVE_TOOL_RETURNED_ERROR")
    diag=None
    if controller.decision:
        d=controller.decision
        diag={"action":d.kind,"incumbent":list(d.incumbent),
            "algorithm_chosen_suffix":list(d.suffix),
            "current_optimal_suffix":list(d.new_optimal) if d.new_optimal is not None else None,
            "old_cost":d.old_cost,"incumbent_updated_cost":d.incumbent_post_cost,
            "algorithm_cost":d.selected_post_cost,
            "current_full_optimal_cost":d.full_post_cost,
            "safe_upper_bound_on_switch_gain":d.upper_bound_gain,
            "certificate_kind":d.certificate,"switch_penalty":d.switch_penalty,
            "old_search_expansions":d.old_search_expansions,
            "new_search_expansions":d.new_search_expansions,
            "local_search_expansions":d.local_search_expansions,
            "planning_wall_seconds":d.planning_wall_seconds}
    record={
        "query_id":archived["query_id"].strip("<>"),
        "category":q["task"],"policy":mode,
        "run_status":"complete" if not issues else "incomplete",
        "issues":issues,
        "native_runner_status":result.get("status"),
        "native_goal_reached":result.get("is_goal_state") is True,
        "pre_event_archived_native_tool_failures":prefix_tool_failures,
        "official_final_answer_accepted":accepted,
        "observed_final_answer":final,
        "event_count_effective":event_count,
        "checkpoint_replayed":controller.started,
        "checkpoint_native_state":sorted(S) if S is not None else None,
        "checkpoint_native_state_sha256":types_sha,
        "checkpoint_public_tool_sha256":controller.checkpoint_tools_digest,
        "checkpoint_conversation_sha256":controller.conversation_digest,
        "selected_policy_action":controller.selected,
        "planned_remaining_native_tool_calls":list(controller.plan or ()),
        "actually_requested_post_event_native_calls":attempted,
        "observed_public_tool_cost_attempted":cost,
        "walltime_python_planning_seconds":controller.planning_seconds,
        "public_graph_search_expansions":controller.search_expansions,
        "counterfactual_decision_audit":diag,
        "pre_event_text_plan_memory":controller.plan_commitment,
        "public_evidence_gate":controller.evidence_gate,
        "model_provider_calls_post_event":0,
        "model_provider_tokens_post_event":0,
        "native_transcript":[{
            "role":m.get("role"),"content":m.get("content"),
            "calls":[{"id":i,"name":n,"arguments":a} for i,n,a in calls(m)]
                if m.get("tool_calls") else [],
            "tool_call_id":m.get("tool_call_id")} for m in hist]
    }
    return record

async def execute(costbench_root,out,smoke_count=None,smoke_id=None):
    sys.path.insert(0,str(costbench_root))
    import env.run as official
    archives=load_dynamic()
    queries=load_dev80()
    gates=json.loads((ROOT/"research/costbench_method_studies/plan_commitment_evidence_gate/REPLAY_GATE.json").read_text())
    eligible={x["query_id"]:x for x in gates["tasks"]
              if x["status"]=="replay_matched_checkpoint"}
    if len(eligible)!=67:raise AssertionError("official 80-task baseline has exactly 67 observed event checkpoints")
    taskids=sorted(eligible)
    if smoke_count is not None:taskids=taskids[:smoke_count]
    if smoke_id is not None:
        if smoke_id not in eligible:raise ValueError("smoke ID is not a real certified development checkpoint")
        taskids=[smoke_id]
    all_rows=[]
    for qid in taskids:
        rows=[]
        for policy in POLICIES:
            item=await one(official,queries[qid],archives[qid],policy,eligible[qid])
            rows.append(item)
        for field in ("checkpoint_native_state_sha256","checkpoint_public_tool_sha256",
                      "checkpoint_conversation_sha256"):
            observed={x[field] for x in rows}
            if len(observed)!=1 or None in observed:
                raise AssertionError("not genuinely paired from one checkpoint "+qid+" "+field)
        all_rows.extend(rows)
        write_new(out/"cases"/(qid+".json"),{"query_id":qid,"rows":rows})
    result={"schema":"native_plan_commitment_evidence_gate",
        "run_kind":"integration_smoke" if smoke_count or smoke_id else "native_plan_commitment_evidence_gate_all_observed_events",
        "pinned_upstream_commit":"6424069f3f773ade076bcedbed302ed47cfb1837",
        "independent_dev_tasks":len(taskids),
        "related_strategy_trajectories":len(all_rows),
        "selected_query_ids":taskids,
        "strategies":list(POLICIES),
        "fixed_switch_penalty_tool_units":PENALTY,
        "provider_calls_for_strategy_continuation":0,
        "other_13_baseline_dev_tasks":"no_observed_dynamic_checkpoint",
        "records":all_rows}
    write_new(out/"RESULTS.json",result)
    summary={p:{
        "goal":sum(x["native_goal_reached"] for x in all_rows if x["policy"]==p),
        "correct":sum(x["official_final_answer_accepted"] for x in all_rows if x["policy"]==p),
        "incomplete":sum(x["run_status"]!="complete" for x in all_rows if x["policy"]==p),
    } for p in POLICIES}
    print( "COSTBENCH_NATIVE_DEV_REPLAY "+json.dumps({
        "independent_base_tasks":len(taskids),"arm_trajectories":len(all_rows),
        "results":summary},sort_keys=True))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--costbench-root",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--smoke-count",type=int)
    ap.add_argument("--smoke-id",type=str)
    args=ap.parse_args()
    if args.smoke_count and args.smoke_id:raise ValueError("use only one smoke selector")
    if args.smoke_count is not None and not 1<=args.smoke_count<=3:
        raise ValueError("smoke count must be in 1 to 3")
    root=args.costbench_root.resolve()
    out=args.out.resolve()
    if out.exists():raise FileExistsError("would overwrite prior original output")
    cwd=Path.cwd()
    try:
        os.chdir(root)
        asyncio.run(execute(root,out,args.smoke_count,args.smoke_id))
    finally:
        os.chdir(cwd)
if __name__=="__main__":main()
