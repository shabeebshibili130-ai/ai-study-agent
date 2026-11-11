"""Streamlit Web Application for the AI Study Agent."""

from pathlib import Path
import streamlit as st

from study_agent.agent import run_agent
from study_agent.cli import build_mock_llm
from study_agent.llm import RealLLM
from study_agent.logger import AgentLogger
from study_agent.memory import (
    DEFAULT_MEMORY_FILE,
    format_memory_for_prompt,
    get_empty_memory,
    load_memory,
    reset_memory,
    save_memory,
)
from study_agent.planner import Plan, generate_plan
from study_agent.tools import TOOLS

# ── Page Configuration ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Study Agent",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Initialize Session State (always first, before any widgets) ──────────────
if "plan" not in st.session_state:
    st.session_state.plan = None
if "goal" not in st.session_state:
    st.session_state.goal = ""
if "run_result" not in st.session_state:
    st.session_state.run_result = None
if "quiz_content" not in st.session_state:
    st.session_state.quiz_content = None          # Bug 4 fix: store quiz in state
if "quiz_filename" not in st.session_state:
    st.session_state.quiz_filename = None
if "memory" not in st.session_state:              # Bug 5 fix: memory in session state
    st.session_state.memory = None
if "logger_path" not in st.session_state:         # Bug 2 fix: store log path in state
    st.session_state.logger_path = None
if "steps_log" not in st.session_state:
    st.session_state.steps_log = []

# Load or init memory once per session
if st.session_state.memory is None:
    mem, _ = load_memory(DEFAULT_MEMORY_FILE)
    st.session_state.memory = mem


def get_llm(mode: str, provider: str, api_key: str | None):
    """Build the LLM based on sidebar settings."""
    if mode == "Live LLM (Gemini / OpenAI)":
        return RealLLM(api_key=api_key or None, provider=provider)
    return build_mock_llm(st.session_state.goal)


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Agent Controls")

    mode = st.radio(
        "LLM Engine:",
        ["Live LLM (Gemini / OpenAI)", "Mock Mode (Free, Instant)"],
        index=0,  # Default to Live LLM now
    )

    api_key = None
    provider = "auto"
    if mode == "Live LLM (Gemini / OpenAI)":
        provider = st.selectbox("Provider:", ["gemini", "openai", "auto"])
        # Try Streamlit secrets first, then let user enter manually
        secret_key = None
        try:
            if provider in ("gemini", "auto"):
                secret_key = st.secrets.get("GEMINI_API_KEY", None)
            elif provider == "openai":
                secret_key = st.secrets.get("OPENAI_API_KEY", None)
        except Exception:
            pass

        if secret_key:
            api_key = secret_key
            st.success("✅ API key loaded from Streamlit secrets.", icon="🔑")
        else:
            api_key = st.text_input(
                "Paste your API Key here:",
                type="password",
                placeholder="AIza... (Gemini) or sk-... (OpenAI)",
                help="Get a free Gemini key at https://aistudio.google.com/app/apikey",
            )
            if not api_key:
                st.info(
                    "🔑 Enter a Gemini API key above, or switch to **Mock Mode** to try without one.\n\n"
                    "[Get a free Gemini key →](https://aistudio.google.com/app/apikey)"
                )

    st.divider()

    # Bug 5 fix: use session-state memory, not disk
    st.header("🧠 Student Memory")
    mem = st.session_state.memory
    weak_spots = mem.get("weak_spots", [])
    if weak_spots:
        st.markdown("**Known Weak Spots:**")
        for ws in weak_spots:
            st.markdown(f"- 🔴 `{ws}`")
    else:
        st.caption("No weak spots recorded yet.")

    progress = mem.get("progress", {})
    if progress:
        st.markdown("**Topic Progress:**")
        for topic, data in progress.items():
            score = data.get("score", 0)
            bar_color = "🟢" if score >= 0.8 else "🟡" if score >= 0.5 else "🔴"
            st.markdown(f"- {bar_color} **{topic}**: {score:.0%}")

    if st.button("🗑️ Reset Memory", use_container_width=True):
        st.session_state.memory = get_empty_memory()
        reset_memory(DEFAULT_MEMORY_FILE)
        st.toast("Memory reset successfully!")
        st.rerun()

    st.divider()
    st.header("📁 Available Study Notes")
    notes_dir = Path("notes")
    if notes_dir.exists():
        notes_files = [p.name for p in notes_dir.glob("*.md")]
        if notes_files:
            selected_note = st.selectbox("Inspect Note:", notes_files)
            if selected_note:
                note_content = (notes_dir / selected_note).read_text(encoding="utf-8")
                with st.expander(f"📄 View {selected_note}"):
                    st.markdown(note_content)
        else:
            st.caption("No notes files found.")
    else:
        st.caption("⚠️ `notes/` folder not found in working directory.")


