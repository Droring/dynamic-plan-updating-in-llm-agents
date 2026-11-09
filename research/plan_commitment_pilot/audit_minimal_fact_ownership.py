#!/usr/bin/env python3
"""Independent original native log audit: minimal fact x plan-authorship.
Recompute arguments, user fact change, actual first tool response, and paired accuracy.
"""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STYLES={
"Query00271":("comfort_priority","scenic_route"),
"Query00306":("comfort_priority","scenic_route"),
"Query00261":("scenic_route","comfort_priority"),
"Query00249":("scenic_route","comfort_priority")}
PREFTOOLS={"Decide_Transportation_Preference","Transportation_Preference_and_Search",
 "Transportation_Full_Planning_to_Step1","Transportation_Full_Planning_to_Step2"}

def first_tool(row):
    h=row["native_conversation_history"]
    idx=[i for i,m in enumerate(h) if m.get("role")=="user" and m.get("content")==row["event_user_message"]]
    if len(idx)!=1:raise AssertionError("exact intervention message missing")
    after=h[idx[0]+1:]
    a=next((m for m in after if m.get("role")=="assistant" and m.get("tool_calls")),None)
    if not a:return None,None,None
    call=a["tool_calls"][0]
    nm=call.get("name") or (call.get("function") or {}).get("name")
    args=call.get("arguments") or (call.get("function") or {}).get("arguments") or "{}"
    if isinstance(args,str):args=json.loads(args)
    resp=next((m.get("content") for m in after if m.get("role")=="tool" and m.get("tool_call_id")==call.get("id")),None)
    return nm,args,resp

def audit():
    records=[]
    for q,(old,new) in STYLES.items():
        raw=json.loads((ROOT/"evidence/minimal_fact_ownership"/f"{q}.json").read_text())
        assert raw["base_tasks"]==1 and raw["correlated_arms"]==4
        matched=set()
        for z in raw["results"]:
            cond=z["fact_condition"];hist=z["commitment_condition"]
            expected=old if cond=="retain" else new
            nm,args,resp=first_tool(z)
            valid=resp is not None and not resp.startswith(("[ERROR]","Tool execution failed","Error:"))
            update=nm in PREFTOOLS and args.get("TransportationStyle")==new if args else False
            keep=bool(nm) and nm not in PREFTOOLS
            behavior=(update if cond=="switch" else keep)
            records.append({"task":q,"fact_condition":cond,"history":hist,
                "first_tool":nm,"first_arguments":args,
                "first_tool_response_excerpt":resp[:300] if resp else None,
                "tool_call_valid":valid,"first_update_decision_correct":behavior,
                "first_action_overall_correct":behavior and valid,
                "original_checkpoint_hash":z["original_checkpoint_hash"],
                "native_state_digest":z["checkpoint_native_state_digest"],
                "tool_interface_digest":z["tool_interface_digest"],
                "status":z["status"],"provider_calls":z["provider_calls_after_checkpoint"]})
            matched.add((cond,hist))
        assert len(matched)==4
        group=[r for r in records if r["task"]==q]
        for field in ("original_checkpoint_hash","native_state_digest","tool_interface_digest"):
            assert len({x[field] for x in group})==1,(q,field)
    assert len(records)==16
    table={}
    for hist in ("committed","neutralized"):
        for cond in ("retain","switch"):
            grp=[x for x in records if x["history"]==hist and x["fact_condition"]==cond]
            assert len(grp)==4
            table[f"{hist}__{cond}"]={
              "n":4,"first_decision_correct":sum(x["first_update_decision_correct"] for x in grp),
              "valid_first_tool":sum(x["tool_call_valid"] for x in grp),
              "first_action_correct":sum(x["first_action_overall_correct"] for x in grp)}
    pairs={}
    for hist in ("committed","neutralized"):
        pairs[hist]=sum(
          all(any(r["task"]==q and r["history"]==hist and r["fact_condition"]==c and r["first_action_overall_correct"]
                  for r in records) for c in ("retain","switch"))
          for q in STYLES)
    return {"schema":"native-minimal-fact-ownership-independent-audit-v1",
     "unique_development_tasks":4,"correlated_live_trajectories":16,
     "real_model_calls":sum(x["provider_calls"] for x in records),
     "results":table,"paired_task_correct":pairs,"records":records,
     "warnings":["Neutralizing prospective authorial words does not erase plan contents or tool history.",
       "Causal contrast holds native checkpoint and minimal new user message identical within task.",
       "No model-internal cause can be inferred; use observed next tools and arguments.",
       "Original CostBench final answer scorer is stale for newly changed user preference."]}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    if a.out.exists():raise FileExistsError("no overwriting")
    x=audit()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(x,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print("MINIMAL_FACT_OWNERSHIP_AUDIT",json.dumps({"results":x["results"],"pairs":x["paired_task_correct"]},sort_keys=True))
