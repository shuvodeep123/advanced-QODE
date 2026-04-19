"""
llm_client.py — KodeKloud OpenAI-compatible LLM wrapper.

Provides:
    chat(messages)        -> str          (blocking)
    chat_stream(messages) -> Iterator[str] (streaming tokens)
"""

from __future__ import annotations

import os
from typing import Iterator

from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration — override via environment variables when desired.
# ---------------------------------------------------------------------------
_API_KEY = os.environ.get("KODEKLOUD_API_KEY") or "sk-bjhEx0Xa0dCm8kOF0hzUHg"
_BASE_URL = os.environ.get("KODEKLOUD_BASE_URL", "https://api.ai.kodekloud.com/v1")
MODEL = os.environ.get("KODEKLOUD_MODEL", "anthropic/claude-sonnet-4.5")


def _validate_config() -> None:
    """Raise a clear error if the API key is missing."""
    if not _API_KEY:
        raise EnvironmentError(
            "KodeKloud API key is not configured.  "
            "Set the KODEKLOUD_API_KEY environment variable."
        )

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Return a cached OpenAI client pointed at the KodeKloud endpoint."""
    global _client
    if _client is None:
        _validate_config()
        _client = OpenAI(api_key=_API_KEY, base_url=_BASE_URL)
    return _client


def chat(messages: list[dict], model: str = MODEL) -> str:
    """Send *messages* to the LLM and return the full response text.

    Args:
        messages: OpenAI-format message list, e.g.
                  [{"role": "system", "content": "..."}, {"role": "user", ...}]
        model:    Model identifier (default: ``MODEL``).

    Returns:
        The assistant's reply as a plain string.
    """
    response = _get_client().chat.completions.create(
        model=model,
        messages=messages,
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
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
