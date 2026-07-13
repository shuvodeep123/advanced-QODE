"""
langfuse_tracer.py — Langfuse v4 observability wrapper for advanced-QODE.

Provides a thin, production-safe tracer that:
  - Integrates with Langfuse v4 when LANGFUSE_SECRET_KEY + LANGFUSE_PUBLIC_KEY are set.
  - Falls back to a no-op tracer when Langfuse is not configured (zero-dependency).
  - Exposes a context-manager span API so call-sites are identical in both modes.
  - Captures latency_ms, errors, metadata, and eval scores per trace.

"""

from __future__ import annotations

import logging
import os
import time
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

    def set_error(self, error: str) -> None:
        pass

    def set_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_inr: float,
    ) -> None:
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

    def log_scores(self, scores: dict[str, float], trace_id: str | None = None) -> None:
        pass

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Real span wrapper — adapts Langfuse v4 OTel-based context manager
# ---------------------------------------------------------------------------
class _LangfuseSpan:
    """Wraps a live Langfuse v4 span observation; records latency + errors on exit."""

    def __init__(self, lf: Any, name: str) -> None:
        self._lf = lf
        self._name = name
        self._start = time.monotonic()

    def set_output(self, output: Any) -> None:  # noqa: ANN401
        try:
            self._lf.update_current_span(output=output)
        except Exception:
            pass

    def set_metadata(self, metadata: dict) -> None:
        try:
            self._lf.update_current_span(metadata=metadata)
        except Exception:
            pass

    def set_error(self, error: str) -> None:
        try:
            self._lf.update_current_span(
                output={"error": error},
                level="ERROR",
                status_message=error,
            )
        except Exception:
            pass

    def set_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_inr: float,
    ) -> None:
        """Attach model + token usage + cost to the current span."""
        try:
            self._lf.update_current_span(
                model=model,
                usage={
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                    "unit": "TOKENS",
                },
                metadata={
                    "cost_inr": cost_inr,
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
            )
        except Exception:
            pass

    def _finalize(self, exc_type: type | None, exc_val: BaseException | None) -> None:
        latency_ms = round((time.monotonic() - self._start) * 1000, 1)
        # Suppress Langfuse's OTel "no active span" warning — it fires when an
        # exception unwinds the context before _finalize runs; data is still flushed.
        _lf_logger = logging.getLogger("langfuse")
        _prev_level = _lf_logger.level
        _lf_logger.setLevel(logging.ERROR)
        try:
            if exc_type is not None:
                self._lf.update_current_span(
                    metadata={"latency_ms": latency_ms, "error": str(exc_val)},
                    level="ERROR",
                    status_message=str(exc_val),
                )
            else:
                self._lf.update_current_span(metadata={"latency_ms": latency_ms})
        except Exception:
            pass
        finally:
            _lf_logger.setLevel(_prev_level)


# ---------------------------------------------------------------------------
# Langfuse v4 tracer
# ---------------------------------------------------------------------------
class _LangfuseTracer:
    def __init__(self) -> None:
        from langfuse import Langfuse  # type: ignore[import]

        self._lf = Langfuse(
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            host=os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
        )
        self._lf.auth_check()

    @contextmanager
    def trace(
        self, name: str, input: dict | None = None  # noqa: A002
    ) -> Generator[_LangfuseSpan, None, None]:
        """Open a Langfuse trace (as_type='chain') and yield a span wrapper.

        Latency is measured from context entry to exit.
        Exceptions are captured as ERROR level on the span but re-raised.
        """
        _input = input or {}
        span = _LangfuseSpan(self._lf, name=name)

        obs_ctx = self._lf.start_as_current_observation(
            name=name,
            as_type="chain",
            input=_input,
        )
        with obs_ctx:
            exc_type_ref: type | None = None
            exc_val_ref: BaseException | None = None
            try:
                yield span
            except Exception as exc:
                exc_type_ref = type(exc)
                exc_val_ref = exc
                raise
            finally:
                # finalize while obs_ctx still active so update_current_span has a context
                span._finalize(exc_type_ref, exc_val_ref)

    def log_score(self, name: str, value: float, trace_id: str | None = None) -> None:
        try:
            tid = trace_id or self._lf.get_current_trace_id()
            if tid:
                self._lf.create_score(trace_id=tid, name=name, value=value)
        except Exception as exc:
            logger.warning("log_score failed: %s", exc)

    def log_scores(self, scores: dict[str, float], trace_id: str | None = None) -> None:
        """Log multiple numeric scores to the current (or specified) trace at once."""
        try:
            tid = trace_id or self._lf.get_current_trace_id()
            if tid:
                for name, value in scores.items():
                    self._lf.create_score(trace_id=tid, name=name, value=value)
        except Exception as exc:
            logger.warning("log_scores failed: %s", exc)

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
            logger.info(
                "Langfuse tracer initialised (host=%s).",
                os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            )
        except Exception as exc:
            logger.warning("Langfuse init failed, using no-op tracer: %s", exc)
            _tracer_instance = _NoOpTracer()
    else:
        logger.debug("Langfuse keys not set — using no-op tracer.")
        _tracer_instance = _NoOpTracer()

    return _tracer_instance


def reset_tracer() -> None:
    """Force re-initialisation on next get_tracer() call (useful in tests)."""
    global _tracer_instance
    _tracer_instance = None
