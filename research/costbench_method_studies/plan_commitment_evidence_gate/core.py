"""State-Certified Selective Replanning (SCSR), public CostBench tool interface only.

Formal controller, not a prompt variant. The controller owns its incumbent
counterfactual shortest suffix; it never claims the LLM precommitted that path.
All choices depend on the publicly visible tool schema, current native executed
data-type state, and fixed costs. No CostBench groundtruth or future tool outputs.

When a cost change occurs, certify inexpensive RETAIN by an admissible
sensitivity lower bound. Otherwise compare a valid old suffix, a bounded
prefix-preserving LOCAL_REPAIR, and exact FULL_REPLAN. Retain/switch threshold
is frozen before model execution, not fitted to oracle labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappush, heappop
from math import isfinite
import re
import time
from typing import Iterable, Mapping

_COST = re.compile(r"\bThis tool has a cost of ([0-9]+(?:\.[0-9]+)?) units\.")
_OUTPUT = re.compile(r"\bThe output type of this tool is ([A-Za-z][A-Za-z0-9_]*)\.")

@dataclass(frozen=True)
class ToolSpec:
    name: str
    inputs: frozenset[str]
    output: str
    cost: float

@dataclass(frozen=True)
class Path:
    names: tuple[str, ...]
    cost: float
    expansions: int = 0

@dataclass(frozen=True)
class Decision:
    kind: str
    suffix: tuple[str, ...]
    incumbent: tuple[str, ...]
    new_optimal: tuple[str, ...] | None
    old_cost: float
    incumbent_post_cost: float
    selected_post_cost: float
    full_post_cost: float | None
    upper_bound_gain: float | None
    switch_penalty: float
    certificate: str
    old_search_expansions: int
    new_search_expansions: int
    local_search_expansions: int
    planning_wall_seconds: float

def parse_public_tools(interfaces: Iterable[Mapping]) -> dict[str, ToolSpec]:
    """Parse only model-visible OpenAI tool interfaces; no hidden native Tool."""
    result = {}
    for data in interfaces:
        fn = data.get("function", {})
        name = fn.get("name")
        desc = fn.get("description", "")
        cm, om = _COST.search(desc), _OUTPUT.search(desc)
        required = fn.get("parameters", {}).get("required", [])
        if not isinstance(name, str) or not cm or not om or not isinstance(required, list):
            raise ValueError("public tool schema missing cost, name, input or output")
        cost = float(cm.group(1))
        if cost <= 0 or not isfinite(cost):
            raise ValueError("tool costs must be positive and finite")
        if name in result:
            raise ValueError("duplicated public tool name: " + name)
        result[name] = ToolSpec(name, frozenset(required), om.group(1), cost)
    if not result:
        raise ValueError("empty publicly visible tool interface")
    return result

def simulate(state: frozenset[str], names: Iterable[str],
             tools: Mapping[str, ToolSpec]) -> frozenset[str] | None:
    cur = state
    for name in names:
        t = tools.get(name)
        if t is None or not t.inputs <= cur:
            return None
        cur = cur | {t.output}
    return cur

def price(names: Iterable[str], tools: Mapping[str, ToolSpec]) -> float:
    return round(sum(tools[n].cost for n in names), 6)

def shortest(start: frozenset[str], goal: frozenset[str],
             tools: Mapping[str, ToolSpec], max_tools: int = 6) -> Path | None:
    """Exact nonnegative Dijkstra in publicly observable monotone type graph.

    A tool that does not add a type is never useful for the type-reachability
    objective and cannot belong to a minimum-cost positive-price suffix.
    Tie-breaking: total price, number of steps, lexical tool-name path.
    """
    if goal <= start: return Path((), 0., 0)
    if max_tools < 1: return None
    pq = [(0., 0, (), start)]
    best = {(start, 0): (0., ())}
    expansions = 0
    while pq:
        cost, count, path, state = heappop(pq)
        if (cost, path) != best.get((state, count)): continue
        expansions += 1
        if goal <= state:
            return Path(path, round(cost, 6), expansions)
        if count >= max_tools: continue
        for name, t in sorted(tools.items()):
            if not t.inputs <= state or t.output in state: continue
            nxt = state | {t.output}
            value = (round(cost+t.cost, 6), path+(name,))
            key = (nxt, count+1)
            if key not in best or value < best[key]:
                best[key] = value
                heappush(pq,(value[0],count+1,value[1],nxt))
    return None

def local_repair(start: frozenset[str], goal: frozenset[str],
                 incumbent: tuple[str,...], tools: Mapping[str,ToolSpec],
                 max_tools: int) -> Path | None:
    """Prefix-preserving repair: keep >=1 incumbent step, replan a short tail.

    A repaired path is required to share the next observable incumbent tool.
    If alternatives rejoin later, their cheapest bridge can also be considered
    without overwriting successfully obtained data types.
    """
    if len(incumbent) <= 1: return None
    if incumbent[0] not in tools: return None
    first=tools[incumbent[0]]
    if not first.inputs <= start: return None
    after = start | {first.output}
    best: Path | None = None
    tail = shortest(after,goal,tools,max_tools-1)
    if tail is not None:
        path = (incumbent[0],)+tail.names
        if path != incumbent and simulate(start,path,tools) is not None:
            best = Path(path,price(path,tools),tail.expansions)
    # Look for short local bridges that rejoin an original later suffix.
    for idx in range(2,len(incumbent)):
        anchor=simulate(start,incumbent[:idx],tools)
        if anchor is None: continue
        bridge=shortest(after,anchor,tools,min(2,max_tools-1))
        if bridge is None: continue
        candidate=(incumbent[0],)+bridge.names+incumbent[idx:]
        if candidate == incumbent or len(candidate)>max_tools:continue
        endpoint=simulate(start,candidate,tools)
        if endpoint is None or not goal <= endpoint:continue
        p=Path(candidate,price(candidate,tools),bridge.expansions)
        if best is None or (p.cost,len(p.names),p.names)<(best.cost,len(best.names),best.names):
            best=p
    return best

def safe_retain_certificate(old: Mapping[str,ToolSpec],
                            new: Mapping[str,ToolSpec],
                            old_path: Path) -> tuple[bool,float,str]:
    """Exact sensitivity bound on *maximal possible* saving from switching.

    Every optimal path uses each strictly-positive-cost producing tool at most
    once under monotone data-type accumulation. Therefore the sum of all
    price decreases is an upper bound on ANY path's cost reduction. Combined
    with the optimal old suffix, this lower-bounds the unknown new optimum.
    New tools, removed tools or changed IO contracts disable the certificate.
    """
    if set(old)!=set(new):return False,float("inf"),"tool_set_changed"
    if any((a.inputs,a.output)!=(new[n].inputs,new[n].output) for n,a in old.items()):
        return False,float("inf"),"public_dependency_contract_changed"
    if simulate(frozenset(),[],old) is None: raise AssertionError("unreachable")
    discounts=sum(max(0.,old[n].cost-new[n].cost) for n in old)
    incumbent_after=price(old_path.names,new)
    optimistic_new_lower=max(0.,old_path.cost-discounts)
    upper_gain=max(0.,round(incumbent_after-optimistic_new_lower,6))
    return True,upper_gain,"public_cost_sensitivity_lower_bound"

def decide(state: Iterable[str], goal: str,
           old_interface: Iterable[Mapping], new_interface: Iterable[Mapping],
           switch_penalty: float = 0.25, max_tools: int = 5) -> Decision:
    """Choose RETAIN, LOCAL_REPAIR, or FULL_REPLAN with a verifiable certificate.

    The old-cost incumbent is **planner-derived from the actually executed
    state**, not an inferred prior LLM plan. Penalty is an explicit modeled
    switching inconvenience in CostBench cost units, not a paid token charge.
    """
    started=time.perf_counter()
    if switch_penalty < 0 or not isfinite(switch_penalty):
        raise ValueError("invalid replan penalty")
    if max_tools <= 0: raise ValueError("no room for final answer")
    S=frozenset(state); target=frozenset({goal})
    old=parse_public_tools(old_interface)
    new=parse_public_tools(new_interface)
    incumbent=shortest(S,target,old,max_tools)
    if incumbent is None:
        raise ValueError("no feasible predecessor incumbent under public old tools")
    feasible=simulate(S,incumbent.names,new)
    incumbent_new=price(incumbent.names,new) if feasible is not None and target<=feasible else float("inf")
    certified, upper,reason=safe_retain_certificate(old,new,incumbent)
    new_best=None
    full_cost=None
    new_exp=0;local_exp=0
    if certified and incumbent_new< float("inf") and upper <= switch_penalty+1e-9:
        kind="CERTIFIED_RETAIN";suffix=incumbent.names
    else:
        new_best=shortest(S,target,new,max_tools)
        if new_best is None:raise ValueError("no public feasible current suffix")
        full_cost=new_best.cost
        new_exp=new_best.expansions
        local=local_repair(S,target,incumbent.names,new,max_tools)
        local_exp=local.expansions if local else 0
        if incumbent_new <= full_cost+switch_penalty+1e-9:
            kind="RETAIN_WITHIN_MARGIN";suffix=incumbent.names
        elif (local is not None and local.cost<incumbent_new-switch_penalty
              and local.cost<=full_cost+switch_penalty):
            kind="LOCAL_REPAIR";suffix=local.names
        else:
            kind="FULL_REPLAN";suffix=new_best.names
    if simulate(S,suffix,new) is None or not target<=simulate(S,suffix,new):
        raise AssertionError("selected suffix is infeasible under public tools")
    selected=price(suffix,new)
    return Decision(kind,suffix,incumbent.names,
                    new_best.names if new_best else None,
                    incumbent.cost,incumbent_new,selected,full_cost,
                    upper if certified else None,switch_penalty,
                    reason if certified else "requires_current_state_search",
                    incumbent.expansions,new_exp,local_exp,
                    round(time.perf_counter()-started,7))

def baseline_paths(state: Iterable[str],goal: str,
                   old_interface: Iterable[Mapping],new_interface: Iterable[Mapping],
                   max_tools: int=5) -> dict[str, Path|None]:
    S=frozenset(state);G=frozenset({goal})
    old=parse_public_tools(old_interface);new=parse_public_tools(new_interface)
    old_path=shortest(S,G,old,max_tools)
    full=shortest(S,G,new,max_tools)
    local=local_repair(S,G,old_path.names,new,max_tools) if old_path else None
    return {"RETAIN":old_path if old_path and
                 (end:=simulate(S,old_path.names,new)) is not None and G<=end else None,
            "LOCAL_REPAIR":local or old_path,
            "FULL_REPLAN":full}
