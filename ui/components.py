"""
ui/components.py — Reusable Streamlit HTML/CSS components for advanced-QODE.

All components render via st.markdown(..., unsafe_allow_html=True) using
the design tokens defined in ui/theme.py and ui/styles.css.

Public API
----------
    inject_css()                          Inject styles.css into the page once.
    render_header()                       Top-of-page branded header banner.
    render_welcome()                      First-run welcome card.
    render_user_bubble(text)              Right-aligned user chat bubble.
    render_assistant_bubble(text, mode)   Left-aligned assistant bubble (mode-aware).
    render_mode_badge(mode)               Coloured pill indicating As-Is vs LLM path.
    render_eval_bar(score)                Visual eval score progress bar.
    render_diagram_card(path, dtype)      Framed diagram — auto-detects .png/.mmd/.puml/.dot.
    render_mermaid(mmd_text, dtype)       Inline Mermaid diagram via mermaid.js CDN.
    render_plantuml(puml_text, dtype)     PlantUML diagram via public render server.
    render_dot_fallback(dot_text, dtype)  Mermaid + PlantUML online links (no Lucidchart).
    render_info_card(label, value)        Small metric card for sidebar stats.
    render_sidebar_section(title)         Styled sidebar section heading.
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
                directly from your questionnaire via the core Python generators.
                Output rendered as <strong>Mermaid</strong> or <strong>PlantUML</strong>.
              </div>
              <div style="margin-top:8px;font-size:0.75rem;color:#8b949e;">
                <em>Try: "Create an As-Is People Architecture"</em>
              </div>
            </div>
            <div class="welcome-mode-box">
              <div class="icon">🔮</div>
              <div class="title" style="color:#10b981;">To-Be Architecture Mode</div>
              <div class="desc">
                LLM + Graph-RAG — generates recommended target-state diagrams
                across People, Process &amp; Technology with actionable improvements.
                Output also rendered as <strong>Mermaid</strong> or <strong>PlantUML</strong>.
              </div>
              <div style="margin-top:8px;font-size:0.75rem;color:#8b949e;">
                <em>Try: "Create a To-Be Technology Architecture"</em>
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
# Mermaid inline renderer
# ---------------------------------------------------------------------------

def render_mermaid(mmd_text: str, dtype: str) -> None:
    """Render a Mermaid diagram inline using mermaid.js via CDN."""
    import html as _html
    safe_mmd = _html.escape(mmd_text)
    title = f"{dtype.title()} Architecture Diagram"

    st.markdown(
        f"""
        <div class="diagram-card">
          <div class="diagram-card-header">
            <span class="diagram-card-title">📐 {title}</span>
            <span style="font-size:0.7rem;color:#8b5cf6;font-weight:600;">
              ◈ Mermaid
            </span>
          </div>
          <div class="mermaid" style="background:#0d1117;border-radius:8px;padding:12px;">
{mmd_text}
          </div>
        </div>
        <script type="module">
          import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
          mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {{
              primaryColor: '#1d4ed8',
              primaryTextColor: '#f0f6fc',
              primaryBorderColor: '#3b82f6',
              lineColor: '#8b949e',
              secondaryColor: '#1c2330',
              tertiaryColor: '#161b22'
            }}
          }});
        </script>
        """,
        unsafe_allow_html=True,
    )

    # Download button
    col1, col2 = st.columns([1, 1])
    with col1:
        st.download_button(
            label="⬇️ Download Mermaid (.mmd)",
            data=mmd_text,
            file_name=f"{dtype}_diagram.mmd",
            mime="text/plain",
            use_container_width=True,
        )
    with col2:
        import urllib.parse
        encoded = urllib.parse.quote(mmd_text)
        st.markdown(
            f'<a href="https://mermaid.live/edit#base64:{_b64(mmd_text)}" target="_blank" '
            f'style="display:block;text-align:center;background:rgba(139,92,246,0.1);'
            f'border:1px solid rgba(139,92,246,0.3);border-radius:6px;padding:6px 0;'
            f'font-size:0.8125rem;color:#8b5cf6;text-decoration:none;">🔗 Open in Mermaid Live</a>',
            unsafe_allow_html=True,
        )


def _b64(text: str) -> str:
    """Base64-encode text for Mermaid Live editor URL."""
    import base64
    return base64.urlsafe_b64encode(text.encode()).decode()


# ---------------------------------------------------------------------------
# PlantUML renderer
# ---------------------------------------------------------------------------

def render_plantuml(puml_text: str, dtype: str) -> None:
    """Render a PlantUML diagram via the public PlantUML server."""
    import base64
    import zlib
    import urllib.parse

    title = f"{dtype.title()} Architecture Diagram"

    # PlantUML uses a custom base64 alphabet
    def _plantuml_encode(data: bytes) -> str:
        _PLANTUML_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
        compressed = zlib.compress(data)[2:-4]
        result = []
        i = 0
        while i < len(compressed):
            b0 = compressed[i] if i < len(compressed) else 0
            b1 = compressed[i + 1] if i + 1 < len(compressed) else 0
            b2 = compressed[i + 2] if i + 2 < len(compressed) else 0
            result.append(_PLANTUML_CHARS[(b0 >> 2) & 0x3F])
            result.append(_PLANTUML_CHARS[((b0 & 0x3) << 4) | ((b1 >> 4) & 0xF)])
            result.append(_PLANTUML_CHARS[((b1 & 0xF) << 2) | ((b2 >> 6) & 0x3)])
            result.append(_PLANTUML_CHARS[b2 & 0x3F])
            i += 3
        return "".join(result)

    try:
        encoded = _plantuml_encode(puml_text.encode("utf-8"))
        img_url = f"https://www.plantuml.com/plantuml/png/{encoded}"
        edit_url = f"https://www.plantuml.com/plantuml/uml/{encoded}"

        st.markdown(
            f"""
            <div class="diagram-card">
              <div class="diagram-card-header">
                <span class="diagram-card-title">📐 {title}</span>
                <span style="font-size:0.7rem;color:#10b981;font-weight:600;">
                  ◈ PlantUML
                </span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(img_url, use_container_width=True)

        col1, col2 = st.columns([1, 1])
        with col1:
            st.download_button(
                label="⬇️ Download PlantUML (.puml)",
                data=puml_text,
                file_name=f"{dtype}_diagram.puml",
                mime="text/plain",
                use_container_width=True,
            )
        with col2:
            st.markdown(
                f'<a href="{edit_url}" target="_blank" '
                f'style="display:block;text-align:center;background:rgba(16,185,129,0.1);'
                f'border:1px solid rgba(16,185,129,0.3);border-radius:6px;padding:6px 0;'
                f'font-size:0.8125rem;color:#10b981;text-decoration:none;">🔗 Edit in PlantUML</a>',
                unsafe_allow_html=True,
            )
    except Exception as exc:
        st.warning(f"PlantUML render failed: {exc}")
        with st.expander("View PlantUML source"):
            st.code(puml_text, language="text")


