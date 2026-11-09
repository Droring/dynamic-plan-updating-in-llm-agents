#!/usr/bin/env python3
"""Evidence-Dependency Refresh (EDR) prototype: observe -> invalidate -> verify.

User fact inputs and previous tool arguments are the sole source of differences.
No known correct action, scenario label, test answer, or candidate optimal path
is required. This does NOT mutate CostBench's internal semantic state.
"""
from __future__ import annotations
import json
import re

STYLE=re.compile(r"Current transportation style preference:\s*([a-z][a-z0-9_]*)",re.I)
TOOL_NAME="Decide_Transportation_Preference"
PREFIX="Transportation"
def args_of(call):
    if not isinstance(call,dict):
        c=getattr(call,"function",None)
        data=getattr(c,"arguments",None)
    else:
        fn=call.get("function") or {}
        data=call.get("arguments") or fn.get("arguments")
    if isinstance(data,dict):return data
    try:return json.loads(data) if data else {}
    except (ValueError,TypeError):return {}
def historical_style(history):
    """Extract from the actual, observed, earlier tool invocation; never from task gold."""
    values=[]
    for message in history:
        if message.get("role")!="assistant":continue
        for call in message.get("tool_calls") or []:
            args=args_of(call)
            if "TransportationStyle" in args:
                values.append(args["TransportationStyle"])
    return values[-1] if values else None

def build_ledger(history,fact,state_types,public_tools):
    match=STYLE.search(fact)
    if not match:
        return {"status":"unknown","reason":"current style not parsed",
                "original_style":historical_style(history),"new_style":None,"intervention":None}
    new_style=match.group(1)
    old_style=historical_style(history)
    if not old_style:
        return {"status":"unknown","reason":"cannot verify prior style provenance",
                "original_style":None,"new_style":new_style,"intervention":None}
    changed=new_style!=old_style
    if changed:
        intervention=(
          "Execution evidence check (derived from the actual prior tool arguments and the new user fact): "
          f"the previous preference tool call used TransportationStyle={old_style}; the current user fact is "
          f"TransportationStyle={new_style}. A preference result produced by the earlier call does not establish "
          "the current preference. Before taking any dependent action, obtain an updated preference result using "
          "the new user fact. Check that each next tool's required input types are actually available. "
          "Do not reuse the old preference result merely because it remains a valid-looking identifier. "
          "Use the available tools to proceed; do not assume a particular final plan."
        )
    else:
        intervention=(
          "Execution evidence check (derived from actual prior tool arguments and the current user fact): "
          f"TransportationStyle remains {new_style}. The prior preference result is not invalidated by this fact. "
          "Continue using already verified evidence where tool prerequisites remain satisfied; do not "
          "repeat a preference decision solely because a status message was received."
        )
    return {"status":"changed" if changed else "unchanged",
      "reason":"observed prior tool arguments compared with current user fact",
      "original_style":old_style,"new_style":new_style,
      "current_types":sorted(state_types),
      "visible_tool_names":[t["function"]["name"] for t in public_tools],
      "intervention":intervention}
