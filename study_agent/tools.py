"""Tool registry, definitions, and execution handlers."""

from dataclasses import dataclass
import difflib
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional
from study_agent.safety import validate_safe_path


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    risk: str  # "low" or "high"
    func: Callable[..., Dict[str, Any]]


DEFAULT_NOTES_DIR = Path("notes")
DEFAULT_OUTPUT_DIR = Path("output")


def read_notes(filename: str, notes_dir: Optional[Path | str] = None) -> Dict[str, Any]:
    """Reads a study notes file from the notes folder and returns its text."""
    base_dir = Path(notes_dir) if notes_dir else DEFAULT_NOTES_DIR
    is_safe, target_path, err = validate_safe_path(filename, base_dir)
    if not is_safe or target_path is None:
        return {
            "error": "SecurityError",
            "message": err or f"Access denied: Path traversal detected for '{filename}'.",
            "hint": "Specify a filename within notes/ only without '..' or absolute paths.",
        }

    base_dir = base_dir.resolve()

    if not target_path.is_file():
        # Look for suggestions in the base_dir
        available = [p.name for p in base_dir.glob("*.md")] if base_dir.exists() else []
        matches = difflib.get_close_matches(filename, available, n=1, cutoff=0.5)
        if matches:
            hint = f"File not found. Did you mean '{matches[0]}'?"
        elif available:
            hint = f"File not found in notes/. Available files: {', '.join(available)}"
        else:
            hint = "Notes folder is empty or not found."

        return {
            "error": "FileNotFoundError",
            "message": f"Notes file '{filename}' was not found.",
            "hint": hint,
        }

    try:
        text = target_path.read_text(encoding="utf-8")
        return {"text": text}
    except Exception as e:
        return {
            "error": "ReadError",
            "message": f"Failed to read '{filename}': {str(e)}",
            "hint": "Check file permissions and encoding.",
        }


def make_quiz(text: str, n: int = 5) -> Dict[str, Any]:
    """Generates N quiz questions with answers from a given block of text."""
    if not isinstance(text, str) or not text.strip():
        return {
            "error": "ValueError",
            "message": "Argument 'text' must be a non-empty string.",
            "hint": "Provide study notes text to generate quiz questions.",
        }

    if not isinstance(n, int) or not (1 <= n <= 10):
        return {
            "error": "ValueError",
            "message": f"Argument 'n' must be an integer between 1 and 10 (received {n}).",
            "hint": "Specify n as an integer between 1 and 10.",
        }

    questions: List[Dict[str, str]] = []

    # Extract key concepts based on headers, bold terms, or bullet points
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Look for patterns like "## Title" or "- **Key**: Explanation" or "Key: Explanation"
    candidates = []
    for line in lines:
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            if heading and heading.lower() not in ["notes", "overview"]:
                candidates.append((f"What is the significance of {heading}?", f"See section on {heading}."))
        elif "**" in line and ":" in line:
            parts = line.split(":", 1)
            term = parts[0].replace("**", "").replace("-", "").strip()
            definition = parts[1].strip()
            if term and definition:
                candidates.append((f"What is {term}?", definition))
        elif line.startswith("- ") or line.startswith("* "):
            content = line[2:].strip()
            if len(content) > 10:
                candidates.append((f"Explain: {content[:40]}...", content))

    # Add candidates to questions
    for q, a in candidates:
        if len(questions) < n:
            questions.append({"q": q, "a": a})

    # If we need more questions, create general synthesis questions from text lines
    idx = 0
    while len(questions) < n and idx < len(lines):
        line = lines[idx]
        if len(line) > 15 and not line.startswith("#"):
            q_text = f"According to the notes, what can be stated about: {line[:35]}...?"
            if not any(item["q"] == q_text for item in questions):
                questions.append({"q": q_text, "a": line})
        idx += 1

    # Fallback to ensure exactly n questions
    while len(questions) < n:
        num = len(questions) + 1
        questions.append({
            "q": f"Key question {num} on the provided topic",
            "a": f"Key takeaway {num} from the study notes.",
        })

    return {"questions": questions}


