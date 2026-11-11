"""Unit tests for plan generation, user approval, and dynamic re-planning."""

from study_agent.agent import run_agent
from study_agent.llm import FakeLLM
from study_agent.planner import (
    Plan,
    PlanStep,
    generate_plan,
    request_plan_approval,
    revise_plan,
)


def test_plan_generation_and_formatting():
    fake_llm = FakeLLM([])
    plan = generate_plan(goal="Revise photosynthesis for Friday", llm=fake_llm)

    assert plan.goal == "Revise photosynthesis for Friday"
    assert len(plan.steps) == 4
    assert plan.steps[0].tool == "read_notes"
    # save_file is high risk and should be flagged for approval
    assert any(s.tool == "save_file" and s.needs_approval for s in plan.steps)

    display = plan.format_for_display()
    assert "PLAN" in display
    assert "read_notes" in display
    assert "[needs approval]" in display


def test_plan_approval_interactive():
    plan = Plan(goal="Test plan", steps=[PlanStep(1, "read_notes", "read file")])

    # Approve with 'y'
    status, feedback = request_plan_approval(plan, input_func=lambda _: "y")
    assert status == "approved"
    assert plan.status == "approved"

    # Reject with 'n'
    status, feedback = request_plan_approval(plan, input_func=lambda _: "n")
    assert status == "rejected"

    # Default reject with empty input
    status, feedback = request_plan_approval(plan, input_func=lambda _: "")
    assert status == "rejected"

    # Edit option
    inputs = iter(["edit", "Make 10 questions instead of 5"])
    status, feedback = request_plan_approval(plan, input_func=lambda _: next(inputs))
    assert status == "edit"
    assert feedback == "Make 10 questions instead of 5"


def test_agent_aborts_on_plan_rejection():
    fake_llm = FakeLLM([
        # Scripted response if a tool was erroneously called
        {"thought": "Should not run", "tool_call": {"name": "read_notes", "args": {"filename": "test.md"}}}
    ])

    result = run_agent(
        goal="Revise biology",
        llm=fake_llm,
        require_plan=True,
        auto_approve_plan=False,
        plan_approval_func=lambda plan: ("rejected", None),
    )

    assert result["status"] == "aborted"
    assert result["step_count"] == 0
    assert len(result["steps"]) == 0
    # Verify no tool calls were made
    assert len(fake_llm.calls) <= 1  # only plan generation call if any, no action calls


def test_dynamic_plan_revision():
    fake_llm = FakeLLM([
        {
            "plan": [
                {"tool": "read_notes", "description": "retry with corrected filename: photosynthesis.md", "args_hint": '"photosynthesis.md"'},
                {"tool": "make_quiz", "description": "generate questions", "args_hint": "text, n=5"},
            ]
        }
    ])

    plan = Plan(
        goal="Revise photosynthesis",
        steps=[
            PlanStep(1, "read_notes", "read bilogy.md"),
            PlanStep(2, "make_quiz", "create quiz"),
        ],
    )

    observation = {
        "error": "FileNotFoundError",
        "message": "File 'bilogy.md' not found",
        "hint": "Did you mean 'photosynthesis.md'?",
    }

    revised = revise_plan(plan, failed_step_num=1, observation=observation, llm=fake_llm)

    assert revised.status == "revised"
    assert any("photosynthesis.md" in s.description for s in revised.steps)


def test_plan_carried_through_successful_agent_run(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "genetics.md").write_text("Mendelian inheritance laws.", encoding="utf-8")

    fake_llm = FakeLLM([
        {
            "thought": "Reading genetics notes.",
            "tool_call": {
                "name": "read_notes",
                "args": {"filename": "genetics.md", "notes_dir": str(notes_dir)},
            },
        },
        {
            "thought": "All done.",
            "final_answer": "Summary of genetics created.",
        },
    ])

    result = run_agent(
        goal="Revise genetics",
        llm=fake_llm,
        require_plan=True,
        auto_approve_plan=True,
    )

    assert result["status"] == "completed"
    assert result["plan"] is not None
    assert result["plan"].status == "approved"
    # Step 1 should be marked done
    assert result["plan"].steps[0].status == "done"

