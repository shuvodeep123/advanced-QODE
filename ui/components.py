"""
ui/components.py — Reusable Streamlit HTML/CSS components for advanced-QODE.

All components render via st.markdown(..., unsafe_allow_html=True) using
the design tokens defined in ui/theme.py and ui/styles.css.

Public API
----------
    inject_css()                         Inject styles.css into the page once.
    render_header()                      Top-of-page branded header banner.
    render_welcome()                     First-run welcome card.
    render_user_bubble(text)             Right-aligned user chat bubble.
    render_assistant_bubble(text, mode)  Left-aligned assistant bubble (mode-aware).
    render_mode_badge(mode)              Coloured pill indicating As-Is vs LLM path.
    render_eval_bar(score)               Visual eval score progress bar.
    render_diagram_card(path, dtype)     Framed diagram with download button.
    render_info_card(label, value)       Small metric card for sidebar stats.
    render_sidebar_section(title)        Styled sidebar section heading.
    render_dot_fallback(dot_text, dtype) Code block + Lucidchart/Graphviz link.
"""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from ui.theme import COLORS, MODE_CONFIG

# ---------------------------------------------------------------------------
# CSS injection (call once at top of app.py)
# ---------------------------------------------------------------------------
_CSS_INJECTED = False


def inject_css() -> None:
    """Inject ui/styles.css into the Streamlit page (idempotent)."""
    global _CSS_INJECTED
    if _CSS_INJECTED:
        return

    css_path = Path(__file__).parent / "styles.css"
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # Also inject Google Fonts link tag
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )
    _CSS_INJECTED = True


# ---------------------------------------------------------------------------
# Header banner
# ---------------------------------------------------------------------------

