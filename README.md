# AI Study Agent 🎓

A minimalist, goal-driven study assistant demonstrating the core foundations of AI agents: **Think → Act → Look**, planning before acting, persistent memory, sandboxing, and safety controls.

Built with pure Python (no heavyweight agent frameworks) across 8 core lessons (L1–L8).

[![Live Web App](https://img.shields.io/badge/Live%20Web%20App-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit)](https://ai-study-agent-xjqgdlcbihtbcg7vxkklk2.streamlit.app/)
[![PyPI version](https://img.shields.io/pypi/v/ai-study-agent.svg?style=for-the-badge&color=blue)](https://pypi.org/project/ai-study-agent/1.0.0/)
[![GitHub Repo](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github)](https://github.com/shabeebshibili130-ai/ai-study-agent)

---

## 🌐 Try It Live
You can test the agent right now in your web browser with zero setup:
👉 **[https://ai-study-agent-xjqgdlcbihtbcg7vxkklk2.streamlit.app/](https://ai-study-agent-xjqgdlcbihtbcg7vxkklk2.streamlit.app/)**

---

## 📦 Install from PyPI
Install globally via pip:
```bash
pip install ai-study-agent
```
And run anywhere:
```bash
study-agent "Help me revise photosynthesis for Friday"
```

---

## 🚀 Quickstart: Running Locally

### 1. Requirements & Setup
Make sure you have Python 3.10+ installed:
```bash
pip install -r requirements.txt
```

### 2. Run in Mock Mode (Free, Instant, No API Key Required)
You can test the agent right away with built-in realistic mock scenarios:
```bash
python cli.py "Help me revise photosynthesis for Friday"
```
Or for mitochondria:
```bash
python cli.py "Help me revise mitochondria for Friday"
```

Interactive prompts will appear:
- **Plan Approval**: `Approve plan? [y/N/edit]` (type `y` to proceed)
- **High-Risk Confirmation**: `Write output/quiz_photosynthesis.md? [y/N]` (type `y` to save)

### 3. Run in Live Mode (Real LLM)
To run with real models (Google Gemini or OpenAI):
1. Create a `.env` file in the root directory:
   ```env
   # Choose either Gemini or OpenAI
   GEMINI_API_KEY="your-gemini-api-key"
   # OR
   OPENAI_API_KEY="your-openai-api-key"
   ```
2. Run with the `--live` flag:
   ```bash
   python cli.py "Help me revise photosynthesis for Friday" --live
   ```

### 4. Memory Management
The agent remembers what you studied and notes weak spots across sessions:
- **View memory**:
  ```bash
  python cli.py --show-memory
  ```
- **Reset memory**:
  ```bash
  python cli.py --reset-memory
  ```

---

## 🧪 Running Tests

Run the full deterministic unit test suite (36 tests, passes in < 0.5s offline):
```bash
pytest
```

Run live LLM integration tests (requires valid API key in environment):
```bash
pytest -m live
```

---

## 📦 How to Publish

### Option 1: Publish to GitHub
1. Initialize git and commit:
   ```bash
   git init
   git add .
   git commit -m "feat: complete AI Study Agent"
   ```
2. Create a new repository on [GitHub](https://github.com/new).
3. Link and push:
   ```bash
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```

### Option 2: Publish as a PyPI Package
1. Install build tools:
   ```bash
   pip install build twine
   ```
2. Build distribution archives:
   ```bash
   python -m build
   ```
3. Upload to PyPI (or TestPyPI):
   ```bash
   twine upload dist/*
   ```

---

## 📂 Project Architecture

```
study_agent/
├── agent.py        # Think → Act → Look loop with retry limits (L1, L3)
├── tools.py        # 4 domain tools: read_notes, make_quiz, save_file, update_progress (L2)
├── planner.py      # Plan formulation, user approval & dynamic revision (L5)
├── memory.py       # Persistent JSON memory store (L4)
├── safety.py       # Sandboxing, write confirmations & secret redaction (L7)
├── logger.py       # Append-only daily JSONL audit logs (L7)
├── llm.py          # BaseLLM, FakeLLM, and RealLLM (L8)
└── cli.py          # Interactive command-line interface
cli.py              # Root convenience runner
notes/              # Student study notes folder (read-only)
output/             # Sandboxed output folder for quizzes and schedules
logs/               # Daily audit logs (logs/YYYY-MM-DD.jsonl)
```

