#!/usr/bin/env python3
"""Recompute four-task matched native fact-update contrast from real histories.
Distinguish semantic first-step update from technical tool precondition failure.
No LLM calls, no hidden-state inference and no stale original answer scoring.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILE1=ROOT/"evidence/NATIVE_FACT_SALIENCE.json"
FILE2=ROOT/"evidence/NATIVE_FACT_SALIENCE_REPLICATE2.json"

def get_first_tool_result(record):
    history=record.get("native_conversation_history") or []
    prompt=record["user_fact"]
    inserts=[i for i,m in enumerate(history) if m.get("role")=="user" and m.get("content")==prompt]
    if len(inserts)!=1:raise AssertionError("cannot locate unique injected user fact")
    post=history[inserts[0]+1:]
    first=next((m for m in post if m.get("role")=="assistant" and m.get("tool_calls")),None)
    if not first:return {"tool":None,"result":None,"error":True}
    calls=first["tool_calls"]
    first_call=calls[0]
    name=first_call.get("name") or (first_call.get("function") or {}).get("name")
    key=first_call.get("id")
    response=next((m.get("content","") for m in post if m.get("role")=="tool" and m.get("tool_call_id")==key),None)
    bad=response is None or response.startswith(("[ERROR]","Tool execution failed","Error:"))
    return {"tool":name,"result":response[:350] if response else response,"error":bad}

def audit():
    result=[]
    for path in (FILE1,FILE2):
        raw=json.loads(path.read_text())
        assert raw["independent_development_tasks"]==2
        assert raw["correlated_continuations"]==8
        for row in raw["results"]:
            first=get_first_tool_result(row)
            result.append({"task":row["task"],"fact_condition":row["fact_condition"],
                "factual_explicitness":row["factual_explicitness"],
                "first_action_update_correct":bool(row["first_action_correct"]),
                "first_tool_execution_valid":not first["error"],
                "first_action_overall_correct":bool(row["first_action_correct"] and not first["error"]),
                "first_tool":first["tool"],"first_tool_result_excerpt":first["result"],
                "provider_calls":row["provider_calls_after_checkpoint"],
                "status":row["status"],
                "original_checkpoint_digest":row["original_checkpoint_digest"],
                "native_state_digest":row["checkpoint_native_state_digest"],
                "tool_interface_digest":row["tool_interface_digest"]})
    assert len(result)==16
    ids=set(x["task"] for x in result)
    assert len(ids)==4
    for q in ids:
        group=[x for x in result if x["task"]==q]
        assert len(group)==4
        assert len({x["original_checkpoint_digest"] for x in group})==1
        assert len({x["native_state_digest"] for x in group})==1
        assert len({x["tool_interface_digest"] for x in group})==1
    table={}
    for event in ("retain","switch"):
        for clarity in ("minimal_fact","explicit_temporal_update"):
            group=[x for x in result if x["fact_condition"]==event and x["factual_explicitness"]==clarity]
            assert len(group)==4
            table[event+"__"+clarity]={
                "tasks":len(group),
                "preference_update_correct":sum(x["first_action_update_correct"] for x in group),
                "first_native_tool_valid":sum(x["first_tool_execution_valid"] for x in group),
                "overall_first_action_correct":sum(x["first_action_overall_correct"] for x in group)}
    return {"schema":"four-task-native-fact-salience-reaudit-v1",
        "independent_tasks":4,"correlated_continuations":16,
        "provider_calls":sum(x["provider_calls"] for x in result),
        "matched_checkpoint_per_task":True,
        "table":table,"records":result,
        "conclusion_boundary":[
          "Explicit temporal update includes a reason explaining that the old preference result belongs to the former user request; it is not a mere paraphrase length control.",
          "The silent minimal condition is not a pure lack-of-notice: the current preference value changes, but the relation to the old result is left implicit.",
          "One retain arm produced an invalid tool invocation despite correctly not reissuing preference; overall correctness must count this as a failure.",
          "No model internal commitment mechanism is proven, and the four cases are selected development tasks.",
          "Original CostBench goal checker cannot validate the new preference semantic outcome." ]}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    if a.out.exists():raise FileExistsError("do not overwrite")
    result=audit()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print("FACT_SALIENCE_AUDIT",json.dumps({"tasks":result["independent_tasks"],"arms":result["correlated_continuations"],"calls":result["provider_calls"],"table":result["table"]},sort_keys=True))
