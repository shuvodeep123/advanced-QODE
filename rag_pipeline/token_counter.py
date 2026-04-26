"""
token_counter.py — Real-time token usage tracking for advanced-QODE.

Tracks prompt tokens, completion tokens, and total tokens across all LLM
calls in a session.  The counter is backed by a thread-safe in-process store
that is kept in sync with Streamlit session state on every update so the UI
reflects usage immediately after each request.

Token counting strategy
-----------------------
1. **Actual usage** (preferred): read ``usage`` from the OpenAI response object
   for non-streaming calls — this is exact.
2. **tiktoken estimation** (streaming / fallback): count tokens in the message
   list with ``tiktoken`` when the response has no usage field.  Falls back to
   a simple whitespace-split heuristic if ``tiktoken`` is not installed.

Token budget
------------
Set ``TOKEN_BUDGET`` in the environment (or ``.env``) to the total tokens
allotted for the session.  Defaults to 100 000.

Public API
----------
    TokenUsage                      — dataclass: prompt / completion / total
    get_usage()  -> TokenUsage      — current session totals
    record_call(prompt_tokens, completion_tokens, model)  — add a call's usage
    reset()                         — zero all counters (new session)
    estimate_tokens(messages)       — count tokens in an OpenAI message list
    pct_used(budget)                — float 0–100
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token budget — override via TOKEN_BUDGET env var or .env
# ---------------------------------------------------------------------------
DEFAULT_BUDGET: int = int(os.environ.get("TOKEN_BUDGET", "248000"))

# ---------------------------------------------------------------------------
# Thread-safe usage store
# ---------------------------------------------------------------------------
_lock = threading.Lock()


@dataclass
class TokenUsage:
    """Snapshot of token consumption for a session."""

    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0
    call_count:        int = 0
    # per-model breakdown  {model_name: total_tokens}
    by_model:          dict[str, int] = field(default_factory=dict)

    def pct_used(self, budget: int = DEFAULT_BUDGET) -> float:
        """Return percentage of budget consumed (0.0 – 100.0)."""
        if budget <= 0:
            return 0.0
        return min(100.0, round(self.total_tokens / budget * 100, 2))


# Module-level mutable instance (one per Python process)
_usage = TokenUsage()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_usage() -> TokenUsage:
    """Return a snapshot copy of current session token usage."""
    with _lock:
        return TokenUsage(
            prompt_tokens=_usage.prompt_tokens,
            completion_tokens=_usage.completion_tokens,
            total_tokens=_usage.total_tokens,
            call_count=_usage.call_count,
            by_model=dict(_usage.by_model),
        )


def record_call(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "unknown",
) -> TokenUsage:
    """Add one LLM call's token counts to the session totals.

    Thread-safe.  Returns the updated snapshot so callers can read immediately.

    Args:
        prompt_tokens:      Tokens consumed by the input messages.
        completion_tokens:  Tokens in the model's reply.
        model:              Model identifier string (for per-model breakdown).

    Returns:
        Updated :class:`TokenUsage` snapshot.
    """
    with _lock:
        _usage.prompt_tokens     += prompt_tokens
        _usage.completion_tokens += completion_tokens
        _usage.total_tokens      += prompt_tokens + completion_tokens
        _usage.call_count        += 1
        _usage.by_model[model]    = (
            _usage.by_model.get(model, 0) + prompt_tokens + completion_tokens
        )
        logger.debug(
            "Token usage recorded — prompt=%d completion=%d total=%d (session=%d)",
            prompt_tokens, completion_tokens,
            prompt_tokens + completion_tokens, _usage.total_tokens,
        )
        return TokenUsage(
            prompt_tokens=_usage.prompt_tokens,
            completion_tokens=_usage.completion_tokens,
            total_tokens=_usage.total_tokens,
            call_count=_usage.call_count,
            by_model=dict(_usage.by_model),
        )


def reset() -> None:
    """Zero all counters (call at the start of a new session)."""
    with _lock:
        _usage.prompt_tokens     = 0
        _usage.completion_tokens = 0
        _usage.total_tokens      = 0
        _usage.call_count        = 0
        _usage.by_model.clear()
    logger.info("Token counter reset.")


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------

def _tiktoken_count(text: str, model: str) -> int:
    """Encode *text* with tiktoken and return the token count."""
    try:
        import tiktoken  # type: ignore[import]
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Heuristic fallback: ~0.75 tokens per word (GPT-style estimate)
        return max(1, int(len(text.split()) / 0.75))


def estimate_tokens(
    messages: Sequence[dict],
    model: str = "gpt-4",
) -> int:
    """Estimate prompt token count for an OpenAI message list.

    Uses tiktoken when available, falls back to a whitespace heuristic.
    Adds the standard per-message overhead (4 tokens/message, 2 for reply primer).

    Args:
        messages: OpenAI-format message list.
        model:    Model name used for tiktoken encoding selection.

    Returns:
        Estimated integer token count.
    """
    total = 0
    per_message_overhead = 4   # role + content delimiters
    for msg in messages:
        total += per_message_overhead
        content = msg.get("content") or ""
        total += _tiktoken_count(content, model)
    total += 2   # reply primer
    return total
