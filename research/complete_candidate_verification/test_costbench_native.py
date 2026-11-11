"""One provider-free integration step through the pinned native CostBench helper."""
from __future__ import annotations
import json, os, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE_DIR = ROOT / "experiments" / "paired_50" / "native_execution"
sys.path.insert(0, str(NATIVE_DIR))

from .policy_input import build_policy_input
from .committed_plan_executor import CommittedPlanExecutor
from .costbench_adapter import CostBenchNativeExecutionAdapter


@unittest.skipUnless(os.environ.get("COSTBENCH_ROOT"),
                     "COSTBENCH_ROOT is required for pinned native integration")
class PinnedCostBenchNativeTests(unittest.TestCase):
    def test_committed_plan_executes_one_real_native_tool(self):
        import run_official_harness as native

        costbench_root = Path(os.environ["COSTBENCH_ROOT"]).resolve()
        original_cwd = Path.cwd()
        try:
            os.chdir(costbench_root)
            costbench = native.load_costbench(costbench_root)
            requests, manifest, registry = native.load_frozen_inputs()
            request = next(
                row for row in requests
                if row["query_id"] == "Query00178"
                and manifest[row["trial_id"]]["condition"] == "RETAIN"
            )
            manifest_row = manifest[request["trial_id"]]
            registry_rows = {
                row["task_id"]: row
                for row in registry["selection"]["task_ids"]
            }
            query_path = costbench_root / "env" / "data" / "runtime" / "queries" / "queries.json"
            query_rows = json.loads(query_path.read_text(encoding="utf-8"))
            query = {
                row["query_id"].strip("<>"): row
                for row in query_rows
            }[request["query_id"]]
            prepared = native.prepare_trial(
                request, manifest_row, query,
                registry_rows[request["query_id"]], costbench,
            )
            policy_input = build_policy_input(
                task=prepared["task"],
                user_request=prepared["user_request"],
                goal_type=prepared["goal_type"],
                observed_state_types=prepared["state"],
                old_remaining_plan=prepared["incumbent_suffix"],
                current_tool_interfaces=prepared["tool_interfaces"],
                checkpoint_id=prepared["checkpoint_sha256"],
            )
            executor = CommittedPlanExecutor(policy_input, policy_input.old_remaining_plan)
            state = set(prepared["state"])
            tool_name = executor.next_tool(state, prepared["tool_interfaces"])
            tool_obj = prepared["tool_objects"][tool_name]

            known = {}
            for input_type in tool_obj.input_types:
                try:
                    known[input_type] = native.query_input_for_type(
                        input_type, query, prepared["task"]
                    )
                except ValueError:
                    if (prepared.get("prefix_name")
                            and input_type == prepared["tool_objects"][prepared["prefix_name"]].output_type
                            and prepared.get("prefix_output_id")):
                        known[input_type] = prepared["prefix_output_id"]
                    else:
                        raise
            arguments = json.dumps(
                {name: known[name] for name in tool_obj.input_types},
                ensure_ascii=False, sort_keys=True,
            )

            adapter = CostBenchNativeExecutionAdapter(
                executor=executor,
                native_execute=prepared_official_execute(costbench),
                state_supplier=lambda: state,
                interfaces_supplier=lambda: list(prepared["tool_interfaces"]),
            )
            result = adapter.execute(
                tool_obj=tool_obj,
                arguments_str=arguments,
                refinement_level=native.REFINEMENT_LEVEL,
                available_tools=prepared["tool_objects"],
            )
            self.assertFalse(
                isinstance(result, str) and result.startswith(native.ERROR_PREFIXES),
                msg=f"pinned native CostBench tool failed: {result}",
            )
            state.add(tool_obj.output_type)
            status = adapter.confirm_observed_state()
            self.assertIn(status, {"ADVANCED", "GOAL_REACHED"})
            self.assertEqual(executor.cursor, 1)
            if not executor.finished:
                self.assertEqual(
                    executor.next_tool(state, prepared["tool_interfaces"]),
                    policy_input.old_remaining_plan[1],
                )
        finally:
            os.chdir(original_cwd)


def prepared_official_execute(costbench):
    return costbench["official_run"]._execute_tool_simulation


if __name__ == "__main__":
    unittest.main()
