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

def render_mermaid(mmd_text: str, dtype: str, key: str = "") -> None:
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
            key=f"dl_mmd_{key}",
        )
    with col2:
        st.markdown(
            f'<a href="https://mermaid.live/edit#base64:{_b64(mmd_text)}" target="_blank" '
            f'style="display:block;text-align:center;background:rgba(139,92,246,0.1);'
            f'border:1px solid rgba(139,92,246,0.3);border-radius:6px;padding:6px 0;'
            f'font-size:0.8125rem;color:#8b5cf6;text-decoration:none;">\U0001f517 Open in mermaid.ai\/app</a>',
            unsafe_allow_html=True,
        )


def _b64(text: str) -> str:
    """Base64-encode text for Mermaid Live / edotor.net URL."""
    import base64
    return base64.urlsafe_b64encode(text.encode()).decode()


# ---------------------------------------------------------------------------
# DOT diagram renderer (To-Be)
# ---------------------------------------------------------------------------

def render_dot_diagram(dot_text: str, dtype: str, key: str = "") -> None:
    """Render a To-Be DOT graph card with inline preview + edotor.net link.

    Shows the raw DOT source, a download button, and an "Open in edotor.net"
    button that pre-loads the diagram in the online Graphviz editor.
    """
    import base64

    title = f"{dtype.title()} To-Be Architecture \u2014 DOT Graph"
    b64_dot = base64.urlsafe_b64encode(dot_text.encode()).decode()
    edotor_url = f"https://edotor.net/?engine=dot#{b64_dot}"

    st.markdown(
        f"""
        <div class="diagram-card">
          <div class="diagram-card-header">
            <span class="diagram-card-title">\U0001f5fa\ufe0f {title}</span>
            <span style="font-size:0.7rem;color:#f59e0b;font-weight:600;">
              \u25c8 Graphviz DOT
            </span>
          </div>
          <div style="padding:10px 12px;background:rgba(245,158,11,0.07);
                border-radius:8px;border:1px solid rgba(245,158,11,0.2);
                font-size:0.78rem;color:#8b949e;">
            \U0001f4a1 DOT graph generated from To-Be LLM output.
            Click <strong>Open in edotor.net</strong> to visualise interactively.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("\U0001f9f1 View To-Be DOT source", expanded=False):
        st.code(dot_text, language="dot")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.download_button(
            label="\u2b07\ufe0f Download DOT (.dot)",
            data=dot_text,
            file_name=f"{dtype}_tobe_diagram.dot",
            mime="text/plain",
            use_container_width=True,
            key=f"dl_tobe_dot_{key}",
        )
    with col2:
        st.markdown(
            f'<a href="{edotor_url}" target="_blank" '
            f'style="display:block;text-align:center;background:rgba(245,158,11,0.1);'
            f'border:1px solid rgba(245,158,11,0.3);border-radius:6px;padding:6px 0;'
            f'font-size:0.8125rem;color:#f59e0b;text-decoration:none;">'
            f'\U0001f517 Open in edotor.net</a>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# PlantUML renderer
# ---------------------------------------------------------------------------

def render_plantuml(puml_text: str, dtype: str, key: str = "") -> None:
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
                key=f"dl_puml_{key}",
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
# draw.io renderer
# ---------------------------------------------------------------------------

def render_drawio(drawio_text: str, dtype: str, key: str = "") -> None:
    """Render a draw.io diagram — provides download + open-in-diagrams.net link.

    draw.io XML cannot be rendered inline in a browser without the draw.io
    embed script (requires iframe + CORS). We therefore:
    1. Show a styled download button for the ``.drawio`` file.
    2. Provide a one-click link to open the diagram in diagrams.net.
    3. Show the raw XML in a collapsible expander for inspection.

    To wire up a custom draw.io MCP server, replace the ``diagrams_url`` below
    with your MCP endpoint and pass the XML as a POST body.
    """
    import base64

    title = f"{dtype.title()} Architecture Diagram"
    # diagrams.net opens inline XML via the #xml= fragment (standard base64).
    # The ?xml= query param is ignored; the fragment is the correct approach.
    b64_xml = base64.b64encode(drawio_text.encode()).decode()
    diagrams_url = f"https://app.diagrams.net/#xml={b64_xml}"

    st.markdown(
        f"""
        <div class="diagram-card">
          <div class="diagram-card-header">
            <span class="diagram-card-title">📄 {title}</span>
            <span style="font-size:0.7rem;color:#f59e0b;font-weight:600;">
              ◈ draw.io
            </span>
          </div>
          <div style="padding:12px;background:rgba(245,158,11,0.08);
                border-radius:8px;border:1px solid rgba(245,158,11,0.25);
                font-size:0.8rem;color:#e5c07b;">
            💡 draw.io XML generated — use the buttons below to open or download.
            <br>
            <span style="font-size:0.72rem;color:#8b949e;">
              To use a custom MCP server, replace the diagrams.net URL in
              <code>ui/components.py &gt; render_drawio()</code>.
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        st.download_button(
            label="⬇️ Download draw.io (.drawio)",
            data=drawio_text,
            file_name=f"{dtype}_diagram.drawio",
            mime="application/xml",
            use_container_width=True,
            key=f"dl_drawio_{key}",
        )
    with col2:
        st.markdown(
            f'<a href="{diagrams_url}" target="_blank" '
            f'style="display:block;text-align:center;background:rgba(245,158,11,0.1);'
            f'border:1px solid rgba(245,158,11,0.3);border-radius:6px;padding:6px 0;'
            f'font-size:0.8125rem;color:#f59e0b;text-decoration:none;">'
            f'🔗 Open in diagrams.net</a>',
            unsafe_allow_html=True,
        )

    with st.expander("🔧 View draw.io XML source"):
        st.code(drawio_text, language="xml")


# ---------------------------------------------------------------------------
# Diagram card — auto-detects format
# ---------------------------------------------------------------------------

def render_diagram_card(path: str, dtype: str, key: str = "") -> None:
    """Render a framed diagram card — auto-detects .png / .mmd / .puml / .dot."""
    p = Path(path)
    if not p.exists():
        st.warning(f"⚠️ Diagram file not found: `{path}`")
        return

    ext = p.suffix.lower()
    text = p.read_text(encoding="utf-8", errors="replace") if ext != ".png" else ""
    _key = key or p.stem

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
                key=f"dl_png_{_key}",
            )

    elif ext == ".mmd":
        render_mermaid(text, dtype, key=_key)

    elif ext == ".puml":
        render_plantuml(text, dtype, key=_key)

    elif ext in (".drawio", ".xml"):
        render_drawio(text, dtype, key=_key)

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


