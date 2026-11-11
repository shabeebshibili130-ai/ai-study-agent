"""Core Agent Loop: think -> act -> look."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from study_agent.llm import BaseLLM
from study_agent.logger import AgentLogger
from study_agent.memory import (
    add_task_summary,
    format_memory_for_prompt,
    get_empty_memory,
    load_memory,
    record_progress,
    save_memory,
)
from study_agent.planner import Plan, generate_plan, request_plan_approval, revise_plan
from study_agent.safety import request_action_confirmation
from study_agent.tools import TOOLS, Tool, dispatch_tool


def run_agent(
    goal: str,
    llm: BaseLLM,
    tools: Optional[Dict[str, Tool]] = None,
    max_steps: int = 15,
    max_retries: int = 2,
    memory: Optional[Dict[str, Any]] = None,
    memory_path: Optional[Path | str] = None,
    require_plan: bool = True,
    auto_approve_plan: bool = True,
    plan_approval_func: Optional[Callable[[Plan], Tuple[str, Optional[str]]]] = None,
    confirm_high_risk: bool = False,
    confirmation_func: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    logger: Optional[AgentLogger] = None,
    on_step: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_plan_created: Optional[Callable[[Plan], None]] = None,
    on_plan_revised: Optional[Callable[[Plan], None]] = None,
) -> Dict[str, Any]:
    """
    Executes the think -> act -> look agent loop until goal completion or limit reached.

    Args:
        goal: The plain-language study goal provided by the student.
        llm: The LLM client (BaseLLM implementation).
        tools: Optional dictionary of available tools (defaults to TOOLS).
        max_steps: Maximum number of think-act-look iterations before forced stop (hard cap).
        max_retries: Maximum consecutive retries allowed per tool call when errors occur.
        memory: In-memory dictionary representing student's memory state.
        memory_path: Optional path to memory.json file to load from and save to.
        require_plan: Whether to generate and enforce a plan prior to any tool execution.
        auto_approve_plan: If True, bypasses interactive console prompt for plan approval.
        plan_approval_func: Custom approval callback returning (status, optional_feedback).
        confirm_high_risk: If True, requires user confirmation before executing High risk tools.
        confirmation_func: Custom confirmation callback for High risk tools returning bool.
        logger: Optional AgentLogger for audit logging.
        on_step: Optional callback invoked after each step with step record.
        on_plan_created: Optional callback invoked when a plan is formulated.
        on_plan_revised: Optional callback invoked when a plan is dynamically updated.

    Returns:
        Summary dict containing:
        - status: "completed" | "max_steps_exceeded" | "retry_limit_exceeded" | "aborted"
        - final_answer: str or None
        - steps: list of step records {step, thought, action, observation}
        - step_count: int
        - memory: current memory state dictionary
        - plan: Plan object or None
    """
    registry = tools if tools is not None else TOOLS
    steps: List[Dict[str, Any]] = []
    consecutive_retries: Dict[str, int] = {}

    if logger:
        logger.log("task_start", {"goal": goal, "max_steps": max_steps})

    # Initialize memory
    if memory is not None:
        mem = memory
    elif memory_path is not None:
        mem, _ = load_memory(memory_path)
    else:
        mem = get_empty_memory()

    # Plan Generation & Approval Phase (FR5)
    plan: Optional[Plan] = None
    if require_plan:
        memory_summary = format_memory_for_prompt(mem)
        plan = generate_plan(goal, llm, memory_summary=memory_summary, tools_registry=registry)
        if on_plan_created:
            on_plan_created(plan)

        if not auto_approve_plan:
            if plan_approval_func:
                action, feedback = plan_approval_func(plan)
            else:
                action, feedback = request_plan_approval(plan)

            approved = (action == "approved" or (action == "edit" and feedback))
            if logger:
                logger.log_user_decision(
                    decision_type="plan_approval",
                    approved=approved,
                    details={"action": action, "feedback": feedback},
                )

            if action == "edit" and feedback:
                plan = generate_plan(f"{goal} (User notes: {feedback})", llm, memory_summary=memory_summary, tools_registry=registry)
                plan.status = "approved"
            elif action != "approved":
                if logger:
                    logger.log("task_aborted", {"reason": "Plan rejected by user"})
                return {
                    "status": "aborted",
                    "final_answer": "Plan was rejected or cancelled by user.",
                    "steps": [],
                    "step_count": 0,
                    "memory": mem,
                    "plan": plan,
                }
        else:
            plan.status = "approved"
            if logger:
                logger.log_user_decision(
                    decision_type="plan_approval",
                    approved=True,
                    details={"mode": "auto_approved"},
                )

    for step_num in range(1, max_steps + 1):
        # 1. THINK: Provide goal, plan, memory, and previous observations to LLM
        memory_summary = format_memory_for_prompt(mem)
        plan_display = plan.format_for_display() if plan else "No plan"
        prompt = (
            f"Goal: {goal}\n"
            f"Plan:\n{plan_display}\n"
            f"Memory:\n{memory_summary}\n"
            f"Step: {step_num}\n"
        )
        context = {
            "goal": goal,
            "step": step_num,
            "memory": mem,
            "plan": plan.to_dict() if plan else None,
            "history": steps,
        }

        decision = llm.generate(prompt=prompt, context=context)
        thought = decision.get("thought", "")
        tool_call = decision.get("tool_call")
        final_answer = decision.get("final_answer")

        # Check for final answer / completion
        if final_answer is not None:
            step_record = {
                "step": step_num,
                "thought": thought,
                "action": None,
                "observation": {"final_answer": final_answer},
            }
            steps.append(step_record)
            if logger:
                logger.log_step(step_record)
                logger.log("task_completed", {"final_answer": final_answer, "steps": step_num})

            if on_step:
                on_step(step_record)

            # Record task summary in memory upon completion
            add_task_summary(mem, goal=goal, summary=final_answer)
            if memory_path is not None:
                save_memory(mem, filepath=memory_path)

            return {
                "status": "completed",
                "final_answer": final_answer,
                "steps": steps,
                "step_count": step_num,
                "memory": mem,
                "plan": plan,
            }

        # 2. ACT: Execute tool call with safety gates
        if tool_call:
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {})
            action = {"tool": tool_name, "args": tool_args}
            target_tool = registry.get(tool_name)

            # High-risk confirmation gate (FR6)
            denied = False
            if target_tool and target_tool.risk == "high" and confirm_high_risk:
                if confirmation_func:
                    confirmed = confirmation_func(tool_name, tool_args)
                else:
                    confirmed = request_action_confirmation(tool_name, tool_args)

                if logger:
                    logger.log_user_decision(
                        decision_type="action_confirmation",
                        approved=confirmed,
                        details={"tool": tool_name, "args": tool_args},
                    )

                if not confirmed:
                    denied = True
                    observation = {
                        "error": "UserDeniedError",
                        "message": f"User declined confirmation to execute high-risk tool '{tool_name}'.",
                        "hint": "The file was not saved. Adapt by providing the content directly to the student in your final_answer.",
                    }

            if not denied:
                # 3. LOOK: Capture observation from tool output
                observation = dispatch_tool(tool_name, tool_args, registry=registry)

            # Handle progress updates in memory
            if tool_name == "update_progress" and observation.get("ok"):
                record_progress(
                    mem,
                    topic=tool_args.get("topic", "general"),
                    score=float(tool_args.get("score", 0.0)),
                    note=tool_args.get("note", ""),
                )

            # Check for tool errors and track retries
            if "error" in observation:
                if plan:
                    revise_plan(plan, step_num, observation, llm)
                    if on_plan_revised:
                        on_plan_revised(plan)

                prior_retries = consecutive_retries.get(tool_name, 0)
                if prior_retries >= max_retries:
                    # Exceeded maximum allowed retries
                    step_record = {
                        "step": step_num,
                        "thought": thought,
                        "action": action,
                        "observation": observation,
                    }
                    steps.append(step_record)
                    if logger:
                        logger.log_step(step_record)
                        logger.log("retry_limit_exceeded", {"tool": tool_name, "retries": max_retries})
                    if on_step:
                        on_step(step_record)

                    failure_msg = (
                        f"Tool '{tool_name}' failed after {max_retries} retries: "
                        f"{observation.get('message', '')}. Please provide guidance."
                    )
                    return {
                        "status": "retry_limit_exceeded",
                        "final_answer": failure_msg,
                        "steps": steps,
                        "step_count": step_num,
                        "memory": mem,
                        "plan": plan,
                    }
                else:
                    consecutive_retries[tool_name] = prior_retries + 1
            else:
                # Succeeded: reset retry count for this tool
                consecutive_retries[tool_name] = 0
                if plan:
                    plan.mark_step_done(step_num)
        else:
            action = None
            observation = {
                "error": "NoActionError",
                "message": "LLM returned neither a tool call nor a final answer.",
                "hint": "Provide a tool_call or final_answer in your decision.",
            }

        step_record = {
            "step": step_num,
            "thought": thought,
            "action": action,
            "observation": observation,
        }
        steps.append(step_record)
        if logger:
            logger.log_step(step_record)

        if on_step:
            on_step(step_record)

    # Exceeded max_steps
    if logger:
        logger.log("max_steps_exceeded", {"step_count": max_steps})

    return {
        "status": "max_steps_exceeded",
        "final_answer": None,
        "steps": steps,
        "step_count": max_steps,
        "memory": mem,
        "plan": plan,
    }
