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
from .diagram_executor import run as run_diagram, get_dot_path, ASIS_DIRS, TOBE_DIRS, dot_to_drawio, dot_to_plantuml, dot_to_mermaid, _validate_mermaid
from .principles_engine import PrinciplesEngine, extract_principle_context
from .langfuse_tracer import get_tracer
from . import llm_client as llm_client_mod
from .diagram_schema import DiagramAsIs, DiagramToBe
from .image_generator import generate_report_images
from .guardrails_config import (
    validate_conversation,
    ASIS_GROUNDEDNESS_RULES,
    CONVERSATION_QUALITY_RULES,
)

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

# Diagram-specific nouns — a generate verb only triggers diagram mode if one of these is present
_DIAGRAM_NOUNS = [
    "diagram", "chart", "flowchart", "architecture diagram",
    "network diagram", "graph", "mermaid", "dot graph",
    "people diagram", "process diagram", "technology diagram",
    "as-is diagram", "to-be diagram", "architecture",
]

# Agile / planning terms — presence of any of these suppresses diagram routing
_PLANNING_EXCLUSION_KEYWORDS = [
    "epic", "epics", "story", "stories", "task", "tasks",
    "story point", "story points", "sprint", "backlog",
    "stakeholder", "dependency", "dependencies",
    "acceptance criteria", "definition of done",
    "jira", "confluence", "scrum", "kanban", "agile",
    "user story", "feature request", "milestone",
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

    Explicitly returns False for To-Be requests and planning/agile requests
    (epics, stories, tasks, etc.) even if generate verbs are present.
    """
    lower = query.lower()
    if any(kw in lower for kw in _TOBE_KEYWORDS):
        return False
    if any(kw in lower for kw in _PLANNING_EXCLUSION_KEYWORDS):
        return False
    # Must have an asis marker AND a diagram noun to qualify
    has_asis_marker = any(kw in lower for kw in ["as-is", "as is", "asis", "current state", "existing"])
    has_diagram_noun = any(kw in lower for kw in _DIAGRAM_NOUNS)
    has_generate_verb = any(kw in lower for kw in _GENERATE_KEYWORDS)
    # Explicit asis markers with diagram noun — clear intent
    if has_asis_marker and has_diagram_noun:
        return True
    # Generate verb + diagram noun without asis marker — could be either; treat as asis only if no tobe
    if has_generate_verb and has_diagram_noun:
        return True
    return False


# Keywords that indicate a narrative/planning follow-up (document-worthy response)
_NARRATIVE_KEYWORDS = [
    "30-60-90", "30 60 90", "roadmap", "plan",
    "what improvements", "improvement", "recommendation",
    "assessment", "maturity", "report", "summary",
    "strategy", "assess", "review", "across all",
    "all engineering", "all principles",
    "success metrics", "metrics", "days", "timeline",
    "propensity", "people propensity", "organizational",
    # Agile / project planning
    "epic", "epics", "story", "stories", "task", "tasks",
    "story point", "story points", "sprint", "backlog",
    "stakeholder", "dependency", "dependencies",
    "acceptance criteria", "definition of done",
    "user story", "milestone", "jira", "scrum", "kanban",
]
_DIAGRAM_NOUN_KEYWORDS = ["diagram", "chart", "flowchart", "architecture"]


def detect_narrative_request(query: str) -> bool:
    """Return True for analysis/planning questions that warrant document generation.

    These are follow-up questions (not diagram requests) that produce structured
    narrative output — e.g. 'What improvements are required in Technology Disciplines
    across all engineering principles?' or 'Create a 30-60-90 days plan'.

    Narrative keywords like 'propensity', 'metrics', 'days' override diagram keywords
    to ensure image generation still happens for context-aware visualization requests.
    """
    lower = query.lower()
    has_narrative = any(kw in lower for kw in _NARRATIVE_KEYWORDS)
    # Override: if propensity/metrics/days/timeline present, treat as narrative even if "diagram" mentioned
    has_special_narrative = any(kw in lower for kw in ["propensity", "metrics", "days", "timeline"])
    has_diagram   = any(kw in lower for kw in _DIAGRAM_NOUN_KEYWORDS)
    return has_narrative and (has_special_narrative or not has_diagram)


def _wants_diagram(query: str) -> bool:
    """True only when the query explicitly requests a diagram/architecture output.

    Requires BOTH a generate verb AND a diagram noun. Agile/planning terms
    (epics, stories, tasks, story points, etc.) suppress diagram routing even
    if generate verbs are present.
    """
    lower = query.lower()
    if any(kw in lower for kw in _PLANNING_EXCLUSION_KEYWORDS):
        return False
    has_verb = any(kw in lower for kw in _GENERATE_KEYWORDS)
    has_noun = any(kw in lower for kw in _DIAGRAM_NOUNS)
    return has_verb and has_noun


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
    # To-Be diagram data — persisted across turns for follow-up analysis
    tobe_diagram_data: str | None   # raw DOT text for To-Be architecture (from LLM)
    # gap / impact analysis
    is_gap_analysis: bool           # True when user wants pillar removal impact analysis
    gap_items: list[str]            # pillar / component names to be "removed"
    # output
    diagram_path: str | None
    tobe_mermaid_path: str | None   # Mermaid .mmd for To-Be diagram (from LLM)
    diagram_type: str | None
    reply_text: str
    thinking_text: str          # content of <think>…</think> block (may be empty)
    reply_stream: Iterator[str] | None
    mode: str            # "asis" | "principles"
    eval_score: float | None
    error: str | None
    report_images: list[dict] | None  # Generated images for gap/narrative reports


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
    tracer = get_tracer()
    query = state["user_message"]
    with tracer.trace("intent_routing", input={"query_preview": query[:120]}) as span:
        state["intent"] = detect_intent(query)
        state["is_asis"] = detect_asis_request(query)
        state["principle_ctx"] = extract_principle_context(query)
        state["is_gap_analysis"] = detect_gap_analysis_request(query)
        state["gap_items"] = _extract_removed_items(query) if state["is_gap_analysis"] else []
        if state["is_gap_analysis"]:
            state["is_asis"] = False
        span.set_output({
            "intent": state["intent"],
            "is_asis": state["is_asis"],
            "is_gap_analysis": state["is_gap_analysis"],
            "principle": state["principle_ctx"].get("principle") if state.get("principle_ctx") else None,
        })
    return state


def _node_load_asis(state: AgentState) -> AgentState:
    """Pre-load As-Is architecture data to ground every LLM call.

    Runs the diagram generator for the detected intent, reads the raw DOT text
    from the questionnaire, and stores it in ``state['asis_diagram_data']``.
    The LLM in ``_node_principles`` receives this as verified ground truth.
    Also captures the rendered diagram path so the UI can display it.

    For multi-turn conversations, checks if As-Is data was loaded in a prior turn
    and reuses it if available.
    """
    intent = state["intent"]

    # ── Check if As-Is data already exists from a prior turn ──────────────────
    if state.get("asis_diagram_data"):
        logger.info("As-Is ground truth already loaded in session (reusing from prior turn)")
        return state

    if intent == "general":
        state["asis_diagram_data"] = None
        state["diagram_path"] = None
        state["diagram_type"] = None
        return state

    tracer = get_tracer()
    with tracer.trace("load_asis_ground_truth", input={"intent": intent}) as span:
        diagram_path: str | None = None
        try:
            diagram_path = run_diagram(
                diagram_type=intent,
                excel_path=state.get("excel_path"),
                is_tobe=False,
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
            span.set_output({
                "asis_loaded": True,
                "asis_chars": len(state["asis_diagram_data"]),
                "diagram_path": diagram_path,
            })
        else:
            state["asis_diagram_data"] = None
            logger.warning(
                "As-Is DOT file not found for intent '%s'. "
                "LLM will lack questionnaire ground truth — responses may be less accurate.",
                intent,
            )
            span.set_output({"asis_loaded": False, "diagram_path": diagram_path})

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


def _try_extract_diagram_json(text: str, diagram_type: str, is_tobe: bool = False) -> DiagramAsIs | DiagramToBe | None:
    """Attempt to extract and validate diagram structure from LLM reply.

    Looks for a JSON block containing nodes/edges array within the text.
    Returns a validated Pydantic model (DiagramAsIs or DiagramToBe) or None.
    """
    import json
    try:
        # Look for a JSON block within code fence or raw
        m = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if not m:
            # Try raw JSON if no fence
            m = re.search(r"(\{.*?\})", text, re.DOTALL)
        if not m:
            return None

        raw_json = m.group(1)
        data = json.loads(raw_json)

        if not isinstance(data, dict):
            return None

        # Inject diagram_type if missing
        if "diagram_type" not in data:
            data["diagram_type"] = diagram_type

        Model = DiagramToBe if is_tobe else DiagramAsIs
        try:
            return Model(**data)
        except Exception as e:
            logger.warning("Diagram validation failed: %s", e)
            return None
    except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as e:
        logger.debug("No valid diagram JSON found: %s", e)
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


def _validate_grounding(chunks: list[dict], asis_data: str | None, is_asis: bool, is_gap: bool) -> tuple[bool, str]:
    """Validate if the query has sufficient context for LLM response.

    Returns (is_grounded, reason_text). For To-Be mode, requires either:
    - verified As-Is questionnaire data (asis_data) OR
    - sufficient retrieval context (chunks with quality checks)

    For As-Is/Gap modes, always grounded if we have asis_data.
    """
    has_asis_data = bool(asis_data)

    # Filter chunks: require non-empty 'text' field (prevent poisoning by empty dicts)
    valid_chunks = [
        c for c in chunks
        if isinstance(c, dict) and c.get("text") and len(str(c.get("text", "")).strip()) > 10
    ]
    has_quality_chunks = len(valid_chunks) > 0

    if is_asis or is_gap:
        if has_asis_data:
            return True, "As-Is questionnaire loaded"
        else:
            return False, "No As-Is questionnaire data available for analysis"

    # To-Be mode: must have either As-Is or quality context (not just any chunks)
    if has_asis_data:
        return True, "Grounded in As-Is questionnaire"
    if has_quality_chunks:
        logger.info("Grounded in %d quality context chunk(s)", len(valid_chunks))
        return True, f"Grounded in {len(valid_chunks)} context chunk(s)"

    return False, "No questionnaire or context available — cannot generate To-Be without grounding"


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
    with tracer.trace("graph_rag_retrieval", input={"intent": intent, "query": state["user_message"]}) as _rspan:
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
        _graph_chunks = sum(1 for c in chunks if c.get("source") == "graph")
        _vec_chunks   = sum(1 for c in chunks if c.get("source") == "vector")
        _rspan.set_output({
            "total_chunks": len(chunks),
            "graph_chunks": _graph_chunks,
            "vector_chunks": _vec_chunks,
        })

    # ── Validate context quality against QODE propensities + readiness ──────
    from . import eval_metrics
    import json
    graph_data = {}
    with tracer.trace("context_quality_check", input={"intent": intent, "chunk_count": len(chunks)}) as span:
        try:
            with open(state["graph_path"], "r") as f:
                graph_data = json.load(f)
        except Exception as e:
            logger.warning("Could not load graph for evaluation: %s", e)

        if graph_data:
            eval_valid = eval_metrics.validate_context_before_llm(graph_data)
            node_count  = len(graph_data.get("nodes", graph_data.get("entities", [])))
            edge_count  = len(graph_data.get("edges", graph_data.get("relationships", [])))
            chunk_count = len(chunks)
            asis_present = bool(state.get("asis_diagram_data"))
            logger.info(
                "[PRE-LLM DATA CHECK] graph_nodes=%d  graph_edges=%d  "
                "retrieval_chunks=%d  asis_loaded=%s  intent=%s  eval_gate=%s",
                node_count, edge_count, chunk_count, asis_present,
                state.get("intent", "general"),
                "PASS" if eval_valid else "WARN",
            )
            if not eval_valid:
                logger.warning("[PRE-LLM DATA CHECK] Graph context quality issues — proceeding with degraded context")
            span.set_output({
                "graph_nodes": node_count,
                "graph_edges": edge_count,
                "retrieval_chunks": chunk_count,
                "asis_present": asis_present,
                "eval_gate": "PASS" if eval_valid else "WARN",
            })
        else:
            logger.warning(
                "[PRE-LLM DATA CHECK] graph_nodes=0  graph_edges=0  "
                "retrieval_chunks=%d  asis_loaded=%s  intent=%s  eval_gate=SKIP (no graph)",
                len(chunks), bool(state.get("asis_diagram_data")), state.get("intent", "general"),
            )
            span.set_output({"graph_nodes": 0, "graph_edges": 0,
                             "retrieval_chunks": len(chunks), "eval_gate": "SKIP"})

    # ── Validate grounding before LLM call ──────────────────────────────────
    with tracer.trace("grounding_check", input={"intent": intent, "is_asis": state.get("is_asis"), "is_gap": state.get("is_gap_analysis")}) as span:
        is_grounded, reason = _validate_grounding(
            chunks,
            state.get("asis_diagram_data"),
            state.get("is_asis", False),
            state.get("is_gap_analysis", False),
        )
        span.set_output({"is_grounded": is_grounded, "reason": reason})
    if not is_grounded:
        logger.warning("Query not grounded: %s", reason)
        state["reply_text"] = f"Cannot process request: {reason}\n\nPlease provide a QODE questionnaire or ask about existing documented practices."
        state["thinking_text"] = ""
        state["reply_stream"] = None
        state["error"] = reason
        return state
    else:
        logger.info("Query grounded — proceeding: %s", reason)

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
    _active_model = llm_client.get_active_model()
    with tracer.trace(
        "llm_generation",
        input={"messages_count": len(messages), "intent": intent, "model": _active_model},
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
            # Attach token usage + cost to span (non-streaming only; streaming tokens
            # arrive asynchronously so we capture what's available immediately)
            if not state.get("stream"):
                _u = llm_client_mod.get_last_call_usage()
                span.set_usage(
                    model=_active_model,
                    prompt_tokens=_u["prompt_tokens"],
                    completion_tokens=_u["completion_tokens"],
                    cost_inr=_u["cost_inr"],
                )
            span.set_output({"status": "ok"})
        except RuntimeError as exc:
            # Latency or critical errors — user should switch models
            logger.error("LLM critical error: %s", exc)
            error_msg = str(exc)
            if "latency" in error_msg.lower():
                state["reply_text"] = (
                    f"API Latency ⏱️  Critical: {exc}\n\n"
                    "The LLM provider is responding too slowly. "
                    "Use the model selector to switch to a faster provider."
                )
            else:
                state["reply_text"] = f"Critical error: {exc}"
            state["thinking_text"] = ""
            state["reply_stream"] = None
            state["error"] = error_msg
            span.set_output({"status": "error", "error": error_msg})
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            state["reply_text"] = f"LLM error: {exc}"
            state["thinking_text"] = ""
            state["reply_stream"] = None
            state["error"] = str(exc)
            span.set_output({"status": "error", "error": str(exc)})

    # ── Post-LLM policy validation ────────────────────────────────────
    if not state.get("stream") and state.get("reply_text"):
        try:
            # Hallucination check: reject if LLM mentions unsupported formats
            reply_lower = state.get("reply_text", "").lower()
            banned_formats = ["draw.io", "plantuml", "plant uml", "puml"]
            for fmt in banned_formats:
                if fmt in reply_lower:
                    logger.error("LLM hallucination detected: mentions '%s' (unsupported format)", fmt)
                    state["reply_text"] = (
                        f"❌ Response validation failed: LLM mentioned unsupported format '{fmt}'.\n\n"
                        "Only DOT and Mermaid diagrams are generated. "
                        "Please try again with a refined query."
                    )
                    state["error"] = f"Hallucination: LLM mentioned {fmt}"
                    return state

            is_grounded = bool(state.get("context_chunks")) or bool(state.get("asis_diagram_data"))
            is_valid = validate_conversation({
                "is_grounded": is_grounded,
                "is_respectful": True,
            })
            if is_valid:
                logger.info("Conversation quality policy passed")
            else:
                logger.warning("Conversation quality policy check failed (non-blocking)")

            # ── Response completeness checks ──────────────────────────────
            wants_diag_check = _wants_diagram(state.get("user_message", ""))
            reply_check = state.get("reply_text", "")
            if wants_diag_check:
                has_dot      = "digraph" in reply_check.lower() or "```dot" in reply_check.lower()
                has_mermaid  = "```mermaid" in reply_check.lower()
                has_labels   = "|\"" in reply_check or "-->|" in reply_check or "->" in reply_check
                edge_count_r = reply_check.count("-->") + reply_check.count("->")
                logger.info(
                    "[POST-LLM RESPONSE CHECK] has_dot=%s  has_mermaid=%s  "
                    "has_edge_labels=%s  edge_count=%d",
                    has_dot, has_mermaid, has_labels, edge_count_r,
                )
                if not has_dot:
                    logger.warning("[POST-LLM RESPONSE CHECK] DOT block missing from diagram response")
                if not has_mermaid:
                    logger.warning("[POST-LLM RESPONSE CHECK] Mermaid block missing from diagram response")
                if edge_count_r < 3:
                    logger.warning("[POST-LLM RESPONSE CHECK] Very few edges (%d) — diagram may have disconnected nodes", edge_count_r)
        except Exception as e:
            logger.warning("Policy validation issue (non-blocking): %s", e)

    # ── Extract and persist DOT + Mermaid + PlantUML from LLM reply ──────
    # Runs for ALL diagram requests: As-Is AND To-Be.
    # As-Is diagrams are saved to ASIS_DIRS; To-Be / gap diagrams to TOBE_DIRS.
    is_asis_req     = state.get("is_asis", False)
    is_gap          = state.get("is_gap_analysis", False)
    wants_diag      = _wants_diagram(state["user_message"]) or is_gap
    should_extract  = (
        not state.get("stream")
        and state.get("reply_text")
        and (wants_diag or is_asis_req)
    )

    if should_extract:
        with tracer.trace(
            "diagram_extraction",
            input={"intent": state.get("intent"), "is_asis": is_asis_req, "is_gap": is_gap},
        ) as dspan:
            reply_text  = state["reply_text"]
            intent_key  = state.get("intent", "general")
            stem_suffix = "_gap" if is_gap else ""
            base_name   = f"{intent_key}{stem_suffix}"

            out_dirs  = ASIS_DIRS if is_asis_req else TOBE_DIRS
            dir_label = "As-Is" if is_asis_req else ("Gap" if is_gap else "To-Be")
            dot_ref   = get_dot_path(intent_key) if intent_key != "general" else None

            _extracted = {"mermaid": False, "dot": False, "struct_nodes": 0, "struct_edges": 0}

            # ── Validate diagram structure (optional JSON) ─────────────────────
            diagram_struct = _try_extract_diagram_json(
                reply_text, intent_key, is_tobe=not is_asis_req and not is_gap
            )
            if diagram_struct:
                _extracted["struct_nodes"] = len(diagram_struct.nodes)
                _extracted["struct_edges"] = len(diagram_struct.edges)
                logger.info("%s diagram structure validated: %d nodes, %d edges",
                            dir_label, len(diagram_struct.nodes), len(diagram_struct.edges))

            # ── Mermaid → <dir>/Mermaid/ ────────────────────────────────────
            mermaid_src = _extract_mermaid(reply_text)
            if mermaid_src:
                mmd_out = out_dirs["mermaid"] / f"{base_name}.mmd"
                try:
                    mmd_out.write_text(mermaid_src, encoding="utf-8")
                    state["diagram_path"] = str(mmd_out)
                    state["diagram_type"] = intent_key
                    _extracted["mermaid"] = True
                    logger.info("%s Mermaid saved: %s (%d chars)", dir_label, mmd_out, len(mermaid_src))
                    if dot_ref:
                        try:
                            legacy = dot_ref.parent / f"{dot_ref.stem}{'_gap' if is_gap else ('_asis' if is_asis_req else '_tobe')}.mmd"
                            legacy.write_text(mermaid_src, encoding="utf-8")
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("Could not save %s Mermaid: %s", dir_label, e)
            else:
                logger.warning("LLM reply contained no Mermaid block for '%s' %s request.", intent_key, dir_label)

            # ── DOT → <dir>/DotGraph/ ────────────────────────────────────────
            dot_src = _extract_dot(reply_text)
            if dot_src:
                if not is_asis_req and not is_gap:
                    state["tobe_diagram_data"] = dot_src
                    logger.info("To-Be diagram data persisted for session (%d chars)", len(dot_src))

                dot_out = out_dirs["dot"] / f"{base_name}.dot"
                try:
                    dot_out.write_text(dot_src, encoding="utf-8")
                    _extracted["dot"] = True
                    logger.info("%s DOT saved: %s (%d chars)", dir_label, dot_out, len(dot_src))

                    try:
                        mmd_text = dot_to_mermaid(dot_src, intent_key)
                        is_valid, err_msg = _validate_mermaid(mmd_text)
                        if not is_valid:
                            logger.warning("Mermaid validation failed for %s: %s", dir_label, err_msg)
                            state["tobe_mermaid_path"] = None
                        else:
                            mmd_out = out_dirs["mermaid"] / f"{base_name}.mmd"
                            mmd_out.write_text(mmd_text, encoding="utf-8")
                            state["tobe_mermaid_path"] = str(mmd_out)
                            logger.info("%s Mermaid UI path saved: %s", dir_label, mmd_out)
                    except Exception as me:
                        logger.warning("Could not convert %s DOT to Mermaid: %s", dir_label, me)
                        state["tobe_mermaid_path"] = None

                    try:
                        puml_text = dot_to_plantuml(dot_src, intent_key)
                        puml_out = out_dirs["plantuml"] / f"{base_name}.puml"
                        puml_out.write_text(puml_text, encoding="utf-8")
                        logger.info("%s PlantUML saved: %s", dir_label, puml_out)
                    except Exception as pe:
                        logger.warning("Could not generate %s PlantUML: %s", dir_label, pe)

                    try:
                        drawio_text = dot_to_drawio(dot_src, intent_key)
                        drawio_out = out_dirs["drawio"] / f"{base_name}.drawio"
                        drawio_out.write_text(drawio_text, encoding="utf-8")
                        logger.info("%s draw.io saved: %s", dir_label, drawio_out)
                    except Exception as de:
                        logger.warning("Could not generate %s draw.io: %s", dir_label, de)
                except Exception as e:
                    logger.warning("Could not save %s DOT: %s", dir_label, e)

            dspan.set_output(_extracted)

    # ── Eval scoring (async, non-blocking) ────────────────────────────────
    try:
        from .eval_metrics import score_response
        if not state.get("stream") and state.get("reply_text"):
            context_text = "\n".join(c.get("text", "") for c in chunks if c.get("text"))
            with tracer.trace("eval_scoring", input={"intent": intent}) as espan:
                state["eval_score"] = score_response(
                    query=state["user_message"],
                    answer=state["reply_text"],
                    context=context_text,
                )
                tracer.log_score("faithfulness", state["eval_score"])
                raw_score = state["eval_score"] or 0.0
                score_10  = round(raw_score * 10, 1)
                pct       = round(raw_score * 100, 1)
                band      = (
                    "EXCELLENT" if score_10 >= 8.5 else
                    "GOOD"      if score_10 >= 7.0 else
                    "FAIR"      if score_10 >= 5.0 else
                    "LOW"
                )
                espan.set_output({"score": raw_score, "score_10": score_10, "band": band})
                logger.info(
                    "[ACCURACY] %.1f/10  (%.1f%%)  [%s] — delivering response to user",
                    score_10, pct, band,
                )
                if raw_score < 0.6:
                    logger.warning(
                        "[ACCURACY] Low Confidence — score %.1f/10 below threshold (6.0/10). "
                        "Please review and validate against source documents.",
                        score_10,
                    )
    except Exception as e:
        logger.warning("Eval scoring failed (non-blocking): %s", e)
        state["eval_score"] = None

    # ── Image generation for gap analysis and narrative reports ──────────────
    is_gap = state.get("is_gap_analysis", False)
    is_narrative = detect_narrative_request(state.get("user_message", ""))

    if (is_gap or is_narrative) and state.get("reply_text"):
        report_type = "gap_analysis" if is_gap else "assessment"
        with tracer.trace(
            "image_generation",
            input={"intent": intent, "report_type": report_type},
        ) as ispan:
            try:
                images = generate_report_images(
                    narrative_text=state["reply_text"],
                    intent=intent,
                    report_type=report_type,
                    max_images=3,
                )
                if images:
                    state["report_images"] = images
                    logger.info("Generated %d images for %s report", len(images), report_type)
                ispan.set_output({"image_count": len(images) if images else 0})
            except Exception as e:
                logger.warning("Image generation failed (non-blocking): %s", e)
                state["report_images"] = None
                ispan.set_error(str(e))

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

""" + ASIS_GROUNDEDNESS_RULES + """
- **Toolchain Improvement (Technology Discipline)**: When the user asks to improve an existing \
  As-Is Technology diagram, you MUST:\
    1. **Stay within the verified As-Is toolchain** — Only recommend enhancements or replacements \
       for tools/platforms that are already present in the questionnaire.\
    2. **Best-fit tools** — Recommend the most effective tool for each capability gap, whether \
       open-source, commercial, SaaS, or AI-enabled. Examples:\
       - CI/CD: Jenkins, GitLab CI, GitHub Actions, CircleCI\
       - Observability: Prometheus+Grafana, Datadog, New Relic, Dynatrace\
       - Security: HashiCorp Vault, AWS Secrets Manager, CyberArk\
       - AI/ML Ops: MLflow, Weights & Biases, Azure ML, SageMaker\
       - AI-enabled services: GitHub Copilot, Snyk, Veracode, Harness, OpsRamp\
    3. **Prioritize production-proven tools** — Avoid experimental or beta software. \
       Prefer widely-adopted tools with strong enterprise support.\
    4. **Justify each recommendation** — Explain:\
       - Why the tool fits into the existing As-Is architecture\
       - Integration points and data flows\
       - Migration path from current state (if applicable)\
    5. **AI enablement is encouraged** — Actively identify where AI-assisted tooling \
       (copilots, AIOps, intelligent testing, predictive security) improves the architecture.
- **To-Be recommendations**: ALWAYS ground in the verified As-Is data and the QODE Knowledge \
  Graph. Recommend the best-fit tools regardless of licensing model. Actively include \
  commercially available and AI-enabled services where they deliver clear improvement. \
  For every tool recommendation:\
    • Justify fit with the existing As-Is architecture\
    • Confirm the tool is production-proven and widely adopted\
    • Identify integration points and data flows\
    • Flag where AI/ML-enabled capabilities add measurable value
- Never invent facts that contradict the verified As-Is data when it is present.

## Diagram Output Format (MANDATORY — EXACT formats only)
**CRITICAL: Output ONLY these two formats. Do NOT mention, reference, or output draw.io, PlantUML, or any other format.**
- **Graphviz DOT** inside: \`\`\`dot digraph G { … } \`\`\`
- **Mermaid flowchart** inside: \`\`\`mermaid flowchart … \`\`\`
- **Both blocks are REQUIRED** — do NOT emit only one format. Output DOT first, then Mermaid.
- **OPTIONAL — Structured JSON** (for improved validation): After the diagrams, optionally \
  provide a JSON block with nodes and edges arrays.
- Do NOT mention draw.io, PlantUML, or other formats — those are handled internally.
- DOT direction: `rankdir=TD` for People/Process; `rankdir=LR` for Technology.
- Mermaid direction: `flowchart TD` for People/Process; `flowchart LR` for Technology.

## Diagram Graph Quality Rules (MANDATORY — no exceptions)
**CONNECTIVITY**: Every node MUST have at least one edge. Zero isolated/disconnected nodes. \
If a node has no natural connection, attach it to the most relevant parent with an appropriate label.

**EDGE LABELS (MANDATORY)**: Every edge MUST carry a descriptive label that explains the \
relationship or improvement. Bare unlabelled arrows are NOT acceptable. Examples:\
  - People: `-->|"owns / approves"| `, `-->|"reviews & escalates"|`\
  - Process: `-->|"triggers"| `, `-->|"feeds into"| `, `-->|"gates release"|`\
  - Technology: `-->|"deploys via"| `, `-->|"monitors"| `, `-->|"scans for CVEs"|`\
  - To-Be improvement edges: `-->|"replaces — AI-assisted"| `, `-->|"enhances with ML scoring"|`

**AI TOOL INFUSION (MANDATORY for To-Be)**: For every major capability area, explicitly \
evaluate whether an AI-enabled or intelligent tool should be introduced or replace an existing \
node. Label such nodes with `[AI]` suffix (e.g., `CopilotAI["GitHub Copilot [AI]"]`). \
Connect them with edges labelled to explain the AI value-add.

**COMMERCIAL TOOL INCLUSION**: Do NOT default to open-source only. Where a commercial or \
SaaS tool is the industry-standard best practice for that capability, include it. \
Examples: Datadog, Snyk, GitHub Actions, Harness, PagerDuty, Veracode, Dynatrace.

**IMPROVEMENT TRACEABILITY (To-Be only)**: For every IMPROVED or REPLACED node, the edge \
from its As-Is predecessor MUST be labelled with what changed and why. \
Example: `OldJenkins -->|"replaced — native GitOps, zero scripting"| ArgoCDNew`

**NO ORPHAN SUBGRAPHS**: If using subgraphs/clusters, every subgraph must have at least \
one cross-subgraph edge connecting it to the rest of the diagram.

- For a **People** diagram: actor nodes → responsibility / ownership arrows with role labels.
- For a **Process** diagram: activity nodes → sequence / dependency arrows with action labels.
- For a **Technology** diagram: tool/platform nodes → integration / data-flow arrows with protocol or capability labels.

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

## Conversation Quality Standards (MANDATORY)

""" + CONVERSATION_QUALITY_RULES + """
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
            # As-Is analysis mode: regenerate the diagram + provide structured analysis
            system_content += (
                "\n\n---\n## ⚠️ As-Is Architecture — Verified Ground Truth\n\n"
                "The following DOT graph is the **verified current-state architecture** "
                "extracted directly from the client's QODE questionnaire.\n\n"
                "```dot\n"
                + asis_diagram_data
                + "\n```\n\n"
                "## 📊 As-Is Diagram Generation Mode — ACTIVE\n\n"
                "You MUST output BOTH a **Graphviz DOT graph** and a **Mermaid flowchart** "
                "that faithfully reproduces the verified As-Is architecture above.\n"
                "Use EXACTLY the nodes and edges from the ground-truth DOT — do not add or remove any.\n\n"
                "**Output format (MANDATORY):**\n"
                "1. Emit the DOT graph inside: ```dot digraph G { … } ```\n"
                "2. Emit the Mermaid flowchart inside: ```mermaid flowchart … ```\n"
                "3. Both blocks are REQUIRED — output DOT first, then Mermaid.\n\n"
                "After the diagrams, provide a structured analysis:\n"
                "1. **Architecture Summary** — what the current state looks like\n"
                "2. **Key Components** — list all roles / tools / processes found\n"
                "3. **Strengths** — what is working well\n"
                "4. **Gaps & Areas for Attention** — missing capabilities or improvement areas\n"
                "5. **Quick Wins** — 2–3 immediate improvements with low effort / high impact\n"
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
                "\n\n---\n## 📊 As-Is Diagram Generation Mode — No Questionnaire Loaded\n\n"
                "No client questionnaire has been uploaded. Generate a best-practice "
                "current-state architecture diagram for the requested discipline, "
                "based on the QODE Knowledge Graph Context above.\n\n"
                "**Output format (MANDATORY):**\n"
                "1. Emit a **Graphviz DOT graph** inside: ```dot digraph G { … } ```\n"
                "2. Emit a **Mermaid flowchart** inside: ```mermaid flowchart … ```\n"
                "3. Both blocks are REQUIRED — output DOT first, then Mermaid.\n\n"
                "After the diagrams, provide a structured analysis: "
                "Summary, Key Components, Strengths, Gaps, Quick Wins."
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

    # ── Roadmap / long-term planning overlay ──────────────────────────────
    if detect_narrative_request(user_message):
        roadmap_sys = (
            "## 📋 Strategic Roadmap Mode — ACTIVE\n\n"
            "The user is requesting a long-term / mid-term / short-term plan (e.g., 30-60-90 days, "
            "roadmap, strategy, or assessment).\n\n"
            "### Chain-of-Thought Planning Constraint (MANDATORY)\n\n"
            "You MUST use **structured chain-of-thought reasoning** that explicitly considers "
            "interdependencies across **People — Process — Technology** when building the roadmap:\n\n"
            "1. **Dependency Mapping Phase**:\n"
            "   - Identify which initiatives depend on **People** changes (hiring, training, org restructure)\n"
            "   - Identify which initiatives depend on **Process** changes (workflow redesign, governance, culture)\n"
            "   - Identify which initiatives depend on **Technology** adoption (tool implementation, integration)\n"
            "   - Map cross-cutting dependencies: e.g., 'Tool X cannot be deployed until Process Y is in place "
            "     and Team Z has training'\n\n"
            "2. **Complexity & Priority Analysis**:\n"
            "   - **High Complexity**: Multi-disciplinary initiatives (e.g., CI/CD transformation requires "
            "     People training + Process redesign + Technology setup)\n"
            "   - **Medium Complexity**: Single-discipline initiatives with dependencies on others\n"
            "   - **Low Complexity**: Self-contained improvements with minimal cross-discipline dependencies\n"
            "   - **Priority Assignment**: Consider execution sequence — address blocking dependencies first\n\n"
            "3. **Phased Roadmap Construction**:\n"
            "   - **Short-term (0–30 days)**: Foundation-building, low-complexity items, People/Process prep\n"
            "   - **Mid-term (30–60 days)**: Medium-complexity initiatives, early technology pilots\n"
            "   - **Long-term (60–90+ days)**: High-complexity initiatives, mature deployments, measurement\n\n"
            "4. **Explicit Output Format**:\n"
            "   For each phase, structure as:\n"
            "   ```\n"
            "   ### [Phase Name] ([Days])\n"
            "   \n"
            "   #### Initiatives\n"
            "   - **[Initiative Name]** (People | Process | Technology | Multi-disciplinary)\n"
            "     - Objective: [1–2 lines]\n"
            "     - Dependencies: [blocking factors from other disciplines]\n"
            "     - Effort: Low | Medium | High\n"
            "     - Owner: [Role]\n"
            "     - Success Metric: [measurable outcome]\n"
            "   ```\n\n"
            "5. **Cross-Phase Dependency Callout**:\n"
            "   After the phased roadmap, add a section:\n"
            "   ```\n"
            "   ### Critical Path & Interdependencies\n"
            "   \n"
            "   | Initiative | Blocks | Blocked By | Discipline | Risk |\n"
            "   |---|---|---|---|---|\n"
            "   ```\n\n"
            "### NO skipping this reasoning\n"
            "- Do NOT produce a flat list of activities.\n"
            "- Do NOT ignore People and Process when planning Technology initiatives.\n"
            "- Do NOT reorder phases without explicitly justifying priority shifts via interdependencies.\n"
            "- Always show your reasoning about which initiatives must come first."
        )
        messages.append({"role": "system", "content": roadmap_sys})

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
    # diagram_path, tobe_mermaid_path, eval_score must NOT reach the LLM API.
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
    asis_diagram_data: str | None = None,
    tobe_diagram_data: str | None = None,
) -> dict[str, Any]:
    """Run the LangGraph-based Graph-RAG chain for one user turn.

    For multi-turn conversations, pass diagram data from the prior turn
    so it's reused across the conversation without re-loading.

    Args:
        user_message: Current user query
        history: Conversation history
        excel_path: Path to QODE questionnaire Excel
        chroma_path: Path to ChromaDB vector store
        graph_path: Path to knowledge graph
        stream: Whether to stream tokens
        asis_diagram_data: Pre-loaded As-Is DOT graph from prior turn (optional)
        tobe_diagram_data: Pre-loaded To-Be DOT graph from prior turn (optional)

    Returns a dict with keys:
      - ``text``         : full reply string (stream=False) or ""
      - ``stream``       : token iterator (stream=True) or None
      - ``diagram_path`` : PNG/DOT path or None
      - ``diagram_type`` : "process" | "people" | "technology" | None
      - ``mode``         : "asis" | "principles"
      - ``eval_score``   : float 0-1 or None
      - ``asis_diagram_data`` : As-Is DOT data (for passing to next turn)
      - ``tobe_diagram_data`` : To-Be DOT data (for passing to next turn)
    """
    import time as _time
    from .token_counter import get_usage as _get_usage
    from .token_cache import get_metrics as _get_cache_metrics

    if history is None:
        history = []

    tracer = get_tracer()
    _t0 = _time.monotonic()

    initial_state: AgentState = {
        "user_message": user_message,
        "history": history,
        "excel_path": excel_path,
        "chroma_path": chroma_path,
        "graph_path": graph_path,
        "stream": stream,
        "asis_diagram_data": asis_diagram_data,
        "tobe_diagram_data": tobe_diagram_data,
    }

    with tracer.trace(
        "run_chain",
        input={
            "query_preview": user_message[:120],
            "stream": stream,
            "history_turns": len(history),
        },
    ) as root_span:
        if _COMPILED_GRAPH is not None:
            try:
                final_state: AgentState = _COMPILED_GRAPH.invoke(initial_state)
            except Exception as exc:
                logger.error("LangGraph execution failed, falling back: %s", exc)
                root_span.set_error(str(exc))
                final_state = _fallback_run(initial_state)
        else:
            final_state = _fallback_run(initial_state)

        _total_ms = round((_time.monotonic() - _t0) * 1000, 1)
        _usage    = _get_usage()
        _cache    = _get_cache_metrics()
        _has_error = bool(final_state.get("error"))

        # ── Functional metrics ────────────────────────────────────────────
        # Encode categorical values as numeric scores Langfuse can chart.
        # Intent: process=1 people=2 technology=3 general=0
        _intent_map = {"general": 0, "process": 1, "people": 2, "technology": 3}
        _intent_val = _intent_map.get(final_state.get("intent", "general"), 0)

        _functional: dict[str, float] = {
            "intent_code":      float(_intent_val),           # 0–3
            "is_gap_analysis":  float(bool(final_state.get("is_gap_analysis", False))),
            "is_asis_request":  float(bool(final_state.get("is_asis", False))),
            "has_diagram":      float(bool(final_state.get("diagram_path") or final_state.get("tobe_mermaid_path"))),
            "has_error":        float(_has_error),
        }
        if final_state.get("eval_score") is not None:
            _functional["faithfulness"] = float(final_state["eval_score"])

        # ── Non-functional metrics ────────────────────────────────────────
        _nonfunctional: dict[str, float] = {
            "total_latency_ms":      _total_ms,
            "prompt_tokens":         float(_usage.last_call_prompt),
            "completion_tokens":     float(_usage.last_call_completion),
            "session_total_tokens":  float(_usage.total_tokens),
            "session_cost_inr":      float(_usage.total_cost_inr),
            "cache_hit_rate":        float(_cache.hit_rate),
            "cache_hits":            float(_cache.hits),
            "cache_misses":          float(_cache.misses),
        }

        tracer.log_scores({**_functional, **_nonfunctional})

        # ── Root span summary ─────────────────────────────────────────────
        root_span.set_output({
            "intent": final_state.get("intent"),
            "diagram_type": final_state.get("diagram_type"),
            "mode": final_state.get("mode", "principles"),
            "eval_score": final_state.get("eval_score"),
            "has_error": _has_error,
            "total_latency_ms": _total_ms,
            "session_total_tokens": _usage.total_tokens,
            "session_cost_inr": round(_usage.total_cost_inr, 4),
            "cache_hit_rate": round(_cache.hit_rate, 3),
        })
        if _has_error:
            root_span.set_error(final_state["error"])

    return {
        "text": final_state.get("reply_text", ""),
        "stream": final_state.get("reply_stream"),
        "thinking_text": final_state.get("thinking_text", ""),
        "diagram_path": final_state.get("diagram_path"),
        "tobe_mermaid_path": final_state.get("tobe_mermaid_path"),
        "diagram_type": final_state.get("diagram_type"),
        "mode": final_state.get("mode", "principles"),
        "eval_score": final_state.get("eval_score"),
        "asis_diagram_data": final_state.get("asis_diagram_data"),
        "tobe_diagram_data": final_state.get("tobe_diagram_data"),
        "report_images": final_state.get("report_images"),
    }


def _fallback_run(state: AgentState) -> AgentState:
    """Direct execution fallback when LangGraph is not available."""
    state = _node_route(state)
    # All requests (As-Is and To-Be) go through load_asis → principles
    state = _node_load_asis(state)
    return _node_principles(state)
