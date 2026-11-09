#!/usr/bin/env python3
"""Falsification test for why candidate-list exposure failed to resolve RETAIN.

Five frozen dev tasks, two paired environments, two witness-evidence levels:
  A. one *fixed* feasible competitor path, no sums or better-label.
  B. same path with two independently computed sums, no better-label.
The candidate is selected from <=2-step feasible paths based on a strict
improvement in the SWITCH graph. This is EXPERIMENTER-ASSISTED witness
selection (not a deployable non-oracle candidate finder). Candidate identity
is HELD EXACTLY CONSTANT across the paired RETAIN and SWITCH conditions.
"""
import json,os,time,hashlib,urllib.request,urllib.error,argparse
from pathlib import Path
from collections import defaultdict,Counter
from decimal import Decimal
from feasible_alternative_visibility import make as make_inputs, enumerate_paths,path_value,ser

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"research/plan_commitment_pilot/evidence/evidence_ladder"
MAX_CALLS=20
MAX_TOTAL_TOKENS=60000
def hash_(x):return hashlib.sha256(x).hexdigest()
def readlines(p):return [json.loads(t) for t in p.read_text(encoding="utf8").splitlines() if t.strip()]
def build():
    prior,checks=make_inputs()
    byid=defaultdict(dict)
    for t in prior:
        if t["arm"]=="original_label_only":byid[t["query_id"]][t["condition"]]=t
    tasks=[x["query_id"] for x in checks]
    assert len(tasks)==5
    trials=[];selection=[]
    for qid in tasks:
        pair=byid[qid]
        assert set(pair)=={"RETAIN","SWITCH"}
        qS=json.loads(pair["SWITCH"]["messages"][-1]["content"])
        qR=json.loads(pair["RETAIN"]["messages"][-1]["content"])
        candidates=enumerate_paths(qS)
        original=qS["supplied_old_plan_suffix"]
        oldS=path_value(qS,original)
        viable=[p for p in candidates if p!=original and path_value(qS,p)<oldS]
        if not viable:raise AssertionError(("no short improving alternative",qid))
        witness=viable[0]
        assert witness==next(p for p in enumerate_paths(qR)
                              if p==witness)
        assert path_value(qR,witness)>=path_value(qR,original)
        selection.append({"qid":qid,"selected_path":witness,
           "selection_is_experimenter_witness_using_switch_prices":True,
           "same_candidate_on_both_conditions":True})
        for condition in ("RETAIN","SWITCH"):
            source=pair[condition]
            q=json.loads(source["messages"][-1]["content"])
            old_total=path_value(q,original)
            witness_total=path_value(q,witness)
            true="SWITCH" if witness_total<old_total else "RETAIN"
            assert true==condition
            for mode in ("path_only","path_plus_verified_totals"):
                messages=json.loads(ser(source["messages"]))
                old_sentence='Reply ONLY as a JSON object with one field: {"intervention":"RETAIN"} or {"intervention":"SWITCH"}.'
                assert old_sentence in messages[0]["content"]
                messages[0]["content"]=messages[0]["content"].replace(old_sentence,
                    "Compare EXACTLY the supplied incumbent suffix and one additional feasible goal-reaching candidate. "
                    "The candidate is not labelled as optimal or better; it is the same path in both factual conditions. "
                    "Use current tool values, choosing SWITCH only if the candidate is strictly preferable, "
                    "otherwise RETAIN. Reply ONLY JSON with {\"intervention\":\"RETAIN\" or \"SWITCH\", "
                    "\"old_total\":number, \"candidate_total\":number}.")
                info={"additional_feasible_suffix":witness,
                      "note":"No label or optimality status is supplied."}
                if mode=="path_plus_verified_totals":
                    info["independently_aggregated_values"]={
                       "incumbent_suffix_total":str(old_total),
                       "additional_suffix_total":str(witness_total)}
                messages[-1]["content"]+="\nADDITIONAL DECISION EVIDENCE:\n"+ser(info)
                trials.append({"trial_id":f"{qid}-{condition}-{mode}",
                  "qid":qid,"condition":condition,"mode":mode,
                  "messages":messages,"sha256":hash_(ser(messages).encode()),
                  "candidate":witness,"correct_label":true,
                  "true_old":str(old_total),"true_candidate":str(witness_total)})
    assert len(trials)==20
    return trials,selection

def prepare():
    trials,selection=build()
    if OUT.exists():raise FileExistsError("no overwrite")
    OUT.mkdir(parents=True)
    lock={"schema":"witness-price-evidence-ladder-v1",
      "base_tasks":5,"correlated_conditions":2,
      "arms":["path_only","path_plus_verified_totals"],"max_provider_calls":20,
      "max_charged_tokens":MAX_TOTAL_TOKENS,
      "model":"deepseek-flash","thinking":"disabled","temperature":0,
      "candidate_selection":"experimenter selects first <=2-step feasible competitor strictly better in SWITCH scenario; SAME candidate on matched RETAIN side",
      "limitations":["EXPERIMENTER-ASSISTED: chosen witness depends on SWITCH-side true price advantage, although chosen path is fixed across both conditions",
        "Aggregated values make correct binary label straightforward; numeric arm diagnoses integration, not alternative discovery",
        "The path-only versus numeric arm changes available evidence; not a deployable method",
        "Synthetic graph decisions are not autonomous Agent tool execution"],
      "selection":selection}
    (OUT/"LOCK.json").write_text(json.dumps(lock,indent=2,ensure_ascii=False)+"\n")
    (OUT/"TRIALS.jsonl").write_text("".join(ser(x)+"\n" for x in trials),encoding="utf8")
    print("FROZEN_LADDER",ser({"tasks":5,"trials":20,"witnesses":selection}),flush=True)