def render_header() -> None:
    """Render the top-of-page branded header."""
    st.markdown(
        """
        <div class="qode-header">
          <h1>🔷 advanced-QODE</h1>
          <div class="subtitle">
            GenAI Diagram Assistant
            <span class="pill">📊 Graph-RAG</span>
            <span class="pill">🧠 LangGraph</span>
            <span class="pill">📡 Langfuse</span>
            <span class="pill">🔗 LlamaIndex</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Welcome card
# ---------------------------------------------------------------------------

def render_welcome() -> None:
    """Render the first-run welcome card."""
    st.markdown(
        """
        <div class="welcome-card">
          <h3>👋 Welcome to advanced-QODE</h3>
          <p>Your AI-powered DevSecOps diagram and maturity assessment assistant.
             Upload your QODE questionnaire in the sidebar, then ask away.</p>
          <div class="welcome-mode-row">
            <div class="welcome-mode-box">
              <div class="icon">📊</div>
              <div class="title" style="color:#f59e0b;">As-Is Architecture Mode</div>
              <div class="desc">
                Zero LLM cost — generates People, Process &amp; Technology diagrams
                directly from your questionnaire data via the core Python generators.
              </div>
              <div style="margin-top:8px;font-size:0.75rem;color:#8b949e;">
                <em>Try: "Create an As-Is People Architecture"</em>
              </div>
            </div>
            <div class="welcome-mode-box">
              <div class="icon">🧠</div>
              <div class="title" style="color:#10b981;">Engineering Principles Mode</div>
              <div class="desc">
                LLM + Graph-RAG — reasons across 9 Engineering Principles ×
                3 Disciplines (People, Process, Technology) for targeted recommendations.
              </div>
              <div style="margin-top:8px;font-size:0.75rem;color:#8b949e;">
                <em>Try: "How can I improve Security for my Technology stack?"</em>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Chat bubbles
# ---------------------------------------------------------------------------

def render_user_bubble(text: str) -> None:
    """Render a right-aligned user message bubble."""
    safe = html.escape(text).replace("\n", "<br>")
    st.markdown(
        f'<div class="chat-bubble-user">{safe}</div>',
        unsafe_allow_html=True,
    )


def render_assistant_bubble(text: str, mode: str = "principles") -> None:
    """Render a left-aligned assistant message bubble, styled by mode."""
    css_class = {
        "asis":       "chat-bubble-asis",
        "principles": "chat-bubble-llm",
        "error":      "chat-bubble-assistant",
    }.get(mode, "chat-bubble-assistant")

    # Convert markdown-style bold/italic minimally for HTML safety
    safe = html.escape(text)
    safe = safe.replace("\n\n", "</p><p>").replace("\n", "<br>")
    safe = f"<p>{safe}</p>"

    st.markdown(
        f'<div class="{css_class}">{safe}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Mode badge
# ---------------------------------------------------------------------------

def render_mode_badge(mode: str) -> None:
    """Render a coloured pill badge for the current execution mode."""
    cfg = MODE_CONFIG.get(mode, MODE_CONFIG["principles"])
    css_cls = {
        "asis": "mode-badge mode-badge-asis",
        "principles": "mode-badge mode-badge-principles",
        "error": "mode-badge mode-badge-error",
    }.get(mode, "mode-badge mode-badge-principles")

    st.markdown(
        f'<div class="{css_cls}">{cfg["label"]}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Eval score bar
# ---------------------------------------------------------------------------

def render_eval_bar(score: float | None) -> None:
    """Render a mini progress bar showing the RAG eval score."""
    if score is None:
        return
    pct = min(100, max(0, int(score * 100)))
    label = f"Eval score: {pct}%"
    st.markdown(
        f"""
        <div class="eval-bar">
          <span>{label}</span>
          <div class="eval-bar-track">
            <div class="eval-bar-fill" style="width:{pct}%;"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Diagram card
# ---------------------------------------------------------------------------

def render_diagram_card(path: str, dtype: str) -> None:
    """Render a framed diagram card with image display and download button."""
    p = Path(path)
    if not p.exists():
        st.warning(f"⚠️ Diagram file not found: `{path}`")
        return

    title = f"{dtype.title()} Architecture Diagram"

    st.markdown(
        f"""
        <div class="diagram-card">
          <div class="diagram-card-header">
            <span class="diagram-card-title">📐 {title}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if p.suffix.lower() == ".png":
        st.image(str(p), use_container_width=True)
        with open(str(p), "rb") as f:
            st.download_button(
                label=f"⬇️ Download PNG",
                data=f.read(),
                file_name=p.name,
                mime="image/png",
                use_container_width=True,
            )
    else:
        render_dot_fallback(p.read_text(encoding="utf-8", errors="replace"), dtype)


# ---------------------------------------------------------------------------
# DOT source fallback (Graphviz not installed)
# ---------------------------------------------------------------------------

def render_dot_fallback(dot_text: str, dtype: str) -> None:
    """Show DOT source with links to online visualisers."""
    import urllib.parse

    encoded = urllib.parse.quote(dot_text)
    gv_url = f"https://dreampuf.github.io/GraphvizOnline/#{encoded}"

    st.markdown(
        f"""
        <div style="background:var(--bg-elevated,#1c2330);border:1px solid
             var(--border-default,#30363d);border-radius:10px;padding:14px;margin-top:8px;">
          <div style="font-size:0.75rem;font-weight:600;text-transform:uppercase;
               letter-spacing:0.08em;color:#8b949e;margin-bottom:8px;">
            📄 {dtype.title()} Diagram — DOT source
          </div>
          <p style="font-size:0.8125rem;color:#8b949e;margin:0 0 10px 0;">
            Graphviz is not installed locally. Visualise in your browser:
          </p>
          <a href="{gv_url}" target="_blank"
             style="display:inline-block;background:rgba(59,130,246,0.1);
                    border:1px solid rgba(59,130,246,0.3);border-radius:6px;
                    padding:4px 12px;font-size:0.8125rem;color:#3b82f6;
                    text-decoration:none;margin-right:8px;">
            🌐 Graphviz Online
          </a>
          <a href="https://www.lucidchart.com/pages/integrations/graphviz" target="_blank"
             style="display:inline-block;background:rgba(139,92,246,0.1);
                    border:1px solid rgba(139,92,246,0.3);border-radius:6px;
                    padding:4px 12px;font-size:0.8125rem;color:#8b5cf6;
                    text-decoration:none;">
            📐 Lucidchart Import
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("View DOT source"):
        st.code(dot_text, language="dot")
    st.download_button(
        label="⬇️ Download DOT file",
        data=dot_text,
        file_name=f"{dtype}_diagram.dot",
        mime="text/plain",
    )


# ---------------------------------------------------------------------------
# Sidebar helpers
# ---------------------------------------------------------------------------

def render_sidebar_section(title: str) -> None:
    """Render a styled sidebar section heading."""
    st.markdown(
        f'<div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.1em;color:#484f58;margin:16px 0 6px 0;">{title}</div>',
        unsafe_allow_html=True,
    )


def render_info_card(label: str, value: str, color: str = "#f0f6fc") -> None:
    """Render a small metric card in the sidebar."""
    st.markdown(
        f"""
        <div class="info-card">
          <div class="info-card-label">{label}</div>
          <div class="info-card-value" style="color:{color};">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
