"""Append-only JSONL run logger for auditing and debugging."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional
from study_agent.safety import sanitize_secrets

DEFAULT_LOGS_DIR = Path("logs")


class AgentLogger:
    """Writes sanitized, timestamped, append-only JSONL log records."""

    def __init__(self, log_dir: Optional[Path | str] = None):
        self.log_dir = Path(log_dir) if log_dir else DEFAULT_LOGS_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"{today}.jsonl"

    def log(self, event: str, data: Dict[str, Any]) -> None:
        """Appends a single JSON line record to today's log file."""
        now_iso = datetime.now(timezone.utc).isoformat()
        sanitized_data = sanitize_secrets(data)
        record = {
            "timestamp": now_iso,
            "event": event,
            **sanitized_data,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def log_step(self, step_record: Dict[str, Any]) -> None:
        """Logs a single think -> act -> look loop step."""
        self.log("step", {"record": step_record})

    def log_user_decision(
        self,
        decision_type: str,
        approved: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Logs interactive approvals or rejections from the user."""
        self.log(
            "user_decision",
            {
                "decision_type": decision_type,
                "approved": approved,
                "details": details or {},
            },
        )

