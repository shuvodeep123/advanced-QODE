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
from typing import Any, Iterator, TypedDict

from .graph_builder import DEFAULT_GRAPH_PATH
from .graph_retriever import get_retriever
from .diagram_executor import run as run_diagram
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


def detect_asis_request(query: str) -> bool:
    """Return True when the query is asking for an As-Is architecture diagram."""
    lower = query.lower()
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

    state["diagram_path"] = diagram_path
    state["diagram_type"] = intent if intent != "general" else None
    state["mode"] = "asis"
    state["eval_score"] = None

    # Build a descriptive reply without calling an LLM
    if diagram_path:
        state["reply_text"] = (
            f"✅ **As-Is {intent.title()} Architecture** generated from your questionnaire.\n\n"
            f"The diagram was produced directly by the `Generate_{intent.title()}_*_Diagram.py` "
            f"module — no LLM involved. Download or view it below."
        )
    else:
        state["reply_text"] = (
            "⚠️ Could not generate the diagram. "
            "Please upload a QODE questionnaire first."
        )
    state["reply_stream"] = None
    return state


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

    # ── Optional diagram generation ───────────────────────────────────────
    diagram_path: str | None = None
    if _wants_diagram(state["user_message"]) and intent != "general":
        try:
            diagram_path = run_diagram(
                diagram_type=intent,
                excel_path=state.get("excel_path"),
            )
        except Exception as exc:
            logger.error("Diagram generation failed: %s", exc)

    state["diagram_path"] = diagram_path
    state["diagram_type"] = intent if intent != "general" else None
    state["mode"] = "principles"

    # ── Build messages ────────────────────────────────────────────────────
    messages = _build_messages(
        user_message=state["user_message"],
        history=state.get("history", []),
        context_chunks=chunks,
        principle_ctx=state.get("principle_ctx", {}),
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
        builder.add_node("principles", _node_principles)

        builder.set_entry_point("route")
        builder.add_conditional_edges(
            "route",
            lambda s: "asis" if s.get("is_asis") else "principles",
            {"asis": "asis", "principles": "principles"},
        )
        builder.add_edge("asis", END)
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

Your responsibilities:
- When a user asks to CREATE / GENERATE a diagram → confirm the diagram type only \
  (the diagram is generated separately from the Python files, no LLM needed).
- When a user asks for IMPROVEMENTS or ANALYSIS → reason across the relevant \
  Engineering Principle × Discipline intersection using the provided context.
- Prefer the **Knowledge Graph Context** (graph traversal) over Semantic Context \
  for relationship/structural questions.
- Ground every answer in the retrieved context. Be concise and actionable.
"""


def _build_messages(
    user_message: str,
    history: list[dict],
    context_chunks: list[dict],
    principle_ctx: dict | None = None,
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

    messages: list[dict] = [{"role": "system", "content": system_content}]
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
    return _node_principles(state)
