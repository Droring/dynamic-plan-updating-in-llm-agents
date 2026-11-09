#!/usr/bin/env python3
"""Build five new CostBench paired tasks to complete the unified 50-task dataset, using CostBench but NO model API.

All checkpoints/plans here are deterministic oracle-derived counterfactual fixtures,
NOT archived or newly committed LLM plans. The initial state is the matched checkpoint.
Run with an external pinned CostBench checkout. Never edit frozen post-hoc records.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import random
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPSTREAM_SHA = "6424069f3f773ade076bcedbed302ed47cfb1837"
SELECTION_SEED = 0x013528F5  # fixed deterministic selection seed
CATEGORIES = ("transportation", "accommodation", "attraction", "dining", "shopping")
EXCLUDED = [1,5,6,13,14,17,18,21,33,47,65,76,94,115,130,147,178,188,227,229,236,238,240,312,329,347,351,403,425,440,466,477,489,494,518,549,576,590,598,610,624,658,662,685,689,705,706,740,761,766,790,798,851,858,867,898,916,933,941,944,967]
# Includes every task already represented in the merged source archive and earlier probes.
D = lambda x: Decimal(str(x))
ROUND = Decimal("0.01")
MARGIN = Decimal("1.00")
EPS = Decimal("0.00001")
SYSTEM = (
    "You are evaluating a supplied plan in a tool-dependency cost graph. "
    "Use only the visible current type state, tool input/output types, and current tool costs. "
    "RETAIN means the provided suffix is still minimum execution-cost under the current "
    "tools (ties are RETAIN). SWITCH means a strictly cheaper type-feasible suffix exists. "
    "Do not consider LLM tokens, replanning latency or business validity. "
    "Reply ONLY as a JSON object with one field: "
    '{"intervention":"RETAIN"} or {"intervention":"SWITCH"}.'
)


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def cents(x):
    return D(x).quantize(ROUND, rounding=ROUND_HALF_UP)


def compact(tools):
    return {name: {"input_types": list(t["input_types"]), "output_type": t["output_type"],
                   "cost": t["cost"]} for name, t in sorted(tools.items())}


def walk(state, path, tools):
    state = set(state)
    for name in path:
        if name not in tools or not set(tools[name]["input_types"]).issubset(state):
            raise ValueError("type-infeasible old plan: " + name)
        state.add(tools[name]["output_type"])
    return state


def path_cost(path, tools):
    return sum((D(tools[name]["cost"]) for name in path), Decimal(0))


def pure_dijkstra(tools, start, goal):
    """Independent Decimal shortest-path check under the SAME type-set abstraction."""
    initial = frozenset(start)
    serial = 0
    pq = [(Decimal(0), 0, initial)]
    dist = {initial: Decimal(0)}
    while pq:
        cost, _, state = heapq.heappop(pq)
        if cost != dist[state]:
            continue
        if goal in state:
            return cost
        for tool in tools.values():
            output = tool["output_type"]
            if output in state or not set(tool["input_types"]).issubset(state):
                continue
            next_state = frozenset(state | {output})
            next_cost = cost + D(tool["cost"])
            if next_cost < dist.get(next_state, Decimal("Infinity")):
                dist[next_state] = next_cost
                serial += 1
                heapq.heappush(pq, (next_cost, serial, next_state))
    return None


def native(solver_cls, tools, state, goal):
    try:
        result = solver_cls(tools).solve(current_state=set(state), goal_types={goal})
        return D(result.total_cost), list(result.tools)
    except Exception as exc:
        if type(exc).__name__ == "NoPathFoundError":
            return None, []
        raise


def cost_variant(tools, name, amount):
    out = {n: dict(t) for n, t in tools.items()}
    out[name]["cost"] = float(amount)
    return out


def check_pair(pair, solver_cls):
    st, goal, path = pair["checkpoint"]["types"], pair["goal_type"], pair["incumbent_suffix"]
    orig = pair["baseline_tools"]
    if goal in st or not path or goal not in walk(st, path, orig):
        raise ValueError("invalid checkpoint / suffix")
    if sha(pair["checkpoint"]) != pair["checkpoint_sha256"]:
        raise ValueError("checkpoint hash mismatch")
    a, b = pair["conditions"]
    if [a["name"], b["name"]] != ["RETAIN", "SWITCH"]:
        raise ValueError("wrong order")
    for row in (a, b):
        altered = cost_variant(orig, pair["changed_tool"], row["changed_price"])
        diffs = [n for n in orig if orig[n] != altered[n]]
        if diffs != [pair["changed_tool"]]:
            raise ValueError("more than one changed tool")
        if goal not in walk(st, path, altered):
            raise ValueError("suffix lost type feasibility")
        old_cost = path_cost(path, altered)
        result, _ = native(solver_cls, altered, st, goal)
        independent = pure_dijkstra(altered, st, goal)
        if result is None or independent is None or abs(result - independent) > EPS:
            raise ValueError("oracle vs independent Decimal disagreement")
        regret = old_cost - independent
        if row["name"] == "RETAIN" and abs(regret) > EPS:
            raise ValueError("retain condition not optimal")
        if row["name"] == "SWITCH" and regret + EPS < MARGIN:
            raise ValueError("switch margin below 1.00")
        if row["name"] == "RETAIN" and regret < -EPS:
            raise ValueError("negative regret")
        if abs(D(row["oracle_cost"])-independent)>EPS or abs(D(row["old_cost"])-old_cost)>EPS:
            raise ValueError("recorded costs mismatch")
    if (a["changed_price"] - pair["original_price"]) * (b["changed_price"] - pair["original_price"]) <= 0:
        raise ValueError("direction confound within pair")


def try_orientation(solver_cls, q, tools, state, path, direction):
    goal = q["goal_type"]
    old = path_cost(path, tools)
    possibilities = []
    for banned in path:
        alt, alt_path = native(solver_cls, {n:t for n,t in tools.items() if n != banned}, state, goal)
        if alt is None or not alt_path:
            continue
        gap = alt - old
        if gap < Decimal("0.10"):
            continue
        if direction == "up":
            changes = [banned]
        else:
            changes = [n for n in alt_path if n not in path]
        for tool in changes:
            price = D(tools[tool]["cost"])
            if not price.is_finite() or price <= 0:
                continue
            desired = cents(gap + Decimal("1.30"))
            small = max(Decimal("0.01"), cents(gap * Decimal("0.25")))
            if direction == "up":
                # Exclude extreme >100% price increases; both conditions are increases.
                if desired > price:
                    continue
                new_retain = cents(price + small)
                new_switch = cents(price + desired)
            else:
                # Both conditions are decreases; avoid negative / near-zero prices.
                if desired > price * Decimal("0.80"):
                    continue
                new_retain = cents(price - small)
                new_switch = cents(price - desired)
            if new_retain <= 0 or new_switch <= 0 or new_retain == new_switch:
                continue
            if direction == "up" and new_retain >= new_switch:
                continue
            if direction == "down" and new_retain <= new_switch:
                continue
            possibilities.append((float(desired/price), tool, new_retain, new_switch))
    possibilities.sort(key=lambda row:(row[0],row[1]))
    for _, tool, retain_price, switch_price in possibilities:
        rows = []
        good = True
        for label, amount in (("RETAIN",retain_price),("SWITCH",switch_price)):
            env = cost_variant(tools, tool, amount)
            result, _ = native(solver_cls, env, state, goal)
            if result is None:
                good = False
                break
            actual_old = path_cost(path, env)
            regret = actual_old - result
            if (label == "RETAIN" and abs(regret)>EPS) or (label == "SWITCH" and regret < MARGIN):
                good = False
                break
            rows.append({"name":label, "changed_price":float(amount),
                         "old_cost":float(actual_old), "oracle_cost":float(result),
                         "regret":float(regret), "environment_sha256":sha(compact(env))})
        if good:
            return tool, rows
    return None


def relevant_tools(tools, state, goal):
    """Cost-independent forward/reverse reachability filter for a full public tool catalog."""
    reach = set(state)
    changed = True
    while changed:
        earlier = len(reach)
        for t in tools.values():
            if set(t["input_types"]).issubset(reach):
                reach.add(t["output_type"])
        changed = len(reach) != earlier
    if goal not in reach:
        raise ValueError("unreachable goal")
    backwards = {goal}
    changed = True
    while changed:
        earlier = len(backwards)
        for t in tools.values():
            if t["output_type"] in backwards and set(t["input_types"]).issubset(reach):
                backwards.update(t["input_types"])
        changed = len(backwards) != earlier
    # Keep every tool which can participate in a type-relevant path, including alternatives.
    return {n:t for n,t in sorted(tools.items())
            if t["output_type"] in backwards and set(t["input_types"]).issubset(reach)}


def create_request(pair, label):
    row = next(z for z in pair["conditions"] if z["name"] == label)
    tools = cost_variant(pair["baseline_tools"], pair["changed_tool"], row["changed_price"])
    question = {
        "task_id":pair["query_id"], "task":pair["task"],
        "user_request":pair["user_request"], "available_types":pair["checkpoint"]["types"],
        "goal_type":pair["goal_type"], "supplied_old_plan_suffix":pair["incumbent_suffix"],
        "current_tools": compact(relevant_tools(tools,pair["checkpoint"]["types"],pair["goal_type"])),
    }
    return {"trial_id":sha({"qid":pair["query_id"],"side":label,"seed":SELECTION_SEED})[:20],
            "query_id":pair["query_id"],"checkpoint_sha256":pair["checkpoint_sha256"],
            "messages":[{"role":"system","content":SYSTEM},
                        {"role":"user","content":json.dumps(question,ensure_ascii=False,sort_keys=True)}],
            "response_format":{"type":"json_object"}}


def generate(costbench_root, source, limit_per_category=1):
    sys.path.insert(0,str(costbench_root))
    from env.domains.travel.tool_registry import tools_ready_in_memory
    from env.utils.solver import GroundtruthSolver
    queries=json.loads(source.read_text(encoding="utf-8"))
    selected=[]
    attempts=Counter()
    rejection=Counter()
    for category in CATEGORIES:
        candidates=[q for q in queries
                    if q.get("task")==category and q.get("is_valid")==1
                    and int(q["query_id"].strip("<>").replace("Query","")) not in EXCLUDED
                    and int(q["query_id"].strip("<>").replace("Query",""))>33]
        rng=random.Random(SELECTION_SEED+CATEGORIES.index(category))
        rng.shuffle(candidates)
        accepted={"up":0,"down":0}
        accepted_count=0
        for q in candidates:
            if accepted_count >= limit_per_category:
                break
            query_id=q["query_id"].strip("<>")
            numeric=int(query_id.replace("Query",""))
            attempts[category]+=1
            try:
                registry=tools_ready_in_memory(refinement_level=2,ban_longest_tool=True,
                                               random_seed=200000+numeric)["tools"]
                tools=registry
                solver=GroundtruthSolver(tools)
                state=set(solver._infer_initial_state(category))
                goal=q["goal_type"]
                basic,incumbent=native(GroundtruthSolver,tools,state,goal)
                if basic is None or not incumbent:
                    rejection["no_initial_path"]+=1
                    continue
                # Freeze the type state after the first tool if it leaves a nonempty suffix.
                prefix=incumbent[:1] if len(incumbent)>=2 else []
                state=walk(state,prefix,tools)
                suffix=incumbent[len(prefix):]
                if not suffix or goal in state:
                    rejection["empty_suffix"]+=1
                    continue
                c, path=native(GroundtruthSolver,tools,state,goal)
                if abs(c-path_cost(suffix,tools))>EPS:
                    rejection["baseline_path_not_optimal"]+=1
                    continue
                preferred="up" if CATEGORIES.index(category)%2==0 else "down"
                orientation_order=[preferred,"down" if preferred=="up" else "up"]
                for orientation in orientation_order:
                    if accepted[orientation]>= (2 if orientation == ("up" if CATEGORIES.index(category)%2==0 else "down") else 1):
                        continue
                    outcome=try_orientation(GroundtruthSolver,q,tools,state,suffix,orientation)
                    if outcome is None:
                        rejection["no_"+orientation+"_pair"]+=1
                        continue
                    changed,rows=outcome
                    checkpoint={"types":sorted(state),"prefix":prefix,"source":"oracle_derived_type_state",
                                "query_id":query_id,"task":category}
                    p={"query_id":query_id,"task":category,"goal_type":goal,
                       "user_request":q["query"]["input"],"registry_seed":200000+numeric,
                       "checkpoint":checkpoint,"checkpoint_sha256":sha(checkpoint),
                       "incumbent_suffix":suffix,"incumbent_source":"CostBench_oracle_not_model_precommit",
                       "original_price":tools[changed]["cost"],"changed_tool":changed,
                       "price_direction":orientation,"baseline_tools":tools,"conditions":rows}
                    check_pair(p,GroundtruthSolver)
                    selected.append(p)
                    accepted[orientation]+=1
                    accepted_count+=1
                    break
                else:
                    rejection["no_admissible_orientation"]+=1
            except (ValueError,KeyError,OverflowError) as exc:
                rejection[type(exc).__name__+":"+str(exc)[:65]]+=1
        if accepted_count!=limit_per_category:
            raise RuntimeError(f"category={category}: only {accepted_count}/{limit_per_category}; "+
                               f"attempts={attempts[category]}, reasons={dict(rejection)}")
    if len(selected)!=len(CATEGORIES)*limit_per_category:
        raise AssertionError("wrong number of unique base tasks")
    if len({x["query_id"] for x in selected}) != len(selected):
        raise AssertionError("duplicate base task")
    if len(selected) != 5:
        raise AssertionError("the extension must contain exactly five new base tasks")
    return selected, attempts, rejection, source


def write_outputs(pairs,attempts,rejected,source,out):
    out.mkdir(parents=True,exist_ok=True)
    # Everything needed to independently reconstruct the oracle and pair inputs.
    public={"format":"unified_50_extension_counterfactual_5_v1","upstream_sha":UPSTREAM_SHA,
            "source_repo":"JiayuJeff/CostBench",
            "source_query_file":"env/data/runtime/queries/queries.json",
            "source_query_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
            "selection_seed":SELECTION_SEED, "pairs":pairs}
    (out/"pairs.json").write_text(json.dumps(public,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    order=[]
    manifest=[]
    rng=random.Random(SELECTION_SEED)
    switch_first=set(rng.sample(range(len(pairs)),len(pairs)//2))
    for idx,p in enumerate(pairs):
        conditions=["SWITCH","RETAIN"] if idx in switch_first else ["RETAIN","SWITCH"]
        for label in conditions:
            req=create_request(p,label)
            order.append(req)
            manifest.append({"trial_id":req["trial_id"],"query_id":p["query_id"],
                             "condition":label,"request_sha256":sha(req),
                             "checkpoint_sha256":p["checkpoint_sha256"]})
    with (out/"model_requests.jsonl").open("w",encoding="utf-8") as f:
        for req in order:
            f.write(json.dumps(req,ensure_ascii=False,sort_keys=True)+"\n")
    (out/"trial_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={
        "status":"offline_validated_no_model_calls",
        "base_tasks":len(pairs), "conditions":len(order),
        "category_counts":dict(Counter(x["task"] for x in pairs)),
        "direction_counts":dict(Counter(x["price_direction"] for x in pairs)),
        "first_condition_counts":dict(Counter(manifest[i]["condition"] for i in range(0,len(manifest),2))),
        "queries":[p["query_id"] for p in pairs],
        "attempts":dict(attempts),"rejected_candidates":dict(rejected),
        "minimum_switch_margin":min(p["conditions"][1]["regret"] for p in pairs),
        "all_retain_regrets":[p["conditions"][0]["regret"] for p in pairs],
        "precommitted_llm_plans":0,"model_calls":0,"budget_charged":0,
        "limitations":"Synthetic oracle-derived initial/prefix checkpoints; no LLM precommit, "
                      "no complete business-state match, no online adaptation; "
                      "two-sided same-sign cost perturbations reduce but do not remove "
                      "price-magnitude shortcuts. Pairs are not full real-world tasks."
    }
    (out/"REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--costbench-root",type=Path,required=True)
    parser.add_argument("--source",type=Path)
    parser.add_argument("--out",type=Path,default=HERE/"generated")
    args=parser.parse_args()
    root=args.costbench_root.resolve()
    source=args.source or root/"env/data/runtime/queries/queries.json"
    if not source.is_file():
        raise FileNotFoundError("Official CostBench queries.json not present: "+str(source))
    pairs, attempts, rejected, src=generate(root,source)
    write_outputs(pairs,attempts,rejected,src,args.out)
    print("Independent Decimal audit: ALL PAIRS VERIFIED")

if __name__=="__main__":
    main()