# ── Main Header (always visible — Bug 1 fix) ─────────────────────────────────
st.title("🎓 AI Study Agent")
st.markdown(
    "**Autonomous, goal-driven study assistant** with planning, tool sandboxing, and persistent memory."
)
st.divider()

# ── Quick Goal Buttons ────────────────────────────────────────────────────────
col_g1, col_g2, col_g3 = st.columns(3)
with col_g1:
    if st.button("🌱 Revise Photosynthesis", use_container_width=True):
        st.session_state.goal = "Help me revise photosynthesis for Friday"
        st.session_state.plan = None
        st.session_state.run_result = None
        st.rerun()
with col_g2:
    if st.button("⚡ Revise Mitochondria", use_container_width=True):
        st.session_state.goal = "Help me revise mitochondria for Friday"
        st.session_state.plan = None
        st.session_state.run_result = None
        st.rerun()
with col_g3:
    # Bug 6 fix: label and goal now match
    if st.button("📝 Quiz Me on Cell Biology", use_container_width=True):
        st.session_state.goal = "Create a 5-question quiz on cell biology topics including photosynthesis and mitochondria"
        st.session_state.plan = None
        st.session_state.run_result = None
        st.rerun()

goal_input = st.text_input(
    "What is your study goal?",
    value=st.session_state.goal,
    placeholder="e.g. Help me revise photosynthesis for Friday",
)

col_act1, col_act2 = st.columns([1, 4])
with col_act1:
    generate_clicked = st.button("🎯 Formulate Plan", type="primary", use_container_width=True)

# Bug 8 fix: show warning if Formulate Plan clicked with empty goal
if generate_clicked:
    if not goal_input.strip():
        st.warning("⚠️ Please enter a study goal first (e.g. 'Help me revise photosynthesis for Friday').")
    else:
        st.session_state.goal = goal_input.strip()
        st.session_state.run_result = None
        st.session_state.quiz_content = None
        st.session_state.steps_log = []
        mem = st.session_state.memory
        memory_summary = format_memory_for_prompt(mem)

        # Build LLM — with graceful error for missing key
        try:
            llm = get_llm(mode, provider, api_key)
        except Exception as e:
            st.error(f"❌ Could not start LLM: {e}\n\nPlease enter a valid API key or switch to **Mock Mode**.")
            st.stop()

        with st.spinner("🤔 Generating step-by-step study plan..."):
            plan = generate_plan(
                goal=st.session_state.goal,
                llm=llm,
                memory_summary=memory_summary,
                tools_registry=TOOLS,
            )
            st.session_state.plan = plan

# ── Step 1: Plan Review ───────────────────────────────────────────────────────
if st.session_state.plan and not st.session_state.run_result:
    st.subheader("📋 Step 1: Review Proposed Plan")
    st.info("The agent plans before acting. Approve or decline before any tool executes.")

    for s in st.session_state.plan.steps:
        badge = "🔒 Requires Confirmation" if s.needs_approval else "🟢 Safe Read/Compute"
        st.markdown(f"**Step {s.step_num}.** `{s.tool}` — *{s.description}* &nbsp;&nbsp; `{badge}`")

    col_p1, col_p2, _ = st.columns([1.5, 1.5, 4])
    with col_p1:
        approve_clicked = st.button("🚀 Approve & Execute Plan", type="primary", use_container_width=True)
    with col_p2:
        if st.button("❌ Reject Plan", use_container_width=True):
            st.session_state.plan = None
            st.session_state.run_result = None
            st.warning("Plan was cancelled.")
            st.rerun()

    # ── Step 2: Execution ─────────────────────────────────────────────────────
    if approve_clicked:
        st.subheader("⚡ Step 2: Agent Execution Loop")

        try:
            llm = get_llm(mode, provider, api_key)
        except Exception as e:
            st.error(f"❌ Could not start LLM: {e}")
            st.stop()

        steps_log: list = []
        step_placeholder = st.empty()

        def on_step_web(step_record):
            steps_log.append(step_record)
            # Bug 4 fix: capture quiz content in session state as agent runs
            obs = step_record.get("observation", {})
            action = step_record.get("action")
            if action and action.get("tool") == "save_file":
                args = action.get("args", {})
                fname = args.get("filename", "")
                content = args.get("content", "")
                if fname.startswith("quiz_") and content:
                    st.session_state.quiz_content = content
                    st.session_state.quiz_filename = fname

            with step_placeholder.container():
                for s in steps_log:
                    snum = s.get("step")
                    thought = s.get("thought", "")
                    act = s.get("action")
                    ob = s.get("observation", {})
                    if act:
                        tool = act.get("tool", "")
                        obs_preview = str(ob)[:150] + ("..." if len(str(ob)) > 150 else "")
                        with st.container():
                            st.markdown(
                                f"**[Step {snum}]** 💭 *{thought}*  \n"
                                f"**Action:** `{tool}`  \n"
                                f"**Observation:** {obs_preview}"
                            )
                            st.divider()
                    else:
                        final_ans = ob.get("final_answer", "")
                        st.success(f"**[Step {snum}] ✅ Final Answer:** {final_ans}")

        # Bug 2 fix: create logger here and store path in session state
        logger = AgentLogger()
        st.session_state.logger_path = str(logger.log_file)

        with st.spinner("🤖 Agent running think → act → observe cycle..."):
            result = run_agent(
                goal=st.session_state.goal,
                llm=llm,
                max_steps=15,
                memory=st.session_state.memory,  # Bug 5 fix: pass session memory
                memory_path=DEFAULT_MEMORY_FILE,
                require_plan=False,
                confirm_high_risk=False,
                logger=logger,
                on_step=on_step_web,
            )
            st.session_state.run_result = result
            # Update session memory from agent result
            if result.get("memory"):
                st.session_state.memory = result["memory"]
            st.rerun()

