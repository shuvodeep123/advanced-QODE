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
from .diagram_executor import run as run_diagram, get_dot_path
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
    diagram_type: str | None
    reply_text: str
    reply_stream: Iterator[str] | None
    mode: str            # "asis" | "principles"
    eval_score: float | None
    error: str | None


# ---------------------------------------------------------------------------
# Node functions — each takes/returns AgentState
# ---------------------------------------------------------------------------

def _node_route(state: AgentState) -> AgentState:
    """Classify intent and decide which path to take."""
    query = state["user_message"]
    state["intent"] = detect_intent(query)
    state["is_asis"] = detect_asis_request(query)
    state["principle_ctx"] = extract_principle_context(query)
    state["is_gap_analysis"] = detect_gap_analysis_request(query)
    state["gap_items"] = _extract_removed_items(query) if state["is_gap_analysis"] else []
    # Gap analysis always takes the LLM path even if as-is keywords present
    if state["is_gap_analysis"]:
        state["is_asis"] = False
    return state


def _node_asis(state: AgentState) -> AgentState:
    """As-Is path: RAG retrieval → diagram generator, zero LLM."""
    intent = state["intent"]
    tracer = get_tracer()

    with tracer.trace("asis_retrieval", input={"intent": intent}):
        retriever = get_retriever(
            graph_path=state["graph_path"],
            chroma_path=state["chroma_path"],
        )
        chunks = retriever.retrieve(
            query=state["user_message"],
            k=5,
            diagram_type=intent if intent != "general" else None,
            graph_hops=2,
        )
        state["context_chunks"] = chunks

    diagram_path: str | None = None
    if intent != "general":
        try:
            diagram_path = run_diagram(
                diagram_type=intent,
                excel_path=state.get("excel_path"),
            )
        except Exception as exc:
            logger.error("Diagram generation failed: %s", exc)
            state["error"] = str(exc)

    # Validate that the generated file actually exists on disk
    if diagram_path and not _Path(diagram_path).exists():
        logger.error("As-Is diagram file not found at '%s'", diagram_path)
        state["error"] = f"Diagram file was not saved at '{diagram_path}'"
        diagram_path = None

    state["diagram_path"] = diagram_path
    state["diagram_type"] = intent if intent != "general" else None
    state["mode"] = "asis"
    state["eval_score"] = None
    state["asis_diagram_data"] = None  # As-Is path does not need LLM grounding

    # Build a descriptive reply without calling an LLM
    if diagram_path:
        fmt = _Path(diagram_path).suffix.upper().lstrip(".")
        state["reply_text"] = (
            f"✅ **As-Is {intent.title()} Architecture** generated from your questionnaire.\n\n"
            f"Rendered as **{fmt}** directly by the `Generate_{intent.title()}_*_Diagram.py` "
            f"module — no LLM involved. View or download the diagram below."
        )
    else:
        state["reply_text"] = (
            "⚠️ Could not generate the As-Is diagram. "
            "Please ensure a valid QODE questionnaire is uploaded and retry."
        )
    state["reply_stream"] = None
    return state


