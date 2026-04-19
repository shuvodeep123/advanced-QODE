"""
chain.py — Intent detection + RAG chain orchestration for advanced-QODE.

Public API
----------
    run_chain(
        user_message  : str,
        history       : list[dict],
        excel_path    : str | None = None,
        chroma_path   : str = "./chroma_db",
        stream        : bool = False,
    ) -> dict

Returns a dict with keys:
    "text"         : str   — the LLM reply text (populated when stream=False)
    "stream"       : Iterator[str] | None — token stream (when stream=True)
    "diagram_path" : str | None — path to generated PNG, or None
    "diagram_type" : str | None — "process" | "people" | "technology" | None
"""

from __future__ import annotations

import re
from typing import Iterator

from . import llm_client
from .retriever import retrieve
from .diagram_executor import run as run_diagram

# ---------------------------------------------------------------------------
# Intent detection
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

_GENERATE_KEYWORDS = [
    "create", "generate", "build", "produce", "make", "draw", "show",
    "render", "display", "visualise", "visualize", "diagram",
]


def detect_intent(query: str) -> str:
    """Return 'process', 'people', 'technology', or 'general'.

    Uses simple keyword matching on the lower-cased query.
    """
    lower = query.lower()
    scores: dict[str, int] = {"process": 0, "people": 0, "technology": 0}
    for intent, keywords in _INTENT_PATTERNS:
        for kw in keywords:
            if kw in lower:
                scores[intent] += 1
    best_intent = max(scores, key=lambda k: scores[k])
    if scores[best_intent] == 0:
        return "general"
    return best_intent


def _wants_diagram(query: str) -> bool:
    """Return True when the query explicitly requests a diagram be generated."""
    lower = query.lower()
    return any(kw in lower for kw in _GENERATE_KEYWORDS)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert DevSecOps consultant specializing in the advanced-QODE framework \
(Quality & Optimization of DevSecOps Engineering).  advanced-QODE assesses DevSecOps \
maturity across 9 SDLC pillars and produces three types of Graphviz diagrams:

  1. **Process Network Diagram** — end-to-end SDLC process flow with critical-path analysis.
  2. **People Diagram** — team-role collaboration and handover map.
  3. **Technology Diagram** — automation-tool integration chain.

Your responsibilities:
- Answer questions about DevSecOps maturity, SDLC best practices, and the QODE framework.
- When a user asks to **create / generate** a diagram, confirm the diagram type and \
advise that the diagram is being generated.
- When a user asks how to **optimise** their process, analyse the provided QODE context \
and recommend improvements using DORA metrics, lead-time reduction, and automation.
- Always ground your answers in the retrieved context provided below.
- Be concise, practical, and focused on actionable insights.
"""


def _build_messages(
    user_message: str,
    history: list[dict],
    context_chunks: list[dict],
) -> list[dict]:
    """Compose the full message list for the LLM."""
    # Build context block from retrieved chunks
    context_text = "\n\n".join(
        f"[Context {i+1}] {chunk['text']}"
        for i, chunk in enumerate(context_chunks)
    )

    system_content = _SYSTEM_PROMPT
    if context_text:
        system_content += (
            "\n\n---\n## Retrieved QODE Context\n\n" + context_text
        )

    messages: list[dict] = [{"role": "system", "content": system_content}]

    # Add the last 6 history turns to preserve conversation context
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
    stream: bool = False,
) -> dict:
    """Run the full RAG chain for a single user turn.

    Args:
        user_message: The latest message from the user.
        history:      Previous ``[{"role": ..., "content": ...}]`` turns.
        excel_path:   Path to the uploaded QODE questionnaire (may be None).
        chroma_path:  Path to the ChromaDB persistence directory.
        stream:       If True, return a token-stream iterator instead of a
                      blocking string.

    Returns:
        A dict with keys:
          - ``"text"``         : full reply (``stream=False``) or ``""``
          - ``"stream"``       : token iterator (``stream=True``) or ``None``
          - ``"diagram_path"`` : path to generated PNG or ``None``
          - ``"diagram_type"`` : detected diagram type or ``None``
    """
    if history is None:
        history = []

    # 1. Detect intent
    intent = detect_intent(user_message)
    wants_diagram = _wants_diagram(user_message)

    # 2. Retrieve context from ChromaDB
    filter_type = intent if intent != "general" else None
    context_chunks = retrieve(
        query=user_message,
        k=5,
        diagram_type=filter_type,
        chroma_path=chroma_path,
    )

    # 3. Build LLM messages
    messages = _build_messages(user_message, history, context_chunks)

    # 4. Generate diagram if requested
    diagram_path: str | None = None
    if wants_diagram and intent != "general":
        diagram_path = run_diagram(
            diagram_type=intent,
            excel_path=excel_path,
        )

    # 5. Call LLM
    result: dict = {
        "text": "",
        "stream": None,
        "diagram_path": diagram_path,
        "diagram_type": intent if intent != "general" else None,
    }

    if stream:
        result["stream"] = llm_client.chat_stream(messages)
    else:
        result["text"] = llm_client.chat(messages)

    return result
