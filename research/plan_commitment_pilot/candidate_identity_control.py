#!/usr/bin/env python3
"""Frozen 4-task two-by-two candidate-identity diagnostic, 16 paid calls max.
Same prompt, same current graph, same condition; candidate = old suffix vs
the previously generated, independently verified different feasible suffix.
No oracle paths/labels. This is NOT native tool execution.
"""
import json,os,time,hashlib,urllib.request,urllib.error,argparse
from pathlib import Path
from decimal import Decimal
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"research/plan_commitment_pilot/evidence/candidate_identity"
SOURCE=ROOT/"experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a/generated/model_requests.jsonl"
GENERATED=ROOT/"research/plan_commitment_pilot/evidence/mechanism_probe/CANDIDATES.jsonl"
def j(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def lines(p):return [json.loads(x) for x in p.read_text(encoding="utf8").splitlines() if x.strip()]
def sha(x):return hashlib.sha256(x).hexdigest()
def path_total(q,path):
    state=set(q["available_types"]);tot=Decimal(0)
    for name in path:
        t=q["current_tools"][name]
        if not set(t["input_types"]).issubset(state):raise AssertionError("unexecutable path")
        state.add(t["output_type"]);tot+=Decimal(str(t["cost"]))
    if q["goal_type"] not in state:raise AssertionError("goal unreached")
    return tot
def make():
    byid={(x["query_id"],json.loads(x["messages"][-1]["content"])["task_id"]):x for x in lines(SOURCE)}
    # Use trial-manifest to avoid interpreting task_id as condition.
    manifest=json.loads((ROOT/"experiments/paired_50/provenance/source_records/source_archive/raw_source_material_a/generated/trial_manifest.json").read_text())
    ids={(m["query_id"],m["trial_id"]):m["condition"] for m in manifest}
    paired=defaultdict(dict)
    for source in lines(SOURCE):
        c=ids[(source["query_id"],source["trial_id"])]
        paired[source["query_id"]][c]=source
    candidates={x["query_id"]:x for x in lines(GENERATED) if x["candidate_valid"]}
    qids=["Query00347","Query00610","Query00685","Query00916"]
    assert set(qids)==set(candidates)
    trials=[]
    for qid in qids:
        pair=paired[qid]
        assert set(pair)=={"RETAIN","SWITCH"}
        for cond in ("RETAIN","SWITCH"):
            source=pair[cond]
            q=json.loads(source["messages"][-1]["content"])
            old=q["supplied_old_plan_suffix"]
            different=candidates[qid]["candidate"]
            assert old!=different
            for identity,path in (("same_as_incumbent",old),("different_feasible",different)):
                old_total=path_total(q,old);candidate_total=path_total(q,path)
                if identity=="same_as_incumbent":assert old_total==candidate_total
                else:assert candidate_total>old_total,(qid,cond,candidate_total,old_total)
                messages=json.loads(j(source["messages"]))
                needle='Reply ONLY as a JSON object with one field: {"intervention":"RETAIN"} or {"intervention":"SWITCH"}.'
                assert needle in messages[0]["content"]
                messages[0]["content"]=messages[0]["content"].replace(needle,
                    "Compare exactly two listed feasible suffixes: the original suffix and the shown candidate. "
                    "The candidate can be identical to the old plan, or different, and is not necessarily an improvement. "
                    "Add the visible current tool values for each. Choose SWITCH only when the shown candidate is strictly preferable; "
                    "otherwise RETAIN. Respond ONLY in JSON with intervention, old_total and candidate_total.")
                messages[-1]["content"]+="\nADDITIONAL FEASIBLE CANDIDATE (not ranked; may match the original):\n"+j({"candidate_suffix":path})
                trials.append({"trial_id":f"{qid}-{cond}-{identity}","qid":qid,"condition":cond,
                    "identity":identity,"messages":messages,
                    "messages_sha256":sha(j(messages).encode()),"old_true":str(old_total),
                    "candidate_true":str(candidate_total),"true_two_option_label":"RETAIN",
                    "candidate":path})
    assert len(trials)==16
    return trials
def prepare():
    if OUT.exists():raise FileExistsError("output folder exists")
    trials=make()
    OUT.mkdir(parents=True)
    lock={"schema":"nonoracle-candidate-identity-4task-v1",
      "independent_development_tasks":4,"conditions":2,
      "identities":["same_as_incumbent","different_feasible"],
      "max_calls":16,"max_total_tokens":42000,
      "model":"deepseek-flash","thinking":"disabled","temperature":0,
      "source":"4 previously generated feasible candidate routes with no oracle best path",
      "design":"same prompt except candidate path; compare presence of identical candidate with novel but worse candidate",
      "correct_two_option_label_all_arms":"RETAIN",
      "warning":"Do not equate original global SWITCH truth with correctness of two-option comparison; original graph may contain third, improving path."}
    (OUT/"LOCK.json").write_text(json.dumps(lock,indent=2)+"\n")
    (OUT/"TRIALS.jsonl").write_text("".join(j(t)+"\n" for t in trials))
    print("FROZEN_IDENTITY_16",flush=True)
def run():
    ts=lines(OUT/"TRIALS.jsonl")
    if (OUT/"RESPONSES.jsonl").exists():raise FileExistsError("no model-call retries")
    key=os.environ.get("DEEPSEEK_API_KEY")
    if not key:raise RuntimeError("KEY_MISSING")
    spent=0
    for idx,t in enumerate(ts):
        if spent+4000>42000:
            print("HARD_RESERVATION_STOP",idx,spent,flush=True)
            break
        payload={"model":"deepseek-flash","messages":t["messages"],"temperature":0,
                 "thinking":{"type":"disabled"},"response_format":{"type":"json_object"},
                 "max_tokens":180,"stream":False}
        request=urllib.request.Request("https://api.deepseek.com/chat/completions",
          method="POST",data=j(payload).encode(),
          headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
        row={"trial_id":t["trial_id"],"prompt_sha256":t["messages_sha256"]}
        start=time.monotonic()
        try:
            with urllib.request.urlopen(request,timeout=100) as response:body=response.read(200000)
            z=json.loads(body);usage=z["usage"];spent+=usage["total_tokens"]
            row.update({"text":z["choices"][0]["message"]["content"],
                        "usage":usage,"error":None,"raw_sha256":sha(body)})
        except urllib.error.HTTPError as e:
            row.update({"text":None,"error":"HTTP_"+str(e.code)})
        except Exception as e:
            row.update({"text":None,"error":type(e).__name__})
        row["latency_s"]=round(time.monotonic()-start,3)
        with (OUT/"RESPONSES.jsonl").open("a") as f:
            f.write(j(row)+"\n");f.flush()
        print("IDENTITY_CALL",idx+1,"/",len(ts),row.get("error") or "OK",flush=True)
        if row.get("error")=="HTTP_402":break
    print("IDENTITY_PROVIDER_SPENT_TOKENS",spent,flush=True)
def score():
    ts=lines(OUT/"TRIALS.jsonl");res=lines(OUT/"RESPONSES.jsonl")
    byid={x["trial_id"]:x for x in res}
    assert len(byid)==len(res)
    cases=[];counts=defaultdict(Counter)
    for t in ts:
        rr=byid.get(t["trial_id"],{})
        if rr and rr["prompt_sha256"]!=t["messages_sha256"]:raise AssertionError("hash mismatch")
        try:d=json.loads(rr.get("text") or "{}")
        except Exception:d={}
        label=d.get("intervention")
        if label not in ("RETAIN","SWITCH"):label=None
        try:old=Decimal(str(d["old_total"]));can=Decimal(str(d["candidate_total"]))
        except Exception:old=can=None
        identity=t["identity"];key=counts[identity]
        key["planned"]+=1;key["valid"]+=int(label is not None)
        key["correct_two_option"]+=int(label=="RETAIN")
        key["predicted_switch"]+=int(label=="SWITCH")
        key["old_total_correct"]+=int(old==Decimal(t["old_true"]))
        key["candidate_total_correct"]+=int(can==Decimal(t["candidate_true"]))
        consistent=None if old is None or can is None or label is None else label==("SWITCH" if can<old else "RETAIN")
        key["self_report_consistent"]+=int(consistent is True)
        key["self_report_contradiction"]+=int(consistent is False)
        cases.append({"trial_id":t["trial_id"],"qid":t["qid"],"condition":t["condition"],
             "identity":identity,"label":label,"correct_two_option":label=="RETAIN",
             "old_total_reported":str(old) if old is not None else None,
             "candidate_total_reported":str(can) if can is not None else None,
             "old_total_true":t["old_true"],"candidate_total_true":t["candidate_true"],
             "evidence_label_consistent":consistent,"error":rr.get("error")})
    o={"schema":"nonoracle-candidate-identity-4task-scored-v1",
       "status":"complete" if len(res)==16 else "partial",
       "base_tasks":4,"calls":len(res),"metrics":{k:dict(v) for k,v in counts.items()},
       "cases":cases,
       "interpretation":"Both alternatives are never better than incumbent. RETAIN is correct for the two-option comparator in BOTH original globally RETAIN and globally SWITCH conditions. Distinct candidate path is the within-task randomized-variable-like contrast; not randomized ordering and not a native-agent experiment."}
    (OUT/"SCORE.json").write_text(json.dumps(o,indent=2,sort_keys=True)+"\n")
    print("IDENTITY_SCORE",j(o["metrics"]),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("cmd",choices=["prepare","run","score"]);a=ap.parse_args()
    if a.cmd=="prepare":prepare()
    elif a.cmd=="run":run()
    else:score()
