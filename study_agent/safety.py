"""Safety module: path sandboxing, high-risk confirmations, and secret sanitization."""

from pathlib import Path
import re
from typing import Any, Callable, Dict, Optional, Tuple

DEFAULT_NOTES_DIR = Path("notes")
DEFAULT_OUTPUT_DIR = Path("output")

# Regex pattern for potential API keys or secrets
SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z-_]{35})"),                      # Google API keys
    re.compile(r"(sk-[a-zA-Z0-9_-]{20,})"),                     # OpenAI style keys
    re.compile(r"(ghp_[a-zA-Z0-9]{36})"),                       # GitHub PAT
    re.compile(r"(Bearer\s+[a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
]


def validate_safe_path(
    filename: str,
    allowed_dir: Path | str,
) -> Tuple[bool, Optional[Path], Optional[str]]:
    """
    Validates that a given filename resolves strictly inside the allowed directory.
    Returns (is_safe, resolved_path, error_message).
    """
    base_dir = Path(allowed_dir).resolve()

    # Reject obvious traversal attempts in the raw string
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return False, None, f"Access denied: Path traversal detected in '{filename}'."

    try:
        resolved = (base_dir / filename).resolve()
        resolved.relative_to(base_dir)
        return True, resolved, None
    except (ValueError, Exception):
        return False, None, f"Access denied: Path '{filename}' escapes allowed directory {base_dir}."


def request_action_confirmation(
    tool_name: str,
    args: Dict[str, Any],
    input_func: Optional[Callable[[str], str]] = None,
) -> bool:
    """
    Prompts the user for explicit y/N confirmation before executing high-risk tools.
    Default is No.
    """
    prompt_input = input_func if input_func is not None else input
    target = args.get("filename", "unknown")
    content = args.get("content", "")
    size_bytes = len(content.encode("utf-8")) if isinstance(content, str) else 0
    size_kb = size_bytes / 1024

    prompt_msg = f"\n  ⚠ High-Risk Action: Tool '{tool_name}' will write {target} ({size_kb:.1f} KB)? [y/N]: "
    try:
        choice = prompt_input(prompt_msg).strip().lower()
        return choice in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def sanitize_secrets(obj: Any) -> Any:
    """
    Recursively scans strings, dictionaries, and lists to redact known secrets or sensitive tokens.
    """
    if isinstance(obj, str):
        sanitized = obj
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
        return sanitized
    elif isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if any(term in k.lower() for term in ("key", "secret", "token", "password", "auth")):
                cleaned[k] = "[REDACTED_SECRET]"
            else:
                cleaned[k] = sanitize_secrets(v)
        return cleaned
    elif isinstance(obj, list):
        return [sanitize_secrets(item) for item in obj]
    return obj

