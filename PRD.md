# PRD: AI Study Agent

**Version:** 1.0
**Date:** 2026-11-10
**Status:** Draft

---

## 1. Overview

The AI Study Agent is a small, command-line agent that helps a student study. Given a goal such as *"Help me revise photosynthesis for Friday"*, it makes a plan, uses a few tools to read notes, create quiz questions, and schedule study sessions, and remembers progress between sessions.

The project is also a teaching build: every requirement maps to a lesson (L1–L8) so the finished agent demonstrates each core agent concept in a minimal, readable codebase.

## 2. Goals and Non-Goals

### Goals
- Demonstrate a clean **think → act → look** agent loop.
- Use **2–4 well-described tools**.
- Recover gracefully when a tool fails.
- Remember the student's progress **between tasks**.
- **Plan before acting**.
- Be **safe by default**: ask before risky actions, cap steps, log everything.
- Be **testable**: run deterministically with a fake LLM, then validate with a real one.

### Non-Goals
- No web UI, mobile app, or multi-user accounts.
- No autonomous web browsing or access to external accounts.
- No fine-tuning or custom models.
- No more than 4 tools (scope is intentionally small).

## 3. Target User

A student (high school or college) who keeps notes as local text/markdown files and wants help summarizing, quizzing, and planning revision.

## 4. User Stories

| # | As a student, I want to... | So that... |
|---|---|---|
| U1 | give a study goal in plain English | the agent figures out the steps |
| U2 | see the plan before anything runs | I can approve or change it |
| U3 | get quiz questions from my notes | I can test myself |
| U4 | have the agent remember what I got wrong | next session focuses on weak spots |
| U5 | be asked before files are written or changed | my notes are never damaged unexpectedly |
| U6 | read a log of what the agent did | I can trust and debug it |

## 5. Functional Requirements

### FR1: Agent Loop (think → act → look) 📘 L1, L3

The agent runs a repeating cycle until the goal is met or a stop condition is hit:

1. **Think:** the LLM receives the goal, plan, memory, and prior observations, then decides the next action (a tool call or a final answer).
2. **Act:** the agent executes the chosen tool with the given arguments.
3. **Look:** the tool result (or error) is added to the context as an observation.
4. Repeat.

**Acceptance criteria**
- The loop is implemented in a single, readable function (`run_agent`).
- Each iteration is logged as `{step, thought, action, observation}`.
- The loop exits when the LLM returns a `final_answer`, the step limit is reached, or the user cancels.

```
        ┌──────────────────────────────┐
        ▼                              │
     THINK ──► ACT (tool call) ──► LOOK (observe result)
        │
        └──► final_answer ──► DONE
```

### FR2: Tools (2–4, clearly described) 📘 L2

Each tool has a name, a plain-language description, a typed input schema, and a defined output/error format. The LLM only sees these descriptions, so they must be precise.

| Tool | Description | Inputs | Output | Risk |
|---|---|---|---|---|
| `read_notes` | Reads a study notes file from the notes folder and returns its text. | `filename: str` | `{text: str}` | Low (read-only) |
| `make_quiz` | Generates N quiz questions with answers from a given block of text. | `text: str`, `n: int (1–10)` | `{questions: [{q, a}]}` | Low |
| `save_file` | Writes text (e.g. summary, quiz, study schedule) to the output folder. Never overwrites without confirmation. | `filename: str`, `content: str` | `{path: str}` | **High (writes)** |
| `update_progress` | Records a topic score or weak spot in memory. | `topic: str`, `score: float (0–1)`, `note: str` | `{ok: true}` | Low |

**Acceptance criteria**
- Tool descriptions are stored in one registry (`TOOLS`) used both to build the LLM prompt and to dispatch calls.
- Calling an unknown tool or passing invalid arguments returns a structured error (see FR3), not a crash.
- Only tools in the registry can be called.

### FR3: Fixing Errors When a Tool Fails 📘 L2

Tools return errors as data, which the agent sees in the **look** step and can react to.

**Error format:** `{"error": "<type>", "message": "<human-readable>", "hint": "<what to try>"}`

