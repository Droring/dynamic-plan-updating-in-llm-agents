#!/usr/bin/env python3
"""Frozen 5-task/25-call mechanism discrimination.
Independent masked-price alternative generation, then matched original-vs-candidate
decision calls. The candidate is NOT oracle-chosen, never gold-labelled, and
held identical across RETAIN/SWITCH for the same base task.

DO NOT use as a native-agent or model-self-commitment evaluation.
"""
import argparse
import hashlib
import json
import os
import time
import urllib.request
import urllib.error
from collections import defaultdict, Counter
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a/generated"
CATS=("transportation","accommodation","attraction","dining","shopping")
OUT=ROOT/"research/plan_commitment_pilot/evidence/mechanism_probe"
MAX_CALLS=25
MAX_TOKENS_TOTAL=70000

def canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def sha(x):return hashlib.sha256(x).hexdigest()
def lines(p):return [json.loads(t) for t in p.read_text(encoding="utf-8").splitlines() if t.strip()]

def legal(q,path):
    if not isinstance(path,list) or not path or any(not isinstance(t,str) for t in path):
        return False,None,"not_nonempty_tool_list"
    state=set(q["available_types"])
    total=Decimal(0)
    for name in path:
        tool=q["current_tools"].get(name)
        if tool is None:return False,None,"unknown_tool"
        if not set(tool["input_types"]).issubset(state):return False,None,"missing_precondition"
        state.add(tool["output_type"])
        total+=Decimal(str(tool["cost"]))
    if q["goal_type"] not in state:return False,None,"goal_not_reached"
    return True,total,None

def make():
    requests=lines(SOURCE/"model_requests.jsonl")
    manifest=json.loads((SOURCE/"trial_manifest.json").read_text(encoding="utf-8"))
    m={x["trial_id"]:x for x in manifest}
    grouped=defaultdict(dict);bycat=defaultdict(list)
    for t in requests:
        assert t["trial_id"] in m and t["query_id"]==m[t["trial_id"]]["query_id"]
        q=json.loads(t["messages"][-1]["content"])
        category=q["task"];qid=t["query_id"]
        if qid not in bycat[category]:bycat[category].append(qid)
        grouped[qid][m[t["trial_id"]]["condition"]]=t
    selected=[bycat[cat][2] for cat in CATS]
    assert len(selected)==len(set(selected))==5
    # Verify same predecessor state, goal, old suffix and topology in paired arms.
    data=[]
    for qid in selected:
        pair=grouped[qid]
        assert set(pair)=={"RETAIN","SWITCH"}
        a=json.loads(pair["RETAIN"]["messages"][-1]["content"])
        b=json.loads(pair["SWITCH"]["messages"][-1]["content"])
        for k in ("available_types","goal_type","supplied_old_plan_suffix","task","user_request"):
            assert a[k]==b[k],(qid,k)
        ta=a["current_tools"];tb=b["current_tools"]
        assert ta.keys()==tb.keys()
        for name in ta:
            for k in ("input_types","output_type"):
                assert ta[name][k]==tb[name][k]
        # Construct a topology-only task. No prices, no label, no solution.
        masked=json.loads(canon(a))
        for tool in masked["current_tools"].values():tool.pop("cost",None)
        sysmessage=("You are checking possible future tool actions in a dependency graph. "
            "No tool prices or outcome labels are shown. Supply ONE type-feasible, goal-reaching "
            "alternative suffix that is DIFFERENT from the supplied old suffix, if possible. "
            "Use only named tools and the visible current type state. Output JSON only: "
            "{\"alternative_suffix\":[\"tool names\"]}. If none found output an empty list. "
            "Do not guess costs, do not label RETAIN or SWITCH.")
        gen=[{"role":"system","content":sysmessage},
             {"role":"user","content":canon(masked)}]
        data.append({"query_id":qid,"task":a["task"],
          "conditions":{k:pair[k] for k in ("RETAIN","SWITCH")},
          "generator_messages":gen,
          "generator_sha256":sha(canon(gen).encode())})
    return data

