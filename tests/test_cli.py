"""Unit tests for the CLI entry point, argument parsing, and interactive outputs."""

import json
from pathlib import Path
from study_agent.cli import format_step_for_terminal, main
from study_agent.memory import get_empty_memory, save_memory


def test_format_step_for_terminal():
    record_act = {
        "step": 1,
        "thought": "Need to read notes file.",
        "action": {"tool": "read_notes", "args": {"filename": "photosynthesis.md"}},
        "observation": {"text": "Photosynthesis is the process..."},
    }
    line = format_step_for_terminal(record_act)
    assert "[step 1]" in line
    assert "think: Need to read notes file." in line
    assert "act: read_notes" in line
    assert "look:" in line

    record_done = {
        "step": 4,
        "thought": "All done.",
        "action": None,
        "observation": {"final_answer": "Quiz created and saved successfully."},
    }
    done_line = format_step_for_terminal(record_done)
    assert "[step 4]" in done_line
    assert "final_answer:" in done_line


def test_cli_no_goal(capsys):
    ret = main([])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Error: Please provide a study goal" in captured.out


def test_cli_show_memory(tmp_path, capsys):
    mem_file = tmp_path / "memory.json"
    mem = get_empty_memory()
    mem["weak_spots"] = ["light-dependent reactions"]
    save_memory(mem, mem_file)

    ret = main(["--show-memory", "--memory-file", str(mem_file)])
    assert ret == 0
    captured = capsys.readouterr()
    assert "light-dependent reactions" in captured.out


def test_cli_reset_memory(tmp_path, monkeypatch, capsys):
    mem_file = tmp_path / "memory.json"
    mem = get_empty_memory()
    mem["weak_spots"] = ["light-dependent reactions"]
    save_memory(mem, mem_file)

    # Simulate user answering 'y'
    monkeypatch.setattr("builtins.input", lambda _: "y")

    ret = main(["--reset-memory", "--memory-file", str(mem_file)])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Memory has been reset" in captured.out

    # Verify reset
    content = json.loads(mem_file.read_text(encoding="utf-8"))
    assert content["weak_spots"] == []


def test_cli_full_execution_approved(tmp_path, monkeypatch, capsys):
    mem_file = tmp_path / "memory.json"
    mem = get_empty_memory()
    mem["weak_spots"] = ["light-dependent reactions"]
    save_memory(mem, mem_file)

    # User answers 'y' to plan approval, and 'y' to save_file confirmation
    inputs = iter(["y", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    ret = main([
        "Help me revise photosynthesis for Friday",
        "--memory-file", str(mem_file),
        "--mock",
    ])

    assert ret == 0
    captured = capsys.readouterr()
    assert "PLAN" in captured.out
    assert "[step 1] think:" in captured.out
    assert "Done in" in captured.out
    assert "Summary:" in captured.out

