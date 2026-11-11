import unittest
from summarize_plan_handoff_results import analyze,TASKS,ENVS,ARMS,REPS
def fixture():
    rows=[]
    for i,t in enumerate(TASKS):
        for e in ENVS:
            for a in ARMS:
                for r in REPS:
                    loss=0.1 if e=="RETAIN" and a in {"A","C"} and i==0 else 0.5 if e=="SWITCH" and a in {"A","C"} and i in {0,1} else 0.0
                    rows.append({"query_id":t,"environment":e,"arm":a,"repetition":r,"goal_reached":True,"provider_outcome_unknown":False,
                        "trace":[{"bellman_loss":loss}],"continuation_regret":loss,"common_prefix_loss":0.2,"full_path_regret":0.2+loss,
                        "checkpoint_sha256":f"{t}-{e}","common_first_action":"common","common_arguments_sha256":f"{t}-{e}-a",
                        "common_tool_result_sha256":f"{t}-{e}-r","post_action_state_sha256":f"{t}-{e}-s",
                        "executed_continuation":["new"],"model_calls":1,"provider_tokens":100,"elapsed_seconds":1.0})
    summary={"status":"complete","completed_trajectories":80,"goal_reached":80,"unknown_provider_outcomes":0,"model_calls":80,"provider_tokens_charged":8000,"by_environment_and_arm":{}}
    for e in ENVS:
        for a in ARMS:
            g=[x for x in rows if x["environment"]==e and x["arm"]==a]; rr=[x["continuation_regret"] for x in g]; ff=[x["full_path_regret"] for x in g]
            summary["by_environment_and_arm"][f"{e}/{a}"]={"n":10,"exact_optimal_continuations":sum(v==0 for v in rr),"mean_continuation_regret":sum(rr)/10,"mean_full_path_regret":sum(ff)/10}
    return rows,summary,{"status":"complete","completed_trajectories":80}
class Tests(unittest.TestCase):
    def test_valid(self):
        r,s,l=fixture(); z=analyze(r,s,l); self.assertEqual(z["status"],"verified")
        self.assertEqual(z["B_D_exact_continuation_path_match"]["SWITCH"]["exact_B_D_continuation_matches"],10)
        self.assertEqual(len(z["task_level_paired_contrasts"]["SWITCH"]["A_to_B"]["tasks_improved_by_right"]),2)
    def test_missing(self):
        r,s,l=fixture()
        with self.assertRaisesRegex(ValueError,"matrix mismatch"): analyze(r[:-1],s,l)
    def test_bellman_mismatch(self):
        r,s,l=fixture(); r[0]["full_path_regret"]+=0.01
        with self.assertRaisesRegex(ValueError,"Full-path regret"): analyze(r,s,l)
if __name__=="__main__": unittest.main()