def provider(messages,max_tokens=320):
    payload={"model":"deepseek-flash","messages":messages,"temperature":0,
      "thinking":{"type":"disabled"},"response_format":{"type":"json_object"},
      "max_tokens":max_tokens,"stream":False}
    request=urllib.request.Request("https://api.deepseek.com/chat/completions",
      data=canon(payload).encode(),method="POST",
      headers={"Authorization":"Bearer "+os.environ["DEEPSEEK_API_KEY"],
        "Content-Type":"application/json"})
    with urllib.request.urlopen(request,timeout=95) as response:
        raw=response.read(200000)
    d=json.loads(raw)
    usage=d["usage"]
    assert isinstance(usage["total_tokens"],int)
    return {"text":d["choices"][0]["message"]["content"],
      "usage":usage,"body_sha256":sha(raw),
      "finish_reason":d["choices"][0].get("finish_reason")}

def preflight():
    d=make()
    assert len(d)==5 and len({x["query_id"] for x in d})==5
    names=[x["query_id"] for x in d]
    assert names==["Query00312","Query00347","Query00610","Query00685","Query00916"],names
    return d

def run():
    tasks=preflight()
    if OUT.exists():raise FileExistsError("Output already exists; no relaunch/overwrite.")
    if not os.environ.get("DEEPSEEK_API_KEY"):raise RuntimeError("DEEPSEEK_API_KEY missing")
    OUT.mkdir(parents=True)
    lock={"schema":"retention-mechanism-five-dev-task-frozen-v1",
      "source":"merged source archive, third task per category, disjoint from earlier first-two-per-category mechanism samples",
      "base_task_ids":[x["query_id"] for x in tasks],
      "base_tasks":5,"matched_conditions":10,
      "calls_per_task":{"masked_price_candidate_generation":1,
        "original_decision_control":2,"generated_candidate_decision":2},
      "max_calls":MAX_CALLS,"max_total_provider_tokens":MAX_TOKENS_TOTAL,
      "thinking":"disabled","temperature":0,
      "no_gold_or_oracle_witness":True,
      "candidate_same_across_retain_switch":True,
      "primary_metrics":["alternative_feasible","alternative_improves_switch",
        "original_correct_RETAIN","original_correct_SWITCH",
        "candidate_correct_RETAIN","candidate_correct_SWITCH",
        "evidence_to_label_consistency","task_pair_correct"],
      "warnings":["5 reused merged source archive development tasks, not independent validation",
       "A non-improving sampled candidate cannot demonstrate a better plan exists",
       "The candidate presentation and explicit arithmetic also change prompt scaffolding",
       "This is structured graph decision only, not real Agent tool execution",
       "No original plan self-commitment intervention performed"] }
    (OUT/"LOCK.json").write_text(json.dumps(lock,indent=2,sort_keys=True)+"\n")
    records=[]
    tokens=0;attempted=0
    def ask(info,messages,token_cap=320):
        nonlocal tokens,attempted
        if attempted>=MAX_CALLS or tokens+5000>MAX_TOKENS_TOTAL:
            raise RuntimeError("CALL_OR_TOKEN_RESERVATION_HARD_STOP")
        attempted+=1
        row={**info,"messages_sha256":sha(canon(messages).encode()),
          "attempt_index":attempted}
        started=time.monotonic()
        try:
            z=provider(messages,token_cap)
            tokens+=z["usage"]["total_tokens"]
            row.update({"error":None,**z})
        except urllib.error.HTTPError as exc:
            row.update({"error":"HTTP_"+str(exc.code),"text":None})
            if exc.code==402:raise RuntimeError("DEEPSEEK_HTTP402_STOP_IMMEDIATELY")
        except Exception as exc:
            row.update({"error":type(exc).__name__,"text":None})
        finally:
            row["elapsed_seconds"]=round(time.monotonic()-started,3)
            with (OUT/"RESPONSES.jsonl").open("a",encoding="utf-8") as f:
                f.write(canon(row)+"\n")
                f.flush()
        return row

    for task in tasks:
        qid=task["query_id"]
        gen=ask({"query_id":qid,"arm":"generate_candidate","condition":"BOTH_MASKED"},
                task["generator_messages"],350)
        try:
            generated=json.loads(gen["text"] or "{}")
            candidate=generated["alternative_suffix"]
        except Exception:candidate=[]
        q_switch=json.loads(task["conditions"]["SWITCH"]["messages"][-1]["content"])
        q_retain=json.loads(task["conditions"]["RETAIN"]["messages"][-1]["content"])
        ok,cost_switch,reason=legal(q_switch,candidate)
        ok_retain,cost_retain,_=legal(q_retain,candidate)
        other=candidate!=q_switch["supplied_old_plan_suffix"]
        valid=bool(ok and ok_retain and other)
        met={"query_id":qid,"candidate":candidate,"candidate_valid":valid,
          "reason_invalid":reason if not valid else None,
          "candidate_price_hidden_from_generator":True,
          "candidate_cost_switch":str(cost_switch) if ok else None,
          "candidate_cost_retain":str(cost_retain) if ok_retain else None}
        with (OUT/"CANDIDATES.jsonl").open("a",encoding="utf-8") as f:
            f.write(canon(met)+"\n")
        for condition in ("RETAIN","SWITCH"):
            source=task["conditions"][condition]
            q=json.loads(source["messages"][-1]["content"])
            # Keep the baseline exact archived prompt; independent new provider draw.
            original=source["messages"]
            ask({"query_id":qid,"arm":"original_control","condition":condition,
                "source_request_trial":source["trial_id"]},original,160)
            if not valid:
                continue
            alternate=json.loads(canon(original))
            instruction='Reply ONLY as a JSON object with one field: {"intervention":"RETAIN"} or {"intervention":"SWITCH"}.'
            assert instruction in alternate[0]["content"]
            alternate[0]["content"]=alternate[0]["content"].replace(instruction,
                'Compare the supplied old suffix and the additional feasible candidate using the visible current tool data. '
                'Sum both execution values. The added candidate is NOT guaranteed preferable. '
                'Reply with exactly JSON: {"intervention":"RETAIN" or "SWITCH", '
                '"old_total":number, "candidate_total":number}. '
                'Choose SWITCH only if the candidate is strictly preferable; RETAIN on a tie.')
            alternate[-1]["content"]+="\nADDITIONAL CANDIDATE (not ranked, generated without prices, same candidate across both conditions):\n"+canon({"candidate_suffix":candidate})
            ask({"query_id":qid,"arm":"generated_candidate","condition":condition,
                "candidate_sha256":sha(canon(candidate).encode())},alternate,300)
    print("FINISHED",canon({"tasks":len(tasks),"provider_attempts":attempted,
                             "charged_provider_tokens":tokens}),flush=True)

