"""
langfuse_tracer.py — Langfuse observability wrapper for advanced-QODE.

Provides a thin, production-safe tracer that:
  - Integrates with Langfuse when LANGFUSE_SECRET_KEY + LANGFUSE_PUBLIC_KEY are set.
  - Falls back to a no-op tracer when Langfuse is not configured (zero-dependency).
  - Exposes a context-manager span API so call-sites are identical in both modes.

Usage:
    tracer = get_tracer()
    with tracer.trace("my_step", input={"key": "val"}) as span:
        result = do_work()
        span.set_output({"result": result})
    tracer.log_score("faithfulness", 0.92)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# No-op span — used when Langfuse is absent
# ---------------------------------------------------------------------------
class _NoOpSpan:
    def set_output(self, output: Any) -> None:  # noqa: ANN401
        pass

    def set_metadata(self, metadata: dict) -> None:
        pass


# ---------------------------------------------------------------------------
# No-op tracer
# ---------------------------------------------------------------------------
class _NoOpTracer:
    @contextmanager
    def trace(
        self, name: str, input: dict | None = None  # noqa: A002
    ) -> Generator[_NoOpSpan, None, None]:
        yield _NoOpSpan()

    def log_score(self, name: str, value: float, trace_id: str | None = None) -> None:
        pass

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Langfuse tracer (real)
# ---------------------------------------------------------------------------
class _LangfuseTracer:
    def __init__(self) -> None:
        from langfuse import Langfuse  # type: ignore[import]

        self._lf = Langfuse(
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        self._current_trace_id: str | None = None

    @contextmanager
    def trace(
        self, name: str, input: dict | None = None  # noqa: A002
    ) -> Generator[Any, None, None]:
        trace = self._lf.trace(name=name, input=input or {})
        self._current_trace_id = trace.id
        span = trace.span(name=name)
        try:
            yield span
        finally:
            span.end()

    def log_score(self, name: str, value: float, trace_id: str | None = None) -> None:
        tid = trace_id or self._current_trace_id
        if tid:
            self._lf.score(trace_id=tid, name=name, value=value)

    def flush(self) -> None:
        self._lf.flush()


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------
_tracer_instance: _NoOpTracer | _LangfuseTracer | None = None


def get_tracer() -> _NoOpTracer | _LangfuseTracer:
    """Return the singleton tracer. Initialises once per process."""
    global _tracer_instance
    if _tracer_instance is not None:
        return _tracer_instance

    if os.environ.get("LANGFUSE_SECRET_KEY") and os.environ.get("LANGFUSE_PUBLIC_KEY"):
        try:
            _tracer_instance = _LangfuseTracer()
            logger.info("Langfuse tracer initialised (host=%s).", os.environ.get("LANGFUSE_HOST", "cloud"))
        except Exception as exc:
            logger.warning("Langfuse init failed, using no-op tracer: %s", exc)
            _tracer_instance = _NoOpTracer()
    else:
        logger.debug("Langfuse keys not set — using no-op tracer.")
        _tracer_instance = _NoOpTracer()

    return _tracer_instance
