"""
chain.py — LangGraph-based agentic router for advanced-QODE.

Two execution paths
-------------------
  1. **As-Is Architecture path** (no LLM)
     Triggered by: "create as-is", "generate as-is", "show as-is" etc.
     Flow: intent detection → RAG retrieval → diagram generator (Python files) → return

  2. **Engineering Principles path** (LLM + Graph-RAG)
     Triggered by: any modification / improvement / analysis request.
     Flow: intent detection → principle/discipline extraction → hybrid Graph-RAG
           retrieval → Langfuse-traced LLM call → eval scoring → return

Public API
----------
    run_chain(...) -> dict
    detect_intent(query) -> str          # "process" | "people" | "technology" | "general"
    detect_asis_request(query) -> bool   # True when user wants As-Is diagram
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterator, TypedDict

from pathlib import Path as _Path

from .graph_builder import DEFAULT_GRAPH_PATH
from .graph_retriever import get_retriever
from .diagram_executor import run as run_diagram, get_dot_path, TOBE_DIRS, dot_to_drawio
from .principles_engine import PrinciplesEngine, extract_principle_context
from .langfuse_tracer import get_tracer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent patterns
# ---------------------------------------------------------------------------
_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "people",
        [   
            "people", "team", "role", "stakeholder", "collaboration",
            "ownership", "owner", "resource", "who", "personnel",
            "target people", "people architecture", "people diagram",
        ],
    ),
    (
        "technology",
        [
            "technology", "tool", "automation", "toolchain", "integration",
            "platform", "software", "ci/cd", "pipeline tool", "devops tool",
            "technology diagram", "tech diagram", "target technology",
        ],
    ),
    (
        "process",
        [
            "process", "network", "flow", "critical path", "time to market",
            "bottleneck", "lead time", "cycle time", "sdlc", "workflow",
            "process diagram", "process network", "target process",
        ],
    ),
]

# Keywords that trigger As-Is diagram generation WITHOUT an LLM call
_ASIS_KEYWORDS = [
    "as-is", "as is", "asis", "current state", "existing",
    "create", "generate", "build", "produce", "make", "draw",
    "show", "render", "display", "visualise", "visualize", "diagram",
]

# Keywords that trigger diagram generation in the principles path too
_GENERATE_KEYWORDS = [
    "create", "generate", "build", "produce", "make", "draw",
    "show", "render", "display", "visualise", "visualize", "diagram",
]

# Keywords that indicate gap / impact analysis (removing a pillar or component)
_REMOVE_KEYWORDS = [
    "remove", "removed", "removing", "without", "exclude", "drop",
    "eliminate", "if we remove", "if removed", "not present",
]
_IMPACT_KEYWORDS = [
    "impact", "effect", "consequence", "risk", "dependency", "depends",
    "breakdown", "failure", "gap", "what would happen", "what happens",
]


def detect_gap_analysis_request(query: str) -> bool:
    """Return True when the user wants gap/impact analysis of removing components."""
    lower = query.lower()
    has_remove = any(kw in lower for kw in _REMOVE_KEYWORDS)
    has_impact = any(kw in lower for kw in _IMPACT_KEYWORDS)
    return (
        (has_remove and has_impact)
        or "gap analysis" in lower
        or "impact analysis" in lower
    )


def _extract_removed_items(query: str) -> list[str]:
    """Extract component / pillar names the user wants to remove.

    Recognises patterns like:
    - "remove X"  / "removing X"  / "without X"  / "if X is removed"
    - "impact of removing X from ..."
    """
    lower = query.lower()
    items: list[str] = []
    patterns = [
        r"(?:remove|removing|without|exclude|drop|eliminat\w*)\s+([\w\s/,&-]+?)"
        r"(?:\s+(?:from|in|pillar|component)|\s*[,.]|$)",
        r"if\s+([\w\s/,&-]+?)\s+(?:is|are|were)\s+removed",
        r"impact\s+of\s+removing\s+([\w\s/,&-]+?)(?:\s+from|\s*[,.]|$)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, lower):
            raw = m.group(1).strip()
            parts = re.split(r"\s*(?:and|or|,)\s*", raw)
            items.extend(p.strip() for p in parts if len(p.strip()) > 2)

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def detect_intent(query: str) -> str:
    """Return 'process', 'people', 'technology', or 'general'."""
    lower = query.lower()
    scores: dict[str, int] = {"process": 0, "people": 0, "technology": 0}
    for intent, keywords in _INTENT_PATTERNS:
        for kw in keywords:
            if kw in lower:
                scores[intent] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "general"


_TOBE_KEYWORDS = ["to-be", "to be", "tobe", "target state", "future state", "target architecture"]


def detect_asis_request(query: str) -> bool:
    """Return True when the query is asking for an As-Is architecture diagram.

    Explicitly returns False for To-Be requests even if generate keywords present,
    since To-Be always routes through the LLM path.
    """
    lower = query.lower()
    # To-Be always takes LLM path — never As-Is
    if any(kw in lower for kw in _TOBE_KEYWORDS):
        return False
    return any(kw in lower for kw in _ASIS_KEYWORDS)


# Keywords that indicate a narrative/planning follow-up (document-worthy response)
_NARRATIVE_KEYWORDS = [
    "30-60-90", "30 60 90", "roadmap", "plan",
    "what improvements", "improvement", "recommendation",
    "assessment", "maturity", "report", "summary",
    "strategy", "assess", "review", "across all",
    "all engineering", "all principles",
]
_DIAGRAM_NOUN_KEYWORDS = ["diagram", "chart", "flowchart", "architecture"]


def detect_narrative_request(query: str) -> bool:
    """Return True for analysis/planning questions that warrant document generation.

    These are follow-up questions (not diagram requests) that produce structured
    narrative output — e.g. 'What improvements are required in Technology Disciplines
    across all engineering principles?' or 'Create a 30-60-90 days plan'.
    """
    lower = query.lower()
    has_narrative = any(kw in lower for kw in _NARRATIVE_KEYWORDS)
    has_diagram   = any(kw in lower for kw in _DIAGRAM_NOUN_KEYWORDS)
    return has_narrative and not has_diagram


def _wants_diagram(query: str) -> bool:
    lower = query.lower()
    return any(kw in lower for kw in _GENERATE_KEYWORDS)


# ---------------------------------------------------------------------------
# LangGraph state schema
# ---------------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    user_message: str
    history: list[dict]
    excel_path: str | None
    chroma_path: str
    graph_path: str
    stream: bool
    # routing
    intent: str
    is_asis: bool
    principle_ctx: dict
    # retrieval
    context_chunks: list[dict]
    # As-Is ground truth — loaded before any LLM call to prevent hallucination
    asis_diagram_data: str | None   # raw DOT text from the questionnaire generator
    # gap / impact analysis
    is_gap_analysis: bool           # True when user wants pillar removal impact analysis
    gap_items: list[str]            # pillar / component names to be "removed"
    # output
    diagram_path: str | None
    tobe_dot_path: str | None   # Graphviz DOT for To-Be diagram (from LLM)
    diagram_type: str | None
    reply_text: str
    thinking_text: str          # content of <think>…</think> block (may be empty)
    reply_stream: Iterator[str] | None
    mode: str            # "asis" | "principles"
    eval_score: float | None
    error: str | None


# ---------------------------------------------------------------------------
# Node functions — each takes/returns AgentState
# ---------------------------------------------------------------------------

def _node_route(state: AgentState) -> AgentState:
    """Classify intent and decide which path to take.

    Both As-Is and To-Be diagram requests now go through the LLM path
    (load_asis → principles).  As-Is requests keep ``is_asis=True`` so
    ``_node_principles`` knows to produce an analysis of the current state
    rather than a To-Be diagram.
    """
    query = state["user_message"]
    state["intent"] = detect_intent(query)
    state["is_asis"] = detect_asis_request(query)
    state["principle_ctx"] = extract_principle_context(query)
    state["is_gap_analysis"] = detect_gap_analysis_request(query)
    state["gap_items"] = _extract_removed_items(query) if state["is_gap_analysis"] else []
    # Gap analysis always takes the LLM path
    if state["is_gap_analysis"]:
        state["is_asis"] = False
    return state


def _node_load_asis(state: AgentState) -> AgentState:
    """Pre-load As-Is architecture data to ground every LLM call.

    Runs the diagram generator for the detected intent, reads the raw DOT text
    from the questionnaire, and stores it in ``state['asis_diagram_data']``.
    The LLM in ``_node_principles`` receives this as verified ground truth.
    Also captures the rendered diagram path so the UI can display it.
    """
    intent = state["intent"]

    if intent == "general":
        state["asis_diagram_data"] = None
        state["diagram_path"] = None
        state["diagram_type"] = None
        return state

    tracer = get_tracer()
    with tracer.trace("load_asis_ground_truth", input={"intent": intent}):
        diagram_path: str | None = None
        try:
            diagram_path = run_diagram(
                diagram_type=intent,
                excel_path=state.get("excel_path"),
            )
        except Exception as exc:
            logger.warning("As-Is diagram render failed: %s", exc)

        if diagram_path and not _Path(diagram_path).exists():
            logger.warning("As-Is diagram file not found at '%s' — proceeding without it.", diagram_path)
            diagram_path = None

        state["diagram_path"] = diagram_path
        state["diagram_type"] = intent

        dot_file = get_dot_path(intent)
        if dot_file and dot_file.exists():
            state["asis_diagram_data"] = dot_file.read_text(encoding="utf-8", errors="replace")
            logger.info("As-Is ground truth loaded (%d chars) for intent '%s'.",
                        len(state["asis_diagram_data"]), intent)
        else:
            state["asis_diagram_data"] = None
            logger.warning(
                "As-Is DOT file not found for intent '%s'. "
                "LLM will lack questionnaire ground truth — responses may be less accurate.",
                intent,
            )

    return state


def _extract_mermaid(text: str) -> str | None:
    """Extract the first Mermaid diagram from an LLM reply text.

    Looks for a fenced ```mermaid … ``` block first, then falls back to
    an un-fenced ``flowchart`` or ``graph`` declaration.
    Returns the raw Mermaid source (without the fence lines), or None.
    """
    m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"((?:flowchart|graph)\s+(?:TD|LR|BT|RL)\b.*)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def _extract_dot(text: str) -> str | None:
    """Extract the first Graphviz DOT graph from an LLM reply text.

    Looks for a fenced ```dot … ``` block first, then falls back to
    a bare ``digraph`` / ``graph`` declaration.
    Returns the raw DOT source (without the fence lines), or None.
    """
    m = re.search(r"```dot\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"((?:di)?graph\s+\w*\s*\{.*?\}\s*)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def _node_principles(state: AgentState) -> AgentState:
    """Engineering Principles path: Graph-RAG + LLM with Langfuse tracing.

    Handles three sub-modes:
    - ``is_asis=True``        : As-Is analysis — explain + assess current state
    - ``is_gap_analysis=True``: Gap analysis  — impact of removing components
    - default                 : To-Be          — recommend target-state improvements
    """
    from . import llm_client  # lazy import to keep As-Is path LLM-free

    intent = state["intent"]
    tracer = get_tracer()

    # ── Retrieval ─────────────────────────────────────────────────────────
    with tracer.trace("graph_rag_retrieval", input={"intent": intent, "query": state["user_message"]}):
        retriever = get_retriever(
            graph_path=state["graph_path"],
            chroma_path=state["chroma_path"],
        )
        chunks = retriever.retrieve(
            query=state["user_message"],
            k=6,
            diagram_type=intent if intent != "general" else None,
            graph_hops=2,
        )
        state["context_chunks"] = chunks

    # diagram_path / diagram_type already set by _node_load_asis — do not overwrite
    state["mode"] = "principles"

    # ── Build messages — inject verified As-Is data + optional gap analysis ──
    messages = _build_messages(
        user_message=state["user_message"],
        history=state.get("history", []),
        context_chunks=chunks,
        principle_ctx=state.get("principle_ctx", {}),
        asis_diagram_data=state.get("asis_diagram_data"),
        gap_items=state.get("gap_items"),
        is_asis=state.get("is_asis", False),
    )

    # ── LLM call with Langfuse tracing ────────────────────────────────────
    with tracer.trace(
        "llm_generation",
        input={"messages_count": len(messages), "intent": intent},
    ) as span:
        try:
            if state.get("stream"):
                state["reply_stream"] = llm_client.chat_stream(messages)
                state["reply_text"] = ""
                state["thinking_text"] = ""
            else:
                raw_reply = llm_client.chat(messages)
                thinking, clean = llm_client._extract_thinking(raw_reply or "")
                state["reply_text"] = clean
                state["thinking_text"] = thinking
                state["reply_stream"] = None
            span.set_output({"status": "ok"})
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            state["reply_text"] = f"❌ LLM error: {exc}"
            state["thinking_text"] = ""
            state["reply_stream"] = None
            state["error"] = str(exc)
            span.set_output({"status": "error", "error": str(exc)})

    # ── Extract and persist Mermaid + DOT + draw.io from LLM reply ────────
    # For To-Be / gap-analysis requests extract both formats from the LLM response
    # and save them into the structured TO-BE/ output directories.
    # diagram_path is overwritten with the To-Be path for non-as-is requests.
    if (
        not state.get("is_asis")
        and (_wants_diagram(state["user_message"]) or state.get("is_gap_analysis"))
        and not state.get("stream")
        and state.get("reply_text")
    ):
        reply_text  = state["reply_text"]
        intent_key  = state.get("intent", "general")
        is_gap      = state.get("is_gap_analysis", False)
        stem_suffix = "_gap" if is_gap else ""
        # Base filename: e.g. "process_tobe", "people_tobe", "technology_gap"
        base_name   = f"{intent_key}{stem_suffix}"
        dot_ref     = get_dot_path(intent_key) if intent_key != "general" else None

        # ── Mermaid → TO-BE/Mermaid/ ─────────────────────────────────────
        mermaid_src = _extract_mermaid(reply_text)
        if mermaid_src:
            tobe_mmd = TOBE_DIRS["mermaid"] / f"{base_name}.mmd"
            try:
                tobe_mmd.write_text(mermaid_src, encoding="utf-8")
                state["diagram_path"] = str(tobe_mmd)
                state["diagram_type"] = intent_key
                logger.info("%s Mermaid saved: %s (%d chars)",
                            "Gap" if is_gap else "To-Be", tobe_mmd, len(mermaid_src))
                # Legacy root copy (keeps backward compat with render_diagram_card)
                if dot_ref:
                    try:
                        legacy = dot_ref.parent / f"{dot_ref.stem}{'_gap' if is_gap else '_tobe'}.mmd"
                        legacy.write_text(mermaid_src, encoding="utf-8")
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("Could not save To-Be Mermaid: %s", e)
        else:
            logger.warning("LLM reply contained no Mermaid block for '%s' request.", intent_key)

        # ── DOT → TO-BE/DotGraph/ ────────────────────────────────────────
        dot_src = _extract_dot(reply_text)
        if dot_src:
            tobe_dot = TOBE_DIRS["dot"] / f"{base_name}.dot"
            try:
                tobe_dot.write_text(dot_src, encoding="utf-8")
                state["tobe_dot_path"] = str(tobe_dot)
                logger.info("To-Be DOT saved: %s (%d chars)", tobe_dot, len(dot_src))
                # ── draw.io → TO-BE/draw.io/ (derived from LLM DOT) ──────
                try:
                    drawio_text = dot_to_drawio(dot_src, intent_key)
                    tobe_drawio = TOBE_DIRS["drawio"] / f"{base_name}.drawio"
                    tobe_drawio.write_text(drawio_text, encoding="utf-8")
                    logger.info("To-Be draw.io saved: %s", tobe_drawio)
                except Exception as de:
                    logger.warning("Could not generate To-Be draw.io: %s", de)
            except Exception as e:
                logger.warning("Could not save To-Be DOT: %s", e)

    # ── Eval scoring (async, non-blocking) ────────────────────────────────
    try:
        from .eval_metrics import score_response
        if not state.get("stream") and state.get("reply_text"):
            context_text = "\n".join(c["text"] for c in chunks)
            state["eval_score"] = score_response(
                query=state["user_message"],
                answer=state["reply_text"],
                context=context_text,
            )
            tracer.log_score("faithfulness", state["eval_score"])
    except Exception:
        state["eval_score"] = None

    return state


# ---------------------------------------------------------------------------
# LangGraph wiring
# ---------------------------------------------------------------------------

def _build_graph():
    """Build the LangGraph StateGraph. Returns a compiled graph."""
    try:
        from langgraph.graph import StateGraph, END  # type: ignore[import]

        builder = StateGraph(AgentState)
        builder.add_node("route",      _node_route)
        builder.add_node("load_asis",  _node_load_asis)   # grounding step before LLM
        builder.add_node("principles", _node_principles)

        builder.set_entry_point("route")
        # Both As-Is and To-Be now go through load_asis → principles so the LLM
        # always has verified ground-truth data and Graph-RAG context.
        builder.add_edge("route",      "load_asis")
        builder.add_edge("load_asis",  "principles")
        builder.add_edge("principles", END)
        return builder.compile()
    except ImportError:
        return None  # Fallback to direct function calls if langgraph not installed


_COMPILED_GRAPH = _build_graph()


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert DevSecOps consultant specializing in the advanced-QODE framework \
(Quality & Optimization of DevSecOps Engineering). advanced-QODE assesses DevSecOps \
maturity across 9 Engineering Principles:

  1. Requirement Engineering   2. Code / Data Engineering   3. Quality Engineering
  4. Build & Release Engg      5. Environment Engineering   6. Service Ops
  7. Security                  8. Reliability               9. Ontology Engineering

Each principle spans 3 core disciplines:  (a) People  (b) Process  (c) Technology

You have access to a **QODE Knowledge Graph** providing structural multi-hop reasoning \
over pillars, roles, tools, and activities.

## Anti-Hallucination Rules (MANDATORY)
- **As-Is Architecture Ground Truth**: When the section \
  "As-Is Architecture — Verified Ground Truth" is present in your context, it contains \
  the ONLY authoritative description of the current-state architecture, extracted directly \
  from the client's QODE questionnaire.  You MUST treat it as the sole source of truth. \
  Never assume, invent, or infer any roles, tools, processes, or relationships \
  that are not explicitly present in that section.
- **To-Be recommendations with questionnaire data**: derive all recommendations \
  exclusively from the verified As-Is data, the Knowledge Graph, and Semantic Context.
- **To-Be recommendations without questionnaire data**: you MUST still produce a \
  comprehensive, fully-specified To-Be architecture.  Use the QODE Knowledge Graph context, \
  the 9 Engineering Principles × 3 Disciplines framework, and DevSecOps best practices to \
  reason through a logical target-state architecture.  Clearly label it as \
  "Best-Practice To-Be Architecture (QODE Framework)" so it is distinguished from \
  client-specific output.  **Refusing to generate a diagram is not acceptable.**
- Never invent facts that contradict the verified As-Is data when it is present.

## Diagram Output Format (MANDATORY — BOTH formats required for every diagram request)
- Emit a **Graphviz DOT graph** inside a fenced block: \`\`\`dot digraph G { … } \`\`\`
- Emit a **Mermaid flowchart** inside a fenced block: \`\`\`mermaid flowchart … \`\`\`
- **Both blocks are REQUIRED** — do NOT emit only one format. Output DOT first, then Mermaid.
- Do NOT describe the diagram only in prose — render both formats.
- Include labelled nodes for every key role / tool / process in the architecture.
- DOT direction: `rankdir=TD` for People/Process; `rankdir=LR` for Technology.
- Mermaid direction: `flowchart TD` for People/Process; `flowchart LR` for Technology.
- For a **People** diagram: actor nodes → responsibility / ownership arrows.
- For a **Process** diagram: activity nodes → sequence / dependency arrows, \
  annotate critical-path edges.
- For a **Technology** diagram: tool/platform nodes → integration / data-flow arrows.

## To-Be Diagram Derivation (MANDATORY when As-Is data is present)
When producing a To-Be diagram you MUST:
1. Start from the exact nodes and edges in the verified As-Is DOT graph.
2. Classify each node: **KEPT** (unchanged), **IMPROVED** (enhanced), \
   **REPLACED** (swapped for better tool/role), or **NEW** (not in As-Is).
3. In the **DOT graph** colour-code with `style=filled`:
   - NEW → `fillcolor="#34d399"`  IMPROVED → `fillcolor="#60a5fa"`
   - REPLACED/REMOVED → `fillcolor="#f87171"`  KEPT → default
4. In the **Mermaid diagram** add classDef at the end:
   `classDef kept fill:#1e3a5f,stroke:#3b82f6,color:#e0e7ff`
   `classDef improved fill:#1d4ed8,stroke:#60a5fa,color:#fff`
   `classDef new fill:#065f46,stroke:#34d399,color:#fff`
   `classDef replaced fill:#7f1d1d,stroke:#f87171,color:#fff`
   Apply with `class NodeId improved` / `class NodeId new` / etc.
5. Add a short **Legend** section after both diagrams.

Your responsibilities:
- When a user asks for IMPROVEMENTS, ANALYSIS, or a TO-BE diagram → reason across the \
  relevant Engineering Principle × Discipline intersection using the provided context, \
  then emit BOTH DOT and Mermaid diagrams.
- Prefer the **Knowledge Graph Context** (graph traversal) over Semantic Context \
  for relationship/structural questions.
- Ground every answer in the retrieved context. Be concise and actionable.
"""


