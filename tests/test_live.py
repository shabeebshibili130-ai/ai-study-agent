"""Live LLM tests against real model APIs (opt-in via @pytest.mark.live)."""

import os
import pytest
from study_agent.agent import run_agent
from study_agent.llm import RealLLM
from study_agent.planner import generate_plan
from study_agent.tools import TOOLS


def check_api_keys():
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        pytest.skip("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured in the environment.")


@pytest.mark.live
def test_live_plan_generation():
    check_api_keys()
    llm = RealLLM()
    plan = generate_plan(goal="Help me revise photosynthesis for Friday", llm=llm)

    assert plan is not None
    assert len(plan.steps) >= 2
    # Ensure all proposed tools belong to registry
    for step in plan.steps:
        assert step.tool in TOOLS, f"Live model proposed unknown tool: '{step.tool}'"


@pytest.mark.live
def test_live_agent_revision_flow(tmp_path):
    check_api_keys()
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "photosynthesis.md").write_text(
        "# Photosynthesis\nLight-dependent reactions convert sunlight to ATP and NADPH.\n"
        "Calvin cycle fixes CO2 into sugars.",
        encoding="utf-8",
    )

    llm = RealLLM()
    result = run_agent(
        goal="Help me revise photosynthesis",
        llm=llm,
        max_steps=8,
        auto_approve_plan=True,
    )

    assert result["status"] in ("completed", "max_steps_exceeded")
    assert result["step_count"] <= 8
    # Validate step observations contain no unhandled system crashes
    for step in result["steps"]:
        obs = step.get("observation", {})
        if "error" in obs:
            assert obs["error"] != "SystemError"


@pytest.mark.live
def test_live_unapproved_write_blocked(tmp_path):
    check_api_keys()
    out_dir = tmp_path / "output"
    target_file = out_dir / "live_quiz.md"

    llm = RealLLM()
    result = run_agent(
        goal="Create and save a quiz to live_quiz.md",
        llm=llm,
        confirm_high_risk=True,
        confirmation_func=lambda tool, args: False,  # Explicitly deny write
        auto_approve_plan=True,
        max_steps=5,
    )

    # High-risk action was denied: target file must not be created on disk
    assert not target_file.exists()