# ── Step 3: Results & Quiz ────────────────────────────────────────────────────
if st.session_state.run_result:
    res = st.session_state.run_result
    st.divider()
    st.subheader("🎉 Study Session Complete")

    # Bug 2 fix: use stored logger path string, not the logger object
    log_ref = f"`{st.session_state.logger_path}`" if st.session_state.logger_path else "log file"
    st.success(f"Goal achieved in **{res['step_count']} steps**! Logged to {log_ref}.")

    if res.get("final_answer"):
        st.markdown(f"**Agent Message:**\n\n{res['final_answer']}")

    # Bug 4 fix: show quiz from session state (not ephemeral filesystem)
    if st.session_state.quiz_content:
        st.subheader("📝 Practice Quiz")
        fname = st.session_state.quiz_filename or "quiz.md"
        with st.expander(f"📖 View Quiz: {fname}", expanded=True):
            st.markdown(st.session_state.quiz_content)
        st.download_button(
            label=f"⬇️ Download {fname}",
            data=st.session_state.quiz_content,
            file_name=fname,
            mime="text/markdown",
        )
    else:
        # Fallback: check filesystem in case save_file succeeded
        out_dir = Path("output")
        quiz_files = sorted(out_dir.glob("quiz_*.md")) if out_dir.exists() else []
        if quiz_files:
            st.subheader("📝 Practice Quiz")
            latest = quiz_files[-1]
            quiz_text = latest.read_text(encoding="utf-8")
            with st.expander(f"📖 View Quiz: {latest.name}", expanded=True):
                st.markdown(quiz_text)
            st.download_button(
                label=f"⬇️ Download {latest.name}",
                data=quiz_text,
                file_name=latest.name,
                mime="text/markdown",
            )

    if st.button("🔄 Start New Session", type="primary"):
        st.session_state.plan = None
        st.session_state.run_result = None
        st.session_state.quiz_content = None
        st.session_state.quiz_filename = None
        st.session_state.steps_log = []
        st.session_state.goal = ""
        st.rerun()

# ── Welcome Screen (shown only when no plan and no result — Bug 1 fix) ────────
if not st.session_state.plan and not st.session_state.run_result:
    st.markdown("### 👋 Welcome! How it works:")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.info("**1. Set Goal**\n\nType your study goal above or click a quick-start button.")
    with col2:
        st.info("**2. Review Plan**\n\nThe AI creates a step-by-step plan for you to approve.")
    with col3:
        st.info("**3. Agent Runs**\n\nThe agent reads notes, makes a quiz, and saves your progress.")
    with col4:
        st.info("**4. Get Results**\n\nDownload your quiz and track your performance over time.")

    st.markdown("---")
    st.markdown("#### 📚 Example study goals:")
    st.code("Help me revise photosynthesis for Friday")
    st.code("Create a 5-question quiz on mitochondria")
    st.code("Summarise my biology notes and test me")
