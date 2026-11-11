"""Unit tests for safety controls: sandboxing, confirmation prompts, step limits, and JSONL logging."""

import json
from pathlib import Path
from study_agent.agent import run_agent
from study_agent.llm import FakeLLM
from study_agent.logger import AgentLogger
from study_agent.safety import (
    request_action_confirmation,
    sanitize_secrets,
    validate_safe_path,
)
from study_agent.tools import read_notes, save_file


def test_path_sandboxing(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "valid.md").write_text("Valid notes content.", encoding="utf-8")

    # Safe access
    is_safe, resolved, _ = validate_safe_path("valid.md", notes_dir)
    assert is_safe is True
    assert resolved == (notes_dir / "valid.md").resolve()

    # Traversal attempts
    is_safe, _, err = validate_safe_path("../../etc/passwd", notes_dir)
    assert is_safe is False
    assert "Path traversal" in err

    is_safe, _, _ = validate_safe_path("/etc/shadow", notes_dir)
    assert is_safe is False

    # Verify tools reject traversal
    res = read_notes("../../etc/passwd", notes_dir=notes_dir)
    assert res["error"] == "SecurityError"

    res_save = save_file("../../escape.txt", "data", output_dir=tmp_path / "output")
    assert res_save["error"] == "SecurityError"


def test_high_risk_confirmation_prompt():
    # User types 'y'
    confirmed = request_action_confirmation(
        "save_file",
        {"filename": "quiz.md", "content": "12345"},
        input_func=lambda _: "y",
    )
    assert confirmed is True

    # User types 'n'
    declined = request_action_confirmation(
        "save_file",
        {"filename": "quiz.md", "content": "12345"},
        input_func=lambda _: "n",
    )
    assert declined is False

    # Default answer is No (empty string)
    default_no = request_action_confirmation(
        "save_file",
        {"filename": "quiz.md", "content": "12345"},
        input_func=lambda _: "",
    )
    assert default_no is False


def test_agent_adapts_when_save_file_confirmation_denied(tmp_path):
    out_dir = tmp_path / "output"
    target_file = out_dir / "quiz.md"

    fake_llm = FakeLLM([
        {
            "thought": "I want to save the quiz to disk.",
            "tool_call": {
                "name": "save_file",
                "args": {"filename": "quiz.md", "content": "Q1: What is ATP?", "output_dir": str(out_dir)},
            },
        },
        {
            "thought": "User denied file write. I will adapt and show the quiz directly in final answer.",
            "final_answer": "Here is your quiz: Q1: What is ATP?",
        },
    ])

    result = run_agent(
        goal="Save quiz to file",
        llm=fake_llm,
        confirm_high_risk=True,
        confirmation_func=lambda tool, args: False,  # User declines
        max_steps=5,
    )

    assert result["status"] == "completed"
    assert not target_file.exists()  # File was NOT written
    assert result["steps"][0]["observation"]["error"] == "UserDeniedError"
    assert "Here is your quiz" in result["final_answer"]


def test_secret_sanitization():
    raw_text = "My API key is AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q and bearer is Bearer eyJhbGciOiJIUzI1NiJ9.test"
    cleaned = sanitize_secrets(raw_text)
    assert "[REDACTED_SECRET]" in cleaned
    assert "AIzaSy" not in cleaned

    secret_dict = {
        "api_key": "super_secret_token_12345",
        "nested": {"user_password": "mypassword123", "normal": "study notes"},
    }
    sanitized_dict = sanitize_secrets(secret_dict)
    assert sanitized_dict["api_key"] == "[REDACTED_SECRET]"
    assert sanitized_dict["nested"]["user_password"] == "[REDACTED_SECRET]"
    assert sanitized_dict["nested"]["normal"] == "study notes"


def test_agent_logger_jsonl(tmp_path):
    log_dir = tmp_path / "logs"
    logger = AgentLogger(log_dir=log_dir)

    fake_llm = FakeLLM([
        {
            "thought": "Direct final answer.",
            "final_answer": "Done studying.",
        }
    ])

    result = run_agent(
        goal="Test logging",
        llm=fake_llm,
        logger=logger,
        max_steps=3,
    )

    assert result["status"] == "completed"
    assert logger.log_file.exists()

    lines = logger.log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3  # task_start, user_decision (plan), step, task_completed
    events = [json.loads(line) for line in lines]

    event_types = [e["event"] for e in events]
    assert "task_start" in event_types
    assert "step" in event_types
    assert "task_completed" in event_types
    for e in events:
        assert "timestamp" in e

