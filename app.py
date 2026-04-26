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

import os
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
    render_token_counter,
)

inject_css()

# ---------------------------------------------------------------------------
# Lazy domain imports (after page config)
# ---------------------------------------------------------------------------
from rag_pipeline.chain import run_chain, detect_intent, detect_asis_request
from rag_pipeline.ingest import ingest_all
from rag_pipeline.graph_builder import DEFAULT_GRAPH_PATH
from rag_pipeline.graph_retriever import invalidate_cache
from rag_pipeline.token_counter import get_usage, reset as reset_token_counter, DEFAULT_BUDGET

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CHROMA_PATH = "./chroma_db"
_GRAPH_PATH  = DEFAULT_GRAPH_PATH
_SUPPORTED   = ["xlsm", "xlsx", "docx", "pdf", "txt"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
import re as _re

def _strip_mermaid_fences(text: str) -> str:
    """Remove ```mermaid ... ``` code fences from the reply text.

    The diagram itself is rendered separately via render_diagram_card, so the
    raw source should not appear in the chat bubble.
    """
    # Remove fenced ```mermaid blocks (possibly with trailing whitespace)
    cleaned = _re.sub(
        r"```mermaid\s*\n.*?```",
        "",
        text,
        flags=_re.DOTALL | _re.IGNORECASE,
    )
    # Collapse multiple blank lines left by the removal
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

# ---------------------------------------------------------------------------
# Session-state initialisation
# ---------------------------------------------------------------------------
_DEFAULTS: dict[str, Any] = {
    "messages":       [],    # list[dict] — chat history
    "uploaded_files": {},    # filename → tmp path
    "excel_path":     None,  # persisted questionnaire path across reruns
    "ingested":       False,
    "diagram_paths":  {},    # dtype → latest diagram path
    # Token budget — read from env so it can be overridden per deployment
    "token_budget":   int(os.environ.get("TOKEN_BUDGET", "248000")),
    # Token usage snapshot — refreshed from token_counter after each LLM call
    "token_prompt":       0,
    "token_completion":   0,
    "token_total":        0,
    "token_call_count":   0,
    "token_by_model":     {},
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _sync_token_state() -> None:
    """Copy the in-process token counter into Streamlit session state.

    Calling this after every chain execution ensures the sidebar Token Count
    section reflects the latest usage without requiring a full page rerun.
    """
    usage = get_usage()
    st.session_state.token_prompt       = usage.prompt_tokens
    st.session_state.token_completion   = usage.completion_tokens
    st.session_state.token_total        = usage.total_tokens
    st.session_state.token_call_count   = usage.call_count
    st.session_state.token_by_model     = usage.by_model

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

    # ── Token Count ───────────────────────────────────────────────────────
    render_sidebar_section("🔢 Token Count")
    render_token_counter(
        prompt_tokens=st.session_state.token_prompt,
        completion_tokens=st.session_state.token_completion,
        total_tokens=st.session_state.token_total,
        budget=st.session_state.token_budget,
        call_count=st.session_state.token_call_count,
        by_model=st.session_state.token_by_model,
    )
    if st.button("↺ Reset Token Counter", use_container_width=True, key="reset_tokens"):
        reset_token_counter()
        _sync_token_state()
        st.rerun()

    st.divider()

    # ── File uploader ─────────────────────────────────────────────────────
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

    # ── Resolve paths ──────────────────────────────────────────────
    excel_path: str | None = None
    extra_docs: list[str] = []
    for fname, fpath in st.session_state.uploaded_files.items():
        if fname.endswith((".xlsm", ".xlsx")):
            excel_path = fpath
        else:
            extra_docs.append(fpath)

    # Persist resolved excel_path so it survives across reruns and page refreshes
    # without the user needing to re-upload the file.
    if excel_path:
        st.session_state.excel_path = excel_path
    elif st.session_state.get("excel_path"):
        # Re-use previously uploaded file if the upload widget was cleared
        prev = st.session_state.excel_path
        if Path(prev).exists():
            excel_path = prev
            st.info(
                f"📁 Using previously uploaded questionnaire: "
                f"`{Path(prev).name}`",
                icon="📂",
            )

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

    # ── As-Is quick-action buttons ─────────────────────────────────────────
    render_sidebar_section("⚡ As-Is Diagrams")

    def _qprompt(p: str) -> None:
        st.session_state._quick_input = p

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📊\nProcess", use_container_width=True, key="asis_process"):
            _qprompt("Create an As-Is Process Network Architecture diagram.")
    with c2:
        if st.button("👥\nPeople", use_container_width=True, key="asis_people"):
            _qprompt("Create an As-Is People Architecture diagram.")
    with c3:
        if st.button("🔧\nTech", use_container_width=True, key="asis_tech"):
            _qprompt("Create an As-Is Technology Architecture diagram.")

    # ── To-Be quick-action buttons ─────────────────────────────────────────
    render_sidebar_section("🔮 To-Be Diagrams")

    t1, t2, t3 = st.columns(3)
    with t1:
        if st.button("📊\nProcess", use_container_width=True, key="tobe_process"):
            _qprompt("Create a To-Be Process Network Architecture diagram with improvements.")
    with t2:
        if st.button("👥\nPeople", use_container_width=True, key="tobe_people"):
            _qprompt("Create a To-Be People Architecture diagram with recommended role changes.")
    with t3:
        if st.button("🔧\nTech", use_container_width=True, key="tobe_tech"):
            _qprompt("Create a To-Be Technology Architecture diagram with recommended toolchain improvements.")

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
        "Create a To-Be Process Architecture.",
        "Create a To-Be Technology Architecture.",
        "How can I improve Security for my Technology?",
        "Which critical-path activities are fully manual?",
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
for _msg_idx, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        with st.chat_message("user"):
            render_user_bubble(msg["content"])
    else:
        with st.chat_message("assistant"):
            render_assistant_bubble(msg["content"], msg.get("mode", "principles"))
            render_mode_badge(msg.get("mode", "principles"))
            render_eval_bar(msg.get("eval_score"))
            if msg.get("diagram_path"):
                render_diagram_card(msg["diagram_path"], msg.get("diagram_type", ""), key=f"hist_{_msg_idx}")

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
quick_input: str | None = st.session_state.pop("_quick_input", None)
user_input = st.chat_input(
    "Ask about As-Is / To-Be Architecture or DevSecOps improvements …",
    key="chat_input",
)
prompt = quick_input or user_input

if prompt:
    # Render user bubble immediately
    with st.chat_message("user"):
        render_user_bubble(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    history = st.session_state.messages[:-1]
    is_asis = detect_asis_request(prompt)
    intent  = detect_intent(prompt)

    # Detect To-Be mode (LLM path even if "generate" keyword present)
    is_tobe = any(kw in prompt.lower() for kw in ["to-be", "to be", "tobe", "target state", "future state"])
    if is_tobe:
        is_asis = False   # To-Be always uses LLM path

    status_msg = (
        f"📊 Generating As-Is {intent.title()} diagram (Mermaid/PlantUML) …"
        if is_asis and intent != "general"
        else f"🔮 Generating To-Be {intent.title()} diagram via LLM + Graph-RAG …"
        if is_tobe and intent != "general"
        else "🧠 Reasoning with Graph-RAG + LLM …"
    )

    with st.chat_message("assistant"):
        with st.status(status_msg, expanded=False):
            try:
                # Stream only for general (non-diagram) LLM questions.
                # For diagram requests the full reply must be available so the
                # Mermaid block can be extracted, saved, and stripped from the
                # chat text before display — streaming would expose raw fences.
                wants_diagram = (intent != "general")
                use_stream = (not is_asis) and (not wants_diagram)
                result = run_chain(
                    user_message=prompt,
                    history=history,
                    excel_path=excel_path,
                    chroma_path=_CHROMA_PATH,
                    graph_path=_GRAPH_PATH,
                    stream=use_stream,
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

        # Sync token usage into session state immediately after chain execution
        _sync_token_state()

        # Resolve reply text
        if result.get("stream"):
            full_reply = st.write_stream(result["stream"])
        else:
            full_reply = result.get("text", "")
            # Strip any raw Mermaid fence blocks before showing in the chat
            # (the diagram is rendered separately via render_diagram_card)
            display_text = _strip_mermaid_fences(full_reply)
            render_assistant_bubble(display_text, result.get("mode", "principles"))

        mode         = result.get("mode", "principles")
        diagram_path = result.get("diagram_path")
        diagram_type = result.get("diagram_type") or ""
        eval_score   = result.get("eval_score")

        render_mode_badge(mode)
        render_eval_bar(eval_score)

        if diagram_path:
            render_diagram_card(diagram_path, diagram_type, key="live")

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
