"""LLM interface and implementations (BaseLLM, FakeLLM, RealLLM)."""

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class BaseLLM(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a response given a prompt and optional context.

        Returns a dictionary with:
        - "thought": str
        - "tool_call": Optional[Dict[str, Any]] with "name" and "args"
        - "final_answer": Optional[str]
        - or "plan": Optional[List[Dict[str, Any]]] for planning steps
        """
        pass


class FakeLLM(BaseLLM):
    """
    Scripted LLM for deterministic, zero-cost, offline testing.
    Can be loaded with a single response or a sequence of responses.
    """

    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None):
        self.responses: List[Dict[str, Any]] = list(responses or [])
        self.calls: List[Dict[str, Any]] = []

    def add_response(self, response: Dict[str, Any]) -> None:
        """Add a scripted response to the queue."""
        self.responses.append(response)

    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record the call and return the next scripted response."""
        ctx = context or {}
        self.calls.append({"prompt": prompt, "context": ctx})

        # If call is for planning or re-planning
        if ctx.get("action") in ("create_plan", "revise_plan"):
            if self.responses and "plan" in self.responses[0]:
                return self.responses.pop(0)
            return {}

        if not self.responses:
            return {
                "thought": "No further scripted actions available.",
                "final_answer": "Terminated: No more scripted responses in FakeLLM.",
            }
        return self.responses.pop(0)


class RealLLM(BaseLLM):
    """
    Production LLM client supporting Google Gemini and OpenAI-compatible APIs.
    Reads credentials securely from environment variables.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: str = "auto",
        model: Optional[str] = None,
        timeout: int = 30,
    ):
        self.gemini_key = api_key or os.getenv("GEMINI_API_KEY")
        self.openai_key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = timeout

        if provider == "auto":
            if self.gemini_key:
                self.provider = "gemini"
                self.model = model or "gemini-2.0-flash"
                self.api_key = self.gemini_key
            elif self.openai_key:
                self.provider = "openai"
                self.model = model or "gpt-4o-mini"
                self.api_key = self.openai_key
            else:
                raise ValueError(
                    "No LLM API key detected. Please set GEMINI_API_KEY or OPENAI_API_KEY in your environment or .env file."
                )
        elif provider == "gemini":
            if not self.gemini_key:
                raise ValueError("GEMINI_API_KEY not found in environment.")
            self.provider = "gemini"
            self.model = model or "gemini-2.0-flash"
            self.api_key = self.gemini_key
        elif provider == "openai":
            if not self.openai_key:
                raise ValueError("OPENAI_API_KEY not found in environment.")
            self.provider = "openai"
            self.model = model or "gpt-4o-mini"
            self.api_key = self.openai_key
        else:
            raise ValueError(f"Unsupported provider: '{provider}'. Supported: 'gemini', 'openai'.")

    def _call_gemini(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            candidates = body.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return "{}"

    def _call_openai(self, prompt: str) -> str:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an autonomous AI Study Agent. Output strictly valid JSON matching the requested structure.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return "{}"

    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Sends prompt to the configured LLM API and parses the JSON decision."""
        ctx = context or {}
        action = ctx.get("action")

        if action == "create_plan":
            instruction = (
                "You are planning a study revision workflow. Produce JSON with:\n"
                '{"plan": [{"tool": "read_notes", "description": "...", "args_hint": "..."}]}\n\n'
            )
        else:
            instruction = (
                "You are an AI Study Agent executing a task. Return strictly JSON with:\n"
                '{"thought": "Your reasoning", "tool_call": {"name": "...", "args": {...}}, "final_answer": null}\n'
                "OR if done:\n"
                '{"thought": "Summary reasoning", "tool_call": null, "final_answer": "Final message to student"}\n\n'
            )

        full_prompt = instruction + prompt

        try:
            if self.provider == "gemini":
                raw_response = self._call_gemini(full_prompt)
            else:
                raw_response = self._call_openai(full_prompt)

            return self._parse_json(raw_response)
        except Exception as e:
            return {
                "thought": f"Encountered LLM API error: {str(e)}",
                "final_answer": f"Unable to reach LLM provider ({str(e)}). Please check network and API key.",
            }

    def _parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Extracts JSON object from model response text."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            return {
                "thought": "Failed to parse JSON response from LLM.",
                "final_answer": cleaned or "Malformed LLM response.",
            }
