"""Persistent memory manager for student progress, weak spots, and task history."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_MEMORY_FILE = Path("memory.json")
MAX_PAST_TASKS = 50


def get_empty_memory() -> Dict[str, Any]:
    """Returns a fresh memory structure with default fields."""
    return {
        "progress": {},
        "weak_spots": [],
        "preferences": {
            "default_quiz_length": 5,
        },
        "past_tasks": [],
    }


def load_memory(filepath: Optional[Path | str] = None) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Loads memory from a JSON file.
    If missing or corrupt, returns a clean default schema with a warning message.
    """
    path = Path(filepath) if filepath else DEFAULT_MEMORY_FILE
    if not path.exists():
        return get_empty_memory(), None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return get_empty_memory(), f"Warning: Corrupted memory file at {path}. Starting fresh."

        # Ensure all required keys exist
        empty = get_empty_memory()
        for key, default_val in empty.items():
            if key not in data:
                data[key] = default_val

        return data, None
    except Exception as e:
        return get_empty_memory(), f"Warning: Failed to load {path} ({str(e)}). Starting fresh."


def save_memory(memory_data: Dict[str, Any], filepath: Optional[Path | str] = None) -> None:
    """Saves memory dictionary to JSON file."""
    path = Path(filepath) if filepath else DEFAULT_MEMORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory_data, indent=2), encoding="utf-8")


def reset_memory(filepath: Optional[Path | str] = None) -> None:
    """Resets the memory file to a fresh empty state."""
    save_memory(get_empty_memory(), filepath=filepath)


def record_progress(
    memory_data: Dict[str, Any],
    topic: str,
    score: float,
    note: str = "",
) -> None:
    """Records or updates student progress on a specific topic."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if "progress" not in memory_data:
        memory_data["progress"] = {}

    memory_data["progress"][topic] = {
        "score": score,
        "note": note,
        "last_studied": now_iso,
    }

    # Automatically add to weak_spots if score is low or note highlights difficulty
    if score < 0.6:
        add_weak_spot(memory_data, topic)
    elif "weak" in note.lower() or "struggle" in note.lower():
        add_weak_spot(memory_data, f"{topic} ({note})" if note else topic)


def add_weak_spot(memory_data: Dict[str, Any], item: str) -> None:
    """Appends an item to weak spots if not already present."""
    if "weak_spots" not in memory_data:
        memory_data["weak_spots"] = []

    cleaned = item.strip()
    if cleaned and cleaned not in memory_data["weak_spots"]:
        memory_data["weak_spots"].append(cleaned)


def add_task_summary(
    memory_data: Dict[str, Any],
    goal: str,
    summary: str,
    max_past_tasks: int = MAX_PAST_TASKS,
) -> None:
    """Appends a task record and caps the total past tasks list."""
    if "past_tasks" not in memory_data:
        memory_data["past_tasks"] = []

    now_iso = datetime.now(timezone.utc).isoformat()
    memory_data["past_tasks"].append({
        "date": now_iso,
        "goal": goal,
        "summary": summary,
    })

    # Enforce maximum tasks cap (keep the most recent)
    if len(memory_data["past_tasks"]) > max_past_tasks:
        memory_data["past_tasks"] = memory_data["past_tasks"][-max_past_tasks:]


def format_memory_for_prompt(memory_data: Dict[str, Any]) -> str:
    """Formats the memory contents into a concise summary block for the LLM prompt."""
    sections: List[str] = []

    # Weak spots
    weak_spots = memory_data.get("weak_spots", [])
    if weak_spots:
        sections.append("Known Weak Spots:\n- " + "\n- ".join(weak_spots))

    # Topic progress
    progress = memory_data.get("progress", {})
    if progress:
        prog_lines = [
            f"- {topic}: score {info.get('score', 0):.0%} (last studied {info.get('last_studied', 'N/A')[:10]})"
            + (f" Note: {info.get('note')}" if info.get("note") else "")
            for topic, info in progress.items()
        ]
        sections.append("Topic Progress:\n" + "\n".join(prog_lines))

    # Preferences
    prefs = memory_data.get("preferences", {})
    if prefs:
        pref_lines = [f"- {k}: {v}" for k, v in prefs.items()]
        sections.append("Student Preferences:\n" + "\n".join(pref_lines))

    # Recent past tasks (last 3)
    past = memory_data.get("past_tasks", [])
    if past:
        recent = past[-3:]
        task_lines = [f"- [{t.get('date', '')[:10]}] Goal: {t.get('goal')} -> {t.get('summary')}" for t in recent]
        sections.append("Recent Sessions:\n" + "\n".join(task_lines))

    return "\n\n".join(sections) if sections else "No prior study memory recorded."
