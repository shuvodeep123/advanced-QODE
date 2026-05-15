"""
app.py — Streamlit chat interface for the Diagram Assistant.

Architecture
------------
  📊 As-Is path       : RAG only, zero LLM — generates diagrams from the 3 core Python files.
  🧠 Principles path  : LLM + Graph-RAG across 8 Engineering Principles × 3 Disciplines.

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
    render_mermaid,
    render_sidebar_section,
    render_info_card,
    render_token_counter,
    render_model_card,
)

inject_css()

# ---------------------------------------------------------------------------
# Lazy domain imports (after page config)
# ---------------------------------------------------------------------------
from rag_pipeline.chain import run_chain, detect_intent, detect_asis_request, detect_narrative_request
from rag_pipeline.ingest import ingest_all
from rag_pipeline.graph_builder import DEFAULT_GRAPH_PATH
from rag_pipeline.graph_retriever import invalidate_cache
from rag_pipeline.token_counter import get_usage, reset as reset_token_counter, DEFAULT_BUDGET
from rag_pipeline.doc_generator import generate_document
from rag_pipeline.chat_history import (
    new_session_id, save_message, load_history, list_sessions,
    clear_session, prune_old_sessions,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CHROMA_PATH = "./chroma_db"
_GRAPH_PATH  = DEFAULT_GRAPH_PATH
_SUPPORTED   = ["xlsm", "xlsx", "docx", "txt"]

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
    # Persistent session ID — stable across Streamlit reruns within one browser session
    "session_id":     new_session_id(),
    # Pending session switch — set to a session_id string to switch on next rerun
    "_switch_session": None,
    # Token budget — read from env so it can be overridden per deployment
    "token_budget":   int(os.environ.get("TOKEN_BUDGET", str(DEFAULT_BUDGET))),
    # Token usage snapshot — refreshed from token_counter after each LLM call
    "token_prompt":       0,
    "token_completion":   0,
    "token_total":        0,
    "token_call_count":   0,
    "token_by_model":     {},
    # Last single-call token counts (auto-refreshed after each iteration)
    "last_call_prompt":     0,
    "last_call_completion": 0,
    "last_call_total":      0,
    # Flag: True once the SQLite history has been loaded into session_state.messages
    "_history_loaded":    False,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Session switch (triggered by Chat History Panel) ─────────────────────────
_pending_switch: str | None = st.session_state.pop("_switch_session", None)
if _pending_switch and _pending_switch != st.session_state.session_id:
    _switched_msgs = load_history(_pending_switch)
    st.session_state.session_id     = _pending_switch
    st.session_state.messages       = _switched_msgs
    st.session_state.diagram_paths  = {}
    st.session_state._history_loaded = True

# Load persisted chat history into session state on the FIRST run of this session.
# Subsequent reruns skip this to avoid overwriting in-memory messages.
if not st.session_state._history_loaded:
    _persisted = load_history(st.session_state.session_id)
    if _persisted:
        st.session_state.messages = _persisted
    st.session_state._history_loaded = True
    # Housekeeping: quietly remove sessions older than 96 hours
    try:
        prune_old_sessions(days=4)   # 96 hours
    except Exception:
        pass


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
    st.session_state.last_call_prompt   = usage.last_call_prompt
    st.session_state.last_call_completion = usage.last_call_completion
    st.session_state.last_call_total    = usage.last_call_total

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

    # ── Active model ────────────────────────────────────────────────────────
    render_sidebar_section("Current Model")
    render_model_card(
        model_name=os.environ.get("HF_MODEL", "unknown"),
        base_url=os.environ.get("HF_BASE_URL", ""),
    )

    st.divider()

    # ── Token Count ───────────────────────────────────────────────────────
    render_sidebar_section("Token Counts")
    render_token_counter(
        prompt_tokens=st.session_state.token_prompt,
        completion_tokens=st.session_state.token_completion,
        total_tokens=st.session_state.token_total,
        budget=st.session_state.token_budget,
        call_count=st.session_state.token_call_count,
        by_model=st.session_state.token_by_model,
        last_call_prompt=st.session_state.last_call_prompt,
        last_call_completion=st.session_state.last_call_completion,
        last_call_total=st.session_state.last_call_total,
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
        with st.spinner("🔄 Re-concilling Knowledge Base"):
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
    render_sidebar_section("⚡ One Touch As-Is Diagram ")

    def _qprompt(p: str) -> None:
        st.session_state._quick_input = p

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📊\nProcess", use_container_width=True, key="asis_process"):
            _qprompt("Create an As-Is Process Network Architecture diagram codebase")
    with c2:
        if st.button("👥\nPeople", use_container_width=True, key="asis_people"):
            _qprompt("Create an As-Is People Architecture diagram codebase.")
    with c3:
        if st.button("🔧\nTechnology", use_container_width=True, key="asis_tech"):
            _qprompt("Create an As-Is Technology Architecture diagram codebase .")

    # ── To-Be quick-action buttons ─────────────────────────────────────────
    render_sidebar_section("🔮 One Touch To-Be Diagram")

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
        clear_session(st.session_state.session_id)
        st.session_state.messages = []
        st.session_state.diagram_paths = {}
        st.rerun()

    if st.button("➕ New session", use_container_width=True):
        st.session_state.session_id    = new_session_id()
        st.session_state.messages      = []
        st.session_state.diagram_paths = {}
        st.session_state._history_loaded = True
        st.rerun()

    st.divider()

    # ── Chat History Panel (96 h) ──────────────────────────────────────────
    render_sidebar_section("📜 Chat History (96 h)")
    try:
        _sessions = list_sessions(hours=96)
    except Exception:
        _sessions = []

    if not _sessions:
        st.markdown(
            '<div style="font-size:0.75rem;color:#484f58;padding:4px 0;">'
            'No recent sessions found.</div>',
            unsafe_allow_html=True,
        )
    else:
        from datetime import datetime as _dt, timezone as _tz
        _now = _dt.now(_tz.utc)

        for _si, _sess in enumerate(_sessions):
            _sid        = _sess["session_id"]
            _is_current = (_sid == st.session_state.session_id)
            _msg_count  = _sess["message_count"]
            _title      = _sess["first_message"] or "(empty session)"

            # Human-readable age
            try:
                _created = _dt.fromisoformat(_sess["created_at"].replace("Z", "+00:00"))
                _age_sec = int((_now - _created).total_seconds())
                if _age_sec < 3600:
                    _age_str = f"{_age_sec // 60}m ago"
                elif _age_sec < 86400:
                    _age_str = f"{_age_sec // 3600}h ago"
                else:
                    _age_str = f"{_age_sec // 86400}d ago"
            except Exception:
                _age_str = "—"

            _icon  = "📌" if _is_current else "📖"
            _style = (
                "background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.4);"
                if _is_current else
                "background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);"
            )
            st.markdown(
                f'<div style="{_style}border-radius:6px;padding:6px 8px;margin-bottom:4px;">'
                f'<div style="font-size:0.72rem;color:#8b949e;">'
                f'{_icon} {_age_str} &nbsp;·&nbsp; {_msg_count} msg</div>'
                f'<div style="font-size:0.78rem;color:#e6edf3;white-space:nowrap;'
                f'overflow:hidden;text-overflow:ellipsis;max-width:190px;" '
                f'title="{_title}">{_title}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if not _is_current:
                if st.button(
                    "↩ Load",
                    key=f"load_sess_{_si}",
                    use_container_width=True,
                ):
                    st.session_state._switch_session = _sid
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
            # Show Mermaid diagram
            if msg.get("tobe_mermaid_path") and Path(msg["tobe_mermaid_path"]).exists():
                _hist_mmd = Path(msg["tobe_mermaid_path"]).read_text(encoding="utf-8", errors="replace")
                render_mermaid(_hist_mmd, msg.get("diagram_type", "general"), key=f"hist_mmd_{_msg_idx}")

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
    save_message(st.session_state.session_id, {"role": "user", "content": prompt})

    history      = st.session_state.messages[:-1]
    is_asis      = detect_asis_request(prompt)
    intent     = detect_intent(prompt)
    is_narrative = detect_narrative_request(prompt)

    # Detect To-Be mode (LLM path even if "generate" keyword present)
    is_tobe = any(kw in prompt.lower() for kw in ["to-be", "to be", "tobe", "target state", "future state"])
    if is_tobe:
        is_asis = False   # To-Be always uses LLM path

    # Narrative questions (e.g. "30-60-90 plan", "what improvements …") are
    # never streamed — we need the full text to offer document downloads.
    status_msg = (
        f"📊 Analysing As-Is {intent.title()} Architecture via LLM + Graph-RAG …"
        if is_asis and intent != "general"
        else f"🔮 Generating To-Be {intent.title()} diagram via LLM + Graph-RAG …"
        if is_tobe and intent != "general"
        else "📝 Preparing analysis …"
        if is_narrative
        else "🧠 Reasoning with Graph-RAG + LLM …"
    )

    with st.chat_message("assistant"):
        with st.status(status_msg, expanded=False):
            try:
                # Narrative and diagram requests always run non-streaming so the
                # full text is available for Mermaid extraction and doc generation.
                wants_diagram = (intent != "general")
                use_stream = (not is_asis) and (not wants_diagram) and (not is_narrative)
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

        # ── Show thinking (chain-of-thought) if the model emitted one ─────────
        _thinking = result.get("thinking_text", "")
        if _thinking:
            with st.expander("🧠 Reasoning…", expanded=False):
                st.markdown(
                    f'<div style="font-size:0.82rem;color:#484f58;'
                    f'white-space:pre-wrap;font-family:JetBrains Mono,monospace;">'
                    f'{__import__("html").escape(_thinking)}</div>',
                    unsafe_allow_html=True,
                )

        # ── Resolve and display reply ─────────────────────────────────────
        if result.get("stream"):
            full_reply = st.write_stream(result["stream"])
        else:
            full_reply   = result.get("text", "")
            display_text = _strip_mermaid_fences(full_reply)

            if is_narrative and full_reply and result.get("mode") != "error":
                # Show a condensed preview (first ~400 chars) then offer docs
                preview = display_text[:400].rsplit(" ", 1)[0] + " …" if len(display_text) > 400 else display_text
                render_assistant_bubble(preview, result.get("mode", "principles"))

                st.markdown(
                    "<div style='font-size:0.82rem;color:#8b949e;margin:8px 0 4px;'>"
                    "📄 <strong>Download full analysis as a document:</strong></div>",
                    unsafe_allow_html=True,
                )
                _doc_title = prompt[:80]
                _dcols = st.columns(4)
                _doc_fmts = [
                    ("word",  "📝 Word",        ".docx"),
                    ("excel", "📊 Excel",       ".xlsx"),
                    ("pptx",  "📽 PowerPoint", ".pptx"),
                    ("pdf",   "📑 PDF",         ".pdf"),
                ]
                for _col, (_fmt, _label, _ext) in zip(_dcols, _doc_fmts):
                    with _col:
                        try:
                            _data, _fname, _mime = generate_document(_fmt, _doc_title, full_reply)
                            st.download_button(
                                label=_label,
                                data=_data,
                                file_name=_fname,
                                mime=_mime,
                                use_container_width=True,
                                key=f"dl_{_fmt}_{len(st.session_state.messages)}",
                            )
                        except Exception as _de:
                            st.button(_label, disabled=True, use_container_width=True,
                                      help=f"Unavailable: {_de}",
                                      key=f"dl_{_fmt}_err_{len(st.session_state.messages)}")
            else:
                render_assistant_bubble(display_text, result.get("mode", "principles"))

        mode         = result.get("mode", "principles")
        diagram_path = result.get("diagram_path")
        diagram_type = result.get("diagram_type") or ""
        eval_score   = result.get("eval_score")

        render_mode_badge(mode)
        render_eval_bar(eval_score)

        # Show Mermaid diagram
        tobe_mmd_path = result.get("tobe_mermaid_path")
        if tobe_mmd_path and Path(tobe_mmd_path).exists():
            mmd_text_live = Path(tobe_mmd_path).read_text(encoding="utf-8", errors="replace")
            render_mermaid(mmd_text_live, diagram_type or "general", key="live_mmd")

    _asst_msg = {
        "role":           "assistant",
        "content":        full_reply or "",
        "diagram_path":   diagram_path,
        "tobe_mermaid_path":  result.get("tobe_mermaid_path"),
        "diagram_type":   diagram_type,
        "mode":           mode,
        "eval_score":     eval_score,
    }
    st.session_state.messages.append(_asst_msg)
    save_message(st.session_state.session_id, _asst_msg)

    if diagram_path and diagram_type:
        st.session_state.diagram_paths[diagram_type] = diagram_path