# ---------------------------------------------------------------------------
# Diagram card — auto-detects format
# ---------------------------------------------------------------------------

def render_diagram_card(path: str, dtype: str) -> None:
    """Render a framed diagram card — auto-detects .png / .mmd / .puml / .dot."""
    p = Path(path)
    if not p.exists():
        st.warning(f"⚠️ Diagram file not found: `{path}`")
        return

    ext = p.suffix.lower()
    text = p.read_text(encoding="utf-8", errors="replace") if ext != ".png" else ""

    if ext == ".png":
        st.markdown(
            f'<div class="diagram-card"><div class="diagram-card-header">'
            f'<span class="diagram-card-title">📐 {dtype.title()} Architecture Diagram</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        st.image(str(p), use_container_width=True)
        with open(str(p), "rb") as f:
            st.download_button(
                label="⬇️ Download PNG",
                data=f.read(),
                file_name=p.name,
                mime="image/png",
                use_container_width=True,
            )

    elif ext == ".mmd":
        render_mermaid(text, dtype)

    elif ext == ".puml":
        render_plantuml(text, dtype)

    else:
        # Raw DOT fallback → convert on-the-fly to Mermaid for display
        render_dot_fallback(text, dtype)


# ---------------------------------------------------------------------------
# DOT fallback — converts to Mermaid + PlantUML online (no Lucidchart)
# ---------------------------------------------------------------------------

def render_dot_fallback(dot_text: str, dtype: str) -> None:
    """Show Mermaid + PlantUML online links when only raw DOT is available."""
    import urllib.parse
    from rag_pipeline.diagram_executor import dot_to_mermaid, dot_to_plantuml

    # Convert DOT → Mermaid and render inline
    try:
        mmd_text = dot_to_mermaid(dot_text, dtype)
        render_mermaid(mmd_text, dtype)
    except Exception:
        pass

    # Also offer PlantUML
    try:
        puml_text = dot_to_plantuml(dot_text, dtype)
        with st.expander("🔮 Also view as PlantUML"):
            render_plantuml(puml_text, dtype)
    except Exception:
        pass

    # Raw DOT source always available
    with st.expander("🔧 View raw DOT source"):
        st.code(dot_text, language="dot")
        gv_url = f"https://dreampuf.github.io/GraphvizOnline/#{urllib.parse.quote(dot_text)}"
        st.markdown(
            f'<a href="{gv_url}" target="_blank" style="font-size:0.8rem;color:#3b82f6;">'
            f'🌐 Open in Graphviz Online</a>',
            unsafe_allow_html=True,
        )
        st.download_button(
            label="⬇️ Download DOT",
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
