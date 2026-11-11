"""Unit tests for the core agent loop and FakeLLM integration."""

from study_agent.agent import run_agent
from study_agent.llm import FakeLLM


def test_agent_happy_path(tmp_path):
    # Setup test notes
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    sample_file = notes_dir / "sample.md"
    sample_file.write_text("Cellular respiration notes content.", encoding="utf-8")

    fake_llm = FakeLLM([
        {
            "thought": "I need to read the notes first.",
            "tool_call": {
                "name": "read_notes",
                "args": {"filename": "sample.md", "notes_dir": str(notes_dir)},
            },
        },
        {
            "thought": "I have read the notes and can now answer the student.",
            "final_answer": "Summary of cellular respiration: Energy is generated in mitochondria.",
        },
    ])

    result = run_agent(goal="Revise cellular respiration", llm=fake_llm, max_steps=5)

    assert result["status"] == "completed"
    assert result["step_count"] == 2
    assert "Cellular respiration notes content." in result["steps"][0]["observation"]["text"]
    assert result["final_answer"] == "Summary of cellular respiration: Energy is generated in mitochondria."


def test_agent_step_limit():
    # LLM always makes a call without terminating
    fake_llm = FakeLLM()
    # Populate with 10 dummy tool calls for a 3-step max
    for i in range(10):
        fake_llm.add_response({
            "thought": f"Looping step {i}",
            "tool_call": {"name": "update_progress", "args": {"topic": "photosynthesis", "score": 0.8}},
        })

    result = run_agent(goal="Infinite loop goal", llm=fake_llm, max_steps=3)

    assert result["status"] == "max_steps_exceeded"
    assert result["step_count"] == 3
    assert len(result["steps"]) == 3
    assert result["final_answer"] is None


def test_agent_handles_unknown_tool():
    fake_llm = FakeLLM([
        {
            "thought": "Let me delete all notes.",
            "tool_call": {"name": "delete_all", "args": {}},
        },
        {
            "thought": "Tool failed as expected, now providing final answer.",
            "final_answer": "Could not delete notes as tool is unavailable.",
        },
    ])

    result = run_agent(goal="Dangerous request", llm=fake_llm, max_steps=5)

    assert result["status"] == "completed"
    assert result["steps"][0]["observation"]["error"] == "UnknownToolError"
    assert "delete_all" in result["steps"][0]["observation"]["message"]


def test_on_step_callback():
    recorded = []

    def callback(record):
        recorded.append(record["step"])

    fake_llm = FakeLLM([
        {"thought": "Thinking...", "final_answer": "Done!"}
    ])

    result = run_agent(goal="Quick test", llm=fake_llm, max_steps=2, on_step=callback)

    assert result["status"] == "completed"
    assert recorded == [1]