**Behavior**
- **Recoverable errors** (file not found, bad argument, malformed output): the error is fed back to the LLM, which may retry with corrected arguments (e.g. list the closest filename match).
- **Retry limit:** max **2 retries** per tool call with the same intent. After that, the agent tells the user what failed and asks for guidance.
- **Unrecoverable errors** (permission denied, disk full): stop the step, log, and report to the user.
- The agent never silently ignores a failure or pretends it succeeded.

**Acceptance criteria**
- Test: `read_notes("bilogy.md")` fails → agent corrects to `biology.md` and succeeds.
- Test: a tool that always fails ends after 2 retries with a clear message.

### FR4: Memory Between Tasks 📘 L4

The agent persists a small memory file (`memory.json`) so later sessions build on earlier ones.

**What is stored**
- **Progress:** per-topic score and last-studied date.
- **Weak spots:** questions or topics the student got wrong.
- **Preferences:** e.g. preferred quiz length, study time of day.
- **Past task summaries:** one-line summary of each completed task.

**Behavior**
- At the start of a task, relevant memory is loaded and added to the prompt.
- At the end of a task, the agent writes a short summary and updates progress.
- The student can view (`--show-memory`) and clear (`--reset-memory`) memory.
- Memory is capped (e.g. last 50 task summaries) to keep prompts small.

**Acceptance criteria**
- Task 1 records "weak at mitochondria"; task 2 ("what should I revise?") mentions it without being told again.
- Corrupt or missing `memory.json` is handled by starting fresh with a warning.

### FR5: Plan Before Acting 📘 L5

Before the first tool call, the agent produces a numbered plan.

**Behavior**
1. Agent generates a plan: ordered steps, the tool each step will use, and the expected result.
2. The plan is shown to the student, who can **approve**, **edit**, or **cancel**.
3. During execution, the agent follows the plan and marks steps done.
4. If an observation makes the plan invalid (e.g. a file is missing), the agent **revises the plan**, shows the change, and continues.

**Example plan**
```
Goal: Revise photosynthesis for Friday
1. read_notes("photosynthesis.md")       → get source text
2. make_quiz(text, n=5)                  → create practice questions
3. save_file("quiz_photosynthesis.md")   → store quiz   [needs approval]
4. update_progress("photosynthesis", …)  → record result
```

**Acceptance criteria**
- No tool runs before a plan exists.
- The plan is stored in the log.
- Plan revisions are visible to the user.

### FR6: Safety: Ask First, Step Limit, Log 📘 L7

| Control | Requirement |
|---|---|
| **Ask first** | Any tool marked High risk (`save_file`) requires explicit `y/n` confirmation showing the exact filename and content preview. Plan approval (FR5) is also required. Default answer is **No**. |
| **Step limit** | Hard cap of **15 steps** per task (configurable). On reaching it, the agent stops and reports progress so far. |
| **Log** | Every task writes an append-only JSONL log (`logs/YYYY-MM-DD.jsonl`) with timestamp, step, thought, tool, arguments, result/error, and user decisions. |
| **Sandboxing** | File tools only access `notes/` (read) and `output/` (write). Path traversal (`../`) is rejected. |
| **No secrets** | API keys come from environment variables and are never logged. |

**Acceptance criteria**
- Declining confirmation skips the action and the agent adapts (e.g. prints content instead).
- An infinite-loop scenario halts at the step limit.
- `read_notes("../../etc/passwd")` is rejected and logged.

### FR7: Testing: Fake LLM First, Then Real 📘 L8

**Phase 1: Fake LLM (deterministic, free, fast)**
- A `FakeLLM` class implements the same interface as the real client but returns **scripted responses**.
- Used to test the loop, tool dispatch, error recovery, planning, memory, step limits, and confirmation prompts without network calls.

| Test | Scripted behavior | Expected |
|---|---|---|
| Happy path | plan → read → quiz → save → final | All steps logged, file saved |
| Tool failure | bad filename, then corrected | Recovers in 1 retry |
| Repeated failure | always-bad call | Stops after 2 retries |
| Step limit | LLM never finishes | Halts at 15 steps |
| Denied approval | user says "n" to `save_file` | File not written |
| Unknown tool | LLM calls `delete_all` | Structured error, no crash |
| Memory | run two tasks | Task 2 prompt includes Task 1 weak spot |