def save_file(
    filename: str,
    content: str,
    output_dir: Optional[Path | str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Writes text (summary, quiz, schedule) to output folder. Never overwrites without confirmation."""
    base_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    is_safe, target_path, err = validate_safe_path(filename, base_dir)
    if not is_safe or target_path is None:
        return {
            "error": "SecurityError",
            "message": err or f"Access denied: Path traversal detected for '{filename}'.",
            "hint": "Specify a filename within output/ only without '..' or absolute paths.",
        }

    base_dir = base_dir.resolve()

    if target_path.exists() and not overwrite:
        return {
            "error": "FileExistsError",
            "message": f"File '{filename}' already exists and overwrite is set to False.",
            "hint": "Provide a different filename or explicitly confirm overwrite.",
        }

    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return {
            "path": str(target_path),
            "bytes_written": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {
            "error": "WriteError",
            "message": f"Failed to write file '{filename}': {str(e)}",
            "hint": "Check disk space and write permissions.",
        }


def update_progress(topic: str, score: float, note: str = "") -> Dict[str, Any]:
    """Records a topic score or weak spot in memory."""
    if not isinstance(topic, str) or not topic.strip():
        return {
            "error": "ValueError",
            "message": "Argument 'topic' must be a non-empty string.",
            "hint": "Specify a valid study topic (e.g. 'photosynthesis').",
        }

    try:
        score_val = float(score)
    except (ValueError, TypeError):
        return {
            "error": "ValueError",
            "message": f"Argument 'score' must be a numeric float (received {score}).",
            "hint": "Provide a numeric score between 0.0 and 1.0 (e.g. 0.85).",
        }

    if not (0.0 <= score_val <= 1.0):
        return {
            "error": "ValueError",
            "message": f"Argument 'score' must be between 0.0 and 1.0 (received {score_val}).",
            "hint": "Provide a score between 0.0 and 1.0.",
        }

    return {
        "ok": True,
        "topic": topic.strip(),
        "score": score_val,
        "note": note.strip() if isinstance(note, str) else "",
    }


TOOLS: Dict[str, Tool] = {
    "read_notes": Tool(
        name="read_notes",
        description="Reads a study notes file from the notes folder and returns its text.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "The name of the file to read, e.g. 'photosynthesis.md'"},
                "notes_dir": {"type": "string", "description": "Optional notes directory path"},
            },
            "required": ["filename"],
        },
        risk="low",
        func=read_notes,
    ),
    "make_quiz": Tool(
        name="make_quiz",
        description="Generates N quiz questions with answers from a given block of text.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Source text to base questions on"},
                "n": {"type": "integer", "description": "Number of questions to generate (1-10)"},
            },
            "required": ["text"],
        },
        risk="low",
        func=make_quiz,
    ),
    "save_file": Tool(
        name="save_file",
        description="Writes text (e.g. summary, quiz, study schedule) to the output folder. Never overwrites without confirmation.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Target filename in output folder"},
                "content": {"type": "string", "description": "Text content to save"},
                "output_dir": {"type": "string", "description": "Optional output directory path"},
                "overwrite": {"type": "boolean", "description": "Whether to overwrite existing file"},
            },
            "required": ["filename", "content"],
        },
        risk="high",
        func=save_file,
    ),
    "update_progress": Tool(
        name="update_progress",
        description="Records a topic score or weak spot in memory.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The subject topic studied"},
                "score": {"type": "number", "description": "Student score between 0.0 and 1.0"},
                "note": {"type": "string", "description": "Optional note regarding weak spots"},
            },
            "required": ["topic", "score"],
        },
        risk="low",
        func=update_progress,
    ),
}


def dispatch_tool(name: str, args: Dict[str, Any], registry: Optional[Dict[str, Tool]] = None) -> Dict[str, Any]:
    """Safely executes a registered tool and returns a structured output or error dictionary."""
    reg = registry if registry is not None else TOOLS

    if name not in reg:
        return {
            "error": "UnknownToolError",
            "message": f"Tool '{name}' is not registered.",
            "hint": f"Choose from available tools: {', '.join(reg.keys())}",
        }

    tool = reg[name]
    try:
        return tool.func(**args)
    except TypeError as te:
        return {
            "error": "InvalidArgumentsError",
            "message": f"Invalid arguments for tool '{name}': {str(te)}",
            "hint": f"Check tool parameter schema: {tool.parameters}",
        }
    except Exception as e:
        return {
            "error": type(e).__name__,
            "message": f"Tool '{name}' raised an unexpected error: {str(e)}",
            "hint": "Inspect tool arguments and retry.",
        }
