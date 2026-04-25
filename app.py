"""
app.py — Streamlit chat interface for the advanced-QODE GenAI Diagram Assistant.

Architecture
------------
  📊 As-Is path       : RAG only, zero LLM — generates diagrams from the 3 core Python files.
  🧠 Principles path  : LLM + Graph-RAG across 9 Engineering Principles × 3 Disciplines.

UI layer
--------
  ui/theme.py      — Figma design tokens (colours, typography, spacing)
  ui/styles.css    — Full custom CSS matching Figma frame "advanced-QODE · GenAI Assistant"
  ui/components.py — Reusable HTML/CSS Streamlit components (bubbles, badges, cards)

Run
---
    streamlit run app.py
    # or
    bash run.sh
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration — MUST be the very first Streamlit call
# ---------------------------------------------------------------------------
from ui.theme import PAGE_CONFIG

st.set_page_config(**PAGE_CONFIG)

# ---------------------------------------------------------------------------
# CSS injection — second call, before any visible content
# ---------------------------------------------------------------------------
from ui.components import (
    inject_css,
    render_header,
    render_welcome,
    render_user_bubble,
    render_assistant_bubble,
    render_mode_badge,
    render_eval_bar,
    render_diagram_card,
    render_sidebar_section,
    render_info_card,
)

inject_css()

# ---------------------------------------------------------------------------
# Lazy domain imports (after page config)
# ---------------------------------------------------------------------------
from rag_pipeline.chain import run_chain, detect_intent, detect_asis_request
from rag_pipeline.ingest import ingest_all
from rag_pipeline.graph_builder import DEFAULT_GRAPH_PATH
from rag_pipeline.graph_retriever import invalidate_cache

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CHROMA_PATH = "./chroma_db"
_GRAPH_PATH  = DEFAULT_GRAPH_PATH
_SUPPORTED   = ["xlsm", "xlsx", "docx", "pdf", "txt"]

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
_DEFAULTS: dict[str, Any] = {
    "messages":           [],    # list[dict] — chat history
    "uploaded_files":     {},    # filename → tmp path
    "ingested":           False,
    "diagram_paths":      {},    # dtype → latest diagram path
    "selected_principle": None,
    "selected_discipline": "Technology",
    "msg_count":          0,     # for sidebar stat
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# ── SIDEBAR ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
with st.sidebar:

    # Brand mark
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0 4px;">
          <span style="font-size:1.6rem;">🔷</span>
          <div>
            <div style="font-size:1rem;font-weight:700;color:#f0f6fc;">advanced-QODE</div>
            <div style="font-size:0.7rem;color:#8b949e;letter-spacing:0.05em;">
              GenAI Diagram Assistant
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Session stats ──────────────────────────────────────────────────────
    render_sidebar_section("Session")
    col_a, col_b = st.columns(2)
    with col_a:
        render_info_card(
            "Messages",
            str(len(st.session_state.messages)),
            "#3b82f6",
        )
    with col_b:
        render_info_card(
            "Diagrams",
            str(len(st.session_state.diagram_paths)),
            "#10b981",
        )

    st.divider()

    # ── File uploader ──────────────────────────────────────────────────────
    render_sidebar_section("📂 Upload Documents")
    uploaded_files = st.file_uploader(
        "xlsm · xlsx · docx · pdf · txt",
        type=_SUPPORTED,
        accept_multiple_files=True,
        help="Upload your QODE questionnaire (.xlsm/.xlsx) and any supporting docs.",
        label_visibility="collapsed",
    )

    if uploaded_files:
        for uf in uploaded_files:
            suffix = Path(uf.name).suffix
            if uf.name not in st.session_state.uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uf.getbuffer())
                    st.session_state.uploaded_files[uf.name] = tmp.name
                st.session_state.ingested = False  # force re-ingest on new file

        st.success(f"✅ {len(st.session_state.uploaded_files)} file(s) ready")

    # ── Resolve paths ──────────────────────────────────────────────────────
    excel_path: str | None = None
    extra_docs: list[str] = []
    for fname, fpath in st.session_state.uploaded_files.items():
        if fname.endswith((".xlsm", ".xlsx")):
            excel_path = fpath
        else:
            extra_docs.append(fpath)

    # ── Ingest ────────────────────────────────────────────────────────────
    if not st.session_state.ingested:
        with st.spinner("🔄 Building knowledge base …"):
            try:
                n_docs = ingest_all(
                    excel_path=excel_path,
                    chroma_path=_CHROMA_PATH,
                    extra_file_paths=extra_docs,
                )
                st.session_state.ingested = True
                invalidate_cache(graph_path=_GRAPH_PATH, chroma_path=_CHROMA_PATH)
                render_info_card("Docs indexed", str(n_docs), "#10b981")
            except Exception as exc:
                st.error(f"Ingestion error: {exc}")

    st.divider()

    # ── Engineering Principles selector ───────────────────────────────────
    render_sidebar_section("⚙️ Engineering Principles")
    selected_principle = st.selectbox(
        "Principle",
        options=["— none —"] + _PRINCIPLES,
        index=0,
        help="Prefix your question with this principle for targeted LLM reasoning.",
        label_visibility="collapsed",
    )
    selected_discipline = st.radio(
        "Discipline",
        options=_DISCIPLINES,
        horizontal=True,
        index=_DISCIPLINES.index(st.session_state.selected_discipline),
    )
    st.session_state.selected_principle = (
        None if selected_principle == "— none —" else selected_principle
    )
    st.session_state.selected_discipline = selected_discipline

    if selected_principle != "— none —":
        st.markdown(
            f'<div style="font-size:0.75rem;color:#8b5cf6;padding:4px 0;">'
            f'🔗 Lens: <strong>{selected_principle}</strong> × <strong>{selected_discipline}</strong>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Quick-action buttons ───────────────────────────────────────────────
    render_sidebar_section("⚡ As-Is Diagrams")

    def _qprompt(p: str) -> None:
        st.session_state._quick_input = p

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📊\nProcess", use_container_width=True):
            _qprompt("Create an As-Is Process Network Architecture diagram.")
    with c2:
        if st.button("👥\nPeople", use_container_width=True):
            _qprompt("Create an As-Is People Architecture diagram.")
    with c3:
        if st.button("🔧\nTech", use_container_width=True):
            _qprompt("Create an As-Is Technology Architecture diagram.")

    st.divider()

    # ── Chat controls ──────────────────────────────────────────────────────
    render_sidebar_section("🗂 Conversation")
    if st.button("🗑 Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.diagram_paths = {}
        st.rerun()

    st.divider()

    # ── Example prompts ────────────────────────────────────────────────────
    render_sidebar_section("💡 Example Prompts")
    examples = [
        "Create an As-Is People Architecture.",
        "Create an As-Is Technology Architecture.",
        "How can I improve Security for my Technology?",
        "Suggest Reliability improvements for Process.",
        "Which critical-path activities are fully manual?",
        "What Requirement Engineering gaps exist in People?",
    ]
    for ex in examples:
        st.markdown(
            f'<div style="font-size:0.78rem;color:#8b949e;padding:2px 0;">'
            f'<span style="color:#484f58;">›</span> {ex}</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# ── MAIN AREA ────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
render_header()

# Welcome card (first run only)
if not st.session_state.messages:
    render_welcome()

# ---------------------------------------------------------------------------
# Render existing conversation history
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            render_user_bubble(msg["content"])
    else:
        with st.chat_message("assistant"):
            render_assistant_bubble(msg["content"], msg.get("mode", "principles"))
            render_mode_badge(msg.get("mode", "principles"))
            render_eval_bar(msg.get("eval_score"))
            if msg.get("diagram_path"):
                render_diagram_card(msg["diagram_path"], msg.get("diagram_type", ""))

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
    # Enrich prompt with active principle/discipline lens
    enriched = prompt
    if st.session_state.selected_principle:
        enriched = (
            f"[{st.session_state.selected_principle}] "
            f"[Discipline: {st.session_state.selected_discipline}] "
            f"{prompt}"
        )

    # Render user bubble immediately
    with st.chat_message("user"):
        render_user_bubble(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    history = st.session_state.messages[:-1]
    is_asis = detect_asis_request(enriched)
    intent  = detect_intent(enriched)

    status_msg = (
        f"📊 Generating As-Is {intent.title()} diagram …"
        if is_asis and intent != "general"
        else "🧠 Reasoning with Graph-RAG + LLM …"
    )

    with st.chat_message("assistant"):
        with st.status(status_msg, expanded=False):
            try:
                result = run_chain(
                    user_message=enriched,
                    history=history,
                    excel_path=excel_path,
                    chroma_path=_CHROMA_PATH,
                    graph_path=_GRAPH_PATH,
                    stream=not is_asis,
                )
            except Exception as exc:
                result = {
                    "text":         f"❌ An error occurred: {exc}",
                    "stream":       None,
                    "diagram_path": None,
                    "diagram_type": None,
                    "mode":         "error",
                    "eval_score":   None,
                }

        # Resolve reply text
        if result.get("stream"):
            full_reply = st.write_stream(result["stream"])
        else:
            full_reply = result.get("text", "")
            render_assistant_bubble(full_reply, result.get("mode", "principles"))

        mode         = result.get("mode", "principles")
        diagram_path = result.get("diagram_path")
        diagram_type = result.get("diagram_type") or ""
        eval_score   = result.get("eval_score")

        render_mode_badge(mode)
        render_eval_bar(eval_score)

        if diagram_path:
            render_diagram_card(diagram_path, diagram_type)

    # Persist to session state
    st.session_state.messages.append({
        "role":         "assistant",
        "content":      full_reply or "",
        "diagram_path": diagram_path,
        "diagram_type": diagram_type,
        "mode":         mode,
        "eval_score":   eval_score,
    })

    if diagram_path and diagram_type:
        st.session_state.diagram_paths[diagram_type] = diagram_path
