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
MODEL = os.environ.get("HF_MODEL", "claude-opus-4-7")


def _validate_config(api_key: str | None) -> None:
    """Raise a clear error if the API key is missing or looks wrong."""
    if not api_key:
        raise EnvironmentError(
            "API token is not configured. "
            "Set HF_TOKEN in .env or export HF_TOKEN=<your-token>."
        )
    if api_key.startswith("hf_"):
        raise EnvironmentError(
            "HF_TOKEN starts with 'hf_' — this is a raw HuggingFace token and will "
            "be rejected by the LiteLLM proxy.  Please set HF_TOKEN to the 'sk-' "
            "virtual key issued by your LiteLLM / KodeKloud endpoint in .env."
        )


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Return a cached OpenAI client pointed at the configured endpoint.

    Reads HF_TOKEN and HF_BASE_URL fresh from the environment on every
    cold-start so that .env changes take effect without restarting Python.
    """
    global _client
    if _client is None:
        api_key = os.environ.get("HF_TOKEN")
        base_url = os.environ.get("HF_BASE_URL", "https://api.ai.kodekloud.com/v1")
        _validate_config(api_key)
        _client = OpenAI(api_key=api_key, base_url=base_url)
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
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
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
