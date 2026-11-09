#!/usr/bin/env python3
"""Official CostBench native paired tool-removal experiment (one development task).
Two matched post-event removal conditions x two authorship-context conditions.
The native tool loop executes all actions; only its available-tools provider is
intervened on, AFTER the archived checkpoint. This is a NEW removal event
following the original native cost_change event, NOT an upstream ban_tool replay.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PHASE=ROOT/"research/costbench_method_studies/plan_commitment_evidence_gate"
sys.path.insert(0,str(PHASE))
import policy_pilot as pilot
from replay_gate import load_dev80,load_dynamic,canonical

TASK="Query00271"
INCUMBENT="Transportation_Search_Planning_to_Step2"
UNRELATED="Transportation_Search_to_Final_4Steps"
PLAN_OLD="I’ll use the atomic preference decision first, then the cheapest composite covering search plus both refinement steps, followed by the final selection."
PLAN_NEUTRAL="One potential sequence is an atomic preference decision followed by a composite search/refinement and final selection."

def digest(messages):
    return hashlib.sha256(canonical([pilot.scrub_message(m) for m in messages]).encode()).hexdigest()

def tool_name(call):
    if isinstance(call,dict):
        fn=call.get("function") or {}
        return call.get("name") or (fn.get("name") if isinstance(fn,dict) else getattr(fn,"name",None))
    return getattr(call,"name",None) or getattr(getattr(call,"function",None),"name",None)

async def experiment(costbench_root,out,call_cap,preflight):
    if not preflight and not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("MISSING_DEEPSEEK_API_KEY")
    if out.exists():raise FileExistsError("never overwrite result file")
    sys.path.insert(0,str(costbench_root.resolve()))
    import env.run as official
    from env.utils.blocker import DynamicBlocker
    queries=load_dev80()
    archive=load_dynamic()[TASK]
    gates={r["query_id"]:r for r in json.loads((PHASE/"REPLAY_GATE.json").read_text())["tasks"]}
    gate=gates[TASK]
    if gate["status"]!="replay_matched_checkpoint":raise AssertionError("uncertified checkpoint")
    if archive["block_stats"]["block_count_agent"]!=1:raise AssertionError("event was not observed")

    results=[]
    # Match across environment and history conditions with one archived native prefix.
    arms=[("retain","committed"),("switch","committed"),
          ("retain","neutralized"),("switch","neutralized")]
    prior=Path.cwd()
    original_visible=DynamicBlocker.get_visible_tools
    original_fork=pilot.ForkedCompletions
    try:
        os.chdir(costbench_root.resolve())
        for event,context in arms:
            removed=UNRELATED if event=="retain" else INCUMBENT
            baseline_snapshot={}
            def controlled_visibility(blocker,tools):
                visible=original_visible(blocker,tools)
                if blocker.blocked_count>=1:
                    baseline_snapshot["unfiltered_names"]=sorted(t.name for t in visible)
                    visible=[t for t in visible if t.name!=removed]
                    baseline_snapshot["filtered_names"]=sorted(t.name for t in visible)
                return visible

            class ControlledFork(original_fork):
                async def create(self,*,messages,tools,**kwargs):
                    if self.step==self.trigger_step and not self.entered:
                        self.original_digest=digest(messages)
                        self.original_model_tool_names=baseline_snapshot.get("unfiltered_names",[])
                        if INCUMBENT not in self.original_model_tool_names or UNRELATED not in self.original_model_tool_names:
                            raise AssertionError("both tools must be in original post-event interface")
                        assert removed not in [t["function"]["name"] for t in tools]
                        assert INCUMBENT in [t["function"]["name"] for t in tools] or event=="switch"
                        self.expected_tools_digest=hashlib.sha256(canonical(tools).encode()).hexdigest()
                        self.modified_public_tools_digest=self.expected_tools_digest
                        if context=="neutralized":
                            matches=[m for m in messages if m.get("role")=="assistant" and PLAN_OLD in (m.get("content") or "")]
                            if len(matches)!=1:raise AssertionError("missing exact self-plan utterance")
                            matches[0]["content"]=matches[0]["content"].replace(PLAN_OLD,PLAN_NEUTRAL,1)
                        self.modified_history_digest=digest(messages)
                        # Report actual tool unavailability without giving any correct answer.
                        messages.append({"role":"user","content":
                            "Tool availability update: "+removed+
                            " is unavailable for subsequent calls. Use only tools currently available. "
                            "Already executed actions and tool outputs remain valid."})
                    if preflight and self.step==self.trigger_step:
                        # Preserve all replay checks, then stop before any provider request.
                        try:
                            return await super().create(messages=messages,tools=tools,**kwargs)
                        except RuntimeError:
                            raise
                    return await super().create(messages=messages,tools=tools,**kwargs)

            DynamicBlocker.get_visible_tools=controlled_visibility
            pilot.ForkedCompletions=ControlledFork
            try:
                if preflight:
                    # Use an offline token to instantiate AsyncOpenAI but never make an API request.
                    os.environ.setdefault("DEEPSEEK_API_KEY","OFFLINE_ONLY_NO_NETWORK")
                    class OfflineControlledFork(ControlledFork):
                        async def create(self,*,messages,tools,**kwargs):
                            if self.step==self.trigger_step:
                                self.original_digest=digest(messages)
                                self.original_model_tool_names=baseline_snapshot.get("unfiltered_names",[])
                                if INCUMBENT not in self.original_model_tool_names or UNRELATED not in self.original_model_tool_names:
                                    raise AssertionError("original tools absent at native event checkpoint")
                                if removed in [t["function"]["name"] for t in tools]:
                                    raise AssertionError("removed tool still advertised")
                                if context=="neutralized":
                                    if sum(PLAN_OLD in (m.get("content") or "") for m in messages if m.get("role")=="assistant")!=1:
                                        raise AssertionError("model-authored plan absent")
                                self.entered=True
                                self.original_digest=digest(messages)
                                self.fork_public_tools_sha256=hashlib.sha256(canonical(tools).encode()).hexdigest()
                                raise RuntimeError("OFFLINE_PREFLIGHT_COMPLETED")
                            return await super().create(messages=messages,tools=tools,**kwargs)
                    pilot.ForkedCompletions=OfflineControlledFork
                row,track,status=await pilot.run_case(official,archive,queries[TASK],"native_continue",gate,call_cap)
            finally:
                DynamicBlocker.get_visible_tools=original_visible
                pilot.ForkedCompletions=original_fork
            if preflight:
                if not track.entered or "OFFLINE_PREFLIGHT_COMPLETED" not in str(track.failure_types):
                    # native runner catches the intentionally raised sentinel.
                    if not track.entered:raise AssertionError("native checkpoint not reached")
                results.append({"environment":event,"context":context,"removed_tool":removed,
                  "checkpoint_reached":track.entered,
                  "unmodified_history_digest":getattr(track,"original_digest",None),
                  "unfiltered_tools":baseline_snapshot.get("unfiltered_names"),
                  "visible_tools":baseline_snapshot.get("filtered_names")})
                continue
            result=pilot.execution_summary(official,row,track,context,status,gate["tool_state_digest"])
            assistant=[m for m in row.get("conversation_history",[]) if m.get("role")=="assistant"]
            next_turn=assistant[track.trigger_step] if len(assistant)>track.trigger_step else {}
            first=[tool_name(t) for t in (next_turn.get("tool_calls") or [])]
            result.update({"environment":event,"context":context,"removed_tool":removed,
                "first_post_event_tools":first,
                "retained_incumbent_first_action":INCUMBENT in first,
                "invalid_banned_call_requested":removed in first,
                "unmodified_history_digest":getattr(track,"original_digest",None),
                "original_unfiltered_tools":getattr(track,"original_model_tool_names",None),
                "modified_history_digest":getattr(track,"modified_history_digest",None)})
            results.append(result)
            if 402 in (result.get("provider_failure_status_codes") or []):
                raise RuntimeError("DEEPSEEK_API_HTTP_402_HALT")
    finally:
        DynamicBlocker.get_visible_tools=original_visible
        pilot.ForkedCompletions=original_fork
        os.chdir(prior)
    for event in ("retain","switch"):
        pair=[r for r in results if r["environment"]==event]
        if len(pair)!=2:raise AssertionError("incomplete history pair")
        if len({p["unmodified_history_digest"] for p in pair})!=1:
            raise AssertionError("original history differs within environment")
    if len({r["unmodified_history_digest"] for r in results})!=1:
        raise AssertionError("original checkpoint history differs across environment scenarios")
    if not preflight:
        if len({r["checkpoint_native_state_digest"] for r in results})!=1:
            raise AssertionError("native checkpoint state mismatch")
        for e in ("retain","switch"):
            if len({r["tool_interface_digest"] for r in results if r["environment"]==e})!=1:
                raise AssertionError("tool interface mismatch within event/history pair")
        if len({r["tool_interface_digest"] for r in results})!=2:
            raise AssertionError("environment intervention did not change the tool interface")
    payload={"schema":"native-removal-paired-commitment-gate-v1",
        "task":TASK,"independent_tasks":1,"condition_arms":len(results),
        "live_provider_calls":0 if preflight else sum(r["provider_calls_after_checkpoint"] for r in results),
        "preflight":preflight,
        "event_definition":{"retain":"Unrelated tool unavailable; incumbent still executable",
                            "switch":"Original promised next tool unavailable; alternative must be chosen"},
        "warning":"One-task feasibility diagnostic. A post-checkpoint additional tool-removal event is injected into the official CostBench native tool availability provider. This is not the upstream ban_tool event or a balanced independent benchmark. No label appears in the model-visible prompt.",
        "results":results}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False,default=str)+"\n",encoding="utf-8")
    print("PAIRED_NATIVE_GATE "+json.dumps({"preflight":preflight,"arms":len(results),
        "live_provider_calls":payload["live_provider_calls"],
        "first_actions":[(r["environment"],r["context"],r.get("first_post_event_tools")) for r in results]}))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--call-cap",type=int,default=3)
    a=p.parse_args()
    if not 1<=a.call_cap<=3:raise ValueError("max 3 calls/arm")
    asyncio.run(experiment(a.costbench_root.resolve(),a.out.resolve(),a.call_cap,a.preflight))
