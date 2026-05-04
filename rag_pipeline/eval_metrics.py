"""
eval_metrics.py — RAG evaluation scoring for advanced-QODE.

Provides lightweight faithfulness and relevancy scoring that:
  - Uses RAGAS when available (full semantic scoring).
  - Falls back to a lexical overlap heuristic when RAGAS / OpenAI are not configured.
  - Is always safe to call — returns a float in [0, 1] or None on hard failure.

Public API
----------
    score_response(query, answer, context) -> float | None
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lexical overlap heuristic (always available, zero-dependency fallback)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b[a-z]{3,}\b", text.lower()))


def _lexical_faithfulness(answer: str, context: str) -> float:
    """Fraction of answer tokens present in the context (recall over answer)."""
    ans_tokens = _tokenize(answer)
    if not ans_tokens:
        return 0.0
    ctx_tokens = _tokenize(context)
    overlap = ans_tokens & ctx_tokens
    return len(overlap) / len(ans_tokens)


def _lexical_relevancy(query: str, answer: str) -> float:
    """Fraction of query tokens present in the answer."""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 1.0
    ans_tokens = _tokenize(answer)
    overlap = q_tokens & ans_tokens
    return len(overlap) / len(q_tokens)


def _combined_lexical_score(query: str, answer: str, context: str) -> float:
    faith = _lexical_faithfulness(answer, context)
    relev = _lexical_relevancy(query, answer)
    return round((faith + relev) / 2, 4)


# ---------------------------------------------------------------------------
# RAGAS scoring (optional, requires ragas + langchain + OpenAI key)
# ---------------------------------------------------------------------------

def _ragas_score(query: str, answer: str, context: str) -> float | None:
    try:
        from ragas import evaluate  # type: ignore[import]
        from ragas.metrics import faithfulness, answer_relevancy  # type: ignore[import]
        from datasets import Dataset  # type: ignore[import]

        dataset = Dataset.from_dict(
            {
                "question": [query],
                "answer": [answer],
                "contexts": [[context]],
            }
        )
        result = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
        faith_val = result["faithfulness"]
        relev_val = result["answer_relevancy"]
        return round((faith_val + relev_val) / 2, 4)
    except Exception as exc:
        logger.debug("RAGAS scoring skipped: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_response(
    query: str,
    answer: str,
    context: str,
    prefer_ragas: bool = True,
) -> float:
    """Score an LLM response for faithfulness and relevancy.

    Tries RAGAS first (when *prefer_ragas* is True and dependencies exist),
    then falls back to lexical overlap scoring.

    Returns:
        Float in [0, 1]. Higher is better. Returns 0.0 on unexpected error.
    """
    if not answer or not context:
        return 0.0

    try:
        if prefer_ragas:
            ragas_val = _ragas_score(query, answer, context)
            if ragas_val is not None:
                return ragas_val

        return _combined_lexical_score(query, answer, context)
    except Exception as exc:
        logger.error("score_response failed: %s", exc)
        return 0.0