**Phase 2: Real LLM (small, targeted)**
- A short suite (3–5 goals) run against the real model, marked `@pytest.mark.live` and excluded from default runs.
- Checks **behavior**, not exact wording: a plan was produced, only valid tools were called, step count ≤ limit, no unapproved writes.
- Run manually before release; token cost is tracked.

**Acceptance criteria**
- `pytest` (fake LLM only) passes with no network and no API key.
- `pytest -m live` runs the real-LLM suite.
- Core logic has ≥ 80% test coverage.

## 6. Non-Functional Requirements

- **Simplicity:** the core agent is under ~500 lines of Python with no agent frameworks.
- **Performance:** each loop iteration adds < 100ms of overhead beyond LLM latency.
- **Portability:** Python 3.10+, runs on macOS, Linux, and Windows.
- **Cost control:** the step limit and memory cap bound token usage per task.
- **Readability:** each lesson concept (loop, tools, memory, plan, safety) lives in its own clearly named module.

## 7. Architecture

```
study_agent/
├── agent.py        # main loop: think → act → look            (L1, L3)
├── tools.py        # tool registry + 4 tools                  (L2)
├── planner.py      # plan creation, approval, revision        (L5)
├── memory.py       # load/save memory.json                    (L4)
├── safety.py       # confirmations, step limit, path checks   (L7)
├── logger.py       # JSONL logging                            (L7)
├── llm.py          # LLM interface, RealLLM, FakeLLM          (L8)
├── cli.py          # command-line entry point
├── notes/          # student's input notes
├── output/         # files the agent writes
├── logs/           # JSONL run logs
├── memory.json     # persistent memory
└── tests/
    ├── test_loop.py
    ├── test_tools.py
    ├── test_safety.py
    ├── test_memory.py
    └── test_live.py   # real LLM, opt-in
```

## 8. Example Session

```
$ python cli.py "Help me revise photosynthesis for Friday"

Memory: weak spot noted last time → "light-dependent reactions"

PLAN
 1. read_notes("photosynthesis.md")
 2. make_quiz(text, n=5)  (focus: light-dependent reactions)
 3. save_file("quiz_photosynthesis.md")
 4. update_progress("photosynthesis")
Approve plan? [y/N/edit]: y

[step 1] think: need the notes → act: read_notes → look: 2,140 chars
[step 2] think: make quiz → act: make_quiz → look: 5 questions
[step 3] think: save quiz → act: save_file
  ⚠ Write output/quiz_photosynthesis.md (1.2 KB)? [y/N]: y
[step 4] update_progress → ok

Done in 4 steps. Log: logs/2026-11-10.jsonl
```

## 9. Success Metrics

- All FR acceptance criteria pass in the fake-LLM suite.
- Live suite: ≥ 4 of 5 goals complete without unapproved writes or step-limit breaches.
- Median task completes in ≤ 8 steps.
- 0 file writes without explicit confirmation across all test runs.
- A new reader can map each module to its lesson (L1–L8) in under 10 minutes.

## 10. Milestones

| Milestone | Scope | Lessons |
|---|---|---|
| M1 | Loop + `FakeLLM` + first tool (`read_notes`) | L1, L3, L8 |
| M2 | Remaining tools + registry + error recovery | L2 |
| M3 | Memory | L4 |
| M4 | Planner with approval and revision | L5 |
| M5 | Safety layer + logging | L7 |
| M6 | Full fake-LLM test suite, then live suite | L8 |

## 11. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM emits malformed tool calls | Validate against schemas; return structured errors; retry limit |
| Infinite or wasteful loops | Hard step limit; repeated-identical-call detection |
| Accidental overwriting of notes | Separate `notes/` (read-only) and `output/` (write); confirm writes |
| Memory grows or becomes stale | Cap size; allow view/reset |
| Real-LLM tests are flaky or costly | Behavior-based assertions; opt-in marker; small suite |

## 12. Open Questions

- Which LLM provider and model will be used for the live suite?
- Should memory be plain JSON or SQLite if it grows?
- Should the student be able to set a custom step limit per task?
