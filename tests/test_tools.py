"""Unit tests for tool implementations, schemas, error recovery, and retries."""

from pathlib import Path
from study_agent.agent import run_agent
from study_agent.llm import FakeLLM
from study_agent.tools import (
    TOOLS,
    dispatch_tool,
    make_quiz,
    read_notes,
    save_file,
    update_progress,
)


def test_read_notes_success(tmp_path):
    note_file = tmp_path / "biology.md"
    note_file.write_text("Cell division has mitosis and meiosis.", encoding="utf-8")

    result = read_notes("biology.md", notes_dir=tmp_path)
    assert "text" in result
    assert "Cell division" in result["text"]


def test_read_notes_path_traversal(tmp_path):
    result = read_notes("../../secret.txt", notes_dir=tmp_path)
    assert result["error"] == "SecurityError"
    assert "Path traversal" in result["message"]


def test_read_notes_fuzzy_suggestion(tmp_path):
    (tmp_path / "biology.md").write_text("Content", encoding="utf-8")

    result = read_notes("bilogy.md", notes_dir=tmp_path)
    assert result["error"] == "FileNotFoundError"
    assert "biology.md" in result["hint"]


def test_make_quiz_success():
    notes_content = """# Cell Biology
## Mitosis
- **Prophase**: Chromatin condenses into chromosomes.
- **Metaphase**: Chromosomes align at the equator.
- **Anaphase**: Sister chromatids separate.
- **Telophase**: Nuclear envelope reforms.
"""
    result = make_quiz(notes_content, n=4)
    assert "questions" in result
    assert len(result["questions"]) == 4
    for item in result["questions"]:
        assert "q" in item and "a" in item


def test_make_quiz_invalid_inputs():
    res1 = make_quiz("", n=5)
    assert res1["error"] == "ValueError"

    res2 = make_quiz("valid text", n=15)
    assert res2["error"] == "ValueError"


def test_save_file_and_overwrite(tmp_path):
    out_dir = tmp_path / "output"

    # First write
    res1 = save_file("summary.md", "First content", output_dir=out_dir)
    assert "path" in res1
    assert (out_dir / "summary.md").read_text(encoding="utf-8") == "First content"

    # Attempt overwrite without flag
    res2 = save_file("summary.md", "Second content", output_dir=out_dir, overwrite=False)
    assert res2["error"] == "FileExistsError"

    # Overwrite with flag
    res3 = save_file("summary.md", "Second content", output_dir=out_dir, overwrite=True)
    assert "path" in res3
    assert (out_dir / "summary.md").read_text(encoding="utf-8") == "Second content"


def test_save_file_path_traversal(tmp_path):
    out_dir = tmp_path / "output"
    result = save_file("../escape.txt", "evil", output_dir=out_dir)
    assert result["error"] == "SecurityError"


def test_update_progress_validation():
    valid = update_progress("mitosis", 0.85, note="review anaphase")
    assert valid["ok"] is True
    assert valid["topic"] == "mitosis"
    assert valid["score"] == 0.85

    bad_score = update_progress("mitosis", 1.5)
    assert bad_score["error"] == "ValueError"

    empty_topic = update_progress("", 0.5)
    assert empty_topic["error"] == "ValueError"


def test_agent_recovers_from_misspelled_file(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "biology.md").write_text("Genetics and heredity notes.", encoding="utf-8")

    fake_llm = FakeLLM([
        # Step 1: LLM tries misspelled file
        {
            "thought": "Let me read bilogy.md.",
            "tool_call": {
                "name": "read_notes",
                "args": {"filename": "bilogy.md", "notes_dir": str(notes_dir)},
            },
        },
        # Step 2: LLM observes error and corrects to biology.md
        {
            "thought": "The file was not found, the hint says biology.md. Reading that.",
            "tool_call": {
                "name": "read_notes",
                "args": {"filename": "biology.md", "notes_dir": str(notes_dir)},
            },
        },
        # Step 3: Conclude
        {
            "thought": "I have the notes now.",
            "final_answer": "Successfully read biology notes.",
        },
    ])

    result = run_agent(goal="Study biology", llm=fake_llm, max_steps=5)
    assert result["status"] == "completed"
    assert result["step_count"] == 3
    assert result["steps"][0]["observation"]["error"] == "FileNotFoundError"
    assert "Genetics and heredity" in result["steps"][1]["observation"]["text"]


def test_agent_stops_after_max_retries(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()

    # Tool call will fail 3 times consecutively (initial + 2 retries)
    fake_llm = FakeLLM([
        {
            "thought": "Attempt 1",
            "tool_call": {"name": "read_notes", "args": {"filename": "ghost.md", "notes_dir": str(notes_dir)}},
        },
        {
            "thought": "Attempt 2 (retry 1)",
            "tool_call": {"name": "read_notes", "args": {"filename": "ghost.md", "notes_dir": str(notes_dir)}},
        },
        {
            "thought": "Attempt 3 (retry 2)",
            "tool_call": {"name": "read_notes", "args": {"filename": "ghost.md", "notes_dir": str(notes_dir)}},
        },
    ])

    result = run_agent(goal="Read missing file", llm=fake_llm, max_steps=10, max_retries=2)
    assert result["status"] == "retry_limit_exceeded"
    assert "failed after 2 retries" in result["final_answer"]
    assert "Please provide guidance" in result["final_answer"]
    assert result["step_count"] == 3

