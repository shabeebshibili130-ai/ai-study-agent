"""Streamlit Web Application for the AI Study Agent."""

from pathlib import Path
import json
import streamlit as st

from study_agent.agent import run_agent
from study_agent.cli import build_mock_llm
from study_agent.llm import RealLLM
from study_agent.logger import AgentLogger
from study_agent.memory import (
    DEFAULT_MEMORY_FILE,
    format_memory_for_prompt,
    load_memory,
    reset_memory,
)
from study_agent.planner import Plan, generate_plan
from study_agent.tools import TOOLS, read_notes

# Page Configuration
st.set_page_config(
    page_title="AI Study Agent",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
        color: #1E3A8A;
    }
    .sub-header {
        color: #4B5563;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .step-box {
        background-color: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 12px 16px;
        margin-bottom: 10px;
        border-radius: 4px;
    }
    .quiz-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize Session State
if "plan" not in st.session_state:
    st.session_state.plan = None
if "goal" not in st.session_state:
    st.session_state.goal = ""
if "run_result" not in st.session_state:
    st.session_state.run_result = None

# Sidebar
with st.sidebar:
    st.header("⚙️ Agent Controls")
    mode = st.radio("LLM Engine:", ["Mock Mode (Free, Instant)", "Live LLM (Gemini / OpenAI)"])

    api_key = None
    provider = "auto"
    if mode == "Live LLM (Gemini / OpenAI)":
        provider = st.selectbox("Provider:", ["auto", "gemini", "openai"])
        api_key = st.text_input("API Key (optional if in .env):", type="password")

    st.divider()

    st.header("🧠 Student Memory")
    mem, _ = load_memory(DEFAULT_MEMORY_FILE)
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
            st.markdown(f"- **{topic}**: {data.get('score', 0):.0%}")

    if st.button("🗑️ Reset Memory", use_container_width=True):
        reset_memory(DEFAULT_MEMORY_FILE)
        st.toast("Memory reset successfully!")
        st.rerun()

    st.divider()
    st.header("📁 Available Study Notes")
    notes_dir = Path("notes")
    if notes_dir.exists():
        notes_files = [p.name for p in notes_dir.glob("*.md")]
        selected_note = st.selectbox("Inspect Note:", notes_files if notes_files else ["No notes found"])
        if selected_note and selected_note != "No notes found":
            note_content = (notes_dir / selected_note).read_text(encoding="utf-8")
            with st.expander(f"View {selected_note}"):
                st.markdown(note_content)

# Main UI
st.markdown('<div class="main-header">🎓 AI Study Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Autonomous, goal-driven study assistant with planning, tool sandboxing, and persistent memory.</div>', unsafe_allow_html=True)

# Quick Goal Prompts
col_g1, col_g2, col_g3 = st.columns(3)
with col_g1:
    if st.button("🌱 Revise Photosynthesis for Friday", use_container_width=True):
        st.session_state.goal = "Help me revise photosynthesis for Friday"
with col_g2:
    if st.button("⚡ Revise Mitochondria & Respiration", use_container_width=True):
        st.session_state.goal = "Help me revise mitochondria for Friday"
with col_g3:
    if st.button("📝 Quiz Me on Cell Biology", use_container_width=True):
        st.session_state.goal = "Create a 5-question quiz on photosynthesis"

goal_input = st.text_input(
    "What is your study goal?",
    value=st.session_state.goal,
    placeholder="e.g. Help me revise photosynthesis for Friday",
)

col_act1, col_act2 = st.columns([1, 4])
with col_act1:
    generate_clicked = st.button("🎯 Formulate Plan", type="primary", use_container_width=True)

if generate_clicked and goal_input.strip():
    st.session_state.goal = goal_input.strip()
    mem, _ = load_memory(DEFAULT_MEMORY_FILE)
    memory_summary = format_memory_for_prompt(mem)

    # Initialize LLM
    if mode == "Live LLM (Gemini / OpenAI)":
        try:
            llm = RealLLM(api_key=api_key if api_key else None, provider=provider)
        except Exception as e:
            st.error(f"Failed to initialize RealLLM: {str(e)}")
            st.stop()
    else:
        llm = build_mock_llm(st.session_state.goal)

    with st.spinner("Generating step-by-step study plan..."):
        plan = generate_plan(
            goal=st.session_state.goal,
            llm=llm,
            memory_summary=memory_summary,
            tools_registry=TOOLS,
        )
        st.session_state.plan = plan
        st.session_state.run_result = None

