"""Planner module: plan creation, interactive approval, and dynamic revision."""

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Callable, Dict, List, Optional
from study_agent.llm import BaseLLM
from study_agent.tools import TOOLS, Tool


@dataclass
class PlanStep:
    step_num: int
    tool: str
    description: str
    args_hint: str = ""
    needs_approval: bool = False
    status: str = "pending"  # "pending", "done", "failed", "skipped"


@dataclass
class Plan:
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    status: str = "proposed"  # "proposed", "approved", "rejected", "revised"

    def format_for_display(self) -> str:
        """Formats the plan cleanly for terminal display."""
        lines = ["PLAN"]
        for s in self.steps:
            approval_badge = "   [needs approval]" if s.needs_approval else ""
            status_badge = f" [{s.status.upper()}]" if s.status != "pending" else ""
            tool_display = f"{s.tool}({s.args_hint})" if s.args_hint else s.tool
            lines.append(f" {s.step_num}. {tool_display:<35} → {s.description}{approval_badge}{status_badge}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Converts plan into serializable dictionary."""
        return {
            "goal": self.goal,
            "status": self.status,
            "steps": [asdict(s) for s in self.steps],
        }

    def mark_step_done(self, step_num: int) -> None:
        for s in self.steps:
            if s.step_num == step_num:
                s.status = "done"

    def mark_step_failed(self, step_num: int) -> None:
        for s in self.steps:
            if s.step_num == step_num:
                s.status = "failed"


def generate_plan(
    goal: str,
    llm: BaseLLM,
    memory_summary: str = "",
    tools_registry: Optional[Dict[str, Tool]] = None,
) -> Plan:
    """
    Prompts the LLM to create an ordered study plan before executing any tool.
    """
    reg = tools_registry if tools_registry is not None else TOOLS
    tools_desc = "\n".join([f"- {name}: {t.description} (Risk: {t.risk})" for name, t in reg.items()])

    prompt = (
        f"Goal: {goal}\n\n"
        f"Memory Context:\n{memory_summary}\n\n"
        f"Available Tools:\n{tools_desc}\n\n"
        "Create an ordered study plan with numbered steps before taking action.\n"
        "Return a plan structure with steps, tools, and descriptions."
    )

    decision = llm.generate(prompt=prompt, context={"action": "create_plan", "goal": goal})

    # Check if the LLM provided a structured plan
    if "plan" in decision and isinstance(decision["plan"], list):
        plan_steps = []
        for i, item in enumerate(decision["plan"], 1):
            tool_name = item.get("tool", "")
            risk = reg[tool_name].risk if tool_name in reg else "low"
            plan_steps.append(
                PlanStep(
                    step_num=i,
                    tool=tool_name,
                    description=item.get("description", ""),
                    args_hint=item.get("args_hint", ""),
                    needs_approval=(risk == "high" or item.get("needs_approval", False)),
                )
            )
        return Plan(goal=goal, steps=plan_steps)

    # Fallback heuristic plan generation based on goal
    topic = goal.lower().replace("help me revise", "").replace("revise", "").replace("study", "").strip()
    words = [w for w in topic.split() if w not in ["for", "friday", "monday", "tomorrow", "exam", "the", "my"]]
    clean_topic = words[0] if words else "notes"
    clean_filename = f"{clean_topic}.md"

    steps = [
        PlanStep(
            step_num=1,
            tool="read_notes",
            args_hint=f'"{clean_filename}"',
            description="get source text",
            needs_approval=False,
        ),
        PlanStep(
            step_num=2,
            tool="make_quiz",
            args_hint="text, n=5",
            description="create practice questions",
            needs_approval=False,
        ),
        PlanStep(
            step_num=3,
            tool="save_file",
            args_hint=f'"quiz_{clean_topic}.md"',
            description="store quiz",
            needs_approval=True,
        ),
        PlanStep(
            step_num=4,
            tool="update_progress",
            args_hint=f'"{clean_topic}", score, note',
            description="record result",
            needs_approval=False,
        ),
    ]
    return Plan(goal=goal, steps=steps)


def request_plan_approval(
    plan: Plan,
    input_func: Optional[Callable[[str], str]] = None,
) -> tuple[str, Optional[str]]:
    """
    Displays the plan and requests approval from the student.
    Returns:
        ("approved", None)
        ("rejected", None)
        ("edit", user_edit_feedback)
    """
    prompt_input = input_func if input_func is not None else input
    print("\n" + plan.format_for_display())
    try:
        choice = prompt_input("Approve plan? [y/N/edit]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ("rejected", None)

    if choice in ["y", "yes"]:
        plan.status = "approved"
        return ("approved", None)
    elif choice in ["edit", "e"]:
        try:
            feedback = prompt_input("Enter feedback / changes for the plan: ").strip()
        except (EOFError, KeyboardInterrupt):
            return ("rejected", None)
        plan.status = "revised"
        return ("edit", feedback)
    else:
        plan.status = "rejected"
        return ("rejected", None)


def revise_plan(
    plan: Plan,
    failed_step_num: int,
    observation: Dict[str, Any],
    llm: BaseLLM,
) -> Plan:
    """
    Revises the plan dynamically when a step fails or produces unexpected observations.
    """
    plan.mark_step_failed(failed_step_num)
    plan.status = "revised"

    prompt = (
        f"Goal: {plan.goal}\n"
        f"Step {failed_step_num} failed with observation: {json.dumps(observation)}\n"
        "Current Plan:\n" + plan.format_for_display() + "\n"
        "Provide a revised sequence of remaining steps to achieve the goal."
    )

    decision = llm.generate(prompt=prompt, context={"action": "revise_plan", "failed_step": failed_step_num})

    if "plan" in decision and isinstance(decision["plan"], list):
        # Keep completed steps, replace pending steps with new ones
        new_steps = [s for s in plan.steps if s.step_num < failed_step_num]
        start_idx = failed_step_num
        for i, item in enumerate(decision["plan"], start=start_idx):
            tool_name = item.get("tool", "")
            risk = TOOLS[tool_name].risk if tool_name in TOOLS else "low"
            new_steps.append(
                PlanStep(
                    step_num=i,
                    tool=tool_name,
                    description=item.get("description", ""),
                    args_hint=item.get("args_hint", ""),
                    needs_approval=(risk == "high" or item.get("needs_approval", False)),
                )
            )
        plan.steps = new_steps
    elif "hint" in observation:
        # If observation had a specific hint (e.g. file suggestion)
        suggestion = observation.get("hint", "")
        for s in plan.steps:
            if s.step_num == failed_step_num and "read_notes" in s.tool:
                s.description = f"retry reading notes with suggestion: {suggestion}"
                s.status = "pending"

    return plan