# ---------------------------------------------------------------------------
# Active model card
# ---------------------------------------------------------------------------

def render_model_card(model_name: str, base_url: str = "") -> None:
    """Render a styled card showing the active LLM model name."""
    # e.g. "zai-org/glm-4.7" → org="zai-org", short="glm-4.7"
    if "/" in model_name:
        org, short = model_name.rsplit("/", 1)
        org_html = f'<span style="font-size:0.65rem;color:#484f58;">{html.escape(org)}/</span>'
    else:
        short = model_name
        org_html = ""

    host = ""
    if base_url:
        try:
            from urllib.parse import urlparse as _urlparse
            host = _urlparse(base_url).netloc or base_url
        except Exception:
            host = base_url

    host_html = (
        f'<div style="font-size:0.62rem;color:#484f58;margin-top:2px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
        f'{html.escape(host)}</div>'
        if host else ""
    )

    st.markdown(
        f"""
        <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;
                    padding:8px 10px;margin-bottom:4px;">
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="font-size:1rem;">🤖</span>
            <div style="overflow:hidden;">
              <div style="font-size:0.75rem;font-weight:600;color:#60a5fa;
                          white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                {org_html}{html.escape(short)}
              </div>
              {host_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Token counter widget
# ---------------------------------------------------------------------------

def render_token_counter(
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    budget: int,
    call_count: int,
    by_model: dict | None = None,
    last_call_prompt: int = 0,
    last_call_completion: int = 0,
    last_call_total: int = 0,
) -> None:
    """Render a real-time token usage panel in the sidebar.

    Shows:
    - A segmented arc gauge: green → amber → red as usage climbs
    - Prompt / completion breakdown
    - Per-model breakdown (collapsible)
    - Number of LLM calls this session
    """
    if budget <= 0:
        budget = 1  # avoid divide-by-zero

    pct = min(100.0, total_tokens / budget * 100)

    # ── Arc gauge colour: green < 60 %, amber 60–85 %, red > 85 % ──────
    if pct < 60:
        bar_color = "#10b981"   # emerald
        text_color = "#10b981"
    elif pct < 85:
        bar_color = "#f59e0b"   # amber
        text_color = "#f59e0b"
    else:
        bar_color = "#ef4444"   # red
        text_color = "#ef4444"

    # Dash-array for a semi-circle arc: circumference of r=40 circle ≈ 251.2
    # We use a 75 % arc (270°) = 0.75 × 251.2 ≈ 188.4 total dash
    arc_total   = 188.4
    arc_used    = arc_total * pct / 100
    arc_remain  = arc_total - arc_used

    # Rotation: start the arc at 7 o'clock (225° from top = 135° CSS rotation)
    rotate_deg  = 135

    budget_k    = f"{budget // 1000}k" if budget >= 1000 else str(budget)
    total_k     = (
        f"{total_tokens / 1000:.1f}k" if total_tokens >= 1000
        else str(total_tokens)
    )

    st.markdown(
        f"""
        <div style="display:flex;flex-direction:column;align-items:center;
                    padding:8px 0 4px;">

          <!-- Arc gauge via SVG -->
          <svg width="110" height="72" viewBox="0 0 110 72"
               style="overflow:visible;margin-bottom:2px;">
            <!-- Track arc (dark) -->
            <circle cx="55" cy="55" r="40"
              fill="none"
              stroke="#21262d"
              stroke-width="10"
              stroke-dasharray="{arc_total:.1f} {251.2 - arc_total:.1f}"
              stroke-dashoffset="0"
              stroke-linecap="round"
              transform="rotate({rotate_deg} 55 55)"/>
            <!-- Used arc (colour) -->
            <circle cx="55" cy="55" r="40"
              fill="none"
              stroke="{bar_color}"
              stroke-width="10"
              stroke-dasharray="{arc_used:.1f} {251.2 - arc_used:.1f}"
              stroke-dashoffset="0"
              stroke-linecap="round"
              transform="rotate({rotate_deg} 55 55)"/>
            <!-- Centre label -->
            <text x="55" y="52" text-anchor="middle"
              font-size="14" font-weight="700"
              fill="{text_color}" font-family="Inter,sans-serif">
              {pct:.1f}%
            </text>
            <text x="55" y="65" text-anchor="middle"
              font-size="8" fill="#8b949e" font-family="Inter,sans-serif">
              used
            </text>
          </svg>

          <!-- Token totals row -->
          <div style="font-size:0.72rem;color:#8b949e;margin-bottom:6px;">
            <span style="color:{text_color};font-weight:600;">{total_k}</span>
            &nbsp;/&nbsp;{budget_k} tokens
          </div>

          <!-- Prompt / completion breakdown -->
          <div style="width:100%;display:flex;gap:6px;margin-bottom:4px;">
            <div style="flex:1;background:#161b22;border:1px solid #21262d;
                        border-radius:6px;padding:5px 6px;text-align:center;">
              <div style="font-size:0.65rem;color:#8b949e;text-transform:uppercase;
                          letter-spacing:0.05em;">Prompt</div>
              <div style="font-size:0.78rem;font-weight:600;color:#3b82f6;">
                {prompt_tokens:,}
              </div>
            </div>
            <div style="flex:1;background:#161b22;border:1px solid #21262d;
                        border-radius:6px;padding:5px 6px;text-align:center;">
              <div style="font-size:0.65rem;color:#8b949e;text-transform:uppercase;
                          letter-spacing:0.05em;">Completion</div>
              <div style="font-size:0.78rem;font-weight:600;color:#8b5cf6;">
                {completion_tokens:,}
              </div>
            </div>
            <div style="flex:1;background:#161b22;border:1px solid #21262d;
                        border-radius:6px;padding:5px 6px;text-align:center;">
              <div style="font-size:0.65rem;color:#8b949e;text-transform:uppercase;
                          letter-spacing:0.05em;">Calls</div>
              <div style="font-size:0.78rem;font-weight:600;color:#10b981;">
                {call_count}
              </div>
            </div>
          </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    # ⚡ Last Iteration card (only shown after at least one LLM call)
    if last_call_total > 0:
        lc_p = f"{last_call_prompt:,}"
        lc_c = f"{last_call_completion:,}"
        lc_t = f"{last_call_total:,}"
        st.markdown(
            f"""
            <div style="background:rgba(96,165,250,0.07);border:1px solid rgba(96,165,250,0.2);
                        border-radius:6px;padding:6px 8px;margin-bottom:6px;">
              <div style="font-size:0.65rem;color:#60a5fa;font-weight:700;
                          text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">
                ⚡ Last Iteration
              </div>
              <div style="display:flex;gap:4px;">
                <div style="flex:1;text-align:center;">
                  <div style="font-size:0.6rem;color:#8b949e;">Prompt</div>
                  <div style="font-size:0.75rem;font-weight:600;color:#3b82f6;">{lc_p}</div>
                </div>
                <div style="flex:1;text-align:center;">
                  <div style="font-size:0.6rem;color:#8b949e;">Compl.</div>
                  <div style="font-size:0.75rem;font-weight:600;color:#8b5cf6;">{lc_c}</div>
                </div>
                <div style="flex:1;text-align:center;">
                  <div style="font-size:0.6rem;color:#8b949e;">Total</div>
                  <div style="font-size:0.75rem;font-weight:600;color:#60a5fa;">{lc_t}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Per-model breakdown (collapsible, only show when multiple models used)
    if by_model:
        with st.expander("📊 By model", expanded=False):
            for mname, mtokens in sorted(
                by_model.items(), key=lambda x: -x[1]
            ):
                mpct = min(100, int(mtokens / budget * 100))
                st.markdown(
                    f'<div style="font-size:0.72rem;display:flex;'
                    f'justify-content:space-between;padding:2px 0;">'
                    f'<span style="color:#8b949e;overflow:hidden;'
                    f'text-overflow:ellipsis;max-width:60%;">{mname}</span>'
                    f'<span style="color:#f0f6fc;font-weight:600;">'
                    f'{mtokens:,} <span style="color:#484f58;">({mpct}%)</span>'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )

