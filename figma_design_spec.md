# advanced-QODE — Figma Design Specification
**Frame:** `advanced-QODE · GenAI Assistant`  
**Version:** 1.0 · 2026-04-25  
**Designer handoff:** Import this file into Figma → create matching components → export tokens to `ui/theme.py`

---

## 1. Colour Palette

| Token | Hex | Usage |
|---|---|---|
| `bg-base` | `#0d1117` | Page background |
| `bg-surface` | `#161b22` | Card / panel surface |
| `bg-elevated` | `#1c2330` | Sidebar sections, elevated cards |
| `brand-blue` | `#3b82f6` | Primary CTA, focus rings, links |
| `brand-blue-dim` | `#1d4ed8` | Hover / pressed state |
| `accent-amber` | `#f59e0b` | As-Is mode badge, amber tint bubbles |
| `accent-emerald` | `#10b981` | Principles mode badge, LLM tint bubbles |
| `accent-violet` | `#8b5cf6` | Graph-RAG indicator, lens label |
| `accent-rose` | `#f43f5e` | Error state |
| `text-primary` | `#f0f6fc` | Headings, main body copy |
| `text-secondary` | `#8b949e` | Captions, sub-text |
| `text-muted` | `#484f58` | Placeholders, disabled |
| `border-default` | `#30363d` | Default borders |

---

## 2. Typography

| Style name | Font | Size | Weight | Usage |
|---|---|---|---|---|
| `Page Title` | Inter | 28px | 700 | `app.py` header H1 |
| `Section Title` | Inter | 12px | 700 | Sidebar section labels (uppercase) |
| `Card Title` | Inter | 14px | 600 | Diagram card header |
| `Body` | Inter | 15px | 400 | Chat bubble text |
| `Caption` | Inter | 12px | 400 | Mode badge, eval score, timestamps |
| `Code` | JetBrains Mono | 13px | 400 | DOT source blocks |

---

## 3. Component Library

### 3.1 Header Banner (`render_header`)
```
┌─────────────────────────────────────────────────────────────┐
│ ▬▬▬ gradient top border (blue → violet → emerald)           │
│                                                             │
│  🔷 advanced-QODE                                           │
│  GenAI Diagram Assistant                                    │
│  [📊 Graph-RAG] [🧠 LangGraph] [📡 Langfuse] [🔗 LlamaIndex]│
└─────────────────────────────────────────────────────────────┘
Background: linear-gradient(135deg, #0f172a → #1e293b → #0f172a)
Border: 1px solid border-default
Border-radius: 16px
```

### 3.2 Welcome Card (`render_welcome`)
```
┌──────────────────────────────────────────┐
│ 👋 Welcome to advanced-QODE              │
│ Subtitle text...                         │
│ ┌───────────────┐ ┌───────────────┐      │
│ │ 📊            │ │ 🧠            │      │
│ │ As-Is Mode    │ │ Principles    │      │
│ │ (amber)       │ │ Mode (green)  │      │
│ └───────────────┘ └───────────────┘      │
└──────────────────────────────────────────┘
Background: rgba(blue 8%) + rgba(violet 8%)
Border: 1px solid rgba(blue 20%)
```

### 3.3 Chat Bubbles

**User bubble** (right-aligned, 85% width)
```
                    ┌────────────────────────────┐
                    │ User message text here      │
                    └────────────────────────────┘
Background: linear-gradient(135deg, #1d4ed8 → #2563eb)
Border-radius: 16px 16px 6px 16px
```

**Assistant bubble — As-Is** (left-aligned)
```
┌──────────────────────────────────┐
▌ (amber left border 3px)          │
│ Diagram generated message        │
└──────────────────────────────────┘
Background: rgba(#451a03, 0.6)
Border-left: 3px solid #f59e0b
```

**Assistant bubble — Principles** (left-aligned)
```
┌──────────────────────────────────┐
▌ (emerald left border 3px)        │
│ LLM reasoning response           │
└──────────────────────────────────┘
Background: rgba(#052e16, 0.6)
Border-left: 3px solid #10b981
```

### 3.4 Mode Badge (`render_mode_badge`)
```
[📊 As-Is (no LLM)]              ← amber pill
[🧠 Principles (LLM + RAG)]      ← emerald pill
[❌ Error]                        ← rose pill

Height: 24px  |  Border-radius: 9999px  |  Font: 12px 600
```

### 3.5 Eval Score Bar (`render_eval_bar`)
```
Eval score: 87%  [████████░░]   ← gradient: rose → amber → emerald
Track height: 4px  |  max-width: 160px
```

