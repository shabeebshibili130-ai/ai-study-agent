"""Unit tests for persistent memory, capping, corrupted files, and multi-task learning."""

import json
from pathlib import Path
from study_agent.agent import run_agent
from study_agent.llm import FakeLLM
from study_agent.memory import (
    add_task_summary,
    add_weak_spot,
    format_memory_for_prompt,
    get_empty_memory,
    load_memory,
    record_progress,
    reset_memory,
    save_memory,
)


def test_load_memory_nonexistent(tmp_path):
    mem_file = tmp_path / "memory.json"
    data, warning = load_memory(mem_file)
    assert data["progress"] == {}
    assert data["weak_spots"] == []
    assert warning is None


def test_load_memory_corrupted(tmp_path):
    mem_file = tmp_path / "memory.json"
    mem_file.write_text("{corrupt: json content", encoding="utf-8")

    data, warning = load_memory(mem_file)
    assert data["progress"] == {}
    assert warning is not None
    assert "Warning" in warning


def test_record_progress_auto_weak_spot():
    mem = get_empty_memory()

    # High score, no weak spot note
    record_progress(mem, topic="photosynthesis", score=0.9, note="mastered light cycle")
    assert "photosynthesis" in mem["progress"]
    assert len(mem["weak_spots"]) == 0

    # Low score (< 0.6)
    record_progress(mem, topic="mitochondria", score=0.4, note="needs review")
    assert "mitochondria" in mem["weak_spots"]

    # High score but explicit weak note
    record_progress(mem, topic="genetics", score=0.8, note="weak at pedigree analysis")
    assert any("pedigree" in spot for spot in mem["weak_spots"])


def test_task_summary_capping():
    mem = get_empty_memory()
    for i in range(60):
        add_task_summary(mem, goal=f"Goal {i}", summary=f"Summary {i}", max_past_tasks=50)

    assert len(mem["past_tasks"]) == 50
    # Earliest preserved should be Goal 10 (since 0..9 were dropped)
    assert mem["past_tasks"][0]["goal"] == "Goal 10"
    assert mem["past_tasks"][-1]["goal"] == "Goal 59"


def test_format_memory_for_prompt():
    mem = get_empty_memory()
    add_weak_spot(mem, "Calvin cycle RuBisCO enzyme")
    record_progress(mem, topic="Photosynthesis", score=0.85)
    add_task_summary(mem, goal="Revise Photosynthesis", summary="Created 5 practice questions")

    formatted = format_memory_for_prompt(mem)
    assert "Known Weak Spots:" in formatted
    assert "Calvin cycle RuBisCO" in formatted
    assert "Topic Progress:" in formatted
    assert "Photosynthesis: score 85%" in formatted
    assert "Recent Sessions:" in formatted


def test_reset_memory(tmp_path):
    mem_file = tmp_path / "memory.json"
    mem = get_empty_memory()
    add_weak_spot(mem, "Weak concept")
    save_memory(mem, mem_file)

    assert mem_file.exists()
    reset_memory(mem_file)

    loaded, _ = load_memory(mem_file)
    assert loaded["weak_spots"] == []


def test_multi_session_memory_persistence(tmp_path):
    mem_file = tmp_path / "memory.json"

    # Session 1: Student struggles with mitochondria
    fake_llm_1 = FakeLLM([
        {
            "thought": "Recording progress with low score.",
            "tool_call": {
                "name": "update_progress",
                "args": {"topic": "mitochondria", "score": 0.45, "note": "weak at electron transport chain"},
            },
        },
        {
            "thought": "Finished study session.",
            "final_answer": "Recorded weak spot in electron transport chain for mitochondria.",
        },
    ])

    res1 = run_agent(
        goal="Study cellular respiration",
        llm=fake_llm_1,
        memory_path=mem_file,
    )
    assert res1["status"] == "completed"
    assert mem_file.exists()

    # Session 2: Fresh session asking what to revise
    fake_llm_2 = FakeLLM([
        {
            "thought": "Looking at memory, student was weak at mitochondria electron transport chain.",
            "final_answer": "You should revise the electron transport chain in mitochondria.",
        }
    ])

    res2 = run_agent(
        goal="What should I revise today?",
        llm=fake_llm_2,
        memory_path=mem_file,
    )
    assert res2["status"] == "completed"

    # Verify that the LLM received the weak spot in its prompt context
    first_call_prompt = fake_llm_2.calls[0]["prompt"]
    assert "electron transport chain" in first_call_prompt
    assert "mitochondria" in first_call_prompt