# Step 1: Plan Review
if st.session_state.plan:
    st.subheader("📋 Step 1: Review Proposed Plan")
    st.info("The agent plans before acting. You can approve or decline before any tool executes.")

    for s in st.session_state.plan.steps:
        badge = "🔒 Requires Confirmation" if s.needs_approval else "🟢 Safe Read/Compute"
        st.markdown(
            f"**Step {s.step_num}.** `{s.tool}` &nbsp;—&nbsp; *{s.description}* &nbsp;&nbsp; `<small>{badge}</small>`",
            unsafe_allow_html=True,
        )

    col_p1, col_p2, _ = st.columns([1.5, 1.5, 4])
    with col_p1:
        approve_clicked = st.button("🚀 Approve & Execute Plan", type="primary", use_container_width=True)
    with col_p2:
        if st.button("❌ Reject Plan", use_container_width=True):
            st.session_state.plan = None
            st.session_state.run_result = None
            st.warning("Plan was cancelled.")
            st.rerun()

    # Step 2: Execution
    if approve_clicked:
        st.subheader("⚡ Step 2: Agent Execution Loop")
        status_container = st.container()

        # Build LLM
        if mode == "Live LLM (Gemini / OpenAI)":
            try:
                llm = RealLLM(api_key=api_key if api_key else None, provider=provider)
            except Exception as e:
                st.error(f"Error initializing RealLLM: {str(e)}")
                st.stop()
        else:
            llm = build_mock_llm(st.session_state.goal)

        steps_log = []
        step_ui_placeholder = st.empty()

        def on_step_web(step_record):
            steps_log.append(step_record)
            with step_ui_placeholder.container():
                for s in steps_log:
                    step_num = s.get("step")
                    thought = s.get("thought", "")
                    action = s.get("action")
                    obs = s.get("observation", {})
                    if action:
                        tool = action.get("tool")
                        st.markdown(
                            f"""
                            <div class="step-box">
                                <b>[Step {step_num}] Think:</b> {thought}<br>
                                <b>Action:</b> <code>{tool}</code><br>
                                <b>Observation:</b> {str(obs)[:120]}...
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"""
                            <div class="step-box" style="border-left-color: #10B981;">
                                <b>[Step {step_num}] Final Answer:</b> {obs.get('final_answer', '')}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

        logger = AgentLogger()
        with st.spinner("Agent running think → act → look cycle..."):
            result = run_agent(
                goal=st.session_state.goal,
                llm=llm,
                max_steps=15,
                memory_path=DEFAULT_MEMORY_FILE,
                require_plan=False,         # Already approved in UI
                confirm_high_risk=False,    # User approved plan in web UI
                logger=logger,
                on_step=on_step_web,
            )
            st.session_state.run_result = result

# Step 3: Results & Quiz
if st.session_state.run_result:
    res = st.session_state.run_result
    st.divider()
    st.subheader("🎉 Study Session Complete")

    st.success(f"Goal achieved in **{res['step_count']} steps**! Logged to `{logger.log_file.name}`.")

    if res.get("final_answer"):
        st.markdown(f"**Agent Message:**\n\n{res['final_answer']}")

    # Check for generated quiz file in output
    out_dir = Path("output")
    quiz_files = list(out_dir.glob("quiz_*.md")) if out_dir.exists() else []
    if quiz_files:
        st.subheader("📝 Practice Quiz")
        latest_quiz = quiz_files[-1]
        quiz_text = latest_quiz.read_text(encoding="utf-8")

        with st.expander(f"📖 View Practice Quiz: {latest_quiz.name}", expanded=True):
            st.markdown(quiz_text)

        st.download_button(
            label=f"⬇️ Download {latest_quiz.name}",
            data=quiz_text,
            file_name=latest_quiz.name,
            mime="text/markdown",
        )

