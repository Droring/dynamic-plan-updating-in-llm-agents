#!/usr/bin/env python3
"""Stage 2 reproducible eligibility census, all archived official CostBench dev80.
No additional provider calls, interventions, or reclassification as independent outcomes.
"""
import json,re,hashlib
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"research/costbench_method_studies/official_dev_baseline/evidence"
GATE=ROOT/"research/costbench_method_studies/plan_commitment_evidence_gate/REPLAY_GATE.json"
OUT=ROOT/"research/plan_commitment_pilot/evidence/ELIGIBILITY_CENSUS_80.json"
PREVIOUS={"Query00271","Query00261","Query00249","Query00306"}
PROSPECTIVE=re.compile(r"\b(?:I(?:'ll| will| plan to| intend to)|my plan|proceed|first|next|then|followed by|path)\b",re.I)
def load():
    dyn={}
    for i in range(4):
        p=BASE/"results/official_cost_change"/f"shard{i:02d}"/"results_deepseek-flash_blocked-cost_change-1_refinement_2.json"
        for x in json.loads(p.read_text(encoding="utf8"))["results"]:
            q=x["query_id"].strip("<>")
            assert q not in dyn
            dyn[q]=x
    assert len(dyn)==80
    return dyn
def main():
    dyn=load()
    rows={r["query_id"]:r for r in json.loads(GATE.read_text())["tasks"]}
    assert len(rows)==80 and rows.keys()==dyn.keys()
    results=[];counts=Counter()
    for q in sorted(dyn):
        x=dyn[q];g=rows[q];hist=x.get("conversation_history") or []
        assistant=[(i,m) for i,m in enumerate(hist) if m.get("role")=="assistant"]
        first=assistant[0][1] if assistant else {}
        plan=first.get("content") or ""
        has_plan=bool(plan.strip()) and bool(PROSPECTIVE.search(plan))
        pre_steps=(x.get("block_stats") or {}).get("block_step") or []
        trigger=int(pre_steps[0]) if pre_steps else 0
        actual_calls=[m for m in hist if m.get("role")=="assistant" and m.get("tool_calls")]
        observed_prefix=trigger>0 and len(actual_calls)>=trigger
        matched=g["status"]=="replay_matched_checkpoint"
        excluded=q in PREVIOUS
        provisional=matched and observed_prefix and has_plan and not excluded
        # The official scenario checks original user task, *not* the factual
        # corrections introduced by the experimental event. Do not claim this.
        semantic_updated_goal_verifier=False
        # Replanning label oracle and synthetic fact-update intervention are
        # not interchangeable. The original event is cost_change, not a
        # preference change or semantic invalidation.
        matched_retain_switch_semantic_pairs=False
        eligible=provisional and semantic_updated_goal_verifier and matched_retain_switch_semantic_pairs
        notes=[]
        if not matched:notes.append("unmatched_original_native_checkpoint")
        if not observed_prefix:notes.append("no_confirmed_pre_event_tool_execution")
        if not has_plan:notes.append("no_detectable_self_authored_prospective_text")
        if excluded:notes.append("previously_used_for_intervention_design")
        if provisional:notes.append("further_manual_plan_authorship_check_required")
        notes.append("independent_post_update_semantic_verifier_unavailable")
        notes.append("no_paired_semantic_retain_switch_event_frozen")
        rec={"query_id":q,"category":x.get("task"),
             "native_checkpoint_matched":matched,
             "pre_event_tool_execution_observed":observed_prefix,
             "prospective_plan_text_heuristic":has_plan,
             "prospective_text_preview":plan[:220],
             "earlier_method_development_task":excluded,
             "provisional_screen_pass":provisional,
             "full_semantic_retain_switch_pairs_verified":matched_retain_switch_semantic_pairs,
             "independent_updated_goal_verifier":semantic_updated_goal_verifier,
             "fully_eligible_for_stage2":eligible,
             "exclusion_or_pending_reasons":notes}
        results.append(rec)
        counts["attempted"]+=1
        counts["native_checkpoint_matched"]+=matched
        counts["prior_method_tasks"]+=excluded
        counts["pre_event_tool_execution_observed"]+=observed_prefix
        counts["prospective_plan_text_heuristic"]+=has_plan
        counts["provisional_screen_pass"]+=provisional
        counts["fully_eligible"]+=eligible
    assert counts["attempted"]==80 and counts["native_checkpoint_matched"]==67
    out={"schema":"stage2-all80-archived-native-eligibility-census-v1",
         "source":"official CostBench dev80 original historical dynamic trajectories; archived checkpoint replay gate",
         "counts":dict(counts),
         "target_independent_tasks":30,
         "minimum_eligible_independent_tasks":20,
         "current_technical_gate":"NOT_MET",
         "interpretation":["A self-authored plan-text regex is a SCREENING HEURISTIC, not full scientific confirmation of meaningful commitment.",
           "The frozen official event is cost_change; it does not generate paired semantic retain/switch preference updates.",
           "The original CostBench goal checker cannot certify compliance with a newly corrected user preference.",
           "No novel 20-task paid run or repeated test is claimed.",
           "Four previously studied transportation IDs excluded from independent confirmation."],
         "tasks":results}
    if OUT.exists():raise FileExistsError("refuse replacing previous evidence")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf8")
    print("STAGE2_ELIGIBILITY_CENSUS",json.dumps(out["counts"],sort_keys=True))
if __name__=="__main__":main()
