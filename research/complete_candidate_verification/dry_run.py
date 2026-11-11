"""Provider-free end-to-end protocol dry run."""
from __future__ import annotations
import asyncio, json
from .policy_input import build_policy_input
from .update_controller import run_update
from .committed_plan_executor import CommittedPlanExecutor

def interface(name: str, inputs: list[str], output: str, cost: float) -> dict:
    properties = {item: {"type": "string", "description": f"{item} observed identifier"}
                  for item in inputs}
    return {"type": "function", "function": {
        "name": name,
        "description": (f"Native dry-run tool. This tool has a cost of {cost} units. "
                        f"The output type of this tool is {output}."),
        "parameters": {"type": "object", "properties": properties, "required": inputs},
    }}

class FakeCompletion:
    def __init__(self):
        self.calls = 0
        self.responses = [
            {"plan": ["Acquire_A", "Finish_A"]},
            {"plan": ["Acquire_B", "Finish_B"]},
        ]
    async def __call__(self, **kwargs):
        self.calls += 1
        return self.responses[self.calls-1]

async def run_dry_run() -> dict:
    tools = [
        interface("Acquire_A", ["Start"], "A", 2.0),
        interface("Finish_A", ["A"], "Goal", 4.0),
        interface("Acquire_B", ["Start"], "B", 0.5),
        interface("Finish_B", ["B"], "Goal", 1.0),
    ]
    policy_input = build_policy_input(task="dry_run",
        user_request="Complete the dry-run task.", goal_type="Goal",
        observed_state_types=["Start"],
        old_remaining_plan=["Acquire_A", "Finish_A"],
        current_tool_interfaces=tools, checkpoint_id="offline-dry-run-checkpoint")
    fake = FakeCompletion()
    decision = await run_update(policy_input, fake)
    if decision.action != "SWITCH" or decision.selected_plan != ("Acquire_B", "Finish_B"):
        raise AssertionError("dry-run did not select the strictly cheaper complete candidate")
    executor = CommittedPlanExecutor(policy_input, decision.selected_plan)
    current, executed = {"Start"}, []
    for name, output in (("Acquire_B", "B"), ("Finish_B", "Goal")):
        if executor.next_tool(current, tools) != name:
            raise AssertionError("executor did not enforce the committed sequence")
        args = {"Start": "OBS-START"} if name == "Acquire_B" else {"B": "OBS-B"}
        executor.validate_arguments(name, json.dumps(args))
        current.add(output)
        executor.record_tool_result(tool_name=name, success=True,
            observed_state_types=current, current_tool_interfaces=tools)
        executed.append(name)
    if not executor.finished or current != {"Start", "B", "Goal"}:
        raise AssertionError("dry-run native observation sequence did not finish")
    return {"status": "passed", "provider_calls": 0, "planning_calls": fake.calls,
            "decision": decision.action, "selected_plan": list(decision.selected_plan),
            "executed_plan": executed, "executor": executor.execution_record()}

def main() -> int:
    print(json.dumps(asyncio.run(run_dry_run()), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
