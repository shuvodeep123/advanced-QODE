"""
app.py — Streamlit chat interface for the advanced-QODE GenAI Diagram Assistant.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration (must be the first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="advanced-QODE — GenAI Diagram Assistant",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Lazy imports — only pulled in after page config
# ---------------------------------------------------------------------------
from rag_pipeline.chain import run_chain, detect_intent
from rag_pipeline.ingest import ingest_all

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CHROMA_PATH = "./chroma_db"
_WELCOME = (
    "👋 Welcome to the **advanced-QODE GenAI Diagram Assistant**!\n\n"
    "I can help you:\n"
    "- 📊 **Generate** a Process Network, People, or Technology diagram from your questionnaire\n"
    "- 🔍 **Analyse** your DevSecOps maturity and suggest improvements\n"
    "- 💡 **Answer** questions about QODE pillars, critical path, and SDLC best practices\n\n"
    "**Get started:** Upload your `QODE-Questionnaire.xlsm` in the sidebar, then ask me anything!"
)

# ---------------------------------------------------------------------------
# Session-state initialisation
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # list[{"role": str, "content": str}]

if "excel_path" not in st.session_state:
    st.session_state.excel_path = None  # path to the uploaded questionnaire

if "ingested" not in st.session_state:
    st.session_state.ingested = False  # whether static docs have been ingested

if "diagram_paths" not in st.session_state:
    st.session_state.diagram_paths = {}  # diagram_type -> png/dot path

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Graphviz-spring.svg/240px-Graphviz-spring.svg.png",
        width=60,
    )
    st.title("🔷 advanced-QODE")
    st.caption("GenAI Diagram Assistant")
    st.divider()

    # ── File uploader ──────────────────────────────────────────────────────
    st.subheader("📂 Upload Questionnaire")
    uploaded_file = st.file_uploader(
        "QODE-Questionnaire.xlsm",
        type=["xlsm", "xlsx"],
        help="Upload your completed QODE questionnaire to enable diagram generation.",
    )

    if uploaded_file is not None:
        # Save to a temp file so pandas can read it
        suffix = Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        if st.session_state.excel_path != tmp_path:
            st.session_state.excel_path = tmp_path
            st.session_state.ingested = False  # force re-ingest

    # ── Ingest trigger ─────────────────────────────────────────────────────
    if not st.session_state.ingested:
        with st.spinner("🔄 Ingesting knowledge base …"):
            try:
                n_docs = ingest_all(
                    excel_path=st.session_state.excel_path,
                    chroma_path=_CHROMA_PATH,
                )
                st.session_state.ingested = True
                st.success(f"✅ Ingested {n_docs} documents into ChromaDB.")
            except Exception as e:
                st.error(f"Ingestion error: {e}")

    st.divider()

    # ── Quick-action pills ─────────────────────────────────────────────────
    st.subheader("⚡ Quick Actions")
    col1, col2, col3 = st.columns(3)

    def _quick_prompt(prompt: str) -> None:
        st.session_state._quick_input = prompt

    with col1:
        if st.button("📊 Process", use_container_width=True):
            _quick_prompt("Generate a Process Network Diagram from my questionnaire.")
    with col2:
        if st.button("👥 People", use_container_width=True):
            _quick_prompt("Generate a People Diagram showing team roles and collaboration.")
    with col3:
        if st.button("🔧 Technology", use_container_width=True):
            _quick_prompt("Generate a Technology Diagram showing the automation toolchain.")

    st.divider()

    # ── Chat history controls ───────────────────────────────────────────────
    st.subheader("🗂 Chat History")
    if st.button("🗑 Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.diagram_paths = {}
        st.rerun()

    st.divider()

    # ── Tips ───────────────────────────────────────────────────────────────
    st.subheader("💡 Example Questions")
    examples = [
        "Create a Target People Architecture Diagram.",
        "How can I optimise my Process Network to reduce time to market?",
        "Which activities on the critical path are fully manual?",
        "Show me the Technology Diagram for my current toolchain.",
        "What DevSecOps improvements can I make for Pillar 5 security?",
    ]
    for ex in examples:
        st.caption(f"• {ex}")

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.title("🔷 advanced-QODE — GenAI Diagram Assistant")
st.caption(
    "Powered by ChromaDB · KodeKloud LLM (Claude Sonnet 4.5) · Graphviz"
)

# ---------------------------------------------------------------------------
# Diagram rendering helper — defined before the history-render loop below.
# ---------------------------------------------------------------------------
def _render_diagram(path: str, dtype: str) -> None:
    """Display a diagram image or DOT source in the chat."""
    p = Path(path)
    if not p.exists():
        st.warning(f"⚠️ Diagram file not found: `{path}`")
        return

    if p.suffix.lower() == ".png":
        st.image(str(p), caption=f"{dtype.title()} Diagram", use_container_width=True)
        with open(str(p), "rb") as f:
            st.download_button(
                label=f"⬇️ Download {dtype.title()} Diagram (PNG)",
                data=f.read(),
                file_name=p.name,
                mime="image/png",
            )
    else:
        # Fallback: show DOT source when Graphviz is not available locally
        dot_text = p.read_text(encoding="utf-8", errors="replace")
        st.code(dot_text, language="dot")
        st.download_button(
            label=f"⬇️ Download {dtype.title()} Diagram (DOT)",
            data=dot_text,
            file_name=p.name,
            mime="text/plain",
        )
        st.info(
            "💡 Graphviz is not installed locally. "
            "Paste the DOT source into [Graphviz Online](https://dreampuf.github.io/GraphvizOnline/) to visualize."
        )


# Display welcome message if no history yet
if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(_WELCOME)

# Render existing conversation
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            # Check if a diagram path is attached
            st.markdown(msg["content"])
            if "diagram_path" in msg and msg["diagram_path"]:
                _render_diagram(msg["diagram_path"], msg.get("diagram_type", ""))
        else:
            st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
# Check for quick-action button click
quick_input: str | None = st.session_state.pop("_quick_input", None)

user_input = st.chat_input(
    "Ask me about your DevSecOps diagrams or QODE assessment …",
    key="chat_input",
)

# Resolve which prompt to process (quick-action takes precedence)
prompt = quick_input or user_input

if prompt:
    # Show user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Build conversation history for the chain (exclude the message just added)
    history = st.session_state.messages[:-1]

    # Detect intent for UI feedback
    intent = detect_intent(prompt)
    diagram_label = {
        "process": "Process Network",
        "people": "People",
        "technology": "Technology",
    }.get(intent, "")

    wants_diagram = any(
        kw in prompt.lower()
        for kw in ["create", "generate", "build", "show", "draw", "make", "produce", "visuali"]
    )

    with st.chat_message("assistant"):
        # Show a status spinner while processing
        status_msg = "Thinking …"
        if wants_diagram and diagram_label:
            status_msg = f"🎨 Generating {diagram_label} Diagram …"

        with st.status(status_msg, expanded=False):
            # Run the RAG chain (streaming)
            try:
                result = run_chain(
                    user_message=prompt,
                    history=history,
                    excel_path=st.session_state.excel_path,
                    chroma_path=_CHROMA_PATH,
                    stream=True,
                )
            except Exception as chain_err:
                result = {
                    "text": f"❌ An error occurred: {chain_err}",
                    "stream": None,
                    "diagram_path": None,
                    "diagram_type": None,
                }

        # Stream the LLM reply
        if result.get("stream"):
            full_reply = st.write_stream(result["stream"])
        else:
            full_reply = result.get("text", "")
            st.markdown(full_reply)

        # Show diagram if one was generated
        diagram_path = result.get("diagram_path")
        diagram_type = result.get("diagram_type") or ""
        if diagram_path:
            _render_diagram(diagram_path, diagram_type)

    # Persist assistant message (with optional diagram path)
    assistant_msg: dict = {
        "role": "assistant",
        "content": full_reply or "",
        "diagram_path": diagram_path,
        "diagram_type": diagram_type,
    }
    st.session_state.messages.append(assistant_msg)

    # Cache the latest diagram path per type
    if diagram_path and diagram_type:
        st.session_state.diagram_paths[diagram_type] = diagram_path