### 3.6 Diagram Card (`render_diagram_card`)
```
┌──────────────────────────────────────────┐
│ 📐 PROCESS ARCHITECTURE DIAGRAM          │
│ ┌──────────────────────────────────────┐ │
│ │          [diagram image]             │ │
│ └──────────────────────────────────────┘ │
│  [⬇️ Download PNG]                        │
└──────────────────────────────────────────┘
Background: bg-surface  |  Border-radius: 16px
```

### 3.7 Info Card (`render_info_card`) — Sidebar
```
┌────────────────┐
│ MESSAGES       │  ← label: 11px uppercase muted
│ 12             │  ← value: 18px bold brand-blue
└────────────────┘
Background: bg-elevated  |  Border-radius: 10px
```

### 3.8 Sidebar Section Heading (`render_sidebar_section`)
```
UPLOAD DOCUMENTS   ← 11px, 700, uppercase, letter-spacing 0.1em, muted color
────────────────
```

---

## 4. Layout Grid

```
┌─────────────────────────────────────────────────────────────────┐
│  SIDEBAR (280px fixed)           │  MAIN CONTENT (fluid)        │
│                                  │                              │
│  Brand mark                      │  Header banner               │
│  ── Session stats ──             │                              │
│  File uploader                   │  [Welcome card — first run]  │
│  ── Engineering Principles ──    │                              │
│  Principle selectbox             │  Chat history                │
│  Discipline radio                │  ┌─ user bubble ───────────┐ │
│  ── As-Is Diagrams ──            │  └────────────────────────┘ │
│  [Process] [People] [Tech]       │  ┌─ assistant bubble ──────┐ │
│  ── Conversation ──              │  │  [mode badge]           │ │
│  [Clear chat]                    │  │  [eval bar]             │ │
│  ── Example Prompts ──           │  │  [diagram card]         │ │
│  › Example 1                     │  └────────────────────────┘ │
│  › Example 2                     │                              │
│                                  │  [Chat input bar]            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Streamlit ↔ Figma Component Mapping

| Figma component | Streamlit implementation | File |
|---|---|---|
| `Header/Banner` | `render_header()` | `ui/components.py` |
| `Chat/WelcomeCard` | `render_welcome()` | `ui/components.py` |
| `Chat/UserBubble` | `render_user_bubble()` | `ui/components.py` |
| `Chat/AssistantBubble` | `render_assistant_bubble()` | `ui/components.py` |
| `Badge/Mode` | `render_mode_badge()` | `ui/components.py` |
| `EvalBar` | `render_eval_bar()` | `ui/components.py` |
| `DiagramCard` | `render_diagram_card()` | `ui/components.py` |
| `Sidebar/InfoCard` | `render_info_card()` | `ui/components.py` |
| `Sidebar/SectionLabel` | `render_sidebar_section()` | `ui/components.py` |
| `Sidebar/FileUpload` | `st.file_uploader()` + custom CSS | `ui/styles.css` |
| `Sidebar/PrincipleSelect` | `st.selectbox()` + custom CSS | `ui/styles.css` |
| `Sidebar/DisciplineRadio` | `st.radio()` + custom CSS | `ui/styles.css` |
| `Sidebar/QuickButtons` | `st.button()` × 3 + custom CSS | `ui/styles.css` |
| `ChatInput` | `st.chat_input()` + custom CSS | `ui/styles.css` |

---

## 6. Figma Import Instructions

1. Open Figma → New file → Import the following tokens as **local styles**:
   - Copy colour tokens from `ui/theme.py → COLORS` → paste into Figma Colour styles
   - Copy typography tokens from `ui/theme.py → TYPOGRAPHY` → paste into Text styles

2. Build components top-down: Header → Sidebar → ChatBubble (×3 variants) → DiagramCard

3. Use **Auto Layout** with these gap values (from `ui/theme.py → SPACING`):
   - Component inner padding: `16px`
   - Section gap: `8px`
   - Card gap: `12px`

4. Use **Figma Dev Mode** to export CSS variables — they map 1:1 to `ui/styles.css` custom properties.

5. To import a Lucidchart diagram: File → Import → Visio / DOT → paste the DOT source output from the app.

---

## 7. How to Run

```bash
# 1. Install dependencies
pip install -r requirements_rag.txt

# 2. Set API keys
cp .env.example .env
# Edit .env → set KODEKLOUD_API_KEY (and optionally LANGFUSE_* keys)

# 3. Launch
bash run.sh
# or directly:
streamlit run app.py --server.port 8501
```
