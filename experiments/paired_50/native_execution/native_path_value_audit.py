#!/usr/bin/env python3
"""Offline value/regret audit for the frozen native 50-task cohort; no model calls."""
import argparse, csv, hashlib, heapq, json, math
from collections import Counter, defaultdict
from pathlib import Path

TOL=1e-6

def read_jsonl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]

def sha(x):
    b=json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(b).hexdigest()

def value(tools, state, goal):
    start=frozenset(state); q=[(0.0,0,start,())]; best={start:0.0}; serial=0
    while q:
        cost,_,s,path=heapq.heappop(q)
        if cost>best.get(s,math.inf)+TOL: continue
        if goal in s: return cost,list(path)
        for name in sorted(tools):
            t=tools[name]
            if not set(t["input_types"]).issubset(s) or t["output_type"] in s: continue
            ns=frozenset(set(s)|{t["output_type"]}); nc=cost+float(t["cost"])
            if nc+TOL<best.get(ns,math.inf):
                best[ns]=nc; serial+=1; heapq.heappush(q,(nc,serial,ns,path+(name,)))
    raise ValueError("No path to goal")

def replay(path,tools,state,goal,trace=None):
    s=set(state); total=0.0
    if trace is not None and [x.get("tool_name") for x in trace]!=path: raise ValueError("trace/path mismatch")
    for i,n in enumerate(path):
        if n not in tools: raise ValueError("unknown tool: "+n)
        t=tools[n]; missing=set(t["input_types"])-s
        if missing: raise ValueError(f"infeasible {n}: {sorted(missing)}")
        c=float(t["cost"])
        if trace is not None:
            x=trace[i]
            if x.get("success") is not True or x.get("tool_cost") is None or abs(float(x["tool_cost"])-c)>TOL:
                raise ValueError("trace success/cost mismatch: "+n)
        total+=c; s.add(t["output_type"])
    if goal not in s: raise ValueError("path does not reach goal")
    return total

def run(responses,requests,out):
    rs=read_jsonl(responses); qs=read_jsonl(requests)
    if len(rs)!=100 or len(qs)!=100: raise ValueError("expected exactly 100 requests and responses")
    qmap={x["trial_id"]:x for x in qs}
    if len(qmap)!=100: raise ValueError("duplicate request IDs")
    rows=[]; acts=[]; pairs=defaultdict(dict)
    for r in rs:
        q=qmap[r["trial_id"]]
        if r["request_sha256"]!=sha(q) or r["checkpoint_sha256"]!=q["checkpoint_sha256"]:
            raise ValueError("request/checkpoint hash mismatch: "+r["trial_id"])
        v=json.loads(q["messages"][-1]["content"]); tools=v["current_tools"]; s=set(v["available_types"]); goal=v["goal_type"]
        path=r["executed_path"]; trace=r["trace"]; inc=v["supplied_old_plan_suffix"]; oracle=r["native_optimal_path_audit"]
        actual=replay(path,tools,s,goal,trace); incv=replay(inc,tools,s,goal); ov=replay(oracle,tools,s,goal)
        opt,_=value(tools,s,goal)
        if abs(opt-ov)>TOL: raise ValueError("Dijkstra/native solver mismatch: "+r["trial_id"])
        if abs((incv-opt)-float(r["native_regret_audit"]))>TOL: raise ValueError("incumbent audit mismatch")
        st=set(s); regs=[]
        for i,n in enumerate(path):
            before,_=value(tools,st,goal); t=tools[n]; after_state=st|{t["output_type"]}; after,_=value(tools,after_state,goal)
            reg=float(t["cost"])+after-before
            if reg < -TOL: raise ValueError("negative Bellman regret")
            reg=max(0.0,reg); regs.append(reg)
            acts.append({"query_id":r["query_id"],"condition":r["condition"],"step":i+1,"tool":n,
                         "action_value":float(t["cost"]),"optimal_remaining_before":before,
                         "optimal_remaining_after":after,"step_regret":reg})
            st=after_state
        regret=actual-opt
        if abs(sum(regs)-regret)>1e-5: raise ValueError("Bellman decomposition does not reconcile")
        row={"query_id":r["query_id"],"condition":r["condition"],
             "first_action_prediction":r["first_action_prediction"],
             "trajectory_relation":r["trajectory_relation"],
             "actual_path":" -> ".join(path),"native_optimal_path":" -> ".join(oracle),
             "actual_steps":len(path),"optimal_steps":len(oracle),
             "actual_path_value":actual,"native_optimal_value":opt,"incumbent_value":incv,
             "path_regret":max(0.0,regret),"first_action_regret":regs[0] if regs else 0.0,
             "later_action_regret":sum(regs[1:]),"value_optimal":abs(regret)<=TOL,
             "goal_reached":goal in st}
        rows.append(row); pairs[r["query_id"]][r["condition"]]=row
    if len(pairs)!=50 or any(set(x)!={"RETAIN","SWITCH"} for x in pairs.values()): raise ValueError("incomplete pairs")
    def summary(xs):
        n=len(xs); reg=sum(x["path_regret"] for x in xs); first=sum(x["first_action_regret"] for x in xs); later=sum(x["later_action_regret"] for x in xs)
        return {"n":n,"value_optimal":sum(x["value_optimal"] for x in xs),
                "mean_actual_value":sum(x["actual_path_value"] for x in xs)/n,
                "mean_optimal_value":sum(x["native_optimal_value"] for x in xs)/n,
                "total_regret":reg,"mean_regret":reg/n,"first_regret":first,"later_regret":later,
                "first_regret_share":first/reg if reg else 0,"later_regret_share":later/reg if reg else 0}
    retain=[x for x in rows if x["condition"]=="RETAIN"]; switch=[x for x in rows if x["condition"]=="SWITCH"]
    overlap=Counter((x["first_action_regret"]>TOL,x["later_action_regret"]>TOL) for x in rows)
    paired=Counter(f'RETAIN_{"OPT" if p["RETAIN"]["value_optimal"] else "SUBOPT"}__SWITCH_{"OPT" if p["SWITCH"]["value_optimal"] else "SUBOPT"}' for p in pairs.values())
    result={"base_tasks":50,"trajectories":100,"native_solver_value_crosschecks":100,
            "all_traces_valid":True,"all_goals_reached":all(x["goal_reached"] for x in rows),
            "overall":summary(rows),"retain":summary(retain),"switch":summary(switch),
            "paired_value_outcomes":dict(paired),"pairs_optimal_both":sum(p["RETAIN"]["value_optimal"] and p["SWITCH"]["value_optimal"] for p in pairs.values()),
            "first_vs_later_overlap":{"first_and_later":overlap[(True,True)],"first_only":overlap[(True,False)],
                                      "later_only":overlap[(False,True)],"neither":overlap[(False,False)]},
            "switch_nonoptimal_regret_distribution":dict(Counter(round(x["path_regret"],6) for x in switch if not x["value_optimal"])),
            "retain_nonoptimal":[{"query_id":x["query_id"],"regret":x["path_regret"]} for x in retain if not x["value_optimal"]],
            "switch_value_optimal_queries":[x["query_id"] for x in switch if x["value_optimal"]]}
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    for name,data in [("trajectory_value_audit.csv",rows),("action_regret_decomposition.csv",acts)]:
        with (out/name).open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--responses",required=True); p.add_argument("--requests",required=True); p.add_argument("--out-dir",required=True)
    a=p.parse_args(); run(a.responses,a.requests,a.out_dir)