def _build_messages(
    user_message: str,
    history: list[dict],
    context_chunks: list[dict],
    principle_ctx: dict | None = None,
    asis_diagram_data: str | None = None,
    gap_items: list[str] | None = None,
    is_asis: bool = False,
) -> list[dict]:
    graph_chunks = [c for c in context_chunks if c.get("source") == "graph"]
    vector_chunks = [c for c in context_chunks if c.get("source") != "graph"]

    system_content = _SYSTEM_PROMPT

    # Inject principle/discipline context if present
    if principle_ctx and (principle_ctx.get("principle") or principle_ctx.get("discipline")):
        system_content += (
            f"\n\n---\n## Active Engineering Lens\n\n"
            f"Principle: **{principle_ctx.get('principle', 'General')}**  |  "
            f"Discipline: **{principle_ctx.get('discipline', 'All')}**\n\n"
            "Prioritise your reasoning through this lens."
        )

    if graph_chunks:
        system_content += (
            "\n\n---\n## Knowledge Graph Context\n\n"
            "(Structural relationships via multi-hop graph traversal — "
            "prefer this for role/tool/pillar questions.)\n\n"
            + "\n\n".join(c["text"] for c in graph_chunks)
        )

    if vector_chunks:
        system_content += (
            "\n\n---\n## Semantic Context\n\n"
            "(Retrieved by vector similarity — for descriptive and long-tail questions.)\n\n"
            + "\n\n".join(
                f"[{i + 1}] {c['text']}" for i, c in enumerate(vector_chunks)
            )
        )

    # ── As-Is ground truth ── injected LAST so it is closest to the user turn
    if asis_diagram_data:
        if is_asis:
            # As-Is analysis mode: explain + assess current state, no To-Be diagram
            system_content += (
                "\n\n---\n## ⚠️ As-Is Architecture — Verified Ground Truth\n\n"
                "The following DOT graph is the **verified current-state architecture** "
                "extracted directly from the client's QODE questionnaire.\n\n"
                "```dot\n"
                + asis_diagram_data
                + "\n```\n\n"
                "## 📊 As-Is Analysis Mode — ACTIVE\n\n"
                "The diagram has already been rendered by the QODE diagram engine.\n"
                "**Your role**: Provide a structured analysis of the current-state architecture above.\n"
                "Structure your response as:\n"
                "1. **Architecture Summary** — what the current state looks like\n"
                "2. **Key Components** — list all roles / tools / processes found\n"
                "3. **Strengths** — what is working well\n"
                "4. **Gaps & Areas for Attention** — missing capabilities or improvement areas\n"
                "5. **Quick Wins** — 2–3 immediate improvements with low effort / high impact\n\n"
                "**Do NOT generate a new Mermaid diagram.** "
                "Provide structured analysis in well-formatted prose."
            )
        else:
            system_content += (
                "\n\n---\n## ⚠️ As-Is Architecture — Verified Ground Truth\n\n"
                "The following DOT graph is the **verified current-state architecture** "
                "extracted directly from the client's QODE questionnaire.\n"
                "**Base ALL To-Be recommendations on this exact data. "
                "Do NOT invent roles, tools, or processes absent from it.**\n\n"
                "```dot\n"
                + asis_diagram_data
                + "\n```\n\n"
                "## \U0001f52e To-Be Generation Instructions\n\n"
                "You MUST produce **both** a DOT graph (```dot\u2026```) and a Mermaid "
                "flowchart (```mermaid\u2026```) for the To-Be architecture:\n\n"
                "1. Parse every node and edge from the As-Is DOT above.\n"
                "2. Classify each node as **KEPT**, **IMPROVED**, **REPLACED**, or **NEW**.\n"
                "3. DOT block: colour-code with `style=filled fillcolor=\"#34d399\"` (NEW), "
                "`fillcolor=\"#60a5fa\"` (IMPROVED), `fillcolor=\"#f87171\"` (REPLACED).\n"
                "4. Mermaid block: apply classDef `new`, `improved`, `replaced`, `kept`.\n"
                "5. Both blocks are MANDATORY \u2014 output DOT first, then Mermaid.\n"
            )
    else:
        if is_asis:
            system_content += (
                "\n\n---\n## 📊 As-Is Analysis Mode — No Questionnaire Loaded\n\n"
                "No client questionnaire has been uploaded. Provide a general best-practice "
                "analysis of what a mature current-state architecture looks like for the "
                "requested discipline, based on the QODE Knowledge Graph Context above.\n"
                "Structure your response with: Summary, Key Components, Strengths, Gaps, Quick Wins.\n"
                "**Do NOT generate a Mermaid diagram.**"
            )
        else:
            system_content += (
                "\n\n---\n## 📋 As-Is Architecture — Not Loaded (Best-Practice Mode)\n\n"
                "No client questionnaire has been loaded for this session.\n"
                "**You MUST NOT refuse to generate a To-Be diagram.**  "
                "Proceed as follows:\n\n"
                "1. Use the **QODE Knowledge Graph Context** above (pillars, roles, tools, "
                "activities) as the source of structural best practices.\n"
                "2. Apply the **9 Engineering Principles × 3 Disciplines** framework to reason "
                "through what a mature, modern To-Be architecture looks like for the requested domain.\n"
                "3. Produce a comprehensive To-Be architecture recommendation.\n"
                "4. **Mandatory**: Output BOTH a DOT graph (```dot\u2026```) AND a Mermaid "
                "flowchart (```mermaid\u2026```) showing the recommended target-state "
                "architecture with nodes for key roles / tools / processes and labelled arrows.\n"
                "5. Label your output: **Best-Practice To-Be Architecture (QODE Framework)** "
                "— based on QODE principles, not a specific client questionnaire."
            )

    messages: list[dict] = [{"role": "system", "content": system_content}]
    # ── Gap analysis overlay ─────────────────────────────────────────────

    if gap_items:
        removed_str = ", ".join(f"’{item}’" for item in gap_items)
        gap_sys = (
            f"## 🔴 Gap Analysis Mode — ACTIVE\n\n"
            f"The user wants to understand the impact of **removing**: {removed_str}\n\n"
            "You MUST structure your response as follows:\n\n"
            "### 1. Impact Analysis Table\n"
            "| Removed Component | Direct Impacts | Indirect Impacts | Risk Level |\n"
            "|---|---|---|---|\n"
            "(fill one row per removed component)\n\n"
            "### 2. Regenerated To-Be Diagram with Gap Highlighting\n"
            "Emit a complete `mermaid` flowchart block with these mandatory style classes:\n"
            "```\n"
            "classDef gap  fill:#ef4444,stroke:#991b1b,color:#fff\n"
            "classDef risk fill:#f97316,stroke:#c2410c,color:#fff\n"
            "classDef warn fill:#eab308,stroke:#a16207,color:#000\n"
            "```\n"
            "Apply them with `class NodeId gap` / `class NodeId risk` / `class NodeId warn` lines.\n"
            "  - 🔴 **gap** (red) — the removed nodes themselves\n"
            "  - 🟠 **risk** (orange) — nodes with a direct dependency on removed nodes\n"
            "  - 🟡 **warn** (yellow) — nodes with indirect / downstream effects\n"
            "  - Default style — fully unaffected nodes\n\n"
            "### 3. Mitigation Recommendations\n"
            "For each High-risk gap, provide one or two concrete, actionable mitigations."
        )
        messages.append({"role": "system", "content": gap_sys})
    # ── Inject conversation history ──────────────────────────────────────
    # Pass all turns in the session (up to 40 messages = ~20 exchanges) so
    # the LLM retains full context throughout the session.
    # Messages are sanitized to only {role, content} — extra keys like
    # diagram_path, tobe_dot_path, eval_score must NOT reach the LLM API.
    for turn in history[-40:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_chain(
    user_message: str,
    history: list[dict] | None = None,
    excel_path: str | None = None,
    chroma_path: str = "./chroma_db",
    graph_path: str = DEFAULT_GRAPH_PATH,
    stream: bool = False,
) -> dict[str, Any]:
    """Run the LangGraph-based Graph-RAG chain for one user turn.

    Returns a dict with keys:
      - ``text``         : full reply string (stream=False) or ""
      - ``stream``       : token iterator (stream=True) or None
      - ``diagram_path`` : PNG/DOT path or None
      - ``diagram_type`` : "process" | "people" | "technology" | None
      - ``mode``         : "asis" | "principles"
      - ``eval_score``   : float 0-1 or None
    """
    if history is None:
        history = []

    initial_state: AgentState = {
        "user_message": user_message,
        "history": history,
        "excel_path": excel_path,
        "chroma_path": chroma_path,
        "graph_path": graph_path,
        "stream": stream,
    }

    if _COMPILED_GRAPH is not None:
        try:
            final_state: AgentState = _COMPILED_GRAPH.invoke(initial_state)
        except Exception as exc:
            logger.error("LangGraph execution failed, falling back: %s", exc)
            final_state = _fallback_run(initial_state)
    else:
        final_state = _fallback_run(initial_state)

    return {
        "text": final_state.get("reply_text", ""),
        "stream": final_state.get("reply_stream"),
        "thinking_text": final_state.get("thinking_text", ""),
        "diagram_path": final_state.get("diagram_path"),
        "tobe_dot_path": final_state.get("tobe_dot_path"),
        "diagram_type": final_state.get("diagram_type"),
        "mode": final_state.get("mode", "principles"),
        "eval_score": final_state.get("eval_score"),
    }


def _fallback_run(state: AgentState) -> AgentState:
    """Direct execution fallback when LangGraph is not available."""
    state = _node_route(state)
    # All requests (As-Is and To-Be) go through load_asis → principles
    state = _node_load_asis(state)
    return _node_principles(state)