def score():
    lock=json.loads((OUT/"LOCK.json").read_text())
    candidates={r["query_id"]:r for r in lines(OUT/"CANDIDATES.jsonl")}
    responses=lines(OUT/"RESPONSES.jsonl")
    tasks=preflight()
    truth={(t["query_id"],c):json.loads(t["conditions"][c]["messages"][-1]["content"])
        for t in tasks for c in ("RETAIN","SWITCH")}
    report=[];armcounts=defaultdict(Counter);pairs=defaultdict(dict)
    for row in responses:
        if row["arm"]=="generate_candidate":continue
        arm=row["arm"];qid=row["query_id"];c=row["condition"]
        parsed={}
        if row.get("text") and not row.get("error"):
            try:parsed=json.loads(row["text"])
            except Exception:pass
        label=parsed.get("intervention")
        if label not in ("RETAIN","SWITCH"):label=None
        item={"query_id":qid,"condition":c,"arm":arm,"label":label,
          "label_correct":label==c,"provider_error":row.get("error"),
          "candidate_valid":candidates[qid]["candidate_valid"]}
        if arm=="generated_candidate":
            q=truth[(qid,c)];cand=candidates[qid]["candidate"]
            old_ok,old_true,_=legal(q,q["supplied_old_plan_suffix"])
            can_ok,can_true,_=legal(q,cand)
            assert old_ok and can_ok
            try:
                ro=Decimal(str(parsed.get("old_total")))
                rc=Decimal(str(parsed.get("candidate_total")))
            except Exception:ro=rc=None
            item.update({"true_old":str(old_true),"true_candidate":str(can_true),
              "reported_old":str(ro) if ro is not None else None,
              "reported_candidate":str(rc) if rc is not None else None,
              "old_correct":ro==old_true,"candidate_correct":rc==can_true,
              "reported_comparison_consistent":None if ro is None or rc is None or label is None else
                 label==("SWITCH" if rc<ro else "RETAIN"),
              "candidate_improves":can_true<old_true,
              "candidate_only_gold":("SWITCH" if can_true<old_true else "RETAIN"),
              "two_candidate_decision_correct":label==("SWITCH" if can_true<old_true else "RETAIN"),
              "two_candidate_decision_valid":label is not None})
        report.append(item);armcounts[arm][c+"_attempts"]+=1
        armcounts[arm][c+"_correct"]+=int(item["label_correct"])
        pairs[(arm,qid)][c]=label
    for arm,c in armcounts.items():
        c["pair_correct"]=sum(v=={"RETAIN":"RETAIN","SWITCH":"SWITCH"}
             for (k,qid),v in pairs.items() if k==arm)
    out={"schema":"retention-mechanism-5-task-scored-v1",
      "status":"completed" if len(responses)==25 else "partial",
      "independent_base_tasks":5,"calls_attempted":len(responses),
      "candidate_valid_count":sum(x["candidate_valid"] for x in candidates.values()),
      "candidate_generated":list(candidates.values()),
      "arm_metrics":{k:dict(v) for k,v in armcounts.items()},
      "candidate_two_option_correct":sum(x.get("two_candidate_decision_correct",False) for x in report if x["arm"]=="generated_candidate"),
      "candidate_two_option_trials":sum(x["arm"]=="generated_candidate" for x in report),
      "reported_evidence_label_contradictions":sum(x.get("reported_comparison_consistent") is False for x in report if x["arm"]=="generated_candidate"),
      "candidate_improves_any":sum(x.get("candidate_improves",False) for x in report if x["arm"]=="generated_candidate"),
      "cases":report,
      "interpretation_boundary":[
        "The original ground-truth SWITCH label is NOT the gold decision when comparing only incumbent against one generated candidate; the latter may be worse than incumbent even when another superior path exists.",
        "Candidate generator is price-blind and not instructed to find the actual better path.",
        "Candidate experiment measures accessible alternatives and decision consistency, not the ability to identify the optimum.",
        "Generated candidate might be valid but not improve SWITCH; no gain is not evidence of plan anchoring.",
        "Mechanisms cannot be inferred from internal reasoning or model labels alone.",
        "Five previously studied development tasks, never report heldout performance.",
        "No native execution or self-authored incumbent in this batch."]}
    (OUT/"SCORE.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("SCORED",canon({"status":out["status"],"candidates":out["candidate_valid_count"],
       "metrics":out["arm_metrics"]}),flush=True)

if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("action",choices=["preflight","run","score"])
    args=arg.parse_args()
    if args.action=="preflight":
        print("PREFLIGHT",canon({"task_ids":[x["query_id"] for x in preflight()],
            "new_model_calls":0}),flush=True)
    elif args.action=="run":run()
    else:score()
