"""
AI Study Agent — Dynamic Conversational Chat Interface
Full live LLM integration (Gemini / OpenAI) with multi-turn memory.
"""

from pathlib import Path
import json
import urllib.error
import urllib.request

import streamlit as st

from study_agent.memory import (
    DEFAULT_MEMORY_FILE,
    format_memory_for_prompt,
    get_empty_memory,
    load_memory,
    record_progress,
    reset_memory,
)

# ── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title="AI Study Agent",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert AI Study Agent — an autonomous, adaptive, goal-driven study assistant.

Your capabilities:
- Break down complex topics into clear, digestible explanations tailored to the student's level.
- Create adaptive quizzes (multiple-choice, short-answer, true/false) and give instant feedback.
- Track what the student has covered so far and what they are struggling with.
- Provide hints, worked examples, and step-by-step explanations when asked.
- Celebrate progress and keep the student motivated.
- Summarise key concepts at the end of a session when requested.

Available Study Notes (use these as your primary source of truth):
{notes_context}

Student Memory & Progress:
{memory_context}

Behaviour rules:
- Be conversational, encouraging, and clear.
- Use markdown formatting (headers, bold key terms, bullet lists, code blocks for equations).
- After answering, ask a follow-up question to check understanding.
- When the student gets a quiz question wrong, explain the correct answer and offer another question.
- Adapt difficulty based on how the student is responding.
- Never invent facts beyond the notes provided; say so if the question is out of scope.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_all_notes() -> str:
    notes_dir = Path("notes")
    if not notes_dir.exists():
        return "No study notes found."
    sections = []
    for f in sorted(notes_dir.glob("*.md")):
        sections.append(f"### {f.stem.capitalize()}\n{f.read_text(encoding='utf-8')}")
    return "\n\n".join(sections) if sections else "No study notes found."


def _build_system_prompt() -> str:
    mem = st.session_state.get("memory", get_empty_memory())
    return _SYSTEM_PROMPT_TEMPLATE.format(
        notes_context=_load_all_notes(),
        memory_context=format_memory_for_prompt(mem),
    )


# ── LLM backends ─────────────────────────────────────────────────────────────
def _gemini_sdk(messages: list[dict], api_key: str, model: str) -> str:
    """Call Gemini via google-generativeai SDK (preferred)."""
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=api_key)
    gmodel = genai.GenerativeModel(
        model_name=model,
        system_instruction=_build_system_prompt(),
    )

    # Convert to Gemini history format (all but last message)
    history = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
        for m in messages[:-1]
    ]
    chat = gmodel.start_chat(history=history)
    response = chat.send_message(messages[-1]["content"])
    return response.text


