#!/usr/bin/env python3
"""Gate same-conversation native checkpoint replay through official CostBench.run_single_query.

No self-built tool execution or model calls. The official Agent loop performs
tool simulation, cost-change blocking, and state updates. A shim ONLY returns
archived assistant turns before the event, verifies the re-executed native tool
observations, and halts on the next model request. Model responses are never
generated or selected by this feasibility test.
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
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/"research/costbench_method_studies/official_dev_baseline/evidence"
DYNAMIC_FILE="results_deepseek-flash_blocked-cost_change-1_refinement_2.json"

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))

class ReachedCheckpoint(Exception):
    pass

class AttrDict(dict):
    """Attribute-compatible, JSON-serializable native tool-call record."""
    __getattr__=dict.__getitem__

class ReplayCompletions:
    def __init__(self,archive,trigger_step):
        self.expected=[m for m in archive["conversation_history"] if m["role"]=="assistant"][:trigger_step]
        self.expected_tools=[m for m in archive["conversation_history"] if m["role"]=="tool"][:trigger_step]
        self.step=0
        self.trigger_step=trigger_step
        self.fork_public_tools_sha256=None
        self.first_public_tools_sha256=None
        self.model_calls=0
        self.mismatches=[]

    async def create(self,*,messages,tools,**kwargs):
        # CostBench may make several API requests; the shim never contacts a provider.
        if self.first_public_tools_sha256 is None:
            self.first_public_tools_sha256=hashlib.sha256(canonical(tools).encode()).hexdigest()
        tool_msgs=[m for m in messages if m.get("role")=="tool"]
        if len(tool_msgs)!=self.step:
            self.mismatches.append("tool_response_count")
            raise AssertionError("official loop did not replay one tool per archived assistant step")
        for i,(seen,expected) in enumerate(zip(tool_msgs,self.expected_tools)):
            if seen.get("content")!=expected.get("content"):
                self.mismatches.append("native_tool_observation_mismatch_at_"+str(i))
                raise AssertionError("native CostBench tool output changed at prefix step "+str(i))
        if self.step==self.trigger_step:
            self.fork_public_tools_sha256=hashlib.sha256(canonical(tools).encode()).hexdigest()
            raise ReachedCheckpoint("replayed observed native prefix, stopping before API request")
        assistant=self.expected[self.step]
        tool_calls=[]
        for i,call in enumerate(assistant.get("tool_calls") or []):
            tool_calls.append(AttrDict(
                id="call_"+hashlib.sha256(f"{self.step}:{i}:{call['name']}".encode()).hexdigest()[:24],
                type="function",
                function=AttrDict(name=call["name"],arguments=call["arguments"])))
        if len(tool_calls)!=1:
            raise AssertionError("event-reaching archived prefix must have one native call per turn")
        self.step+=1
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=assistant.get("content"),tool_calls=tool_calls))])
        return response

class OfflineClient:
    def __init__(self,completion):
        self.chat=SimpleNamespace(completions=completion)

def native_args(upstream,query_path):
    cfg=upstream.CONFIG
    d=dict(
       tool_creation_seed=42,
       tool_output_dir=cfg.paths.tool_output_dir,
       refinement_level=2,
       changed_tool_output_dir=cfg.paths.changed_tool_output_dir,
       max_tool_steps=7,tool_mode="memory",
       min_atomic_cost=15,max_atomic_cost=25,noise_std=0.1,
       use_blocker=True,block_mode="cost_change",block_num=1,
       control_tool_length=False,max_tool_length=cfg.tool_defaults.max_tool_length,
       ban_longest_tool=True,query_path=str(query_path),
       model_name="deepseek-flash",temperature=0,max_tokens=8192,
       start_index=0,end_index=1,num_threads=1,
       output_dir="/tmp/native_replay_unused",require_goal_state=False,
       print_tool_interface=False,use_example=False,
       provide_composite_concept=False,provide_atomic_tool_sequence=False,
       use_stimulation=False,stimulation_num=0,
       vis_stimulation=False,greedy=False,vis_agent=False,vis_gt=False,
       rerun_failed_queries=False,failed_index_path=None)
    return SimpleNamespace(**d)

def load_dev80():
    queries={}
    for i in range(4):
        path=BASE/"inputs"/f"shard{i:02d}.json"
        for q in json.loads(path.read_text(encoding="utf-8")):
            qid=q["query_id"].strip("<>")
            if qid in queries:raise AssertionError("duplicate base task")
            queries[qid]=q
    if len(queries)!=80:raise AssertionError("wrong 80-task development inputs")
    return queries

def load_dynamic():
    result={}
    for i in range(4):
        path=BASE/"results/official_cost_change"/f"shard{i:02d}"/DYNAMIC_FILE
        for q in json.loads(path.read_text(encoding="utf-8"))["results"]:
            qid=q["query_id"].strip("<>")
            if qid in result:raise AssertionError("duplicate dynamic task")
            result[qid]=q
    if len(result)!=80:raise AssertionError("wrong dynamic outputs")
    return result

async def run_gate(costbench_root:Path,only_ids=None):
    sys.path.insert(0,str(costbench_root.resolve()))
    import env.run as official
    queries=load_dev80()
    dynamic=load_dynamic()
    if set(queries)!=set(dynamic):raise AssertionError("task membership mismatch")
    gate_records=[]
    for qid in sorted(dynamic):
        if only_ids and qid not in only_ids: continue
        record=dynamic[qid]
        bs=record.get("block_stats") or {}
        if bs.get("block_count_agent")!=1:
            gate_records.append({"query_id":qid,"status":"not_observed_pre_event","tool_state_digest":None})
            continue
        k=bs["block_step"][0]
        c=ReplayCompletions(record,k)
        client=OfflineClient(c)
        q=copy.deepcopy(queries[qid])
        seed=official._stable_int(f"42:{q['query_id']}")
        if seed!=record.get("tool_creation_seed"):
            raise AssertionError("official tool initialization seed changed")
        args=native_args(official,BASE/"inputs/manifest.json")
        try:
            returned=await official.run_single_query(client,q,args,0,seed)
        except Exception as e:
            gate_records.append({"query_id":qid,"status":"runner_exception",
               "reason":type(e).__name__+":"+str(e)[:180],
               "replayed_calls":c.step,"tool_state_digest":c.fork_public_tools_sha256})
            continue
        actual=(returned.get("block_stats") or {}).get("block_count_agent")
        observed_metadata=bs.get("metadata") or []
        generated_metadata=(returned.get("block_stats") or {}).get("metadata") or []
        # Upstream discards a cost-change event from the EFFECTIVE event count
        # when the run is interrupted immediately after it (trigger_step+1 >= total_steps).
        # This replay intentionally stops on the first post-event model request.
        # Verify event parameters and the changed model-visible tool snapshot instead.
        changed_tools=(c.fork_public_tools_sha256 is not None and
                       c.first_public_tools_sha256 is not None and
                       c.fork_public_tools_sha256!=c.first_public_tools_sha256)
        same_event=(bool(generated_metadata and observed_metadata)
                    and generated_metadata[0]["parameters"]==observed_metadata[0]["parameters"]
                    and generated_metadata[0]["trigger_step"]==observed_metadata[0]["trigger_step"]
                    and changed_tools)
        status="replay_matched_checkpoint" if (
            c.step==k and c.fork_public_tools_sha256 is not None
            and not c.mismatches and same_event) else "replay_unmatched"
        gate_records.append({"query_id":qid,"status":status,
          "replayed_calls":c.step,"required_prefix_steps":k,
          "same_dynamic_event":bool(same_event),
          "reported_effective_event_count_after_forced_stop":actual,
          "public_tools_changed_at_event":bool(changed_tools),
          "initial_public_tools_sha256":c.first_public_tools_sha256,
          "archived_event_metadata":observed_metadata[:1],
          "replayed_event_metadata":generated_metadata[:1],
          "tool_state_digest":c.fork_public_tools_sha256,
          "mismatches":c.mismatches,
          "runner_status":returned.get("status")})
    counts={}
    for r in gate_records:counts[r["status"]]=counts.get(r["status"],0)+1
    return {"schema":"phase2b-official-native-replay-gate-v1",
            "official_commit":"6424069f3f773ade076bcedbed302ed47cfb1837",
            "provider_calls":0,
            "tool_execution":"original env.run.run_single_query",
            "counts":counts,"tasks":gate_records,
            "scope":"existing 80 dev tasks, observed dynamic prefix replay only",
            "limitations":["A successful replay verifies archived prefix tool messages and event-tool interface; it does not demonstrate policy superiority.",
               "Independent strategy arms must replay the exact same cached conversation and verify digest equality before evaluating outcomes."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--queries",nargs="*")
    args=p.parse_args()
    if args.out.exists():raise FileExistsError("no result overwrite")
    original=Path.cwd()
    try:
        os.chdir(args.costbench_root.resolve())
        result=asyncio.run(run_gate(args.costbench_root.resolve(),set(args.queries) if args.queries else None))
    finally:
        os.chdir(original)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print("OFFICIAL_NATIVE_REPLAY_GATE "+json.dumps(result["counts"],sort_keys=True))
    return 0 if result["counts"].get("runner_exception",0)==0 else 2

if __name__=="__main__":
    raise SystemExit(main())
