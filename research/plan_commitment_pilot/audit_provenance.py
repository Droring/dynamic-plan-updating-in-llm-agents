#!/usr/bin/env python3
"""Trace old/new preference provenance through actual native CostBench tool outputs.

This tool does not infer semantic validity from the original official answer scorer.
Only explicit, observable dependency provenance is credited. No API calls.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TASKS={
 "Query00271":("comfort_priority","scenic_route"),
 "Query00261":("scenic_route","comfort_priority"),
 "Query00249":("scenic_route","comfort_priority"),
 "Query00306":("comfort_priority","scenic_route"),
}
TOKEN=re.compile(r"<?(?:TransportationPreference|TransportationCandidateSet|TransportationCandidate)[0-9]+>?")
PREFTOOLS={"Decide_Transportation_Preference",
           "Transportation_Preference_and_Search",
           "Transportation_Full_Planning_to_Step1",
           "Transportation_Full_Planning_to_Step2"}
def load(q):
    path=ROOT/"evidence"/("QUERY00271_FACT_REVISION.json" if q=="Query00271" else f"fact_update_batch/{q}.json")
    return json.loads(path.read_text(encoding="utf-8"))

def calls(history):
    byid={}
    events=[]
    for m in history:
        if m["role"]=="assistant":
            for c in m.get("tool_calls") or []:
                nm=c.get("name")
                args=c.get("arguments") or "{}"
                try:args=json.loads(args)
                except (ValueError,TypeError):args={}
                e={"name":nm,"arguments":args,"call_id":c.get("id"),"output":None}
                events.append(e)
                if c.get("id"):byid[c["id"]]=e
        elif m["role"]=="tool":
            target=byid.get(m.get("tool_call_id"))
            if target is not None:target["output"]=m.get("content","")
    return events

def evaluate(rec,q,old,new):
    raw=rec["native_conversation_history"]
    event=rec["fact_condition"];target=old if event=="retain" else new
    hist_calls=calls(raw)
    # Last pre-event tool call count is 1 in each frozen base task.
    allas=[m for m in raw if m.get("role")=="assistant"]
    if not allas or not allas[0].get("tool_calls"):raise AssertionError("missing pre-event tool call")
    # Cross-check prefix against original checkpoint: event preceded by the
    # first native call in every frozen development case.
    prior=hist_calls[0]
    post=hist_calls[1:]
    own=[c for c in post if c["name"] in PREFTOOLS and c["arguments"].get("TransportationStyle")==target]
    first=post[0] if post else None
    corrected=(event=="switch" and first is not None and bool(own) and first is own[0])
    old_correct=(event=="retain" and not any(c["name"] in PREFTOOLS for c in post))
    # Track candidate instances that appear in fresh preference-producing
    # tool outputs, and separately track subsequent inputs and selected output.
    producing=own[0] if own else None
    prefoutput=(producing or {}).get("output") or ""
    generated_tokens=set(TOKEN.findall(prefoutput))
    downstream=[c for c in post if c is not producing]
    used_tokens=set()
    for c in downstream:
        for value in c["arguments"].values():
            if isinstance(value,str):used_tokens|=set(TOKEN.findall(value))
    outputs=[c.get("output") or "" for c in post]
    selected=[c for c in post if c["name"]=="Select_Final_Transportation"]
    errors=[c for c in post if (c.get("output") or "").startswith(("[ERROR]","Tool execution failed","Error:"))]
    # A matching numeric suffix is evidence of candidate ancestry but NOT proof
    # the target preference is semantically enforced by the simulator.
    suffixes={re.search(r"(\d+)\>?",tok).group(1) for tok in generated_tokens if re.search(r"(\d+)\>?",tok)}
    downstream_suffixes={re.search(r"(\d+)\>?",tok).group(1) for tok in used_tokens if re.search(r"(\d+)\>?",tok)}
    return {"task":q,"event":event,"context":rec["commitment_condition"],
            "target_style":target,"original_pref_tool":prior["name"],
            "first_post_event_tool":first["name"] if first else None,
            "first_update_correct":corrected if event=="switch" else old_correct,
            "first_updated_pref_tool":producing["name"] if producing else None,
            "fresh_pref_output_ids":sorted(generated_tokens),
            "downstream_input_ids":sorted(used_tokens),
            "observed_id_lineage_overlap":bool(suffixes&downstream_suffixes),
            "final_selection_tool_called":bool(selected),
            "tool_errors":[{"tool":x["name"],"output":x.get("output")} for x in errors],
            "provider_cap_or_error":rec["status"]!="executed",
            "goal_type_reached":rec["goal_state_reached"],
            "semantic_goal_verified":False,
            "semantic_goal_status":"NOT_VERIFIABLE_WITH_ORIGINAL_COSTBENCH_ORACLE"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():raise FileExistsError("audit path must be new")
    records=[]
    for q,(old,new) in TASKS.items():
        x=load(q)
        for rec in x["results"]:
            records.append(evaluate(rec,q,old,new))
    assert len(records)==16
    switch=[r for r in records if r["event"]=="switch"]
    retain=[r for r in records if r["event"]=="retain"]
    report={"schema":"native-fact-revision-execution-provenance-audit-v1",
         "independent_tasks":4,"real_native_continuations":16,"new_provider_calls":0,
         "correct_switch_first_action":sum(r["first_update_correct"] for r in switch),
         "correct_retain_first_action":sum(r["first_update_correct"] for r in retain),
         "switch_lineage_overlap":sum(r["observed_id_lineage_overlap"] for r in switch),
         "switch_final_select_tool_called":sum(r["final_selection_tool_called"] for r in switch),
         "switch_tool_errors":sum(len(r["tool_errors"]) for r in switch),
         "semantic_success_claims":0,
         "limitations":["Numeric identifier lineage is an observable dataflow proxy, not a semantic truth predicate.",
                        "The original task oracle is stale for changed user preferences.",
                        "A first-action update alone cannot prove fully correct re-planning.",
                        "This is an exploratory reused development cohort, not independent validation."],
         "records":records}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print("PROVENANCE_AUDIT "+json.dumps({k:report[k] for k in
          ("independent_tasks","real_native_continuations","correct_switch_first_action","correct_retain_first_action","switch_lineage_overlap","switch_final_select_tool_called","switch_tool_errors","semantic_success_claims")},sort_keys=True))
if __name__=="__main__":main()