def _gemini_http(messages: list[dict], api_key: str, model: str) -> str:
    """Call Gemini via raw HTTP (fallback when SDK not installed)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    contents = [
        {
            "role": "user" if m["role"] == "user" else "model",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
    ]
    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": _build_system_prompt()}]},
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    candidates = body.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            return parts[0].get("text", "")
    return "No response from Gemini."


def _call_gemini(messages: list[dict], api_key: str, model: str = "gemini-1.5-flash") -> str:
    try:
        return _gemini_sdk(messages, api_key, model)
    except ImportError:
        return _gemini_http(messages, api_key, model)


def _openai_sdk(messages: list[dict], api_key: str, model: str) -> str:
    """Call OpenAI via openai SDK (preferred)."""
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=api_key)
    full = [{"role": "system", "content": _build_system_prompt()}] + messages
    response = client.chat.completions.create(
        model=model, messages=full, temperature=0.7, max_tokens=2048
    )
    return response.choices[0].message.content


def _openai_http(messages: list[dict], api_key: str, model: str) -> str:
    """Call OpenAI via raw HTTP (fallback when SDK not installed)."""
    url = "https://api.openai.com/v1/chat/completions"
    full = [{"role": "system", "content": _build_system_prompt()}] + messages
    payload = {"model": model, "messages": full, "temperature": 0.7, "max_tokens": 2048}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    choices = body.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return "No response from OpenAI."


def _call_openai(messages: list[dict], api_key: str, model: str = "gpt-4o-mini") -> str:
    try:
        return _openai_sdk(messages, api_key, model)
    except ImportError:
        return _openai_http(messages, api_key, model)


def _mock_response(user_message: str) -> str:
    """Deterministic fallback when no API key is available."""
    msg = user_message.lower()
    if any(w in msg for w in ["photosynthesis", "light reaction", "calvin", "rubisco"]):
        return (
            "Great question! 🌱 Let me break down **Photosynthesis** for you.\n\n"
            "**Core equation:**\n"
            "> 6CO₂ + 6H₂O + light → C₆H₁₂O₆ + 6O₂\n\n"
            "**Two stages:**\n"
            "1. **Light-Dependent Reactions** (thylakoid membranes)\n"
            "   - Splits water (photolysis) → releases O₂\n"
            "   - Produces ATP and NADPH\n"
            "2. **Calvin Cycle** (stroma)\n"
            "   - Uses ATP + NADPH to fix CO₂ → glucose\n"
            "   - Key enzyme: **RuBisCO**\n\n"
            "💡 **Quick check:** What two products of the light-dependent reactions "
            "are used in the Calvin Cycle?"
        )
    if any(w in msg for w in ["mitochondria", "atp", "respiration", "krebs", "glycolysis"]):
        return (
            "⚡ Let's explore **Mitochondria & Cellular Respiration**!\n\n"
            "Mitochondria are the **powerhouse of the cell** — they produce ATP.\n\n"
            "**Three stages:**\n"
            "1. **Glycolysis** → cytoplasm → 2 ATP\n"
            "2. **Krebs Cycle** → mitochondrial matrix → electron carriers\n"
            "3. **Oxidative Phosphorylation (ETC)** → inner membrane → ~34 ATP\n\n"
            "💡 **Quick check:** Where exactly does glycolysis occur — inside or "
            "outside the mitochondrion?"
        )
    if any(w in msg for w in ["quiz", "test me", "question"]):
        return (
            "🎯 Let's test your knowledge!\n\n"
            "**Question 1:** Which enzyme is responsible for fixing CO₂ in the Calvin Cycle?\n"
            "- A) ATP Synthase\n"
            "- B) **RuBisCO** ✅\n"
            "- C) Helicase\n"
            "- D) Amylase\n\n"
            "**Question 2:** Glycolysis produces how many net ATP molecules per glucose?\n"
            "- A) 36\n"
            "- B) 4\n"
            "- C) **2** ✅\n"
            "- D) 0\n\n"
            "Reply with your answers or say **'next question'** for more! 🚀"
        )
    return (
        "👋 Hi! I'm your **AI Study Agent** running in **Mock Mode** (no API key needed).\n\n"
        "I can help you:\n"
        "- 📖 **Explain topics** — ask about photosynthesis, mitochondria, cell biology…\n"
        "- 🎯 **Quiz you** — say *'quiz me on photosynthesis'*\n"
        "- 📊 **Track progress** — I remember what we've covered this session\n\n"
        "To unlock full AI responses, add your **Gemini** or **OpenAI** API key in the sidebar "
        "and switch to **Live LLM** mode.\n\n"
        "What would you like to study today?"
    )


def get_ai_response(user_message: str, mode: str, provider: str, api_key: str | None) -> str:
    """Route the user message to the right backend; auto-fallback to mock on any failure."""
    if mode == "Mock Mode (Free, Instant)":
        return _mock_response(user_message)

    # No key → friendly message + mock fallback
    if not api_key or not api_key.strip():
        st.warning(
            "⚠️ No API key found — using Mock Mode. "
            "Add your Gemini key in the sidebar to get real AI responses.",
            icon="🔑",
        )
        return _mock_response(user_message)

    # Build the full conversation for the API call
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]

    try:
        if provider == "openai":
            reply = _call_openai(messages, api_key.strip())
        else:  # "gemini" or "auto"
            reply = _call_gemini(messages, api_key.strip())

        # Detect error strings returned by the backends and fall back gracefully
        if reply.startswith("❌"):
            raise RuntimeError(reply)
        return reply

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        # API_KEY_INVALID or quota issues → show a helpful banner and use mock
        if e.code in (400, 401, 403):
            st.error(
                f"**API key error ({e.code}):** The key you entered is not valid or has no access to Gemini.\n\n"
                "👉 Get a free valid key → [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)\n\n"
                "Falling back to **Mock Mode** for now.",
                icon="🔑",
            )
        else:
            st.error(f"**API error {e.code}** — falling back to Mock Mode.", icon="⚠️")
        return _mock_response(user_message)

    except Exception as e:
        err = str(e)
        if "API_KEY_INVALID" in err or "api key" in err.lower():
            st.error(
                "**Invalid API key.** The key you entered was rejected by Google.\n\n"
                "👉 [Get a free valid Gemini key](https://aistudio.google.com/app/apikey) · "
                "Falling back to **Mock Mode**.",
                icon="🔑",
            )
        else:
            st.error(f"**Unexpected error** — falling back to Mock Mode.\n\n`{err[:200]}`", icon="⚠️")
        return _mock_response(user_message)


# ── Session-state bootstrap ───────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "memory" not in st.session_state:
    mem, _ = load_memory(DEFAULT_MEMORY_FILE)
    st.session_state.memory = mem
if "pending_prompt" not in st.session_state:
    # Set by quick-start buttons; consumed on the next render cycle
    st.session_state.pending_prompt = None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Agent Controls")

    # Auto-detect secrets so we default to Live if a key is already configured
    _secret_gemini, _secret_openai = None, None
    try:
        _secret_gemini = st.secrets.get("GEMINI_API_KEY") or None
        _secret_openai = st.secrets.get("OPENAI_API_KEY") or None
    except Exception:
        pass
    _has_secret = bool(_secret_gemini or _secret_openai)

    mode = st.radio(
        "LLM Engine:",
        ["Mock Mode (Free, Instant)", "Live LLM (Gemini / OpenAI)"],
        index=0 if not _has_secret else 1,
    )

    api_key: str | None = None
    provider = "gemini"

    if mode == "Live LLM (Gemini / OpenAI)":
        provider = st.selectbox("Provider:", ["gemini", "openai"])
        secret_key = _secret_gemini if provider == "gemini" else _secret_openai

        if secret_key:
            api_key = secret_key
            st.success("🔑 API key loaded from Streamlit secrets.")
        else:
            api_key = st.text_input(
                "Paste your API Key:",
                type="password",
                placeholder="AIza… (Gemini)  or  sk-… (OpenAI)",
                help="Get a free Gemini key → https://aistudio.google.com/app/apikey",
            )
            if not api_key:
                st.info(
                    "Enter an API key above **or switch to Mock Mode** (free, no key needed).\n\n"
                    "👉 [Get a free Gemini key](https://aistudio.google.com/app/apikey)"
                )
    else:
        st.success("✅ Mock Mode — no API key required.")

    st.divider()

    # ── Student Memory ────────────────────────────────────────────────────────
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
            icon = "🟢" if score >= 0.8 else "🟡" if score >= 0.5 else "🔴"
            st.markdown(f"- {icon} **{topic}**: {score:.0%}")

    if st.button("🗑️ Reset Memory", use_container_width=True):
        st.session_state.memory = get_empty_memory()
        reset_memory(DEFAULT_MEMORY_FILE)
        st.toast("Memory reset!")
        st.rerun()

    st.divider()

    # ── Chat controls ─────────────────────────────────────────────────────────
    st.header("💬 Chat Controls")
    if st.button("🔄 Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pending_prompt = None
        st.rerun()

    st.divider()

    # ── Available Notes ───────────────────────────────────────────────────────
    st.header("📁 Study Notes")
    notes_dir = Path("notes")
    if notes_dir.exists():
        note_files = [p.name for p in notes_dir.glob("*.md")]
        if note_files:
            sel = st.selectbox("Inspect note:", note_files)
            if sel:
                with st.expander(f"📄 {sel}"):
                    st.markdown((notes_dir / sel).read_text(encoding="utf-8"))
        else:
            st.caption("No notes files found.")
    else:
        st.caption("⚠️ `notes/` folder not present.")


# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🎓 AI Study Agent")
st.caption("Autonomous, goal-driven study assistant · Powered by Gemini or OpenAI")

# ── Quick-start buttons ───────────────────────────────────────────────────────
qc1, qc2, qc3, qc4 = st.columns(4)
_quick_prompts = {
    "🌱 Revise Photosynthesis":    "Help me revise photosynthesis. Start with the key concepts and then quiz me.",
    "⚡ Revise Mitochondria":      "Help me revise mitochondria and cellular respiration. Give me a summary then quiz me.",
    "📝 Quiz on Cell Biology":     "Quiz me on cell biology topics including photosynthesis and mitochondria.",
    "📊 Show My Progress":         "Show me what I've studied so far and what my weak spots are.",
}
_btns = list(_quick_prompts.items())
for col, (label, prompt) in zip([qc1, qc2, qc3, qc4], _btns):
    with col:
        if st.button(label, use_container_width=True):
            st.session_state.pending_prompt = prompt
            st.rerun()

st.divider()

# ── Welcome message on first load ─────────────────────────────────────────────
if not st.session_state.messages:
    with st.chat_message("assistant", avatar="🎓"):
        st.markdown(
            "👋 **Welcome! I'm your AI Study Agent.**\n\n"
            "I can help you:\n"
            "- 📖 **Explain** any topic from your study notes\n"
            "- 🎯 **Quiz you** adaptively and give instant feedback\n"
            "- 📊 **Track** your progress across sessions\n"
            "- 💡 **Break down** complex ideas step by step\n\n"
            "Click a **quick-start button** above, or just type your study goal below! ✍️"
        )

# ── Render existing conversation ──────────────────────────────────────────────
for msg in st.session_state.messages:
    avatar = "🧑‍🎓" if msg["role"] == "user" else "🎓"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ── Handle pending quick-start prompt ────────────────────────────────────────
if st.session_state.pending_prompt:
    user_text = st.session_state.pending_prompt
    st.session_state.pending_prompt = None
    # Append and immediately get response
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(user_text)

    with st.chat_message("assistant", avatar="🎓"):
        with st.spinner("Thinking…"):
            reply = get_ai_response(user_text, mode, provider, api_key)
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.rerun()

# ── Chat input (always rendered at bottom) ────────────────────────────────────
if user_input := st.chat_input("Ask me anything about your studies…"):
    # Show user bubble immediately
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(user_input)

    # Get and stream assistant reply
    with st.chat_message("assistant", avatar="🎓"):
        with st.spinner("Thinking…"):
            reply = get_ai_response(user_input, mode, provider, api_key)
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})

    # Auto-update memory: naive topic detection from conversation
    low = user_input.lower()
    if any(w in low for w in ["photosynthesis", "light reaction", "calvin", "chlorophyll"]):
        record_progress(st.session_state.memory, "photosynthesis", score=0.75,
                        note="Discussed in chat session.")
    elif any(w in low for w in ["mitochondria", "atp", "respiration", "krebs", "glycolysis"]):
        record_progress(st.session_state.memory, "mitochondria", score=0.75,
                        note="Discussed in chat session.")
    # Save to disk too
    try:
        from study_agent.memory import save_memory
        save_memory(st.session_state.memory, DEFAULT_MEMORY_FILE)
    except Exception:
        pass
