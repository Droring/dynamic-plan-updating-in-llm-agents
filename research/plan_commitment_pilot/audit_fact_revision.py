#!/usr/bin/env python3
"""Independent observational action audit for four native fact-revision task pairs.
Does not treat official answer acceptance as semantic correctness.
"""
import json,argparse
from pathlib import Path
CASES={
"Query00271":("comfort_priority","scenic_route"),
"Query00261":("scenic_route","comfort_priority"),
"Query00249":("scenic_route","comfort_priority"),
"Query00306":("comfort_priority","scenic_route"),
}
PREF_TOOLS={"Decide_Transportation_Preference","Transportation_Preference_and_Search",
    "Transportation_Full_Planning_to_Step1","Transportation_Full_Planning_to_Step2"}
def read(root,qid):
    path=(root/"QUERY00271_FACT_REVISION.json" if qid=="Query00271"
      else root/"fact_update_batch"/f"{qid}.json")
    return json.loads(path.read_text(encoding="utf-8"))
def post_calls(record):
    history=[m for m in record["native_conversation_history"] if m["role"]=="assistant"]
    # Every selected native archive has exactly one completed tool turn preceding event.
    calls=[]
    for m in history[1:]:
        for t in m.get("tool_calls") or []:
            if not isinstance(t,dict):
                raise AssertionError("saved tool call must be a scrubbed dict")
            nm=t.get("name") or (t.get("function") or {}).get("name")
            arg=t.get("arguments") or (t.get("function") or {}).get("arguments") or "{}"
            try:arg=json.loads(arg)
            except Exception:arg={}
            calls.append({"name":nm,"arguments":arg})
    return calls

def audit(root):
    records=[];hashes={}
    for qid,(old,new) in CASES.items():
        data=read(root,qid)
        assert data["base_tasks"]==1 and data["correlated_arms"]==4
        assert len(data["results"])==4
        for result in data["results"]:
            event=result["fact_condition"];context=result["commitment_condition"]
            assert event in ("retain","switch") and context in ("committed","neutralized")
            calls=post_calls(result)
            pref=[c for c in calls if c["name"] in PREF_TOOLS and
                  isinstance(c["arguments"],dict) and "TransportationStyle" in c["arguments"]]
            target=old if event=="retain" else new
            first=calls[0] if calls else None
            updated_first=(bool(pref) and bool(first)
                 and pref[0]["name"]==first["name"] and pref[0]["arguments"]["TransportationStyle"]==new)
            if event=="switch":
                behavioral_correct=updated_first
            else:
                # No redundant repeated preference; previously observed preference retained.
                behavioral_correct=not pref and bool(first)
            messages=[m for m in result["native_conversation_history"] if m["role"]=="tool"]
            post_outputs=[(m.get("content") or "") for m in messages[1:]]
            bad=sum(x.startswith(("[ERROR]","Tool execution failed","Error:")) for x in post_outputs)
            rec={"task":qid,"event":event,"context":context,
                "first_post_event_tool":first["name"] if first else None,
                "reissued_target_preference_in_first_action":updated_first,
                "behavioral_first_action_correct":bool(behavioral_correct),
                "first_new_preference_value":pref[0]["arguments"].get("TransportationStyle") if pref else None,
                "failed_post_event_tool_outputs":bad,
                "goal_type_reached":result["goal_state_reached"],
                "official_final_answer_accepted":result["official_final_answer_accepted"],
                "status":result["status"],"api_calls":result["provider_calls_after_checkpoint"]}
            records.append(rec)
            hashes.setdefault(qid,[]).append((result["original_checkpoint_hash"],
                                             result["checkpoint_native_state_digest"],
                                             result["tool_interface_digest"]))
    assert len(records)==16
    for task,triples in hashes.items():
        assert len(triples)==4
        for dimension in range(3):
            assert len({tuple_[dimension] for tuple_ in triples})==1,(task,dimension)
    out={"schema":"fact-revision-independent-observable-action-audit-v1",
      "independent_development_tasks":len(CASES),"real_continuations":len(records),
      "real_provider_calls":sum(r["api_calls"] for r in records),
      "switch_first_action_correct":sum(r["behavioral_first_action_correct"] for r in records if r["event"]=="switch"),
      "switch_arms":sum(r["event"]=="switch" for r in records),
      "retain_first_action_correct":sum(r["behavioral_first_action_correct"] for r in records if r["event"]=="retain"),
      "retain_arms":sum(r["event"]=="retain" for r in records),
      "switch_goal_reached":sum(r["goal_type_reached"] is True for r in records if r["event"]=="switch"),
      "switch_complete_executions":sum(r["status"]=="executed" for r in records if r["event"]=="switch"),
      "execution_errors_switch":sum(r["failed_post_event_tool_outputs"] for r in records if r["event"]=="switch"),
      "warnings":["Native CostBench goal-state and original-answer scorer do not validate the newly changed user preference.",
                  "A correctly updated next action is not necessarily a successful final plan.",
                  "One task can have four correlated arms; count tasks, not arms, as independent observations.",
                  "No original plan-commitment causal effect has been established."],
      "records":records}
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--evidence-root",type=Path,default=Path("research/plan_commitment_pilot/evidence"))
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    report=audit(a.evidence_root)
    if a.out:
        if a.out.exists():raise FileExistsError("do not overwrite audit")
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("FACT_REVISION_AUDIT "+json.dumps({k:report[k] for k in ("independent_development_tasks","real_continuations","real_provider_calls","switch_first_action_correct","switch_arms","retain_first_action_correct","retain_arms","switch_goal_reached","execution_errors_switch")},sort_keys=True))
