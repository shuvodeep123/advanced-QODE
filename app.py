"""
app.py — Streamlit chat interface for the advanced-QODE GenAI Diagram Assistant.

Architecture:
  - As-Is path  : RAG only, no LLM — generates diagrams directly from core Python files.
  - Principles path : LLM + Graph-RAG using 9 Engineering Principles × 3 Disciplines.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

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
from rag_pipeline.chain import run_chain, detect_intent, detect_asis_request
from rag_pipeline.ingest import ingest_all
from rag_pipeline.graph_builder import DEFAULT_GRAPH_PATH
from rag_pipeline.graph_retriever import invalidate_cache

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CHROMA_PATH = "./chroma_db"
_GRAPH_PATH = DEFAULT_GRAPH_PATH

_SUPPORTED_TYPES = ["xlsm", "xlsx", "docx", "pdf", "txt"]

_WELCOME = (
    "👋 Welcome to the **advanced-QODE GenAI Diagram Assistant**!\n\n"
    "I operate in two modes:\n\n"
    "**📊 As-Is Architecture Mode** *(no LLM — fast & deterministic)*\n"
    "- Generates People / Process / Technology diagrams directly from your questionnaire.\n"
    "- Ask: *\"Create an As-Is People Architecture\"* or *\"Generate the As-Is Process diagram\"*\n\n"
    "**🧠 Engineering Principles Mode** *(LLM + Graph-RAG)*\n"
    "- Reasons across 9 Engineering Principles × 3 Disciplines (People, Process, Technology).\n"
    "- Ask: *\"How can I improve Security for my Technology stack?\"* or "
    "*\"Suggest Reliability improvements for our Process\"*\n\n"
    "**Get started:** Upload your questionnaire in the sidebar, then ask away!"
)

_PRINCIPLES = [
    "1. Requirement Engineering",
    "2. Code / Data Engineering",
    "3. Quality Engineering",
    "4. Build & Release Engineering",
    "5. Environment Engineering",
    "6. Service Ops",
    "7. Security",
    "8. Reliability",
    "9. Ontology Engineering",
]

_DISCIPLINES = ["People", "Process", "Technology"]

# ---------------------------------------------------------------------------
# Session-state initialisation
# ---------------------------------------------------------------------------
defaults: dict[str, Any] = {
    "messages": [],
    "uploaded_files": {},      # filename -> tmp path
    "ingested": False,
    "diagram_paths": {},
    "selected_principle": None,
    "selected_discipline": None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🔷 advanced-QODE")
    st.caption("GenAI Diagram Assistant · Graph-RAG Edition")
    st.divider()

    # ── File uploader (multi-format) ───────────────────────────────────────
    st.subheader("📂 Upload Documents")
    uploaded_files = st.file_uploader(
        "Supported: .xlsm · .xlsx · .docx · .pdf · .txt",
        type=_SUPPORTED_TYPES,
        accept_multiple_files=True,
        help="Upload your QODE questionnaire and any supporting documents.",
    )

    if uploaded_files:
        for uf in uploaded_files:
            suffix = Path(uf.name).suffix
            if uf.name not in st.session_state.uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uf.getbuffer())
                    st.session_state.uploaded_files[uf.name] = tmp.name
                st.session_state.ingested = False  # force re-ingest on new file

        if st.session_state.uploaded_files:
            st.success(f"✅ {len(st.session_state.uploaded_files)} file(s) loaded.")

    # ── Ingest trigger ─────────────────────────────────────────────────────
    excel_path: str | None = None
    extra_docs: list[str] = []
    for fname, fpath in st.session_state.uploaded_files.items():
        if fname.endswith((".xlsm", ".xlsx")):
            excel_path = fpath
        else:
            extra_docs.append(fpath)

    if not st.session_state.ingested:
        with st.spinner("🔄 Ingesting knowledge base …"):
            try:
                n_docs = ingest_all(
                    excel_path=excel_path,
                    chroma_path=_CHROMA_PATH,
                    extra_file_paths=extra_docs,
                )
                st.session_state.ingested = True
                invalidate_cache(graph_path=_GRAPH_PATH, chroma_path=_CHROMA_PATH)
                st.success(f"✅ Ingested {n_docs} documents.")
            except Exception as e:
                st.error(f"Ingestion error: {e}")

    st.divider()

    # ── Engineering Principles selector ───────────────────────────────────
    st.subheader("⚙️ Engineering Principles")
    selected_principle = st.selectbox(
        "Apply principle (optional)",
        options=["— none —"] + _PRINCIPLES,
        index=0,
        help="Prefix your question with a specific principle for targeted LLM reasoning.",
    )
    selected_discipline = st.radio(
        "Discipline",
        options=_DISCIPLINES,
        horizontal=True,
    )
    st.session_state.selected_principle = (
        None if selected_principle == "— none —" else selected_principle
    )
    st.session_state.selected_discipline = selected_discipline

    st.divider()

    # ── Quick-action pills ─────────────────────────────────────────────────
    st.subheader("⚡ Quick Actions — As-Is Diagrams")
    col1, col2, col3 = st.columns(3)

    def _quick_prompt(prompt: str) -> None:
        st.session_state._quick_input = prompt

    with col1:
        if st.button("📊 Process", use_container_width=True):
            _quick_prompt("Create an As-Is Process Network Architecture diagram.")
    with col2:
        if st.button("👥 People", use_container_width=True):
            _quick_prompt("Create an As-Is People Architecture diagram.")
    with col3:
        if st.button("🔧 Technology", use_container_width=True):
            _quick_prompt("Create an As-Is Technology Architecture diagram.")

    st.divider()

    # ── Chat controls ──────────────────────────────────────────────────────
    st.subheader("🗂 Chat")
    if st.button("🗑 Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.diagram_paths = {}
        st.rerun()

    st.divider()
    st.subheader("💡 Example Questions")
    examples = [
        "Create an As-Is People Architecture.",
        "Create an As-Is Technology Architecture.",
        "How can I improve Security for my Process?",
        "Suggest Reliability improvements for Technology.",
        "Which activities on the critical path are fully manual?",
        "What Requirement Engineering gaps exist in my People setup?",
    ]
    for ex in examples:
        st.caption(f"• {ex}")

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.title("🔷 advanced-QODE — GenAI Diagram Assistant")

mode_badge = "📊 As-Is Mode  |  🧠 Principles Mode"
st.caption(f"Powered by Graph-RAG · LangGraph · Langfuse · {mode_badge}")

# ---------------------------------------------------------------------------
# Diagram rendering helper
# ---------------------------------------------------------------------------
def _render_diagram(path: str, dtype: str) -> None:
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
        dot_text = p.read_text(encoding="utf-8", errors="replace")
        st.code(dot_text, language="dot")
        st.download_button(
            label=f"⬇️ Download {dtype.title()} Diagram (DOT)",
            data=dot_text,
            file_name=p.name,
            mime="text/plain",
        )
        st.info(
            "💡 Graphviz not installed locally. "
            "Paste the DOT source into [Graphviz Online](https://dreampuf.github.io/GraphvizOnline/) "
            "or [Lucidchart](https://www.lucidchart.com) to visualise."
        )


# Display welcome if no history
if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(_WELCOME)

# Render existing conversation
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if msg.get("diagram_path"):
                _render_diagram(msg["diagram_path"], msg.get("diagram_type", ""))
            if msg.get("mode"):
                badge = "📊 As-Is (no LLM)" if msg["mode"] == "asis" else "🧠 Principles (LLM+RAG)"
                st.caption(f"Mode: {badge}")
            if msg.get("eval_score") is not None:
                st.caption(f"Eval score: {msg['eval_score']:.2f}")

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
quick_input: str | None = st.session_state.pop("_quick_input", None)
user_input = st.chat_input(
    "Ask about As-Is Architecture or Engineering Principle improvements …",
    key="chat_input",
)
prompt = quick_input or user_input

if prompt:
    # Enrich prompt with selected principle/discipline if set
    enriched_prompt = prompt
    if st.session_state.selected_principle:
        enriched_prompt = (
            f"[{st.session_state.selected_principle}] "
            f"[Discipline: {st.session_state.selected_discipline}] "
            f"{prompt}"
        )

    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    history = st.session_state.messages[:-1]

    with st.chat_message("assistant"):
        is_asis = detect_asis_request(enriched_prompt)
        intent = detect_intent(enriched_prompt)

        status_msg = (
            f"📊 Generating As-Is {intent.title()} diagram (no LLM) …"
            if is_asis and intent != "general"
            else "🧠 Reasoning with Graph-RAG + LLM …"
        )

        with st.status(status_msg, expanded=False):
            try:
                result = run_chain(
                    user_message=enriched_prompt,
                    history=history,
                    excel_path=excel_path,
                    chroma_path=_CHROMA_PATH,
                    graph_path=_GRAPH_PATH,
                    stream=not is_asis,  # As-Is is fast/sync; principles path streams
                )
            except Exception as chain_err:
                result = {
                    "text": f"❌ An error occurred: {chain_err}",
                    "stream": None,
                    "diagram_path": None,
                    "diagram_type": None,
                    "mode": "error",
                    "eval_score": None,
                }

        if result.get("stream"):
            full_reply = st.write_stream(result["stream"])
        else:
            full_reply = result.get("text", "")
            st.markdown(full_reply)

        diagram_path = result.get("diagram_path")
        diagram_type = result.get("diagram_type") or ""
        mode = result.get("mode", "principles")
        eval_score = result.get("eval_score")

        if diagram_path:
            _render_diagram(diagram_path, diagram_type)

        badge = "📊 As-Is (no LLM)" if mode == "asis" else "🧠 Principles (LLM+RAG)"
        st.caption(f"Mode: {badge}")
        if eval_score is not None:
            st.caption(f"Eval score: {eval_score:.2f}")

    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": full_reply or "",
        "diagram_path": diagram_path,
        "diagram_type": diagram_type,
        "mode": mode,
        "eval_score": eval_score,
    }
    st.session_state.messages.append(assistant_msg)

    if diagram_path and diagram_type:
        st.session_state.diagram_paths[diagram_type] = diagram_path
