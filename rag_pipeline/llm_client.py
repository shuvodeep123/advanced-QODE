"""
llm_client.py — HuggingFace OpenAI-compatible LLM wrapper.

Provides:
    chat(messages)        -> str          (blocking)
    chat_stream(messages) -> Iterator[str] (streaming tokens)
"""

from __future__ import annotations

import os
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from .token_counter import record_call, estimate_tokens

# override=True ensures the .env file always wins over stale shell exports
# (e.g. an old hf_ token that was exported in a previous session).
load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Configuration — resolved lazily inside _get_client() so that a
# load_dotenv(override=True) call anywhere before the first LLM request
# is always picked up, even if this module was imported earlier.
# ---------------------------------------------------------------------------
MODEL = os.environ.get("HF_MODEL")


def _extract_thinking(text: str) -> tuple[str, str]:
    """Extract ``<think>…</think>`` block from an LLM reply.

    Many reasoning models (GLM, Qwen, DeepSeek-R1) emit a chain-of-thought
    inside ``<think>…</think>`` tags before the actual answer.  This helper
    separates the two so the UI can display them independently.

    Args:
        text: Raw LLM output, potentially containing ``<think>`` tags.

    Returns:
        ``(thinking, clean_text)`` where *thinking* is the inner content of
        the first ``<think>`` block (empty string if absent) and *clean_text*
        is the remaining text with the ``<think>`` block stripped.
    """
    import re as _re
    m = _re.search(r"<think>(.*?)</think>", text, _re.DOTALL | _re.IGNORECASE)
    if not m:
        return "", text.strip()
    thinking = m.group(1).strip()
    clean = (text[: m.start()] + text[m.end() :]).strip()
    return thinking, clean


def _validate_config(api_key: str | None) -> None:
    """Raise a clear error if the API key is missing."""
    if not api_key:     
        raise EnvironmentError(
            "API token is not configured. "
            "Set HF_TOKEN in .env or export HF_TOKEN=<your-token>."
        )


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Return a cached OpenAI client pointed at the configured endpoint.

    Reads HF_TOKEN and HF_BASE_URL fresh from the environment on every
    cold-start so that .env changes take effect without restarting Python"""
    global _client
    if _client is None:
        api_key = os.environ.get("HF_TOKEN")
        base_url = os.environ.get("HF_BASE_URL")
        _validate_config(api_key)
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def chat(messages: list[dict], model: str = MODEL) -> str:
    """Send *messages* to the LLM and return the full response text."""
    response = _get_client().chat.completions.create(
        model=model,
        messages=messages,
    )
    # Record exact usage from the response object (always present for non-streaming)
    usage = getattr(response, "usage", None)
    if usage:
        record_call(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            model=model,
        )
    else:
        # Fallback: estimate prompt tokens; completion approximated from reply length
        reply = response.choices[0].message.content or ""
        record_call(
            prompt_tokens=estimate_tokens(messages, model),
            completion_tokens=estimate_tokens([{"role": "assistant", "content": reply}], model),
            model=model,
        )
    return response.choices[0].message.content


def chat_stream(messages: list[dict], model: str = MODEL) -> Iterator[str]:
    """Stream tokens from the LLM.

    Yields individual text chunks as they arrive, suitable for use with
    ``st.write_stream()`` in Streamlit.

    Args:
        messages: OpenAI-format message list.
        model:    Model identifier (default: ``MODEL``).

    Yields:
        String fragments of the assistant reply.
    """
    stream = _get_client().chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )
    # Estimate prompt tokens upfront (streaming usage arrives only at the final chunk)
    estimated_prompt = estimate_tokens(messages, model)
    completion_text: list[str] = []
    usage_recorded = False
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            completion_text.append(delta.content)
            yield delta.content
        # OpenAI streaming: usage is sent in the final chunk when stream_options used
        usage = getattr(chunk, "usage", None)
        if usage and not usage_recorded:
            record_call(
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
                model=model,
            )
            usage_recorded = True
    # Fallback if the endpoint did not return usage in the stream
    if not usage_recorded:
        record_call(
            prompt_tokens=estimated_prompt,
            completion_tokens=estimate_tokens(
                [{"role": "assistant", "content": "".join(completion_text)}], model
            ),
            model=model,
        )
