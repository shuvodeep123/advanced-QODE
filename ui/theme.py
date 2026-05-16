"""
ui/theme.py — Figma design tokens for advanced-QODE.

These constants mirror the Figma design file:
  Frame: "advanced-QODE · GenAI Assistant"
  Version: 1.0  |  Last updated: 2026-04-25

Design philosophy:
  - Dark-first professional palette (DevSecOps / engineering tool aesthetic)
  - Electric-blue primary accent — signals AI / intelligence
  - Amber warning for As-Is path (deterministic, no LLM)
  - Emerald success for principles path (LLM+RAG)
  - Inter typeface throughout (closest web equivalent to Figma default)
"""

# ---------------------------------------------------------------------------
# Colour palette  (Figma → CSS custom properties)
# ---------------------------------------------------------------------------
COLORS = {
    # ── Backgrounds ──────────────────────────────────────────────────────
    "bg_base":        "#0d1117",   # Page background
    "bg_surface":     "#161b22",   # Card / panel surface
    "bg_elevated":    "#1c2330",   # Elevated elements (sidebar sections)
    "bg_input":       "#0d1117",   # Input fields

    # ── Brand / Primary ──────────────────────────────────────────────────
    "brand_blue":     "#3b82f6",   # Primary action — electric blue
    "brand_blue_dim": "#1d4ed8",   # Hover / pressed state
    "brand_glow":     "rgba(59,130,246,0.15)",  # Glow effect on focus

    # ── Accent states ────────────────────────────────────────────────────
    "accent_amber":   "#f59e0b",   # As-Is mode badge (deterministic)
    "accent_emerald": "#10b981",   # Principles mode badge (LLM)
    "accent_rose":    "#f43f5e",   # Error / warning
    "accent_violet":  "#8b5cf6",   # Graph-RAG indicator

    # ── Text ─────────────────────────────────────────────────────────────
    "text_primary":   "#f0f6fc",   # Headings, main copy
    "text_secondary": "#8b949e",   # Captions, sub-text
    "text_muted":     "#484f58",   # Placeholder, disabled

    # ── Borders ──────────────────────────────────────────────────────────
    "border_default": "#30363d",   # Default borders
    "border_focus":   "#3b82f6",   # Focus ring

    # ── Chat bubbles ─────────────────────────────────────────────────────
    "bubble_user":    "#1d4ed8",   # User message background
    "bubble_ai":      "#1c2330",   # Assistant message background
    "bubble_asis":    "#451a03",   # As-Is path response (amber tint)
    "bubble_llm":     "#052e16",   # Principles path response (emerald tint)
}

# ---------------------------------------------------------------------------
# Typography  (Figma text styles)
# ---------------------------------------------------------------------------
TYPOGRAPHY = {
    "font_family":    "'Inter', 'Segoe UI', system-ui, sans-serif",
    "font_mono":      "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",

    # Scale (rem)
    "size_xs":   "0.75rem",   # 12px — captions, badges
    "size_sm":   "0.875rem",  # 14px — body small
    "size_base":  "1rem",     # 16px — body
    "size_lg":   "1.125rem",  # 18px — lead
    "size_xl":   "1.25rem",   # 20px — card titles
    "size_2xl":  "1.5rem",    # 24px — section headings
    "size_3xl":  "1.875rem",  # 30px — page title

    # Weights
    "weight_normal": "400",
    "weight_medium": "500",
    "weight_semibold": "600",
    "weight_bold": "700",
}

# ---------------------------------------------------------------------------
# Spacing  (Figma auto-layout gap / padding)
# ---------------------------------------------------------------------------
SPACING = {
    "xs":  "4px",
    "sm":  "8px",
    "md":  "16px",
    "lg":  "24px",
    "xl":  "32px",
    "2xl": "48px",
}

# ---------------------------------------------------------------------------
# Border radius
# ---------------------------------------------------------------------------
RADIUS = {
    "sm":   "6px",
    "md":   "10px",
    "lg":   "16px",
    "full": "9999px",
}

# ---------------------------------------------------------------------------
# Shadow / elevation
# ---------------------------------------------------------------------------
SHADOWS = {
    "card":   "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)",
    "raised": "0 4px 12px rgba(0,0,0,0.5)",
    "glow":   "0 0 20px rgba(59,130,246,0.25)",
}

# ---------------------------------------------------------------------------
# Mode badge config  (used by components.py)
# ---------------------------------------------------------------------------
MODE_CONFIG = {
    "asis": {
        "label":  "📊 As-Is  (no LLM)",
        "color":  COLORS["accent_amber"],
        "bg":     "rgba(245,158,11,0.12)",
        "border": "rgba(245,158,11,0.35)",
        "bubble_bg": COLORS["bubble_asis"],
    },
    "principles": {
        "label":  "🧠 Principles  (LLM + RAG)",
        "color":  COLORS["accent_emerald"],
        "bg":     "rgba(16,185,129,0.12)",
        "border": "rgba(16,185,129,0.35)",
        "bubble_bg": COLORS["bubble_llm"],
    },
    "error": {
        "label":  "❌ Error",
        "color":  COLORS["accent_rose"],
        "bg":     "rgba(244,63,94,0.12)",
        "border": "rgba(244,63,94,0.35)",
        "bubble_bg": COLORS["bg_elevated"],
    },
}

# ---------------------------------------------------------------------------
# Streamlit page_config kwargs  (import and spread into st.set_page_config)
# ---------------------------------------------------------------------------
PAGE_CONFIG = {
    "page_title": "advanced-QODE — GenAI Diagram Assistant",
    "page_icon":  "🔷",
    "layout":     "wide",
    "initial_sidebar_state": "expanded",
    "menu_items": {
        "Get Help": "https://github.com/shuvodeep123/advanced-QODE",
        "Report a bug": "https://github.com/shuvodeep123/advanced-QODE/issues",
        "About": "**advanced-QODE** · Gen-AI based DevOps Assesment Specialist\n\n",
    },
}
