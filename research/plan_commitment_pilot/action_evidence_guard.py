#!/usr/bin/env python3
"""Bounded native pre-action evidence guard (experimental action-level controller).

Pure validator: user facts, previously observed tool args, current input types,
and proposed tool action; never receives gold label, oracle plan or tool output.
"""
import json
from evidence_dependency_refresh import args_of

PREFERENCE_PRODUCERS={
 "Decide_Transportation_Preference",
 "Transportation_Preference_and_Search",
 "Transportation_Full_Planning_to_Step1",
 "Transportation_Full_Planning_to_Step2",
}
def extract_calls(response):
    out=[]
    for choice in (getattr(response,"choices",[]) or []):
        msg=getattr(choice,"message",None)
        for c in getattr(msg,"tool_calls",[]) or []:
            f=getattr(c,"function",None)
            out.append({"tool":getattr(f,"name",None),"arguments":args_of(c)})
    return out

def inspect_action(calls,visible_tools,state_types,ledger,has_refreshed=False):
    """Return only concrete violations, never a suggested optimal path."""
    tool_by_name={item["function"]["name"]:item["function"] for item in visible_tools}
    available=set(state_types)
    invalid=[]
    for call in calls:
        name=call["tool"]
        args=call["arguments"]
        if name not in tool_by_name:
            invalid.append({"code":"not_visible_tool","tool":name})
            continue
        spec=tool_by_name[name]
        required=(spec.get("parameters") or {}).get("required") or []
        # Some native tool parameters are business enum fields, not type objects.
        # Only check parameter types that are *known* current native type names
        # from an observed argument schema or the benchmark type universe.
        typed_requirements=[field for field in required
            if field in {"TransportationPreference","TransportationCandidate_Raw",
                          "TransportationCandidate_L1_Available","TransportationCandidate_L2_Located",
                          "LocationPreference","TimeInfo"}]
        absent=[x for x in typed_requirements if x not in available]
        if absent:
            invalid.append({"code":"missing_native_prerequisite","tool":name,
                            "missing":sorted(absent)})
        if ledger and ledger.get("status")=="changed" and not has_refreshed:
            if name in PREFERENCE_PRODUCERS:
                if args.get("TransportationStyle")!=ledger["new_style"]:
                    invalid.append({"code":"incorrect_updated_fact","tool":name,
                                    "field":"TransportationStyle"})
            else:
                downstream=any(x.startswith("Transportation") and x!="TransportationStyle"
                               for x in (args if isinstance(args,dict) else {}))
                # Do not veto unrelated read-only data gathering. Guard the
                # consumption of stale transportation artifacts specifically.
                keys=set(args) if isinstance(args,dict) else set()
                consumes=bool(keys & {"TransportationPreference",
                    "TransportationCandidate_Raw","TransportationCandidate_L1_Available",
                    "TransportationCandidate_L2_Located"})
                if consumes:
                    invalid.append({"code":"stale_dependency","tool":name,
                                    "field":"TransportationStyle",
                                    "prior":ledger["original_style"],"current":ledger["new_style"]})
    return invalid

def correction_for(violations):
    parts=[]
    for item in violations:
        if item["code"]=="missing_native_prerequisite":
            parts.append("The proposed tool "+str(item["tool"])+
                         " requires missing native state types: "+", ".join(item["missing"])+".")
        elif item["code"]=="stale_dependency":
            parts.append("The proposed tool "+str(item["tool"])+
                         " consumes an old transportation intermediate result. Current style is "+
                         item["current"]+", whereas the observed prior tool was invoked with "+
                         item["prior"]+". Refresh the dependent evidence first.")
        elif item["code"]=="incorrect_updated_fact":
            parts.append("The proposed preference-producing action did not use the current style.")
        else:parts.append("The proposed tool is not in the visible tool catalogue.")
    return ("Pre-execution evidence validation blocked the previous proposed action. "+
            "No tool was executed, and the native state has not changed. "+
            "Please choose a valid next tool using only the currently visible evidence. "+
            "Do not repeat an invalid or stale action. "+" ".join(parts))
