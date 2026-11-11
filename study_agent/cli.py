"""Command-line interface for the AI Study Agent."""

import argparse
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from study_agent.agent import run_agent
from study_agent.llm import BaseLLM, FakeLLM, RealLLM
from study_agent.logger import AgentLogger
from study_agent.memory import (
    DEFAULT_MEMORY_FILE,
    format_memory_for_prompt,
    load_memory,
    reset_memory,
)


def format_step_for_terminal(step_record: Dict[str, Any]) -> str:
    """Formats a single think-act-look iteration for terminal display."""
    step_num = step_record.get("step", 1)
    thought = step_record.get("thought", "")
    action = step_record.get("action")
    observation = step_record.get("observation", {})

    thought_preview = (thought[:60] + "...") if len(thought) > 60 else thought

    if action:
        tool_name = action.get("tool", "")
        # Summarize observation
        if "error" in observation:
            look_summary = f"error: {observation.get('message', '')}"
        elif "text" in observation:
            look_summary = f"{len(observation['text']):,} chars"
        elif "questions" in observation:
            look_summary = f"{len(observation['questions'])} questions"
        elif "path" in observation:
            look_summary = f"wrote {observation['path']}"
        elif observation.get("ok"):
            look_summary = "ok"
        else:
            look_summary = str(observation)[:40]

        return f"[step {step_num}] think: {thought_preview} → act: {tool_name} → look: {look_summary}"
    else:
        # Final step
        final_ans = observation.get("final_answer", "")
        preview = (final_ans[:70] + "...") if len(final_ans) > 70 else final_ans
        return f"[step {step_num}] think: {thought_preview} → final_answer: {preview}"


def build_mock_llm(goal: str) -> BaseLLM:
    """Constructs a realistic FakeLLM script for demo and mock runs."""
    goal_lower = goal.lower()
    # Bug 7 fix: fall back to "photosynthesis" (a file that exists) instead of "notes"
    if "photosynthesis" in goal_lower:
        topic = "photosynthesis"
    elif "mitochondria" in goal_lower or "respiration" in goal_lower:
        topic = "mitochondria"
    else:
        topic = "photosynthesis"   # safe default — file always exists in notes/
    filename = f"{topic}.md"

    responses = [
        {
            "thought": f"I need to read the study notes for {topic}.",
            "tool_call": {
                "name": "read_notes",
                "args": {"filename": filename},
            },
        },
        {
            "thought": f"Creating 5 quiz questions based on the {topic} notes.",
            "tool_call": {
                "name": "make_quiz",
                "args": {
                    "text": f"Study notes for {topic}.\n## Key Concepts\n- **Mechanism**: Essential biological process.",
                    "n": 5,
                },
            },
        },
        {
            "thought": f"Saving the generated quiz to output/quiz_{topic}.md.",
            "tool_call": {
                "name": "save_file",
                "args": {
                    "filename": f"quiz_{topic}.md",
                    "content": f"# Quiz: {topic.capitalize()}\n1. What is the primary function of {topic}?\n",
                    "overwrite": True,
                },
            },
        },
        {
            "thought": f"Updating progress on {topic}.",
            "tool_call": {
                "name": "update_progress",
                "args": {
                    "topic": topic,
                    "score": 0.85,
                    "note": f"Completed revision of {topic}.",
                },
            },
        },
        {
            "thought": f"Revision plan for {topic} complete.",
            "final_answer": f"Completed study session on {topic}! Created 5 quiz questions and recorded your progress.",
        },
    ]
    return FakeLLM(responses)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="AI Study Agent: Goal-driven student revision assistant.",
    )
    parser.add_argument(
        "goal",
        nargs="?",
        default=None,
        help="Study goal in plain English, e.g. 'Help me revise photosynthesis for Friday'",
    )
    parser.add_argument(
        "--show-memory",
        action="store_true",
        help="View stored progress, weak spots, and task summaries.",
    )
    parser.add_argument(
        "--reset-memory",
        action="store_true",
        help="Clear persistent memory.json after confirmation.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum allowed agent steps (default: 15).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Connect to real LLM API (requires GEMINI_API_KEY or OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Run in mock mode with FakeLLM for deterministic offline execution (default if --live not set).",
    )
    parser.add_argument(
        "--memory-file",
        type=str,
        default=str(DEFAULT_MEMORY_FILE),
        help="Path to memory.json file.",
    )

    args = parser.parse_args(argv)

    # 1. Handle --show-memory
    if args.show_memory:
        mem, warning = load_memory(args.memory_file)
        if warning:
            print(warning)
        print("\n--- STUDENT MEMORY ---")
        print(format_memory_for_prompt(mem))
        print("----------------------\n")
        return 0

    # 2. Handle --reset-memory
    if args.reset_memory:
        confirm = input(f"Reset memory file at '{args.memory_file}'? [y/N]: ").strip().lower()
        if confirm in ("y", "yes"):
            reset_memory(args.memory_file)
            print("Memory has been reset.")
        else:
            print("Reset cancelled.")
        return 0

    # 3. Ensure a goal was provided
    if not args.goal:
        parser.print_help()
        print("\nError: Please provide a study goal in quotes, e.g.:")
        print('  python cli.py "Help me revise photosynthesis for Friday"')
        return 1

    # 4. Display Memory Context
    mem, warning = load_memory(args.memory_file)
    if warning:
        print(f"[{warning}]")

    weak_spots = mem.get("weak_spots", [])
    if weak_spots:
        print(f"\nMemory: weak spot noted last time → \"{weak_spots[-1]}\"")

    # 5. Initialize LLM & Logger
    logger = AgentLogger()
    if args.live:
        try:
            llm = RealLLM()
            print(f"Using live LLM provider: {llm.provider} ({llm.model})")
        except Exception as e:
            print(f"\nConfiguration Error: {str(e)}")
            return 1
    else:
        llm = build_mock_llm(args.goal)

    print(f"\nInitiating Study Agent with Goal: \"{args.goal}\"")

    def on_step_terminal(step_record: Dict[str, Any]) -> None:
        print(format_step_for_terminal(step_record))

    # 6. Run Agent
    result = run_agent(
        goal=args.goal,
        llm=llm,
        max_steps=args.max_steps,
        memory=mem,
        memory_path=args.memory_file,
        require_plan=True,
        auto_approve_plan=False,     # Request user approval for plan
        confirm_high_risk=True,      # Ask before writing files
        logger=logger,
        on_step=on_step_terminal,
    )

    # 7. Print Final Status
    print()
    if result["status"] == "completed":
        print(f"Done in {result['step_count']} steps. Log: {logger.log_file}")
        if result.get("final_answer"):
            print(f"\nSummary:\n{result['final_answer']}")
        return 0
    elif result["status"] == "aborted":
        print(f"Task cancelled. Log: {logger.log_file}")
        return 0
    else:
        print(f"Stopped ({result['status']}): {result.get('final_answer')}. Log: {logger.log_file}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

