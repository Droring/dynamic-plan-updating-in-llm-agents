#!/usr/bin/env python3
"""Run the full-trajectory Plan Handoff × Observed-State 2×2 screen.

Dry-run by default. Live execution replays the frozen common native action in
each isolated branch, then lets DeepSeek choose and parameterize subsequent
native tools. No reference path or value is included in model-facing prompts.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import shutil
import time
from collections import defaultdict
from pathlib import Path

import graph_planning_baseline as graph
import run_bounded_verifier_confirmation as confirmation
import run_official_harness as native
from prepare_plan_handoff_experiment import render_ledger, update_ledger
from preflight_common_action_restoration import ARMS, ENVIRONMENTS, TASKS

TOL=1e-5


def append_jsonl(path: Path, value: dict):
    """Durably append one JSONL record; never depend on another runner's private helper."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_json_durable(path: Path, value: dict):
    """Atomically replace a JSON checkpoint after flushing it to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)



def clone_trial_for_branch(trial):
    """Deep-copy every mutable native tool instance for one isolated branch."""
    cloned=copy.deepcopy(trial)
    original_tools=trial["prepared"]["tool_objects"]
    cloned_tools=cloned["prepared"]["tool_objects"]
    if cloned_tools is original_tools or set(cloned_tools)!=set(original_tools):
        raise ValueError("Native tool registry was not independently cloned")
    if any(cloned_tools[name] is original_tools[name] for name in original_tools):
        raise ValueError("At least one native tool object is shared across branches")
    if cloned["prepared"]["state"] is trial["prepared"]["state"]:
        raise ValueError("Typed checkpoint state was not independently cloned")
    return cloned


def validate_deepcopy_restores(requests,lookup,official_run):
    """Prove four deep-copied branches replay the exact same native prefix."""
    cells={}
    for row in requests:
        cells.setdefault((row["query_id"],row["environment"]),row)
    summaries=[]
    for key,request in sorted(cells.items()):
        base=lookup[key]
        outputs=[]
        clones=[]
        clone_ids=set()
        for arm in ARMS:
            branch=clone_trial_for_branch(base)
            clones.append(branch)
            prepared=branch["prepared"]
            clone_ids.add(id(prepared["tool_objects"]))
            tool=prepared["tool_objects"][request["common_first_action"]]
            result=official_run._execute_tool_simulation(
                tool_obj=tool,arguments_str=request["common_arguments"],
                refinement_level=native.REFINEMENT_LEVEL,
                available_tools=prepared["tool_objects"])
            result_text=str(result)
            if isinstance(result,str) and result.startswith(native.ERROR_PREFIXES):
                raise ValueError(f"Deep-copy branch native replay failed: {key}/{arm}")
            if result_text!=request["common_tool_result"]:
                raise ValueError(f"Deep-copy branch result differs from frozen observation: {key}/{arm}")
            state=set(prepared["state"])
            state.add(tool.output_type)
            state_hash=native.canonical_sha(sorted(state))
            if state_hash!=request["post_action_state_sha256"]:
                raise ValueError(f"Deep-copy branch post-action state mismatch: {key}/{arm}")
            outputs.append((result_text,state_hash))
        if len(clone_ids)!=4 or len(set(outputs))!=1:
            raise ValueError(f"Deep-copy branches are not independent and equivalent: {key}")
        summaries.append({"query_id":key[0],"environment":key[1],
                          "independent_tool_registries":4,
                          "exact_native_result_matches":4,
                          "post_action_state_matches":True})
    return {"cells":len(summaries),"branch_contexts":len(summaries)*4,
            "native_replays":len(summaries)*4,"passed":len(summaries)==10,
            "rows":summaries}


def load_and_validate(requests_path:Path,costbench_root:Path):
    requests=[json.loads(x) for x in requests_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(requests)!=80:
        raise ValueError(f"Expected 80 frozen 2x2 continuation requests, found {len(requests)}")
    ids=[r["trial_id"] for r in requests]
    if len(set(ids))!=80:
        raise ValueError("Duplicate request trial identifiers")
    expected={(q,e,a,rep) for q in TASKS for e in ENVIRONMENTS for a in ARMS for rep in (1,2)}
    actual={(r["query_id"],r["environment"],r["arm"],r["repetition"]) for r in requests}
    if actual!=expected:
        raise ValueError("Request file does not contain the complete frozen 5×2×4×2 matrix")
    trials,cb=confirmation.load_checkpoints(costbench_root.resolve())
    lookup={(t["query_id"],t["environment_condition"]):t for t in trials}
    if len(lookup)!=20:
        raise ValueError("Expected 20 frozen native paired checkpoints")
    group={}
    for r in requests:
        key=(r["query_id"],r["environment"])
        trial=lookup.get(key)
        if trial is None:
            raise ValueError(f"Missing native checkpoint: {key}")
        prepared=trial["prepared"]
        payload=r["payload"]
        if native.canonical_sha(payload)!=r["payload_sha256"]:
            raise ValueError(f"Prompt payload hash mismatch: {r['trial_id']}")
        if payload.get("model")!=native.MODEL or payload.get("temperature")!=0 or payload.get("max_tokens")!=2048:
            raise ValueError(f"Model settings differ from frozen configuration: {r['trial_id']}")
        if trial["source_trial_id"]!=r["source_trial_id"] or prepared["checkpoint_sha256"]!=r["checkpoint_sha256"]:
            raise ValueError(f"Checkpoint provenance mismatch: {r['trial_id']}")
        if native.canonical_sha(payload["tools"])!=r["tool_schema_sha256"]:
            raise ValueError(f"Tool schema hash mismatch: {r['trial_id']}")
        if native.canonical_sha(prepared["tool_interfaces"])!=r["tool_schema_sha256"]:
            raise ValueError(f"Reconstructed native tool schema mismatch: {r['trial_id']}")
        messages=payload["messages"]
        if len(messages)<5 or messages[-2].get("role")!="tool" or messages[-3].get("role")!="assistant":
            raise ValueError(f"Common first-action history is malformed: {r['trial_id']}")
        calls=messages[-3].get("tool_calls") or []
        if len(calls)!=1 or calls[0]["function"]["name"]!=r["common_first_action"]:
            raise ValueError(f"Common assistant tool call mismatch: {r['trial_id']}")
        if calls[0]["function"]["arguments"]!=r["common_arguments"]:
            raise ValueError(f"Common first-action arguments mismatch: {r['trial_id']}")
        if messages[-2].get("content")!=r["common_tool_result"]:
            raise ValueError(f"Common tool observation mismatch: {r['trial_id']}")
        if native.sha_bytes(r["common_tool_result"].encode("utf-8"))!=r["common_tool_result_sha256"]:
            raise ValueError(f"Common tool observation hash mismatch: {r['trial_id']}")
        tool=prepared["tool_objects"].get(r["common_first_action"])
        if tool is None or not set(tool.input_types).issubset(set(prepared["state"])) or tool.output_type==prepared["goal_type"]:
            raise ValueError(f"Frozen common action is not feasible and nonterminal: {r['trial_id']}")
        post_state=set(prepared["state"])
        post_state.add(tool.output_type)
        if native.canonical_sha(sorted(post_state))!=r["post_action_state_sha256"]:
            raise ValueError(f"Post-action state hash mismatch: {r['trial_id']}")
        initial_path=graph.shortest_feasible_path(prepared)
        post_path=graph.shortest_feasible_path({**prepared,"state":post_state})
        if initial_path is None or post_path is None or not post_path[1]:
            raise ValueError(f"Frozen common action leaves no continuation: {r['trial_id']}")
        prefix_loss=float(tool.cost)+float(post_path[0])-float(initial_path[0])
        if abs(prefix_loss-float(r["common_prefix_loss"]))>TOL:
            raise ValueError(f"Common-prefix loss metadata mismatch: {r['trial_id']}")
        if abs(float(initial_path[0])-float(r["initial_optimal_value"]))>TOL or abs(float(post_path[0])-float(r["post_action_optimal_value"]))>TOL:
            raise ValueError(f"Optimal continuation value metadata mismatch: {r['trial_id']}")
        expected_plan=list(post_path[1])
        if r["arm"] in ("B","D") and r.get("updated_plan")!=expected_plan:
            raise ValueError(f"Replacement plan differs from reconstructed graph plan: {r['trial_id']}")
        if (r["arm"] in ("C","D")) != (r.get("initial_ledger") is not None):
            raise ValueError(f"Ledger treatment metadata mismatch: {r['trial_id']}")
        if (r["arm"] in ("B","D")) != (r.get("updated_plan") is not None):
            raise ValueError(f"Plan handoff metadata mismatch: {r['trial_id']}")
        group.setdefault((r["query_id"],r["environment"],r["repetition"]),[]).append(r)
    for key,rows in group.items():
        if len(rows)!=4 or {r["arm"] for r in rows}!=set(ARMS):
            raise ValueError(f"Incomplete four-arm cell: {key}")
        if len({r["payload"]["messages"][:-1][0]["content"] for r in rows})!=1:
            raise ValueError(f"System prompt differs within four-arm cell: {key}")
        if len({r["common_first_action"] for r in rows})!=1 or len({r["common_arguments"] for r in rows})!=1 or len({r["common_tool_result_sha256"] for r in rows})!=1:
            raise ValueError(f"Common action differs within four-arm cell: {key}")
        if len({native.canonical_sha(r["payload"]["messages"][:-1]) for r in rows})!=1:
            raise ValueError(f"Common post-action history differs within four-arm cell: {key}")
        if len({r["tool_schema_sha256"] for r in rows})!=1:
            raise ValueError(f"Native tool schema differs within four-arm cell: {key}")
    clone_preflight=validate_deepcopy_restores(requests,lookup,cb["official_run"])
    if not clone_preflight["passed"]:
        raise ValueError("In-process native branch restoration preflight failed")
    return requests,lookup,cb,clone_preflight


def load_resume_state(resume_dir: Path, requests, effective_cap: int, approved_cap: int, orphaned_reserve: int):
    """Load only a durable completed-trial prefix; refuse to replay an uncertain active trial."""
    resume_dir=Path(resume_dir).resolve()
    response_path=resume_dir/"responses.jsonl"
    ledger_path=resume_dir/"ledger.json"
    if not response_path.is_file() or not ledger_path.is_file():
        raise FileNotFoundError("Resume directory must contain responses.jsonl and ledger.json")
    records=native.read_jsonl(response_path)
    ledger=json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("status")!="incomplete":
        raise ValueError("Only an incomplete, checkpointed run can be resumed")
    if ledger.get("active_trial_id") is not None:
        raise ValueError("The prior run stopped inside a trial; refusing to replay it because provider usage may be duplicated")
    if not records or len(records)>=len(requests):
        raise ValueError("Resume checkpoint must contain a nonempty, incomplete trial prefix")
    expected_ids=[r["trial_id"] for r in requests[:len(records)]]
    actual_ids=[r.get("trial_id") for r in records]
    if actual_ids!=expected_ids:
        raise ValueError("Resume records are not an exact prefix of the frozen trial order")
    for index,(record,request) in enumerate(zip(records,requests)):
        if record.get("payload_sha256")!=request.get("payload_sha256"):
            raise ValueError(f"Resume payload hash mismatch at frozen index {index}")
    if ledger.get("completed_trial_ids")!=expected_ids:
        raise ValueError("Resume ledger completed-trial list does not match saved responses")
    if ledger.get("approved_total_token_cap")!=approved_cap:
        raise ValueError("Resume approved token cap differs from the original run")
    if ledger.get("prior_orphaned_attempt_reserve")!=orphaned_reserve:
        raise ValueError("Resume orphaned-attempt reserve differs from the original run")
    if ledger.get("effective_new_run_token_cap")!=effective_cap:
        raise ValueError("Resume effective token cap differs from the original run")
    charged=int(ledger.get("provider_tokens_charged_this_run") or 0)
    reserved=int(ledger.get("reservation_units_requested_this_run") or 0)
    if charged>effective_cap:
        raise ValueError("Resume ledger exceeds the effective token cap")
    return records,charged,reserved


def current_value(prepared,state):
    result=graph.shortest_feasible_path({**prepared,"state":set(state)})
    return None if result is None else float(result[0])


async def run_one(request,trial,official_run,client,budget,args,event_sink=None):
    prepared=trial["prepared"]
    payload=request["payload"]
    messages=copy.deepcopy(payload["messages"])
    tools=prepared["tool_objects"]
    state=set(prepared["state"])
    common_name=request["common_first_action"]
    common_tool=tools[common_name]
    common_result=official_run._execute_tool_simulation(
        tool_obj=common_tool,arguments_str=request["common_arguments"],
        refinement_level=native.REFINEMENT_LEVEL,available_tools=tools)
    common_text=str(common_result)
    if isinstance(common_result,str) and common_result.startswith(native.ERROR_PREFIXES):
        raise RuntimeError("Frozen common action failed during live branch restoration")
    if common_text!=request["common_tool_result"]:
        raise ValueError("Live branch common-action result differs from frozen exact observation")
    state.add(common_tool.output_type)
    if native.canonical_sha(sorted(state))!=request["post_action_state_sha256"]:
        raise ValueError("Live branch post-action state differs from frozen checkpoint")
    start_value=current_value(prepared,state)
    if start_value is None:
        raise ValueError("No feasible completion exists after the common action")
    initial_state_after_common=sorted(state)
    prefix_cost=float(common_tool.cost)
    ledger=copy.deepcopy(request["initial_ledger"]) if request["arm"] in ("C","D") else None
    plan=request.get("updated_plan") if request["arm"] in ("B","D") else None
    incumbent=request.get("remaining_incumbent_after_common_action") or []
    trace=[]
    tokens=0
    model_calls=0
    provider_outcome_unknown=False
    halt="max_steps"
    plan_cursor=0
    incumbent_cursor=0
    plan_deviated=False
    incumbent_deviated=False
    for step_index in range(1,args.max_steps+1):
        if prepared["goal_type"] in state:
            halt="goal_reached"
            break
        before_state=sorted(state)
        before_value=current_value(prepared,state)
        if event_sink is not None:
            event_sink({
                "event":"model_call_started","trial_id":request["trial_id"],
                "step":step_index,"messages_sha256":native.canonical_sha(messages),
                "charged_tokens_before":budget.charged,
                "reserved_units_before":budget.reserved,
            })
        charged_before=budget.charged
        try:
            response=await native.call_model(client,messages,payload["tools"],"required",args.max_tokens,budget)
        except Exception as exc:
            halt="reservation_cap" if "reservation_cap" in str(exc) else "api_error:"+str(exc)
            charged_delta=max(0,budget.charged-charged_before)
            provider_outcome_unknown=halt.startswith("api_error") and charged_delta==0
            if charged_delta:
                model_calls+=1
                tokens+=charged_delta
            if event_sink is not None:
                event_sink({
                    "event":"model_call_error","trial_id":request["trial_id"],
                    "step":step_index,"error_type":type(exc).__name__,
                    "error":str(exc),"provider_outcome_unknown":halt.startswith("api_error") and charged_delta==0,
                    "charged_tokens_before":charged_before,
                    "charged_tokens_after":budget.charged,
                    "provider_tokens_accounted":charged_delta,
                    "reserved_units_after":budget.reserved,
                })
            break
        model_calls+=1
        call_tokens=int(response.usage.total_tokens)
        tokens+=call_tokens
        msg=response.choices[0].message
        assistant_record=native.assistant_message_dict(msg)
        messages.append(assistant_record)
        if event_sink is not None:
            event_sink({
                "event":"model_response","trial_id":request["trial_id"],
                "step":step_index,"model_reported":getattr(response,"model",None),
                "provider_tokens":call_tokens,"charged_tokens_after":budget.charged,
                "assistant_message":assistant_record,
            })
        calls=msg.tool_calls or []
        if len(calls)!=1:
            halt="no_or_multiple_tool_calls"
            break
        call=calls[0]
        name=call.function.name
        arguments=call.function.arguments
        tool=tools.get(name)
        if tool is None or not set(tool.input_types).issubset(state):
            error_text="[ERROR] Invalid or infeasible native tool action at the current observed state."
            messages.append({"role":"tool","tool_call_id":call.id,"name":name,"content":error_text})
            if event_sink is not None:
                event_sink({
                    "event":"tool_execution","trial_id":request["trial_id"],
                    "step":step_index,"tool":name,"arguments":arguments,
                    "success":False,"output":error_text,
                    "state_before":before_state,"state_after":before_state,
                })
            if ledger is not None:
                ledger=update_ledger(ledger,f"STEP-{step_index:02d}",name,"unknown",error_text,False)
                messages.append({"role":"user","content":"[Updated observed-state ledger]\n"+render_ledger(ledger)})
            trace.append({"step":step_index,"tool":name,"arguments":arguments,"success":False,
                          "cost":None,"output":error_text,"bellman_loss":None,
                          "state_before":before_state,"state_after":before_state})
            halt="invalid_or_infeasible_tool"
            break
        try:
            result=official_run._execute_tool_simulation(
                tool_obj=tool,arguments_str=arguments,
                refinement_level=native.REFINEMENT_LEVEL,available_tools=tools)
            output=str(result)
            success=not (isinstance(result,str) and result.startswith(native.ERROR_PREFIXES))
        except Exception as exc:
            output=f"[ERROR] {type(exc).__name__}: {exc}"
            success=False
        messages.append({"role":"tool","tool_call_id":call.id,"name":name,"content":output})
        if event_sink is not None:
            event_sink({
                "event":"tool_execution","trial_id":request["trial_id"],
                "step":step_index,"tool":name,"arguments":arguments,
                "success":success,"output":output,
                "state_before":before_state,
                "state_after":sorted(set(before_state)|({tool.output_type} if success else set())),
            })
        if not success:
            if ledger is not None:
                ledger=update_ledger(ledger,f"STEP-{step_index:02d}",name,tool.output_type,output,False)
                messages.append({"role":"user","content":"[Updated observed-state ledger]\n"+render_ledger(ledger)})
            trace.append({"step":step_index,"tool":name,"arguments":arguments,"success":False,
                          "cost":float(tool.cost),"output":output,"bellman_loss":None,
                          "state_before":before_state,"state_after":before_state})
            halt="native_tool_execution_error"
            break
        state.add(tool.output_type)
        after_state=sorted(state)
        after_value=current_value(prepared,state)
        delta=None
        if after_value is not None and before_value is not None:
            delta=float(tool.cost)+after_value-before_value
            if delta < -TOL:
                raise ValueError(f"Negative Bellman loss after successful action {name}: {delta}")
            delta=max(0.0,delta)
        matches_plan=(plan is not None and not plan_deviated and plan_cursor<len(plan) and name==plan[plan_cursor])
        matches_incumbent=(not incumbent_deviated and incumbent_cursor<len(incumbent) and name==incumbent[incumbent_cursor])
        trace.append({
            "step":step_index,"tool":name,"arguments":arguments,"success":True,
            "cost":float(tool.cost),"output":output,
            "state_before":before_state,"state_after":after_state,
            "V_before":before_value,"V_after":after_value,
            "bellman_loss":delta,
            "matches_updated_plan_next":matches_plan,
            "matches_incumbent_plan_next":matches_incumbent,
        })
        if plan is not None:
            if matches_plan:
                plan_cursor+=1
            else:
                plan_deviated=True
        if matches_incumbent:
            incumbent_cursor+=1
        else:
            incumbent_deviated=True
        if ledger is not None:
            ledger=update_ledger(ledger,f"STEP-{step_index:02d}",name,tool.output_type,output,True)
            messages.append({"role":"user","content":"[Updated observed-state ledger]\n"+render_ledger(ledger)})
        if after_value is None:
            halt="no_feasible_completion_after_action"
            break
        if prepared["goal_type"] in state:
            halt="goal_reached"
            break
    reached=prepared["goal_type"] in state
    continuation_cost=sum(float(x["cost"]) for x in trace if x.get("success") and x.get("cost") is not None)
    continuation_regret=(continuation_cost-start_value) if reached else None
    if continuation_regret is not None and continuation_regret < -TOL:
        raise ValueError("Realized continuation is cheaper than the graph reference value")
    if continuation_regret is not None:
        continuation_regret=max(0.0,continuation_regret)
    loss_values=[x["bellman_loss"] for x in trace if x.get("bellman_loss") is not None]
    bellman_sum=sum(loss_values)
    if reached and all(x.get("success") for x in trace):
        if abs(bellman_sum-continuation_regret)>TOL:
            raise ValueError("Continuation Bellman losses do not telescope to realized continuation regret")
    common_prefix_loss=float(request["common_prefix_loss"])
    full_regret=(common_prefix_loss+continuation_regret) if continuation_regret is not None else None
    return {
        "trial_id":request["trial_id"],"query_id":request["query_id"],
        "environment":request["environment"],"arm":request["arm"],
        "repetition":request["repetition"],
        "checkpoint_sha256":request["checkpoint_sha256"],
        "payload_sha256":request["payload_sha256"],
        "common_first_action":common_name,
        "common_arguments_sha256":native.sha_bytes(request["common_arguments"].encode("utf-8")),
        "common_tool_result_sha256":request["common_tool_result_sha256"],
        "post_action_state_sha256":request["post_action_state_sha256"],
        "common_prefix_loss":common_prefix_loss,
        "initial_optimal_value_before_common_action":request["initial_optimal_value"],
        "optimal_continuation_value_after_common_action":start_value,
        "executed_continuation":[x["tool"] for x in trace],
        "trace":trace,"goal_reached":reached,"halt_reason":halt,
        "continuation_cost":round(continuation_cost,8),
        "continuation_regret":None if continuation_regret is None else round(max(0.0,continuation_regret),8),
        "continuation_bellman_loss_sum":round(bellman_sum,8),
        "full_path_regret":None if full_regret is None else round(max(0.0,full_regret),8),
        "model_calls":model_calls,"provider_tokens":tokens,
        "provider_outcome_unknown":provider_outcome_unknown,
        "updated_plan":plan,"updated_plan_steps_matched":plan_cursor if plan is not None else None,
        "incumbent_plan":incumbent,"incumbent_steps_matched":incumbent_cursor,
        "ledger_enabled":ledger is not None,"final_ledger":ledger,
    }


def summarize(rows,planned,budget):
    by_arm={}
    for env in ENVIRONMENTS:
        for arm in ARMS:
            subset=[r for r in rows if r["environment"]==env and r["arm"]==arm]
            completed=[r for r in subset if r["continuation_regret"] is not None]
            by_arm[f"{env}/{arm}"]={
                "n":len(subset),
                "goals_reached":sum(r["goal_reached"] for r in subset),
                "exact_optimal_continuations":sum(r["continuation_regret"] is not None and r["continuation_regret"]<=TOL for r in subset),
                "mean_continuation_regret":round(sum(r["continuation_regret"] for r in completed)/len(completed),8) if completed else None,
                "mean_full_path_regret":round(sum(r["full_path_regret"] for r in subset if r["full_path_regret"] is not None)/sum(r["full_path_regret"] is not None for r in subset),8) if any(r["full_path_regret"] is not None for r in subset) else None,
                "mean_provider_tokens":round(sum(r["provider_tokens"] for r in subset)/len(subset),2) if subset else None,
                "model_calls":sum(r["model_calls"] for r in subset),
                "halt_reasons":{reason:sum(r["halt_reason"]==reason for r in subset) for reason in sorted({r["halt_reason"] for r in subset})},
            }
    per_task={}
    for q in TASKS:
        per_task[q]={}
        for env in ENVIRONMENTS:
            for arm in ARMS:
                subset=[r for r in rows if r["query_id"]==q and r["environment"]==env and r["arm"]==arm]
                done=[r["continuation_regret"] for r in subset if r["continuation_regret"] is not None]
                per_task[q][f"{env}/{arm}"]={
                    "n":len(subset),"goals_reached":sum(r["goal_reached"] for r in subset),
                    "mean_continuation_regret":round(sum(done)/len(done),8) if done else None,
                }
    return {
        "status":"complete" if len(rows)==planned else "partial",
        "planned_trajectories":planned,"completed_trajectories":len(rows),
        "base_task_count":len(TASKS),"independent_statistical_unit":"base task (n=5)",
        "arms":list(ARMS),"environment_conditions":list(ENVIRONMENTS),
        "provider_tokens_charged":budget.charged,"reservation_units_requested":budget.reserved,
        "token_cap":budget.cap,"model_calls":sum(r["model_calls"] for r in rows),
        "goal_reached":sum(r["goal_reached"] for r in rows),
        "unknown_provider_outcomes":sum(bool(r.get("provider_outcome_unknown")) for r in rows),
        "by_environment_and_arm":by_arm,"per_task":per_task,
        "note":"Development-screen results on five previously explored tasks; repeats are nested within task and are not independent samples.",
    }


async def run_live(requests,lookup,cb,args):
    from openai import AsyncOpenAI
    key=os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError("Output directory must be empty; do not overwrite prior run records")
    args.out.mkdir(parents=True,exist_ok=True)
    if args.orphaned_attempt_reserve < 0 or args.orphaned_attempt_reserve >= args.cap:
        raise ValueError("orphaned_attempt_reserve must be nonnegative and smaller than cap")
    effective_cap=args.cap-args.orphaned_attempt_reserve
    prior_rows=[]
    prior_charged=0
    prior_reserved=0
    if args.resume_from is not None:
        prior_rows,prior_charged,prior_reserved=load_resume_state(
            args.resume_from,requests,effective_cap,args.cap,args.orphaned_attempt_reserve
        )
    budget=native.TokenBudget(effective_cap,charged=prior_charged,reserved=prior_reserved)
    rows=list(prior_rows)
    events_path=args.out/"call_events.jsonl"
    ledger_path=args.out/"ledger.json"
    if prior_rows:
        with (args.out/"responses.jsonl").open("w",encoding="utf-8") as stream:
            for prior in prior_rows:
                stream.write(json.dumps(prior,ensure_ascii=False,sort_keys=True)+"\\n")
            stream.flush()
            os.fsync(stream.fileno())
        previous_events=args.resume_from/"call_events.jsonl"
        if previous_events.is_file():
            shutil.copyfile(previous_events,events_path)

    def persist_ledger(status, active_trial=None, active_call_count=0, active_trial_tokens=0):
        save_json_durable(ledger_path,{
            "status":status,"completed_trajectories":len(rows),
            "planned_trajectories":len(requests),
            "completed_trial_ids":[r["trial_id"] for r in rows],
            "active_trial_id":active_trial,
            "active_trial_model_responses":active_call_count,
            "active_trial_provider_tokens":active_trial_tokens,
            "provider_tokens_charged_this_run":budget.charged,
            "reservation_units_requested_this_run":budget.reserved,
            "approved_total_token_cap":args.cap,
            "prior_orphaned_attempt_reserve":args.orphaned_attempt_reserve,
            "effective_new_run_token_cap":budget.cap,
            "no_automatic_retries":True,
        })

    persist_ledger("in_progress")
    async with AsyncOpenAI(base_url="https://api.deepseek.com",api_key=key,timeout=args.timeout) as client:
        completed_ids={row["trial_id"] for row in rows}
        for index,request in enumerate(requests,1):
            if request["trial_id"] in completed_ids:
                continue
            trial=clone_trial_for_branch(lookup[(request["query_id"],request["environment"])])
            start=time.monotonic()
            trial_events=[]
            append_jsonl(events_path,{
                "event":"trial_started","trial_id":request["trial_id"],
                "trial_index":index,"planned_trials":len(requests),
                "request_payload_sha256":request["payload_sha256"],
            })

            def event_sink(event):
                trial_events.append(event)
                append_jsonl(events_path,event)
                persist_ledger(
                    "in_progress",request["trial_id"],
                    sum(x["event"]=="model_response" for x in trial_events),
                    sum(int(x.get("provider_tokens") or 0) for x in trial_events),
                )

            try:
                row=await run_one(
                    request,trial,cb["official_run"],client,budget,args,
                    event_sink=event_sink,
                )
            except Exception as exc:
                response_events=[x for x in trial_events if x["event"]=="model_response"]
                row={
                    "trial_id":request["trial_id"],"query_id":request["query_id"],
                    "environment":request["environment"],"arm":request["arm"],
                    "repetition":request["repetition"],"payload_sha256":request["payload_sha256"],
                    "goal_reached":False,
                    "halt_reason":"execution_error:"+str(exc),
                    "model_calls":len(response_events),
                    "provider_tokens":sum(int(x.get("provider_tokens") or x.get("provider_tokens_accounted") or 0) for x in trial_events if x["event"] in ("model_response","model_call_error")),
                    "provider_outcome_unknown":any(x.get("provider_outcome_unknown") for x in trial_events),
                    "continuation_regret":None,
                    "partial_call_events":trial_events,
                }
            row["elapsed_seconds"]=round(time.monotonic()-start,3)
            rows.append(row)
            append_jsonl(args.out/"responses.jsonl",row)
            persist_ledger(
                "incomplete" if len(rows)<len(requests) else "complete",
            )
            print(json.dumps({
                "completed":len(rows),"planned":len(requests),
                "trial_id":request["trial_id"],"goal_reached":row.get("goal_reached"),
                "halt_reason":row.get("halt_reason"),
                "provider_tokens_charged":budget.charged,
            }),flush=True)
            if row.get("halt_reason")=="reservation_cap" or str(row.get("halt_reason","")).startswith("api_error") or str(row.get("halt_reason","")).startswith("execution_error"):
                break
    summary=summarize(rows,len(requests),budget)
    summary.update({
        "approved_total_token_cap":args.cap,
        "prior_orphaned_attempt_reserve":args.orphaned_attempt_reserve,
        "effective_new_run_token_cap":budget.cap,
        "call_event_journal":"call_events.jsonl",
        "resumed_from_completed_trajectories":len(prior_rows),
    })
    save_json_durable(args.out/"summary.json",summary)
    persist_ledger("complete" if len(rows)==len(requests) else "incomplete")
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--requests",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--live",action="store_true")
    p.add_argument("--cap",type=int,default=3443584)
    p.add_argument("--max-tokens",type=int,default=2048)
    p.add_argument("--max-steps",type=int,default=8)
    p.add_argument("--timeout",type=int,default=120)
    p.add_argument("--orphaned-attempt-reserve",type=int,default=0,
                   help="Conservatively reserve part of the approved cap for a prior paid attempt whose usage record was lost.")
    p.add_argument("--resume-from",type=Path,default=None,
                   help="Resume from a prior output directory containing a durable completed-trial prefix.")
    args=p.parse_args()
    if args.max_tokens!=2048:
        p.error("The frozen experiment requires max_tokens=2048")
    requests,lookup,cb,clone_preflight=load_and_validate(args.requests.resolve(),args.costbench_root.resolve())
    preflight={
        "status":"validated_no_provider_calls","provider_calls":0,
        "trajectories":len(requests),"base_tasks":len(TASKS),
        "repetitions":2,"arms":list(ARMS),
        "model":native.MODEL,"max_tokens":args.max_tokens,
    }
    if not args.live:
        print(json.dumps(preflight,ensure_ascii=False,indent=2))
        return
    result=asyncio.run(run_live(requests,lookup,cb,args))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result["status"]!="complete":
        raise SystemExit(2)


if __name__=="__main__":
    main()