def _node_load_asis(state: AgentState) -> AgentState:
    """Pre-load As-Is architecture data to ground every To-Be / principles LLM call.

    Runs the diagram generator for the detected intent, reads the raw DOT text
    from the questionnaire, and stores it in ``state['asis_diagram_data']``.
    The LLM in ``_node_principles`` will receive this as verified ground truth
    so it cannot hallucinate the current-state architecture.

    Also captures the rendered diagram path so the UI can display the As-Is
    diagram alongside any To-Be recommendations.
    """
    intent = state["intent"]

    if intent == "general":
        state["asis_diagram_data"] = None
        state["diagram_path"] = None
        state["diagram_type"] = None
        return state

    tracer = get_tracer()
    with tracer.trace("load_asis_ground_truth", input={"intent": intent}):
        # Generate the As-Is diagram (writes the DOT file as a side-effect)
        diagram_path: str | None = None
        try:
            diagram_path = run_diagram(
                diagram_type=intent,
                excel_path=state.get("excel_path"),
            )
        except Exception as exc:
            logger.warning("As-Is diagram render failed: %s", exc)

        # Validate the rendered file exists
        if diagram_path and not _Path(diagram_path).exists():
            logger.warning("As-Is diagram file not found at '%s' — proceeding without it.", diagram_path)
            diagram_path = None

        state["diagram_path"] = diagram_path
        state["diagram_type"] = intent

        # Read the DOT file that the generator always writes as ground truth
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
    # Fenced block: ```mermaid … ```
    m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Un-fenced flowchart / graph declaration
    m = re.search(
        r"((?:flowchart|graph)\s+(?:TD|LR|BT|RL)\b.*)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def _node_principles(state: AgentState) -> AgentState:
    """Engineering Principles path: Graph-RAG + LLM with Langfuse tracing."""
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
            else:
                state["reply_text"] = llm_client.chat(messages)
                state["reply_stream"] = None
            span.set_output({"status": "ok"})
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            state["reply_text"] = f"❌ LLM error: {exc}"
            state["reply_stream"] = None
            state["error"] = str(exc)
            span.set_output({"status": "error", "error": str(exc)})

    # ── Extract and persist Mermaid diagram from LLM reply ───────────────
    # When the LLM generates a To-Be Mermaid diagram (either from As-Is data
    # or from QODE principles), extract it and save it as a .mmd file so the
    # UI can render it and run_chain can return a valid diagram_path.
    if (
        (_wants_diagram(state["user_message"]) or state.get("is_gap_analysis"))
        and not state.get("diagram_path")
        and not state.get("stream")
        and state.get("reply_text")
    ):
        mermaid_src = _extract_mermaid(state["reply_text"])
        if mermaid_src:
            intent = state.get("intent", "general")
            if intent != "general":
                dot_file = get_dot_path(intent)
                if dot_file:
                    # gap analysis → _gap.mmd, to-be → _tobe.mmd
                    suffix = "_gap.mmd" if state.get("is_gap_analysis") else "_tobe.mmd"
                    out_path = dot_file.parent / f"{dot_file.stem}{suffix}"
                    try:
                        out_path.write_text(mermaid_src, encoding="utf-8")
                        state["diagram_path"] = str(out_path)
                        state["diagram_type"] = intent
                        logger.info(
                            "%s Mermaid diagram saved: %s (%d chars)",
                            "Gap" if state.get("is_gap_analysis") else "To-Be",
                            out_path, len(mermaid_src),
                        )
                    except Exception as save_err:
                        logger.warning("Could not save Mermaid diagram: %s", save_err)
        else:
            logger.warning(
                "LLM reply did not contain a Mermaid diagram block for '%s' request.",
                state.get("intent", "general"),
            )

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
        builder.add_node("route", _node_route)
        builder.add_node("asis", _node_asis)
        builder.add_node("load_asis", _node_load_asis)   # grounding step before LLM
        builder.add_node("principles", _node_principles)

        builder.set_entry_point("route")
        builder.add_conditional_edges(
            "route",
            lambda s: "asis" if s.get("is_asis") else "load_asis",
            {"asis": "asis", "load_asis": "load_asis"},
        )
        builder.add_edge("asis", END)
        builder.add_edge("load_asis", "principles")   # always ground before LLM
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

## Diagram Output Format (MANDATORY when a diagram is requested)
- **Always** emit a complete Mermaid flowchart inside a fenced code block: \
  \`\`\`mermaid … \`\`\`.
- Do NOT describe the diagram only in prose — render it.
- Include labelled nodes for every key role / tool / process in the architecture.
- Use `flowchart TD` for People and Process diagrams; `flowchart LR` for Technology diagrams.
- For a **People** diagram: actor nodes → responsibility / ownership arrows.
- For a **Process** diagram: activity nodes → sequence / dependency arrows, \
  annotate critical-path edges.
- For a **Technology** diagram: tool/platform nodes → integration / data-flow arrows.

Your responsibilities:
- When a user asks for IMPROVEMENTS, ANALYSIS, or a TO-BE diagram → reason across the \
  relevant Engineering Principle × Discipline intersection using the provided context, \
  then emit the Mermaid diagram.
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
    # and the LLM cannot overlook it.  This is the primary anti-hallucination guard.
    if asis_diagram_data:
        system_content += (
            "\n\n---\n## ⚠️ As-Is Architecture — Verified Ground Truth\n\n"
            "The following DOT graph is the **verified current-state architecture** "
            "extracted directly from the client's QODE questionnaire.\n"
            "**Base all To-Be recommendations on this data. "
            "Do NOT invent roles, tools, or processes absent from it.**\n"
            "When a To-Be diagram is requested, analyse the As-Is state and emit a "
            "`mermaid` flowchart (```mermaid … ```) showing the recommended target-state "
            "with explicit improvement annotations.\n\n"
            "```dot\n"
            + asis_diagram_data
            + "\n```"
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
            "4. **Mandatory**: Output a complete `mermaid` flowchart (\'\'\'mermaid … \'\'\') "
            "showing the recommended target-state architecture with nodes for key "
            "roles / tools / processes and labelled arrows.\n"
            "5. Label your output: **Best-Practice To-Be Architecture (QODE Framework)** "
            "— based on QODE principles, not a specific client questionnaire."
        )

    messages: list[dict] = [{"role": "system", "content": system_content}]
    # ── Gap analysis overlay ─────────────────────────────────────────────
    # Injected as an extra system message (not inside the main system prompt)
    # so it has the highest priority and the LLM processes it as a late
    # constraint — the same pattern used by tool-call frameworks.
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
    for turn in history[-6:]:
        messages.append(turn)
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
        "diagram_path": final_state.get("diagram_path"),
        "diagram_type": final_state.get("diagram_type"),
        "mode": final_state.get("mode", "principles"),
        "eval_score": final_state.get("eval_score"),
    }


def _fallback_run(state: AgentState) -> AgentState:
    """Direct execution fallback when LangGraph is not available."""
    state = _node_route(state)
    if state.get("is_asis"):
        return _node_asis(state)
    # Load As-Is ground truth BEFORE calling the LLM to prevent hallucination
    state = _node_load_asis(state)
    return _node_principles(state)
