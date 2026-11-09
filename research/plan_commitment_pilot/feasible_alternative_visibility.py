#!/usr/bin/env python3
"""Causal source-of-alternative-evidence study on 5 frozen development tasks.

Original-control vs same-prompt old-only vs same-prompt all feasible candidate
suffixes. Candidate set consists of all <=2-step paths plus incumbent, generated from input/output dependencies ONLY,
without reading prices, gold labels, or a winning path.
Original snapshots and RETAIN/SWITCH matched. No new algorithm is proposed.
"""
import argparse,hashlib,json,os,urllib.request,urllib.error,time
from collections import defaultdict,Counter
from decimal import Decimal
from pathlib import Path
from heapq import heappush,heappop

ROOT=Path(__file__).resolve().parents[2]
INPUT=ROOT/"experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a/generated"
OUT=ROOT/"research/plan_commitment_pilot/evidence/path_visibility"
CATEGORIES=("transportation","accommodation","attraction","dining","shopping")
EXPECTED=("Query00236","Query00489","Query00662","Query00766","Query00944")
MAX_LENGTH=2
MAX_PROVIDER_CALLS=30
MAX_CHARGED_TOKENS=75000
def ser(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def hash_(x):return hashlib.sha256(x).hexdigest()
def jl(p):return [json.loads(t) for t in p.read_text(encoding="utf8").splitlines() if t.strip()]
def enumerate_paths(q):
    """No prices, current cost, condition or label accessed here."""
    tools=q["current_tools"]
    initial=frozenset(q["available_types"])
    goal=q["goal_type"]
    paths=[]
    def dfs(state,path):
        if goal in state:
            paths.append(list(path));return
        if len(path)>=MAX_LENGTH:return
        for name in sorted(tools):
            tool=tools[name]
            if tool["output_type"] in state:continue
            if not set(tool["input_types"]).issubset(state):continue
            dfs(state|{tool["output_type"]},path+[name])
    dfs(initial,[])
    return sorted(paths,key=lambda p:(len(p),p))
def path_value(q,path):
    state=set(q["available_types"]);total=Decimal("0")
    for name in path:
        t=q["current_tools"][name]
        if not set(t["input_types"]).issubset(state):raise AssertionError("invalid path")
        total+=Decimal(str(t["cost"]));state.add(t["output_type"])
    assert q["goal_type"] in state
    return total
def make():
    req=jl(INPUT/"model_requests.jsonl")
    man=json.loads((INPUT/"trial_manifest.json").read_text(encoding="utf8"))
    mapping={m["trial_id"]:m for m in man}
    bycat=defaultdict(list);grouped=defaultdict(dict)
    for entry in req:
        m=mapping[entry["trial_id"]];qid=m["query_id"]
        q=json.loads(entry["messages"][-1]["content"]);category=q["task"]
        if qid not in bycat[category]:bycat[category].append(qid)
        grouped[qid][m["condition"]]=entry
    chosen=tuple(bycat[c][3] for c in CATEGORIES)
    assert chosen==EXPECTED,chosen
    trials=[];checks=[]
    for qid in chosen:
        assert set(grouped[qid])=={"RETAIN","SWITCH"}
        r=json.loads(grouped[qid]["RETAIN"]["messages"][-1]["content"])
        s=json.loads(grouped[qid]["SWITCH"]["messages"][-1]["content"])
        paths=enumerate_paths(r)
        assert paths==enumerate_paths(s),"paired topology differs"
        old=r["supplied_old_plan_suffix"]
        if old not in paths:
            paths.append(list(old))
            paths.sort(key=lambda p:(len(p),p))
        assert old in paths,"incumbent not in candidate list"
        assert len(paths)<=20,(qid,len(paths))
        # all graph-reachable goal suffixes under 4 steps, hence no path
        # pre-selected because it wins under the SWITCH-side prices.
        best={c:min(path_value(q,p) for p in paths)
          for c,q in (("RETAIN",r),("SWITCH",s))}
        for cond,q in (("RETAIN",r),("SWITCH",s)):
            old_val=path_value(q,old)
            gold="SWITCH" if best[cond]<old_val else "RETAIN"
            assert gold==cond,(qid,cond,gold)
            original=grouped[qid][cond]["messages"]
            for arm in ("original_label_only","matched_old_only","full_feasible_set"):
                messages=json.loads(ser(original))
                if arm!="original_label_only":
                    old_instruction='Reply ONLY as a JSON object with one field: {"intervention":"RETAIN"} or {"intervention":"SWITCH"}.'
                    assert old_instruction in messages[0]["content"]
                    new_instruction=('Use the visible current tool graph to decide whether ANY listed feasible suffix is strictly better '
                       'than the supplied original suffix. The lists contain feasible goal-reaching suffixes, '
                       'not ranked recommendations. Sum current tool values yourself; do not assume a listed '
                       'alternative is better. If none listed is strictly better, RETAIN. '
                       'Return JSON only: {"intervention":"RETAIN" or "SWITCH", '
                       '"selected_suffix":["tool names"], "original_total":number, "selected_total":number}.')
                    messages[0]["content"]=messages[0]["content"].replace(old_instruction,new_instruction)
                    offered=[old] if arm=="matched_old_only" else paths
                    messages[-1]["content"]+="\nBOUNDED FEASIBLE TOOL SUFFIXES (MAX TWO ACTIONS) AND INCUMBENT FROM THE CURRENT TYPE STATE "
                    messages[-1]["content"]+="(not ranked, no comparative score provided):\n"+ser({"suffixes":offered})
                trials.append({"trial_id":f"{qid}-{cond}-{arm}",
                    "query_id":qid,"condition":cond,"arm":arm,
                    "messages":messages,"prompt_sha256":hash_(ser(messages).encode()),
                    "old_path":old,"num_feasible_paths":len(paths),
                    "old_value":str(old_val),"true_best_value":str(best[cond])})
        checks.append({"query_id":qid,"n_feasible":len(paths),
                       "old_path":old,"max_length":MAX_LENGTH})
    assert len(trials)==30
    return trials,checks

def prep():
    trials,checks=make()
    print("PREFLIGHT",ser({"tasks":list(EXPECTED),"n_trials":len(trials),"checks":checks}))
    if OUT.exists():raise FileExistsError("outputs already exist")
    OUT.mkdir(parents=True)
    lock={"schema":"all-feasible-alternatives-causal-comparison-v1",
        "selected_task_ids":list(EXPECTED),"base_tasks":5,
        "matched_conditions":10,"max_provider_calls":MAX_PROVIDER_CALLS,
        "max_charged_tokens":MAX_CHARGED_TOKENS,
        "model":"deepseek-flash","temperature":0,"thinking":"disabled",
        "arms":["original_label_only","matched_old_only","full_feasible_set"],
        "candidate_generation":"dependency-only DFS, all goal-reaching suffixes <=2 actions plus the original incumbent, even if incumbent is longer; no costs or labels used",
        "same_candidate_identity_across_retain_switch":True,
        "primary_metrics":["original_switch_accuracy","matched_old_only_switch_accuracy",
                           "full_feasible_set_switch_accuracy","balanced_accuracy",
                           "correct_matched_pairs","model_reported_value_consistency"],
        "limitations":["5 selected development tasks, original graphs not live Agent actions",
            "Full-list length and number of candidate tokens are not matched to old-only list",
            "Providing all feasible up-to-two-step paths reduces search burden but also changes presentation",
            "No plan authored by this model in original historical task"],
        "offline_candidate_set_checks":checks}
    (OUT/"LOCK.json").write_text(json.dumps(lock,indent=2,ensure_ascii=False)+"\n")
    (OUT/"TRIALS.jsonl").write_text("".join(ser(t)+"\n" for t in trials),encoding="utf8")

def run():
    trials=jl(OUT/"TRIALS.jsonl")
    if (OUT/"RESPONSES.jsonl").exists():raise FileExistsError("no retry")
    key=os.environ.get("DEEPSEEK_API_KEY")
    if not key:raise RuntimeError("API key missing")
    used=0
    for i,t in enumerate(trials):
        payload={"model":"deepseek-flash","messages":t["messages"],
          "temperature":0,"thinking":{"type":"disabled"},
          "response_format":{"type":"json_object"},"max_tokens":250,"stream":False}
        body=ser(payload).encode("utf8")
        if used+max(5000,len(body)//2+250)>MAX_CHARGED_TOKENS:
            print("HARD_TOKEN_CEILING",i,used,flush=True)
            break
        row={"trial_id":t["trial_id"],"prompt_sha256":t["prompt_sha256"]}
        start=time.monotonic()
        try:
            rq=urllib.request.Request("https://api.deepseek.com/chat/completions",
              method="POST",data=body,
              headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
            with urllib.request.urlopen(rq,timeout=120) as response:raw=response.read(300000)
            parsed=json.loads(raw);usage=parsed["usage"]
            used+=usage["total_tokens"]
            row.update({"response_text":parsed["choices"][0]["message"]["content"],
              "usage":usage,"body_sha256":hash_(raw),"error":None})
        except urllib.error.HTTPError as e:
            row.update({"response_text":None,"error":"HTTP_"+str(e.code)})
        except Exception as e:
            row.update({"response_text":None,"error":type(e).__name__+":"+str(e)[:180]})
        row["latency_seconds"]=round(time.monotonic()-start,3)
        with (OUT/"RESPONSES.jsonl").open("a",encoding="utf8") as f:
            f.write(ser(row)+"\n");f.flush()
        print("ALTERNATIVE_VISIBILITY_TRIAL",i+1,"/",len(trials),
              t["arm"],t["condition"],row.get("error") or "OK",flush=True)
        if row.get("error")=="HTTP_402":break
    print("PROVIDER_TOTAL_TOKENS",used,flush=True)

def score():
    trials=jl(OUT/"TRIALS.jsonl");responses=jl(OUT/"RESPONSES.jsonl")
    byid={x["trial_id"]:x for x in responses}
    assert len(byid)==len(responses)
    counts=defaultdict(Counter);by_pair=defaultdict(dict);details=[]
    for t in trials:
        response=byid.get(t["trial_id"],{})
        if response and response["prompt_sha256"]!=t["prompt_sha256"]:
            raise AssertionError("request hash mismatch")
        try:ans=json.loads(response.get("response_text") or "{}")
        except Exception:ans={}
        label=ans.get("intervention")
        if label not in ("RETAIN","SWITCH"):label=None
        c=counts[t["arm"]]
        c["planned"]+=1
        c["received"]+=int(bool(response))
        c["valid"]+=int(label is not None)
        c[t["condition"]+"_correct"]+=int(label==t["condition"])
        by_pair[(t["arm"],t["query_id"])][t["condition"]]=label
        record={"trial_id":t["trial_id"],"arm":t["arm"],"condition":t["condition"],
          "label":label,"correct":label==t["condition"],
          "error":response.get("error"),"num_feasible_paths":t["num_feasible_paths"]}
        if t["arm"]!="original_label_only":
            try:
                old=Decimal(str(ans.get("original_total")))
                selected=Decimal(str(ans.get("selected_total")))
            except Exception:old=selected=None
            record.update({"reported_original":str(old) if old is not None else None,
                 "reported_selected":str(selected) if selected is not None else None,
                 "old_value_correct":old==Decimal(t["old_value"]),
                 "self_comparison_consistent":None if label is None or old is None or selected is None else
                   label==("SWITCH" if selected<old else "RETAIN")})
            c["old_value_correct"]+=int(record["old_value_correct"])
            c["self_report_contradiction"]+=int(record["self_comparison_consistent"] is False)
        details.append(record)
    for arm,c in counts.items():
        c["pairs_both_correct"]=sum(
            v=={"RETAIN":"RETAIN","SWITCH":"SWITCH"}
            for (a,q),v in by_pair.items() if a==arm)
    result={"schema":"feasible-alternative-presentation-diagnostic-five-task-v1",
      "status":"complete" if len(responses)==30 else "partial",
      "unique_development_tasks":5,
      "provider_attempts":len(responses),
      "metrics":{k:dict(v) for k,v in counts.items()},
      "details":details,
      "warnings":["The candidate set is type-feasible and selected without prices, but listing the set also exposes a prompt-format and token-length difference.",
       "A correct SWITCH label does not establish a correct executed native action.",
       "This evaluates availability of non-oracle alternatives, NOT independently causally proving source of 41 historical errors.",
       "Original full-plan cost is part of benchmark; avoid transferring to real user-fact update claims."]}
    (OUT/"SCORE.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print("ALTERNATIVE_VISIBILITY_SCORE",ser(result["metrics"]),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["prepare","run","score"]);a=p.parse_args()
    if a.action=="prepare":prep()
    elif a.action=="run":run()
    else:score()