def run():
    trials=readlines(OUT/"TRIALS.jsonl")
    if (OUT/"RESPONSES.jsonl").exists():raise FileExistsError("do not retry paid outputs")
    key=os.environ.get("DEEPSEEK_API_KEY")
    if not key:raise RuntimeError("missing API key")
    used=0
    for i,t in enumerate(trials):
        payload={"model":"deepseek-flash","messages":t["messages"],"temperature":0,
         "thinking":{"type":"disabled"},"response_format":{"type":"json_object"},
         "max_tokens":200,"stream":False}
        raw=ser(payload).encode("utf8")
        if used+max(4200,len(raw)//2+200)>MAX_TOTAL_TOKENS:
            print("HARD_TOKEN_STOP",i,used,flush=True);break
        rq=urllib.request.Request("https://api.deepseek.com/chat/completions",method="POST",
            data=raw,headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
        row={"trial_id":t["trial_id"],"prompt_sha256":t["sha256"]}
        ts=time.monotonic()
        try:
            with urllib.request.urlopen(rq,timeout=110) as res:body=res.read(200000)
            parsed=json.loads(body);usage=parsed["usage"];used+=usage["total_tokens"]
            row.update({"error":None,"response_text":parsed["choices"][0]["message"]["content"],
                       "usage":usage,"raw_sha256":hash_(body)})
        except urllib.error.HTTPError as e:
            row.update({"error":"HTTP_"+str(e.code),"response_text":None})
        except Exception as e:
            row.update({"error":type(e).__name__+":"+str(e)[:150],"response_text":None})
        row["time_s"]=round(time.monotonic()-ts,3)
        with (OUT/"RESPONSES.jsonl").open("a",encoding="utf8") as file:
            file.write(ser(row)+"\n");file.flush()
        print("LADDER_TRIAL",i+1,"/",len(trials),t["mode"],t["condition"],row.get("error") or "OK",flush=True)
        if row.get("error")=="HTTP_402":break
    print("LADDER_SPENT_TOKENS",used,flush=True)
def score():
    trials=readlines(OUT/"TRIALS.jsonl");resp=readlines(OUT/"RESPONSES.jsonl")
    byid={x["trial_id"]:x for x in resp}
    assert len(byid)==len(resp)
    counts=defaultdict(Counter);pairs=defaultdict(dict);rows=[]
    for t in trials:
        r=byid.get(t["trial_id"],{})
        if r and r["prompt_sha256"]!=t["sha256"]:raise AssertionError("trial hash mismatch")
        try:answer=json.loads(r.get("response_text") or "{}")
        except Exception:answer={}
        label=answer.get("intervention")
        if label not in ("RETAIN","SWITCH"):label=None
        try:old=Decimal(str(answer.get("old_total")));candidate=Decimal(str(answer.get("candidate_total")))
        except Exception:old=candidate=None
        c=counts[t["mode"]]
        c["planned"]+=1;c["valid"]+=int(label is not None)
        c[t["condition"]+"_correct"]+=int(label==t["condition"])
        c["old_report_correct"]+=int(old==Decimal(t["true_old"]))
        c["candidate_report_correct"]+=int(candidate==Decimal(t["true_candidate"]))
        consistent=None if old is None or candidate is None or label is None else label==("SWITCH" if candidate<old else "RETAIN")
        c["self_report_contradictions"]+=int(consistent is False)
        pairs[(t["mode"],t["qid"])][t["condition"]]=label
        rows.append({"trial_id":t["trial_id"],"mode":t["mode"],"qid":t["qid"],
            "condition":t["condition"],"label":label,"correct":label==t["condition"],
            "old_report":str(old) if old is not None else None,
            "candidate_report":str(candidate) if candidate is not None else None,
            "old_true":t["true_old"],"candidate_true":t["true_candidate"],
            "self_report_consistent":consistent,"error":r.get("error")})
    for arm,c in counts.items():
        c["pair_accuracy"]=sum(x=={"RETAIN":"RETAIN","SWITCH":"SWITCH"}
                                 for (a,q),x in pairs.items() if a==arm)
    result={"schema":"witness-price-evidence-ladder-scored-v1",
       "status":"complete" if len(resp)==20 else "partial",
       "base_tasks":5,"calls":len(resp),"metrics":{k:dict(v) for k,v in counts.items()},
       "cases":rows,
       "limits":["Witness is experimenter selected using SWITCH-side condition; same candidate path in both conditions avoids path-identity leakage across pair",
                 "Supplying correct totals is oracle-assisted evidence, not a production technique",
                 "Do not infer source of original 41 cases individually."]}
    (OUT/"SCORE.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print("LADDER_SCORE",ser(result["metrics"]),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("action",choices=["prepare","run","score"]);a=ap.parse_args()
    if a.action=="prepare":prepare()
    elif a.action=="run":run()
    else:score()
